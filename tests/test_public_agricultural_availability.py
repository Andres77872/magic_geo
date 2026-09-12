"""Versioned public land-use integration on complete retained current-water worlds."""

from copy import deepcopy

import pytest
from typer.testing import CliRunner

from magic_geo.cli import app
from magic_geo.geo_validation import validate_geo_world
from magic_geo.geo_validation_suite.evaluate import geo_fingerprint
from magic_geo.human_geography_validation import validate_human_geography_replay
from magic_geo.io import write_json
from magic_geo.land_use_availability_validation import (
    LandUseAvailabilityError, validate_land_use_availability, validate_land_use_inputs,
)
from magic_geo.land_use_validation_dispatch import validate_public_land_use
from magic_geo.land_use_zones import enrich_world_with_land_use_zones
from support.agricultural_public_worlds import (
    NATIVE_KEYS, archived_agricultural_world_readonly, current_agricultural_world_readonly,
)


FLAGS = (
    "agricultural_habitat_applicable", "agricultural_climate_supported",
    "agricultural_potential_supported", "mining_surface_applicable",
)
FAILURE = "land use zone model or causal replay invalid"


@pytest.fixture(scope="module")
def current():
    return current_agricultural_world_readonly()


def run_cli(world, tmp_path):
    path = tmp_path / "world.json"
    write_json(path, world)
    return CliRunner().invoke(app, ["validate", "--world", str(path)])


@pytest.mark.parametrize("version", [1, 2])
def test_actual_full_worlds_pass_independent_families_and_public_cli(current, version, tmp_path):
    world = current if version == 2 else archived_agricultural_world_readonly()
    before = deepcopy(world)
    assert validate_public_land_use(world) == (version == 2, [])
    assert validate_land_use_availability(world) == []
    assert validate_human_geography_replay(world) == []
    result = run_cli(world, tmp_path)
    assert result.exit_code == 0, (result.output, repr(result.exception))
    assert world == before


def test_actual_upgrade_and_reenrichment_preserve_native_and_unowned_outputs(current):
    world = deepcopy(current)
    native = {key: world[key] for key in NATIVE_KEYS}
    before = deepcopy(world)
    assert enrich_world_with_land_use_zones(world) is world
    assert world == before
    assert all(world[key] is value for key, value in native.items())
    legacy = archived_agricultural_world_readonly()
    # Neither a new land-use version nor replaying successors changes their own
    # contracts, geology, native temperatures, economic equations, or outputs.
    for key in ("resource_deposits", "commodity_occurrences", "worldbuilding_realism_model",
                "worldbuilding_realism_checks", "economy_histories", "economy_history_model"):
        assert key in legacy and current[key] == legacy[key]
    assert any(c["agricultural_potential_supported"] for c in current["cells"])
    assert any(not c["agricultural_habitat_applicable"] for c in current["cells"])
    assert all(c["agricultural_potential_index"] == 0.0 and c["agricultural_zone_id"] == -1
               for c in current["cells"] if not c["agricultural_potential_supported"])


def test_actual_cold_climate_omits_unsupported_agriculture_but_retains_mining(tmp_path):
    world = current_agricultural_world_readonly("cold")
    assert any(c["agricultural_habitat_applicable"] and not c["agricultural_climate_supported"]
               for c in world["cells"])
    assert world["summary"]["unsupported_terrestrial_agricultural_cell_count"] > 0
    assert world["agricultural_zones"] == []
    assert world["mining_zones"]
    assert all(c["agricultural_potential_index"] == 0.0 and c["agricultural_zone_id"] == -1
               for c in world["cells"] if not c["agricultural_potential_supported"])
    assert validate_human_geography_replay(world) == []
    result = run_cli(world, tmp_path)
    assert result.exit_code == 0, (result.output, repr(result.exception))


@pytest.mark.parametrize("change", ["missing", "summary-missing", "unknown", "null", "typed-coefficient", "summary-only", "legacy-with-flags"])
def test_strict_own_contract_refuses_missing_unknown_partial_or_mixed_declarations(current, change):
    world = deepcopy(current)
    if change == "missing":
        del world["land_use_zone_model"]
        del world["summary"]["land_use_zone_model"]
    elif change == "summary-missing":
        del world["summary"]["land_use_zone_model"]
    elif change == "unknown":
        world["land_use_zone_model"]["model_type"] = "future"
    elif change == "null":
        world["land_use_zone_model"] = None
    elif change == "typed-coefficient":
        world["land_use_zone_model"]["deterministic"] = 1
    elif change == "summary-only":
        del world["land_use_zone_model"]
    else:
        legacy = archived_agricultural_world_readonly()
        world["land_use_zone_model"] = deepcopy(legacy["land_use_zone_model"])
        world["summary"]["land_use_zone_model"] = legacy["summary"]["land_use_zone_model"]
    before = deepcopy(world)
    errors = validate_public_land_use(world)[1]
    assert len(errors) == 1 and errors[0].startswith("land use availability:")
    assert validate_human_geography_replay(world) == [FAILURE]
    assert world == before


@pytest.mark.parametrize("field", [*FLAGS, "agricultural_potential_index", "mining_potential_index", "agricultural_zone_id", "mining_zone_id"])
def test_cell_mirror_forgery_is_replayed_independently_by_human_wrapper(current, field):
    world = deepcopy(current)
    value = world["cells"][0][field]
    world["cells"][0][field] = not value if type(value) is bool else value + 1
    assert validate_human_geography_replay(world) == [FAILURE]


@pytest.mark.parametrize("field", [*(key + "_cell_count" for key in FLAGS),
                                   "agricultural_potential_supported_area_km2",
                                   "unsupported_terrestrial_agricultural_cell_count"])
def test_availability_summary_forgery_is_recounted_by_human_wrapper(current, field):
    world = deepcopy(current)
    world["summary"][field] += 1
    assert validate_human_geography_replay(world) == [FAILURE]


@pytest.mark.parametrize("field,value", [("agricultural_potential_index", None),
                                         ("mining_potential_index", "unavailable"),
                                         ("agricultural_potential_supported", 0)])
def test_v2_public_cli_rejects_bad_mirrors_before_eager_numeric_use(current, field, value, tmp_path):
    world = deepcopy(current)
    world["cells"][0][field] = value
    result = run_cli(world, tmp_path)
    assert result.exit_code == 1, (result.output, repr(result.exception))
    assert "FAIL land use availability:" in result.output
    assert not isinstance(result.exception, (TypeError, ValueError, KeyError))


def test_v1_public_numerical_messages_remain_in_the_historical_block(tmp_path):
    world = deepcopy(archived_agricultural_world_readonly())
    assert validate_public_land_use(world) == (False, [])
    world["cells"][0]["agricultural_potential_index"] = 2.0
    result = run_cli(world, tmp_path)
    assert result.exit_code == 1, (result.output, repr(result.exception))
    assert "FAIL land use zone cell fields invalid" in result.output
    assert "FAIL land use zone model or causal replay invalid" in result.output
    assert "FAIL land use availability:" not in result.output


def test_earlier_water_parent_failure_keeps_priority_over_land_use(current, tmp_path):
    world = deepcopy(current)
    world["aquifer_resource_model"]["model_type"] = "unknown"
    world["cells"][0]["agricultural_potential_index"] = None
    result = run_cli(world, tmp_path)
    assert result.exit_code == 1
    assert "FAIL " in result.output and "aquifer" in result.output
    assert "FAIL land use availability:" not in result.output


def test_actual_geo_retains_legitimate_human_absence():
    world = archived_agricultural_world_readonly("geo_only")
    before = deepcopy(world)
    assert "land_use_zone_model" not in world
    assert not any(any(key in c for key in FLAGS) for c in world["cells"])
    report = validate_geo_world(world, profile="generic")
    assert report["passed"], report
    assert world == before
    # The full-world boundary deliberately requires a published human stage;
    # geography validation above does not invent it.
    assert validate_public_land_use(world)[1] == [
        "land use availability: published land_use_zone_model required"
    ]


@pytest.mark.parametrize("field", FLAGS)
def test_geo_fingerprint_excludes_the_new_human_cell_flags(field):
    world = deepcopy(archived_agricultural_world_readonly("geo_only"))
    before = geo_fingerprint(world)
    world["cells"][0][field] = False
    assert geo_fingerprint(world) == before


@pytest.mark.parametrize("family", ["natural_frontier", "worldbuilding_realism"])
def test_other_human_family_contracts_remain_independent(current, family):
    world = deepcopy(current)
    key = family + "_model"
    world[key]["model_type"] = "unknown"
    message = "natural frontier" if family == "natural_frontier" else "worldbuilding realism"
    assert validate_human_geography_replay(world) == [message + " model or causal replay invalid"]


@pytest.mark.parametrize("published", [False, True], ids=["first-v2-call", "v2-reenrichment"])
@pytest.mark.parametrize("missing", ["neighbors", "reciprocal-neighbors", "resource",
                                     "resource_deposits", "settlements", "routes"])
def test_required_actual_candidate_sources_reject_atomically(current, published, missing):
    world = deepcopy(current if published else archived_agricultural_world_readonly())
    if not published:
        assert validate_land_use_availability(world) == []
        del world["land_use_zone_model"]
        del world["summary"]["land_use_zone_model"]
    cells = {c["id"]: c for c in world["cells"]}
    # Actual source-cell graph: removing 9's outgoing candidate links used to
    # split this agricultural component into three accepted singleton zones.
    assert any(zone["cell_ids"] == [9, 12, 14] for zone in current["agricultural_zones"])
    assert all(n in cells[9]["neighbors"] and 9 in cells[n]["neighbors"] for n in (12, 14))
    # Actual mining candidate: its material/deposit are consumed, and actual
    # settlements/routes contribute nonempty retained zone links.
    assert cells[17]["resource"] == "sedimentary_fuels"
    assert current["cells"][17]["mining_potential_index"] >= .52
    assert any(d["cell_id"] == 17 for d in world["resource_deposits"])
    assert any(z["settlement_ids"] and z["route_ids"] for z in current["agricultural_zones"])
    if missing == "neighbors":
        del cells[9]["neighbors"]
        diagnostic = "neighbors must be nonnegative integer IDs"
    elif missing == "reciprocal-neighbors":
        cells[9]["neighbors"] = [n for n in cells[9]["neighbors"] if n not in (12, 14)]
        diagnostic = "neighbors must be reciprocal"
    elif missing == "resource":
        del cells[17]["resource"]
        diagnostic = "explicit primary resource categorical string required"
    else:
        del world[missing]
        diagnostic = missing + " must be a list"
    before = deepcopy(world)
    identities = {key: value for key, value in world.items() if isinstance(value, (dict, list))}
    cell_objects = list(world["cells"])
    with pytest.raises(LandUseAvailabilityError, match=diagnostic):
        validate_land_use_inputs(world)
    if published:
        errors = validate_land_use_availability(world)
        assert len(errors) == 1 and diagnostic in errors[0]
        assert validate_human_geography_replay(world)[0] == FAILURE
    with pytest.raises(LandUseAvailabilityError, match=diagnostic):
        enrich_world_with_land_use_zones(world)
    assert world == before
    assert all(world[key] is value for key, value in identities.items())
    assert all(a is b for a, b in zip(world["cells"], cell_objects))
