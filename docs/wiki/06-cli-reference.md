# CLI Reference

[Wiki home](./README.md) > CLI Reference

`magic-geo` exposes fifteen subcommands built on a single Typer application (`src/magic_geo/cli/_app.py:13`). Every parameter in the CLI is an *option* — there are no positional arguments anywhere, and no global flags beyond Typer's built-in `--install-completion`, `--show-completion`, and `--help`. This page enumerates each subcommand's synopsis, complete option table, exact artifacts, exit-code semantics, and worked examples, then chains them into end-to-end recipes. Numbers, defaults, and paths below were read out of `src/magic_geo/cli/` and confirmed by running the CLI in this checkout.

## On this page

- [Global usage](#global-usage)
- [Command index](#command-index)
- [Shared conventions](#shared-conventions)
- [init-config](#init-config)
- [backend](#backend)
- [generate](#generate)
- [validate-geo](#validate-geo)
- [validate-geo-suite](#validate-geo-suite)
- [validate](#validate)
- [calibrate](#calibrate)
- [calibrate-ensemble](#calibrate-ensemble)
- [derive-targets](#derive-targets)
- [render](#render)
- [render-raster](#render-raster)
- [export-debug-map](#export-debug-map)
- [export-debug](#export-debug)
- [export-rerun](#export-rerun)
- [serve](#serve)
- [Recipes](#recipes)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

---

## Global usage

```text
Usage: magic-geo [OPTIONS] COMMAND [ARGS]...

  Causal planet generator CLI.
```

Two equivalent entry points exist:

| Invocation | Source |
|---|---|
| `magic-geo …` | console script `magic-geo = "magic_geo.cli:main"` (`pyproject.toml:31`), which calls `main()` → `app()` (`src/magic_geo/cli/__init__.py:22`) |
| `python -m magic_geo …` | `src/magic_geo/__main__.py` re-exports the same `main` |

The Typer app is created with `no_args_is_help=True` (`src/magic_geo/cli/_app.py:13`). There is **no `@app.callback`**, so the only application-level options are the ones Typer injects:

| Flag | Type | Default | Description |
|---|---|---|---|
| `--install-completion` | flag | off | Install completion for the current shell. |
| `--show-completion` | flag | off | Show completion for the current shell, to copy it or customize the installation. |
| `--help` | flag | off | Show help for the app or for a subcommand and exit `0`. |

Running `magic-geo` with no subcommand prints the command list and exits with status `2` (verified by invocation).

---

## Command index

The order below is the order `magic-geo --help` prints, which is fixed by the module import order in `src/magic_geo/cli/commands/__init__.py:8-15` (`config, generate, validate_geo, validate, calibrate, render, export, serve`).

| Command | One-line purpose | Primary output |
|---|---|---|
| `init-config` | Create a validated, editable YAML configuration. | YAML config file at `--output` (default `magic-geo.yaml`) |
| `backend` | Print native backend and OpenCL probe information. | JSON on stdout; no file |
| `generate` | Generate a planet from YAML config. | World `.json` or `.mgeo` at `--output` (default `runs/world.json`) |
| `validate-geo` | Validate only natural geography, conservation, and selected realism gates. | `OK`/`FAIL` line; optional JSON report at `--output` |
| `validate-geo-suite` | Run geo-only replays, diverse response gates, and configured empirical fit. | Suite JSON at `--output` (default `runs/geo_validation.json`) |
| `validate` | Run the full world-consistency gate on a generated world file. | `OK` on stdout or `FAIL …` lines on stderr; no file |
| `calibrate` | Compare a generated world against external dataset-derived calibration ranges. | Calibration JSON at `--output` (default `runs/calibration.json`) |
| `calibrate-ensemble` | Generate and evaluate an explicit seed/resolution calibration matrix. | Ensemble JSON at `--output` (default `runs/calibration_ensemble.json`) |
| `derive-targets` | Derive target ranges from supported local raster, vector, and archive sources. | Targets JSON at `--output` (default `runs/calibration_targets.json`) |
| `render` | Render a generated world file as a layer-driven SVG map. | SVG at `--output` (default `runs/world.svg`) |
| `render-raster` | Render a generated world file as a dependency-free PPM raster map. | Binary P6 PPM at `--output` (default `runs/world.ppm`) |
| `export-debug-map` | Export a debug layer PNG and matching GPT Image prompt without a browser. | `<base>.png` and `<base>.gpt-image-prompt.md` |
| `export-debug` | Export a columnar debug cache (Parquet/JSONL/mesh/VTU) for the web workbench. | Cache directory with `manifest.json`, `tables/`, `events/`, `mesh/`, `vtu/` |
| `export-rerun` | Export a Rerun (`.rrd`) recording with stage-scrubbable mesh and feedback ledgers. | `.rrd` recording (default `<world dir>/world.rrd`) |
| `serve` | Serve the browser workbench; an existing debug cache is optional. | Long-running HTTP server; browser writes into `<workspace>` |

Command definitions live in eight modules:

| Module | Commands defined |
|---|---|
| `src/magic_geo/cli/commands/config.py` | `init-config` (`:16`), `backend` (`:52`) |
| `src/magic_geo/cli/commands/generate.py` | `generate` (`:18`) |
| `src/magic_geo/cli/commands/validate_geo.py` | `validate-geo` (`:23`), `validate-geo-suite` (`:91`) |
| `src/magic_geo/cli/commands/validate.py` | `validate` (`:91`) |
| `src/magic_geo/cli/commands/calibrate.py` | `calibrate` (`:32`), `calibrate-ensemble` (`:94`), `derive-targets` (`:202`) |
| `src/magic_geo/cli/commands/render.py` | `render` (`:14`), `render-raster` (`:60`) |
| `src/magic_geo/cli/commands/export.py` | `export-debug-map` (`:13`), `export-debug` (`:164`), `export-rerun` (`:208`) |
| `src/magic_geo/cli/commands/serve.py` | `serve` (`:13`) |

---

## Shared conventions

### World format autodetection by suffix

`generate` writes through `write_world(..., format=world_format, validate_model=False)` (`src/magic_geo/cli/commands/generate.py:78`). On **write**, `format="auto"` picks the binary MessagePack `.mgeo` container when the output suffix is in `MGEO_SUFFIXES` and JSON otherwise (`src/magic_geo/serialization.py:532`, `:543-544`):

| Constant | Value | Source |
|---|---|---|
| `MGEO_SUFFIXES` | `{".mgeo", ".mgpack", ".msgpack", ".mpk"}` | `src/magic_geo/serialization.py:35` |
| `MGEO_MAGIC` | `b"MGEO\r\n\x1a\n"` | `src/magic_geo/serialization.py:28` |
| `CURRENT_WORLD_SCHEMA_VERSION` | `2` | `src/magic_geo/serialization.py:27` |
| `DEFAULT_MAX_WORLD_FILE_BYTES` | `2 * 1024**3` (2 GiB) | `src/magic_geo/serialization.py:39` |

On **read**, `format="auto"` sniffs the leading magic bytes rather than the suffix (`src/magic_geo/serialization.py:557`, `:576-578`), so a `.mgeo` payload stored under a `.json` name still loads. A file over `DEFAULT_MAX_WORLD_FILE_BYTES` raises `WorldSerializationError` before decoding.

Every world-consuming command routes through the shared loader `_load_world_for_cli` (`src/magic_geo/cli/_app.py:16-23`), which uses strict JSON-model validation because CLI paths are user-selected. On `OSError | UnicodeError | ValueError` it prints `Invalid world file: <exc>` to stderr and exits `2`. The commands that use it are `validate`, `validate-geo`, `calibrate`, `render`, `render-raster`, `export-debug`, and `export-rerun`. `export-debug-map` reads a debug cache, not a world, and does not use this loader.

### Default config discovery

`magic-geo.yaml` in the current working directory is the shared default for both ends of the config lifecycle:

| Command | Flag | Default |
|---|---|---|
| `init-config` | `--output` | `magic-geo.yaml` |
| `generate` | `--config` | `magic-geo.yaml` (with `exists=True`) |

So `magic-geo init-config` followed by `magic-geo generate --output runs/world.json` works with no config path at all. `validate-geo-suite` instead defaults to the repo-relative `configs/earthlike_seed.yaml` and `configs/geo_validation_matrix.yaml`; `calibrate-ensemble` has **no** config default and requires `--config`.

### Default output rooting under `runs/`

Almost every writing command defaults into `runs/`:

| Command | Flag | Default path |
|---|---|---|
| `generate` | `--output` | `runs/world.json` |
| `render` | `--output` | `runs/world.svg` |
| `render-raster` | `--output` | `runs/world.ppm` |
| `validate-geo-suite` | `--output` | `runs/geo_validation.json` |
| `calibrate` | `--output` | `runs/calibration.json` |
| `calibrate-ensemble` | `--output` | `runs/calibration_ensemble.json` |
| `derive-targets` | `--output` | `runs/calibration_targets.json` |
| `export-debug-map` | `--debug-dir` | `runs/debug` |
| `export-debug-map` | `--output` | `runs/<generated basename>` (`src/magic_geo/debug_map_export.py:1433`) |
| `serve` | `--workspace` | `runs` |

Three defaults are derived from the world file instead of `runs/`:

| Command | Flag omitted | Derived default | Source |
|---|---|---|---|
| `export-debug` | `--output` | `<world dir>/debug` | `src/magic_geo/cli/commands/export.py:187` |
| `export-rerun` | `--output` | `<world dir>/world.rrd` | `src/magic_geo/cli/commands/export.py:223` |
| `serve` | `--debug-dir` | `<workspace>/debug`, only if `<workspace>/debug/manifest.json` is a file | `src/magic_geo/cli/commands/serve.py:64-69` |

This is a deliberate asymmetry the README calls out explicitly: the browser workbench's `export-debug` default is `<workspace>/debug` (`runs/debug`), while the CLI `export-debug` default is `<world parent>/debug`.

### Workspace rooting

`serve` resolves `--workspace` relative to `Path.cwd()` and requires the result to stay inside it (`src/magic_geo/cli/commands/serve.py:50-63`). An escaping path prints `Web workspace must stay inside <cwd>: <workspace>` and exits `2` (verified). Browser-created artifacts are confined to that workspace: configs go to `<workspace>/configs` (`src/magic_geo/debug_server.py:1020`), and the prepared/browser cache goes to `<workspace>/debug` (`src/magic_geo/web_jobs.py:1252`).

### Environment variables

Only `serve` declares `envvar=`. Typer precedence applies: explicit flag beats environment variable, environment variable beats default.

| Env var | Backs flag | Default if unset | Source |
|---|---|---|---|
| `MAGIC_GEO_WORKSPACE` | `serve --workspace` | `runs` | `src/magic_geo/cli/commands/serve.py:30` |
| `MAGIC_GEO_HOST` | `serve --host` | `127.0.0.1` | `src/magic_geo/cli/commands/serve.py:36` |
| `MAGIC_GEO_PORT` | `serve --port` | `8642` | `src/magic_geo/cli/commands/serve.py:42` |

Two further variables affect CLI behavior but back **no** flag:

| Env var | Effect | Source |
|---|---|---|
| `MAGIC_GEO_NATIVE_LIBRARY` | Overrides the `ctypes` shared-library path; raises `RuntimeError` if it does not name a file. Visible indirectly through `magic-geo backend`. | `src/magic_geo/native.py:111-118` |
| `PYTHONUNBUFFERED` | Set (not read) to `"1"` on subprocesses the `serve` workbench spawns. | `src/magic_geo/web_jobs.py:1187` |

`.env.example` is Docker-oriented. It additionally documents
`MAGIC_GEO_WORLDS_DIR`, `MAGIC_GEO_CONTAINER_WORKSPACE`,
`MAGIC_GEO_PUBLISH_HOST`, `MAGIC_GEO_PYTHON_VERSION`,
`MAGIC_GEO_APP_UID`, `MAGIC_GEO_APP_GID`, and
`MAGIC_GEO_ENABLE_CUDA`; those are consumed by Docker Compose or the image
build, not directly by the Python CLI. Compose maps
`MAGIC_GEO_CONTAINER_WORKSPACE` to the process-facing
`MAGIC_GEO_WORKSPACE`.

### Exit-code semantics shared by every command

| Code | Meaning |
|---|---|
| `0` | Success. Also the code for `--help`. |
| `1` | Semantic failure *after* the command's own work completed — a failed validation gate or a failed calibration policy. Only `validate`, `validate-geo`, `validate-geo-suite`, `calibrate`, and `calibrate-ensemble` ever return `1`. |
| `2` | Usage error (missing required option, unknown option, `exists=True` path missing, `file_okay=False` violated, `IntRange`/`FloatRange` out of bounds), a `typer.BadParameter`, an unloadable world, an unloadable config, a missing optional dependency, or an invalid enum-like string value hand-checked inside the command. Also the code for a bare `magic-geo` invocation. |

Reports are written **before** a policy-driven nonzero exit in `calibrate` and `calibrate-ensemble` (`src/magic_geo/cli/commands/calibrate.py:71` and `:178` precede the exit branches), so a failing policy still leaves the machine-readable evidence on disk.

### Optional dependency groups

| Extra | Packages | Commands that need it |
|---|---|---|
| `debug` | `pyarrow>=19`, `duckdb>=1.2`, `fastapi>=0.115`, `uvicorn[standard]>=0.34` (`pyproject.toml:18-24`) | `export-debug`, `export-debug-map`, `serve` |
| — (`rerun-sdk`, not declared in any extra) | `rerun-sdk` | `export-rerun` |
| `test` | `pytest>=9,<10`, `pytest-cov>=7` | test suite only |

Each of those four commands — `export-debug-map`, `export-debug`, `export-rerun`, and `serve` — imports its heavy module lazily inside the function body and converts `ImportError` into an actionable message plus exit `2`.

---

## init-config

### Synopsis

```bash
magic-geo init-config [--output PATH] [--profile NAME] [--set section.field=YAML]... [--force]
```

### Description

Creates a validated, editable YAML configuration from one of three built-in profiles, optionally with typed dotted-path overrides. Defined at `src/magic_geo/cli/commands/config.py:16-49`; it calls `create_config(profile, parse_config_overrides(overrides or ()))` (`src/magic_geo/config.py:754`, `:665`) and then `write_config` (`src/magic_geo/config.py:800`).

### Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--output`, `-o` | `Path` | `magic-geo.yaml` | New YAML config path. |
| `--profile`, `-p` | `str` (`default`, `earthlike`, `smoke`) | `earthlike` | Built-in starting profile: default, earthlike, or smoke. |
| `--set` | `str`, repeatable | none | Override `section.field=YAML_VALUE`; repeat for multiple fields. |
| `--force` | flag (no `--no-force`) | `False` | Overwrite the target file. |

Profiles are defined at `src/magic_geo/config.py:507` (descriptions) and `:513` (overrides):

| Profile | Description | Deltas versus schema defaults |
|---|---|---|
| `default` | Schema defaults suitable as a neutral editable starting point. | none |
| `earthlike` | Calibrated 4,096-cell Earth-like reference configuration. | `tectonics.plate_motion_scale_deg_per_step` 2.0 → 4.0; `climate.precipitation_scale` 1.0 → 0.8 |
| `smoke` | Small deterministic CPU configuration for fast integration checks. | `run.name` → `smoke`; `mesh.cell_count` 4096 → 128; `tectonics.plate_count` 14 → 8; `tectonics.plate_motion_scale_deg_per_step` → 4.0; `climate.precipitation_scale` → 0.8; `erosion.iterations` 6 → 1; `compute.backend` → `cpu`; `compute.threads` → 1 |

`--set` values are parsed with `yaml.safe_load`, so `false` becomes a bool, `1024` an int, `0.8` a float, and `geodesic_icosahedron` a string. `apply_config_overrides` requires at least two non-empty dotted parts and refuses any path whose leaf is a mapping (`src/magic_geo/config.py:726-748`), so replacing a whole section is rejected. The schema is two levels deep — nine sections holding 44 leaf fields, none of them nested — so in practice every valid path is exactly `section.field`.

### Artifacts written

| Path | Content |
|---|---|
| `--output` | The dumped config, section order preserved, `sort_keys=False`, no anchors/aliases (`dump_config_yaml`, `src/magic_geo/config.py:653`). All 44 leaf fields are always written out. |
| `.{name}.{uuid4hex}.tmp` in the same directory | Transient. `write_config` writes the temp file, re-parses the exact bytes it is about to publish, then commits with `os.replace` (`--force`) or `os.link` (no `--force`), and unlinks the temp on every path. |

Without `--force`, publication uses a same-directory hard link, so a concurrent writer that created the target after the initial existence check causes `FileExistsError` rather than a silent clobber.

### Exit codes

| Code | Trigger |
|---|---|
| `0` | Config written. Prints `Wrote <output> \| profile=<profile>`. |
| `2` | `ConfigError` (unknown profile, malformed `--set`, duplicate override path, validation failure) or `OSError` including `FileExistsError` when the target exists without `--force`; both are re-raised as `typer.BadParameter` (`src/magic_geo/cli/commands/config.py:47-48`). |

This command never exits `1`.

### Examples

Create the default Earth-like config in the working directory, then generate from it with no `--config` flag:

```bash
magic-geo init-config
magic-geo generate --output runs/world.json
```

Create a fast smoke config and a tuned custom config with typed overrides:

```bash
magic-geo init-config --profile smoke --output runs/configs/smoke.yaml

magic-geo init-config --profile earthlike \
  --set mesh.cell_count=1024 \
  --set hydrology.preserve_geologic_depressions=false \
  --output runs/configs/custom.yaml
```

Overwrite an existing file deliberately:

```bash
magic-geo init-config --profile default --output configs/neutral.yaml --force
```

Observed failure shape for an unknown profile (exit `2`):

```text
Invalid value: <profile>: unknown configuration profile 'bogus'; choose one of: default, earthlike, smoke
```

---

## backend

### Synopsis

```bash
magic-geo backend
```

### Description

Prints `json.dumps(backend_info(), indent=2, sort_keys=True)` (`src/magic_geo/cli/commands/config.py:52-55`). `backend_info()` forwards to the native `magic_geo_backend_info_json` entry point through `ctypes` (`src/magic_geo/native.py:344-346`), so a successful run is also a proof that the shared library loads.

### Options

| Flag | Type | Default | Description |
|---|---|---|---|
| — | — | — | This command takes no options other than `--help`. |

### Artifacts written

None. Output goes to stdout only. Redirect it if you need a file:

```bash
magic-geo backend > runs/backend.json
```

### Output shape

A single flat JSON object. In this checkout it carried **178** keys, grouped by prefix: `cuda_*` (69), `opencl_*` (58), `crust_*` (36), `backend_*` (5), `openmp_*` (2), plus `native_core`, `requested_backend`, `selected_backend`, `active_backend`, `initial_selected_backend`, `cpu_conservative_crust_overlap_transition_count`, `automatic_planning_cell_count`, and `accelerator_kernel_dispatch_count`. Representative fields:

| Key | Observed value here | Meaning |
|---|---|---|
| `native_core` | `"c++20"` | Native core language level. |
| `active_backend` / `selected_backend` / `requested_backend` | `"cpu"` | Backend state for a capability-only probe. |
| `backend_scope` | `"accelerated_native_kernels_not_end_to_end_pipeline"` | Explicitly scopes what "accelerated" means. |
| `backend_selection_reason` | `"capability-only probe; no generation is active"` | Why the reported backend was chosen. |
| `cuda_auto_min_cell_count` / `cuda_sm_120_auto_min_cell_count` | `8192` | Native `sm_120` CUDA automatic-offload threshold. |
| `cuda_uncalibrated_auto_min_cell_count` | `32768` | Uncalibrated CUDA automatic-offload threshold. |
| `opencl_auto_min_cell_count` | `32768` | OpenCL automatic-offload threshold. |
| `crust_transport_execution_backend` | `"cpu"` | Authoritative forward overlap transport runs on CPU. |
| `crust_overlap_continuous_shadow_authoritative` | `false` | The accelerator shadow is never authoritative. |
| `crust_overlap_accelerator_complete_parity_demonstrated` | `false` | Complete accelerator parity is explicitly **not** demonstrated. |
| `crust_overlap_continuous_shadow_validation_status` | `"not_run_no_conservative_transition"` | No shadow validation ran during a probe. |
| `openmp_enabled` / `openmp_max_threads` | `true` / `16` | OpenMP availability on this host. |

Treat every `*_parity_demonstrated`, `*_authoritative`, and `*_result_used_for_state` flag as load-bearing: they are how the engine states that geometry, coverage, membership classes, categories, and production state remain CPU-authoritative and that complete accelerator parity is false.

### Exit codes

| Code | Trigger |
|---|---|
| `0` | Backend JSON printed. |
| non-zero via unhandled exception | Native library missing or `MAGIC_GEO_NATIVE_LIBRARY` pointing at a non-file — `RuntimeError` from `src/magic_geo/native.py:114-127` propagates; this is not converted to a Typer exit code. |

### Examples

```bash
magic-geo backend
```

Probe an explicitly staged shared library:

```bash
MAGIC_GEO_NATIVE_LIBRARY=$PWD/build/libmagic_geo_native.so magic-geo backend
```

Extract a single field without extra tooling:

```bash
magic-geo backend | python -c "import json,sys; d=json.load(sys.stdin); print(d['active_backend'], d['openmp_max_threads'])"
```

---

## generate

### Synopsis

```bash
magic-geo generate [--config PATH] [--output PATH] [--summary PATH] [--cells-csv PATH]
                   [--cells N] [--geo-only] [--format auto|json|mgeo]
```

### Description

Loads and validates the YAML config, optionally rewrites `mesh.cell_count`, runs either the full pipeline (`generate_world`) or the natural-geography-only pipeline (`generate_geo_world`), then writes the world plus optional companions. Defined at `src/magic_geo/cli/commands/generate.py:18-90`.

### Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--config`, `-c` | `Path`, `exists=True` | `magic-geo.yaml` | YAML config path. |
| `--output`, `-o` | `Path` | `runs/world.json` | World `.json` or fast `.mgeo` output path. |
| `--summary` | `Path` or unset | unset | Optional Markdown summary path. |
| `--cells-csv` | `Path` or unset | unset | Optional cell CSV path. |
| `--cells` | `int`, `min=128` | unset | Override `mesh.cell_count` for smoke runs. |
| `--geo-only` | flag (no negative form) | `False` | Generate only natural geography enrichments; omit civilization, settlement, and history layers. |
| `--format` | `str` (`auto`, `json`, `mgeo`) | `auto` | World serialization: auto (from suffix), json, or mgeo. |

`--cells` has a Click lower bound of 128 but no upper bound; the schema cap of 200,000 is enforced a moment later by re-validating the mutated config (`src/magic_geo/cli/commands/generate.py:49-55`), which surfaces as a pydantic error and exit `2`.

### Artifacts written

| Path | Written when | Content |
|---|---|---|
| `--output` | always | The world document. JSON when the resolved format is `json`; the versioned MessagePack `.mgeo` container when `mgeo`. Written with `validate_model=False` because the generation pipeline owns the payload's JSON-value invariants on this hot path (`src/magic_geo/cli/commands/generate.py:76-78`). |
| `--summary` | when supplied | Markdown summary built from `world["summary"]` and `world["backend"]` (`src/magic_geo/io/summary_markdown.py:9`). |
| `--cells-csv` | when supplied | One row per cell with a fixed **397**-column header hard-coded as `fieldnames` (`src/magic_geo/io/cells_csv.py:14`), written by `csv.DictWriter(..., extrasaction="ignore")` (`:414-416`). `extrasaction="ignore"` drops cell keys that are not in the header instead of raising; header columns a given world does not populate fall back to `DictWriter`'s default `restval` and are emitted empty. |

### Console output

The progress line goes to **stderr**; the completion line goes to **stdout**:

```text
Generating world | scope=full_world cells=128          # stderr
Wrote runs/world.json | scope=full_world cells=128 plates=8 ocean=0.609 rivers=4 elapsed=0.3s   # stdout
```

`scope` is `geo_only` under `--geo-only` and `full_world` otherwise; the generated payload records the same distinction in its `generation_scope` field (observed value `geo_only` after a `--geo-only` run).

### Exit codes

| Code | Trigger |
|---|---|
| `0` | World written. |
| `2` | Config load failure — `OSError \| ValidationError \| ValueError` (`generate.py:53-55`); `--format` not in `{auto, json, mgeo}` (`:57-59`), printing `--format must be auto, json, or mgeo`; generation failure — `RuntimeError \| ValueError` (`:73-75`), which is also where a native-library or explicit-accelerator-unavailable error lands. |

This command never exits `1`; it does not validate the world it produced.

### Examples

The README's canonical Earth-like run with all three artifacts:

```bash
magic-geo generate \
  --config configs/earthlike_seed.yaml \
  --output runs/earthlike/world.json \
  --summary runs/earthlike/summary.md \
  --cells-csv runs/earthlike/cells.csv
```

A fast smoke run at reduced resolution, overriding the config's cell count:

```bash
magic-geo generate --config configs/earthlike_seed.yaml --cells 512 --output /tmp/world.json
```

Natural-geography-only output in the compact binary format (suffix alone selects `mgeo` under `--format auto`):

```bash
magic-geo generate --geo-only --config configs/earthlike_seed.yaml --output runs/geo-world.mgeo
```

Force JSON despite an `.mgeo`-looking name, or force `mgeo` despite a `.json` name:

```bash
magic-geo generate -c configs/earthlike_seed.yaml -o runs/world.mgeo --format json
magic-geo generate -c configs/earthlike_seed.yaml -o runs/world.json --format mgeo
```

Preview one of the nine checked-in seed presets:

```bash
magic-geo generate \
  --geo-only \
  --config configs/seeds/pelagic_archipelago.yaml \
  --cells 512 \
  --output runs/pelagic-preview.json
```

---

## validate-geo

### Synopsis

```bash
magic-geo validate-geo --world PATH [--profile generic|earthlike] [--output PATH]
                       [--fail-on-warnings | --allow-warnings]
```

### Description

Runs `validate_geo_world(payload, profile=profile)` (`src/magic_geo/geo_validation.py:2743`) and applies a CLI-level severity policy. Defined at `src/magic_geo/cli/commands/validate_geo.py:23-88`. The scope deliberately excludes settlements, navigation/ports/routes, politics, territory, culture, history, population, economy, conflict, logistics, markets, campaigns, and language — that exclusion is recorded verbatim in the report's `excluded_scope` field.

### Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--world`, `-w` | `Path`, `exists=True`, **required** | — | Generated `.json` or `.mgeo` world. |
| `--profile` | `str` (`generic`, `earthlike`) | `generic` | Natural-system validation profile: generic or earthlike. |
| `--output`, `-o` | `Path` or unset | unset | Optional machine-readable validation report. |
| `--fail-on-warnings` / `--allow-warnings` | bool pair | `--allow-warnings` (`False`) | Treat failed evidence-backed realism diagnostics as fatal. |

### Artifacts written

| Path | Written when | Content |
|---|---|---|
| `--output` | when supplied | The full report object plus a CLI-injected `requested_policy` block `{fail_on_warnings, policy_passed}` (`validate_geo.py:62-67`). Serialized by `write_json` with `indent=2, sort_keys=True, allow_nan=False`. |

Report top-level keys (`src/magic_geo/geo_validation.py:2808-2826`, `:2769-2783`):

| Key | Content |
|---|---|
| `schema_version` | `GEO_VALIDATION_SCHEMA_VERSION` = `1` (`geo_validation.py:20`) |
| `report_type` | `"geo_world_validation_v1"` |
| `scope` | Natural-system scope string (`geo_validation.py:22-26`) |
| `excluded_scope` | The civilization-layer exclusion string |
| `model_limitations` | The twelve `GEO_MODEL_LIMITATIONS` strings (`geo_validation.py:28-41`) |
| `profile` | Echoed `--profile` |
| `passed` | `not error_failures` **and** `all_layer_contracts_passed` |
| `summary` | `check_count`, `passed_count`, `error_failure_count`, `warning_failure_count`, `not_applicable_count`, per-domain `domains`, plus `layer_contract_count`, `layer_contract_pass_count`, `layer_contract_failure_count`, `all_layer_contracts_passed` |
| `metrics` | Derived natural-system metrics |
| `checks` | One record per check with `domain`, `name`, `status` (`passed`/`failed`/`not_applicable`), `severity`, `message`, `observed`, `expected` |
| `layer_contracts` | Per-layer artifact/domain/dependency contract results |
| `requested_policy` | CLI-injected policy echo |

Absent rivers, deltas, currents, or biomes are reported as `not_applicable` rather than receiving a vacuous perfect score.

### Console output

```text
OK geo | checks=149 errors=0 warnings=0 not_applicable=3
```

Failures print to stderr as `FAIL <domain>.<name>: <message>`, and failed layer contracts print as `FAIL layer_contract.<id>: required artifacts, validation domains, or dependencies failed`.

### Exit codes

| Code | Trigger |
|---|---|
| `0` | `policy_passed` true. |
| `1` | `policy_passed` false — that is, `report["passed"]` false (any error-severity failure, or any failed layer contract) **or**, under `--fail-on-warnings`, any failed check at all (`validate_geo.py:55-61`, `:87-88`). The `--output` report is written before the exit. |
| `2` | `--profile` not in `{generic, earthlike}`, printing `--profile must be generic or earthlike` (`:50-52`); or a world-load failure. |

Note the ordering at `validate_geo.py:49-52`: the world is loaded **before** the profile is checked, so an invalid world path fails first.

### Examples

Earth-regime gates with a machine-readable report:

```bash
magic-geo validate-geo \
  --world runs/earthlike/world.json \
  --profile earthlike \
  --output runs/earthlike/geo-validation.json
```

Strict mode that also fails on warning-severity realism diagnostics, against a binary world:

```bash
magic-geo validate-geo --world runs/world.mgeo --profile earthlike --fail-on-warnings
```

Inspect only the failed checks from a written report:

```bash
magic-geo validate-geo -w runs/world.json -o runs/geo.json --allow-warnings || true
python -c "
import json
r = json.load(open('runs/geo.json'))
for c in r['checks']:
    if c['status'] == 'failed':
        print(c['severity'], c['domain'] + '.' + c['name'], c['message'])
"
```

---

## validate-geo-suite

### Synopsis

```bash
magic-geo validate-geo-suite [--config PATH] [--matrix PATH] [--output PATH] [--summary PATH]
```

### Description

Generates and validates every scenario in a matrix manifest, evaluates cross-scenario paired response relations, and optionally evaluates configured external empirical target bundles. Defined at `src/magic_geo/cli/commands/validate_geo.py:91-169`; the evaluator is `evaluate_geo_validation_suite` (`src/magic_geo/geo_validation_suite/evaluate.py:171`) and the manifest loader is `load_geo_validation_manifest` (`src/magic_geo/geo_validation_suite/manifest.py:46`).

This command **generates worlds itself**, which makes it the most expensive command in the CLI: the checked-in matrix declares 21 scenarios (22 pipeline runs once `earthlike_pair`'s `repeat: 2` is expanded) plus determinism reruns where the manifest configures them. `calibrate-ensemble` is the only other command that generates worlds; the checked-in `configs/calibration_ensemble.r1.json` has 10 members.

### Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--config`, `-c` | `Path`, `exists=True` | `configs/earthlike_seed.yaml` | Base YAML config path. |
| `--matrix`, `-m` | `Path`, `exists=True` | `configs/geo_validation_matrix.yaml` | Geo scenario matrix with nested config overrides and paired gates. |
| `--output`, `-o` | `Path` | `runs/geo_validation.json` | Machine-readable suite report. |
| `--summary` | `Path` or unset | unset | Optional Markdown suite report. |

The checked-in matrix (`configs/geo_validation_matrix.yaml`) declares `schema_version: 1`, `name: geo_only_earth_and_diverse_planet_matrix_v1`, and a `scenarios:` list where each entry carries `id`, `description`, `profile`, optional `repeat`, `tags`, nested `overrides`, `expectations` ranges, and optionally an `empirical_calibration` block with `target_bundle`, `require_complete`, and `require_all_passed`.

### Artifacts written

| Path | Written when | Content |
|---|---|---|
| `--output` | always | Suite report JSON (`write_json`). |
| `--summary` | when supplied | Markdown rendering via `write_geo_validation_suite_markdown` (`src/magic_geo/geo_validation_suite/report.py`). |

Suite report top-level keys (`src/magic_geo/geo_validation_suite/evaluate.py:313-383`): `schema_version`, `report_type` (`"geo_pipeline_validation_suite_v1"`), `name`, `scope`, `excluded_scope`, `model_limitations`, `passed`, `summary`, `empirical_calibration`, `members`, `relations`.

Selected `summary` fields:

| Field | Meaning |
|---|---|
| `scenario_count`, `scenario_pass_count`, `scenario_pass_fraction` | Overall scenario policy results |
| `internal_scenario_pass_count`, `internal_scenario_pass_fraction`, `all_internal_scenarios_passed` | Internal-only (non-empirical) scenario policy results |
| `relation_count`, `relation_pass_count`, `relation_pass_fraction`, `response_validation_performed`, `all_relations_passed` | Paired cross-scenario response gates |
| `determinism_tested_scenario_count`, `deterministic_scenario_count` | Determinism reruns |
| `empirical_calibration_scenario_count`, `_policy_pass_count`, `_check_count`, `_evaluated_metric_count`, `_pass_count`, `_missing_metric_count`, `_metric_coverage_fraction`, `_pass_fraction`, `_evaluated_pass_fraction`, `all_empirical_calibrations_passed` | External Earth-fit results, kept as a **separate verdict** from internal contract integrity |

`report["passed"]` is `member_pass_count == len(members) and relation_pass_count == len(relation_results)` (`evaluate.py:312`).

### Console output

Per-scenario progress (`[i/n] <scenario id>`), then a single summary line:

```text
Wrote runs/geo_validation.json | scenarios=19/21 relations=26/26 empirical_fit=17/22 coverage=22/22
```

When no scenario configures an empirical bundle, the tail reads `empirical_fit=not-configured` (`validate_geo.py:139-148`).

### Exit codes

| Code | Trigger |
|---|---|
| `0` | `report["passed"]` true. |
| `1` | `report["passed"]` false. Failed scenario ids, failed relation ids, and failed `scenario_id:metric` empirical pairs are printed to stderr (`validate_geo.py:150-169`). The report and summary are written first. |
| `2` | `GeoValidationSuiteError \| ValidationError \| ValueError` while loading the config or manifest, or during evaluation (`:128-130`). |

### Examples

Run the checked-in matrix with both machine-readable and Markdown reports:

```bash
magic-geo validate-geo-suite \
  --config configs/earthlike_seed.yaml \
  --matrix configs/geo_validation_matrix.yaml \
  --output runs/geo-validation-v3.json \
  --summary runs/geo-validation-v3.md
```

Run a custom matrix against a custom base config and keep the defaults for output:

```bash
magic-geo validate-geo-suite -c configs/seeds/verdant_hothouse.yaml -m runs/my_matrix.yaml
```

Extract the failed empirical checks from the report:

```bash
python -c "
import json
r = json.load(open('runs/geo-validation-v3.json'))
for c in r['empirical_calibration']['failed_checks']:
    print(c['scenario_id'], c['metric'])
"
```

---

## validate

### Synopsis

```bash
magic-geo validate --world PATH
```

### Description

The full world-consistency gate. Defined at `src/magic_geo/cli/commands/validate.py:91-95`; that module is the largest in the repository at 22,333 lines, nearly all of it this one function body. It accumulates a `failures: list[str]` from 1,089 inline `failures.append(...)` sites plus delegated validator families, then prints `OK` or every failure.

`--world` is the **entire** signature. There are no per-domain enable/disable flags, no `--output`, no report file, and no severity policy switch. Use `validate-geo` when you want a machine-readable report or a natural-systems-only scope.

### Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--world`, `-w` | `Path`, `exists=True`, **required** | — | Generated `.json` or `.mgeo` world. |

### Two-phase structure

`validate` short-circuits on a schema/planet gate **before** examining anything else (`validate.py:100-122`):

| Early gate check | Failure message shape |
|---|---|
| `type(schema_version) is int and schema_version == CURRENT_WORLD_SCHEMA_VERSION` (`2`) | `world schema_version must be 2, got <repr>` |
| `retired_world_schema_fields(payload)` is empty | `world schema contains retired fields: <names>` |
| `configured_planet_radius_km(payload)` and `surface_gravity_m_s2(payload)` both succeed | `planet parameters invalid: <exc>` |

If any of the three fails, the command prints those failures and exits `1` immediately — **a schema-version mismatch therefore masks every other diagnostic**. Only after that gate passes does the remaining body run, ending in the final accumulation gate at `validate.py:22328-22333`.

### Delegated validator families

Eighteen pure per-domain checkers live in eight modules under `src/magic_geo/cli/validators/` and are re-exported through `src/magic_geo/cli/validators/__init__.py`. Per the package docstring, none of them raise or exit; each returns a list of failure strings.

| Validator module | Families | Call sites in `validate.py` |
|---|---|---|
| `validators/hydrology.py` | water budget, groundwater recharge, aquifer resources, groundwater flow | `:7948`, `:14592`, `:14593`, `:14594` |
| `validators/rivers.py` | channel morphology, hydraulics | `:10127`, `:10129` |
| `validators/sediment.py` | fluvial, hillslope, glacial routing and inventory | `:9101`, `:9107`, `:9113`, `:9116` |
| `validators/settlement.py` | settlement selection, route network | `:10584`, `:10585` |
| `validators/political.py` | political regions, borders, trade flows | `:10586`, `:10587`, `:10588` |
| `validators/navigability.py` | navigable waterways | `:10601` |
| `validators/ports.py` | port sites | `:10856` |
| `validators/corridors.py` | route corridors | `:17996` |

Top-level `magic_geo.*_validation` modules are called for tectonics/crust and for the human/cultural/historical replay block:

| Called validator | Call site |
|---|---|
| `validate_crust_overlap_transport` | `validate.py:6037` |
| `validate_oceanic_age_depth` | `:6040` |
| `validate_initial_oceanic_crust_age` | `:6047` |
| `validate_plate_boundary_edges` | `:6056` |
| `validate_crust_material_shadow` | `:6063` |
| `validate_sediment_interfaces` | `:9119` |
| `validate_human_geography_replay` … `validate_phonology_history_replay` (twelve replays) | `:10589`–`:10600` |

Everything else is inline: schema and planet parameters, mesh backend and control-volume geometry, sea level and ocean circulation, hydrology and depression routing, rivers, sediment and stratigraphy, cryosphere, climate and biosphere, resources, settlement and political layers, history/agents/economy, markets, language, and the trailing `calibration_checks` consistency block (`validate.py:22306-22326`).

### Artifacts written

None. `validate` is read-only.

### Console output

`OK` on stdout for success; one `FAIL <message>` line per accumulated failure on stderr otherwise.

### Exit codes

| Code | Trigger |
|---|---|
| `0` | No failures; prints `OK`. |
| `1` | Early schema/planet gate failed (`:119-122`), or the final accumulated `failures` list is non-empty (`:22328-22331`). |
| `2` | World-load failure only, via `_load_world_for_cli`. |

### Examples

Validate a JSON world and a binary world with the same command:

```bash
magic-geo validate --world runs/world.json
magic-geo validate --world runs/world.mgeo
```

Gate a pipeline on validation, keeping the failure text:

```bash
magic-geo generate -c configs/earthlike_seed.yaml -o runs/world.json
if ! magic-geo validate --world runs/world.json 2> runs/validate-failures.txt; then
  echo "world rejected; first failures:"
  head -20 runs/validate-failures.txt
  exit 1
fi
```

---

## calibrate

### Synopsis

```bash
magic-geo calibrate --world PATH --targets PATH [--output PATH] [--summary PATH]
                    [--require-all-metrics | --allow-missing-metrics]
                    [--require-all-passed  | --allow-fit-failures]
```

### Description

Compares metrics computed from a generated world against externally derived target ranges. Defined at `src/magic_geo/cli/commands/calibrate.py:32-91`; evaluation is `evaluate_calibration_targets` (`src/magic_geo/calibration/evaluate.py:406`) over targets loaded by `load_calibration_targets` (`src/magic_geo/calibration/sources.py:12`).

Earth empirical fit is a **separate verdict** from internal contract integrity: a world that passes `validate` and `validate-geo` can still fail `calibrate`, and that is by design.

### Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--world`, `-w` | `Path`, `exists=True`, **required** | — | Generated `.json` or `.mgeo` world. |
| `--targets`, `-t` | `Path`, `exists=True`, **required** | — | JSON calibration target ranges derived from external datasets. |
| `--output`, `-o` | `Path` | `runs/calibration.json` | Calibration report JSON path. |
| `--summary` | `Path` or unset | unset | Optional Markdown calibration report path. |
| `--require-all-metrics` / `--allow-missing-metrics` | bool pair | `--allow-missing-metrics` (`False`) | Exit nonzero after writing the report when any target metric is unavailable. |
| `--require-all-passed` / `--allow-fit-failures` | bool pair | `--allow-fit-failures` (`False`) | Exit nonzero after writing the report unless every target metric is available and in range. |

### Artifacts written

| Path | Written when | Content |
|---|---|---|
| `--output` | always, before any policy exit | Calibration report JSON. |
| `--summary` | when supplied | Markdown via `write_calibration_markdown`. |

Report keys (`src/magic_geo/calibration/evaluate.py:469-488`):

| Key | Content |
|---|---|
| `summary.external_calibration_check_count` | Number of targets evaluated |
| `summary.external_calibration_evaluated_metric_count` | Checks with an available world metric |
| `summary.external_calibration_pass_count` | Checks in range |
| `summary.external_calibration_missing_metric_count` | Checks whose world metric was unavailable |
| `summary.external_calibration_metric_coverage_fraction` | evaluated / total, rounded to 6 dp |
| `summary.external_calibration_pass_fraction` | passed / total, rounded to 6 dp |
| `summary.external_calibration_evaluated_pass_fraction` | passed / evaluated, rounded to 6 dp |
| `summary.external_mean_calibration_score`, `summary.external_mean_evaluated_calibration_score` | Mean scores over all / evaluated checks |
| `summary.external_calibration_complete` | `missing_count == 0 and count > 0` |
| `available_world_metrics`, `missing_world_metrics` | Sorted metric-name lists |
| `checks[]` | `id`, `dataset`, `layer`, `metric`, `source_metric`, `value`, `target_min`, `target_max`, `score`, `passed`, `missing_metric`, `source`, plus any `source_*` provenance keys and `tolerance_basis` |

### Console output

```text
Wrote runs/calibration.json | checks=4 coverage=1.000 pass_fraction=0.500
```

### Exit codes

| Code | Trigger |
|---|---|
| `0` | Report written and no policy flag was violated. |
| `1` | `--require-all-metrics` with `external_calibration_complete` false, printing `Calibration coverage incomplete; missing world metrics: …` or `… no calibration targets were evaluated` (`calibrate.py:81-85`); or `--require-all-passed` with any failed check **or zero checks**, printing `Calibration fit failed; failed metrics: …` (`:86-91`). |
| `2` | `CalibrationError \| json.JSONDecodeError` from target loading or evaluation (`:67-69`); or a world-load failure. |

Verified behavior in this checkout: the same world/targets pair exits `0` under `--require-all-metrics` (coverage 4/4) and exits `1` under `--require-all-passed` with `failed metrics: global_mean_temperature_c, coastal_land_fraction`.

### Examples

Contract-fixture round trip (synthetic grids checked into the repository):

```bash
magic-geo derive-targets \
  --sources configs/calibration_sources.example.json \
  --output runs/example_targets.json

magic-geo calibrate \
  --world runs/world.json \
  --targets runs/example_targets.json \
  --output runs/calibration.json \
  --summary runs/calibration.md
```

Enforce complete coverage against a real derived bundle, keeping the report even on failure:

```bash
bash scripts/fetch_etopo_2022_1deg.sh
magic-geo derive-targets --sources configs/calibration_sources.etopo_2022_1deg.json --output runs/etopo_targets.json
magic-geo calibrate --world runs/world.json --targets runs/etopo_targets.json \
  --output runs/etopo_calibration.json --require-all-metrics
```

Enforce full fit (this is the strict gate; expect nonzero on a world that has not been tuned):

```bash
magic-geo calibrate -w runs/world.json -t runs/etopo_targets.json \
  -o runs/etopo_calibration.json --require-all-passed || echo "fit gate failed; report still written"
```

---

## calibrate-ensemble

### Synopsis

```bash
magic-geo calibrate-ensemble --config PATH --matrix PATH --targets PATH [--targets PATH]...
                             [--output PATH] [--summary PATH]
                             [--require-all-metrics | --allow-missing-metrics]
                             [--require-all-passed  | --allow-fit-failures]
```

### Description

Generates every member of an explicit seed/cell-count manifest and evaluates each generated world against the union of one or more target bundles. Defined at `src/magic_geo/cli/commands/calibrate.py:94-199`; the manifest loader is `load_calibration_ensemble_manifest` (`src/magic_geo/ensemble_calibration.py:27`) and the evaluator is `evaluate_calibration_ensemble` (`:226`). Like `validate-geo-suite`, this command generates worlds and is expensive.

### Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--config`, `-c` | `Path`, `exists=True`, **required** | — | Base YAML config path. |
| `--matrix`, `-m` | `Path`, `exists=True`, **required** | — | JSON manifest containing explicit seed/cell-count ensemble members. |
| `--targets`, `-t` | `Path`, `exists=True`, **required**, repeatable | — | Calibration target JSON path; repeat for multiple non-overlapping target bundles. |
| `--output`, `-o` | `Path` | `runs/calibration_ensemble.json` | Calibration ensemble report JSON path. |
| `--summary` | `Path` or unset | unset | Optional Markdown calibration ensemble report path. |
| `--require-all-metrics` / `--allow-missing-metrics` | bool pair | `--allow-missing-metrics` (`False`) | Exit nonzero after writing unless every member covers every target. |
| `--require-all-passed` / `--allow-fit-failures` | bool pair | `--allow-fit-failures` (`False`) | Exit nonzero after writing unless every member passes every target. |

The checked-in manifest `configs/calibration_ensemble.r1.json` has `schema_version: 1`, `name: r1_empirical_seed_resolution_matrix_v1`, and a `members` list where each entry carries `id`, `seed`, `cell_count`, and `groups` (for example `seed_sweep`, `resolution_sweep`).

### Provenance

The report embeds cryptographic provenance so a result can be traced back to its exact inputs (`calibrate.py:150-171`):

| Provenance field | Source |
|---|---|
| `provenance.base_config_sha256` | SHA-256 of the canonically serialized base config (`ensemble_calibration.py:298-308`) |
| `provenance.matrix_sha256` | SHA-256 of the `--matrix` file bytes (`calibrate.py:169`) |
| `provenance.target_bundles[]` | Per bundle: `name`, `sha256` of the file bytes, `target_count` (`calibrate.py:150-156`) |

### Artifacts written

| Path | Written when | Content |
|---|---|---|
| `--output` | always, before any policy exit | Ensemble report JSON. |
| `--summary` | when supplied | Markdown via `write_calibration_ensemble_markdown` (`ensemble_calibration.py:340`). |

Report top-level keys (`ensemble_calibration.py:303-337`): `schema_version`, `report_type`, `name`, `provenance`, `base_config` (`name`, `seed`, `mesh_backend`, `cell_count`), `summary`, `members`, `datasets`, `metrics`, `groups`.

`summary` fields: `member_count`, `group_count`, `target_count`, `dataset_count`, `complete_member_count`, `complete_member_fraction`, `all_targets_passed_member_count`, `all_targets_passed_member_fraction`, `reference_matrix_complete`, `reference_matrix_all_passed`.

### Console output

Per-member progress (`[i/n] <id> seed=<seed> cells=<cells>`), then:

```text
Wrote runs/calibration_ensemble.json | members=9 coverage=1.000 all_passed=0.667
```

### Exit codes

| Code | Trigger |
|---|---|
| `0` | Report written and no policy flag was violated. |
| `1` | `--require-all-metrics` with `reference_matrix_complete` false, printing `Calibration ensemble coverage incomplete` (`:188-190`); or `--require-all-passed` with `reference_matrix_all_passed` false, printing `Calibration ensemble fit failed; failed members: …` (`:191-199`). |
| `2` | `CalibrationError \| json.JSONDecodeError \| ValidationError \| ValueError` during config/manifest/target loading or evaluation (`:174-176`). |

### Examples

Run the checked-in r1 matrix against a single derived bundle:

```bash
magic-geo calibrate-ensemble \
  --config configs/earthlike_seed.yaml \
  --matrix configs/calibration_ensemble.r1.json \
  --targets runs/etopo_targets.json \
  --output runs/calibration_ensemble.json \
  --summary runs/calibration_ensemble.md
```

Combine several non-overlapping bundles and require complete coverage on every member:

```bash
magic-geo calibrate-ensemble \
  -c configs/earthlike_seed.yaml \
  -m configs/calibration_ensemble.r1.json \
  -t runs/natural_earth_targets.json \
  -t runs/etopo_targets.json \
  -t runs/worldclim_targets.json \
  -t configs/calibration_targets.seton_2020_oceanic_age.json \
  --require-all-metrics
```

Verify the recorded provenance hashes against the input files:

```bash
python -c "
import hashlib, json
r = json.load(open('runs/calibration_ensemble.json'))
print(r['provenance']['matrix_sha256'])
print(hashlib.sha256(open('configs/calibration_ensemble.r1.json','rb').read()).hexdigest())
"
```

---

## derive-targets

### Synopsis

```bash
magic-geo derive-targets --sources PATH [--output PATH] [--summary PATH]
```

### Description

Derives calibration target ranges from supported **local** raster, vector, and archive sources. Defined at `src/magic_geo/cli/commands/calibrate.py:202-233`; loading is `load_calibration_sources` (`src/magic_geo/calibration/sources.py:16`) and derivation is `derive_calibration_targets` (`src/magic_geo/calibration/derive.py:64`). No network access happens here — the `scripts/fetch_*.sh` helpers download the datasets separately.

### Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--sources`, `-s` | `Path`, `exists=True`, **required** | — | JSON source manifest for deriving calibration target ranges from local raster/vector data. |
| `--output`, `-o` | `Path` | `runs/calibration_targets.json` | Derived calibration targets JSON path. |
| `--summary` | `Path` or unset | unset | Optional Markdown target derivation report path. |

Each entry in the manifest's `sources` array carries at least `dataset`, `layer`, `metric`, `world_metric`, `path`, `format`, `statistic`, and a tolerance key such as `tolerance_abs` (observed in `configs/calibration_sources.example.json`). Relative `path` values resolve against the manifest's own directory — the example manifest points at `calibration_fixtures/*.asc` next to it.

### Checked-in source manifests

| File | Dataset |
|---|---|
| `configs/calibration_sources.example.json` | Synthetic contract fixtures only; the file's own `description` says to replace these grids with real data before treating results as empirical calibration. |
| `configs/calibration_sources.natural_earth_110m.json` | Natural Earth 110m |
| `configs/calibration_sources.etopo_2022_1deg.json` | ETOPO 2022 1° |
| `configs/calibration_sources.worldclim_2_1_10m.json` | WorldClim 2.1 10m |
| `configs/calibration_sources.hydrobasins_level3.json` | HydroBASINS level 3 |
| `configs/calibration_sources.hydrorivers_v10.json` | HydroRIVERS v1.0 |
| `configs/calibration_sources.seton_2020_oceanic_age.json` | Seton 2020 oceanic age |

`configs/calibration_targets.seton_2020_oceanic_age.json` is a checked-in *derived* bundle; `configs/geo_validation_earth_empirical_targets.json` is the authoritative bundle the geo suite's empirical policy consumes.

### Artifacts written

| Path | Written when | Content |
|---|---|---|
| `--output` | always | Derived target ranges JSON with `summary.derived_target_count` and `summary.source_count` (`src/magic_geo/calibration/derive.py:240-241`). |
| `--summary` | when supplied | Markdown via `write_target_derivation_markdown`. |

### Console output

```text
Wrote runs/calibration_targets.json | targets=4 sources=4
```

### Exit codes

| Code | Trigger |
|---|---|
| `0` | Targets written. |
| `2` | `CalibrationError \| json.JSONDecodeError` while loading the manifest or deriving targets (`calibrate.py:221-223`). |

This command never exits `1` — it has no policy flags.

### Examples

Derive from the checked-in synthetic fixtures (works with no downloads):

```bash
magic-geo derive-targets \
  --sources configs/calibration_sources.example.json \
  --output runs/example_targets.json \
  --summary runs/example_targets.md
```

Fetch and derive a real bundle, then calibrate against it:

```bash
bash scripts/fetch_natural_earth_110m.sh
magic-geo derive-targets --sources configs/calibration_sources.natural_earth_110m.json \
  --output runs/natural_earth_targets.json
magic-geo calibrate --world runs/world.json --targets runs/natural_earth_targets.json \
  --output runs/natural_earth_calibration.json --require-all-metrics
```

---

## render

### Synopsis

```bash
magic-geo render --world PATH [--output PATH] [--width N] [--height N] [--projection NAME]
                 [--labels | --no-labels] [--max-cells N]
                 [--contours | --no-contours] [--contour-interval M]
```

### Description

Renders a generated world as a layer-driven SVG map. Defined at `src/magic_geo/cli/commands/render.py:14-57`; the writer is `write_svg_map` (`src/magic_geo/io/svg_map.py:12`). The SVG draws control-volume cells colored by a biome/landform palette, marks river cells from each cell's `is_river` flag, and overlays `routes`, `settlements`, `sacred_areas`, and `ruins` from the world payload when present.

### Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--world`, `-w` | `Path`, `exists=True`, **required** | — | Generated `.json` or `.mgeo` world. |
| `--output`, `-o` | `Path` | `runs/world.svg` | SVG map output path. |
| `--width` | `int`, `320 ≤ x ≤ 6400` | `1600` | SVG width in pixels. |
| `--height` | `int`, `160 ≤ x ≤ 3200` | `800` | SVG height in pixels. |
| `--projection` | `str` (`equirectangular`, `mollweide`, `orthographic`) | `equirectangular` | SVG projection. |
| `--labels` / `--no-labels` | bool pair | `--no-labels` (`False`) | Render settlement labels. |
| `--max-cells` | `int`, `x ≥ 128` | unset | Optional maximum cells to render for low-detail maps. |
| `--contours` / `--no-contours` | bool pair | `--contours` (`True`) | Render symbolic elevation contour layer. |
| `--contour-interval` | `float`, `x ≥ 50.0` | `500.0` | Contour interval in meters when contours are enabled. |

The projection string is normalized with `.lower().replace("_", "-")` before the membership check (`src/magic_geo/io/svg_map.py:30-32`), so `EQUIRECTANGULAR` is accepted and anything else raises `unknown projection: <value>`. `render-raster` applies the same normalization (`src/magic_geo/io/raster_map.py:25-27`).

### Artifacts written

| Path | Content |
|---|---|
| `--output` | One SVG document. The root element carries `data-projection`, `data-renderer="terrain-v1"`, and `data-contours` attributes, and `<title>` is `"<world name> <projection> causal terrain map"` (`src/magic_geo/io/svg_map.py:189-190`). Parent directories are created automatically. |

### Exit codes

| Code | Trigger |
|---|---|
| `0` | SVG written; prints `Wrote <output>`. |
| `2` | `ValueError` from `write_svg_map`, notably an unknown projection (`render.py:54-56`); or a world-load failure. |

Verified: `--projection bogus` prints `unknown projection: bogus` and exits `2`.

### Examples

The README's reference map:

```bash
magic-geo render \
  --world runs/world.json \
  --output runs/world.svg \
  --projection mollweide \
  --labels \
  --contours \
  --max-cells 4096
```

A clean, contour-free orthographic hemisphere at higher resolution:

```bash
magic-geo render -w runs/world.mgeo -o runs/globe.svg \
  --projection orthographic --width 2400 --height 2400 --no-contours --no-labels
```

Fine contours on a wide equirectangular sheet:

```bash
magic-geo render -w runs/world.json -o runs/contours.svg \
  --width 6400 --height 3200 --contour-interval 100
```

---

## render-raster

### Synopsis

```bash
magic-geo render-raster --world PATH [--output PATH] [--width N] [--height N]
                        [--projection NAME] [--max-cells N] [--texture | --no-texture]
```

### Description

Renders a dependency-free binary PPM (P6) raster map. Defined at `src/magic_geo/cli/commands/render.py:60-96`; the writer is `write_raster_map` (`src/magic_geo/io/raster_map.py:10`). It uses the same three projections and the same palette family as `render`, but produces pixels rather than vectors and has no label or contour layer.

### Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--world`, `-w` | `Path`, `exists=True`, **required** | — | Generated `.json` or `.mgeo` world. |
| `--output`, `-o` | `Path` | `runs/world.ppm` | PPM raster map output path. |
| `--width` | `int`, `320 ≤ x ≤ 6400` | `1600` | Raster width in pixels. |
| `--height` | `int`, `160 ≤ x ≤ 3200` | `800` | Raster height in pixels. |
| `--projection` | `str` (`equirectangular`, `mollweide`, `orthographic`) | `equirectangular` | Raster projection. |
| `--max-cells` | `int`, `x ≥ 128` | unset | Optional maximum cells to render for low-detail rasters. |
| `--texture` / `--no-texture` | bool pair | `--texture` (`True`) | Apply deterministic terrain texture. |

### Artifacts written

| Path | Content |
|---|---|
| `--output` | Binary P6 PPM. The header is `P6\n# magic-geo raster-terrain-v1 projection=<projection> texture=<true\|false>\n<width> <height>\n255\n` followed by raw RGB bytes (`src/magic_geo/io/raster_map.py:276`). Confirmed by inspecting a generated file. |

PPM has no compression, so a 6400×3200 raster is roughly 61 MB of pixel data. Convert with any external tool if you need PNG.

### Exit codes

| Code | Trigger |
|---|---|
| `0` | Raster written; prints `Wrote <output>`. |
| `2` | `ValueError` from `write_raster_map`, notably an unknown projection (`render.py:93-95`); or a world-load failure. |

### Examples

Mollweide raster matching the README recipe:

```bash
magic-geo render-raster \
  --world runs/world.json \
  --output runs/world.ppm \
  --projection mollweide \
  --max-cells 4096
```

Flat-shaded (untextured) equirectangular raster for diffing two worlds byte-for-byte:

```bash
magic-geo render-raster -w runs/a.json -o runs/a.ppm --no-texture
magic-geo render-raster -w runs/b.json -o runs/b.ppm --no-texture
cmp runs/a.ppm runs/b.ppm && echo "identical"
```

---

## export-debug-map

### Synopsis

```bash
magic-geo export-debug-map [--debug-dir DIR] [--layer ID] [--output BASENAME]
                           [--projection globe|equirect|mollweide] [--width N] [--height N]
                           [--stage N] [--month 1-12] [--center-lat D] [--center-lon D]
                           [--camera-distance D] [--camera-position X,Y,Z]
                           [--camera-target X,Y,Z] [--camera-up X,Y,Z] [--vertical-fov D]
                           [--cache-identity S] [--wireframe] [--plates] [--graticule]
                           [--image | --no-image] [--prompt | --no-prompt]
```

### Description

Renders one layer of an existing debug cache to a PNG and writes a matching copy/paste GPT Image Markdown prompt with an adaptive color codex — without a browser. Defined at `src/magic_geo/cli/commands/export.py:13-161`; the implementation is `export_map_reference` (`src/magic_geo/debug_map_export.py:1291`). It reads a cache produced by `export-debug`, **not** a world file. The module never calls an image-generation service; it only writes the prompt text.

### Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--debug-dir`, `-d` | `Path`, `exists=True`, `file_okay=False` | `runs/debug` | Debug cache directory produced by `export-debug`. |
| `--layer`, `-l` | `str` or unset | unset | Manifest layer id (default: `cells/elevation_m`, then the first numeric layer). |
| `--output`, `-o` | `Path` or unset | unset → `runs/<generated name>` | Output basename; `.png` and `.gpt-image-prompt.md` are appended. |
| `--projection` | `str` (`globe`, `equirect`, `mollweide`) | `globe` | Map projection. |
| `--width` | `int`, `320 ≤ x ≤ 6400` | `1600` | PNG width in pixels. |
| `--height` | `int`, `160 ≤ x ≤ 3200` | `900` | PNG height in pixels. |
| `--stage` | `int`, `x ≥ 0` | `0` | Zero-based stage for `*_stage` layers. |
| `--month` | `int`, `1 ≤ x ≤ 12` | `1` | Month (1-12) for monthly layers. |
| `--center-lat` | `float`, `-90.0 ≤ x ≤ 90.0` | `0.0` | Latitude at the center of the exported view. |
| `--center-lon` | `float`, `-360.0 ≤ x ≤ 360.0` | `0.0` | Longitude at the center of the exported view. |
| `--camera-distance` | `float`, `1.01 ≤ x ≤ 100.0` | unset → `3.0` globe, `3.4` flat | Perspective camera distance. |
| `--camera-position` | `str` `x,y,z` | unset | Exact Three.js camera position; enables explicit web-camera replay. |
| `--camera-target` | `str` `x,y,z` | unset → `0,0,0` | Exact OrbitControls target (requires `--camera-position`). |
| `--camera-up` | `str` `x,y,z` | unset → `0,1,0` | Exact Three.js camera up vector (requires `--camera-position`). |
| `--vertical-fov` | `float`, `1.0 ≤ x ≤ 179.0` | `50.0` | Perspective vertical field of view in degrees. |
| `--cache-identity` | `str` or unset | unset | Browser cache identity override for byte-exact view-fingerprint/name parity. |
| `--wireframe` / `--no-wireframe` | bool pair | `--no-wireframe` (`False`) | Include diagnostic cell/triangle edges in the PNG. |
| `--plates` / `--no-plates` | bool pair | `--no-plates` (`False`) | Include diagnostic plate-boundary guides in the PNG. |
| `--graticule` / `--no-graticule` | bool pair | `--no-graticule` (`False`) | Include diagnostic latitude/longitude guides in the PNG. |
| `--image` / `--no-image` | bool pair | `--image` (`True`) | Write the diagnostic PNG reference image. |
| `--prompt` / `--no-prompt` | bool pair | `--prompt` (`True`) | Write the copy/paste GPT Image Markdown prompt and color codex. |

`--month` is 1-based at the CLI and converted to a 0-based index (`month=month - 1`) before `export_map_reference` (`export.py:139`); the completion line converts it back (`month={result.month + 1}`). Two aliases are accepted so the `render`/`render-raster` projection vocabulary also works here: `equirectangular` maps to `equirect` and `orthographic` maps to `globe` (`debug_map_export.py:1317-1321`).

### Layer selection

Debug-cache layers carry a `kind`. In a 128-cell smoke cache this checkout produced 428 layers: 361 `numeric`, 47 `categorical`, 16 `numeric_stage`, and 4 `numeric_monthly`. `--stage` applies only to `*_stage` kinds and `--month` only to `numeric_monthly`. Ids look like `cells/elevation_m`, `cells/biome`, `monthly/precipitation_monthly_mm`, and `hydrologic_water_budget_history/elevation_m`. An unknown `--layer` raises with a sample of available ids.

### Limits enforced before rendering

| Limit | Value | Source |
|---|---|---|
| `MAX_RASTER_PIXELS` | `8_294_400` | `src/magic_geo/debug_map_export.py:40` |
| `MAX_DEBUG_CELLS` | `200_000` | `:41` |
| `MAX_MESH_VERTICES` | `2_000_000` | `:42` |
| `MAX_MESH_TRIANGLES` | `2_000_000` | `:43` |

Additionally, a cache whose mesh reports any `cells_without_ring` is rejected, because "a semantic image prompt would mislabel those holes as outside-map background" (`debug_map_export.py:1363-1367`). If the cache changes mid-export, the snapshot fingerprint check fails with `debug cache changed while its export snapshot was being opened; retry`.

### Artifacts written

| Path | Written when | Content |
|---|---|---|
| `<base>.png` | `--image` (default on) | Diagnostic PNG of the selected layer with the requested projection, camera, and optional wireframe/plates/graticule overlays. |
| `<base>.gpt-image-prompt.md` | `--prompt` (default on) | Copy/paste Markdown prompt plus the adaptive color codex for the rendered values. |

`<base>` is `--output` when supplied, otherwise `runs/<generated name>` where the name is assembled by `map_export_base_name` (`debug_map_export.py:192-214`) as `world--layer--projection[--stage-N][--month-M]--view-<fingerprint>`. A default export from a 128-cell smoke cache in this checkout produced `runs/smoke--cells-elevation-m--globe--view-<fingerprint>.png`; the trailing view fingerprint is derived from the requested view and cache identity, so do not expect a specific hex value to reproduce across caches. Both artifacts are written to temporary files first and published together.

Passing both `--no-image` and `--no-prompt` raises `at least one of PNG or Markdown output must be enabled` (`debug_map_export.py:1322-1323`).

### Exit codes

| Code | Trigger |
|---|---|
| `0` | Artifacts written; prints `Wrote <paths> \| layer=<id> projection=<p> stage=<s> month=<1-based m>`. |
| `2` | `ImportError` on the optional debug dependencies, printing `pip install 'magic-geo[debug]'` (`export.py:123-129`); `OSError \| ValueError` from `export_map_reference`, printed as `Unable to export debug map: <exc>` (`:154-156`); or a Click bound violation on any numeric option. |

This command never exits `1`.

### Examples

Export a named biome map with an explicit output basename:

```bash
magic-geo export-debug-map \
  --debug-dir runs/debug \
  --layer cells/biome \
  --projection mollweide \
  --output runs/biome-reference
# writes runs/biome-reference.png and runs/biome-reference.gpt-image-prompt.md
```

Export the July frame of a monthly layer, with graticule, and no prompt file:

```bash
magic-geo export-debug-map -d runs/debug \
  --layer monthly/precipitation_monthly_mm \
  --month 7 --projection equirect --graticule --no-prompt \
  --output runs/precip-july
```

Export a specific maturation stage of a stage layer as a wireframed globe centered on a region:

```bash
magic-geo export-debug-map -d runs/debug \
  --layer hydrologic_water_budget_history/elevation_m \
  --stage 3 --projection globe --center-lat 35 --center-lon -20 \
  --camera-distance 2.2 --vertical-fov 40 --wireframe --plates \
  --output runs/stage3-relief
```

Reproduce a browser view byte-exactly by replaying its camera and cache identity:

```bash
magic-geo export-debug-map -d runs/debug -l cells/elevation_m \
  --camera-position 1.5,2.0,2.5 --camera-target 0,0,0 --camera-up 0,1,0 \
  --cache-identity "$BROWSER_CACHE_IDENTITY"
```

---

## export-debug

### Synopsis

```bash
magic-geo export-debug --world PATH [--output DIR] [--vtu | --no-vtu]
                       [--elevation-exaggeration X]
```

### Description

Exports a world into a columnar debug cache the web workbench, `export-debug-map`, and ParaView can all read. Defined at `src/magic_geo/cli/commands/export.py:164-205`; the implementation is `export_debug_cache` (`src/magic_geo/debug_export.py:819`).

### Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--world`, `-w` | `Path`, `exists=True`, **required** | — | Generated `.json` or `.mgeo` world. |
| `--output`, `-o` | `Path` or unset | unset → `<world dir>/debug` | Debug cache directory. |
| `--vtu` / `--no-vtu` | bool pair | `--vtu` (`True`) | Also emit ParaView `.vtu` stage files and `world.pvd`. |
| `--elevation-exaggeration` | `float`, `x ≥ 1.0` | `30.0` | Radial elevation exaggeration for `.vtu` geometry. |

A world generated with `output.include_cells: false` cannot be exported: `export_debug_cache` raises `world payload has no cells; generate with output.include_cells enabled` (`debug_export.py:832-833`).

### Artifacts written

| Path | Content |
|---|---|
| `<out>/manifest.json` | The cache index. Top-level keys observed: `format` (`"magic-geo-debug-cache"`, `debug_export.py:30`), `version` (`1`, `:31`), `world`, `cells`, `monthly`, `layers`, `stage_histories`, `families`, `sections`, `scalars`, `skipped_sections`, `mesh`, `paraview`, `simulation_clock`, `source`. |
| `<out>/tables/cells.parquet` | One row per cell, all scalar cell columns. |
| `<out>/tables/cells_monthly.parquet` | Monthly climatology columns. |
| `<out>/tables/<family>-<sha256>.parquet` and `…​.scalars.parquet` | One table per nested record family. |
| `<out>/tables/<history>_stage_cells.parquet`, `<history>_stages.parquet` | Per-stage cell values and per-stage summaries. |
| `<out>/events/cell_details.jsonl`, `<out>/events/cell_details_index.json` | Non-columnar per-cell detail records. |
| `<out>/events/<family>-<sha256>.jsonl`, `<history>_stage_extras.jsonl` | Retained non-columnar family and stage extras. |
| `<out>/mesh/positions.f32`, `cell_ids.u32`, `indices.u32`, `pos_equirect.f32`, `pos_mollweide.f32`, `mesh.json` | Little-endian binary mesh buffers plus their descriptor. Buffer dtypes and component counts are declared in `manifest["mesh"]["buffers"]` (`debug_export.py:663-667`). |
| `<out>/sections.json` | Every non-list, non-scalar world section, `indent=2, sort_keys=True`. |
| `<out>/vtu/stage_NNNN.vtu` and `<out>/world.pvd` | Written only under `--vtu` (`debug_export.py:807-811`, `:767`). |

`manifest["source"]` records the source world's `path`, `bytes`, and `sha256` when `source_path` is supplied — which the CLI always does (`export.py:189-195`).

### Console output

```text
Wrote runs/debug | layers=428 stage_histories=1 families=99 mesh_vertices=884 mesh_triangles=756
```

### Exit codes

| Code | Trigger |
|---|---|
| `0` | Cache written. |
| `2` | `ImportError` on the optional debug dependencies, printing `pip install 'magic-geo[debug]'` (`export.py:182-185`); `ValueError` from `export_debug_cache` (`:196-198`); or a world-load failure. |

This command never exits `1`.

### Examples

Export next to the world (the CLI default) and then to an explicit workbench-rooted directory:

```bash
magic-geo export-debug --world runs/earthlike/world.json
# -> runs/earthlike/debug

magic-geo export-debug --world runs/world.json --output runs/debug
```

Skip the ParaView companion for a faster, smaller cache (README recipe):

```bash
magic-geo export-debug --world runs/world.json --output runs/debug --no-vtu
```

Exaggerate relief for a ParaView flythrough:

```bash
magic-geo export-debug -w runs/world.mgeo -o runs/debug-vtu --elevation-exaggeration 80
```

---

## export-rerun

### Synopsis

```bash
magic-geo export-rerun --world PATH [--output PATH]
```

### Description

Writes a Rerun `.rrd` recording with the triangulated cell mesh on a `stage` timeline, every numeric earth-system feedback scalar as a time series, and plate-boundary line segments. Defined at `src/magic_geo/cli/commands/export.py:208-232`; the implementation is `export_rerun_recording` (`src/magic_geo/debug_rerun.py:59`). Requires `rerun-sdk`, which is **not** part of the `debug` extra.

### Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--world`, `-w` | `Path`, `exists=True`, **required** | — | Generated `.json` or `.mgeo` world. |
| `--output`, `-o` | `Path` or unset | unset → `<world dir>/world.rrd` | Rerun recording path. |

### Artifacts written

| Path | Content |
|---|---|
| `--output` (or `<world dir>/world.rrd`) | One `.rrd` recording. The stage timeline is driven by the hydrologic water-budget history; per-vertex colors use a viridis ramp stretched between the 2nd and 98th percentile of finite values (`debug_rerun.py:86-97`). |

`export_rerun_recording` returns six statistics — `output`, `vertices`, `triangles`, `stages`, `feedback_scalars`, `plate_boundary_segments` (`debug_rerun.py:166-173`). The completion line prints four of them (`stages`, `vertices`, `feedback_scalars`, `plate_boundary_segments` as `plate_segments`) alongside the resolved output path; `triangles` is returned but not echoed.

### Console output

```text
Wrote world.rrd | stages=3 vertices=884 feedback_scalars=336 plate_segments=162
```

### Exit codes

| Code | Trigger |
|---|---|
| `0` | Recording written. |
| `2` | `ImportError`, printing `Rerun export requires the rerun-sdk package: pip install rerun-sdk (…)` (`export.py:218-221`); `ValueError` from `export_rerun_recording`, including a world with no cells (`:226-228`); or a world-load failure. |

This command never exits `1`.

### Examples

Default placement next to the world:

```bash
pip install rerun-sdk
magic-geo export-rerun --world runs/earthlike/world.json
# -> runs/earthlike/world.rrd
```

Explicit output path, then open it in the viewer:

```bash
magic-geo export-rerun -w runs/world.mgeo -o runs/recordings/earthlike.rrd
rerun runs/recordings/earthlike.rrd
```

---

## serve

### Synopsis

```bash
magic-geo serve [--debug-dir DIR] [--workspace DIR] [--host ADDR] [--port N]
```

### Description

Starts the local browser workbench (FastAPI + uvicorn). Defined at `src/magic_geo/cli/commands/serve.py:13-114`; the app factory is `create_app` (`src/magic_geo/debug_server.py:877`). `serve` works before any world exists: the Config and Operations views remain available with no cache selected.

The workbench is a trusted-local, single-user tool with no authentication or user isolation. Keep the default loopback binding unless a trusted network boundary or authenticating reverse proxy protects it.

### Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--debug-dir`, `-d` | `Path`, `exists=True`, `file_okay=False`, `dir_okay=True`, or unset | unset → auto-discover `<workspace>/debug` | Optional cache from `export-debug`; auto-loads `<workspace>/debug` when present. |
| `--workspace` | `Path`, env `MAGIC_GEO_WORKSPACE` | `runs` | Directory for browser-created configs, worlds, reports, and exports. |
| `--host` | `str`, env `MAGIC_GEO_HOST` | `127.0.0.1` | Bind address. |
| `--port` | `int`, `1 ≤ x ≤ 65535`, env `MAGIC_GEO_PORT` | `8642` | Bind port. |

### Cache selection logic

1. If `-d` is given, it must contain a `manifest.json` file, otherwise `serve` prints `No manifest.json in <dir>; choose an export-debug cache or omit -d.` and exits `2` (`serve.py:70-75`).
2. If `-d` is omitted, `<workspace>/debug` is selected **only** when `<workspace>/debug/manifest.json` is a file (`serve.py:64-69`).
3. If an auto-discovered cache turns out invalid at `create_app` time, `serve` prints `Ignoring invalid automatic cache <dir>: <exc>` and retries with no cache rather than failing (`serve.py:85-96`). An explicitly requested `-d` that fails instead exits `2`.

### Artifacts written

`serve` itself writes nothing at startup. The running workbench writes inside the resolved workspace:

| Path | Content |
|---|---|
| `<workspace>/configs/` | Browser-created and validated YAML configs (`src/magic_geo/debug_server.py:1020`). |
| `<workspace>/debug/` | The prepared/browser `export-debug` cache (`src/magic_geo/web_jobs.py:1252`). |
| `<workspace>/.magic-geo-web/` | Internal job state (`src/magic_geo/web_jobs.py:429`). |
| `<workspace>/…` | Worlds, reports, and exports produced by Operations jobs. |

Cache exports are built in staging and published only after success, so a failed or cancelled replacement does not damage the selected cache. Download links serve immutable per-job snapshots, and reports remain downloadable even when a validation or calibration policy makes the job exit nonzero.

### HTTP surface

| Path | Content |
|---|---|
| `/` | The workbench UI |
| `/api/docs` | Swagger UI (`debug_server.py:915`) |
| `/api/redoc` | ReDoc (`:916`) |
| `/api/openapi.json` | OpenAPI schema (`:917`) |

### Console output

```text
Serving web workbench debug cache runs/debug at http://127.0.0.1:8642
```

or, with no cache selected:

```text
Serving web workbench with automatic workspace cache discovery (Config and Operations remain available) at http://127.0.0.1:8642
```

### Exit codes

| Code | Trigger |
|---|---|
| (blocks) | On success `serve` calls `uvicorn.run(...)` at `log_level="warning"` and never returns normally; stop it with SIGINT. |
| `2` | Resolved `--workspace` escapes `Path.cwd()` (`serve.py:57-63`); explicit `-d` without `manifest.json` (`:70-75`); `ImportError` on `uvicorn`/`debug_server` (`:80-82`); `create_app` `ValueError`/`OSError` that is not recoverable by dropping the auto-discovered cache (`:85-102`); or `-d` pointing at a nonexistent path / a file (Click `exists=True`, `file_okay=False`). |

This command never exits `1`.

### Examples

Minimal start with the loopback default:

```bash
python -m pip install -e '.[debug]'
magic-geo serve
# http://127.0.0.1:8642
```

Select an existing cache explicitly and move the workspace:

```bash
magic-geo export-debug --world runs/earthlike/world.json --output runs/earthlike/debug
magic-geo serve --debug-dir runs/earthlike/debug --workspace runs/earthlike
```

Configure entirely from the environment (this is how the Docker deployment is wired from `.env`):

```bash
export MAGIC_GEO_WORKSPACE=/app/runs
export MAGIC_GEO_HOST=0.0.0.0
export MAGIC_GEO_PORT=8642
magic-geo serve
```

Explicit flags win over the environment:

```bash
MAGIC_GEO_PORT=9000 magic-geo serve --port 8642   # binds 8642
```

---

## Recipes

### 1. Config to validated world to map, with no pre-existing files

```bash
magic-geo init-config                                  # writes ./magic-geo.yaml (earthlike)
magic-geo backend                                      # confirm the native core loads
magic-geo generate --output runs/world.json            # reads ./magic-geo.yaml
magic-geo validate --world runs/world.json             # exits 1 on any consistency failure
magic-geo render --world runs/world.json --output runs/world.svg --projection mollweide --labels
```

### 2. Fast smoke loop

`smoke` is the small deterministic CPU profile; a 128-cell run completed in well under a second in this checkout.

```bash
magic-geo init-config --profile smoke --output runs/configs/smoke.yaml --force
magic-geo generate -c runs/configs/smoke.yaml -o runs/smoke/world.json --summary runs/smoke/summary.md
magic-geo validate -w runs/smoke/world.json
magic-geo validate-geo -w runs/smoke/world.json --profile generic -o runs/smoke/geo.json
```

### 3. Geo-only pipeline (natural systems, no civilization layers)

```bash
magic-geo generate --geo-only \
  --config configs/earthlike_seed.yaml \
  --output runs/earthlike/geo-world.mgeo

magic-geo validate-geo \
  --world runs/earthlike/geo-world.mgeo \
  --profile earthlike \
  --output runs/earthlike/geo-validation.json \
  --fail-on-warnings
```

`--geo-only` sets `generation_scope: geo_only` in the payload; `validate-geo` is the matching gate, since `validate` also checks settlement, political, historical, market, and language layers that a geo-only world does not contain.

### 4. Full external calibration sweep

```bash
# derive from the checked-in synthetic fixtures first (no downloads required)
magic-geo derive-targets --sources configs/calibration_sources.example.json \
  --output runs/example_targets.json
magic-geo calibrate --world runs/world.json --targets runs/example_targets.json \
  --output runs/calibration.json --require-all-metrics

# then the real bundles
for ds in natural_earth_110m etopo_2022_1deg worldclim_2_1_10m hydrobasins_level3 hydrorivers_v10; do
  bash "scripts/fetch_${ds}.sh"
  magic-geo derive-targets --sources "configs/calibration_sources.${ds}.json" \
    --output "runs/${ds}_targets.json"
  magic-geo calibrate --world runs/world.json --targets "runs/${ds}_targets.json" \
    --output "runs/${ds}_calibration.json" --require-all-metrics
done
```

Then widen to an ensemble so a single lucky seed cannot carry the verdict:

```bash
magic-geo calibrate-ensemble \
  --config configs/earthlike_seed.yaml \
  --matrix configs/calibration_ensemble.r1.json \
  -t runs/natural_earth_110m_targets.json \
  -t runs/etopo_2022_1deg_targets.json \
  -t runs/worldclim_2_1_10m_targets.json \
  -t configs/calibration_targets.seton_2020_oceanic_age.json \
  --output runs/calibration_ensemble.json \
  --summary runs/calibration_ensemble.md \
  --require-all-metrics
```

### 5. Debug, visualize, and serve

```bash
magic-geo export-debug --world runs/world.json --output runs/debug
magic-geo export-debug-map -d runs/debug --layer cells/elevation_m --projection mollweide \
  --output runs/elevation-reference
magic-geo export-rerun --world runs/world.json --output runs/world.rrd
magic-geo serve --workspace runs           # auto-loads runs/debug because manifest.json exists
```

### 6. Fast serialization path

Every world-consuming command accepts either format; only the suffix changes.

```bash
magic-geo generate --config configs/earthlike_seed.yaml --output runs/world.mgeo
magic-geo validate --world runs/world.mgeo
magic-geo render --world runs/world.mgeo --output runs/world.svg
magic-geo export-debug --world runs/world.mgeo --output runs/debug
```

The README reports that on a local 4,096-cell artifact the trusted generated-world path made `.mgeo` 50.2% smaller, 3.92x faster to save, and 2.60x faster to load **in a single benchmark** — treat it as one measurement, not a calibrated performance claim.

### 7. Regression gate in CI

```bash
set -euo pipefail
magic-geo init-config --profile earthlike --output runs/ci.yaml --force
magic-geo generate -c runs/ci.yaml -o runs/ci/world.mgeo --cells 1024
magic-geo validate -w runs/ci/world.mgeo
magic-geo validate-geo -w runs/ci/world.mgeo --profile earthlike \
  -o runs/ci/geo.json --fail-on-warnings
magic-geo calibrate -w runs/ci/world.mgeo -t configs/calibration_targets.seton_2020_oceanic_age.json \
  -o runs/ci/calibration.json --require-all-metrics
```

Because `--require-all-*` policies write their report before exiting nonzero, the JSON artifacts are always available for CI upload even on a red build.

### 8. Docker

```bash
cp .env.example .env
mkdir -p worlds
docker compose up --build -d
# web workbench: http://127.0.0.1:8642

docker compose run --rm magic-geo generate \
  --config configs/earthlike_seed.yaml --output runs/world.json
docker compose run --rm magic-geo backend
```

---

## Limitations and unresolved claims

- **`validate` masks diagnostics behind its schema gate.** The schema-version, retired-field, and planet-parameter block exits `1` before any other check runs (`src/magic_geo/cli/commands/validate.py:119-122`). A `schema_version` mismatch will therefore report exactly one failure even if the world has many.
- **`validate` produces no machine-readable artifact.** It has a single option (`--world`) and no report file, no severity policy, and no per-domain toggles. Only `validate-geo` and `validate-geo-suite` emit structured reports.
- **Internal contract integrity is not Earth realism.** The geo report carries `"Earth empirical fit remains a separate calibration verdict from internal contract integrity"` in its `model_limitations` list (`src/magic_geo/geo_validation.py:40`). A world can pass `validate` and `validate-geo` and still fail `calibrate`.
- **`magic-geo backend` reports non-authoritative shadow state.** `crust_overlap_continuous_shadow_authoritative`, `crust_overlap_continuous_shadow_result_used_for_state`, `crust_overlap_accelerator_state_authoritative`, and `crust_overlap_accelerator_complete_parity_demonstrated` were all `false` on this host. The accelerator shadow reduces the exact CPU CSR into continuous moments, validates against finite operation-derived bounds, records telemetry, and **discards** the result; geometry, coverage, membership classes, categories, and production state remain CPU-authoritative, and complete accelerator parity is explicitly false. This host has no device-run evidence for the shadow.
- **Simulation-clock output carries no calibrated physical time.** The geo report's limitations state that "the simulation clock orders procedural stages but has no calibrated physical duration". `--stage` in `export-debug-map` and the `stage` timeline in `export-rerun` index procedural stages, not calibrated ages.
- **Subduction polarity and material provenance are unresolved.** The plate-boundary ledger records only a *candidate* subducting side with `unknown` physical fields, source `none`, and zero confidence; the overlap candidate-fate crosswalk accounts for excess area without resolving fragment-to-segment links, allocation, fate, or slab transfer. Nothing in the CLI upgrades those diagnostics into resolved physics.
- **`validate-geo` warnings are non-fatal by default.** Warning-severity realism diagnostics do not fail the command unless `--fail-on-warnings` is passed, and `not_applicable` checks are neither passes nor failures.
- **`--require-all-passed` on `calibrate` treats "zero checks" as failure** (`src/magic_geo/cli/commands/calibrate.py:88`), which is deliberate but easy to misread as a fit failure when the real problem is an empty target bundle.
- **`configs/calibration_sources.example.json` is synthetic.** Its own `description` field says the grids are contract fixtures and must be replaced with real ETOPO, WorldClim, HydroSHEDS, and Natural Earth-derived artifacts for empirical calibration. Targets derived from it are a plumbing test, not evidence.
- **The workbench has no authentication or user isolation.** `serve` binds `127.0.0.1` by default for that reason; the workspace containment check is a path-confinement guard, not an access-control mechanism.
- **`--cells` bounds are split across two layers.** Click enforces only `>= 128`; the `<= 200000` schema cap surfaces later as a pydantic validation error with exit `2` rather than as a Click usage error.
- **PPM output is uncompressed and unindexed.** `render-raster` is dependency-free by design; there is no built-in PNG/GeoTIFF map output from the CLI (the PNG produced by `export-debug-map` is a debug-cache layer render, not a cartographic map export).
- **Counts observed in this checkout are checkout-specific.** The 428 debug-cache layers and 149 `validate-geo` checks above come from a 128-cell smoke world on this host and will differ with resolution and scope; the 178 `backend` keys depend on the native build and probe result. The 397 cells-CSV columns are the exception — that header is a fixed literal list in `cells_csv.py` and does not vary with the world.

---

## See also

- [Configuration Reference](./05-configuration-reference.md) — every YAML field, constraint, profile, and override rule that `init-config` and `generate` consume.
- [Quickstart](./03-quickstart.md) — the shortest path from install to a rendered map.
- [Installation and Build](./02-installation-and-build.md) — staging `libmagic_geo_native.so` so `magic-geo backend` succeeds.
- [Python API](./07-python-api.md) — the in-process equivalents of every command (`generate_world`, `validate_geo_world`, `evaluate_calibration_targets`, `export_debug_cache`, …).
- [Validation](./12-validation.md) — what the full `validate` gate actually checks.
- [Geo Validation Suite](./13-geo-validation-suite.md) — the scenario matrix, paired relations, and empirical policy behind `validate-geo-suite`.
- [Calibration Against Real-Earth Data](./14-calibration.md) — target derivation, source manifests, and ensemble methodology.
- [Serialization and World Formats](./11-serialization.md) — `.mgeo` container format, suffix and magic-byte detection, and size limits.
- [Rendering and Map Output](./17-rendering.md) — projections, palettes, and layer semantics for `render`/`render-raster`.
- [Debug Exports and Visualization](./16-debug-and-visualization.md) — debug-cache layout, layer kinds, and the Rerun recording.
- [Web Workbench](./15-web-workbench.md) — what `serve` hosts and how workspace rooting behaves in the browser.
- [Compute Backends (CPU, OpenCL, CUDA)](./09-compute-backends.md) — how to read `magic-geo backend` output.
- [Docker Deployment](./19-docker-deployment.md) — `.env` reference and running CLI subcommands inside the image.
- [Example Seeds and Presets](./20-seed-gallery.md) — the nine checked-in `configs/seeds/*.yaml` presets.
- [Troubleshooting and FAQ](./22-troubleshooting.md) — common exit-`2` causes and missing-dependency messages.
