from __future__ import annotations

from collections import Counter, defaultdict, deque
from typing import Any


def _round(value: float, digits: int = 6) -> float:
    return round(float(value), digits)


def _index_records(records: Any) -> dict[int, dict[str, Any]]:
    if not isinstance(records, list):
        return {}
    indexed: dict[int, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        record_id = int(record.get("id", -1))
        if record_id >= 0:
            indexed[record_id] = record
    return indexed


def _component_count(node_ids: set[int], adjacency: dict[int, set[int]]) -> int:
    remaining = set(node_ids)
    count = 0
    while remaining:
        count += 1
        start = remaining.pop()
        queue: deque[int] = deque([start])
        while queue:
            current = queue.popleft()
            for neighbor in adjacency.get(current, set()):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    queue.append(neighbor)
    return count


def _dominant(counter: Counter[str], fallback: str = "none") -> str:
    if not counter:
        return fallback
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _edge_distance_by_pair(adjacency_edges: list[dict[str, Any]]) -> dict[tuple[int, int], float]:
    distances: dict[tuple[int, int], float] = {}
    for edge in adjacency_edges:
        a = int(edge.get("cell_a_id", -1))
        b = int(edge.get("cell_b_id", -1))
        if a >= 0 and b >= 0:
            distances[(min(a, b), max(a, b))] = max(0.0, float(edge.get("great_circle_distance_km", 0.0)))
    return distances


def _build_plate_graph(world: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> dict[str, Any]:
    plates = _index_records(world.get("plates", []))
    adjacency_edges = world.get("cell_adjacency_edges", [])
    if not isinstance(adjacency_edges, list):
        adjacency_edges = []

    edge_buckets: dict[tuple[int, int], dict[str, Any]] = {}
    for edge in adjacency_edges:
        a = cells_by_id.get(int(edge.get("cell_a_id", -1)))
        b = cells_by_id.get(int(edge.get("cell_b_id", -1)))
        if a is None or b is None:
            continue
        plate_a = int(a.get("plate_id", -1))
        plate_b = int(b.get("plate_id", -1))
        if plate_a < 0 or plate_b < 0 or plate_a == plate_b:
            continue
        key = (min(plate_a, plate_b), max(plate_a, plate_b))
        bucket = edge_buckets.setdefault(
            key,
            {
                "cell_edge_count": 0,
                "total_boundary_length_km": 0.0,
                "boundary_activity_sum": 0.0,
                "boundary_type_counts": Counter(),
                "sample_cell_edge_ids": [],
            },
        )
        boundary_activity = max(
            float(a.get("boundary_convergent", 0.0)),
            float(a.get("boundary_divergent", 0.0)),
            float(a.get("boundary_transform", 0.0)),
            float(b.get("boundary_convergent", 0.0)),
            float(b.get("boundary_divergent", 0.0)),
            float(b.get("boundary_transform", 0.0)),
        )
        bucket["cell_edge_count"] += 1
        bucket["total_boundary_length_km"] += max(0.0, float(edge.get("boundary_segment_length_km", edge.get("great_circle_distance_km", 0.0))))
        bucket["boundary_activity_sum"] += boundary_activity
        bucket["boundary_type_counts"][str(a.get("boundary_type", "unknown"))] += 1
        bucket["boundary_type_counts"][str(b.get("boundary_type", "unknown"))] += 1
        if len(bucket["sample_cell_edge_ids"]) < 8:
            bucket["sample_cell_edge_ids"].append(int(edge.get("id", -1)))

    graph_adjacency: dict[int, set[int]] = defaultdict(set)
    edges: list[dict[str, Any]] = []
    boundary_cell_edge_count = 0
    boundary_length_sum = 0.0
    for (plate_a, plate_b), bucket in sorted(edge_buckets.items()):
        edge_id = len(edges)
        graph_adjacency[plate_a].add(plate_b)
        graph_adjacency[plate_b].add(plate_a)
        cell_edge_count = int(bucket["cell_edge_count"])
        boundary_length = float(bucket["total_boundary_length_km"])
        boundary_cell_edge_count += cell_edge_count
        boundary_length_sum += boundary_length
        counts = Counter(bucket["boundary_type_counts"])
        edges.append(
            {
                "id": edge_id,
                "plate_a": plate_a,
                "plate_b": plate_b,
                "cell_edge_count": cell_edge_count,
                "total_boundary_length_km": _round(boundary_length),
                "mean_boundary_activity": _round(float(bucket["boundary_activity_sum"]) / max(1, cell_edge_count)),
                "dominant_boundary_type": _dominant(counts, "unknown"),
                "boundary_type_counts": dict(sorted(counts.items())),
                "sample_cell_edge_ids": [value for value in bucket["sample_cell_edge_ids"] if value >= 0],
            }
        )

    edge_ids_by_plate: dict[int, list[int]] = defaultdict(list)
    for edge in edges:
        edge_ids_by_plate[int(edge["plate_a"])].append(int(edge["id"]))
        edge_ids_by_plate[int(edge["plate_b"])].append(int(edge["id"]))
    nodes = [
        {
            "id": plate_id,
            "plate_id": plate_id,
            "kind": str(plate.get("kind", "unknown")),
            "cell_count": int(plate.get("cell_count", 0)),
            "area_km2": _round(float(plate.get("area_km2", 0.0))),
            "dominant_crust_type": str(plate.get("dominant_crust_type", "unknown")),
            "dominant_lithology": str(plate.get("dominant_lithology", "unknown")),
            "mean_crust_age_ma": _round(float(plate.get("mean_crust_age_ma", 0.0))),
            "degree": len(edge_ids_by_plate.get(plate_id, [])),
            "edge_ids": sorted(edge_ids_by_plate.get(plate_id, [])),
        }
        for plate_id, plate in sorted(plates.items())
    ]
    node_ids = set(plates)
    return {
        "graph_type": "plate_graph_v0",
        "node_count": len(nodes),
        "edge_count": len(edges),
        "connected_component_count": _component_count(node_ids, graph_adjacency) if node_ids else 0,
        "boundary_cell_edge_count": boundary_cell_edge_count,
        "total_boundary_length_km": _round(boundary_length_sum),
        "nodes": nodes,
        "edges": edges,
    }


def _build_river_graph(world: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> dict[str, Any]:
    adjacency_edges = world.get("cell_adjacency_edges", [])
    if not isinstance(adjacency_edges, list):
        adjacency_edges = []
    distances = _edge_distance_by_pair(adjacency_edges)
    river_cells = {
        cell_id: cell
        for cell_id, cell in cells_by_id.items()
        if bool(cell.get("is_river", False))
    }
    upstream: dict[int, list[int]] = defaultdict(list)
    edges: list[dict[str, Any]] = []
    graph_adjacency: dict[int, set[int]] = defaultdict(set)
    total_length = 0.0
    for cell_id, cell in sorted(river_cells.items()):
        target = int(cell.get("flow_to", -1))
        if target not in cells_by_id or target == cell_id:
            continue
        target_cell = cells_by_id[target]
        if not bool(target_cell.get("is_river", False)) and str(target_cell.get("water_body_type", "land")) == "land":
            continue
        pair = (min(cell_id, target), max(cell_id, target))
        length = distances.get(pair, 0.0)
        drop = float(cell.get("elevation_m", 0.0)) - float(target_cell.get("elevation_m", 0.0))
        edge_id = len(edges)
        edges.append(
            {
                "id": edge_id,
                "from_cell_id": cell_id,
                "to_cell_id": target,
                "from_basin_id": int(cell.get("basin_id", -1)),
                "to_basin_id": int(target_cell.get("basin_id", -1)),
                "length_km": _round(length),
                "elevation_drop_m": _round(drop),
                "flow_accumulation": _round(float(cell.get("flow_accumulation", 0.0))),
                "sediment_export_m": _round(float(cell.get("sediment_export_m", 0.0))),
            }
        )
        total_length += length
        upstream[target].append(cell_id)
        graph_adjacency[cell_id].add(target)
        graph_adjacency[target].add(cell_id)

    sink_count = 0
    nodes: list[dict[str, Any]] = []
    for cell_id, cell in sorted(river_cells.items()):
        flow_to = int(cell.get("flow_to", -1))
        if flow_to not in cells_by_id or (flow_to not in river_cells and str(cells_by_id[flow_to].get("water_body_type", "land")) == "land"):
            sink_count += 1
        nodes.append(
            {
                "id": len(nodes),
                "cell_id": cell_id,
                "basin_id": int(cell.get("basin_id", -1)),
                "flow_to_cell_id": flow_to,
                "upstream_cell_ids": sorted(upstream.get(cell_id, [])),
                "flow_accumulation": _round(float(cell.get("flow_accumulation", 0.0))),
                "runoff_mm_y": _round(float(cell.get("runoff_mm_y", 0.0))),
                "elevation_m": _round(float(cell.get("elevation_m", 0.0))),
            }
        )
    node_ids = set(river_cells)
    return {
        "graph_type": "river_graph_v0",
        "node_count": len(nodes),
        "edge_count": len(edges),
        "sink_count": sink_count,
        "connected_component_count": _component_count(node_ids, graph_adjacency) if node_ids else 0,
        "total_channel_length_km": _round(total_length),
        "nodes": nodes,
        "edges": edges,
    }


def _build_watershed_graph(world: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> dict[str, Any]:
    watersheds = _index_records(world.get("watersheds", []))
    watershed_by_basin = {int(record.get("basin_id", -1)): record for record in watersheds.values()}
    watershed_id_by_basin = {int(record.get("basin_id", -1)): int(record.get("id", -1)) for record in watersheds.values()}
    adjacency_edges = world.get("cell_adjacency_edges", [])
    if not isinstance(adjacency_edges, list):
        adjacency_edges = []

    edge_buckets: dict[tuple[int, int], dict[str, Any]] = {}
    for edge in adjacency_edges:
        a = cells_by_id.get(int(edge.get("cell_a_id", -1)))
        b = cells_by_id.get(int(edge.get("cell_b_id", -1)))
        if a is None or b is None:
            continue
        basin_a = int(a.get("basin_id", -1))
        basin_b = int(b.get("basin_id", -1))
        watershed_a = watershed_id_by_basin.get(basin_a, -1)
        watershed_b = watershed_id_by_basin.get(basin_b, -1)
        if watershed_a < 0 or watershed_b < 0 or watershed_a == watershed_b:
            continue
        key = (min(watershed_a, watershed_b), max(watershed_a, watershed_b))
        bucket = edge_buckets.setdefault(key, {"edge_count": 0, "length_sum": 0.0, "divide_elevation_sum": 0.0})
        bucket["edge_count"] += 1
        bucket["length_sum"] += max(0.0, float(edge.get("boundary_segment_length_km", edge.get("great_circle_distance_km", 0.0))))
        bucket["divide_elevation_sum"] += (float(a.get("elevation_m", 0.0)) + float(b.get("elevation_m", 0.0))) / 2.0

    graph_adjacency: dict[int, set[int]] = defaultdict(set)
    edges: list[dict[str, Any]] = []
    total_boundary_length = 0.0
    boundary_edge_count = 0
    for (watershed_a, watershed_b), bucket in sorted(edge_buckets.items()):
        edge_count = int(bucket["edge_count"])
        length_sum = float(bucket["length_sum"])
        graph_adjacency[watershed_a].add(watershed_b)
        graph_adjacency[watershed_b].add(watershed_a)
        boundary_edge_count += edge_count
        total_boundary_length += length_sum
        edges.append(
            {
                "id": len(edges),
                "watershed_a": watershed_a,
                "watershed_b": watershed_b,
                "basin_a": int(watersheds[watershed_a].get("basin_id", -1)),
                "basin_b": int(watersheds[watershed_b].get("basin_id", -1)),
                "boundary_edge_count": edge_count,
                "boundary_length_km": _round(length_sum),
                "mean_divide_elevation_m": _round(float(bucket["divide_elevation_sum"]) / max(1, edge_count)),
            }
        )

    edge_ids_by_watershed: dict[int, list[int]] = defaultdict(list)
    for edge in edges:
        edge_ids_by_watershed[int(edge["watershed_a"])].append(int(edge["id"]))
        edge_ids_by_watershed[int(edge["watershed_b"])].append(int(edge["id"]))
    nodes = [
        {
            "id": watershed_id,
            "watershed_id": watershed_id,
            "basin_id": int(watershed.get("basin_id", -1)),
            "outlet_cell_id": int(watershed.get("outlet_cell_id", -1)),
            "outlet_type": str(watershed.get("outlet_type", "unknown")),
            "area_km2": _round(float(watershed.get("area_km2", 0.0))),
            "river_cell_count": int(watershed.get("river_cell_count", 0)),
            "degree": len(edge_ids_by_watershed.get(watershed_id, [])),
            "edge_ids": sorted(edge_ids_by_watershed.get(watershed_id, [])),
        }
        for watershed_id, watershed in sorted(watersheds.items())
    ]
    node_ids = set(watersheds)
    return {
        "graph_type": "watershed_graph_v0",
        "node_count": len(nodes),
        "edge_count": len(edges),
        "connected_component_count": _component_count(node_ids, graph_adjacency) if node_ids else 0,
        "boundary_edge_count": boundary_edge_count,
        "total_boundary_length_km": _round(total_boundary_length),
        "nodes": nodes,
        "edges": edges,
    }


def _build_trade_route_graph(world: dict[str, Any]) -> dict[str, Any]:
    settlements = _index_records(world.get("settlements", []))
    routes = _index_records(world.get("routes", []))
    trade_by_route = {int(flow.get("route_id", -1)): flow for flow in world.get("trade_flows", []) if isinstance(flow, dict)}
    edge_ids_by_settlement: dict[int, list[int]] = defaultdict(list)
    graph_adjacency: dict[int, set[int]] = defaultdict(set)
    edges: list[dict[str, Any]] = []
    interregional_count = 0
    total_volume = 0.0
    total_distance = 0.0
    for route_id, route in sorted(routes.items()):
        source = int(route.get("from", -1))
        target = int(route.get("to", -1))
        if source not in settlements or target not in settlements or source == target:
            continue
        trade = trade_by_route.get(route_id, {})
        volume = float(trade.get("volume_index", 0.0)) if trade else 0.0
        distance = max(0.0, float(route.get("distance_km", 0.0)))
        edge_id = len(edges)
        region_from = int(trade.get("region_from", settlements[source].get("region_id", -1)))
        region_to = int(trade.get("region_to", settlements[target].get("region_id", -1)))
        interregional = bool(trade.get("interregional", region_from >= 0 and region_to >= 0 and region_from != region_to))
        if interregional:
            interregional_count += 1
        total_volume += volume
        total_distance += distance
        edge_ids_by_settlement[source].append(edge_id)
        edge_ids_by_settlement[target].append(edge_id)
        graph_adjacency[source].add(target)
        graph_adjacency[target].add(source)
        edges.append(
            {
                "id": edge_id,
                "route_id": route_id,
                "from_settlement_id": source,
                "to_settlement_id": target,
                "from_region_id": region_from,
                "to_region_id": region_to,
                "route_type": str(route.get("type", "unknown")),
                "route_corridor_id": int(route.get("route_corridor_id", -1)),
                "route_capacity_constraint_id": int(route.get("route_capacity_constraint_id", -1)),
                "trade_flow_id": int(trade.get("id", -1)) if trade else -1,
                "primary_good": str(trade.get("primary_good", "none")) if trade else "none",
                "distance_km": _round(distance),
                "cost": _round(float(route.get("cost", 0.0))),
                "friction": _round(float(trade.get("friction", float(route.get("cost", 0.0)) / distance if distance > 0 else 0.0))),
                "volume_index": _round(volume),
                "interregional": interregional,
            }
        )

    nodes = [
        {
            "id": settlement_id,
            "settlement_id": settlement_id,
            "cell_id": int(settlement.get("cell_id", -1)),
            "region_id": int(settlement.get("region_id", -1)),
            "type": str(settlement.get("type", "unknown")),
            "score": _round(float(settlement.get("score", 0.0))),
            "degree": len(edge_ids_by_settlement.get(settlement_id, [])),
            "edge_ids": sorted(edge_ids_by_settlement.get(settlement_id, [])),
        }
        for settlement_id, settlement in sorted(settlements.items())
    ]
    node_ids = set(settlements)
    return {
        "graph_type": "trade_route_graph_v0",
        "node_count": len(nodes),
        "edge_count": len(edges),
        "connected_component_count": _component_count(node_ids, graph_adjacency) if node_ids else 0,
        "interregional_edge_count": interregional_count,
        "total_trade_volume_index": _round(total_volume),
        "total_route_distance_km": _round(total_distance),
        "nodes": nodes,
        "edges": edges,
    }


def _build_political_region_graph(world: dict[str, Any]) -> dict[str, Any]:
    regions = _index_records(world.get("political_regions", []))
    routes = _index_records(world.get("routes", []))
    trade_flows = _index_records(world.get("trade_flows", []))
    borders = _index_records(world.get("borders", []))
    frontiers = _index_records(world.get("natural_frontiers", []))
    settlements = _index_records(world.get("settlements", []))

    route_ids_by_pair: dict[tuple[int, int], list[int]] = defaultdict(list)
    for route_id, route in routes.items():
        source = settlements.get(int(route.get("from", -1)), {})
        target = settlements.get(int(route.get("to", -1)), {})
        region_a = int(source.get("region_id", -1))
        region_b = int(target.get("region_id", -1))
        if region_a >= 0 and region_b >= 0 and region_a != region_b:
            route_ids_by_pair[(min(region_a, region_b), max(region_a, region_b))].append(route_id)

    trade_ids_by_pair: dict[tuple[int, int], list[int]] = defaultdict(list)
    trade_volume_by_pair: dict[tuple[int, int], float] = defaultdict(float)
    for trade_id, trade in trade_flows.items():
        region_a = int(trade.get("region_from", -1))
        region_b = int(trade.get("region_to", -1))
        if region_a >= 0 and region_b >= 0 and region_a != region_b:
            key = (min(region_a, region_b), max(region_a, region_b))
            trade_ids_by_pair[key].append(trade_id)
            trade_volume_by_pair[key] += max(0.0, float(trade.get("volume_index", 0.0)))

    border_ids_by_pair: dict[tuple[int, int], list[int]] = defaultdict(list)
    border_length_by_pair: dict[tuple[int, int], float] = defaultdict(float)
    border_barrier_by_pair: dict[tuple[int, int], float] = defaultdict(float)
    border_type_counts_by_pair: dict[tuple[int, int], Counter[str]] = defaultdict(Counter)
    for border_id, border in borders.items():
        region_a = int(border.get("region_a", -1))
        region_b = int(border.get("region_b", -1))
        if region_a >= 0 and region_b >= 0 and region_a != region_b:
            key = (min(region_a, region_b), max(region_a, region_b))
            border_ids_by_pair[key].append(border_id)
            border_length_by_pair[key] += max(0.0, float(border.get("length_km", 0.0)))
            border_barrier_by_pair[key] += float(border.get("barrier_score", 0.0))
            border_type_counts_by_pair[key][str(border.get("type", "unknown"))] += 1

    frontier_ids_by_pair: dict[tuple[int, int], list[int]] = defaultdict(list)
    for frontier_id, frontier in frontiers.items():
        region_ids = sorted({int(value) for value in frontier.get("region_ids", []) if int(value) >= 0})
        if len(region_ids) == 2:
            frontier_ids_by_pair[(region_ids[0], region_ids[1])].append(frontier_id)

    all_pairs = sorted(set(route_ids_by_pair) | set(trade_ids_by_pair) | set(border_ids_by_pair) | set(frontier_ids_by_pair))
    graph_adjacency: dict[int, set[int]] = defaultdict(set)
    edge_ids_by_region: dict[int, list[int]] = defaultdict(list)
    edges: list[dict[str, Any]] = []
    trade_edge_count = 0
    total_border_length = 0.0
    total_trade_volume = 0.0
    for region_a, region_b in all_pairs:
        edge_id = len(edges)
        route_ids = sorted(route_ids_by_pair.get((region_a, region_b), []))
        trade_ids = sorted(trade_ids_by_pair.get((region_a, region_b), []))
        border_ids = sorted(border_ids_by_pair.get((region_a, region_b), []))
        frontier_ids = sorted(frontier_ids_by_pair.get((region_a, region_b), []))
        border_count = len(border_ids)
        border_length = border_length_by_pair.get((region_a, region_b), 0.0)
        trade_volume = trade_volume_by_pair.get((region_a, region_b), 0.0)
        if trade_ids:
            trade_edge_count += 1
        total_border_length += border_length
        total_trade_volume += trade_volume
        graph_adjacency[region_a].add(region_b)
        graph_adjacency[region_b].add(region_a)
        edge_ids_by_region[region_a].append(edge_id)
        edge_ids_by_region[region_b].append(edge_id)
        type_counts = border_type_counts_by_pair.get((region_a, region_b), Counter())
        edges.append(
            {
                "id": edge_id,
                "region_a": region_a,
                "region_b": region_b,
                "border_ids": border_ids,
                "route_ids": route_ids,
                "trade_flow_ids": trade_ids,
                "natural_frontier_ids": frontier_ids,
                "border_segment_count": border_count,
                "border_length_km": _round(border_length),
                "route_count": len(route_ids),
                "trade_flow_count": len(trade_ids),
                "trade_volume_index": _round(trade_volume),
                "mean_barrier_score": _round(border_barrier_by_pair.get((region_a, region_b), 0.0) / max(1, border_count)),
                "dominant_border_type": _dominant(type_counts, "none"),
                "border_type_counts": dict(sorted(type_counts.items())),
            }
        )

    nodes = [
        {
            "id": region_id,
            "region_id": region_id,
            "type": str(region.get("type", "unknown")),
            "capital_settlement_id": int(region.get("capital_settlement_id", -1)),
            "settlement_count": int(region.get("settlement_count", len(region.get("settlement_ids", [])))),
            "area_km2": _round(float(region.get("area_km2", 0.0))),
            "dominant_biome": str(region.get("dominant_biome", "unknown")),
            "dominant_resource": str(region.get("dominant_resource", "none")),
            "degree": len(edge_ids_by_region.get(region_id, [])),
            "edge_ids": sorted(edge_ids_by_region.get(region_id, [])),
        }
        for region_id, region in sorted(regions.items())
    ]
    node_ids = set(regions)
    return {
        "graph_type": "political_region_graph_v0",
        "node_count": len(nodes),
        "edge_count": len(edges),
        "connected_component_count": _component_count(node_ids, graph_adjacency) if node_ids else 0,
        "border_segment_count": sum(len(ids) for ids in border_ids_by_pair.values()),
        "trade_edge_count": trade_edge_count,
        "total_border_length_km": _round(total_border_length),
        "total_trade_volume_index": _round(total_trade_volume),
        "nodes": nodes,
        "edges": edges,
    }


def enrich_world_with_physical_graph_diagnostics(
    world: dict[str, Any],
) -> dict[str, Any]:
    """Add graph products derived only from the planet's physical systems."""
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world
    cells_by_id = {int(cell.get("id", -1)): cell for cell in cells if isinstance(cell, dict)}
    plate_graph = _build_plate_graph(world, cells_by_id)
    river_graph = _build_river_graph(world, cells_by_id)
    watershed_graph = _build_watershed_graph(world, cells_by_id)

    world["plate_graph"] = plate_graph
    world["river_graph"] = river_graph
    world["watershed_graph"] = watershed_graph

    summary = world.setdefault("summary", {})
    summary["plate_graph_node_count"] = plate_graph["node_count"]
    summary["plate_graph_edge_count"] = plate_graph["edge_count"]
    summary["plate_graph_component_count"] = plate_graph["connected_component_count"]
    summary["plate_graph_boundary_cell_edge_count"] = plate_graph["boundary_cell_edge_count"]
    summary["river_graph_node_count"] = river_graph["node_count"]
    summary["river_graph_edge_count"] = river_graph["edge_count"]
    summary["river_graph_sink_count"] = river_graph["sink_count"]
    summary["river_graph_component_count"] = river_graph["connected_component_count"]
    summary["river_graph_total_channel_length_km"] = river_graph["total_channel_length_km"]
    summary["watershed_graph_node_count"] = watershed_graph["node_count"]
    summary["watershed_graph_edge_count"] = watershed_graph["edge_count"]
    summary["watershed_graph_component_count"] = watershed_graph["connected_component_count"]
    summary["watershed_graph_boundary_edge_count"] = watershed_graph["boundary_edge_count"]
    summary["watershed_graph_total_boundary_length_km"] = watershed_graph["total_boundary_length_km"]
    return world


def enrich_world_with_graph_diagnostics(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world

    enrich_world_with_physical_graph_diagnostics(world)
    trade_route_graph = _build_trade_route_graph(world)
    political_region_graph = _build_political_region_graph(world)

    world["trade_route_graph"] = trade_route_graph
    world["political_region_graph"] = political_region_graph

    summary = world.setdefault("summary", {})
    summary["trade_route_graph_node_count"] = trade_route_graph["node_count"]
    summary["trade_route_graph_edge_count"] = trade_route_graph["edge_count"]
    summary["trade_route_graph_component_count"] = trade_route_graph["connected_component_count"]
    summary["interregional_trade_route_graph_edge_count"] = trade_route_graph["interregional_edge_count"]
    summary["trade_route_graph_total_volume_index"] = trade_route_graph["total_trade_volume_index"]
    summary["political_region_graph_node_count"] = political_region_graph["node_count"]
    summary["political_region_graph_edge_count"] = political_region_graph["edge_count"]
    summary["political_region_graph_component_count"] = political_region_graph["connected_component_count"]
    summary["political_region_graph_border_segment_count"] = political_region_graph["border_segment_count"]
    summary["political_region_graph_trade_edge_count"] = political_region_graph["trade_edge_count"]
    summary["political_region_graph_total_border_length_km"] = political_region_graph["total_border_length_km"]
    return world
