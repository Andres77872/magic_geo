"""Final graph consumer checks on retained sources and scoped mixed paths."""

from copy import deepcopy

import pytest

from magic_geo.graph_diagnostics import (
    _build_trade_route_graph,
    enrich_world_with_graph_diagnostics,
)
from magic_geo.graph_corridor_validation import (
    corridor_graph_link,
    validate_trade_graph_corridor_links,
)
from test_human_water_transport import load
from test_settlement_available_human_water import STAGES, clear_transport, graph, check_equations


@pytest.fixture(scope="module")
def current_graph():
    world = clear_transport(load("natural_parents_full"))
    for _, _, _, producer in STAGES:
        producer(world)
    enrich_world_with_graph_diagnostics(world)
    return world


def test_retained_actual_source_projects_every_link_and_preserves_parents(current_graph):
    world = deepcopy(current_graph)
    before = deepcopy(world)
    assert world["trade_route_graph"]["graph_type"] == "trade_route_graph_v1"
    assert validate_trade_graph_corridor_links(world) == []
    enrich_world_with_graph_diagnostics(world)
    assert world == before
    routes = {row["id"]: row for row in world["routes"]}
    for edge in world["trade_route_graph"]["edges"]:
        assert edge["route_corridor_id"] == routes[edge["route_id"]]["route_corridor_id"]
        assert edge["route_path_supported"] is routes[edge["route_id"]]["route_path_supported"]


def test_scoped_mixed_paths_keep_native_graph_topology_and_unknown_link():
    # This checks projection of independently replayed equation-unit outputs;
    # it does not claim a full native/world/climate publication.
    world, states = graph()
    for stage in ("navigation", "ports", "corridors"):
        check_equations(world, states, stage)
    before = deepcopy(world)
    product = _build_trade_route_graph(world, corridor_availability=True)
    assert world == before
    assert product["node_count"] == 2
    assert product["edge_count"] == 2
    assert product["connected_component_count"] == 1
    assert product["total_route_distance_km"] == 200
    assert product["edges"][0]["route_corridor_id"] == 0
    assert product["edges"][0]["route_path_supported"] is True
    assert product["edges"][1]["route_corridor_id"] is None
    assert product["edges"][1]["route_path_supported"] is False
    assert all(edge["distance_km"] == 100 for edge in product["edges"])


def test_scoped_disconnected_known_empty_path_keeps_negative_sentinel():
    world, states = graph()
    world["cells"][2]["neighbors"] = []
    world["cells"][0]["neighbors"].remove(2)
    for stage in ("navigation", "ports", "corridors"):
        check_equations(world, states, stage)
    product = _build_trade_route_graph(world, corridor_availability=True)
    assert product["edges"][1]["route_path_supported"] is True
    assert product["edges"][1]["route_corridor_id"] == -1
    assert product["edge_count"] == 2


@pytest.mark.parametrize("supported,link", [(1, 0), (True, None), (False, -1), (False, 0), (True, True), (True, -2)])
def test_malformed_source_link_cannot_be_coerced(supported, link):
    with pytest.raises(ValueError):
        corridor_graph_link({"route_path_supported": supported, "route_corridor_id": link})


@pytest.mark.parametrize("change", [
    lambda w: w["trade_route_graph"]["edges"][0].update(route_corridor_id=None),
    lambda w: w["trade_route_graph"]["edges"][0].update(route_path_supported=1),
    lambda w: w["trade_route_graph"]["edges"][0].pop("route_path_supported"),
    lambda w: w["trade_route_graph"]["edges"].pop(),
    lambda w: w["trade_route_graph"]["edges"].append(w["trade_route_graph"]["edges"][0]),
    lambda w: w["trade_route_graph"].update(graph_type="trade_route_graph_v0"),
    lambda w: w["trade_route_graph"].update(source_route_corridor_model="unknown"),
])
def test_public_projection_rejects_tampering_without_mutation(current_graph, change):
    world = deepcopy(current_graph)
    change(world)
    before = deepcopy(world)
    assert validate_trade_graph_corridor_links(world)
    assert world == before


@pytest.mark.parametrize("change", [
    lambda w: w["routes"][0].update(route_path_supported=False),
    lambda w: w["route_corridor_model"].update(model_type="unknown"),
    lambda w: w.pop("route_corridor_model"),
])
def test_invalid_parent_fails_before_any_graph_mutation(current_graph, change):
    world = deepcopy(current_graph)
    change(world)
    before = deepcopy(world)
    with pytest.raises(ValueError):
        enrich_world_with_graph_diagnostics(world)
    assert world == before


def test_retained_historical_graph_has_original_schema_and_values():
    world = load("legacy_full")
    expected = deepcopy(world["trade_route_graph"])
    assert validate_trade_graph_corridor_links(world) == []
    enrich_world_with_graph_diagnostics(world)
    assert world["trade_route_graph"] == expected
    assert world["trade_route_graph"]["graph_type"] == "trade_route_graph_v0"
