> **Historical / superseded backend status**
>
> This document preserves the original CPU/OpenCL pipeline audit and
> determinism analysis. Its backend inventory, automatic-selection policy,
> thresholds, and latest benchmark results are superseded by the
> [RTX 5090 CUDA optimization audit](cuda_rtx5090_optimization.md).

# GPU simulation audit and architecture guide

This document records the repository-specific performance audit, the current
CPU/OpenCL split, and the constraints that future acceleration work must
preserve. It describes the working tree as of 2026-07-10. Measurements are
diagnostic observations from one host, not release budgets or cross-machine
benchmarks.

## Executive summary

The engine is not an end-to-end GPU workload. It is a C++ simulation that emits
a large JSON document, followed by a long Python enrichment pipeline that
materializes and mutates dictionaries. On the canonical 4,096-cell, six-erosion
workload, the pre-optimization native-plus-JSON boundary was about 1.70 s of a
4.21 s full API call. That is roughly a 40% native fraction and an Amdahl limit
of about 1.67x even if all native work became free:

```text
native fraction = 1.70 / 4.21 ~= 0.40
ideal native-only speedup = 4.21 / (4.21 - 1.70) ~= 1.68
```

The first safe acceleration tranche therefore focuses on deterministic,
dense native loops rather than claiming that GPU execution will solve the full
pipeline. The current implementation has:

- a deterministic KD tree for Fibonacci nearest-neighbor construction;
- fixed-size inline arrays for the four 12-month cell fields;
- a versioned CPU/auto/OpenCL backend contract and truthful telemetry;
- FP64 OpenCL kernels for plate assignment, scalar and fused three-field
  fixed-order CSR smoothing, and segmented same-plate crust-source remapping;
- planet-radius propagation through remaining route/logistics/campaign paths;
- fail-closed finite/range validation at both Python and native boundaries.

The next large wins are structural: remove the JSON/dictionary boundary from
the middle of generation, reduce full per-stage provenance duplication, use
SoA/columnar state, persist device/program/mesh caches across worlds, extend
field/world batching, and optimize the irregular graph stages on CPU.

## Audit host and interpretation of measurements

The audit host reports:

- Intel Core i5-14400F, 10 cores / 16 logical CPUs;
- approximately 123 GiB host RAM;
- NVIDIA GeForce RTX 5090, 32,607 MiB reported device memory;
- NVIDIA driver 595.71.05;
- CMake Release native build with OpenMP and `-ffp-contract=off`.

The normal sandboxed workspace can load the OpenCL loader but reports no
platform. GPU parity and timing evidence was collected in a device-enabled run
on the RTX 5090 with GCC 15.2. Thermal state and power limits were not captured,
and the final table uses only two runs per case, so the figures are directional
rather than statistically stable release budgets. Re-benchmark before changing
thresholds or assuming that the RTX threshold transfers to another GPU.

## Actual generation and data flow

There are two important pipelines, separated by JSON:

```text
WorldConfig (Pydantic)
  -> config_to_native: nested Python mappings
  -> ctypes CConfigV2
  -> magic_geo_generate_json_v2
     -> validate ComputeOptions and Params
     -> scoped OpenMP thread policy / ComputeSession
     -> simulate_world
        -> mesh
        -> plates, boundaries, crust, topography
        -> initial sea-level/climate/hydrology stabilization
        -> erosion loop
           -> plate motion and crust remap
           -> tectonic + hillslope + fluvial work
           -> sea-level/climate/water-budget/hydrology stabilization
        -> cryosphere coupling
        -> soils, biomes, resources, water features
        -> settlements, civilization, history
     -> serialize_world: one compact C++ JSON string
  -> C pointer copy and json.loads
  -> one large Python dict/list object graph
  -> ~60 ordered enrich_world_* passes in api.py
  -> optional pretty, sorted json.dumps in io.py
```

The native ordering is centralized in `cpp/src/engine/pipeline.cpp`; the full
Python enrichment ordering is centralized in `src/magic_geo/api.py`. Both are
semantic orderings, not merely scheduling choices. Later stages consume fields
written by earlier stages.

`generate_geo_world` is not yet a native physical-only simulation. It invokes
the same full native world generation, parses the same JSON, removes native
civilization fields, and then runs a shorter physical enrichment sequence.
That explains why the measured geo API time (about 4.00 s) is close to the full
API time (about 4.21 s).

### Memory path

The native engine simultaneously owns a large `GeneratedWorld`, per-cell
`Cell` objects, graph vectors, and stage/provenance histories while constructing
the compact JSON string. Python then copies the returned bytes and expands them
through `json.loads` into dictionaries, strings, integers, floats, and lists.
Subsequent enrichers add more objects, and final pretty JSON creates another
large string.

Consequently, `output.include_cells=false` is not a simulation-memory switch.
It changes the serialized cell list but does not avoid building the native cell
state and process histories. The measured peak still remained about 338 MB.

## Measured baseline and profile evidence

| Workload / measurement | Observation | Interpretation |
| --- | ---: | --- |
| Pre-optimization canonical native + compact JSON, 4,096 cells / erosion 6 | ~1.70 s | C++ simulation, C++ serialization, C boundary copy, and parse dominate only part of the full call. |
| Pre-optimization canonical full API | ~4.21 s | Native boundary plus all Python enrichers. |
| Pre-optimization canonical geo API | ~4.00 s | Native civilization is still generated and then stripped. |
| Direct canonical full API audit run | 3.946 s internal; 4.22 s process | Same scale; process startup and teardown explain the outer difference. |
| Direct canonical peak RSS | 450,108 KiB, about 440 MiB | Dominated by duplicated native/JSON/Python representations and provenance. |
| Compact native JSON | 66.3 MiB | Before Python pretty-printing and object expansion. |
| Native run with `include_cells=false` | ~338 MB peak RSS | Confirms internal state/history, not only exported cells, drives memory. |
| 1,024 cells / erosion 1 cProfile | 2.525 s, ~7.5 million calls | A smaller, Python-heavy workload; do not combine its percentages with the canonical Amdahl calculation. |
| cProfile: native boundary | 0.211 s | About 8.4% of this smaller workload. |
| cProfile: cell geometry | 0.468 s | Largest named Python hotspot. |
| cProfile: seasonal climate | 0.208 s | Per-cell/list/dict processing remains material. |
| cProfile: route corridors | 0.151 s | Repeated graph/path work. |
| cProfile: species ranges | 0.112 s | Another Python object-heavy pass. |

### KD-tree mesh microbenchmark

The Fibonacci mesh formerly tested every cell against every other cell. The
current KD tree changed the observed mesh-build times as follows:

| Cells | Legacy all-pairs | Deterministic KD tree | Directional speedup |
| ---: | ---: | ---: | ---: |
| 16,384 | 0.791 s | 0.663 s | 1.19x |
| 65,536 | 4.697 s | 2.845 s | 1.65x |

This is a mesh microbenchmark, not a full API result. The benefit grows with
cell count, but reciprocal-neighbor repair and downstream work remain.

### Current OpenCL tranche timing

These direct native two-run medians use 16 host threads and
`include_cells=false`. They include plate assignment, scalar smoothing, fused
convergence/divergence/transform smoothing, and the segmented crust-remap
kernel. Every erosion-6 OpenCL run made 53 kernel dispatches: seven plate
assignments, six crust remaps, five scalar smoothing steps, and 35 fused
boundary-smoothing steps. That is down from 123 dispatches before fusion. The
physical payload was exactly equal to CPU after only backend telemetry was
removed.

| Cells / erosion | CPU | Explicit OpenCL | H2D / D2H | Result |
| --- | ---: | ---: | ---: | --- |
| 4,096 / 6 | 1.137 s | 1.272 s | 2.015 / 0.967 MB | OpenCL is about 12% slower; setup, scans, and transfers dominate. |
| 16,384 / 6 | 4.418 s | 4.471 s | 8.056 / 3.867 MB | Effectively even, with OpenCL about 1% slower. |
| 32,768 / 6 | 10.171 s | 9.077 s | 16.116 / 7.733 MB | OpenCL is about 10.8% faster, a 1.12x speedup. |

This evidence supports the current `auto` threshold of 32,768 cells and also
shows that kernel offload alone is not a compelling end-to-end optimization.
The remap kernel preserves the same scan complexity and adds per-iteration
transfers; it improves throughput only after the workload is large enough.

A final 80-generation explicit-OpenCL repeat used 128 cells, two erosion steps,
the remap kernel, and fused smoothing. RSS samples in KiB, before generation and
then every ten worlds, were:

```text
[27576, 98848, 101252, 101252, 101252, 101252, 101252, 101252, 101252]
```

That is useful leak evidence for the tested success path, not a substitute for
fault-injected release-path testing.

## Implemented performance and correctness work

### Deterministic Fibonacci KD tree

`cpp/src/engine/mesh.cpp` now builds a three-axis KD tree with subtree AABBs.
Queries retain a conservative candidate superset, sort retained IDs, and replay
the legacy ascending-ID candidate evaluation. This deliberately preserves:

- strict `score > best_score` tie behavior;
- score-ascending final neighbor storage;
- deterministic reciprocal-neighbor repair;
- the downstream graph and serialized payload.

The AABB bound is evaluated in `long double` and inflated before pruning so a
few ulps in an optimized dot product cannot incorrectly remove a candidate.
`MAGIC_GEO_VALIDATE_FIBONACCI_KNN=1` recomputes the brute-force reference and
requires exact neighbor-vector equality. CTest runs the native API binary both
normally and with this validation enabled.

The geodesic backend is unchanged. Code that depends on mesh scale now uses the
actual generated `cells.size()` where geodesic frequency rounding can make the
real mesh size differ from the requested `cell_count`.

### Inline monthly climate arrays

The four per-cell monthly fields are now `std::array<double, 12>`:

- temperature;
- precipitation;
- east wind;
- north wind.

The configuration already requires exactly 12 months, so heap-allocated vectors
were unnecessary. Inline arrays remove four allocations per cell and make the
field shape explicit without changing serialized arrays or month order.

### Backend and ABI contract

Public C++ `ComputeOptions` and Python expose `compute.backend =
auto|cpu|opencl` plus `opencl_prefer_gpu`; the original `Params` layout no
longer carries compute policy. The legacy one-argument C++ overload, original
304-byte `CConfig`, and v1 C entry point preserve historical CPU execution.
`CConfigV2` nests `CConfig` and adds the two compute controls; Python uses the
v2 entry point and its dedicated conversion helper.

Compile-time checks freeze the type and 64-bit offset of every v1 field. A
separate legacy-client test does not include the current public header: it
declares the old 304-byte layout and C symbols, links to the new library, and
verifies CPU-only generation. This catches same-size field reordering as well
as total-size changes.

`ComputeSession` is generation-scoped and thread-local so existing simulation
function signatures remain stable. It dynamically loads OpenCL, selects a
device, owns the context/queue/program/kernels/buffers, caches mesh positions
and CSR adjacency within that generation, and releases resources on success,
initialization failure, runtime fallback, and destruction.

Backend semantics are:

- `cpu`: do not probe or initialize OpenCL;
- `auto` below 32,768 requested cells: select CPU without probing and without
  reporting a fallback;
- eligible `auto`: never select a CPU OpenCL device; with
  `opencl_prefer_gpu=true`, require a qualifying GPU, otherwise allow any
  qualifying non-CPU device; if none exists, select CPU and record the
  device-selection fallback;
- explicit `opencl`: ignore the automatic size threshold and fail rather than
  silently switching to CPU;
- an `auto` runtime error releases OpenCL, records the failed stage/reason, and
  reruns the incomplete operation on CPU; if earlier GPU dispatches succeeded,
  telemetry reports the final active backend as `hybrid`.

A qualifying device must be available and compiler-capable, expose usable FP64
with denorm, INF/NAN, and round-to-nearest behavior, match host endianness,
support OpenCL C 1.2, use at least 64-bit addresses, and expose nonzero
work-group, work-item, and allocation limits. Local sizes are capped by device,
per-dimension, and kernel limits. Telemetry separates raw FP64 devices from
fully qualifying devices and reports selection, fallback, program state,
dispatch counts, work sizes, device capabilities, and transfer bytes.

### Current GPU kernels

All kernels use OpenCL C 1.2 FP64 and disable contraction.

1. `assign_plates`: one work item per cell, iterating plate centers in ascending
   order and using strict improvement, matching the CPU tie rule.
2. `smooth_neighbor_field`: one work item per cell over immutable CSR adjacency;
   neighbors are accumulated in stored order, and ping-pong buffers preserve
   the CPU step boundary.
3. `smooth_three_neighbor_fields`: one work item traverses CSR once while
   independently updating convergence, divergence, and transform fields with
   weights 0.58, 0.58, and 0.62. Field-major ping-pong buffers preserve the
   scalar kernel's arithmetic order for each field.
4. `remap_crust_sources`: one work item per current cell over the ascending
   candidate segment for its plate. The CPU computes deterministic backtraced
   queries; the GPU returns source IDs; the CPU validates every ID and then
   computes all provenance deltas.

Positions and adjacency are uploaded once per generation. The three boundary
fields now share one packed upload/read pair and one traversal per smoothing
step; the independent continental-coherence and relief fields still use scalar
transfers. Crust remap uploads queries, plate IDs, offsets, and candidate IDs
every erosion iteration. Context creation and source compilation also occur
once per world, not once per process. These costs explain the limited gain.

### Radius propagation and finite validation

Remaining Earth-radius literals in route-corridor, logistics/campaign generation,
and campaign replay were replaced with `planet_parameters.radius_km`. Legacy
artifacts without `planet_parameters` intentionally fall back to 6,371 km so
old payload replay remains stable. Native settlement/sacred-site scale and
climate traversal use actual generated mesh size, and native distances/areas
continue to use configured radius.

All Pydantic configuration models now reject NaN and infinity and enforce
explicit practical ranges. Native `validate_params` independently checks every
floating input for finiteness and enforces matching limits before allocation or
OpenCL initialization. Native serialization now throws on a non-finite value
instead of silently converting it to zero. This is both a correctness rule and
a GPU safety boundary: invalid numeric state cannot be hidden in JSON or sent
to device kernels.

The supported upper bounds also prevent finite-but-overflowing input, such as a
radius whose square is not representable. Tests generate a world at the
supported numeric extrema, reject every value immediately above those bounds,
and ensure Python seeds cannot wrap the unsigned 64-bit ABI field.

An explicit thread count is applied only for one generation and restores the
calling thread's prior OpenMP ICV on normal or exceptional exit. `threads=0`
does not call `omp_set_num_threads` and therefore leaves host policy untouched.

## Determinism contract

The CPU implementation is the reference semantics. Optimizations must preserve:

- RNG construction and consumption order;
- cell, plate, neighbor, candidate, graph-edge, and serializer order;
- strict-improvement tie breaking and stable identifiers;
- OpenMP static schedules where output can depend on iteration ownership;
- floating expression and accumulation order;
- complete provenance and replay relationships.

The Release build disables FP contraction on the CPU, and the OpenCL source
does the same. GPU kernels use double precision, ascending candidates, stored
CSR neighbor order, and separate input/output buffers. On the RTX 5090, CPU and
OpenCL physical payloads were exactly equal after removing the intentionally
different `backend` object for 128/erosion-0, 512/erosion-2, 4,096/erosion-6,
16,384/erosion-6, and 32,768/erosion-6 cases. The larger cases include the
segmented remap kernel; the device-enabled CTests also passed.

GCC 15.2 formerly produced three one-ulp differences between optimized and
unoptimized climate output because it rewrote one `pow(delta, 2.0)` only at
optimization levels above zero. Expressing that mathematical square directly
preserves the optimized code and makes Release, Debug, and unoptimized canonical
CPU JSON byte-identical on the audit host: 77,823,497 bytes with SHA-256
`ea081457727952240c3afc8cf66700f302732e3f2edffc861fc21b2adf107be7`.
This is scoped evidence, not a cross-compiler identity promise.

Exact cross-backend equality on one NVIDIA device is evidence, not a portable
bitwise promise across all OpenCL vendors and compilers. The supported contract
should be:

- same CPU build/platform/configuration: byte-stable output remains expected;
- CPU versus GPU: identical discrete topology/IDs/order and numerically equal
  physical fields under explicit tolerances and invariant/replay validation;
- full JSON across hosts: backend telemetry is expected to differ;
- `auto`: hardware-dependent selection is allowed, but selection and fallback
  must be truthfully serialized.

Do not move an ordered reduction, RNG-consuming loop, priority queue, union-find
tie, or graph traversal to an unordered atomic implementation and call it
equivalent. A backend change must carry a parity test for the exact tie and
ordering rules it replaces.

## Safe CPU/GPU stage partition

| Stage shape | Placement | Reason / requirement |
| --- | --- | --- |
| Plate-center argmax | GPU now | Dense cell-by-plate loop; fixed ascending plate order. |
| Fixed-step scalar or fused three-field neighbor smoothing | GPU now | Independent destination cells over immutable ordered CSR; field arithmetic remains ordered. |
| Same-plate crust-source scan | GPU now, still a bottleneck | Dense segmented scan with deterministic candidate order; CPU retains rotations, validation, and provenance. |
| Independent per-cell algebra with immutable inputs | GPU candidate | Safe only if field order, clamping, and FP policy match and several fields are batched to amortize transfers. |
| Monthly climate fields | GPU candidate after SoA | Twelve fixed lanes are suitable, but atmospheric/moisture dependencies and downstream parity require a whole-stage design, not isolated expressions. |
| Sea-level connectivity sweep / union-find | CPU | Ordered connectivity changes and deterministic component choice. |
| Priority-Flood, depression correction, and routing | CPU | Priority queues, graph mutation, event selection, and provenance are irregular and order-sensitive. |
| Flow accumulation and sediment routing | CPU initially | Topological order and conservation ledgers matter more than raw arithmetic throughput. Parallelize independent components only after replay tests. |
| Dijkstra routes, campaigns, and graph diagnostics | CPU | Small-to-medium irregular searches; reuse CSR/scratch and batch independent queries before considering GPU graph algorithms. |
| Civilization/history/provenance assembly | CPU | Branch-heavy records and stable ordering, not dense numeric kernels. |
| JSON serialization / Python enrichment | Neither GPU nor kernel work | Remove or redesign the boundary; GPU offload cannot accelerate dictionary creation and string formatting. |

## Remaining bottlenecks and recommended order

### 1. Eliminate the intermediate JSON/dictionary boundary

This is the largest architectural constraint. The C++ engine serializes tens of
MiB, the C ABI copies it, Python parses it, dozens of enrichers repeatedly walk
dicts, and output is serialized again. Prefer a versioned columnar/native result
API with explicit lifetime management. JSON should be a terminal exporter, not
the internal interchange format.

An incremental route is to expose immutable typed cell columns plus top-level
records to Python, then migrate enrichers in dependency order. Arrow is useful
for debug/export interoperability, but the hot in-process ABI can remain a
small C view over contiguous arrays.

Also add a physical-only native mode so `generate_geo_world` never computes or
serializes civilization state that it immediately deletes.

### 2. Make provenance selectable and columnar

The 66.3 MiB compact JSON and roughly 450 MB peak show that full per-cell,
per-stage provenance is expensive. `include_cells=false` does not solve it.
Introduce an explicit provenance policy such as `full`, `summary`, and `none`,
while keeping `full` as the validation/reference mode. Internally store repeated
stage fields as typed columns, delta/unchanged masks, or streamed records rather
than nested objects and copied full-length arrays.

Performance modes must never silently weaken evidence. The selected provenance
level belongs in the schema and validation should report which replay guarantees
are available.

### 3. Replace scan-heavy crust remap, not merely its processor

The new remap kernel parallelizes one query per cell, but each query still scans
all previous cells in its plate, approximately O(N^2 / plate_count), and uploads
the segmented candidate structure each erosion step. Benchmark it separately.
Likely next designs are deterministic per-plate spatial indices on CPU, or a
device-resident segmented spatial index. Any replacement must replay ascending
cell IDs for exact-distance ties and return the same source IDs before the CPU
builds transport/process provenance.

### 4. Move from `Cell` AoS to simulation SoA

`Cell` is a large aggregate with a per-cell neighbor vector and many cold fields.
Hot stages touch only a small subset yet load and traverse the full array of
structures. Keep stable IDs and schema records, but execute physical stages over
field-major arrays and a shared CSR graph. Materialize `Cell`/JSON records only
at compatibility/export boundaries.

### 5. Persist and batch OpenCL work

The current session rebuilds the context, queue, program, kernels, and buffers
for every world. Add a thread-safe process-level device/program cache and a
mesh-keyed immutable position/CSR cache. Cache identity must be an explicit mesh
version/fingerprint, not only `cells.data()` and size.

Convergence/divergence/transform are now one field-major batch. Extend the same
pattern to compatible independent fields rather than launching isolated kernels.
For calibration/ensemble work, batch independent worlds or at least reuse
compiled programs and capacity buffers. Collect actual event timings if the
profiling queue remains enabled.

### 6. Optimize graph stages on CPU first

Cell geometry, route corridors, species ranges, Priority-Flood, flow routing,
components, and repeated shortest paths remain substantial. Use shared CSR,
precomputed edge distances/barrier factors, reusable scratch arrays, and batched
independent searches. Profile after each change; irregular GPU graph ports are
unlikely to pay until Python objects and repeated reconstruction are removed.

## Test matrix

Every performance change should cover these axes:

| Axis | Required cases |
| --- | --- |
| Backend | `cpu`, below-threshold `auto`, eligible `auto`, explicit `opencl`, initialization fallback, runtime fallback after at least one dispatch. |
| Mesh | Fibonacci and geodesic; Fibonacci with brute-force KNN validation. |
| Size | 128, 512, 4,096, 16,384, 32,767, 32,768, and a 65,536 performance case. |
| Erosion | 0, 1, 2, and canonical 6. |
| Planet | 3,000 km, 6,371 km, and 12,000 km radii; sub-/super-Earth gravity. |
| Threads | Automatic and multiple explicit counts; verify explicit generation telemetry and restoration of the caller's prior ICV, including when its initial maximum is 1. |
| Output | cells included/excluded and all supported precision values. |
| Determinism | repeated CPU hashes; CPU/OpenCL physical payload comparison; multiple seeds and plate counts. |
| Failure | invalid/non-finite config; missing loader/platform/device; build failure; buffer allocation, write, enqueue, read, and release paths. |
| Lifetime | repeated worlds, nested sessions, concurrent host threads, and RSS/resource-handle plateau. |
| Device coverage | NVIDIA, AMD, Intel, and a CPU OpenCL implementation; OpenCL C 1.2/3.x front ends with required FP64 behavior. |

Current evidence:

- Release and strict-warning (`-Wall -Wextra -Wpedantic -Werror`) native CTest:
  3/3 passing, including brute-force Fibonacci KNN and the frozen legacy client;
- final optimized Python suite: 105 tests passing in 90.350 s;
- focused configuration/planet-scaling and numeric-extrema tests pass; a
  128-cell full-API maximum-supported-parameter run produced 89,329 finite
  floating values and no non-finite value;
- device-enabled RTX 5090 CTest: 3/3, including concurrent CPU/OpenCL geodesic
  generation with cells included at precision 8;
- exact tested CPU/OpenCL physical parity through 32,768 cells / erosion 6;
- automatic selection verified as CPU/no-probe at 32,767 and OpenCL at 32,768;
- CPU physical payloads match for explicit 1/4-thread and automatic-thread runs;
- final ASan/UBSan CTest: 3/3 passing with leak detection disabled because
  the ptrace environment made LeakSanitizer unusable;
- final remap/fused explicit-OpenCL 80-world RSS reaches a plateau.

Important gaps are cross-vendor parity, fault-injected OpenCL command failures,
release-count verification on failed commands, per-event kernel timing, and
automated performance regression thresholds. The single device-independent
automatic threshold is a portability heuristic, not a guarantee on slower or
integrated GPUs. The ordinary sandboxed CTest run exercises explicit OpenCL
initialization failure; automatic initialization/runtime fallback and device
kernels require a suitable OpenCL test environment.

## Exact verification and profiling commands

Run from the repository root.

### Release build and tests

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
ctest --test-dir build --output-on-failure
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest tests.test_config tests.test_planet_scaling -v
.venv/bin/magic-geo backend
```

The KNN reference can also be forced directly:

```bash
MAGIC_GEO_VALIDATE_FIBONACCI_KNN=1 build/magic_geo_native_api_test
```

### Reproduce the three API boundary timings

Each command runs in a fresh process and reports wall time and peak RSS. Do not
compare results from a debug or sanitizer build with the table above.

```bash
/usr/bin/time -v .venv/bin/python -c 'from pathlib import Path; from magic_geo.config import load_config, config_to_native; from magic_geo.native import generate_world; generate_world(config_to_native(load_config(Path("configs/earthlike_seed.yaml"))))'
/usr/bin/time -v .venv/bin/python -c 'from pathlib import Path; from magic_geo.api import generate_world; from magic_geo.config import load_config; generate_world(load_config(Path("configs/earthlike_seed.yaml")))'
/usr/bin/time -v .venv/bin/python -c 'from pathlib import Path; from magic_geo.api import generate_geo_world; from magic_geo.config import load_config; generate_geo_world(load_config(Path("configs/earthlike_seed.yaml")))'
```

Use multiple warm and cold runs and retain the raw `/usr/bin/time -v` output
before treating a change as a regression or improvement.

### Reproduce the 1,024-cell / erosion-1 Python profile

```bash
.venv/bin/python - <<'PY'
import cProfile
import pstats
from pathlib import Path

from magic_geo.api import generate_world
from magic_geo.config import WorldConfig, load_config

data = load_config(Path("configs/earthlike_seed.yaml")).model_dump(mode="python")
data["mesh"]["cell_count"] = 1024
data["erosion"]["iterations"] = 1
config = WorldConfig.model_validate(data)

profile = cProfile.Profile()
profile.runcall(generate_world, config)
profile.dump_stats("/tmp/magic_geo_1024_e1.prof")
pstats.Stats(profile).strip_dirs().sort_stats("cumulative").print_stats(40)
PY
```

### CPU/OpenCL physical payload parity

Run this only where `magic-geo backend` reports a qualifying GPU. It compares
the complete native payload after normalizing only backend telemetry.

```bash
.venv/bin/python - <<'PY'
from copy import deepcopy
from pathlib import Path

from magic_geo.config import load_config
from magic_geo.native import generate_world

base = load_config(Path("configs/earthlike_seed.yaml")).model_dump(mode="python")

for cells, erosion in (
    (128, 0),
    (512, 2),
    (4096, 6),
    (16384, 6),
    (32768, 6),
):
    cpu_config = deepcopy(base)
    cpu_config["mesh"]["cell_count"] = cells
    cpu_config["erosion"]["iterations"] = erosion
    cpu_config["compute"]["backend"] = "cpu"

    opencl_config = deepcopy(cpu_config)
    opencl_config["compute"]["backend"] = "opencl"

    cpu = generate_world(cpu_config)
    opencl = generate_world(opencl_config)
    if erosion:
        assert opencl["backend"]["opencl_crust_source_remap_dispatch_count"] == erosion
    cpu["backend"] = {}
    opencl["backend"] = {}
    assert cpu == opencl, (cells, erosion)
    print("exact physical parity", cells, erosion)
PY
```

The dispatch assertion proves that the remap kernel, rather than only
assignment/smoothing, executed.

### Sanitizers

```bash
cmake -S . -B build-asan \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DMAGIC_GEO_LIBRARY_OUTPUT_DIRECTORY="$(pwd)/build-asan/lib" \
  -DCMAKE_CXX_FLAGS='-fsanitize=address,undefined -fno-omit-frame-pointer' \
  -DCMAKE_EXE_LINKER_FLAGS='-fsanitize=address,undefined' \
  -DCMAKE_SHARED_LINKER_FLAGS='-fsanitize=address,undefined'
cmake --build build-asan -j
ASAN_OPTIONS=detect_leaks=0 ctest --test-dir build-asan --output-on-failure
```

`detect_leaks=0` documents an environment limitation, not a claim that leak
testing is unnecessary. Run LeakSanitizer or Valgrind in an environment where
ptrace and the OpenCL driver are compatible. Post-dispatch OpenCL failure
injection and release-count testing remain release-hardening work.

## Acceptance rule for future acceleration

A GPU or parallel change is ready only when it:

1. improves a named end-to-end or stage benchmark at the target size;
2. preserves discrete topology, stable IDs, ordering, and provenance;
3. passes CPU repeatability and CPU/GPU parity across the test matrix;
4. reports actual backend selection, dispatch, transfer, fallback, and errors;
5. has success and failure lifetime evidence;
6. does not move cost across the JSON/Python boundary and present it as an
   end-to-end speedup.

The highest-value program is therefore not “put every stage on the GPU.” It is
“keep a deterministic columnar simulation state alive across stages, use the
GPU for dense field transforms, use optimized CPU graph algorithms for ordered
topology, and serialize once at the edge.”
