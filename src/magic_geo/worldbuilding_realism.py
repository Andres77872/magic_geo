from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .worldbuilding_fishery_validation import (
    WorldbuildingFisheryValidationError,
    WORLDBUILDING_SUMMARY_FIELDS,
    audit_worldbuilding_fishery_inputs,
    validate_worldbuilding_fishery_context,
    worldbuilding_fishery_contract,
)


MARINE_WATER_TYPES = {"ocean", "continental_shelf", "inland_sea"}
WATER_ACCESS_TYPES = MARINE_WATER_TYPES | {"fresh_lake", "saline_basin"}
WORLDBUILDING_REALISM_MODEL = "causal_upstream_evidence_worldbuilding_realism_checks_v1"
WORLDBUILDING_FISHERY_MODEL = {'model_type': 'causal_upstream_evidence_worldbuilding_realism_checks_v2',
 'resource_support_model': 'material_geology_or_supported_fishery_parent_and_habitat_v2',
 'source_ecosystem_model': 'heuristic_ecosystem_climate_support_v4',
 'source_resource_deposit_model': 'causal_geologic_resource_deposit_diagnostics_v3',
 'fishery_water_body_types': ['continental_shelf', 'fresh_lake', 'inland_sea', 'ocean'],
 'fishery_support_policy': 'require_independently_replayed_resource_deposit_v3_primary_and_derived_fishery_support',
 'resource_check_scope': 'emitted_deposits_only_unsupported_fishery_sources_reported_separately',
 'empty_resource_deposit_policy': 'conditional_fraction_one_not_global_resource_availability'}


WORLDBUILDING_PRESCRIBED_NATURAL_MODEL = {
    **WORLDBUILDING_FISHERY_MODEL,
    'full_world_cell_source_policy': 'nonempty_full_world_cells_required_geo_scope_omits_stage',
    "model_type": "causal_upstream_evidence_worldbuilding_realism_checks_v3",
    "source_ecosystem_model": "heuristic_ecosystem_climate_support_v5",
    "source_resource_deposit_model": "causal_geologic_resource_deposit_diagnostics_v4",
    "fishery_support_policy": "require_independently_replayed_resource_deposit_v4_primary_and_derived_fishery_support",
}

WORLDBUILDING_SETTLEMENT_AVAILABILITY_MODEL = {
    **WORLDBUILDING_PRESCRIBED_NATURAL_MODEL,
    "model_type": "causal_upstream_evidence_worldbuilding_realism_checks_v4",
    "source_resource_deposit_model": "causal_geologic_resource_deposit_diagnostics_v5",
    "source_settlement_model": "causal_native_score_local_max_separated_settlement_selection_v3",
    "fishery_support_policy": "require_independently_replayed_resource_deposit_v5_primary_and_derived_fishery_support",
    "economic_access_scope": "natural_resource_context_check_independent_of_economic_access_availability",
}


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _score_range(value: float, target_min: float, target_max: float) -> float:
    if target_min <= value <= target_max:
        return 1.0
    if value < target_min:
        return _clamp(value / target_min) if target_min > 0.0 else 0.0
    remaining = 1.0 - target_max
    return _clamp((1.0 - value) / remaining) if remaining > 0.0 else 0.0


def _check_record(
    *,
    checks: list[dict[str, Any]],
    name: str,
    question: str,
    metric: str,
    value: float,
    target_min: float,
    target_max: float,
    evidence: dict[str, Any],
) -> None:
    rounded_value = round(_clamp(value), 6)
    checks.append(
        {
            "id": len(checks),
            "domain": "worldbuilding",
            "name": name,
            "question": question,
            "metric": metric,
            "value": rounded_value,
            "target_min": round(_clamp(target_min), 6),
            "target_max": round(_clamp(target_max), 6),
            "score": round(_score_range(rounded_value, target_min, target_max), 6),
            "passed": target_min <= rounded_value <= target_max,
            "evidence": evidence,
        }
    )


def _is_coastal_land(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> bool:
    for neighbor_id in cell.get("neighbors", []):
        neighbor = cells_by_id.get(int(neighbor_id))
        if neighbor is not None and str(neighbor.get("water_body_type", "land")) in MARINE_WATER_TYPES:
            return True
    return False


def _settlement_has_water(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> bool:
    water_body = str(cell.get("water_body_type", "land"))
    return (
        bool(cell.get("is_river", False))
        or bool(cell.get("is_lake", False))
        or water_body in WATER_ACCESS_TYPES
        or float(cell.get("runoff_mm_y", 0.0)) >= 120.0
        or _is_coastal_land(cell, cells_by_id)
    )


def _large_settlements(settlements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not settlements:
        return []
    ranked = sorted(settlements, key=lambda item: float(item.get("score", 0.0)), reverse=True)
    target_count = max(1, min(len(ranked), max(5, (len(ranked) + 3) // 4)))
    return ranked[:target_count]


def _route_threshold(route_type: str) -> float:
    if route_type == "coastal_sea":
        return 0.95
    if route_type == "river_corridor":
        return 1.10
    if route_type == "mountain_pass":
        return 1.75
    return 1.35


def _resource_has_geologic_support(deposit: dict[str, Any], cell: dict[str, Any]) -> bool:
    resource = str(deposit.get("resource", "none"))
    evidence = deposit.get("formation_evidence", {})
    if not isinstance(evidence, dict):
        evidence = {}
    convergent = float(evidence.get("boundary_convergent", cell.get("boundary_convergent", 0.0)))
    divergent = float(evidence.get("boundary_divergent", cell.get("boundary_divergent", 0.0)))
    crust_age = float(evidence.get("crust_age_ma", cell.get("crust_age_ma", 0.0)))
    sediment = float(evidence.get("sediment_thickness_m", cell.get("sediment_thickness_m", 0.0)))
    flow = float(evidence.get("flow_accumulation", cell.get("flow_accumulation", 0.0)))
    fertility = float(evidence.get("fertility", cell.get("fertility", 0.0)))
    salinity = float(evidence.get("salinity_index", cell.get("soil_salinity_index", 0.0)))
    crust = str(deposit.get("host_crust_type", cell.get("crust_type", "")))
    lithology = str(deposit.get("host_lithology", cell.get("lithology", "")))
    landform = str(deposit.get("landform", cell.get("landform", "")))
    water_body = str(cell.get("water_body_type", "land"))

    if resource == "volcanic_arc_metals":
        return crust == "volcanic_arc" or landform == "volcanic_arc" or convergent >= 0.28
    if resource == "craton_iron_gold":
        return crust == "craton" or crust_age >= 1800.0
    if resource == "sedimentary_fuels":
        return (
            crust == "sedimentary_basin"
            or lithology in {"shale", "sandstone", "limestone"}
            or sediment >= 1.0
            or "basin" in landform
        )
    if resource == "evaporites":
        return landform == "salt_flat" or salinity >= 0.45 or water_body == "saline_basin"
    if resource == "placer_metals":
        return bool(cell.get("is_river", False)) or flow >= 25.0 or convergent >= 0.16
    if resource == "geothermal":
        return (
            divergent >= 0.30
            or convergent >= 0.20
            or landform in {"volcanic_arc", "rift_valley"}
            or crust in {"volcanic_arc", "rift_basin"}
        )
    if resource == "fertile_alluvium":
        return (
            landform in {"floodplain", "delta", "river_valley", "alluvial_fan"}
            or bool(cell.get("is_river", False))
            or fertility >= 0.62
        )
    if resource == "coastal_fisheries":
        return water_body in MARINE_WATER_TYPES
    return float(deposit.get("geologic_confidence_index", 0.0)) >= 0.25


def _enrich_world_with_worldbuilding_realism(
    world: dict[str, Any], fishery_support: dict[int, tuple[bool, bool]] | None = None
) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world
    cells_by_id = {int(cell.get("id", -1)): cell for cell in cells if isinstance(cell, dict)}
    settlements = world.get("settlements", [])
    routes = world.get("routes", [])
    regions = world.get("political_regions", [])
    borders = world.get("borders", [])
    deposits = world.get("resource_deposits", [])
    if not isinstance(settlements, list):
        settlements = []
    if not isinstance(routes, list):
        routes = []
    if not isinstance(regions, list):
        regions = []
    if not isinstance(borders, list):
        borders = []
    if not isinstance(deposits, list):
        deposits = []

    checks: list[dict[str, Any]] = []

    top_settlements = _large_settlements(settlements)
    water_settlements = [
        settlement
        for settlement in top_settlements
        if _settlement_has_water(cells_by_id.get(int(settlement.get("cell_id", -1)), {}), cells_by_id)
    ]
    settlement_water_index = len(water_settlements) / len(top_settlements) if top_settlements else 1.0
    _check_record(
        checks=checks,
        name="large_settlement_water_access",
        question="Do large settlements have water access?",
        metric="fraction_top_settlements_with_water_access",
        value=settlement_water_index,
        target_min=0.85,
        target_max=1.0,
        evidence={
            "top_settlement_count": len(top_settlements),
            "water_accessible_top_settlement_count": len(water_settlements),
            "mean_top_settlement_score": round(_mean([float(item.get("score", 0.0)) for item in top_settlements]), 6),
        },
    )

    route_frictions: list[float] = []
    low_barrier_routes = 0
    high_cost_routes = 0
    for route in routes:
        distance = max(1.0, float(route.get("distance_km", 0.0)))
        friction = float(route.get("cost", 0.0)) / distance
        route_frictions.append(friction)
        threshold = _route_threshold(str(route.get("type", "overland")))
        if friction <= threshold:
            low_barrier_routes += 1
        if friction > 1.55:
            high_cost_routes += 1
    route_avoidance_index = low_barrier_routes / len(routes) if routes else 1.0
    _check_record(
        checks=checks,
        name="route_barrier_avoidance",
        question="Do routes avoid expensive terrain barriers?",
        metric="fraction_routes_below_type_specific_barrier_cost",
        value=route_avoidance_index,
        target_min=0.8,
        target_max=1.0,
        evidence={
            "route_count": len(routes),
            "low_barrier_route_count": low_barrier_routes,
            "high_cost_route_count": high_cost_routes,
            "mean_route_friction": round(_mean(route_frictions), 6),
            "max_route_friction": round(max(route_frictions), 6) if route_frictions else 0.0,
        },
    )

    settlement_route_graph: dict[int, set[int]] = defaultdict(set)
    for route in routes:
        source = int(route.get("from", -1))
        target = int(route.get("to", -1))
        if source >= 0 and target >= 0:
            settlement_route_graph[source].add(target)
            settlement_route_graph[target].add(source)

    reachable_sum = 0
    settlement_sum = 0
    region_reachability: list[float] = []
    connected_regions = 0
    for region in regions:
        settlement_ids = {int(value) for value in region.get("settlement_ids", [])}
        if not settlement_ids:
            region_reachability.append(1.0)
            connected_regions += 1
            continue
        capital_id = int(region.get("capital_settlement_id", -1))
        if capital_id not in settlement_ids:
            capital_id = next(iter(settlement_ids))
        seen = {capital_id}
        stack = [capital_id]
        while stack:
            current = stack.pop()
            for neighbor in settlement_route_graph.get(current, set()):
                if neighbor in settlement_ids and neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        reachability = len(seen) / len(settlement_ids)
        region_reachability.append(reachability)
        reachable_sum += len(seen)
        settlement_sum += len(settlement_ids)
        if reachability >= 0.6:
            connected_regions += 1
    political_connectivity_index = reachable_sum / settlement_sum if settlement_sum else 1.0
    _check_record(
        checks=checks,
        name="political_region_connectivity",
        question="Do generated political regions originate around connected settlement networks?",
        metric="fraction_region_settlements_reachable_from_capital_by_internal_routes",
        value=political_connectivity_index,
        target_min=0.55,
        target_max=1.0,
        evidence={
            "political_region_count": len(regions),
            "connected_region_count": connected_regions,
            "region_settlement_count": settlement_sum,
            "capital_reachable_settlement_count": reachable_sum,
            "mean_region_capital_reachability": round(_mean(region_reachability), 6),
        },
    )

    total_border_length = 0.0
    natural_border_length = 0.0
    natural_border_count = 0
    border_barrier_scores: list[float] = []
    for border in borders:
        length = max(0.0, float(border.get("length_km", 0.0)))
        barrier_score = _clamp(float(border.get("barrier_score", 0.0)))
        border_barrier_scores.append(barrier_score)
        is_natural = str(border.get("type", "open_lowland")) != "open_lowland" or barrier_score >= 0.45
        total_border_length += length
        if is_natural:
            natural_border_length += length
            natural_border_count += 1
    natural_border_index = natural_border_length / total_border_length if total_border_length > 0.0 else 1.0
    _check_record(
        checks=checks,
        name="natural_border_alignment",
        question="Do political borders follow real terrain, water, desert, ice, or coastal barriers?",
        metric="length_weighted_fraction_borders_on_natural_barriers",
        value=natural_border_index,
        target_min=0.4,
        target_max=1.0,
        evidence={
            "border_segment_count": len(borders),
            "natural_border_segment_count": natural_border_count,
            "border_total_length_km": round(total_border_length, 6),
            "natural_border_length_km": round(natural_border_length, 6),
            "mean_border_barrier_score": round(_mean(border_barrier_scores), 6),
        },
    )

    resource_counts: Counter[str] = Counter()
    supported_resource_counts: Counter[str] = Counter()
    supported_deposits = 0
    for deposit in deposits:
        cell = cells_by_id.get(int(deposit.get("cell_id", -1)))
        resource = str(deposit.get("resource", "none"))
        resource_counts[resource] += 1
        context_supported = (
            fishery_support[int(cell["id"])][1]
            if cell is not None and fishery_support is not None and resource == "coastal_fisheries"
            else cell is not None and _resource_has_geologic_support(deposit, cell)
        )
        if context_supported:
            supported_deposits += 1
            supported_resource_counts[resource] += 1
    resource_geology_index = supported_deposits / len(deposits) if deposits else 1.0
    _check_record(
        checks=checks,
        name="resource_geology_dependency",
        question="Do resources depend on geology and causal physical context?",
        metric="fraction_resource_deposits_with_resource_specific_geologic_support",
        value=resource_geology_index,
        target_min=0.85,
        target_max=1.0,
        evidence={
            "resource_deposit_count": len(deposits),
            "geologically_supported_resource_deposit_count": supported_deposits,
            "resource_counts": dict(sorted(resource_counts.items())),
            "supported_resource_counts": dict(sorted(supported_resource_counts.items())),
        },
    )

    if fishery_support is not None:
        check = checks[-1]
        check["question"] = "Do emitted resources have material geology or supported fishery source context?"
        check["metric"] = "fraction_emitted_resource_deposits_with_material_or_supported_fishery_context"
        evidence = check["evidence"]
        evidence["source_context_supported_resource_deposit_count"] = evidence.pop("geologically_supported_resource_deposit_count")
        applicable_count = sum(applicable for applicable, _ in fishery_support.values())
        supported_count = sum(supported for _, supported in fishery_support.values())
        evidence.update({
            "emitted_resource_evidence_available": bool(deposits),
            "fishery_resource_proxy_applicable_cell_count": applicable_count,
            "fishery_resource_proxy_supported_cell_count": supported_count,
            "unsupported_fishery_resource_proxy_cell_count": applicable_count - supported_count,
        })

    pass_count = sum(1 for check in checks if check["passed"])
    score_sum = sum(float(check["score"]) for check in checks)
    summary = world.setdefault("summary", {})
    world["worldbuilding_realism_checks"] = checks
    summary["large_settlement_water_access_index"] = round(settlement_water_index, 6)
    summary["route_barrier_avoidance_index"] = round(route_avoidance_index, 6)
    summary["political_region_connectivity_index"] = round(political_connectivity_index, 6)
    summary["natural_border_alignment_index"] = round(natural_border_index, 6)
    summary["resource_geology_dependency_index"] = round(resource_geology_index, 6)
    summary["worldbuilding_realism_check_count"] = len(checks)
    summary["worldbuilding_realism_pass_count"] = pass_count
    summary["worldbuilding_realism_pass_fraction"] = round(pass_count / len(checks), 6) if checks else 0.0
    summary["mean_worldbuilding_realism_score"] = round(score_sum / len(checks), 6) if checks else 0.0
    world["worldbuilding_realism_model"] = {
        "model_type": WORLDBUILDING_REALISM_MODEL,
        "deterministic": True,
        "check_order": [
            "large_settlement_water_access",
            "route_barrier_avoidance",
            "political_region_connectivity",
            "natural_border_alignment",
            "resource_geology_dependency",
        ],
        "score_model": "bounded_distance_to_closed_target_interval_v1",
        "targets": {
            "large_settlement_water_access": [0.85, 1.0],
            "route_barrier_avoidance": [0.8, 1.0],
            "political_region_connectivity": [0.55, 1.0],
            "natural_border_alignment": [0.4, 1.0],
            "resource_geology_dependency": [0.85, 1.0],
        },
        "large_settlement_model": "top_max_5_or_ceil_quarter_by_descending_score_v1",
        "water_access_model": "river_lake_water_body_runoff_or_adjacent_marine_v1",
        "water_access_runoff_threshold_mm_y": 120.0,
        "route_friction_model": "cost_div_max_one_distance_v1",
        "route_type_friction_thresholds": {
            "coastal_sea": 0.95,
            "river_corridor": 1.10,
            "mountain_pass": 1.75,
            "default": 1.35,
        },
        "high_cost_route_threshold": 1.55,
        "political_connectivity_model": "capital_reachability_on_internal_settlement_route_graph_v1",
        "connected_region_reachability_threshold": 0.6,
        "natural_border_model": "length_weighted_non_open_or_threshold_barrier_fraction_v1",
        "natural_border_barrier_threshold": 0.45,
        "resource_support_model": "resource_specific_geology_and_physical_context_predicates_v1",
        "model_limitation": "internal_generated_evidence_checks_without_external_historical_geographic_calibration",
    }
    if fishery_support is not None:
        # This changes only the fifth check's context policy. Marine navigation,
        # material rules, and the four human checks retain their existing scope.
        from copy import deepcopy
        world["worldbuilding_realism_model"].update(deepcopy(WORLDBUILDING_FISHERY_MODEL))
    summary["worldbuilding_realism_model"] = world["worldbuilding_realism_model"]["model_type"]
    return world


def enrich_world_with_worldbuilding_realism(world: dict[str, Any]) -> dict[str, Any]:
    """Preserve declared historical models; publish the new chain atomically."""
    support = audit_worldbuilding_fishery_inputs(world)
    if support is None:
        return _enrich_world_with_worldbuilding_realism(world)
    model = worldbuilding_fishery_contract(world)
    natural = model["model_type"] in (WORLDBUILDING_PRESCRIBED_NATURAL_MODEL["model_type"], WORLDBUILDING_SETTLEMENT_AVAILABILITY_MODEL["model_type"])
    natural_model = WORLDBUILDING_SETTLEMENT_AVAILABILITY_MODEL if model["model_type"] == WORLDBUILDING_SETTLEMENT_AVAILABILITY_MODEL["model_type"] else WORLDBUILDING_PRESCRIBED_NATURAL_MODEL
    if natural and not world["cells"]:
        raise WorldbuildingFisheryValidationError("worldbuilding-v3 requires a nonempty full-world cell source; geo scope omits this stage")
    staged = dict(world)
    staged["summary"] = dict(world.get("summary", {}))
    _enrich_world_with_worldbuilding_realism(staged, support)
    if natural:
        from copy import deepcopy
        staged["worldbuilding_realism_model"].update(deepcopy(natural_model))
        staged["summary"]["worldbuilding_realism_model"] = natural_model["model_type"]
        errors = validate_worldbuilding_fishery_context(staged)
        if errors:
            raise WorldbuildingFisheryValidationError(errors[0])
        # Existing independent replay owns the first four human equations; it
        # never calls this producer. Its fifth check delegates to the independent
        # source-context helper above, rather than copying producer formulas.
        from .human_geography_validation import _worldbuilding_replay_valid
        try:
            valid = _worldbuilding_replay_valid(staged)
        except (TypeError, ValueError, KeyError, OverflowError, ArithmeticError, AttributeError) as exc:
            raise WorldbuildingFisheryValidationError("worldbuilding-v3 human replay input is malformed: " + type(exc).__name__) from exc
        if not valid:
            raise WorldbuildingFisheryValidationError("worldbuilding-v3 independent full human replay failed before publication")
        world["worldbuilding_realism_model"] = staged["worldbuilding_realism_model"]
        world["worldbuilding_realism_checks"] = staged["worldbuilding_realism_checks"]
        world["summary"].update({key: staged["summary"][key] for key in WORLDBUILDING_SUMMARY_FIELDS})
    else:
        # Exact established WB2 behavior, including its historical source scope.
        world.update({key: staged[key] for key in (
            "worldbuilding_realism_model", "worldbuilding_realism_checks", "summary"
        )})
    return world
