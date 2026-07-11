from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


MAX_SEED = (1 << 64) - 1
MAX_PLANET_RADIUS_KM = 100_000.0
MAX_DAY_LENGTH_HOURS = 10_000.0
MAX_STELLAR_LUMINOSITY = 100.0
MAX_ATMOSPHERE_PRESSURE_BAR = 1_000.0
MAX_GREENHOUSE_FACTOR = 100.0
MAX_INTERNAL_HEAT = 100.0
MAX_GEOLOGICAL_AGE_GA = 100.0
MAX_ANGULAR_SPEED = 100.0
MAX_COMPUTE_THREADS = 1_024


class RunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    seed: int = Field(424242, ge=0, le=MAX_SEED)
    name: str = "earthlike_mvp"


class PlanetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    radius_km: float = Field(6371.0, gt=100.0, le=MAX_PLANET_RADIUS_KM)
    gravity_g: float = Field(1.0, gt=0.05, lt=5.0)
    day_length_hours: float = Field(24.0, gt=1.0, le=MAX_DAY_LENGTH_HOURS)
    axial_tilt_deg: float = Field(23.5, ge=0.0, le=90.0)
    orbital_eccentricity: float = Field(0.016, ge=0.0, lt=1.0)
    stellar_luminosity: float = Field(
        1.0,
        gt=0.01,
        le=MAX_STELLAR_LUMINOSITY,
    )
    atmosphere_pressure_bar: float = Field(
        1.0,
        ge=0.0,
        le=MAX_ATMOSPHERE_PRESSURE_BAR,
    )
    greenhouse_factor: float = Field(
        1.0,
        ge=0.0,
        le=MAX_GREENHOUSE_FACTOR,
    )
    ocean_fraction_target: float = Field(0.70, ge=0.0, le=0.95)
    ocean_water_inventory_km3: float = Field(1_338_000_000.0, ge=0.0, le=10_000_000_000.0)
    internal_heat: float = Field(1.0, ge=0.0, le=MAX_INTERNAL_HEAT)
    geological_age_ga: float = Field(
        4.5,
        ge=0.01,
        le=MAX_GEOLOGICAL_AGE_GA,
    )


class MeshConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    backend: Literal["fibonacci_sphere", "geodesic_icosahedron"] = "fibonacci_sphere"
    cell_count: int = Field(4096, ge=128, le=200_000)
    neighbor_count: int = Field(7, ge=4, le=16)


class TectonicsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    plate_count: int = Field(14, ge=2, le=256)
    continental_plate_fraction: float = Field(0.38, ge=0.0, le=1.0)
    continental_crust_fraction_target: float = Field(0.34, ge=0.0, le=0.95)
    min_angular_speed: float = Field(0.03, ge=0.0, le=MAX_ANGULAR_SPEED)
    max_angular_speed: float = Field(0.95, ge=0.0, le=MAX_ANGULAR_SPEED)
    boundary_smoothing_steps: int = Field(5, ge=0, le=32)
    plate_motion_scale_deg_per_step: float = Field(2.0, ge=0.0, le=10.0)
    oceanic_crust_aging_ma_per_step: float = Field(5.0, ge=0.0, le=50.0)

    @model_validator(mode="after")
    def validate_speeds(self) -> "TectonicsConfig":
        if self.max_angular_speed < self.min_angular_speed:
            raise ValueError("max_angular_speed must be >= min_angular_speed")
        return self


class ClimateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    months: Literal[12] = 12
    lapse_rate_c_per_km: float = Field(6.5, ge=0.0, le=15.0)
    base_temperature_c: float = Field(15.0, ge=-100.0, le=100.0)
    precipitation_scale: float = Field(1.0, ge=0.0, le=10.0)
    subtropical_drying_strength: float = Field(0.65, ge=0.0, le=0.9)


class HydrologyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    river_percentile: float = Field(0.92, ge=0.50, le=0.995)
    preserve_geologic_depressions: bool = True


class ErosionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    iterations: int = Field(6, ge=0, le=250)
    stream_power_coefficient: float = Field(7.5, ge=0.0, le=1000.0)
    drainage_exponent: float = Field(0.5, ge=0.0, le=2.0)
    slope_exponent: float = Field(1.0, ge=0.0, le=3.0)
    hillslope_diffusion: float = Field(0.055, ge=0.0, le=1.0)
    tectonic_uplift_scale: float = Field(0.85, ge=0.0, le=10.0)


class ComputeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    backend: Literal["auto", "cpu", "opencl", "cuda"] = "auto"
    threads: int = Field(0, ge=0, le=MAX_COMPUTE_THREADS)
    # OpenCL fallback device ranking; automatic mode prefers native CUDA when
    # that backend was compiled and the actual mesh meets its threshold.
    opencl_prefer_gpu: bool = True


class OutputConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    include_cells: bool = True
    float_precision: int = Field(4, ge=0, le=8)


class WorldConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    run: RunConfig = Field(default_factory=RunConfig)
    planet: PlanetConfig = Field(default_factory=PlanetConfig)
    mesh: MeshConfig = Field(default_factory=MeshConfig)
    tectonics: TectonicsConfig = Field(default_factory=TectonicsConfig)
    climate: ClimateConfig = Field(default_factory=ClimateConfig)
    hydrology: HydrologyConfig = Field(default_factory=HydrologyConfig)
    erosion: ErosionConfig = Field(default_factory=ErosionConfig)
    compute: ComputeConfig = Field(default_factory=ComputeConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)

    @model_validator(mode="after")
    def validate_plate_density(self) -> "WorldConfig":
        if self.tectonics.plate_count >= self.mesh.cell_count:
            raise ValueError("plate_count must be smaller than mesh.cell_count")
        return self


def seed_config_text() -> str:
    return resources.files("magic_geo").joinpath("seed_config.yaml").read_text(encoding="utf-8")


def write_seed_config(path: Path, *, force: bool = False) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists; pass --force to overwrite")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(seed_config_text(), encoding="utf-8")


def load_config(path: Path) -> WorldConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("config root must be a YAML mapping")
    return WorldConfig.model_validate(data)


def config_to_native(config: WorldConfig) -> dict:
    return config.model_dump(mode="json")
