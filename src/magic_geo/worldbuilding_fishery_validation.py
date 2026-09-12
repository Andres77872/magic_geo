"""Independent, bounded worldbuilding-v2/v3 source-context replay.

This checks the resource diagnostic and its upstream availability, not the other
four human-geography checks or biological stock/yield calibration. No producer
functions are imported. Known declared v1 keeps its historical rule.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from .biological_resource_validation import (
    BiologicalResourceValidationError,
    audit_biological_resource_deposits,
    biological_resource_contract,
    resource_access_v5,
)

MARINE_WATER_TYPES = {"ocean", "continental_shelf", "inland_sea"}

def _legacy_model() -> dict[str, Any]:
    return {
        "model_type": "causal_upstream_evidence_worldbuilding_realism_checks_v1",
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

_V1 = _legacy_model()
_V2 = {**_V1, **{'model_type': 'causal_upstream_evidence_worldbuilding_realism_checks_v2',
 'resource_support_model': 'material_geology_or_supported_fishery_parent_and_habitat_v2',
 'source_ecosystem_model': 'heuristic_ecosystem_climate_support_v4',
 'source_resource_deposit_model': 'causal_geologic_resource_deposit_diagnostics_v3',
 'fishery_water_body_types': ['continental_shelf', 'fresh_lake', 'inland_sea', 'ocean'],
 'fishery_support_policy': 'require_independently_replayed_resource_deposit_v3_primary_and_derived_fishery_support',
 'resource_check_scope': 'emitted_deposits_only_unsupported_fishery_sources_reported_separately',
 'empty_resource_deposit_policy': 'conditional_fraction_one_not_global_resource_availability'}}

_V3 = {**_V2,
    'full_world_cell_source_policy': 'nonempty_full_world_cells_required_geo_scope_omits_stage',
    "model_type": "causal_upstream_evidence_worldbuilding_realism_checks_v3",
    "source_ecosystem_model": "heuristic_ecosystem_climate_support_v5",
    "source_resource_deposit_model": "causal_geologic_resource_deposit_diagnostics_v4",
    "fishery_support_policy": "require_independently_replayed_resource_deposit_v4_primary_and_derived_fishery_support",
}
_V4 = {**_V3, "model_type": "causal_upstream_evidence_worldbuilding_realism_checks_v4",
       "source_resource_deposit_model": "causal_geologic_resource_deposit_diagnostics_v5",
       "source_settlement_model": "causal_native_score_local_max_separated_settlement_selection_v3",
       "fishery_support_policy": "require_independently_replayed_resource_deposit_v5_primary_and_derived_fishery_support",
       "economic_access_scope": "natural_resource_context_check_independent_of_economic_access_availability"}

_MODELS_BY_PARENT = {
    "heuristic_ecosystem_climate_support_v4": _V2,
    "heuristic_ecosystem_climate_support_v5": _V3,
}
WORLDBUILDING_SUMMARY_FIELDS = ('large_settlement_water_access_index', 'mean_worldbuilding_realism_score', 'natural_border_alignment_index', 'political_region_connectivity_index', 'resource_geology_dependency_index', 'route_barrier_avoidance_index', 'worldbuilding_realism_check_count', 'worldbuilding_realism_model', 'worldbuilding_realism_pass_count', 'worldbuilding_realism_pass_fraction')


class WorldbuildingFisheryValidationError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise WorldbuildingFisheryValidationError(message)


def _same(actual: Any, expected: Any) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(_same(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(_same(a, b) for a, b in zip(actual, expected))
    return actual == expected


def worldbuilding_fishery_contract(world: dict[str, Any]) -> dict[str, Any]:
    """Exact own-first dispatch; known own-v1 retains its historical exception."""
    _require(isinstance(world, dict), "worldbuilding fishery: world must be an object")
    model_present = "worldbuilding_realism_model" in world
    model = world.get("worldbuilding_realism_model")
    summary = world.get("summary", {})
    _require(isinstance(summary, dict), "worldbuilding fishery: summary must be an object")
    if model_present:
        _require(any(_same(model, m) for m in (_V1, _V2, _V3, _V4)),
                 "worldbuilding fishery: malformed or unknown worldbuilding_realism_model")
    if "worldbuilding_realism_model" in summary:
        _require(model_present and _same(summary["worldbuilding_realism_model"], model["model_type"]),
                 "worldbuilding fishery: missing or mismatched own model/summary identity")
    parent = biological_resource_contract(world)
    if model_present and _same(model, _V1):
        return _V1  # Deliberate, historically established own-v1 exception.
    expected = _V4 if parent == "heuristic_ecosystem_climate_support_v5" and resource_access_v5(world) else _MODELS_BY_PARENT.get(parent, _V1)
    if model_present:
        _require(_same(model, expected), "worldbuilding fishery: own declaration requires its exact matched ecosystem/deposit parents")
    if expected in (_V3, _V4):
        if not model_present:
            present = "worldbuilding_realism_checks" in world or any(k in summary for k in WORLDBUILDING_SUMMARY_FIELDS)
            _require(not present, "worldbuilding-v3: undeclared existing owned outputs require an explicit audited archive upgrade")
        else:
            _require(_same(summary.get("worldbuilding_realism_model"), expected["model_type"]),
                     "worldbuilding-v3: complete own summary identity required")
    return expected


def _natural_human_sources(world: dict[str, Any]) -> None:
    """Explicit preceding-stage sources; empty lists remain meaningful inputs."""
    import math
    def finite(value: Any) -> bool:
        if type(value) not in (int, float):
            return False
        try:
            return math.isfinite(value)
        except OverflowError:
            return False
    cells = world["cells"]
    _require(bool(cells), "worldbuilding-v3 requires a nonempty full-world cell source; geo scope omits this stage")
    by_id = {c["id"]: c for c in cells}
    for cell in cells:
        context = f"worldbuilding-v3 cell {cell['id']}"
        for key in ("is_river", "is_lake"):
            _require(type(cell.get(key)) is bool, context + ": explicit " + key + " boolean required")
        _require(type(cell.get("water_body_type")) is str, context + ": explicit water_body_type string required")
        _require(finite(cell.get("runoff_mm_y")), context + ": explicit finite runoff_mm_y required")
        neighbors = cell.get("neighbors")
        _require(isinstance(neighbors, list) and all(type(n) is int and n in by_id for n in neighbors),
                 context + ": explicit neighbors list of existing cell IDs required")
        _require(len(neighbors) == len(set(neighbors)), context + ": duplicate neighbor ID")
        _require(all(isinstance(by_id[n].get("neighbors"), list) and cell["id"] in by_id[n]["neighbors"] for n in neighbors),
                 context + ": reciprocal physical neighbor links required")
    for key in ("settlements", "routes", "political_regions", "borders"):
        _require(isinstance(world.get(key), list), "worldbuilding-v3: explicit " + key + " list required")
        _require(all(isinstance(r, dict) for r in world[key]), "worldbuilding-v3: " + key + " records must be objects")
    settlements = world["settlements"]
    ids = set()
    for index, record in enumerate(settlements):
        context = f"worldbuilding-v3 settlement {index}"
        _require(type(record.get("id")) is int and record["id"] not in ids, context + ": unique explicit integer id required")
        ids.add(record["id"])
        _require(type(record.get("cell_id")) is int and record["cell_id"] in by_id, context + ": existing cell_id required")
        _require(finite(record.get("score")), context + ": explicit finite score required")
    for index, record in enumerate(world["routes"]):
        context = f"worldbuilding-v3 route {index}"
        for key in ("cost", "distance_km"):
            _require(finite(record.get(key)), context + ": explicit finite " + key + " required")
        _require(type(record.get("type")) is str, context + ": explicit type string required")
        for key in ("from", "to"):
            _require(type(record.get(key)) is int and (record[key] < 0 or record[key] in ids),
                     context + ": explicit known or historical negative-sentinel " + key + " required")
    for index, record in enumerate(world["political_regions"]):
        context = f"worldbuilding-v3 political region {index}"
        members = record.get("settlement_ids")
        _require(isinstance(members, list) and all(type(x) is int and x in ids for x in members)
                 and len(members) == len(set(members)), context + ": explicit unique existing settlement_ids required")
        _require(type(record.get("capital_settlement_id")) is int,
                 context + ": explicit capital_settlement_id required (historical fallback retained)")
    for index, record in enumerate(world["borders"]):
        context = f"worldbuilding-v3 border {index}"
        for key in ("length_km", "barrier_score"):
            _require(finite(record.get(key)), context + ": explicit finite " + key + " required")
        _require(type(record.get("type")) is str, context + ": explicit type string required")


def audit_worldbuilding_fishery_inputs(world: dict[str, Any]) -> dict[int, tuple[bool, bool]] | None:
    """Choose exact own version, then audit matched inputs before mutation."""
    try:
        model = worldbuilding_fishery_contract(world)
        if model is _V1:
            return None
        support = audit_biological_resource_deposits(world)
        if model in (_V3, _V4):
            _natural_human_sources(world)
        if model is _V4:
            from .settlement_input_availability import require_settlement_v3_inputs
            require_settlement_v3_inputs(world)
        return support
    except WorldbuildingFisheryValidationError:
        raise
    except BiologicalResourceValidationError as exc:
        raise WorldbuildingFisheryValidationError("worldbuilding fishery parent: " + str(exc)) from exc
    except (TypeError, ValueError, KeyError, OverflowError, ArithmeticError, AttributeError) as exc:
        raise WorldbuildingFisheryValidationError("worldbuilding fishery envelope is malformed: " + type(exc).__name__) from exc


def _material_context_supported(deposit: dict[str, Any], cell: dict[str, Any]) -> bool:
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
        return crust == "sedimentary_basin" or lithology in {"shale", "sandstone", "limestone"} or sediment >= 1.0 or "basin" in landform
    if resource == "evaporites":
        return landform == "salt_flat" or salinity >= 0.45 or water_body == "saline_basin"
    if resource == "placer_metals":
        return bool(cell.get("is_river", False)) or flow >= 25.0 or convergent >= 0.16
    if resource == "geothermal":
        return divergent >= 0.30 or convergent >= 0.20 or landform in {"volcanic_arc", "rift_valley"} or crust in {"volcanic_arc", "rift_basin"}
    if resource == "fertile_alluvium":
        return landform in {"floodplain", "delta", "river_valley", "alluvial_fan"} or bool(cell.get("is_river", False)) or fertility >= 0.62
    if resource == "coastal_fisheries":
        return water_body in MARINE_WATER_TYPES
    return float(deposit.get("geologic_confidence_index", 0.0)) >= 0.25


def validate_worldbuilding_fishery_context(world: dict[str, Any]) -> list[str]:
    """Return at most one actionable error; preserve the world on every path.

    Historical v1 is left to the existing full human-geography validator. Each matched
    source audit is performed once here; other human checks are out of scope.
    """
    try:
        support = audit_worldbuilding_fishery_inputs(world)
        if support is None:
            return []
        expected_model = worldbuilding_fishery_contract(world)
        _require(_same(world.get("worldbuilding_realism_model"), expected_model),
                 "worldbuilding source-context output requires exact own model metadata")
        cells = {cell["id"]: cell for cell in world["cells"]}
        deposits = world["resource_deposits"]
        counts: Counter[str] = Counter()
        supported_counts: Counter[str] = Counter()
        for deposit in deposits:
            resource = deposit["resource"]
            cell = cells[deposit["cell_id"]]
            counts[resource] += 1
            supported = support[cell["id"]][1] if resource == "coastal_fisheries" else _material_context_supported(deposit, cell)
            if supported:
                supported_counts[resource] += 1
        count = len(deposits)
        supported_count = sum(supported_counts.values())
        applicable = sum(a for a, _ in support.values())
        available = sum(b for _, b in support.values())
        ratio = round(supported_count / count, 6) if count else 1.0
        score = 1.0 if ratio >= .85 else round(ratio / .85, 6)
        expected = {
            "id": 4, "domain": "worldbuilding", "name": "resource_geology_dependency",
            "question": "Do emitted resources have material geology or supported fishery source context?",
            "metric": "fraction_emitted_resource_deposits_with_material_or_supported_fishery_context",
            "value": ratio, "target_min": .85, "target_max": 1.0,
            "score": score, "passed": ratio >= .85,
            "evidence": {
                "resource_deposit_count": count,
                "source_context_supported_resource_deposit_count": supported_count,
                "resource_counts": dict(sorted(counts.items())),
                "supported_resource_counts": dict(sorted(supported_counts.items())),
                "emitted_resource_evidence_available": count > 0,
                "fishery_resource_proxy_applicable_cell_count": applicable,
                "fishery_resource_proxy_supported_cell_count": available,
                "unsupported_fishery_resource_proxy_cell_count": applicable - available,
            },
        }
        checks = world.get("worldbuilding_realism_checks")
        _require(isinstance(checks, list) and len(checks) == 5, "worldbuilding source-context requires five ordered checks")
        _require(_same(checks[4], expected), "worldbuilding resource source-context check/evidence does not replay")
        summary = world["summary"]
        _require(summary.get("worldbuilding_realism_model") == expected_model["model_type"],
                 "worldbuilding source-context summary model identity mismatch")
        _require(_same(summary.get("resource_geology_dependency_index"), ratio),
                 "worldbuilding resource source-context summary does not replay")
        # These totals use the retained first four records, not a claim to replay
        # their unrelated settlement/route/region/border inputs.
        _require(all(isinstance(c, dict) and type(c.get("passed")) is bool
                     and type(c.get("score")) is float and 0.0 <= c["score"] <= 1.0 for c in checks),
                 "worldbuilding source-context check totals require finite unit scores and boolean outcomes")
        passed = sum(c["passed"] for c in checks)
        total_fields = {
            "worldbuilding_realism_check_count": 5,
            "worldbuilding_realism_pass_count": passed,
            "worldbuilding_realism_pass_fraction": round(passed / 5, 6),
            "mean_worldbuilding_realism_score": round(sum(c["score"] for c in checks) / 5, 6),
        }
        for key, expected_value in total_fields.items():
            _require(_same(summary.get(key), expected_value), "worldbuilding source-context summary mismatch: " + key)
        return []
    except WorldbuildingFisheryValidationError as exc:
        return [str(exc)]
    except (TypeError, ValueError, KeyError, OverflowError, ArithmeticError, AttributeError) as exc:
        return ["worldbuilding fishery output is malformed: " + type(exc).__name__]
