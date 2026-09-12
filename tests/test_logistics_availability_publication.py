"""Actual native social-stage source gates; no complete climate certification."""
from copy import deepcopy

import pytest

from support.native_campaign_worlds import campaign_source_world, campaign_public_world
from magic_geo.logistics_history import enrich_world_with_logistics_history
from magic_geo.logistics_exchange_validation import validate_logistics_exchange_replay
from magic_geo.campaign_operations_validation import validate_campaign_operations_replay
from magic_geo.logistics_availability_validation import NETWORK_ESTIMATES, EXCHANGE_ESTIMATES


@pytest.mark.parametrize("case", ["healthy", "mixed"])
def test_public_first_and_repeat_publication_preserve_parents(case):
    world = campaign_source_world(case)
    before = deepcopy(world)
    parents = {key: world[key] for key in ("cells", "routes", "trade_flows", "economy_histories", "population_histories")}
    assert enrich_world_with_logistics_history(world) is world
    assert validate_logistics_exchange_replay(world) == []
    assert validate_campaign_operations_replay(world) == []
    for key, value in parents.items():
        assert world[key] is value and world[key] == before[key]
    for old, new in zip(before["conflicts"], world["conflicts"]):
        assert all(new[key] == value for key, value in old.items())
    final = deepcopy(world)
    assert enrich_world_with_logistics_history(world) is world
    assert world == final


@pytest.mark.parametrize("collection,field", [
    *(("logistics_networks", key) for key in NETWORK_ESTIMATES),
    *(("market_exchanges", key) for key in EXCHANGE_ESTIMATES),
])
def test_each_logistics_estimate_is_independently_checked(collection, field):
    world = campaign_public_world("healthy")
    assert world[collection]
    world[collection][0][field] += 100.0
    before = deepcopy(world)
    assert validate_logistics_exchange_replay(world)
    with pytest.raises(ValueError):
        enrich_world_with_logistics_history(world)
    assert world == before


@pytest.mark.parametrize("value", [0, 1, None, "true"])
def test_logistics_estimate_availability_requires_exact_boolean(value):
    world = campaign_public_world("healthy")
    world["logistics_networks"][0]["estimate_availability"]["army_capacity_population"] = value
    assert validate_logistics_exchange_replay(world)


@pytest.mark.parametrize("mutation", [
    lambda world: world["population_regions"][0].__setitem__("estimated_population", 999999999.),
    lambda world: world["economy_histories"][0]["steps"][-1].__setitem__("prosperity_index", 999999.),
    lambda world: world["cells"][0].__setitem__("seasonal_aridity_index", True),
    lambda world: world["routes"][0].__setitem__("cost", "9"),
    lambda world: world["summary"].__setitem__("logistics_exchange_model", None),
    lambda world: world.__setitem__("logistics_networks", []),
])
def test_source_and_stale_output_fail_before_publication(mutation):
    world = campaign_source_world("healthy")
    mutation(world)
    before = deepcopy(world)
    with pytest.raises(ValueError):
        enrich_world_with_logistics_history(world)
    assert world == before


def test_mutated_producer_result_is_rejected_atomically(monkeypatch):
    import magic_geo.logistics_availability as producer
    original = producer.networks_and_exchanges

    def poisoned(world):
        output = original(world)
        output["logistics_networks"][0]["total_route_distance_km"] += 100.
        return output

    monkeypatch.setattr(producer, "networks_and_exchanges", poisoned)
    world = campaign_source_world("healthy")
    before = deepcopy(world)
    with pytest.raises(ValueError, match="invalid computed logistics"):
        enrich_world_with_logistics_history(world)
    assert world == before


def test_descendant_exchange_annotations_survive_parent_validation_and_repeat():
    world = campaign_public_world("healthy")
    exchange = world["market_exchanges"][0]
    # This only exercises parent ownership; it does not certify market output.
    exchange["market_clearing_record_id"] = 0
    exchange["market_clearing_estimate_availability"] = {"cleared_volume_index": False}
    exchange["cleared_volume_index"] = None
    before = deepcopy(world)
    assert validate_logistics_exchange_replay(world) == []
    assert enrich_world_with_logistics_history(world) is world
    assert world == before and world["market_exchanges"][0] is exchange


def test_unknown_parent_map_fields_are_rejected_even_with_descendant_annotations():
    world = campaign_public_world("healthy")
    world["market_exchanges"][0]["estimate_availability"]["cleared_volume_index"] = False
    assert validate_logistics_exchange_replay(world)


def test_serialized_numeric_mutation_is_not_hidden_by_a_replay_tolerance():
    world = campaign_public_world("healthy")
    original = world["logistics_networks"][0]["transport_efficiency_index"]
    world["logistics_networks"][0]["transport_efficiency_index"] = original + .000001
    assert world["logistics_networks"][0]["transport_efficiency_index"] != original
    assert validate_logistics_exchange_replay(world)
