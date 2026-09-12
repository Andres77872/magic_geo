"""Isolated applicability/selection replay, not full-world climate validation.

Native unit worlds below are synthetic subsystem fixtures with prescribed
monthly source inputs. Archived fixtures retain actual accepted climate sources
but regenerate only environment/settlement/route/political stages.
"""
from copy import deepcopy
import gzip
import hashlib
import json
import math
from pathlib import Path

import pytest

from magic_geo.settlement_routes import enrich_world_with_settlement_route_models, _candidate_count
from magic_geo.settlement_climate_support import seasonal_settlement_inputs, SETTLEMENT_CLIMATE_SUPPORT_MODEL
from magic_geo.political_geography import enrich_world_with_political_geography_models
from magic_geo.cli.validators.settlement import _validate_settlement_selection, _validate_route_network
from magic_geo.cli.validators.political import _validate_political_regions
from magic_geo.cli.validators.settlement_climate import replay_settlement_climate

FIXTURES = Path(__file__).parent / "fixtures/settlement_climate_support"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text())


def _retained_bytes(label):
    entry = MANIFEST[label]
    raw = (FIXTURES / entry["fixture"]).read_bytes()
    if entry["fixture"].endswith(".gz"):
        assert hashlib.sha256(raw).hexdigest() == entry["gzip_sha256"]
        raw = gzip.decompress(raw)
    assert hashlib.sha256(raw).hexdigest() == entry["sha256"]
    return raw


CASES = json.loads(_retained_bytes("native-unit-worlds"))
ARCHIVES = {name: json.loads(_retained_bytes(name))
    for name in ("earthlike_seed", "verdant_hothouse", "young_volcanic")}
CHECKERS = (_validate_settlement_selection, _validate_route_network, _validate_political_regions)


def enrich(world):
    enrich_world_with_settlement_route_models(world)
    enrich_world_with_political_geography_models(world)
    return world


def validate(checker, world):
    return checker(world, world["summary"], {c["id"]: c for c in world["cells"]})


def synthetic(name="supported"):
    world = deepcopy(CASES[name])
    if name != "legacy":
        source = ARCHIVES["earthlike_seed"]["seasonal_supported_selection"]
        for key in ("climate_model", "climate_energy_model", "climate_energy_forcing_intervals", "climate_energy_transport_edges", "native_climate_energy_enrichment_model"):
            world[key] = deepcopy(source[key])
        world["climate_energy_balance_records"] = [
            {"cell_id": c["id"], "monthly_mean_temperature_k": [c["settlement_climate_temperature_c"] + 273.15] * 12}
            for c in world["cells"]
        ]
    return world


@pytest.mark.parametrize("name", list(CASES))
@pytest.mark.parametrize("checker", CHECKERS)
def test_native_synthetic_selection_and_source_links(name, checker):
    world = enrich(synthetic(name))
    assert validate(checker, world) == []
    snapshot = deepcopy(world)
    enrich(world)
    assert world == snapshot


@pytest.mark.parametrize("name", list(ARCHIVES))
@pytest.mark.parametrize("branch", ("old_selection_on_same_seasonal_inputs", "seasonal_supported_selection"))
@pytest.mark.parametrize("checker", CHECKERS)
def test_actual_archived_input_selection_and_links(name, branch, checker):
    world = enrich(deepcopy(ARCHIVES[name][branch]))
    assert validate(checker, world) == []


def test_archived_candidate_change_does_not_modify_material():
    expected = {"earthlike_seed": ([8, 76], [8, 76]), "verdant_hothouse": ([88, 76], []), "young_volcanic": ([62], [])}
    for name, branches in ARCHIVES.items():
        before, after = branches["old_selection_on_same_seasonal_inputs"], branches["seasonal_supported_selection"]
        assert ([s["cell_id"] for s in before["settlements"]], [s["cell_id"] for s in after["settlements"]]) == expected[name]
        for old, new in zip(before["cells"], after["cells"]):
            for key in ("fertility", "soil_depth_m", "soil_type", "biome", "landform", "resource", "temperature_c", "temperature_monthly_c", "elevation_m", "sediment_thickness_m"):
                assert old[key] == new[key]
            if new["settlement_climate_supported"]:
                assert old["settlement_score"] == new["settlement_score"]
            else:
                assert new["settlement_score"] == 0


def test_legacy_model_is_byte_equivalent_to_previous_metadata():
    second = synthetic("legacy")
    enrich_world_with_settlement_route_models(second)
    assert _retained_bytes("legacy-enriched") == json.dumps(second, separators=(",", ":")).encode()
    assert second["settlement_selection_model"]["model_type"].endswith("_v2")
    assert "annual_climate_applicability" not in second["settlement_selection_model"]


def test_inside_endpoint_uses_roundtrip_input_instead_of_display_temperature():
    world = enrich(synthetic("inside"))
    assert world["cells"][0]["temperature_c"] == 48
    assert world["cells"][0]["settlement_climate_temperature_c"] == math.nextafter(48, -math.inf)
    assert world["cells"][0]["settlement_climate_supported"] is True
    assert validate(_validate_settlement_selection, world) == []
    endpoint = enrich(synthetic("endpoint"))
    assert all(c["settlement_climate_supported"] is False and c["settlement_score"] == 0 for c in endpoint["cells"])


@pytest.mark.parametrize("value", [-14, math.nextafter(-14, math.inf), math.nextafter(48, -math.inf), 48])
def test_exact_bounds_and_independent_replay(value):
    world = synthetic("hot")
    for cell, record in zip(world["cells"], world["climate_energy_balance_records"]):
        cell["settlement_climate_temperature_c"] = value
        cell["settlement_climate_supported"] = -14 < value < 48
        record["monthly_mean_temperature_k"] = [value + 273.15] * 12
    assert seasonal_settlement_inputs(world) == replay_settlement_climate(world)[1]


@pytest.mark.parametrize("bad", [None, True, "17", [], {}, math.nan, math.inf, -math.inf, 10**1000])
@pytest.mark.parametrize("field", ["settlement_climate_temperature_c", "settlement_climate_supported"])
def test_malformed_input_fails_before_metadata_mutation(bad, field):
    world = enrich(synthetic())
    if field == "settlement_climate_supported" and bad is True:
        bad = False  # A well-typed flag with incorrect applicability is invalid.
    world["cells"][0][field] = bad
    snapshot = json.dumps(world, sort_keys=True)
    with pytest.raises(ValueError):
        enrich_world_with_settlement_route_models(world)
    assert json.dumps(world, sort_keys=True) == snapshot
    for check in CHECKERS:
        assert validate(check, world)


@pytest.mark.parametrize("mutation", [
    lambda w: w["cells"][0].pop("settlement_climate_supported"),
    lambda w: w["cells"][0].pop("settlement_climate_temperature_c"),
    lambda w: w["cells"][0].update(settlement_climate_temperature_c=17.00000001),
    lambda w: w["climate_model"].update(model_type="unknown"),
    lambda w: w["climate_energy_model"].update(model="unknown"),
    lambda w: w.pop("native_climate_energy_enrichment_model"),
    lambda w: w["native_climate_energy_enrichment_model"].update(model="unknown"),
    lambda w: w["climate_energy_balance_records"].pop(),
    lambda w: w["climate_energy_balance_records"].append(deepcopy(w["climate_energy_balance_records"][0])),
    lambda w: w["cells"][0].update(id=1),
])
def test_partial_unknown_or_inconsistent_dependency_fails_closed(mutation):
    world = enrich(synthetic()); mutation(world)
    snapshot = deepcopy(world)
    with pytest.raises(ValueError):
        enrich_world_with_settlement_route_models(world)
    assert world == snapshot
    for checker in CHECKERS:
        assert validate(checker, world)


def test_unsupported_bonus_and_graph_contamination_cannot_be_published():
    world = enrich(synthetic("hot"))
    world["cells"][0]["settlement_score"] = 1
    with pytest.raises(ValueError):
        enrich_world_with_settlement_route_models(world)
    assert validate(_validate_settlement_selection, world)
    cells = [{"id": 0, "neighbors": [1], "settlement_score": .6}, {"id": 1, "neighbors": [0], "settlement_score": 1}]
    assert _candidate_count(cells, {0: 17, 1: 85}) == 1
    # The native unit additionally checks which candidate wins in each mode.


@pytest.mark.parametrize("key,checker", [("route_network_model", _validate_route_network), ("political_region_model", _validate_political_regions)])
def test_wrong_source_model_link_rejected(key, checker):
    world = enrich(synthetic())
    world[key]["source_settlement_model"] = "causal_native_score_local_max_separated_settlement_selection_v2"
    assert validate(checker, world)


def test_independent_metadata_is_not_imported_from_producer():
    world = enrich(synthetic())
    world["settlement_selection_model"]["annual_climate_applicability"]["maximum_temperature_c_exclusive"] = 90
    assert validate(_validate_settlement_selection, world)
    assert SETTLEMENT_CLIMATE_SUPPORT_MODEL["maximum_temperature_c_exclusive"] == 48


def test_legacy_cannot_be_relabelled_by_injected_seasonal_fields():
    world = synthetic("legacy")
    world["cells"][0]["settlement_climate_supported"] = True
    with pytest.raises(ValueError):
        enrich_world_with_settlement_route_models(world)


@pytest.mark.parametrize("field,value", [
    ("temperature_source", "climate_energy_balance_records_monthly_mean_temperature_k"),
    ("temperature_model", "periodic_graybody_storage_conservative_transport_future"),
    ("ownership", "native_temperature_producer"),
])
def test_independent_replay_rejects_contradictory_legacy_identity(field, value):
    world = enrich(synthetic("legacy"))
    world["climate_model"] = {"model_type": "equilibrium_latitude_circulation_climate_v5", field: value}
    with pytest.raises(ValueError):
        seasonal_settlement_inputs(world)
    with pytest.raises(ValueError):
        replay_settlement_climate(world)
    for checker in CHECKERS:
        assert validate(checker, world)


@pytest.mark.parametrize("field,value", [("response_center_c", 17), ("response_half_width_c", 31)])
def test_new_support_metadata_preserves_its_exact_number_types(field, value):
    world = enrich(synthetic())
    world["settlement_selection_model"]["annual_climate_applicability"][field] = value
    assert validate(_validate_settlement_selection, world)


@pytest.mark.parametrize("value", [None, [], 12, "world"])
def test_new_support_helpers_reject_non_mapping_roots(value):
    with pytest.raises(ValueError):
        seasonal_settlement_inputs(value)
    with pytest.raises(ValueError):
        replay_settlement_climate(value)
