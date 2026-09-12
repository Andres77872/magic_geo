"""Isolated ecosystem v5: actual-source replay, arithmetic and atomic contracts."""
from copy import deepcopy
from decimal import Decimal
from functools import lru_cache
import gzip
import hashlib
import json
import math
from pathlib import Path

import pytest

from magic_geo import ecosystem_dynamics as producer
from magic_geo.aquatic_climate_validation import _EXPECTED_MODELS, validate_aquatic_climate_support
from magic_geo.prescribed_natural_ecosystem_validation import (
    CELL_FIELDS, RECORD_FIELDS, SUMMARY_FIELDS, PrescribedNaturalEcosystemError,
    validate_prescribed_natural_ecosystem,
)

DATA = Path(__file__).parent / "data/prescribed_natural_ecosystem"


@lru_cache(maxsize=None)
def archived(scope="full"):
    record = json.loads((DATA / "manifest.json").read_text())[scope]
    packed = (DATA / record["file"]).read_bytes()
    assert hashlib.sha256(packed).hexdigest() == record["compressed_sha256"]
    raw = gzip.decompress(packed)
    assert hashlib.sha256(raw).hexdigest() == record["raw_sha256"]
    world = json.loads(raw)
    assert len(world["cells"]) == record["cell_count"]
    return world


def owned(world):
    return {"cells": [{key: c[key] for key in CELL_FIELDS} for c in world["cells"]],
            "summary": {key: world["summary"][key] for key in SUMMARY_FIELDS},
            **{key: world[key] for key in RECORD_FIELDS},
            "ecosystem_dynamics_model": world["ecosystem_dynamics_model"]}


def fresh_inputs(scope="full"):
    """Deliberate v4 migration clears precisely this stage's complete ownership."""
    world = deepcopy(archived(scope))
    assert world["ecosystem_dynamics_model"] == _EXPECTED_MODELS["heuristic_ecosystem_climate_support_v4"]
    assert validate_aquatic_climate_support(world) == []
    for c in world["cells"]:
        for key in CELL_FIELDS:
            c.pop(key)
    for key in SUMMARY_FIELDS:
        world["summary"].pop(key)
    for key in (*RECORD_FIELDS, "ecosystem_dynamics_model"):
        world.pop(key)
    return world


def stage_input(**overrides):
    c = dict(id=0, biome="temperate_forest", water_body_type="land", is_water=False,
             is_lake=False, temperature_c=18.0, precipitation_mm_y=600.0,
             potential_evapotranspiration_mm_y=1000.0, soil_moisture_index=.5,
             fertility=.5, growing_season_months=6.0, soil_organic_matter_fraction=.1,
             fire_frequency_index=.3, seasonal_aridity_index=.2, ecotone_index=.4,
             erosion_rate=.008, wind_east=.3, wind_north=.4, runoff_mm_y=0.0,
             ocean_current_temperature_c=0.0, ocean_current_east=0.0,
             ice_thickness_m=0.0, groundwater_recharge_mm_y=0.0)
    c.update(overrides)
    return {"cells": [c], "summary": {}}


def build(world):
    assert producer.enrich_world_with_ecosystem_dynamics(world) is world
    assert validate_aquatic_climate_support(world) == []
    assert validate_prescribed_natural_ecosystem(world) == []
    return world


def test_actual_full_and_geo_natural_values_are_identical_after_deliberate_upgrade():
    full, geo = build(fresh_inputs("full")), build(fresh_inputs("geo"))
    assert owned(full) == owned(geo)
    assert full["settlements"] and "settlements" not in geo
    assert full["vegetation_succession_histories"] and full["renewable_resource_records"]
    assert any(c["ecosystem_disturbance_pressure_index"] != old["ecosystem_disturbance_pressure_index"]
               for c, old in zip(full["cells"], archived()["cells"]))


@pytest.mark.parametrize("value", [None, True, "not activity", [], {}, math.nan, math.inf, -math.inf, 1 << 20000, -.5, 0., .25, 1., 2.],
                         ids=["null", "bool", "text", "list", "dict", "nan", "inf", "minusinf", "hugeint", "negative", "zero", "interior", "one", "aboveone"])
def test_actual_inputs_ignore_present_missing_or_malformed_settlement_score(value):
    world = fresh_inputs()
    baseline = fresh_inputs()
    for c in baseline["cells"]:
        c.pop("settlement_score", None)
    for c in world["cells"]:
        c["settlement_score"] = value
    assert owned(build(world)) == owned(build(baseline))
    assert all(c["settlement_score"] is value for c in world["cells"])


@pytest.mark.parametrize("records", [None, [], [{"id": 0, "cell_id": 9, "score": .99}], "not consumed"])
def test_selected_settlement_records_are_not_an_activity_input(records):
    world = fresh_inputs()
    world["settlements"] = records
    assert owned(build(world)) == owned(build(fresh_inputs()))
    assert world["settlements"] is records


@pytest.mark.parametrize("scope", ["full", "geo"])
def test_exact_declared_v4_is_historically_identical(scope):
    world = deepcopy(archived(scope))
    before = deepcopy(world)
    producer.enrich_world_with_ecosystem_dynamics(world)
    assert world == before
    assert world["ecosystem_dynamics_model"]["model"].endswith("_v4")
    assert validate_aquatic_climate_support(world) == []


@pytest.mark.parametrize("version", ["v2", "v3"])
def test_exact_known_older_producer_inputs_retain_existing_upgrade_to_v4(version):
    world = stage_input(settlement_score=.8)
    world["ecosystem_dynamics_model"] = deepcopy(_EXPECTED_MODELS["heuristic_ecosystem_climate_support_" + version])
    producer.enrich_world_with_ecosystem_dynamics(world)
    assert world["ecosystem_dynamics_model"] == _EXPECTED_MODELS["heuristic_ecosystem_climate_support_v4"]
    assert validate_aquatic_climate_support(world) == []
    old = deepcopy(world)
    producer.enrich_world_with_ecosystem_dynamics(world)
    assert world == old


def test_decimal_raw_ancestry_and_no_renormalization():
    world = build(stage_input(settlement_score=.75))
    d = Decimal
    p = d('.26') + d('.6') * d('.22') + d('.5') * d('.18') + d('.5') * d('.18') + d('.5') * d('.18') - d('.2') * d('.14')
    b = p * d('.52') + d('.1') * d('.18') + d('.5') * d('.14') + d('.28')
    risk = d('.3') * d('.38') + b * d('.22') + d('.2') * d('.22') + d('.5') * d('.10')
    disturbance = risk * d('.42') + d('.4') * d('.16') + d('.1') * d('.14') + d('.2') * d('.12')
    forest = p * d('.44') + b * d('.28') + d('.5') * d('.14') + d('.5') * d('.12') - disturbance * d('.16')
    for key, expected in (("primary_productivity_index", p), ("vegetation_biomass_index", b),
                          ("wildfire_spread_risk_index", risk), ("ecosystem_disturbance_pressure_index", disturbance),
                          ("forest_growth_index", forest)):
        assert world["cells"][0][key] == float(expected.quantize(d('.000001')))
    legacy = stage_input(settlement_score=.75)
    legacy["ecosystem_dynamics_model"] = deepcopy(_EXPECTED_MODELS["heuristic_ecosystem_climate_support_v4"])
    producer.enrich_world_with_ecosystem_dynamics(legacy)
    assert abs(legacy["cells"][0]["ecosystem_disturbance_pressure_index"] - world["cells"][0]["ecosystem_disturbance_pressure_index"] - .16 * .75) < 1e-6


def test_raw_parent_rounding_boundary_is_not_replayed_from_published_risk():
    fertility = 3 / 997
    world = build(stage_input(fertility=fertility))
    d = Decimal
    f = d.from_float(fertility)
    p = d('.26') + d('.6') * d('.22') + d('.5') * d('.18') + f * d('.18') + d('.5') * d('.18') - d('.2') * d('.14')
    b = p * d('.52') + d('.1') * d('.18') + d('.5') * d('.14') + d('.28')
    risk = d('.3') * d('.38') + b * d('.22') + d('.2') * d('.22') + d('.5') * d('.10')
    expected = risk * d('.42') + d('.4') * d('.16') + d('.1') * d('.14') + d('.2') * d('.12')
    assert float(expected.quantize(d('.000001'))) == .249527
    c = world["cells"][0]
    assert c["ecosystem_disturbance_pressure_index"] == .249527
    wrong = round(c["wildfire_spread_risk_index"] * .42 + .4 * .16 + .1 * .14 + .2 * .12, 6)
    assert wrong == .249528
    c["ecosystem_disturbance_pressure_index"] = wrong
    assert validate_prescribed_natural_ecosystem(world)


@pytest.mark.parametrize("temperature", [-100., -16., math.nextafter(-16., math.inf), 18., math.nextafter(52., -math.inf), 52., 100., None, "18", math.nan])
@pytest.mark.parametrize("aquatic", [False, True])
def test_existing_own_temperature_support_and_aquatic_zero_policies(temperature, aquatic):
    world = build(stage_input(temperature_c=temperature, is_lake=aquatic,
                              water_body_type="fresh_lake" if aquatic else "land"))
    c = world["cells"][0]
    if aquatic:
        assert c["vegetation_biomass_index"] == c["wildfire_spread_risk_index"] == c["forest_growth_index"] == 0.
        assert c["vegetation_succession_stage"] == "aquatic_primary_productivity"
        assert world["vegetation_succession_histories"] == []
    if not c["primary_productivity_supported"]:
        assert c["primary_productivity_index"] == 0.
        assert c["vegetation_recovery_supported"] is False
        assert c["vegetation_recovery_years"] == 0


@pytest.mark.parametrize("key", CELL_FIELDS)
def test_every_cell_owned_output_is_independently_replayed(key):
    world = build(stage_input())
    value = world["cells"][0][key]
    world["cells"][0][key] = not value if type(value) is bool else (value + 1 if isinstance(value, (int, float)) else "unknown")
    assert validate_prescribed_natural_ecosystem(world)
    assert validate_aquatic_climate_support(world)


@pytest.mark.parametrize("key", SUMMARY_FIELDS)
def test_every_summary_counter_and_mean_is_replayed(key):
    world = build(stage_input())
    world["summary"][key] = None
    assert validate_prescribed_natural_ecosystem(world)


@pytest.mark.parametrize("family", RECORD_FIELDS)
def test_record_coverage_and_every_first_record_field_are_replayed(family):
    source = build(fresh_inputs())
    assert source[family]
    world = deepcopy(source)
    world[family].pop(0)
    assert validate_prescribed_natural_ecosystem(world)
    for key in source[family][0]:
        world = deepcopy(source)
        world[family][0][key] = None
        assert validate_prescribed_natural_ecosystem(world), (family, key)
    if family == "vegetation_succession_histories":
        for step in range(4):
            for key in source[family][0]["steps"][step]:
                world = deepcopy(source)
                world[family][0]["steps"][step][key] = None
                assert validate_prescribed_natural_ecosystem(world), (step, key)


def test_unknown_model_partial_mirrors_and_late_bad_physical_input_reject_atomically():
    cases = []
    w = fresh_inputs(); w["ecosystem_dynamics_model"] = {"model": "future"}; cases.append(w)
    w = deepcopy(archived()); del w["ecosystem_dynamics_model"]; cases.append(w)
    w = fresh_inputs(); w["cells"][-1]["soil_moisture_index"] = None; cases.append(w)
    w = fresh_inputs(); w["cells"][-1]["wind_east"] = 1e308; cases.append(w)
    for world in cases:
        before = deepcopy(world)
        refs = {key: value for key, value in world.items() if isinstance(value, (dict, list))}
        with pytest.raises(PrescribedNaturalEcosystemError):
            producer.enrich_world_with_ecosystem_dynamics(world)
        assert world == before
        assert all(world[key] is value for key, value in refs.items())


@pytest.mark.parametrize("field", [*CELL_FIELDS, *SUMMARY_FIELDS, *RECORD_FIELDS])
def test_first_call_cannot_reinterpret_any_undeclared_mirror(field):
    world = stage_input()
    if field in CELL_FIELDS:
        world["cells"][0][field] = 0
    elif field in SUMMARY_FIELDS:
        world["summary"][field] = 0
    else:
        world[field] = []
    before = deepcopy(world)
    with pytest.raises(PrescribedNaturalEcosystemError, match="undeclared owned outputs"):
        producer.enrich_world_with_ecosystem_dynamics(world)
    assert world == before


def test_v5_stale_numerics_are_rebuilt_idempotently_with_unowned_identity_retained():
    world = build(fresh_inputs())
    original = deepcopy(world)
    refs = {key: value for key, value in world.items() if key not in (*RECORD_FIELDS, "ecosystem_dynamics_model")}
    cell_refs = list(world["cells"])
    world["cells"][0]["ecosystem_disturbance_pressure_index"] = .999999
    build(world)
    assert world == original
    assert all(world[key] is value for key, value in refs.items())
    assert all(a is b for a, b in zip(world["cells"], cell_refs))
    build(world)
    assert world == original


@pytest.mark.parametrize("published", [False, True])
def test_changed_producer_equation_is_rejected_before_any_publication(monkeypatch, published):
    world = build(fresh_inputs()) if published else fresh_inputs()
    original = producer._disturbance_pressure
    def wrong(cell, biomass, *, prescribed_natural=False):
        return original(cell, biomass, prescribed_natural=False)
    monkeypatch.setattr(producer, "_disturbance_pressure", wrong)
    before = deepcopy(world)
    with pytest.raises(PrescribedNaturalEcosystemError, match="raw-input replay"):
        producer.enrich_world_with_ecosystem_dynamics(world)
    assert world == before


@pytest.mark.parametrize("change", ["missing-policy", "extra-policy", "typed-bound", "old-scope"])
def test_reenrichment_cannot_silently_repair_a_corrupt_v5_declaration(change):
    world = build(fresh_inputs())
    model = world["ecosystem_dynamics_model"]
    if change == "missing-policy":
        del model["activity_forcing_policy"]
    elif change == "extra-policy":
        model["unclaimed"] = True
    elif change == "typed-bound":
        model["aquatic_primary_maximum_temperature_c"] = 52
    else:
        model["ecosystem_disturbance_input_scope"] = _EXPECTED_MODELS["heuristic_ecosystem_climate_support_v4"]["ecosystem_disturbance_input_scope"]
    before = deepcopy(world)
    assert validate_prescribed_natural_ecosystem(world)
    with pytest.raises(PrescribedNaturalEcosystemError, match="unknown or malformed own model"):
        producer.enrich_world_with_ecosystem_dynamics(world)
    assert world == before


def test_empty_v5_is_complete_and_unknown_empty_model_cannot_hide_in_early_return():
    world = build({"cells": [], "summary": {}})
    assert all(world[key] == [] for key in RECORD_FIELDS)
    assert world["summary"]["mean_primary_productivity_index"] == 0.0
    before = deepcopy(world)
    world["ecosystem_dynamics_model"]["model"] = "future"
    invalid = deepcopy(world)
    with pytest.raises(PrescribedNaturalEcosystemError):
        producer.enrich_world_with_ecosystem_dynamics(world)
    assert world == invalid
    assert before["ecosystem_dynamics_model"]["model"].endswith("_v5")
