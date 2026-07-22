# Troubleshooting and FAQ

[Wiki home](./README.md) > Troubleshooting and FAQ

This page collects the failure modes you can actually hit in `magic-geo`, organized by the layer that raises them: the CMake/native build, the `ctypes` boundary, the Pydantic configuration model, the C++ parameter/pipeline guards, backend selection, serialization, the validation commands, the web workbench and its job manager, the debug cache, calibration data, and the test suites. Every quoted message below is a literal string found in the source (or captured from a real run on the development host); the tables give the exact symptom, where it is raised, why, and what to change. Nothing here upgrades a hedged claim: where the engine marks a result non-authoritative, unresolved, or uncalibrated, the troubleshooting advice says so too.

## On this page

- [How to read this page](#how-to-read-this-page)
- [Exit codes and error surfaces](#exit-codes-and-error-surfaces)
- [Build and native-library loading](#build-and-native-library-loading)
- [Configuration errors](#configuration-errors)
- [Generation failures and constraint violations](#generation-failures-and-constraint-violations)
- [Compute backend selection surprises](#compute-backend-selection-surprises)
- [Memory and payload size at large cell counts](#memory-and-payload-size-at-large-cell-counts)
- [World file and serialization errors](#world-file-and-serialization-errors)
- [Validation command failures](#validation-command-failures)
- [Web workbench and job failures](#web-workbench-and-job-failures)
- [Debug cache, stale revisions, and exports](#debug-cache-stale-revisions-and-exports)
- [Calibration data and target derivation](#calibration-data-and-target-derivation)
- [Test failures and skips](#test-failures-and-skips)
- [FAQ](#faq)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

---

## How to read this page

`magic-geo` has four distinct places a run can fail, and the message text tells you which one you are in:

| Layer | Typical message shape | Raised from | What it means |
|---|---|---|---|
| Typer/Click argument parsing | `Invalid value for '--config' / '-c': Path 'nope.yaml' does not exist.` inside a boxed `Error` panel | Typer built-ins on `exists=True`, `IntRange`, `FloatRange` | A flag was mistyped or a path does not exist; nothing ran |
| Python configuration model | `configuration validation failed:` followed by `  - <path>: <message>` bullets, or a bare `ConfigError` string | `src/magic_geo/config.py:532` `_config_validation_error` | The YAML parsed but violates the Pydantic schema |
| Native `ctypes` boundary | `native library ...`, `MAGIC_GEO_NATIVE_LIBRARY does not name a file: ...` | `src/magic_geo/native.py` | The shared library is missing, stale, or returned something the Python layer refuses to accept |
| C++ engine guards | short lowercase sentences such as `cell_count must be between 128 and 200000` | `cpp/src/engine/core.cpp`, `cpp/src/engine/pipeline.cpp`, and domain TUs; surfaced through the C ABI error envelope and re-raised as `RuntimeError` | A parameter or an internal invariant was rejected inside the simulation |

A fifth surface exists only in the browser: the FastAPI workbench returns HTTP status codes with a `detail` field (`src/magic_geo/debug_server.py`), and its background jobs raise `JobInputError` (`src/magic_geo/web_jobs.py:338`) which becomes HTTP 422.

The C ABI wraps every entry point in `try`/`catch`, converting `std::exception::what()` into a JSON error envelope (`cpp/src/c_api.cpp`); `src/magic_geo/native.py:179-180` and `:229-230` detect the `"error"` key and re-raise it as a Python `RuntimeError` carrying the original C++ text. That is why engine messages reach you verbatim.

---

## Exit codes and error surfaces

There are no global CLI options: `typer.Typer(no_args_is_help=True, help="Causal planet generator CLI.")` at `src/magic_geo/cli/_app.py:13` declares no `@app.callback`, so only `--install-completion`, `--show-completion`, and `--help` exist outside a subcommand.

| Exit code | Meaning | Examples |
|---|---|---|
| `0` | Success | `magic-geo validate --world w.json` printing `OK` (`src/magic_geo/cli/commands/validate.py:22333`) |
| `1` | Semantic failure after the command ran | `validate` accumulated failures; `validate-geo` policy failure; `validate-geo-suite` failed scenarios; `calibrate`/`calibrate-ensemble` policy gates. Also the default code for an *unhandled* Python exception (e.g. a `RuntimeError` from `magic-geo backend`) |
| `2` | Usage error, world-load error, missing optional dependency, or a caught configuration/generation error | Missing required option, `exists=True` path absent, out-of-range `IntRange`, `typer.BadParameter`, bare `magic-geo` with no subcommand, `Invalid world file: ...`, `pip install 'magic-geo[debug]'` hints |

Verified on the development host:

```console
$ magic-geo                       ; echo $?      # no_args_is_help
2
$ magic-geo generate --config nope.yaml ; echo $?
2
$ magic-geo validate --world bad.json   ; echo $?
1
```

The shared world loader is the single source of the exit-2 load path:

```python
# src/magic_geo/cli/_app.py:16-23
def _load_world_for_cli(path: Path) -> dict[str, Any]:
    try:
        return read_world(path)
    except (OSError, UnicodeError, ValueError) as exc:
        typer.echo(f"Invalid world file: {exc}", err=True)
        raise typer.Exit(2) from exc
```

It is used by `validate`, `validate-geo`, `calibrate`, `render`, `render-raster`, `export-debug`, and `export-rerun`. `WorldSerializationError` subclasses `ValueError` (`src/magic_geo/serialization.py:48-49`), so every framing/limit/checksum error surfaces through that one line.

---

## Build and native-library loading

### Symptoms and fixes

| Symptom (exact text) | Raised at | Cause | Fix |
|---|---|---|---|
| `native library was not found. Build it with: cmake -S . -B build && cmake --build build` | `src/magic_geo/native.py:124-127` | No `libmagic_geo_native.so` / `magic_geo_native.dll` / `libmagic_geo_native.dylib` beside `src/magic_geo/`, and `MAGIC_GEO_NATIVE_LIBRARY` is unset | Run `cmake -S . -B build && cmake --build build`. The library is staged into `MAGIC_GEO_LIBRARY_OUTPUT_DIRECTORY`, which defaults to `${CMAKE_CURRENT_SOURCE_DIR}/src/magic_geo` (`CMakeLists.txt:84-88`) |
| `MAGIC_GEO_NATIVE_LIBRARY does not name a file: /nope/lib.so` | `src/magic_geo/native.py:115-117` | The override env var is set but does not point at an existing file | Unset it, or point it at the built shared library. Note the value is `expanduser().resolve()`d first |
| `OSError: /path/to/file: invalid ELF header` (or a platform equivalent) | `ctypes.CDLL(...)` at `src/magic_geo/native.py:131` | `MAGIC_GEO_NATIVE_LIBRARY` points at a file that is not a loadable shared object for this host | Point it at a real library built for this OS/architecture |
| `native library does not expose the current V3 JSON and MessagePack ABI; rebuild magic_geo_native from the current source tree` | `src/magic_geo/native.py:140-144` | A stale `.so`/`.dll`/`.dylib` is present but is missing one of the seven required symbols | Rebuild. The seven resolved symbols are `magic_geo_backend_info_json`, `magic_geo_generate_json_v3`, `magic_geo_generate_geo_json_v3`, `magic_geo_generate_msgpack_v3`, `magic_geo_generate_geo_msgpack_v3`, `magic_geo_free_string`, `magic_geo_free_buffer` (`src/magic_geo/native.py:133-139`) |
| `native library returned unsupported world schema_version 1; expected 2; rebuild magic_geo_native from the current source tree` | `src/magic_geo/native.py:236-241` | The library builds and loads but emits an older world schema | Rebuild the native core from the current tree. `CURRENT_WORLD_SCHEMA_VERSION = 2` (`src/magic_geo/serialization.py:27`) |
| `native library returned retired fields in a schema-2 world: <names>` | `src/magic_geo/native.py:243-247` | The library emits fields listed in `retired_world_schema_fields` (`src/magic_geo/serialization.py:68-234`) | Rebuild; a mixed-generation tree is being loaded |
| `cannot build a wheel without <path>/libmagic_geo_native.so; build the native Release target with CMake first` | `setup.py:50-53` | `pip wheel`/`python -m build` was run before CMake staged the library | Build the native Release target first: `cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build` |
| `the staged native core is incompatible with this build host or package: <path>: <exc>` | `setup.py:66-70` | The staged library exists but `ctypes.CDLL` or one of the seven ABI symbol lookups failed | Rebuild from the current source tree on this host |
| CMake: `magic-geo CUDA backend disabled: CUDA runtime development files were not found; building runtime stub` | `CMakeLists.txt:47-51` | `nvcc` >= 12.8 exists, but `find_package(CUDAToolkit 12.8 QUIET)` failed | Install the CUDA toolkit development files, or accept the CPU/OpenMP core with a CUDA stub |
| CMake: `magic-geo CUDA backend disabled: CUDA <version> cannot compile sm_120; CUDA 12.8+ is required` | `CMakeLists.txt:53-58` | `nvcc` older than 12.8 | Upgrade the toolkit, or set `-DMAGIC_GEO_ENABLE_CUDA=OFF` to silence it |
| CMake: `magic-geo CUDA backend disabled: compiler '<id>' is not supported; NVIDIA nvcc 12.8+ is required` | `CMakeLists.txt:59-64` | `CMAKE_CUDA_COMPILER_ID` is not `NVIDIA` (e.g. Clang CUDA) | Point CMake at NVIDIA `nvcc`, or disable CUDA |
| CMake: `magic-geo CUDA backend: compiler not found; building runtime stub` | `CMakeLists.txt:65` | No CUDA compiler on `PATH` | Informational only; the stub build is fully usable for CPU and OpenCL |
| Runtime: `CUDA backend is unavailable because this build was compiled without CUDA support` | `cpp/src/cuda_compute_stub.cpp:8-12` | A CUDA code path was reached in a stub build | Rebuild with CUDA, or do not request the CUDA backend |

### Why a Debug build "does nothing"

`CMakeLists.txt:152-186` deliberately isolates non-Release configurations. When `MAGIC_GEO_LIBRARY_OUTPUT_DIRECTORY` still equals the package directory `src/magic_geo`:

- `LIBRARY_OUTPUT_DIRECTORY_RELEASE` / `RUNTIME_OUTPUT_DIRECTORY_RELEASE` are pinned to `src/magic_geo` so multi-config generators (Windows, macOS) do not append a config subdirectory.
- `Debug`, `RelWithDebInfo`, and `MinSizeRel` are redirected to `${CMAKE_CURRENT_BINARY_DIR}/native/<Config>/`.

So a `Debug` build **will not** replace the library that Python loads. That is intentional (a non-Release artifact must not overwrite the packaged Release one). To test a Debug build from Python, set `MAGIC_GEO_NATIVE_LIBRARY=<build>/native/Debug/libmagic_geo_native.so`, or configure a separate tree with an explicit `-DMAGIC_GEO_LIBRARY_OUTPUT_DIRECTORY=<dir>` (an explicitly supplied output directory stays caller-controlled).

`CMAKE_BUILD_TYPE` defaults to `Release` when neither it nor `CMAKE_CONFIGURATION_TYPES` is set (`CMakeLists.txt:70-73`).

### Library resolution order

```
MAGIC_GEO_NATIVE_LIBRARY set?
  yes -> Path(override).expanduser().resolve(); must be a file       # native.py:111-118
  no  -> Path(__file__).resolve().parent / <host-native filename>    # native.py:119-123
         win32   -> magic_geo_native.dll
         darwin  -> libmagic_geo_native.dylib
         other   -> libmagic_geo_native.so                            # native.py:30-37
  neither -> RuntimeError("native library was not found. ...")        # native.py:124-127
```

There is deliberately **no cross-platform name fallback**: `_native_library_names()` returns only the host-native filename. Copying a `.dll` onto Linux will not be picked up.

`_load_library()` is called on **every** public call (`backend_info`, `generate_world`, `generate_geo_world`) — there is no module-level cache. That keeps a rebuilt library visible without restarting the process, at the cost of one `dlopen` per call.

### Confirming a healthy install

```bash
magic-geo backend            # prints the full backend probe as sorted JSON
```

`magic-geo backend` takes no options at all (`src/magic_geo/cli/commands/config.py:52-55`) and prints `json.dumps(backend_info(), indent=2, sort_keys=True)`. If the native core is missing, this command raises the `RuntimeError` above as an *unhandled* exception — you get a Python traceback and **exit code 1**, not the usual exit 2.

---

## Configuration errors

The configuration model is `WorldConfig` (`src/magic_geo/config.py:458-504`): nine sections, every model declaring `ConfigDict(extra="forbid", allow_inf_nan=False)`.

### YAML-level failures

| Symptom (exact text) | Raised at | Cause | Fix |
|---|---|---|---|
| `<source>:<line>:<col>: invalid YAML: <problem>` | `src/magic_geo/config.py:593-600` and `:623-631` | PyYAML syntax error; the mark is converted to one-based line/column | Fix the YAML syntax at the reported position |
| `<source>: invalid or excessively complex YAML: <exc>` | `src/magic_geo/config.py:601-602` | `RecursionError`, `MemoryError`, `ValueError`, or `OverflowError` while parsing | Simplify the document |
| `<source>: YAML exceeds the 20000 event complexity limit` | `src/magic_geo/config.py:570-574` (`MAX_YAML_EVENTS = 20_000`, `:35`) | Pathologically large document | Split or shrink the config |
| `<source>: YAML nesting exceeds the 64-level limit` | `src/magic_geo/config.py:577-581` (`MAX_YAML_NESTING_DEPTH = 64`, `:34`) | Deeply nested structure | Flatten the document |
| `<source>: YAML exceeds the 64 alias limit` | `src/magic_geo/config.py:586-590` (`MAX_YAML_ALIASES = 64`, `:36`) | Anchor/alias expansion bomb | Remove aliases |
| `<source>: YAML text must be well-formed UTF-8 Unicode` | `src/magic_geo/config.py:560-563` | Surrogates or otherwise non-encodable text | Save the file as valid UTF-8 |
| `while constructing a mapping ... found duplicate key '<key>'` | `src/magic_geo/config.py:107-113` via `_UniqueKeySafeLoader` | The same key appears twice in a mapping — PyYAML would silently keep the last one, this loader refuses | Remove the duplicate |
| `<source>: config root must be a YAML mapping` | `src/magic_geo/config.py:637-649` | The document is a list or scalar | Make the top level a mapping. An **empty** document is legal and equals the `default` profile (`:635-636`) |

### Schema-level failures

Pydantic errors are reformatted into one `ConfigError` with a bullet list (`src/magic_geo/config.py:532-554`):

```
<source>: configuration validation failed:
  - <dotted.path>: <message>
```

`ConfigError.to_dict()` (`:70-82`) returns `{message, source, issues[], line?, column?}` — the web layer returns exactly that as an HTTP 422 body, so CLI and browser see the same structured error.

The complete bound table (all limits verified in `src/magic_geo/config.py`):

| Section.field | Default | Bound | Line |
|---|---|---|---|
| `run.seed` | `424242` | `0 <= x <= 2**64-1` (`MAX_SEED`) | `:129-134` |
| `run.name` | `earthlike_mvp` | 1–256 chars; no NUL; UTF-8 encodable; <= 1024 UTF-8 bytes | `:135-153` |
| `planet.radius_km` | `6371.0` | `100.0 < x <= 100000.0` | `:161-166` |
| `planet.gravity_g` | `1.0` | `0.05 < x < 5.0` | `:167-172` |
| `planet.day_length_hours` | `24.0` | `1.0 < x <= 10000.0` | `:173-178` |
| `planet.axial_tilt_deg` | `23.5` | `0.0 <= x <= 90.0` | `:179-184` |
| `planet.orbital_eccentricity` | `0.016` | `0.0 <= x < 1.0` | `:185-190` |
| `planet.stellar_luminosity` | `1.0` | `0.01 < x <= 100.0` | `:191-196` |
| `planet.atmosphere_pressure_bar` | `1.0` | `0.0 <= x <= 1000.0` | `:197-202` |
| `planet.greenhouse_factor` | `1.0` | `0.0 <= x <= 100.0` | `:203-208` |
| `planet.ocean_fraction_target` | `0.70` | `0.0 <= x <= 0.95` | `:209-214` |
| `planet.ocean_water_inventory_km3` | `1338000000.0` | `0.0 <= x <= 1.0e10` | `:215-220` |
| `planet.internal_heat` | `1.0` | `0.0 <= x <= 100.0` | `:221-226` |
| `planet.geological_age_ga` | `4.5` | `0.01 <= x <= 100.0` | `:227-232` |
| `mesh.backend` | `fibonacci_sphere` | `fibonacci_sphere` \| `geodesic_icosahedron` | `:240-243` |
| `mesh.cell_count` | `4096` | `128 <= x <= 200000` | `:244-249` |
| `mesh.neighbor_count` | `7` | `4 <= x <= 16` | `:250-255` |
| `tectonics.plate_count` | `14` | `2 <= x <= 256`, and `< mesh.cell_count` | `:263-268`, `:500-504` |
| `tectonics.continental_plate_fraction` | `0.38` | `0.0 <= x <= 1.0` | `:269-274` |
| `tectonics.continental_crust_fraction_target` | `0.34` | `0.0 <= x <= 0.95` | `:275-280` |
| `tectonics.min_angular_speed` | `0.03` | `0.0 <= x <= 100.0` | `:281-286` |
| `tectonics.max_angular_speed` | `0.95` | `0.0 <= x <= 100.0`, and `>= min_angular_speed` | `:287-292`, `:312-316` |
| `tectonics.boundary_smoothing_steps` | `5` | `0 <= x <= 32` | `:293-298` |
| `tectonics.plate_motion_scale_deg_per_step` | `2.0` | `0.0 <= x <= 10.0` | `:299-304` |
| `tectonics.oceanic_crust_aging_ma_per_step` | `5.0` | `0.0 <= x <= 50.0` | `:305-310` |
| `climate.months` | `12` | literally `12` only | `:324-327` |
| `climate.lapse_rate_c_per_km` | `6.5` | `0.0 <= x <= 15.0` | `:328-333` |
| `climate.base_temperature_c` | `15.0` | `-100.0 <= x <= 100.0` | `:334-339` |
| `climate.precipitation_scale` | `1.0` | `0.0 <= x <= 10.0` | `:340-345` |
| `climate.subtropical_drying_strength` | `0.65` | `0.0 <= x <= 0.9` | `:346-351` |
| `hydrology.river_percentile` | `0.92` | `0.50 <= x <= 0.995` | `:359-364` |
| `hydrology.preserve_geologic_depressions` | `true` | bool | `:365-368` |
| `erosion.iterations` | `6` | `0 <= x <= 250` | `:376-381` |
| `erosion.maturation_timestep_ma` | `5.0` | `0.0 < x <= 5.0` | `:382-387` |
| `erosion.stream_power_coefficient` | `7.5` | `0.0 <= x <= 1000.0` | `:388-393` |
| `erosion.drainage_exponent` | `0.5` | `0.0 <= x <= 2.0` | `:394-399` |
| `erosion.slope_exponent` | `1.0` | `0.0 <= x <= 3.0` | `:400-405` |
| `erosion.hillslope_diffusion` | `0.055` | `0.0 <= x <= 1.0` | `:406-411` |
| `erosion.tectonic_uplift_scale` | `0.85` | `0.0 <= x <= 10.0` | `:412-417` |
| `compute.backend` | `auto` | `auto` \| `cpu` \| `opencl` \| `cuda` | `:425-428` |
| `compute.threads` | `0` | `0 <= x <= 1024` (`MAX_COMPUTE_THREADS`) | `:429-434` |
| `compute.opencl_prefer_gpu` | `true` | bool | `:435-438` |
| `output.include_cells` | `true` | bool | `:446-449` |
| `output.float_precision` | `4` | `0 <= x <= 8` | `:450-455` |

Two cross-field validators fire only *after* every field validates:

- `validate_speeds` (`:312-316`): `max_angular_speed must be >= min_angular_speed`
- `validate_plate_density` (`:500-504`): `plate_count must be smaller than mesh.cell_count`

Because these are model-level validators, they report at path `<root>`:

```console
$ magic-geo init-config --profile smoke -o smoke.yaml --set tectonics.plate_count=256
Invalid value: <overrides>: configuration validation failed:
  - <root>: Value error, plate_count must be smaller than mesh.cell_count
$ echo $?
2
```

### Override and profile failures

| Symptom (exact text) | Raised at | Cause | Fix |
|---|---|---|---|
| `<override>: override '<text>' must use section.field=value` | `src/magic_geo/config.py:676-680` | `--set` value has no `=` | Use `--set section.field=VALUE` |
| `<override>: override path cannot be empty` | `src/magic_geo/config.py:683-689` | `--set =3` | Supply a dotted path |
| `<override>: duplicate configuration override '<path>'` | `src/magic_geo/config.py:683-689` | The same dotted path was given twice | Pass it once |
| `<override>: invalid YAML value for override '<path>': <exc>` | `src/magic_geo/config.py:695-699` | Right-hand side is not parseable YAML | Quote it correctly. Values use YAML scalar syntax, so `false`, `128`, and `geodesic_icosahedron` keep their types (`:665-672`) |
| `<overrides>: override path '<path>' must identify a dotted field` | `src/magic_geo/config.py:727-731` | Fewer than two path components, or an empty component | Use `section.field` |
| `<overrides>: unknown configuration override '<path>'` | `src/magic_geo/config.py:736-748` | The path does not exist, or names a whole section rather than a leaf | Check the field table above; whole-section replacement is intentionally rejected |
| `<profile>: unknown configuration profile 'bogus'; choose one of: default, earthlike, smoke` | `src/magic_geo/config.py:760-765` | Bad `--profile` on `init-config` | Use one of the three profiles (`:513-529`) |
| `<target> already exists; pass --force to overwrite` | `src/magic_geo/config.py:804-805` (early check) and `:819-822` (atomic race) | Writing over an existing config | Add `--force`, or choose a different `-o` |

`write_config` is atomic and self-checking (`src/magic_geo/config.py:800-826`): it writes a `.{name}.{uuid4}.tmp` sibling, **re-parses the temporary file** before committing, then either `os.replace` (with `--force`) or `os.link` (without). The hard link makes a concurrent creation of the target raise `FileExistsError` instead of silently clobbering it.

The three built-in profiles (`src/magic_geo/config.py:507-529`):

| Profile | Description | Overrides applied on top of schema defaults |
|---|---|---|
| `default` | `Schema defaults suitable as a neutral editable starting point.` | none |
| `earthlike` | `Calibrated 4,096-cell Earth-like reference configuration.` | `tectonics.plate_motion_scale_deg_per_step: 4.0`, `climate.precipitation_scale: 0.8` |
| `smoke` | `Small deterministic CPU configuration for fast integration checks.` | `run.name: smoke`, `mesh.cell_count: 128`, `tectonics.plate_count: 8`, `tectonics.plate_motion_scale_deg_per_step: 4.0`, `climate.precipitation_scale: 0.8`, `erosion.iterations: 1`, `compute.backend: cpu`, `compute.threads: 1` |

`init-config` defaults to `--profile earthlike` (`src/magic_geo/cli/commands/config.py:21-28`), while the Python `create_config()` default is `"default"` (`src/magic_geo/config.py:754-757`). That asymmetry is real; do not assume they match.

`load_config` deliberately does **not** wrap read errors: "Preserve the original `Path.read_text` exception contract (for example `FileNotFoundError` and `PermissionError`); `ConfigError` is reserved for YAML and model validation failures after bytes have been read successfully" (`src/magic_geo/config.py:833-836`).

---

## Generation failures and constraint violations

### The `plate_count` versus cell-count family

There are **three** distinct guards, and they fire in this order:

| Guard | Message | Location | When |
|---|---|---|---|
| Pydantic model validator | `plate_count must be smaller than mesh.cell_count` | `src/magic_geo/config.py:502-504` | At config validation, before any native call |
| Native parameter validation | `plate_count must be between 2 and 256 and smaller than cell_count` | `cpp/src/engine/core.cpp:295-301` | Inside `validate_params`, before mesh construction |
| Pipeline post-mesh guard | `plate_count must be smaller than generated mesh cell count` | `cpp/src/engine/pipeline.cpp:13-15` | After `build_mesh`, comparing against the **generated** count, not the requested one |

The third is a defence-in-depth check against a mesh backend producing a different count than requested. It is the only one that references the *generated* mesh.

The `--cells` override on `generate` re-runs the whole model validation, so it can trip the first guard even though the file on disk was fine:

```console
$ magic-geo init-config --profile default -o d.yaml \
    --set tectonics.plate_count=200 --set mesh.cell_count=1024
$ magic-geo generate -c d.yaml --cells 128 -o x.json
1 validation error for WorldConfig
  Value error, plate_count must be smaller than mesh.cell_count [type=value_error, ...]
$ echo $?
2
```

That re-validation is `src/magic_geo/cli/commands/generate.py:49-55`: `model_dump` → mutate `data["mesh"]["cell_count"]` → `model_validate`.

### Native parameter guards (`validate_params`)

`cpp/src/engine/core.cpp:238-432`. Every one of these becomes a Python `RuntimeError` and, from `magic-geo generate`, an exit-2 message on stderr (`src/magic_geo/cli/commands/generate.py:73-75`).

| Message | Line | Notes |
|---|---|---|
| `<name> must be finite` | `:240-244` | Applied to 30 doubles via a `require_finite` lambda, including `radius_km`, `gravity_g`, `maturation_timestep_ma`, `river_percentile`, `tectonic_uplift_scale` |
| `cell_count must be between 128 and 200000` | `:287-289` | Mirrors `mesh.cell_count` |
| `unknown mesh backend` | `:290-293` | Only `0` (Fibonacci) and `1` (geodesic icosahedron) exist; `MESH_BACKEND_IDS` at `src/magic_geo/native.py:17-20` |
| `plate_count must be between 2 and 256 and smaller than cell_count` | `:295-301` | |
| `neighbor_count must be between 4 and 16` | `:302-304` | |
| `radius_km must be greater than 100 and at most 100000` | `:305-309` | |
| `gravity_g must be greater than 0.05 and less than 5` | `:310-312` | |
| `day_length_hours must be greater than 1 and at most 10000` | `:313-317` | |
| `axial_tilt_deg must be between 0 and 90` | `:318-320` | |
| `orbital_eccentricity must be at least 0 and less than 1` | `:321-323` | |
| `stellar_luminosity must be greater than 0.01 and at most 100` | `:324-328` | |
| `atmosphere_pressure_bar must be between 0 and 1000` | `:330-336` | |
| `greenhouse_factor must be between 0 and 100` | `:337-339` | |
| `ocean_fraction_target must be between 0 and 0.95` | `:340-342` | |
| `ocean_water_inventory_km3 must be between 0 and 10000000000` | `:343-350` | |
| `internal_heat must be between 0 and 100` | `:351-353` | |
| `geological_age_ga must be between 0.01 and 100` | `:354-356` | |
| `continental_plate_fraction must be between 0 and 1` | `:360-362` | |
| `angular speeds must be between 0 and 100 and max_angular_speed must be >= min_angular_speed` | `:363-372` | One combined guard; the Pydantic side splits this into a field bound plus `validate_speeds` |
| `boundary_smoothing_steps must be between 0 and 32` | `:373-375` | |
| `months must be exactly 12` | `:376-378` | |
| `plate_motion_scale_deg_per_step must be between 0 and 10` | `:379-381` | |
| `continental_crust_fraction_target must be between 0 and 0.95` | `:382-384` | |
| `oceanic_crust_aging_ma_per_step must be between 0 and 50` | `:385-387` | |
| `maturation_timestep_ma must be greater than 0 and at most 5` | `:388-390` | |
| `subtropical_drying_strength must be between 0 and 0.9` | `:391-393` | |
| `lapse_rate_c_per_km must be between 0 and 15` | `:394-396` | |
| `base_temperature_c must be between -100 and 100` | `:397-399` | |
| `precipitation_scale must be between 0 and 10` | `:400-402` | |
| `river_percentile must be between 0.5 and 0.995` | `:403-405` | |
| `erosion_iterations must be between 0 and 250` | `:406-408` | |
| `stream_power_coefficient must be between 0 and 1000` | `:412-414` | |
| `drainage_exponent must be between 0 and 2` | `:415-417` | |
| `slope_exponent must be between 0 and 3` | `:418-420` | |
| `hillslope_diffusion must be between 0 and 1` | `:421-423` | |
| `tectonic_uplift_scale must be between 0 and 10` | `:424-426` | |
| `threads must be between 0 and 1024` | `:427-429` | |
| `float_precision must be between 0 and 8` | `:430-432` | |
| `compute_backend must be auto, cpu, opencl, or cuda` | `:231-236` (`validate_compute_options`) | Raised before `validate_params` |

Reaching a native guard usually means you bypassed the Python config model (calling `magic_geo.native.generate_world` with a hand-built dict, or driving the C ABI directly). Through `magic-geo generate` the Pydantic bounds fire first.

### Marshalling failures at the `ctypes` boundary

`_native_config` (`src/magic_geo/native.py:281-341`) reads nine nested sections by name and coerces with `int()`/`float()`.

| Symptom | Cause | Fix |
|---|---|---|
| `KeyError: 'run'` (or `'planet'`, `'mesh'`, `'tectonics'`, `'climate'`, `'hydrology'`, `'erosion'`, `'compute'`, `'output'`) | A hand-built dict missing a section | Build it with `config_to_native(WorldConfig)` (`src/magic_geo/config.py:840-843`) |
| `KeyError: '<name>'` from `MESH_BACKEND_IDS[str(mesh["backend"])]` | Unknown mesh backend string | `src/magic_geo/native.py:307`; valid keys are `fibonacci_sphere`, `geodesic_icosahedron` |
| `KeyError: '<name>'` from `COMPUTE_BACKEND_IDS[str(compute["backend"])]` | Unknown compute backend string | `src/magic_geo/native.py:337`; valid keys are `auto`, `cpu`, `opencl`, `cuda` |
| `ValueError: serialization must be auto, json, or msgpack` | Bad `serialization=` keyword | `src/magic_geo/native.py:356-357` and `:382-383` |

### Runtime invariant failures inside the engine

These indicate a genuine numerical or topological breakdown rather than a bad flag. They surface as `RuntimeError` with the C++ text.

| Message | Location | Meaning |
|---|---|---|
| `numeric depression correction did not converge within the bounded pass count` | `cpp/src/engine/hydrology.cpp:1177-1179` | `stabilize_numeric_depressions` exhausted `NUMERIC_DEPRESSION_CORRECTION_MAX_PASSES = 16` (`cpp/src/engine/constants.hpp:55`) |
| `Priority-Flood routing surface rises downstream` | `cpp/src/engine/hydrology.cpp:344` | Conditioned surface monotonicity broken |
| `conditioned hydrologic surface is not downhill` | `cpp/src/engine/hydrology.cpp:362` | |
| `hydrology flow graph contains a cycle` | `cpp/src/engine/hydrology.cpp:699` | |
| `open depression unit has no spill corridor` | `cpp/src/engine/hydrology.cpp:606` | |
| `closed depression raw routing leaves its footprint` | `cpp/src/engine/hydrology.cpp:623` | |
| `attempted to serialize a non-finite simulation value` | `cpp/src/engine/core.cpp:168-176` (`num`) | A NaN/Inf reached the JSON serializer. This is a fail-closed guard: the world document is never allowed to contain non-finite numbers |
| `plate-boundary <context> is degenerate` / `plate-boundary <context> is not finite` | `cpp/src/engine/plate_boundary_segments.cpp:48-68` | Degenerate control-volume geometry |
| `plate-boundary per-cell control-volume segment cap exceeded` | `cpp/src/engine/plate_boundary_segments.cpp:235-241` | `MAX_CONTROL_VOLUME_SEGMENTS_PER_CELL = 64` (`:7`) |
| `plate-boundary reciprocal mesh segment cap exceeded` | `cpp/src/engine/plate_boundary_segments.cpp:332-338` | `MAX_RECIPROCAL_MESH_SEGMENTS_PER_CELL = 8` per cell (`:8`) |
| `crust-overlap candidate-fate boundary segment cap exceeded` | `cpp/src/engine/crust_overlap_candidate_fate.cpp:397` | `MAX_BOUNDARY_SEGMENTS_PER_CELL = 8` (`:8`) |
| `finite dry-rock accounting surface-owner packet safety limit exceeded` | `cpp/src/engine/crust_reservoir.cpp:228-232` | `CRUST_DRY_ROCK_MAX_SURFACE_PACKETS_PER_OWNER = 1024` (`cpp/src/engine/types/crust_reservoir.hpp:16`) |
| `finite dry-rock accounting live reservoir packet safety limit exceeded` | `cpp/src/engine/crust_reservoir.cpp:212-218`, `:263-267` | `CRUST_DRY_ROCK_MAX_LIVE_RESERVOIR_PACKETS = 1000000` (`types/crust_reservoir.hpp:18`) |
| `finite dry-rock accounting per-step transfer safety limit exceeded` | `cpp/src/engine/crust_reservoir.cpp:744-748` | `CRUST_DRY_ROCK_MAX_PROXY_TRANSFERS_PER_STEP = 1000000` (`types/crust_reservoir.hpp:20`) |
| `crust material shadow source packet allocation exceeded its forward-error bound` | `cpp/src/engine/crust_material.cpp:704` | The **non-authoritative** dry-rock mass shadow failed its own error bound |
| `crust material shadow/raw transported mass difference exceeded its geometry bound` | `cpp/src/engine/crust_material.cpp:799` | Same shadow; see the caveat below |

The last two belong to the crust material shadow, which the engine documents as a non-authoritative sparse dry-rock mass shadow with `physical_basis_resolved = false` on every reservoir transfer. A failure there is a real internal-consistency failure of the shadow bookkeeping; it is **not** evidence about physical mass provenance, which the project marks unresolved.

The three dry-rock packet caps are described in the engine README (`cpp/src/engine/README.md:321-324`) as "fail-closed operational caps: 1,024 packets per surface owner, 1,000,000 packets across live reservoirs, and 1,000,000 transfers per step", and it states outright that "they are numerical memory-safety limits, not physical flux or capacity limits". The plate-boundary and candidate-fate segment caps (`MAX_CONTROL_VOLUME_SEGMENTS_PER_CELL`, `MAX_RECIPROCAL_MESH_SEGMENTS_PER_CELL`, `MAX_BOUNDARY_SEGMENTS_PER_CELL`) are the same kind of construct. Hitting any of them is a resource/topology limit, not a statement about the planet.

### The mesh-count surprise (`geodesic_icosahedron`)

`mesh.cell_count` is a **target**, not a guarantee, for the geodesic backend. `geodesic_frequency_for_target` (`cpp/src/engine/mesh.cpp:840-844`) computes `f = max(1, ceil(sqrt((max(12, cell_count) - 2) / 10)))` and the mesh then has `10*f^2 + 2` points (`:907-909`).

Measured on this host (`--geo-only`, `erosion.iterations: 0`):

| Requested `mesh.cell_count` | Generated `summary.cell_count` |
|---|---|
| 128 | 162 |
| 512 | 642 |
| 4096 | 4412 |

The Fibonacci backend produces exactly `params.cell_count` cells (`cpp/src/engine/mesh.cpp:777`). If you compare runs across backends, compare `summary.cell_count`, not the config value. This also matters for automatic backend selection, which uses the generated mesh size (see below).

### `output.include_cells: false`

`generate_geo_world` refuses it outright:

```
generate_geo_world requires output.include_cells=true because natural enrichers
and layer validation consume per-cell state
```

(`src/magic_geo/api.py:296-300`, a `ValueError`.)

The full-world path does **not** refuse it. Verified: `generate_world` with `output.include_cells: false` succeeds and returns a world whose `cells` key exists but is an empty list. Everything downstream then fails:

```console
$ magic-geo validate --world nocells.json
FAIL cell_count does not match cells length
FAIL sea level model metadata or connectivity invalid
FAIL hydrology flow routing or accumulation invalid
FAIL hydrology depression components or lake basin aggregation invalid
FAIL climate model metadata invalid
FAIL simulation clock or earth-system feedback history invalid
...
$ magic-geo export-debug --world nocells.json --output dbg2
world payload has no cells; generate with output.include_cells enabled
```

The export message is `src/magic_geo/debug_export.py:833`. Keep `output.include_cells: true` unless you specifically want a cell-free summary payload and intend to skip validation, debug export, rendering, and the workbench.

### Planet snapshot mismatch

```
native planet_parameters do not match the configured planet snapshot
```

`src/magic_geo/api.py:189-192` compares `world["planet_parameters"]` against `planet_parameter_snapshot(config.planet)` after every native generation. A mismatch means the loaded library and the Python `PLANET_PARAMETER_DEFAULTS` (`src/magic_geo/planet_parameters.py:10-23`) disagree — rebuild the native core.

---

## Compute backend selection surprises

### `magic-geo backend` always reports `cpu`

This is expected. `backend_info()` constructs a **capability-only** probe session, and the code sets:

```
"active_backend": "cpu",
"backend_selection_reason": "capability-only probe; no generation is active"
```

(`cpp/src/opencl_compute.cpp:849-852`.) A real backend is chosen per generation. Read `opencl_available`, `opencl_qualifying_device_count`, `cuda_compiled`, `cuda_available`, and the threshold fields instead.

Actual output from this host (abridged, `magic-geo backend`):

```json
{
  "active_backend": "cpu",
  "backend_selection_reason": "capability-only probe; no generation is active",
  "cuda_compiled": false,
  "cuda_error": "CUDA support was not compiled into the native library",
  "cuda_auto_min_cell_count": 8192,
  "cuda_sm_120_auto_min_cell_count": 8192,
  "cuda_uncalibrated_auto_min_cell_count": 32768,
  "opencl_available": true,
  "opencl_auto_min_cell_count": 32768,
  "opencl_device_name": "NVIDIA GeForce RTX 5090",
  "opencl_device_fp64": true,
  "opencl_qualifying_device_count": 1,
  "opencl_qualifying_gpu_device_count": 1,
  "openmp_enabled": true,
  "openmp_max_threads": 16
}
```

### `compute.backend: auto` picked CPU on a machine with a GPU

Automatic selection is **deferred until the actual mesh size is known** and then compared against evidence-based thresholds (`cpp/src/opencl_compute.cpp:99-101`, `:952-1050`):

| Constant | Value | Meaning |
|---|---|---|
| `CUDA_SM_120_AUTO_MIN_CELL_COUNT` | `8192` | Minimum generated cells before an sm_120 CUDA device is auto-selected |
| `CUDA_UNCALIBRATED_AUTO_MIN_CELL_COUNT` | `32768` | Minimum generated cells for a non-sm_120 CUDA device |
| `OPENCL_AUTO_MIN_CELL_COUNT` | `32768` | Minimum generated cells for automatic OpenCL |

The selection ladder for `auto` (`ensure_auto_backend`, `cpp/src/opencl_compute.cpp:952-1050`):

| Situation | `backend_selection_reason` (verbatim) |
|---|---|
| Below both probe thresholds | `automatic acceleration is below the evidence-based actual-mesh thresholds; CUDA/OpenCL probes skipped` |
| sm_120 CUDA device, eligible | `automatic selection chose native CUDA for an NVIDIA sm_120 device` |
| Non-sm_120 CUDA device, eligible | `automatic selection chose an uncalibrated FP64 NVIDIA CUDA device at the conservative threshold` |
| CUDA device present but below its own policy threshold, OpenCL not eligible | `automatic CUDA probe found an uncalibrated device below its conservative actual-mesh threshold; CPU retained by policy` |
| CUDA unavailable, OpenCL selected | `automatic CUDA selection was unavailable (<cuda reason>); selected qualifying OpenCL device` |
| OpenCL device chosen but runtime init failed | `automatic accelerator initialization fell back to CPU` |
| Nothing qualifies | `automatic accelerator selection fell back to CPU` |
| OpenCL device selection failed under `auto` | `automatic OpenCL selection fell back to CPU` |

Diagnostic fields to check in the generated world's `backend` object (and in `magic-geo backend`): `automatic_planning_cell_count`, `cuda_auto_offload_eligible`, `opencl_auto_offload_eligible`, `backend_fallback_used`, `backend_fallback_stage`, `backend_fallback_reason`.

`backend_fallback_reason` for `auto` is composed (`cpp/src/opencl_compute.cpp:1036-1047`), e.g. `CUDA: <reason>; OpenCL: <reason>`, or `no qualifying accelerator is available`.

Additional `auto`-only device policy (`cpp/src/opencl_compute.cpp:903-913` and `choose_device_for_records` at `:1051-1062`): `auto` **never** selects a CPU-type OpenCL device. Two reasons exist for that outcome:

- `automatic GPU preference found no qualifying GPU OpenCL device` (when `opencl_prefer_gpu` is true and no qualifying GPU exists)
- `automatic OpenCL selection found no qualifying non-CPU device` (when qualifying devices exist but they are all CPU-type)

### Explicit backends never silently fall back

| Symptom (exact text) | Raised at | Cause | Fix |
|---|---|---|---|
| `explicit CUDA backend requested but initialization failed: CUDA support was not compiled into the native library` | `cpp/src/opencl_compute.cpp:830-838` with the stub telemetry from `cpp/src/cuda_compute_stub.cpp:23-24` | `compute.backend: cuda` on a build without CUDA | Rebuild with CUDA 12.8+, or use `auto`/`cpu`/`opencl` |
| `explicit CUDA backend requested but initialization failed: no usable NVIDIA CUDA device is available` | same, `:833` | CUDA compiled in, but no usable device | Check driver/device; the concrete driver error is substituted when non-empty |
| `explicit OpenCL backend requested but initialization failed: no qualifying FP64 OpenCL device is available` | `cpp/src/opencl_compute.cpp:900-919` | No device passed the FP64/behavioral qualification | Install a conforming ICD/driver, or use `cpu` |
| `explicit OpenCL backend requested but initialization failed: <runtime error>` | `cpp/src/opencl_compute.cpp:936-946` | Device selected, but program build/queue/context creation failed | See the appended loader error (`OpenCL loader API is unavailable`, `clCreateContext returned a null context`, etc.) |

Reproduced on this host:

```console
$ python -c "from magic_geo.config import *; from magic_geo.native import generate_world; \
    c=apply_config_overrides(create_config('smoke'), {'compute.backend':'cuda'}); \
    generate_world(config_to_native(c))"
RuntimeError: explicit CUDA backend requested but initialization failed: CUDA support was not compiled into the native library
```

Explicit backends also **ignore the automatic thresholds**. Verified: `compute.backend: opencl` at `mesh.cell_count: 128` selected OpenCL and generated successfully. That is by design — thresholds are an `auto` policy, not a hard eligibility rule.

### `compute.backend: cpu` and probe truthfulness

`cpu` short-circuits before any probe:

```
"backend_selection_reason": "CPU backend explicitly requested; CUDA/OpenCL probes skipped"
```

(`cpp/src/opencl_compute.cpp:815-820`.) The engine README states this as invariant #7 ("Preserve backend truthfulness"): `cpu` must not initialize or probe CUDA or OpenCL, and below-threshold `auto` CPU selection is not a fallback. If you need a deterministic reference run, use `cpu`.

### Threads

`compute.threads` maps to a generation-scoped OpenMP policy: `ScopedThreadConfiguration` (`cpp/src/engine/core.cpp:211-229`) calls `omp_set_num_threads(requested)` only when `requested > 0`, and restores the caller's previous `omp_get_max_threads()` in its destructor. `threads = 0` leaves host policy untouched — including any `OMP_NUM_THREADS` you set in the environment. If a run uses more cores than you expect with `threads: 0`, that is host OpenMP policy, not a magic-geo default.

### Accelerator parity caveat

Do not read a successful accelerator run as evidence of accelerator/CPU equivalence. The backend telemetry itself reports:

```
"crust_overlap_accelerator_complete_parity_demonstrated": false,
"crust_overlap_accelerator_state_authoritative": false,
"crust_overlap_continuous_shadow_authoritative": false,
"crust_overlap_continuous_production_remap_authoritative_backend": "cpu",
"crust_transport_execution_backend": "cpu",
"backend_scope": "accelerated_native_kernels_not_end_to_end_pipeline"
```

Authoritative forward spherical crust overlap executes on CPU regardless of backend. The accelerator shadow kernel's result is validated against bounds and then **discarded** (`crust_overlap_continuous_shadow_result_used_for_state: false`). `-ffp-contract=off` (`CMakeLists.txt`) and the CUDA flags `--fmad=false --ftz=false --prec-div=true --prec-sqrt=true` exist to limit backend drift, but the project checks parity with tolerances and invariants, not byte hashes.

---

## Memory and payload size at large cell counts

### Hard limits

| Limit | Value | Where | What it bounds |
|---|---|---|---|
| `mesh.cell_count` | `128 .. 200000` | `src/magic_geo/config.py:244-249`, `cpp/src/engine/core.cpp:287-289` | Requested mesh resolution |
| `DEFAULT_MAX_WORLD_FILE_BYTES` | `2 GiB` (`2 * 1024**3`) | `src/magic_geo/serialization.py:39` | Encoded world file size on read |
| `DEFAULT_MAX_STRING_BYTES` | `256 MiB` | `src/magic_geo/serialization.py:40` | Any single string in a world |
| `DEFAULT_MAX_ARRAY_LENGTH` | `50_000_000` | `src/magic_geo/serialization.py:41` | Any single array |
| `DEFAULT_MAX_MAP_LENGTH` | `2_000_000` | `src/magic_geo/serialization.py:42` | Any single object |
| `MAX_WORLD_NESTING_DEPTH` | `64` | `src/magic_geo/serialization.py:43` | Container nesting |
| `MAX_DEBUG_CELLS` | `200_000` | `src/magic_geo/debug_map_export.py:41` | `export-debug-map` cell count |
| `MAX_MESH_VERTICES` / `MAX_MESH_TRIANGLES` | `2_000_000` each | `src/magic_geo/debug_map_export.py:42`, `:43` | `export-debug-map` mesh |
| `MAX_RASTER_PIXELS` | `8_294_400` (3840×2160) | `src/magic_geo/debug_map_export.py:40` | `export-debug-map` PNG area |
| `_MAX_CONFIG_BYTES` | `1_000_000` | `src/magic_geo/debug_server.py:45` | YAML accepted by the workbench |
| `_MAX_WEB_MANIFEST_BYTES` | `8 MiB` | `src/magic_geo/web_jobs.py:47` | Browser-supplied source/matrix manifests |

### Measured sizes

From a real run on this host, a 128-cell full smoke world (profile `smoke`, `erosion.iterations: 1`):

| Artifact | Bytes | Note |
|---|---|---|
| `w.json` (full world, JSON) | 7,568,614 | `json.dumps(payload, indent=2, sort_keys=True, allow_nan=False)` at `src/magic_geo/io/json_writer.py:12-15` — indentation is a large fraction of this |
| `w.mgeo` (same world, `.mgeo`) | 4,645,747 | 61.4% of the JSON size |
| `geo.json` (`--geo-only`, JSON) | 7,327,664 | Civilization layers stripped |
| `dbg/` (debug cache, `--no-vtu`) | ~4.7 MB | 428 layers, 1 stage history, 99 families |

The serialization module's own comment records the 4,096-cell reference artifact as "roughly 193 MB as `.mgeo`" (`src/magic_geo/serialization.py:37-38`); the README separately reports one benchmark on a local 4,096-cell artifact where `.mgeo` was 50.2% smaller, 3.92x faster to save, and 2.60x faster to load (`README.md:177-179`). Treat both as single measurements, not guarantees.

### Practical guidance

| Problem | Cause | Mitigation |
|---|---|---|
| `world file is <n> bytes; limit is <m> bytes` on read | `src/magic_geo/serialization.py:572-575` (and `:371-374` for in-memory decode) | Pass a larger `max_file_bytes=` to `read_world`. The CLI does not expose this; use the Python API |
| `world file exceeds the <m>-byte limit` (JSON path) | `src/magic_geo/serialization.py:587-590` | Same |
| RAM exhaustion at high cell counts | The decoded Python object graph is far larger than the encoded file; `DEFAULT_MAX_WORLD_FILE_BYTES` is explicitly "an encoded-input bound, not a promise about the larger decoded Python graph" (`src/magic_geo/serialization.py:37-38`) | Reduce `mesh.cell_count`; use `--geo-only`; use `.mgeo`; lower `output.float_precision` (JSON only) |
| Debug cache too big / slow | Every scalar cell column becomes a Parquet column and a layer | `export-debug --no-vtu` skips ParaView `.vtu` stage files entirely |
| `debug cache exceeds the 200,000-cell map export limit` | `src/magic_geo/debug_map_export.py:1371` | Export a smaller world for the PNG/prompt path |
| `map raster cannot exceed 8,294,400 pixels` | `src/magic_geo/debug_map_export.py:1335-1336` | `--width`/`--height` individually allow up to 6400×3200, whose product (20,480,000) exceeds the cap. Keep `width * height <= 8294400` |

Reproduced:

```console
$ magic-geo export-debug-map -d dbg -o mapref --width 6400 --height 3200
Unable to export debug map: map raster cannot exceed 8,294,400 pixels
$ echo $?
2
```

`output.float_precision` (`0..8`, default `4`) controls only the *general* JSON decimal precision. Replay-critical numeric state is exempt: per the engine README, initial/final cell crust age, thickness and density, remapped crust roots, boundary forcing, transport, process-change, equilibrium, dynamic-relief and tectonic-change arrays, and final elevation/water depth use general-format `max_digits10` and recover the original binary64 after JSON parsing (`cpp/src/engine/numeric_serialization.cpp`). Lowering `float_precision` will not shrink those.

---

## World file and serialization errors

Every message below reaches the CLI as `Invalid world file: <message>` with exit 2.

| Symptom (exact text) | Raised at | Cause | Fix |
|---|---|---|---|
| `truncated .mgeo header` | `src/magic_geo/serialization.py:375-376` | File shorter than `MGEO_HEADER_SIZE` | The file is incomplete; regenerate |
| `invalid .mgeo magic` | `:389-390`, `:605-606` | First 8 bytes are not `b"MGEO\r\n\x1a\n"` (`:28`) | The file is not a `.mgeo` container |
| `unsupported .mgeo version <maj>.<min>; expected 1.0` | `:391-395` | Container written by a different framing version | Regenerate with this build |
| `unsupported .mgeo codec <n>` | `:396-397` | Codec byte is not `MGEO_CODEC_MESSAGEPACK = 1` (`:31`) | Regenerate |
| `unsupported .mgeo flags 0x<hh>` | `:398-399` | Flags byte is not `MGEO_FLAGS_NONE = 0` (`:32`) | Regenerate |
| `unsupported .mgeo header size <n>` | `:400-403` | Declared header size differs from `MGEO_HEADER_SIZE` | Regenerate |
| `.mgeo payload length mismatch: header declares <a>, file contains <b>` | `:405-409` | Truncated or padded file | Re-copy or regenerate |
| `.mgeo checksum mismatch; the file is corrupt or incomplete` | `:414-417` | CRC32 over the payload disagrees with the header | Regenerate; the file is corrupt |
| `invalid MessagePack world payload: <exc>` | `:438-440` | Payload failed strict unpacking (`raw=False`, `strict_map_key=True`, `max_bin_len=0`, `max_ext_len=0`) | Regenerate |
| `MessagePack extension type <n> is not valid in a world payload` | `:52-56` | An ext type appeared; ext and bin types are forbidden outright | Regenerate |
| `decoded world root must be an object` | `:444-445`, `:597-598` | Top-level value is not a map/object | Not a world file |
| `.mgeo world schema does not match its container header` | `:446-450` | The header's schema field disagrees with `payload["schema_version"]` | Regenerate |
| `empty .mgeo file` | `:603-604` | Zero-byte file | Regenerate |
| `binary .mgeo file was requested as JSON` | `:580-584` | `format="json"` passed for a `.mgeo` file | Use `format="auto"` or `"mgeo"` |
| `JSON world nesting exceeds the decoder limit` | `:593-596` | `RecursionError` from `json.loads` | Not a magic-geo world |
| `world format must be auto, json, or mgeo` | `:619-626` | Bad `format=` argument | Accepted: `auto`, `json`, `mgeo`, plus the aliases `msgpack` and `binary` which normalize to `mgeo` |
| `world root must be an object` | `:240-241`, `:325-326` | Writing a non-dict | Pass a world dict |
| `binary worlds require an integer schema_version between 0 and 2^32-1` | `:59-65` | Missing/invalid `schema_version` on write | Write a real generated world |
| `world contains a non-finite floating-point value` | `:304-308` | NaN/Inf in the payload during `validate_world_payload` | The native serializer already rejects these at `cpp/src/engine/core.cpp:170-173`; a hand-edited world is the usual cause |
| `world contains a reference cycle` | `:265-266` | Self-referential container | Hand-built payload |
| `world object keys must be strings, not <type>` | `:276-280` | Non-string map key | Hand-built payload |
| `world integer is outside MessagePack's signed/unsigned 64-bit range` | `:298-303` | Python bigint | Hand-built payload |
| `world nesting exceeds 64 containers` | `:261-264` | Depth over `MAX_WORLD_NESTING_DEPTH` | Hand-built payload |

### Format selection rules

- **Writing** (`write_world`, `src/magic_geo/serialization.py:532-554`): `format="auto"` picks `mgeo` when `path.suffix.lower()` is in `MGEO_SUFFIXES = {".mgeo", ".mgpack", ".msgpack", ".mpk"}` (`:35`), else JSON.
- **Reading** (`read_world`, `:557-616`): `format="auto"` sniffs the **magic bytes**, not the suffix. A `.json`-named file containing `.mgeo` bytes still loads correctly.
- `magic-geo generate --format` is validated by hand against `{auto, json, mgeo}` (`src/magic_geo/cli/commands/generate.py:57-59`), printing `--format must be auto, json, or mgeo` and exiting 2.
- `generate` writes with `validate_model=False` on the hot path with an explicit rationale: "The generation pipeline owns this object and its JSON-value invariants; skip the otherwise-public recursive preflight on the hot save path" (`src/magic_geo/cli/commands/generate.py:76-78`). CLI **reads** keep strict validation (`src/magic_geo/cli/_app.py:18-20`).

---

## Validation command failures

### `validate` — the two-phase gate

`magic-geo validate --world <path>` takes exactly one option (`src/magic_geo/cli/commands/validate.py:92-94`). There are no per-domain switches, no `--output`, no severity policy.

**Phase 1 (short-circuit)** at `src/magic_geo/cli/commands/validate.py:100-122`:

| Failure line | Cause |
|---|---|
| `world schema_version must be 2, got <repr>` | Wrong or non-`int` `schema_version` |
| `world schema contains retired fields: <names>` | `retired_world_schema_fields(payload)` non-empty (`src/magic_geo/serialization.py:68-234`) |
| `planet parameters invalid: <message>` | `planet_radius_km`/`surface_gravity_m_s2` raised. Messages come from `src/magic_geo/planet_parameters.py:48-69`: `world must be an object`, `world must provide planet_parameters`, `planet_parameters must be an object`, `planet_parameters.<key> is required`, `planet_parameters.<key> must be numeric`, `planet_parameters.<key> must be finite and positive` |

If any of these fire, the command exits 1 **immediately** — masking every other diagnostic. Verified:

```console
$ echo '{"schema_version": 1}' > bad.json
$ magic-geo validate --world bad.json
FAIL world schema_version must be 2, got 1
FAIL planet parameters invalid: world must provide planet_parameters
$ echo $?
1
```

**Phase 2** accumulates 1,089 `failures.append(...)` sites plus 18 pure per-domain validators imported from `src/magic_geo/cli/validators/` (`:68-88`) and 18 delegated top-level validators (`validate_*_replay`, `validate_crust_material_shadow`, `validate_oceanic_age_depth`, and siblings, imported at `:15-45`), and prints them all at the end (`:22328-22333`):

```python
if failures:
    for failure in failures:
        typer.echo(f"FAIL {failure}", err=True)
    raise typer.Exit(1)

typer.echo("OK")
```

### `validate` fails on a `--geo-only` world

This is the single most common surprise. `validate` is the *full-world* gate; it unconditionally runs the civilization, settlement, political, and history replays. Verified on a 128-cell geo-only world — the run emitted **184** `FAIL` lines, of which 22 are `... replay invalid`; the first eight are shown:

```console
$ magic-geo generate -c smoke.yaml -o geo.json --geo-only
$ magic-geo validate --world geo.json
FAIL settlement selection model or causal replay invalid
FAIL route network model or causal replay invalid
FAIL political region model or causal replay invalid
FAIL political border model or causal replay invalid
FAIL trade flow model or causal replay invalid
FAIL land use zone model or causal replay invalid
FAIL natural frontier model or causal replay invalid
FAIL worldbuilding realism model or causal replay invalid
... (176 further FAIL lines: cultural/historical geography, demography, dynasty,
     logistics, campaign, market, phonology, navigability, port, corridor
     replays, plus every count/consistency field that depends on them)
$ echo $?
1
```

Use `validate-geo` for geo-only worlds:

```console
$ magic-geo validate-geo --world geo.json
OK geo | checks=150 errors=0 warnings=0 not_applicable=3
$ echo $?
0
```

### `validate-geo`

| Symptom | Raised at | Cause | Fix |
|---|---|---|---|
| `--profile must be generic or earthlike` (exit 2) | `src/magic_geo/cli/commands/validate_geo.py:50-52` | Bad `--profile` | Use `generic` (default) or `earthlike` |
| `FAIL geo \| checks=<n> errors=<n> warnings=<n> not_applicable=<n>` then `FAIL <domain>.<name>: <message>` (exit 1) | `:68-79`, `:87-88` | `report["passed"]` false, or any failed check with `severity == "error"` | Read the per-check messages; write the machine-readable report with `-o` |
| `FAIL layer_contract.<id>: required artifacts, validation domains, or dependencies failed` | `:80-86` | A layer contract in `report["layer_contracts"]["layers"]` reported `contract_passed: false` | See [Geo Validation Suite](./13-geo-validation-suite.md) |

Policy: `policy_passed = bool(report["passed"]) and not failed_checks` where `failed_checks` filters on `status == "failed"` and (`severity == "error"` **or** `--fail-on-warnings`) (`:55-61`). So by default warnings do not fail the command; `--fail-on-warnings` promotes them.

`not_applicable` is a deliberate third state: absent rivers, deltas, currents, or biomes are reported as `not_applicable` rather than receiving a vacuous perfect score.

Profile choice is resolution-sensitive. Verified on the same 128-cell geo-only world:

```console
$ magic-geo validate-geo --world geo.json --profile earthlike
FAIL geo | checks=160 errors=1 warnings=0 not_applicable=3
FAIL earthlike_profile.calibration_pass_fraction: Earth-like calibration_pass_fraction must fall in the declared broad validation envelope
$ echo $?
1
```

The `earthlike` profile adds broad Earth-regime gates that a 128-cell smoke world is not expected to satisfy. Use `generic` for smoke-scale runs, and reserve `earthlike` for Earth-configured worlds at reference resolution.

### `validate-geo-suite`

| Symptom | Raised at | Cause | Fix |
|---|---|---|---|
| `geo validation manifest was not loaded or normalized` (exit 2) | `src/magic_geo/geo_validation_suite/evaluate.py:179` | The manifest dict did not pass through `load_geo_validation_manifest` | Load via the CLI, not by hand |
| `geo validation manifest has no scenarios` (exit 2) | `:182` | Empty/missing `scenarios` list | Fix the matrix YAML |
| `scenario '<id>' must keep output.include_cells=true for deep validation` (exit 2) | `:190-193` | A scenario override disabled cells | Remove that override |
| `scenario '<id>' config is invalid: <pydantic error>` (exit 2) | `:194-196` | Merged overrides violate `WorldConfig` | Fix the scenario overrides |
| `scenario '<id>' generation failed: <engine message>` (exit 2) | `:201-205` | A native `RuntimeError` during that scenario | See the generation sections above |
| `unknown config override '<path>'` / `config override '<path>' must be an object` / `config override '<path>' cannot be an object` (exit 2) | `src/magic_geo/geo_validation_suite/_helpers.py:79-85` | Malformed nested override tree | Match the config schema shape |
| `scenario '<id>' external empirical calibration failed: <CalibrationError>` (exit 2) | `src/magic_geo/geo_validation_suite/evaluate.py:134-138` | A configured empirical bundle could not be evaluated | See the calibration section |
| `Failed scenarios: <ids>` / `Failed relations: <ids>` / `Failed external empirical metrics: <scenario:metric>` (exit 1) | `src/magic_geo/cli/commands/validate_geo.py:150-169` | `report["passed"]` is false | The JSON report at `-o` (default `runs/geo_validation.json`) carries per-member detail |

The report is written **before** the nonzero exit (`:131`), so a failing suite still leaves you a report.

### `calibrate` and `calibrate-ensemble`

| Symptom | Raised at | Exit | Notes |
|---|---|---|---|
| `<CalibrationError text>` | `src/magic_geo/cli/commands/calibrate.py:67-69` | 2 | Target bundle malformed or unreadable; also catches `json.JSONDecodeError` |
| `Calibration coverage incomplete; missing world metrics: <names>` | `:81-85` | 1 | Only with `--require-all-metrics`. Report is written first (`:71`) |
| `Calibration coverage incomplete; no calibration targets were evaluated` | `:81-85` | 1 | Same gate, empty bundle |
| `Calibration fit failed; failed metrics: <names>` | `:86-91` | 1 | Only with `--require-all-passed` |
| `Calibration fit failed; no calibration targets` | `:86-91` | 1 | `--require-all-passed` with zero checks is a failure by design |
| `Calibration ensemble coverage incomplete` | `:188-190` | 1 | `--require-all-metrics` and `reference_matrix_complete` false |
| `Calibration ensemble fit failed; failed members: <ids>` | `:191-199` | 1 | `--require-all-passed` and `reference_matrix_all_passed` false |

Both write their JSON report before exiting nonzero, so policy failures never destroy evidence. `calibrate-ensemble` also records SHA-256 provenance of the matrix and of each targets bundle into `report["provenance"]` (`:153`, `:169`).

---

## Web workbench and job failures

### Startup

| Symptom (exact text) | Raised at | Cause | Fix |
|---|---|---|---|
| `Web workspace must stay inside <project root>: <path>` (exit 2) | `src/magic_geo/cli/commands/serve.py:56-63` | The resolved `--workspace` escapes `Path.cwd().resolve()` | Use an in-project directory. `_CacheManager` and `JobManager` re-apply the same rule with `web workspace must be inside the project directory` (`src/magic_geo/debug_server.py:513-514`) |
| `No manifest.json in <dir>; choose an export-debug cache or omit -d.` (exit 2) | `src/magic_geo/cli/commands/serve.py:70-75` | Explicit `-d` names a directory without `manifest.json` | Point at a real `export-debug` cache, or drop `-d` and let discovery run |
| `Serving requires the optional debug dependencies: pip install 'magic-geo[debug]' (<exc>)` (exit 2) | `src/magic_geo/cli/commands/serve.py:76-82` | `uvicorn` or the `debug_server` imports are unavailable | `pip install -e '.[debug]'` (pulls `pyarrow>=19`, `duckdb>=1.2`, `fastapi>=0.115`, `uvicorn[standard]>=0.34`) |
| `Ignoring invalid automatic cache <dir>: <exc>` (warning, server still starts) | `src/magic_geo/cli/commands/serve.py:85-91` | An auto-discovered cache failed validation | The server restarts cacheless; Config, Operations, Backend, jobs, and OpenAPI remain usable |
| `Unable to start web workbench: <exc>` (exit 2) | `src/magic_geo/cli/commands/serve.py:94-102` | `create_app` raised `ValueError` or `OSError` | Read the appended reason |

Verified:

```console
$ magic-geo serve --workspace /etc
Web workspace must stay inside /tmp/mgtest: /etc
$ echo $?
2
$ magic-geo serve -d emptycache
No manifest.json in emptycache; choose an export-debug cache or omit -d.
$ echo $?
2
```

Environment variables back three flags only, and only when the flag is omitted (Typer `envvar=`):

| Env var | Flag | Default | Line |
|---|---|---|---|
| `MAGIC_GEO_WORKSPACE` | `--workspace` | `runs` | `src/magic_geo/cli/commands/serve.py:26-33` |
| `MAGIC_GEO_HOST` | `--host` | `127.0.0.1` | `:34-37` |
| `MAGIC_GEO_PORT` | `--port` (1–65535) | `8642` | `:38-47` |

### HTTP errors from the cache-backed API

| Status | `detail` (exact text) | Raised at | Meaning |
|---|---|---|---|
| 409 | `no debug cache selected; generate a world or run export-debug` | `src/magic_geo/debug_server.py:684-687` | No cache is selected; every `/api/manifest`, `/api/catalog`, `/api/layer`, `/api/cell`, `/api/stage-summary`, `/api/family`, `/api/section`, `/api/plate-boundaries`, and `/mesh/*` request returns this |
| 409 | `no manifest.json in <dir>` | `:697` | The selected directory lost its manifest |
| 409 | `debug cache revision changed; refresh status and retry` | `:735-738` | The client sent a `revision` query parameter that no longer matches |
| 500 | `invalid debug cache <dir>: <reason>` | `:102-135`, surfaced at `:713` | The cache directory failed structural validation |
| 500 | `unsupported debug cache <dir>: expected 'magic-geo-debug-cache' version 1, got <format> version <version>` | `:124-128` | Format/version mismatch |
| 400 | `invalid NUL in field name` | `:58-63` | A manifest column name contains NUL; DuckDB identifiers are quoted via `_quote_identifier` |
| 400 | `month <n> out of range` | `:286-289` | Requested month outside `0 .. month_count-1` |
| 400 | `stage <n> out of range` | `:298-305` | Requested stage outside `0 .. stage_count-1` |
| 400 | `cache paths must be relative` / `cache path escapes root: <rel>` | `:241-250` | Manifest path containment violation |
| 400 | `mesh paths must be relative` / `mesh path escapes mesh root: <rel>` | `:255-264` | |
| 404 | `unknown layer <id>` | `:277-280` | Layer id not in the manifest |
| 404 | `missing cache file <rel>` | `:248-249` | Manifest references a file that disappeared |
| 404 | `missing mesh asset <rel>` | `:265-266` | |
| 404 | `monthly table is unavailable` / `cells table is unavailable` | `:291-292`, `:312-314` | Manifest lacks that section |
| 404 | `missing stage history <name>` | `:299-302` | |
| 404 | `cell <n> out of range` / `cell <n> not found` | `:359-365` | |
| 404 | `unknown stage history <name>` | `:419-422` | |
| 404 | `unknown family <name>` | `:456-458` | |
| 404 | `family <name> has no readable data` | `:470-473` | Manifest family entry has none of `parquet`, `scalars_parquet`, `jsonl` |
| 404 | `unknown section <name>` | `:1176-1181` | |
| 404 | `unknown job <id>` / `unknown artifact` / `artifact is not available` | `:1067-1088` | |
| 413 | `YAML exceeds the 1000000-byte request limit (<n> bytes)` | `:861-874` | Editor content over `_MAX_CONFIG_BYTES` |
| 422 | `{message, source, issues[], line?, column?}` | `:857-858` via `ConfigError.to_dict()` | Any config parse/validate failure; identical structure to the CLI error |
| 422 | `name must use only letters, digits, '.', '_', and '-'` | `:1010-1014` | Config save name failed `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`, or is `.`/`..` |
| 422 | `workspace config directory must not be a symbolic link` / `configuration target must not be a symbolic link` / `config directory escapes workspace` / `invalid configuration name` | `:1020-1038` | Save-path containment |
| 422 | `cache must be inside the web workspace` | `:1104-1105` | `POST /api/worlds/select` with an out-of-workspace path |
| 422 | `unable to resolve cache path: <exc>` | `:1100-1103` | |
| 409 | `configuration already exists: <name>; confirm overwrite to replace it` | `:1039-1043` | Save without `force` |
| 500 | `unable to save configuration: <OSError>` | `:1048-1049` | |
| 503 | `backend probe failed: <exc>` | `:944-951` | `GET /api/backend` could not load the native library — same causes as the build section |

### Job submission errors (HTTP 422, `JobInputError`)

| `detail` (exact text) | Raised at | Cause |
|---|---|---|
| `unknown operation: <name>` | `src/magic_geo/web_jobs.py:487` | Operation not in `_OPERATIONS` |
| `web job manager is closed` | `:485`, `:498` | Submitted during shutdown |
| `web job executor is unavailable` | `:540` | The single-worker executor rejected the task |
| `job queue is full (100); wait for or cancel existing work` | `:529-531` | `max_jobs = 100` (`:419`) and no terminal jobs left to evict |
| `output already targeted by an active job: <paths>` | `:512-517` | Another queued/running job declares the same (or a nested cache) output |
| `declared outputs overlap: <a> and <b>` | `:955-960` | One submission declares two conflicting outputs |
| `output must not replace an input: <path>` | `:963-968` | |
| `cache output must be a directory path: <path>` | `:970-975` | The cache artifact path exists and is not a directory |
| `cache output must not replace or contain an input: <cache> contains <input>` | `:975-981` | |
| `unknown arguments for <operation>: <names>` | `:876` | Extra keys in the request body |
| `missing required argument: <name>` | `:894` | |
| `<name> must be true or false` / `must be an integer` / `must be a number` / `must be finite` / `must be >= <min>` / `must be <= <max>` / `must be one of: <choices>` / `is outside the supported 64-bit range` | `:828-866` | Typed field validation |
| `<name> must contain at least one path` | `:926-931` | Empty `path_list` |
| `input path must name an existing regular file: <value>` | `:609` | |
| `input path must stay inside <project root>: <value>` / `output path must stay inside <workspace>: <value>` | `:605-607` | Containment |
| `output path must not replace the web workspace` | `:611-612` | |
| `output path uses the reserved web-internal directory` | `:613-614` | `<workspace>/.magic-geo-web` is reserved |
| `unable to resolve <role> path <value>: <exc>` | `:601-603` | |
| `indirect input path must stay inside <project root>: <context>=<value>` | `:632-637` | A path *inside* a submitted manifest escapes the project |
| `<context> must be a non-empty path string` / `<context> must name an existing regular file: <value>` | `:625-638` | |
| `<context> exceeds the 8388608-byte web limit` | `:644-648` | Manifest over `_MAX_WEB_MANIFEST_BYTES` |
| `<context> exceeds the 20000-event web limit` / `the 64-level web limit` / `the 64-alias web limit` | `:667-686` | YAML complexity caps for browser-supplied matrices |
| `invalid <context>: <path>: <exc>` | `:655-659`, `:696-697` | JSON/YAML parse failure |
| `geo-validation matrix must contain a scenarios array` | `:756` | |
| `calibration sources[<i>] must be an object` | `:709` | |

The workbench walks **transitive** inputs before spawning: `derive-targets` follows `sources[].path`, `dbf_path`, `prj_path`, and the `archives[].path` entries of a HydroBASINS catalog; `validate-geo-suite` follows `scenarios[].empirical_calibration.target_bundle` into `derivation.source_manifests[]` and `supplemental_target_derivations[].path`. The CLI intentionally allows absolute paths; the browser does not.

### Job runtime behaviour

| Behaviour | Where | Consequence |
|---|---|---|
| One job at a time | `ThreadPoolExecutor(max_workers=1, thread_name_prefix="magic-geo-web")` | Your second submission queues; this is not a hang |
| Deduplication | `src/magic_geo/web_jobs.py:508-511` | Re-submitting an identical `(operation, normalized arguments)` while it is active returns the existing job instead of creating a new one |
| Log cap | `max_log_bytes = 2_000_000` (`:418`); truncation marker `[earlier output truncated]\n` (`:1183`) | Long logs lose their head, not their tail |
| Subprocess environment | `PYTHONUNBUFFERED=1` (`:1187`), `cwd=project_root`, merged stdout+stderr | Live streaming; argv is fixed and typed, never shell-evaluated |
| Cancellation is refused mid-commit | `:549-554` | While `_publishing` or `_finalizing`, `cancel` is a no-op returning the current job, so a completed publication is never described as cancelled |
| Cancellation escalation | SIGTERM to the process group, then SIGKILL after 5 s (POSIX); `terminate()`/`kill()` on Windows | |
| `web job failed: <Type>: <message>` in the log, `exit_code = -1` | `:1279` | An exception inside the job runner itself |
| `export-debug command has no output argument` | `:1143` | Internal invariant of staged cache publication |
| `export produced an invalid debug cache: <exc>` / `export produced non-object manifest or sections metadata` / `export produced an unsupported debug cache format/version: <fmt> v<ver>` / `export produced incomplete world/layer metadata` | `:1075-1098` | The staged cache failed validation, so it is **not** published; the previously selected cache is untouched |
| `published debug cache escaped the web workspace` | `:1169-1171` | Containment failure after publication |
| `cache destination is not a directory: <path>` | `:1104-1105`, and `src/magic_geo/debug_server.py:610-611` | |
| `published cache must stay inside the web workspace` | `src/magic_geo/debug_server.py:606-609` | |

`export-rerun` appears in `/api/operations` with `available: false` and `dependency: "rerun"` when `importlib.util.find_spec("rerun")` is `None` (`src/magic_geo/web_jobs.py:237`, `:314-316`). Install `rerun-sdk` to enable it.

### Security posture

The workbench has **no authentication, no authorization, no per-user isolation, and no TLS**. Anyone who can reach the port can read workspace data and submit or cancel jobs. The defaults are the mitigation: bind `127.0.0.1`, publish on loopback in Compose (`MAGIC_GEO_PUBLISH_HOST` defaults to `127.0.0.1`), and confine every path with component-aware `Path.relative_to` checks rather than string prefixes. If you set `--host 0.0.0.0`, put an authenticating proxy in front of it. See [Web Workbench](./15-web-workbench.md) and [Docker Deployment](./19-docker-deployment.md).

---

## Debug cache, stale revisions, and exports

### Cache format identity

The on-disk contract is `FORMAT_NAME = "magic-geo-debug-cache"` and `FORMAT_VERSION = 1` (`src/magic_geo/debug_export.py:30-31`). A cache is only accepted when `manifest["format"]` matches exactly and `type(manifest["version"]) is int and version == 1` (`src/magic_geo/debug_server.py:118-128`).

`_DebugCache.__init__` validates **every** manifest-referenced file before the cache goes live (`src/magic_geo/debug_server.py:173-235`): cells parquet plus optional details JSONL/index, monthly parquet, each history's two parquets plus optional extras, each family's parquet/scalars/jsonl, all five mesh buffers (`positions`, `cell_ids`, `indices`, `pos_equirect`, `pos_mollweide`), the optional ParaView `.pvd`, and that every `sections[]` name exists in `sections.json`. Each is checked for being relative, resolving inside the cache root, and existing as a file.

| Symptom (exact text) | Raised at | Cause |
|---|---|---|
| `invalid debug cache <dir>: manifest file must stay inside the cache` | `:103-110` | `manifest.json` is a symlink pointing out of the cache |
| `invalid debug cache <dir>: manifest and sections must be objects` | `:116-117` | |
| `invalid debug cache <dir>: missing world/layer metadata` | `:129-133` | |
| `invalid debug cache <dir>: invalid cell/layer metadata` | `:134-135` | `cell_count < 1`, or `layers` is not a list |
| `invalid debug cache <dir>: duplicate or malformed layer ids` | `:145-146` | |
| `invalid debug cache <dir>: <context> path must be relative` / `escapes root` / `missing <context> file <rel>` / `<context> path is missing` | `:155-171` | Any referenced file failed the containment/existence check |
| `invalid debug cache <dir>: family <name> has no data file` | `:212-213` | |
| `invalid debug cache <dir>: malformed section catalog` | `:215-219` | A name in `manifest["sections"]` is missing from `sections.json` |
| `invalid debug cache <dir>: missing mesh buffer catalog` / `missing mesh buffer <name>` | `:221-229` | |
| `unable to open DuckDB for debug cache <dir>: <exc>` | `:148-151` | |

### Revision tokens

The cache revision is `"-".join(hex)` of `(st_dev, st_ino, st_size, st_mtime_ns)` of `manifest.json` (`src/magic_geo/debug_server.py:558-567`). Device and inode are included specifically so that an atomic replacement with an identical size and timestamp still changes the token.

`get()` re-stats the manifest on every access and transparently reopens `_DebugCache` (closing the old DuckDB connection) when the fingerprint changes (`:699-721`). `with_cache(action, expected_revision)` then compares the caller's token under the manager lock and raises 409 `debug cache revision changed; refresh status and retry` on mismatch (`:723-739`).

**How to recover in the browser:** refresh `GET /api/status`, take the new `cache_revision`, and retry the read. The UI does this automatically; a manual `curl` with a stale `?revision=` will keep failing until you re-read status.

### `export-debug` failures

| Symptom (exact text) | Raised at | Exit | Cause / fix |
|---|---|---|---|
| `Debug export requires the optional debug dependencies: pip install 'magic-geo[debug]' (<exc>)` | `src/magic_geo/cli/commands/export.py:181-185` | 2 | `pyarrow`/`duckdb` missing |
| `world payload has no cells; generate with output.include_cells enabled` | `src/magic_geo/debug_export.py:833` | 2 | See the `include_cells` section above |
| `debug export requires contiguous cell ids 0..n-1` | `src/magic_geo/debug_export.py:600-602` | 2 | A hand-edited or filtered world; the mesh builder requires a contiguous id range |

Default output when `-o` is omitted is `<world dir>/debug` (`src/magic_geo/cli/commands/export.py:187`). The browser's default is `<workspace>/debug` instead — these are deliberately different.

### `export-debug-map` failures

| Symptom (exact text) | Raised at | Cause / fix |
|---|---|---|
| `Debug map export requires the optional debug dependencies: pip install 'magic-geo[debug]' (<exc>)` | `src/magic_geo/cli/commands/export.py:121-129` | Install the `debug` extra |
| `projection must be globe, equirect, or mollweide` | `src/magic_geo/debug_map_export.py:1321` | Accepted after normalization (`lower()`, `_`→`-`) with aliases `equirectangular`→`equirect`, `orthographic`→`globe` |
| `at least one of PNG or Markdown output must be enabled` | `:1323` | You passed both `--no-image` and `--no-prompt` |
| `center latitude must be between -90 and 90` / `center longitude must be between -360 and 360` | `:1325-1327` | |
| `stage must be non-negative` / `month index must be between 0 and 11` | `:1330-1332` | `--month` is 1-based on the CLI and converted with `month=month - 1` (`src/magic_geo/cli/commands/export.py:139`) |
| `map width and height must be positive` | `:1334` | |
| `map raster cannot exceed 8,294,400 pixels` | `:1335-1336` | See the memory section |
| `debug mesh is incomplete: <n> cells have no boundary ring; a semantic image prompt would mislabel those holes as outside-map background` | `:1364-1367` | Fail-closed: the export refuses rather than producing a misleading image |
| `debug mesh contains no renderable triangles` | `:1369` | |
| `debug cache exceeds the 200,000-cell map export limit` | `:1371` | |
| `debug mesh exceeds the 2,000,000-vertex export limit` / `2,000,000-triangle export limit` | `:1372-1375` (manifest counts), `:1095-1106` (buffer sizes) | |
| `unknown or unavailable layer '<id>'; available examples: <first 12 sorted ids>` | `:1385` | Copy an exact id from the listed examples or from `/api/catalog` |
| `layer <id> has no readable data table` | `:1252` | |
| `debug cache changed while its export snapshot was being opened; retry` | `:1277`, `:1355`, `:1396` | The cache was replaced between opening and snapshotting |
| `debug cache changed during map export; retry` | `:1286-1288` (`_snapshot_fingerprints` re-check) | Fingerprints of `manifest.json`, the layer's data table, and the needed mesh buffers changed between read and rename |
| `<label> must contain exactly three comma-separated numbers` / `<label> components must be finite` / `<label> must have non-zero length` | `:723-748` | Malformed `--camera-position` / `--camera-target` / `--camera-up` |
| `--camera-target and --camera-up require --camera-position` | `:799` | The canonical and explicit camera modes are mutually exclusive |
| `camera up vector must not be parallel to the viewing direction` | `:811` | |
| `camera distance must be a finite number between 1.01 and 100` | `:816` | |
| `vertical field of view must be a finite number between 1 and 179 degrees` | `:793-795` | |
| `malformed mesh buffer <path>: byte length is not divisible by <n>` | `:686` | Corrupt cache |
| `output basename cannot be empty` | `:1203` | |
| `cache file escapes the debug directory: <rel>` / `missing cache file: <rel>` | `:1212-1214` | |

Verified:

```console
$ magic-geo export-debug-map -d dbg -l cells/nonexistent
Unable to export debug map: unknown or unavailable layer 'cells/nonexistent'; available examples: cells/absorbed_shortwave_w_m2, cells/active_layer_depth_m, ...
$ magic-geo export-debug-map -d dbg --projection foo
Unable to export debug map: projection must be globe, equirect, or mollweide
```

### `export-rerun` failures

| Symptom (exact text) | Raised at | Cause / fix |
|---|---|---|
| `Rerun export requires the rerun-sdk package: pip install rerun-sdk (<exc>)` | `src/magic_geo/cli/commands/export.py:217-221` | `rerun` is an undeclared optional extra; install `rerun-sdk` |
| `<ValueError text>` (exit 2) | `src/magic_geo/cli/commands/export.py:226-228` | From `export_rerun_recording` |

Default output when `-o` is omitted is `<world dir>/world.rrd` (`:223`).

### Rendering failures

`render` and `render-raster` both normalize the projection with `projection.lower().replace("_", "-")` and reject anything outside `{equirectangular, mollweide, orthographic}`:

```
unknown projection: <value>
```

(`src/magic_geo/io/svg_map.py:30-32`, `src/magic_geo/io/raster_map.py:25-27`.) The CLI catches `ValueError` and exits 2 (`src/magic_geo/cli/commands/render.py:54-56`, `:93-95`). Note the projection vocabulary here (`equirectangular`/`orthographic`) differs from `export-debug-map`'s (`equirect`/`globe`) — they are separate renderers.

`--max-cells` on `render`/`render-raster` is naive stride slicing; `docs/gui_debug_visualization_research.md` explicitly notes it ignores the `cube_quadtree_v0` mesh LOD index. The LOD index is generation-time scaffolding that nothing in the debugger consumes.

---

## Calibration data and target derivation

### Fetch scripts

The five dataset fetchers are `bash` scripts under `scripts/`, all `set -euo pipefail`, `curl -L -fS`, SHA-256-verified with `sha256sum --check --status`, installing under `<repo>/calibration_data/<name>/`:

| Script | Installs into | Typical failure |
|---|---|---|
| `scripts/fetch_natural_earth_110m.sh` | `calibration_data/natural_earth_110m/` | Archive or shapefile SHA mismatch (silent `sha256sum --check --status` non-zero exit under `set -e`); or `Unexpected Natural Earth version: expected 4.1.0, got <x>` (`fetch_natural_earth_110m.sh:22-25`) |
| `scripts/fetch_etopo_2022_1deg.sh` | `calibration_data/etopo_2022_1deg/` | NOAA THREDDS OPeNDAP endpoint unavailable; the query uses bracket subscripts and needs `--globoff` |
| `scripts/fetch_worldclim_2_1_10m.sh` | `calibration_data/worldclim_2_1_10m/` | Large downloads; prints a non-commercial-use license notice |
| `scripts/fetch_hydrobasins_level3.sh` | `calibration_data/hydrobasins_level3/` | Nine regional archives with per-region checksums; any one failing aborts |
| `scripts/fetch_hydrorivers_v10.sh` | `calibration_data/hydrorivers_v10/` | The only resumable/idempotent fetcher: it skips when the existing archive already verifies, downloads to `.part` with an `rm -f` EXIT trap, and atomically `mv`s on success |

Only `fetch_natural_earth_110m.sh` unpacks through a `mktemp -d` cleaned by an `EXIT` trap (`:11-12`); `fetch_etopo_2022_1deg.sh`, `fetch_worldclim_2_1_10m.sh`, and `fetch_hydrobasins_level3.sh` download straight into `calibration_data/<name>/` and abort under `set -e` at the first `sha256sum --check --status` failure, leaving the bad file on disk. Re-running the script overwrites it; the fetchers are otherwise not resumable.

### Path resolution: the biggest gotcha

Relative `path`, `dbf_path`, and `prj_path` entries in a source manifest resolve **against the manifest's own directory**, not the current working directory:

```python
# src/magic_geo/calibration/sources.py:21-25
source_path = Path(raw_path)
if not source_path.is_absolute():
    source_path = path.parent / source_path
```

That is why the checked-in `configs/calibration_sources.natural_earth_110m.json` uses `"path": "../calibration_data/natural_earth_110m/ne_110m_land.shp"` and works from any working directory. Verified: `magic-geo derive-targets -s <abs path to configs/...json> -o t.json` succeeded from `/tmp`.

### `derive-targets` errors

All are `CalibrationError` (a `ValueError` subclass, `src/magic_geo/calibration/errors.py:6`) and exit 2 via `src/magic_geo/cli/commands/calibrate.py:219-223`.

| Symptom (exact text) | Raised at | Cause / fix |
|---|---|---|
| `calibration source does not exist: <path>` | `src/magic_geo/calibration/derive.py:74-75` | Run the matching `scripts/fetch_*.sh` first |
| `calibration source SHA-256 mismatch for <path>: expected <a>, got <b>` | `src/magic_geo/calibration/_helpers.py:100-104` | The local file differs from the pinned digest; re-fetch |
| `calibration source 'source_sha256' must be a 64-character hexadecimal digest` | `_helpers.py:98-99` | Manifest typo |
| `calibration source 'source_archive_sha256' must be a 64-character hexadecimal digest` | `_helpers.py:119-123` | |
| `calibration source 'source_acquired_on' must use YYYY-MM-DD` | `_helpers.py:113-117` | |
| `cannot infer calibration source format for <path>` | `derive.py:35` | Add an explicit `"format"` field; suffix inference covers `.asc`/`.ascii`, `.geojson`/`.json`, `.shp` |
| `unsupported calibration source format '<fmt>'` | `derive.py:46` | |
| `fibonacci_coastal_land_fraction requires a shapefile source` | `derive.py:83` | |
| `<statistic> requires an OPeNDAP ASCII grid source` | `derive.py:90` | ETOPO relief statistics |
| `<statistic> requires a WorldClim GeoTIFF ZIP source` | `derive.py:97` | |
| `<statistic> requires a HydroBASINS archive catalog` | `derive.py:104` | |
| `<statistic> requires a HydroRIVERS shapefile ZIP archive` | `derive.py:111` | |
| `HydroRIVERS minimum_upstream_area_km2 must match the generated Hack-fit floor of <n> km2` | `derive.py:117-121` | The source-side minimum must match `HACK_FIT_MINIMUM_BASIN_AREA_KM2`, otherwise the comparison is not scale-matched |
| `derived source value for '<metric>' must be finite` | `derive.py:150` | |
| `derived target range for '<metric>' is inverted` | `derive.py:166` | `target_min > target_max` |
| `calibration source 'sample_cell_count' must be at least 128` | `src/magic_geo/calibration/sampling.py:21`, `:83`, `:142` | The Fibonacci resampling statistics need a real mesh |
| `matched Fibonacci relief statistics require a global OPeNDAP grid` | `sampling.py:87` | |
| `<path> has a fill value at a sampled Fibonacci point` | `sampling.py:96` | Grid has no-data at a sample site |
| `matched Fibonacci relief statistics require both land and ocean samples` | `sampling.py:102` | |
| `<statistic> requires WorldClim variable '<var>'` | `sampling.py:150` | |
| `<path> has no complete twelve-month WorldClim land samples` | `sampling.py:168` | |
| `fibonacci_coastal_land_fraction requires geographic lon/lat polygons` / `requires a polygon shapefile` | `sampling.py:29`, `:32` | |
| `calibration targets must be a list or an object with a 'targets' list` | `_helpers.py:22` | |
| `calibration sources must be a list or an object with a 'sources' list` | `_helpers.py:33` | |
| `calibration target missing '<key>'` / `calibration target '<key>' must be numeric` / `must be finite` | `_helpers.py:44-55` | |
| `unsupported calibration statistic '<name>'` | `_helpers.py:163` | |
| `polygon shapefile feature is missing its bounding box` / `missing polygon parts` / `shapefile record has invalid part indexes` | `_helpers.py:225-257` | Corrupt or unsupported shapefile |

### `calibrate` coverage vs fit

Two separate policies:

- `--require-all-metrics` checks `summary["external_calibration_complete"]` — every target metric had a corresponding world metric. Missing names appear as `report["missing_world_metrics"]` (`src/magic_geo/calibration/evaluate.py:487`) and are echoed in the failure line.
- `--require-all-passed` checks that every check passed **and** that there was at least one check (`src/magic_geo/cli/commands/calibrate.py:86-91`).

`report["available_world_metrics"]` (`evaluate.py:486`) tells you what the world actually exposes — use it to fix a metric-name mismatch in a hand-written target bundle.

The project is explicit that internal closure does not substitute for Earth fit. The README records that against the checked-in 22-metric authoritative bundle, coverage is complete at 22/22 while fit is 17/22, with failures in Natural Earth coastal land fraction, all three ETOPO relief metrics, and the HydroBASINS non-Antarctic endorheic watershed-area fraction. A failing `calibrate --require-all-passed` on Earth-like settings may therefore be reporting a known, documented gap rather than a regression you introduced.

---

## Test failures and skips

### Running the suites

```bash
pip install -e ".[test]"          # add ",debug" to also run the workbench/server tests
python -m pytest                  # full suite
python -m pytest -m "not slow"    # skips the exhaustive validate-command tier
python -m pytest -m "slow"        # exhaustive validate-command tier only
python -m pytest --cov --cov-report=term-missing
```

The one marker is declared at `pyproject.toml`: `slow: exhaustive CLI validate-command coverage; deselect with -m "not slow"`. It is applied as a module-level `pytestmark` in the eight `tests/test_validate_cli_*.py` modules. Per the README those are 21% of the tests but 54% of the runtime, because each case runs a full validation over a generated world.

Native tests use CTest:

```bash
cmake --build build                          # builds the test executables too
ctest --test-dir build --output-on-failure
```

`BUILD_TESTING` comes from `include(CTest)` at `CMakeLists.txt:5` and defaults to `ON`; the whole test block is `if(BUILD_TESTING)` at `:223`.

### Skips and import gates

| Symptom | Where | Cause | Fix |
|---|---|---|---|
| `SkipTest: debug server tests require magic-geo[debug]: <exc>` — whole module skipped | `tests/test_debug_server.py:21-28` | `pyarrow`, `pyarrow.ipc`, `pyarrow.parquet`, or `fastapi` missing | `pip install -e '.[debug]'` |
| `SkipTest: rerun export tests require rerun-sdk: <exc>` — whole module skipped | `tests/test_debug_rerun.py:22-25` | `rerun` not installed (it is an undeclared optional extra) | `pip install rerun-sdk` |
| CTest `magic_geo_cuda_compute` reported as skipped | `CMakeLists.txt:507-511`, `SKIP_RETURN_CODE 77` | The test binary exits 77 when no compatible GPU is present | Expected on GPU-less hosts |
| CTest `magic_geo_cuda_compute` absent entirely | `CMakeLists.txt` guards it behind `MAGIC_GEO_CUDA_ENABLED` | The build fell back to `cuda_compute_stub.cpp` | Build with CUDA 12.8+ to register it |
| CTest `magic_geo_c_api_v1_client` absent | `CMakeLists.txt:513` requires `CMAKE_SIZEOF_VOID_P EQUAL 8` | Non-64-bit host | Expected |
| Two CTest names from one binary | `CMakeLists.txt:473` registers `magic_geo_native_api_test` a second time with `ENVIRONMENT "MAGIC_GEO_VALIDATE_FIBONACCI_KNN=1"` | By design | The `magic_geo_fibonacci_knn_reference` entry is the same executable under that env var |

### Common test-run problems

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'support'` | The shared helpers live in `tests/support/` (which has an `__init__.py`) and are imported as `from support import worlds`. That works because pytest inserts `tests/` on `sys.path` — `tests/` itself has **no** `__init__.py` | Run `python -m pytest` from the repository root; `testpaths = ["tests"]` in `pyproject.toml` is rootdir-relative. Avoid `--import-mode=importlib` unless you also add `tests/` to the path |
| Every test errors with the native-library `RuntimeError` | The `.so`/`.dll`/`.dylib` was never built | `cmake -S . -B build && cmake --build build` |
| Coverage report shows 0% for the C++ core | `[tool.coverage.run] source = ["magic_geo"]` measures Python only | Expected; use the CTest suite for the native core |
| Coverage looks like it measured a stale copy | It cannot: `source` is the *import name*, and `[tool.coverage.paths] magic_geo = ["src/magic_geo", "*/site-packages/magic_geo"]` merges the editable and installed locations | — |
| Suite is much slower with `--cov` | Branch coverage is on (`branch = true`); the README notes instrumenting the generation-heavy suite takes roughly four times its normal runtime | Run coverage separately from the fast loop |
| Parallel runners each pay a full generation | `tests/support/worlds.py` caches generated worlds **per process** | Expected; reduce worker count if generation dominates |
| A test mutated a shared world and later tests fail | `cached_world_readonly(key)` returns the shared object and must not be mutated; `cached_world(key)` returns a deep copy | Use `cached_world` when you intend to mutate |
| A CLI test "passes" with an empty output and exit 1 | Typer's `CliRunner` turns an uncaught exception into `exit_code == 1` with empty output; only `result.exception` (non-`SystemExit`) distinguishes a crash from a reported failure | Use `tests/support/cli.py::assert_no_cli_crash` |

There is no `tests/conftest.py`; fixtures were consolidated into `tests/support/` (commit `11b16b9`). If you are following older instructions that reference `conftest` fixtures, they no longer exist.

---

## FAQ

**1. Why does `magic-geo backend` report `"active_backend": "cpu"` when my GPU is clearly detected?**

Because `backend_info()` builds a capability-only probe, not a generation session. The reason string says so verbatim: `capability-only probe; no generation is active` (`cpp/src/opencl_compute.cpp:849-852`). Look at `opencl_available`, `opencl_qualifying_gpu_device_count`, `cuda_compiled`, and `cuda_available` instead, and at the `backend` object inside a *generated world* to see what actually ran.

**2. Do I need to rebuild the C++ core after pulling changes?**

Yes, whenever the native sources or the world schema changed. Three guards will tell you: `native library does not expose the current V3 JSON and MessagePack ABI; rebuild magic_geo_native from the current source tree` (`src/magic_geo/native.py:140-144`), `native library returned unsupported world schema_version ...` (`:236-241`), and `native library returned retired fields in a schema-2 world: ...` (`:243-247`). `cmake --build build` restages the library into `src/magic_geo/`, and Python reloads it on the next call (there is no process-level cache).

**3. Where does `magic-geo generate` look for its configuration?**

`./magic-geo.yaml`, relative to the current working directory (`src/magic_geo/cli/commands/generate.py:20-22`). That is also `init-config`'s default output path (`src/magic_geo/cli/commands/config.py:18-20`), so `magic-geo init-config && magic-geo generate` works with no flags. `--config` has `exists=True`, so a missing file is a Typer usage error (exit 2), not a Python exception.

**4. Should I write `.json` or `.mgeo`?**

Both are fully supported and every command that consumes a world accepts either. `.mgeo` is a versioned, CRC32-checksummed MessagePack container (`src/magic_geo/serialization.py:28-35`); on a 128-cell smoke world measured here it was 4,645,747 bytes versus 7,568,614 bytes of JSON. `format="auto"` picks `mgeo` from the suffix when writing and sniffs the magic bytes when reading — a `.json`-named `.mgeo` file still loads. Use JSON when you want to read or diff the file by hand.

**5. Why does `magic-geo validate` fail on a world I generated with `--geo-only`?**

`validate` is the full-world gate and unconditionally runs the settlement, route, political, trade, land-use, frontier, worldbuilding, cultural, historical, demographic, dynasty, logistics, campaign, market, and phonology replays, which a geo-only world does not contain. Use `magic-geo validate-geo` (and `validate-geo-suite` for the scenario matrix). Verified: the same 128-cell geo-only world produced 184 `FAIL` lines from `validate` — 22 of them `... replay invalid` — and `OK geo | checks=150 errors=0 warnings=0 not_applicable=3` from `validate-geo`.

**6. I asked for 4,096 cells and got 4,412. Is that a bug?**

No — you are using `mesh.backend: geodesic_icosahedron`. The frequency is `ceil(sqrt((cell_count - 2) / 10))` and the mesh has `10*f^2 + 2` points (`cpp/src/engine/mesh.cpp:840-844`, `:907-909`), so `cell_count` is a lower-bound target. Measured: 128→162, 512→642, 4096→4412. The `fibonacci_sphere` backend produces exactly the requested count. Compare `summary.cell_count` across runs, not the config value.

**7. Is generation deterministic, and what changes results?**

Determinism is a stated engine invariant: "Preserve RNG consumption, OpenMP schedules, floating-point expression order, serializer key order, and precision unless a schema/behavior change is intended" (`cpp/src/engine/README.md`, invariant #4). `run.seed` is an unsigned 64-bit master seed used by every deterministic random process (`src/magic_geo/config.py:129-134`). What *can* change results: a different `compute.backend` (parity is checked with tolerances and invariants, not byte hashes), a different mesh backend or cell count, any parameter change, and a rebuilt library with different simulation code. `compute.backend: cpu` is the deterministic reference and does not probe either accelerator runtime.

**8. What does `--cells` do that editing the YAML would not?**

Nothing semantically — it dumps the loaded config, replaces `mesh.cell_count`, and re-validates the whole model (`src/magic_geo/cli/commands/generate.py:49-52`). It exists for quick smoke runs. Because it re-validates, it can trip the `plate_count must be smaller than mesh.cell_count` cross-field rule even though the on-disk config was valid. Its Typer bound is `min=128`.

**9. Do I need `pip install '.[debug]'`?**

Only for the debug/visualization surface: `magic-geo serve`, `export-debug`, and `export-debug-map`. The extra pulls `pyarrow>=19`, `duckdb>=1.2`, `fastapi>=0.115`, and `uvicorn[standard]>=0.34`. Each command catches the `ImportError` and exits 2 with an explicit `pip install 'magic-geo[debug]'` hint. `export-rerun` needs a *separate*, undeclared package: `pip install rerun-sdk`.

**10. Can I expose the web workbench on `0.0.0.0`?**

Technically yes (`--host 0.0.0.0` or `MAGIC_GEO_HOST=0.0.0.0`; Docker sets exactly that inside the container). But the workbench is documented as a trusted-local, single-user tool with no authentication, no authorization, no per-user isolation, and no TLS. Anyone who can reach the port can read workspace data and submit or cancel jobs. Keep it on loopback, or front it with an authenticating reverse proxy. In Compose, `MAGIC_GEO_PUBLISH_HOST` defaults to `127.0.0.1` for that reason.

**11. Why does my second workbench job just sit in `queued`?**

The job manager runs a single worker: `ThreadPoolExecutor(max_workers=1, thread_name_prefix="magic-geo-web")`. One job runs at a time and everything else queues. Additionally, submitting an identical `(operation, arguments)` pair while one is active returns the existing job instead of creating a second, and a submission whose output overlaps an active job's output is rejected with `output already targeted by an active job: <paths>` (`src/magic_geo/web_jobs.py:512-517`).

**12. A validation or calibration job failed — did I lose the report?**

No. `validate-geo`, `validate-geo-suite`, `calibrate`, and `calibrate-ensemble` all write their report **before** the policy exit, and the workbench treats those four as `_REPORTING_OPERATIONS`, snapshotting their artifacts even on failure. Download links serve immutable per-job snapshots verified by `(st_dev, st_ino, st_size, st_mtime_ns)` fingerprint, so a pre-existing untouched path is never exposed.

**13. Why do the calibration commands need `bash scripts/fetch_*.sh` first?**

The repository ships source *manifests* (`configs/calibration_sources.*.json`) with pinned SHA-256 digests and license metadata, not the datasets themselves. `derive-targets` fails with `calibration source does not exist: <path>` (`src/magic_geo/calibration/derive.py:74-75`) until the matching fetcher has installed the data under `calibration_data/`. Relative manifest paths resolve against the manifest's directory (`src/magic_geo/calibration/sources.py:21-25`), so you can run the commands from anywhere.

**14. What is the maximum world size?**

`mesh.cell_count` is capped at 200,000 by both the Pydantic model (`src/magic_geo/config.py:244-249`) and the native validator (`cpp/src/engine/core.cpp:287-289`). Reading a world file is capped at 2 GiB encoded by default (`DEFAULT_MAX_WORLD_FILE_BYTES`), which is "an encoded-input bound, not a promise about the larger decoded Python graph". The debug map export refuses caches above 200,000 cells, 2,000,000 mesh vertices, or 2,000,000 triangles. In practice RAM for the decoded Python object graph, not these caps, is the binding constraint.

**15. Which numbers in a generated world can I treat as physical?**

Fewer than the field names suggest, and the document tells you which. The serializers preserve explicit *false* authority flags: no dry-rock mass, sediment density, porosity, compaction, grain provenance, chemical weathering, physical source/sink, material provenance, solid volume, phase, mass-weighted age, mantle, slab, global crust-cycle, subduction polarity, or connected-fragment topology claims are made; physical time, process-rate calibration, and whole-coupling timestep convergence stay false; every reservoir transfer carries `physical_basis_resolved = false`. The plate-boundary ledger's oceanic side is a subducting/overriding *candidate pair* with physical sides explicitly `unknown`. Backend telemetry states `crust_overlap_accelerator_complete_parity_demonstrated: false`. Read the flags next to a number before you cite the number.

---

## Limitations and unresolved claims

- **This page is not exhaustive over `validate`.** The full-world gate contains 1,089 distinct `failures.append(...)` sites, plus 18 pure per-domain validators in `src/magic_geo/cli/validators/` and 18 delegated top-level validators. Only the schema/planet phase-1 gate and representative phase-2 lines are quoted here; the remainder are documented per-domain on the feature pages. Measured here, a 128-cell geo-only world produced 184 `FAIL` lines from a single `validate` run.
- **Phase-1 masking is real.** A `schema_version`, retired-field, or planet-parameter failure exits 1 before any other diagnostic runs (`src/magic_geo/cli/commands/validate.py:119-122`). A clean-looking two-line failure does not mean the rest of the world is valid.
- **Physical time is not calibrated.** `erosion.maturation_timestep_ma` is described as *nominal* millions of years per transition (`src/magic_geo/config.py:382-387`); `plate_motion_scale_deg_per_step` and `oceanic_crust_aging_ma_per_step` are defined against a "five-million-year reference step". The engine keeps physical-time and process-rate calibration flags false. Do not convert stage indices into geological dates.
- **Accelerator parity is explicitly unproven.** `crust_overlap_accelerator_complete_parity_demonstrated`, `..._geometry_parity_demonstrated`, `..._categorical_parity_demonstrated`, and `..._coverage_membership_parity_demonstrated` are all `false` in the shipped telemetry; the continuous shadow is `crust_overlap_continuous_shadow_authoritative: false` and its result is discarded (`crust_overlap_continuous_shadow_result_used_for_state: false`). Authoritative forward crust overlap is CPU-only. A GPU run that "works" is not evidence of equivalence.
- **Subduction polarity and mass provenance are unresolved.** The plate-boundary segment ledger emits candidate side pairs with physical sides `unknown`, and the dry-rock reservoir counter-model marks `physical_basis_resolved = false` on every transfer. Errors raised from `crust_material.cpp` / `crust_reservoir.cpp` are internal-consistency failures of a non-authoritative shadow, not physical findings.
- **Earth fit is incomplete and documented as such.** The README records 17/22 external metrics passing at complete 22/22 coverage, with named failures (Natural Earth coastal land fraction, three ETOPO relief metrics, HydroBASINS endorheic area fraction). A `calibrate --require-all-passed` failure may be that known gap.
- **The `earthlike` validation profile is regime-dependent.** Verified here: a 128-cell smoke world passes `--profile generic` and fails `--profile earthlike` on `calibration_pass_fraction`. Profile choice is part of the question you are asking, not a strictness knob.
- **The workbench security model is containment, not isolation.** Path confinement, staged publication, immutable artifact snapshots, and fixed subprocess argv are all real, but there is no authentication, authorization, per-user isolation, or TLS. Do not treat the containment measures as a tenant boundary.
- **Timings and sizes here are single-host measurements.** The byte counts, cell-count mappings, and command transcripts in this page came from one Linux development machine with an OpenCL-capable NVIDIA device and a CUDA-stub build (`cuda_compiled: false`). Your `backend_info()` will differ.
- **Some limits are numerical safety caps, not physics.** The 64 control-volume segments per cell, 8 reciprocal mesh segments per cell, 1,024 packets per surface owner, 1,000,000 live reservoir packets, and 1,000,000 per-step transfers are fail-closed memory-safety bounds. Exceeding one says nothing about the planet.
- **Not verified in source for this page:** the exact wall-clock runtimes quoted in the README's testing section (`~29 min` full, `~13 min` fast tier, `~16 min` slow tier, `~2 h` with coverage, `~5 s` for CTest) were not re-measured here; treat them as the README's figures for its own host.

---

## See also

- [Installation and Build](./02-installation-and-build.md) — CMake options, dependency ladder, wheel packaging rules
- [Quickstart](./03-quickstart.md) — the minimal working path before anything goes wrong
- [Configuration Reference](./05-configuration-reference.md) — every field, bound, and profile in detail
- [CLI Reference](./06-cli-reference.md) — complete option tables and exit-code semantics
- [Python API](./07-python-api.md) — `generate_world`, `generate_geo_world`, and the `ctypes` boundary
- [Native Engine (C++ Core)](./08-native-engine.md) — stage ordering, invariants, and the C ABI
- [Compute Backends (CPU, OpenCL, CUDA)](./09-compute-backends.md) — selection policy, thresholds, and telemetry fields
- [Serialization and World Formats](./11-serialization.md) — `.mgeo` framing, limits, and the value model
- [Validation](./12-validation.md) — what `validate` and `validate-geo` actually check
- [Geo Validation Suite](./13-geo-validation-suite.md) — scenario matrix, relations, and layer contracts
- [Calibration Against Real-Earth Data](./14-calibration.md) — datasets, manifests, and fit policy
- [Web Workbench](./15-web-workbench.md) — routes, jobs, workspace policy, and the security model
- [Debug Exports and Visualization](./16-debug-and-visualization.md) — cache layout, revisions, and map export
- [Rendering and Map Output](./17-rendering.md) — SVG and PPM renderers
- [Testing and Quality Gates](./18-testing.md) — suite structure, markers, and native CTest coverage
- [Docker Deployment](./19-docker-deployment.md) — `.env` reference and the publish-host default
- [Glossary](./21-glossary.md) — terminology used across these messages
