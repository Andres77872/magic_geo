"""Real shared-library seasonal Python boundary and certificate preservation."""
from __future__ import annotations

from copy import deepcopy
from unittest.mock import patch

import pytest

from magic_geo.climate_energy import enrich_world_with_climate_energy_balance
from magic_geo.native import generate_seasonal_world, generate_seasonal_geo_world
from magic_geo.native_climate_energy_validation import audit_native_climate_energy
from magic_geo.native_climate_energy_enrichment_validation import validate_native_climate_energy_enrichment
from magic_geo.seasonal_config import SeasonalWorldConfig


@pytest.fixture(scope="module")
def native_worlds():
    data = {
        "config_version": 2, "run": {"seed": 424242, "name": "seasonal_python_boundary"},
        "mesh": {"cell_count": 128}, "tectonics": {"plate_count": 8},
        "erosion": {"iterations": 0}, "compute": {"threads": 1, "backend": "cpu"},
        "output": {"float_precision": 8},
    }
    config = SeasonalWorldConfig.model_validate(data)
    full = generate_seasonal_world(config, serialization="json")
    geo = generate_seasonal_geo_world(config, serialization="msgpack")
    return full, geo


def test_real_full_and_geography_routes_have_same_physical_solution(native_worlds):
    full, geo = native_worlds
    for key in ("climate_model", "climate_energy_model", "climate_energy_balance_records",
                "climate_energy_forcing_intervals", "climate_energy_transport_edges", "planet_parameters"):
        assert full[key] == geo[key]
    assert full["settlements"]
    assert not geo["settlements"]
    assert audit_native_climate_energy(full)["algebraic_checks"] > 12000


def test_real_native_enrichment_is_atomic_and_preserves_temperature_authority(native_worlds):
    full, _ = native_worlds
    world = deepcopy(full)
    keys = ("climate_model", "climate_energy_model", "climate_energy_balance_records",
            "climate_energy_forcing_intervals", "climate_energy_transport_edges")
    retained = {key: world[key] for key in keys}
    temperatures = [(cell["temperature_c"], cell["temperature_monthly_c"]) for cell in world["cells"]]
    enrich_world_with_climate_energy_balance(world)
    once = deepcopy(world)
    enrich_world_with_climate_energy_balance(world)
    assert world == once
    for key in keys:
        assert world[key] is retained[key]
        assert world[key] == full[key]
    for cell, (annual, monthly) in zip(world["cells"], temperatures):
        assert cell["temperature_c"] == annual
        assert cell["temperature_monthly_c"] is monthly
        assert "climate_energy_stress_index" not in cell
        assert "annual_net_heating_w_m2" in cell


def test_real_airless_output_has_empty_transport_and_finite_verified_budget():
    config = SeasonalWorldConfig(
        config_version=2, run={"name": "seasonal_airless_python"},
        mesh={"cell_count": 128}, tectonics={"plate_count": 8},
        erosion={"iterations": 0}, compute={"threads": 1, "backend": "cpu"},
        planet={"atmosphere_pressure_bar": 0.0}, output={"float_precision": 0},
    )
    world = generate_seasonal_geo_world(config)
    assert world["climate_energy_transport_edges"] == []
    assert all(record["infrared_optical_depth"] == 0 for record in world["climate_energy_balance_records"])
    assert all(record["atmospheric_heat_capacity_j_m2_k"] == 0 for record in world["climate_energy_balance_records"])
    assert audit_native_climate_energy(world)["full_world_display_fields_linked"] is True


@pytest.mark.parametrize("geography_only", [False, True])
def test_public_api_completes_native_physical_and_ecology_layers(native_worlds, geography_only):
    from magic_geo.api import generate_geo_world as api_geo, generate_world as api_full

    config = SeasonalWorldConfig(
        config_version=2, mesh={"cell_count": 128}, tectonics={"plate_count": 8},
        erosion={"iterations": 0}, compute={"threads": 1, "backend": "cpu"},
        output={"float_precision": 8},
    )
    raw = deepcopy(native_worlds[1 if geography_only else 0])
    preserved = {key: raw[key] for key in (
        "climate_model", "climate_energy_model", "climate_energy_balance_records",
        "climate_energy_forcing_intervals", "climate_energy_transport_edges",
    )}
    native_route = "generate_seasonal_geo_world" if geography_only else "generate_seasonal_world"
    legacy_route = "generate_geo_world" if geography_only else "generate_world"
    # Reuse this module's actual generated native states while exercising the
    # entire public Python pipeline and checking that it selects the V4 route.
    with patch(f"magic_geo.native.{native_route}", return_value=raw) as selected, \
         patch(f"magic_geo.native.{legacy_route}", side_effect=AssertionError("legacy route selected")):
        world = (api_geo if geography_only else api_full)(config)
    assert selected.call_args.args[0]["config_version"] == 2
    assert selected.call_args.args[0]["output"]["include_cells"] is True
    assert world is raw
    for key, value in preserved.items():
        assert world[key] is value
    assert audit_native_climate_energy(world)["full_world_display_fields_linked"] is True
    assert validate_native_climate_energy_enrichment(world) == []
    assert world["reef_diagnostics_model"]["bleaching_estimate_available"] is False
    assert world["ecosystem_dynamics_model"]["model"] == "heuristic_ecosystem_climate_support_v5"
    assert world["species_ranges_model"]["model"] == "heuristic_species_parent_support_v4"
    assert world["wildfire_disturbance_model"]["model"] == "heuristic_wildfire_native_seasonal_prescribed_natural_parent_availability_v7"
    assert world["resource_deposit_model"]["model_type"] == "causal_geologic_resource_deposit_diagnostics_v4"
    assert world["commodity_occurrence_model"]["model_type"] == "causal_resource_commodity_occurrences_with_parent_support_v2"
    assert all("reef_bleaching_risk_index" not in cell for cell in world["cells"])
    assert all("climate_energy_stress_index" not in cell for cell in world["cells"])
    if geography_only:
        assert world["generation_scope"] == "geo_only"
        assert "settlements" not in world
    else:
        assert world["settlements"]
        assert world["worldbuilding_realism_model"]["model_type"] == "causal_upstream_evidence_worldbuilding_realism_checks_v3"


def test_public_full_api_suppresses_cells_only_after_native_enrichment(native_worlds):
    from magic_geo.api import generate_world

    config = SeasonalWorldConfig(config_version=2, output={"include_cells": False, "float_precision": 8})
    raw = deepcopy(native_worlds[0])
    with patch("magic_geo.native.generate_seasonal_world", return_value=raw) as selected:
        world = generate_world(config)
    assert selected.call_args.args[0]["output"]["include_cells"] is True
    assert world["cells"] == []
    assert world["summary"]["native_climate_energy_record_count"] == 128
    assert len(world["climate_energy_balance_records"]) == 128
    assert world["reef_diagnostics_model"]["bleaching_estimate_available"] is False
