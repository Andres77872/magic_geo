"""A dry global Priority-Flood seed is not a wet watershed or a routing waiver."""
from copy import deepcopy

import pytest

from magic_geo.api import generate_geo_world
from magic_geo.config import WorldConfig
from magic_geo.geo_validation import validate_geo_world


@pytest.fixture(scope="module")
def dry_world():
    # Reproduce the actual Glasswind integration failure without depending on
    # ignored run artifacts or editing a generated flow graph to fit the test.
    config = WorldConfig.model_validate({
        "config_version": 2,
        "run": {"seed": 12051002, "name": "dry_global_drainage_regression"},
        "planet": {
            "radius_km": 5600.0, "gravity_g": 0.82, "day_length_hours": 30.0,
            "axial_tilt_deg": 18.0, "orbital_eccentricity": 0.05,
            "stellar_luminosity": 1.1, "atmosphere_pressure_bar": 0.7,
            "greenhouse_factor": 1.05, "ocean_fraction_target": 0.0,
            "ocean_water_inventory_km3": 0.0, "internal_heat": 0.75, "geological_age_ga": 5.6,
        },
        "mesh": {"cell_count": 128, "neighbor_count": 7},
        "tectonics": {"plate_count": 8, "continental_plate_fraction": 0.78, "continental_crust_fraction_target": 0.72},
        "climate": {"reference_infrared_optical_depth": 1.0, "precipitation_scale": 0.08, "subtropical_drying_strength": 0.88},
        "hydrology": {"river_percentile": 0.97, "preserve_geologic_depressions": True},
        "erosion": {"iterations": 0, "stream_power_coefficient": 3.0, "drainage_exponent": 0.45, "hillslope_diffusion": 0.025, "tectonic_uplift_scale": 0.55},
        "compute": {"backend": "cpu", "threads": 1},
        "output": {"include_cells": True, "float_precision": 4},
    })
    world = generate_geo_world(config)
    assert all(not cell["is_water"] and not cell["is_lake"] for cell in world["cells"])
    assert all(cell["runoff_mm_y"] == cell["flow_accumulation"] == 0.0 for cell in world["cells"])
    assert world["watersheds"] == []
    return world


def drainage(world):
    report = validate_geo_world(world, profile="generic")
    return report, next(check for check in report["checks"] if check["name"] == "acyclic_downhill_drainage")


def seed(world):
    return min(world["cells"], key=lambda cell: (cell["elevation_m"], cell["id"]))


def test_actual_zero_runoff_graph_and_global_seed_pass_complete_generic_validation(dry_world):
    report, check = drainage(dry_world)
    assert report["passed"], [check for check in report["checks"] if check["status"] == "failed"]
    assert check["passed"], check
    root = seed(dry_world)
    assert root["flow_to"] == root["spill_to"] == root["basin_id"] == -1
    assert not root["is_closed_basin"] and root["lake_basin_id"] == -1
    assert check["observed"]["dry_priority_flood_seed_cell_id"] == root["id"]
    assert check["observed"]["dry_priority_flood_seed_path_count"] > 0
    assert check["observed"]["processed_flow_cell_count"] == len(dry_world["cells"])
    assert check["observed"]["maximum_accumulation_residual"] == 0.0
    assert check["observed"]["land_basin_count"] == check["observed"]["watershed_basin_count"] == 0


@pytest.mark.parametrize("field", ["runoff_mm_y", "flow_accumulation"])
def test_even_tiny_positive_water_does_not_get_the_dry_terminal_contract(dry_world, field):
    world = deepcopy(dry_world)
    seed(world)[field] = 1e-12
    _report, check = drainage(world)
    assert not check["passed"]
    assert check["observed"]["dry_priority_flood_seed_cell_id"] is None
    assert check["observed"]["invalid_terminal_count"] > 0


@pytest.mark.parametrize("section,field", [
    ("summary", "hydrologic_surface_model"),
    ("summary", "depression_routing_model"),
    ("hydrologic_water_budget_model", "model_type"),
    ("hydrologic_water_budget_model", "runoff_computed_before_flow_routing"),
])
def test_dry_exception_requires_the_known_hydrology_contract(dry_world, section, field):
    world = deepcopy(dry_world)
    del world[section][field]
    _report, check = drainage(world)
    assert not check["passed"]
    assert check["observed"]["invalid_terminal_count"] > 0


@pytest.mark.parametrize("field", ["spill_elevation_m", "hydrologic_surface_elevation_m"])
def test_dry_global_seed_must_keep_the_unfilled_terrain_potential(dry_world, field):
    world = deepcopy(dry_world)
    seed(world)[field] += 1.0
    _report, check = drainage(world)
    assert not check["passed"]
    assert check["observed"]["dry_priority_flood_seed_cell_id"] is None


def test_an_arbitrary_dry_land_terminal_is_still_invalid(dry_world):
    world = deepcopy(dry_world)
    cell = next(cell for cell in world["cells"] if cell["flow_to"] >= 0 and not cell["is_closed_basin"])
    cell["flow_to"] = -1
    _report, check = drainage(world)
    assert not check["passed"]
    assert check["observed"]["invalid_terminal_count"] > 0


def test_dry_graph_still_rejects_uphill_edges_and_cycles(dry_world):
    world = deepcopy(dry_world)
    root = seed(world)
    parent = next(cell for cell in world["cells"] if cell["flow_to"] == root["id"])
    root["flow_to"] = parent["id"]
    _report, check = drainage(world)
    assert not check["passed"]
    assert check["observed"]["uphill_link_count"] > 0
    assert check["observed"]["cycle_cell_count"] > 0
    assert check["observed"]["processed_flow_cell_count"] < len(world["cells"])


def test_dry_graph_still_rejects_nonadjacent_downhill_edges(dry_world):
    world = deepcopy(dry_world)
    source, receiver = next(
        (cell, target) for cell in world["cells"] for target in world["cells"]
        if cell["flow_to"] >= 0 and target["id"] not in cell["neighbors"]
        and target["hydrologic_surface_elevation_m"] < cell["hydrologic_surface_elevation_m"] - 1.0
    )
    source["flow_to"] = receiver["id"]
    _report, check = drainage(world)
    assert not check["passed"]
    assert check["observed"]["nonneighbor_link_count"] > 0


def test_dry_graph_still_rejects_a_river_without_runoff(dry_world):
    world = deepcopy(dry_world)
    next(cell for cell in world["cells"] if cell["flow_to"] >= 0)["is_river"] = True
    _report, check = drainage(world)
    assert not check["passed"]
    assert check["observed"]["invalid_river_cell_count"] == 1
