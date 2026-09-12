"""Scoped equation controls; these projections are not new public worlds."""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from magic_geo.logistics_availability import networks_and_exchanges
from magic_geo.campaign_availability import campaign_records
from magic_geo.logistics_exchange_validation import _expected_logistics_exchanges
from magic_geo.campaign_operations_validation import _expected_campaign_operations
from magic_geo.logistics_availability_validation import expected_networks_and_exchanges
from magic_geo.campaign_availability_validation import expected_campaign_records


@pytest.fixture(scope="module")
def retained():
    root = Path(__file__).parent / "fixtures" / "legacy_human_water"
    entry = json.loads((root / "manifest.json").read_text())["small_smoke"]
    raw = (root / entry["fixture"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == entry["fixture_gzip_sha256"]
    data = gzip.decompress(raw)
    assert hashlib.sha256(data).hexdigest() == entry["world_sha256"]
    return json.loads(data)


def scoped_inputs(retained):
    world = deepcopy(retained)
    # Equation-only source flags: no model declarations or physical certificates
    # are modified, and no public producer/validator consumes this projection.
    world["native_social_availability"] = {"conflict_inference_available": True}
    for record in world["economy_histories"]:
        for row in [record, *record["steps"]]:
            row["estimate_availability"] = {key: True for key, value in row.items() if type(value) in (int, float)}
    return world


def assert_projection(actual, expected):
    if type(expected) is dict:
        for key, value in expected.items():
            assert key in actual
            assert_projection(actual[key], value)
    elif type(expected) is list:
        assert len(actual) == len(expected)
        for left, right in zip(actual, expected):
            assert_projection(left, right)
    elif type(expected) is float:
        assert actual == pytest.approx(expected, abs=2e-6, rel=0)
    else:
        assert actual == expected


def test_complete_network_and_exchange_equations_match_independent_legacy_oracle(retained):
    world = scoped_inputs(retained)
    before = deepcopy(world)
    actual = networks_and_exchanges(world)
    networks, exchanges, summary = _expected_logistics_exchanges(retained)
    assert_projection(actual["logistics_networks"], networks)
    assert_projection(actual["market_exchanges"], exchanges)
    assert_projection(actual["summary"], summary)
    assert world == before


def test_complete_campaign_equations_match_independent_legacy_oracle(retained):
    world = scoped_inputs(retained)
    networks = networks_and_exchanges(world)["logistics_networks"]
    before = deepcopy(world)
    actual = campaign_records(world, {row["region_id"]: row for row in networks})
    expected = _expected_campaign_operations(retained)
    for key, records in zip(("campaign_movements", "campaign_path_segments", "campaign_front_histories", "tactical_engagements", "strategic_campaign_plans"), expected[:5]):
        assert_projection(actual[key], records)
    assert_projection(actual["summary"], expected[-1])
    assert world == before


@pytest.mark.parametrize("field,missing", [
    ("max_army_capacity_population", {"army_capacity_population", "supply_capacity_index"}),
    ("peak_gross_output_index", {"supply_capacity_index"}),
    ("peak_treasury_index", {"logistics_resilience_index"}),
])
def test_unavailable_economy_does_not_remove_independent_network_fields(retained, field, missing):
    world = scoped_inputs(retained)
    baseline = networks_and_exchanges(world)
    economy = world["economy_histories"][0]
    economy[field] = None
    economy["estimate_availability"][field] = False
    actual = networks_and_exchanges(world)
    expected, exchanges, summaries = expected_networks_and_exchanges(world)
    assert_projection(actual["logistics_networks"], expected)
    assert_projection(actual["market_exchanges"], exchanges)
    assert_projection(actual["summary"], summaries)
    for old, new in zip(baseline["logistics_networks"], actual["logistics_networks"]):
        for key in old["estimate_availability"]:
            if old["region_id"] == economy["region_id"] and key in missing:
                assert new[key] is None and new["estimate_availability"][key] is False
            else:
                assert new[key] == old[key]


@pytest.mark.parametrize("field", ["army_capacity_population", "logistics_resilience_index"])
def test_unavailable_operations_preserve_campaign_geometry(retained, field):
    world = scoped_inputs(retained)
    networks = {row["region_id"]: row for row in networks_and_exchanges(world)["logistics_networks"]}
    baseline = campaign_records(world, networks)
    assert baseline["campaign_movements"]
    origin = baseline["campaign_movements"][0]["origin_region_id"]
    networks[origin][field] = None
    networks[origin]["estimate_availability"][field] = False
    actual = campaign_records(world, networks)
    expected = expected_campaign_records(world, networks)
    for key, rows in zip(("campaign_movements", "campaign_path_segments", "campaign_front_histories", "tactical_engagements", "strategic_campaign_plans"), expected[:5]):
        assert_projection(actual[key], rows)
    assert len(actual["campaign_movements"]) == len(baseline["campaign_movements"])
    for old, new in zip(baseline["campaign_movements"], actual["campaign_movements"]):
        for key in ("path_cell_ids", "path_length_km", "path_terrain_cost_index", "travel_time_days", "force_estimate"):
            assert new[key] == old[key]
        if old["origin_region_id"] == origin:
            assert new["campaign_success_index"] is None
            assert new["campaign_front_history_id"] is None
            assert new["campaign_front_history_available"] is False
    assert actual["campaign_operations_availability"]["movement"]["inference_available"] is True
    assert actual["campaign_operations_availability"]["front"]["inference_available"] is False
    assert actual["summary"]["campaign_front_history_count"] is None


def test_incomplete_conflict_scope_does_not_mean_zero_campaigns(retained):
    world = scoped_inputs(retained)
    world["native_social_availability"]["conflict_inference_available"] = False
    world["conflicts"] = []
    networks = {row["region_id"]: row for row in networks_and_exchanges(world)["logistics_networks"]}
    actual = campaign_records(world, networks)
    assert actual["campaign_movements"] == []
    assert actual["summary"]["campaign_movement_count"] is None
    assert actual["summary"]["recorded_campaign_movement_count"] == 0
    assert actual["campaign_operations_availability"]["movement"]["applicable_source_count"] is None
