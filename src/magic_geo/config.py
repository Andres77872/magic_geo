from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from os import PathLike, link, replace
from pathlib import Path
from typing import Any, Iterable, Literal, TypeAlias
from uuid import uuid4

import yaml
from pydantic import (
    Field,
    ValidationError,
)
from yaml.constructor import ConstructorError
from yaml.events import AliasEvent, CollectionEndEvent, CollectionStartEvent
from yaml.nodes import MappingNode

from ._config_models import (
    LegacyWorldConfig, LegacyClimateConfig,
    MAX_SEED, MAX_PLANET_RADIUS_KM, MAX_DAY_LENGTH_HOURS, MAX_STELLAR_LUMINOSITY,
    MAX_ATMOSPHERE_PRESSURE_BAR, MAX_GREENHOUSE_FACTOR, MAX_INTERNAL_HEAT,
    MAX_GEOLOGICAL_AGE_GA, MAX_ANGULAR_SPEED, MAX_COMPUTE_THREADS,
    MAX_YAML_NESTING_DEPTH, MAX_YAML_EVENTS, MAX_YAML_ALIASES,
)
from .seasonal_config import (
    SeasonalWorldConfig,
    SeasonalRunConfig as RunConfig, SeasonalPlanetConfig as PlanetConfig,
    SeasonalMeshConfig as MeshConfig, SeasonalTectonicsConfig as TectonicsConfig,
    SeasonalClimateConfig as ClimateConfig, SeasonalHydrologyConfig as HydrologyConfig,
    SeasonalErosionConfig as ErosionConfig, SeasonalComputeConfig as ComputeConfig,
    SeasonalOutputConfig as OutputConfig,
)


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


class WorldConfig(SeasonalWorldConfig):
    """Current seasonal configuration for a deliberately new generation run.

    YAML documents must still carry their own explicit version discriminator.
    """

    config_version: Literal[2] = Field(
        2, description="Configuration document version; required in serialized YAML, independent of world schema and C ABI versions."
    )


_PROFILE_DESCRIPTIONS: dict[str, str] = {
    "default": "Prescribed seasonal energy model with neutral physical inputs.",
    "earthlike": "4,096-cell Earth reference inputs for the seasonal model; new climate calibration is not established.",
    "smoke": "Small deterministic CPU seasonal configuration for integration checks.",
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
    if "config_version" not in data:
        message = (
            "config_version is required. Start from a current profile or migrate the document "
            "to config_version: 2, remove climate.base_temperature_c and climate.lapse_rate_c_per_km, "
            "and choose climate.reference_infrared_optical_depth explicitly. "
            "There is no equivalent automatic temperature-to-opacity conversion."
        )
        raise ConfigError(
            message, source=source,
            issues=({"path": "config_version", "location": ["config_version"],
                     "message": message, "type": "missing"},),
        )
    try:
        return WorldConfig.model_validate(dict(data), strict=True)
    except ValidationError as exc:
        raise _config_validation_error(exc, source=source) from exc


def parse_config_yaml(text: str, *, source: str = "<string>") -> WorldConfig:
    """Parse and validate YAML text, rejecting duplicate keys.

    The exact integer config_version 2 is required in every document, including
    otherwise empty mappings. New profiles deliberately supply this version;
    an old or empty file cannot silently acquire new physical semantics. Errors
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


def _require_supported_config_model(config: WorldConfig) -> None:
    if hasattr(config, "config_version"):
        from .seasonal_config import SeasonalWorldConfig

        if not isinstance(config, SeasonalWorldConfig):
            raise ConfigError(
                "a config_version marker requires a validated SeasonalWorldConfig; "
                "parse explicit version-2 YAML or construct SeasonalWorldConfig(config_version=2). "
                "An unvalidated version marker on a legacy model cannot select new climate semantics.",
                source="<model>",
            )


def dump_config_yaml(config: WorldConfig) -> str:
    """Serialize a validated config as stable, human-editable YAML."""

    _require_supported_config_model(config)
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

    _require_supported_config_model(config)
    data = config.model_dump(mode="python")
    for dotted_path, value in overrides.items():
        if not isinstance(dotted_path, str):
            raise ConfigError("override paths must be strings", source=source)
        if data.get("config_version") == 2 and dotted_path in {
            "climate.base_temperature_c", "climate.lapse_rate_c_per_km",
        }:
            # Preserve the same field-specific migration message used by YAML,
            # even though obsolete fields are absent from the new schema.
            data["climate"][dotted_path.split(".")[1]] = value
            return _validate_config_data(data, source=source)
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

    if isinstance(config, LegacyWorldConfig) and not isinstance(config, SeasonalWorldConfig):
        # Only explicit legacy model instances may retain old ABI semantics.
        # Document parsing and current profiles never select this path.
        try:
            return LegacyWorldConfig.model_validate(data)
        except ValidationError as exc:
            raise _config_validation_error(exc, source=source) from exc
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


def _add_exact_integer_schema_display(node: dict[str, Any]) -> None:
    """Keep unsafe binary64 integers readable without changing JSON Schema.

    Browsers parse JSON numbers as binary64. These strings are presentation
    metadata only; the original numeric validation keywords remain intact.
    Traverse schema children, never values inside defaults/consts/examples.
    """
    exact = {
        key: str(node[key])
        for key in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "default", "const")
        if type(node.get(key)) is int and abs(node[key]) > 2**53 - 1
    }
    if exact:
        node["x-magic-geo-integer-display"] = exact
    for key in ("$defs", "definitions", "properties", "patternProperties", "dependentSchemas"):
        children = node.get(key)
        if isinstance(children, dict):
            for child in children.values():
                if isinstance(child, dict):
                    _add_exact_integer_schema_display(child)
    for key in ("items", "additionalProperties", "unevaluatedProperties", "propertyNames", "contains", "not", "if", "then", "else"):
        child = node.get(key)
        if isinstance(child, dict):
            _add_exact_integer_schema_display(child)
    for key in ("allOf", "anyOf", "oneOf", "prefixItems"):
        children = node.get(key)
        if isinstance(children, list):
            for child in children:
                if isinstance(child, dict):
                    _add_exact_integer_schema_display(child)


def config_schema() -> dict[str, Any]:
    """Return JSON Schema plus web-form metadata and built-in profile values."""

    schema = WorldConfig.model_json_schema()
    _add_exact_integer_schema_display(schema)
    schema["$id"] = "urn:magic-geo:schema:world-config:v2"
    # Constructors intentionally create new configurations with version 2;
    # serialized documents must explicitly identify their physical semantics.
    schema["required"] = list(dict.fromkeys([*schema.get("required", []), "config_version"]))
    schema["x-magic-geo"] = {
        "schema_version": 2,
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

    _require_supported_config_model(config)
    return config.model_dump(mode="json")
