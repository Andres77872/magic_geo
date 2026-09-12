"""Marine-distance source contract and replay, independent of its producer."""
from collections import Counter
import heapq
import math


MODEL = {
    "model_type": "marine_source_aware_continentality_v1",
    "distance_metric": "mesh_shortest_path_km",
    "edge_policy": "great_circle_edges_else_cell_mean_neighbor_length_floor_0.001_km",
    "marine_water_types": ["continental_shelf", "inland_sea", "ocean"],
    "no_source_policy": "null_distance_zero_oceanic_humidity_and_coastal_effects",
    "continentality_no_source_policy": "distance_term_one_other_terms_unchanged",
    "unreachable_source_policy": "refuse_before_publication",
}
MARINE = set(MODEL["marine_water_types"])


def _need(ok, message):
    if not ok:
        raise ValueError("marine distance: " + message)


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def source_graph(world):
    """Check the complete declared input graph without mutating any source."""
    _need(isinstance(world, dict) and isinstance(world.get("cells"), list), "cells must be a list")
    _need(isinstance(world.get("summary", {}), dict), "summary must be an object")
    cells = world["cells"]
    by_id = {}
    for c in cells:
        _need(isinstance(c, dict), "cells must be objects")
        cid = c.get("id")
        _need(type(cid) is int and cid >= 0 and cid not in by_id, "unique nonnegative cell IDs required")
        by_id[cid] = c
        _need(type(c.get("is_water")) is bool and isinstance(c.get("water_body_type"), str), "explicit water classification required")
        _need(c["water_body_type"] in MARINE | {"land", "fresh_lake", "saline_basin"}, "known water classification required")
        _need(c["water_body_type"] not in MARINE or c["is_water"], "marine cell must be water")
        for key in ("area_km2", "lat_deg", "lon_deg", "humidity_transport_index", "upwind_ocean_fetch_km",
                    "advected_moisture_factor", "precipitation_mm_y", "mean_neighbor_edge_length_km"):
            if key in c:
                _need(_finite(c[key]), f"cell {cid}: finite {key} required")
        _need(c.get("area_km2", 0.0) >= 0, "nonnegative area required")
        temperatures = c.get("temperature_monthly_c", [])
        _need(isinstance(temperatures, list) and all(_finite(t) for t in temperatures), "finite temperature list required")
    pairs = set()
    for cid, c in by_id.items():
        neighbors = c.get("neighbors", [])
        _need(isinstance(neighbors, list) and all(type(n) is int and n in by_id and n != cid for n in neighbors), "valid neighbor IDs required")
        _need(len(neighbors) == len(set(neighbors)), "duplicate neighbor")
    for cid, c in by_id.items():
        neighbors = c.get("neighbors", [])
        for n in neighbors:
            _need(cid in by_id[n].get("neighbors", []), "reciprocal neighbors required")
            pairs.add(tuple(sorted((cid, n))))
    graph = {cid: [] for cid in by_id}
    edges = world.get("cell_adjacency_edges", [])
    _need(isinstance(edges, list), "adjacency edges must be a list")
    if edges:
        seen = set()
        for edge in edges:
            _need(isinstance(edge, dict), "edge must be an object")
            a, b = edge.get("cell_a_id"), edge.get("cell_b_id")
            _need(type(a) is int and type(b) is int and a in by_id and b in by_id and a != b, "valid edge endpoints required")
            pair = tuple(sorted((a, b)))
            _need(pair not in seen, "duplicate adjacency edge")
            seen.add(pair)
            length = edge.get("great_circle_distance_km")
            _need(_finite(length) and length >= 0, "finite nonnegative edge distance required")
            graph[a].append((b, max(0.001, float(length))))
            graph[b].append((a, max(0.001, float(length))))
        _need(seen == pairs, "adjacency edges must cover declared neighbors exactly")
    else:
        for cid, c in by_id.items():
            length = max(0.001, float(c.get("mean_neighbor_edge_length_km", 1.0)))
            graph[cid] = [(n, length) for n in c.get("neighbors", [])]
    return by_id, graph


def _distances(by_id, graph):
    sources = [cid for cid, c in by_id.items() if c["water_body_type"] in MARINE]
    if not sources:
        return {cid: None for cid in by_id}
    distances = dict.fromkeys(by_id, math.inf)
    queue = [(0.0, cid) for cid in sources]
    heapq.heapify(queue)
    for cid in sources:
        distances[cid] = 0.0
    while queue:
        value, cid = heapq.heappop(queue)
        if value != distances[cid]:
            continue
        for neighbor, length in graph[cid]:
            candidate = value + length
            if candidate < distances[neighbor]:
                distances[neighbor] = candidate
                heapq.heappush(queue, (candidate, neighbor))
    _need(all(math.isfinite(d) for d in distances.values()), "marine source unreachable in declared graph")
    return distances


def _close(actual, expected):
    if expected is None:
        return actual is None
    if not _finite(expected) or not _finite(actual):
        return False
    target = round(expected, 6)
    if target == 0.0:
        return actual == 0.0
    return abs(actual - target) <= max(1e-12, 8 * math.ulp(target))


def _bounded(value):
    return max(0.0, min(1.0, value))


def require_marine_distance(world):
    """Return False for unmarked historical data; authenticate marked parents.

    Historical numeric distances retain their old consumer meaning. A null or
    new status cannot be smuggled into that historical branch.
    """
    if "climate_continentality_model" not in world:
        _need(not any(isinstance(c, dict) and "marine_distance_status" in c for c in world.get("cells", [])), "distance status requires its model declaration")
        _need(not any(isinstance(c, dict) and "distance_to_marine_water_km" in c and c["distance_to_marine_water_km"] is None for c in world.get("cells", [])), "null distance requires its model declaration")
        _need(not any(key in world.get("summary", {}) for key in ("marine_distance_defined_cell_count", "no_marine_source_cell_count")), "source counts require their model declaration")
        return False
    _need(world["climate_continentality_model"] == MODEL, "unknown model declaration")
    by_id, graph = source_graph(world)
    distances = _distances(by_id, graph)
    expected = {}
    for cid, c in by_id.items():
        distance = distances[cid]
        no_source = distance is None
        _need(c.get("marine_distance_status") == ("no_marine_source" if no_source else "reachable_marine"), f"cell {cid}: source status mismatch")
        _need("distance_to_marine_water_km" in c and _close(c["distance_to_marine_water_km"], distance), f"cell {cid}: source distance mismatch")
        temps = [float(t) for t in c.get("temperature_monthly_c", [])]
        temperature_range = max(temps) - min(temps) if temps else 0.0
        transport = _bounded(float(c.get("humidity_transport_index", 0.0)))
        continentality = _bounded((1.0 if no_source else _bounded(distance / 3000.0)) * .58 + _bounded(temperature_range / 34.0) * .30 + (1.0 - transport) * .12)
        humidity = 0.0 if no_source else _bounded(math.exp(-distance / 1200.0) * .36 + _bounded(float(c.get("upwind_ocean_fetch_km", 0.0)) / 2500.0) * .30 + _bounded((float(c.get("advected_moisture_factor", 1.0)) - .65) / .85) * .20 + transport * .14)
        if no_source:
            kind = "no_marine_source"
        elif c["water_body_type"] in MARINE:
            kind, humidity, continentality = "marine", max(.75, humidity), min(.18, continentality)
        elif distance <= 250 or continentality < .24:
            kind = "coastal"
        elif distance <= 1000 or continentality < .45:
            kind = "maritime_influenced"
        elif distance <= 2500 or continentality < .68:
            kind = "interior"
        else:
            kind = "continental_core"
        _need(c.get("marine_influence_class") == kind and _close(c.get("continentality_index"), continentality) and _close(c.get("oceanic_humidity_availability_index"), humidity), f"cell {cid}: influence mismatch")
        expected[cid] = (continentality, humidity, temperature_range)
    summary = world.get("summary", {})
    count = len(by_id)
    defined = sum(d is not None for d in distances.values())
    means = {
        "mean_distance_to_marine_water_km": sum(d for d in distances.values() if d is not None) / defined if defined else None,
        "mean_continentality_index": sum(v[0] for v in expected.values()) / count if count else 0.0,
        "max_continentality_index": max((v[0] for v in expected.values()), default=0.0),
        "mean_oceanic_humidity_availability_index": sum(v[1] for v in expected.values()) / count if count else 0.0,
    }
    for key, value in means.items():
        _need(key in summary and _close(summary[key], value), "summary " + key + " mismatch")
    counts = {
        "marine_distance_defined_cell_count": defined, "no_marine_source_cell_count": count - defined,
        "high_continentality_cell_count": sum(v[0] >= .65 for v in expected.values()),
        "low_oceanic_humidity_availability_cell_count": sum(v[1] <= .25 for v in expected.values()),
    }
    for key, value in counts.items():
        _need(type(summary.get(key)) is int and summary[key] == value, "summary " + key + " mismatch")
    class_counts = summary.get("marine_influence_class_counts")
    _need(isinstance(class_counts, dict) and all(type(v) is int for v in class_counts.values()) and class_counts == dict(sorted(Counter(c["marine_influence_class"] for c in by_id.values()).items())), "summary influence counts mismatch")
    regions = world.get("climate_continentality_regions")
    _need(isinstance(regions, list), "regions must be a list")
    remaining = set(by_id)
    for rid, region in enumerate(regions):
        _need(isinstance(region, dict) and type(region.get("id")) is int and region["id"] == rid and remaining, "invalid region identity")
        first = min(remaining)
        kind = by_id[first]["marine_influence_class"]
        component, pending = set(), [first]
        while pending:
            cid = pending.pop()
            if cid in component or by_id[cid]["marine_influence_class"] != kind:
                continue
            component.add(cid)
            pending.extend(n for n in by_id[cid].get("neighbors", []) if n not in component)
        members_raw = region.get("cell_ids")
        _need(isinstance(members_raw, list) and all(type(cid) is int for cid in members_raw) and members_raw == sorted(component) and region.get("region_class") == kind, "region component mismatch")
        remaining -= component
        members = [by_id[cid] for cid in sorted(component)]
        n = len(members)
        defined_here = sum(distances[c["id"]] is not None for c in members)
        region_values = {
            "area_km2": sum(float(c.get("area_km2", 0.0)) for c in members),
            "mean_distance_to_marine_water_km": sum(c["distance_to_marine_water_km"] for c in members) / n if defined_here else None,
            "mean_continentality_index": sum(c["continentality_index"] for c in members) / n,
            "mean_oceanic_humidity_availability_index": sum(c["oceanic_humidity_availability_index"] for c in members) / n,
            "mean_temperature_range_c": sum(expected[c["id"]][2] for c in members) / n,
            "mean_precipitation_mm_y": sum(float(c.get("precipitation_mm_y", 0.0)) for c in members) / n,
        }
        for key, value in region_values.items():
            _need(key in region and _close(region[key], value), "region " + key + " mismatch")
        region_counts = {"cell_count": n, "marine_distance_defined_cell_count": defined_here, "no_marine_source_cell_count": n - defined_here,
                         "land_cell_count": sum(not c["is_water"] for c in members), "marine_cell_count": sum(c["water_body_type"] in MARINE for c in members)}
        for key, value in region_counts.items():
            _need(type(region.get(key)) is int and region[key] == value, "region " + key + " mismatch")
        _need(all(type(c.get("climate_continentality_region_id")) is int and c["climate_continentality_region_id"] == rid for c in members), "region inverse mismatch")
    _need(not remaining, "missing region coverage")
    for key, value in {"climate_continentality_region_count": len(regions), "continental_core_region_count": sum(r["region_class"] == "continental_core" for r in regions), "maritime_influence_region_count": sum(r["region_class"] in {"marine", "coastal", "maritime_influenced"} for r in regions)}.items():
        _need(type(summary.get(key)) is int and summary[key] == value, "summary " + key + " mismatch")
    return True


def validate_marine_distance(world):
    try:
        require_marine_distance(world)
        return []
    except (TypeError, ValueError, KeyError, OverflowError, AttributeError) as error:
        return [str(error)[:600]]
