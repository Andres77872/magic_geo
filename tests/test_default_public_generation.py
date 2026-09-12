"""Current constructors and shared public fixtures exercise the seasonal core.

The expensive default 128-cell world is shared per process. Explicit legacy
controls remain separate and never supply a default-generation assertion.
"""
from __future__ import annotations

from copy import deepcopy
import math
from unittest.mock import patch

import pytest

from magic_geo import api, native
from magic_geo.config import LegacyWorldConfig, WorldConfig, config_to_native, create_config
from magic_geo.native_climate_energy_validation import audit_native_climate_energy
from magic_geo.native_climate_energy_enrichment_validation import (
    validate_native_climate_energy_enrichment,
)
from magic_geo.seasonal_config import SeasonalWorldConfig
from support import worlds
from support.nativestub import patch_generation_payload


@pytest.mark.parametrize("profile", ["default", "earthlike", "smoke"])
def test_new_constructor_profiles_and_serialized_mapping_select_seasonal(profile):
    config = WorldConfig() if profile == "default" else create_config(profile)
    assert isinstance(config, SeasonalWorldConfig)
    assert config.config_version == 2
    assert config.climate.reference_infrared_optical_depth == 1.0
    data = config_to_native(config)
    assert type(data["config_version"]) is int and data["config_version"] == 2
    assert "base_temperature_c" not in data["climate"]
    assert "lapse_rate_c_per_km" not in data["climate"]


def test_all_generic_canonical_configs_use_the_current_model():
    for key in worlds.CANONICAL:
        config = worlds.canonical_config(key)
        assert isinstance(config, SeasonalWorldConfig), key
        assert config.config_version == 2
    legacy = worlds.build_legacy_config()
    assert type(legacy) is LegacyWorldConfig
    assert "config_version" not in config_to_native(legacy)
    assert "base_temperature_c" in config_to_native(legacy)["climate"]


@pytest.fixture(scope="module")
def default_world():
    return worlds.cached_world_readonly("default_128")


def _assert_current_physical_output(world):
    assert world["climate_model"]["model_type"] == "prescribed_seasonal_surface_energy_v1"
    assert world["climate_model"]["imposed_mean_temperature"] is False
    assert world["climate_model"]["post_solve_temperature_adjustments"] is False
    assert world["climate_energy_model"]["model"] == "native_prescribed_seasonal_energy_v1"
    assert world["native_climate_energy_enrichment_model"]["model"] == (
        "native_climate_energy_annual_aggregation_v1"
    )
    assert len(world["cells"]) == len(world["climate_energy_balance_records"]) == 128
    assert audit_native_climate_energy(world)["verified"]
    assert validate_native_climate_energy_enrichment(world) == []
    durations = world["climate_energy_model"]["monthly_duration_seconds"]
    for cell, record in zip(world["cells"], world["climate_energy_balance_records"], strict=True):
        assert len(cell["temperature_monthly_c"]) == 12
        assert all(math.isfinite(value) for value in cell["temperature_monthly_c"])
        assert not {
            "climate_energy_stress_index", "energy_balance_residual_c",
            "greenhouse_trapping_w_m2", "radiative_equilibrium_temperature_c",
        }.intersection(cell)
        # Independent annual aggregation of the native monthly heat ledger.
        expected = math.fsum(
            duration * flux for duration, flux in zip(
                durations, record["monthly_absorbed_shortwave_w_m2"], strict=True,
            )
        ) / math.fsum(durations)
        assert math.isclose(cell["annual_absorbed_shortwave_w_m2"], expected, rel_tol=2e-15)


def test_default_full_public_generation_retains_auditable_native_budget(default_world):
    _assert_current_physical_output(default_world)
    assert "settlements" in default_world
    assert "ecosystem_dynamics_model" in default_world
    assert "species_ranges_model" in default_world


def test_default_geo_public_generation_retains_auditable_native_budget():
    world = api.generate_geo_world(worlds.canonical_config("default_128"))
    _assert_current_physical_output(world)
    assert world["generation_scope"] == "geo_only"
    assert "settlements" not in world
    assert "ecosystem_dynamics_model" in world


def test_shared_default_cache_preserves_readonly_identity_and_private_mutation(default_world):
    assert worlds.cached_world_readonly("default_128") is default_world
    before = deepcopy(default_world["cells"][0])
    private = worlds.cached_world("default_128")
    private["cells"][0]["temperature_monthly_c"][0] += 99.0
    private["climate_energy_balance_records"].clear()
    assert default_world["cells"][0] == before
    assert len(default_world["climate_energy_balance_records"]) == 128


class _StaleV4Library:
    @staticmethod
    def magic_geo_generate_json_v4(*_args):
        return 1

    magic_geo_generate_geo_json_v4 = magic_geo_generate_json_v4
    magic_geo_generate_msgpack_v4 = magic_geo_generate_json_v4
    magic_geo_generate_geo_msgpack_v4 = magic_geo_generate_json_v4


@pytest.mark.parametrize("generator", [native.generate_world, native.generate_geo_world])
@pytest.mark.parametrize("serialization", ["json", "msgpack", "auto"])
def test_default_native_mapping_uses_only_v4_and_keeps_schema_gate(generator, serialization):
    with (
        patch_generation_payload(_StaleV4Library(), {"schema_version": 1}, model="seasonal"),
        patch.object(native, "_load_library", side_effect=AssertionError("legacy fallback")),
    ):
        with pytest.raises(RuntimeError, match="unsupported world schema_version 1"):
            generator(config_to_native(WorldConfig()), serialization=serialization)
