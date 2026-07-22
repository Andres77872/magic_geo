# Python API

[Wiki home](./README.md) > Python API

This page is the reference for embedding magic-geo as a library rather than driving it through the CLI. It covers the exported package surface, every configuration helper, the five generation entry points, the shape of the returned world dictionary, the JSON/`.mgeo` serialization layer, the `magic_geo.io` writers, direct enricher invocation and its ordering constraints, native backend introspection, the error types, and complete end-to-end recipes. Every signature, default, and field name below was read out of the source tree; observed runtime counts were produced from a real `smoke`-profile generation in this repository and are labelled as such.

## On this page

- [Package surface and import paths](#package-surface-and-import-paths)
- [Configuration helpers](#configuration-helpers)
- [Generation entry points](#generation-entry-points)
- [The returned world document](#the-returned-world-document)
- [Serialization: JSON and .mgeo](#serialization-json-and-mgeo)
- [The io writers](#the-io-writers)
- [Calling enrichers directly](#calling-enrichers-directly)
- [Native backend introspection](#native-backend-introspection)
- [Error types and what raises them](#error-types-and-what-raises-them)
- [End-to-end recipes](#end-to-end-recipes)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

---

## Package surface and import paths

`src/magic_geo/__init__.py` re-exports **only the configuration layer**. Generation, serialization, and writers are not exported from the package root and must be imported from their own modules. This is deliberate: `magic_geo.api` transitively imports 69 enrichers from 67 modules (`boundary_geometry` and `graph_diagnostics` each export two), and `magic_geo.native` loads a shared library, so keeping them out of `__init__` makes `import magic_geo` cheap and import-safe on a host with no built native library.

### Exported from `magic_geo` (`src/magic_geo/__init__.py:19`)

| Name | Kind | Signature | Defined at |
|---|---|---|---|
| `ConfigError` | exception class | `ConfigError(message: str, *, source: str = "<config>", line: int \| None = None, column: int \| None = None, issues: tuple[dict[str, Any], ...] = ())` | `src/magic_geo/config.py:41` |
| `WorldConfig` | pydantic model | `WorldConfig(run=…, planet=…, mesh=…, tectonics=…, climate=…, hydrology=…, erosion=…, compute=…, output=…)` | `src/magic_geo/config.py:458` |
| `apply_config_overrides` | function | `(config: WorldConfig, overrides: Mapping[str, Any], *, source: str = "<overrides>") -> WorldConfig` | `src/magic_geo/config.py:710` |
| `config_schema` | function | `() -> dict[str, Any]` | `src/magic_geo/config.py:780` |
| `create_config` | function | `(profile: ConfigProfile \| str = "default", overrides: Mapping[str, Any] \| None = None) -> WorldConfig` | `src/magic_geo/config.py:754` |
| `dump_config_yaml` | function | `(config: WorldConfig) -> str` | `src/magic_geo/config.py:653` |
| `list_config_profiles` | function | `() -> tuple[str, ...]` | `src/magic_geo/config.py:704` |
| `load_config` | function | `(path: str \| PathLike[str]) -> WorldConfig` | `src/magic_geo/config.py:829` |
| `parse_config_overrides` | function | `(assignments: Iterable[str]) -> dict[str, Any]` | `src/magic_geo/config.py:665` |
| `parse_config_yaml` | function | `(text: str, *, source: str = "<string>") -> WorldConfig` | `src/magic_geo/config.py:612` |
| `write_config` | function | `(path: str \| PathLike[str], config: WorldConfig, *, force: bool = False) -> None` | `src/magic_geo/config.py:800` |
| `__version__` | `str` | `"0.1.0"` | `src/magic_geo/__init__.py:17` |

### Public surfaces that live outside the package root

| Import | Contents | Module |
|---|---|---|
| `from magic_geo.api import generate_world, generate_geo_world, generate_from_file, generate_geo_from_file, backend_info` | generation entry points | `src/magic_geo/api.py` |
| `from magic_geo.api import NATIVE_CIVILIZATION_TOP_LEVEL_FIELDS, NATIVE_CIVILIZATION_CELL_FIELDS, NATIVE_CIVILIZATION_SUMMARY_FIELDS` | geo-only strip sets (`src/magic_geo/api.py:86`, `:106`, `:115`) | `src/magic_geo/api.py` |
| `from magic_geo.config import config_to_native` | validated JSON mapping handed to the native layer (`src/magic_geo/config.py:840`) — not in `__all__` | `src/magic_geo/config.py` |
| `from magic_geo.io import read_world, write_world, write_world_binary, write_json, write_cells_csv, write_summary_markdown, write_svg_map, write_raster_map` | all output writers (`src/magic_geo/io/__init__.py:16`) | `src/magic_geo/io/` |
| `from magic_geo.serialization import dumps_world, loads_world, validate_world_payload, retired_world_schema_fields, WorldSerializationError, …` | in-memory codec, validators, framing constants | `src/magic_geo/serialization.py` |
| `from magic_geo.native import backend_info, generate_world, generate_geo_world` | raw ctypes bridge, **no Python enrichment** | `src/magic_geo/native.py` |
| `from magic_geo.planet_parameters import planet_parameter_snapshot, planet_radius_km, planet_gravity_g, surface_gravity_m_s2` | planet snapshot helpers | `src/magic_geo/planet_parameters.py` |
| `from magic_geo.geo_validation import validate_geo_world` | `(world, *, profile: str = "generic") -> dict[str, Any]` (`src/magic_geo/geo_validation.py:2743`) | `src/magic_geo/geo_validation.py` |
| `from magic_geo.<domain> import enrich_world_with_*` | 69 individual enrichers | 67 modules (`boundary_geometry` and `graph_diagnostics` export two each) |

Runtime requirements are `msgpack>=1.1,<2`, `pydantic>=2.10`, `PyYAML>=6.0.2`, `typer>=0.16.0` on Python `>=3.11` (`pyproject.toml`). Only the CLI needs `typer`; the library paths above use the other three.

---

## Configuration helpers

`WorldConfig` is a pydantic v2 model with **9 sections and 44 leaf fields** (verified by introspecting `WorldConfig.model_fields`). Every model sets `model_config = ConfigDict(extra="forbid", allow_inf_nan=False)`, so unknown keys are rejected and `nan`/`inf`/`-inf` fail on every float field.

Section classes, in declaration order (`src/magic_geo/config.py:463`–`:498`):

| Section | Class | Class line | Leaf fields |
|---|---|---|---|
| `run` | `RunConfig` | `src/magic_geo/config.py:124` | 2 |
| `planet` | `PlanetConfig` | `src/magic_geo/config.py:156` | 12 |
| `mesh` | `MeshConfig` | `src/magic_geo/config.py:235` | 3 |
| `tectonics` | `TectonicsConfig` | `src/magic_geo/config.py:258` | 8 |
| `climate` | `ClimateConfig` | `src/magic_geo/config.py:319` | 5 |
| `hydrology` | `HydrologyConfig` | `src/magic_geo/config.py:354` | 2 |
| `erosion` | `ErosionConfig` | `src/magic_geo/config.py:371` | 7 |
| `compute` | `ComputeConfig` | `src/magic_geo/config.py:420` | 3 |
| `output` | `OutputConfig` | `src/magic_geo/config.py:441` | 2 |

Cross-field validators that can fail *after* per-field validation succeeds:

| Validator | Location | Raised message |
|---|---|---|
| `TectonicsConfig.validate_speeds` | `src/magic_geo/config.py:312` | `max_angular_speed must be >= min_angular_speed` |
| `WorldConfig.validate_plate_density` | `src/magic_geo/config.py:500` | `plate_count must be smaller than mesh.cell_count` |
| `RunConfig.validate_name_for_native_boundary` | `src/magic_geo/config.py:142` | `name must not contain NUL characters` / `name must be well-formed Unicode encodable as UTF-8` / `name must be at most 1024 UTF-8 bytes` |

The full per-field default/bound table lives on [Configuration Reference](./05-configuration-reference.md); this page documents the *functions*.

### `create_config`

```python
create_config(profile: ConfigProfile | str = "default",
              overrides: Mapping[str, Any] | None = None) -> WorldConfig
```
`src/magic_geo/config.py:754`. `ConfigProfile` is `Literal["default", "earthlike", "smoke"]` (`src/magic_geo/config.py:38`).

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `profile` | `ConfigProfile \| str` | `"default"` | Built-in profile name; must be a key of `_PROFILE_OVERRIDES` (`src/magic_geo/config.py:513`). |
| `overrides` | `Mapping[str, Any] \| None` | `None` | Dotted `section.field` leaf overrides applied on top of the profile, via `apply_config_overrides`. |

**Returns** a fully validated `WorldConfig`. **Raises** `ConfigError` with `source="<profile>"` and message `unknown configuration profile {profile!r}; choose one of: default, earthlike, smoke` for an unknown profile; `ConfigError` with `source="<profile:{name}>"` if a profile override is itself invalid; `ConfigError` with `source="<overrides>"` for a bad caller override.

Built-in profiles (`_PROFILE_DESCRIPTIONS` at `src/magic_geo/config.py:507`, `_PROFILE_OVERRIDES` at `:513`):

| Profile | Description | Deltas from schema defaults |
|---|---|---|
| `default` | "Schema defaults suitable as a neutral editable starting point." | none |
| `earthlike` | "Calibrated 4,096-cell Earth-like reference configuration." | `tectonics.plate_motion_scale_deg_per_step=4.0`, `climate.precipitation_scale=0.8` |
| `smoke` | "Small deterministic CPU configuration for fast integration checks." | `run.name="smoke"`, `mesh.cell_count=128`, `tectonics.plate_count=8`, `tectonics.plate_motion_scale_deg_per_step=4.0`, `climate.precipitation_scale=0.8`, `erosion.iterations=1`, `compute.backend="cpu"`, `compute.threads=1` |

```python
from magic_geo import create_config

config = create_config("earthlike", {"run.seed": 20240117, "mesh.cell_count": 2048})
print(config.run.seed)                                        # 20240117
print(config.mesh.cell_count)                                 # 2048
print(config.tectonics.plate_motion_scale_deg_per_step)       # 4.0  (from the profile)
print(config.climate.precipitation_scale)                     # 0.8  (from the profile)
```

### `list_config_profiles`

```python
list_config_profiles() -> tuple[str, ...]
```
`src/magic_geo/config.py:704`. No parameters. **Returns** `tuple(_PROFILE_OVERRIDES)` — the profile names in stable presentation order. **Raises** nothing.

```python
from magic_geo import list_config_profiles

assert list_config_profiles() == ("default", "earthlike", "smoke")
```

### `parse_config_yaml`

```python
parse_config_yaml(text: str, *, source: str = "<string>") -> WorldConfig
```
`src/magic_geo/config.py:612`.

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `text` | `str` | — | YAML document text. |
| `source` | `str` | `"<string>"` | Label attached to every raised `ConfigError` and used in the `source[:line[:column]]` message prefix. |

**Returns** a validated `WorldConfig`. Pipeline, in order:

1. UTF-8 well-formedness check (`src/magic_geo/config.py:561`).
2. `_check_yaml_complexity` (`src/magic_geo/config.py:557`) streams `yaml.parse` events *before* constructing objects, enforcing `MAX_YAML_EVENTS = 20_000`, `MAX_YAML_NESTING_DEPTH = 64`, and `MAX_YAML_ALIASES = 64` (`src/magic_geo/config.py:34`–`:36`).
3. Load with `_UniqueKeySafeLoader` (`src/magic_geo/config.py:85`), whose `_construct_unique_mapping` (`:89`) rejects duplicate keys and unhashable mapping keys instead of silently taking the last value.
4. `None` (empty document) becomes `{}`, which is intentionally equivalent to the `default` profile.
5. Non-mapping roots are rejected.
6. `WorldConfig.model_validate` through `_validate_config_data` (`src/magic_geo/config.py:605`).

**Raises** `ConfigError` only. Observable variants:

| Condition | Message | Extra state |
|---|---|---|
| non-UTF-8 text | `YAML text must be well-formed UTF-8 Unicode` | — |
| > 20 000 parse events | `YAML exceeds the 20000 event complexity limit` | — |
| collection nesting > 64 | `YAML nesting exceeds the 64-level limit` | — |
| > 64 aliases | `YAML exceeds the 64 alias limit` | — |
| YAML syntax error, duplicate key, unhashable key | `invalid YAML: {problem}` | 1-based `line`, `column` |
| other loader failure | `invalid or excessively complex YAML: {exc}` / `invalid YAML: {exc}` | — |
| root is not a mapping | `config root must be a YAML mapping` | `issues` has one `mapping_type` entry |
| model validation failure | `configuration validation failed:\n  - {path}: {msg}` per issue | `issues` tuple of `{path, location, message, type}` |

```python
from magic_geo import ConfigError, parse_config_yaml

config = parse_config_yaml(
    """
    run:
      seed: 7
      name: worked_example
    mesh:
      cell_count: 1024
    """,
    source="inline.yaml",
)
print(config.run.name, config.mesh.cell_count)   # worked_example 1024

try:
    parse_config_yaml("mesh:\n  cell_count: 64\n", source="bad.yaml")
except ConfigError as exc:
    print(exc.source)                      # bad.yaml
    print(exc.issues[0]["path"])           # mesh.cell_count
    print(exc.issues[0]["type"])           # greater_than_equal
```

### `dump_config_yaml`

```python
dump_config_yaml(config: WorldConfig) -> str
```
`src/magic_geo/config.py:653`. Single parameter, the validated model. **Returns** `yaml.safe_dump(config.model_dump(mode="python"), allow_unicode=True, default_flow_style=False, sort_keys=False, width=100)` — declaration order preserved, no anchors or aliases. **Raises** whatever `yaml.safe_dump` raises on a pathological value; validated models cannot produce one.

```python
from magic_geo import create_config, dump_config_yaml

text = dump_config_yaml(create_config("smoke"))
print(text.splitlines()[0])   # run:
```

### `parse_config_overrides`

```python
parse_config_overrides(assignments: Iterable[str]) -> dict[str, Any]
```
`src/magic_geo/config.py:665`. Parses repeatable `section.field=YAML_VALUE` strings — the same syntax the CLI `--set` flag uses. The split is on the **first** `=` only, so values may contain `=`. The path is stripped; the value is passed verbatim to `yaml.safe_load`, so YAML scalar typing applies (`false` → `bool`, `128` → `int`, `0.8` → `float`, `cpu` → `str`, `"128"` → `str`, empty/`null` → `None`). Insertion order is preserved.

**Returns** `dict[str, Any]`. **Raises** `ConfigError`:

| Condition | `source` | Message |
|---|---|---|
| item is not a `str`, or contains no `=` | `<override>` | `override {assignment!r} must use section.field=value` |
| empty path after strip | `<override>` | `override path cannot be empty` |
| path already seen | `<override>` | `duplicate configuration override {path!r}` |
| value fails the YAML complexity pre-pass | `<override:{path}>` | re-raised unchanged from `_check_yaml_complexity` |
| `yaml.safe_load` failure | `<override>` | `invalid YAML value for override {path!r}: {exc}` |

```python
from magic_geo import parse_config_overrides

overrides = parse_config_overrides([
    "mesh.cell_count=2048",
    "compute.backend=cpu",
    "hydrology.preserve_geologic_depressions=false",
])
print(overrides)
# {'mesh.cell_count': 2048, 'compute.backend': 'cpu',
#  'hydrology.preserve_geologic_depressions': False}
```

### `apply_config_overrides`

```python
apply_config_overrides(config: WorldConfig,
                       overrides: Mapping[str, Any],
                       *, source: str = "<overrides>") -> WorldConfig
```
`src/magic_geo/config.py:710`.

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `config` | `WorldConfig` | — | Source model. Never mutated — the function works on `config.model_dump(mode="python")`. |
| `overrides` | `Mapping[str, Any]` | — | Dotted leaf paths to values. Each value is `deepcopy`-ed, so caller-owned objects are never aliased into the result. |
| `source` | `str` | `"<overrides>"` | Error label. |

**Returns** a new validated `WorldConfig`. Overrides are applied in mapping iteration order, then the whole document is re-validated, so cross-field validators still run.

**Raises** `ConfigError`:

| Condition | Message |
|---|---|
| non-string key | `override paths must be strings` |
| fewer than two dotted parts, or an empty part (`"seed"`, `"a."`, `".b"`, `"a..b"`) | `override path {dotted_path!r} must identify a dotted field` |
| intermediate part missing or not a mapping | `unknown configuration override {dotted_path!r}` |
| leaf missing, or leaf resolves to a whole section | `unknown configuration override {dotted_path!r}` |
| resulting document fails validation | `configuration validation failed: …` with populated `issues` |

```python
from magic_geo import ConfigError, create_config, apply_config_overrides

base = create_config("default")
tuned = apply_config_overrides(base, {"erosion.iterations": 12, "output.float_precision": 8})
print(base.erosion.iterations, tuned.erosion.iterations)   # 6 12

try:
    apply_config_overrides(base, {"mesh": {"cell_count": 512}})   # whole-section replacement
except ConfigError as exc:
    print(exc.message)      # override path 'mesh' must identify a dotted field

try:
    apply_config_overrides(base, {"mesh.foo": 1})                 # unknown leaf
except ConfigError as exc:
    print(exc.message)      # unknown configuration override 'mesh.foo'
```

A single-part path such as `"mesh"` fails the dotted-path check *before* the lookup, so whole-section replacement reports `must identify a dotted field`, not `unknown configuration override`.

### `config_schema`

```python
config_schema() -> dict[str, Any]
```
`src/magic_geo/config.py:780`. No parameters. **Returns** `WorldConfig.model_json_schema()` augmented with:

| Key | Value |
|---|---|
| `$id` | `"urn:magic-geo:schema:world-config:v1"` |
| `x-magic-geo.schema_version` | `1` |
| `x-magic-geo.section_order` | `list(WorldConfig.model_fields)` — the 9 section names in declaration order |
| `x-magic-geo.profiles` | list of `{name, description, values}`, where `values` is `create_config(name).model_dump(mode="json")` |

**Raises** nothing under normal use. This is the payload the web workbench form is generated from.

```python
import json
from magic_geo import config_schema

schema = config_schema()
print(schema["$id"])                                    # urn:magic-geo:schema:world-config:v1
print(schema["x-magic-geo"]["section_order"])           # ['run', 'planet', 'mesh', ...]
print([p["name"] for p in schema["x-magic-geo"]["profiles"]])   # ['default', 'earthlike', 'smoke']
print(json.dumps(schema["x-magic-geo"]["profiles"][2]["values"]["mesh"]))
# {"backend": "fibonacci_sphere", "cell_count": 128, "neighbor_count": 7}
```

### `write_config`

```python
write_config(path: str | PathLike[str], config: WorldConfig, *, force: bool = False) -> None
```
`src/magic_geo/config.py:800`.

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `path` | `str \| PathLike[str]` | — | Target YAML path; parent directories are created. |
| `config` | `WorldConfig` | — | Validated model to serialize. |
| `force` | `bool` | `False` | Overwrite an existing target. |

Publication protocol: write to a hidden same-directory temp file `.{name}.{uuid4().hex}.tmp`, **re-parse exactly the bytes that will be committed** via `parse_config_yaml`, then publish with `os.replace` (`force=True`, atomic overwrite) or `os.link` (`force=False`, atomic create that fails if a concurrent writer beat you). A `finally` block removes any temp debris. Readers therefore never observe a partial or invalid file.

**Returns** `None`. **Raises** `FileExistsError(f"{target} already exists; pass --force to overwrite")` on both the early existence check and the `os.link` race; `ConfigError` if the round-tripped bytes fail to validate; `OSError` subclasses from the filesystem.

```python
from pathlib import Path
from magic_geo import create_config, write_config

target = Path("runs/generated.yaml")
write_config(target, create_config("smoke"))
try:
    write_config(target, create_config("earthlike"))
except FileExistsError as exc:
    print(exc)          # runs/generated.yaml already exists; pass --force to overwrite
write_config(target, create_config("earthlike"), force=True)
```

### `load_config`

```python
load_config(path: str | PathLike[str]) -> WorldConfig
```
`src/magic_geo/config.py:829`. Reads `Path(path).read_text(encoding="utf-8")` and hands it to `parse_config_yaml(text, source=str(config_path))`.

**Returns** a validated `WorldConfig`. **Raises** — and this distinction is deliberate and documented in the source comment at `src/magic_geo/config.py:833` — the *original* `Path.read_text` exception contract for I/O problems (`FileNotFoundError`, `PermissionError`, `IsADirectoryError`, `UnicodeDecodeError`) untouched, and `ConfigError` **only** for YAML syntax and model-validation failures after bytes were read successfully. The error `source` is the stringified path, so downstream tools can render `path:line:column` diagnostics.

```python
from magic_geo import ConfigError, load_config

try:
    config = load_config("configs/earthlike_seed.yaml")
except FileNotFoundError:
    print("no such config")     # I/O problem: not a ConfigError
except ConfigError as exc:
    print(exc.to_dict())        # {'message': ..., 'source': 'configs/earthlike_seed.yaml', 'issues': [...]}
```

### `ConfigError`

`src/magic_geo/config.py:41`. Subclasses `ValueError`, so `except ValueError` catches it.

| Attribute | Type | Meaning |
|---|---|---|
| `.message` | `str` | Message without the location prefix. |
| `.source` | `str` | Label: file path, `<string>`, `<override>`, `<override:path>`, `<overrides>`, `<profile>`, `<profile:name>`, `<config>`. |
| `.line` | `int \| None` | 1-based YAML line, when the failure came from the parser. |
| `.column` | `int \| None` | 1-based YAML column. |
| `.issues` | `tuple[dict[str, Any], ...]` | Per-issue records `{path, location, message, type}`; `path` is dotted or `"<root>"`. |
| `.to_dict()` | `dict[str, Any]` | JSON-compatible payload (`message`, `source`, `issues`, plus `line`/`column` when present). |

The stringified exception is `f"{location}: {message}"` where `location` is `source[:line[:column]]`.

### `config_to_native` (not exported from the root)

```python
config_to_native(config: WorldConfig) -> dict[str, Any]
```
`src/magic_geo/config.py:840`. A one-liner: `config.model_dump(mode="json")`. It produces the nested mapping with **identical section and field names** — no renames, no flattening at this layer. Renames happen one level down in `native._native_config` (`src/magic_geo/native.py:281`), which flattens the 9 sections into the `NativeConfigV3` ctypes struct; there, `erosion.iterations` becomes `erosion_iterations`, `mesh.backend` becomes the integer `mesh_backend` via `MESH_BACKEND_IDS` (`src/magic_geo/native.py:17`), and `compute.backend` becomes the integer `compute_backend` via `COMPUTE_BACKEND_IDS` (`:22`).

---

## Generation entry points

All five live in `src/magic_geo/api.py`. `magic_geo.native` is imported lazily *inside* each function body (`src/magic_geo/api.py:180`, `:196`, `:294`), so importing `magic_geo.api` does not touch the shared library.

| Function | Signature | Line | Native call | Enricher calls |
|---|---|---|---|---|
| `generate_world` | `(config: WorldConfig) -> dict[str, Any]` | `src/magic_geo/api.py:195` | `native.generate_world(config_to_native(config))` | 66 |
| `generate_geo_world` | `(config: WorldConfig) -> dict[str, Any]` | `src/magic_geo/api.py:287` | `native.generate_geo_world(config_to_native(config))` | 48 |
| `generate_from_file` | `(path: Path) -> dict[str, Any]` | `src/magic_geo/api.py:378` | via `generate_world(load_config(path))` | 66 |
| `generate_geo_from_file` | `(path: Path) -> dict[str, Any]` | `src/magic_geo/api.py:384` | via `generate_geo_world(load_config(path))` | 48 |
| `backend_info` | `() -> dict[str, Any]` | `src/magic_geo/api.py:179` | `native.backend_info()` | none |

### `generate_world`

```python
generate_world(config: WorldConfig) -> dict[str, Any]
```

| Parameter | Type | Meaning |
|---|---|---|
| `config` | `WorldConfig` | Fully validated configuration. Passed through `config_to_native` before crossing the FFI boundary. |

**Returns** the world `dict`. The same object is mutated in place by every enricher and returned; there is no copy.

Execution order:

1. `world = native_generate_world(config_to_native(config))` (`src/magic_geo/api.py:198`).
2. `_require_configured_planet_snapshot(world, config)` (`:185`, called at `:199`) — compares `world["planet_parameters"]` against `planet_parameter_snapshot(config.planet)`.
3. 66 enricher calls in the fixed order tabulated in [Calling enrichers directly](#calling-enrichers-directly).
4. `return world`.

**Raises**

| Exception | Cause |
|---|---|
| `RuntimeError("native planet_parameters do not match the configured planet snapshot")` | step 2 mismatch (`src/magic_geo/api.py:190`) |
| `RuntimeError` from `magic_geo.native` | library not found, missing V3 ABI symbols, null/empty pointer, invalid MessagePack, `{"error": …}` payload, wrong `schema_version`, retired fields, malformed `planet_parameters` (`src/magic_geo/native.py:110`–`:278`) |
| `ValueError("world planet_parameters must match the configured planet snapshot")` | second gate inside `enrich_world_with_planet_realism` (`src/magic_geo/planet_realism.py:79`–`:85`) |

```python
from magic_geo import create_config
from magic_geo.api import generate_world

world = generate_world(create_config("smoke"))
s = world["summary"]
print(s["cell_count"], s["plate_count"], round(s["ocean_fraction"], 3), s["river_count"])
print("generation_scope" in world)      # False — the key exists only in geo-only worlds
```

### `generate_geo_world`

```python
generate_geo_world(config: WorldConfig) -> dict[str, Any]
```

Generates and enriches natural systems only. Native civilization simulation is skipped, and the stable empty/default civilization schema fields the serializer still emits are removed **before any enricher runs**, so mixed natural models take their documented no-human default branches instead of reading empty lists as real data (docstring at `src/magic_geo/api.py:288`).

Execution order:

1. **Guard**: `if not config.output.include_cells: raise ValueError(...)` (`src/magic_geo/api.py:296`).
2. `world = native_generate_geo_world(config_to_native(config))`.
3. `_require_configured_planet_snapshot(world, config)`.
4. `_strip_native_civilization_outputs(world)` (`src/magic_geo/api.py:269`) — pops 15 top-level fields, 58 summary fields, and 4 per-cell fields.
5. `world["generation_scope"] = "geo_only"` (`:305`).
6. 48 enricher calls.

Stripped sets:

| Set | Count | Constant | Members |
|---|---|---|---|
| Top level | 15 | `NATIVE_CIVILIZATION_TOP_LEVEL_FIELDS` (`src/magic_geo/api.py:86`) | `borders`, `conflicts`, `cultures`, `dynasties`, `historical_eras`, `historical_events`, `language_regions`, `political_regions`, `population_regions`, `routes`, `ruins`, `sacred_areas`, `settlements`, `territorial_snapshots`, `trade_flows` |
| Per cell | 4 | `NATIVE_CIVILIZATION_CELL_FIELDS` (`:106`) | `culture_region_id`, `language_region_id`, `political_region_id`, `settlement_score` |
| Summary | 58 | `NATIVE_CIVILIZATION_SUMMARY_FIELDS` (`:115`) | see `src/magic_geo/api.py:117`–`:175` |

`settlement_score` is the load-bearing per-cell removal. The enricher modules that read it with a `0.0` default are `aquifer_resources`, `ecosystem_dynamics`, `wildfire_disturbance`, `resource_dynamics`, `navigability_diagnostics`, `port_sites`, `land_use_zones`, `settlement_routes`, and `worldbuilding_realism`; of those, the first four also run in geo-only mode, so removing the key forces their natural baseline branch rather than a "civilization exists but scores zero" branch. (`route_corridors` reads the `settlements` array, not the per-cell score, and does not run in geo-only mode at all.)

**Raises** everything `generate_world` raises, plus:

| Exception | Cause |
|---|---|
| `ValueError("generate_geo_world requires output.include_cells=true because natural enrichers and layer validation consume per-cell state")` | `config.output.include_cells` is false (`src/magic_geo/api.py:297`) |

```python
from magic_geo import create_config, apply_config_overrides
from magic_geo.api import generate_geo_world

config = create_config("smoke")
geo = generate_geo_world(config)
print(geo["generation_scope"])                  # geo_only
print("settlements" in geo)                     # False
print("settlement_score" in geo["cells"][0])    # False
print(geo["geo_evolution_provenance"]["model_type"])
# geo_evolution_provenance_registry_v2

blind = apply_config_overrides(config, {"output.include_cells": False})
try:
    generate_geo_world(blind)
except ValueError as exc:
    print(exc)   # generate_geo_world requires output.include_cells=true ...
```

### `generate_from_file` and `generate_geo_from_file`

```python
generate_from_file(path: Path) -> dict[str, Any]         # src/magic_geo/api.py:378
generate_geo_from_file(path: Path) -> dict[str, Any]     # src/magic_geo/api.py:384
```

| Parameter | Type | Meaning |
|---|---|---|
| `path` | `Path` | YAML config path. Annotated as `Path`, but the call goes straight to `load_config`, which accepts `str \| PathLike[str]`. |

Each is a one-line composition: `generate_world(load_config(path))` and `generate_geo_world(load_config(path))`. **Returns** the same world `dict` as the underlying entry point. **Raises** the union of `load_config`'s contract (`OSError` family and `ConfigError`) and the corresponding generator's contract.

```python
from pathlib import Path
from magic_geo.api import generate_from_file, generate_geo_from_file

world = generate_from_file(Path("configs/earthlike_seed.yaml"))
geo   = generate_geo_from_file(Path("configs/seeds/pelagic_archipelago.yaml"))
```

### `backend_info`

```python
backend_info() -> dict[str, Any]
```
`src/magic_geo/api.py:179`. Thin forwarder to `native.backend_info()` (`src/magic_geo/native.py:344`), which loads the library and consumes `magic_geo_backend_info_json()` (`cpp/src/c_api.cpp:153` → `magic_geo::backend_info_json()` at `cpp/src/opencl_compute.cpp:3059`). No parameters. **Returns** a flat `dict` of capability, selection, telemetry, and parity flags. **Raises** the same `RuntimeError` family as generation for library-loading and pointer problems.

When no compute session is active, the C++ side constructs a probe session with `compute_backend = 1` (CPU) and serializes that (`cpp/src/opencl_compute.cpp:3044`), which is why the `backend_selection_reason` on a bare call reads as a capability-only probe. See [Native backend introspection](#native-backend-introspection) for the key table.

---

## The returned world document

The world is a plain Python `dict` of JSON-compatible values: `dict`, `list`, `str`, `int`, `float`, `bool`, `None`. There are no custom classes, no NumPy arrays, and no non-finite floats — the C++ serializers raise `std::runtime_error("attempted to serialize a non-finite simulation value")` rather than emit `NaN`/`Inf`.

### Layers of the document

| Layer | Source | Top-level keys |
|---|---|---|
| Native serialization | `cpp/src/engine/world_serialization.cpp:49`–`:289` | 57, in stable emission order beginning `schema_version`, `name`, `planet_parameters`, `mesh_backend`, `cell_area_model`, `summary`, `backend`, … and ending `cells` |
| Geo-only strip | `src/magic_geo/api.py:269` | removes 15, adds `generation_scope` |
| Python enrichment | 69 enrichers across 67 modules | adds new top-level keys, new per-cell fields, and new `summary` keys |

Observed on a real `smoke`-profile run in this repository (128 cells, 1 erosion iteration, CPU backend):

| Measure | `generate_world` | `generate_geo_world` |
|---|---|---|
| Native top-level keys before enrichment | 57 | 57 (then 15 popped) |
| Top-level keys after enrichment | 191 | 113 |
| Top-level keys added by Python enrichers | 134 | 71 (including `generation_scope` and `geo_evolution_provenance`) |
| Fields on `cells[0]` | 419 | 388 |
| Keys in `summary` | 1293 | 974 |
| `schema_version` | `2` | `2` |
| Keys present only in the geo world | — | `generation_scope`, `geo_evolution_provenance` |

These counts are resolution- and content-dependent: several enrichers only publish a key when the corresponding feature exists in the world, so a different seed or cell count can shift them. Treat them as a scale indicator, not a schema contract. The authoritative per-field schema is on [World Document Schema](./10-world-schema.md).

### Navigating safely

The enrichers themselves model good defensive practice — nearly every one begins with the same guard (for example `src/magic_geo/mesh_lod.py:73`):

```python
cells = world.get("cells", [])
if not isinstance(cells, list) or not cells:
    return world
```

Rules to follow when consuming a world:

| Rule | Why |
|---|---|
| Use `world.get(key, default)`, never `world[key]`, for anything outside the native 57 | Enricher-added top-level keys are conditional on the world containing the relevant feature. |
| Treat `world["cells"]` as possibly `[]` | The native serializer emits `cells: []` when `output.include_cells` is false; the key is always present. |
| Never assume `generation_scope` exists | It is set *only* by `generate_geo_world` (`src/magic_geo/api.py:305`). Full worlds have no such key, and `geo_layer_contracts` tests `root.get("generation_scope") == "geo_only"`. |
| Do not read civilization arrays in geo-only mode | They are popped, not emptied. `world.get("settlements", [])` is the portable form. |
| Treat negative entity ids as "unassigned" | The bundled renderers use this convention, e.g. `int(cell.get("reef_system_id", -1)) >= 0` at `src/magic_geo/io/svg_map.py:118`. |
| Index cells by `cell["id"]`, not by list position | Both bundled renderers build `cell_by_id = {int(cell["id"]): cell for cell in cells if "id" in cell}` (`src/magic_geo/io/svg_map.py:60`, `src/magic_geo/io/raster_map.py:47`). |
| Read planet constants through the helpers | `planet_radius_km(world)`, `planet_gravity_g(world)`, `surface_gravity_m_s2(world)` (`src/magic_geo/planet_parameters.py:73`, `:79`, `:85`) raise `ValueError` on missing/non-finite/non-positive values instead of silently substituting Earth. |
| Do not rely on `summary` completeness across scopes | 58 summary keys are removed in geo-only mode; use `summary.get(...)`. |
| Do not treat any `*_history`/`*_histories` array as physically timed | See [Limitations](#limitations-and-unresolved-claims). `geo_evolution_provenance` classifies each of its 20 registered families explicitly; unregistered ledgers carry their own `*_model` object instead. |

The geo-only world carries a machine-readable provenance registry for exactly this reason. `enrich_world_with_geo_evolution_provenance` (`src/magic_geo/geo_evolution_provenance.py:63`) splits the 20 history families it registers — 7 in `NATIVE_STATE_HISTORY_FAMILIES` and 13 in `DIAGNOSTIC_TRAJECTORY_FAMILIES` — into `native_state_mutation_ledger` versus `posthoc_diagnostic_trajectory`, and records `physical_time_resolved: False` and `nominal_time_calibrated: False` on every family (`src/magic_geo/geo_evolution_provenance.py:85`, `:107`, `:130`). Its model type string is `geo_evolution_provenance_registry_v2` (`:16`). The registry is not a census of every array whose name contains "history": a geo world also carries `crust_dry_rock_accounting_history` and `crust_material_shadow_history`, which are native-side ledgers with no entry in the 20-family registry. Read their own `crust_material_shadow_model` and `crust_dry_rock_accounting_model` objects for their provenance rather than assuming the registry covers them.

---

## Serialization: JSON and .mgeo

`src/magic_geo/serialization.py` is the world persistence layer. The `.mgeo` container stores ordinary MessagePack rather than a Python-specific object representation, so loading it cannot execute code and other languages can decode it from the published framing constants (module docstring, `src/magic_geo/serialization.py:1`).

### Constants

| Constant | Value | Line |
|---|---|---|
| `WorldFormat` | `Literal["auto", "json", "mgeo", "msgpack", "binary"]` | `:25` |
| `CURRENT_WORLD_SCHEMA_VERSION` | `2` | `:27` |
| `MGEO_MAGIC` | `b"MGEO\r\n\x1a\n"` (8 bytes) | `:28` |
| `MGEO_VERSION_MAJOR` / `MGEO_VERSION_MINOR` | `1` / `0` | `:29`, `:30` |
| `MGEO_CODEC_MESSAGEPACK` | `1` | `:31` |
| `MGEO_FLAGS_NONE` | `0` | `:32` |
| `MGEO_HEADER` | `struct.Struct("<8sHHBBHQII")` | `:33` |
| `MGEO_HEADER_SIZE` | `32` (computed from the struct) | `:34` |
| `MGEO_SUFFIXES` | `{".mgeo", ".mgpack", ".msgpack", ".mpk"}` | `:35` |
| `DEFAULT_MAX_WORLD_FILE_BYTES` | `2 * 1024**3` | `:39` |
| `DEFAULT_MAX_STRING_BYTES` | `256 * 1024**2` | `:40` |
| `DEFAULT_MAX_ARRAY_LENGTH` | `50_000_000` | `:41` |
| `DEFAULT_MAX_MAP_LENGTH` | `2_000_000` | `:42` |
| `MAX_WORLD_NESTING_DEPTH` | `64` | `:43` |
| `MIN_MESSAGEPACK_INTEGER` / `MAX_MESSAGEPACK_INTEGER` | `-(2**63)` / `2**64 - 1` | `:44`, `:45` |

The comment at `src/magic_geo/serialization.py:37` notes that the 4 096-cell reference artifact is roughly 193 MB as `.mgeo`, and that `DEFAULT_MAX_WORLD_FILE_BYTES` is an encoded-input bound, **not** a promise about the larger decoded Python graph.

`.mgeo` header layout (little-endian, 32 bytes, `_header` at `src/magic_geo/serialization.py:338`):

| Offset | Struct code | Field | Value |
|---|---|---|---|
| 0 | `8s` | magic | `MGEO\r\n\x1a\n` |
| 8 | `H` | version major | `1` |
| 10 | `H` | version minor | `0` |
| 12 | `B` | codec | `1` = MessagePack |
| 13 | `B` | flags | `0` |
| 14 | `H` | header size | `32` |
| 16 | `Q` | payload size in bytes | `len(packed)` |
| 24 | `I` | payload CRC-32 | `zlib.crc32(packed)` |
| 28 | `I` | world schema version | `payload["schema_version"]` |

### Functions

| Function | Signature | Line | Returns |
|---|---|---|---|
| `dumps_world` | `(payload: dict[str, Any], *, validate_model: bool = True) -> bytes` | `:352` | header + MessagePack bytes |
| `loads_world` | `(data: bytes \| bytearray \| memoryview, *, max_file_bytes: int = DEFAULT_MAX_WORLD_FILE_BYTES, validate_model: bool = True) -> dict[str, Any]` | `:456` | decoded world |
| `write_world_binary` | `(path: Path, payload: dict[str, Any], *, validate_model: bool = True) -> None` | `:475` | — |
| `write_world` | `(path: Path, payload: dict[str, Any], *, format: WorldFormat = "auto", validate_model: bool = True) -> None` | `:532` | — |
| `read_world` | `(path: Path, *, format: WorldFormat = "auto", max_file_bytes: int = DEFAULT_MAX_WORLD_FILE_BYTES, validate_model: bool = True) -> dict[str, Any]` | `:557` | decoded world |
| `validate_world_payload` | `(payload: dict[str, Any]) -> None` | `:237` | — (raises on violation) |
| `retired_world_schema_fields` | `(payload: dict[str, Any]) -> tuple[str, ...]` | `:68` | dotted paths of forbidden retired fields |

Format selection rules:

| Call | Behaviour |
|---|---|
| `write_world(..., format="auto")` | `mgeo` if `path.suffix.lower() in MGEO_SUFFIXES`, else `json` (`:543`) |
| `read_world(..., format="auto")` | `mgeo` if the first 8 bytes equal `MGEO_MAGIC`, else `json` (`:578`) — content sniffing, not suffix |
| `format="msgpack"` or `"binary"` | normalized to `"mgeo"` by `_normalize_format` (`:619`) |
| any other value | `ValueError("world format must be auto, json, or mgeo")` |

`validate_model=True` (the default) runs `validate_world_payload`, a recursive walk enforcing: string-only object keys; UTF-8 strings under `DEFAULT_MAX_STRING_BYTES`; container nesting `<= MAX_WORLD_NESTING_DEPTH`; no reference cycles; map/array size ceilings; integers inside MessagePack's signed/unsigned 64-bit range; finite floats; and no non-JSON value types. The CLI `generate` command deliberately passes `validate_model=False` on the hot save path because the generation pipeline owns the object and its invariants (`src/magic_geo/cli/commands/generate.py:76`–`:78`).

`retired_world_schema_fields` enumerates fields and container aliases that must **not** appear in a schema-2 world — retired accelerator remap counters, retired numeric-depression fill accounting, retired legacy semantics flags on `simulation_clock`, `plate_kinematic_model`, `plate_boundary_segment_model`, `crust_dry_rock_accounting_model`, `backend`, `climate_model`, `oceanic_age_depth_model`, `initial_oceanic_crust_age_model`, and `summary`, plus per-cell, per-feedback-step, per-correction-event and per-motion-step retired fields. `native._require_current_world_schema` (`src/magic_geo/native.py:234`) calls it and raises if any survive, which is how a stale native build is detected.

```python
from pathlib import Path
from magic_geo import create_config
from magic_geo.api import generate_world
from magic_geo.serialization import (
    MGEO_HEADER, MGEO_HEADER_SIZE, MGEO_MAGIC,
    dumps_world, loads_world, read_world, write_world,
)

world = generate_world(create_config("smoke"))

# In-memory round trip.
blob = dumps_world(world)                       # validates the value model first
assert blob[:8] == MGEO_MAGIC
magic, major, minor, codec, flags, hsize, psize, crc, schema = MGEO_HEADER.unpack_from(blob)
print(major, minor, codec, hsize, schema)       # 1 0 1 32 2
assert psize == len(blob) - MGEO_HEADER_SIZE
restored = loads_world(blob)
assert restored["summary"]["cell_count"] == world["summary"]["cell_count"]

# File round trips; format follows the suffix under "auto".
write_world(Path("runs/world.mgeo"), world, validate_model=False)   # binary
write_world(Path("runs/world.json"), world, validate_model=False)   # JSON
same = read_world(Path("runs/world.mgeo"))                          # sniffs the magic
```

`write_world_binary` writes through an `O_EXCL` temp file beside the target (up to 128 name attempts), preserves the existing file mode when overwriting, `fsync`s, and then `os.replace`s — so a reader never sees a torn `.mgeo`. Decoding enforces magic, version, codec, flags, header size, declared-vs-actual payload length, CRC-32, and that the decoded `schema_version` matches the header's copy; MessagePack extension types are rejected outright by `_reject_extension` (`src/magic_geo/serialization.py:52`).

---

## The io writers

`src/magic_geo/io/__init__.py` re-exports `read_world`, `write_world`, and `write_world_binary` from `magic_geo.serialization` "because callers have always imported them from here", plus the five format writers below. All five create parent directories themselves — `write_json` (`src/magic_geo/io/json_writer.py:11`), `write_cells_csv` (`src/magic_geo/io/cells_csv.py:13`), `write_summary_markdown` (`src/magic_geo/io/summary_markdown.py:10`), `write_svg_map` (`src/magic_geo/io/svg_map.py:29`), and `write_raster_map` (`src/magic_geo/io/raster_map.py:24`) each call `path.parent.mkdir(parents=True, exist_ok=True)` before writing, so you never have to pre-create the output directory.

| Writer | Signature | Module | Output |
|---|---|---|---|
| `write_json` | `(path: Path, payload: dict[str, Any]) -> None` | `src/magic_geo/io/json_writer.py:10` | UTF-8 JSON, `indent=2`, `sort_keys=True`, `allow_nan=False` |
| `write_cells_csv` | `(path: Path, world: dict[str, Any]) -> None` | `src/magic_geo/io/cells_csv.py:11` | CSV with a fixed 397-column header |
| `write_summary_markdown` | `(path: Path, world: dict[str, Any]) -> None` | `src/magic_geo/io/summary_markdown.py:9` | Markdown report |
| `write_svg_map` | `(path, world, *, width=1600, height=800, projection="equirectangular", labels=False, max_cells=None, contours=True, contour_interval_m=500.0) -> None` | `src/magic_geo/io/svg_map.py:12` | SVG |
| `write_raster_map` | `(path, world, *, width=1600, height=800, projection="equirectangular", max_cells=None, texture=True) -> None` | `src/magic_geo/io/raster_map.py:10` | binary PPM (`P6`) |

### `write_json`

No options. `json.dumps(payload, indent=2, sort_keys=True, allow_nan=False)` — keys are sorted, so the on-disk order is *not* the native emission order, and a non-finite float raises `ValueError` from the stdlib encoder. This is the same writer `write_world` delegates to for the JSON branch (`src/magic_geo/serialization.py:550`).

### `write_cells_csv`

Reads `world.get("cells", [])` and writes a `csv.DictWriter` with `extrasaction="ignore"` over a **fixed** 397-name `fieldnames` list (`src/magic_geo/io/cells_csv.py:14`–`:412`, count verified by AST). Consequences worth knowing:

| Behaviour | Detail |
|---|---|
| Column set is fixed, not derived from the world | Cell fields not in the list are silently dropped (`extrasaction="ignore"`). |
| Missing fields are not an error | `DictWriter` writes the empty string for any listed name a cell lacks — so a geo-only export still emits `political_region_id`, `culture_region_id`, `language_region_id`, `settlement_score` columns, empty. |
| Column order is the literal list order | It groups roughly by domain: identity/geometry → tectonics → elevation/water → navigation/ports/routes → reefs → climate → energy balance → hydrology → sediment → cryosphere → permafrost → landform/soil → biome → groundwater → karst → ecology → resources → land use → spatial indices → ocean circulation → plate history → hydrologic surface → sediment ledgers. |
| Rows are the cells in list order | No sorting, no filtering. |

```python
from pathlib import Path
from magic_geo.io import write_cells_csv

write_cells_csv(Path("runs/cells.csv"), world)
```

### `write_summary_markdown`

Reads `world.get("summary", {})` and `world.get("backend", {})`. Structure of the emitted document:

| Part | Content |
|---|---|
| `# {world.get('name', 'magic-geo world')}` | title line (`src/magic_geo/io/summary_markdown.py:15`) |
| `## Summary` | bullets for a fixed candidate list of **1 243** summary keys, each emitted only `if key in summary` (`:1265`) — so absent keys are skipped rather than rendered blank |
| 35 histogram sections | one `## {section}` per non-empty count map, from `boundary_counts` through `natural_frontier_type_counts` (`:1269`–`:1304`), each rendering `` - `key`: value `` sorted by key |
| `## Backend` | every key of `world["backend"]`, sorted (`:1311`) |

Both list lengths were verified by parsing the module's AST. The candidate key list covers native summary keys *and* enricher-added summary keys (`mesh_lod_*`, `spherical_spatial_index`, realism scores, and so on), which is why it is far larger than the native summary itself.

### `write_svg_map`

| Option | Type | Default | Effect |
|---|---|---|---|
| `width` | `int` | `1600` | SVG viewBox width in px. |
| `height` | `int` | `800` | SVG viewBox height in px. |
| `projection` | `str` | `"equirectangular"` | Lowercased and `_`→`-` normalized, then checked against `{"equirectangular", "mollweide", "orthographic"}`; anything else raises `ValueError(f"unknown projection: {projection}")` (`src/magic_geo/io/svg_map.py:31`). |
| `labels` | `bool` | `False` | Draws text labels for the top 24 settlements by `score` (`:350`). |
| `max_cells` | `int \| None` | `None` | When set and smaller than the cell count, renders `cells[::stride]` with `stride = ceil(len(cells) / max_cells)` (`:182`). |
| `contours` | `bool` | `True` | Emits a `<g class="terrain-contours">` layer of per-edge contour crossings. |
| `contour_interval_m` | `float` | `500.0` | Contour spacing, clamped to at least `50.0` (`:215`). |

Rendering facts: each cell becomes a `<circle class="terrain-cell">` whose radius is `max(0.7, min(3.2, (width*height/len(render_cells))**0.5 * 0.23))` (`:187`); fills blend a 16-entry biome palette (`:34`) with an elevation ramp, then apply aridity, ice, landform and local-relief modifiers; water cells blend by `water_depth_m / 4200` and pick up a reef tint when `reef_system_id >= 0` or `reef_growth_index >= 0.46`. Routes, `sacred_areas`, `ruins`, and `settlements` are drawn only if those arrays exist — in a geo-only world they are absent and `world.get(...)` yields `[]`, so the map is purely physical. Equirectangular edges that wrap more than `width * 0.55` are skipped to avoid seam artifacts (`:263`, `:296`). The root element carries `data-projection`, `data-renderer="terrain-v1"`, and `data-contours`.

### `write_raster_map`

| Option | Type | Default | Effect |
|---|---|---|---|
| `width` | `int` | `1600` | Pixel width. |
| `height` | `int` | `800` | Pixel height. |
| `projection` | `str` | `"equirectangular"` | Same three-value set and same `ValueError` (`src/magic_geo/io/raster_map.py:26`). |
| `max_cells` | `int \| None` | `None` | Same stride subsampling as the SVG writer (`:222`). |
| `texture` | `bool` | `True` | Adds deterministic per-cell noise plus relief and erosion shading (`:133`). |

Output is a dependency-free binary PPM: header `P6\n# magic-geo raster-terrain-v1 projection={projection} texture={true|false}\n{width} {height}\n255\n` followed by raw RGB bytes (`:275`). Disc radius is `max(1.0, min(18.0, (width*height/len(render_cells))**0.5 * 0.48))` (`:238`). Under `orthographic`, pixels outside the disc are painted `(12, 25, 37)`. Note this writer emits `.ppm` content regardless of the filename you give it — convert externally if you need PNG.

```python
from pathlib import Path
from magic_geo.io import write_raster_map, write_svg_map

write_svg_map(Path("runs/world.svg"), world,
              projection="mollweide", labels=True, contour_interval_m=250.0)
write_raster_map(Path("runs/world.ppm"), world,
                 projection="orthographic", width=1200, height=1200, texture=False)
```

---

## Calling enrichers directly

Every enricher has the shape `enrich_world_with_X(world: dict[str, Any], ...) -> dict[str, Any]`, **mutates `world` in place**, and returns the same object. There are 69 distinct enrichers; `generate_world` calls 66 of them and `generate_geo_world` calls 48.

### The ordering constraint

The call order is a data dependency graph, not a style choice. Enrichers read fields that earlier enrichers wrote, and they read them with `.get(field, default)` — so calling one out of order does **not** raise; it silently produces a result computed from the default. Two concrete examples visible in the source:

- `enrich_world_with_river_hydraulics` reads `river_channel_width_m`, `river_channel_depth_m`, `bankfull_discharge_m3_s`, and `channel_slope_index`, all of which are written by `enrich_world_with_river_channel_morphology`. Running hydraulics first yields a fully populated but physically meaningless reach set.
- `enrich_world_with_groundwater_flow` consumes `world["aquifer_systems"]` and the per-cell `groundwater_recharge_km3_y` produced by `enrich_world_with_aquifer_resources`.

Two enrichers are wrappers that internally guarantee their own prerequisite:

| Wrapper | Calls first | Line |
|---|---|---|
| `enrich_world_with_graph_diagnostics` | `enrich_world_with_physical_graph_diagnostics` | `src/magic_geo/graph_diagnostics.py:552` |
| `enrich_world_with_boundary_geometry` | `enrich_world_with_physical_boundary_geometry` | `src/magic_geo/boundary_geometry.py:280` |

Practical guidance: to add a layer, run the full pipeline and then call your own function; to *re-run* a bundled enricher after mutating the world, re-run every enricher downstream of it in the table below as well.

### Complete ordered call table

Positions are the literal call order in `src/magic_geo/api.py:200`–`:265` (full) and `:308`–`:374` (geo-only). `—` means the entry point does not call that enricher.

| Full # | Geo # | Enricher (`enrich_world_with_` prefix stripped) | Module |
|---:|---:|---|---|
| 1 | 1 | `mesh_lod` | `src/magic_geo/mesh_lod.py:72` |
| 2 | 2 | `spherical_index` | `src/magic_geo/spherical_index.py:102` |
| 3 | 3 | `cell_geometry` | `src/magic_geo/cell_geometry.py:249` |
| 4 | 7 | `sea_level_diagnostics` | `src/magic_geo/sea_level_diagnostics.py:300` |
| 5 | 8 | `ocean_circulation` | `src/magic_geo/ocean_circulation.py:221` |
| 6 | 9 | `climate_continentality` | `src/magic_geo/climate_continentality.py:178` |
| 7 | 4 | `geology_realism` | `src/magic_geo/geology_realism.py:127` |
| 8 | 5 | `tectonic_zones` | `src/magic_geo/tectonic_zones.py:241` |
| 9 | 6 | `fault_systems` | `src/magic_geo/fault_systems.py:198` |
| 10 | 10 | `seasonal_climate_history` | `src/magic_geo/climate_dynamics.py:178` |
| 11 | 11 | `climate_energy_balance` | `src/magic_geo/climate_energy.py:116` |
| 12 | 12 | `planet_realism` | `src/magic_geo/planet_realism.py:79` |
| 13 | 13 | `climate_realism` | `src/magic_geo/climate_realism.py:77` |
| 14 | 14 | `lake_overflow_history` | `src/magic_geo/hydrology_dynamics.py:292` |
| 15 | 15 | `watershed_diagnostics` | `src/magic_geo/watershed_diagnostics.py:94` |
| 16 | 17 | `sediment_routing_history` | `src/magic_geo/sediment_routing.py:82` |
| 17 | 16 | `hydrology_realism` | `src/magic_geo/hydrology_realism.py:151` |
| 18 | 18 | `river_network_evolution` | `src/magic_geo/river_network_evolution.py:217` |
| 19 | 19 | `sediment_transport_history` | `src/magic_geo/sediment_dynamics.py:44` |
| 20 | 20 | `sequence_stratigraphy` | `src/magic_geo/sequence_stratigraphy.py:84` |
| 21 | 21 | `ice_sheet_history` | `src/magic_geo/cryosphere_dynamics.py:11` |
| 22 | 22 | `ice_sheet_stability` | `src/magic_geo/cryosphere_stability.py:64` |
| 23 | 23 | `ice_flowline_history` | `src/magic_geo/cryosphere_flow.py:86` |
| 24 | 24 | `soil_diagnostics` | `src/magic_geo/soil_dynamics.py:262` |
| 25 | 27 | `biome_diagnostics` | `src/magic_geo/biome_dynamics.py:89` |
| 26 | 25 | `permafrost_diagnostics` | `src/magic_geo/permafrost_diagnostics.py:129` |
| 27 | 26 | `glacial_landforms` | `src/magic_geo/glacial_landforms.py:279` |
| 28 | 28 | `biome_ecotones` | `src/magic_geo/biome_ecotones.py:205` |
| 29 | 29 | `biome_realism` | `src/magic_geo/biome_realism.py:90` |
| 30 | 30 | `aquifer_resources` | `src/magic_geo/aquifer_resources.py:58` |
| 31 | 31 | `hydrology_budget` | `src/magic_geo/hydrology_budget.py:138` |
| 32 | 32 | `wetland_diagnostics` | `src/magic_geo/wetland_diagnostics.py:262` |
| 33 | 33 | `groundwater_flow` | `src/magic_geo/groundwater_flow.py:115` |
| 34 | 34 | `river_channel_morphology` | `src/magic_geo/river_channel_morphology.py:144` |
| 35 | 35 | `river_hydraulics` | `src/magic_geo/river_hydraulics.py:111` |
| 36 | — | `settlement_route_models` | `src/magic_geo/settlement_routes.py:41` |
| 37 | — | `political_geography_models` | `src/magic_geo/political_geography.py:14` |
| 38 | — | `cultural_geography_models` | `src/magic_geo/cultural_geography.py:11` |
| 39 | — | `historical_geography_model` | `src/magic_geo/historical_geography.py:9` |
| 40 | — | `civilization_geography_models` | `src/magic_geo/civilization_geography.py:11` |
| 41 | — | `territorial_geography_model` | `src/magic_geo/territorial_geography.py:9` |
| 42 | — | `navigability_diagnostics` | `src/magic_geo/navigability_diagnostics.py:251` |
| 43 | — | `port_sites` | `src/magic_geo/port_sites.py:176` |
| 44 | — | `route_corridors` | `src/magic_geo/route_corridors.py:380` |
| 45 | 36 | `karst_diagnostics` | `src/magic_geo/karst_diagnostics.py:121` |
| 46 | 37 | `ecosystem_dynamics` | `src/magic_geo/ecosystem_dynamics.py:133` |
| 47 | 38 | `reef_diagnostics` | `src/magic_geo/reef_diagnostics.py:281` |
| 48 | 39 | `species_ranges` | `src/magic_geo/species_ranges.py:297` |
| 49 | 40 | `wildfire_disturbance` | `src/magic_geo/wildfire_disturbance.py:270` |
| 50 | 41 | `resource_deposits` | `src/magic_geo/resource_dynamics.py:148` |
| 51 | 42 | `ore_genesis` | `src/magic_geo/ore_genesis.py:323` |
| 52 | 43 | `sedimentary_resource_systems` | `src/magic_geo/sedimentary_resource_systems.py:152` |
| 53 | 44 | `petroleum_migration` | `src/magic_geo/petroleum_migration.py:281` |
| 54 | 45 | `commodity_occurrences` | `src/magic_geo/commodity_resources.py:195` |
| 55 | — | `land_use_zones` | `src/magic_geo/land_use_zones.py:205` |
| 56 | — | `natural_frontiers` | `src/magic_geo/natural_frontiers.py:166` |
| 57 | — | `worldbuilding_realism` | `src/magic_geo/worldbuilding_realism.py:145` |
| 58 | — | `population_history` | `src/magic_geo/history_dynamics.py:107` |
| 59 | — | `economy_history` | `src/magic_geo/economy_dynamics.py:119` |
| 60 | — | `dynasty_genealogy` | `src/magic_geo/dynasty_genealogy.py:110` |
| 61 | — | `logistics_history` | `src/magic_geo/logistics_history.py:746` |
| 62 | — | `demographic_agents` | `src/magic_geo/demographic_agents.py:152` |
| 63 | — | `market_clearing` | `src/magic_geo/market_clearing.py:120` |
| 64 | — | `graph_diagnostics` | `src/magic_geo/graph_diagnostics.py:547` |
| 65 | — | `boundary_geometry` | `src/magic_geo/boundary_geometry.py:275` |
| 66 | — | `phonology_history` | `src/magic_geo/phonology_history.py:273` |
| — | 46 | `physical_graph_diagnostics` | `src/magic_geo/graph_diagnostics.py:513` |
| — | 47 | `physical_boundary_geometry` | `src/magic_geo/boundary_geometry.py:261` |
| — | 48 | `geo_evolution_provenance` | `src/magic_geo/geo_evolution_provenance.py:63` |

### Ordering deltas between the two entry points

Beyond the 21 civilization enrichers geo-only omits, five orderings genuinely differ:

| Change | Full-world | Geo-only |
|---|---|---|
| Geology/tectonics/faults relative to sea level and ocean circulation | 7–9 (after) | 4–6 (before) |
| `hydrology_realism` vs `sediment_routing_history` | 17 after 16 | 16 before 17 |
| `permafrost_diagnostics` + `glacial_landforms` vs `biome_diagnostics` | 26–27 after 25 | 25–26 before 27 |
| `karst_diagnostics` | 45, trailing `route_corridors` | 36, inside the water-systems block |
| Graph and boundary products | `graph_diagnostics`, `boundary_geometry` | `physical_graph_diagnostics`, `physical_boundary_geometry`, plus geo-only `geo_evolution_provenance` |

### Enrichers with parameters beyond `world`

Sixty-two of the sixty-nine take exactly `(world)`. The remaining seven:

| Enricher | Full signature | Passed by `api.py` as | Why |
|---|---|---|---|
| `climate_energy_balance` | `(world, planet: Any \| None = None)` | `enrich_world_with_climate_energy_balance(world, config.planet)` (`src/magic_geo/api.py:210`, `:324`) | The zero-dimensional radiation budget needs `stellar_luminosity`, `greenhouse_factor`, `atmosphere_pressure_bar`, `axial_tilt_deg`, `orbital_eccentricity`, read through `_planet_value` (`src/magic_geo/climate_energy.py:17`), which accepts a dict or an attribute object and falls back to `1.0 / 1.0 / 1.0 bar / 23.5° / 0.016` when `planet is None`. `SOLAR_CONSTANT_W_M2 = 1361.0` (`:8`). |
| `planet_realism` | `(world, planet: Any \| None = None)` | `enrich_world_with_planet_realism(world, config.planet)` (`:211`, `:325`) | Acts as a second consistency gate: recomputes `planet_parameter_snapshot(planet)` and raises `ValueError("world planet_parameters must match the configured planet snapshot")` on disagreement (`src/magic_geo/planet_realism.py:79`–`:85`). |
| `ice_sheet_history` | `(world, step_count: int = 8)` | default | 8 mass-balance steps per ice sheet. |
| `sediment_transport_history` | `(world, step_count: int = 6)` | default | 6 transport steps per basin. |
| `lake_overflow_history` | `(world, simulation_years: int = 12)` | default | 12-step fill/spill trajectory. |
| `sediment_routing_history` | `(world, route_limit: int = 12, max_path_length: int = 72)` | default | 12 traced source paths, at most 72 cells each. |
| `ice_flowline_history` | `(world, flowline_limit: int = 10, max_path_length: int = 48)` | default | 10 flowlines, at most 48 cells each. |

Those five step/limit knobs set the depth and cost of *diagnostic trajectories*, not of the native simulation. Raising them produces longer synthetic sequences; it does not add physical resolution. See [Limitations](#limitations-and-unresolved-claims).

```python
from magic_geo import create_config
from magic_geo.api import generate_geo_world
from magic_geo.cryosphere_dynamics import enrich_world_with_ice_sheet_history
from magic_geo.cryosphere_stability import enrich_world_with_ice_sheet_stability

world = generate_geo_world(create_config("smoke"))

# Re-run a trajectory at greater depth, then re-run everything downstream of it.
enrich_world_with_ice_sheet_history(world, step_count=24)
enrich_world_with_ice_sheet_stability(world)   # consumes ice_sheet_histories

print(len(world.get("ice_sheet_histories", [])))
```

### Writing your own enricher

Follow the house pattern so your layer behaves like the bundled ones:

```python
from typing import Any


def enrich_world_with_my_layer(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world

    summary = world.setdefault("summary", {})
    records: list[dict[str, Any]] = []
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        # Read with explicit defaults; never assume an upstream enricher ran.
        relief = float(cell.get("elevation_m", 0.0)) - float(cell.get("filled_elevation_m", 0.0))
        cell["my_layer_relief_m"] = relief
        if relief < -1.0:
            records.append({"cell_id": int(cell.get("id", -1)), "relief_m": relief})

    world["my_layer_records"] = records
    summary["my_layer_record_count"] = len(records)
    return world
```

Conventions the bundled enrichers follow and that keep your output serializable: mutate in place and return `world`; guard on `cells` being a non-empty list; write into `world.setdefault("summary", {})` for scalar rollups; emit only JSON value types (a `set`, `Decimal`, or NumPy scalar will fail `validate_world_payload` and `msgpack.packb`); and emit explicit zeroed defaults rather than omitting keys when a feature is absent, so consumers can distinguish "none present" from "layer never ran".

---

## Native backend introspection

`src/magic_geo/native.py` is the ctypes bridge. It is usable directly when you want the raw native world with **no Python enrichment** — for example to diff native output against an enriched world.

| Function | Signature | Line |
|---|---|---|
| `backend_info` | `() -> dict[str, Any]` | `:344` |
| `generate_world` | `(data: dict[str, Any], *, serialization: str = "auto") -> dict[str, Any]` | `:349` |
| `generate_geo_world` | `(data: dict[str, Any], *, serialization: str = "auto") -> dict[str, Any]` | `:375` |

`data` is the mapping produced by `config_to_native`, i.e. the nested 9-section JSON dump. `serialization` must be `"auto"`, `"json"`, or `"msgpack"`; `"auto"` and `"msgpack"` both take the MessagePack path (`magic_geo_generate_msgpack_v3`), `"json"` takes `magic_geo_generate_json_v3`. Any other value raises `ValueError("serialization must be auto, json, or msgpack")`.

Library resolution (`_library_path`, `src/magic_geo/native.py:110`):

| Step | Behaviour |
|---|---|
| 1 | `MAGIC_GEO_NATIVE_LIBRARY` env var, if set, is expanded and resolved; a non-file raises `RuntimeError(f"MAGIC_GEO_NATIVE_LIBRARY does not name a file: {candidate}")`. |
| 2 | Otherwise the package directory is searched for exactly one host-native name: `magic_geo_native.dll` (win32), `libmagic_geo_native.dylib` (darwin), else `libmagic_geo_native.so` (`:30`). |
| 3 | Nothing found → `RuntimeError("native library was not found. Build it with: cmake -S . -B build && cmake --build build")`. |

`_load_library` (`:130`) then requires the full current V3 ABI — `magic_geo_backend_info_json`, `magic_geo_generate_json_v3`, `magic_geo_generate_geo_json_v3`, `magic_geo_generate_msgpack_v3`, `magic_geo_generate_geo_msgpack_v3`, `magic_geo_free_string`, `magic_geo_free_buffer` — and raises `RuntimeError("native library does not expose the current V3 JSON and MessagePack ABI; rebuild magic_geo_native from the current source tree")` if any is missing.

### The `backend` object

`backend_info()` returns the same object the native serializer embeds at `world["backend"]` (`cpp/src/engine/world_serialization.cpp:85`). On this repository's CPU build a bare `backend_info()` call returned **178 keys**; the exact key set depends on which accelerators were compiled in, so treat the count as build-specific. First keys in emission order (`cpp/src/opencl_compute.cpp:2033`):

| Key | Kind | Notes |
|---|---|---|
| `native_core` | string | `"c++20"` |
| `openmp_enabled` | bool | compile-time `MAGIC_GEO_HAS_OPENMP` |
| `openmp_max_threads` | int | `omp_get_max_threads()`, else `1` |
| `requested_backend` | string | from `compute.backend` |
| `selected_backend` | string | what the runtime chose |
| `active_backend` | string | `"hybrid"` when a fallback occurred *and* accelerator dispatches happened, else `selected_backend` |
| `initial_selected_backend` | string | pre-fallback choice |
| `backend_selection_reason` | string | human-readable; on a bare probe it reads `capability-only probe; no generation is active` |
| `backend_scope` | string | fixed `"accelerated_native_kernels_not_end_to_end_pipeline"` |
| `crust_transport_execution_backend` | string | fixed `"cpu"` |
| `crust_transport_execution_model` | string | `"forward_spherical_control_volume_overlap_v1"` |
| `crust_transport_accelerator_dispatch_count` | int | fixed `0` |
| `cpu_conservative_crust_overlap_transition_count` | int | CPU conservative-overlap transition counter (`cpp/src/opencl_compute.cpp:2088`) |
| `crust_overlap_geometry_and_csr_authoritative_backend` | string | fixed `"cpu"` |
| `crust_overlap_continuous_production_remap_authoritative_backend` | string | fixed `"cpu"` |
| `crust_overlap_continuous_shadow_model` | string | `"cpu_authoritative_overlap_csr_continuous_moment_shadow_v1"` |

followed by the shadow-validation block, the accelerator-parity flags, planning thresholds (`automatic_planning_cell_count`, `cuda_auto_min_cell_count`, `opencl_auto_min_cell_count`, `*_auto_offload_eligible`), fallback telemetry (`backend_fallback_used`, `backend_fallback_stage`, `backend_fallback_reason`), and the long `cuda_*` / OpenCL device and counter blocks.

The parity and authority flags are the epistemically load-bearing ones. All four are hard-coded literals in the current source — the accelerated continuous overlap path is shadow-only (`true`), and every parity/authority claim about it is `false`:

| Key | Value | Location |
|---|---|---|
| `crust_overlap_continuous_shadow_only` | `true` | `cpp/src/opencl_compute.cpp:2130` |
| `crust_overlap_continuous_shadow_authoritative` | `false` | `cpp/src/opencl_compute.cpp:2136` |
| `crust_overlap_accelerator_complete_parity_demonstrated` | `false` | `cpp/src/opencl_compute.cpp:2166` |
| `crust_overlap_accelerator_state_authoritative` | `false` | `cpp/src/opencl_compute.cpp:2172` |

```python
from magic_geo.api import backend_info

info = backend_info()
print(info["native_core"], info["selected_backend"], info["active_backend"])
print(info["backend_scope"])
# accelerated_native_kernels_not_end_to_end_pipeline
assert info["crust_overlap_accelerator_complete_parity_demonstrated"] is False
assert info["crust_overlap_accelerator_state_authoritative"] is False
```

### Native-only generation

```python
from magic_geo import create_config
from magic_geo.config import config_to_native
from magic_geo.native import generate_world as native_generate_world

raw = native_generate_world(config_to_native(create_config("smoke")))
print(len(raw))                 # 57 native top-level keys
print(raw["schema_version"])    # 2
print("mesh_lod" in raw)        # False — no Python enrichment has run
```

`_require_current_world_schema` (`src/magic_geo/native.py:234`) runs on every native return and enforces, in order: `schema_version == CURRENT_WORLD_SCHEMA_VERSION` (2); no retired fields per `retired_world_schema_fields`; `planet_parameters` present as a dict; all 12 `PLANET_PARAMETER_DEFAULTS` keys present; each value non-bool numeric and finite; and `radius_km`, `gravity_g`, `geological_age_ga` strictly positive.

---

## Error types and what raises them

| Exception | Base | Raised by | Typical triggers |
|---|---|---|---|
| `ConfigError` | `ValueError` | `magic_geo.config` (`src/magic_geo/config.py:41`) | invalid YAML syntax, duplicate/unhashable YAML keys, YAML complexity limits, non-mapping root, model-validation failures, unknown profile, malformed or unknown overrides |
| `pydantic.ValidationError` | `ValueError` | direct `WorldConfig.model_validate(...)` / `WorldConfig(...)` calls you make yourself | any field or cross-field violation. The library's own helpers convert this to `ConfigError` via `_config_validation_error` (`src/magic_geo/config.py:532`); it escapes only when you bypass them. |
| `FileExistsError` | `OSError` | `write_config` (`src/magic_geo/config.py:805`, `:820`) | target exists without `force=True`, or a concurrent writer won the `os.link` race |
| `FileNotFoundError`, `PermissionError`, `IsADirectoryError`, `UnicodeDecodeError` | — | `load_config` (`src/magic_geo/config.py:836`) | I/O problems, deliberately *not* wrapped in `ConfigError` |
| `ValueError` | — | `generate_geo_world` (`src/magic_geo/api.py:297`) | `output.include_cells` is false |
| `ValueError` | — | `enrich_world_with_planet_realism` (`src/magic_geo/planet_realism.py:82`) | `world["planet_parameters"]` disagrees with the configured snapshot |
| `ValueError` | — | `write_svg_map` (`src/magic_geo/io/svg_map.py:32`), `write_raster_map` (`src/magic_geo/io/raster_map.py:27`) | `unknown projection: {projection}` |
| `ValueError` | — | `magic_geo.native.generate_world` / `generate_geo_world` (`:357`, `:383`) | `serialization` not in `{"auto", "json", "msgpack"}` |
| `ValueError` | — | `_normalize_format` (`src/magic_geo/serialization.py:626`) | `format` not in `{auto, json, mgeo, msgpack, binary}` |
| `ValueError` | — | `read_world`/`loads_world` (`src/magic_geo/serialization.py:370`, `:569`) | `max_file_bytes` negative |
| `ValueError` | — | `planet_radius_km`, `planet_gravity_g`, `surface_gravity_m_s2` (`src/magic_geo/planet_parameters.py:49`) | missing/non-numeric/non-finite/non-positive planet parameter in the world |
| `WorldSerializationError` | `ValueError` | `magic_geo.serialization` (`:48`) | bad magic/version/codec/flags/header size, payload-length mismatch, CRC mismatch, MessagePack extension types, non-integer `schema_version`, non-object root, size/depth/cycle/type violations from `validate_world_payload`, oversized files |
| `RuntimeError` | — | `magic_geo.api` (`:190`) | native `planet_parameters` disagree with the configured snapshot |
| `RuntimeError` | — | `magic_geo.native` (`:115`, `:124`, `:141`, `:171`, `:175`, `:180`, `:191`, `:194`, `:220`, `:228`, `:230`, `:237`, `:245`, `:251`, `:255`, `:263`) | library path override is not a file; library not found; missing V3 ABI; null/empty pointer; native `{"error": …}` payload; invalid MessagePack; non-object root; unsupported `schema_version`; retired fields present; missing/incomplete/invalid `planet_parameters` |

`ConfigError` and `WorldSerializationError` both subclass `ValueError`, so a single `except ValueError` catches configuration and serialization failures but **not** the `RuntimeError` family from the native bridge. A robust embedding catches both:

```python
from magic_geo import ConfigError, load_config
from magic_geo.api import generate_world
from magic_geo.serialization import WorldSerializationError

try:
    world = generate_world(load_config("magic-geo.yaml"))
except ConfigError as exc:
    print("config problem:", exc.to_dict())
except (FileNotFoundError, PermissionError, IsADirectoryError) as exc:
    print("io problem:", exc)
except WorldSerializationError as exc:
    print("payload problem:", exc)
except RuntimeError as exc:
    print("native problem:", exc)
except ValueError as exc:
    print("api problem:", exc)
```

---

## End-to-end recipes

### Recipe 1 — generate and post-process entirely in memory

Generate a geo-only world, derive a small statistic from the per-cell fields, attach it as a custom layer, validate it, and persist. Nothing touches disk until the final write.

```python
from statistics import fmean

from magic_geo import create_config
from magic_geo.api import generate_geo_world
from magic_geo.geo_validation import validate_geo_world
from magic_geo.planet_parameters import planet_radius_km, surface_gravity_m_s2
from magic_geo.serialization import validate_world_payload, write_world

config = create_config("earthlike", {"run.seed": 91117, "mesh.cell_count": 2048})
world = generate_geo_world(config)

print(world["generation_scope"])                     # geo_only
print(planet_radius_km(world), surface_gravity_m_s2(world))

cells = world.get("cells", [])
land = [c for c in cells if not c.get("is_water", False)]
rivers = [c for c in land if c.get("is_river", False)]

# Custom derived layer, written with the same conventions the bundled enrichers use.
for cell in cells:
    head = float(cell.get("groundwater_hydraulic_head_m", 0.0))
    surface = float(cell.get("elevation_m", 0.0))
    cell["my_water_table_depth_m"] = max(0.0, surface - head)

world["my_layer_model"] = {
    "model_type": "surface_minus_hydraulic_head_v1",
    "unit": "m",
    "physical_time_resolved": False,
}
world.setdefault("summary", {})["my_mean_water_table_depth_m"] = fmean(
    float(c.get("my_water_table_depth_m", 0.0)) for c in land
) if land else 0.0

print(f"land={len(land)} rivers={len(rivers)} "
      f"mean_water_table_depth_m={world['summary']['my_mean_water_table_depth_m']:.2f}")

report = validate_geo_world(world, profile="generic")
print("validation passed:", report["passed"],
      "checks:", len(report["checks"]),
      "layer contracts:", report["summary"]["layer_contract_count"])

validate_world_payload(world)                        # your added keys must stay JSON-typed
write_world("runs/geo_with_custom_layer.mgeo", world, validate_model=False)
```

Notes: `validate_geo_world` never raises — a malformed payload becomes a failed `contract/malformed_optional_payload` check instead (`src/magic_geo/geo_validation.py:2761`). Run `validate_world_payload` yourself after adding custom keys; it is the same check `write_world` would run with `validate_model=True`, and it will reject a `set`, a `Decimal`, a NumPy scalar, or a non-finite float before it reaches the encoder.

### Recipe 2 — batch sweep over seeds

One config, many seeds, one row of metrics per world, plus a `.mgeo` per run. `create_config` is cheap; `generate_geo_world` is the expensive part, so keep the loop body minimal and drop each world as soon as its metrics are extracted.

```python
import csv
import time
from pathlib import Path

from magic_geo import create_config
from magic_geo.api import generate_geo_world
from magic_geo.serialization import write_world

SEEDS = [101, 202, 303, 404, 505]
OUT = Path("runs/sweep")
OUT.mkdir(parents=True, exist_ok=True)

FIELDS = [
    "seed", "elapsed_s", "cell_count", "plate_count", "ocean_fraction",
    "river_count", "lake_count", "watershed_count",
    "mean_land_elevation_m", "min_elevation_m", "max_elevation_m",
    "sediment_budget_residual_km3", "mean_geology_realism_score",
    "mean_climate_realism_score", "mean_hydrology_realism_score",
]

with (OUT / "sweep.csv").open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
    writer.writeheader()
    for seed in SEEDS:
        config = create_config("earthlike", {
            "run.seed": seed,
            "run.name": f"sweep_{seed}",
            "mesh.cell_count": 4096,
            "compute.backend": "cpu",
        })
        started = time.monotonic()
        world = generate_geo_world(config)
        elapsed = time.monotonic() - started

        summary = world.get("summary", {})
        row = {"seed": seed, "elapsed_s": round(elapsed, 2)}
        for key in FIELDS[2:]:
            row[key] = summary.get(key)          # absent keys stay blank, never KeyError
        writer.writerow(row)
        handle.flush()

        write_world(OUT / f"world_{seed}.mgeo", world, validate_model=False)
        del world                                # release before the next generation
        print(f"seed={seed} elapsed={elapsed:.1f}s ocean={summary.get('ocean_fraction')}")
```

Determinism note: `run.seed` is the unsigned 64-bit master seed used by every deterministic random process (`src/magic_geo/config.py:129`). Holding everything else fixed, a seed change is the only intended source of variation. Changing `compute.backend` is **not** guaranteed to preserve results — the backend object itself reports `crust_overlap_accelerator_complete_parity_demonstrated: false`, so pin `compute.backend` inside a sweep you intend to compare.

### Recipe 3 — custom export pipeline

Generate once, then fan out to every bundled writer plus a hand-rolled GeoJSON extract, without regenerating.

```python
from pathlib import Path

from magic_geo import load_config
from magic_geo.api import generate_world
from magic_geo.io import (
    write_cells_csv, write_json, write_raster_map,
    write_summary_markdown, write_svg_map, write_world,
)

out = Path("runs/export")
world = generate_world(load_config("configs/earthlike_seed.yaml"))

# Bundled writers.
write_world(out / "world.mgeo", world, validate_model=False)      # binary, by suffix
write_world(out / "world.json", world, validate_model=False)      # JSON, by suffix
write_summary_markdown(out / "summary.md", world)
write_cells_csv(out / "cells.csv", world)                          # fixed 397 columns
write_svg_map(out / "map.svg", world, projection="mollweide",
              labels=True, contours=True, contour_interval_m=250.0)
write_svg_map(out / "globe.svg", world, projection="orthographic",
              width=1200, height=1200, contours=False)
write_raster_map(out / "map.ppm", world, projection="equirectangular",
                 width=2048, height=1024, texture=True)
write_raster_map(out / "preview.ppm", world, max_cells=1500, texture=False)

# Hand-rolled GeoJSON point layer over an arbitrary numeric cell field.
def cells_to_geojson(world, field, *, land_only=True):
    features = []
    for cell in world.get("cells", []):
        if land_only and cell.get("is_water", False):
            continue
        value = cell.get(field)
        if value is None:
            continue
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(cell.get("lon_deg", 0.0)),
                                float(cell.get("lat_deg", 0.0))],
            },
            "properties": {
                "id": int(cell.get("id", -1)),
                field: value,
                "biome": cell.get("biome"),
                "landform": cell.get("landform"),
            },
        })
    return {"type": "FeatureCollection", "features": features}

write_json(out / "elevation.geojson", cells_to_geojson(world, "elevation_m"))
write_json(out / "aquifers.geojson", cells_to_geojson(world, "aquifer_productivity_index"))

# Subset export: only the layers a downstream consumer needs.
slim = {
    "schema_version": world["schema_version"],
    "name": world["name"],
    "planet_parameters": world["planet_parameters"],
    "summary": world["summary"],
    "watersheds": world.get("watersheds", []),
    "river_graph": world.get("river_graph", {}),
    "watershed_graph": world.get("watershed_graph", {}),
}
write_world(out / "slim.mgeo", slim)      # schema_version is required by the .mgeo header
```

`write_world` requires an integer `schema_version` in any payload it packs (`_world_schema`, `src/magic_geo/serialization.py:59`), which is why the slim subset carries it forward. `write_json` sorts keys, so its output is diff-friendly but not in native emission order. `write_raster_map` always writes PPM bytes; give it a `.ppm` name to avoid confusing downstream tooling.

---

## Limitations and unresolved claims

These are properties of the system as implemented, carried forward from the source rather than softened.

- **Physical time is not resolved anywhere in the natural pipeline.** `enrich_world_with_geo_evolution_provenance` records `physical_time_resolved: False` and `nominal_time_calibrated: False` for every history family it registers (`src/magic_geo/geo_evolution_provenance.py:85`, `:107`, `:130`), and its own contract checks assert those values must be false (`:175`, `:179`, `:259`). The nominal time basis is `configured_maturation_timestep_ma_per_erosion_transition_v1`, sourced from `erosion.maturation_timestep_ma` (`:19`, `:21`) — a configuration parameter, not a calibrated geologic rate. Do not report ages, rates, or durations from a magic-geo world as physical values.
- **"History" is two different things.** The provenance registry deliberately separates `native_state_mutation_ledger` families (`plate_motion_history`, `earth_system_feedback_history`, `hydrologic_water_budget_history`, `numeric_depression_correction_history`, `hillslope_sediment_transport_history`, `fluvial_sediment_routing_history`, `glacial_sediment_transport_history` — `src/magic_geo/geo_evolution_provenance.py:25`) from `posthoc_diagnostic_trajectory` families (`climate_seasonal_histories`, `lake_overflow_histories`, `sediment_routing_histories`, `ice_sheet_histories`, `soil_profile_histories`, `wildfire_spread_histories`, and the rest at `:46`). Only the first group records state mutations the native pipeline actually performed, and even there `numeric_depression_correction_history` is marked `"mixed"` rather than `"yes"` (`:36`). The `step_count`/`route_limit`/`flowline_limit` parameters documented above tune the *second* group only. The registry covers those 20 families and no others: `crust_material_shadow_history` and `crust_dry_rock_accounting_history` are emitted by the native layer without a registry entry, so their temporal status must be read from `crust_material_shadow_model` and `crust_dry_rock_accounting_model`.
- **Accelerator parity is not demonstrated and accelerated crust overlap is not authoritative.** The `backend` object reports `crust_overlap_continuous_shadow_only: true`, `crust_overlap_continuous_shadow_authoritative: false`, `crust_overlap_accelerator_complete_parity_demonstrated: false`, and `crust_overlap_accelerator_state_authoritative: false` (`cpp/src/opencl_compute.cpp:2130`, `:2136`, `:2166`, `:2172`). `crust_transport_execution_backend` and the two `crust_overlap_*_authoritative_backend` keys are hard-coded `"cpu"`. `backend_scope` is `"accelerated_native_kernels_not_end_to_end_pipeline"` — accelerators cover kernels, not the pipeline. Treat backend changes as potentially result-changing.
- **Subduction polarity and mass provenance are explicitly unresolved in the ledgers.** The candidate-fate ledger separates `physical_polarity_backed_candidate_excess_area_km2` from `oceanic_heuristic_candidate_excess_area_km2` and `unresolved_candidate_excess_area_km2`, and the boundary-segment records carry `polarity_candidate_status` alongside `physical_polarity_status`; the dry-rock ledger carries `physical_basis_resolved` and `physical_source_sink_resolved` flags on proxy transfers and reason transactions. The Python API surfaces these arrays verbatim — it does not resolve them. Do not read a subduction direction or a mass origin out of a magic-geo world as settled.
- **Realism checks are internal plausibility scores, not validation against Earth data.** `geology_realism_checks`, `climate_realism_checks`, `hydrology_realism_checks`, `biome_realism_checks`, `planet_realism_checks`, and `worldbuilding_realism_checks` score the generated world against pattern expectations encoded in the same codebase. They are self-consistency diagnostics. Calibration against real-earth data is a separate concern — see [Calibration Against Real-Earth Data](./14-calibration.md).
- **Many "model" keys are declarations, not computations.** `settlement_selection_model`, `political_region_model`, `culture_region_model`, `historical_event_model`, `territorial_snapshot_model`, and their siblings publish the algorithm contract, parameters, and stated limitations of native products; they do not recompute those products. Reading them tells you what the generator claims to have done, not an independent verification of it.
- **The geo-only strip is a Python-layer concern.** At the C++ layer there is no shape difference between full and geo-only serialization: `simulate_geo_world` runs the same `serialize_world`, and the society arrays are simply empty. If you call `magic_geo.native.generate_geo_world` directly you get all 57 top-level keys including empty `settlements`/`routes`/etc., and no `generation_scope`. Only `magic_geo.api.generate_geo_world` performs the strip (`src/magic_geo/api.py:304`).
- **Out-of-order enricher invocation fails silently.** Every enricher reads upstream fields with `.get(field, default)`. Calling one before its dependencies produces a fully populated but meaningless layer rather than an exception. The ordered table above is the only enforcement mechanism.
- **Observed document counts are not a schema contract.** The 191/113 top-level, 419/388 per-cell, and 1293/974 summary key counts in this page came from one 128-cell `smoke` run. Enrichers publish some keys conditionally, so a different configuration can produce different counts. The stable contract is the native 57 top-level keys plus `schema_version == 2`.
- **`DEFAULT_MAX_WORLD_FILE_BYTES` bounds encoded input, not memory.** The 2 GiB ceiling applies to the file on disk; the decoded Python graph is substantially larger, and the source comment says so explicitly (`src/magic_geo/serialization.py:37`).
- **`write_cells_csv` has a frozen column set.** New per-cell fields added by future enrichers will not appear until the `fieldnames` list is updated, and dropped fields will appear as empty columns. Use the world dict, not the CSV, when you need completeness.
- **`write_raster_map` writes PPM regardless of filename.** There is no PNG encoder in the writer; the header is always `P6` with the `magic-geo raster-terrain-v1` comment (`src/magic_geo/io/raster_map.py:275`).

---

## See also

- [Project Overview](./01-overview.md)
- [Installation and Build](./02-installation-and-build.md)
- [Quickstart](./03-quickstart.md)
- [Architecture](./04-architecture.md)
- [Configuration Reference](./05-configuration-reference.md)
- [CLI Reference](./06-cli-reference.md)
- [Native Engine (C++ Core)](./08-native-engine.md)
- [Compute Backends (CPU, OpenCL, CUDA)](./09-compute-backends.md)
- [World Document Schema](./10-world-schema.md)
- [Serialization and World Formats](./11-serialization.md)
- [Validation](./12-validation.md)
- [Geo Validation Suite](./13-geo-validation-suite.md)
- [Calibration Against Real-Earth Data](./14-calibration.md)
- [Web Workbench](./15-web-workbench.md)
- [Debug Exports and Visualization](./16-debug-and-visualization.md)
- [Rendering and Map Output](./17-rendering.md)
- [Testing and Quality Gates](./18-testing.md)
- [Docker Deployment](./19-docker-deployment.md)
- [Example Seeds and Presets](./20-seed-gallery.md)
- [Glossary](./21-glossary.md)
- [Troubleshooting and FAQ](./22-troubleshooting.md)
