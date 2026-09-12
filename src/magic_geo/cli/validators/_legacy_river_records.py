"""Historical v1 channel and hydraulic record mirrors, with unchanged arithmetic."""

from __future__ import annotations
from typing import Any


def _validate_legacy_river_records(
    payload: dict[str, Any], summary: dict[str, Any],
    cells_payload: list[dict[str, Any]], cells_by_id: dict[int, dict[str, Any]],
) -> list[str]:
    failures: list[str] = []
    river_channel_systems = payload.get("river_channel_systems", [])
    river_channel_summary_keys = {
        "river_channel_morphology_model",
        "river_channel_cell_count",
        "river_channel_system_count",
        "navigable_channel_depth_cell_count",
        "floodplain_connected_channel_cell_count",
        "high_stream_power_channel_cell_count",
        "total_river_channel_length_km",
        "mean_river_channel_width_m",
        "mean_river_channel_depth_m",
        "mean_bankfull_discharge_m3_s",
        "mean_stream_power_index",
        "mean_channel_slope_index",
        "channel_morphology_class_counts",
    }
    if not river_channel_summary_keys.issubset(summary):
        failures.append("river channel summary metrics missing")
    if not isinstance(river_channel_systems, list):
        failures.append("river_channel_systems missing")
        river_channel_systems = []
    river_channel_cell_keys = {
        "river_channel_width_m",
        "river_channel_depth_m",
        "bankfull_discharge_m3_s",
        "channel_slope_index",
        "stream_power_index",
        "floodplain_connectivity_index",
        "channel_morphology_class",
        "river_channel_system_id",
    }
    if cells_payload and not river_channel_cell_keys.issubset(cells_payload[0]):
        failures.append("river channel cell fields missing")
    allowed_channel_classes = {
        "non_channel",
        "small_headwater",
        "incised_bedrock_channel",
        "braided_sediment_rich_channel",
        "deep_alluvial_channel",
        "navigable_lowland_channel",
        "ephemeral_wadi",
        "glacial_outwash_channel",
    }
    river_channel_class_counts: dict[str, int] = {}
    river_channel_candidate_ids: set[int] = set()
    river_channel_assigned_ids: set[int] = set()
    river_channel_width_sum = 0.0
    river_channel_depth_sum = 0.0
    bankfull_discharge_sum = 0.0
    stream_power_sum = 0.0
    channel_slope_sum = 0.0
    navigable_channel_depth_count = 0
    floodplain_connected_channel_count = 0
    high_stream_power_channel_count = 0
    river_channel_cell_invalid = False
    for cell in cells_payload:
        cell_id = int(cell.get("id", -1))
        width = float(cell.get("river_channel_width_m", -1.0))
        depth = float(cell.get("river_channel_depth_m", -1.0))
        discharge = float(cell.get("bankfull_discharge_m3_s", -1.0))
        slope = float(cell.get("channel_slope_index", -1.0))
        stream_power = float(cell.get("stream_power_index", -1.0))
        floodplain = float(cell.get("floodplain_connectivity_index", -1.0))
        channel_class = str(cell.get("channel_morphology_class", ""))
        channel_system_id = int(cell.get("river_channel_system_id", -2))
        channel_candidate = bool(cell.get("is_river", False)) and not bool(cell.get("is_water", False))
        river_channel_class_counts[channel_class] = river_channel_class_counts.get(channel_class, 0) + 1
        if (
            width < 0.0
            or depth < 0.0
            or discharge < 0.0
            or not 0.0 <= slope <= 1.0
            or not 0.0 <= stream_power <= 1.0
            or not 0.0 <= floodplain <= 1.0
            or channel_class not in allowed_channel_classes
            or channel_system_id < -1
            or (not channel_candidate and (width != 0.0 or depth != 0.0 or discharge != 0.0 or slope != 0.0 or stream_power != 0.0 or floodplain != 0.0 or channel_class != "non_channel" or channel_system_id != -1))
            or (channel_candidate and channel_class == "non_channel")
        ):
            river_channel_cell_invalid = True
            break
        if channel_candidate:
            river_channel_candidate_ids.add(cell_id)
            river_channel_width_sum += width
            river_channel_depth_sum += depth
            bankfull_discharge_sum += discharge
            stream_power_sum += stream_power
            channel_slope_sum += slope
            navigable_channel_depth_count += 1 if depth >= 1.8 and width >= 35.0 else 0
            floodplain_connected_channel_count += 1 if floodplain >= 0.45 else 0
            high_stream_power_channel_count += 1 if stream_power >= 0.62 else 0
        if channel_system_id >= 0:
            river_channel_assigned_ids.add(cell_id)
    if river_channel_cell_invalid:
        failures.append("river channel cell fields invalid")
    if river_channel_class_counts != {str(key): int(value) for key, value in summary.get("channel_morphology_class_counts", {}).items()}:
        failures.append("channel_morphology_class_counts does not match cells")
    if int(summary.get("river_channel_cell_count", -1)) != len(river_channel_candidate_ids):
        failures.append("river_channel_cell_count does not match cells")
    if int(summary.get("river_channel_system_count", -1)) != len(river_channel_systems):
        failures.append("river_channel_system_count does not match systems")
    expected_channel_counts = {
        "navigable_channel_depth_cell_count": navigable_channel_depth_count,
        "floodplain_connected_channel_cell_count": floodplain_connected_channel_count,
        "high_stream_power_channel_cell_count": high_stream_power_channel_count,
    }
    for key, expected in expected_channel_counts.items():
        if int(summary.get(key, -1)) != expected:
            failures.append(f"{key} does not match cells")
            break
    river_channel_divisor = float(len(river_channel_candidate_ids)) if river_channel_candidate_ids else 1.0
    expected_channel_means = {
        "mean_river_channel_width_m": river_channel_width_sum / river_channel_divisor if river_channel_candidate_ids else 0.0,
        "mean_river_channel_depth_m": river_channel_depth_sum / river_channel_divisor if river_channel_candidate_ids else 0.0,
        "mean_bankfull_discharge_m3_s": bankfull_discharge_sum / river_channel_divisor if river_channel_candidate_ids else 0.0,
        "mean_stream_power_index": stream_power_sum / river_channel_divisor if river_channel_candidate_ids else 0.0,
        "mean_channel_slope_index": channel_slope_sum / river_channel_divisor if river_channel_candidate_ids else 0.0,
    }
    for key, expected in expected_channel_means.items():
        if abs(float(summary.get(key, 0.0)) - expected) > 0.001:
            failures.append(f"{key} does not match cells")
            break
    river_channel_system_keys = {
        "id",
        "channel_type",
        "cell_count",
        "cell_ids",
        "basin_ids",
        "source_cell_id",
        "outlet_cell_id",
        "length_km",
        "area_km2",
        "mean_channel_width_m",
        "mean_channel_depth_m",
        "mean_bankfull_discharge_m3_s",
        "mean_stream_power_index",
        "mean_channel_slope_index",
        "mean_floodplain_connectivity_index",
        "navigable_depth_cell_count",
        "floodplain_connected_cell_count",
        "high_stream_power_cell_count",
        "channel_morphology_class_counts",
    }
    if river_channel_systems and not river_channel_system_keys.issubset(river_channel_systems[0]):
        failures.append("river channel system fields missing")
    river_channel_system_ids_seen: set[int] = set()
    river_channel_system_member_ids: set[int] = set()
    river_channel_total_length = 0.0
    river_channel_system_invalid = False
    for index, system in enumerate(river_channel_systems):
        system_id = int(system.get("id", -1))
        cell_ids_for_system = system.get("cell_ids", [])
        basin_ids_for_system = system.get("basin_ids", [])
        if not isinstance(cell_ids_for_system, list) or not isinstance(basin_ids_for_system, list):
            river_channel_system_invalid = True
            break
        group_cells = [cells_by_id.get(int(cell_id)) for cell_id in cell_ids_for_system]
        if any(cell is None for cell in group_cells):
            river_channel_system_invalid = True
            break
        valid_group_cells = [cell for cell in group_cells if cell is not None]
        group_count = len(valid_group_cells)
        group_ids = {int(cell.get("id", -1)) for cell in valid_group_cells}
        river_channel_system_member_ids.update(group_ids)
        system_class_counts: dict[str, int] = {}
        for cell in valid_group_cells:
            class_name = str(cell.get("channel_morphology_class", ""))
            system_class_counts[class_name] = system_class_counts.get(class_name, 0) + 1
        expected_basin_ids = sorted({int(cell.get("basin_id", -1)) for cell in valid_group_cells if int(cell.get("basin_id", -1)) >= 0})
        area_sum = sum(max(0.0, float(cell.get("area_km2", 0.0))) for cell in valid_group_cells)
        width_sum = sum(float(cell.get("river_channel_width_m", 0.0)) for cell in valid_group_cells)
        depth_sum = sum(float(cell.get("river_channel_depth_m", 0.0)) for cell in valid_group_cells)
        discharge_sum = sum(float(cell.get("bankfull_discharge_m3_s", 0.0)) for cell in valid_group_cells)
        stream_power_group_sum = sum(float(cell.get("stream_power_index", 0.0)) for cell in valid_group_cells)
        slope_group_sum = sum(float(cell.get("channel_slope_index", 0.0)) for cell in valid_group_cells)
        floodplain_group_sum = sum(float(cell.get("floodplain_connectivity_index", 0.0)) for cell in valid_group_cells)
        river_channel_total_length += float(system.get("length_km", 0.0))
        river_channel_system_ids_seen.add(system_id)
        if (
            system_id != index
            or group_count <= 0
            or int(system.get("cell_count", -1)) != group_count
            or len(group_ids) != len(cell_ids_for_system)
            or not group_ids.issubset(river_channel_candidate_ids)
            or any(int(cell.get("river_channel_system_id", -1)) != system_id for cell in valid_group_cells)
            or str(system.get("channel_type", "")) not in allowed_channel_classes
            or int(system.get("source_cell_id", -1)) not in group_ids
            or int(system.get("outlet_cell_id", -1)) not in group_ids
            or [int(basin_id) for basin_id in basin_ids_for_system] != expected_basin_ids
            or float(system.get("length_km", -1.0)) < 0.0
            or abs(float(system.get("area_km2", 0.0)) - area_sum) > max(0.001, area_sum * 0.0001)
            or abs(float(system.get("mean_channel_width_m", 0.0)) - width_sum / group_count) > 0.001
            or abs(float(system.get("mean_channel_depth_m", 0.0)) - depth_sum / group_count) > 0.001
            or abs(float(system.get("mean_bankfull_discharge_m3_s", 0.0)) - discharge_sum / group_count) > 0.001
            or abs(float(system.get("mean_stream_power_index", 0.0)) - stream_power_group_sum / group_count) > 0.001
            or abs(float(system.get("mean_channel_slope_index", 0.0)) - slope_group_sum / group_count) > 0.001
            or abs(float(system.get("mean_floodplain_connectivity_index", 0.0)) - floodplain_group_sum / group_count) > 0.001
            or int(system.get("navigable_depth_cell_count", -1)) != sum(1 for cell in valid_group_cells if float(cell.get("river_channel_depth_m", 0.0)) >= 1.8 and float(cell.get("river_channel_width_m", 0.0)) >= 35.0)
            or int(system.get("floodplain_connected_cell_count", -1)) != sum(1 for cell in valid_group_cells if float(cell.get("floodplain_connectivity_index", 0.0)) >= 0.45)
            or int(system.get("high_stream_power_cell_count", -1)) != sum(1 for cell in valid_group_cells if float(cell.get("stream_power_index", 0.0)) >= 0.62)
            or system_class_counts != {str(key): int(value) for key, value in system.get("channel_morphology_class_counts", {}).items()}
        ):
            river_channel_system_invalid = True
            break
    if river_channel_system_invalid:
        failures.append("river channel system records invalid")
    if len(river_channel_system_ids_seen) != len(river_channel_systems):
        failures.append("river channel system ids are not unique")
    if river_channel_system_member_ids != river_channel_assigned_ids or river_channel_assigned_ids != river_channel_candidate_ids:
        failures.append("river channel system membership does not match cells")
    if abs(float(summary.get("total_river_channel_length_km", 0.0)) - river_channel_total_length) > max(
        0.001,
        river_channel_total_length * 0.0001,
    ):
        failures.append("total_river_channel_length_km does not match systems")

    river_hydraulic_reaches = payload.get("river_hydraulic_reaches", [])
    river_hydraulic_summary_keys = {
        "river_hydraulics_model",
        "river_hydraulic_cell_count",
        "river_hydraulic_reach_count",
        "mean_hydraulic_radius_m",
        "mean_flow_velocity_m_s",
        "mean_froude_number",
        "mean_bed_shear_stress_pa",
        "mean_manning_roughness_n",
        "mean_channel_capacity_index",
        "mean_hydraulic_navigability_index",
        "hydraulically_navigable_cell_count",
        "supercritical_flow_cell_count",
        "high_shear_stress_cell_count",
        "hydraulic_flow_regime_counts",
    }
    if not river_hydraulic_summary_keys.issubset(summary):
        failures.append("river hydraulic summary metrics missing")
    if not isinstance(river_hydraulic_reaches, list):
        failures.append("river_hydraulic_reaches missing")
        river_hydraulic_reaches = []
    river_hydraulic_cell_keys = {
        "hydraulic_radius_m",
        "flow_velocity_m_s",
        "froude_number",
        "bed_shear_stress_pa",
        "manning_roughness_n",
        "channel_capacity_index",
        "hydraulic_navigability_index",
        "hydraulic_flow_regime",
        "river_hydraulic_reach_id",
    }
    if cells_payload and not river_hydraulic_cell_keys.issubset(cells_payload[0]):
        failures.append("river hydraulic cell fields missing")
    allowed_hydraulic_regimes = {
        "non_channel",
        "subcritical",
        "swift_subcritical",
        "transitional",
        "supercritical",
    }
    hydraulic_regime_counts: dict[str, int] = {}
    hydraulic_candidate_ids: set[int] = set()
    hydraulic_reach_assigned_ids: set[int] = set()
    hydraulic_radius_sum = 0.0
    velocity_sum = 0.0
    froude_sum = 0.0
    shear_sum = 0.0
    roughness_sum = 0.0
    capacity_sum = 0.0
    hydraulic_nav_sum = 0.0
    hydraulically_navigable_count = 0
    supercritical_flow_count = 0
    high_shear_count = 0
    hydraulic_cell_invalid = False
    for cell in cells_payload:
        cell_id = int(cell.get("id", -1))
        radius = float(cell.get("hydraulic_radius_m", -1.0))
        velocity = float(cell.get("flow_velocity_m_s", -1.0))
        froude = float(cell.get("froude_number", -1.0))
        shear = float(cell.get("bed_shear_stress_pa", -1.0))
        roughness = float(cell.get("manning_roughness_n", -1.0))
        capacity = float(cell.get("channel_capacity_index", -1.0))
        hydraulic_nav = float(cell.get("hydraulic_navigability_index", -1.0))
        regime = str(cell.get("hydraulic_flow_regime", ""))
        reach_id = int(cell.get("river_hydraulic_reach_id", -2))
        channel_candidate = bool(cell.get("is_river", False)) and not bool(cell.get("is_water", False))
        hydraulic_regime_counts[regime] = hydraulic_regime_counts.get(regime, 0) + 1
        if (
            radius < 0.0
            or velocity < 0.0
            or froude < 0.0
            or shear < 0.0
            or roughness < 0.0
            or not 0.0 <= capacity <= 1.0
            or not 0.0 <= hydraulic_nav <= 1.0
            or regime not in allowed_hydraulic_regimes
            or reach_id < -1
            or (
                not channel_candidate
                and (
                    radius != 0.0
                    or velocity != 0.0
                    or froude != 0.0
                    or shear != 0.0
                    or roughness != 0.0
                    or capacity != 0.0
                    or hydraulic_nav != 0.0
                    or regime != "non_channel"
                    or reach_id != -1
                )
            )
            or (channel_candidate and (regime == "non_channel" or reach_id != int(cell.get("river_channel_system_id", -1))))
        ):
            hydraulic_cell_invalid = True
            break
        if channel_candidate:
            hydraulic_candidate_ids.add(cell_id)
            hydraulic_radius_sum += radius
            velocity_sum += velocity
            froude_sum += froude
            shear_sum += shear
            roughness_sum += roughness
            capacity_sum += capacity
            hydraulic_nav_sum += hydraulic_nav
            hydraulically_navigable_count += 1 if hydraulic_nav >= 0.55 else 0
            supercritical_flow_count += 1 if regime == "supercritical" else 0
            high_shear_count += 1 if shear >= 120.0 else 0
        if reach_id >= 0:
            hydraulic_reach_assigned_ids.add(cell_id)
    if hydraulic_cell_invalid:
        failures.append("river hydraulic cell fields invalid")
    if hydraulic_regime_counts != {str(key): int(value) for key, value in summary.get("hydraulic_flow_regime_counts", {}).items()}:
        failures.append("hydraulic_flow_regime_counts does not match cells")
    if int(summary.get("river_hydraulic_cell_count", -1)) != len(hydraulic_candidate_ids):
        failures.append("river_hydraulic_cell_count does not match cells")
    if int(summary.get("river_hydraulic_reach_count", -1)) != len(river_hydraulic_reaches):
        failures.append("river_hydraulic_reach_count does not match reaches")
    if len(hydraulic_candidate_ids) != len(river_channel_candidate_ids):
        failures.append("river hydraulic cell set does not match river channel cells")
    hydraulic_divisor = float(len(hydraulic_candidate_ids)) if hydraulic_candidate_ids else 1.0
    expected_hydraulic_means = {
        "mean_hydraulic_radius_m": hydraulic_radius_sum / hydraulic_divisor if hydraulic_candidate_ids else 0.0,
        "mean_flow_velocity_m_s": velocity_sum / hydraulic_divisor if hydraulic_candidate_ids else 0.0,
        "mean_froude_number": froude_sum / hydraulic_divisor if hydraulic_candidate_ids else 0.0,
        "mean_bed_shear_stress_pa": shear_sum / hydraulic_divisor if hydraulic_candidate_ids else 0.0,
        "mean_manning_roughness_n": roughness_sum / hydraulic_divisor if hydraulic_candidate_ids else 0.0,
        "mean_channel_capacity_index": capacity_sum / hydraulic_divisor if hydraulic_candidate_ids else 0.0,
        "mean_hydraulic_navigability_index": hydraulic_nav_sum / hydraulic_divisor if hydraulic_candidate_ids else 0.0,
    }
    for key, expected in expected_hydraulic_means.items():
        if abs(float(summary.get(key, 0.0)) - expected) > 0.001:
            failures.append(f"{key} does not match cells")
            break
    expected_hydraulic_counts = {
        "hydraulically_navigable_cell_count": hydraulically_navigable_count,
        "supercritical_flow_cell_count": supercritical_flow_count,
        "high_shear_stress_cell_count": high_shear_count,
    }
    for key, expected in expected_hydraulic_counts.items():
        if int(summary.get(key, -1)) != expected:
            failures.append(f"{key} does not match cells")
            break
    river_channel_system_by_id = {int(system.get("id", -1)): system for system in river_channel_systems if isinstance(system, dict)}
    river_hydraulic_reach_keys = {
        "id",
        "river_channel_system_id",
        "cell_count",
        "cell_ids",
        "basin_ids",
        "source_cell_id",
        "outlet_cell_id",
        "length_km",
        "area_km2",
        "dominant_hydraulic_flow_regime",
        "mean_hydraulic_radius_m",
        "mean_flow_velocity_m_s",
        "mean_froude_number",
        "mean_bed_shear_stress_pa",
        "mean_manning_roughness_n",
        "mean_channel_capacity_index",
        "mean_hydraulic_navigability_index",
        "hydraulically_navigable_cell_count",
        "supercritical_flow_cell_count",
        "high_shear_stress_cell_count",
        "hydraulic_flow_regime_counts",
    }
    if river_hydraulic_reaches and not river_hydraulic_reach_keys.issubset(river_hydraulic_reaches[0]):
        failures.append("river hydraulic reach fields missing")
    reach_ids_seen: set[int] = set()
    reach_member_ids: set[int] = set()
    hydraulic_reach_invalid = False
    for index, reach in enumerate(river_hydraulic_reaches):
        reach_id = int(reach.get("id", -1))
        system_id = int(reach.get("river_channel_system_id", -1))
        system = river_channel_system_by_id.get(system_id)
        cell_ids_for_reach = reach.get("cell_ids", [])
        basin_ids_for_reach = reach.get("basin_ids", [])
        if system is None or not isinstance(cell_ids_for_reach, list) or not isinstance(basin_ids_for_reach, list):
            hydraulic_reach_invalid = True
            break
        valid_reach_cells = [cells_by_id.get(int(cell_id)) for cell_id in cell_ids_for_reach]
        if any(cell is None for cell in valid_reach_cells):
            hydraulic_reach_invalid = True
            break
        reach_cells = [cell for cell in valid_reach_cells if cell is not None]
        group_count = len(reach_cells)
        group_ids = {int(cell.get("id", -1)) for cell in reach_cells}
        reach_member_ids.update(group_ids)
        reach_ids_seen.add(reach_id)
        regime_counts_for_reach: dict[str, int] = {}
        for cell in reach_cells:
            regime = str(cell.get("hydraulic_flow_regime", ""))
            regime_counts_for_reach[regime] = regime_counts_for_reach.get(regime, 0) + 1
        dominant_regime = sorted(regime_counts_for_reach.items(), key=lambda item: (-item[1], item[0]))[0][0] if regime_counts_for_reach else "non_channel"
        radius_sum = sum(float(cell.get("hydraulic_radius_m", 0.0)) for cell in reach_cells)
        reach_velocity_sum = sum(float(cell.get("flow_velocity_m_s", 0.0)) for cell in reach_cells)
        reach_froude_sum = sum(float(cell.get("froude_number", 0.0)) for cell in reach_cells)
        reach_shear_sum = sum(float(cell.get("bed_shear_stress_pa", 0.0)) for cell in reach_cells)
        reach_roughness_sum = sum(float(cell.get("manning_roughness_n", 0.0)) for cell in reach_cells)
        reach_capacity_sum = sum(float(cell.get("channel_capacity_index", 0.0)) for cell in reach_cells)
        reach_nav_sum = sum(float(cell.get("hydraulic_navigability_index", 0.0)) for cell in reach_cells)
        if (
            reach_id != index
            or system_id != reach_id
            or group_count <= 0
            or int(reach.get("cell_count", -1)) != group_count
            or group_ids != {int(cell_id) for cell_id in system.get("cell_ids", [])}
            or any(int(cell.get("river_hydraulic_reach_id", -1)) != reach_id for cell in reach_cells)
            or [int(value) for value in basin_ids_for_reach] != [int(value) for value in system.get("basin_ids", [])]
            or int(reach.get("source_cell_id", -1)) != int(system.get("source_cell_id", -1))
            or int(reach.get("outlet_cell_id", -1)) != int(system.get("outlet_cell_id", -1))
            or abs(float(reach.get("length_km", 0.0)) - float(system.get("length_km", 0.0))) > max(0.001, float(system.get("length_km", 0.0)) * 0.0001)
            or abs(float(reach.get("area_km2", 0.0)) - float(system.get("area_km2", 0.0))) > max(0.001, float(system.get("area_km2", 0.0)) * 0.0001)
            or str(reach.get("dominant_hydraulic_flow_regime", "")) != dominant_regime
            or abs(float(reach.get("mean_hydraulic_radius_m", 0.0)) - radius_sum / group_count) > 0.001
            or abs(float(reach.get("mean_flow_velocity_m_s", 0.0)) - reach_velocity_sum / group_count) > 0.001
            or abs(float(reach.get("mean_froude_number", 0.0)) - reach_froude_sum / group_count) > 0.001
            or abs(float(reach.get("mean_bed_shear_stress_pa", 0.0)) - reach_shear_sum / group_count) > 0.001
            or abs(float(reach.get("mean_manning_roughness_n", 0.0)) - reach_roughness_sum / group_count) > 0.001
            or abs(float(reach.get("mean_channel_capacity_index", 0.0)) - reach_capacity_sum / group_count) > 0.001
            or abs(float(reach.get("mean_hydraulic_navigability_index", 0.0)) - reach_nav_sum / group_count) > 0.001
            or int(reach.get("hydraulically_navigable_cell_count", -1)) != sum(1 for cell in reach_cells if float(cell.get("hydraulic_navigability_index", 0.0)) >= 0.55)
            or int(reach.get("supercritical_flow_cell_count", -1)) != sum(1 for cell in reach_cells if str(cell.get("hydraulic_flow_regime", "")) == "supercritical")
            or int(reach.get("high_shear_stress_cell_count", -1)) != sum(1 for cell in reach_cells if float(cell.get("bed_shear_stress_pa", 0.0)) >= 120.0)
            or regime_counts_for_reach != {str(key): int(value) for key, value in reach.get("hydraulic_flow_regime_counts", {}).items()}
        ):
            hydraulic_reach_invalid = True
            break
    if hydraulic_reach_invalid:
        failures.append("river hydraulic reach records invalid")
    if len(reach_ids_seen) != len(river_hydraulic_reaches):
        failures.append("river hydraulic reach ids are not unique")
    if reach_member_ids != hydraulic_reach_assigned_ids or hydraulic_reach_assigned_ids != hydraulic_candidate_ids:
        failures.append("river hydraulic reach membership does not match cells")

    return failures
