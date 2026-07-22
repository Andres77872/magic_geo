# Installation and Build

[Wiki home](./README.md) > Installation and Build

`magic-geo` is a two-part artifact: a pure-Python package (`src/magic_geo/`) that owns configuration, validation, orchestration and file output, and a C++20 shared library (`magic_geo_native`) that runs the simulation and is loaded through `ctypes` — never as a CPython extension module. Installing the Python package and building the native core are therefore two independent steps, and the build deliberately stages the shared library *into the Python package directory* so an editable checkout works with no extra path plumbing. This page enumerates every prerequisite, every CMake cache option, the staging rules, the `magic-geo backend` verification output, the optional-dependency extras, the CUDA/OpenMP detection ladders, and the packaging gates enforced by `setup.py`.

## On this page

- [Prerequisites](#prerequisites)
- [Step 1: install the Python package](#step-1-install-the-python-package)
- [Step 2: configure and build the native core](#step-2-configure-and-build-the-native-core)
- [CMake option reference](#cmake-option-reference)
- [Library staging into src/magic_geo](#library-staging-into-srcmagic_geo)
- [Step 3: verify the install with `magic-geo backend`](#step-3-verify-the-install-with-magic-geo-backend)
- [Running the native test suite](#running-the-native-test-suite)
- [Optional dependency extras](#optional-dependency-extras)
- [Building with and without CUDA](#building-with-and-without-cuda)
- [OpenMP detection](#openmp-detection)
- [OpenCL is a runtime dependency only](#opencl-is-a-runtime-dependency-only)
- [Wheels, sdists and the ABI symbol check](#wheels-sdists-and-the-abi-symbol-check)
- [Platform notes and library naming](#platform-notes-and-library-naming)
- [Build troubleshooting](#build-troubleshooting)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

## Prerequisites

The README states the minimum set in one sentence (`README.md:18-20`); each entry below is traced to the file that actually enforces it.

| Component | Minimum version | Enforced / declared at | Notes |
| --- | --- | --- | --- |
| Python | `>=3.11` | `pyproject.toml:10` (`requires-python`) | The package is src-layout (`pyproject.toml:33-34`); the console script is `magic-geo = "magic_geo.cli:main"` (`pyproject.toml:30-31`). |
| CMake | `3.20` | `CMakeLists.txt:1` (`cmake_minimum_required`) | `include(CTest)` at `CMakeLists.txt:5` is what introduces `BUILD_TESTING`. |
| C++ compiler | C++20 | `CMakeLists.txt:76-78` (`CMAKE_CXX_STANDARD 20`, `CXX_STANDARD_REQUIRED ON`, `CXX_EXTENSIONS OFF`) | No specific GCC/Clang/MSVC minimum version is pinned anywhere in the tree — not verified in source. Compiler-family branches only test `CMAKE_CXX_COMPILER_ID MATCHES "GNU\|Clang"` (e.g. `CMakeLists.txt:137`). |
| Threads | required | `CMakeLists.txt:81` (`find_package(Threads REQUIRED)`) | `Threads::Threads` is linked into four of the five test executables that link the shared library (`CMakeLists.txt:275-278`, `:408-411`, `:435-438`, `:461-464`); `magic_geo_c_api_v1_client_test` links the library alone (`:518-521`). |
| OpenMP | optional | `CMakeLists.txt:80`, used at `CMakeLists.txt:188-191` | Found → `OpenMP::OpenMP_CXX` linked and `MAGIC_GEO_HAS_OPENMP=1` defined. Not found → single-threaded core, build still succeeds. |
| CUDA toolkit | `12.8` | `CMakeLists.txt:35-39` (`CMAKE_CUDA_COMPILER_VERSION VERSION_GREATER_EQUAL 12.8` **and** `find_package(CUDAToolkit 12.8 QUIET)`) | Entirely optional. Absent or older → the CUDA runtime stub is compiled instead (`CMakeLists.txt:19`). |
| OpenCL | none at build time | `CMakeLists.txt:193` adds only `${CMAKE_DL_LIBS}`; no OpenCL library is ever linked | The ICD loader is opened at runtime with `dlopen("libOpenCL.so.1")`, falling back to `libOpenCL.so` (`cpp/src/opencl_compute.cpp:159-175`). No headers or libraries are needed to build. |
| `setuptools` | `>=70.1` | `pyproject.toml:1-3` | Build backend is `setuptools.build_meta`. |

Declared Python runtime dependencies (`pyproject.toml:11-16`):

| Package | Constraint |
| --- | --- |
| `msgpack` | `>=1.1,<2` |
| `pydantic` | `>=2.10` |
| `PyYAML` | `>=6.0.2` |
| `typer` | `>=0.16.0` |

## Step 1: install the Python package

The documented order in `README.md:22-30` installs Python **before** the native library exists. That works because the ABI gate described below is registered on the `bdist_wheel` command only (`setup.py:89`), not on the editable-install path:

```bash
python -m pip install -e .   # Python CLI + library (editable)
```

This makes the `magic-geo` console script available and puts `src/magic_geo/` on the import path. At this point `magic-geo backend` will still fail, because no shared library has been staged yet — that is expected.

For a non-editable install from a checkout you must build the native core first; see [Wheels, sdists and the ABI symbol check](#wheels-sdists-and-the-abi-symbol-check).

## Step 2: configure and build the native core

```bash
cmake -S . -B build          # configure the C++ simulation core
cmake --build build          # stages libmagic_geo_native.so into src/magic_geo/
```

Because `CMAKE_BUILD_TYPE` is forced to `Release` when neither it nor `CMAKE_CONFIGURATION_TYPES` is set (`CMakeLists.txt:71-74`), a bare `cmake -S . -B build` on a single-config generator already produces the Release artifact that the packaging workflow expects. On a multi-config generator (Visual Studio, Xcode) you must select it explicitly:

```bash
cmake -S . -B build
cmake --build build --config Release
```

`BUILD_TESTING` defaults to `ON` (from `include(CTest)`, `CMakeLists.txt:5`), so `cmake --build build` also builds the native test executables gated by `if(BUILD_TESTING)` at `CMakeLists.txt:223-528`. Pass `-DBUILD_TESTING=OFF` for a production/library-only build — this is exactly what the Docker builder stage does (`Dockerfile:27-31`).

A minimal production configure, matching the container build:

```bash
cmake -S . -B build \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_TESTING=OFF \
  -DMAGIC_GEO_ENABLE_CUDA=OFF
cmake --build build --config Release -j"$(nproc)"
```

### What gets compiled

`magic_geo_native` is a single `SHARED` target (`CMakeLists.txt:94-129`) built from `cpp/src/c_api.cpp`, `cpp/src/engine.cpp`, 28 `cpp/src/engine/*.cpp` translation units, `${MAGIC_GEO_CUDA_SOURCE}` (real `.cu` or stub), `cpp/src/crust_overlap_shadow.cpp` and `cpp/src/opencl_compute.cpp`. Both `crust_overlap_shadow.cpp` and `opencl_compute.cpp` are compiled unconditionally — the OpenCL path is dynamic-loading only, so it costs nothing at build time.

Target-level properties that affect the artifact (`CMakeLists.txt:131-151`):

| Setting | Value | Source | Why it matters |
| --- | --- | --- | --- |
| `target_include_directories` | `cpp/include` (PRIVATE) | `CMakeLists.txt:131` | The public header `cpp/include/magic_geo/native.hpp` is not installed by the build. |
| `target_compile_features` | `cxx_std_20` (PRIVATE) | `CMakeLists.txt:132` | — |
| CXX compile option | `-ffp-contract=off` under `$<$<COMPILE_LANGUAGE:CXX>>`, GNU/Clang only | `CMakeLists.txt:137-142` | Keeps FMA contraction from introducing avoidable backend drift. The comment is explicit that cross-compiler/GPU parity is validated with numeric tolerances and physical invariants, **not** byte hashes. |
| `CXX_VISIBILITY_PRESET` | `hidden` | `CMakeLists.txt:146` | Only the declared public symbols are exported. |
| `VISIBILITY_INLINES_HIDDEN` | `YES` | `CMakeLists.txt:150` | — |
| `OUTPUT_NAME` | `magic_geo_native` | `CMakeLists.txt:147` | Produces the platform names in the [naming table](#platform-notes-and-library-naming). |
| `install(TARGETS ...)` | `LIBRARY DESTINATION magic_geo`, `RUNTIME DESTINATION magic_geo` | `CMakeLists.txt:217-221` | Only relevant if you run `cmake --install`; the editable workflow uses the staging directory instead. |

Because visibility is hidden by default, the exported surface is small. On the Linux CPU/OpenMP build measured for this page, `libmagic_geo_native.so` exports 19 dynamic text symbols: 10 `extern "C"` ABI entry points (`magic_geo_backend_info_json`, `magic_geo_generate_json`, `..._json_v2`, `..._json_v3`, `..._geo_json_v2`, `..._geo_json_v3`, `..._msgpack_v3`, `..._geo_msgpack_v3`, `magic_geo_free_string`, `magic_geo_free_buffer`) plus 9 mangled `magic_geo::` C++ facade symbols. Verify with:

```bash
nm -D --defined-only src/magic_geo/libmagic_geo_native.so | grep " T " | c++filt | sort
```

## CMake option reference

### Options and cache variables defined by this project

| Name | Type | Default | Effect |
| --- | --- | --- | --- |
| `MAGIC_GEO_ENABLE_CUDA` | `option` (BOOL) | `ON` | Master switch for the CUDA detection ladder (`CMakeLists.txt:7-11`, consumed at `:21`). `ON` only *attempts* CUDA; every failure path still builds the stub. `OFF` skips detection entirely and emits `magic-geo CUDA backend: disabled by MAGIC_GEO_ENABLE_CUDA=OFF` (`CMakeLists.txt:67-69`). |
| `MAGIC_GEO_CUDA_ARCHITECTURES` | `CACHE STRING` | `75-real;75-virtual;80-real;86-real;89-real;90-real;120-real;120-virtual` | Value of the `CUDA_ARCHITECTURES` target property when CUDA is enabled (`CMakeLists.txt:12-17`, applied at `:208`). Provides SASS for `sm_75`, `sm_80`, `sm_86`, `sm_89`, `sm_90`, `sm_120` plus forward PTX at the 7.5 and 12.0 baselines (`docs/cuda_rtx5090_optimization.md:55-58`). Ignored when CUDA is not enabled. |
| `MAGIC_GEO_LIBRARY_OUTPUT_DIRECTORY` | `CACHE PATH` | `${CMAKE_CURRENT_SOURCE_DIR}/src/magic_geo` | Destination of `LIBRARY_OUTPUT_DIRECTORY` and `RUNTIME_OUTPUT_DIRECTORY` for `magic_geo_native` (`CMakeLists.txt:83-88`, applied at `:148-149`). Overriding it to any other path disables the per-config isolation block (`CMakeLists.txt:158-186`) and leaves placement fully caller-controlled. |
| `CMAKE_BUILD_TYPE` | `CACHE STRING` | `Release`, forced only when both `CMAKE_BUILD_TYPE` and `CMAKE_CONFIGURATION_TYPES` are empty | Set with `FORCE` plus a `STRINGS` property of `Debug;Release;RelWithDebInfo;MinSizeRel` (`CMakeLists.txt:71-74`). |
| `BUILD_TESTING` | `option` (BOOL, from `include(CTest)`) | `ON` | Gates the entire native test block, `CMakeLists.txt:223-528`. With `OFF`, no test executable is compiled and no CTest name is registered. |

### Non-cache variables the configure step derives

| Name | Initial value | Becomes | Source |
| --- | --- | --- | --- |
| `MAGIC_GEO_CUDA_SOURCE` | `cpp/src/cuda_compute_stub.cpp` | `cpp/src/cuda_compute.cu` on full CUDA success | `CMakeLists.txt:19`, `:41` |
| `MAGIC_GEO_CUDA_ENABLED` | `OFF` | `ON` on full CUDA success | `CMakeLists.txt:20`, `:42` |
| `_MAGIC_GEO_PACKAGE_LIBRARY_OUTPUT_DIRECTORY` | `${CMAKE_CURRENT_SOURCE_DIR}/src/magic_geo` | constant | `CMakeLists.txt:89-92` — the reference value the staging isolation compares against |
| `CMAKE_CUDA_FLAGS_INIT` | inherited | gains `-U_GNU_SOURCE -D_DEFAULT_SOURCE=1 -D_POSIX_C_SOURCE=200809L -D_XOPEN_SOURCE=700` | `CMakeLists.txt:27-30`, only when `MAGIC_GEO_ENABLE_CUDA` is on |

### Standard CMake variables worth passing

These are not defined by the project but are read by the detection ladder, and appear in the audited CUDA build recipe (`docs/cuda_rtx5090_optimization.md:76-83`):

| Variable | Purpose |
| --- | --- |
| `CMAKE_CUDA_COMPILER` | Point `check_language(CUDA)` at a specific `nvcc`. |
| `CUDAToolkit_ROOT` | Point `find_package(CUDAToolkit 12.8 QUIET)` at a specific toolkit. |
| `CMAKE_INSTALL_PREFIX` | Destination root for the optional `install(TARGETS ...)` at `CMakeLists.txt:217-221`. |

## Library staging into src/magic_geo

The Python layer never searches a build tree. `native._library_path()` resolves the library from exactly two places (`src/magic_geo/native.py:110-127`):

1. `MAGIC_GEO_NATIVE_LIBRARY`, if set — `Path(override).expanduser().resolve()`. If that path is not a file it raises `RuntimeError("MAGIC_GEO_NATIVE_LIBRARY does not name a file: …")` (`native.py:111-118`).
2. Otherwise `Path(__file__).resolve().parent` — the installed `magic_geo` package directory — joined with the **host-native filename only** (`native.py:119-123`). There is no cross-platform name fallback: `_native_library_names()` returns a one-element tuple (`native.py:30-37`).

`MAGIC_GEO_LIBRARY_OUTPUT_DIRECTORY` therefore defaults to precisely the directory that resolution rule 2 above will search, which is why `cmake --build build` alone is enough to make an editable checkout functional. `.gitignore:20` excludes the staged `.so` from version control, and `.dockerignore:20-22` excludes all three staged host binaries so a host build can never leak into an image.

### Per-configuration isolation

When (and only when) `MAGIC_GEO_LIBRARY_OUTPUT_DIRECTORY` still equals the package directory, the build applies extra isolation (`CMakeLists.txt:158-186`):

| Configuration | `LIBRARY_OUTPUT_DIRECTORY_<CONFIG>` / `RUNTIME_OUTPUT_DIRECTORY_<CONFIG>` | `ARCHIVE_OUTPUT_DIRECTORY_<CONFIG>` | Rationale |
| --- | --- | --- | --- |
| `Release` | `${CMAKE_CURRENT_SOURCE_DIR}/src/magic_geo` (pinned explicitly) | not set by this project | Multi-config generators append a config subdirectory unless the per-config property is explicit; pinning keeps the production DLL/dylib beside the Python package on Windows/macOS exactly as on single-config Linux. |
| `Debug` | `${CMAKE_CURRENT_BINARY_DIR}/native/Debug` | `${CMAKE_CURRENT_BINARY_DIR}/native/Debug` | A non-Release build must not overwrite the packaged Release artifact, and must not silently make another build tree test the wrong binary. |
| `RelWithDebInfo` | `${CMAKE_CURRENT_BINARY_DIR}/native/RelWithDebInfo` | same | same |
| `MinSizeRel` | `${CMAKE_CURRENT_BINARY_DIR}/native/MinSizeRel` | same | same |

Consequences to be aware of:

- A `Debug` build **does not** update `src/magic_geo/`. To exercise a debug library from Python, point `MAGIC_GEO_NATIVE_LIBRARY` at `build/native/Debug/libmagic_geo_native.so`.
- If you pass an explicit `-DMAGIC_GEO_LIBRARY_OUTPUT_DIRECTORY=...`, none of this applies; every configuration writes where you asked. This is how the audited CUDA build keeps its artifact out of the package tree (`docs/cuda_rtx5090_optimization.md:76-83`).
- `ARCHIVE_OUTPUT_DIRECTORY` is only overridden for the three isolated configurations. The Windows Release import library (`magic_geo_native.lib`) follows CMake's default archive location, not the package directory.

Keeping a second, non-package build tree is a first-class workflow:

```bash
cmake -S . -B build-cuda \
  -DCMAKE_BUILD_TYPE=Release \
  -DMAGIC_GEO_LIBRARY_OUTPUT_DIRECTORY="$PWD/build-cuda/lib"
cmake --build build-cuda -j
MAGIC_GEO_NATIVE_LIBRARY="$PWD/build-cuda/lib/libmagic_geo_native.so" magic-geo backend
```

## Step 3: verify the install with `magic-geo backend`

```bash
magic-geo backend
```

The command body is a single statement (`src/magic_geo/cli/commands/config.py:52-55`): it calls `magic_geo.api.backend_info()` (`src/magic_geo/api.py:179-182`) → `magic_geo.native.backend_info()` (`native.py:344-346`) → the exported `magic_geo_backend_info_json` → `magic_geo::backend_info_json()` → `detail::compute_backend_info_json()` (`cpp/src/opencl_compute.cpp:3044-3061`), and prints the result with `json.dumps(..., indent=2, sort_keys=True)`.

Two things matter about what that call actually does:

- With no generation in flight, it constructs a **capability-only probe** session with `compute_backend = 1` (`opencl_compute.cpp:3048-3052`). The capability-only branch probes CUDA capability without creating a session and always probes OpenCL, then reports `selected_backend = "cpu"` with the reason `capability-only probe; no generation is active` (`opencl_compute.cpp:828-853`).
- There is no `try`/`except` around `backend_info()` in the CLI, and no global handler in `cli/_app.py`. A missing or stale library therefore surfaces as an uncaught `RuntimeError` traceback with exit code 1, not a tidy typer message.

### Worked example

Output of `magic-geo backend` on a Linux host whose library was built with OpenMP, **without** CUDA, with a working OpenCL ICD (subset of the emitted keys; this probe emitted 178 keys in total):

```json
{
  "active_backend": "cpu",
  "backend_scope": "accelerated_native_kernels_not_end_to_end_pipeline",
  "backend_selection_reason": "capability-only probe; no generation is active",
  "crust_overlap_continuous_shadow_validation_status": "not_run_no_conservative_transition",
  "crust_transport_execution_backend": "cpu",
  "cuda_auto_min_cell_count": 8192,
  "cuda_available": false,
  "cuda_capability_status": "not_compiled",
  "cuda_compiled": false,
  "cuda_error": "CUDA support was not compiled into the native library",
  "cuda_sm_120_auto_min_cell_count": 8192,
  "cuda_uncalibrated_auto_min_cell_count": 32768,
  "initial_selected_backend": "cpu",
  "native_core": "c++20",
  "opencl_auto_min_cell_count": 32768,
  "opencl_available": true,
  "opencl_capability_status": "available",
  "opencl_error": "",
  "opencl_loader_found": true,
  "openmp_enabled": true,
  "openmp_max_threads": 16
}
```

### How to read the output

| Key | Emitted at | What a successful install looks like |
| --- | --- | --- |
| `native_core` | `opencl_compute.cpp:2036` | Always the literal `"c++20"`. Its presence proves the library loaded and the JSON entry point ran. |
| `openmp_enabled` | `opencl_compute.cpp:2037-2041` | `true` iff `MAGIC_GEO_HAS_OPENMP` was defined at compile time, i.e. CMake found OpenMP. `false` is a valid, working single-threaded build. |
| `openmp_max_threads` | `opencl_compute.cpp:2042-2046` | `omp_get_max_threads()` when `_OPENMP` is defined, otherwise the literal `1`. Note the two keys use *different* macros, so they can disagree in an unusual toolchain. |
| `requested_backend` | `opencl_compute.cpp:2047-2049` | `"cpu"` for the probe, because the probe session sets `compute_backend = 1`. This is not a statement about your config file. |
| `selected_backend` / `active_backend` / `initial_selected_backend` | `:2053-2059` | All `"cpu"` for a probe. `active_backend` becomes `"hybrid"` only when a fallback happened *and* accelerator dispatches were recorded. |
| `backend_selection_reason` | `:2060` | `"capability-only probe; no generation is active"` identifies a `magic-geo backend` invocation rather than telemetry embedded in a generated world. |
| `backend_scope` | `:2061-2066` | Always `"accelerated_native_kernels_not_end_to_end_pipeline"`. Read it literally: acceleration covers specific kernels, not the pipeline. |
| `cuda_compiled` | `:2354-2359` | `true` iff `MAGIC_GEO_HAS_CUDA` was defined — i.e. the CUDA ladder fully succeeded at configure time. |
| `cuda_capability_status` | `:2361-2366` | `not_probed` / `not_compiled` / `available` / `unavailable`. The first branch is `!cuda_probe_performed`, so a stub build reports `not_compiled` only once a probe has run — which the capability-only `magic-geo backend` path always does (`opencl_compute.cpp:828-829`). A deferred-`auto` generation session can still report `not_probed` (`:821-826`). |
| `cuda_error` | `:2372` | On a stub build, exactly `"CUDA support was not compiled into the native library"` (`cpp/src/cuda_compute_stub.cpp:23-24`). |
| `cuda_auto_min_cell_count` | `:2326-2328` | Defaults to `CUDA_SM_120_AUTO_MIN_CELL_COUNT` (8192, `opencl_compute.cpp:100`) and is only recomputed when a CUDA device is actually available (`:873-877`). On a stub build the reported 8192 is the struct default, not a measured threshold. |
| `cuda_sm_120_auto_min_cell_count` / `cuda_uncalibrated_auto_min_cell_count` | `:2329-2340` | Compile-time constants `8192` and `32768` (`opencl_compute.cpp:100-101`). |
| `opencl_loader_found` | `:2545` | `true` once `dlopen` succeeded on `libOpenCL.so.1` or `libOpenCL.so`. |
| `opencl_capability_status` | `:2544` | `not_probed` / `probe_failed` / `available` / `no_qualifying_device`. |
| `opencl_available` / `opencl_error` | `:2570-2571` | `opencl_available` is `qualifying_device_count > 0`; `opencl_error` is empty on success. FP64 is mandatory — `opencl_fp64_required` is hardcoded `true` (`:2569`). |
| `opencl_auto_min_cell_count` | `:2344-2346` | Compile-time constant `32768` (`opencl_compute.cpp:99`). |
| `opencl_device_*`, `opencl_platform_*` | `:2628-…` | Emitted **only** when a selected or qualifying device record exists (`opencl_compute.cpp:2619-2628`); their absence is why the total key count varies between hosts. |
| `crust_transport_execution_backend` | `:2067-2072` | Always `"cpu"`. Authoritative forward spherical crust overlap executes on CPU regardless of backend. |
| `crust_overlap_accelerator_complete_parity_demonstrated` | `:2163-2168` | Hardcoded `false`. See [Limitations](#limitations-and-unresolved-claims). |

A full end-to-end smoke check after `backend` succeeds:

```bash
magic-geo generate --config configs/earthlike_seed.yaml --cells 512 --output /tmp/world.json
```

`--cells` has `min=128` (`src/magic_geo/cli/commands/generate.py:28-30`) and overrides `mesh.cell_count` for smoke runs.

## Running the native test suite

```bash
cmake --build build                          # builds the test executables too
ctest --test-dir build --output-on-failure   # 13 native tests, ~5 s
```

The runtime and count come from `README.md:263-275`. The registrations live in `CMakeLists.txt:223-528`:

| CTest name | Executable | Conditional | Registered at |
| --- | --- | --- | --- |
| `magic_geo_initial_oceanic_age` | `magic_geo_initial_oceanic_age_test` | — | `CMakeLists.txt:241-244` |
| `magic_geo_oceanic_age_depth` | `magic_geo_oceanic_age_depth_test` | — | `:263-266` |
| `magic_geo_oceanic_age_depth_integration` | `magic_geo_oceanic_age_depth_integration_test` | links the shared library | `:293-296` |
| `magic_geo_crust_overlap_shadow` | `magic_geo_crust_overlap_shadow_test` | — | `:315-318` |
| `magic_geo_serialization_roundtrip` | `magic_geo_serialization_roundtrip_test` | — (no `-ffp-contract=off` block; same for `magic_geo_crust_reservoir_integration_test`, `magic_geo_native_api_test` and `magic_geo_c_api_v1_client_test` — the source states no rationale) | `:333-336` |
| `magic_geo_plate_boundary_segments` | `magic_geo_plate_boundary_segments_test` | — | `:355-358` |
| `magic_geo_crust_overlap_candidate_fate` | `magic_geo_crust_overlap_candidate_fate_test` | — | `:377-380` |
| `magic_geo_crust_reservoir` | `magic_geo_crust_reservoir_test` | — | `:398` |
| `magic_geo_crust_reservoir_integration` | `magic_geo_crust_reservoir_integration_test` | links the shared library | `:421-424` |
| `magic_geo_sediment_partition` | `magic_geo_sediment_partition_test` | links the shared library | `:454-457` |
| `magic_geo_native_api` | `magic_geo_native_api_test` | links the shared library | `:469` |
| `magic_geo_fibonacci_knn_reference` | *same binary as above* | re-registered with `ENVIRONMENT "MAGIC_GEO_VALIDATE_FIBONACCI_KNN=1"` | `:470-474` |
| `magic_geo_cuda_compute` | `magic_geo_cuda_compute_test` | only `if(MAGIC_GEO_CUDA_ENABLED)`; `SKIP_RETURN_CODE 77` so it skips cleanly with no GPU | `:475-512` |
| `magic_geo_c_api_v1_client` | `magic_geo_c_api_v1_client_test` | only `if(CMAKE_SIZEOF_VOID_P EQUAL 8)` | `:513-527` |

That is 14 registered names from 13 executables on a 64-bit CUDA build; a CPU-only 64-bit build registers 13 names. The Python suite is separate — see [Testing and Quality Gates](./18-testing.md).

## Optional dependency extras

Declared at `pyproject.toml:18-28`.

| Extra | Packages | What it unlocks | What happens without it |
| --- | --- | --- | --- |
| `debug` | `pyarrow>=19`, `duckdb>=1.2`, `fastapi>=0.115`, `uvicorn[standard]>=0.34` | `magic-geo export-debug` (Parquet/JSONL/mesh/VTU cache), `magic-geo export-debug-map` (DuckDB-backed layer PNG + prompt), and `magic-geo serve` (the FastAPI/uvicorn web workbench). | Each command catches `ImportError` on its lazy import and exits **2** with an actionable message: `Debug export requires the optional debug dependencies: pip install 'magic-geo[debug]'` (`cli/commands/export.py:181-185`), `Debug map export requires the optional debug dependencies…` (`export.py:121-129`), `Serving requires the optional debug dependencies…` (`cli/commands/serve.py:76-82`). In the test suite the failure is silent by design: `tests/test_debug_export.py:42-43`, `tests/test_debug_server.py:27-28` raise `SkipTest` at import. |
| `test` | `pytest>=9,<10`, `pytest-cov>=7` | Running `python -m pytest` and `--cov` reports. | `pytest` is simply unavailable; nothing in the library changes. |
| *(undeclared)* `rerun-sdk` | `rerun` | `magic-geo export-rerun` (`.rrd` stage-scrubbable recording). | Exits **2** with `Rerun export requires the rerun-sdk package: pip install rerun-sdk` (`cli/commands/export.py:217-221`). `tests/test_debug_rerun.py:24-25` raises `SkipTest`. This package is **not** in any extra: it appears nowhere in `pyproject.toml:18-28`, and `tests/test_debug_rerun.py:24` calls it "an undeclared, optional visualisation extra". `README.md:259-261` notes only that the test skips unless `rerun-sdk` is installed. |

Notes on partial availability:

- `debug_map_export.py:29-32` imports `duckdb` inside a `try` and sets `duckdb = None` on failure, but `debug_map_export` also imports `debug_server` at module scope (`debug_map_export.py:27`), which imports `duckdb` and `fastapi` unconditionally (`debug_server.py:26-29`). Installing only `pyarrow` therefore does **not** enable the map exporter.
- The Docker runtime installs the wheel with the `debug` extra: `pip install --no-cache-dir "$(echo /wheels/*.whl)[debug]"` (`Dockerfile:45-46`).

```bash
python -m pip install -e '.[debug]'          # web workbench + debug cache
python -m pip install -e '.[test]'           # pytest + coverage
python -m pip install -e '.[debug,test]'     # both
python -m pip install rerun-sdk              # optional, undeclared
```

## Building with and without CUDA

CUDA is optional and is not allowed to weaken the CPU path (`docs/cuda_rtx5090_optimization.md:44-70`). The configure step walks a strict ladder.

### The detection ladder

| # | Condition | CMake message severity + text | Resulting `MAGIC_GEO_CUDA_SOURCE` | Source |
| --- | --- | --- | --- | --- |
| 0 | `MAGIC_GEO_ENABLE_CUDA=OFF` | STATUS `magic-geo CUDA backend: disabled by MAGIC_GEO_ENABLE_CUDA=OFF` | stub | `CMakeLists.txt:67-69` |
| 1 | `check_language(CUDA)` finds no compiler | STATUS `magic-geo CUDA backend: compiler not found; building runtime stub` | stub | `CMakeLists.txt:64-66` |
| 2 | Compiler found but `CMAKE_CUDA_COMPILER_ID` is not `NVIDIA` | **WARNING** `magic-geo CUDA backend disabled: compiler '<id>' is not supported; NVIDIA nvcc 12.8+ is required` | stub | `CMakeLists.txt:58-62` |
| 3 | NVIDIA compiler older than 12.8 | **WARNING** `magic-geo CUDA backend disabled: CUDA <version> cannot compile sm_120; CUDA 12.8+ is required` | stub | `CMakeLists.txt:53-57` |
| 4 | NVIDIA ≥ 12.8 but `find_package(CUDAToolkit 12.8 QUIET)` fails | **WARNING** `magic-geo CUDA backend disabled: CUDA runtime development files were not found; building runtime stub` | stub | `CMakeLists.txt:47-52` |
| 5 | NVIDIA ≥ 12.8 **and** `CUDAToolkit_FOUND` | STATUS `magic-geo CUDA backend: <version>; architectures=<list>` | `cpp/src/cuda_compute.cu`, `MAGIC_GEO_CUDA_ENABLED ON` | `CMakeLists.txt:40-46` |

Before the ladder runs, and only when `MAGIC_GEO_ENABLE_CUDA` is on, `CMAKE_CUDA_FLAGS_INIT` is prepended with `-U_GNU_SOURCE -D_DEFAULT_SOURCE=1 -D_POSIX_C_SOURCE=200809L -D_XOPEN_SOURCE=700` (`CMakeLists.txt:22-30`). The in-source comment explains why: CUDA 13.1 must see these flags *during compiler identification*, before any target exists, because glibc 2.43's GNU feature set exposes new C23 `rsqrt` symbols that collide with CUDA's device declarations. It retains the default, POSIX and X/Open declarations libstdc++ requires while disabling only GNU extensions for CUDA translation units.

### What the CUDA build changes

When `MAGIC_GEO_CUDA_ENABLED` is `ON` (`CMakeLists.txt:195-215`):

| Item | Value | Note |
| --- | --- | --- |
| Compile definition | `MAGIC_GEO_HAS_CUDA=1` | Drives `cuda_compiled` in backend telemetry (`opencl_compute.cpp:2354-2359`). |
| CUDA compile options | `--fmad=false --ftz=false --prec-div=true --prec-sqrt=true -lineinfo` | Applied via `$<$<COMPILE_LANGUAGE:CUDA>>`; the same set is applied to `magic_geo_cuda_compute_test` (`CMakeLists.txt:493-497`). |
| `CUDA_ARCHITECTURES` | `${MAGIC_GEO_CUDA_ARCHITECTURES}` | See the option table. |
| `CUDA_RUNTIME_LIBRARY` | `Static` | Embeds the small runtime support layer so a CUDA-enabled wheel still loads and uses CPU/OpenCL on a host with no separately installed cudart. `libcuda` remains driver-provided; static cudart does **not** bundle a driver (`docs/cuda_rtx5090_optimization.md:62-66`). |
| `CUDA_SEPARABLE_COMPILATION` | `OFF` | — |
| `CUDA_STANDARD` / `CUDA_STANDARD_REQUIRED` | `20` / `ON` | — |
| `CUDA_VISIBILITY_PRESET` | `hidden` | — |

### What the stub does

Every non-success path substitutes `cpp/src/cuda_compute_stub.cpp`, which is a complete, build-preserving implementation of the `CudaComputeSession` interface:

- Its `Impl` constructor sets `telemetry.compiled = false`, `runtime_initialized = false`, `available = false`, `selected_device_ordinal = -1`, and `error = "CUDA support was not compiled into the native library"` (`cuda_compute_stub.cpp:16-28`).
- `probe()` constructs a session and returns that telemetry (`:37-40`); `available()` returns `false` (`:42-44`).
- Every kernel entry point — `run_assign_plates`, `run_smooth_field`, `run_smooth_three_fields`, `run_crust_overlap_continuous_shadow` — calls `throw_cuda_not_compiled()`, raising `std::runtime_error("CUDA backend is unavailable because this build was compiled without CUDA support")` (`:8-12`, `:50-93`).

So a stub build is fully functional for `cpu` and `opencl`; only an explicit `compute.backend: cuda` request fails, and it fails with an actionable message rather than silently degrading (`docs/cuda_rtx5090_optimization.md:51-54`).

### Reproducing an isolated CUDA build

```bash
cmake -S . -B build-cuda \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CUDA_COMPILER=/usr/local/cuda-13.1/bin/nvcc \
  -DCUDAToolkit_ROOT=/usr/local/cuda-13.1 \
  -DMAGIC_GEO_CUDA_ARCHITECTURES='120-real;120-virtual' \
  -DMAGIC_GEO_LIBRARY_OUTPUT_DIRECTORY="$PWD/build-cuda/lib"
cmake --build build-cuda -j
ctest --test-dir build-cuda --output-on-failure
```

Verbatim from `docs/cuda_rtx5090_optimization.md:76-83`. Omit the architecture override for the portable project default; the `120-real;120-virtual` narrowing is an audit artifact, explicitly *not* the project-wide default (`docs/cuda_rtx5090_optimization.md:59-61`). In Docker, CUDA requires swapping the builder stage's base image for a CUDA 12.8+ devel image and passing `MAGIC_GEO_ENABLE_CUDA=ON` (`Dockerfile:24-31`, `docs/docker_deployment.md:99-110`).

## OpenMP detection

`find_package(OpenMP)` at `CMakeLists.txt:80` is **not** `REQUIRED`. When `OpenMP_CXX_FOUND` (`CMakeLists.txt:188-191`):

- `magic_geo_native` links `OpenMP::OpenMP_CXX` (PRIVATE).
- `MAGIC_GEO_HAS_OPENMP=1` is defined on the target.

The same `if(OpenMP_CXX_FOUND)` guard repeats for four of the five test targets that link the shared library: `magic_geo_oceanic_age_depth_integration_test` (`:279-284`), `magic_geo_crust_reservoir_integration_test` (`:412-417`), `magic_geo_sediment_partition_test` (`:439-444`), and `magic_geo_native_api_test` (`:465-467`). `magic_geo_c_api_v1_client_test` links `magic_geo_native` without an OpenMP guard (`:518-521`); it exercises the frozen v1 C layout and needs no OpenMP symbols of its own.

Runtime consequences:

- `backend_info()` reports `openmp_enabled` from `MAGIC_GEO_HAS_OPENMP` and `openmp_max_threads` from `omp_get_max_threads()` under `_OPENMP` (`opencl_compute.cpp:2037-2046`).
- On Linux the built library gains a dynamic dependency on `libgomp.so.1` (with GCC); this is why the Docker runtime stage installs `libgomp1` (`Dockerfile:40-43`).
- Thread policy is generation-scoped: `ScopedThreadConfiguration` (`cpp/src/engine/internal.hpp:81-87`, `cpp/src/engine/core.cpp:213-225`) restores the calling thread's prior ICV on every exit, and `compute.threads = 0` leaves host policy untouched (`cpp/src/engine/README.md:356-357`).

Missing OpenMP is not an error. The library builds and runs; parallel loops fall back to serial execution.

## OpenCL is a runtime dependency only

Nothing about OpenCL is checked at configure time. `cpp/src/opencl_compute.cpp` is always in the source list (`CMakeLists.txt:128`), and the only link-time concession is `${CMAKE_DL_LIBS}` (`CMakeLists.txt:193`). The loader is opened dynamically:

- `dlopen("libOpenCL.so.1", RTLD_NOW | RTLD_LOCAL)`, then `dlopen("libOpenCL.so", …)` as a fallback (`opencl_compute.cpp:161-165`). Failure sets the telemetry error `"OpenCL loader library was not found"` (`:166-169`).
- Outside `__linux__`, both `load()` and `load_symbol()` return the error `"OpenCL dynamic loading is only implemented on Linux"` (`opencl_compute.cpp:151-156`, `:171-174`). On macOS and Windows the OpenCL backend is consequently unavailable regardless of installed drivers.
- Each required entry point is resolved individually; a missing symbol yields `OpenCL loader is missing required symbol <name>` (`:146-149`).

## Wheels, sdists and the ABI symbol check

`setup.py` exists solely to make the packaging honest about the bundled binary.

| Rule | Implementation | Effect |
| --- | --- | --- |
| The wheel is never `py3-none-any` | `NativeDistribution.has_ext_modules() -> True` (`setup.py:29-33`), installed as `distclass` (`setup.py:88`) | Setuptools stops treating the distribution as pure Python. |
| The wheel root is not pure | `PlatformWheel.finalize_options` sets `self.root_is_pure = False` (`setup.py:39-41`) | Forces a platform-specific wheel layout. |
| The tag is Python-ABI-independent but OS/arch-specific | `PlatformWheel.get_tag()` returns `("py3", "none", platform)` (`setup.py:43-45`) | Correct for a `ctypes` core: it does not link `libpython`, so no CPython ABI tag is warranted; but the ELF/DLL/dylib is host-specific, so the platform slot is kept. |
| A wheel cannot be built without the staged library | `PlatformWheel.run()` checks `src/magic_geo/<host name>` with `Path.is_file()` and raises `RuntimeError("cannot build a wheel without <path>; build the native Release target with CMake first")` (`setup.py:47-54`) | Turns "forgot to build the core" into a build-time failure instead of a runtime ImportError for the end user. |
| The staged library must actually export the current ABI | `PlatformWheel.run()` `ctypes.CDLL`s the resolved path and `getattr`s seven symbols; `OSError`/`AttributeError` becomes `RuntimeError("the staged native core is incompatible with this build host or package: …")` (`setup.py:55-71`) | Catches a stale or mismatched `.so` before it ships. |
| Sdists never contain a host binary | `SourceDistribution.make_release_tree()` unlinks all three names from `<base>/src/magic_geo/` with `missing_ok=True` (`setup.py:77-84`); `MANIFEST.in:11` additionally `global-exclude *.dll *.dylib *.so` | An sdist ships rebuildable CMake/C++ sources; build the extracted tree with CMake before requesting its wheel (`README.md:42-44`). |
| The wheel carries only the host's library name | `exclude_package_data={"magic_geo": [name for name in _NATIVE_NAMES if name != _native_name()]}` (`setup.py:90-92`) | `pyproject.toml:36-45` lists all three names as package data; this prunes the two that do not apply. |

The seven symbols checked (`setup.py:57-65`) are exactly the seven that `native._load_library()` resolves at runtime (`src/magic_geo/native.py:132-144`):

| Symbol | Role |
| --- | --- |
| `magic_geo_backend_info_json` | Backend/capability telemetry |
| `magic_geo_generate_json_v3` | Full world, JSON |
| `magic_geo_generate_geo_json_v3` | Geo-only world, JSON |
| `magic_geo_generate_msgpack_v3` | Full world, MessagePack |
| `magic_geo_generate_geo_msgpack_v3` | Geo-only world, MessagePack |
| `magic_geo_free_string` | Frees a JSON return |
| `magic_geo_free_buffer` | Frees a MessagePack return |

Python only ever calls the **v3** entry points; the v1/v2 C symbols remain exported for external C callers but are never used by this package. A missing symbol at runtime produces `RuntimeError("native library does not expose the current V3 JSON and MessagePack ABI; rebuild magic_geo_native from the current source tree")` (`native.py:140-144`).

### Why a local linux tag is not a manylinux claim

`README.md:38-46` is explicit and should be carried forward unchanged in spirit: a locally produced Linux tag such as `linux_x86_64` **is not a manylinux portability claim**. Its glibc, libstdc++ and `libgomp` requirements follow the build host and toolchain. Concretely, a Linux build of this library links `libgomp.so.1`, `libstdc++.so.6`, `libm.so.6`, `libgcc_s.so.1` and `libc.so.6`; any of those can be too new for a target host. Producing a genuinely portable wheel would require a manylinux-compatible toolchain and an auditwheel-style repair step — neither is implemented in this repository, so no manylinux tag is produced or claimed anywhere in the tree.

### Building a wheel

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF
cmake --build build --config Release
python -m pip wheel --no-deps --wheel-dir dist .
```

This is the Docker builder-stage sequence (`Dockerfile:27-35`), where the comment notes that the `setup.py` ABI-symbol check is the build-time gate, "so a broken native build fails here, not at runtime".

### What lands in an sdist

`MANIFEST.in` controls the source archive:

| Directive | Value |
| --- | --- |
| `include` | `CMakeLists.txt`, `README.md`, `pyproject.toml`, `setup.py` (`MANIFEST.in:1-4`) |
| `recursive-include` | `cpp` (`*.cpp *.cu *.hpp *.md`), `configs` (`*.json *.yaml`), `docs` (`*.md`), `scripts` (`*.mjs *.py`), `src/magic_geo` (`*.css *.html *.js *.py *.yaml`), `tests` (`*.py`) (`MANIFEST.in:5-10`) |
| `global-exclude` | `*.dll *.dylib *.so`, `*.py[cod]`, `__pycache__` (`MANIFEST.in:11-13`) |
| `prune` | `build`, `cmake-build-debug`, `runs` (`MANIFEST.in:14-16`) |

## Platform notes and library naming

| Platform | Built filename | Where CMake stages it | Python lookup | Packaging |
| --- | --- | --- | --- | --- |
| Linux | `libmagic_geo_native.so` | `LIBRARY_OUTPUT_DIRECTORY` → `src/magic_geo/` | `native.py:37` (fallback branch) | `pyproject.toml:38`; wheel keeps it, sdist strips it |
| macOS | `libmagic_geo_native.dylib` | `LIBRARY_OUTPUT_DIRECTORY`; Release pinned to `src/magic_geo/` so multi-config Xcode does not append a config directory (`CMakeLists.txt:165-172`) | `native.py:35-36` (`sys.platform == "darwin"`) | `pyproject.toml:40` |
| Windows | `magic_geo_native.dll` | `RUNTIME_OUTPUT_DIRECTORY`; Release pinned to `src/magic_geo/` (`CMakeLists.txt:170-171`). The import `.lib` follows CMake's default archive directory for Release. | `native.py:33-34` (`sys.platform == "win32"`) | `pyproject.toml:39` |

Additional platform facts:

- **No cross-platform name fallback.** `_native_library_names()` returns a single-element tuple per platform (`native.py:30-37`), so a `.so` sitting in the package directory on Windows is never picked up.
- **OpenCL is Linux-only** in this implementation (`opencl_compute.cpp:151-156`, `:171-174`).
- **`setup.py` mirrors the same mapping** in `_native_name()` (`setup.py:19-26`) and enumerates all three in `_NATIVE_NAMES` (`setup.py:12-16`).
- **The `debug_ui` assets ship as package data** alongside the library: `debug_ui/*.html`, `debug_ui/*.css`, `debug_ui/*.js`, `debug_ui/vendor/*.js` (`pyproject.toml:41-44`).

## Build troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `RuntimeError: native library was not found. Build it with: cmake -S . -B build && cmake --build build` (traceback, exit 1) | No host-native library in the installed `magic_geo` package directory (`native.py:124-127`). | Run the CMake build; confirm `src/magic_geo/libmagic_geo_native.so` (or `.dll`/`.dylib`) exists. |
| `RuntimeError: MAGIC_GEO_NATIVE_LIBRARY does not name a file: <path>` | The env override points at a missing or non-file path (`native.py:113-118`). | Correct or `unset MAGIC_GEO_NATIVE_LIBRARY`. The override wins over the packaged library and is resolved with `expanduser().resolve()`. |
| `RuntimeError: native library does not expose the current V3 JSON and MessagePack ABI; rebuild magic_geo_native from the current source tree` | A stale library missing one of the seven v3/free symbols (`native.py:140-144`). | Rebuild from the current tree; delete the stale artifact first if `MAGIC_GEO_NATIVE_LIBRARY` might be resolving elsewhere. |
| `RuntimeError: native library returned unsupported world schema_version <n>; expected <m>; rebuild magic_geo_native from the current source tree` | The Python schema gate rejected the payload version (`native.py:234-241`). | The C++ and Python halves are out of sync; rebuild the native core. |
| `RuntimeError: native library returned retired fields in a schema-2 world: …` | The library still emits fields retired from the current schema (`native.py:242-247`). | Same fix: rebuild the native core. |
| `RuntimeError: cannot build a wheel without <path>; build the native Release target with CMake first` | `pip wheel` / `python -m build` ran before the CMake build (`setup.py:51-54`). | Build the Release target, then re-run the wheel build. |
| `RuntimeError: the staged native core is incompatible with this build host or package: <path>: <exc>` | `ctypes.CDLL` failed to load the staged library, or one of the seven symbols was absent (`setup.py:67-71`). | Inspect the nested exception. Typical causes: a Debug artifact staged by hand, a wrong-architecture binary, or a missing `libgomp`/`libstdc++`. |
| CMake WARNING `magic-geo CUDA backend disabled: CUDA <ver> cannot compile sm_120; CUDA 12.8+ is required` | An NVIDIA compiler older than 12.8 (`CMakeLists.txt:53-57`). | Install CUDA 12.8+ and point `-DCMAKE_CUDA_COMPILER=` at its `nvcc`, or set `-DMAGIC_GEO_ENABLE_CUDA=OFF` to silence the warning and build the stub deliberately. |
| CMake WARNING `magic-geo CUDA backend disabled: CUDA runtime development files were not found; building runtime stub` | `nvcc` present but `find_package(CUDAToolkit 12.8 QUIET)` failed (`CMakeLists.txt:47-52`). | Install the toolkit development files and/or pass `-DCUDAToolkit_ROOT=`. |
| CMake WARNING `magic-geo CUDA backend disabled: compiler '<id>' is not supported` | A non-NVIDIA CUDA compiler was detected (`CMakeLists.txt:58-62`). | Set `-DCMAKE_CUDA_COMPILER=` to NVIDIA `nvcc` 12.8+ or disable CUDA. |
| CUDA compile errors mentioning `rsqrt` during compiler identification | glibc 2.43's C23 declarations colliding with CUDA device declarations, on a build where the `CMAKE_CUDA_FLAGS_INIT` mitigation did not apply. | The mitigation is already in `CMakeLists.txt:22-30` and must be visible *before* any target exists; make sure it is not being overridden by a cached `CMAKE_CUDA_FLAGS`. Delete the build directory and reconfigure from scratch. |
| Python still loads an old library after a rebuild | You built `Debug`, `RelWithDebInfo` or `MinSizeRel`, which are redirected to `${CMAKE_CURRENT_BINARY_DIR}/native/<Config>/` and never touch the package directory (`CMakeLists.txt:173-185`). | Build `Release`, or set `MAGIC_GEO_NATIVE_LIBRARY` to the isolated path. |
| On Windows/macOS the artifact lands in `src/magic_geo/Release/` | You overrode `MAGIC_GEO_LIBRARY_OUTPUT_DIRECTORY`, which disables the explicit per-config pinning at `CMakeLists.txt:158-172`. | Drop the override, or add your own `*_OUTPUT_DIRECTORY_RELEASE` pins. |
| `Serving requires the optional debug dependencies: pip install 'magic-geo[debug]'` (exit 2) | `uvicorn` or `magic_geo.debug_server` failed to import (`cli/commands/serve.py:76-82`). | `pip install -e '.[debug]'`. |
| `Debug export requires the optional debug dependencies` (exit 2) | `pyarrow` missing (`cli/commands/export.py:181-185`). | `pip install -e '.[debug]'`. |
| `Rerun export requires the rerun-sdk package: pip install rerun-sdk` (exit 2) | `rerun` missing; it is intentionally not in any extra (`cli/commands/export.py:217-221`). | `pip install rerun-sdk`. |
| Workbench/server tests silently skip | `SkipTest` raised at module import when the `debug` extra is absent (`tests/test_debug_server.py:27-28`, `tests/test_debug_export.py:42-43`); `tests/test_debug_rerun.py:24-25` for `rerun-sdk`. | Install the extra if you need that coverage; otherwise the skip is expected. |
| `backend` reports `cuda_capability_status: not_compiled` on a machine with a GPU | The library was built with the stub — the CUDA ladder did not reach step 5 at configure time. | Re-run `cmake -S . -B build` and read the STATUS/WARNING line; the ladder table above names the exact failure. |
| `opencl_capability_status: probe_failed` or `opencl_loader_found: false` | No `libOpenCL.so.1`/`libOpenCL.so` on the loader path, or you are not on Linux (`opencl_compute.cpp:151-175`). | Install a vendor ICD. On macOS/Windows the OpenCL path is unimplemented. |
| `ImportError` for `magic_geo` after `pip install -e .` | src-layout means the package is under `src/`; a bare `python` in the repo root will not find it without the install. | Re-run the editable install in the active interpreter, or set `PYTHONPATH=src` as the audit scripts do (`docs/cuda_rtx5090_optimization.md:227`). |
| Docker image somehow contains a host binary | `.dockerignore:20-22` excludes all three staged names; verify it was not edited. | Restore the exclusions; rebuild. The image must build the native core itself. |

## Limitations and unresolved claims

- **`-ffp-contract=off` is not a bit-reproducibility guarantee.** The in-source comment (`CMakeLists.txt:134-136`) states that it prevents FMA from introducing *avoidable* backend drift, and that cross-compiler/GPU parity is validated with numeric tolerances and physical invariants, **not byte hashes**. Do not read the flag as a claim of byte-identical output across compilers or hardware.
- **Accelerator parity is explicitly false.** `backend_info()` hardcodes `crust_overlap_accelerator_geometry_parity_demonstrated`, `..._coverage_membership_parity_demonstrated`, `..._categorical_parity_demonstrated`, `..._complete_parity_demonstrated` and `crust_overlap_accelerator_state_authoritative` to `false` (`opencl_compute.cpp:2145-2174`). `crust_transport_execution_backend` is always `"cpu"` (`:2067-2072`). Geometry, coverage, membership classes, categories and production state remain CPU-authoritative (`README.md:313-315`).
- **`backend_scope` is a scope limitation, not marketing.** The literal value `accelerated_native_kernels_not_end_to_end_pipeline` (`opencl_compute.cpp:2061-2066`) means acceleration covers specific kernels — plate assignment and fixed-order scalar/fused boundary smoothing (`README.md:306-307`) — not the pipeline.
- **The continuous shadow is discarded, not used.** `crust_overlap_continuous_shadow_only = true`, `..._authoritative = false`, `..._result_used_for_state = false` (`opencl_compute.cpp:2127-2144`). `README.md:314-315` records that "This host has no device-run evidence for the shadow."
- **The CUDA `auto` thresholds are host-specific numbers, not calibrated physics.** `CUDA_SM_120_AUTO_MIN_CELL_COUNT = 8192` and `CUDA_UNCALIBRATED_AUTO_MIN_CELL_COUNT = 32768` (`opencl_compute.cpp:99-101`) come from a single-GPU audit whose own document warns that all figures "should be rerun before changing a threshold, treating them as a release budget, or extrapolating them to another GPU, driver, toolkit, power state, mesh family, output mode, or workload" (`docs/cuda_rtx5090_optimization.md:216-221`). On a stub build the reported `cuda_auto_min_cell_count` is merely the struct default (`opencl_compute.cpp:2735`), not a measurement.
- **The reported 178-key `backend` payload is one observation, not an invariant.** The `opencl_device_*`/`opencl_platform_*` block is emitted only when a selected or qualifying device record exists (`opencl_compute.cpp:2619-2628`), so the key count varies by host.
- **No manylinux claim exists anywhere.** See [Why a local linux tag is not a manylinux claim](#why-a-local-linux-tag-is-not-a-manylinux-claim). There is no auditwheel step, no manylinux container definition, and no policy tag in the tree.
- **No minimum compiler version is pinned.** `CMAKE_CXX_STANDARD 20` is the only stated requirement (`CMakeLists.txt:76-78`); a concrete GCC/Clang/MSVC floor is not verified in source.
- **Build-order coupling is documented, not enforced for editable installs.** The ABI symbol gate is registered only on `bdist_wheel` (`setup.py:89`). An editable install with no staged library succeeds and fails later at first native call — which is precisely the order `README.md:22-26` prescribes, but it means `pip install -e .` returning success is not evidence that the native core works. Run `magic-geo backend`.
- **`install(TARGETS ...)` and the staging directory are different mechanisms.** `cmake --install` writes to `<prefix>/magic_geo` (`CMakeLists.txt:217-221`); the editable workflow relies on `MAGIC_GEO_LIBRARY_OUTPUT_DIRECTORY` instead. Nothing in the tree reconciles the two, and the Python loader only knows about the package directory and the env override.

## See also

- [Project Overview](./01-overview.md)
- [Quickstart](./03-quickstart.md)
- [Architecture](./04-architecture.md)
- [Configuration Reference](./05-configuration-reference.md)
- [CLI Reference](./06-cli-reference.md)
- [Python API](./07-python-api.md)
- [Native Engine (C++ Core)](./08-native-engine.md)
- [Compute Backends (CPU, OpenCL, CUDA)](./09-compute-backends.md)
- [Testing and Quality Gates](./18-testing.md)
- [Docker Deployment](./19-docker-deployment.md)
- [Troubleshooting and FAQ](./22-troubleshooting.md)
