"""Historical seasonal selection-v2 stays distinct from current selection-v3.

Positive historical cases are unchanged complete, hash-checked native archives.
Mutations are refusal probes only; no world generation or fixture retagging.
"""
from copy import deepcopy
import json
import math

import pytest

from magic_geo.cli.validators.settlement_climate import (
    LEGACY_MODEL, SEASONAL_MODEL, replay_settlement_climate,
)
from magic_geo.cli.validators.settlement import (
    _validate_settlement_selection, _validate_route_network,
)
from magic_geo.cli.validators.political import (
    _validate_political_regions, _validate_political_borders,
)
from support.legacy_human_water_worlds import legacy_human_water_world
from test_settlement_climate_support import enrich, synthetic


CHECKERS = (
    _validate_settlement_selection, _validate_route_network,
    _validate_political_regions, _validate_political_borders,
)


@pytest.mark.parametrize("key", ["small_smoke", "mid_512"])
def test_genuine_seasonal_v2_archive_preserves_all_four_historical_replays(key):
    world = legacy_human_water_world(key)
    before = deepcopy(world)
    assert world["climate_model"]["model_type"] == "prescribed_seasonal_surface_energy_v1"
    assert world["settlement_selection_model"]["model_type"] == LEGACY_MODEL
    assert world["summary"]["settlement_selection_model"] == LEGACY_MODEL
    assert all("settlement_climate_supported" not in cell and
               "settlement_climate_temperature_c" not in cell for cell in world["cells"])
    assert replay_settlement_climate(world) == (LEGACY_MODEL, None)
    cells = {cell["id"]: cell for cell in world["cells"]}
    for checker in CHECKERS:
        assert checker(world, world["summary"], cells) == [], checker.__name__
    assert world == before


@pytest.mark.parametrize("annotated", [False, True])
def test_current_v3_raw_and_annotated_inputs_keep_annual_source_replay(annotated):
    world = synthetic("supported")
    if annotated:
        enrich(world)
    else:
        assert "settlement_selection_model" not in world
        assert "settlement_selection_model" not in world["summary"]
    before = deepcopy(world)
    family, annual = replay_settlement_climate(world)
    assert family == SEASONAL_MODEL
    assert annual == {cell["id"]: cell["settlement_climate_temperature_c"] for cell in world["cells"]}
    assert world == before


@pytest.mark.parametrize("mutate", [
    pytest.param(lambda w: w.pop("settlement_selection_model"), id="missing-own"),
    pytest.param(lambda w: w["summary"].pop("settlement_selection_model"), id="missing-summary"),
    pytest.param(lambda w: w.update(settlement_selection_model=None), id="null-own"),
    pytest.param(lambda w: w["settlement_selection_model"].pop("model_type"), id="partial-own"),
    pytest.param(lambda w: w["settlement_selection_model"].update(model_type="future"), id="unknown-own"),
    pytest.param(lambda w: w["summary"].update(settlement_selection_model=SEASONAL_MODEL), id="mismatched-summary"),
    pytest.param(lambda w: w["settlement_selection_model"].update(model_type=SEASONAL_MODEL), id="retagged-own"),
    pytest.param(lambda w: w["settlement_selection_model"].update(annual_climate_applicability={}), id="new-applicability"),
    pytest.param(lambda w: w["cells"][0].update(settlement_climate_supported=False), id="new-support"),
    pytest.param(lambda w: w["cells"][0].update(settlement_climate_temperature_c=0), id="new-roundtrip"),
    pytest.param(lambda w: w.update(native_social_availability_model={}), id="social-model"),
    pytest.param(lambda w: w.update(native_social_availability={}), id="social-envelope"),
    pytest.param(lambda w: w["route_network_model"].update(source_settlement_model=SEASONAL_MODEL), id="route-source-v3"),
    pytest.param(lambda w: w["political_region_model"].update(source_settlement_model=SEASONAL_MODEL), id="political-source-v3"),
    pytest.param(lambda w: w.update(extra_model={"source_settlement_selection_model": SEASONAL_MODEL}), id="other-source-v3"),
])
def test_explicit_historical_branch_rejects_partial_or_mixed_versions(mutate):
    world = legacy_human_water_world("small_smoke")
    mutate(world)
    before = deepcopy(world)
    with pytest.raises(ValueError):
        replay_settlement_climate(world)
    assert world == before


@pytest.mark.parametrize("key", [
    "native_social_summary_availability", "recorded_historical_event_count",
    "recorded_ruin_count", "recorded_conflict_count", "recorded_dynasty_count",
    "available_population_region_count", "available_culture_continuity_count",
])
def test_historical_branch_rejects_each_native_social_summary_marker(key):
    world = legacy_human_water_world("small_smoke")
    world["summary"][key] = None
    with pytest.raises(ValueError, match="mixed settlement versions"):
        replay_settlement_climate(world)


@pytest.mark.parametrize("mutate", [
    pytest.param(lambda w: w.pop("climate_model"), id="missing-climate"),
    pytest.param(lambda w: w["climate_model"].update(model_type="equilibrium_latitude_circulation_climate_v5"), id="contradictory-climate"),
    pytest.param(lambda w: w["climate_model"].update(model_type="future"), id="unknown-climate"),
    pytest.param(lambda w: w.pop("climate_energy_model"), id="missing-energy"),
    pytest.param(lambda w: w["climate_energy_model"].update(model="future"), id="unknown-energy"),
    pytest.param(lambda w: w.pop("native_climate_energy_enrichment_model"), id="missing-enrichment"),
    pytest.param(lambda w: w["native_climate_energy_enrichment_model"].update(model="future"), id="wrong-enrichment"),
    pytest.param(lambda w: w.pop("climate_energy_transport_edges"), id="missing-edges"),
    pytest.param(lambda w: w.update(climate_energy_transport_edges={}), id="typed-edges"),
    pytest.param(lambda w: w.pop("climate_energy_forcing_intervals"), id="missing-forcing"),
    pytest.param(lambda w: w.update(climate_energy_forcing_intervals=[]), id="empty-forcing"),
    pytest.param(lambda w: w["climate_energy_forcing_intervals"].__setitem__(0, None), id="typed-forcing-record"),
    pytest.param(lambda w: w.pop("climate_energy_balance_records"), id="missing-balance"),
    pytest.param(lambda w: w["climate_energy_balance_records"].pop(), id="source-coverage"),
    pytest.param(lambda w: w["climate_energy_balance_records"].append(deepcopy(w["climate_energy_balance_records"][0])), id="duplicate-source"),
    pytest.param(lambda w: w["climate_energy_balance_records"][0].update(cell_id=True), id="bool-source-id"),
    pytest.param(lambda w: w["climate_energy_balance_records"][0]["monthly_mean_temperature_k"].pop(), id="monthly-length"),
    pytest.param(lambda w: w["climate_energy_balance_records"][0]["monthly_mean_temperature_k"].__setitem__(0, math.inf), id="nonfinite-monthly"),
    pytest.param(lambda w: w["climate_energy_balance_records"][0]["monthly_mean_temperature_k"].__setitem__(0, False), id="bool-monthly"),
    pytest.param(lambda w: w["climate_energy_model"]["monthly_duration_seconds"].pop(), id="duration-length"),
    pytest.param(lambda w: w["climate_energy_model"]["monthly_duration_seconds"].__setitem__(0, 0), id="nonpositive-duration"),
    pytest.param(lambda w: w["climate_energy_model"].update(year_duration_seconds=0), id="nonpositive-year"),
    pytest.param(lambda w: w["cells"].pop(), id="cell-coverage"),
    pytest.param(lambda w: w["cells"][0].update(id=True), id="bool-cell-id"),
    pytest.param(lambda w: w["cells"][1].update(id=w["cells"][0]["id"]), id="duplicate-cell-id"),
])
def test_native_source_audits_still_precede_historical_return(mutate):
    world = legacy_human_water_world("small_smoke")
    mutate(world)
    before = json.dumps(world, sort_keys=True)
    with pytest.raises(ValueError):
        replay_settlement_climate(world)
    assert json.dumps(world, sort_keys=True) == before


def test_current_v3_cannot_be_retagged_into_legacy_with_native_social_markers():
    world = enrich(synthetic("supported"))
    world["settlement_selection_model"]["model_type"] = LEGACY_MODEL
    world["summary"]["settlement_selection_model"] = LEGACY_MODEL
    world["settlement_selection_model"].pop("annual_climate_applicability")
    for cell in world["cells"]:
        cell.pop("settlement_climate_supported")
        cell.pop("settlement_climate_temperature_c")
    world["native_social_availability"] = {}
    with pytest.raises(ValueError, match="mixed settlement versions"):
        replay_settlement_climate(world)


def test_v3_own_identity_requires_native_climate():
    world = enrich(synthetic("legacy"))
    world["settlement_selection_model"]["model_type"] = SEASONAL_MODEL
    world["summary"]["settlement_selection_model"] = SEASONAL_MODEL
    with pytest.raises(ValueError, match="settlement-v3 requires native climate"):
        replay_settlement_climate(world)
