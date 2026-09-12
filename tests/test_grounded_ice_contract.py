"""Grounded-domain controls only: no native generation or thermal integration."""
from copy import deepcopy
import gzip
import hashlib
import json
import math
from pathlib import Path

import pytest

from magic_geo.grounded_ice_validation import (
    MODEL, STABILITY_MODEL, RAW_THICKNESS, APPLICABLE,
    grounded_ice_version, require_grounded_ice, validate_grounded_ice,
)
from magic_geo.cryosphere_dynamics import enrich_world_with_ice_sheet_history
from magic_geo.cryosphere_stability import enrich_world_with_ice_sheet_stability
from magic_geo.cryosphere_flow import enrich_world_with_ice_flowline_history
from magic_geo.glacial_landforms import enrich_world_with_glacial_landforms
from magic_geo.cli.validators.sediment import _validate_glacial_sediment_transport

DATA = Path(__file__).parent / "data/grounded_ice"
ENRICHERS = (
    enrich_world_with_ice_sheet_history, enrich_world_with_ice_sheet_stability,
    enrich_world_with_ice_flowline_history, enrich_world_with_glacial_landforms,
)


def _load(name):
    manifest = json.loads((DATA / "manifest.json").read_text())
    raw = (DATA / name).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == manifest[name]["sha256"]
    return json.loads(gzip.decompress(raw) if name.endswith(".gz") else raw)


def unit_world():
    """Attach explicit test wrapper context; native physical records stay exact.

    The native unit intentionally omits full-world wrappers. Clock/feedback and
    summary mirrors below are synthetic serialization context, not independently
    generated world evidence. The actual transfer and source records are pinned.
    """
    world = _load("native_unit.json")
    world["planet_parameters"] = {"radius_km": 6371.0, "gravity_g": 1.0}
    world["summary"] = {"grounded_ice_model": MODEL["model_type"], "output_float_precision": 4, "ice_sheet_count": len(world["ice_sheets"])}
    stage = world["glacial_sediment_transport_history"][0]
    iterations = stage["feedback_stage_id"] - 1
    world["simulation_clock"] = {"configured_erosion_iteration_count": iterations, "nominal_timestep_ma": stage["nominal_elapsed_time_ma"] / iterations}
    mapping = {
        **{f"glacial_sediment_{k}": k for k in ("transfer_count", "source_cell_count", "target_cell_count", "land_target_transfer_count", "marine_target_transfer_count", "production_volume_km3", "deposition_volume_km3", "mass_balance_residual_km3", "terrain_volume_change_residual_km3")},
        "max_glacial_sediment_source_production_depth_m": "max_source_production_depth_m",
        "max_glacial_sediment_target_deposition_depth_m": "max_target_deposition_depth_m",
    }
    mirrors = {k: stage[v] for k, v in mapping.items()}
    world["summary"].update(mirrors, glacial_sediment_transport_stage_count=1)
    world["earth_system_feedback_history"] = [{} for _ in range(stage["feedback_stage_id"])] + [{**mirrors, "stage": "cryosphere_coupling", "cryosphere_applied": True, "erosion_applied": False}]
    return world


def sediment(world):
    return _validate_glacial_sediment_transport(world, world["summary"], {c["id"]: c for c in world["cells"]})


def test_actual_native_unit_domain_and_dry_to_lake_sediment():
    world = unit_world()
    before = deepcopy(world)
    assert require_grounded_ice(world)
    failures, expected, valid = sediment(world)
    assert valid, failures
    assert failures == []
    assert expected["production"][0] > 0 and expected["deposition"][1] > 0
    assert world == before
    assert world["cells"][1]["is_lake"] is True
    assert world["cells"][1][APPLICABLE] is False


def test_current_flow_stops_before_lake_and_context_landform_is_preserved():
    world = unit_world()
    # Explicit synthetic context case, independently distinct from raw unit.
    lake = world["cells"][1]
    lake.update(landform="glacial_lake", ice_sheet_id=0, deglaciation_age_ka=20.0, moraine_deposition_m=0.4)
    for enrich in ENRICHERS:
        enrich(world)
    assert validate_grounded_ice(world) == []
    assert world["grounded_ice_stability_model"] == STABILITY_MODEL
    assert world["ice_flowline_histories"] == []
    assert lake["ice_flowline_path_count"] == 0
    assert lake["glacial_landform_type"] == "glacial_lake"
    assert lake["deglaciation_age_ka"] == 20.0


@pytest.mark.parametrize("field", [APPLICABLE, RAW_THICKNESS, "is_lake", "is_water", "ice_sheet_id", "glacier_flow_to", "ice_surface_mass_balance_m_y", "neighbors"])
def test_missing_required_sources_reject_without_mutation(field):
    world = unit_world()
    del world["cells"][1][field]
    before = deepcopy(world)
    assert validate_grounded_ice(world)
    assert world == before


@pytest.mark.parametrize("field,value", [
    (APPLICABLE, True), ("ice_thickness_m", 25.0), (RAW_THICKNESS, 25.0),
    ("glacier_flow_to", 0), ("ice_surface_mass_balance_m_y", 0.1),
    ("ice_velocity_m_y", 1.0), ("glacial_erosion_m", 1.0),
    ("is_lake", "false"), (RAW_THICKNESS, False), (RAW_THICKNESS, math.inf),
    ("ice_sheet_id", 0), ("moraine_deposition_m", 0.2),
])
@pytest.mark.parametrize("enrich", ENRICHERS)
@pytest.mark.parametrize("reenrich", [False, True])
def test_invalid_current_parent_is_atomic_at_every_entry(field, value, enrich, reenrich):
    world = unit_world()
    if reenrich:
        for function in ENRICHERS:
            function(world)
    world["cells"][1][field] = value
    before = deepcopy(world)
    with pytest.raises(ValueError):
        enrich(world)
    assert world == before


@pytest.mark.parametrize("kind", ["missing_own", "missing_summary", "own_false", "unknown_own", "model_bool", "old_transport", "missing_link", "stability_orphan"])
def test_exact_dispatch_rejects_partial_unknown_and_mixed_models(kind):
    world = unit_world()
    if kind == "missing_own": del world["grounded_ice_model"]
    elif kind == "missing_summary": del world["summary"]["grounded_ice_model"]
    elif kind == "own_false": world["grounded_ice_model"] = False
    elif kind == "unknown_own": world["grounded_ice_model"]["model_type"] = "future"
    elif kind == "model_bool": world["grounded_ice_model"]["lake_ice_resolved"] = 0
    elif kind == "old_transport": world["glacial_sediment_transport_model"]["model_type"] = "downhill_area_conserving_glacial_sediment_transport_v2"
    elif kind == "missing_link": del world["glacial_sediment_transport_model"]["source_grounded_ice_model"]
    else: world["ice_sheet_stability_histories"] = []
    before = deepcopy(world)
    assert validate_grounded_ice(world)
    assert world == before


def test_raw_threshold_remains_strict_when_display_rounds_to_25():
    world = unit_world()
    c, sheet = world["cells"][0], world["ice_sheets"][0]
    c[RAW_THICKNESS] = math.nextafter(25.0, math.inf)
    c["ice_thickness_m"] = 25.0
    sheet.update(mean_ice_thickness_m=25.0, max_ice_thickness_m=25.0)
    assert require_grounded_ice(world)
    enrich_world_with_glacial_landforms(world)
    assert world["glacial_landform_systems"][0]["ice_covered_cell_count"] == 1
    c[RAW_THICKNESS] = 25.0
    assert validate_grounded_ice(world)
    c[RAW_THICKNESS] = math.nextafter(25.0, math.inf)
    c["ice_thickness_m"] = 25.001
    assert validate_grounded_ice(world)


@pytest.mark.parametrize("mutation", ["missing", "wrong_type", "wet_donor", "source_link", "snapshot", "forged_erosion"])
def test_v3_stage_domain_and_source_tampers_fail(mutation):
    world = unit_world()
    source = world["glacial_sediment_transport_history"][0]["input_cells"][0]
    if mutation == "missing": del source["is_lake"]
    elif mutation == "wrong_type": source["is_lake"] = 0
    elif mutation == "wet_donor": source["is_lake"] = True
    elif mutation == "source_link": world["glacial_sediment_transport_model"]["source_grounded_ice_model"] = "wrong"
    elif mutation == "snapshot": world["glacial_sediment_transport_model"]["stage_input_snapshot"] = "complete_cell_cryosphere_terrain_and_sediment_inventory_before_transport_v2"
    else: source["glacial_erosion_m"] += 1.0
    before = deepcopy(world)
    assert sediment(world)[2] is False
    assert world == before


def test_stage_lake_flag_is_not_compared_with_final_restabilized_flag():
    world = unit_world()
    # A retained lake receiver can be dry after restabilization. This changes
    # only the final flag, not the recorded stage's correctly wet destination.
    world["cells"][1]["is_lake"] = False
    world["cells"][1][APPLICABLE] = True
    assert sediment(world)[2] is True


def test_retained_legacy_v2_remains_accepted_without_retagging():
    world = _load("legacy_cold.json.gz")
    before = deepcopy(world)
    assert grounded_ice_version(world) == 0
    assert sediment(world)[2] is True
    assert world == before


def test_legacy_marine_ice_field_and_malformed_legacy_history_scope():
    world = {"cells": [{"id": 0, "is_water": True, "landform": "ice_field", "ice_thickness_m": 30.0, "lat_deg": 70.0}]}
    enrich_world_with_glacial_landforms(world)
    assert world["cells"][0]["glacial_landform_type"] == "ice_cap"
    assert grounded_ice_version({"glacial_sediment_transport_history": None}) == 0


def test_current_forged_water_flowline_and_landform_outputs_reject():
    world = unit_world()
    world["ice_flowline_histories"] = [{"flowline_cell_ids": [0, 1]}]
    assert validate_grounded_ice(world)
    del world["ice_flowline_histories"]
    world["cells"][1]["glacial_landform_type"] = "ice_cap"
    assert validate_grounded_ice(world)


def test_context_cannot_propagate_across_a_context_only_neighbor():
    world = unit_world()
    lake = world["cells"][1]
    lake.update(landform="glacial_lake", ice_sheet_id=0, deglaciation_age_ka=20.0)
    far = deepcopy(lake)
    far.update(id=2, neighbors=[1], is_lake=False, grounded_ice_surface_applicable=True)
    lake["neighbors"].append(2)
    world["cells"].append(far)
    assert any("directly adjacent" in failure for failure in validate_grounded_ice(world))


def test_native_display_precision_is_not_raw_precision():
    world = unit_world()
    world["summary"]["output_float_precision"] = 17
    assert validate_grounded_ice(world)


def test_api_rejects_parent_before_first_physical_enricher(monkeypatch):
    from magic_geo import api
    world = unit_world()
    world["cells"][1][RAW_THICKNESS] = 30.0
    before = deepcopy(world)
    def forbidden(*args, **kwargs):
        raise AssertionError("physical enrichment ran before grounded input audit")
    monkeypatch.setattr(api, "enrich_world_with_mesh_lod", forbidden)
    with pytest.raises(ValueError, match="grounded ice"):
        api._enrich_physical_foundation(world, None)
    assert world == before


def test_source_partition_v3_dispatch_with_explicit_zero_erosion_wrapper():
    from magic_geo.sediment_source_partition_validation import (
        COMMON_AUDIT_METADATA, validate_sediment_source_partitions,
    )
    world = unit_world()
    # This is a synthetic zero-erosion wrapper, not an actual full-world output.
    # Preserve every native glacial numerical record; explicitly relink only its
    # feedback slot to the wrapper's sole post-erosion stage.
    world["simulation_clock"]["configured_erosion_iteration_count"] = 0
    world["glacial_sediment_transport_history"][0]["feedback_stage_id"] = 1
    world["earth_system_feedback_history"] = [{"id": 0}, {"id": 1}]
    for prefix, kind, partition in (
        ("hillslope_sediment_transport", "pairwise_lithology_dependent_volume_conserving_hillslope_transport_v2", "available_alluvium_first_then_bedrock_erosion_v1"),
        ("fluvial_sediment_routing", "topological_capacity_limited_fluvial_sediment_routing_v1", "available_alluvium_after_hillslope_then_bedrock_erosion_v1"),
    ):
        model = {**COMMON_AUDIT_METADATA, "model_type": kind,
                 "source_material_partition_model": partition, "stage_count": 0,
                 "total_alluvium_entrainment_volume_km3": 0.0,
                 "total_bedrock_erosion_volume_km3": 0.0}
        if prefix.startswith("hillslope"):
            model.update(erosion_stage_source_partition_order="hillslope_before_fluvial", total_production_volume_km3=0.0)
        else:
            model.update(source_material_partition_is_coupled_external_state=True, total_local_source_volume_km3=0.0)
        world[prefix + "_model"] = model
        world[prefix + "_history"] = []
    before = deepcopy(world)
    result = validate_sediment_source_partitions(world)
    assert result["passed"], result["failures"]
    assert world == before
    del world["glacial_sediment_transport_history"][0]["input_cells"][0]["is_lake"]
    assert not validate_sediment_source_partitions(world)["passed"]


def test_retained_legacy_v2_source_partition_stays_accepted():
    from magic_geo.sediment_source_partition_validation import validate_sediment_source_partitions
    world = _load("legacy_cold.json.gz")
    before = deepcopy(world)
    result = validate_sediment_source_partitions(world)
    assert result["passed"], result["failures"]
    assert world == before
