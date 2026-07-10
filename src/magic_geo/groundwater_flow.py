from __future__ import annotations

from collections import Counter
from typing import Any


MARINE_WATER_TYPES = {"ocean", "continental_shelf", "inland_sea"}
SURFACE_WATER_TYPES = {"fresh_lake", "saline_basin"}
GROUNDWATER_FLOW_REGIMES = {
    "excluded",
    "recharge_mound",
    "recharge_throughflow",
    "throughflow",
    "discharge_zone",
    "lowland_discharge",
    "stagnant_or_low_yield",
}
GROUNDWATER_FLOW_MODEL = "descending_head_recharge_conserving_groundwater_flow_v1"
MINIMUM_RECEIVER_HEAD_DROP_M = 0.5
GROUNDWATER_GRADIENT_SCALE_M = 900.0
MAXIMUM_LATERAL_EXPORT_FRACTION = 0.82


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _area(cell: dict[str, Any]) -> float:
    return max(0.0, float(cell.get("area_km2", 0.0)))


def _cell_id(cell: dict[str, Any]) -> int:
    return int(cell.get("id", -1))


def _is_aquifer_cell(cell: dict[str, Any]) -> bool:
    return str(cell.get("aquifer_class", "")) != "marine_excluded" and str(cell.get("water_body_type", "land")) not in MARINE_WATER_TYPES


def _water_surface_head(cell: dict[str, Any]) -> float:
    elevation = float(cell.get("elevation_m", 0.0))
    if bool(cell.get("is_water", False)):
        return elevation + max(0.0, float(cell.get("water_depth_m", 0.0)))
    return elevation


def _hydraulic_head(cell: dict[str, Any]) -> float:
    if not _is_aquifer_cell(cell):
        return _water_surface_head(cell)

    elevation = float(cell.get("elevation_m", 0.0))
    recharge = _clamp(float(cell.get("groundwater_recharge_mm_y", 0.0)) / 360.0)
    storage = _clamp(float(cell.get("aquifer_storage_index", 0.0)))
    quality = _clamp(float(cell.get("aquifer_quality_index", 0.0)))
    moisture = _clamp(float(cell.get("soil_moisture_index", 0.0)))
    aridity = _clamp(float(cell.get("seasonal_aridity_index", 0.0)))
    salinity = _clamp(float(cell.get("soil_salinity_index", 0.0)))
    extraction_risk = _clamp(float(cell.get("aquifer_extraction_risk_index", 0.0)))
    water_bonus = 0.18 if bool(cell.get("is_lake", False)) or str(cell.get("water_body_type", "land")) in SURFACE_WATER_TYPES else 0.0
    river_bonus = 0.10 if bool(cell.get("is_river", False)) else 0.0
    saturation = _clamp(
        recharge * 0.28
        + storage * 0.26
        + quality * 0.10
        + moisture * 0.18
        + water_bonus
        + river_bonus
        - aridity * 0.12
        - salinity * 0.08
        - extraction_risk * 0.08
    )
    depth_to_water_m = max(0.0, 12.0 + (1.0 - saturation) * 210.0 + aridity * 70.0 + extraction_risk * 45.0 - storage * 35.0)
    return elevation - depth_to_water_m


def _surface_connection_index(cell: dict[str, Any]) -> float:
    water_body = str(cell.get("water_body_type", "land"))
    connection = 0.0
    if bool(cell.get("is_river", False)):
        connection = max(connection, 0.62)
    if bool(cell.get("is_lake", False)) or water_body in SURFACE_WATER_TYPES:
        connection = max(connection, 0.56)
    if float(cell.get("wetland_extent_index", 0.0)) >= 0.35:
        connection = max(connection, 0.42)
    if bool(cell.get("is_closed_basin", False)):
        connection = max(connection, 0.24)
    if float(cell.get("distance_to_marine_water_km", 9999.0)) <= 160.0:
        connection = max(connection, 0.28)
    return _clamp(connection)


def _flow_regime(cell: dict[str, Any], gradient: float, discharge_mm_y: float, spring_index: float, flow_to: int) -> str:
    if not _is_aquifer_cell(cell):
        return "excluded"
    recharge = float(cell.get("groundwater_recharge_mm_y", 0.0))
    if spring_index >= 0.45 and discharge_mm_y >= 20.0:
        return "discharge_zone"
    if recharge >= 60.0 and gradient >= 0.08 and flow_to >= 0:
        return "recharge_throughflow"
    if recharge >= 60.0:
        return "recharge_mound"
    if gradient >= 0.05 and flow_to >= 0:
        return "throughflow"
    if discharge_mm_y >= 12.0:
        return "lowland_discharge"
    return "stagnant_or_low_yield"


def _primary_key(counter: Counter[str], fallback: str) -> str:
    if not counter:
        return fallback
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


def enrich_world_with_groundwater_flow(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world

    cells_by_id = {_cell_id(cell): cell for cell in cells}
    candidate_ids = {_cell_id(cell) for cell in cells if _is_aquifer_cell(cell)}
    heads = {_cell_id(cell): _hydraulic_head(cell) for cell in cells}

    flow_to_by_id: dict[int, int] = {}
    gradient_by_id: dict[int, float] = {}
    throughput_by_id: dict[int, float] = {}
    lateral_export_by_id: dict[int, float] = {}
    lateral_inflow_by_id: dict[int, float] = {}
    internal_lateral_outflow_by_id: dict[int, float] = {}
    discharge_by_id: dict[int, float] = {}
    retained_storage_by_id: dict[int, float] = {}
    mass_balance_residual_by_id: dict[int, float] = {}

    for cell in cells:
        cell_id = _cell_id(cell)
        head = heads[cell_id]
        cell["groundwater_hydraulic_head_m"] = round(head, 6)
        cell["groundwater_gradient_index"] = 0.0
        cell["groundwater_lateral_flow_km3_y"] = 0.0
        cell["groundwater_lateral_inflow_km3_y"] = 0.0
        cell["groundwater_available_volume_km3_y"] = 0.0
        cell["groundwater_internal_lateral_outflow_km3_y"] = 0.0
        cell["groundwater_discharge_mm_y"] = 0.0
        cell["groundwater_discharge_km3_y"] = 0.0
        cell["groundwater_retained_storage_km3_y"] = 0.0
        cell["groundwater_flow_mass_balance_residual_km3_y"] = 0.0
        cell["groundwater_flow_to_cell_id"] = -1
        cell["spring_discharge_index"] = 0.0
        cell["baseflow_support_index"] = 0.0
        cell["groundwater_flow_regime"] = "excluded"
        cell["groundwater_flow_system_id"] = -1
        if cell_id in candidate_ids:
            throughput_by_id[cell_id] = max(0.0, float(cell.get("groundwater_recharge_km3_y", 0.0)))
            lateral_export_by_id[cell_id] = 0.0
            lateral_inflow_by_id[cell_id] = 0.0
            internal_lateral_outflow_by_id[cell_id] = 0.0
            discharge_by_id[cell_id] = 0.0
            retained_storage_by_id[cell_id] = 0.0
            mass_balance_residual_by_id[cell_id] = 0.0

    for cell_id in sorted(candidate_ids):
        cell = cells_by_id[cell_id]
        head = heads[cell_id]
        aquifer_system_id = int(cell.get("aquifer_system_id", -1))
        best_neighbor_id = -1
        best_drop = 0.0
        for neighbor_id_raw in cell.get("neighbors", []):
            neighbor_id = int(neighbor_id_raw)
            neighbor = cells_by_id.get(neighbor_id)
            if neighbor is None:
                continue
            same_system = neighbor_id in candidate_ids and int(neighbor.get("aquifer_system_id", -2)) == aquifer_system_id
            surface_sink = neighbor_id not in candidate_ids
            if not same_system and not surface_sink:
                continue
            drop = head - heads.get(neighbor_id, _water_surface_head(neighbor))
            if drop > best_drop:
                best_drop = drop
                best_neighbor_id = neighbor_id
        if best_drop >= MINIMUM_RECEIVER_HEAD_DROP_M:
            flow_to_by_id[cell_id] = best_neighbor_id
            gradient_by_id[cell_id] = _clamp(best_drop / GROUNDWATER_GRADIENT_SCALE_M)
        else:
            flow_to_by_id[cell_id] = -1
            gradient_by_id[cell_id] = 0.0

    for cell_id in sorted(candidate_ids, key=lambda item: (-heads[item], item)):
        cell = cells_by_id[cell_id]
        available = max(0.0, throughput_by_id.get(cell_id, 0.0))
        gradient = gradient_by_id.get(cell_id, 0.0)
        storage = _clamp(float(cell.get("aquifer_storage_index", 0.0)))
        productivity = _clamp(float(cell.get("aquifer_productivity_index", 0.0)))
        extraction_risk = _clamp(float(cell.get("aquifer_extraction_risk_index", 0.0)))
        export_fraction = _clamp(
            0.12
            + gradient * 0.56
            + productivity * 0.18
            + storage * 0.08
            - extraction_risk * 0.12,
            0.0,
            MAXIMUM_LATERAL_EXPORT_FRACTION,
        )
        flow_to = flow_to_by_id.get(cell_id, -1)
        export = available * export_fraction if flow_to >= 0 else 0.0
        lateral_export_by_id[cell_id] = export
        if flow_to in candidate_ids:
            throughput_by_id[flow_to] = throughput_by_id.get(flow_to, 0.0) + export
            lateral_inflow_by_id[flow_to] = lateral_inflow_by_id.get(flow_to, 0.0) + export
            internal_lateral_outflow_by_id[cell_id] = export

    for cell_id in sorted(candidate_ids):
        cell = cells_by_id[cell_id]
        area = _area(cell)
        available = max(0.0, throughput_by_id.get(cell_id, 0.0))
        export = max(0.0, lateral_export_by_id.get(cell_id, 0.0))
        flow_to = flow_to_by_id.get(cell_id, -1)
        flow_to_candidate = flow_to in candidate_ids
        internal_lateral_outflow = max(0.0, internal_lateral_outflow_by_id.get(cell_id, 0.0))
        surface_connection = _surface_connection_index(cell)
        gradient = gradient_by_id.get(cell_id, 0.0)
        productivity = _clamp(float(cell.get("aquifer_productivity_index", 0.0)))
        storage = _clamp(float(cell.get("aquifer_storage_index", 0.0)))
        quality = _clamp(float(cell.get("aquifer_quality_index", 0.0)))
        extraction_risk = _clamp(float(cell.get("aquifer_extraction_risk_index", 0.0)))
        local_available = max(0.0, available - (export if flow_to >= 0 else 0.0))
        surface_fraction = _clamp(surface_connection * 0.58 + (1.0 - gradient) * 0.10 + productivity * 0.08 - extraction_risk * 0.12)
        if flow_to >= 0 and not flow_to_candidate:
            discharge_km3_y = min(available, export + local_available * surface_fraction)
        else:
            discharge_km3_y = min(available, local_available * surface_fraction)
        retained_storage_km3_y = max(
            0.0,
            available - internal_lateral_outflow - discharge_km3_y,
        )
        mass_balance_residual_km3_y = (
            available
            - internal_lateral_outflow
            - discharge_km3_y
            - retained_storage_km3_y
        )
        discharge_mm_y = discharge_km3_y / (area * 0.000001) if area > 0.0 else 0.0
        spring_index = _clamp(discharge_mm_y / 260.0 * 0.42 + gradient * 0.20 + surface_connection * 0.18 + productivity * 0.12 + quality * 0.08)
        baseflow_index = _clamp(
            discharge_mm_y / 260.0 * 0.42
            + float(cell.get("groundwater_recharge_mm_y", 0.0)) / 340.0 * 0.16
            + storage * 0.16
            + productivity * 0.16
            + (0.12 if bool(cell.get("is_river", False)) else 0.0)
            - extraction_risk * 0.10
        )
        regime = _flow_regime(cell, gradient, discharge_mm_y, spring_index, flow_to)
        discharge_by_id[cell_id] = discharge_km3_y
        retained_storage_by_id[cell_id] = retained_storage_km3_y
        mass_balance_residual_by_id[cell_id] = mass_balance_residual_km3_y

        cell["groundwater_gradient_index"] = round(gradient, 6)
        cell["groundwater_lateral_flow_km3_y"] = round(export, 6)
        cell["groundwater_lateral_inflow_km3_y"] = round(
            lateral_inflow_by_id.get(cell_id, 0.0),
            6,
        )
        cell["groundwater_available_volume_km3_y"] = round(available, 6)
        cell["groundwater_internal_lateral_outflow_km3_y"] = round(
            internal_lateral_outflow,
            6,
        )
        cell["groundwater_discharge_mm_y"] = round(discharge_mm_y, 6)
        cell["groundwater_discharge_km3_y"] = round(discharge_km3_y, 6)
        cell["groundwater_retained_storage_km3_y"] = round(
            retained_storage_km3_y,
            6,
        )
        cell["groundwater_flow_mass_balance_residual_km3_y"] = round(
            mass_balance_residual_km3_y,
            12,
        )
        cell["groundwater_flow_to_cell_id"] = int(flow_to)
        cell["spring_discharge_index"] = round(spring_index, 6)
        cell["baseflow_support_index"] = round(baseflow_index, 6)
        cell["groundwater_flow_regime"] = regime

    groups: dict[int, list[dict[str, Any]]] = {}
    for cell_id in sorted(candidate_ids):
        cell = cells_by_id[cell_id]
        aquifer_system_id = int(cell.get("aquifer_system_id", -1))
        if aquifer_system_id >= 0:
            groups.setdefault(aquifer_system_id, []).append(cell)

    systems: list[dict[str, Any]] = []
    for aquifer_system_id, group in sorted(groups.items()):
        system_id = len(systems)
        for cell in group:
            cell["groundwater_flow_system_id"] = system_id
        group_ids = {_cell_id(cell) for cell in group}
        cell_count = len(group)
        area_sum = sum(_area(cell) for cell in group)
        recharge_sum = sum(float(cell.get("groundwater_recharge_km3_y", 0.0)) for cell in group)
        lateral_inflow_sum = sum(float(cell.get("groundwater_lateral_inflow_km3_y", 0.0)) for cell in group)
        internal_lateral_outflow_sum = sum(
            float(cell.get("groundwater_internal_lateral_outflow_km3_y", 0.0))
            for cell in group
        )
        discharge_sum = sum(float(cell.get("groundwater_discharge_km3_y", 0.0)) for cell in group)
        lateral_sum = sum(float(cell.get("groundwater_lateral_flow_km3_y", 0.0)) for cell in group)
        retained_storage_sum = sum(
            float(cell.get("groundwater_retained_storage_km3_y", 0.0))
            for cell in group
        )
        mass_balance_residual_sum = sum(
            float(cell.get("groundwater_flow_mass_balance_residual_km3_y", 0.0))
            for cell in group
        )
        regime_counter = Counter(str(cell.get("groundwater_flow_regime", "stagnant_or_low_yield")) for cell in group)
        terminal_ids = sorted(
            _cell_id(cell)
            for cell in group
            if int(cell.get("groundwater_flow_to_cell_id", -1)) < 0 or int(cell.get("groundwater_flow_to_cell_id", -1)) not in group_ids
        )
        discharge_cell_ids = sorted(
            _cell_id(cell)
            for cell in group
            if float(cell.get("groundwater_discharge_mm_y", 0.0)) >= 25.0 or float(cell.get("spring_discharge_index", 0.0)) >= 0.45
        )
        recharge_cell_ids = sorted(_cell_id(cell) for cell in group if float(cell.get("groundwater_recharge_mm_y", 0.0)) >= 50.0)
        outlet_candidates = discharge_cell_ids or terminal_ids or sorted(group_ids)
        outlet_cell_id = sorted(
            outlet_candidates,
            key=lambda item: (-float(cells_by_id[item].get("groundwater_discharge_km3_y", 0.0)), item),
        )[0]
        divisor = max(1, cell_count)
        first_aquifer = next((system for system in world.get("aquifer_systems", []) if int(system.get("id", -1)) == aquifer_system_id), {})
        systems.append(
            {
                "id": system_id,
                "aquifer_system_id": aquifer_system_id,
                "basin_id": int(first_aquifer.get("basin_id", group[0].get("basin_id", -1))),
                "flow_regime": _primary_key(regime_counter, "stagnant_or_low_yield"),
                "cell_count": cell_count,
                "cell_ids": sorted(group_ids),
                "recharge_cell_ids": recharge_cell_ids,
                "discharge_cell_ids": discharge_cell_ids,
                "terminal_cell_ids": terminal_ids,
                "outlet_cell_id": int(outlet_cell_id),
                "area_km2": round(area_sum, 6),
                "total_groundwater_recharge_km3_y": round(recharge_sum, 6),
                "total_groundwater_lateral_inflow_km3_y": round(lateral_inflow_sum, 6),
                "total_groundwater_internal_lateral_outflow_km3_y": round(
                    internal_lateral_outflow_sum,
                    6,
                ),
                "total_groundwater_discharge_km3_y": round(discharge_sum, 6),
                "total_groundwater_lateral_flow_km3_y": round(lateral_sum, 6),
                "total_groundwater_retained_storage_km3_y": round(
                    retained_storage_sum,
                    6,
                ),
                "groundwater_flow_mass_balance_residual_km3_y": round(
                    mass_balance_residual_sum,
                    12,
                ),
                "groundwater_balance_residual_km3_y": round(recharge_sum - discharge_sum, 6),
                "discharge_to_recharge_ratio": round(discharge_sum / recharge_sum, 6) if recharge_sum > 0.0 else 0.0,
                "mean_hydraulic_head_m": round(sum(float(cell.get("groundwater_hydraulic_head_m", 0.0)) for cell in group) / divisor, 6),
                "mean_groundwater_gradient_index": round(sum(float(cell.get("groundwater_gradient_index", 0.0)) for cell in group) / divisor, 6),
                "mean_groundwater_discharge_mm_y": round(sum(float(cell.get("groundwater_discharge_mm_y", 0.0)) for cell in group) / divisor, 6),
                "mean_spring_discharge_index": round(sum(float(cell.get("spring_discharge_index", 0.0)) for cell in group) / divisor, 6),
                "mean_baseflow_support_index": round(sum(float(cell.get("baseflow_support_index", 0.0)) for cell in group) / divisor, 6),
                "mean_aquifer_extraction_risk_index": round(
                    sum(float(cell.get("aquifer_extraction_risk_index", 0.0)) for cell in group) / divisor,
                    6,
                ),
                "river_cell_count": sum(1 for cell in group if bool(cell.get("is_river", False))),
                "lake_cell_count": sum(1 for cell in group if bool(cell.get("is_lake", False))),
                "wetland_cell_count": sum(1 for cell in group if float(cell.get("wetland_extent_index", 0.0)) >= 0.35),
                "closed_basin_cell_count": sum(1 for cell in group if bool(cell.get("is_closed_basin", False))),
                "flow_regime_counts": dict(sorted(regime_counter.items())),
            }
        )

    summary = world.setdefault("summary", {})
    regime_counts = Counter(str(cell.get("groundwater_flow_regime", "excluded")) for cell in cells)
    aquifer_cells = [cells_by_id[cell_id] for cell_id in sorted(candidate_ids)]
    divisor = len(aquifer_cells) if aquifer_cells else 1
    total_recharge = sum(float(cell.get("groundwater_recharge_km3_y", 0.0)) for cell in aquifer_cells)
    total_lateral_inflow = sum(lateral_inflow_by_id.values())
    total_internal_lateral_outflow = sum(
        internal_lateral_outflow_by_id.values()
    )
    total_discharge = sum(discharge_by_id.values())
    total_lateral = sum(lateral_export_by_id.values())
    total_retained_storage = sum(retained_storage_by_id.values())
    total_mass_balance_residual = sum(mass_balance_residual_by_id.values())

    world["groundwater_flow_model"] = {
        "model_type": GROUNDWATER_FLOW_MODEL,
        "source_field": "groundwater_recharge_km3_y",
        "domain": "non_marine_aquifer_cells",
        "hydraulic_head_model": "terrain_minus_diagnostic_depth_to_water_v1",
        "receiver_model": "steepest_head_drop_within_aquifer_system_or_surface_sink_v1",
        "minimum_receiver_head_drop_m": MINIMUM_RECEIVER_HEAD_DROP_M,
        "gradient_scale_m": GROUNDWATER_GRADIENT_SCALE_M,
        "routing_order": "descending_hydraulic_head_then_cell_id",
        "lateral_export_model": "bounded_gradient_productivity_storage_extraction_fraction_v1",
        "maximum_lateral_export_fraction": MAXIMUM_LATERAL_EXPORT_FRACTION,
        "surface_discharge_model": "surface_target_export_plus_fraction_of_remaining_volume_v1",
        "local_mass_balance_equation": "recharge_plus_lateral_inflow_minus_internal_lateral_outflow_minus_discharge_minus_retained_storage",
        "mass_conserving": True,
        "acyclic_flow_required": True,
        "candidate_cell_count": len(aquifer_cells),
        "total_source_recharge_volume_km3_y": round(total_recharge, 9),
        "total_internal_lateral_inflow_volume_km3_y": round(
            total_lateral_inflow,
            9,
        ),
        "total_internal_lateral_outflow_volume_km3_y": round(
            total_internal_lateral_outflow,
            9,
        ),
        "total_lateral_throughput_volume_km3_y": round(total_lateral, 9),
        "total_groundwater_discharge_volume_km3_y": round(total_discharge, 9),
        "total_retained_storage_volume_km3_y": round(
            total_retained_storage,
            9,
        ),
        "mass_balance_residual_km3_y": round(
            total_mass_balance_residual,
            12,
        ),
        "model_limitation": "annual_diagnostic_head_and_flux_routing_without_transient_aquifer_storage_or_groundwater_surface_water_feedback",
    }
    world["groundwater_flow_systems"] = systems
    summary["groundwater_flow_model"] = GROUNDWATER_FLOW_MODEL
    summary["groundwater_flow_cell_count"] = sum(1 for cell in aquifer_cells if int(cell.get("groundwater_flow_system_id", -1)) >= 0)
    summary["groundwater_flow_system_count"] = len(systems)
    summary["groundwater_discharge_cell_count"] = sum(1 for cell in aquifer_cells if float(cell.get("groundwater_discharge_mm_y", 0.0)) >= 25.0)
    summary["spring_candidate_cell_count"] = sum(1 for cell in aquifer_cells if float(cell.get("spring_discharge_index", 0.0)) >= 0.45)
    summary["baseflow_supported_river_cell_count"] = sum(
        1 for cell in aquifer_cells if bool(cell.get("is_river", False)) and float(cell.get("baseflow_support_index", 0.0)) >= 0.35
    )
    summary["total_groundwater_discharge_km3_y"] = round(total_discharge, 6)
    summary["total_groundwater_lateral_flow_km3_y"] = round(total_lateral, 6)
    summary["total_groundwater_internal_lateral_flow_km3_y"] = round(
        total_internal_lateral_outflow,
        6,
    )
    summary["total_groundwater_retained_storage_km3_y"] = round(
        total_retained_storage,
        6,
    )
    summary["groundwater_flow_mass_balance_residual_km3_y"] = round(
        total_mass_balance_residual,
        12,
    )
    summary["total_groundwater_flow_balance_residual_km3_y"] = round(total_recharge - total_discharge, 6)
    summary["mean_groundwater_gradient_index"] = round(sum(float(cell.get("groundwater_gradient_index", 0.0)) for cell in aquifer_cells) / divisor, 6) if aquifer_cells else 0.0
    summary["mean_groundwater_discharge_mm_y"] = round(sum(float(cell.get("groundwater_discharge_mm_y", 0.0)) for cell in aquifer_cells) / divisor, 6) if aquifer_cells else 0.0
    summary["mean_spring_discharge_index"] = round(sum(float(cell.get("spring_discharge_index", 0.0)) for cell in aquifer_cells) / divisor, 6) if aquifer_cells else 0.0
    summary["mean_baseflow_support_index"] = round(sum(float(cell.get("baseflow_support_index", 0.0)) for cell in aquifer_cells) / divisor, 6) if aquifer_cells else 0.0
    summary["groundwater_flow_regime_counts"] = dict(sorted(regime_counts.items()))
    return world
