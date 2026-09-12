"""Successor dependency boundary over existing hash-verified stage fixtures."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
import math

import pytest

from test_settlement_climate_support import ARCHIVES, enrich, synthetic
from magic_geo.settlement_input_availability import require_settlement_v3_inputs


def test_retained_mixed_world_distinguishes_three_zero_states_without_mutation():
    world = enrich(deepcopy(ARCHIVES["earthlike_seed"]["seasonal_supported_selection"]))
    before = deepcopy(world)
    inputs = require_settlement_v3_inputs(world)
    states = set()
    for cell in world["cells"]:
        state = inputs[cell["id"]]
        if cell["settlement_score"] == 0:
            states.add((state.surface_applicable, state.available, state.value, state.structural_zero))
    assert (True, True, 0.0, False) in states
    assert (True, False, None, False) in states
    assert (False, True, 0.0, True) in states
    assert world == before
    assert require_settlement_v3_inputs(world) == inputs
    with pytest.raises(FrozenInstanceError):
        inputs[0].available = True


@pytest.mark.parametrize("name", ["supported", "hot", "inside", "endpoint"])
def test_existing_native_boundary_fixtures(name):
    world = enrich(synthetic(name))
    states = require_settlement_v3_inputs(world)
    for cell in world["cells"]:
        state = states[cell["id"]]
        assert state.available == (cell["is_water"] or cell["is_lake"] or cell["settlement_climate_supported"])
    assert states[1].structural_zero and states[1].value == 0


@pytest.mark.parametrize("name", list(ARCHIVES))
def test_actual_retained_selection_sources(name):
    world = enrich(deepcopy(ARCHIVES[name]["seasonal_supported_selection"]))
    assert len(require_settlement_v3_inputs(world)) == len(world["cells"])


@pytest.mark.parametrize("mutate", [
    lambda w: w.update(generation_scope="geo_only"),
    lambda w: w.pop("settlement_selection_model"),
    lambda w: w["settlement_selection_model"].update(model_type="future"),
    lambda w: w["settlement_selection_model"].update(extra=True),
    lambda w: w["settlement_selection_model"].update(target_minimum=4.0),
    lambda w: w["summary"].update(settlement_count=True),
    lambda w: w["summary"].update(output_float_precision=9),
    lambda w: w["summary"].update(output_float_precision=8.0),
    lambda w: w["cells"][0].pop("is_lake"),
    lambda w: w["cells"][0].update(is_water=0),
    lambda w: w["cells"][0].update(settlement_climate_supported=False),
    lambda w: w["cells"][0].update(settlement_score=math.nan),
    lambda w: w["cells"][0].update(settlement_score=.1),
    lambda w: w["cells"][1].update(settlement_score=1e-10),
    lambda w: w["cells"][0].update(boundary_convergent=math.nan),
    lambda w: w["cells"][0].pop("runoff_mm_y"),
    lambda w: w["cells"][0].update(neighbors=[True]),
    lambda w: w["cells"][0].update(neighbors=[1, 1]),
    lambda w: w["cells"][0]["temperature_monthly_c"].pop(),
    lambda w: w["cells"][0]["position_3d"].__setitem__(0, math.inf),
    lambda w: w["cells"][0].update(settlement_climate_temperature_c=17.000001),
    lambda w: w["climate_energy_balance_records"].pop(),
    lambda w: w["settlements"][0].update(cell_id=-1),
    lambda w: w["settlements"][0].update(score=math.nan),
])
def test_malformed_or_tampered_parent_refuses_without_mutation(mutate):
    world = enrich(synthetic())
    mutate(world)
    before = deepcopy(world)
    with pytest.raises(ValueError):
        require_settlement_v3_inputs(world)
    # NaN needs identity-aware recursive comparison; no writes are permitted.
    def same(left, right):
        if isinstance(left, dict):
            return left.keys() == right.keys() and all(same(left[k], right[k]) for k in left)
        if isinstance(left, list):
            return len(left) == len(right) and all(same(a, b) for a, b in zip(left, right))
        return left == right or isinstance(left, float) and isinstance(right, float) and math.isnan(left) and math.isnan(right)
    assert same(world, before)


def test_old_family_is_not_implicitly_promoted():
    world = enrich(synthetic("legacy"))
    with pytest.raises(ValueError):
        require_settlement_v3_inputs(world)
