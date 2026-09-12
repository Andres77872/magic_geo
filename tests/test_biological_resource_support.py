"""Historical E4 resource stages; no generation or native-world certificate."""

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

import pytest

from magic_geo.aquatic_climate_validation import _EXPECTED_MODELS, validate_aquatic_climate_support
from magic_geo.biological_resource_validation import validate_biological_resources
from magic_geo.commodity_resources import enrich_world_with_commodity_occurrences
from magic_geo.ecosystem_dynamics import enrich_world_with_ecosystem_dynamics
from magic_geo.resource_dynamics import enrich_world_with_resource_deposits


DATA = Path(__file__).parent / "data"
ACTUAL = json.loads((DATA / "biological_resource_inputs.json").read_text())
LEGACY = json.loads((DATA / "biological_resource_legacy_outputs.json").read_text())


def cell(**overrides):
    return {"id": 0, "area_km2": 1.0, "neighbors": [], "temperature_c": 18.0,
            "is_water": True, "is_lake": False, "water_body_type": "continental_shelf",
            "resource": "coastal_fisheries", "biome": "shallow_marine", "flow_accumulation": 1.0,
            "runoff_mm_y": 0.0, **overrides}


def parent(*cells):
    world = {"cells": list(cells or [cell()]), "summary": {"unrelated": {"retained": True}},
             "ecosystem_dynamics_model": deepcopy(_EXPECTED_MODELS["heuristic_ecosystem_climate_support_v4"])}
    enrich_world_with_ecosystem_dynamics(world)
    assert validate_aquatic_climate_support(world) == []
    return world


def chain(world):
    assert enrich_world_with_resource_deposits(world) is world
    assert enrich_world_with_commodity_occurrences(world) is world
    assert validate_biological_resources(world) == []
    return world


@pytest.mark.parametrize("temperature,expected", [
    (-100.0, False), (-20.0, False), (-18.0, False), (-16.0, False),
    (math.nextafter(-16.0, math.inf), True), (0.0, True), (18.0, True),
    (math.nextafter(44.0, -math.inf), True), (44.0, False), (52.0, False), (100.0, False),
])
@pytest.mark.parametrize("water,is_water,is_lake", [
    ("ocean", True, False), ("continental_shelf", True, False),
    ("inland_sea", True, False), ("fresh_lake", False, True),
])
def test_composed_existing_parent_domain_includes_standing_fresh_lakes(temperature, expected, water, is_water, is_lake):
    world = chain(parent(cell(temperature_c=temperature, water_body_type=water, is_water=is_water, is_lake=is_lake)))
    current = world["cells"][0]
    assert current["resource"] == "coastal_fisheries"
    assert current["fishery_resource_proxy_applicable"] is True
    assert current["fishery_commodity_applicable"] is True
    assert current["fishery_resource_proxy_supported"] is expected
    assert current["fishery_commodity_supported"] is expected
    assert len(world["resource_deposits"]) == int(expected)
    assert len(world["commodity_occurrences"]) == int(expected)
    if temperature == -18:
        assert current["fishery_climate_supported"] is True
        assert current["primary_productivity_supported"] is False
        assert current["fishery_productivity_supported"] is False


@pytest.mark.parametrize("water,is_water,is_lake", [
    ("land", False, False), ("land", True, False), ("saline_basin", False, True),
    ("saline_basin", False, False), ("unknown", False, False),
])
def test_native_fishery_label_does_not_override_missing_fishery_habitat(water, is_water, is_lake):
    world = chain(parent(cell(water_body_type=water, is_water=is_water, is_lake=is_lake)))
    assert world["cells"][0]["fishery_resource_proxy_applicable"]
    assert not world["cells"][0]["fishery_resource_proxy_supported"]
    assert world["resource_deposits"] == world["commodity_occurrences"] == []


@pytest.mark.parametrize("water", ["ocean", "continental_shelf", "fresh_lake"])
def test_supported_zero_parents_are_known_inputs_and_have_no_record_threshold(water):
    world = parent(cell(water_body_type=water, is_water=water != "fresh_lake", is_lake=water == "fresh_lake"))
    world["cells"][0].update(primary_productivity_index=0.0, fishery_productivity_index=0.0)
    world["renewable_resource_records"] = []  # Known zero need not meet that different producer's .35 threshold.
    chain(world)
    current = world["cells"][0]
    assert current["primary_productivity_supported"] is current["fishery_productivity_supported"] is True
    assert current["fishery_resource_proxy_supported"] is current["fishery_commodity_supported"] is True
    deposit = world["resource_deposits"][0]
    occurrence = world["commodity_occurrences"][0]
    expected = .30 * deposit["reserve_potential_index"] + .18 * deposit["geologic_confidence_index"]
    expected += .24 if water != "fresh_lake" else 0.0
    expected += .16 if water == "continental_shelf" else 0.0
    assert occurrence["occurrence_potential_index"] == round(expected, 6)
    assert occurrence["occurrence_potential_index"] > 0


@pytest.mark.parametrize("key", ["primary_productivity_index", "fishery_productivity_index"])
@pytest.mark.parametrize("value", [None, "0.2", True, math.nan, math.inf, -0.01, 1.01])
def test_unusable_numeric_parent_is_not_consumed(key, value):
    world = parent()
    world["cells"][0][key] = value
    chain(world)
    assert not world["cells"][0]["fishery_resource_proxy_supported"]
    assert world["resource_deposits"] == world["commodity_occurrences"] == []


@pytest.mark.parametrize("key", ["primary_productivity_index", "fishery_productivity_index"])
def test_absent_parent_is_unavailable_instead_of_default_known_zero(key):
    world = parent()
    del world["cells"][0][key]
    chain(world)
    assert not world["cells"][0]["fishery_commodity_supported"]


@pytest.mark.parametrize("case", ACTUAL["cases"], ids=lambda case: case["name"])
def test_actual_archived_input_subsets_preserve_physical_inputs_and_materials(case):
    original = case["cell"]
    raw = json.dumps(original, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    assert hashlib.sha256(raw).hexdigest() == case["canonical_cell_sha256"]
    assert len(case["compressed_sha256"]) == len(case["uncompressed_sha256"]) == 64
    world = parent(deepcopy(original))
    before = deepcopy(world["cells"][0])
    chain(world)
    after = world["cells"][0]
    assert all(after[key] == value for key, value in before.items())
    if case["name"] in {"hot_marine", "cold_marine"}:
        assert not after["fishery_productivity_supported"]
        assert world["resource_deposits"] == world["commodity_occurrences"] == []
    elif case["name"] == "standing_fresh_lake":
        assert not after["is_water"] and after["is_lake"]
        assert after["fishery_commodity_supported"]
        assert world["commodity_occurrences"][0]["commodity"] == "fishery_biomass"
    else:
        assert after["resource"] in {"evaporites", "placer_metals"}
        assert not after["fishery_resource_proxy_applicable"]
        assert world["resource_deposits"] and world["commodity_occurrences"]


@pytest.mark.parametrize("version", [None, "heuristic_ecosystem_climate_support_v2", "heuristic_ecosystem_climate_support_v3"])
def test_historical_mapping_equations_scope_and_summary_are_exactly_preserved(version):
    world = deepcopy(LEGACY["input"])
    expected = deepcopy(LEGACY["output"])
    if version:
        world["ecosystem_dynamics_model"] = deepcopy(_EXPECTED_MODELS[version])
        expected["ecosystem_dynamics_model"] = deepcopy(_EXPECTED_MODELS[version])
    enrich_world_with_resource_deposits(world)
    enrich_world_with_commodity_occurrences(world)
    assert world == expected
    assert validate_biological_resources(world) == []


def test_all_cell_p95_and_material_equations_survive_biological_omission_and_dense_relink():
    world = deepcopy(LEGACY["input"])
    world["ecosystem_dynamics_model"] = deepcopy(_EXPECTED_MODELS["heuristic_ecosystem_climate_support_v4"])
    enrich_world_with_ecosystem_dynamics(world)
    chain(world)
    old = LEGACY["output"]
    assert world["resource_deposit_model"]["flow_accumulation_scale"] == old["resource_deposit_model"]["flow_accumulation_scale"] == 2e12
    assert world["summary"]["unsupported_fishery_resource_proxy_cell_count"] == 2
    deposits = world["resource_deposits"]
    occurrences = world["commodity_occurrences"]
    assert [r["id"] for r in deposits] == list(range(len(deposits)))
    assert [r["id"] for r in occurrences] == list(range(len(occurrences)))
    old_deposits = {r["cell_id"]: r for r in old["resource_deposits"]}
    old_occurrences = {(r["cell_id"], r["commodity"]): r for r in old["commodity_occurrences"]}
    for deposit in deposits:
        if deposit["resource"] != "coastal_fisheries":
            assert {k: v for k, v in deposit.items() if k != "id"} == {k: v for k, v in old_deposits[deposit["cell_id"]].items() if k != "id"}
    for occurrence in occurrences:
        assert deposits[occurrence["resource_deposit_id"]]["cell_id"] == occurrence["cell_id"]
        if occurrence["commodity"] != "fishery_biomass":
            omit = {"id", "resource_deposit_id"}
            old_record = old_occurrences[occurrence["cell_id"], occurrence["commodity"]]
            assert {k: v for k, v in occurrence.items() if k not in omit} == {k: v for k, v in old_record.items() if k not in omit}
    hot_soil = next(r for r in occurrences if r["commodity"] == "fertile_soils")
    assert hot_soil["occurrence_potential_index"] > 0  # Explicitly material; no present crop-yield claim.


def test_native_and_unrelated_object_identity_atomic_commit_and_idempotence():
    world = parent(cell(), cell(id=1, temperature_c=80))
    # Opaque retained objects test identity; this is not a fabricated certificate validation.
    physical = {"temperature_model": "opaque retained native object", "values": [1.0, 2.0]}
    world["climate_energy_model"] = physical
    source_cells = list(world["cells"])
    summary = world["summary"]
    unrelated_summary = summary["unrelated"]
    chain(world)
    once = deepcopy(world)
    chain(world)
    assert world == once
    assert world["climate_energy_model"] is physical
    assert world["summary"] is summary and summary["unrelated"] is unrelated_summary
    assert all(a is b for a, b in zip(source_cells, world["cells"]))


@pytest.mark.parametrize("target", ["resource", "commodity"])
@pytest.mark.parametrize("mutation", [
    lambda w: w.__setitem__("ecosystem_dynamics_model", None),
    lambda w: w["ecosystem_dynamics_model"].__setitem__("model", "unknown"),
    lambda w: w["ecosystem_dynamics_model"].__setitem__("aquatic_primary_minimum_temperature_c", -15.0),
    lambda w: w["ecosystem_dynamics_model"].__setitem__("extra", "unexpected"),
    lambda w: w["cells"][-1].__setitem__("primary_productivity_supported", False),
    lambda w: w.__setitem__("resource_deposit_model", {}),
    lambda w: w.__setitem__("commodity_occurrence_model", {"model_type": "unknown"}),
])
def test_bad_later_parent_or_model_rejected_before_any_mutation(target, mutation):
    world = parent(cell(id=0), cell(id=1))
    if target == "commodity":
        enrich_world_with_resource_deposits(world)
    mutation(world)
    before = deepcopy(world)
    refs = list(world["cells"])
    with pytest.raises(ValueError):
        (enrich_world_with_resource_deposits if target == "resource" else enrich_world_with_commodity_occurrences)(world)
    assert world == before
    assert all(a is b for a, b in zip(refs, world["cells"]))


@pytest.mark.parametrize("mutation", [
    lambda w: w["resource_deposits"].pop(),
    lambda w: w["resource_deposits"][0].__setitem__("cell_id", 100),
    lambda w: w["resource_deposits"][0].__setitem__("reserve_potential_index", .99),
    lambda w: w["resource_deposits"][0].__setitem__("geologic_confidence_index", None),
    lambda w: w["resource_deposits"][0].__setitem__("id", True),
    lambda w: w["resource_deposits"][0].pop("formation_evidence"),
    lambda w: w["resource_deposits"][0]["formation_evidence"].__setitem__("fertility", .99),
    lambda w: w["resource_deposits"][0].__setitem__("host_lithology", "fabricated"),
    lambda w: w["cells"][0].__setitem__("fishery_resource_proxy_supported", False),
    lambda w: w["summary"].__setitem__("fishery_resource_proxy_supported_cell_count", 0),
])
def test_missing_or_malformed_supported_deposit_is_not_replaced_by_zero_inputs(mutation):
    world = parent()
    enrich_world_with_resource_deposits(world)
    mutation(world)
    before = deepcopy(world)
    with pytest.raises(ValueError):
        enrich_world_with_commodity_occurrences(world)
    assert world == before


@pytest.mark.parametrize("mutation", [
    lambda w: w["commodity_occurrences"].pop(),
    lambda w: w["commodity_occurrences"][0].__setitem__("resource_deposit_id", 200),
    lambda w: w["commodity_occurrences"][0].__setitem__("occurrence_potential_index", .99),
    lambda w: w["commodity_occurrences"][0].__setitem__("geologic_confidence_index", .99),
    lambda w: w["commodity_occurrences"][0].__setitem__("source_resource", "evaporites"),
    lambda w: w["commodity_occurrences"][0].__setitem__("area_km2", .99),
    lambda w: w["commodity_occurrences"][0].pop("formation_evidence"),
    lambda w: w["commodity_occurrences"][0].__setitem__("commodity_group", []),
    lambda w: w["cells"][0].__setitem__("fishery_commodity_supported", False),
    lambda w: w["summary"].__setitem__("fishery_commodity_supported_cell_count", True),
    lambda w: w["summary"].__setitem__("commodity_occurrence_count", True),
    lambda w: w["summary"].__setitem__("commodity_occurrence_total_area_km2", 0),
    lambda w: w["summary"].__setitem__("mean_commodity_occurrence_potential_index", .99),
    lambda w: w["summary"].__setitem__("resource_deposit_total_area_km2", 0),
    lambda w: w["commodity_occurrence_model"].__setitem__("fertile_soils_scope", "crop yield"),
])
def test_independent_validator_replays_biological_values_and_links_without_mutation(mutation):
    world = chain(parent())
    mutation(world)
    before = deepcopy(world)
    errors = validate_biological_resources(world)
    assert len(errors) == 1
    assert world == before


def test_unknown_or_partial_new_empty_envelopes_cannot_take_legacy_early_return():
    for model in (None, {}, {"model": "unknown"}, {"model": "heuristic_ecosystem_climate_support_v4"}):
        world = {"cells": [], "ecosystem_dynamics_model": model}
        before = deepcopy(world)
        for stage in (enrich_world_with_resource_deposits, enrich_world_with_commodity_occurrences):
            with pytest.raises(ValueError):
                stage(world)
            assert world == before
    for stage in (enrich_world_with_resource_deposits, enrich_world_with_commodity_occurrences):
        world = {"cells": []}
        assert stage(world) == {"cells": []}


def test_no_declared_parent_cannot_keep_new_flags_as_historical_output():
    world = chain(parent())
    del world["ecosystem_dynamics_model"]
    before = deepcopy(world)
    assert validate_biological_resources(world)
    with pytest.raises(ValueError):
        enrich_world_with_resource_deposits(world)
    assert world == before


@pytest.mark.parametrize("model_key", ["resource_deposit_model", "commodity_occurrence_model"])
def test_undeclared_new_mirrors_cannot_be_silently_upgraded(model_key):
    world = chain(parent())
    del world[model_key]
    before = deepcopy(world)
    for stage in (enrich_world_with_resource_deposits, enrich_world_with_commodity_occurrences):
        with pytest.raises(ValueError):
            stage(world)
        assert world == before


@pytest.mark.parametrize("field,value", [("lat_deg", math.inf), ("area_km2", math.inf), ("flow_accumulation", math.inf)])
def test_nonfinite_source_arithmetic_rejected_without_partial_publication(field, value):
    world = parent(cell(id=0), cell(id=1))
    world["cells"][-1][field] = value
    before = deepcopy(world)
    with pytest.raises(ValueError):
        enrich_world_with_resource_deposits(world)
    assert world == before


def test_complete_empty_v4_parent_has_zero_new_counts_and_empty_records():
    world = parent()
    world["cells"] = []
    world["vegetation_succession_histories"] = []
    world["renewable_resource_records"] = []
    for key in list(world["summary"]):
        if key.endswith("_supported_cell_count"):
            world["summary"][key] = 0
    chain(world)
    assert world["resource_deposits"] == world["commodity_occurrences"] == []
    assert world["summary"]["fishery_resource_proxy_applicable_cell_count"] == 0


@pytest.mark.parametrize("world", [None, False, 0, 1.5, "world", [], [{}]])
def test_non_object_root_returns_a_bounded_validation_diagnostic(world):
    before = deepcopy(world)
    assert validate_biological_resources(world) == ["biological resources: world must be an object"]
    assert world == before


@pytest.mark.parametrize("stage", [enrich_world_with_resource_deposits, enrich_world_with_commodity_occurrences])
@pytest.mark.parametrize("world", [None, False, 0, 1.5, "world", [], [{}]])
def test_non_object_root_rejects_before_producer_mutation(stage, world):
    before = deepcopy(world)
    with pytest.raises(ValueError, match="world must be an object"):
        stage(world)
    assert world == before


@pytest.mark.parametrize("stage", [enrich_world_with_resource_deposits, enrich_world_with_commodity_occurrences])
@pytest.mark.parametrize("world", [{}, {"cells": []}])
def test_root_guard_preserves_historical_empty_mapping_noop(stage, world):
    before = deepcopy(world)
    assert stage(world) is world
    assert world == before
    assert validate_biological_resources(world) == []


@pytest.mark.parametrize("raw_viability,expected_count", [(.6499998, 0), (.65, 1), (.6500002, 1)])
def test_biological_raw_threshold_count_is_replayed_before_display_rounding(raw_viability, expected_count):
    # At runoff600 on a shelf with no hazards, the unchanged independent
    # expansion is viability=.63576+.126*settlement_score.
    score = (raw_viability - .63576) / .126
    world = chain(parent(cell(runoff_mm_y=600.0, settlement_score=score)))
    assert world["resource_deposits"][0]["economic_viability_index"] == .65
    assert world["summary"]["high_viability_resource_deposit_count"] == expected_count
    world["summary"]["high_viability_resource_deposit_count"] = 1 - expected_count
    assert validate_biological_resources(world)


@pytest.mark.parametrize("raw_viability,biological_count", [(.6499998, 0), (.65, 1), (.6500002, 1)])
def test_mixed_material_uncertainty_does_not_erase_replayed_biological_counts(raw_viability, biological_count):
    # Plain alluvial material has potential=.081216+.56256*fertility before
    # the deposit's six-place rounding, and viability=.31176+.2628*f+.126*s.
    # Choose actual source inputs whose material records lie at both displayed
    # thresholds. The helper deliberately does not replay these mineral/soil
    # formulas, so only this record's contribution remains uncertain.
    fertility = (.62 - .081216) / .56256
    material_score = (.65 - .31176 - .2628 * fertility) / .126
    world = chain(parent(
        cell(runoff_mm_y=600.0, settlement_score=(raw_viability - .63576) / .126),
        cell(id=1, is_water=False, water_body_type="land", resource="fertile_alluvium",
             fertility=fertility, settlement_score=material_score, landform="plain"),
    ))
    material = next(r for r in world["resource_deposits"] if r["resource"] == "fertile_alluvium")
    occurrence = next(r for r in world["commodity_occurrences"] if r["commodity"] == "fertile_soils")
    assert material["economic_viability_index"] == .65
    assert occurrence["occurrence_potential_index"] == .62
    original = deepcopy(world["summary"])
    for key, known in (("high_viability_resource_deposit_count", biological_count),
                       ("high_potential_commodity_occurrence_count", 1)):
        for count in (known, known + 1):
            world["summary"][key] = count
            assert validate_biological_resources(world) == []
        for count in (known - 1, known + 2):
            world["summary"][key] = count
            assert validate_biological_resources(world)
        world["summary"].update(original)


@pytest.mark.parametrize("water,expected_count", [("continental_shelf", 1), ("ocean", 0), ("fresh_lake", 0)])
def test_biological_commodity_threshold_count_is_independently_replayed(water, expected_count):
    world = parent(cell(water_body_type=water, is_water=water != "fresh_lake", is_lake=water == "fresh_lake"))
    world["cells"][0]["fishery_productivity_index"] = 0.0
    chain(world)
    assert world["summary"]["high_potential_commodity_occurrence_count"] == expected_count
    world["summary"]["high_potential_commodity_occurrence_count"] = 1 - expected_count
    assert validate_biological_resources(world)
