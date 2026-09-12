"""Upstream omissions cannot masquerade as a complete natural ecosystem input."""
from copy import deepcopy

import pytest

from magic_geo import ecosystem_dynamics as producer
from magic_geo.aquatic_climate_validation import validate_aquatic_climate_support
from magic_geo.prescribed_natural_ecosystem_validation import PrescribedNaturalEcosystemError
from test_prescribed_natural_ecosystem import build, fresh_inputs, stage_input


PHYSICAL_SOURCES = (
    "precipitation_mm_y", "potential_evapotranspiration_mm_y", "soil_moisture_index",
    "fertility", "growing_season_months", "runoff_mm_y", "ocean_current_temperature_c",
    "ocean_current_east", "ice_thickness_m", "seasonal_aridity_index",
    "soil_organic_matter_fraction", "fire_frequency_index", "ecotone_index",
    "erosion_rate", "wind_east", "wind_north", "groundwater_recharge_mm_y",
)
HABITAT_SOURCES = ("biome", "water_body_type", "is_water", "is_lake")


def assert_rejected_atomically(world, key):
    before = deepcopy(world)
    root_refs = {k: v for k, v in world.items() if isinstance(v, (dict, list))}
    cells = list(world["cells"])
    with pytest.raises(PrescribedNaturalEcosystemError, match=key):
        producer.enrich_world_with_ecosystem_dynamics(world)
    assert world == before
    assert all(world[k] is v for k, v in root_refs.items())
    assert all(a is b for a, b in zip(cells, world["cells"]))


@pytest.mark.parametrize("published", [False, True])
@pytest.mark.parametrize("key", PHYSICAL_SOURCES + HABITAT_SOURCES)
def test_actual_late_missing_parent_rejects_first_call_and_reenrichment(key, published):
    world = fresh_inputs()
    if published:
        build(world)
    assert all(key in cell for cell in world["cells"])
    del world["cells"][-1][key]
    if published:
        errors = validate_aquatic_climate_support(world)
        assert len(errors) == 1 and key in errors[0]
    assert_rejected_atomically(world, key)


@pytest.mark.parametrize("key", ("is_water", "is_lake"))
@pytest.mark.parametrize("value", [None, 0, 1, "false", "true", [], {}])
def test_habitat_masks_reject_truthiness_coercion(key, value):
    world = build(stage_input())
    world["cells"][0][key] = value
    assert key in validate_aquatic_climate_support(world)[0]
    assert_rejected_atomically(world, key)


@pytest.mark.parametrize("key", ("biome", "water_body_type"))
@pytest.mark.parametrize("value", [None, 0, False, [], {}, "", "   "])
def test_habitat_categories_reject_missing_or_malformed_text(key, value):
    world = build(stage_input())
    world["cells"][0][key] = value
    assert key in validate_aquatic_climate_support(world)[0]
    assert_rejected_atomically(world, key)


def test_explicit_zero_sources_and_false_masks_remain_valid():
    world = build(stage_input(**dict.fromkeys(PHYSICAL_SOURCES, 0.0)))
    cell = world["cells"][0]
    assert cell["is_water"] is cell["is_lake"] is False
    assert cell["aquatic_climate_proxy_applicable"] is False
    assert cell["primary_productivity_supported"] is True
    assert cell["primary_productivity_index"] == .26
    assert cell["ecosystem_disturbance_pressure_supported"] is True


def test_explicit_unknown_categories_do_not_claim_a_taxonomy_certificate():
    world = build(stage_input(biome="unknown", water_body_type="saline_basin"))
    assert world["cells"][0]["aquatic_climate_proxy_applicable"] is False
    assert world["cells"][0]["forest_growth_index"] == 0.0


def test_missing_annual_temperature_retains_declared_unsupported_policy():
    world = stage_input()
    del world["cells"][0]["temperature_c"]
    build(world)
    cell = world["cells"][0]
    assert cell["primary_productivity_supported"] is False
    assert cell["primary_productivity_index"] == 0.0
    assert cell["vegetation_recovery_years"] == 0
