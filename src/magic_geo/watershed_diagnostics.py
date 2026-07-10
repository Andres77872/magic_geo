from __future__ import annotations

import math
from typing import Any

from .planet_parameters import planet_radius_km
from .scaling import HACK_FIT_MINIMUM_BASIN_AREA_KM2, fit_power_law


HACK_EXPONENT = 0.6


def _great_circle_km(a: dict[str, Any], b: dict[str, Any], radius_km: float) -> float:
    lat_a = math.radians(float(a.get("lat_deg", 0.0)))
    lat_b = math.radians(float(b.get("lat_deg", 0.0)))
    dlat = lat_b - lat_a
    dlon = math.radians(float(b.get("lon_deg", 0.0)) - float(a.get("lon_deg", 0.0)))
    hav = math.sin(dlat / 2.0) ** 2 + math.cos(lat_a) * math.cos(lat_b) * math.sin(dlon / 2.0) ** 2
    return 2.0 * radius_km * math.asin(min(1.0, math.sqrt(hav)))


def _trace_downstream_path(
    start_cell: dict[str, Any],
    basin_id: int,
    cells_by_id: dict[int, dict[str, Any]],
    max_steps: int,
) -> list[int]:
    path: list[int] = []
    seen: set[int] = set()
    current = start_cell
    for _ in range(max_steps):
        cell_id = int(current.get("id", -1))
        if cell_id < 0 or cell_id in seen:
            break
        path.append(cell_id)
        seen.add(cell_id)
        next_id = int(current.get("flow_to", -1))
        next_cell = cells_by_id.get(next_id)
        if next_cell is None or int(next_cell.get("basin_id", -1)) != basin_id:
            break
        current = next_cell
    return path


def _path_length(path: list[int], cells_by_id: dict[int, dict[str, Any]], radius_km: float) -> float:
    length = 0.0
    for first_id, second_id in zip(path, path[1:]):
        first = cells_by_id.get(first_id)
        second = cells_by_id.get(second_id)
        if first is not None and second is not None:
            length += _great_circle_km(first, second, radius_km)
    return length


def _path_drop(path: list[int], cells_by_id: dict[int, dict[str, Any]]) -> float:
    if len(path) < 2:
        return 0.0
    first = cells_by_id.get(path[0])
    last = cells_by_id.get(path[-1])
    if first is None or last is None:
        return 0.0
    return max(
        0.0,
        float(
            first.get(
                "hydrologic_surface_elevation_m",
                first.get("filled_elevation_m", first.get("elevation_m", 0.0)),
            )
        )
        - float(
            last.get(
                "hydrologic_surface_elevation_m",
                last.get("filled_elevation_m", last.get("elevation_m", 0.0)),
            )
        ),
    )


def _basin_river_length(
    river_cells: list[dict[str, Any]],
    basin_id: int,
    cells_by_id: dict[int, dict[str, Any]],
    radius_km: float,
) -> float:
    total = 0.0
    for cell in river_cells:
        next_cell = cells_by_id.get(int(cell.get("flow_to", -1)))
        if next_cell is None or int(next_cell.get("basin_id", -1)) != basin_id:
            continue
        total += _great_circle_km(cell, next_cell, radius_km)
    return total


def enrich_world_with_watershed_diagnostics(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    watersheds = world.get("watersheds", [])
    if not isinstance(cells, list) or not isinstance(watersheds, list):
        return world

    radius_km = planet_radius_km(world)
    cells_by_id = {int(cell.get("id", index)): cell for index, cell in enumerate(cells)}
    basin_cells: dict[int, list[dict[str, Any]]] = {}
    for cell in cells:
        basin_id = int(cell.get("basin_id", -1))
        if basin_id >= 0:
            basin_cells.setdefault(basin_id, []).append(cell)

    diagnostics: list[dict[str, Any]] = []
    outlet_counts: dict[str, int] = {}
    for watershed in watersheds:
        basin_id = int(watershed.get("basin_id", -1))
        basin_group = basin_cells.get(basin_id, [])
        river_cells = [cell for cell in basin_group if bool(cell.get("is_river", False))]
        drainage_cells = [cell for cell in basin_group if not bool(cell.get("is_water", False))]
        max_steps = max(1, len(basin_group) + 1)
        best_path: list[int] = []
        best_length = 0.0
        best_accumulation = -1.0

        for cell in drainage_cells:
            path = _trace_downstream_path(cell, basin_id, cells_by_id, max_steps)
            length = _path_length(path, cells_by_id, radius_km)
            accumulation = float(cell.get("flow_accumulation", 0.0))
            if (
                not best_path
                or length > best_length
                or (math.isclose(length, best_length) and accumulation > best_accumulation)
            ):
                best_path = path
                best_length = length
                best_accumulation = accumulation

        if not best_path and river_cells:
            outlet_candidate = max(river_cells, key=lambda cell: float(cell.get("flow_accumulation", 0.0)))
            best_path = [int(outlet_candidate.get("id", -1))]
            best_accumulation = float(outlet_candidate.get("flow_accumulation", 0.0))

        total_river_length = _basin_river_length(river_cells, basin_id, cells_by_id, radius_km)
        area_km2 = max(0.0, float(watershed.get("area_km2", 0.0)))
        drainage_density = total_river_length / max(1.0, area_km2) * 1000.0
        hack_denominator = area_km2 ** HACK_EXPONENT if area_km2 > 0.0 else 0.0
        hack_coefficient = best_length / hack_denominator if hack_denominator > 0.0 and best_length > 0.0 else 0.0
        direct_length = 0.0
        if len(best_path) >= 2:
            first = cells_by_id.get(best_path[0])
            last = cells_by_id.get(best_path[-1])
            if first is not None and last is not None:
                direct_length = _great_circle_km(first, last, radius_km)
        sinuosity = best_length / max(1.0, direct_length) if best_length > 0.0 and direct_length > 0.0 else 1.0
        channel_drop = _path_drop(best_path, cells_by_id)
        channel_gradient = channel_drop / max(1.0, best_length * 1000.0)
        outlet_type = str(watershed.get("outlet_type", "unknown"))
        outlet_counts[outlet_type] = outlet_counts.get(outlet_type, 0) + 1

        diagnostics.append(
            {
                "watershed": watershed,
                "main_channel_length_km": best_length,
                "total_river_length_km": total_river_length,
                "hack_coefficient": hack_coefficient,
                "has_main_channel": best_length > 0.0 and len(best_path) >= 2,
            }
        )
        watershed["main_channel_cell_ids"] = best_path
        watershed["main_channel_source_cell_id"] = best_path[0] if best_path else -1
        watershed["main_channel_outlet_cell_id"] = best_path[-1] if best_path else int(watershed.get("outlet_cell_id", -1))
        watershed["main_channel_length_km"] = round(best_length, 6)
        watershed["main_channel_drop_m"] = round(channel_drop, 6)
        watershed["main_channel_gradient"] = round(channel_gradient, 8)
        watershed["main_channel_sinuosity_index"] = round(sinuosity, 6)
        watershed["total_river_length_km"] = round(total_river_length, 6)
        watershed["drainage_density_km_per_1000_km2"] = round(drainage_density, 6)
        watershed["hack_exponent"] = HACK_EXPONENT
        watershed["hack_coefficient"] = round(hack_coefficient, 6)

    active = [diagnostic for diagnostic in diagnostics if diagnostic["has_main_channel"]]
    fitted_hack_relation = fit_power_law(
        (
            (
                float(diagnostic["watershed"].get("area_km2", 0.0)),
                float(diagnostic["main_channel_length_km"]),
            )
            for diagnostic in active
            if float(diagnostic["watershed"].get("area_km2", 0.0))
            >= HACK_FIT_MINIMUM_BASIN_AREA_KM2
        ),
        fallback_exponent=HACK_EXPONENT,
    )
    fit_coefficient = (
        sum(float(diagnostic["hack_coefficient"]) for diagnostic in active) / len(active)
        if active
        else 0.0
    )
    residual_sum = 0.0
    residual_count = 0
    for diagnostic in diagnostics:
        watershed = diagnostic["watershed"]
        area_km2 = max(0.0, float(watershed.get("area_km2", 0.0)))
        expected_length = fit_coefficient * (area_km2 ** HACK_EXPONENT) if fit_coefficient > 0.0 and area_km2 > 0.0 else 0.0
        actual_length = float(diagnostic["main_channel_length_km"])
        residual = abs(actual_length - expected_length) / max(1.0, expected_length) if expected_length > 0.0 and actual_length > 0.0 else 0.0
        watershed["hack_expected_main_channel_length_km"] = round(expected_length, 6)
        watershed["hack_residual_fraction"] = round(residual, 6)
        if actual_length > 0.0 and expected_length > 0.0:
            residual_sum += residual
            residual_count += 1

    total_river_length = sum(float(diagnostic["total_river_length_km"]) for diagnostic in diagnostics)
    main_channel_count = len(active)
    main_channel_length_sum = sum(float(diagnostic["main_channel_length_km"]) for diagnostic in active)
    max_main_channel_length = max((float(diagnostic["main_channel_length_km"]) for diagnostic in active), default=0.0)
    drainage_density_sum = sum(float(watershed.get("drainage_density_km_per_1000_km2", 0.0)) for watershed in watersheds)
    hack_coefficient_sum = sum(float(diagnostic["hack_coefficient"]) for diagnostic in active)

    summary = world.setdefault("summary", {})
    summary["watershed_main_channel_count"] = main_channel_count
    summary["watershed_total_river_length_km"] = round(total_river_length, 6)
    summary["watershed_mean_main_channel_length_km"] = round(main_channel_length_sum / main_channel_count, 6) if main_channel_count else 0.0
    summary["watershed_max_main_channel_length_km"] = round(max_main_channel_length, 6)
    summary["watershed_mean_drainage_density_km_per_1000_km2"] = round(drainage_density_sum / len(watersheds), 6) if watersheds else 0.0
    summary["watershed_hack_exponent"] = HACK_EXPONENT
    summary["watershed_hack_fit_coefficient"] = round(fit_coefficient, 6)
    summary["watershed_mean_hack_coefficient"] = round(hack_coefficient_sum / main_channel_count, 6) if main_channel_count else 0.0
    summary["watershed_mean_abs_hack_residual_fraction"] = round(residual_sum / residual_count, 6) if residual_count else 0.0
    summary["watershed_hack_fitted_observation_count"] = fitted_hack_relation.observation_count
    summary["watershed_hack_fitted_minimum_basin_area_km2"] = HACK_FIT_MINIMUM_BASIN_AREA_KM2
    summary["watershed_hack_fitted_exponent"] = round(fitted_hack_relation.exponent, 6)
    summary["watershed_hack_fitted_coefficient"] = round(fitted_hack_relation.coefficient, 6)
    summary["watershed_hack_fitted_log_rmse"] = round(fitted_hack_relation.log_rmse, 6)
    summary["watershed_outlet_type_counts"] = dict(sorted(outlet_counts.items()))
    return world
