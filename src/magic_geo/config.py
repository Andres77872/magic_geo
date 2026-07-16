from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from os import PathLike, link, replace
from pathlib import Path
from typing import Any, Iterable, Literal, TypeAlias
from uuid import uuid4

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
from yaml.constructor import ConstructorError
from yaml.events import AliasEvent, CollectionEndEvent, CollectionStartEvent
from yaml.nodes import MappingNode


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

ConfigProfile: TypeAlias = Literal["default", "earthlike", "smoke"]


class ConfigError(ValueError):
    """A source-aware YAML or configuration validation error.

    ``issues`` is deliberately JSON-compatible so CLI and web clients can use
    the same error without parsing the human-readable exception string.
    """

    def __init__(
        self,
        message: str,
        *,
        source: str = "<config>",
        line: int | None = None,
        column: int | None = None,
        issues: tuple[dict[str, Any], ...] = (),
    ) -> None:
        self.message = message
        self.source = source
        self.line = line
        self.column = column
        self.issues = tuple(dict(issue) for issue in issues)

        location = source
        if line is not None:
            location += f":{line}"
            if column is not None:
                location += f":{column}"
        super().__init__(f"{location}: {message}")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible error payload for API responses."""

        payload: dict[str, Any] = {
            "message": self.message,
            "source": self.source,
            "issues": [dict(issue) for issue in self.issues],
        }
        if self.line is not None:
            payload["line"] = self.line
        if self.column is not None:
            payload["column"] = self.column
        return payload


class _UniqueKeySafeLoader(yaml.SafeLoader):
    """PyYAML safe loader that fails instead of accepting the last duplicate key."""


def _construct_unique_mapping(
    loader: _UniqueKeySafeLoader,
    node: MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


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


class ClimateConfig(BaseModel):
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


class WorldConfig(BaseModel):
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
    climate: ClimateConfig = Field(
        default_factory=ClimateConfig,
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
    def validate_plate_density(self) -> "WorldConfig":
        if self.tectonics.plate_count >= self.mesh.cell_count:
            raise ValueError("plate_count must be smaller than mesh.cell_count")
        return self


_PROFILE_DESCRIPTIONS: dict[str, str] = {
    "default": "Schema defaults suitable as a neutral editable starting point.",
    "earthlike": "Calibrated 4,096-cell Earth-like reference configuration.",
    "smoke": "Small deterministic CPU configuration for fast integration checks.",
}

_PROFILE_OVERRIDES: dict[str, dict[str, Any]] = {
    "default": {},
    "earthlike": {
        "tectonics.plate_motion_scale_deg_per_step": 4.0,
        "climate.precipitation_scale": 0.8,
    },
    "smoke": {
        "run.name": "smoke",
        "mesh.cell_count": 128,
        "tectonics.plate_count": 8,
        "tectonics.plate_motion_scale_deg_per_step": 4.0,
        "climate.precipitation_scale": 0.8,
        "erosion.iterations": 1,
        "compute.backend": "cpu",
        "compute.threads": 1,
    },
}


def _config_validation_error(exc: ValidationError, *, source: str) -> ConfigError:
    issues: list[dict[str, Any]] = []
    lines: list[str] = []
    for error in exc.errors(
        include_url=False,
        include_context=False,
        include_input=False,
    ):
        location = list(error.get("loc", ()))
        path = ".".join(str(part) for part in location) or "<root>"
        message = str(error.get("msg", "invalid value"))
        issue = {
            "path": path,
            "location": location,
            "message": message,
            "type": str(error.get("type", "value_error")),
        }
        issues.append(issue)
        lines.append(f"{path}: {message}")
    detail = "configuration validation failed"
    if lines:
        detail += ":\n  - " + "\n  - ".join(lines)
    return ConfigError(detail, source=source, issues=tuple(issues))


def _check_yaml_complexity(text: str, *, source: str) -> None:
    """Reject pathological YAML before recursive object construction."""

    try:
        text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ConfigError("YAML text must be well-formed UTF-8 Unicode", source=source) from exc
    depth = 0
    event_count = 0
    alias_count = 0
    try:
        for event in yaml.parse(text, Loader=_UniqueKeySafeLoader):
            event_count += 1
            if event_count > MAX_YAML_EVENTS:
                raise ConfigError(
                    f"YAML exceeds the {MAX_YAML_EVENTS} event complexity limit",
                    source=source,
                )
            if isinstance(event, CollectionStartEvent):
                depth += 1
                if depth > MAX_YAML_NESTING_DEPTH:
                    raise ConfigError(
                        f"YAML nesting exceeds the {MAX_YAML_NESTING_DEPTH}-level limit",
                        source=source,
                    )
            elif isinstance(event, CollectionEndEvent):
                depth = max(0, depth - 1)
            elif isinstance(event, AliasEvent):
                alias_count += 1
                if alias_count > MAX_YAML_ALIASES:
                    raise ConfigError(
                        f"YAML exceeds the {MAX_YAML_ALIASES} alias limit",
                        source=source,
                    )
    except ConfigError:
        raise
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark
        raise ConfigError(
            f"invalid YAML: {exc.problem or 'invalid syntax'}",
            source=source,
            line=mark.line + 1 if mark is not None else None,
            column=mark.column + 1 if mark is not None else None,
        ) from exc
    except (yaml.YAMLError, RecursionError, MemoryError, ValueError, OverflowError) as exc:
        raise ConfigError(f"invalid or excessively complex YAML: {exc}", source=source) from exc


def _validate_config_data(data: Mapping[str, Any], *, source: str) -> WorldConfig:
    try:
        return WorldConfig.model_validate(dict(data))
    except ValidationError as exc:
        raise _config_validation_error(exc, source=source) from exc


def parse_config_yaml(text: str, *, source: str = "<string>") -> WorldConfig:
    """Parse and validate YAML text, rejecting duplicate keys.

    Empty YAML is intentionally equivalent to the ``default`` profile. Errors
    include the supplied source label; YAML syntax errors also include one-based
    line and column numbers.
    """

    _check_yaml_complexity(text, source=source)
    try:
        data = yaml.load(text, Loader=_UniqueKeySafeLoader)
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark
        problem = exc.problem or "invalid YAML"
        raise ConfigError(
            f"invalid YAML: {problem}",
            source=source,
            line=mark.line + 1 if mark is not None else None,
            column=mark.column + 1 if mark is not None else None,
        ) from exc
    except (yaml.YAMLError, RecursionError, MemoryError, ValueError, OverflowError) as exc:
        raise ConfigError(f"invalid YAML: {exc}", source=source) from exc

    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError(
            "config root must be a YAML mapping",
            source=source,
            issues=(
                {
                    "path": "<root>",
                    "location": [],
                    "message": "config root must be a YAML mapping",
                    "type": "mapping_type",
                },
            ),
        )
    return _validate_config_data(data, source=source)


def dump_config_yaml(config: WorldConfig) -> str:
    """Serialize a validated config as stable, human-editable YAML."""

    return yaml.safe_dump(
        config.model_dump(mode="python"),
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=100,
    )


def parse_config_overrides(assignments: Iterable[str]) -> dict[str, Any]:
    """Parse repeatable ``section.field=YAML_VALUE`` assignments.

    Values use YAML scalar/list syntax, so ``false``, ``128``, and
    ``geodesic_icosahedron`` retain their intended types.  The resulting
    mapping is suitable for :func:`apply_config_overrides` or
    :func:`create_config`.
    """

    overrides: dict[str, Any] = {}
    for assignment in assignments:
        if not isinstance(assignment, str) or "=" not in assignment:
            raise ConfigError(
                f"override {assignment!r} must use section.field=value",
                source="<override>",
            )
        path, raw_value = assignment.split("=", 1)
        path = path.strip()
        if not path or path in overrides:
            message = (
                f"duplicate configuration override {path!r}"
                if path in overrides
                else "override path cannot be empty"
            )
            raise ConfigError(message, source="<override>")
        try:
            _check_yaml_complexity(raw_value, source=f"<override:{path}>")
            value = yaml.safe_load(raw_value)
        except ConfigError:
            raise
        except (yaml.YAMLError, RecursionError, MemoryError, ValueError, OverflowError) as exc:
            raise ConfigError(
                f"invalid YAML value for override {path!r}: {exc}",
                source="<override>",
            ) from exc
        overrides[path] = value
    return overrides


def list_config_profiles() -> tuple[str, ...]:
    """Return supported built-in profile names in stable presentation order."""

    return tuple(_PROFILE_OVERRIDES)


def apply_config_overrides(
    config: WorldConfig,
    overrides: Mapping[str, Any],
    *,
    source: str = "<overrides>",
) -> WorldConfig:
    """Return a validated copy with dotted leaf paths replaced.

    The input model and caller-owned override values are never mutated. Unknown
    paths and attempts to replace a whole section fail with ``ConfigError``.
    """

    data = config.model_dump(mode="python")
    for dotted_path, value in overrides.items():
        if not isinstance(dotted_path, str):
            raise ConfigError("override paths must be strings", source=source)
        parts = dotted_path.split(".")
        if len(parts) < 2 or any(not part for part in parts):
            raise ConfigError(
                f"override path {dotted_path!r} must identify a dotted field",
                source=source,
            )

        target: dict[str, Any] = data
        for part in parts[:-1]:
            child = target.get(part)
            if not isinstance(child, dict):
                raise ConfigError(
                    f"unknown configuration override {dotted_path!r}",
                    source=source,
                )
            target = child

        leaf = parts[-1]
        if leaf not in target or isinstance(target[leaf], dict):
            raise ConfigError(
                f"unknown configuration override {dotted_path!r}",
                source=source,
            )
        target[leaf] = deepcopy(value)

    return _validate_config_data(data, source=source)


def create_config(
    profile: ConfigProfile | str = "default",
    overrides: Mapping[str, Any] | None = None,
) -> WorldConfig:
    """Create a validated built-in profile with optional dotted-path overrides."""

    if profile not in _PROFILE_OVERRIDES:
        choices = ", ".join(list_config_profiles())
        raise ConfigError(
            f"unknown configuration profile {profile!r}; choose one of: {choices}",
            source="<profile>",
        )

    config = WorldConfig()
    profile_overrides = _PROFILE_OVERRIDES[profile]
    if profile_overrides:
        config = apply_config_overrides(
            config,
            profile_overrides,
            source=f"<profile:{profile}>",
        )
    if overrides:
        config = apply_config_overrides(config, overrides)
    return config


def config_schema() -> dict[str, Any]:
    """Return JSON Schema plus web-form metadata and built-in profile values."""

    schema = WorldConfig.model_json_schema()
    schema["$id"] = "urn:magic-geo:schema:world-config:v1"
    schema["x-magic-geo"] = {
        "schema_version": 1,
        "section_order": list(WorldConfig.model_fields),
        "profiles": [
            {
                "name": profile,
                "description": _PROFILE_DESCRIPTIONS[profile],
                "values": create_config(profile).model_dump(mode="json"),
            }
            for profile in list_config_profiles()
        ],
    }
    return schema


def write_config(path: str | PathLike[str], config: WorldConfig, *, force: bool = False) -> None:
    """Atomically write validated YAML, creating parent directories as needed."""

    target = Path(path)
    if target.exists() and not force:
        raise FileExistsError(f"{target} already exists; pass --force to overwrite")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(dump_config_yaml(config), encoding="utf-8")
        # Validate exactly what will be committed before replacing the target.
        parse_config_yaml(temporary.read_text(encoding="utf-8"), source=str(temporary))
        if force:
            replace(temporary, target)
        else:
            try:
                # Same-directory hard-link creation is atomic and fails if a
                # concurrent writer created the target after the early check.
                link(temporary, target)
            except FileExistsError as exc:
                raise FileExistsError(
                    f"{target} already exists; pass --force to overwrite"
                ) from exc
            temporary.unlink()
    finally:
        if temporary.exists():
            temporary.unlink()


def load_config(path: str | PathLike[str]) -> WorldConfig:
    """Load a YAML config path with source-aware parse and validation errors."""

    config_path = Path(path)
    # Preserve the original Path.read_text exception contract (for example
    # FileNotFoundError and PermissionError); ConfigError is reserved for YAML
    # and model validation failures after bytes have been read successfully.
    text = config_path.read_text(encoding="utf-8")
    return parse_config_yaml(text, source=str(config_path))


def config_to_native(config: WorldConfig) -> dict[str, Any]:
    """Return the validated JSON-compatible mapping consumed by native.py."""

    return config.model_dump(mode="json")
