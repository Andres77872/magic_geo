"""Historical species3 mutation controls plus actual E5/species4 public coverage."""
from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path

import pytest
from typer.testing import CliRunner

from magic_geo.cli import app
from magic_geo.geo_validation_subsystems import validate_natural_subsystems
from magic_geo.io import write_json
from magic_geo.species_habitat_validation import validate_species_habitat_support
from magic_geo.species_ranges import _guild_scores, enrich_world_with_species_ranges
from support.ecology_worlds import current_ecology_world_readonly, historical_ecology_world_readonly
from support.prescribed_natural_public_worlds import current_world_readonly
from support.species_stage_worlds import species_parent_world


def species_world(**overrides):
    cell = {
        "id": 0, "area_km2": 100.0, "neighbors": [], "lat_deg": 20.0, "lon_deg": 0.0,
        "is_water": False, "is_lake": True, "is_river": False,
        "water_body_type": "fresh_lake", "biome": "temperate_forest",
        "temperature_c": 18.0, "temperature_monthly_c": [18.0] * 12,
        "precipitation_mm_y": 1000.0, "primary_productivity_index": 1.0,
        "fishery_productivity_index": 1.0, "aquatic_primary_climate_supported": True,
        "fishery_productivity_supported": True,
        "vegetation_biomass_index": 1.0, "species_richness_index": 1.0,
        "forest_growth_index": 1.0, "soil_moisture_index": 1.0,
        "seasonal_aridity_index": 0.45, "ecosystem_disturbance_pressure_index": 0.0,
        "biome_confidence_index": 1.0, "river_channel_width_m": 180.0,
        "river_channel_depth_m": 9.0, "fertility": 0.9,
        "growing_season_months": 12, "soil_organic_matter_fraction": 0.2,
        "reef_growth_index": 0.0, "wetland_extent_index": 0.0, **overrides,
    }
    return enrich_world_with_species_ranges(species_parent_world(cell))


def species_check(world):
    return next(check for check in validate_natural_subsystems(world)
                if check["name"] == "species_range_inverse_links_and_envelopes")


def assert_rejected(world, fragment):
    errors = validate_species_habitat_support(world)
    assert any(fragment in error for error in errors), errors
    check = species_check(world)
    assert check["status"] == "failed"
    assert any(fragment in error for error in check["observed"]["errors"]), check["observed"]


@pytest.mark.parametrize("water_type,is_water,is_lake,is_river,terrestrial,freshwater,marine,mode", [
    ("fresh_lake", False, True, False, False, True, False, "standing_water_required"),
    ("fresh_lake", False, False, True, False, True, False, "standing_water_required"),
    ("ocean", True, False, False, False, False, True, "not_applicable"),
    ("continental_shelf", True, False, True, False, False, True, "not_applicable"),
    ("inland_sea", False, False, False, False, False, True, "not_applicable"),
    ("saline_basin", False, True, True, False, False, False, "not_applicable"),
    ("unknown", False, True, True, False, False, False, "not_applicable"),
    ("unknown", True, False, True, False, False, False, "not_applicable"),
    ("saline_basin", False, False, True, True, False, False, "not_applicable"),
    ("land", False, False, True, True, True, False, "river_inapplicable_omitted"),
    ("land", False, False, False, True, False, False, "not_applicable"),
])
def test_exact_habitat_classification_and_existing_taxonomy(water_type, is_water, is_lake, is_river, terrestrial, freshwater, marine, mode):
    world = species_world(water_body_type=water_type, is_water=is_water, is_lake=is_lake, is_river=is_river)
    cell = world["cells"][0]
    assert cell["species_terrestrial_habitat_eligible"] is terrestrial
    assert cell["species_freshwater_habitat_eligible"] is freshwater
    assert cell["species_marine_habitat_eligible"] is marine
    assert cell["species_freshwater_fishery_input_mode"] == mode
    assert validate_species_habitat_support(world) == []
    assert species_check(world)["passed"]


@pytest.mark.parametrize("temperature,supported", [
    (-18.0, False), (-16.0, False), (-10.0, False), (math.nextafter(-10.0, 0.0), True),
    (0.0, True), (18.0, True), (math.nextafter(38.0, 0.0), True), (38.0, False), (44.0, False),
])
def test_standing_fish_support_independently_checks_raw_climate_despite_true_flags(temperature, supported):
    world = species_world(temperature_c=temperature)
    assert world["cells"][0]["species_freshwater_fish_score_supported"] is supported
    assert validate_species_habitat_support(world) == []
    if not supported:
        world["cells"][0]["species_freshwater_fish_score_supported"] = True
        assert_rejected(world, "species_freshwater_fish_score_supported mismatch")


@pytest.mark.parametrize("temperature,supported", [(-16.0, False), (-11.0, False),
    (math.nextafter(-11.0, 0.0), True), (18.0, True),
    (math.nextafter(37.0, 0.0), True), (37.0, False), (43.0, False)])
def test_marine_own_curve_support_is_distinct_from_supported_resource_fishery(temperature, supported):
    world = species_world(water_body_type="inland_sea", is_lake=False, is_water=True,
                          temperature_c=temperature)
    cell = world["cells"][0]
    assert cell["species_marine_fish_score_supported"] is supported
    assert validate_species_habitat_support(world) == []
    if not supported:
        cell["species_marine_fish_score_supported"] = True
        cell["dominant_species_guild"] = "marine_fish"
        assert_rejected(world, "species_marine_fish_score_supported mismatch")


@pytest.mark.parametrize("field", ["aquatic_primary_climate_supported", "fishery_productivity_supported"])
@pytest.mark.parametrize("value", [False, 1, "true", None])
def test_standing_fish_requires_exact_upstream_true(field, value):
    world = species_world()
    world["cells"][0][field] = value
    # The parent is inconsistent before the child can consume the forged flag.
    assert_rejected(world, field + " mismatch")
    before = deepcopy(world)
    with pytest.raises(ValueError, match="valid ecosystem parents"):
        enrich_world_with_species_ranges(world)
    assert world == before


@pytest.mark.parametrize("field", ["primary_productivity_index", "fishery_productivity_index"])
@pytest.mark.parametrize("value", [None, True, "0.5", [], {}, -0.01, 1.01, float("nan"), float("inf"), 10**500])
def test_unavailable_numeric_standing_input_cannot_keep_supported_flag_or_range(field, value):
    # Mutate an existing healthy witness: the validator must not trust the
    # exported True support flag or silently coerce a sentinel/malformed input.
    world = species_world()
    world["cells"][0][field] = value
    errors = validate_species_habitat_support(world)
    if type(value) in (int, float) and not isinstance(value, bool) and -0.1 <= value <= 1.1:
        assert any("species_freshwater_fish_score_supported mismatch" in error for error in errors), errors
        assert any("dominant guild mismatch" in error for error in errors), errors
    else:
        assert any(f"present {field} must be finite numeric" in error for error in errors), errors


def test_known_zero_productivity_is_not_unavailable():
    world = species_world()
    # Supported local scalar-zero vector, not an upstream-formula prediction.
    world["cells"][0].update(primary_productivity_index=0.0, fishery_productivity_index=0.0)
    enrich_world_with_species_ranges(world)
    assert world["cells"][0]["species_freshwater_fish_score_supported"] is True
    assert validate_species_habitat_support(world) == []


@pytest.mark.parametrize("temperature,supported", [(-100.0, False), (-10.0, False),
    (math.nextafter(-10.0, 0.0), True), (18.0, True),
    (math.nextafter(38.0, 0.0), True), (38.0, False), (100.0, False)])
def test_river_uses_own_thermal_curve_and_finite_primary_without_resource_fishery_dependency(temperature, supported):
    world = species_world(water_body_type="land", is_lake=False, is_river=True,
                          temperature_c=temperature, fishery_productivity_supported=False,
                          aquatic_primary_climate_supported=False, fishery_productivity_index=0.0)
    cell = world["cells"][0]
    assert cell["species_freshwater_fish_score_supported"] is supported
    assert any(record["guild_type"] == "freshwater_fish" for record in world["species_range_records"]) is supported
    assert validate_species_habitat_support(world) == []
    # The fish score does not consume river F. The complete parent contract
    # nevertheless requires its unsupported diagnostic to retain numeric zero.
    score = _guild_scores(cell)["freshwater_fish"]
    cell["fishery_productivity_index"] = 1.0
    assert _guild_scores(cell)["freshwater_fish"] == score
    assert any("unsupported fishery_productivity_index must be numeric zero" in error
               for error in validate_species_habitat_support(world))


def test_river_still_requires_supported_numeric_primary_input():
    world = species_world(water_body_type="land", is_lake=False, is_river=True)
    world["cells"][0]["primary_productivity_index"] = None
    assert any("present primary_productivity_index must be finite numeric" in error
               for error in validate_species_habitat_support(world))


@pytest.mark.parametrize("field", ["primary_productivity_index", "fishery_productivity_index"])
@pytest.mark.parametrize("value", [None, True, "0.5", [], {}, float("nan"), float("inf"), 10**500])
def test_present_productivity_preflight_is_required_even_outside_fish_habitat(field, value):
    world = species_world(water_body_type="land", is_lake=False, is_river=False)
    world["cells"][0][field] = value
    errors = validate_species_habitat_support(world)
    expected = f"present {field} must be finite numeric" if field == "primary_productivity_index" else "unsupported fishery_productivity_index must be numeric zero"
    assert any(expected in error for error in errors), errors


def test_absent_river_fishery_rejects_parent_but_standing_input_remains_unavailable():
    world = species_world(water_body_type="land", is_lake=False, is_river=True)
    del world["cells"][0]["fishery_productivity_index"]
    before = deepcopy(world)
    with pytest.raises(ValueError, match="unsupported fishery_productivity_index must be numeric zero"):
        enrich_world_with_species_ranges(world)
    assert world == before
    world = species_world()
    del world["cells"][0]["fishery_productivity_index"]
    world = enrich_world_with_species_ranges(world)
    assert world["cells"][0]["species_freshwater_fish_score_supported"] is False
    assert validate_species_habitat_support(world) == []


@pytest.mark.parametrize("guild", ["canopy_tree", "grassland_grazer", "desert_specialist", "alpine_tundra_specialist", "large_predator", "marine_fish"])
def test_fresh_lake_cannot_host_terrestrial_or_marine_dominant_or_range(guild):
    world = species_world()
    world["cells"][0]["dominant_species_guild"] = guild
    assert_rejected(world, "dominant guild mismatch")
    world = species_world()
    record = next(record for record in world["species_range_records"] if record["guild_type"] == "freshwater_fish")
    record["guild_type"] = guild
    assert_rejected(world, "guild/member/component identity mismatch")


def test_marine_inland_sea_cannot_host_freshwater_resident_range():
    world = species_world(water_body_type="inland_sea", is_water=True, is_lake=False)
    record = next(record for record in world["species_range_records"] if record["guild_type"] == "marine_fish")
    record["guild_type"] = "freshwater_fish"
    assert_rejected(world, "guild/member/component identity mismatch")


@pytest.mark.parametrize("guild", ["reef_builder", "wetland_amphibian", "mangrove_coastal_bird"])
def test_explicit_legacy_guilds_do_not_inherit_whole_cell_terrestrial_gate(guild):
    world = species_world(water_body_type="saline_basin", is_lake=True)
    cell = world["cells"][0]
    assert cell["species_terrestrial_habitat_eligible"] is False
    # The old habitat carveout remains, but v3 now checks every own parent.
    assert cell[f"species_{guild}_score_supported"] is (guild != "reef_builder")
    assert cell["fishery_productivity_supported"] is False
    assert validate_species_habitat_support(world) == []
    original_dominant = cell["dominant_species_guild"]
    cell["dominant_species_guild"] = guild
    if guild != original_dominant:
        assert_rejected(world, "dominant guild mismatch")


@pytest.mark.parametrize("flag", ["species_terrestrial_habitat_eligible", "species_freshwater_habitat_eligible", "species_marine_habitat_eligible", "species_freshwater_fish_score_supported", "species_marine_fish_score_supported"])
def test_missing_wrong_or_nonboolean_flags_rejected(flag):
    for mutation in ("flip", 1, None, "true", "delete"):
        world = species_world()
        cell = world["cells"][0]
        if mutation == "delete":
            del cell[flag]
        else:
            cell[flag] = not cell[flag] if mutation == "flip" else mutation
        assert_rejected(world, flag + " mismatch")


@pytest.mark.parametrize("value", [None, "standing_water_required_typo", "river_inapplicable_omitted", {}, 1])
def test_wrong_fishery_input_mode_rejected(value):
    world = species_world()
    world["cells"][0]["species_freshwater_fishery_input_mode"] = value
    assert_rejected(world, "species_freshwater_fishery_input_mode mismatch")


@pytest.mark.parametrize("value", [[], {}, "unknown_guild", None])
def test_malformed_dominant_does_not_raise_or_bypass_validation(value):
    world = species_world()
    world["cells"][0]["dominant_species_guild"] = value
    assert_rejected(world, "dominant guild")


@pytest.mark.parametrize("value", [None, True, "18", [], {}, float("nan"), float("inf"), 10**500])
def test_all_range_climate_envelopes_require_real_annual_input(value):
    world = species_world()
    world["cells"][0]["temperature_c"] = value
    assert any("requires valid ecosystem parents" in error
               for error in validate_species_habitat_support(world))


def test_water_evidence_counts_standing_lake_and_preserves_mixed_cell_river():
    world = species_world()
    record = next(record for record in world["species_range_records"] if record["guild_type"] == "freshwater_fish")
    assert record["habitat_evidence"]["water_cell_fraction"] == 1.0
    record["habitat_evidence"]["water_cell_fraction"] = 0.0
    assert_rejected(world, "consumed habitat evidence mismatch")
    river = species_world(water_body_type="land", is_lake=False, is_river=True)
    assert all(record["habitat_evidence"]["water_cell_fraction"] == 0.0 for record in river["species_range_records"])
    assert validate_species_habitat_support(river) == []


@pytest.mark.parametrize("value", [None, [], "v2", {}, {"model": "unknown"}])
def test_present_invalid_model_is_never_legacy(value):
    world = species_world()
    world["species_ranges_model"] = value
    assert_rejected(world, "availability fields require the exact species v3 declaration")


def test_each_model_field_is_required_and_strict():
    healthy = species_world()
    for field in healthy["species_ranges_model"]:
        for mutation in ("delete", "change"):
            world = deepcopy(healthy)
            if mutation == "delete":
                del world["species_ranges_model"][field]
            else:
                world["species_ranges_model"][field] = [True] if isinstance(world["species_ranges_model"][field], list) else "unknown"
            assert validate_species_habitat_support(world), (field, mutation)
    world = deepcopy(healthy)
    world["species_ranges_model"]["unsupported_extra"] = True
    assert validate_species_habitat_support(world)


@pytest.mark.parametrize("guild,field,value", [
    ("freshwater_fish", "lower_exclusive", -16.0),
    ("freshwater_fish", "upper_exclusive", 44.0),
    ("marine_fish", "lower_exclusive", "-11"),
    ("marine_fish", "upper_exclusive", True),
])
def test_own_fish_window_metadata_is_exact(guild, field, value):
    world = species_world()
    world["species_ranges_model"]["own_temperature_support_c"][guild][field] = value
    assert_rejected(world, "species parent model metadata")


def test_absent_model_preserves_legacy_without_new_support_fields():
    world = deepcopy(historical_ecology_world_readonly())
    del world["species_ranges_model"]
    world["cells"][0]["dominant_species_guild"] = "grassland_grazer"
    assert validate_species_habitat_support(world) == []


@pytest.mark.parametrize("field,value", [("cell_ids", {}), ("cell_ids", [[]]), ("cell_ids", [True]),
                                         ("guild_type", {}), ("habitat_evidence", None),
                                         ("habitat_evidence", {"water_cell_fraction": []})])
def test_malformed_record_shapes_fail_without_exception(field, value):
    world = species_world()
    world["species_range_records"][0][field] = value
    assert validate_species_habitat_support(world)


@pytest.mark.parametrize("water_type", [[], {}])
def test_unhashable_water_type_does_not_bypass_existing_fresh_habitat_flags(water_type):
    world = species_world()
    world["cells"][0]["water_body_type"] = water_type
    assert any("requires valid ecosystem parents" in error
               for error in validate_species_habitat_support(world))


@pytest.fixture(scope="module")
def full_world():
    world = current_world_readonly("full")
    assert world["ecosystem_dynamics_model"]["model"] == "heuristic_ecosystem_climate_support_v5"
    assert world["species_ranges_model"]["model"] == "heuristic_species_parent_support_v4"
    return world


def invoke_validate(world, tmp_path):
    path = tmp_path / "world.json"
    write_json(path, world)
    result = CliRunner().invoke(app, ["validate", "--world", str(path)])
    assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
    return result


def test_public_cli_accepts_current_and_absent_model_legacy(full_world, tmp_path):
    for legacy in (False, True):
        world = deepcopy(historical_ecology_world_readonly() if legacy else full_world)
        if legacy:
            del world["species_ranges_model"]
        result = invoke_validate(world, tmp_path)
        assert result.exit_code == 0, result.output
    current_without_model = deepcopy(full_world)
    del current_without_model["species_ranges_model"]
    result = invoke_validate(current_without_model, tmp_path)
    assert result.exit_code == 1
    assert "complete ecosystem v5 output requires species parent-support v4" in result.output


@pytest.mark.parametrize("mutation", ["none", "flag", "model", "water_type", "record"])
def test_explicit_frozen_v2_archive_keeps_its_original_validation_contract(mutation):
    world = json.loads((Path(__file__).parent / "fixtures/species_parent_support/legacy_v2.json").read_text())
    assert world["species_ranges_model"]["model"] == "heuristic_species_habitat_support_v2"
    assert validate_species_habitat_support(world) == []
    if mutation == "none":
        return
    if mutation == "flag":
        world["cells"][0]["species_freshwater_fish_score_supported"] = False
        expected = "species_freshwater_fish_score_supported mismatch"
    elif mutation == "model":
        world["species_ranges_model"]["fish_temperature_support_c"]["freshwater_fish"]["upper_exclusive"] = 44.0
        expected = "species habitat model metadata has invalid fish_temperature_support_c"
    elif mutation == "water_type":
        world["cells"][0]["water_body_type"] = []
        expected = "species_freshwater_habitat_eligible mismatch"
    else:
        world["species_range_records"][0]["cell_ids"] = [[]]
        expected = "invalid member cell IDs"
    assert any(expected in error for error in validate_species_habitat_support(world))


def test_public_cli_reports_malformed_dominant_without_exception(full_world, tmp_path):
    world = deepcopy(full_world)
    world["cells"][0]["dominant_species_guild"] = []
    result = invoke_validate(world, tmp_path)
    assert result.exit_code == 1
    assert "FAIL species parent cell 0: dominant guild mismatch" in result.output.splitlines()


def test_public_cli_reports_model_and_standing_lake_habitat_failure(full_world, tmp_path):
    world = deepcopy(full_world)
    world["species_ranges_model"]["aquatic_selector"] = "marine_only"
    result = invoke_validate(world, tmp_path)
    assert result.exit_code == 1
    assert "FAIL prescribed natural species: exact species v4 declaration required" in result.output.splitlines()
    world = deepcopy(full_world)
    cell = next(cell for cell in world["cells"] if cell["is_lake"] and not cell["is_water"])
    cell["dominant_species_guild"] = "grassland_grazer"
    result = invoke_validate(world, tmp_path)
    assert result.exit_code == 1
    assert f"FAIL species parent cell {cell['id']}: dominant guild mismatch" in result.output.splitlines()


@pytest.mark.parametrize("field", ["primary_productivity_index", "fishery_productivity_index"])
@pytest.mark.parametrize("value", [None, [], {}, "not-a-number", "0.5", True, False])
def test_public_cli_productivity_preflight_reports_actionable_failure(full_world, tmp_path, field, value):
    world = deepcopy(full_world)
    world["cells"][0][field] = value
    result = invoke_validate(world, tmp_path)
    assert result.exit_code == 1
    assert "FAIL ecosystem dynamic cell fields invalid" in result.output.splitlines()
    assert f"FAIL ecosystem productivity cell 0: {field} must be finite numeric input" in result.output.splitlines()


def test_public_cli_productivity_preflight_preserves_legacy_error_contract_and_payload(full_world, tmp_path):
    world = deepcopy(historical_ecology_world_readonly())
    del world["species_ranges_model"]
    del world["ecosystem_dynamics_model"]
    world["cells"][0]["primary_productivity_index"] = None
    world["cells"][-1]["fishery_productivity_index"] = []
    original = deepcopy(world)
    result = invoke_validate(world, tmp_path)
    assert result.exit_code == 1
    lines = result.output.splitlines()
    assert lines.count("FAIL ecosystem dynamic cell fields invalid") == 1
    assert "FAIL ecosystem productivity cell 0: primary_productivity_index must be finite numeric input" in lines
    assert f"FAIL ecosystem productivity cell {world['cells'][-1]['id']}: fishery_productivity_index must be finite numeric input" in lines
    assert world == original
    assert json.loads((tmp_path / "world.json").read_text()) == original


@pytest.mark.parametrize("field", ["primary_productivity_index", "fishery_productivity_index"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), 10**500])
def test_public_cli_loader_rejects_nonfinite_or_oversized_productivity_without_traceback(full_world, tmp_path, field, value):
    world = deepcopy(full_world)
    world["cells"][0][field] = value
    path = tmp_path / "invalid-model.json"
    # Deliberately bypass the strict writer to exercise the user-selected
    # file boundary. Its existing JSON-model failure precedes field preflight.
    path.write_text(json.dumps(world, allow_nan=True))
    result = CliRunner().invoke(app, ["validate", "--world", str(path)])
    assert result.exit_code == 2
    assert isinstance(result.exception, SystemExit)
    assert "Invalid world file:" in result.output
    assert "non-finite floating-point" in result.output or "64-bit range" in result.output
