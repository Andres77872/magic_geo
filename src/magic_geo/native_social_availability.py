"""Strict native social-source publication and coverage boundary.

Independent of the native producer. Source equations and complete numerical
replay remain the responsibility of the separate social validators.
"""
from __future__ import annotations

from collections import Counter
import math
from typing import Any

from .settlement_input_availability import require_settlement_v3_inputs

NATIVE_SOCIAL_MODEL = {'conflict_selection_policy': 'complete_actual_border_pair_sources_before_global_rank_cap',
 'history_policy': 'retain_independent_fields_and_families_with_explicit_incomplete_coverage',
 'model_type': 'native_settlement_source_complete_social_estimates_v1',
 'population_membership_policy': 'unchanged_nonmarine_political_territory_area_denominator',
 'population_response_policy': 'unchanged_independent_temperature_precipitation_ice_response',
 'ruin_selection_policy': 'complete_actual_candidate_sources_before_global_rank_spacing_cap',
 'scope': 'prescribed_social_estimate_availability_not_observed_occupation_or_human_survival',
 'site_source_policy': 'known_structural_zero_on_native_water_or_lake_else_exact_annual_settlement_support',
 'snapshot_policy': 'preserve_base_territory_and_null_unavailable_scaled_estimates',
 'source_settlement_climate_support_model': 'native_annual_settlement_suitability_proxy_support_v1',
 'source_settlement_selection_model': 'causal_native_score_local_max_separated_settlement_selection_v3',
 'unavailable_numeric_policy': 'null_with_strict_typed_availability_flag'}

SOCIAL_MODEL_TYPES = {'conflict_model': 'causal_border_pair_pressure_trade_conflict_selection_v2',
 'cultural_site_model': 'causal_terrain_culture_ranked_sacred_ruin_sites_v2',
 'culture_region_model': 'causal_political_homeland_barrier_trade_culture_regions_v2',
 'dynasty_model': 'causal_foundation_continuity_pressure_dynasty_lineages_v2',
 'historical_event_model': 'causal_region_culture_language_trade_site_timeline_v2',
 'population_region_model': 'causal_area_weighted_capacity_occupancy_population_regions_v2',
 'territorial_snapshot_model': 'causal_era_scaled_spherical_region_territorial_snapshots_v2'}

ENVELOPE_KEYS = frozenset(['conflict_candidate_pair_count',
 'conflict_inference_available',
 'conflict_supported_pair_count',
 'conflict_unavailable_region_pairs',
 'dynasty_applicable_region_count',
 'dynasty_available_region_count',
 'dynasty_inference_available',
 'dynasty_unavailable_region_ids',
 'historical_event_family_coverage',
 'historical_event_inference_available',
 'ruin_candidate_cell_count',
 'ruin_inference_available',
 'ruin_supported_candidate_cell_count',
 'ruin_unavailable_cell_ids',
 'territorial_snapshot_inference_available'])

SUMMARY_AVAILABILITY_KEYS = frozenset({
    "conflict_count", "dynastic_change_count", "dynastic_lineage_count", "dynasty_count",
    "dynasty_root_count", "dynasty_successor_link_count", "estimated_world_population",
    "high_economic_disruption_conflict_count", "high_intensity_conflict_count",
    "historical_event_count", "max_conflict_casualty_rate", "max_dynasty_lineage_depth",
    "mean_conflict_casualty_rate", "mean_conflict_economic_disruption_index",
    "mean_conflict_intensity", "mean_conflict_logistics_strain_index",
    "mean_cultural_continuity", "mean_dynastic_continuity_index", "mean_historical_instability",
    "mean_population_pressure", "mean_snapshot_boundary_perimeter_km",
    "mean_snapshot_compactness_index", "mean_snapshot_fragmentation_index",
    "mean_snapshot_geometry_quality", "mean_snapshot_polygon_area_error_fraction",
    "mean_war_duration_years", "ruin_count", "snapshot_polygon_region_count",
    "total_mobilized_population",
})

NULLABLE_FIELDS = {'CultureRegion': {'continuity_estimate_available': ['continuity_index', 'estimated_age_years'],
                   'ruin_count_available': ['ruin_count']},
 'HistoricalEra': {'event_count_available': ['event_count'],
                   'language_event_count_available': ['language_event_count'],
                   'mean_connectivity_available': ['mean_connectivity'],
                   'mean_instability_available': ['mean_instability'],
                   'migration_event_count_available': ['migration_event_count'],
                   'state_event_count_available': ['state_event_count']},
 'HistoricalEvent': {'continuity_estimate_available': ['continuity_index']},
 'PopulationRegion': {'capacity_estimate_available': ['carrying_capacity', 'urbanization_fraction'],
                      'migration_balance_available': ['migration_balance'],
                      'physical_means_available': ['agricultural_capacity_index',
                                                   'water_security_index',
                                                   'hazard_mortality_index'],
                      'population_estimate_available': ['estimated_population',
                                                        'population_pressure',
                                                        'growth_rate_per_year'],
                      'site_strength_available': ['site_strength_index']},
 'SnapshotRegion': {'geometry_estimate_available': ['area_km2',
                                                    'stability_index',
                                                    'boundary_perimeter_km',
                                                    'dissolved_polygon_area_km2',
                                                    'polygon_area_error_fraction',
                                                    'compactness_index',
                                                    'geometry_quality'],
                    'population_estimate_available': ['estimated_population']},
 'TerritorialSnapshot': {'geometry_estimate_available': ['assigned_land_fraction',
                                                         'largest_region_area_km2',
                                                         'largest_region_id',
                                                         'fragmentation_index'],
                         'population_estimate_available': ['estimated_population']}}

def exact_contract(actual: Any, expected: Any) -> bool:
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return actual.keys() == expected.keys() and all(exact_contract(actual[k], v) for k, v in expected.items())
    if type(expected) is list:
        return len(actual) == len(expected) and all(exact_contract(a, b) for a, b in zip(actual, expected))
    return actual == expected


def finite_number(value: Any) -> float:
    if type(value) not in (int, float):
        raise ValueError("social source requires a finite number")
    try:
        value = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError("social source requires a finite number") from error
    if not math.isfinite(value):
        raise ValueError("social source requires a finite number")
    return value


def native_area_matches(actual: Any, expected: float, terms: int, precision: int) -> bool:
    """Compare a coverage sum across the native decimal-serialization bridge.

    Cell areas use 17 decimal places; their accumulated population fields use
    the configured precision. The half decimal quantum is representation
    error, not an uncertainty in the area equation. Positive summands permit
    an absolute gamma(n) summation bound without cancellation amplification.
    """
    value = finite_number(actual)
    expected = finite_number(expected)
    if expected < 0 or type(terms) is not int or terms < 0 or type(precision) is not int or not 0 <= precision <= 8:
        raise ValueError("invalid native area comparison source")
    if value < 0:
        return False
    if terms == 0 or expected == 0:
        return value == 0
    if value != round(value, precision):
        return False
    unit = math.ulp(max(1.0, expected, abs(value)))
    cell_bridge = terms * (0.5e-17 + 0.5 * unit)
    product = max(0, terms - 1) * 2.0**-53
    if product >= 1:
        raise ValueError("native area comparison exceeds summation bound")
    gamma = product / (1.0 - product)
    if gamma >= 1:
        raise ValueError("native area comparison has no positive sum bound")
    source_upper = (expected + cell_bridge) / (1.0 - gamma)
    # Bound both the native and Python sums, cell parsing, final decimal
    # rounding and final binary64 parsing/comparison. Cell areas are positive.
    allowance = 0.5 * 10.0**-precision + cell_bridge + 2.0 * gamma * source_upper + 2.0 * unit
    if not math.isfinite(allowance):
        raise ValueError("nonfinite native area serialization allowance")
    return abs(value - expected) <= allowance


def natural(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("social source requires a nonnegative integer")
    return value


def indexed_records(world: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = world.get(key)
    if type(value) is not list or any(type(row) is not dict or type(row.get("id")) is not int or row["id"] != i for i, row in enumerate(value)):
        raise ValueError("complete indexed social records required: " + key)
    return value


def uses_native_social_availability(world: dict[str, Any]) -> bool:
    if type(world) is not dict:
        raise ValueError("social source requires a world mapping")
    keys = ("native_social_availability_model", "native_social_availability")
    if any(key in world for key in keys):
        if not all(key in world for key in keys):
            raise ValueError("partial native social availability envelope")
        return True
    _reject_orphan_availability(world)
    if "settlement_selection_model" in world:
        selection = world["settlement_selection_model"]
        if type(selection) is not dict or selection.get("model_type") not in {
            "causal_native_score_local_max_separated_settlement_selection_v2",
            "causal_native_score_local_max_separated_settlement_selection_v3",
        }:
            raise ValueError("unknown settlement source for social metadata")
        if selection["model_type"].endswith("_v3"):
            raise ValueError("settlement-v3 social data requires its native availability envelope")
    for key, model_type in SOCIAL_MODEL_TYPES.items():
        if key in world:
            declaration = world[key]
            legacy_type = model_type[:-1] + "1"
            if type(declaration) is not dict or declaration.get("model_type") != legacy_type:
                raise ValueError("unknown or successor social declaration lacks native provenance")
    return False


def _reject_orphan_availability(world: dict[str, Any]) -> None:
    """Successor-owned records cannot enter the historical replay by retagging."""
    owned = {
        "cultures": set(NULLABLE_FIELDS["CultureRegion"]) | {
            "ruin_candidate_cell_count", "ruin_supported_candidate_cell_count", "recorded_ruin_count"},
        "historical_eras": set(NULLABLE_FIELDS["HistoricalEra"]) | {"recorded_event_count"},
        "historical_events": set(NULLABLE_FIELDS["HistoricalEvent"]),
        "population_regions": set(NULLABLE_FIELDS["PopulationRegion"]) | {
            "site_input_complete", "territory_cell_count", "territory_area_km2",
            "site_input_applicable_cell_count", "site_input_supported_cell_count",
            "structural_zero_site_cell_count", "site_input_applicable_area_km2",
            "site_input_supported_area_km2", "structural_zero_site_area_km2",
            "estimate_scope_status", "site_strength_index"},
        "territorial_snapshots": set(NULLABLE_FIELDS["TerritorialSnapshot"]),
    }
    for collection, fields in owned.items():
        rows = world.get(collection)
        if type(rows) is list and any(type(row) is dict and fields.intersection(row) for row in rows):
            raise ValueError("orphan native social availability fields: " + collection)
    snapshots = world.get("territorial_snapshots")
    if type(snapshots) is list:
        fields = set(NULLABLE_FIELDS["SnapshotRegion"]) | {
            "base_area_km2", "base_dissolved_polygon_area_km2", "base_boundary_perimeter_km"}
        for snapshot in snapshots:
            rows = snapshot.get("regions") if type(snapshot) is dict else None
            if type(rows) is list and any(type(row) is dict and fields.intersection(row) for row in rows):
                raise ValueError("orphan native social availability fields: snapshot regions")
    summary = world.get("summary")
    fields = {
        "native_social_summary_availability", "recorded_historical_event_count",
        "recorded_ruin_count", "recorded_conflict_count", "recorded_dynasty_count",
        "available_population_region_count", "available_culture_continuity_count",
    }
    if type(summary) is dict and fields.intersection(summary):
        raise ValueError("orphan native social summary availability")


def _sorted_ids(value: Any) -> list[int]:
    if type(value) is not list or any(type(x) is not int or x < 0 for x in value) or value != sorted(set(value)):
        raise ValueError("sorted unique typed social ids required")
    return value


def _require_equal(actual: Any, expected: Any, label: str) -> None:
    if not exact_contract(actual, expected):
        raise ValueError("social source coverage disagrees: " + label)


def _nullable_fields(record: dict[str, Any], kind: str) -> None:
    for flag, fields in NULLABLE_FIELDS[kind].items():
        available = record.get(flag)
        if type(available) is not bool:
            raise ValueError("typed social availability required: " + flag)
        for key in fields:
            if key not in record:
                raise ValueError("missing owned social estimate: " + key)
            if not available:
                if record[key] is not None:
                    raise ValueError("unavailable social estimate must be null: " + key)
            elif key in {"ruin_count", "event_count", "language_event_count", "migration_event_count", "state_event_count"}:
                natural(record[key])
            elif key == "largest_region_id":
                if type(record[key]) is not int or record[key] < -1:
                    raise ValueError("typed largest-region identity required")
            else:
                finite_number(record[key])


def require_native_social_availability(world: dict[str, Any]) -> dict[str, Any]:
    """Check the exact header, nullable contracts and independently known coverage.

    This gate is suitable before annotation. It does not attest the complete
    culture/history/conflict/population numerical replay owned by their validators.
    """
    if not uses_native_social_availability(world):
        raise ValueError("native social availability source required")
    if not exact_contract(world["native_social_availability_model"], NATIVE_SOCIAL_MODEL):
        raise ValueError("unknown native social availability contract")
    inputs = require_settlement_v3_inputs(world)
    summary_flags = world["summary"].get("native_social_summary_availability")
    if (type(summary_flags) is not dict or summary_flags.keys() != SUMMARY_AVAILABILITY_KEYS
            or any(type(value) is not bool for value in summary_flags.values())):
        raise ValueError("exact typed native social summary availability required")
    envelope = world["native_social_availability"]
    if type(envelope) is not dict or envelope.keys() != ENVELOPE_KEYS:
        raise ValueError("exact native social coverage envelope required")
    for key, value in envelope.items():
        if key.endswith("_available"):
            if type(value) is not bool:
                raise ValueError("typed social collection availability required")
        elif key.endswith("_count"):
            natural(value)
    _sorted_ids(envelope["ruin_unavailable_cell_ids"])
    _sorted_ids(envelope["dynasty_unavailable_region_ids"])
    pairs = envelope["conflict_unavailable_region_pairs"]
    if type(pairs) is not list or any(type(p) is not list or len(p) != 2 or any(type(x) is not int or x < 0 for x in p) or p[0] >= p[1] for p in pairs) or pairs != [list(p) for p in sorted(set(tuple(p) for p in pairs))]:
        raise ValueError("sorted unique typed unavailable border pairs required")
    families = envelope["historical_event_family_coverage"]
    event_types = ["state_foundation", "dynastic_change", "migration", "language_split", "trade_boom", "sacred_founding", "ruin_abandonment"]
    if type(families) is not list or len(families) != 7:
        raise ValueError("complete historical family coverage required")
    family_keys = {"event_type", "inference_available", "applicable_source_count", "available_source_count", "recorded_event_count"}
    for family, event_type in zip(families, event_types):
        if type(family) is not dict or family.keys() != family_keys or family["event_type"] != event_type or type(family["inference_available"]) is not bool:
            raise ValueError("exact historical family coverage required")
        if family["applicable_source_count"] is not None:
            natural(family["applicable_source_count"])
        natural(family["available_source_count"])
        natural(family["recorded_event_count"])
        if family["applicable_source_count"] is not None and family["available_source_count"] > family["applicable_source_count"]:
            raise ValueError("historical supported source coverage exceeds applicability")
    cells = world["cells"]
    regions = indexed_records(world, "political_regions")
    cultures = indexed_records(world, "cultures")
    populations = indexed_records(world, "population_regions")
    ruins = indexed_records(world, "ruins")
    events = indexed_records(world, "historical_events")
    eras = indexed_records(world, "historical_eras")
    snapshots = indexed_records(world, "territorial_snapshots")
    indexed_records(world, "conflicts")
    indexed_records(world, "dynasties")
    active = {row["cell_id"] for row in world["settlements"]}
    candidates = [c for c in cells if not c["is_water"] and c.get("culture_region_id", -1) >= 0 and c["id"] not in active]
    unavailable = sorted(c["id"] for c in candidates if not inputs[c["id"]].available)
    complete_ruins = not unavailable
    for key, expected in (("ruin_candidate_cell_count", len(candidates)), ("ruin_supported_candidate_cell_count", len(candidates)-len(unavailable)), ("ruin_unavailable_cell_ids", unavailable), ("ruin_inference_available", complete_ruins)):
        _require_equal(envelope[key], expected, key)
    if not complete_ruins and ruins:
        raise ValueError("incomplete global ruin selection cannot emit a selected subset")
    ruin_counts = Counter(row["culture_region_id"] for row in ruins)
    cultures_by_region = {}
    for culture in cultures:
        _nullable_fields(culture, "CultureRegion")
        region_id = culture.get("homeland_region_id")
        if type(region_id) is not int or region_id not in range(len(regions)) or region_id in cultures_by_region:
            raise ValueError("exact culture homeland coverage required")
        cultures_by_region[region_id] = culture
        local = [c for c in candidates if c["culture_region_id"] == culture["id"]]
        culture_complete = complete_ruins or not local
        expected = {"ruin_candidate_cell_count": len(local), "ruin_supported_candidate_cell_count": sum(inputs[c["id"]].available for c in local), "recorded_ruin_count": ruin_counts[culture["id"]], "ruin_count_available": culture_complete, "continuity_estimate_available": culture_complete}
        if culture_complete:
            expected["ruin_count"] = ruin_counts[culture["id"]]
        for key, value in expected.items():
            _require_equal(culture.get(key), value, "culture."+key)
    if set(cultures_by_region) != set(range(len(regions))) or len(populations) != len(regions):
        raise ValueError("complete native culture/population regional coverage required")
    for population, region in zip(populations, regions):
        _nullable_fields(population, "PopulationRegion")
        _require_equal(population.get("region_id"), region["id"], "population.region_id")
        territory = [c for c in cells if not c["is_water"] and c.get("political_region_id", -1) == region["id"]]
        areas = {c["id"]: finite_number(c.get("area_km2")) for c in territory}
        if any(area < 0 for area in areas.values()):
            raise ValueError("negative physical territory area")
        applicable = [c for c in territory if areas[c["id"]] > 0 and inputs[c["id"]].surface_applicable]
        supported = [c for c in applicable if inputs[c["id"]].available]
        water = [c for c in territory if areas[c["id"]] > 0 and inputs[c["id"]].structural_zero]
        positive = sum(areas.values()) > 0
        complete = len(applicable) == len(supported)
        capacity = positive and complete
        culture = cultures_by_region[region["id"]]
        total = capacity and culture["continuity_estimate_available"]
        expected = {"territory_cell_count":len(territory), "site_input_applicable_cell_count":len(applicable), "site_input_supported_cell_count":len(supported), "structural_zero_site_cell_count":len(water), "site_input_complete":complete, "site_strength_available":capacity, "physical_means_available":positive, "capacity_estimate_available":capacity, "population_estimate_available":total, "migration_balance_available":True, "estimate_scope_status":"not_applicable_no_positive_territory" if not positive else "complete" if total else "unavailable_inputs"}
        for key, value in expected.items():
            _require_equal(population.get(key), value, "population."+key)
        area_fields = {"territory_area_km2":territory, "site_input_applicable_area_km2":applicable, "site_input_supported_area_km2":supported, "structural_zero_site_area_km2":water}
        for key, rows in area_fields.items():
            expected_area = sum(areas[c["id"]] for c in rows)
            if not native_area_matches(population.get(key), expected_area, len(rows), world["summary"]["output_float_precision"]):
                raise ValueError("social area coverage disagrees: "+key)
    for event in events:
        _nullable_fields(event, "HistoricalEvent")
    for era in eras:
        _nullable_fields(era, "HistoricalEra")
        natural(era.get("recorded_event_count"))
    for snapshot in snapshots:
        _nullable_fields(snapshot, "TerritorialSnapshot")
        if type(snapshot.get("regions")) is not list:
            raise ValueError("complete snapshot regional collection required")
        for row in snapshot["regions"]:
            if type(row) is not dict:
                raise ValueError("typed snapshot regional record required")
            _nullable_fields(row, "SnapshotRegion")
            for key in ("base_area_km2", "base_dissolved_polygon_area_km2", "base_boundary_perimeter_km"):
                if finite_number(row.get(key)) < 0:
                    raise ValueError("negative base territory geometry")
    return envelope
