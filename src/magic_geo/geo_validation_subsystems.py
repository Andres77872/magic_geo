"""Structural validation for the broad natural-system enrichment pipeline.

This module intentionally has no dependency on :mod:`magic_geo.geo_validation`.
It can therefore be used by the main validator without creating an import
cycle, and it remains useful on its own when diagnosing an individual
enricher.  The checks focus on source links, record membership, count mirrors,
finite values, and bounded diagnostic indices.  Civilization layers are not
read or validated here.
"""

from __future__ import annotations

from collections import Counter
import math
from typing import Any, Callable

from .aquatic_climate_validation import validate_aquatic_climate_support
from .marine_distance_validation import validate_marine_distance
from .biological_resource_validation import validate_biological_resources
from .ore_resource_availability_validation import validate_ore_resource_availability
from .ore_genesis import _cell_indices as _replay_ore_cell_indices
from .reef_thermal_validation import validate_reef_thermal_habitat
from .species_habitat_validation import validate_species_habitat_support
from .wildfire_aquatic_validation import validate_wildfire_aquatic_exclusion
from .resource_dynamics import (
    AGRICULTURAL_RESOURCES,
    _accessibility as _replay_resource_accessibility,
    _confidence as _replay_resource_confidence,
    _extraction_hazard as _replay_resource_hazard,
    _reserve_potential as _replay_resource_reserve,
)


Check = dict[str, Any]
Record = dict[str, Any]


def _add(
    checks: list[Check],
    *,
    domain: str,
    name: str,
    passed: bool | None,
    message: str,
    severity: str = "error",
    observed: Any = None,
    expected: Any = None,
    evidence: dict[str, Any] | None = None,
) -> None:
    status = "not_applicable" if passed is None else ("passed" if passed else "failed")
    checks.append(
        {
            "id": len(checks),
            "domain": domain,
            "name": name,
            "status": status,
            "passed": passed is True,
            "severity": severity,
            "message": message,
            "observed": observed,
            "expected": expected,
            "evidence": evidence or {},
        }
    )


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _int(value: Any, default: int = -1) -> int:
    if _integer(value):
        return int(value)
    return default


def _number(value: Any, default: float = math.nan) -> float:
    if not _finite(value):
        return default
    return float(value)


def _close(first: Any, second: Any, *, absolute: float = 1.0e-4) -> bool:
    if not _finite(first) or not _finite(second):
        return False
    a = float(first)
    b = float(second)
    return math.isclose(a, b, rel_tol=5.0e-6, abs_tol=absolute)


def _tight_close(first: Any, second: Any, *, absolute: float = 2.0e-3) -> bool:
    if not _finite(first) or not _finite(second):
        return False
    return math.isclose(
        float(first), float(second), rel_tol=1.0e-10, abs_tol=absolute
    )


def _bounded(value: Any, lower: float = 0.0, upper: float = 1.0) -> bool:
    return _finite(value) and lower <= float(value) <= upper


def _nonnegative(value: Any) -> bool:
    return _finite(value) and float(value) >= 0.0


def _records(world: dict[str, Any], key: str) -> tuple[list[Record], bool]:
    payload = world.get(key)
    if not isinstance(payload, list):
        return [], False
    records = [record for record in payload if isinstance(record, dict)]
    return records, len(records) == len(payload)


def _dict_payload(world: dict[str, Any], key: str) -> tuple[Record, bool]:
    payload = world.get(key)
    return (payload, True) if isinstance(payload, dict) else ({}, False)


def _sequential_ids(records: list[Record]) -> bool:
    return all(_int(record.get("id")) == index for index, record in enumerate(records))


def _id_list(value: Any) -> tuple[list[int], bool]:
    if not isinstance(value, list):
        return [], False
    ids: list[int] = []
    for raw_id in value:
        if not _integer(raw_id):
            return [], False
        ids.append(int(raw_id))
    return ids, len(ids) == len(set(ids))


def _record_area(record: Record, cells_by_id: dict[int, Record]) -> float:
    ids, ok = _id_list(record.get("cell_ids"))
    if not ok or any(cell_id not in cells_by_id for cell_id in ids):
        return math.nan
    return sum(_number(cells_by_id[cell_id].get("area_km2"), 0.0) for cell_id in ids)


def _summary_matches(summary: Record, key: str, expected: Any) -> bool:
    observed = summary.get(key)
    if isinstance(expected, int) and not isinstance(expected, bool):
        return _integer(observed) and int(observed) == expected
    if isinstance(expected, float):
        return _close(observed, expected)
    return observed == expected


def _all_summary_mirrors(summary: Record, expected: dict[str, Any]) -> tuple[bool, list[str]]:
    mismatches = [key for key, value in expected.items() if not _summary_matches(summary, key, value)]
    return not mismatches, mismatches


def _cell_context(world: dict[str, Any]) -> tuple[list[Record], dict[int, Record], bool]:
    cells, shape_ok = _records(world, "cells")
    ids = [_int(cell.get("id")) for cell in cells]
    ids_ok = shape_ok and all(cell_id >= 0 for cell_id in ids) and len(ids) == len(set(ids))
    return cells, {cell_id: cell for cell_id, cell in zip(ids, cells) if cell_id >= 0}, ids_ok


def _adjacent(path: list[int], cells_by_id: dict[int, Record]) -> bool:
    for source_id, target_id in zip(path, path[1:]):
        source = cells_by_id.get(source_id)
        if source is None or target_id not in source.get("neighbors", []):
            return False
    return True


def _validate_ocean(
    checks: list[Check], world: dict[str, Any], cells: list[Record], cells_by_id: dict[int, Record], summary: Record
) -> None:
    domain = "ocean_circulation"
    systems, systems_shape = _records(world, "ocean_current_systems")
    edges, edges_shape = _records(world, "ocean_current_transport_edges")
    structure_ok = systems_shape and edges_shape and _sequential_ids(systems) and _sequential_ids(edges)
    _add(
        checks,
        domain=domain,
        name="record_structure",
        passed=structure_ok,
        message="Ocean-current systems and transport edges are typed records with stable IDs." if structure_ok else "Ocean-current system or transport-edge records are missing, malformed, or have unstable IDs.",
        observed={"system_count": len(systems), "edge_count": len(edges)},
        expected="list[object] with sequential ids",
    )

    system_ids = set(range(len(systems)))
    assigned: set[int] = set()
    membership_errors: list[str] = []
    for system in systems:
        system_id = _int(system.get("id"))
        cell_ids, unique = _id_list(system.get("cell_ids"))
        if not unique or not cell_ids or any(cell_id not in cells_by_id for cell_id in cell_ids):
            membership_errors.append(f"system {system_id}: invalid cell_ids")
            continue
        if assigned.intersection(cell_ids):
            membership_errors.append(f"system {system_id}: overlapping membership")
        assigned.update(cell_ids)
        if _int(system.get("cell_count")) != len(cell_ids):
            membership_errors.append(f"system {system_id}: cell_count")
        if not _close(system.get("area_km2"), _record_area(system, cells_by_id)):
            membership_errors.append(f"system {system_id}: area")
        for cell_id in cell_ids:
            cell = cells_by_id[cell_id]
            if _int(cell.get("ocean_current_system_id")) != system_id:
                membership_errors.append(f"system {system_id}: cell mirror {cell_id}")
            if str(cell.get("water_body_type", "land")) not in {"ocean", "continental_shelf", "inland_sea"}:
                membership_errors.append(f"system {system_id}: non-marine cell {cell_id}")
    expected_assigned = {
        _int(cell.get("id"))
        for cell in cells
        if _int(cell.get("ocean_current_system_id")) >= 0
    }
    if assigned != expected_assigned:
        membership_errors.append("system membership does not invert cell assignments")
    _add(
        checks,
        domain=domain,
        name="system_membership_and_aggregates",
        passed=not membership_errors,
        message="Ocean-current memberships, areas, and cell assignment mirrors agree." if not membership_errors else "Ocean-current membership or aggregate mismatches were found.",
        observed=membership_errors[:12],
        expected="exact non-overlapping cell/system inverse",
        evidence={"assigned_cell_count": len(assigned)},
    )

    edge_errors: list[str] = []
    for edge in edges:
        edge_id = _int(edge.get("id"))
        source_id = _int(edge.get("source_cell_id"))
        target_id = _int(edge.get("target_cell_id"))
        source = cells_by_id.get(source_id)
        target = cells_by_id.get(target_id)
        if source is None or target is None:
            edge_errors.append(f"edge {edge_id}: invalid endpoint")
            continue
        if target_id not in source.get("neighbors", []):
            edge_errors.append(f"edge {edge_id}: target is not adjacent")
        if _int(source.get("ocean_current_transport_target_cell_id")) != target_id:
            edge_errors.append(f"edge {edge_id}: source target mirror")
        if _int(edge.get("source_system_id")) != _int(source.get("ocean_current_system_id")):
            edge_errors.append(f"edge {edge_id}: source system")
        if _int(edge.get("target_system_id")) != _int(target.get("ocean_current_system_id")):
            edge_errors.append(f"edge {edge_id}: target system")
        if _int(edge.get("source_system_id")) not in system_ids or _int(edge.get("target_system_id")) not in system_ids:
            edge_errors.append(f"edge {edge_id}: unknown system")
        for field in ("alignment", "poleward_transport_index", "heat_transport_index"):
            if not _bounded(edge.get(field), -1.0, 1.0):
                edge_errors.append(f"edge {edge_id}: {field}")
        for field in ("current_speed_index", "great_circle_distance_km", "upwelling_index"):
            value = edge.get(field)
            if not _nonnegative(value) or (field == "upwelling_index" and float(value) > 1.0):
                edge_errors.append(f"edge {edge_id}: {field}")
    _add(
        checks,
        domain=domain,
        name="transport_source_links_and_ranges",
        passed=not edge_errors,
        message="Ocean-current transport edges link adjacent marine cells and bounded diagnostics." if not edge_errors else "Ocean-current transport links or diagnostic ranges are inconsistent.",
        observed=edge_errors[:12],
        expected="adjacent endpoints, mirrored targets, finite bounded indices",
    )

    cell_value_errors = []
    for cell in cells:
        for field, lower, upper in (
            ("ocean_current_speed_index", 0.0, math.inf),
            ("ocean_current_poleward_index", -1.0, 1.0),
            ("ocean_heat_transport_index", -1.0, 1.0),
            ("ocean_current_transport_alignment", -1.0, 1.0),
            ("ocean_current_convergence_index", -1.0, 1.0),
            ("ocean_upwelling_index", 0.0, 1.0),
        ):
            if not _bounded(cell.get(field), lower, upper):
                cell_value_errors.append(f"cell {_int(cell.get('id'))}: {field}")
    mirrors_ok, mirror_errors = _all_summary_mirrors(
        summary,
        {
            "ocean_current_system_count": len(systems),
            "ocean_current_transport_edge_count": len(edges),
            "ocean_current_cell_count": len(assigned),
            "ocean_current_total_transport_length_km": float(
                sum(
                    _number(edge.get("great_circle_distance_km"), 0.0)
                    for edge in edges
                )
            ),
        },
    )
    _add(
        checks,
        domain=domain,
        name="cell_values_and_summary_mirrors",
        passed=not cell_value_errors and mirrors_ok,
        message="Ocean-current cell diagnostics are finite and summary counts/totals mirror records." if not cell_value_errors and mirrors_ok else "Ocean-current cell values or summary mirrors are inconsistent.",
        observed={"cell_errors": cell_value_errors[:8], "summary_mismatches": mirror_errors},
        expected="finite bounded cells and exact count/length mirrors",
    )


def _validate_geometry_indices(
    checks: list[Check],
    world: dict[str, Any],
    cells: list[Record],
    cells_by_id: dict[int, Record],
    summary: Record,
) -> None:
    domain = "geometry_indices"
    lod, lod_shape = _dict_payload(world, "mesh_lod")
    tiles = lod.get("tiles")
    levels = lod.get("level_summaries")
    lod_errors: list[str] = []
    if (
        not lod_shape
        or not isinstance(tiles, list)
        or not all(isinstance(tile, dict) for tile in tiles)
        or not isinstance(levels, list)
        or not all(isinstance(level, dict) for level in levels)
    ):
        lod_errors.append("mesh_lod structure")
        tiles = []
        levels = []
    max_level = _int(lod.get("max_level"), -1)
    tile_by_key: dict[tuple[int, int], Record] = {}
    for tile in tiles:
        key = (_int(tile.get("level")), _int(tile.get("tile_id")))
        if min(key) < 0 or key in tile_by_key:
            lod_errors.append(f"duplicate/invalid tile {key}")
        tile_by_key[key] = tile
        if not _nonnegative(tile.get("area_km2")) or _int(tile.get("cell_count"), -1) < 1:
            lod_errors.append(f"tile {key}: area/count")
        if _int(tile.get("representative_cell_id")) not in cells_by_id:
            lod_errors.append(f"tile {key}: representative")
    memberships: Counter[tuple[int, int]] = Counter()
    areas: Counter[tuple[int, int]] = Counter()
    for cell in cells:
        raw_tile_ids = cell.get("mesh_lod_tile_ids")
        tile_ids = (
            [int(tile_id) for tile_id in raw_tile_ids]
            if isinstance(raw_tile_ids, list)
            and all(_integer(tile_id) for tile_id in raw_tile_ids)
            else []
        )
        codes = cell.get("mesh_lod_codes")
        if (
            len(tile_ids) != max_level + 1
            or not isinstance(codes, list)
            or len(codes) != len(tile_ids)
            or not all(isinstance(code, str) and code for code in codes)
        ):
            lod_errors.append(f"cell {_int(cell.get('id'))}: LOD ancestry")
            continue
        if _int(cell.get("mesh_lod_finest_tile_id")) != tile_ids[-1]:
            lod_errors.append(f"cell {_int(cell.get('id'))}: finest tile")
        for level, tile_id in enumerate(tile_ids):
            key = (level, tile_id)
            memberships[key] += 1
            areas[key] += _number(cell.get("area_km2"), 0.0)
            if key not in tile_by_key:
                lod_errors.append(f"cell {_int(cell.get('id'))}: unknown tile {key}")
    for key, tile in tile_by_key.items():
        if _int(tile.get("cell_count")) != memberships[key] or not _close(tile.get("area_km2"), areas[key]):
            lod_errors.append(f"tile {key}: membership aggregate")
    if len(levels) != max_level + 1:
        lod_errors.append("level summary coverage")
    for level, level_record in enumerate(levels):
        level_tiles = [tile for (tile_level, _), tile in tile_by_key.items() if tile_level == level]
        if (
            _int(level_record.get("level")) != level
            or _int(level_record.get("occupied_tile_count")) != len(level_tiles)
            or _int(level_record.get("cell_count")) != len(cells)
        ):
            lod_errors.append(f"level {level}: summary")
    lod_mirror_ok, lod_mirror_errors = _all_summary_mirrors(
        summary,
        {
            "mesh_lod_index": lod.get("index"),
            "mesh_lod_max_level": max_level,
            "mesh_lod_level_count": len(levels),
            "mesh_lod_tile_count": len(tiles),
        },
    )
    _add(
        checks,
        domain=domain,
        name="mesh_lod_membership_and_summaries",
        passed=not lod_errors and lod_mirror_ok,
        message="Mesh LOD tiles exactly aggregate cell ancestry at every level." if not lod_errors and lod_mirror_ok else "Mesh LOD cell ancestry, tile aggregates, or summary mirrors are inconsistent.",
        observed={"errors": lod_errors[:16], "summary_mismatches": lod_mirror_errors},
        expected="complete per-level cell coverage and exact tile aggregates",
    )

    spatial, spatial_shape = _dict_payload(world, "spherical_spatial_index")
    pixels = spatial.get("healpix_like_pixels")
    s2_records = spatial.get("s2_like_cells")
    spatial_errors: list[str] = []
    if (
        not spatial_shape
        or not isinstance(pixels, list)
        or not all(isinstance(record, dict) for record in pixels)
        or not isinstance(s2_records, list)
        or not all(isinstance(record, dict) for record in s2_records)
    ):
        spatial_errors.append("spatial index structure")
        pixels = []
        s2_records = []
    pixel_by_id = {_int(record.get("pixel_id")): record for record in pixels}
    s2_by_id = {_int(record.get("cell_id")): record for record in s2_records}
    if len(pixel_by_id) != len(pixels) or len(s2_by_id) != len(s2_records):
        spatial_errors.append("duplicate occupied spatial IDs")
    pixel_members: Counter[int] = Counter()
    pixel_areas: Counter[int] = Counter()
    s2_members: Counter[int] = Counter()
    s2_areas: Counter[int] = Counter()
    for cell in cells:
        cell_id = _int(cell.get("id"))
        pixel_id = _int(cell.get("healpix_like_pixel_id"))
        s2_id = _int(cell.get("s2_like_cell_id"))
        if pixel_id not in pixel_by_id or s2_id not in s2_by_id:
            spatial_errors.append(f"cell {cell_id}: unknown spatial bucket")
            continue
        if _int(cell.get("healpix_like_nside")) != _int(spatial.get("healpix_like_nside")) or _int(cell.get("s2_like_cell_level")) != _int(spatial.get("s2_like_level")):
            spatial_errors.append(f"cell {cell_id}: index resolution mirror")
        pixel_members[pixel_id] += 1
        pixel_areas[pixel_id] += _number(cell.get("area_km2"), 0.0)
        s2_members[s2_id] += 1
        s2_areas[s2_id] += _number(cell.get("area_km2"), 0.0)
    for record_id, record in pixel_by_id.items():
        if _int(record.get("cell_count")) != pixel_members[record_id] or not _close(record.get("area_km2"), pixel_areas[record_id]):
            spatial_errors.append(f"HEALPix-like bucket {record_id}: aggregate")
    for record_id, record in s2_by_id.items():
        if _int(record.get("cell_count")) != s2_members[record_id] or not _close(record.get("area_km2"), s2_areas[record_id]):
            spatial_errors.append(f"S2-like bucket {record_id}: aggregate")
    spatial_mirror_ok, spatial_mirror_errors = _all_summary_mirrors(
        summary,
        {
            "spherical_spatial_index": spatial.get("index"),
            "healpix_like_occupied_pixel_count": len(pixels),
            "s2_like_occupied_cell_count": len(s2_records),
            "s2_like_cell_level": _int(spatial.get("s2_like_level")),
        },
    )
    _add(
        checks,
        domain=domain,
        name="spherical_index_membership_and_summaries",
        passed=not spatial_errors and spatial_mirror_ok,
        message="HEALPix-like and S2-like records exactly aggregate all generated cells." if not spatial_errors and spatial_mirror_ok else "Spherical index assignments, aggregates, or summary mirrors are inconsistent.",
        observed={"errors": spatial_errors[:16], "summary_mismatches": spatial_mirror_errors},
        expected="exact occupied-bucket membership for both index views",
    )


def _validate_seasonal_climate(
    checks: list[Check],
    world: dict[str, Any],
    cells: list[Record],
    cells_by_id: dict[int, Record],
    summary: Record,
) -> None:
    domain = "seasonal_climate"
    histories, histories_shape = _records(world, "climate_seasonal_histories")
    errors: list[str] = []
    if not histories_shape or not _sequential_ids(histories):
        errors.append("seasonal history structure/IDs")
    grouped_cells: Counter[str] = Counter(str(cell.get("atmospheric_cell", "unknown")) for cell in cells)
    observed_groups: set[str] = set()
    totals = Counter()
    for history in histories:
        history_id = _int(history.get("id"))
        atmospheric_cell = str(history.get("atmospheric_cell", ""))
        steps = history.get("steps")
        if atmospheric_cell in observed_groups or atmospheric_cell not in grouped_cells:
            errors.append(f"history {history_id}: atmospheric group")
        observed_groups.add(atmospheric_cell)
        if _int(history.get("cell_count")) != grouped_cells[atmospheric_cell]:
            errors.append(f"history {history_id}: cell_count")
        if not isinstance(steps, list) or len(steps) != 12 or not all(isinstance(step, dict) for step in steps) or _int(history.get("time_step_count")) != 12:
            errors.append(f"history {history_id}: monthly steps")
            continue
        if [_int(step.get("month")) for step in steps] != list(range(1, 13)):
            errors.append(f"history {history_id}: month sequence")
        previous_storage: float | None = None
        for index, step in enumerate(steps):
            start_storage = _number(step.get("start_humidity_storage_mm"))
            end_storage = _number(step.get("end_humidity_storage_mm"))
            if not math.isfinite(start_storage) or not math.isfinite(end_storage) or min(start_storage, end_storage) < 0.0:
                errors.append(f"history {history_id}: humidity storage {index}")
            if previous_storage is not None and not _close(start_storage, previous_storage, absolute=2.0e-3):
                errors.append(f"history {history_id}: storage continuity {index}")
            previous_storage = end_storage
            for field in ("precipitation_mm", "evaporation_mm", "moisture_convergence_mm", "humidity_export_mm", "vapor_deficit_mm"):
                if not _nonnegative(step.get(field)):
                    errors.append(f"history {history_id}: {field} {index}")
            if not _bounded(step.get("drying_risk")):
                errors.append(f"history {history_id}: drying_risk {index}")
        aggregate_fields = {
            "annual_precipitation_mm": "precipitation_mm",
            "annual_evaporation_mm": "evaporation_mm",
            "annual_moisture_convergence_mm": "moisture_convergence_mm",
            "annual_humidity_export_mm": "humidity_export_mm",
            "annual_vapor_deficit_mm": "vapor_deficit_mm",
        }
        for aggregate, step_field in aggregate_fields.items():
            total = sum(_number(step.get(step_field), 0.0) for step in steps)
            totals[aggregate] += total
            if not _close(history.get(aggregate), total, absolute=2.0e-3):
                errors.append(f"history {history_id}: {aggregate}")
        for field in ("monsoon_index", "max_drying_risk"):
            if not _bounded(history.get(field)):
                errors.append(f"history {history_id}: {field}")
    if observed_groups != set(grouped_cells):
        errors.append("seasonal atmospheric group coverage")
    mirror_ok, mirror_errors = _all_summary_mirrors(
        summary,
        {
            "climate_seasonal_history_count": len(histories),
            "climate_seasonal_step_count": sum(len(history.get("steps", [])) for history in histories if isinstance(history.get("steps"), list)),
            "climate_seasonal_total_precipitation_mm": totals["annual_precipitation_mm"],
            "climate_seasonal_total_evaporation_mm": totals["annual_evaporation_mm"],
        },
    )
    _add(
        checks,
        domain=domain,
        name="seasonal_history_grouping_and_aggregates",
        passed=not errors and mirror_ok,
        message="Seasonal histories cover each atmospheric cell with continuous monthly records and exact totals." if not errors and mirror_ok else "Seasonal climate grouping, monthly records, aggregates, or summary mirrors are inconsistent.",
        observed={"errors": errors[:18], "summary_mismatches": mirror_errors},
        expected="one 12-month history per atmospheric-cell group",
    )

    classification, classification_shape = _dict_payload(world, "climate_classification")
    legend = classification.get("legend")
    class_errors: list[str] = []
    if (
        not classification_shape
        or not isinstance(legend, list)
        or not legend
        or not all(
            isinstance(entry, dict)
            and isinstance(entry.get("code"), str)
            and isinstance(entry.get("name"), str)
            for entry in legend
        )
    ):
        class_errors.append("classification metadata/legend")
        legend = []
    legend_codes = {
        str(entry.get("code")) for entry in legend if isinstance(entry, dict)
    }
    generated_classes = {str(cell.get("climate_class", "")) for cell in cells}
    if any(
        not climate_class or climate_class not in legend_codes
        for climate_class in generated_classes
    ):
        class_errors.append("cell class absent from legend")
    if _int(classification.get("classified_cell_count")) != len(cells) or _int(classification.get("generated_class_count")) != len(generated_classes) or _int(classification.get("available_class_count")) != len(legend):
        class_errors.append("classification counts")
    class_counts = dict(sorted(Counter(str(cell.get("climate_class", "")) for cell in cells).items()))
    if summary.get("climate_class_counts") != class_counts or not _summary_matches(summary, "climate_class_count", len(class_counts)):
        class_errors.append("classification summary mirrors")

    if "climate_continentality_model" in world or validate_marine_distance(world):
        region_errors = validate_marine_distance(world)
    else:
        regions, regions_shape = _records(world, "climate_continentality_regions")
        region_errors: list[str] = []
        if not regions_shape or not _sequential_ids(regions):
            region_errors.append("continentality region structure/IDs")
        assigned: set[int] = set()
        for region in regions:
            region_id = _int(region.get("id"))
            cell_ids, unique = _id_list(region.get("cell_ids"))
            if not unique or not cell_ids or any(cell_id not in cells_by_id for cell_id in cell_ids):
                region_errors.append(f"region {region_id}: cells")
                continue
            if assigned.intersection(cell_ids):
                region_errors.append(f"region {region_id}: overlap")
            assigned.update(cell_ids)
            if _int(region.get("cell_count")) != len(cell_ids) or not _close(region.get("area_km2"), _record_area(region, cells_by_id)):
                region_errors.append(f"region {region_id}: count/area")
            for cell_id in cell_ids:
                if _int(cells_by_id[cell_id].get("climate_continentality_region_id")) != region_id:
                    region_errors.append(f"region {region_id}: cell mirror {cell_id}")
            for field in ("mean_continentality_index", "mean_oceanic_humidity_availability_index"):
                if not _bounded(region.get(field)):
                    region_errors.append(f"region {region_id}: {field}")
            for field in ("mean_distance_to_marine_water_km", "mean_precipitation_mm_y", "mean_temperature_range_c"):
                if not _nonnegative(region.get(field)):
                    region_errors.append(f"region {region_id}: {field}")
        if assigned != {_int(cell.get("id")) for cell in cells if _int(cell.get("climate_continentality_region_id")) >= 0}:
            region_errors.append("continentality assignment inverse")
        if not _summary_matches(summary, "climate_continentality_region_count", len(regions)):
            region_errors.append("continentality summary count")
    _add(
        checks,
        domain=domain,
        name="classification_and_continentality_sources",
        passed=not class_errors and not region_errors,
        message="Climate classes use the declared legend and continentality regions exactly mirror cells." if not class_errors and not region_errors else "Climate classification or continentality sources, assignments, ranges, or summaries are inconsistent.",
        observed={"classification_errors": class_errors, "region_errors": region_errors[:16]},
        expected="legend-backed classes and exact continentality region inverse",
    )


def _validate_tectonics(
    checks: list[Check], world: dict[str, Any], cells: list[Record], cells_by_id: dict[int, Record], summary: Record
) -> None:
    domain = "tectonic_zones_faults"
    group_keys = {"collision": "collision_zones", "subduction": "subduction_zones", "rift": "rift_zones"}
    groups: dict[str, list[Record]] = {}
    shape_ok = True
    for zone_type, key in group_keys.items():
        group, group_shape = _records(world, key)
        groups[zone_type] = group
        shape_ok = shape_ok and group_shape and _sequential_ids(group)
    combined, combined_shape = _records(world, "tectonic_zones")
    combined_ok = combined_shape and _sequential_ids(combined)
    expected_keys = {
        (zone_type, _int(record.get("id"))): set(_id_list(record.get("cell_ids"))[0])
        for zone_type, group in groups.items()
        for record in group
    }
    observed_keys = {
        (str(record.get("zone_type", "")), _int(record.get("local_zone_id"))): set(_id_list(record.get("cell_ids"))[0])
        for record in combined
    }
    combined_ok = combined_ok and observed_keys == expected_keys
    _add(
        checks,
        domain=domain,
        name="zone_registry_structure",
        passed=shape_ok and combined_ok,
        message="Typed zone registries and the combined tectonic-zone registry agree." if shape_ok and combined_ok else "Tectonic zone registries are malformed or disagree with the combined registry.",
        observed={key: len(groups[zone_type]) for zone_type, key in group_keys.items()} | {"combined": len(combined)},
        expected="sequential local/global IDs and exact combined registry",
    )

    edge_records, edge_shape = _records(world, "cell_adjacency_edges")
    edge_ids = {_int(edge.get("id")) for edge in edge_records}
    plate_records, plate_shape = _records(world, "plates")
    plate_ids = {_int(plate.get("id")) for plate in plate_records}
    zone_errors: list[str] = []
    for zone_type, group in groups.items():
        cell_field = f"{zone_type}_zone_id"
        for zone in group:
            zone_id = _int(zone.get("id"))
            cell_ids, unique = _id_list(zone.get("cell_ids"))
            boundary_ids, boundary_unique = _id_list(zone.get("boundary_edge_ids"))
            if not unique or not cell_ids or any(cell_id not in cells_by_id for cell_id in cell_ids):
                zone_errors.append(f"{zone_type} {zone_id}: cell_ids")
                continue
            if not boundary_unique or any(edge_id not in edge_ids for edge_id in boundary_ids):
                zone_errors.append(f"{zone_type} {zone_id}: boundary_edge_ids")
            if _int(zone.get("cell_count")) != len(cell_ids) or _int(zone.get("boundary_edge_count")) != len(boundary_ids):
                zone_errors.append(f"{zone_type} {zone_id}: counts")
            if not _close(zone.get("area_km2"), _record_area(zone, cells_by_id)):
                zone_errors.append(f"{zone_type} {zone_id}: area")
            if _int(zone.get("representative_cell_id")) not in cell_ids:
                zone_errors.append(f"{zone_type} {zone_id}: representative")
            raw_plate_ids, plate_unique = _id_list(zone.get("plate_ids"))
            if not plate_unique or any(plate_id not in plate_ids for plate_id in raw_plate_ids):
                zone_errors.append(f"{zone_type} {zone_id}: plates")
            for cell_id in cell_ids:
                if _int(cells_by_id[cell_id].get(cell_field)) != zone_id:
                    zone_errors.append(f"{zone_type} {zone_id}: cell mirror {cell_id}")
            for field in ("mean_zone_strength", "max_zone_strength", "mean_boundary_convergent", "mean_boundary_divergent", "mean_boundary_transform"):
                if not _bounded(zone.get(field)):
                    zone_errors.append(f"{zone_type} {zone_id}: {field}")
    _add(
        checks,
        domain=domain,
        name="zone_membership_sources_and_ranges",
        passed=edge_shape and plate_shape and not zone_errors,
        message="Tectonic zones link valid cells, plates, boundary edges, and bounded strengths." if edge_shape and plate_shape and not zone_errors else "Tectonic zone membership, source links, or values are inconsistent.",
        observed=zone_errors[:15],
        expected="valid cell/plate/edge sources and exact cell mirrors",
    )

    faults, faults_shape = _records(world, "fault_systems")
    fault_errors: list[str] = []
    assigned: set[int] = set()
    if faults_shape and not _sequential_ids(faults):
        fault_errors.append("fault IDs are not sequential")
    for fault in faults:
        fault_id = _int(fault.get("id"))
        cell_ids, unique = _id_list(fault.get("cell_ids"))
        boundary_ids, boundary_unique = _id_list(fault.get("boundary_edge_ids"))
        if not unique or any(cell_id not in cells_by_id for cell_id in cell_ids):
            fault_errors.append(f"fault {fault_id}: cell_ids")
            continue
        if assigned.intersection(cell_ids):
            fault_errors.append(f"fault {fault_id}: overlapping cells")
        assigned.update(cell_ids)
        if not boundary_unique or any(edge_id not in edge_ids for edge_id in boundary_ids):
            fault_errors.append(f"fault {fault_id}: boundary edges")
        if _int(fault.get("cell_count")) != len(cell_ids) or _int(fault.get("boundary_edge_count")) != len(boundary_ids):
            fault_errors.append(f"fault {fault_id}: counts")
        if not _close(fault.get("area_km2"), _record_area(fault, cells_by_id)):
            fault_errors.append(f"fault {fault_id}: area")
        for cell_id in cell_ids:
            if _int(cells_by_id[cell_id].get("fault_system_id")) != fault_id:
                fault_errors.append(f"fault {fault_id}: cell mirror {cell_id}")
        for field in ("mean_fault_slip_rate_index", "max_fault_slip_rate_index", "mean_seismic_hazard_index", "max_seismic_hazard_index"):
            if not _bounded(fault.get(field)):
                fault_errors.append(f"fault {fault_id}: {field}")
        if not _nonnegative(fault.get("mean_earthquake_recurrence_interval_y")):
            fault_errors.append(f"fault {fault_id}: recurrence")
    expected_assigned = {_int(cell.get("id")) for cell in cells if _int(cell.get("fault_system_id")) >= 0}
    if assigned != expected_assigned:
        fault_errors.append("fault membership does not invert cell assignments")
    mirror_ok, mirror_errors = _all_summary_mirrors(
        summary,
        {
            "tectonic_zone_count": len(combined),
            "collision_zone_count": len(groups["collision"]),
            "subduction_zone_count": len(groups["subduction"]),
            "rift_zone_count": len(groups["rift"]),
            "fault_system_count": len(faults),
            "fault_system_cell_count": len(assigned),
        },
    )
    _add(
        checks,
        domain=domain,
        name="fault_system_membership_and_summary",
        passed=faults_shape and not fault_errors and mirror_ok,
        message="Fault-system memberships, hazards, and tectonic summary counts agree." if faults_shape and not fault_errors and mirror_ok else "Fault-system records or tectonic summary mirrors are inconsistent.",
        observed={"fault_errors": fault_errors[:12], "summary_mismatches": mirror_errors},
        expected="exact fault assignment inverse and summary mirrors",
    )


def _validate_surface_geography(
    checks: list[Check],
    world: dict[str, Any],
    cells: list[Record],
    cells_by_id: dict[int, Record],
    summary: Record,
) -> None:
    domain = "coastal_marine_landmass"
    partitions = (
        (
            "landmass",
            "landmasses",
            "landmass_id",
            lambda cell: not bool(cell.get("is_water", False)),
            "landmass_count",
        ),
        (
            "marine_region",
            "marine_regions",
            "marine_region_id",
            lambda cell: str(cell.get("water_body_type", "land"))
            in {"ocean", "continental_shelf", "inland_sea"},
            "marine_region_count",
        ),
        (
            "continental_shelf",
            "continental_shelves",
            "continental_shelf_id",
            lambda cell: str(cell.get("water_body_type", "land"))
            == "continental_shelf",
            "continental_shelf_count",
        ),
    )
    errors: list[str] = []
    partition_counts: dict[str, int] = {}
    record_sets: dict[str, list[Record]] = {}
    for label, key, cell_field, eligible, summary_key in partitions:
        records, shape_ok = _records(world, key)
        record_sets[key] = records
        partition_counts[label] = len(records)
        if not shape_ok or not _sequential_ids(records):
            errors.append(f"{label}: structure/IDs")
        assigned: set[int] = set()
        for record in records:
            record_id = _int(record.get("id"))
            cell_ids, unique = _id_list(record.get("cell_ids"))
            if (
                not unique
                or not cell_ids
                or any(cell_id not in cells_by_id for cell_id in cell_ids)
            ):
                errors.append(f"{label} {record_id}: cell_ids")
                continue
            if assigned.intersection(cell_ids):
                errors.append(f"{label} {record_id}: overlap")
            assigned.update(cell_ids)
            if (
                _int(record.get("cell_count")) != len(cell_ids)
                or not _close(
                    record.get("area_km2"), _record_area(record, cells_by_id)
                )
            ):
                errors.append(f"{label} {record_id}: count/area")
            for cell_id in cell_ids:
                cell = cells_by_id[cell_id]
                if _int(cell.get(cell_field)) != record_id or not eligible(cell):
                    errors.append(f"{label} {record_id}: cell mirror {cell_id}")
            for field in ("centroid_lat_deg", "centroid_lon_deg"):
                if not _finite(record.get(field)):
                    errors.append(f"{label} {record_id}: {field}")
        expected = {
            _int(cell.get("id"))
            for cell in cells
            if _int(cell.get(cell_field)) >= 0
        }
        if assigned != expected:
            errors.append(f"{label}: assignment inverse")
        if not _summary_matches(summary, summary_key, len(records)):
            errors.append(f"{label}: summary count")
    _add(
        checks,
        domain=domain,
        name="land_marine_shelf_partitions",
        passed=not errors,
        message="Landmasses, marine regions, and shelves exactly partition their cell assignments." if not errors else "Landmass, marine-region, or shelf memberships, aggregates, or summaries are inconsistent.",
        observed={"errors": errors[:18], "record_counts": partition_counts},
        expected="non-overlapping exact cell assignment inverses",
    )

    landmass_ids = set(range(len(record_sets.get("landmasses", []))))
    marine_ids = set(range(len(record_sets.get("marine_regions", []))))
    features, feature_shape = _records(world, "coastal_features")
    chokepoints, chokepoint_shape = _records(world, "marine_chokepoints")
    feature_errors: list[str] = []
    for label, records, shape_ok in (
        ("coastal_feature", features, feature_shape),
        ("marine_chokepoint", chokepoints, chokepoint_shape),
    ):
        if not shape_ok or not _sequential_ids(records):
            feature_errors.append(f"{label}: structure/IDs")
        seen_cells: set[int] = set()
        for record in records:
            record_id = _int(record.get("id"))
            cell_id = _int(record.get("cell_id"))
            if cell_id not in cells_by_id or cell_id in seen_cells:
                feature_errors.append(f"{label} {record_id}: cell source/duplicate")
                continue
            seen_cells.add(cell_id)
            if not _finite(record.get("lat_deg")) or not _finite(
                record.get("lon_deg")
            ):
                feature_errors.append(f"{label} {record_id}: coordinates")
            if label == "coastal_feature":
                for field in (
                    "wave_energy_index",
                    "sediment_supply_index",
                    "longshore_transport_index",
                    "progradation_index",
                ):
                    if not _bounded(record.get(field)):
                        feature_errors.append(f"feature {record_id}: {field}")
                if not _nonnegative(record.get("length_km")) or not _finite(
                    record.get("migration_rate_m_y")
                ):
                    feature_errors.append(f"feature {record_id}: length/migration")
            else:
                if _int(record.get("marine_region_id")) not in marine_ids:
                    feature_errors.append(f"chokepoint {record_id}: marine region")
                linked_land, unique = _id_list(record.get("adjacent_landmass_ids"))
                if not unique or any(
                    landmass_id not in landmass_ids for landmass_id in linked_land
                ):
                    feature_errors.append(f"chokepoint {record_id}: landmasses")
                if not _bounded(record.get("constriction_index")) or not _nonnegative(
                    record.get("width_proxy_km")
                ):
                    feature_errors.append(f"chokepoint {record_id}: geometry")
    if not _summary_matches(summary, "marine_chokepoint_count", len(chokepoints)):
        feature_errors.append("chokepoint summary count")
    _add(
        checks,
        domain=domain,
        name="coastal_feature_and_chokepoint_sources",
        passed=not feature_errors,
        message="Coastal features and marine chokepoints link unique valid cells and natural regions." if not feature_errors else "Coastal-feature or chokepoint source links, values, or summaries are inconsistent.",
        observed=feature_errors[:18],
        expected="unique cell-linked records with valid land/marine sources",
    )


def _validate_soils_ecotones(
    checks: list[Check],
    world: dict[str, Any],
    cells: list[Record],
    cells_by_id: dict[int, Record],
    summary: Record,
) -> None:
    domain = "soils_and_ecotones"
    profiles, profile_shape = _records(world, "soil_profiles")
    horizons, horizon_shape = _records(world, "soil_horizons")
    histories, history_shape = _records(world, "soil_profile_histories")
    pedogenesis_model, pedogenesis_model_shape = _dict_payload(
        world, "soil_pedogenesis_model"
    )
    geo_only = world.get("generation_scope") == "geo_only"
    feedback = world.get("earth_system_feedback_history", [])
    expected_natural_stages = (
        feedback
        if geo_only
        and isinstance(feedback, list)
        and all(isinstance(step, dict) for step in feedback)
        else []
    )
    errors: list[str] = []
    if (
        not profile_shape
        or not horizon_shape
        or not history_shape
        or not _sequential_ids(profiles)
        or not _sequential_ids(horizons)
        or not _sequential_ids(histories)
    ):
        errors.append("soil profile/horizon/history structure or IDs")
    if (
        not pedogenesis_model_shape
        or pedogenesis_model.get("model_type")
        != "posthoc_final_state_profile_reconstruction_v2"
        or pedogenesis_model.get("physical_time_resolved") is not False
        or pedogenesis_model.get("state_mutation_evidence") is not False
    ):
        errors.append("soil pedogenesis temporal model metadata")
    if geo_only and (
        not expected_natural_stages
        or pedogenesis_model.get("time_basis") != "natural_simulation_stage"
        or pedogenesis_model.get("stage_source")
        != "earth_system_feedback_history"
        or _int(pedogenesis_model.get("stage_count"))
        != len(expected_natural_stages)
        or pedogenesis_model.get("natural_stage_flux_partition")
        != "normalized_across_nominally_advancing_erosion_intervals"
        or pedogenesis_model.get("linked_nominal_time_coordinate_available")
        is not True
        or pedogenesis_model.get("nominal_time_calibrated") is not False
    ):
        errors.append("geo-only soil history must use the natural stage ledger")
    horizon_by_id = {_int(horizon.get("id")): horizon for horizon in horizons}
    history_by_id = {_int(history.get("id")): history for history in histories}
    assigned_cells: set[int] = set()
    used_horizons: set[int] = set()
    used_histories: set[int] = set()
    for profile in profiles:
        profile_id = _int(profile.get("id"))
        cell_id = _int(profile.get("cell_id"))
        horizon_ids, unique = _id_list(profile.get("horizon_ids"))
        history_id = _int(profile.get("soil_profile_history_id"))
        if cell_id not in cells_by_id or cell_id in assigned_cells:
            errors.append(f"profile {profile_id}: cell source/duplicate")
            continue
        assigned_cells.add(cell_id)
        cell = cells_by_id[cell_id]
        if _int(cell.get("soil_profile_id")) != profile_id:
            errors.append(f"profile {profile_id}: cell mirror")
        if (
            not unique
            or _int(profile.get("horizon_count")) != len(horizon_ids)
            or any(horizon_id not in horizon_by_id for horizon_id in horizon_ids)
        ):
            errors.append(f"profile {profile_id}: horizon sources")
            continue
        used_horizons.update(horizon_ids)
        previous_bottom = 0.0
        thickness_sum = 0.0
        for sequence_index, horizon_id in enumerate(horizon_ids):
            horizon = horizon_by_id[horizon_id]
            top = _number(horizon.get("top_depth_m"))
            bottom = _number(horizon.get("bottom_depth_m"))
            thickness = _number(horizon.get("thickness_m"))
            if (
                _int(horizon.get("soil_profile_id")) != profile_id
                or _int(horizon.get("cell_id")) != cell_id
                or _int(horizon.get("sequence_index")) != sequence_index
            ):
                errors.append(f"profile {profile_id}: horizon mirror {horizon_id}")
            if (
                not all(math.isfinite(value) for value in (top, bottom, thickness))
                or min(top, bottom, thickness) < 0.0
                or not _close(top, previous_bottom)
                or not _close(bottom - top, thickness)
            ):
                errors.append(f"profile {profile_id}: horizon depths {horizon_id}")
            fractions = [
                _number(horizon.get(field))
                for field in ("sand_fraction", "silt_fraction", "clay_fraction")
            ]
            if not all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in fractions) or not _close(sum(fractions), 1.0):
                errors.append(f"profile {profile_id}: texture fractions {horizon_id}")
            for field in (
                "organic_matter_fraction",
                "salinity_index",
                "root_density_index",
                "weathering_index",
                "carbonate_index",
            ):
                if not _bounded(horizon.get(field)):
                    errors.append(f"profile {profile_id}: {field} {horizon_id}")
            previous_bottom = bottom
            thickness_sum += thickness
        if not _close(profile.get("total_depth_m"), thickness_sum):
            errors.append(f"profile {profile_id}: total depth")
        for field in (
            "moisture_index",
            "drainage_index",
            "organic_matter_fraction",
            "salinity_index",
            "erodibility_index",
            "development_index",
            "weathering_index",
            "leaching_index",
            "bioturbation_index",
        ):
            if not _bounded(profile.get(field)):
                errors.append(f"profile {profile_id}: {field}")
        history = history_by_id.get(history_id)
        if history is None or history_id in used_histories:
            errors.append(f"profile {profile_id}: history source/duplicate")
            continue
        used_histories.add(history_id)
        steps = history.get("steps")
        if (
            _int(history.get("soil_profile_id")) != profile_id
            or _int(history.get("cell_id")) != cell_id
            or not isinstance(steps, list)
            or not all(isinstance(step, dict) for step in steps)
            or _int(history.get("step_count")) != len(steps)
        ):
            errors.append(f"profile {profile_id}: history mirror/steps")
            continue
        if geo_only and len(steps) != len(expected_natural_stages):
            errors.append(f"profile {profile_id}: natural stage coverage")
        previous_depth: float | None = None
        step_production_sum = 0.0
        step_erosion_sum = 0.0
        step_values: dict[str, list[float]] = {
            "weathering_index": [],
            "leaching_index": [],
            "bioturbation_index": [],
            "horizon_differentiation_index": [],
            "pedogenic_flux_index": [],
        }
        for step_index, step in enumerate(steps):
            source_duration = math.nan
            start = _number(step.get("start_depth_m"))
            end = _number(step.get("end_depth_m"))
            production = _number(step.get("soil_production_m"))
            erosion_loss = _number(step.get("erosion_loss_m"))
            if not math.isfinite(start) or not math.isfinite(end) or min(start, end) < 0.0:
                errors.append(f"profile {profile_id}: history depths {step_index}")
            if (
                _int(step.get("stage_index")) != step_index + 1
                or not math.isfinite(production)
                or not math.isfinite(erosion_loss)
                or min(production, erosion_loss) < 0.0
                or not _close(
                    production,
                    max(0.0, end - start + erosion_loss),
                    absolute=3.0e-5,
                )
            ):
                errors.append(
                    f"profile {profile_id}: production/erosion {step_index}"
                )
            if math.isfinite(production):
                step_production_sum += production
            if math.isfinite(erosion_loss):
                step_erosion_sum += erosion_loss
            if previous_depth is not None and not _close(start, previous_depth):
                errors.append(f"profile {profile_id}: history continuity {step_index}")
            previous_depth = end
            if geo_only:
                source_stage = (
                    expected_natural_stages[step_index]
                    if step_index < len(expected_natural_stages)
                    else {}
                )
                if (
                    step.get("time_basis") != "natural_simulation_stage"
                    or step.get("physical_time_resolved") is not False
                    or step.get("start_year_bp") is not None
                    or step.get("end_year_bp") is not None
                    or _int(step.get("natural_stage_id"))
                    != _int(source_stage.get("id"))
                    or str(step.get("natural_stage_name", ""))
                    != str(source_stage.get("stage", ""))
                    or _int(step.get("start_model_step")) != step_index
                    or _int(step.get("end_model_step")) != step_index + 1
                    or step.get("nominal_time_link_available") is not True
                    or step.get("nominal_time_calibrated") is not False
                    or step.get("nominal_time_basis")
                    != source_stage.get("nominal_time_basis")
                    or step.get("nominal_time_source_parameter")
                    != source_stage.get("nominal_time_source_parameter")
                    or not _close(
                        step.get("nominal_interval_start_ma"),
                        source_stage.get("nominal_interval_start_ma"),
                    )
                    or not _close(
                        step.get("nominal_interval_end_ma"),
                        source_stage.get("nominal_interval_end_ma"),
                    )
                    or not _close(
                        step.get("nominal_interval_duration_ma"),
                        source_stage.get("nominal_interval_duration_ma"),
                    )
                ):
                    errors.append(
                        f"profile {profile_id}: natural time provenance {step_index}"
                    )
                source_duration = _number(
                    source_stage.get("nominal_interval_duration_ma")
                )
                if source_duration == 0.0 and (
                    not _close(start, end)
                    or not _close(production, 0.0, absolute=1.0e-9)
                    or not _close(erosion_loss, 0.0, absolute=1.0e-9)
                    or not _close(
                        step.get("pedogenic_flux_index"),
                        0.0,
                        absolute=1.0e-9,
                    )
                ):
                    errors.append(
                        f"profile {profile_id}: zero-duration soil change {step_index}"
                    )
            for field in (
                "weathering_index",
                "leaching_index",
                "bioturbation_index",
                "horizon_differentiation_index",
                "pedogenic_flux_index",
                "erosion_pressure_index",
                "organic_accumulation_index",
                "clay_translocation_index",
                "carbonate_mobilization_index",
                "salinization_index",
            ):
                if not _bounded(step.get(field)):
                    errors.append(f"profile {profile_id}: {field} {step_index}")
            for field in step_values:
                value = _number(step.get(field))
                if math.isfinite(value) and (
                    not geo_only or source_duration > 0.0
                ):
                    step_values[field].append(value)
        if steps:
            if (
                not _close(history.get("initial_depth_m"), steps[0].get("start_depth_m"))
                or not _close(history.get("final_depth_m"), steps[-1].get("end_depth_m"))
                or not _close(history.get("final_depth_m"), profile.get("total_depth_m"))
                or not _close(
                    history.get("total_soil_production_m"),
                    step_production_sum,
                    absolute=2.0e-4,
                )
                or not _close(
                    history.get("total_erosion_loss_m"),
                    step_erosion_sum,
                    absolute=2.0e-4,
                )
            ):
                errors.append(f"profile {profile_id}: history depth/flux totals")
            mean_fields = {
                "mean_weathering_index": "weathering_index",
                "mean_leaching_index": "leaching_index",
                "mean_bioturbation_index": "bioturbation_index",
                "mean_horizon_differentiation_index": (
                    "horizon_differentiation_index"
                ),
                "mean_pedogenic_flux_index": "pedogenic_flux_index",
            }
            for history_field, step_field in mean_fields.items():
                values = step_values[step_field]
                expected_mean = sum(values) / len(values) if values else 0.0
                if not _close(history.get(history_field), expected_mean):
                    errors.append(
                        f"profile {profile_id}: history mean {history_field}"
                    )
            expected_high_erosion = any(
                _number(step.get("erosion_pressure_index"), 0.0) >= 0.65
                and (
                    not geo_only
                    or _number(
                        step.get("nominal_interval_duration_ma"), 0.0
                    )
                    > 0.0
                )
                for step in steps
            )
            if history.get("high_erosion_pressure") is not expected_high_erosion:
                errors.append(f"profile {profile_id}: high erosion mirror")
    expected_profiles = {
        _int(cell.get("id")) for cell in cells if _int(cell.get("soil_profile_id")) >= 0
    }
    if assigned_cells != expected_profiles:
        errors.append("soil profile assignment inverse")
    if used_horizons != set(range(len(horizons))) or used_histories != set(range(len(histories))):
        errors.append("orphan/duplicate soil horizon or history")
    mirror_ok, mirror_errors = _all_summary_mirrors(
        summary,
        {
            "soil_profile_count": len(profiles),
            "soil_horizon_count": len(horizons),
            "soil_profile_history_count": len(histories),
            "soil_pedogenesis_step_count": sum(
                len(history.get("steps", []))
                for history in histories
                if isinstance(history.get("steps"), list)
            ),
            "soil_pedogenesis_stage_count": _int(
                pedogenesis_model.get("stage_count")
            ),
            "soil_pedogenesis_time_basis": pedogenesis_model.get("time_basis"),
            "total_soil_production_m": float(
                sum(
                    _number(history.get("total_soil_production_m"), 0.0)
                    for history in histories
                )
            ),
            "total_soil_erosion_loss_m": float(
                sum(
                    _number(history.get("total_erosion_loss_m"), 0.0)
                    for history in histories
                )
            ),
        },
    )
    _add(
        checks,
        domain=domain,
        name="soil_profile_horizon_history_links",
        passed=not errors and mirror_ok,
        message="Soil profiles link contiguous horizons and continuous pedogenesis histories without orphans." if not errors and mirror_ok else "Soil profile, horizon, history, range, or summary links are inconsistent.",
        observed={"errors": errors[:20], "summary_mismatches": mirror_errors},
        expected="one profile/history per eligible cell with contiguous owned horizons",
    )

    ecotones, ecotone_shape = _records(world, "biome_ecotone_regions")
    ecotone_errors: list[str] = []
    if not ecotone_shape or not _sequential_ids(ecotones):
        ecotone_errors.append("ecotone structure/IDs")
    assigned: set[int] = set()
    for region in ecotones:
        region_id = _int(region.get("id"))
        cell_ids, unique = _id_list(region.get("cell_ids"))
        ecotone_type = str(region.get("ecotone_type", "none"))
        if (
            not unique
            or not cell_ids
            or any(cell_id not in cells_by_id for cell_id in cell_ids)
        ):
            ecotone_errors.append(f"ecotone {region_id}: cells")
            continue
        if assigned.intersection(cell_ids):
            ecotone_errors.append(f"ecotone {region_id}: overlap")
        assigned.update(cell_ids)
        if (
            _int(region.get("cell_count")) != len(cell_ids)
            or not _close(region.get("area_km2"), _record_area(region, cells_by_id))
        ):
            ecotone_errors.append(f"ecotone {region_id}: count/area")
        for cell_id in cell_ids:
            cell = cells_by_id[cell_id]
            if (
                _int(cell.get("biome_ecotone_region_id")) != region_id
                or str(cell.get("biome_ecotone_type", "none")) != ecotone_type
            ):
                ecotone_errors.append(f"ecotone {region_id}: cell mirror {cell_id}")
        if not _bounded(region.get("mean_ecotone_confidence")):
            ecotone_errors.append(f"ecotone {region_id}: confidence")
        if not _nonnegative(region.get("mean_precipitation_mm_y")) or not _finite(
            region.get("mean_temperature_c")
        ):
            ecotone_errors.append(f"ecotone {region_id}: climate values")
    expected_ecotones = {
        _int(cell.get("id"))
        for cell in cells
        if _int(cell.get("biome_ecotone_region_id")) >= 0
    }
    if assigned != expected_ecotones:
        ecotone_errors.append("ecotone assignment inverse")
    ecotone_mirror_ok, ecotone_mirror_errors = _all_summary_mirrors(
        summary,
        {
            "biome_ecotone_region_count": len(ecotones),
            "biome_ecotone_cell_count": sum(
                1
                for cell in cells
                if str(cell.get("biome_ecotone_type", "none")) != "none"
            ),
        },
    )
    _add(
        checks,
        domain=domain,
        name="biome_ecotone_membership_and_ranges",
        passed=not ecotone_errors and ecotone_mirror_ok,
        message="Biome ecotone regions exactly mirror typed cells and bounded confidence." if not ecotone_errors and ecotone_mirror_ok else "Biome ecotone membership, climate values, or summary mirrors are inconsistent.",
        observed={"errors": ecotone_errors[:18], "summary_mismatches": ecotone_mirror_errors},
        expected="exact typed-cell partition with finite bounded diagnostics",
    )


def _validate_lakes_watersheds(
    checks: list[Check], world: dict[str, Any], cells: list[Record], cells_by_id: dict[int, Record], summary: Record
) -> None:
    domain = "lakes_watersheds"
    basins, basins_shape = _records(world, "lake_basins")
    basin_errors: list[str] = []
    basin_ids = {_int(basin.get("id")) for basin in basins}
    if not basins_shape or not _sequential_ids(basins):
        basin_errors.append("lake basin structure or IDs")
    basins_by_id = {_int(basin.get("id")): basin for basin in basins}
    for cell in cells:
        if cell.get("is_lake") is not True:
            continue
        cell_id = _int(cell.get("id"))
        basin = basins_by_id.get(_int(cell.get("lake_basin_id")))
        water_body = cell.get("water_body_type")
        if (
            cell.get("is_water") is not False
            or water_body not in {"fresh_lake", "saline_basin"}
            or basin is None
            or basin.get("water_body_type") != water_body
            or (basin.get("overflows") is True and water_body != "fresh_lake")
        ):
            basin_errors.append(f"cell {cell_id}: lake water-body classification")
        if (
            cell.get("biome") != "lake"
            or cell.get("soil_type") != ("saline" if water_body == "saline_basin" else "wetland")
            or cell.get("landform") not in {"lacustrine_basin", "glacial_lake"}
            or not _close(cell.get("soil_depth_m"), 0.0)
            or not _close(cell.get("fertility"), 0.0)
            or ("settlement_score" in cell and not _close(cell["settlement_score"], 0.0))
        ):
            basin_errors.append(f"cell {cell_id}: standing lake surface coherence")
    for basin in basins:
        basin_id = _int(basin.get("id"))
        linked_cells = [cell for cell in cells if _int(cell.get("lake_basin_id")) == basin_id]
        path, path_unique = _id_list(basin.get("overflow_path_cell_ids"))
        if _int(basin.get("cell_count")) != len(linked_cells):
            basin_errors.append(f"basin {basin_id}: cell_count")
        if not _close(basin.get("area_km2"), sum(_number(cell.get("area_km2"), 0.0) for cell in linked_cells)):
            basin_errors.append(f"basin {basin_id}: area")
        if not path_unique or any(cell_id not in cells_by_id for cell_id in path) or (path and not _adjacent(path, cells_by_id)):
            basin_errors.append(f"basin {basin_id}: overflow path")
        for field in ("outlet_cell_id", "spill_to_cell_id"):
            linked_id = _int(basin.get(field))
            if linked_id >= 0 and linked_id not in cells_by_id:
                basin_errors.append(f"basin {basin_id}: {field}")
        for field in ("area_km2", "lake_area_km2", "storage_capacity_km3", "annual_runoff_km3", "mean_water_depth_m", "max_depression_depth_m", "overflow_path_length_km"):
            if not _nonnegative(basin.get(field)):
                basin_errors.append(f"basin {basin_id}: {field}")
        for field in ("geologic_area_fraction", "avulsion_risk"):
            if not _bounded(basin.get(field)):
                basin_errors.append(f"basin {basin_id}: {field}")
        # `overflow_index` is the unnormalized runoff/storage pressure used by
        # the native lake model. Production clamps that ratio to [0, 50] and
        # only normalizes it later when deriving avulsion pressure; treating it
        # as a unit interval rejects valid high-throughput basins.
        overflows = basin.get("overflows")
        if not isinstance(overflows, bool):
            basin_errors.append(f"basin {basin_id}: overflows")
        overflow_index = basin.get("overflow_index")
        if not _bounded(overflow_index, 0.0, 50.0):
            basin_errors.append(f"basin {basin_id}: overflow_index")
        storage_capacity = _number(basin.get("storage_capacity_km3"))
        annual_runoff = _number(basin.get("annual_runoff_km3"))
        expected_overflow_index = (
            min(50.0, max(0.0, annual_runoff / max(0.001, storage_capacity)))
            if overflows is True
            and math.isfinite(storage_capacity)
            and math.isfinite(annual_runoff)
            else 0.0
        )
        if not _close(overflow_index, expected_overflow_index):
            basin_errors.append(f"basin {basin_id}: overflow_index replay")
        if not _bounded(basin.get("fill_fraction"), 0.0, 1.5):
            basin_errors.append(f"basin {basin_id}: fill_fraction")
        if _int(basin.get("lake_cell_count"), -1) < 0 or _int(basin.get("lake_cell_count")) > len(linked_cells):
            basin_errors.append(f"basin {basin_id}: lake_cell_count")
    _add(
        checks,
        domain=domain,
        name="lake_basin_membership_and_storage",
        passed=not basin_errors,
        message="Lake basins mirror cell membership, storage bounds, and adjacent overflow paths." if not basin_errors else "Lake basin membership, storage, or overflow-path records are inconsistent.",
        observed=basin_errors[:15],
        expected="exact cell assignment inverse and finite physical basin values",
    )

    histories, history_shape = _records(world, "lake_overflow_histories")
    history_errors: list[str] = []
    for history in histories:
        history_id = _int(history.get("id"))
        lake_id = _int(history.get("lake_basin_id"))
        steps = history.get("steps")
        if lake_id not in basin_ids or history_id != lake_id or not isinstance(steps, list) or not all(isinstance(step, dict) for step in steps):
            history_errors.append(f"history {history_id}: structure/source")
            continue
        if _int(history.get("time_step_count")) != len(steps) or _int(history.get("simulation_year_count")) != len(steps):
            history_errors.append(f"history {history_id}: step counts")
        previous_end: float | None = None
        for index, step in enumerate(steps):
            start = _number(step.get("start_volume_km3"))
            end = _number(step.get("end_volume_km3"))
            inflow = _number(step.get("inflow_km3"))
            evaporation = _number(step.get("evaporation_loss_km3"))
            spill = _number(step.get("spill_volume_km3"))
            sink = _number(step.get("sink_loss_km3"))
            if not all(math.isfinite(value) and value >= 0.0 for value in (start, end, inflow, evaporation, spill, sink)):
                history_errors.append(f"history {history_id}: nonfinite/negative step {index}")
                continue
            if previous_end is not None and not _tight_close(start, previous_end):
                history_errors.append(f"history {history_id}: discontinuity {index}")
            if not _close(end, start + inflow - evaporation - spill - sink, absolute=2.0e-3):
                history_errors.append(f"history {history_id}: volume closure {index}")
            if not _bounded(step.get("fill_fraction")) or not _bounded(step.get("avulsion_risk")):
                history_errors.append(f"history {history_id}: bounded step indices {index}")
            previous_end = end
        if not _close(history.get("total_inflow_km3"), sum(_number(step.get("inflow_km3"), 0.0) for step in steps), absolute=2.0e-3):
            history_errors.append(f"history {history_id}: inflow aggregate")
        if not _close(history.get("total_spill_km3"), sum(_number(step.get("spill_volume_km3"), 0.0) for step in steps), absolute=2.0e-3):
            history_errors.append(f"history {history_id}: spill aggregate")
        if not _close(history.get("total_sink_loss_km3"), sum(_number(step.get("sink_loss_km3"), 0.0) for step in steps), absolute=2.0e-3):
            history_errors.append(f"history {history_id}: sink aggregate")
    channels, channel_shape = _records(world, "lake_overflow_channel_histories")
    for channel in channels:
        channel_id = _int(channel.get("id"))
        steps = channel.get("steps")
        path, path_unique = _id_list(channel.get("overflow_path_cell_ids"))
        if _int(channel.get("lake_basin_id")) not in basin_ids or not path_unique or len(path) < 2 or not _adjacent(path, cells_by_id):
            history_errors.append(f"channel {channel_id}: source/path")
        if not isinstance(steps, list) or not all(isinstance(step, dict) for step in steps) or _int(channel.get("time_step_count")) != len(steps):
            history_errors.append(f"channel {channel_id}: steps")
        if _int(channel.get("channel_segment_count")) != max(0, len(path) - 1):
            history_errors.append(f"channel {channel_id}: segment_count")
    mirrors_ok, mirror_errors = _all_summary_mirrors(
        summary,
        {
            "lake_overflow_history_count": len(histories),
            "lake_overflow_history_step_count": sum(len(history.get("steps", [])) for history in histories if isinstance(history.get("steps"), list)),
            "lake_overflow_channel_history_count": len(channels),
            "lake_overflow_channel_step_count": sum(len(channel.get("steps", [])) for channel in channels if isinstance(channel.get("steps"), list)),
        },
    )
    _add(
        checks,
        domain=domain,
        name="lake_overflow_history_conservation",
        passed=history_shape and channel_shape and not history_errors and mirrors_ok,
        message="Lake histories conserve volume, keep continuous stages, and mirror summary counts." if history_shape and channel_shape and not history_errors and mirrors_ok else "Lake overflow histories, channel sources, or summary mirrors are inconsistent.",
        observed={"history_errors": history_errors[:15], "summary_mismatches": mirror_errors},
        expected="continuous conservative histories and linked channel paths",
    )

    watersheds, watershed_shape = _records(world, "watersheds")
    watershed_errors: list[str] = []
    if not watershed_shape or not _sequential_ids(watersheds):
        watershed_errors.append("watershed structure or IDs")
    watershed_ids = set(range(len(watersheds)))
    basin_to_watershed = {_int(watershed.get("basin_id")): _int(watershed.get("id")) for watershed in watersheds}
    if len(basin_to_watershed) != len(watersheds):
        watershed_errors.append("duplicate watershed basin IDs")
    for watershed in watersheds:
        watershed_id = _int(watershed.get("id"))
        basin_id = _int(watershed.get("basin_id"))
        members = [cell for cell in cells if not bool(cell.get("is_water", False)) and _int(cell.get("basin_id")) == basin_id]
        path, path_unique = _id_list(watershed.get("main_channel_cell_ids"))
        neighbors, neighbor_unique = _id_list(watershed.get("neighbor_watershed_ids"))
        if _int(watershed.get("cell_count")) != len(members):
            watershed_errors.append(f"watershed {watershed_id}: cell_count")
        if not _close(watershed.get("area_km2"), sum(_number(cell.get("area_km2"), 0.0) for cell in members)):
            watershed_errors.append(f"watershed {watershed_id}: area")
        if not path_unique or any(cell_id not in cells_by_id or _int(cells_by_id[cell_id].get("basin_id")) != basin_id for cell_id in path):
            watershed_errors.append(f"watershed {watershed_id}: main-channel membership")
        if path and (not _adjacent(path, cells_by_id) or _int(watershed.get("main_channel_source_cell_id")) != path[0] or _int(watershed.get("main_channel_outlet_cell_id")) != path[-1]):
            watershed_errors.append(f"watershed {watershed_id}: main-channel path")
        if not neighbor_unique or any(neighbor_id not in watershed_ids or neighbor_id == watershed_id for neighbor_id in neighbors):
            watershed_errors.append(f"watershed {watershed_id}: neighbors")
        for field in ("area_km2", "main_channel_length_km", "main_channel_drop_m", "main_channel_gradient", "total_river_length_km", "drainage_density_km_per_1000_km2", "boundary_perimeter_km"):
            if not _nonnegative(watershed.get(field)):
                watershed_errors.append(f"watershed {watershed_id}: {field}")
        for field in ("compactness_index", "geometry_quality", "mean_cell_edge_boundary_segment_quality"):
            if not _bounded(watershed.get(field)):
                watershed_errors.append(f"watershed {watershed_id}: {field}")
    for watershed in watersheds:
        watershed_id = _int(watershed.get("id"))
        for neighbor_id in _id_list(watershed.get("neighbor_watershed_ids"))[0]:
            neighbor = watersheds[neighbor_id]
            if watershed_id not in _id_list(neighbor.get("neighbor_watershed_ids"))[0]:
                watershed_errors.append(f"watershed {watershed_id}: asymmetric neighbor {neighbor_id}")
    watershed_mirror_ok, watershed_mirror_errors = _all_summary_mirrors(
        summary,
        {
            "watershed_count": len(watersheds),
            "watershed_main_channel_count": sum(1 for watershed in watersheds if len(_id_list(watershed.get("main_channel_cell_ids"))[0]) >= 2),
            "watershed_total_river_length_km": sum(_number(watershed.get("total_river_length_km"), 0.0) for watershed in watersheds),
        },
    )
    _add(
        checks,
        domain=domain,
        name="watershed_internal_topology_and_aggregates",
        passed=not watershed_errors and watershed_mirror_ok,
        message="Watersheds mirror land-basin membership, channel paths, neighbors, and summary aggregates." if not watershed_errors and watershed_mirror_ok else "Watershed internal topology, aggregates, or summary mirrors are inconsistent.",
        observed={"errors": watershed_errors[:15], "summary_mismatches": watershed_mirror_errors},
        expected="exact basin membership, adjacent channels, reciprocal neighbors",
    )


def _validate_rivers(
    checks: list[Check], world: dict[str, Any], cells: list[Record], cells_by_id: dict[int, Record], summary: Record
) -> None:
    domain = "river_evolution_channels"
    events, events_shape = _records(world, "river_network_evolution_events")
    histories, histories_shape = _records(world, "river_reorganization_histories")
    evolution_errors: list[str] = []
    if not events_shape or not histories_shape or not _sequential_ids(events) or not _sequential_ids(histories):
        evolution_errors.append("event/history structure or IDs")
    event_ids = set(range(len(events)))
    for event in events:
        event_id = _int(event.get("id"))
        for field in ("source_cell_id", "target_cell_id"):
            if _int(event.get(field)) not in cells_by_id:
                evolution_errors.append(f"event {event_id}: {field}")
        if not _bounded(event.get("risk")) or not _nonnegative(event.get("flow_accumulation")):
            evolution_errors.append(f"event {event_id}: risk/flow")
        if str(event.get("type", "")) not in {
            "river_capture_candidate",
            "river_avulsion_candidate",
        }:
            evolution_errors.append(f"event {event_id}: type")
    referenced_events: set[int] = set()
    for history in histories:
        history_id = _int(history.get("id"))
        event_id = _int(history.get("river_network_evolution_event_id"))
        referenced_events.add(event_id)
        steps = history.get("steps")
        if event_id not in event_ids or not isinstance(steps, list) or not all(isinstance(step, dict) for step in steps):
            evolution_errors.append(f"history {history_id}: event/steps")
            continue
        event = events[event_id]
        if _int(history.get("source_cell_id")) != _int(event.get("source_cell_id")) or _int(history.get("target_cell_id")) != _int(event.get("target_cell_id")):
            evolution_errors.append(f"history {history_id}: event source mirror")
        if _int(history.get("step_count")) != len(steps):
            evolution_errors.append(f"history {history_id}: step_count")
        if _int(history.get("projected_flow_to_cell_id")) not in cells_by_id:
            evolution_errors.append(f"history {history_id}: projected target")
        for step_index, step in enumerate(steps):
            for field in ("channelization_index", "diversion_probability_index", "reorganization_confidence_index", "basin_connectivity_change_index"):
                if not _bounded(step.get(field)):
                    evolution_errors.append(f"history {history_id}: {field} step {step_index}")
            for field in ("elapsed_years", "divide_lowering_m", "sediment_reworking_m", "divide_relief_m", "channel_gradient"):
                if not _nonnegative(step.get(field)):
                    evolution_errors.append(f"history {history_id}: {field} step {step_index}")
    if referenced_events != event_ids:
        evolution_errors.append("events and histories are not one-to-one")
    mirror_ok, mirror_errors = _all_summary_mirrors(
        summary,
        {
            "river_network_evolution_event_count": len(events),
            "river_reorganization_history_count": len(histories),
            "river_reorganization_step_count": sum(len(history.get("steps", [])) for history in histories if isinstance(history.get("steps"), list)),
        },
    )
    _add(
        checks,
        domain=domain,
        name="evolution_event_history_links",
        passed=not evolution_errors and mirror_ok,
        message="River reorganization histories link one-to-one to bounded evolution events and summary counts." if not evolution_errors and mirror_ok else "River evolution events, histories, or summary mirrors are inconsistent.",
        observed={"errors": evolution_errors[:15], "summary_mismatches": mirror_errors},
        expected="one history per event with valid cell sources and bounded steps",
    )

    channel_model, channel_model_ok = _dict_payload(world, "river_channel_morphology_model")
    systems, systems_shape = _records(world, "river_channel_systems")
    channel_errors: list[str] = []
    if not systems_shape or not _sequential_ids(systems) or not channel_model_ok:
        channel_errors.append("channel model/system structure")
    assigned: set[int] = set()
    for system in systems:
        system_id = _int(system.get("id"))
        cell_ids, unique = _id_list(system.get("cell_ids"))
        if not unique or not cell_ids or any(cell_id not in cells_by_id for cell_id in cell_ids):
            channel_errors.append(f"channel {system_id}: cell_ids")
            continue
        if assigned.intersection(cell_ids):
            channel_errors.append(f"channel {system_id}: overlap")
        assigned.update(cell_ids)
        if _int(system.get("cell_count")) != len(cell_ids) or not _close(system.get("area_km2"), _record_area(system, cells_by_id)):
            channel_errors.append(f"channel {system_id}: count/area")
        if _int(system.get("source_cell_id")) not in cell_ids or _int(system.get("outlet_cell_id")) not in cell_ids:
            channel_errors.append(f"channel {system_id}: source/outlet")
        for cell_id in cell_ids:
            cell = cells_by_id[cell_id]
            if not bool(cell.get("is_river", False)) or _int(cell.get("river_channel_system_id")) != system_id:
                channel_errors.append(f"channel {system_id}: cell mirror {cell_id}")
        for field in ("length_km", "mean_bankfull_discharge_m3_s", "mean_channel_width_m", "mean_channel_depth_m", "mean_stream_power_index", "mean_channel_slope_index"):
            if not _nonnegative(system.get(field)):
                channel_errors.append(f"channel {system_id}: {field}")
        if not _bounded(system.get("mean_floodplain_connectivity_index")):
            channel_errors.append(f"channel {system_id}: floodplain connectivity")
    if assigned != {_int(cell.get("id")) for cell in cells if _int(cell.get("river_channel_system_id")) >= 0}:
        channel_errors.append("channel membership does not invert cell assignments")
    channel_mirror_ok, channel_mirror_errors = _all_summary_mirrors(
        summary,
        {
            "river_channel_system_count": len(systems),
            "river_channel_cell_count": len(assigned),
            "total_river_channel_length_km": sum(_number(system.get("length_km"), 0.0) for system in systems),
        },
    )
    _add(
        checks,
        domain=domain,
        name="channel_system_membership_and_geometry",
        passed=not channel_errors and channel_mirror_ok,
        message="River channel systems mirror river cells, geometry, and summary totals." if not channel_errors and channel_mirror_ok else "River channel membership, geometry, model metadata, or summary mirrors are inconsistent.",
        observed={"errors": channel_errors[:15], "summary_mismatches": channel_mirror_errors, "model_type": channel_model.get("model_type")},
        expected="exact channel assignment inverse with finite nonnegative geometry",
    )

    hydraulic_model, hydraulic_model_ok = _dict_payload(world, "river_hydraulics_model")
    reaches, reaches_shape = _records(world, "river_hydraulic_reaches")
    reach_errors: list[str] = []
    if not reaches_shape or not _sequential_ids(reaches) or not hydraulic_model_ok:
        reach_errors.append("hydraulic model/reach structure")
    reach_assigned: set[int] = set()
    system_ids = set(range(len(systems)))
    for reach in reaches:
        reach_id = _int(reach.get("id"))
        cell_ids, unique = _id_list(reach.get("cell_ids"))
        if not unique or not cell_ids or any(cell_id not in cells_by_id for cell_id in cell_ids):
            reach_errors.append(f"reach {reach_id}: cell_ids")
            continue
        if reach_assigned.intersection(cell_ids):
            reach_errors.append(f"reach {reach_id}: overlap")
        reach_assigned.update(cell_ids)
        channel_id = _int(reach.get("river_channel_system_id"))
        if channel_id not in system_ids or any(_int(cells_by_id[cell_id].get("river_channel_system_id")) != channel_id for cell_id in cell_ids):
            reach_errors.append(f"reach {reach_id}: channel source")
        if _int(reach.get("cell_count")) != len(cell_ids) or not _close(reach.get("area_km2"), _record_area(reach, cells_by_id)):
            reach_errors.append(f"reach {reach_id}: count/area")
        for cell_id in cell_ids:
            if _int(cells_by_id[cell_id].get("river_hydraulic_reach_id")) != reach_id:
                reach_errors.append(f"reach {reach_id}: cell mirror {cell_id}")
        for field in ("length_km", "mean_hydraulic_radius_m", "mean_flow_velocity_m_s", "mean_froude_number", "mean_bed_shear_stress_pa", "mean_manning_roughness_n"):
            if not _nonnegative(reach.get(field)):
                reach_errors.append(f"reach {reach_id}: {field}")
        for field in ("mean_channel_capacity_index", "mean_hydraulic_navigability_index"):
            if not _bounded(reach.get(field)):
                reach_errors.append(f"reach {reach_id}: {field}")
    if reach_assigned != {_int(cell.get("id")) for cell in cells if _int(cell.get("river_hydraulic_reach_id")) >= 0}:
        reach_errors.append("reach membership does not invert cell assignments")
    reach_mirror_ok, reach_mirror_errors = _all_summary_mirrors(
        summary,
        {"river_hydraulic_reach_count": len(reaches), "river_hydraulic_cell_count": len(reach_assigned)},
    )
    _add(
        checks,
        domain=domain,
        name="hydraulic_reach_source_links_and_ranges",
        passed=not reach_errors and reach_mirror_ok,
        message="Hydraulic reaches mirror channel cells, source systems, bounded indices, and summary counts." if not reach_errors and reach_mirror_ok else "Hydraulic reach sources, assignments, values, or summary mirrors are inconsistent.",
        observed={"errors": reach_errors[:15], "summary_mismatches": reach_mirror_errors, "model_type": hydraulic_model.get("model_type")},
        expected="exact reach assignment inverse and linked channel systems",
    )


def _validate_sequence_stratigraphy(checks: list[Check], world: dict[str, Any], summary: Record) -> None:
    domain = "sequence_stratigraphy"
    histories, shape_ok = _records(world, "sequence_stratigraphy_histories")
    columns, columns_shape = _records(world, "stratigraphic_columns")
    sediment_histories, sediment_shape = _records(world, "sediment_transport_histories")
    column_by_id = {_int(column.get("id")): column for column in columns}
    sediment_by_basin = {_int(history.get("basin_id")): history for history in sediment_histories}
    errors: list[str] = []
    if not shape_ok or not columns_shape or not sediment_shape or not _sequential_ids(histories):
        errors.append("history/source structure or IDs")
    total_surfaces: Counter[str] = Counter()
    total_tracts: Counter[str] = Counter()
    total_trajectories: Counter[str] = Counter()
    for history in histories:
        history_id = _int(history.get("id"))
        column_id = _int(history.get("stratigraphic_column_id"))
        basin_id = _int(history.get("basin_id"))
        column = column_by_id.get(column_id)
        source = sediment_by_basin.get(basin_id)
        steps = history.get("steps")
        if column is None or source is None or not isinstance(steps, list) or not all(isinstance(step, dict) for step in steps):
            errors.append(f"history {history_id}: source/steps")
            continue
        if _int(column.get("basin_id")) != basin_id or _int(source.get("basin_id")) != basin_id:
            errors.append(f"history {history_id}: basin source")
        if _int(history.get("time_step_count")) != len(steps) or len(steps) != len(source.get("steps", [])):
            errors.append(f"history {history_id}: step count/source coverage")
        surface_counts: Counter[str] = Counter()
        tract_counts: Counter[str] = Counter()
        trajectory_counts: Counter[str] = Counter()
        for index, step in enumerate(steps):
            surface = str(step.get("sequence_surface", ""))
            tract = str(step.get("systems_tract", ""))
            trajectory = str(step.get("shoreline_trajectory", ""))
            if surface not in {"none", "sequence_boundary", "transgressive_surface", "maximum_flooding_surface", "regressive_surface"}:
                errors.append(f"history {history_id}: surface {index}")
            if tract not in {"lowstand_systems_tract", "transgressive_systems_tract", "highstand_systems_tract", "falling_stage_systems_tract", "aggradational_systems_tract"}:
                errors.append(f"history {history_id}: tract {index}")
            if trajectory not in {"progradational", "retrogradational", "aggradational"}:
                errors.append(f"history {history_id}: trajectory {index}")
            for field in ("sediment_supply_index", "relative_sea_level_index", "flooding_index", "preservation_potential"):
                if not _bounded(step.get(field)):
                    errors.append(f"history {history_id}: {field} {index}")
            for field in ("start_age_ma", "end_age_ma", "accommodation_to_deposition_ratio", "progradation_distance_km"):
                if not _nonnegative(step.get(field)):
                    errors.append(f"history {history_id}: {field} {index}")
            if _number(step.get("start_age_ma"), -1.0) < _number(step.get("end_age_ma"), 0.0):
                errors.append(f"history {history_id}: reversed age {index}")
            surface_counts[surface] += 1
            tract_counts[tract] += 1
            trajectory_counts[trajectory] += 1
        event_count = sum(count for surface, count in surface_counts.items() if surface != "none")
        if _int(history.get("sequence_event_count")) != event_count:
            errors.append(f"history {history_id}: event_count")
        for field, surface in (
            ("sequence_boundary_count", "sequence_boundary"),
            ("transgressive_surface_count", "transgressive_surface"),
            ("maximum_flooding_surface_count", "maximum_flooding_surface"),
            ("regressive_surface_count", "regressive_surface"),
        ):
            if _int(history.get(field)) != surface_counts[surface]:
                errors.append(f"history {history_id}: {field}")
        if history.get("systems_tract_counts") != dict(sorted(tract_counts.items())) or history.get("shoreline_trajectory_counts") != dict(sorted(trajectory_counts.items())):
            errors.append(f"history {history_id}: categorical aggregates")
        total_surfaces.update(surface_counts)
        total_tracts.update(tract_counts)
        total_trajectories.update(trajectory_counts)
    expected_summary = {
        "sequence_stratigraphy_history_count": len(histories),
        "sequence_stratigraphy_step_count": sum(sum(total_tracts.values()) for _ in [0]),
        "sequence_stratigraphy_event_count": sum(count for surface, count in total_surfaces.items() if surface != "none"),
        "sequence_boundary_count": total_surfaces["sequence_boundary"],
        "transgressive_surface_count": total_surfaces["transgressive_surface"],
        "maximum_flooding_surface_count": total_surfaces["maximum_flooding_surface"],
        "regressive_surface_count": total_surfaces["regressive_surface"],
        "systems_tract_counts": dict(sorted(total_tracts.items())),
        "shoreline_trajectory_counts": dict(sorted(total_trajectories.items())),
    }
    mirrors_ok, mirror_errors = _all_summary_mirrors(summary, expected_summary)
    _add(
        checks,
        domain=domain,
        name="source_links_steps_and_aggregates",
        passed=not errors and mirrors_ok,
        message="Sequence histories cover their source sediment histories and reproduce categorical aggregates." if not errors and mirrors_ok else "Sequence-stratigraphy source links, step values, or aggregates are inconsistent.",
        observed={"errors": errors[:18], "summary_mismatches": mirror_errors},
        expected="one linked column/basin history with exact step and summary aggregates",
    )


def _validate_cryosphere(
    checks: list[Check], world: dict[str, Any], cells: list[Record], cells_by_id: dict[int, Record], summary: Record
) -> None:
    domain = "cryosphere_permafrost_glacial"
    sheets, sheets_shape = _records(world, "ice_sheets")
    histories, histories_shape = _records(world, "ice_sheet_histories")
    sheet_ids = {_int(sheet.get("id")) for sheet in sheets}
    errors: list[str] = []
    if not sheets_shape or not histories_shape:
        errors.append("ice sheet/history structure")
    history_sheet_ids: set[int] = set()
    for history in histories:
        history_id = _int(history.get("id"))
        sheet_id = _int(history.get("ice_sheet_id"))
        history_sheet_ids.add(sheet_id)
        steps = history.get("steps")
        if sheet_id not in sheet_ids or history_id != sheet_id or not isinstance(steps, list) or not all(isinstance(step, dict) for step in steps):
            errors.append(f"history {history_id}: source/steps")
            continue
        if _int(history.get("time_step_count")) != len(steps):
            errors.append(f"history {history_id}: step_count")
        previous_volume: float | None = None
        previous_area: float | None = None
        for index, step in enumerate(steps):
            start_volume = _number(step.get("start_volume_km3"))
            end_volume = _number(step.get("end_volume_km3"))
            start_area = _number(step.get("start_area_km2"))
            end_area = _number(step.get("end_area_km2"))
            surface = _number(step.get("surface_balance_km3"))
            dynamic = _number(step.get("dynamic_loss_km3"))
            retreat = _number(step.get("retreat_loss_km3"))
            adjustment = _number(step.get("stabilization_adjustment_km3"))
            if not all(math.isfinite(value) for value in (start_volume, end_volume, start_area, end_area, surface, dynamic, retreat, adjustment)):
                errors.append(f"history {history_id}: nonfinite step {index}")
                continue
            if min(start_volume, end_volume, start_area, end_area, dynamic, retreat) < 0.0:
                errors.append(f"history {history_id}: negative physical value {index}")
            if previous_volume is not None and (
                not _tight_close(start_volume, previous_volume)
                or not _tight_close(start_area, previous_area)
            ):
                errors.append(f"history {history_id}: discontinuity {index}")
            if not _close(end_volume, start_volume + surface - dynamic - retreat + adjustment, absolute=3.0e-3):
                errors.append(f"history {history_id}: volume closure {index}")
            if not _bounded(step.get("basal_sliding_index")) or not _bounded(step.get("accumulation_area_fraction")):
                errors.append(f"history {history_id}: bounded indices {index}")
            previous_volume, previous_area = end_volume, end_area
        if steps:
            if not _close(history.get("initial_volume_km3"), steps[0].get("start_volume_km3")) or not _close(history.get("final_volume_km3"), steps[-1].get("end_volume_km3")):
                errors.append(f"history {history_id}: endpoint aggregates")
        for field, step_field in (
            ("total_surface_balance_km3", "surface_balance_km3"),
            ("total_dynamic_loss_km3", "dynamic_loss_km3"),
            ("total_retreat_loss_km3", "retreat_loss_km3"),
            ("total_retreat_distance_km", "retreat_distance_km"),
        ):
            if not _close(history.get(field), sum(_number(step.get(step_field), 0.0) for step in steps), absolute=3.0e-3):
                errors.append(f"history {history_id}: {field}")
    if history_sheet_ids != sheet_ids:
        errors.append("ice sheet/history coverage")
    mirror_ok, mirror_errors = _all_summary_mirrors(
        summary,
        {
            "ice_sheet_history_count": len(histories),
            "ice_sheet_history_step_count": sum(len(history.get("steps", [])) for history in histories if isinstance(history.get("steps"), list)),
            "ice_sheet_history_final_volume_km3": float(
                sum(
                    _number(history.get("final_volume_km3"), 0.0)
                    for history in histories
                )
            ),
        },
    )
    _add(
        checks,
        domain=domain,
        name="ice_sheet_history_conservation",
        passed=not errors and mirror_ok,
        message="Ice-sheet histories conserve bounded volume changes and cover each source sheet." if not errors and mirror_ok else "Ice-sheet history conservation, source coverage, or summary mirrors are inconsistent.",
        observed={"errors": errors[:15], "summary_mismatches": mirror_errors},
        expected="continuous per-sheet histories with volume closure",
    )

    stability, stability_shape = _records(world, "ice_sheet_stability_histories")
    flowlines, flow_shape = _records(world, "ice_flowline_histories")
    dynamic_errors: list[str] = []
    if not stability_shape or not flow_shape or not _sequential_ids(stability) or not _sequential_ids(flowlines):
        dynamic_errors.append("stability/flowline structure or IDs")
    if {_int(record.get("ice_sheet_id")) for record in stability} != sheet_ids:
        dynamic_errors.append("stability histories do not cover source sheets")
    for record in stability:
        record_id = _int(record.get("id"))
        steps = record.get("steps")
        if not isinstance(steps, list) or not all(isinstance(step, dict) for step in steps) or _int(record.get("time_step_count")) != len(steps):
            dynamic_errors.append(f"stability {record_id}: steps")
            continue
        for field in ("mean_stability_index", "max_stability_index", "calving_susceptibility_index", "grounding_line_instability_index", "marine_margin_fraction"):
            if not _bounded(record.get(field)):
                dynamic_errors.append(f"stability {record_id}: {field}")
        for index, step in enumerate(steps):
            for field in ("balance_deficit_index", "retreat_pace_index", "calving_susceptibility_index", "grounding_line_instability_index", "retreat_threshold_index"):
                if not _bounded(step.get(field)):
                    dynamic_errors.append(f"stability {record_id}: {field} {index}")
    for flowline in flowlines:
        flowline_id = _int(flowline.get("id"))
        path, unique = _id_list(flowline.get("flowline_cell_ids"))
        steps = flowline.get("steps")
        if not unique or not path or any(cell_id not in cells_by_id for cell_id in path) or not _adjacent(path, cells_by_id):
            dynamic_errors.append(f"flowline {flowline_id}: path")
        if _int(flowline.get("source_cell_id")) != (path[0] if path else -1) or _int(flowline.get("ice_sheet_id")) not in sheet_ids:
            dynamic_errors.append(f"flowline {flowline_id}: source")
        if not isinstance(steps, list) or not all(isinstance(step, dict) for step in steps) or _int(flowline.get("time_step_count")) != len(steps):
            dynamic_errors.append(f"flowline {flowline_id}: steps")
            continue
        if [_int(step.get("cell_id")) for step in steps] != path:
            dynamic_errors.append(f"flowline {flowline_id}: step/path cells")
        for index, step in enumerate(steps):
            start = _number(step.get("start_flux_km3_y"))
            accumulation = _number(step.get("accumulation_flux_km3_y"))
            dynamic_loss = _number(step.get("dynamic_loss_km3_y"))
            melt = _number(step.get("melt_loss_km3_y"))
            end = _number(step.get("end_flux_km3_y"))
            residual = _number(step.get("balance_residual_km3_y"))
            if not all(math.isfinite(value) and value >= 0.0 for value in (start, accumulation, dynamic_loss, melt, end)) or not math.isfinite(residual):
                dynamic_errors.append(f"flowline {flowline_id}: flux values {index}")
            if abs(residual) > 2.0e-5:
                dynamic_errors.append(f"flowline {flowline_id}: balance residual {index}")
            for field in ("basal_sliding_index", "strain_heating_index"):
                if not _bounded(step.get(field)):
                    dynamic_errors.append(f"flowline {flowline_id}: {field} {index}")
    dynamic_mirror_ok, dynamic_mirror_errors = _all_summary_mirrors(
        summary,
        {
            "ice_sheet_stability_history_count": len(stability),
            "ice_sheet_stability_step_count": sum(len(record.get("steps", [])) for record in stability if isinstance(record.get("steps"), list)),
            "ice_flowline_history_count": len(flowlines),
            "ice_flowline_step_count": sum(len(record.get("steps", [])) for record in flowlines if isinstance(record.get("steps"), list)),
        },
    )
    _add(
        checks,
        domain=domain,
        name="stability_and_flowline_sources",
        passed=not dynamic_errors and dynamic_mirror_ok,
        message="Ice stability and flowline histories link valid sheets/cells with bounded dynamics." if not dynamic_errors and dynamic_mirror_ok else "Ice stability or flowline records, links, values, or summary mirrors are inconsistent.",
        observed={"errors": dynamic_errors[:18], "summary_mismatches": dynamic_mirror_errors},
        expected="source-linked sheet stability and adjacent flowline paths",
    )

    permafrost, permafrost_shape = _records(world, "permafrost_regions")
    glacial, glacial_shape = _records(world, "glacial_landform_systems")
    landform_errors: list[str] = []
    for key, records, shape, cell_field, eligibility in (
        ("permafrost", permafrost, permafrost_shape, "permafrost_region_id", lambda cell: _number(cell.get("permafrost_extent_index"), -1.0) >= 0.45),
        ("glacial", glacial, glacial_shape, "glacial_landform_system_id", lambda cell: str(cell.get("glacial_landform_type", "none")) != "none"),
    ):
        if not shape or not _sequential_ids(records):
            landform_errors.append(f"{key}: structure/IDs")
        assigned: set[int] = set()
        for record in records:
            record_id = _int(record.get("id"))
            cell_ids, unique = _id_list(record.get("cell_ids"))
            if not unique or not cell_ids or any(cell_id not in cells_by_id for cell_id in cell_ids):
                landform_errors.append(f"{key} {record_id}: cell_ids")
                continue
            if assigned.intersection(cell_ids):
                landform_errors.append(f"{key} {record_id}: overlap")
            assigned.update(cell_ids)
            if _int(record.get("cell_count")) != len(cell_ids) or not _close(record.get("area_km2"), _record_area(record, cells_by_id)):
                landform_errors.append(f"{key} {record_id}: count/area")
            if key == "permafrost":
                for field in (
                    "permafrost_extent_index",
                    "active_layer_depth_m",
                    "ground_ice_content_index",
                    "frost_months",
                ):
                    expected_mean = sum(
                        _number(cells_by_id[cell_id].get(field))
                        for cell_id in cell_ids
                    ) / len(cell_ids)
                    if not _tight_close(
                        record.get(f"mean_{field}"), expected_mean, absolute=2.0e-6
                    ):
                        landform_errors.append(
                            f"permafrost {record_id}: mean_{field}"
                        )
            for cell_id in cell_ids:
                cell = cells_by_id[cell_id]
                if _int(cell.get(cell_field)) != record_id or not eligibility(cell):
                    landform_errors.append(f"{key} {record_id}: cell mirror {cell_id}")
        expected = {_int(cell.get("id")) for cell in cells if _int(cell.get(cell_field)) >= 0}
        if assigned != expected:
            landform_errors.append(f"{key}: assignment inverse")
    for cell in cells:
        for field in ("permafrost_extent_index", "ground_ice_content_index", "glacial_landform_index", "glacial_erosion_intensity_index", "glacial_deposition_index", "glacial_meltwater_index"):
            if not _bounded(cell.get(field)):
                landform_errors.append(f"cell {_int(cell.get('id'))}: {field}")
        if not _nonnegative(cell.get("active_layer_depth_m")):
            landform_errors.append(f"cell {_int(cell.get('id'))}: active_layer_depth_m")
    landform_mirror_ok, landform_mirror_errors = _all_summary_mirrors(
        summary,
        {
            "permafrost_region_count": len(permafrost),
            "permafrost_cell_count": sum(1 for cell in cells if _number(cell.get("permafrost_extent_index"), -1.0) >= 0.45),
            "glacial_landform_system_count": len(glacial),
            "glacial_landform_cell_count": sum(1 for cell in cells if str(cell.get("glacial_landform_type", "none")) != "none"),
        },
    )
    _add(
        checks,
        domain=domain,
        name="permafrost_and_glacial_membership",
        passed=not landform_errors and landform_mirror_ok,
        message="Permafrost and glacial-landform regions exactly mirror eligible bounded cell diagnostics." if not landform_errors and landform_mirror_ok else "Permafrost or glacial-landform membership, ranges, or summary mirrors are inconsistent.",
        observed={"errors": landform_errors[:18], "summary_mismatches": landform_mirror_errors},
        expected="exact eligible-cell partitions and bounded diagnostics",
    )


def _validate_subsurface_water(
    checks: list[Check], world: dict[str, Any], cells: list[Record], cells_by_id: dict[int, Record], summary: Record
) -> None:
    domain = "aquifers_wetlands_karst"
    aquifer_model, aquifer_model_ok = _dict_payload(world, "aquifer_resource_model")
    recharge_model, recharge_model_ok = _dict_payload(world, "groundwater_recharge_model")
    natural_aquifer = aquifer_model.get("model_type") == "natural_recharge_causal_aquifer_resources_v2"
    limitation_field = "aquifer_natural_limitation_index" if natural_aquifer else "aquifer_extraction_risk_index"
    aquifers, aquifer_shape = _records(world, "aquifer_systems")
    errors: list[str] = []
    if not aquifer_model_ok or not recharge_model_ok or not aquifer_shape or not _sequential_ids(aquifers):
        errors.append("aquifer models/system structure")
    assigned: set[int] = set()
    for system in aquifers:
        system_id = _int(system.get("id"))
        cell_ids, unique = _id_list(system.get("cell_ids"))
        if not unique or not cell_ids or any(cell_id not in cells_by_id for cell_id in cell_ids):
            errors.append(f"aquifer {system_id}: cell_ids")
            continue
        if assigned.intersection(cell_ids):
            errors.append(f"aquifer {system_id}: overlap")
        assigned.update(cell_ids)
        if _int(system.get("cell_count")) != len(cell_ids) or not _close(system.get("area_km2"), _record_area(system, cells_by_id)):
            errors.append(f"aquifer {system_id}: count/area")
        if _int(system.get("basin_id")) != _int(cells_by_id[cell_ids[0]].get("basin_id")) or any(_int(cells_by_id[cell_id].get("basin_id")) != _int(system.get("basin_id")) for cell_id in cell_ids):
            errors.append(f"aquifer {system_id}: basin source")
        for cell_id in cell_ids:
            if _int(cells_by_id[cell_id].get("aquifer_system_id")) != system_id:
                errors.append(f"aquifer {system_id}: cell mirror {cell_id}")
        for field in ("mean_aquifer_storage_index", "mean_aquifer_quality_index", "mean_aquifer_productivity_index", "mean_" + limitation_field, "closed_basin_fraction"):
            if not _bounded(system.get(field)):
                errors.append(f"aquifer {system_id}: {field}")
        for field in ("mean_groundwater_recharge_mm_y", "total_groundwater_recharge_km3_y"):
            if not _nonnegative(system.get(field)):
                errors.append(f"aquifer {system_id}: {field}")
    if assigned != {_int(cell.get("id")) for cell in cells if _int(cell.get("aquifer_system_id")) >= 0}:
        errors.append("aquifer assignment inverse")
    for cell in cells:
        for field in ("aquifer_storage_index", "aquifer_quality_index", "aquifer_productivity_index", limitation_field, "groundwater_recharge_fraction"):
            if not _bounded(cell.get(field)):
                errors.append(f"cell {_int(cell.get('id'))}: {field}")
        for field in ("groundwater_recharge_mm_y", "groundwater_recharge_km3_y", "vadose_zone_retention_km3_y"):
            if not _nonnegative(cell.get(field)):
                errors.append(f"cell {_int(cell.get('id'))}: {field}")
    aquifer_mirror_ok, aquifer_mirror_errors = _all_summary_mirrors(
        summary,
        {"aquifer_system_count": len(aquifers), "aquifer_cell_count": sum(1 for cell in cells if str(cell.get("aquifer_class")) != "marine_excluded")},
    )
    model_totals_ok = (
        _summary_matches(aquifer_model, "aquifer_system_count", len(aquifers))
        and _summary_matches(aquifer_model, "aquifer_cell_count", sum(1 for cell in cells if str(cell.get("aquifer_class")) != "marine_excluded"))
        and bool(recharge_model.get("mass_conserving_source_partition"))
        and abs(_number(recharge_model.get("mass_balance_residual_km3_y"), math.inf)) <= 1.0e-6
    )
    _add(
        checks,
        domain=domain,
        name="aquifer_membership_models_and_ranges",
        passed=not errors and aquifer_mirror_ok and model_totals_ok,
        message="Aquifer systems mirror basin cells, bounded properties, and conservative recharge metadata." if not errors and aquifer_mirror_ok and model_totals_ok else "Aquifer membership, properties, recharge metadata, or summary mirrors are inconsistent.",
        observed={"errors": errors[:18], "summary_mismatches": aquifer_mirror_errors},
        expected="exact basin systems with bounded indices and conservative recharge partition",
    )

    wetlands, wetland_shape = _records(world, "wetland_systems")
    karst, karst_shape = _records(world, "karst_systems")
    watershed_ids = set(range(len(_records(world, "watersheds")[0])))
    wetland_errors: list[str] = []
    for key, records, shape, cell_field, type_field, none_type in (
        ("wetland", wetlands, wetland_shape, "wetland_system_id", "wetland_system_type", "none"),
        ("karst", karst, karst_shape, "karst_system_id", None, None),
    ):
        if not shape or not _sequential_ids(records):
            wetland_errors.append(f"{key}: structure/IDs")
        assigned_ids: set[int] = set()
        for record in records:
            record_id = _int(record.get("id"))
            cell_ids, unique = _id_list(record.get("cell_ids"))
            if not unique or not cell_ids or any(cell_id not in cells_by_id for cell_id in cell_ids):
                wetland_errors.append(f"{key} {record_id}: cell_ids")
                continue
            if assigned_ids.intersection(cell_ids):
                wetland_errors.append(f"{key} {record_id}: overlap")
            assigned_ids.update(cell_ids)
            if _int(record.get("cell_count")) != len(cell_ids) or not _close(record.get("area_km2"), _record_area(record, cells_by_id)):
                wetland_errors.append(f"{key} {record_id}: count/area")
            for cell_id in cell_ids:
                cell = cells_by_id[cell_id]
                if _int(cell.get(cell_field)) != record_id or (type_field is not None and str(cell.get(type_field, none_type)) == none_type):
                    wetland_errors.append(f"{key} {record_id}: cell mirror {cell_id}")
            if key == "wetland":
                linked_watersheds, linked_unique = _id_list(record.get("linked_watershed_ids"))
                if not linked_unique or any(watershed_id not in watershed_ids for watershed_id in linked_watersheds):
                    wetland_errors.append(f"wetland {record_id}: watersheds")
            else:
                linked_aquifers, linked_unique = _id_list(record.get("aquifer_system_ids"))
                if not linked_unique or any(aquifer_id not in set(range(len(aquifers))) for aquifer_id in linked_aquifers):
                    wetland_errors.append(f"karst {record_id}: aquifers")
        expected_ids = {_int(cell.get("id")) for cell in cells if _int(cell.get(cell_field)) >= 0}
        if assigned_ids != expected_ids:
            wetland_errors.append(f"{key}: assignment inverse")
    for cell in cells:
        for field in ("wetland_extent_index", "wetland_hydrology_index", "wetland_soil_saturation_index", "wetland_ecotone_index", "wetland_connectivity_index", "karst_potential_index", "cave_development_index", "subterranean_drainage_fraction"):
            if not _bounded(cell.get(field)):
                wetland_errors.append(f"cell {_int(cell.get('id'))}: {field}")
    wetland_mirror_ok, wetland_mirror_errors = _all_summary_mirrors(
        summary,
        {
            "wetland_system_count": len(wetlands),
            "wetland_cell_count": sum(1 for cell in cells if str(cell.get("wetland_system_type", "none")) != "none"),
            "karst_system_count": len(karst),
            "karst_cell_count": sum(1 for cell in cells if _number(cell.get("karst_potential_index"), -1.0) >= 0.45),
        },
    )
    _add(
        checks,
        domain=domain,
        name="wetland_karst_membership_and_sources",
        passed=not wetland_errors and wetland_mirror_ok,
        message="Wetland and karst systems mirror bounded cell diagnostics and valid watershed/aquifer sources." if not wetland_errors and wetland_mirror_ok else "Wetland or karst memberships, source links, ranges, or summary mirrors are inconsistent.",
        observed={"errors": wetland_errors[:18], "summary_mismatches": wetland_mirror_errors},
        expected="exact system assignment inverse and valid natural source links",
    )


def _validate_ecosystems(
    checks: list[Check], world: dict[str, Any], cells: list[Record], cells_by_id: dict[int, Record], summary: Record
) -> None:
    domain = "ecosystems_reefs_species_wildfire"
    parent_model = world.get("ecosystem_dynamics_model")
    parent_name = parent_model.get("model") if isinstance(parent_model, dict) else None
    succession, succession_shape = _records(world, "vegetation_succession_histories")
    renewables, renewable_shape = _records(world, "renewable_resource_records")
    errors: list[str] = validate_aquatic_climate_support(world)
    if not succession_shape or not renewable_shape or not _sequential_ids(succession) or not _sequential_ids(renewables):
        errors.append("succession/resource structure or IDs")
    seen_cells: set[int] = set()
    for history in succession:
        history_id = _int(history.get("id"))
        cell_id = _int(history.get("cell_id"))
        steps = history.get("steps")
        if cell_id not in cells_by_id or cell_id in seen_cells or not isinstance(steps, list) or not steps or not all(isinstance(step, dict) for step in steps):
            errors.append(f"succession {history_id}: source/steps")
            continue
        seen_cells.add(cell_id)
        if _int(history.get("step_count")) != len(steps) or history.get("initial_succession_stage") != steps[0].get("succession_stage") or history.get("final_succession_stage") != steps[-1].get("succession_stage"):
            errors.append(f"succession {history_id}: step/endpoints")
        for index, step in enumerate(steps):
            for field in ("primary_productivity_index", "biomass_index", "canopy_closure_index", "disturbance_pressure_index", "wildfire_spread_risk_index", "recovery_fraction"):
                if not _bounded(step.get(field)):
                    errors.append(f"succession {history_id}: {field} {index}")
            if not _nonnegative(step.get("years_since_start")):
                errors.append(f"succession {history_id}: years {index}")
    for resource in renewables:
        resource_id = _int(resource.get("id"))
        if _int(resource.get("cell_id")) not in cells_by_id or str(resource.get("resource_type", "")) not in {"forest_growth", "fishery_productivity"}:
            errors.append(f"renewable {resource_id}: source/type")
        for field in ("productivity_index", "sustainable_yield_index", "climate_dependency_index", "water_dependency_index", "disturbance_risk_index"):
            if not _bounded(resource.get(field)):
                errors.append(f"renewable {resource_id}: {field}")
        if _int(resource.get("regeneration_years"), -1) < 1:
            errors.append(f"renewable {resource_id}: regeneration")
    for cell in cells:
        for field in ("primary_productivity_index", "vegetation_biomass_index", "species_richness_index", "wildfire_spread_risk_index", "ecosystem_disturbance_pressure_index", "forest_growth_index", "fishery_productivity_index"):
            if not _bounded(cell.get(field)):
                errors.append(f"cell {_int(cell.get('id'))}: {field}")
    ecosystem_mirror_ok, ecosystem_mirror_errors = _all_summary_mirrors(
        summary,
        {
            "vegetation_succession_history_count": len(succession),
            "vegetation_succession_step_count": sum(len(history.get("steps", [])) for history in succession if isinstance(history.get("steps"), list)),
            "renewable_resource_record_count": len(renewables),
        },
    )
    _add(
        checks,
        domain=domain,
        name="succession_and_renewable_sources",
        passed=not errors and ecosystem_mirror_ok,
        message="Succession and renewable records link bounded cells and satisfy their declared climate and parent availability." if not errors and ecosystem_mirror_ok else "Climate or parent availability, ecosystem metadata, succession, renewable sources, values, or summary mirrors are inconsistent.",
        observed={"errors": errors[:18], "summary_mismatches": ecosystem_mirror_errors},
        expected="unique cell-linked succession histories and bounded resource records",
    )

    reefs, reef_shape = _records(world, "reef_systems")
    reef_errors: list[str] = validate_reef_thermal_habitat(world)
    reef_model = world.get("reef_diagnostics_model")
    native_reef = (
        isinstance(reef_model, dict)
        and reef_model.get("model") == "heuristic_coastal_reef_native_seasonal_v3"
    )
    # The independent thermal helper validates this version and forbids its
    # unavailable bleaching aliases. Preserve all remaining range checks.
    reef_cell_fields = ("reef_growth_index", "reef_sediment_stress_index", "reef_wave_exposure_index", "reef_island_support_index")
    if not native_reef:
        reef_cell_fields += ("reef_bleaching_risk_index",)
    if not reef_shape or not _sequential_ids(reefs):
        reef_errors.append("reef structure/IDs")
    assigned: set[int] = set()
    renewable_ids = set(range(len(renewables)))
    for reef in reefs:
        reef_id = _int(reef.get("id"))
        cell_ids, unique = _id_list(reef.get("cell_ids"))
        if not unique or not cell_ids or any(cell_id not in cells_by_id for cell_id in cell_ids):
            reef_errors.append(f"reef {reef_id}: cell_ids")
            continue
        if assigned.intersection(cell_ids):
            reef_errors.append(f"reef {reef_id}: overlap")
        assigned.update(cell_ids)
        if _int(reef.get("cell_count")) != len(cell_ids) or not _close(reef.get("area_km2"), _record_area(reef, cells_by_id)):
            reef_errors.append(f"reef {reef_id}: count/area")
        for cell_id in cell_ids:
            cell = cells_by_id[cell_id]
            if _int(cell.get("reef_system_id")) != reef_id or _number(cell.get("reef_growth_index"), -1.0) < 0.46:
                reef_errors.append(f"reef {reef_id}: cell mirror {cell_id}")
        fishery_ids, linked_unique = _id_list(reef.get("fishery_resource_record_ids"))
        if not linked_unique or any(resource_id not in renewable_ids for resource_id in fishery_ids):
            reef_errors.append(f"reef {reef_id}: fishery sources")
        for field in (f"mean_{field}" for field in reef_cell_fields):
            if not _bounded(reef.get(field)):
                reef_errors.append(f"reef {reef_id}: {field}")
    if assigned != {_int(cell.get("id")) for cell in cells if _int(cell.get("reef_system_id")) >= 0}:
        reef_errors.append("reef assignment inverse")
    for cell in cells:
        for field in reef_cell_fields:
            if not _bounded(cell.get(field)):
                reef_errors.append(f"cell {_int(cell.get('id'))}: {field}")
    reef_mirror_ok, reef_mirror_errors = _all_summary_mirrors(
        summary,
        {"reef_system_count": len(reefs), "reef_cell_count": len(assigned), "reef_total_area_km2": sum(_number(reef.get("area_km2"), 0.0) for reef in reefs)},
    )
    _add(
        checks,
        domain=domain,
        name="reef_membership_sources_and_ranges",
        passed=not reef_errors and reef_mirror_ok,
        message="Reef systems mirror bounded cells, natural sources, and any declared thermal habitat model." if not reef_errors and reef_mirror_ok else "Reef thermal eligibility, model metadata, membership, source links, ranges, or summary mirrors are inconsistent.",
        observed={"errors": reef_errors[:15], "summary_mismatches": reef_mirror_errors},
        expected="present registry with exact candidate assignment inverse",
    )

    species, species_shape = _records(world, "species_range_records")
    species_errors: list[str] = validate_species_habitat_support(world)
    species_model = world.get("species_ranges_model")
    if parent_name == "heuristic_ecosystem_climate_support_v4" and (not isinstance(species_model, dict) or species_model.get("model") != "heuristic_species_parent_support_v3"):
        species_errors.append("ecosystem v4 requires the species parent-support v3 consumer declaration")
    if parent_name == "heuristic_ecosystem_climate_support_v5" and (not isinstance(species_model, dict) or species_model.get("model") != "heuristic_species_parent_support_v4"):
        species_errors.append("ecosystem v5 requires the species parent-support v4 consumer declaration")
    if not species_shape or not _sequential_ids(species):
        species_errors.append("species range structure/IDs")
    inverse: dict[int, set[int]] = {cell_id: set() for cell_id in cells_by_id}
    wetland_ids = set(range(len(_records(world, "wetland_systems")[0])))
    reef_ids = set(range(len(reefs)))
    aquifer_ids = set(range(len(_records(world, "aquifer_systems")[0])))
    for record in species:
        record_id = _int(record.get("id"))
        cell_ids, unique = _id_list(record.get("cell_ids"))
        if not unique or not cell_ids or any(cell_id not in cells_by_id for cell_id in cell_ids):
            species_errors.append(f"range {record_id}: cell_ids")
            continue
        if _int(record.get("cell_count")) != len(cell_ids) or not _close(record.get("area_km2"), _record_area(record, cells_by_id)):
            species_errors.append(f"range {record_id}: count/area")
        for cell_id in cell_ids:
            inverse[cell_id].add(record_id)
        for field, valid_ids in (("wetland_system_ids", wetland_ids), ("reef_system_ids", reef_ids), ("aquifer_system_ids", aquifer_ids)):
            linked, linked_unique = _id_list(record.get(field))
            if not linked_unique or any(linked_id not in valid_ids for linked_id in linked):
                species_errors.append(f"range {record_id}: {field}")
        for field in ("mean_habitat_suitability_index", "max_habitat_suitability_index", "mean_species_richness_index", "mean_primary_productivity_index", "mean_disturbance_pressure_index", "mean_composition_confidence_index", "range_fragmentation_index", "endemism_index", "conservation_stress_index"):
            if not _bounded(record.get(field)):
                species_errors.append(f"range {record_id}: {field}")
        envelope = record.get("climate_envelope")
        if not isinstance(envelope, dict) or not all(_finite(envelope.get(field)) for field in ("min_temperature_c", "mean_temperature_c", "max_temperature_c", "min_precipitation_mm_y", "mean_precipitation_mm_y", "max_precipitation_mm_y")):
            species_errors.append(f"range {record_id}: climate envelope")
        elif not (float(envelope["min_temperature_c"]) <= float(envelope["mean_temperature_c"]) <= float(envelope["max_temperature_c"]) and 0.0 <= float(envelope["min_precipitation_mm_y"]) <= float(envelope["mean_precipitation_mm_y"]) <= float(envelope["max_precipitation_mm_y"])):
            species_errors.append(f"range {record_id}: climate envelope order")
    for cell_id, expected_ids in inverse.items():
        observed_ids, unique = _id_list(cells_by_id[cell_id].get("species_range_record_ids"))
        if not unique or set(observed_ids) != expected_ids:
            species_errors.append(f"cell {cell_id}: species inverse")
    species_mirror_ok, species_mirror_errors = _all_summary_mirrors(
        summary,
        {"species_range_record_count": len(species), "species_range_cell_count": sum(1 for ids in inverse.values() if ids), "species_range_total_area_km2": sum(_number(record.get("area_km2"), 0.0) for record in species)},
    )
    _add(
        checks,
        domain=domain,
        name="species_range_inverse_links_and_envelopes",
        passed=not species_errors and species_mirror_ok,
        message="Species ranges invert cell assignments and link valid habitats with ordered climate envelopes." if not species_errors and species_mirror_ok else "Species range assignments, habitat sources, envelopes, or summary mirrors are inconsistent.",
        observed={"errors": species_errors[:18], "summary_mismatches": species_mirror_errors},
        expected="exact many-to-many cell inverse and bounded habitat records",
    )

    wildfires, wildfire_shape = _records(world, "wildfire_spread_histories")
    wildfire_errors: list[str] = validate_wildfire_aquatic_exclusion(world)
    fire_model = world.get("wildfire_disturbance_model")
    if parent_name == "heuristic_ecosystem_climate_support_v5" and (
        not isinstance(fire_model, dict) or fire_model.get("model") not in (
            "heuristic_wildfire_prescribed_natural_parent_availability_v6",
            "heuristic_wildfire_native_seasonal_prescribed_natural_parent_availability_v7",
        )
    ):
        wildfire_errors.append("ecosystem v5 requires its prescribed-natural wildfire consumer declaration")
    if not wildfire_shape or not _sequential_ids(wildfires):
        wildfire_errors.append("wildfire structure/IDs")
    fire_inverse: dict[int, set[int]] = {cell_id: set() for cell_id in cells_by_id}
    for history in wildfires:
        history_id = _int(history.get("id"))
        cell_ids, unique = _id_list(history.get("cell_ids"))
        steps = history.get("steps")
        if not unique or not cell_ids or any(cell_id not in cells_by_id for cell_id in cell_ids) or _int(history.get("ignition_cell_id")) not in cell_ids:
            wildfire_errors.append(f"wildfire {history_id}: cells/ignition")
            continue
        if _int(history.get("cell_count")) != len(cell_ids) or not _close(history.get("area_km2"), _record_area(history, cells_by_id)):
            wildfire_errors.append(f"wildfire {history_id}: count/area")
        for cell_id in cell_ids:
            fire_inverse[cell_id].add(history_id)
        if not isinstance(steps, list) or not all(isinstance(step, dict) for step in steps) or _int(history.get("spread_step_count")) != len(steps):
            wildfire_errors.append(f"wildfire {history_id}: steps")
            continue
        previous_count = 0
        for index, step in enumerate(steps):
            active, active_unique = _id_list(step.get("active_front_cell_ids"))
            new, new_unique = _id_list(step.get("newly_burned_cell_ids"))
            cumulative = _int(step.get("cumulative_burned_cell_count"), -1)
            if not active_unique or not new_unique or any(cell_id not in cell_ids for cell_id in active + new):
                wildfire_errors.append(f"wildfire {history_id}: step cells {index}")
            if cumulative < previous_count or cumulative > len(cell_ids):
                wildfire_errors.append(f"wildfire {history_id}: cumulative count {index}")
            previous_count = cumulative
            for field in ("mean_spread_probability_index", "containment_index"):
                if not _bounded(step.get(field)):
                    wildfire_errors.append(f"wildfire {history_id}: {field} {index}")
            if not _nonnegative(step.get("burned_area_km2")):
                wildfire_errors.append(f"wildfire {history_id}: burned area {index}")
        for field in ("max_spread_probability_index", "containment_index", "mean_wildfire_spread_risk_index", "mean_ignition_potential_index", "mean_fuel_continuity_index", "mean_wind_alignment_index", "mean_firebreak_index", "mean_ecosystem_disturbance_pressure_index"):
            if not _bounded(history.get(field)):
                wildfire_errors.append(f"wildfire {history_id}: {field}")
    for cell_id, expected_ids in fire_inverse.items():
        observed_ids, unique = _id_list(cells_by_id[cell_id].get("wildfire_spread_history_ids"))
        if not unique or set(observed_ids) != expected_ids:
            wildfire_errors.append(f"cell {cell_id}: wildfire inverse")
    wildfire_mirror_ok, wildfire_mirror_errors = _all_summary_mirrors(
        summary,
        {
            "wildfire_spread_history_count": len(wildfires),
            "wildfire_disturbance_cell_count": sum(1 for ids in fire_inverse.values() if ids),
            "wildfire_spread_step_count": sum(len(history.get("steps", [])) for history in wildfires if isinstance(history.get("steps"), list)),
            "wildfire_total_burned_area_km2": sum(_number(history.get("area_km2"), 0.0) for history in wildfires),
        },
    )
    _add(
        checks,
        domain=domain,
        name="wildfire_inverse_links_and_steps",
        passed=not wildfire_errors and wildfire_mirror_ok,
        message="Wildfire histories retain valid habitat sources, inverse cell links and bounded monotonic spread steps." if not wildfire_errors and wildfire_mirror_ok else "Wildfire habitat sources, cell links, spread steps, ranges, or summary mirrors are inconsistent.",
        observed={"errors": wildfire_errors[:18], "summary_mismatches": wildfire_mirror_errors},
        expected="versioned habitat and parent availability, explicit examined-front coverage, and exact cell/history inverse with bounded monotonic steps",
    )


def _validate_resources(
    checks: list[Check], world: dict[str, Any], cells: list[Record], cells_by_id: dict[int, Record], summary: Record
) -> None:
    domain = "geologic_resources"
    geo_only = world.get("generation_scope") == "geo_only"
    positive_flow = sorted(
        max(0.0, _number(cell.get("flow_accumulation"), 0.0))
        for cell in cells
        if max(0.0, _number(cell.get("flow_accumulation"), 0.0)) > 0.0
    )
    expected_flow_scale = (
        max(1.0, positive_flow[int(0.95 * (len(positive_flow) - 1))])
        if positive_flow
        else 1.0
    )
    deposit_model, deposit_model_shape = _dict_payload(
        world, "resource_deposit_model"
    )
    deposits, deposit_shape = _records(world, "resource_deposits")
    deposit_errors: list[str] = validate_biological_resources(world, include_commodities=False)
    available_economics = deposit_model.get("model_type") == "causal_geologic_resource_deposit_diagnostics_v5"
    if not deposit_shape or not _sequential_ids(deposits):
        deposit_errors.append("deposit structure/IDs")
    if (
        not deposit_model_shape
        or deposit_model.get("model_type") not in (
            "causal_geologic_resource_deposit_diagnostics_v2",
            "causal_geologic_resource_deposit_diagnostics_v3",
            "causal_geologic_resource_deposit_diagnostics_v4",
            "causal_geologic_resource_deposit_diagnostics_v5",
        )
        or deposit_model.get("flow_accumulation_normalization_model")
        != "positive_cell_p95_v1"
        or not _close(
            deposit_model.get("flow_accumulation_scale"),
            expected_flow_scale,
            absolute=1.0e-4,
        )
        or deposit_model.get("physical_time_resolved") is not False
    ):
        deposit_errors.append("resource flow normalization model")
    deposit_by_id = {_int(deposit.get("id")): deposit for deposit in deposits}
    for deposit in deposits:
        deposit_id = _int(deposit.get("id"))
        cell_id = _int(deposit.get("cell_id"))
        if cell_id not in cells_by_id:
            deposit_errors.append(f"deposit {deposit_id}: cell source")
            continue
        cell = cells_by_id[cell_id]
        resource = str(cell.get("resource", "none"))
        expected_reserve = _replay_resource_reserve(
            resource, cell, expected_flow_scale
        )
        expected_hazard = _replay_resource_hazard(cell)
        expected_confidence = _replay_resource_confidence(
            resource, cell, expected_reserve, expected_flow_scale
        )
        replay_fields = {
            "reserve_potential_index": expected_reserve,
            "extraction_hazard_index": expected_hazard,
            "geologic_confidence_index": expected_confidence,
        }
        if geo_only:
            expected_accessibility = _replay_resource_accessibility(cell)
            expected_renewability = (
                0.78
                if resource in AGRICULTURAL_RESOURCES
                else (0.32 if resource == "geothermal" else 0.02)
            )
            expected_viability = max(
                0.0,
                min(
                    1.0,
                    expected_reserve * 0.46
                    + expected_accessibility * 0.30
                    + expected_confidence * 0.20
                    - expected_hazard * 0.18
                    + expected_renewability * 0.10,
                ),
            )
            replay_fields.update(
                {
                    ("geographic_accessibility_baseline_index" if available_economics else "accessibility_index"): expected_accessibility,
                    ("geographic_economic_viability_baseline_index" if available_economics else "economic_viability_index"): expected_viability,
                    "renewability_index": expected_renewability,
                }
            )
        if str(deposit.get("resource", "")) != resource:
            deposit_errors.append(f"deposit {deposit_id}: resource mirror")
        for field, expected_value in replay_fields.items():
            if not _close(
                deposit.get(field), expected_value, absolute=3.0e-6
            ):
                deposit_errors.append(f"deposit {deposit_id}: {field} replay")
        if not _close(deposit.get("area_km2"), cell.get("area_km2")):
            deposit_errors.append(f"deposit {deposit_id}: area source")
        for field in (
            "reserve_potential_index",
            "geologic_confidence_index",
            "renewability_index",
            "extraction_hazard_index",
        ):
            if not _bounded(deposit.get(field)):
                deposit_errors.append(f"deposit {deposit_id}: {field}")
        if geo_only:
            for field in (("geographic_accessibility_baseline_index", "geographic_economic_viability_baseline_index") if available_economics else ("accessibility_index", "economic_viability_index")):
                if not _bounded(deposit.get(field)):
                    deposit_errors.append(f"deposit {deposit_id}: {field}")
        if not isinstance(deposit.get("formation_evidence"), dict) or not str(deposit.get("resource", "")):
            deposit_errors.append(f"deposit {deposit_id}: formation evidence/resource")
    deposit_summary_expected: dict[str, Any] = {
        "resource_deposit_count": len(deposits),
        "resource_deposit_total_area_km2": float(
            sum(
                _number(deposit.get("area_km2"), 0.0)
                for deposit in deposits
            )
        ),
    }
    if geo_only:
        divisor = len(deposits) if deposits else 1
        deposit_summary_expected.update(
            {
                "mean_resource_reserve_potential_index": sum(
                    _number(deposit.get("reserve_potential_index"), 0.0)
                    for deposit in deposits
                ) / divisor,
                "mean_resource_geologic_confidence_index": sum(
                    _number(deposit.get("geologic_confidence_index"), 0.0)
                    for deposit in deposits
                ) / divisor,
            }
        )
        if not available_economics:
            deposit_summary_expected["mean_resource_economic_viability_index"] = sum(
                _number(deposit.get("economic_viability_index"), 0.0) for deposit in deposits
            ) / divisor
        # Current economic and geographic means are checked separately by the
        # independent access audit. Unavailable economics never enter a sum.
    deposit_mirror_ok, deposit_mirror_errors = _all_summary_mirrors(
        summary, deposit_summary_expected
    )
    _add(
        checks,
        domain=domain,
        name="resource_deposit_sources_and_ranges",
        passed=not deposit_errors and deposit_mirror_ok,
        message="Resource deposits link valid cells with bounded formation and viability diagnostics." if not deposit_errors and deposit_mirror_ok else "Resource deposit sources, values, or summary mirrors are inconsistent.",
        observed={"errors": deposit_errors[:18], "summary_mismatches": deposit_mirror_errors},
        expected="sequential cell-linked deposits with bounded indices",
    )

    ore_model, ore_model_shape = _dict_payload(world, "ore_genesis_model")
    ore, ore_shape = _records(world, "ore_genesis_systems")
    ore_errors: list[str] = validate_ore_resource_availability(world) if available_economics else []
    if not ore_shape or not _sequential_ids(ore):
        ore_errors.append("ore system structure/IDs")
    if (
        not ore_model_shape
        or ore_model.get("model_type")
        != ("causal_tectonic_lithologic_ore_genesis_diagnostics_v3" if available_economics else "causal_tectonic_lithologic_ore_genesis_diagnostics_v2")
        or ore_model.get("flow_accumulation_normalization_model")
        != "positive_cell_p95_v1"
        or not _close(
            ore_model.get("flow_accumulation_scale"),
            expected_flow_scale,
            absolute=1.0e-4,
        )
        or ore_model.get("physical_time_resolved") is not False
    ):
        ore_errors.append("ore flow normalization model")
    assigned: set[int] = set()
    fault_ids = set(range(len(_records(world, "fault_systems")[0])))
    zone_ids = {
        _int(zone.get("id"))
        for key in ("collision_zones", "subduction_zones", "rift_zones")
        for zone in _records(world, key)[0]
    }
    expected_ore_by_cell = {
        _int(cell.get("id")): _replay_ore_cell_indices(
            cell, expected_flow_scale
        )
        for cell in cells
    }
    ore_cell_fields = {
        "ore_genesis_potential_index": "ore",
        "hydrothermal_alteration_index": "hydrothermal",
        "metallogenic_fertility_index": "fertility",
        "ore_structural_control_index": "structural",
        "placer_concentration_index": "placer",
    }
    for cell_id, expected_indices in expected_ore_by_cell.items():
        cell = cells_by_id[cell_id]
        for field, expected_key in ore_cell_fields.items():
            if not _close(
                cell.get(field),
                expected_indices[expected_key],
                absolute=3.0e-6,
            ):
                ore_errors.append(f"cell {cell_id}: {field} replay")
    for system in ore:
        system_id = _int(system.get("id"))
        cell_ids, unique = _id_list(system.get("cell_ids"))
        deposit_ids, deposits_unique = _id_list(system.get("resource_deposit_ids"))
        if not unique or not cell_ids or any(cell_id not in cells_by_id for cell_id in cell_ids):
            ore_errors.append(f"ore {system_id}: cell_ids")
            continue
        if assigned.intersection(cell_ids):
            ore_errors.append(f"ore {system_id}: overlap")
        assigned.update(cell_ids)
        if _int(system.get("cell_count")) != len(cell_ids) or not _close(system.get("area_km2"), _record_area(system, cells_by_id)):
            ore_errors.append(f"ore {system_id}: count/area")
        if not deposits_unique or _int(system.get("resource_deposit_count")) != len(deposit_ids) or any(deposit_id not in deposit_by_id or _int(deposit_by_id[deposit_id].get("cell_id")) not in cell_ids for deposit_id in deposit_ids):
            ore_errors.append(f"ore {system_id}: deposit sources")
        if _int(system.get("representative_cell_id")) not in cell_ids:
            ore_errors.append(f"ore {system_id}: representative")
        for field, valid in (("fault_system_ids", fault_ids), ("tectonic_zone_ids", zone_ids)):
            linked, linked_unique = _id_list(system.get(field))
            if not linked_unique or any(linked_id not in valid for linked_id in linked):
                ore_errors.append(f"ore {system_id}: {field}")
        for cell_id in cell_ids:
            if _int(cells_by_id[cell_id].get("ore_genesis_system_id")) != system_id:
                ore_errors.append(f"ore {system_id}: cell mirror {cell_id}")
        for field in ("mean_ore_genesis_potential_index", "max_ore_genesis_potential_index", "mean_hydrothermal_alteration_index", "mean_metallogenic_fertility_index", "mean_ore_structural_control_index", "mean_placer_concentration_index", "ore_genesis_confidence_index"):
            if not _bounded(system.get(field)):
                ore_errors.append(f"ore {system_id}: {field}")
        if geo_only and not available_economics and not _bounded(system.get("mean_resource_viability_index")):
            ore_errors.append(
                f"ore {system_id}: mean_resource_viability_index"
            )
        expected_system_fields = {
            "mean_ore_genesis_potential_index": sum(
                expected_ore_by_cell[cell_id]["ore"] for cell_id in cell_ids
            ) / len(cell_ids),
            "max_ore_genesis_potential_index": max(
                expected_ore_by_cell[cell_id]["ore"] for cell_id in cell_ids
            ),
            "mean_hydrothermal_alteration_index": sum(
                expected_ore_by_cell[cell_id]["hydrothermal"]
                for cell_id in cell_ids
            ) / len(cell_ids),
            "mean_metallogenic_fertility_index": sum(
                expected_ore_by_cell[cell_id]["fertility"]
                for cell_id in cell_ids
            ) / len(cell_ids),
            "mean_ore_structural_control_index": sum(
                expected_ore_by_cell[cell_id]["structural"]
                for cell_id in cell_ids
            ) / len(cell_ids),
            "mean_placer_concentration_index": sum(
                expected_ore_by_cell[cell_id]["placer"] for cell_id in cell_ids
            ) / len(cell_ids),
        }
        expected_system_fields["ore_genesis_confidence_index"] = max(
            0.0,
            min(
                1.0,
                expected_system_fields["mean_ore_genesis_potential_index"]
                * 0.34
                + expected_system_fields["mean_hydrothermal_alteration_index"]
                * 0.14
                + expected_system_fields[
                    "mean_metallogenic_fertility_index"
                ]
                * 0.16
                + expected_system_fields[
                    "mean_ore_structural_control_index"
                ]
                * 0.12
                + min(1.0, len(deposit_ids) / float(len(cell_ids))) * 0.16
                + min(1.0, len(_id_list(system.get("plate_ids"))[0]) / 3.0)
                * 0.08,
            ),
        )
        if geo_only and not available_economics:
            expected_system_fields["mean_resource_viability_index"] = (
                sum(
                    _number(
                        deposit_by_id[deposit_id].get(
                            "economic_viability_index"
                        ),
                        0.0,
                    )
                    for deposit_id in deposit_ids
                )
                / len(deposit_ids)
                if deposit_ids
                else 0.0
            )
        for field, expected_value in expected_system_fields.items():
            if not _close(system.get(field), expected_value, absolute=3.0e-6):
                ore_errors.append(f"ore {system_id}: {field} replay")
        steps = system.get("formation_steps")
        if not isinstance(steps, list) or not all(isinstance(step, dict) for step in steps) or _int(system.get("formation_step_count")) != len(steps):
            ore_errors.append(f"ore {system_id}: formation steps")
        else:
            for step_index, step in enumerate(steps):
                active_ids, active_unique = _id_list(step.get("active_cell_ids"))
                linked_deposits, linked_unique = _id_list(step.get("linked_resource_deposit_ids"))
                if not active_unique or any(cell_id not in cell_ids for cell_id in active_ids) or _int(step.get("active_cell_count")) != len(active_ids):
                    ore_errors.append(f"ore {system_id}: step cells {step_index}")
                if not linked_unique or any(deposit_id not in deposit_ids for deposit_id in linked_deposits):
                    ore_errors.append(f"ore {system_id}: step deposits {step_index}")
                if not _bounded(step.get("mean_ore_genesis_potential_index")) or not _bounded(step.get("mean_process_intensity_index")):
                    ore_errors.append(f"ore {system_id}: step values {step_index}")
                expected_linked_deposits = sorted(
                    deposit_id
                    for deposit_id in deposit_ids
                    if _int(deposit_by_id[deposit_id].get("cell_id"))
                    in set(active_ids)
                )
                metric_fields = {
                    "metallogenic_fertility": "metallogenic_fertility_index",
                    "placer_concentration": "placer_concentration_index",
                    "hydrothermal_alteration": "hydrothermal_alteration_index",
                    "ore_structural_control": "ore_structural_control_index",
                }
                process_field = metric_fields.get(str(step.get("process_metric", "")))
                expected_step_ore = (
                    sum(
                        _number(
                            cells_by_id[cell_id].get(
                                "ore_genesis_potential_index"
                            ),
                            0.0,
                        )
                        for cell_id in active_ids
                    )
                    / len(active_ids)
                    if active_ids
                    else 0.0
                )
                expected_process = (
                    sum(
                        _number(cells_by_id[cell_id].get(process_field), 0.0)
                        for cell_id in active_ids
                    )
                    / len(active_ids)
                    if active_ids and process_field is not None
                    else math.nan
                )
                if (
                    _int(step.get("step_index")) != step_index
                    or linked_deposits != expected_linked_deposits
                    or process_field is None
                    or not _close(
                        step.get("mean_ore_genesis_potential_index"),
                        expected_step_ore,
                        absolute=3.0e-6,
                    )
                    or not _close(
                        step.get("mean_process_intensity_index"),
                        expected_process,
                        absolute=3.0e-6,
                    )
                ):
                    ore_errors.append(f"ore {system_id}: step replay {step_index}")
    if assigned != {_int(cell.get("id")) for cell in cells if _int(cell.get("ore_genesis_system_id")) >= 0}:
        ore_errors.append("ore assignment inverse")
    ore_mirror_ok, ore_mirror_errors = _all_summary_mirrors(
        summary,
        {"ore_genesis_system_count": len(ore), "ore_genesis_cell_count": len(assigned), "ore_genesis_total_area_km2": sum(_number(system.get("area_km2"), 0.0) for system in ore)},
    )
    _add(
        checks,
        domain=domain,
        name="ore_system_membership_and_formation_sources",
        passed=not ore_errors and ore_mirror_ok,
        message="Ore systems mirror candidate cells and link deposits, tectonics, faults, and formation steps." if not ore_errors and ore_mirror_ok else "Ore-system memberships, formation sources, values, or summary mirrors are inconsistent.",
        observed={"errors": ore_errors[:18], "summary_mismatches": ore_mirror_errors},
        expected="exact ore assignment inverse and valid geological sources",
    )

    sedimentary, sedimentary_shape = _records(world, "sedimentary_resource_systems")
    basins, basins_shape = _records(world, "sedimentary_basins")
    columns, columns_shape = _records(world, "stratigraphic_columns")
    transport, transport_shape = _records(world, "sediment_transport_histories")
    sediment_errors: list[str] = []
    if not sedimentary_shape or not basins_shape or not columns_shape or not transport_shape or not _sequential_ids(sedimentary):
        sediment_errors.append("sedimentary systems/source structure")
    basin_by_id = {_int(basin.get("id")): basin for basin in basins}
    column_by_id = {_int(column.get("id")): column for column in columns}
    transport_by_id = {_int(history.get("id")): history for history in transport}
    for system in sedimentary:
        system_id = _int(system.get("id"))
        cell_ids, unique = _id_list(system.get("cell_ids"))
        deposit_ids, deposits_unique = _id_list(system.get("resource_deposit_ids"))
        basin = basin_by_id.get(_int(system.get("sedimentary_basin_id")))
        column = column_by_id.get(_int(system.get("stratigraphic_column_id")))
        history = transport_by_id.get(_int(system.get("sediment_transport_history_id")))
        if not unique or not cell_ids or any(cell_id not in cells_by_id for cell_id in cell_ids):
            sediment_errors.append(f"sedimentary {system_id}: cells")
            continue
        if basin is None or column is None or history is None:
            sediment_errors.append(f"sedimentary {system_id}: basin/column/history source")
        else:
            basin_id = _int(system.get("basin_id"))
            if any(_int(source.get("basin_id")) != basin_id for source in (basin, column, history)):
                sediment_errors.append(f"sedimentary {system_id}: basin source mismatch")
        if _int(system.get("cell_count")) != len(cell_ids) or not _close(system.get("area_km2"), _record_area(system, cells_by_id)):
            sediment_errors.append(f"sedimentary {system_id}: count/area")
        if not deposits_unique or _int(system.get("resource_deposit_count")) != len(deposit_ids) or any(deposit_id not in deposit_by_id or _int(deposit_by_id[deposit_id].get("cell_id")) not in cell_ids for deposit_id in deposit_ids):
            sediment_errors.append(f"sedimentary {system_id}: deposits")
        for field in ("mean_subsidence_index", "source_rock_index", "reservoir_quality_index", "seal_quality_index", "structural_trap_index", "coal_potential_index", "petroleum_potential_index", "gas_potential_index", "evaporite_salt_potential_index", "system_confidence_index"):
            if not _bounded(system.get(field)):
                sediment_errors.append(f"sedimentary {system_id}: {field}")
        for field in ("mean_sediment_thickness_m", "depositional_age_ma"):
            if not _nonnegative(system.get(field)):
                sediment_errors.append(f"sedimentary {system_id}: {field}")
    sedimentary_mirror_ok, sedimentary_mirror_errors = _all_summary_mirrors(
        summary,
        {
            "sedimentary_resource_system_count": len(sedimentary),
            "sedimentary_resource_system_cell_count": len(
                {
                    cell_id
                    for system in sedimentary
                    for cell_id in _id_list(system.get("cell_ids"))[0]
                }
            ),
            "sedimentary_resource_system_total_area_km2": float(
                sum(
                    _number(system.get("area_km2"), 0.0)
                    for system in sedimentary
                )
            ),
        },
    )
    _add(
        checks,
        domain=domain,
        name="sedimentary_system_source_chain",
        passed=not sediment_errors and sedimentary_mirror_ok,
        message="Sedimentary resource systems link coherent basin, column, transport, cell, and deposit sources." if not sediment_errors and sedimentary_mirror_ok else "Sedimentary resource source chains, values, or summary mirrors are inconsistent.",
        observed={"errors": sediment_errors[:18], "summary_mismatches": sedimentary_mirror_errors},
        expected="basin-consistent source chain with bounded system diagnostics",
    )

    petroleum, petroleum_shape = _records(world, "petroleum_migration_systems")
    petroleum_errors: list[str] = []
    if not petroleum_shape or not _sequential_ids(petroleum):
        petroleum_errors.append("petroleum system structure/IDs")
    sedimentary_ids = set(range(len(sedimentary)))
    petroleum_assigned: set[int] = set()
    for system in petroleum:
        system_id = _int(system.get("id"))
        cell_ids, unique = _id_list(system.get("cell_ids"))
        if not unique or not cell_ids or any(cell_id not in cells_by_id for cell_id in cell_ids):
            petroleum_errors.append(f"petroleum {system_id}: cells")
            continue
        if petroleum_assigned.intersection(cell_ids):
            petroleum_errors.append(f"petroleum {system_id}: overlap")
        petroleum_assigned.update(cell_ids)
        source_system_id = _int(system.get("sedimentary_resource_system_id"))
        if source_system_id not in sedimentary_ids:
            petroleum_errors.append(f"petroleum {system_id}: source system")
        else:
            source_system = sedimentary[source_system_id]
            for field in ("sedimentary_basin_id", "basin_id", "stratigraphic_column_id", "sediment_transport_history_id"):
                if _int(system.get(field)) != _int(source_system.get(field)):
                    petroleum_errors.append(f"petroleum {system_id}: {field} source mirror")
        if _int(system.get("cell_count")) != len(cell_ids) or not _close(system.get("area_km2"), _record_area(system, cells_by_id)):
            petroleum_errors.append(f"petroleum {system_id}: count/area")
        cell_set = set(cell_ids)
        for list_field, count_field in (("source_cell_ids", "source_cell_count"), ("migration_cell_ids", "migration_cell_count"), ("reservoir_cell_ids", "reservoir_cell_count"), ("seal_cell_ids", "seal_cell_count"), ("trap_cell_ids", "trap_cell_count")):
            linked, linked_unique = _id_list(system.get(list_field))
            if not linked_unique or not set(linked).issubset(cell_set) or _int(system.get(count_field)) != len(linked):
                petroleum_errors.append(f"petroleum {system_id}: {list_field}")
        for cell_id in cell_ids:
            if _int(cells_by_id[cell_id].get("petroleum_system_id")) != system_id:
                petroleum_errors.append(f"petroleum {system_id}: cell mirror {cell_id}")
        for field in ("mean_source_rock_index", "mean_maturation_index", "mean_migration_path_index", "mean_reservoir_quality_index", "mean_seal_quality_index", "mean_trap_integrity_index", "mean_accumulation_index", "petroleum_potential_index", "gas_potential_index", "migration_efficiency_index", "leakage_risk_index", "confidence_index"):
            if not _bounded(system.get(field)):
                petroleum_errors.append(f"petroleum {system_id}: {field}")
        steps = system.get("migration_steps")
        if not isinstance(steps, list) or not all(isinstance(step, dict) for step in steps) or _int(system.get("path_step_count")) != len(steps):
            petroleum_errors.append(f"petroleum {system_id}: migration steps")
        else:
            for step_index, step in enumerate(steps):
                path, path_unique = _id_list(step.get("path_cell_ids"))
                if not path_unique or not path or not set(path).issubset(cell_set) or not _adjacent(path, cells_by_id):
                    petroleum_errors.append(f"petroleum {system_id}: path {step_index}")
                if _int(step.get("source_cell_id")) != (path[0] if path else -1) or _int(step.get("target_trap_cell_id")) != (path[-1] if path else -1) or _int(step.get("path_length_cell_count")) != len(path):
                    petroleum_errors.append(f"petroleum {system_id}: path endpoints {step_index}")
                for field in ("mean_path_migration_index", "mean_path_trap_integrity_index", "hydrocarbon_charge_index", "leakage_risk_index", "accumulation_probability_index"):
                    if not _bounded(step.get(field)):
                        petroleum_errors.append(f"petroleum {system_id}: {field} {step_index}")
                if not _nonnegative(step.get("migration_distance_km")):
                    petroleum_errors.append(f"petroleum {system_id}: distance {step_index}")
    if petroleum_assigned != {_int(cell.get("id")) for cell in cells if _int(cell.get("petroleum_system_id")) >= 0}:
        petroleum_errors.append("petroleum assignment inverse")
    petroleum_mirror_ok, petroleum_mirror_errors = _all_summary_mirrors(
        summary,
        {"petroleum_migration_system_count": len(petroleum), "petroleum_migration_cell_count": len(petroleum_assigned), "petroleum_migration_total_area_km2": sum(_number(system.get("area_km2"), 0.0) for system in petroleum)},
    )
    _add(
        checks,
        domain=domain,
        name="petroleum_migration_source_paths",
        passed=not petroleum_errors and petroleum_mirror_ok,
        message="Petroleum systems mirror cells and retain basin-consistent adjacent migration paths." if not petroleum_errors and petroleum_mirror_ok else "Petroleum source systems, memberships, migration paths, values, or summary mirrors are inconsistent.",
        observed={"errors": petroleum_errors[:20], "summary_mismatches": petroleum_mirror_errors},
        expected="exact assignment inverse and basin-consistent migration paths",
    )

    occurrences, occurrence_shape = _records(world, "commodity_occurrences")
    occurrence_errors: list[str] = validate_biological_resources(world)
    if not occurrence_shape or not _sequential_ids(occurrences):
        occurrence_errors.append("commodity occurrence structure/IDs")
    for occurrence in occurrences:
        occurrence_id = _int(occurrence.get("id"))
        deposit_id = _int(occurrence.get("resource_deposit_id"))
        deposit = deposit_by_id.get(deposit_id)
        if deposit is None:
            occurrence_errors.append(f"occurrence {occurrence_id}: deposit source")
            continue
        for field in ("cell_id", "basin_id"):
            if _int(occurrence.get(field)) != _int(deposit.get(field)):
                occurrence_errors.append(f"occurrence {occurrence_id}: {field} mirror")
        if str(occurrence.get("source_resource", "")) != str(deposit.get("resource", "")) or str(occurrence.get("formation_process", "")) != str(deposit.get("formation_process", "")):
            occurrence_errors.append(f"occurrence {occurrence_id}: formation mirror")
        if not _close(occurrence.get("area_km2"), deposit.get("area_km2")):
            occurrence_errors.append(f"occurrence {occurrence_id}: area mirror")
        for field in (
            "occurrence_potential_index",
            "extraction_hazard_index",
            "geologic_confidence_index",
        ):
            if not _bounded(occurrence.get(field)):
                occurrence_errors.append(f"occurrence {occurrence_id}: {field}")
    occurrence_mirror_ok, occurrence_mirror_errors = _all_summary_mirrors(
        summary,
        {"commodity_occurrence_count": len(occurrences), "commodity_occurrence_total_area_km2": float(sum(_number(occurrence.get("area_km2"), 0.0) for occurrence in occurrences))},
    )
    _add(
        checks,
        domain=domain,
        name="commodity_occurrence_deposit_links",
        passed=not occurrence_errors and occurrence_mirror_ok,
        message="Commodity occurrences exactly mirror their natural geological deposit sources." if not occurrence_errors and occurrence_mirror_ok else "Commodity occurrences, deposit mirrors, or summary aggregates are inconsistent.",
        observed={"errors": occurrence_errors[:20], "summary_mismatches": occurrence_mirror_errors},
        expected="deposit-linked occurrences with bounded geological diagnostics",
    )


def validate_natural_subsystems(world: Any) -> list[Check]:
    """Validate broad natural enrichment outputs.

    The return value uses the same record schema as ``geo_validation._check``.
    Malformed input never raises: an individual subsystem exception becomes a
    failed check so validation remains suitable for mutation/fuzz testing.
    """

    checks: list[Check] = []
    root_ok = isinstance(world, dict)
    _add(
        checks,
        domain="natural_pipeline",
        name="world_root",
        passed=root_ok,
        message="Natural subsystem validation received an object world root." if root_ok else "Natural subsystem validation requires an object world root.",
        observed=type(world).__name__,
        expected="dict",
    )
    if not root_ok:
        return checks

    cells, cells_by_id, cells_ok = _cell_context(world)
    summary, summary_ok = _dict_payload(world, "summary")
    _add(
        checks,
        domain="natural_pipeline",
        name="cell_and_summary_context",
        passed=cells_ok and bool(cells) and summary_ok,
        message="Natural subsystem validation has unique cells and an object summary." if cells_ok and bool(cells) and summary_ok else "Natural subsystem validation requires non-empty unique cells and an object summary.",
        observed={"cell_count": len(cells), "unique_cell_ids": len(cells_by_id), "summary_object": summary_ok},
        expected="non-empty unique cells and dict summary",
    )

    validators: tuple[Callable[[], None], ...] = (
        lambda: _validate_geometry_indices(
            checks, world, cells, cells_by_id, summary
        ),
        lambda: _validate_seasonal_climate(
            checks, world, cells, cells_by_id, summary
        ),
        lambda: _validate_surface_geography(
            checks, world, cells, cells_by_id, summary
        ),
        lambda: _validate_soils_ecotones(
            checks, world, cells, cells_by_id, summary
        ),
        lambda: _validate_ocean(checks, world, cells, cells_by_id, summary),
        lambda: _validate_tectonics(checks, world, cells, cells_by_id, summary),
        lambda: _validate_lakes_watersheds(checks, world, cells, cells_by_id, summary),
        lambda: _validate_rivers(checks, world, cells, cells_by_id, summary),
        lambda: _validate_sequence_stratigraphy(checks, world, summary),
        lambda: _validate_cryosphere(checks, world, cells, cells_by_id, summary),
        lambda: _validate_subsurface_water(checks, world, cells, cells_by_id, summary),
        lambda: _validate_ecosystems(checks, world, cells, cells_by_id, summary),
        lambda: _validate_resources(checks, world, cells, cells_by_id, summary),
    )
    domains = (
        "geometry_indices",
        "seasonal_climate",
        "coastal_marine_landmass",
        "soils_and_ecotones",
        "ocean_circulation",
        "tectonic_zones_faults",
        "lakes_watersheds",
        "river_evolution_channels",
        "sequence_stratigraphy",
        "cryosphere_permafrost_glacial",
        "aquifers_wetlands_karst",
        "ecosystems_reefs_species_wildfire",
        "geologic_resources",
    )
    for domain, validator in zip(domains, validators):
        before = len(checks)
        try:
            validator()
        except Exception as exc:  # defensive boundary for deliberately malformed worlds
            del checks[before:]
            _add(
                checks,
                domain=domain,
                name="validator_completed",
                passed=False,
                message=f"Subsystem validation could not safely inspect malformed data: {type(exc).__name__}.",
                observed=str(exc),
                expected="validator completes without exception",
            )

    for index, check in enumerate(checks):
        check["id"] = index
    return checks


__all__ = ["validate_natural_subsystems"]
