"""Historical E4 fire availability and history replay, no world generation."""
from copy import deepcopy
import gzip
import json
import math
from pathlib import Path

import pytest

from magic_geo.ecosystem_dynamics import enrich_world_with_ecosystem_dynamics as ecosystem
from magic_geo.aquatic_climate_validation import _EXPECTED_MODELS
from magic_geo.native_climate_energy import enrich_world_with_native_climate_energy
from magic_geo.wildfire_disturbance import (
    enrich_world_with_wildfire_disturbance as wildfire, _fuel_continuity,
    _spread_probability, _build_history, _ignition_potential,
)
from magic_geo.wildfire_aquatic_validation import validate_wildfire_aquatic_exclusion as validate
from support.native_climate_energy import native_climate_world

ARCHIVE = Path(__file__).resolve().parent / "fixtures/wildfire_parent_availability/native_v3_world.json.gz"
FLAGS = ("wildfire_fuel_continuity_supported", "wildfire_firebreak_supported", "wildfire_ignition_potential_supported")
VALUES = ("wildfire_fuel_continuity_index", "wildfire_firebreak_index", "wildfire_ignition_potential_index")


def cell(i=0, **overrides):
    return {"id": i, "neighbors": [], "temperature_c": 18.0, "area_km2": 1.0,
        "lat_deg": 0.0, "lon_deg": float(i), "is_water": False, "is_lake": False,
        "water_body_type": "land", "biome": "temperate_forest", "fertility": 1.0,
        "soil_moisture_index": 1.0, "soil_organic_carbon_fraction": .2,
        "fire_frequency_index": 1.0, "seasonal_aridity_index": 1.0,
        "settlement_score": 1.0, "wind_east": 1.0, "wind_north": 0.0,
        "climate_energy_stress_index": 1.0, **overrides}


def world(cells=None):
    return ecosystem({"cells": cells if cells is not None else [cell()],
                      "ecosystem_dynamics_model": deepcopy(_EXPECTED_MODELS["heuristic_ecosystem_climate_support_v4"])})


def chain(temperatures):
    return world([cell(i, temperature_c=t, neighbors=([i-1] if i else []) + ([i+1] if i+1 < len(temperatures) else [])) for i, t in enumerate(temperatures)])


@pytest.mark.parametrize("temperature", [-100, -16, 52, 80, None, True, "18", math.nan, math.inf, 10**1000])
def test_unknown_parent_is_not_empty_fuel_or_a_physical_barrier(temperature):
    w = wildfire(world([cell(temperature_c=temperature, ice_thickness_m=200, biome="ice_cap")]))
    c = w["cells"][0]
    assert all(c[flag] is False and c[value] == 0 for flag, value in zip(FLAGS, VALUES))
    assert c["wildfire_disturbance_regime"] == "fuel_proxy_unavailable"
    assert c["ice_thickness_m"] == 200 and c["biome"] == "ice_cap"
    assert w["wildfire_spread_histories"] == []
    assert w["summary"]["high_wildfire_firebreak_cell_count"] == 0
    assert validate(w) == []


@pytest.mark.parametrize("temperature", [math.nextafter(-16, math.inf), 18, math.nextafter(52, -math.inf)])
def test_no_extra_fire_thermal_interval_and_supported_zero_is_known(temperature):
    w = world([cell(temperature_c=temperature)])
    for field in ("primary_productivity_index", "vegetation_biomass_index", "wildfire_spread_risk_index", "ecosystem_disturbance_pressure_index"):
        w["cells"][0][field] = 0.0
    wildfire(w)
    assert all(w["cells"][0][flag] is True for flag in FLAGS)
    assert w["cells"][0]["wildfire_fuel_continuity_index"] > 0  # Preserved descriptor additions.
    assert validate(w) == []


def test_one_hop_biomass_support_and_failed_next_step_front_coverage():
    w = wildfire(chain([18, 18, 80]))
    assert [c[FLAGS[0]] for c in w["cells"]] == [True, False, False]
    history, = w["wildfire_spread_histories"]
    assert history["cell_ids"] == [0]
    assert len(history["steps"]) == 1
    for record in (history, history["steps"][0]):
        assert record["front_coverage_status"] == "partial_unavailable_inputs"
        assert record["unmodelled_adjacent_cell_ids"] == [1]
        assert record["unmodelled_front_cell_ids"] == [0]
        assert record["unmodelled_front_edges"] == [{"from_cell_id": 0, "to_cell_id": 1}]
        assert record["unmodelled_front_edge_count"] == 1
        assert record["containment_scope"] == "coefficient_index_on_modelled_cells_not_physical_containment"
    assert w["summary"]["wildfire_unmodelled_adjacent_cell_count"] == 1
    assert w["summary"]["wildfire_partial_front_history_count"] == 1
    assert validate(w) == []


def test_partial_front_is_tracked_after_successful_spread_too():
    w = wildfire(chain([18, 18, 18, 80]))
    history, = w["wildfire_spread_histories"]
    assert history["cell_ids"] == [0, 1]
    assert history["steps"][0]["front_coverage_status"] == "complete_for_examined_adjacency"
    assert history["steps"][1]["unmodelled_adjacent_cell_ids"] == [2]
    assert history["unmodelled_front_cell_ids"] == [1]
    assert validate(w) == []


@pytest.mark.parametrize("selector", [
    {"is_water": True}, {"is_lake": True}, {"is_lake": True, "water_body_type": "saline_basin"},
    {"water_body_type": "fresh_lake"}, {"water_body_type": "ocean"},
    {"water_body_type": "continental_shelf"}, {"water_body_type": "inland_sea"},
])
def test_aquatic_unknown_primary_is_known_nonburnability_and_retains_denominator(selector):
    w = world([cell(0, neighbors=[1, 2]), cell(1, neighbors=[0]), cell(2, neighbors=[0], temperature_c=80, **selector)])
    c, neighbor, aquatic = w["cells"]
    neighbor["vegetation_biomass_index"] = 1.0
    without = _fuel_continuity(c, [neighbor])
    with_water = _fuel_continuity(c, [neighbor, aquatic])
    assert math.isclose(without - with_water, .06, abs_tol=1e-12)
    wildfire(w)
    assert all(aquatic[flag] is True for flag in FLAGS)
    assert [aquatic[v] for v in VALUES] == [0, 1, 0]
    assert aquatic["wildfire_disturbance_regime"] == "non_burnable_water"
    assert aquatic["wildfire_spread_history_ids"] == []
    assert all(c[flag] is True for flag in FLAGS)
    assert all(aquatic["id"] not in h["unmodelled_adjacent_cell_ids"] for h in w["wildfire_spread_histories"])
    assert validate(w) == []


def test_dry_saline_and_known_ice_keep_separate_established_rules():
    dry = wildfire(world([cell(water_body_type="saline_basin")]))
    assert dry["wildfire_spread_histories"] and all(dry["cells"][0][f] for f in FLAGS)
    icy = wildfire(world([cell(ice_thickness_m=200)]))
    assert all(icy["cells"][0][f] for f in FLAGS)
    assert icy["cells"][0]["wildfire_disturbance_regime"] == "ice_or_barren_firebreak"
    assert icy["wildfire_spread_histories"] == []
    assert validate(dry) == validate(icy) == []


def test_unknown_source_and_target_are_unmodelled_edges_without_numeric_consumption():
    w = wildfire(chain([18, 18, 80]))
    known, unknown = w["cells"][:2]
    unknown["wildfire_fuel_continuity_index"] = object()
    assert _spread_probability(known, unknown) is None
    assert _spread_probability(unknown, known) is None
    with pytest.raises(ValueError):
        _build_history(0, unknown, {c["id"]: c for c in w["cells"]}, set(), availability_aware=True)


@pytest.mark.parametrize("field", ["primary_productivity_index", "vegetation_biomass_index", "wildfire_spread_risk_index", "ecosystem_disturbance_pressure_index", "wind_east"])
@pytest.mark.parametrize("bad", [None, True, "0", [], {}, math.nan, math.inf])
def test_present_malformed_inputs_fail_before_any_fire_mutation(field, bad):
    w = wildfire(chain([18, 18])); w["cells"][1][field] = bad
    before = json.dumps(w, sort_keys=True)
    with pytest.raises(ValueError): wildfire(w)
    assert json.dumps(w, sort_keys=True) == before
    assert validate(w)


@pytest.mark.parametrize("mutation", [
    lambda w: w["ecosystem_dynamics_model"].update(model="unknown"),
    lambda w: w["ecosystem_dynamics_model"].pop("ecosystem_wildfire_availability_policy"),
    lambda w: w.pop("ecosystem_dynamics_model"),
    lambda w: w["cells"][1].pop("vegetation_biomass_supported"),
    lambda w: w["cells"][1].update(vegetation_biomass_supported=False),
    lambda w: w["cells"][1].update(ecosystem_disturbance_pressure_supported=False),
    lambda w: w["cells"][1].update(id=0),
    lambda w: w["cells"][0].update(neighbors=[1, 999]),
    lambda w: w["cells"][0].update(neighbors=[1, 1]),
    lambda w: w["cells"][0].update(neighbors=[True]),
])
def test_unknown_partial_parent_and_graph_fail_closed(mutation):
    w = wildfire(chain([18, 18])); mutation(w); before = deepcopy(w)
    with pytest.raises(ValueError): wildfire(w)
    assert w == before
    assert validate(w)


@pytest.mark.parametrize("field,bad", [
    ("unmodelled_adjacent_cell_ids", []), ("unmodelled_adjacent_cell_ids", [True]),
    ("unmodelled_front_cell_ids", []), ("unmodelled_front_edges", []),
    ("unmodelled_front_edge_count", 0), ("unmodelled_front_edge_count", True),
    ("supported_front_edge_count", 99), ("front_coverage_status", "complete_for_examined_adjacency"),
    ("containment_scope", "physical_containment"),
])
@pytest.mark.parametrize("step", [False, True])
def test_history_unknown_front_coverage_is_independently_replayed(field, bad, step):
    w = wildfire(chain([18, 18, 80])); h = w["wildfire_spread_histories"][0]
    (h["steps"][0] if step else h)[field] = bad
    assert validate(w)


@pytest.mark.parametrize("field", FLAGS + VALUES + ("wildfire_disturbance_regime",))
def test_unavailable_cell_outputs_cannot_claim_known_zero_or_fuel(field):
    w = wildfire(chain([18, 18, 80]))
    w["cells"][1][field] = True if field in FLAGS else "sparse_fuel" if field == "wildfire_disturbance_regime" else 1.0
    assert validate(w)


def test_stale_results_rebuild_idempotently_without_recursive_loss():
    w = wildfire(chain([18, 18, 80])); expected = deepcopy(w)
    for c in w["cells"]:
        c.update(wildfire_fuel_continuity_supported=True, wildfire_firebreak_supported=True,
            wildfire_ignition_potential_supported=True, wildfire_fuel_continuity_index=1,
            wildfire_firebreak_index=1, wildfire_ignition_potential_index=1,
            wildfire_disturbance_regime="sparse_fuel", wildfire_spread_history_ids=[99])
    w["wildfire_spread_histories"] = [{"id": 99}]
    wildfire(w)
    assert w == expected
    assert validate(w) == []


def test_supported_values_and_existing_history_fields_match_old_coefficients():
    fixture = Path(__file__).parent / "fixtures/wildfire_parent_availability/supported_legacy_v2_world.json"
    old = json.loads(fixture.read_text())
    assert validate(old) == []
    w = deepcopy(old)
    ecosystem(w)
    wildfire(w)
    for a, b in zip(w["cells"], old["cells"]):
        for key in VALUES + ("wildfire_wind_alignment_index", "wildfire_disturbance_regime", "wildfire_spread_history_ids"):
            assert a[key] == b[key]
    for current, prior in zip(w["wildfire_spread_histories"], old["wildfire_spread_histories"]):
        for key, value in prior.items():
            if key == "steps":
                for a, b in zip(current[key], value):
                    assert {k: a[k] for k in b} == b
            else: assert current[key] == value
    for key, value in old["summary"].items(): assert w["summary"][key] == value


@pytest.mark.parametrize("parent_version", [None, 2, 3])
def test_exact_historical_parent_and_v2_fire_archive_remain_compatible(parent_version):
    fixture = Path(__file__).parent / "fixtures/wildfire_parent_availability/supported_legacy_v2_world.json"
    w = json.loads(fixture.read_text())
    if parent_version is None: w.pop("ecosystem_dynamics_model")
    elif parent_version == 2:
        w["ecosystem_dynamics_model"]["model"] = "heuristic_ecosystem_climate_support_v2"
        w["ecosystem_dynamics_model"].pop("aquatic_ecology_policy")
    assert validate(w) == []
    expected = deepcopy(w); wildfire(w)
    assert w == expected
    assert w["wildfire_disturbance_model"]["model"] == "heuristic_wildfire_aquatic_exclusion_v2"
    assert validate(w) == []


def test_actual_native_certificate_preserved_new_model_and_old_v3_archive_replay():
    w = enrich_world_with_native_climate_energy(native_climate_world())
    # This control exercises the retained E4/fire5 branch on actual native data.
    w["ecosystem_dynamics_model"] = deepcopy(_EXPECTED_MODELS["heuristic_ecosystem_climate_support_v4"])
    certificate_keys = ("climate_model", "climate_energy_model", "climate_energy_balance_records", "climate_energy_transport_edges", "climate_energy_forcing_intervals")
    before = {key: deepcopy(w[key]) for key in certificate_keys}
    old = json.loads(gzip.decompress(ARCHIVE.read_bytes()))
    assert old["wildfire_disturbance_model"]["model"] == "heuristic_wildfire_native_seasonal_v3"
    assert validate(old) == []
    ecosystem(w); wildfire(w)
    assert w["wildfire_disturbance_model"]["model"] == "heuristic_wildfire_native_seasonal_parent_availability_v5"
    assert {key: w[key] for key in certificate_keys} == before
    assert validate(w) == []
    c = cell(wildfire_spread_risk_index=.3, ecosystem_disturbance_pressure_index=.4)
    assert math.isclose(_ignition_potential(c,.3,.1,.2) - _ignition_potential(c,.3,.1,.2,native_seasonal=True), .06, abs_tol=1e-15)


def test_summary_supported_counts_rounding_and_model_metadata_cannot_drift():
    w = wildfire(chain([18, 18, 80])); original = deepcopy(w)
    for key in original["wildfire_disturbance_model"]:
        tampered = deepcopy(original); tampered["wildfire_disturbance_model"][key] = "unknown"
        assert validate(tampered)
    for key in original["summary"]:
        if key != "high_wildfire_spread_risk_cell_count" and key.startswith(("high_wildfire_", "wildfire_")) and type(original["summary"][key]) is int:
            tampered = deepcopy(original); tampered["summary"][key] += 1
            assert validate(tampered), key


@pytest.mark.parametrize("offset,expected", [(-.0000004, 1), (-.0000006, 0)])
@pytest.mark.parametrize("kind", ["fuel", "ignition", "firebreak"])
def test_supported_counters_keep_published_six_decimal_thresholds(kind, offset, expected):
    c = cell(biome="stable_lowland", wind_east=0, seasonal_aridity_index=0, settlement_score=0, climate_energy_stress_index=0)
    w = world([c] if kind != "firebreak" else [dict(c, neighbors=[1]), cell(1, neighbors=[0], is_water=True)])
    target = w["cells"][0]
    for field in ("primary_productivity_index", "vegetation_biomass_index", "wildfire_spread_risk_index", "ecosystem_disturbance_pressure_index"):
        target[field] = 0
    if kind == "fuel":
        target["vegetation_biomass_index"] = 1
        target["primary_productivity_index"] = (.35 + offset - .32) / .16
        key = "high_wildfire_fuel_continuity_cell_count"
    elif kind == "ignition":
        target["wildfire_spread_risk_index"] = (.28 + offset + .0324) / .40248
        key = "high_wildfire_ignition_potential_cell_count"
    else:
        target["wetland_extent_index"] = (.55 + offset - .52) / .24
        key = "high_wildfire_firebreak_cell_count"
        expected += 1  # Known aquatic firebreak retains its existing count.
    wildfire(w)
    assert w["summary"][key] == expected
    assert validate(w) == []


@pytest.mark.parametrize("overrides", [
    {"lon_deg": 1e300}, {"lat_deg": 91}, {"biome": ["forest"]},
    {"wind_east": 1.7e308, "wind_north": 1.7e308},
])
def test_invalid_consumed_geometry_does_not_hang_or_partially_mutate(overrides):
    w = world(); w["cells"][0].update(overrides); before = deepcopy(w)
    with pytest.raises(ValueError): wildfire(w)
    assert w == before


def test_existing_event_limit_retained_without_generation():
    w = wildfire(world([cell(i) for i in range(97)]))
    assert len(w["wildfire_spread_histories"]) == 96
    assert sum(bool(c["wildfire_spread_history_ids"]) for c in w["cells"]) == 96
    assert validate(w) == []


@pytest.mark.parametrize("bad", [None, [], True, 0, "world"])
def test_malformed_world_root_returns_actionable_validation_error(bad):
    assert validate(bad) == ["wildfire availability requires a world object"]


@pytest.mark.parametrize("bad", [None, [], True, 0, "summary"])
@pytest.mark.parametrize("parent_aware", [False, True])
def test_present_malformed_summary_rejects_before_any_fire_mutation(bad, parent_aware):
    w = world() if parent_aware else {"cells": [cell()]}
    w["summary"] = bad
    before = deepcopy(w)
    with pytest.raises(ValueError, match="summary must be an object"):
        wildfire(w)
    assert w == before


@pytest.mark.parametrize("parent_aware", [False, True])
def test_absent_summary_is_created_for_both_fire_contracts(parent_aware):
    w = world() if parent_aware else {"cells": [cell()]}
    w.pop("summary", None)
    wildfire(w)
    assert isinstance(w["summary"], dict)
    assert validate(w) == []
