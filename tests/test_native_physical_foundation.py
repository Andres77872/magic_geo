"""The full physical diagnostic pipeline must preserve solved native climate."""

from copy import deepcopy
from functools import wraps
import math

import pytest

import magic_geo.api as api
from magic_geo.native import generate_seasonal_geo_world
from magic_geo.native_climate_energy import CELL_FIELDS, LEGACY_CELL_ALIASES
from magic_geo.native_climate_energy_validation import audit_native_climate_energy
from magic_geo.seasonal_config import SeasonalWorldConfig


NATIVE_KEYS = (
    "climate_model", "climate_energy_model", "climate_energy_balance_records",
    "climate_energy_forcing_intervals", "climate_energy_transport_edges",
)


@pytest.fixture(scope="module")
def native_state():
    # Exercise the actual V4 ABI and full geometry/hydrology envelope. The
    # smaller permanent certificate fixture intentionally projects those out.
    config = SeasonalWorldConfig(
        config_version=2, mesh={"cell_count": 128}, tectonics={"plate_count": 8},
        erosion={"iterations": 0}, output={"float_precision": 8},
        compute={"backend": "cpu", "threads": 2},
    )
    return config, generate_seasonal_geo_world(config)


def test_every_physical_stage_preserves_native_budget_and_temperature_authority(native_state, monkeypatch):
    config, raw = native_state
    world = deepcopy(raw)
    retained = {key: world[key] for key in NATIVE_KEYS}
    native_values = deepcopy(retained)
    monthly_objects = [c["temperature_monthly_c"] for c in world["cells"]]
    temperatures = [(c["temperature_c"], deepcopy(c["temperature_monthly_c"])) for c in world["cells"]]
    called = []

    def track(original, name):
        @wraps(original)
        def wrapped(payload, *args, **kwargs):
            result = original(payload, *args, **kwargs)
            called.append(name)
            for key in NATIVE_KEYS:
                assert payload[key] is retained[key], (name, key, "replaced native authority")
                assert payload[key] == native_values[key], (name, key, "changed native authority")
            for c, values, monthly_object in zip(payload["cells"], temperatures, monthly_objects):
                assert (c["temperature_c"], c["temperature_monthly_c"]) == values, name
                assert c["temperature_monthly_c"] is monthly_object, name
            return result
        return wrapped

    for name, original in list(vars(api).items()):
        if name.startswith("enrich_world_with_") and callable(original):
            monkeypatch.setattr(api, name, track(original, name))
    api._enrich_physical_foundation(world, config)
    assert {
        "enrich_world_with_ocean_circulation", "enrich_world_with_climate_continentality",
        "enrich_world_with_seasonal_climate_history", "enrich_world_with_climate_energy_balance",
        "enrich_world_with_climate_realism", "enrich_world_with_permafrost_diagnostics",
        "enrich_world_with_groundwater_flow", "enrich_world_with_karst_diagnostics",
    }.issubset(called)
    assert audit_native_climate_energy(world)["verified"] is True
    assert all(not LEGACY_CELL_ALIASES.intersection(c) for c in world["cells"])
    assert all(CELL_FIELDS.issubset(c) for c in world["cells"])
    assert world["climate_seasonal_histories"]
    assert world["climate_continentality_regions"]
    assert world["climate_realism_checks"]


def test_climate_and_frozen_ground_diagnostics_read_the_published_native_monthly_climate(native_state):
    config, raw = native_state
    world = deepcopy(raw)
    api._enrich_physical_foundation(world, config)
    cells_by_id = {c["id"]: c for c in world["cells"]}
    # These existing diagnostic means are explicitly cell-count means; they
    # do not replace the separately area/time-weighted native energy summary.
    for history in world["climate_seasonal_histories"]:
        members = [c for c in world["cells"] if c["atmospheric_cell"] == history["atmospheric_cell"]]
        for index, step in enumerate(history["steps"]):
            expected = math.fsum(c["temperature_monthly_c"][index] for c in members) / len(members)
            assert step["mean_temperature_c"] == pytest.approx(expected, abs=5.1e-7)
    for region in world["climate_continentality_regions"]:
        members = [cells_by_id[cell_id] for cell_id in region["cell_ids"]]
        expected = math.fsum(max(c["temperature_monthly_c"]) - min(c["temperature_monthly_c"]) for c in members) / len(members)
        assert region["mean_temperature_range_c"] == pytest.approx(expected, abs=5.1e-7)
    assert world["permafrost_regions"], "reference must exercise linked frozen-ground evidence"
    for region in world["permafrost_regions"]:
        members = [cells_by_id[cell_id] for cell_id in region["cell_ids"]]
        expected = sum(sum(value < 0 for value in c["temperature_monthly_c"]) for c in members) / len(members)
        assert region["mean_frost_months"] == pytest.approx(expected, abs=5.1e-7)
    assert audit_native_climate_energy(world)["verified"] is True
