"""Display metadata for declared estimates; never a numerical validator.

Raw values remain in the source tables. These rules describe missing estimates
and surface applicability solely for renderers and portable export schemas.
"""
from __future__ import annotations

import math
from typing import Any

CELL_SUPPORT = {
    "settlement_score": "settlement_climate_supported",
    "harbor_suitability_index": "harbor_suitability_supported",
    "navigability_index": "navigability_supported",
    "navigability_class": "navigability_classification_supported",
    "navigable_waterway_id": "navigable_waterway_membership_complete",
    "protected_bay_index": "protected_bay_supported",
    "river_mouth_port_index": "river_mouth_port_supported",
    "port_suitability_index": "port_suitability_supported",
    "port_site_id": "port_site_selection_supported",
    "port_site_type": "port_site_selection_supported",
    "coastal_route_index": "coastal_route_supported",
    "route_corridor_id": "route_corridor_membership_complete",
    "route_corridor_type": "route_corridor_membership_complete",
    "route_corridor_index": "route_corridor_membership_complete",
    "mining_potential_index": "mining_potential_supported",
    "mining_zone_id": "mining_zone_membership_supported",
}
GROUNDED_ICE_FIELDS = frozenset({
    "ice_thickness_m", "glacier_flow_to", "ice_surface_mass_balance_m_y",
    "basal_sliding_index", "ice_velocity_m_y", "glacial_erosion_m",
})
RECORD_SUPPORT = {
    "accessibility_index": "accessibility_supported",
    "economic_viability_index": "economic_viability_supported",
    "mean_resource_viability_index": "mean_resource_viability_supported",
    "spouse_ruler_id": "alliance_estimate_available",
    "marriage_alliance_id": "alliance_estimate_available",
    "role": "role_available",
}
STRING_FIELDS = {"navigability_class", "port_site_type", "route_corridor_type", "corridor_type", "role"}
BOOLEAN_FIELDS = {"high_contact_speaker_history", "high_inventory_stress"}
NULLABLE_LIST_FIELDS = {"path_cell_ids", "navigable_waterway_ids", "port_site_ids"}
RECORD_CONTEXT_SUPPORT = {
    "route_corridor_id": "route_path_supported",
    "path_cell_ids": "route_path_supported",
    "route_corridor_type": "route_corridor_diagnostics_supported",
    "corridor_type": "route_corridor_diagnostics_supported",
    "mean_route_corridor_index": "route_corridor_membership_complete",
    "max_route_corridor_index": "route_corridor_membership_complete",
    "navigable_waterway_ids": "navigable_waterway_links_complete",
    "port_site_ids": "port_site_links_complete",
}
FAMILY_COVERAGE = {
    "navigable_waterways": "navigable_waterway_selection_complete",
    "port_sites": "port_site_selection_complete",
    "route_corridors": "route_corridor_membership_complete",
    "mining_zones": "mining_zone_selection_complete",
    "firm_agents": "firm_selection_complete",
    "individual_agents": "individual_sampling_complete",
    "individual_life_events": "individual_sampling_complete",
    "market_agent_orders": "market_order_selection_complete",
}
SOCIAL_FAMILY_COVERAGE = {
    "ruins": "ruin_inference_available",
    "conflicts": "conflict_inference_available",
    "dynasties": "dynasty_inference_available",
    "historical_events": "historical_event_inference_available",
    "territorial_snapshots": "territorial_snapshot_inference_available",
}
FIELD_ESTIMATE_FAMILIES = {
    "population_regions", "cultures", "historical_eras", "population_histories",
    "economy_histories", "household_cohorts", "demographic_agent_histories",
    "logistics_networks", "market_exchanges", "speaker_population_histories",
    "route_capacity_constraints", "market_clearing_records",
    "market_price_iterations", "market_inventory_histories",
}
GENEALOGY_COVERAGE = {"rulers": "lineage_inference_available", "cadet_branches": "lineage_inference_available", "marriage_alliances": "alliance_inference_available"}
CAMPAIGN_COVERAGE = {"campaign_movements": "movement", "campaign_path_segments": "movement", "campaign_front_histories": "front", "tactical_engagements": "tactical", "strategic_campaign_plans": "strategic"}


def field_support(record: dict[str, Any], name: str) -> str | None:
    """Return an explicitly published support key, including native maps."""
    from .native_social_availability import NULLABLE_FIELDS
    contextual = RECORD_CONTEXT_SUPPORT.get(name)
    if contextual and type(record.get(contextual)) is bool:
        return contextual
    explicit = {**CELL_SUPPORT, **RECORD_SUPPORT}.get(name)
    if explicit and type(record.get(explicit)) is bool:
        return explicit
    for family in NULLABLE_FIELDS.values():
        for flag, names in family.items():
            if name in names and type(record.get(flag)) is bool:
                return flag
    for key, flags in record.items():
        if key.endswith("availability") and isinstance(flags, dict) and type(flags.get(name)) is bool:
            return key + "." + name
    return None


def nullable_kind(records: list[dict[str, Any]], name: str) -> str | None:
    if name == "distance_to_marine_water_km" and any(
        record.get("marine_distance_status") == "no_marine_source" for record in records
    ):
        return "float"
    if name == "mean_distance_to_marine_water_km" and any(
        record.get("region_class") == "no_marine_source"
        and type(record.get("marine_distance_defined_cell_count")) is int
        and record["marine_distance_defined_cell_count"] == 0
        and type(record.get("no_marine_source_cell_count")) is int
        and record["no_marine_source_cell_count"] == record.get("cell_count")
        for record in records
    ):
        return "float"
    if name in NULLABLE_LIST_FIELDS:
        return None
    if not any(field_support(record, name) for record in records):
        return None
    if name in STRING_FIELDS:
        return "str"
    if name in BOOLEAN_FIELDS:
        return "bool"
    if name.endswith("_id") or name.endswith("_count"):
        return "int"
    return "float"


def marine_distance_layer_metadata(name: str, records: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Preserve declared no-source meaning; this is not geographic replay."""
    if name != "distance_to_marine_water_km" or not records or not all(
        record.get("marine_distance_status") in ("reachable_marine", "no_marine_source")
        for record in records
    ):
        return None
    count = 0
    for record in records:
        distance = record.get(name)
        if record["marine_distance_status"] == "no_marine_source":
            if name not in record or distance is not None:
                raise ValueError("marine distance no-source display requires explicit null")
            count += 1
        elif type(distance) not in (int, float) or not math.isfinite(distance) or distance < 0:
            raise ValueError("marine distance reachable display requires finite nonnegative distance")
    return {"status_field": "marine_distance_status", "no_source_cell_count": count}


def layer_applicability(name: str, columns: dict[str, list[Any]]) -> dict[str, str] | None:
    if name in GROUNDED_ICE_FIELDS and "grounded_ice_surface_applicable" in columns:
        return {"kind": "boolean_field_v1", "field": "grounded_ice_surface_applicable"}
    if name == "settlement_score" and "settlement_climate_supported" in columns:
        if "is_water" in columns and "is_lake" in columns:
            return {"kind": "native_exposed_land_v1"}
    if name == "mining_potential_index" and "mining_potential_supported" in columns:
        return {"kind": "boolean_field_v1", "field": "mining_surface_applicable"}
    return None


def applicability_fields(rule: Any) -> tuple[str, ...]:
    """Validate the complete public descriptor before looking up any column."""
    if type(rule) is not dict:
        raise ValueError("invalid layer applicability metadata")
    if rule == {"kind": "native_exposed_land_v1"}:
        return ("is_water", "is_lake")
    if rule in (
        {"kind": "boolean_field_v1", "field": "mining_surface_applicable"},
        {"kind": "boolean_field_v1", "field": "grounded_ice_surface_applicable"},
    ):
        return (rule["field"],)
    raise ValueError("invalid layer applicability rule")


def inapplicable(rule: dict[str, str], values: tuple[Any, ...]) -> bool:
    fields = applicability_fields(rule)
    if len(values) != len(fields) or any(type(value) is not bool for value in values):
        raise ValueError("layer applicability requires typed boolean source fields")
    return any(values) if rule["kind"] == "native_exposed_land_v1" else values[0] is False


def validate_layer_display_metadata(layer: dict[str, Any], cell_count: int) -> None:
    if "marine_distance" in layer:
        rule = layer["marine_distance"]
        if (layer.get("id") != "cells/distance_to_marine_water_km"
                or layer.get("source") != "cells" or layer.get("name") != "distance_to_marine_water_km"
                or layer.get("kind") != "numeric" or type(rule) is not dict
                or set(rule) != {"status_field", "no_source_cell_count"}
                or rule["status_field"] != "marine_distance_status"
                or type(rule["no_source_cell_count"]) is not int
                or not 0 <= rule["no_source_cell_count"] <= cell_count
                or (rule["no_source_cell_count"] == cell_count) != ("stats" not in layer)):
            raise ValueError("invalid marine distance display metadata")
    if "availability" in layer:
        rule = layer["availability"]
        if (type(rule) is not dict or set(rule) != {"field", "unavailable_when"}
                or type(rule["field"]) is not str or rule["unavailable_when"] not in ("false", "zero")):
            raise ValueError("invalid layer availability metadata")
    if "applicability" in layer:
        applicability_fields(layer["applicability"])
        counts = [layer.get(key) for key in ("inapplicable_cell_count", "unavailable_cell_count")]
        if any(type(value) is not int or not 0 <= value <= cell_count for value in counts) or sum(counts) > cell_count:
            raise ValueError("invalid separate applicability/availability cell counts")


def family_coverage(world: dict[str, Any], family: str) -> dict[str, Any]:
    field = FAMILY_COVERAGE.get(family)
    source = world.get("summary", {})
    if family in SOCIAL_FAMILY_COVERAGE:
        field = SOCIAL_FAMILY_COVERAGE[family]
        source = world.get("native_social_availability", {})
    if family in GENEALOGY_COVERAGE:
        field = GENEALOGY_COVERAGE[family]
        source = world.get("genealogy_availability", {})
    if family in CAMPAIGN_COVERAGE:
        field = "inference_available"
        source = world.get("campaign_operations_availability", {}).get(CAMPAIGN_COVERAGE[family], {})
    if field and type(source.get(field)) is bool:
        return {"field": field, "complete": source[field], "scope": "complete_source_domain"}
    if family in FIELD_ESTIMATE_FAMILIES and "native_social_availability_model" in world:
        return {"complete": None, "scope": "field_specific_availability"}
    return {"complete": None, "scope": "availability_undeclared"}


def require_grounded_ice_display_inputs(world: dict[str, Any]) -> None:
    """Check declared presentation inputs, not geometry or numerical equations."""
    from .grounded_ice_validation import APPLICABLE, RAW_THICKNESS, grounded_ice_version
    if grounded_ice_version(world) == 0:
        return
    cells = world.get("cells", [])
    if type(cells) is not list:
        raise ValueError("grounded ice display requires a cells list")
    for index, cell in enumerate(cells):
        if type(cell) is not dict or type(cell.get(APPLICABLE)) is not bool:
            raise ValueError(f"grounded ice display cell {index} requires typed applicability")
        thickness = cell.get(RAW_THICKNESS)
        try:
            valid = type(thickness) in (int, float) and math.isfinite(thickness)
        except OverflowError:
            valid = False
        if not valid:
            raise ValueError(f"grounded ice display cell {index} requires finite raw thickness")


def display_contract(world: dict[str, Any]) -> dict[str, Any]:
    require_grounded_ice_display_inputs(world)
    return {
        "schema": "typed_estimate_display_v1",
        "scope": world.get("generation_scope", "full"),
        "models": {key: value for key, value in world.items()
                   if key.endswith("_model") and isinstance(value, dict)},
        "null_policy": "false_support_means_null_for_new_derived_estimates; legacy_absence_is_undeclared",
        "settlement_policy": "stored_zero_requires_water_or_lake_structural_case_or_true_climate_support",
        "validation_scope": "presentation_metadata_not_independent_scientific_replay",
        "families": {key: family_coverage(world, key)
                     for key in FAMILY_COVERAGE.keys() | SOCIAL_FAMILY_COVERAGE.keys() | GENEALOGY_COVERAGE.keys() | CAMPAIGN_COVERAGE.keys() | FIELD_ESTIMATE_FAMILIES
                     if key in world},
    }
