"""Explicit version-2 configuration for the prescribed seasonal temperature model.

This model is selected by explicit config_version 2 in YAML and by the seasonal
native entry points. Current YAML documents require the explicit version discriminator. There is no temperature-anchor to optical-depth conversion.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from ._config_models import (
    ComputeConfig, ErosionConfig, HydrologyConfig, MeshConfig, OutputConfig,
    PlanetConfig, RunConfig, TectonicsConfig, LegacyWorldConfig,
)


_STRICT = ConfigDict(
    extra="forbid", allow_inf_nan=False, strict=True, revalidate_instances="always"
)


class SeasonalRunConfig(RunConfig):
    """Deterministic run identity and human-readable metadata."""
    model_config = _STRICT


class SeasonalPlanetConfig(PlanetConfig):
    """Planet geometry, orbit, prescribed atmosphere, water inventory and age."""
    model_config = _STRICT

    atmosphere_pressure_bar: float = deepcopy(PlanetConfig.model_fields["atmosphere_pressure_bar"])
    atmosphere_pressure_bar.description = (
        "Area-weighted mean surface pressure in bar; hydrostatic columns preserve atmospheric mass."
    )
    greenhouse_factor: float = deepcopy(PlanetConfig.model_fields["greenhouse_factor"])
    greenhouse_factor.description = (
        "Dimensionless multiplier on reference infrared optical depth, with local pressure and gravity scaling."
    )


class SeasonalMeshConfig(MeshConfig):
    """Spherical control volumes and process-neighbour topology."""
    model_config = _STRICT


class SeasonalTectonicsConfig(TectonicsConfig):
    """Plate layout, crust allocation, motion and boundary smoothing."""
    model_config = _STRICT


class SeasonalHydrologyConfig(HydrologyConfig):
    """Surface-water routing and river classification policy."""
    model_config = _STRICT


class SeasonalErosionConfig(ErosionConfig):
    """Landscape maturation, incision, diffusion and uplift controls."""
    model_config = _STRICT


class SeasonalComputeConfig(ComputeConfig):
    """Execution backend and CPU/OpenCL scheduling preferences."""
    model_config = _STRICT


class SeasonalOutputConfig(OutputConfig):
    """Payload detail and display precision; native evidence retains full precision."""
    model_config = _STRICT


class SeasonalClimateConfig(BaseModel):
    """Prescribed gray opacity and empirical precipitation controls."""

    model_config = _STRICT

    months: Literal[12] = Field(12, description="Twelve equal elapsed-time months per simulated year.")
    reference_infrared_optical_depth: float = Field(
        1.0, ge=0.0,
        description="Prescribed gray infrared optical depth at one bar and Earth gravity before greenhouse scaling.",
    )
    precipitation_scale: float = Field(
        1.0, ge=0.0, le=10.0,
        description="Empirical precipitation multiplier; zero creates a dry boundary.",
    )
    subtropical_drying_strength: float = Field(
        0.65, ge=0.0, le=0.9,
        description="Empirical subtropical descending-air drying strength.",
    )

    @field_validator("months", mode="before")
    @classmethod
    def require_integer_months(cls, value: Any) -> Any:
        if type(value) is not int:
            raise ValueError("months must be the integer 12")
        return value

    @model_validator(mode="before")
    @classmethod
    def reject_obsolete_temperature_controls(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        errors = []
        for name in ("base_temperature_c", "lapse_rate_c_per_km"):
            if name in value:
                errors.append({
                    "type": "value_error", "loc": (name,), "input": value[name],
                    "ctx": {"error": ValueError(
                        f"{name} is obsolete in config_version 2; remove it and choose "
                        "reference_infrared_optical_depth explicitly. There is no equivalent conversion; "
                        "temperature is solved from the seasonal energy budget."
                    )},
                })
        if errors:
            raise ValidationError.from_exception_data(cls.__name__, errors)
        return value


class SeasonalWorldConfig(LegacyWorldConfig):
    """Strict configuration selecting the seasonal-only native V4 ABI."""

    model_config = _STRICT

    config_version: Literal[2] = Field(
        description="Required configuration discriminator; independent of world schema and C ABI versions."
    )
    run: SeasonalRunConfig = Field(default_factory=SeasonalRunConfig, description="Run identity and deterministic seed settings.")
    planet: SeasonalPlanetConfig = Field(default_factory=SeasonalPlanetConfig, description="Planet size, gravity, orbit, prescribed atmosphere, water, heat and age.")
    mesh: SeasonalMeshConfig = Field(default_factory=SeasonalMeshConfig, description="Spherical mesh backend, resolution and process-neighbour settings.")
    tectonics: SeasonalTectonicsConfig = Field(default_factory=SeasonalTectonicsConfig, description="Plate count, crust allocation, motion and boundary smoothing.")
    climate: SeasonalClimateConfig = Field(default_factory=SeasonalClimateConfig, description="Prescribed infrared opacity and empirical rainfall controls; temperature is a solved output.")
    hydrology: SeasonalHydrologyConfig = Field(default_factory=SeasonalHydrologyConfig, description="River classification and closed-basin routing policy.")
    erosion: SeasonalErosionConfig = Field(default_factory=SeasonalErosionConfig, description="Maturation timestep, incision, diffusion and uplift settings.")
    compute: SeasonalComputeConfig = Field(default_factory=SeasonalComputeConfig, description="Native execution backend and worker scheduling preferences.")
    output: SeasonalOutputConfig = Field(default_factory=SeasonalOutputConfig, description="Payload detail and general floating-point display formatting.")

    @field_validator("config_version", mode="before")
    @classmethod
    def require_integer_version(cls, value: Any) -> Any:
        if type(value) is not int:
            raise ValueError("config_version must be the integer 2")
        return value
