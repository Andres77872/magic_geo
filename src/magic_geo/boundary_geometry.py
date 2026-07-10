from __future__ import annotations

from collections import defaultdict
from typing import Any


def _round(value: float) -> float:
    return round(value, 6)


def _cell_id(cell: dict[str, Any]) -> int:
    return int(cell.get("id", -1))


def _edge_length(edge: dict[str, Any]) -> float:
    return max(0.0, float(edge.get("boundary_segment_length_km", edge.get("great_circle_distance_km", 0.0))))


def _edge_quality(edge: dict[str, Any]) -> float:
    return max(0.0, min(1.0, float(edge.get("boundary_segment_quality", 0.0))))


def _segment_geometry(edge: dict[str, Any]) -> dict[str, float]:
    return {
        "start_lat_deg": _round(float(edge.get("boundary_segment_start_lat_deg", 0.0))),
        "start_lon_deg": _round(float(edge.get("boundary_segment_start_lon_deg", 0.0))),
        "end_lat_deg": _round(float(edge.get("boundary_segment_end_lat_deg", 0.0))),
        "end_lon_deg": _round(float(edge.get("boundary_segment_end_lon_deg", 0.0))),
    }


def _region_members(cells_by_id: dict[int, dict[str, Any]]) -> dict[int, set[int]]:
    members: dict[int, set[int]] = defaultdict(set)
    for cell_id, cell in cells_by_id.items():
        region_id = int(cell.get("political_region_id", -1))
        if region_id >= 0:
            members[region_id].add(cell_id)
    return members


def _build_watershed_segments(
    world: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
) -> dict[int, list[dict[str, Any]]]:
    watersheds = world.get("watersheds", [])
    if not isinstance(watersheds, list):
        watersheds = []
    watershed_id_by_basin = {
        int(watershed.get("basin_id", -1)): int(watershed.get("id", -1))
        for watershed in watersheds
        if isinstance(watershed, dict)
    }

    segments: list[dict[str, Any]] = []
    segments_by_watershed: dict[int, list[dict[str, Any]]] = defaultdict(list)
    adjacency_edges = world.get("cell_adjacency_edges", [])
    if not isinstance(adjacency_edges, list):
        adjacency_edges = []

    for edge in adjacency_edges:
        cell_a = cells_by_id.get(int(edge.get("cell_a_id", -1)))
        cell_b = cells_by_id.get(int(edge.get("cell_b_id", -1)))
        if cell_a is None or cell_b is None:
            continue
        basin_a = int(cell_a.get("basin_id", -1))
        basin_b = int(cell_b.get("basin_id", -1))
        watershed_a = watershed_id_by_basin.get(basin_a, -1)
        watershed_b = watershed_id_by_basin.get(basin_b, -1)
        if watershed_a < 0 or watershed_b < 0 or watershed_a == watershed_b:
            continue
        if watershed_b < watershed_a:
            watershed_a, watershed_b = watershed_b, watershed_a
            basin_a, basin_b = basin_b, basin_a
            cell_a, cell_b = cell_b, cell_a

        length = _edge_length(edge)
        quality = _edge_quality(edge)
        mean_divide_elevation = (float(cell_a.get("elevation_m", 0.0)) + float(cell_b.get("elevation_m", 0.0))) * 0.5
        segment = {
            "id": len(segments),
            "source_edge_id": int(edge.get("id", -1)),
            "watershed_a_id": watershed_a,
            "watershed_b_id": watershed_b,
            "basin_a_id": basin_a,
            "basin_b_id": basin_b,
            "cell_a_id": _cell_id(cell_a),
            "cell_b_id": _cell_id(cell_b),
            "length_km": _round(length),
            "mean_divide_elevation_m": _round(mean_divide_elevation),
            "boundary_segment_quality": _round(quality),
            "edge_class": str(edge.get("edge_class", "unknown")),
            **_segment_geometry(edge),
        }
        segments.append(segment)
        segments_by_watershed[watershed_a].append(segment)
        segments_by_watershed[watershed_b].append(segment)

    world["watershed_boundary_segments"] = segments
    return segments_by_watershed


def _annotate_watersheds(
    world: dict[str, Any],
    segments_by_watershed: dict[int, list[dict[str, Any]]],
) -> None:
    watersheds = world.get("watersheds", [])
    if not isinstance(watersheds, list):
        return

    with_segments = 0
    total_directed_segments = 0
    total_directed_length = 0.0
    total_quality = 0.0
    quality_count = 0
    for watershed in watersheds:
        watershed_id = int(watershed.get("id", -1))
        segments = sorted(segments_by_watershed.get(watershed_id, []), key=lambda item: int(item["id"]))
        segment_ids = [int(segment["id"]) for segment in segments]
        neighbor_ids = sorted(
            {
                int(segment["watershed_b_id"]) if int(segment["watershed_a_id"]) == watershed_id else int(segment["watershed_a_id"])
                for segment in segments
            }
        )
        length_sum = sum(float(segment["length_km"]) for segment in segments)
        quality_sum = sum(float(segment["boundary_segment_quality"]) for segment in segments)
        mean_quality = quality_sum / len(segments) if segments else 0.0

        watershed["cell_edge_boundary_segment_ids"] = segment_ids
        watershed["cell_edge_boundary_segment_count"] = len(segment_ids)
        watershed["cell_edge_boundary_length_km"] = _round(length_sum)
        watershed["mean_cell_edge_boundary_segment_quality"] = _round(mean_quality)
        watershed["neighbor_watershed_ids"] = neighbor_ids

        if segments:
            with_segments += 1
            quality_count += len(segments)
            total_quality += quality_sum
        total_directed_segments += len(segments)
        total_directed_length += length_sum

    summary = world.setdefault("summary", {})
    undirected = world.get("watershed_boundary_segments", [])
    summary["watershed_cell_edge_boundary_segment_count"] = len(undirected) if isinstance(undirected, list) else 0
    summary["watershed_cell_edge_boundary_directed_segment_count"] = total_directed_segments
    summary["watershed_with_cell_edge_boundary_count"] = with_segments
    summary["watershed_cell_edge_boundary_length_km"] = _round(total_directed_length / 2.0)
    summary["mean_watershed_cell_edge_boundary_length_km"] = _round(total_directed_length / len(watersheds)) if watersheds else 0.0
    summary["mean_watershed_cell_edge_boundary_segment_quality"] = _round(total_quality / quality_count) if quality_count else 0.0


def _build_territorial_segments(
    world: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
) -> dict[int, list[dict[str, Any]]]:
    segments: list[dict[str, Any]] = []
    segments_by_region: dict[int, list[dict[str, Any]]] = defaultdict(list)
    adjacency_edges = world.get("cell_adjacency_edges", [])
    if not isinstance(adjacency_edges, list):
        adjacency_edges = []

    for edge in adjacency_edges:
        cell_a = cells_by_id.get(int(edge.get("cell_a_id", -1)))
        cell_b = cells_by_id.get(int(edge.get("cell_b_id", -1)))
        if cell_a is None or cell_b is None:
            continue
        region_a = int(cell_a.get("political_region_id", -1))
        region_b = int(cell_b.get("political_region_id", -1))
        if region_a < 0 or region_b < 0 or region_a == region_b:
            continue
        if region_b < region_a:
            region_a, region_b = region_b, region_a
            cell_a, cell_b = cell_b, cell_a

        length = _edge_length(edge)
        quality = _edge_quality(edge)
        segment = {
            "id": len(segments),
            "source_edge_id": int(edge.get("id", -1)),
            "region_a_id": region_a,
            "region_b_id": region_b,
            "cell_a_id": _cell_id(cell_a),
            "cell_b_id": _cell_id(cell_b),
            "length_km": _round(length),
            "boundary_segment_quality": _round(quality),
            "edge_class": str(edge.get("edge_class", "unknown")),
            "natural_boundary": bool(edge.get("land_water_transition", False))
            or str(edge.get("edge_class", "unknown")) in {"tectonic_plate_edge", "land_water_transition", "water_body_transition"},
            **_segment_geometry(edge),
        }
        segments.append(segment)
        segments_by_region[region_a].append(segment)
        segments_by_region[region_b].append(segment)

    world["territorial_boundary_segments"] = segments
    return segments_by_region


def _annotate_territorial_snapshots(
    world: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
    segments_by_region: dict[int, list[dict[str, Any]]],
) -> None:
    snapshots = world.get("territorial_snapshots", [])
    if not isinstance(snapshots, list):
        return
    members_by_region = _region_members(cells_by_id)

    region_record_count = 0
    region_with_segments = 0
    total_segment_count = 0
    total_length = 0.0
    total_quality = 0.0
    quality_count = 0
    for snapshot in snapshots:
        regions = snapshot.get("regions", [])
        if not isinstance(regions, list):
            continue
        for region in regions:
            region_id = int(region.get("region_id", -1))
            segments = sorted(segments_by_region.get(region_id, []), key=lambda item: int(item["id"]))
            segment_ids = [int(segment["id"]) for segment in segments]
            neighbor_ids = sorted(
                {
                    int(segment["region_b_id"]) if int(segment["region_a_id"]) == region_id else int(segment["region_a_id"])
                    for segment in segments
                }
            )
            length_sum = sum(float(segment["length_km"]) for segment in segments)
            quality_sum = sum(float(segment["boundary_segment_quality"]) for segment in segments)
            mean_quality = quality_sum / len(segments) if segments else 0.0
            dissolved_area = sum(max(0.0, float(cells_by_id[cell_id].get("area_km2", 0.0))) for cell_id in members_by_region.get(region_id, set()))

            region["cell_edge_boundary_segment_ids"] = segment_ids
            region["cell_edge_boundary_segment_count"] = len(segment_ids)
            region["cell_edge_boundary_length_km"] = _round(length_sum)
            region["mean_cell_edge_boundary_segment_quality"] = _round(mean_quality)
            region["neighbor_region_ids"] = neighbor_ids
            region["cell_edge_dissolved_area_km2"] = _round(dissolved_area)

            region_record_count += 1
            total_segment_count += len(segments)
            total_length += length_sum
            if segments:
                region_with_segments += 1
                quality_count += len(segments)
                total_quality += quality_sum

    summary = world.setdefault("summary", {})
    segments = world.get("territorial_boundary_segments", [])
    summary["territorial_cell_edge_boundary_segment_count"] = len(segments) if isinstance(segments, list) else 0
    summary["territorial_cell_edge_boundary_length_km"] = _round(
        sum(float(segment.get("length_km", 0.0)) for segment in segments) if isinstance(segments, list) else 0.0
    )
    summary["snapshot_region_with_cell_edge_boundary_count"] = region_with_segments
    summary["mean_snapshot_cell_edge_boundary_segment_count"] = _round(total_segment_count / region_record_count) if region_record_count else 0.0
    summary["mean_snapshot_cell_edge_boundary_length_km"] = _round(total_length / region_record_count) if region_record_count else 0.0
    summary["mean_snapshot_cell_edge_boundary_quality"] = _round(total_quality / quality_count) if quality_count else 0.0


def enrich_world_with_physical_boundary_geometry(
    world: dict[str, Any],
) -> dict[str, Any]:
    """Add boundary geometry for natural drainage partitions only."""
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world
    cells_by_id = {int(cell.get("id", -1)): cell for cell in cells if isinstance(cell, dict)}

    watershed_segments = _build_watershed_segments(world, cells_by_id)
    _annotate_watersheds(world, watershed_segments)
    return world


def enrich_world_with_boundary_geometry(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world

    enrich_world_with_physical_boundary_geometry(world)
    cells_by_id = {int(cell.get("id", -1)): cell for cell in cells if isinstance(cell, dict)}

    territorial_segments = _build_territorial_segments(world, cells_by_id)
    _annotate_territorial_snapshots(world, cells_by_id, territorial_segments)
    return world
