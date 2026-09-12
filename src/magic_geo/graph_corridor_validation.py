"""Typed projection of audited nullable corridor links into the trade graph.

Graph topology and native trade estimates do not depend on the inferred
corridor path. This boundary checks the link projection, not graph equations.
"""

from typing import Any

CORRIDOR_MODEL = "causal_feature_weighted_dijkstra_route_corridors_v3"
TRADE_GRAPH_TYPE = "trade_route_graph_v1"
_HISTORICAL_CORRIDORS = {
    "causal_feature_weighted_dijkstra_route_corridors_v1",
    "causal_feature_weighted_dijkstra_route_corridors_v2",
}


def require_trade_graph_corridor_inputs(world: dict[str, Any]) -> bool:
    """Audit the new corridor source before any graph product is published."""
    model = world.get("route_corridor_model")
    kind = model.get("model_type") if type(model) is dict else None
    if kind == CORRIDOR_MODEL:
        from .human_water_transport_validation import validate_human_water_transport

        errors = validate_human_water_transport(world, "corridors")
        if errors:
            raise ValueError("trade graph corridor source: " + "; ".join(errors)[:600])
        return True
    if model is not None and kind not in _HISTORICAL_CORRIDORS:
        raise ValueError("trade graph requires a recognized corridor declaration")
    graph = world.get("trade_route_graph")
    if any("route_path_supported" in row for row in world.get("routes", []) if type(row) is dict) or (
        type(graph) is dict and (
            graph.get("graph_type") == TRADE_GRAPH_TYPE
            or "source_route_corridor_model" in graph
            or any("route_path_supported" in row for row in graph.get("edges", []) if type(row) is dict)
        )
    ):
        raise ValueError("trade graph availability requires the current corridor declaration")
    return False


def corridor_graph_link(route: dict[str, Any]) -> dict[str, Any]:
    """Copy a typed current source link without converting unknown to -1."""
    supported = route.get("route_path_supported")
    link = route.get("route_corridor_id")
    if type(supported) is not bool or (
        supported and (type(link) is not int or link < -1)
    ) or (not supported and link is not None):
        raise ValueError("trade graph source corridor link and availability disagree")
    return {"route_path_supported": supported, "route_corridor_id": link}


def validate_trade_graph_corridor_links(world: Any) -> list[str]:
    """Check every current graph edge against its independently audited route."""
    try:
        if type(world) is not dict:
            raise ValueError("world must be an object")
        if not require_trade_graph_corridor_inputs(world):
            return []
        graph = world.get("trade_route_graph")
        if type(graph) is not dict or graph.get("graph_type") != TRADE_GRAPH_TYPE or graph.get("source_route_corridor_model") != CORRIDOR_MODEL:
            raise ValueError("current trade graph declaration must match its corridor source")
        routes = {row["id"]: row for row in world["routes"]}
        edges = graph.get("edges")
        if type(edges) is not list or len(edges) != len(routes):
            raise ValueError("trade graph corridor links must cover every actual route")
        seen = set()
        for edge in edges:
            if type(edge) is not dict or type(edge.get("route_id")) is not int:
                raise ValueError("trade graph edge requires a typed route ID")
            rid = edge["route_id"]
            if rid not in routes or rid in seen:
                raise ValueError("trade graph corridor links must cover distinct actual routes")
            seen.add(rid)
            source = routes[rid]
            # Compare raw owned values with strict types; do not coerce either
            # projection or source, and do not replay the graph producer.
            for name in ("route_path_supported", "route_corridor_id"):
                if name not in edge or type(edge[name]) is not type(source[name]) or edge[name] != source[name]:
                    raise ValueError("trade graph corridor link differs from its source route")
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        return ["trade graph corridor links: " + str(error)[:600]]
    return []
