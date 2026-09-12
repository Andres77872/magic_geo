"""Shipped scenarios must reach V4 without losing their physical differences."""

from pathlib import Path

import pytest
import yaml

from magic_geo.config import load_config
from magic_geo.geo_validation_suite import load_geo_validation_manifest
from magic_geo.geo_validation_suite._helpers import _deep_merge
from magic_geo.native import MESH_BACKEND_IDS, NativeConfigV4, _native_seasonal_config
from magic_geo.seasonal_config import SeasonalWorldConfig


SCENARIOS = [Path("configs/earthlike_seed.yaml"), *sorted(Path("configs/seeds").glob("*.yaml"))]


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda path: path.stem)
def test_shipped_scenario_reaches_seasonal_abi_with_declared_physical_inputs(path):
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    config = load_config(path)
    native = _native_seasonal_config(config)
    assert raw["config_version"] == config.config_version == 2
    assert isinstance(native, NativeConfigV4)
    assert native.reference_infrared_optical_depth == 1.0
    assert "base_temperature_c" not in raw["climate"]
    assert "lapse_rate_c_per_km" not in raw["climate"]
    # In particular do not normalize away the distinct hot/cold, high-pressure,
    # gravity, inventory or orbit inputs when replacing the Celsius controls.
    for key, value in raw["planet"].items():
        assert getattr(native, key) == value
    assert native.mesh_backend == MESH_BACKEND_IDS[raw["mesh"]["backend"]]
    assert native.cell_count == raw["mesh"]["cell_count"]
    assert native.plate_count == raw["tectonics"]["plate_count"]
    assert native.precipitation_scale == raw["climate"]["precipitation_scale"]
    assert native.erosion_iterations == raw["erosion"]["iterations"]


def test_every_matrix_override_remains_valid_on_seasonal_reference():
    base = load_config(Path("configs/earthlike_seed.yaml")).model_dump()
    matrix = load_geo_validation_manifest(Path("configs/geo_validation_matrix.yaml"))
    assert matrix["schema_version"] == 1  # Manifest format, not world config version.
    converted = {}
    for scenario in matrix["scenarios"]:
        config = SeasonalWorldConfig.model_validate(_deep_merge(base, scenario["overrides"]))
        converted[scenario["id"]] = _native_seasonal_config(config)
    cold, hot = converted["snowball"], converted["hothouse"]
    assert cold.reference_infrared_optical_depth == hot.reference_infrared_optical_depth == 1.0
    assert cold.stellar_luminosity == 0.55
    assert cold.greenhouse_factor == 0.50
    assert hot.stellar_luminosity == 1.60
    assert hot.greenhouse_factor == 1.70

