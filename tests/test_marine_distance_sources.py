"""Small complete source graphs; no native/world generation or archive replay."""
from copy import deepcopy
import math

import pytest

from magic_geo.climate_continentality import enrich_world_with_climate_continentality
from magic_geo.groundwater_flow import _surface_connection_index
from magic_geo.species_ranges import _habitat_evidence
from magic_geo.marine_distance_validation import require_marine_distance, validate_marine_distance


def cell(cid, water="land"):
    return {
        "id": cid, "area_km2": 1.0, "neighbors": [], "water_body_type": water,
        "is_water": water != "land", "is_lake": water == "fresh_lake", "is_river": False,
        "is_closed_basin": False, "lat_deg": 0.0, "lon_deg": float(cid),
        "temperature_monthly_c": [10.0] * 12, "humidity_transport_index": 0.0,
        "upwind_ocean_fetch_km": 0.0, "advected_moisture_factor": 0.65,
        "precipitation_mm_y": 0.0, "wetland_extent_index": 0.0,
    }


def world(*waters, connected=True):
    cells = [cell(i, water) for i, water in enumerate(waters)]
    edges = []
    if connected:
        for i in range(len(cells) - 1):
            cells[i]["neighbors"].append(i + 1)
            cells[i + 1]["neighbors"].append(i)
            edges.append({"cell_a_id": i, "cell_b_id": i + 1, "great_circle_distance_km": 100.0})
    return {"cells": cells, "cell_adjacency_edges": edges, "summary": {}}


@pytest.mark.parametrize("waters", [("land",), ("land", "land"), ("fresh_lake", "land")])
def test_no_marine_source_has_null_distance_and_known_zero_ocean_influence(waters):
    w = world(*waters)
    enrich_world_with_climate_continentality(w)
    for c in w["cells"]:
        assert c["distance_to_marine_water_km"] is None
        assert c["marine_distance_status"] == "no_marine_source"
        assert c["marine_influence_class"] == "no_marine_source"
        assert c["oceanic_humidity_availability_index"] == 0.0
        assert math.isfinite(c["continentality_index"])
    assert w["summary"]["mean_distance_to_marine_water_km"] is None
    assert w["summary"]["marine_distance_defined_cell_count"] == 0
    assert w["summary"]["no_marine_source_cell_count"] == len(waters)
    for r in w["climate_continentality_regions"]:
        assert r["mean_distance_to_marine_water_km"] is None


def test_actual_marine_zero_and_coastal_distance_keep_their_numeric_meaning():
    w = world("ocean", "land")
    enrich_world_with_climate_continentality(w)
    assert [c["distance_to_marine_water_km"] for c in w["cells"]] == [0.0, 100.0]
    assert w["cells"][0]["marine_influence_class"] == "marine"
    assert w["cells"][1]["marine_influence_class"] == "coastal"
    assert w["cells"][1]["oceanic_humidity_availability_index"] == round(math.exp(-100 / 1200) * 0.36, 6)
    assert w["summary"]["mean_distance_to_marine_water_km"] == 50.0


def test_freshwater_lake_is_not_a_marine_distance_source():
    w = world("ocean", "land", "fresh_lake")
    enrich_world_with_climate_continentality(w)
    assert [c["distance_to_marine_water_km"] for c in w["cells"]] == [0.0, 100.0, 200.0]


def test_disconnected_marine_graph_refuses_before_publishing():
    w = world("ocean", "land", connected=False)
    before = deepcopy(w)
    cells, summary = w["cells"], w["summary"]
    with pytest.raises(ValueError, match="unreachable|connected"):
        enrich_world_with_climate_continentality(w)
    assert w == before and w["cells"] is cells and w["summary"] is summary


def test_no_marine_source_does_not_invent_a_groundwater_coastal_connection():
    w = world("land")
    enrich_world_with_climate_continentality(w)
    assert _surface_connection_index(w["cells"][0], natural=True) == 0.0


def test_lake_surface_connection_survives_absent_marine_source():
    w = world("fresh_lake")
    enrich_world_with_climate_continentality(w)
    assert _surface_connection_index(w["cells"][0], natural=True) == 0.56


def test_absent_marine_source_is_not_exported_as_coastal_species_habitat():
    w = world("land")
    enrich_world_with_climate_continentality(w)
    assert _habitat_evidence(w["cells"], "mangrove_coastal_bird")["coastal_cell_fraction"] == 0.0


@pytest.mark.parametrize("mutation", [
    "missing_status", "wrong_status", "invented_zero", "humidity", "mean_zero",
    "region_mean_zero", "false_count", "region_count", "missing_model", "wrong_model",
    "new_marine_source", "missing_distance", "tiny_humidity",
])
def test_no_source_claims_are_replayed_against_actual_geography(mutation):
    w = world("land")
    enrich_world_with_climate_continentality(w)
    assert validate_marine_distance(w) == []
    c, summary, region = w["cells"][0], w["summary"], w["climate_continentality_regions"][0]
    if mutation == "missing_status": del c["marine_distance_status"]
    elif mutation == "wrong_status": c["marine_distance_status"] = "reachable_marine"
    elif mutation == "invented_zero": c["distance_to_marine_water_km"] = 0.0
    elif mutation == "humidity": c["oceanic_humidity_availability_index"] = 0.36
    elif mutation == "mean_zero": summary["mean_distance_to_marine_water_km"] = 0.0
    elif mutation == "region_mean_zero": region["mean_distance_to_marine_water_km"] = 0.0
    elif mutation == "false_count": summary["no_marine_source_cell_count"] = True
    elif mutation == "region_count": region["no_marine_source_cell_count"] = 0
    elif mutation == "missing_model": del w["climate_continentality_model"]
    elif mutation == "wrong_model": w["climate_continentality_model"]["distance_metric"] = "invented"
    elif mutation == "new_marine_source": c.update(water_body_type="ocean", is_water=True)
    elif mutation == "missing_distance": del c["distance_to_marine_water_km"]
    elif mutation == "tiny_humidity": c["oceanic_humidity_availability_index"] = 1e-10
    assert validate_marine_distance(w)


@pytest.mark.parametrize("mutation", ["null", "edge", "disconnect"])
def test_defined_distance_requires_current_connected_marine_geometry(mutation):
    w = world("ocean", "land")
    enrich_world_with_climate_continentality(w)
    assert validate_marine_distance(w) == []
    if mutation == "null": w["cells"][0]["distance_to_marine_water_km"] = None
    elif mutation == "edge": w["cell_adjacency_edges"][0]["great_circle_distance_km"] += 1.0
    else:
        w["cell_adjacency_edges"] = []
        for c in w["cells"]: c["neighbors"] = []
    assert validate_marine_distance(w)


def test_unmarked_numeric_history_is_preserved_but_arbitrary_null_is_refused():
    w = world("land")
    w["cells"][0]["distance_to_marine_water_km"] = 0.0
    assert require_marine_distance(w) is False
    assert _surface_connection_index(w["cells"][0], natural=True) == 0.28
    w["cells"][0]["distance_to_marine_water_km"] = None
    assert validate_marine_distance(w)


def test_known_ocean_absence_does_not_remove_total_moisture_or_other_climate_inputs():
    w = world("land")
    w["cells"][0].update(precipitation_mm_y=1200.0, humidity_transport_index=1.0,
                         advected_moisture_factor=1.5, upwind_ocean_fetch_km=2000.0)
    enrich_world_with_climate_continentality(w)
    c = w["cells"][0]
    assert c["oceanic_humidity_availability_index"] == 0.0
    assert c["precipitation_mm_y"] == 1200.0 and c["humidity_transport_index"] == 1.0
    assert c["continentality_index"] == 0.58
    assert validate_marine_distance(w) == []


def test_reenrichment_rebuilds_changed_geographic_source_atomically():
    w = world("land", "land")
    enrich_world_with_climate_continentality(w)
    w["cells"][0].update(water_body_type="ocean", is_water=True)
    enrich_world_with_climate_continentality(w)
    assert [c["distance_to_marine_water_km"] for c in w["cells"]] == [0.0, 100.0]
    assert w["summary"]["no_marine_source_cell_count"] == 0
    assert validate_marine_distance(w) == []


@pytest.mark.parametrize("mutation", ["unknown_water", "neighbors", "edge_coverage", "unknown_model"])
def test_invalid_source_cannot_publish_a_known_absence_or_partial_result(mutation):
    w = world("land", "land")
    if mutation == "unknown_water": w["cells"][-1]["water_body_type"] = "unclassified"
    elif mutation == "neighbors": w["cells"][-1]["neighbors"] = None
    elif mutation == "edge_coverage": w["cell_adjacency_edges"] *= 2
    else: w["climate_continentality_model"] = {"model_type": "unknown"}
    before = deepcopy(w)
    with pytest.raises(ValueError): enrich_world_with_climate_continentality(w)
    assert w == before


def groundwater_source(water="land"):
    w = world(water)
    w["cells"][0].update(
        basin_id=0, lithology="limestone", landform="plain", sediment_thickness_m=1.0,
        soil_drainage_index=.4, soil_moisture_index=.6, soil_salinity_index=.1,
        seasonal_aridity_index=.2, ice_thickness_m=0.0, flow_accumulation=1000.0,
        infiltration_mm_y=300.0, elevation_m=500.0, water_depth_m=0.0,
    )
    w["summary"]["total_infiltration_km3_y"] = .0003
    enrich_world_with_climate_continentality(w)
    return w


@pytest.mark.parametrize("water, connection", [("land", 0.0), ("fresh_lake", 0.56)])
def test_public_natural_groundwater_keeps_other_water_sources_and_replays(water, connection):
    from magic_geo.aquifer_resources import enrich_world_with_aquifer_resources
    from magic_geo.groundwater_flow import enrich_world_with_groundwater_flow
    from magic_geo.natural_groundwater_validation import validate_natural_groundwater_flow
    w = groundwater_source(water)
    enrich_world_with_aquifer_resources(w)
    enrich_world_with_groundwater_flow(w)
    c = w["cells"][0]
    assert c["distance_to_marine_water_km"] is None
    expected_fraction = max(0.0, min(1.0, connection * .58 + .10 + c["aquifer_productivity_index"] * .08 - c["aquifer_natural_limitation_index"] * .12))
    assert c["groundwater_discharge_km3_y"] == round(c["groundwater_available_volume_km3_y"] * expected_fraction, 6)
    assert validate_natural_groundwater_flow(w) == []


@pytest.mark.parametrize("change", ["missing_marker", "forged_absence", "unmarked_null"])
def test_groundwater_rejects_unproven_null_before_mutation(change):
    from magic_geo.aquifer_resources import enrich_world_with_aquifer_resources
    from magic_geo.groundwater_flow import enrich_world_with_groundwater_flow
    w = groundwater_source()
    enrich_world_with_aquifer_resources(w)
    if change in {"missing_marker", "unmarked_null"}:
        del w["climate_continentality_model"]
    if change == "unmarked_null":
        del w["cells"][0]["marine_distance_status"]
        del w["summary"]["marine_distance_defined_cell_count"]
        del w["summary"]["no_marine_source_cell_count"]
    if change == "forged_absence": w["cells"][0].update(water_body_type="ocean", is_water=True)
    before = deepcopy(w)
    with pytest.raises(ValueError): enrich_world_with_groundwater_flow(w)
    assert w == before


def species_source():
    from magic_geo.ecosystem_dynamics import enrich_world_with_ecosystem_dynamics
    w = world("land")
    w.update(wetland_systems=[], reef_systems=[], aquifer_systems=[])
    w["cells"][0].update(
        temperature_c=18.0, temperature_monthly_c=[18.0] * 12,
        biome="temperate_forest", biome_ecotone_type="none", island_class="continent",
        reef_type="none", wetland_system_type="none", wetland_system_id=-1,
        reef_system_id=-1, aquifer_system_id=-1, basin_id=-1,
        precipitation_mm_y=1200.0, potential_evapotranspiration_mm_y=1000.0,
        soil_moisture_index=1.0, fertility=1.0, growing_season_months=12,
        runoff_mm_y=0.0, ocean_current_temperature_c=0.0, ocean_current_east=0.0,
        ice_thickness_m=0.0, seasonal_aridity_index=1.0, soil_organic_matter_fraction=.2,
        fire_frequency_index=1.0, ecotone_index=.4, erosion_rate=0.0,
        wind_east=1.0, wind_north=0.0, groundwater_recharge_mm_y=0.0,
        floodplain_connectivity_index=0.0, climate_energy_stress_index=1.0,
        reef_growth_index=0.0, biome_confidence_index=.7, wetland_hydrology_index=0.0,
        river_channel_width_m=0.0, river_channel_depth_m=0.0, elevation_m=0.0,
        permafrost_extent_index=0.0,
    )
    enrich_world_with_climate_continentality(w)
    enrich_world_with_ecosystem_dynamics(w)
    return w


def test_public_current_species_accepts_known_absence_without_losing_other_scores():
    from magic_geo.species_ranges import enrich_world_with_species_ranges, _guild_scores
    from magic_geo.species_habitat_validation import validate_species_habitat_support
    w = species_source()
    enrich_world_with_species_ranges(w)
    assert validate_species_habitat_support(w) == []
    c = w["cells"][0]
    assert c["species_mangrove_coastal_bird_score_supported"] is True
    assert all(math.isfinite(value) for value in c["species_guild_scores"].values())
    coastal_control = dict(c, distance_to_marine_water_km=0.0)
    coastal_control.pop("marine_distance_status")
    coastal_scores = _guild_scores(coastal_control)
    for guild, value in c["species_guild_scores"].items():
        assert value == pytest.approx(coastal_scores[guild] - (.14 if guild == "mangrove_coastal_bird" else 0.0), abs=1e-6)
    assert all(r["habitat_evidence"]["coastal_cell_fraction"] == 0 for r in w["species_range_records"])


@pytest.mark.parametrize("mutation", ["missing_marker", "wrong_status", "marine_source"])
def test_current_species_refuses_forged_no_source_parent_atomically(mutation):
    from magic_geo.species_ranges import enrich_world_with_species_ranges
    w = species_source()
    if mutation == "missing_marker": del w["climate_continentality_model"]
    elif mutation == "wrong_status": w["cells"][0]["marine_distance_status"] = "reachable_marine"
    else: w["cells"][0].update(water_body_type="ocean", is_water=True)
    before = deepcopy(w)
    with pytest.raises(ValueError): enrich_world_with_species_ranges(w)
    assert w == before
