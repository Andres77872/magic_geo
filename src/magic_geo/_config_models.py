"""Shared scientific bounds and explicit legacy configuration models.

Current seasonal models reuse these bounds; old temperature controls are kept
only in the explicitly named LegacyWorldConfig for ABI compatibility coverage.
"""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
MAX_YAML_NESTING_DEPTH = 64
MAX_YAML_EVENTS = 20_000
MAX_YAML_ALIASES = 64


class RunConfig(BaseModel):
    """Deterministic run identity and human-readable world metadata."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    seed: int = Field(
        424242,
        ge=0,
        le=MAX_SEED,
        description="Unsigned 64-bit master seed used by every deterministic random process.",
    )
    name: str = Field(
        "earthlike_mvp",
        min_length=1,
        max_length=256,
        description="Human-readable world name recorded in generated payload metadata.",
    )

    @field_validator("name")
    @classmethod
    def validate_name_for_native_boundary(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("name must not contain NUL characters")
        try:
            encoded = value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("name must be well-formed Unicode encodable as UTF-8") from exc
        if len(encoded) > 1024:
            raise ValueError("name must be at most 1024 UTF-8 bytes")
        return value


class PlanetConfig(BaseModel):
    """Bulk planetary properties that set geometry, forcing, water, and age."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    radius_km: float = Field(
        6371.0,
        gt=100.0,
        le=MAX_PLANET_RADIUS_KM,
        description="Mean planetary radius in kilometres; scales all surface areas and distances.",
    )
    gravity_g: float = Field(
        1.0,
        gt=0.05,
        lt=5.0,
        description="Surface gravity relative to Earth gravity; affects ice, fluids, and isostasy.",
    )
    day_length_hours: float = Field(
        24.0,
        gt=1.0,
        le=MAX_DAY_LENGTH_HOURS,
        description="Rotation period in hours; controls Coriolis forcing and circulation structure.",
    )
    axial_tilt_deg: float = Field(
        23.5,
        ge=0.0,
        le=90.0,
        description="Axial obliquity in degrees; controls the strength of seasonal insolation.",
    )
    orbital_eccentricity: float = Field(
        0.016,
        ge=0.0,
        lt=1.0,
        description="Orbital eccentricity; modulates seasonal star-distance asymmetry.",
    )
    stellar_luminosity: float = Field(
        1.0,
        gt=0.01,
        le=MAX_STELLAR_LUMINOSITY,
        description="Incident stellar luminosity relative to the Sun; sets global climate forcing.",
    )
    atmosphere_pressure_bar: float = Field(
        1.0,
        ge=0.0,
        le=MAX_ATMOSPHERE_PRESSURE_BAR,
        description="Mean surface atmospheric pressure in bar; affects the climate energy balance.",
    )
    greenhouse_factor: float = Field(
        1.0,
        ge=0.0,
        le=MAX_GREENHOUSE_FACTOR,
        description="Dimensionless greenhouse trapping multiplier used by the climate model.",
    )
    ocean_fraction_target: float = Field(
        0.70,
        ge=0.0,
        le=0.95,
        description="Diagnostic target fraction of surface area covered by ocean.",
    )
    ocean_water_inventory_km3: float = Field(
        1_338_000_000.0,
        ge=0.0,
        le=10_000_000_000.0,
        description="Connected-ocean water inventory in cubic kilometres used by sea-level solving.",
    )
    internal_heat: float = Field(
        1.0,
        ge=0.0,
        le=MAX_INTERNAL_HEAT,
        description="Internal heat flow relative to Earth; scales tectonic and geothermal activity.",
    )
    geological_age_ga: float = Field(
        4.5,
        ge=0.01,
        le=MAX_GEOLOGICAL_AGE_GA,
        description="Planet age in billions of years; bounds crust age and geologic maturity.",
    )


class MeshConfig(BaseModel):
    """Spherical discretisation and process-neighbour topology."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    backend: Literal["fibonacci_sphere", "geodesic_icosahedron"] = Field(
        "fibonacci_sphere",
        description="Spherical mesh construction algorithm used for world control volumes.",
    )
    cell_count: int = Field(
        4096,
        ge=128,
        le=200_000,
        description="Requested number of spherical cells; controls spatial resolution and cost.",
    )
    neighbor_count: int = Field(
        7,
        ge=4,
        le=16,
        description="Target process-stencil neighbour count for the Fibonacci mesh backend.",
    )


class TectonicsConfig(BaseModel):
    """Tectonic plate layout, motion, crust allocation, and smoothing controls."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    plate_count: int = Field(
        14,
        ge=2,
        le=256,
        description="Number of tectonic plates; must remain smaller than mesh.cell_count.",
    )
    continental_plate_fraction: float = Field(
        0.38,
        ge=0.0,
        le=1.0,
        description="Fraction of plate seeds assigned a continental bias.",
    )
    continental_crust_fraction_target: float = Field(
        0.34,
        ge=0.0,
        le=0.95,
        description="Target fraction of surface control-volume area assigned continental crust.",
    )
    min_angular_speed: float = Field(
        0.03,
        ge=0.0,
        le=MAX_ANGULAR_SPEED,
        description="Minimum procedural plate angular-speed index; must not exceed the maximum.",
    )
    max_angular_speed: float = Field(
        0.95,
        ge=0.0,
        le=MAX_ANGULAR_SPEED,
        description="Maximum procedural plate angular-speed index used for boundary activity.",
    )
    boundary_smoothing_steps: int = Field(
        5,
        ge=0,
        le=32,
        description="Number of deterministic plate-boundary label smoothing iterations.",
    )
    plate_motion_scale_deg_per_step: float = Field(
        2.0,
        ge=0.0,
        le=10.0,
        description="Plate displacement scale in degrees per five-million-year reference step.",
    )
    oceanic_crust_aging_ma_per_step: float = Field(
        5.0,
        ge=0.0,
        le=50.0,
        description="Quiet oceanic-crust ageing in Ma per five-million-year reference step.",
    )

    @model_validator(mode="after")
    def validate_speeds(self) -> "TectonicsConfig":
        if self.max_angular_speed < self.min_angular_speed:
            raise ValueError("max_angular_speed must be >= min_angular_speed")
        return self


class LegacyClimateConfig(BaseModel):
    """Annual and seasonal temperature and precipitation controls."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    months: Literal[12] = Field(
        12,
        description="Fixed number of monthly climate samples in one generated year.",
    )
    lapse_rate_c_per_km: float = Field(
        6.5,
        ge=0.0,
        le=15.0,
        description="Atmospheric temperature lapse rate in degrees Celsius per kilometre.",
    )
    base_temperature_c: float = Field(
        15.0,
        ge=-100.0,
        le=100.0,
        description="Global mean sea-level temperature anchor in degrees Celsius.",
    )
    precipitation_scale: float = Field(
        1.0,
        ge=0.0,
        le=10.0,
        description="Dimensionless global precipitation multiplier; zero creates a dry boundary.",
    )
    subtropical_drying_strength: float = Field(
        0.65,
        ge=0.0,
        le=0.9,
        description="Dimensionless strength of subtropical descending-air dry belts.",
    )


class HydrologyConfig(BaseModel):
    """Surface-water routing and river classification policy."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    river_percentile: float = Field(
        0.92,
        ge=0.50,
        le=0.995,
        description="Flow-accumulation percentile threshold used to classify river cells.",
    )
    preserve_geologic_depressions: bool = Field(
        True,
        description="Keep geologic closed basins instead of filling every depression to an outlet.",
    )


class ErosionConfig(BaseModel):
    """Coupled landscape-maturation, incision, diffusion, and uplift controls."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    iterations: int = Field(
        6,
        ge=0,
        le=250,
        description="Number of coupled tectonic, climate, hydrology, and erosion transitions.",
    )
    maturation_timestep_ma: float = Field(
        5.0,
        gt=0.0,
        le=5.0,
        description="Nominal millions of years represented by each maturation transition.",
    )
    stream_power_coefficient: float = Field(
        7.5,
        ge=0.0,
        le=1000.0,
        description="Reference-step stream-power incision coefficient.",
    )
    drainage_exponent: float = Field(
        0.5,
        ge=0.0,
        le=2.0,
        description="Drainage-area exponent in the stream-power erosion relation.",
    )
    slope_exponent: float = Field(
        1.0,
        ge=0.0,
        le=3.0,
        description="Terrain-slope exponent in the stream-power erosion relation.",
    )
    hillslope_diffusion: float = Field(
        0.055,
        ge=0.0,
        le=1.0,
        description="Reference hillslope sediment-diffusion coefficient.",
    )
    tectonic_uplift_scale: float = Field(
        0.85,
        ge=0.0,
        le=10.0,
        description="Dimensionless multiplier on tectonic uplift supplied to landscape maturation.",
    )


class ComputeConfig(BaseModel):
    """Execution backend and CPU/OpenCL scheduling preferences."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    backend: Literal["auto", "cpu", "opencl", "cuda"] = Field(
        "auto",
        description="Requested compute backend; explicit accelerator choices fail if unavailable.",
    )
    threads: int = Field(
        0,
        ge=0,
        le=MAX_COMPUTE_THREADS,
        description="CPU worker-thread count; zero asks the runtime to select automatically.",
    )
    opencl_prefer_gpu: bool = Field(
        True,
        description="Prefer a qualifying GPU when selecting among available OpenCL devices.",
    )


class OutputConfig(BaseModel):
    """Generated payload detail and general numeric formatting controls."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    include_cells: bool = Field(
        True,
        description="Include per-cell state required by enrichers, validation, and the debugger.",
    )
    float_precision: int = Field(
        4,
        ge=0,
        le=8,
        description="General JSON decimal precision; replay-critical fields use higher fixed floors.",
    )


class LegacyWorldConfig(BaseModel):
    """Complete validated configuration for one deterministic magic-geo generation run."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    run: RunConfig = Field(
        default_factory=RunConfig,
        description="Run identity and deterministic seed settings.",
    )
    planet: PlanetConfig = Field(
        default_factory=PlanetConfig,
        description="Planet size, gravity, orbit, atmosphere, water, heat, and age.",
    )
    mesh: MeshConfig = Field(
        default_factory=MeshConfig,
        description="Spherical mesh backend, resolution, and process-neighbour settings.",
    )
    tectonics: TectonicsConfig = Field(
        default_factory=TectonicsConfig,
        description="Plate count, crust allocation, motion, and boundary smoothing.",
    )
    climate: LegacyClimateConfig = Field(
        default_factory=LegacyClimateConfig,
        description="Temperature, precipitation, seasonality, and subtropical drying controls.",
    )
    hydrology: HydrologyConfig = Field(
        default_factory=HydrologyConfig,
        description="River classification and closed-basin routing policy.",
    )
    erosion: ErosionConfig = Field(
        default_factory=ErosionConfig,
        description="Landscape maturation timestep, incision, diffusion, and uplift settings.",
    )
    compute: ComputeConfig = Field(
        default_factory=ComputeConfig,
        description="Native execution backend and worker scheduling preferences.",
    )
    output: OutputConfig = Field(
        default_factory=OutputConfig,
        description="Payload detail and general floating-point output formatting.",
    )

    @model_validator(mode="after")
    def validate_plate_density(self) -> "LegacyWorldConfig":
        if self.tectonics.plate_count >= self.mesh.cell_count:
            raise ValueError("plate_count must be smaller than mesh.cell_count")
        return self

