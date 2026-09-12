"""Historical v1 groundwater record mirrors, preserved without changing arithmetic."""

from __future__ import annotations
from typing import Any


def _validate_legacy_groundwater_records(
    payload: dict[str, Any], summary: dict[str, Any],
    cells_payload: list[dict[str, Any]], cells_by_id: dict[int, dict[str, Any]],
) -> list[str]:
    failures: list[str] = []
    aquifer_systems = payload.get("aquifer_systems", [])
    aquifer_summary_keys = {
        "aquifer_resource_model",
        "aquifer_cell_count",
        "aquifer_system_count",
        "groundwater_recharge_cell_count",
        "high_productivity_aquifer_cell_count",
        "groundwater_stressed_cell_count",
        "total_groundwater_recharge_km3_y",
        "total_groundwater_recharge_source_infiltration_km3_y",
        "total_vadose_zone_retention_km3_y",
        "groundwater_recharge_mass_balance_residual_km3_y",
        "mean_groundwater_recharge_mm_y",
        "mean_aquifer_storage_index",
        "mean_aquifer_quality_index",
        "mean_aquifer_productivity_index",
        "mean_aquifer_extraction_risk_index",
        "aquifer_class_counts",
    }
    if not aquifer_summary_keys.issubset(summary):
        failures.append("aquifer summary metrics missing")
    if not isinstance(aquifer_systems, list):
        failures.append("aquifer_systems missing")
        aquifer_systems = []
    aquifer_cell_keys = {
        "groundwater_recharge_source_infiltration_mm_y",
        "groundwater_recharge_fraction",
        "groundwater_recharge_mm_y",
        "groundwater_recharge_km3_y",
        "vadose_zone_retention_mm_y",
        "vadose_zone_retention_km3_y",
        "groundwater_recharge_mass_balance_residual_mm_y",
        "aquifer_storage_index",
        "aquifer_quality_index",
        "aquifer_productivity_index",
        "aquifer_extraction_risk_index",
        "aquifer_class",
        "aquifer_system_id",
    }
    if cells_payload and not aquifer_cell_keys.issubset(cells_payload[0]):
        failures.append("aquifer cell fields missing")
    aquifer_class_counts: dict[str, int] = {}
    aquifer_cell_count = 0
    groundwater_recharge_cell_count = 0
    high_productivity_aquifer_count = 0
    groundwater_stressed_count = 0
    groundwater_recharge_sum_mm = 0.0
    groundwater_recharge_sum_km3 = 0.0
    aquifer_storage_sum = 0.0
    aquifer_quality_sum = 0.0
    aquifer_productivity_sum = 0.0
    aquifer_risk_sum = 0.0
    aquifer_assigned_cell_ids: set[int] = set()
    aquifer_cell_invalid = False
    for cell in cells_payload:
        cell_id = int(cell.get("id", -1))
        aquifer_class = str(cell.get("aquifer_class", ""))
        recharge_mm = float(cell.get("groundwater_recharge_mm_y", -1.0))
        recharge_km3 = float(cell.get("groundwater_recharge_km3_y", -1.0))
        storage = float(cell.get("aquifer_storage_index", -1.0))
        quality = float(cell.get("aquifer_quality_index", -1.0))
        productivity = float(cell.get("aquifer_productivity_index", -1.0))
        risk = float(cell.get("aquifer_extraction_risk_index", -1.0))
        system_id = int(cell.get("aquifer_system_id", -2))
        area = max(0.0, float(cell.get("area_km2", 0.0)))
        water_body = str(cell.get("water_body_type", "land"))
        aquifer_class_counts[aquifer_class] = aquifer_class_counts.get(aquifer_class, 0) + 1
        if (
            not aquifer_class
            or recharge_mm < 0.0
            or recharge_km3 < 0.0
            or abs(recharge_km3 - recharge_mm * area * 0.000001) > max(0.001, recharge_km3 * 0.0001)
            or not 0.0 <= storage <= 1.0
            or not 0.0 <= quality <= 1.0
            or not 0.0 <= productivity <= 1.0
            or not 0.0 <= risk <= 1.0
            or system_id < -1
            or (water_body in {"ocean", "continental_shelf", "inland_sea"} and aquifer_class != "marine_excluded")
        ):
            aquifer_cell_invalid = True
            break
        if aquifer_class != "marine_excluded":
            aquifer_cell_count += 1
            groundwater_recharge_sum_mm += recharge_mm
            groundwater_recharge_sum_km3 += recharge_km3
            aquifer_storage_sum += storage
            aquifer_quality_sum += quality
            aquifer_productivity_sum += productivity
            aquifer_risk_sum += risk
            groundwater_recharge_cell_count += 1 if recharge_mm >= 50.0 else 0
            high_productivity_aquifer_count += 1 if productivity >= 0.65 else 0
            groundwater_stressed_count += 1 if risk >= 0.65 else 0
        if system_id >= 0:
            aquifer_assigned_cell_ids.add(cell_id)
    if aquifer_cell_invalid:
        failures.append("aquifer cell fields invalid")
    if aquifer_class_counts != {str(key): int(value) for key, value in summary.get("aquifer_class_counts", {}).items()}:
        failures.append("aquifer_class_counts does not match cells")
    if int(summary.get("aquifer_cell_count", -1)) != aquifer_cell_count:
        failures.append("aquifer_cell_count does not match cells")
    aquifer_divisor = float(aquifer_cell_count) if aquifer_cell_count else 1.0
    expected_aquifer_counts = {
        "aquifer_system_count": len(aquifer_systems),
        "groundwater_recharge_cell_count": groundwater_recharge_cell_count,
        "high_productivity_aquifer_cell_count": high_productivity_aquifer_count,
        "groundwater_stressed_cell_count": groundwater_stressed_count,
    }
    for key, expected in expected_aquifer_counts.items():
        if int(summary.get(key, -1)) != expected:
            failures.append(f"{key} does not match aquifer cells")
            break
    expected_aquifer_means = {
        "mean_groundwater_recharge_mm_y": groundwater_recharge_sum_mm / aquifer_divisor if aquifer_cell_count else 0.0,
        "mean_aquifer_storage_index": aquifer_storage_sum / aquifer_divisor if aquifer_cell_count else 0.0,
        "mean_aquifer_quality_index": aquifer_quality_sum / aquifer_divisor if aquifer_cell_count else 0.0,
        "mean_aquifer_productivity_index": aquifer_productivity_sum / aquifer_divisor if aquifer_cell_count else 0.0,
        "mean_aquifer_extraction_risk_index": aquifer_risk_sum / aquifer_divisor if aquifer_cell_count else 0.0,
    }
    for key, expected in expected_aquifer_means.items():
        if abs(float(summary.get(key, 0.0)) - expected) > 0.001:
            failures.append(f"{key} does not match aquifer cells")
            break
    if abs(float(summary.get("total_groundwater_recharge_km3_y", 0.0)) - groundwater_recharge_sum_km3) > max(0.001, groundwater_recharge_sum_km3 * 0.0001):
        failures.append("total_groundwater_recharge_km3_y does not match cells")
    aquifer_system_keys = {
        "id",
        "basin_id",
        "aquifer_class",
        "primary_lithology",
        "dominant_landform",
        "cell_count",
        "cell_ids",
        "area_km2",
        "mean_groundwater_recharge_mm_y",
        "total_groundwater_recharge_km3_y",
        "mean_aquifer_storage_index",
        "mean_aquifer_quality_index",
        "mean_aquifer_productivity_index",
        "mean_aquifer_extraction_risk_index",
        "recharge_cell_count",
        "high_productivity_cell_count",
        "stressed_cell_count",
        "closed_basin_fraction",
        "aquifer_class_counts",
    }
    if aquifer_systems and not aquifer_system_keys.issubset(aquifer_systems[0]):
        failures.append("aquifer system fields missing")
    aquifer_system_ids: set[int] = set()
    aquifer_system_cell_ids: set[int] = set()
    aquifer_system_invalid = False
    for index, system in enumerate(aquifer_systems):
        system_id = int(system.get("id", -1))
        cell_ids_for_system = system.get("cell_ids", [])
        if not isinstance(cell_ids_for_system, list):
            aquifer_system_invalid = True
            break
        group_cells = [cells_by_id.get(int(cell_id)) for cell_id in cell_ids_for_system]
        if any(cell is None for cell in group_cells):
            aquifer_system_invalid = True
            break
        valid_group_cells = [cell for cell in group_cells if cell is not None]
        basin_id = int(system.get("basin_id", -1))
        group_count = len(valid_group_cells)
        area_sum = sum(max(0.0, float(cell.get("area_km2", 0.0))) for cell in valid_group_cells)
        recharge_mm_sum = sum(float(cell.get("groundwater_recharge_mm_y", 0.0)) for cell in valid_group_cells)
        recharge_km3_sum = sum(float(cell.get("groundwater_recharge_km3_y", 0.0)) for cell in valid_group_cells)
        storage_group_sum = sum(float(cell.get("aquifer_storage_index", 0.0)) for cell in valid_group_cells)
        quality_group_sum = sum(float(cell.get("aquifer_quality_index", 0.0)) for cell in valid_group_cells)
        productivity_group_sum = sum(float(cell.get("aquifer_productivity_index", 0.0)) for cell in valid_group_cells)
        risk_group_sum = sum(float(cell.get("aquifer_extraction_risk_index", 0.0)) for cell in valid_group_cells)
        system_class_counts: dict[str, int] = {}
        for cell in valid_group_cells:
            aquifer_system_cell_ids.add(int(cell.get("id", -1)))
            class_name = str(cell.get("aquifer_class", ""))
            system_class_counts[class_name] = system_class_counts.get(class_name, 0) + 1
        aquifer_system_ids.add(system_id)
        if (
            system_id != index
            or group_count <= 0
            or int(system.get("cell_count", -1)) != group_count
            or any(int(cell.get("aquifer_system_id", -1)) != system_id for cell in valid_group_cells)
            or any(int(cell.get("basin_id", -2)) != basin_id for cell in valid_group_cells)
            or any(str(cell.get("aquifer_class", "")) == "marine_excluded" for cell in valid_group_cells)
            or not str(system.get("aquifer_class", "")).strip()
            or not str(system.get("primary_lithology", "")).strip()
            or not str(system.get("dominant_landform", "")).strip()
            or abs(float(system.get("area_km2", 0.0)) - area_sum) > max(0.001, area_sum * 0.0001)
            or abs(float(system.get("mean_groundwater_recharge_mm_y", 0.0)) - recharge_mm_sum / group_count) > 0.001
            or abs(float(system.get("total_groundwater_recharge_km3_y", 0.0)) - recharge_km3_sum) > max(0.001, recharge_km3_sum * 0.0001)
            or abs(float(system.get("mean_aquifer_storage_index", 0.0)) - storage_group_sum / group_count) > 0.001
            or abs(float(system.get("mean_aquifer_quality_index", 0.0)) - quality_group_sum / group_count) > 0.001
            or abs(float(system.get("mean_aquifer_productivity_index", 0.0)) - productivity_group_sum / group_count) > 0.001
            or abs(float(system.get("mean_aquifer_extraction_risk_index", 0.0)) - risk_group_sum / group_count) > 0.001
            or int(system.get("recharge_cell_count", -1)) != sum(1 for cell in valid_group_cells if float(cell.get("groundwater_recharge_mm_y", 0.0)) >= 50.0)
            or int(system.get("high_productivity_cell_count", -1)) != sum(1 for cell in valid_group_cells if float(cell.get("aquifer_productivity_index", 0.0)) >= 0.65)
            or int(system.get("stressed_cell_count", -1)) != sum(1 for cell in valid_group_cells if float(cell.get("aquifer_extraction_risk_index", 0.0)) >= 0.65)
            or not 0.0 <= float(system.get("closed_basin_fraction", -1.0)) <= 1.0
            or system_class_counts != {str(key): int(value) for key, value in system.get("aquifer_class_counts", {}).items()}
        ):
            aquifer_system_invalid = True
            break
    if aquifer_system_invalid:
        failures.append("aquifer system records invalid")
    if len(aquifer_system_ids) != len(aquifer_systems):
        failures.append("aquifer system ids are not unique")
    if aquifer_system_cell_ids != aquifer_assigned_cell_ids:
        failures.append("aquifer system membership does not match cells")

    groundwater_flow_systems = payload.get("groundwater_flow_systems", [])
    groundwater_flow_summary_keys = {
        "groundwater_flow_cell_count",
        "groundwater_flow_system_count",
        "groundwater_discharge_cell_count",
        "spring_candidate_cell_count",
        "baseflow_supported_river_cell_count",
        "total_groundwater_discharge_km3_y",
        "total_groundwater_lateral_flow_km3_y",
        "total_groundwater_internal_lateral_flow_km3_y",
        "total_groundwater_retained_storage_km3_y",
        "groundwater_flow_mass_balance_residual_km3_y",
        "total_groundwater_flow_balance_residual_km3_y",
        "mean_groundwater_gradient_index",
        "mean_groundwater_discharge_mm_y",
        "mean_spring_discharge_index",
        "mean_baseflow_support_index",
        "groundwater_flow_regime_counts",
    }
    if not groundwater_flow_summary_keys.issubset(summary):
        failures.append("groundwater flow summary metrics missing")
    if not isinstance(groundwater_flow_systems, list):
        failures.append("groundwater_flow_systems missing")
        groundwater_flow_systems = []
    groundwater_flow_cell_keys = {
        "groundwater_hydraulic_head_m",
        "groundwater_gradient_index",
        "groundwater_lateral_flow_km3_y",
        "groundwater_lateral_inflow_km3_y",
        "groundwater_available_volume_km3_y",
        "groundwater_internal_lateral_outflow_km3_y",
        "groundwater_discharge_mm_y",
        "groundwater_discharge_km3_y",
        "groundwater_retained_storage_km3_y",
        "groundwater_flow_mass_balance_residual_km3_y",
        "groundwater_flow_to_cell_id",
        "spring_discharge_index",
        "baseflow_support_index",
        "groundwater_flow_regime",
        "groundwater_flow_system_id",
    }
    if cells_payload and not groundwater_flow_cell_keys.issubset(cells_payload[0]):
        failures.append("groundwater flow cell fields missing")
    groundwater_flow_regimes = {
        "excluded",
        "recharge_mound",
        "recharge_throughflow",
        "throughflow",
        "discharge_zone",
        "lowland_discharge",
        "stagnant_or_low_yield",
    }
    groundwater_flow_regime_counts: dict[str, int] = {}
    groundwater_flow_cells: list[dict[str, Any]] = []
    groundwater_flow_assigned_cell_ids: set[int] = set()
    groundwater_flow_cell_count = 0
    groundwater_discharge_cell_count = 0
    spring_candidate_cell_count = 0
    baseflow_supported_river_cell_count = 0
    groundwater_discharge_sum_km3 = 0.0
    groundwater_lateral_sum_km3 = 0.0
    groundwater_recharge_sum_km3 = 0.0
    groundwater_gradient_sum = 0.0
    groundwater_discharge_sum_mm = 0.0
    spring_sum = 0.0
    baseflow_sum = 0.0
    groundwater_flow_cell_invalid = False
    for cell in cells_payload:
        cell_id = int(cell.get("id", -1))
        area = max(0.0, float(cell.get("area_km2", 0.0)))
        aquifer_class = str(cell.get("aquifer_class", ""))
        gradient = float(cell.get("groundwater_gradient_index", -1.0))
        lateral_km3 = float(cell.get("groundwater_lateral_flow_km3_y", -1.0))
        discharge_mm = float(cell.get("groundwater_discharge_mm_y", -1.0))
        discharge_km3 = float(cell.get("groundwater_discharge_km3_y", -1.0))
        flow_to = int(cell.get("groundwater_flow_to_cell_id", -2))
        spring_index = float(cell.get("spring_discharge_index", -1.0))
        baseflow_index = float(cell.get("baseflow_support_index", -1.0))
        flow_regime = str(cell.get("groundwater_flow_regime", ""))
        flow_system_id = int(cell.get("groundwater_flow_system_id", -2))
        groundwater_flow_regime_counts[flow_regime] = groundwater_flow_regime_counts.get(flow_regime, 0) + 1
        flow_to_valid = flow_to == -1 or (flow_to in cells_by_id and flow_to in {int(neighbor_id) for neighbor_id in cell.get("neighbors", [])})
        discharge_volume_valid = abs(discharge_km3 - discharge_mm * area * 0.000001) <= max(0.001, discharge_km3 * 0.0001)
        if (
            flow_regime not in groundwater_flow_regimes
            or not 0.0 <= gradient <= 1.0
            or lateral_km3 < 0.0
            or discharge_mm < 0.0
            or discharge_km3 < 0.0
            or not discharge_volume_valid
            or flow_system_id < -1
            or not 0.0 <= spring_index <= 1.0
            or not 0.0 <= baseflow_index <= 1.0
            or not flow_to_valid
            or (aquifer_class == "marine_excluded" and flow_regime != "excluded")
        ):
            groundwater_flow_cell_invalid = True
            break
        if aquifer_class != "marine_excluded":
            groundwater_flow_cells.append(cell)
            groundwater_recharge_sum_km3 += float(cell.get("groundwater_recharge_km3_y", 0.0))
            groundwater_discharge_sum_km3 += discharge_km3
            groundwater_lateral_sum_km3 += lateral_km3
            groundwater_gradient_sum += gradient
            groundwater_discharge_sum_mm += discharge_mm
            spring_sum += spring_index
            baseflow_sum += baseflow_index
            groundwater_discharge_cell_count += 1 if discharge_mm >= 25.0 else 0
            spring_candidate_cell_count += 1 if spring_index >= 0.45 else 0
            baseflow_supported_river_cell_count += 1 if bool(cell.get("is_river", False)) and baseflow_index >= 0.35 else 0
        if flow_system_id >= 0:
            groundwater_flow_assigned_cell_ids.add(cell_id)
            groundwater_flow_cell_count += 1
    if groundwater_flow_cell_invalid:
        failures.append("groundwater flow cell fields invalid")
    if groundwater_flow_regime_counts != {str(key): int(value) for key, value in summary.get("groundwater_flow_regime_counts", {}).items()}:
        failures.append("groundwater_flow_regime_counts does not match cells")
    expected_groundwater_flow_counts = {
        "groundwater_flow_cell_count": groundwater_flow_cell_count,
        "groundwater_flow_system_count": len(groundwater_flow_systems),
        "groundwater_discharge_cell_count": groundwater_discharge_cell_count,
        "spring_candidate_cell_count": spring_candidate_cell_count,
        "baseflow_supported_river_cell_count": baseflow_supported_river_cell_count,
    }
    for key, expected in expected_groundwater_flow_counts.items():
        if int(summary.get(key, -1)) != expected:
            failures.append(f"{key} does not match groundwater flow cells")
            break
    groundwater_flow_divisor = float(len(groundwater_flow_cells)) if groundwater_flow_cells else 1.0
    expected_groundwater_flow_means = {
        "mean_groundwater_gradient_index": groundwater_gradient_sum / groundwater_flow_divisor if groundwater_flow_cells else 0.0,
        "mean_groundwater_discharge_mm_y": groundwater_discharge_sum_mm / groundwater_flow_divisor if groundwater_flow_cells else 0.0,
        "mean_spring_discharge_index": spring_sum / groundwater_flow_divisor if groundwater_flow_cells else 0.0,
        "mean_baseflow_support_index": baseflow_sum / groundwater_flow_divisor if groundwater_flow_cells else 0.0,
    }
    for key, expected in expected_groundwater_flow_means.items():
        if abs(float(summary.get(key, 0.0)) - expected) > 0.001:
            failures.append(f"{key} does not match groundwater flow cells")
            break
    if abs(float(summary.get("total_groundwater_discharge_km3_y", 0.0)) - groundwater_discharge_sum_km3) > max(0.001, groundwater_discharge_sum_km3 * 0.0001):
        failures.append("total_groundwater_discharge_km3_y does not match cells")
    if abs(float(summary.get("total_groundwater_lateral_flow_km3_y", 0.0)) - groundwater_lateral_sum_km3) > max(0.001, groundwater_lateral_sum_km3 * 0.0001):
        failures.append("total_groundwater_lateral_flow_km3_y does not match cells")
    expected_groundwater_residual = groundwater_recharge_sum_km3 - groundwater_discharge_sum_km3
    if groundwater_discharge_sum_km3 > groundwater_recharge_sum_km3 + max(
        0.001, groundwater_recharge_sum_km3 * 0.0001
    ):
        failures.append("groundwater discharge exceeds finite recharge source")
    if abs(float(summary.get("total_groundwater_flow_balance_residual_km3_y", 0.0)) - expected_groundwater_residual) > max(0.001, abs(expected_groundwater_residual) * 0.0001):
        failures.append("total_groundwater_flow_balance_residual_km3_y does not match cells")

    groundwater_flow_system_keys = {
        "id",
        "aquifer_system_id",
        "basin_id",
        "flow_regime",
        "cell_count",
        "cell_ids",
        "recharge_cell_ids",
        "discharge_cell_ids",
        "terminal_cell_ids",
        "outlet_cell_id",
        "area_km2",
        "total_groundwater_recharge_km3_y",
        "total_groundwater_lateral_inflow_km3_y",
        "total_groundwater_internal_lateral_outflow_km3_y",
        "total_groundwater_discharge_km3_y",
        "total_groundwater_lateral_flow_km3_y",
        "total_groundwater_retained_storage_km3_y",
        "groundwater_flow_mass_balance_residual_km3_y",
        "groundwater_balance_residual_km3_y",
        "discharge_to_recharge_ratio",
        "mean_hydraulic_head_m",
        "mean_groundwater_gradient_index",
        "mean_groundwater_discharge_mm_y",
        "mean_spring_discharge_index",
        "mean_baseflow_support_index",
        "mean_aquifer_extraction_risk_index",
        "river_cell_count",
        "lake_cell_count",
        "wetland_cell_count",
        "closed_basin_cell_count",
        "flow_regime_counts",
    }
    if groundwater_flow_systems and not groundwater_flow_system_keys.issubset(groundwater_flow_systems[0]):
        failures.append("groundwater flow system fields missing")
    groundwater_flow_system_ids: set[int] = set()
    groundwater_flow_system_cell_ids: set[int] = set()
    groundwater_flow_system_invalid = False
    aquifer_system_ids_by_id = {int(system.get("id", -1)) for system in aquifer_systems}
    for index, system in enumerate(groundwater_flow_systems):
        system_id = int(system.get("id", -1))
        aquifer_system_id = int(system.get("aquifer_system_id", -1))
        cell_ids_for_system = system.get("cell_ids", [])
        recharge_cell_ids = system.get("recharge_cell_ids", [])
        discharge_cell_ids = system.get("discharge_cell_ids", [])
        terminal_cell_ids = system.get("terminal_cell_ids", [])
        if (
            not isinstance(cell_ids_for_system, list)
            or not isinstance(recharge_cell_ids, list)
            or not isinstance(discharge_cell_ids, list)
            or not isinstance(terminal_cell_ids, list)
        ):
            groundwater_flow_system_invalid = True
            break
        group_cells = [cells_by_id.get(int(cell_id)) for cell_id in cell_ids_for_system]
        if any(cell is None for cell in group_cells):
            groundwater_flow_system_invalid = True
            break
        valid_group_cells = [cell for cell in group_cells if cell is not None]
        group_count = len(valid_group_cells)
        group_ids = {int(cell.get("id", -1)) for cell in valid_group_cells}
        groundwater_flow_system_cell_ids.update(group_ids)
        area_sum = sum(max(0.0, float(cell.get("area_km2", 0.0))) for cell in valid_group_cells)
        recharge_sum = sum(float(cell.get("groundwater_recharge_km3_y", 0.0)) for cell in valid_group_cells)
        lateral_inflow_sum = sum(float(cell.get("groundwater_lateral_inflow_km3_y", 0.0)) for cell in valid_group_cells)
        internal_lateral_outflow_sum = sum(
            float(cell.get("groundwater_internal_lateral_outflow_km3_y", 0.0))
            for cell in valid_group_cells
        )
        discharge_sum = sum(float(cell.get("groundwater_discharge_km3_y", 0.0)) for cell in valid_group_cells)
        lateral_sum = sum(float(cell.get("groundwater_lateral_flow_km3_y", 0.0)) for cell in valid_group_cells)
        retained_storage_sum = sum(float(cell.get("groundwater_retained_storage_km3_y", 0.0)) for cell in valid_group_cells)
        flow_mass_balance_residual_sum = sum(
            float(cell.get("groundwater_flow_mass_balance_residual_km3_y", 0.0))
            for cell in valid_group_cells
        )
        head_sum = sum(float(cell.get("groundwater_hydraulic_head_m", 0.0)) for cell in valid_group_cells)
        gradient_sum = sum(float(cell.get("groundwater_gradient_index", 0.0)) for cell in valid_group_cells)
        discharge_mm_sum = sum(float(cell.get("groundwater_discharge_mm_y", 0.0)) for cell in valid_group_cells)
        spring_group_sum = sum(float(cell.get("spring_discharge_index", 0.0)) for cell in valid_group_cells)
        baseflow_group_sum = sum(float(cell.get("baseflow_support_index", 0.0)) for cell in valid_group_cells)
        extraction_group_sum = sum(float(cell.get("aquifer_extraction_risk_index", 0.0)) for cell in valid_group_cells)
        system_regime_counts: dict[str, int] = {}
        for cell in valid_group_cells:
            regime_name = str(cell.get("groundwater_flow_regime", ""))
            system_regime_counts[regime_name] = system_regime_counts.get(regime_name, 0) + 1
        groundwater_flow_system_ids.add(system_id)
        expected_discharge_ids = {
            int(cell.get("id", -1))
            for cell in valid_group_cells
            if float(cell.get("groundwater_discharge_mm_y", 0.0)) >= 25.0 or float(cell.get("spring_discharge_index", 0.0)) >= 0.45
        }
        expected_recharge_ids = {
            int(cell.get("id", -1)) for cell in valid_group_cells if float(cell.get("groundwater_recharge_mm_y", 0.0)) >= 50.0
        }
        expected_terminal_ids = {
            int(cell.get("id", -1))
            for cell in valid_group_cells
            if int(cell.get("groundwater_flow_to_cell_id", -1)) < 0 or int(cell.get("groundwater_flow_to_cell_id", -1)) not in group_ids
        }
        expected_residual = recharge_sum - discharge_sum
        expected_ratio = discharge_sum / recharge_sum if recharge_sum > 0.0 else 0.0
        group_divisor = float(group_count) if group_count else 1.0
        if (
            system_id != index
            or group_count <= 0
            or aquifer_system_id not in aquifer_system_ids_by_id
            or int(system.get("cell_count", -1)) != group_count
            or any(int(cell.get("groundwater_flow_system_id", -1)) != system_id for cell in valid_group_cells)
            or any(int(cell.get("aquifer_system_id", -1)) != aquifer_system_id for cell in valid_group_cells)
            or str(system.get("flow_regime", "")) not in groundwater_flow_regimes
            or int(system.get("outlet_cell_id", -1)) not in group_ids
            or set(map(int, recharge_cell_ids)) != expected_recharge_ids
            or set(map(int, discharge_cell_ids)) != expected_discharge_ids
            or set(map(int, terminal_cell_ids)) != expected_terminal_ids
            or abs(float(system.get("area_km2", 0.0)) - area_sum) > max(0.001, area_sum * 0.0001)
            or abs(float(system.get("total_groundwater_recharge_km3_y", 0.0)) - recharge_sum) > max(0.001, recharge_sum * 0.0001)
            or abs(float(system.get("total_groundwater_lateral_inflow_km3_y", 0.0)) - lateral_inflow_sum) > max(0.001, lateral_inflow_sum * 0.0001)
            or abs(float(system.get("total_groundwater_internal_lateral_outflow_km3_y", 0.0)) - internal_lateral_outflow_sum) > max(0.001, internal_lateral_outflow_sum * 0.0001)
            or abs(float(system.get("total_groundwater_discharge_km3_y", 0.0)) - discharge_sum) > max(0.001, discharge_sum * 0.0001)
            or abs(float(system.get("total_groundwater_lateral_flow_km3_y", 0.0)) - lateral_sum) > max(0.001, lateral_sum * 0.0001)
            or abs(float(system.get("total_groundwater_retained_storage_km3_y", 0.0)) - retained_storage_sum) > max(0.001, retained_storage_sum * 0.0001)
            or abs(float(system.get("groundwater_flow_mass_balance_residual_km3_y", 0.0)) - flow_mass_balance_residual_sum) > 0.000001
            or abs(recharge_sum + lateral_inflow_sum - internal_lateral_outflow_sum - discharge_sum - retained_storage_sum - flow_mass_balance_residual_sum) > 0.001
            or abs(float(system.get("groundwater_balance_residual_km3_y", 0.0)) - expected_residual) > max(0.001, abs(expected_residual) * 0.0001)
            or abs(float(system.get("discharge_to_recharge_ratio", 0.0)) - expected_ratio) > 0.001
            or abs(float(system.get("mean_hydraulic_head_m", 0.0)) - head_sum / group_divisor) > 0.001
            or abs(float(system.get("mean_groundwater_gradient_index", 0.0)) - gradient_sum / group_divisor) > 0.001
            or abs(float(system.get("mean_groundwater_discharge_mm_y", 0.0)) - discharge_mm_sum / group_divisor) > 0.001
            or abs(float(system.get("mean_spring_discharge_index", 0.0)) - spring_group_sum / group_divisor) > 0.001
            or abs(float(system.get("mean_baseflow_support_index", 0.0)) - baseflow_group_sum / group_divisor) > 0.001
            or abs(float(system.get("mean_aquifer_extraction_risk_index", 0.0)) - extraction_group_sum / group_divisor) > 0.001
            or int(system.get("river_cell_count", -1)) != sum(1 for cell in valid_group_cells if bool(cell.get("is_river", False)))
            or int(system.get("lake_cell_count", -1)) != sum(1 for cell in valid_group_cells if bool(cell.get("is_lake", False)))
            or int(system.get("wetland_cell_count", -1)) != sum(1 for cell in valid_group_cells if float(cell.get("wetland_extent_index", 0.0)) >= 0.35)
            or int(system.get("closed_basin_cell_count", -1)) != sum(1 for cell in valid_group_cells if bool(cell.get("is_closed_basin", False)))
            or system_regime_counts != {str(key): int(value) for key, value in system.get("flow_regime_counts", {}).items()}
        ):
            groundwater_flow_system_invalid = True
            break
    if groundwater_flow_system_invalid:
        failures.append("groundwater flow system records invalid")
    if len(groundwater_flow_system_ids) != len(groundwater_flow_systems):
        failures.append("groundwater flow system ids are not unique")
    if groundwater_flow_system_cell_ids != groundwater_flow_assigned_cell_ids:
        failures.append("groundwater flow system membership does not match cells")

    return failures
