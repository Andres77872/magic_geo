"""Exact E5 commodity source evidence; retained inputs, no material recalibration."""
from copy import deepcopy
import pytest

from magic_geo import commodity_resources as producer
from magic_geo.resource_dynamics import enrich_world_with_resource_deposits
from magic_geo.biological_resource_validation import BiologicalResourceValidationError, validate_biological_resources
from support.prescribed_resource_worlds import fresh_resource_inputs, retained_resource_world, clear_resource_stage


@pytest.fixture(scope="module")
def current():
    world = fresh_resource_inputs()
    enrich_world_with_resource_deposits(world)
    producer.enrich_world_with_commodity_occurrences(world)
    assert validate_biological_resources(world) == []
    return world


def linked_record(world):
    return next(r for r in world["commodity_occurrences"] if "sedimentary_resource_system_id" in r["formation_evidence"])


def linked_source(world):
    rid = linked_record(world)["formation_evidence"]["sedimentary_resource_system_id"]
    return next(s for s in world["sedimentary_resource_systems"] if s["id"] == rid)


def assert_atomic(world):
    before = deepcopy(world)
    refs = {k: v for k, v in world.items() if isinstance(v, (dict, list))}
    cells = list(world["cells"])
    with pytest.raises(BiologicalResourceValidationError) as error:
        producer.enrich_world_with_commodity_occurrences(world)
    assert len(str(error.value)) <= 600
    assert world == before and all(world[k] is v for k, v in refs.items())
    assert all(a is b for a, b in zip(cells, world["cells"]))


EVIDENCE = ("volcanic_potential_index", "sedimentary_resource_system_id", "petroleum_potential_index",
            "gas_potential_index", "coal_potential_index", "evaporite_salt_potential_index")


@pytest.mark.parametrize("field", EVIDENCE)
@pytest.mark.parametrize("operation", ["remove", "wrong", "boolean"])
def test_each_source_evidence_field_is_required_and_independently_replayed(current, field, operation):
    world = deepcopy(current)
    evidence = linked_record(world)["formation_evidence"]
    if operation == "remove": del evidence[field]
    else: evidence[field] = 999999 if operation == "wrong" else True
    before = deepcopy(world)
    assert validate_biological_resources(world)
    assert world == before


def test_unexpected_source_evidence_is_rejected(current):
    world = deepcopy(current)
    linked_record(world)["formation_evidence"]["unclaimed_source"] = 1
    assert validate_biological_resources(world)


@pytest.mark.parametrize("published", [False, True])
@pytest.mark.parametrize("operation", ["negative", "boolean", "missing", "duplicate_selected", "duplicate_unselected"])
def test_selected_source_links_are_nonnegative_and_unambiguous_before_publication(current, published, operation):
    world = deepcopy(current)
    source = linked_source(world)
    linked = {r["formation_evidence"].get("sedimentary_resource_system_id") for r in world["commodity_occurrences"]}
    if operation == "negative": source["id"] = -1
    elif operation == "boolean": source["id"] = True
    elif operation == "missing": del source["id"]
    elif operation == "duplicate_selected":
        other = next(s for s in world["sedimentary_resource_systems"] if s["id"] in linked and s is not source)
        source["id"] = other["id"]
    else:
        world["sedimentary_resource_systems"].append({"id": source["id"], "basin_id": -1})
    if not published: clear_resource_stage(world, "commodity")
    assert_atomic(world)
    if published: assert validate_biological_resources(world)


@pytest.mark.parametrize("field", EVIDENCE)
def test_stale_selected_source_or_volcanic_evidence_is_rejected(current, field):
    world = deepcopy(current)
    record = linked_record(world)
    if field == "volcanic_potential_index":
        source = next(c for c in world["cells"] if c["id"] == record["cell_id"])
    else:
        source = linked_source(world)
    key = "id" if field == "sedimentary_resource_system_id" else field
    source[key] = 987654 if key == "id" else (0.0 if source[key] > 0.5 else 1.0)
    assert validate_biological_resources(world)


@pytest.mark.parametrize("field", EVIDENCE)
def test_tampered_producer_evidence_fails_independent_preaudit_atomically(current, monkeypatch, field):
    world = deepcopy(current)
    original = producer._formation_evidence
    def bad(*args):
        evidence = original(*args)
        evidence.pop(field, None)
        return evidence
    monkeypatch.setattr(producer, "_formation_evidence", bad)
    assert_atomic(world)


@pytest.mark.parametrize("confidence", [-2.0, -1.000001])
def test_below_initial_confidence_sentinel_is_skipped_without_consuming_missing_potentials(current, confidence):
    # Controlled sedimentary-stage inputs on retained cells, not full-world
    # geological consistency: the unchanged selector starts at confidence -1.
    world = deepcopy(current)
    basin = linked_record(world)["basin_id"]
    world["sedimentary_resource_systems"] = [{"basin_id": basin, "system_confidence_index": confidence}]
    producer.enrich_world_with_commodity_occurrences(world)
    assert validate_biological_resources(world) == []
    assert all("sedimentary_resource_system_id" not in r["formation_evidence"] for r in world["commodity_occurrences"])


@pytest.mark.parametrize("confidence", [-1.0, 0.5])
def test_equal_confidence_uses_last_source_with_exact_clamped_rounded_evidence(current, confidence):
    world = deepcopy(current)
    basin = linked_record(world)["basin_id"]
    first = dict(id=9001, basin_id=basin, system_confidence_index=confidence,
                 petroleum_potential_index=-2.0, gas_potential_index=2.0,
                 coal_potential_index=0.123456789, evaporite_salt_potential_index=0.345678912)
    second = {**first, "id": 9002, "petroleum_potential_index": 0.87654321}
    world["sedimentary_resource_systems"] = [first, second]
    producer.enrich_world_with_commodity_occurrences(world)
    assert validate_biological_resources(world) == []
    records = [r for r in world["commodity_occurrences"] if r["basin_id"] == basin]
    assert records
    for record in records:
        evidence = record["formation_evidence"]
        assert {k: evidence[k] for k in EVIDENCE[1:]} == {
            "sedimentary_resource_system_id": 9002, "petroleum_potential_index": 0.876543,
            "gas_potential_index": 1.0, "coal_potential_index": 0.123457,
            "evaporite_salt_potential_index": 0.345679}
    world["sedimentary_resource_systems"].reverse()
    assert validate_biological_resources(world)  # Retained evidence is now stale.
    producer.enrich_world_with_commodity_occurrences(world)
    assert validate_biological_resources(world) == []
    assert all(r["formation_evidence"]["sedimentary_resource_system_id"] == 9001
               for r in world["commodity_occurrences"] if r["basin_id"] == basin)


def test_negative_basin_sentinel_does_not_consume_confidence_or_potentials(current):
    world = deepcopy(current)
    world["sedimentary_resource_systems"] = [{"basin_id": -1}]
    producer.enrich_world_with_commodity_occurrences(world)
    assert validate_biological_resources(world) == []
    assert all("sedimentary_resource_system_id" not in r["formation_evidence"] for r in world["commodity_occurrences"])


@pytest.mark.parametrize("confidence", [-2.0, 0.5])
def test_changed_producer_source_selection_is_detected_atomically(current, monkeypatch, confidence):
    world = deepcopy(current)
    source = deepcopy(linked_source(world))
    source.update(id=9001, system_confidence_index=confidence)
    world["sedimentary_resource_systems"] = [source, {**source, "id": 9002}]
    # Wrong producer chooses the first even below -1 or at a later equal tie;
    # the independent helper must reproduce the original selector instead.
    monkeypatch.setattr(producer, "_sedimentary_system_by_basin_id", lambda _: {source["basin_id"]: source})
    assert_atomic(world)


def test_exact_historical_commodity1_evidence_scope_is_unchanged():
    world = retained_resource_world()
    linked_record(world)["formation_evidence"].pop("volcanic_potential_index")
    assert validate_biological_resources(world) == []
