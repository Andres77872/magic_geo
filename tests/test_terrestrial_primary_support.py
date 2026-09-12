"""Retained-input E5 support and explicit historical E4 numerical controls."""
from copy import deepcopy
import json
import math
from pathlib import Path

import pytest

from magic_geo.aquatic_climate_validation import _EXPECTED_MODELS, validate_aquatic_climate_support
from magic_geo.ecosystem_dynamics import enrich_world_with_ecosystem_dynamics


FIXTURE = Path(__file__).parent / "fixtures/terrestrial_primary_support/cells.json"
ARCHIVED = json.loads(FIXTURE.read_text())["cases"]
FLAGS = (
    "terrestrial_primary_climate_supported", "primary_productivity_supported",
    "vegetation_biomass_supported", "forest_growth_supported", "vegetation_succession_supported",
    "species_richness_supported", "ecosystem_wildfire_spread_risk_supported",
    "ecosystem_disturbance_pressure_supported", "vegetation_recovery_supported",
)
UNAVAILABLE_NUMBERS = (
    "primary_productivity_index", "vegetation_biomass_index", "forest_growth_index",
    "species_richness_index", "wildfire_spread_risk_index", "ecosystem_disturbance_pressure_index",
)
V4_FIELDS = {
    "terrestrial_temperature_source", "terrestrial_selector",
    "terrestrial_primary_minimum_temperature_c", "terrestrial_primary_maximum_temperature_c",
    "terrestrial_support_scope", "primary_availability_policy", "terrestrial_dependency_policy",
    "unsupported_terrestrial_estimate_policy", "unsupported_terrestrial_succession_policy",
    "unsupported_forest_record_policy",
    "summary_availability_policy",
    "species_richness_availability_policy", "ecosystem_wildfire_availability_policy",
    "ecosystem_disturbance_availability_policy", "vegetation_recovery_availability_policy",
    "renewable_record_availability_policy", "unsupported_parent_estimate_policy",
    "ecosystem_disturbance_input_scope", "aquatic_biomass_input_policy",
}


def land_world(temperature=18.0, **overrides):
    cell = {
        "id": 0, "is_water": False, "is_lake": False, "water_body_type": "land",
        "temperature_c": temperature, "temperature_monthly_c": [18.0] * 12,
        "biome": "temperate_forest", "precipitation_mm_y": 1800.0,
        "potential_evapotranspiration_mm_y": 800.0, "soil_moisture_index": 0.8,
        "fertility": 0.9, "growing_season_months": 12,
        "soil_organic_matter_fraction": 0.2, "wind_east": 0.2,
    }
    cell.update(overrides)
    # Preserve the exact E4 numerical/mutation controls; retained raw cells
    # below still exercise first-publication E5 with their complete sources.
    return {"cells": [cell], "summary": {},
            "ecosystem_dynamics_model": deepcopy(_EXPECTED_MODELS["heuristic_ecosystem_climate_support_v4"])}


def enrich(world):
    assert enrich_world_with_ecosystem_dynamics(world) is world
    return world


def assert_unavailable(world):
    cell = world["cells"][0]
    assert all(cell[field] is False for field in FLAGS)
    assert all(type(cell[field]) is float and cell[field] == 0.0 for field in UNAVAILABLE_NUMBERS)
    assert cell["vegetation_succession_stage"] == "terrestrial_primary_proxy_unavailable"
    assert type(cell["vegetation_recovery_years"]) is int and cell["vegetation_recovery_years"] == 0
    assert world["vegetation_succession_histories"] == []
    assert world["renewable_resource_records"] == []
    assert world["summary"]["forest_growth_resource_count"] == 0
    assert world["summary"]["vegetation_succession_stage_counts"] == {"terrestrial_primary_proxy_unavailable": 1}
    assert validate_aquatic_climate_support(world) == []


@pytest.mark.parametrize("case", ARCHIVED, ids=lambda case: case["name"])
def test_archived_solved_cells_preserve_inputs_and_gate_only_unsupported_estimates(case):
    world = {"cells": [deepcopy(case["inputs"])], "summary": {}}
    before = deepcopy(world["cells"][0])
    enrich(world)
    cell = world["cells"][0]
    assert {key: cell[key] for key in before} == before
    assert validate_aquatic_climate_support(world) == []
    if case["name"] in {"persistent_hot_rainforest", "hot_young_forest", "persistent_cold_land"}:
        assert case["expected_v3"]["primary_productivity_index"] > 0
        assert_unavailable(world)
    else:
        # The ordinary terrestrial and marine equations/coefficients are unchanged.
        assert {key: cell[key] for key in case["expected_v3"]} == case["expected_v3"]
        assert cell["primary_productivity_supported"] is True
    first = deepcopy(world)
    enrich(world)
    assert world == first


@pytest.mark.parametrize("temperature,expected", [
    (math.nextafter(-16.0, -math.inf), False), (-16.0, False),
    (math.nextafter(-16.0, math.inf), True),
    (math.nextafter(52.0, -math.inf), True), (52.0, False),
    (math.nextafter(52.0, math.inf), False), (18, True), (0.0, True),
])
def test_existing_open_input_domain_is_independent_of_triangular_factor_roundoff(temperature, expected):
    world = enrich(land_world(temperature))
    assert all(world["cells"][0][field] is expected for field in FLAGS)
    assert validate_aquatic_climate_support(world) == []
    if not expected:
        assert_unavailable(world)


@pytest.mark.parametrize("temperature", [None, True, False, "18", [], {}, math.nan, math.inf, -math.inf, 10**400])
def test_invalid_annual_inputs_are_unavailable_without_coercion_or_exception(temperature):
    assert_unavailable(enrich(land_world(temperature)))


def test_missing_annual_input_is_not_a_zero_celsius_control():
    world = land_world()
    del world["cells"][0]["temperature_c"]
    assert_unavailable(enrich(world))
    assert "temperature_c" not in world["cells"][0]


def test_supported_zero_is_not_an_unavailable_estimate():
    world = enrich(land_world(
        18.0, biome="hot_desert", precipitation_mm_y=0.0, soil_moisture_index=0.0,
        fertility=0.0, growing_season_months=0, ice_thickness_m=1200.0,
        seasonal_aridity_index=1.0, soil_organic_matter_fraction=0.0,
    ))
    cell = world["cells"][0]
    assert all(cell[field] is True for field in FLAGS)
    assert all(cell[field] == 0.0 for field in (
        "primary_productivity_index", "vegetation_biomass_index", "forest_growth_index",
    ))
    assert cell["vegetation_succession_stage"] == "barren_ice"
    assert cell["vegetation_recovery_years"] > 0
    assert validate_aquatic_climate_support(world) == []


@pytest.mark.parametrize("months", [[-30.0] * 6 + [30.0] * 6, [80.0] * 12, None, ["bad"]])
def test_annual_proxy_does_not_silently_claim_a_new_monthly_or_dormancy_model(months):
    world = enrich(land_world(18.0, temperature_monthly_c=months))
    assert world["cells"][0]["terrestrial_primary_climate_supported"] is True
    assert world["cells"][0]["temperature_monthly_c"] == months
    assert world["ecosystem_dynamics_model"]["monthly_temperature_policy"] == "not_used"
    assert validate_aquatic_climate_support(world) == []


@pytest.mark.parametrize("selector", [
    {"is_water": True, "water_body_type": "ocean"},
    {"is_lake": True, "water_body_type": "fresh_lake"},
    {"is_lake": True, "water_body_type": "saline_basin"},
    {"water_body_type": "fresh_lake"},
])
def test_shared_aquatic_selector_retains_v3_exclusion_and_own_support(selector):
    world = enrich(land_world(18.0, **selector))
    cell = world["cells"][0]
    assert cell["terrestrial_primary_climate_supported"] is False
    assert cell["primary_productivity_supported"] is True
    assert cell["vegetation_biomass_supported"] is False
    assert cell["forest_growth_supported"] is False
    assert cell["vegetation_succession_stage"] == "aquatic_primary_productivity"
    assert world["vegetation_succession_histories"] == []
    assert not any(r["resource_type"] == "forest_growth" for r in world["renewable_resource_records"])
    assert validate_aquatic_climate_support(world) == []


def test_dry_saline_terrain_keeps_terrestrial_support():
    world = enrich(land_world(18.0, water_body_type="saline_basin"))
    assert all(world["cells"][0][field] is True for field in FLAGS)
    assert world["cells"][0]["forest_growth_index"] > 0
    assert validate_aquatic_climate_support(world) == []


def test_stale_estimates_flags_and_records_are_rebuilt_when_support_changes():
    world = enrich(land_world())
    original = deepcopy(world)
    assert world["vegetation_succession_histories"] and world["renewable_resource_records"]
    world["cells"][0]["temperature_c"] = 80.0
    enrich(world)
    assert_unavailable(world)
    second = deepcopy(world)
    enrich(world)
    assert world == second
    world["cells"][0]["temperature_c"] = 18.0
    enrich(world)
    assert world == original


def test_upstream_descriptors_and_native_certificate_objects_are_not_rewritten():
    world = land_world(80.0, biome="tropical_rainforest", growing_season_months=12, fertility=0.9)
    sections = {key: {"marker": key} for key in (
        "climate_model", "climate_energy_model", "climate_energy_balance_records",
        "climate_energy_forcing_intervals", "climate_energy_transport_edges",
    )}
    world.update(sections)
    before = deepcopy(world["cells"][0])
    enrich(world)
    assert {key: world["cells"][0][key] for key in before} == before
    assert all(world[key] is value for key, value in sections.items())


def test_unsupported_primary_does_not_claim_terrestrial_physical_nonburnability():
    world = enrich(land_world(80.0, fire_frequency_index=1.0, seasonal_aridity_index=1.0, wind_east=1.0))
    assert_unavailable(world)
    cell = world["cells"][0]
    assert cell["wildfire_spread_risk_index"] == 0
    assert cell["ecosystem_wildfire_spread_risk_supported"] is False
    assert cell["ecosystem_disturbance_pressure_index"] == 0
    assert cell["ecosystem_disturbance_pressure_supported"] is False
    assert cell["is_water"] is False and cell["is_lake"] is False
    assert cell["soil_organic_matter_fraction"] == 0.2
    assert cell["fire_frequency_index"] == 1.0
    assert "not_absence_damage_or_physical_nonburnability" in world["ecosystem_dynamics_model"]["unsupported_parent_estimate_policy"]


@pytest.mark.parametrize("field", FLAGS)
@pytest.mark.parametrize("value", [True, 1, None, "false"])
def test_independent_validator_rejects_false_availability_claims(field, value):
    world = enrich(land_world(80.0))
    world["cells"][0][field] = value
    assert any(field + " mismatch" in error for error in validate_aquatic_climate_support(world))


@pytest.mark.parametrize("field", UNAVAILABLE_NUMBERS)
@pytest.mark.parametrize("value", [1e-12, -1e-12, False, None, "0", math.nan, math.inf])
def test_independent_validator_rejects_positive_or_malformed_unavailable_sentinels(field, value):
    world = enrich(land_world(80.0))
    world["cells"][0][field] = value
    assert any("unsupported " + field in error for error in validate_aquatic_climate_support(world))


@pytest.mark.parametrize("field,value", [
    ("vegetation_succession_stage", "mature_closed_canopy"),
    ("vegetation_succession_stage", "pioneer_sparse_cover"),
    ("vegetation_succession_stage", []),
    ("vegetation_recovery_years", 1), ("vegetation_recovery_years", 0.0),
    ("vegetation_recovery_years", False),
])
def test_unavailable_succession_cannot_claim_a_stage_or_recovery_estimate(field, value):
    world = enrich(land_world(80.0))
    world["cells"][0][field] = value
    assert validate_aquatic_climate_support(world)


@pytest.mark.parametrize("family,phrase", [
    ("vegetation_succession_histories", "succession history"),
    ("renewable_resource_records", "forest record"),
])
@pytest.mark.parametrize("cell_id", [0, 999, None, True, [], {}])
def test_independent_validator_rejects_unsupported_or_unknown_record_parents(family, phrase, cell_id):
    world = enrich(land_world(80.0))
    record = deepcopy(enrich(land_world())[family][0])
    record["cell_id"] = cell_id
    world[family] = [record]
    assert any(phrase in error and "unsupported source" in error for error in validate_aquatic_climate_support(world))


@pytest.mark.parametrize("field", sorted(V4_FIELDS))
def test_each_v4_declaration_is_required_and_independent(field):
    world = enrich(land_world())
    del world["ecosystem_dynamics_model"][field]
    assert validate_aquatic_climate_support(world)
    world = enrich(land_world())
    world["ecosystem_dynamics_model"][field] = "invented_policy"
    assert validate_aquatic_climate_support(world)


@pytest.mark.parametrize("metadata", [None, [], "v4", {}, {"model": []}, {"model": "future_v5"}])
def test_malformed_or_unknown_metadata_does_not_use_legacy_dispatch(metadata):
    world = enrich(land_world())
    world["ecosystem_dynamics_model"] = metadata
    assert validate_aquatic_climate_support(world)


@pytest.mark.parametrize("model", [None, "heuristic_ecosystem_climate_support_v2", "heuristic_ecosystem_climate_support_v3"])
def test_absent_and_known_old_models_keep_explicit_old_terrestrial_scope(model):
    world = enrich(land_world(80.0))
    for field in FLAGS:
        del world["cells"][0][field]
    world["cells"][0]["primary_productivity_index"] = 0.7
    world["cells"][0]["vegetation_biomass_index"] = 0.8
    if model is None:
        del world["ecosystem_dynamics_model"]
    else:
        metadata = world["ecosystem_dynamics_model"]
        for field in V4_FIELDS:
            del metadata[field]
        metadata["model"] = model
        if model.endswith("_v2"):
            del metadata["aquatic_ecology_policy"]
    # A synthetic historical projection must remove the new summary mirrors
    # as well as the cell flags; the mixed declaration is not a legacy world.
    assert validate_aquatic_climate_support(world)
    for field in FLAGS:
        del world["summary"][field + "_cell_count"]
    assert validate_aquatic_climate_support(world) == []


def test_v4_cannot_borrow_an_old_declaration_to_drop_new_fields():
    world = enrich(land_world())
    world["ecosystem_dynamics_model"]["model"] = "heuristic_ecosystem_climate_support_v3"
    assert validate_aquatic_climate_support(world)


@pytest.mark.parametrize("cell_id", [True, -1, None, [], {}])
def test_v4_malformed_cell_identity_fails_without_exception(cell_id):
    world = enrich(land_world(80.0))
    world["cells"][0]["id"] = cell_id
    assert validate_aquatic_climate_support(world)


def test_v4_duplicate_cell_identity_fails_without_exception():
    world = enrich(land_world(80.0))
    world["cells"].append(deepcopy(world["cells"][0]))
    assert validate_aquatic_climate_support(world)


@pytest.mark.parametrize("flag", FLAGS)
@pytest.mark.parametrize("value", [1, False, None, "0"])
def test_summary_support_counts_cannot_hide_unavailable_cell_estimates(flag, value):
    world = enrich(land_world(80.0))
    field = flag + "_cell_count"
    world["summary"][field] = value
    assert any(field + " mismatch" in error for error in validate_aquatic_climate_support(world))


def test_mixed_summary_support_counts_distinguish_sentinels_from_supported_zero():
    world = land_world(80.0)
    ordinary = land_world()["cells"][0]
    ordinary["id"] = 1
    marine = land_world(18.0, is_water=True, water_body_type="ocean")["cells"][0]
    marine["id"] = 2
    world["cells"].extend([ordinary, marine])
    enrich(world)
    assert world["summary"]["primary_productivity_supported_cell_count"] == 2
    for flag in FLAGS:
        expected = 1 if flag in {
            "terrestrial_primary_climate_supported", "vegetation_biomass_supported",
            "forest_growth_supported", "vegetation_succession_supported",
        } else 2
        assert world["summary"][flag + "_cell_count"] == expected
    assert validate_aquatic_climate_support(world) == []


def test_unsupported_aquatic_production_keeps_independent_disturbance_available():
    world = enrich(land_world(80.0, is_lake=True, water_body_type="fresh_lake", ecotone_index=1.0))
    cell = world["cells"][0]
    assert cell["species_richness_supported"] is False
    assert cell["species_richness_index"] == 0
    assert cell["vegetation_recovery_supported"] is False
    assert cell["vegetation_recovery_years"] == 0
    assert cell["ecosystem_wildfire_spread_risk_supported"] is True
    assert cell["wildfire_spread_risk_index"] == 0
    assert cell["ecosystem_disturbance_pressure_supported"] is True
    assert cell["ecosystem_disturbance_pressure_index"] > 0
    assert validate_aquatic_climate_support(world) == []


@pytest.mark.parametrize("flag", FLAGS)
@pytest.mark.parametrize("value", [False, 1, None, "true"])
def test_independent_validator_rejects_missing_or_false_supported_parent_flags(flag, value):
    world = enrich(land_world())
    assert world["cells"][0][flag] is True
    world["cells"][0][flag] = value
    assert any(flag + " mismatch" in error for error in validate_aquatic_climate_support(world))


@pytest.mark.parametrize("value", [0, -1, 1.0, True, None])
def test_supported_recovery_descriptor_requires_positive_integer(value):
    world = enrich(land_world())
    world["cells"][0]["vegetation_recovery_years"] = value
    assert any("supported recovery years" in error for error in validate_aquatic_climate_support(world))


@pytest.mark.parametrize("resource_type", [[], {}, ["forest_growth"], None, 1, False])
def test_malformed_renewable_resource_type_returns_diagnostic(resource_type):
    world = enrich(land_world())
    assert world["renewable_resource_records"]
    world["renewable_resource_records"][0]["resource_type"] = resource_type
    assert any("resource_type must be a string" in error for error in validate_aquatic_climate_support(world))
