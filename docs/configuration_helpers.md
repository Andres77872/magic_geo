# YAML configuration creation and helper API

This guide covers the supported ways to create, inspect, validate, override,
serialize, and save generation configuration. For the physical meaning and
range of every property, use the [complete configuration reference](configuration_reference.md).

`magic_geo.WorldConfig()` and every built-in profile create version-2
configurations for the prescribed seasonal energy model. Every YAML document
must explicitly contain the exact integer `config_version: 2`; empty or
unversioned files receive migration errors. Nested fields use strict types.

For a small version-2 example, use `configs/seasonal_smoke.yaml`. In Python,
construct `SeasonalWorldConfig(config_version=2, ...)` and use the ordinary
generation API. Version-2 climate uses `reference_infrared_optical_depth`; old
mean-temperature/lapse controls produce located migration errors, including
in dotted overrides. See the [seasonal configuration reference](configuration_reference.md#explicit-seasonal-configuration-version-2).

The workbench schema reference, profiles, templates, `/render`, validation,
saving and generation jobs all use version 2. Its reference describes optical
depth and preserves numeric bounds. Existing editor text is retained when
loading fails or the schema and template versions disagree.

## Built-in profiles

Profiles are explicit starting points; they are not hidden defaults applied by
the loader.

| Profile | Purpose | Important differences |
|---|---|---|
| `default` | Neutral editable schema defaults | Exact `WorldConfig()` values; 4,096 cells, automatic compute, precipitation scale `1.0`, plate-motion scale `2.0`. |
| `earthlike` | Earth reference inputs; seasonal climate calibration not established | Plate-motion scale `4.0` and precipitation scale `0.8`; otherwise schema defaults. This exactly matches `configs/earthlike_seed.yaml`. |
| `smoke` | Fast integration/debug run | Earth-like forcing (`4.0` plate-motion and `0.8` precipitation scales), 128 cells, 8 plates, one erosion iteration, one CPU thread, deterministic CPU backend. |

The minimal valid YAML document is `config_version: 2`, which receives the
neutral `default` values for omitted sections. A profile is materialized as a complete YAML file,
so generated artifacts remain reproducible without depending on future profile
definitions.

List profile names in Python with `list_config_profiles()` or in the browser
with `GET /api/config/profiles`.

## CLI creation

The no-argument command writes `magic-geo.yaml` and never overwrites it. That is
also the default input for `magic-geo generate`, so the installed/source workflow
does not depend on a checkout-only `configs/` path:

```bash
magic-geo init-config
magic-geo generate --output runs/world.json
```

Select another profile or target:

```bash
magic-geo init-config --profile default --output configs/neutral.yaml
magic-geo init-config --profile smoke --output runs/configs/smoke.yaml
```

`--set` accepts a dotted field path and a YAML value. Repeat it as needed:

```bash
magic-geo init-config \
  --profile earthlike \
  --set run.name='large ocean world' \
  --set mesh.cell_count=8192 \
  --set planet.ocean_water_inventory_km3=1800000000 \
  --set compute.backend=cuda \
  --set output.include_cells=true \
  --output runs/configs/ocean.yaml
```

Values retain YAML types: `false` is a boolean, `128` is an integer, and
`[a, b]` is a list. The full model is revalidated after all overrides, so
cross-field constraints such as `tectonics.plate_count < mesh.cell_count` still
apply. Unknown paths, duplicate `--set` paths, invalid values, and unknown
profiles exit with status 2 and a readable field path.

Use `--force` only when replacement is intentional. Writes use a temporary file,
validate its serialized contents, then atomically replace the target.

## Python helpers

The stable helper subset is importable from `magic_geo`:

```python
from pathlib import Path

from magic_geo import (
    ConfigError,
    apply_config_overrides,
    config_schema,
    create_config,
    dump_config_yaml,
    list_config_profiles,
    load_config,
    parse_config_overrides,
    parse_config_yaml,
    write_config,
)
```

### Create and override

```python
config = create_config(
    "earthlike",
    {
        "run.name": "temperate_demo",
        "mesh.cell_count": 1024,
        "compute.backend": "cpu",
    },
)

# Returns a new validated model; `config` is unchanged.
variant = apply_config_overrides(
    config,
    {"planet.axial_tilt_deg": 40.0},
    source="experiment overrides",
)
```

`parse_config_overrides()` is useful when an application accepts the same
`field=value` notation as the CLI:

```python
overrides = parse_config_overrides([
    "mesh.cell_count=512",
    "hydrology.preserve_geologic_depressions=false",
])
config = create_config("smoke", overrides)
```

Override operations deep-copy caller values and never mutate the source model or
mapping.

### Parse and load

```python
config = parse_config_yaml(
    """
    config_version: 2
    mesh:
      cell_count: 512
    tectonics:
      plate_count: 12
    """,
    source="request body",
)

config = load_config(Path("runs/configs/world.yaml"))
```

Both paths reject:

- malformed or multi-document YAML;
- duplicate mapping keys (plain `yaml.safe_load` silently keeps the last one);
- a non-mapping document root;
- missing or unsupported document versions, including `"2"`, `2.0` and booleans;
- unknown sections or properties;
- non-finite numbers and values outside declared ranges;
- invalid cross-field combinations.

Missing sections and fields receive schema defaults after the explicit version
is checked. Numeric strings and boolean numeric controls are rejected. An
integer is accepted for a float field; a float is not accepted for an integer
field. Generated templates emit canonical values. `LegacyWorldConfig` is an
explicit Python compatibility type for old-model/ABI callers; YAML loading and
profile creation never select it.

### Errors

All helper-level YAML construction, parse, and model-validation failures are
`ConfigError`, a `ValueError` subclass. Its string includes the source and, for
YAML syntax errors, one-based line and column. `to_dict()` is safe to return from
JSON APIs:

```python
try:
    parse_config_yaml("run:\n  seed: 1\n  seed: 2\n", source="world.yaml")
except ConfigError as error:
    print(error)
    payload = error.to_dict()
    # {
    #   "message": "invalid YAML: found duplicate key 'seed'",
    #   "source": "world.yaml",
    #   "line": 3,
    #   "column": 3,
    #   "issues": []
    # }
```

Pydantic failures add an `issues` entry per field with `path`, `location`,
`message`, and `type`.

`load_config()` deliberately preserves the original read/decode exception
contract from `Path.read_text`: missing/unreadable files raise the corresponding
`OSError` subclass (for example `FileNotFoundError`) and invalid UTF-8 raises
`UnicodeDecodeError`, while successfully decoded content that fails YAML/model
validation raises `ConfigError`.

### Stable YAML and atomic writes

```python
text = dump_config_yaml(config)
write_config(Path("runs/configs/world.yaml"), config)
write_config(Path("runs/configs/world.yaml"), variant, force=True)
```

`dump_config_yaml()` preserves schema section/field order, emits block YAML, and
ends with a newline. Formatting normalizes the file and does not preserve input
comments. `write_config()` creates parent directories, refuses existing targets
unless `force=True`, validates the normalized temporary file, and commits it
with atomic same-directory publication (readers see either the old or complete
new file). It does not promise power-loss durability because it does not fsync
the file and parent directory.

Use `create_config("earthlike")` with `dump_config_yaml()` when an in-memory
Earth-like template is needed. Use `write_config()` or CLI `init-config` to
publish it atomically.

### JSON Schema

```python
schema = config_schema()
```

The result is standard Pydantic JSON Schema plus `x-magic-geo` metadata:

- all nine section descriptions;
- descriptions, types, defaults, enums, and bounds for all 44 fields;
- stable `section_order` and schema version `2` (`urn:magic-geo:schema:world-config:v2`);
- the name, description, and complete values of each built-in profile.

This is what drives the browser field reference. Applications should follow
`$ref` entries in `$defs` rather than assuming nested schemas are inlined.

## Generation helpers

The public generation API accepts validated models:

```python
from magic_geo.api import generate_geo_world, generate_world

world = generate_world(create_config("earthlike"))
natural_world = generate_geo_world(create_config("smoke"))
```

File companions load the same strict YAML first:

```python
from magic_geo.api import generate_from_file, generate_geo_from_file

world = generate_from_file(Path("runs/configs/world.yaml"))
natural_world = generate_geo_from_file(Path("runs/configs/smoke.yaml"))
```

## Browser editor and HTTP API

Start the cache-optional local workbench:

```bash
pip install -e '.[debug]'
magic-geo serve
```

The **Config** view provides profile reset, a raw YAML editor, inline schema
documentation, validation, local download, and workspace save. Saving is
restricted to `<workspace>/configs/`; the endpoint never accepts an arbitrary
host path.

The configured workspace also rebases conventional output defaults shown by
the Operations view. For example, automatic browser-cache preparation and the
browser `export-debug` form use `<workspace>/debug` (`runs/debug` by default).
That browser rule is distinct from CLI `export-debug` with no `--output`, which
uses `<world parent>/debug`. The Generate and geo-suite forms default to the
Config view's conventional `<workspace>/configs/world.yaml` save path.

| Endpoint | Purpose |
|---|---|
| `GET /api/config/schema` | Full described JSON Schema and profile metadata. |
| `GET /api/config/profiles` | Profile names/descriptions and UI default. |
| `GET /api/config/template?profile=earthlike` | Complete normalized YAML plus parsed values. |
| `POST /api/config/render` | Apply typed dotted overrides to a profile and return YAML. |
| `POST /api/config/validate` | Parse/validate submitted YAML; return normalized YAML and values. |
| `POST /api/config/save` | Validate and atomically save below the configured workspace; existing names require explicit `force: true`. |

Example validation request:

```bash
curl -X POST http://127.0.0.1:8642/api/config/validate \
  -H 'Content-Type: application/json' \
  -d '{"yaml":"mesh:\n  cell_count: 128\ntectonics:\n  plate_count: 8\n"}'
```

The YAML string is limited to 1,000,000 UTF-8 bytes and to bounded nesting,
event, and alias counts. Exceeding the byte limit uses HTTP 413 with a plain
string `detail`; other YAML/config failures use HTTP 422 with the structured
Python `ConfigError` under `detail`; malformed JSON or an invalid request
envelope uses FastAPI's standard validation-detail list. Saving an existing name
without confirmation uses HTTP 409. The complete live contract is at `/api/docs`
and `/api/openapi.json`.

These endpoints belong to a trusted-local, single-user workbench. They enforce
workspace/path and request-shape limits but provide no login, authorization,
per-user isolation, or TLS. Keep the default loopback binding unless a trusted
network boundary and authenticating proxy protect the server.

## Reproducibility checklist

For a reusable run:

1. Materialize a complete profile and save it beside the artifacts.
2. Give the run a stable `run.name` and `run.seed`.
3. Record the selected compute backend and thread count; thread-count
   invariance is not currently guaranteed.
4. Keep `output.include_cells: true` when using the debugger or geo-only API.
5. Validate after every override and retain the normalized YAML.
6. Treat a later profile revision as a new input; never rely on a profile name
   alone as generation provenance.
