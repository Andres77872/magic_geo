"""Full CLI checks of original complete worlds and the ordered consumer replay.

The retained inputs were actually generated as full worlds. Only the Python
consumer tail is replayed; no native generation or physics is substituted.
"""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from magic_geo import api
from magic_geo.aquatic_climate_validation import _EXPECTED_MODELS
from magic_geo.cli import app
from magic_geo.cli.commands.validate import _ecology_contract_preflight, _resource_count_mismatches
from magic_geo.climate_energy_validation_dispatch import climate_energy_validation_mode, validate_native_climate_energy_output
from magic_geo.geo_validation_physics import _validate_climate_energy
from magic_geo.io import write_json


FIXTURES = Path(__file__).parent / "fixtures/cli_ecology_parent_availability"
PHYSICAL_FIELDS = (
    "id", "position_3d", "area_km2", "lat_deg", "lon_deg", "elevation_m",
    "is_water", "is_lake", "water_body_type", "water_depth_m", "ice_thickness_m",
    "temperature_c", "temperature_monthly_c", "precipitation_mm_y", "fertility",
    "soil_type", "soil_depth_m", "lithology", "crust_type", "plate_id", "biome", "resource",
)
PHYSICAL_TABLES = (
    "climate_model", "climate_energy_model", "climate_energy_balance_records",
    "climate_energy_forcing_intervals", "climate_energy_transport_edges",
    "plate_motion_history", "hillslope_sediment_transport_history",
    "glacial_sediment_transport_history", "fluvial_sediment_routing_history", "soil_profiles",
)


def _load(label):
    manifest = json.loads((FIXTURES / "manifest.json").read_text())[label]
    compressed = (FIXTURES / manifest["fixture"]).read_bytes()
    assert hashlib.sha256(compressed).hexdigest() == manifest["fixture_gzip_sha256"]
    raw = gzip.decompress(compressed)
    assert hashlib.sha256(raw).hexdigest() == manifest["world_sha256"]
    world = json.loads(raw)
    assert world.get("generation_scope", "full_world") == "full_world"
    assert len(world["cells"]) == 128
    return world


def _replay_consumer_tail(original):
    world = deepcopy(original)
    physical = [{k: deepcopy(c[k]) for k in PHYSICAL_FIELDS if k in c} for c in world["cells"]]
    tables = {k: world[k] for k in PHYSICAL_TABLES if k in world}
    table_values = deepcopy(tables)
    api._enrich_ecosystems_and_resources(world)
    # Exact post-ecosystem order in api.generate_world. This refreshes every
    # downstream ID-dependent output after fishery deposits/commodities change.
    for enrich in (
        api.enrich_world_with_land_use_zones, api.enrich_world_with_natural_frontiers,
        api.enrich_world_with_worldbuilding_realism, api.enrich_world_with_population_history,
        api.enrich_world_with_economy_history, api.enrich_world_with_dynasty_genealogy,
        api.enrich_world_with_logistics_history, api.enrich_world_with_demographic_agents,
        api.enrich_world_with_market_clearing, api.enrich_world_with_graph_diagnostics,
        api.enrich_world_with_boundary_geometry, api.enrich_world_with_phonology_history,
    ):
        enrich(world)
    assert physical == [{k: c[k] for k in PHYSICAL_FIELDS if k in c} for c in world["cells"]]
    assert all(world[k] is value and world[k] == table_values[k] for k, value in tables.items())
    if climate_energy_validation_mode(world) == "native":
        errors, _ = validate_native_climate_energy_output(world)
        assert not errors, errors
    else:
        checks = []
        _validate_climate_energy(world, checks)
        assert checks[0]["passed"], checks[0]
    return world


@pytest.fixture(scope="module")
def originals():
    return {label: _load(label) for label in ("warm", "cold", "legacy")}


@pytest.fixture(scope="module")
def migrated(originals):
    return {label: _replay_consumer_tail(world) for label, world in originals.items()}


def _run_cli(world, tmp_path):
    path = tmp_path / "world.json"
    write_json(path, world)
    return CliRunner().invoke(app, ["validate", "--world", str(path)])


@pytest.mark.parametrize("label", ["warm", "cold", "legacy"])
def test_original_known_historical_consumers_still_pass_full_cli(originals, label, tmp_path):
    world = originals[label]
    assert world["ecosystem_dynamics_model"]["model"] == "heuristic_ecosystem_climate_support_v3"
    result = _run_cli(world, tmp_path)
    assert result.exit_code == 0, (result.output, repr(result.exception))


@pytest.mark.parametrize("label", ["warm", "cold", "legacy"])
def test_ordered_current_consumers_pass_full_cli_without_changing_physics(migrated, label, tmp_path):
    world = migrated[label]
    assert world["ecosystem_dynamics_model"]["model"] == "heuristic_ecosystem_climate_support_v4"
    assert world["species_ranges_model"]["model"] == "heuristic_species_parent_support_v3"
    expected_fire = "heuristic_wildfire_parent_availability_v4" if label == "legacy" else "heuristic_wildfire_native_seasonal_parent_availability_v5"
    assert world["wildfire_disturbance_model"]["model"] == expected_fire
    assert world["resource_deposit_model"]["model_type"] == "causal_geologic_resource_deposit_diagnostics_v3"
    assert world["commodity_occurrence_model"]["model_type"] == "causal_resource_commodity_occurrences_with_parent_support_v1"
    result = _run_cli(world, tmp_path)
    assert result.exit_code == 0, (result.output, repr(result.exception))


def _assert_rejected(world, tmp_path, fragment):
    result = _run_cli(world, tmp_path)
    assert result.exit_code == 1, (result.output, repr(result.exception))
    assert isinstance(result.exception, SystemExit), repr(result.exception)
    assert fragment in result.output, result.output


@pytest.mark.parametrize("model_key", [
    "ecosystem_dynamics_model", "species_ranges_model", "wildfire_disturbance_model",
    "resource_deposit_model", "commodity_occurrence_model",
])
@pytest.mark.parametrize("mutation", ["unknown", "partial", "none", "list"])
def test_partial_or_unknown_current_declarations_fail_before_eager_consumers(migrated, model_key, mutation, tmp_path):
    world = deepcopy(migrated["warm"])
    if mutation == "unknown":
        world[model_key] = {"model": "unrecognized", "model_type": "unrecognized"}
    elif mutation == "partial":
        declaration = world[model_key]
        key = "model_type" if "model_type" in declaration else "model"
        world[model_key] = {key: declaration[key]}
    else:
        world[model_key] = None if mutation == "none" else []
    _assert_rejected(world, tmp_path, "FAIL")


@pytest.mark.parametrize("child", ["species", "wildfire", "resources"])
@pytest.mark.parametrize("declaration", ["absent", "known_historical"])
def test_complete_v4_output_cannot_delete_child_declarations_and_all_new_flags(originals, migrated, child, declaration, tmp_path):
    world = deepcopy(migrated["warm"])
    if child == "species":
        del world["species_ranges_model"]
        if declaration == "known_historical":
            world["species_ranges_model"] = deepcopy(originals["warm"]["species_ranges_model"])
        for cell in world["cells"]:
            for key in list(cell):
                if key.startswith("species_") and (key.endswith("_supported") or key in {
                    "species_guild_scores", "species_composition_status", "species_applicable_guild_count", "species_supported_guild_count",
                }):
                    del cell[key]
        fragment = "complete ecosystem v4 output requires species parent-support v3"
    elif child == "wildfire":
        del world["wildfire_disturbance_model"]
        if declaration == "known_historical":
            world["wildfire_disturbance_model"] = deepcopy(originals["warm"]["wildfire_disturbance_model"])
        for cell in world["cells"]:
            for key in ("wildfire_fuel_continuity_supported", "wildfire_firebreak_supported", "wildfire_ignition_potential_supported"):
                del cell[key]
        fragment = "complete ecosystem v4 output requires its climate-matched wildfire"
    else:
        del world["resource_deposit_model"]
        del world["commodity_occurrence_model"]
        if declaration == "known_historical":
            world["resource_deposit_model"] = deepcopy(originals["warm"]["resource_deposit_model"])
        for cell in world["cells"]:
            for key in ("fishery_resource_proxy_applicable", "fishery_resource_proxy_supported", "fishery_commodity_applicable", "fishery_commodity_supported"):
                del cell[key]
        fragment = "biological resources"
    # Deleting summary support counters as well cannot restore a legacy child.
    for key in list(world["summary"]):
        if (child == "species" and key.startswith("species_") and ("supported" in key or "composition_status" in key)) or (child == "wildfire" and key.startswith("wildfire_") and "supported" in key) or (child == "resources" and "fishery" in key and any(word in key for word in ("supported", "applicable"))):
            del world["summary"][key]
    _assert_rejected(world, tmp_path, fragment)


@pytest.mark.parametrize("label,other", [("warm", "legacy"), ("legacy", "warm")])
def test_current_fire_model_must_match_the_known_climate_branch(migrated, label, other, tmp_path):
    world = deepcopy(migrated[label])
    world["wildfire_disturbance_model"] = deepcopy(migrated[other]["wildfire_disturbance_model"])
    _assert_rejected(world, tmp_path, "climate-matched wildfire")


@pytest.mark.parametrize("field", [
    "primary_productivity_supported", "species_richness_supported", "vegetation_biomass_supported",
    "ecosystem_disturbance_pressure_supported", "vegetation_recovery_supported",
    "species_canopy_tree_score_supported", "species_record_descriptors_supported",
    "wildfire_fuel_continuity_supported", "wildfire_firebreak_supported", "wildfire_ignition_potential_supported",
    "fishery_resource_proxy_supported", "fishery_commodity_supported",
])
def test_forged_parent_or_consumer_availability_is_rejected(migrated, field, tmp_path):
    world = deepcopy(migrated["cold"])
    cell = next(c for c in world["cells"] if c[field] is False)
    cell[field] = True
    _assert_rejected(world, tmp_path, "FAIL")


@pytest.mark.parametrize("field", [
    "vegetation_biomass_index", "species_richness_index", "ecosystem_disturbance_pressure_index",
    "vegetation_recovery_years", "wildfire_fuel_continuity_index", "wildfire_firebreak_index", "wildfire_ignition_potential_index",
])
@pytest.mark.parametrize("bad", [None, "0.0", True, []])
def test_malformed_unavailable_parent_values_fail_without_coercion_crashes(migrated, field, bad, tmp_path):
    world = deepcopy(migrated["cold"])
    cell = next(c for c in world["cells"] if c["vegetation_recovery_supported"] is False)
    cell[field] = bad
    _assert_rejected(world, tmp_path, "FAIL")


@pytest.mark.parametrize("source_key,record_key", [
    ("forest_growth_index", "mean_forest_growth_index"),
    ("fishery_productivity_index", "mean_fishery_productivity_index"),
])
def test_species_evidence_omission_is_conditional_and_not_a_missing_numeric_zero(migrated, source_key, record_key, tmp_path):
    world = deepcopy(migrated["warm"])
    records = world["species_range_records"]
    required = next(r for r in records if record_key in r["habitat_evidence"])
    del required["habitat_evidence"][record_key]
    _assert_rejected(world, tmp_path, "consumed habitat evidence mismatch")
    world = deepcopy(migrated["warm"])
    omitted = next(r for r in world["species_range_records"] if record_key not in r["habitat_evidence"])
    omitted["habitat_evidence"][record_key] = 0.0
    _assert_rejected(world, tmp_path, "consumed habitat evidence mismatch")


def test_supported_material_records_cannot_be_dropped_with_unavailable_fisheries(migrated, tmp_path):
    world = deepcopy(migrated["cold"])
    assert any(c["resource"] == "coastal_fisheries" and not c["fishery_resource_proxy_supported"] for c in world["cells"])
    deposit = next(d for d in world["resource_deposits"] if d["resource"] != "coastal_fisheries")
    world["resource_deposits"].remove(deposit)
    _assert_rejected(world, tmp_path, "coverage")


def test_historical_absence_does_not_become_a_required_current_model(originals, tmp_path):
    world = deepcopy(originals["legacy"])
    for key in ("ecosystem_dynamics_model", "species_ranges_model", "wildfire_disturbance_model"):
        del world[key]
    result = _run_cli(world, tmp_path)
    assert result.exit_code == 0, (result.output, repr(result.exception))


def test_actual_mixed_availability_fire_front_does_not_claim_physical_containment(migrated, tmp_path):
    world = deepcopy(migrated["legacy"])
    histories = world["wildfire_spread_histories"]
    partial = [h for h in histories if h["front_coverage_status"] == "partial_unavailable_inputs"]
    assert len(partial) == 2
    assert sum(h["unmodelled_front_edge_count"] for h in histories) == 4
    assert all(h["containment_scope"] == "coefficient_index_on_modelled_cells_not_physical_containment" for h in partial)
    history = partial[0]
    for record in [history, *history["steps"]]:
        record["front_coverage_status"] = "complete_for_examined_adjacency"
        for key in ("unmodelled_adjacent_cell_ids", "unmodelled_front_cell_ids", "unmodelled_front_edges"):
            record[key] = []
        record["unmodelled_front_edge_count"] = 0
    # Even summaries made consistent with the false completeness declaration
    # cannot erase the independently reconstructed unknown-input boundary.
    world["summary"]["wildfire_partial_front_history_count"] = sum(h["front_coverage_status"] == "partial_unavailable_inputs" for h in histories)
    world["summary"]["wildfire_unmodelled_adjacent_cell_count"] = len({i for h in histories for i in h["unmodelled_adjacent_cell_ids"]})
    world["summary"]["wildfire_unmodelled_front_edge_count"] = sum(h["unmodelled_front_edge_count"] for h in histories)
    _assert_rejected(world, tmp_path, "wildfire availability:")


def test_unavailable_icy_land_is_not_a_known_firebreak(migrated, tmp_path):
    world = deepcopy(migrated["cold"])
    cell = next(c for c in world["cells"] if c["wildfire_firebreak_supported"] is False and c["ice_thickness_m"] > 0)
    assert cell["wildfire_firebreak_index"] == 0.0
    assert cell["wildfire_disturbance_regime"] == "fuel_proxy_unavailable"
    cell["wildfire_firebreak_index"] = 1.0
    cell["wildfire_disturbance_regime"] = "ice_limited"
    _assert_rejected(world, tmp_path, "wildfire availability:")


@pytest.mark.parametrize("label", ["warm", "cold", "legacy"])
def test_nonfishery_material_records_keep_their_original_values(originals, migrated, label):
    def materials(world):
        return {d["cell_id"]: {k: v for k, v in d.items() if k != "id"}
                for d in world["resource_deposits"] if d["resource"] != "coastal_fisheries"}
    assert materials(migrated[label]) == materials(originals[label])


def test_old_unsupported_fishery_deposit_cannot_be_reinserted_as_known_resource(originals, migrated, tmp_path):
    world = deepcopy(migrated["cold"])
    cells = {c["id"]: c for c in world["cells"]}
    stale = next(d for d in originals["cold"]["resource_deposits"]
                 if d["resource"] == "coastal_fisheries" and not cells[d["cell_id"]]["fishery_resource_proxy_supported"])
    stale = deepcopy(stale)
    stale["id"] = len(world["resource_deposits"])
    world["resource_deposits"].append(stale)
    _assert_rejected(world, tmp_path, "coverage")


@pytest.mark.parametrize("raw_viability,expected_count", [(.6499998, 0), (.65, 1), (.6500002, 1)])
def test_current_raw_resource_threshold_preflight_takes_precedence_over_display_recount(raw_viability, expected_count):
    # Isolated resource-count branch, not a complete physical world. At these
    # declared shelf inputs the unchanged viability is .63576 + .126 * score.
    world = {"summary": {}, "planet_parameters": {"radius_km": 6371.0}, "cells": [{
        "id": 0, "area_km2": 1.0, "neighbors": [], "temperature_c": 18.0,
        "is_water": True, "is_lake": False, "water_body_type": "continental_shelf",
        "resource": "coastal_fisheries", "biome": "shallow_marine", "flow_accumulation": 1.0,
        "runoff_mm_y": 600.0, "settlement_score": (raw_viability - .63576) / .126,
    }]}
    world['ecosystem_dynamics_model'] = deepcopy(_EXPECTED_MODELS['heuristic_ecosystem_climate_support_v4'])
    api._enrich_ecosystems_and_resources(world)
    modes, _, errors = _ecology_contract_preflight(world, native_climate=False)
    assert not errors, errors
    assert modes["resources"]
    key = "high_viability_resource_deposit_count"
    assert world["summary"][key] == expected_count
    assert world["resource_deposits"][0]["economic_viability_index"] == .65
    displayed_counts = {"agricultural_resource_deposit_count": 1, key: 1}
    assert not _resource_count_mismatches(world["summary"], displayed_counts, parent_support_verified=True, records="resource deposits")
    historical_errors = _resource_count_mismatches(world["summary"], displayed_counts, parent_support_verified=False, records="resource deposits")
    assert bool(historical_errors) == (expected_count == 0)
    world["summary"][key] = 1 - expected_count
    assert _ecology_contract_preflight(world, native_climate=False)[2]


def test_current_material_threshold_uncertainty_does_not_override_structural_counts():
    # The independent audit bounds material rounding rather than claiming a raw
    # material replay. The CLI must retain that accepted uncertainty at .62.
    fertility = (.6199998 - .081216) / .56256
    world = {"summary": {}, "planet_parameters": {"radius_km": 6371.0}, "cells": [{
        "id": 0, "area_km2": 1.0, "neighbors": [], "temperature_c": 18.0,
        "is_water": False, "is_lake": False, "water_body_type": "land",
        "resource": "fertile_alluvium", "biome": "grassland", "landform": "plain",
        "flow_accumulation": 1.0, "fertility": fertility,
    }]}
    world['ecosystem_dynamics_model'] = deepcopy(_EXPECTED_MODELS['heuristic_ecosystem_climate_support_v4'])
    api._enrich_ecosystems_and_resources(world)
    modes, _, errors = _ecology_contract_preflight(world, native_climate=False)
    assert not errors, errors
    assert modes["resources"]
    assert world["commodity_occurrences"][0]["occurrence_potential_index"] == .62
    key = "high_potential_commodity_occurrence_count"
    assert world["summary"][key] == 0
    displayed_counts = {"bioproductive_commodity_occurrence_count": 1, key: 1}
    assert not _resource_count_mismatches(world["summary"], displayed_counts, parent_support_verified=True, records="commodity occurrences")
    assert _resource_count_mismatches(world["summary"], displayed_counts, parent_support_verified=False, records="commodity occurrences")
    world["summary"]["bioproductive_commodity_occurrence_count"] = 0
    errors = _resource_count_mismatches(world["summary"], displayed_counts, parent_support_verified=True, records="commodity occurrences")
    assert errors == ["bioproductive_commodity_occurrence_count does not match commodity occurrences"]
