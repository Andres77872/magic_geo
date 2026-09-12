from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from magic_geo.config import (
    ConfigError, WorldConfig, LegacyWorldConfig, apply_config_overrides, dump_config_yaml, load_config,
    parse_config_yaml, write_config,
)
from magic_geo.seasonal_config import SeasonalWorldConfig


def test_explicit_version_and_separate_temperature_schema():
    config = SeasonalWorldConfig(config_version=2)
    assert config.climate.model_dump() == {
        "months": 12, "reference_infrared_optical_depth": 1.0,
        "precipitation_scale": 1.0, "subtropical_drying_strength": 0.65,
    }
    assert "config_version" in SeasonalWorldConfig.model_json_schema()["required"]
    assert "base_temperature_c" not in type(config.climate).model_fields
    assert "lapse_rate_c_per_km" not in type(config.climate).model_fields
    # Reading the seasonal schema must not mutate shared legacy FieldInfo.
    assert "trapping" in LegacyWorldConfig().planet.__class__.model_fields["greenhouse_factor"].description
    assert "optical depth" in WorldConfig().planet.__class__.model_fields["greenhouse_factor"].description


@pytest.mark.parametrize("version", [None, True, False, "2", 2.0, 1, 3])
def test_version_is_required_exact_integer_two(version):
    data = {} if version is None else {"config_version": version}
    with pytest.raises(ValidationError) as caught:
        SeasonalWorldConfig.model_validate(data)
    assert caught.value.errors()[0]["loc"] == ("config_version",)


def test_obsolete_controls_have_actionable_individual_paths():
    with pytest.raises(ValidationError) as caught:
        SeasonalWorldConfig(config_version=2, climate={
            "base_temperature_c": 15, "lapse_rate_c_per_km": 6.5,
        })
    errors = caught.value.errors()
    assert {e["loc"] for e in errors} == {
        ("climate", "base_temperature_c"), ("climate", "lapse_rate_c_per_km"),
    }
    assert all("no equivalent conversion" in e["msg"] for e in errors)
    assert all("reference_infrared_optical_depth" in e["msg"] for e in errors)


@pytest.mark.parametrize(("section", "key", "value"), [
    ("run", "seed", -1), ("run", "seed", 2**64),
    ("run", "seed", True), ("run", "seed", "424242"),
    ("run", "seed", 42.0), ("run", "name", b"bytes"),
    ("run", "name", "nul\0name"), ("run", "name", "bad\ud800"),
    ("planet", "gravity_g", True), ("planet", "radius_km", "6371"),
    ("planet", "greenhouse_factor", math.inf),
    ("planet", "atmosphere_pressure_bar", -1.0),
    ("mesh", "cell_count", 128.0), ("mesh", "cell_count", 2**32 + 128),
    ("mesh", "backend", "unknown"), ("mesh", "neighbor_count", False),
    ("tectonics", "plate_count", "8"),
    ("hydrology", "preserve_geologic_depressions", 1),
    ("hydrology", "preserve_geologic_depressions", "false"),
    ("erosion", "iterations", True), ("erosion", "maturation_timestep_ma", 0),
    ("compute", "threads", "1"), ("compute", "opencl_prefer_gpu", 0),
    ("compute", "backend", "maybe"), ("output", "include_cells", 1),
    ("output", "float_precision", True),
    ("climate", "months", 12.0), ("climate", "months", "12"),
    ("climate", "reference_infrared_optical_depth", True),
    ("climate", "reference_infrared_optical_depth", "1"),
    ("climate", "reference_infrared_optical_depth", -0.1),
    ("climate", "reference_infrared_optical_depth", math.nan),
    ("climate", "reference_infrared_optical_depth", math.inf),
    ("climate", "unknown", 1),
])
def test_sections_reject_coercion_and_invalid_ranges(section, key, value):
    with pytest.raises(ValidationError) as caught:
        SeasonalWorldConfig(config_version=2, **{section: {key: value}})
    assert caught.value.errors()[0]["loc"] == (section, key)


def test_cross_field_validators_and_finite_nonnegative_opacity_domain():
    with pytest.raises(ValidationError, match="plate_count must be smaller"):
        SeasonalWorldConfig(config_version=2, mesh={"cell_count": 128}, tectonics={"plate_count": 128})
    with pytest.raises(ValidationError, match="max_angular_speed"):
        SeasonalWorldConfig(config_version=2, tectonics={"min_angular_speed": 1.0, "max_angular_speed": 0.1})
    for tau in (0, 1, 1e300):
        config = SeasonalWorldConfig(config_version=2, climate={"reference_infrared_optical_depth": tau})
        assert config.climate.reference_infrared_optical_depth == tau


def test_mutated_and_constructed_models_are_revalidated():
    config = SeasonalWorldConfig(config_version=2)
    config.run.seed = -1
    with pytest.raises(ValidationError, match="run.seed"):
        SeasonalWorldConfig.model_validate(config, strict=True)
    invalid = SeasonalWorldConfig.model_construct(config_version=2, output={"include_cells": "false"})
    with pytest.raises(ValidationError):
        SeasonalWorldConfig.model_validate(invalid, strict=True)


def test_yaml_roundtrip_saved_file_and_overrides_preserve_version(tmp_path):
    config = parse_config_yaml("config_version: 2\nclimate:\n  reference_infrared_optical_depth: 0.73\n")
    assert isinstance(config, SeasonalWorldConfig)
    assert parse_config_yaml(dump_config_yaml(config)) == config
    changed = apply_config_overrides(config, {"climate.reference_infrared_optical_depth": 1.4})
    assert isinstance(changed, SeasonalWorldConfig)
    assert changed.config_version == 2
    assert changed.climate.reference_infrared_optical_depth == 1.4
    assert config.climate.reference_infrared_optical_depth == 0.73
    path = tmp_path / "seasonal.yaml"
    write_config(path, changed)
    assert load_config(path) == changed
    assert "config_version: 2" in path.read_text()


@pytest.mark.parametrize("document", ["", "{}", "climate:\n  base_temperature_c: 20\n", "mesh:\n  cell_count: 128\n"])
def test_unversioned_yaml_requires_explicit_migration(document):
    with pytest.raises(ConfigError, match="config_version is required") as caught:
        parse_config_yaml(document)
    assert caught.value.issues[0]["path"] == "config_version"
    assert WorldConfig().config_version == 2
    assert LegacyWorldConfig(climate={"base_temperature_c": 20}).climate.base_temperature_c == 20


@pytest.mark.parametrize("name", ["base_temperature_c", "lapse_rate_c_per_km"])
def test_yaml_and_override_obsolete_errors_keep_source_and_field_path(name):
    config = SeasonalWorldConfig(config_version=2)
    with pytest.raises(ConfigError) as yaml_error:
        parse_config_yaml(f"config_version: 2\nclimate:\n  {name}: 15\n", source="old.yaml")
    assert yaml_error.value.source == "old.yaml"
    assert yaml_error.value.issues[0]["path"] == f"climate.{name}"
    with pytest.raises(ConfigError) as override_error:
        apply_config_overrides(config, {f"climate.{name}": 15}, source="cli-override")
    assert override_error.value.source == "cli-override"
    assert override_error.value.issues[0]["path"] == f"climate.{name}"
    assert "no equivalent conversion" in str(override_error.value)


def test_unvalidated_version_marker_on_legacy_model_is_never_dropped(tmp_path):
    from magic_geo.api import generate_world, generate_geo_world
    from magic_geo.config import config_to_native
    from unittest.mock import patch

    invalid = LegacyWorldConfig().model_copy(update={"config_version": 2})
    actions = (
        lambda: dump_config_yaml(invalid), lambda: config_to_native(invalid),
        lambda: apply_config_overrides(invalid, {"run.name": "changed"}),
        lambda: write_config(tmp_path / "invalid.yaml", invalid),
        lambda: generate_world(invalid), lambda: generate_geo_world(invalid),
    )
    with patch("magic_geo.native._load_library", side_effect=AssertionError("legacy generation selected")):
        for action in actions:
            with pytest.raises(ConfigError, match="unvalidated version marker"):
                action()
    assert not (tmp_path / "invalid.yaml").exists()
