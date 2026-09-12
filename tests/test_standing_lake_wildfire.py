"""Water exclusion in historical wildfire, with an explicit E4-parent bridge control.

The scalar ``cell`` helper deliberately retains its original contract: its
arbitrary numerical parents isolate legacy equations. New world-level cases
explicitly rebuild ecosystem v4 rather than attaching support flags to it.
"""

from copy import deepcopy

import pytest

from magic_geo.ecosystem_dynamics import enrich_world_with_ecosystem_dynamics
from magic_geo.aquatic_climate_validation import _EXPECTED_MODELS
from magic_geo.wildfire_aquatic_validation import validate_wildfire_aquatic_exclusion
from support.fire_worlds import fire_input_world
from magic_geo.wildfire_disturbance import (
    _firebreak,
    _fuel_continuity,
    _ignition_potential,
    _spread_probability,
    enrich_world_with_wildfire_disturbance,
)


def cell(cell_id=0, **overrides):
    return {
        "id": cell_id, "area_km2": 1.0, "lat_deg": 0.0,
        "lon_deg": float(cell_id), "neighbors": [],
        "is_water": False, "is_lake": False, "water_body_type": "land",
        "biome": "temperate_forest", "temperature_c": 18.0,
        "vegetation_biomass_index": 1.0, "primary_productivity_index": 1.0,
        "wildfire_spread_risk_index": 1.0, "seasonal_aridity_index": 1.0,
        "ecosystem_disturbance_pressure_index": 1.0,
        "climate_energy_stress_index": 1.0, "settlement_score": 1.0,
        "wind_east": 1.0,
        **overrides,
    }


def assert_non_burnable(water):
    assert water["wildfire_fuel_continuity_index"] == 0.0
    assert water["wildfire_ignition_potential_index"] == 0.0
    assert water["wildfire_firebreak_index"] == 1.0
    assert water["wildfire_disturbance_regime"] == "non_burnable_water"
    assert water["wildfire_spread_history_ids"] == []


@pytest.mark.parametrize("water_flags", [
    {"is_lake": True, "water_body_type": "fresh_lake"},
    {"is_lake": True, "water_body_type": "saline_basin"},
    {"is_lake": True, "water_body_type": "land"},
    {"water_body_type": "fresh_lake"},
    {"water_body_type": "inland_sea"},
    {"water_body_type": "ocean"},
    {"water_body_type": "continental_shelf"},
    {"is_water": True},
])
def test_all_aquatic_selectors_veto_stale_terrestrial_fuel_and_ignition(water_flags):
    world = enrich_world_with_wildfire_disturbance({"cells": [cell(**water_flags)]})
    assert world["wildfire_disturbance_model"]["model"] == "heuristic_wildfire_aquatic_exclusion_v2"
    assert_non_burnable(world["cells"][0])
    assert world["wildfire_spread_histories"] == []
    assert world["summary"]["wildfire_disturbance_cell_count"] == 0
    assert world["summary"]["wildfire_total_burned_area_km2"] == 0.0
    assert world["summary"]["high_wildfire_firebreak_cell_count"] == 1


@pytest.mark.parametrize("water_body", ["fresh_lake", "saline_basin"])
@pytest.mark.parametrize("current_parent", [False, True], ids=["historical_v2", "historical_parent_v4"])
def test_lake_is_a_graph_barrier_and_dry_bridge_retains_land_spread(water_body, current_parent):
    # The far shore has fuel but cannot ignite independently. A connected
    # dry bridge permits spread from 0 through 1 to 2; inundation blocks it.
    source = cell(0, neighbors=[1])
    bridge = cell(1, neighbors=[0, 2], water_body_type="saline_basin")
    far_shore = cell(
        2, neighbors=[1], vegetation_biomass_index=0.8, primary_productivity_index=0.8,
        wildfire_spread_risk_index=0.0, seasonal_aridity_index=0.0,
        ecosystem_disturbance_pressure_index=0.0, climate_energy_stress_index=0.0,
        settlement_score=0.0, wind_east=0.0, fire_frequency_index=0.0,
    )
    dry_input = {"cells": deepcopy([source, bridge, far_shore])}
    if current_parent:
        dry_input = fire_input_world(dry_input["cells"])
    dry = enrich_world_with_wildfire_disturbance(dry_input)
    expected_model = "heuristic_wildfire_parent_availability_v4" if current_parent else "heuristic_wildfire_aquatic_exclusion_v2"
    assert dry["wildfire_disturbance_model"]["model"] == expected_model
    assert validate_wildfire_aquatic_exclusion(dry) == []
    assert dry["cells"][2]["wildfire_ignition_potential_index"] < 0.28
    assert dry["wildfire_spread_histories"][0]["cell_ids"] == [0, 1, 2]
    assert dry["wildfire_spread_histories"][0]["ignition_cell_id"] == 0

    bridge.update(is_lake=True, water_body_type=water_body, biome="lake")
    wet_input = {"cells": [source, bridge, far_shore]}
    if current_parent:
        wet_input = fire_input_world(wet_input["cells"])
    wet = enrich_world_with_wildfire_disturbance(wet_input)
    assert wet["wildfire_disturbance_model"]["model"] == expected_model
    assert validate_wildfire_aquatic_exclusion(wet) == []
    assert_non_burnable(bridge)
    assert far_shore["wildfire_ignition_potential_index"] < 0.28
    assert far_shore["wildfire_spread_history_ids"] == []
    history, = wet["wildfire_spread_histories"]
    assert history["cell_ids"] == [0]
    assert history["steps"][0]["newly_burned_cell_ids"] == [0]
    assert history["area_km2"] == 1.0


def test_water_cannot_be_a_spread_source_or_target_even_with_stale_diagnostics():
    water = cell(1, is_lake=True, water_body_type="saline_basin",
                 wildfire_ignition_potential_index=1.0, wildfire_fuel_continuity_index=1.0,
                 wildfire_firebreak_index=0.0, wildfire_disturbance_regime="seasonal_surface_fire")
    land = cell(0, wildfire_ignition_potential_index=1.0, wildfire_fuel_continuity_index=1.0)
    assert _spread_probability(land, water) == 0.0
    assert _spread_probability(water, land) == 0.0


def test_aquatic_neighbors_supply_firebreaks_and_cannot_supply_terrestrial_biomass():
    target = cell()
    water = cell(1, is_lake=True, water_body_type="saline_basin")
    dry = cell(1, water_body_type="saline_basin")
    no_neighbor_fuel = _fuel_continuity(target, [dict(water, vegetation_biomass_index=0.0)])
    assert _fuel_continuity(target, [water]) == no_neighbor_fuel
    # Use a low-fuel target so neither independent comparison hits its clamp.
    target.update(vegetation_biomass_index=0.0, primary_productivity_index=0.0,
                  wildfire_spread_risk_index=0.0, seasonal_aridity_index=0.0)
    water_fuel = _fuel_continuity(target, [water])
    assert _fuel_continuity(target, [dry]) - water_fuel == pytest.approx(0.12)
    assert _firebreak(target, [water], water_fuel) - _firebreak(target, [dry], water_fuel) == pytest.approx(0.34)


def test_supported_land_formulas_and_legacy_energy_term_remain_unchanged():
    land = cell(vegetation_biomass_index=0.6, primary_productivity_index=0.7,
                wildfire_spread_risk_index=0.4, seasonal_aridity_index=0.3,
                wetland_extent_index=0.2, is_river=True, floodplain_connectivity_index=0.5,
                ecosystem_disturbance_pressure_index=0.4, settlement_score=0.2,
                climate_energy_stress_index=0.8)
    neighbors = [cell(1), cell(2, vegetation_biomass_index=0.0)]
    fuel = _fuel_continuity(land, neighbors)
    assert fuel == pytest.approx(0.55)
    firebreak = _firebreak(land, neighbors, fuel)
    assert firebreak == pytest.approx(0.369)
    ignition = _ignition_potential(land, fuel, firebreak, 0.5)
    assert ignition == pytest.approx(0.41558)
    unstressed = _ignition_potential(dict(land, climate_energy_stress_index=0.0), fuel, firebreak, 0.5)
    assert ignition - unstressed == pytest.approx(0.06 * 0.8)


def test_actual_ecosystem_lake_productivity_is_not_reinterpreted_as_fire_fuel():
    lake = cell(0, neighbors=[1], is_lake=True, water_body_type="fresh_lake", biome="lake",
                runoff_mm_y=900.0, soil_moisture_index=1.0,
                settlement_score=0.0, climate_energy_stress_index=0.0)
    land = cell(1, neighbors=[0], soil_moisture_index=1.0, fertility=1.0)
    world = enrich_world_with_ecosystem_dynamics({"cells": [lake, land],
        "ecosystem_dynamics_model": deepcopy(_EXPECTED_MODELS["heuristic_ecosystem_climate_support_v4"])})
    assert lake["primary_productivity_index"] == 0.7
    assert lake["vegetation_biomass_index"] == lake["wildfire_spread_risk_index"] == 0.0
    enrich_world_with_wildfire_disturbance(world)
    assert_non_burnable(lake)
    assert all(0 not in history["cell_ids"] for history in world["wildfire_spread_histories"])


def test_marine_and_lake_water_have_identical_fire_policy():
    lake = enrich_world_with_wildfire_disturbance({"cells": [cell(is_lake=True, water_body_type="fresh_lake")]})
    ocean = enrich_world_with_wildfire_disturbance({"cells": [cell(is_water=True, water_body_type="ocean")]})
    assert_non_burnable(lake["cells"][0])
    assert_non_burnable(ocean["cells"][0])
    assert lake["summary"] == ocean["summary"]


def test_inundation_removes_stale_fire_histories_and_is_idempotent():
    world = enrich_world_with_wildfire_disturbance({"cells": [cell()]})
    assert world["wildfire_spread_histories"]
    world["cells"][0].update(is_lake=True, water_body_type="saline_basin")
    enrich_world_with_wildfire_disturbance(world)
    assert_non_burnable(world["cells"][0])
    assert world["wildfire_spread_histories"] == []
    once = deepcopy(world)
    enrich_world_with_wildfire_disturbance(world)
    assert world == once


def test_version_metadata_declares_aquatic_policy_without_migrating_energy_stress():
    model = enrich_world_with_wildfire_disturbance({"cells": [cell()]})["wildfire_disturbance_model"]
    assert model == {
        "model": "heuristic_wildfire_aquatic_exclusion_v2",
        "aquatic_selector": "is_water_or_is_lake_or_fishery_water_body_type",
        "aquatic_fire_policy": "zero_fuel_ignition_and_spread_non_burnable_no_history",
        "neighbor_fuel_policy": "terrestrial_biomass_neighbors",
        "ignition_model": "legacy_energy_aridity_fuel_wind_settlement_proxy_v1",
    }
    assert enrich_world_with_wildfire_disturbance({"cells": []}) == {"cells": []}
