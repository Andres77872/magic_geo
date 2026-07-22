# Compute Backends (CPU, OpenCL, CUDA)

[Wiki home](./README.md) > Compute Backends

magic-geo runs its simulation on a CPU reference implementation and can offload a small, explicitly enumerated set of dense native kernels to an OpenCL or CUDA device. The backend system is built around *truthfulness* rather than maximum offload: `cpu` never touches an accelerator runtime, explicit accelerator requests never silently degrade, automatic selection is deferred until the actual generated mesh size is known, and every selection, fallback, dispatch, transfer, and device capability is serialized into the world document. The only crust-transport work an accelerator does is a **separately named shadow reduction whose result is validated and then thrown away** — the authoritative forward spherical overlap stays on the CPU.

## On this page

- [The four backend selections](#the-four-backend-selections)
- [Where backend policy is configured](#where-backend-policy-is-configured)
- [Backend truthfulness rules](#backend-truthfulness-rules)
- [Automatic selection: thresholds, deferral, and the fallback chain](#automatic-selection-thresholds-deferral-and-the-fallback-chain)
- [What is actually accelerated](#what-is-actually-accelerated)
- [What stays CPU-authoritative](#what-stays-cpu-authoritative)
- [The discarded-output crust-overlap shadow kernel](#the-discarded-output-crust-overlap-shadow-kernel)
- [Backend telemetry in the world document](#backend-telemetry-in-the-world-document)
- [Determinism contract and legitimate cross-backend differences](#determinism-contract-and-legitimate-cross-backend-differences)
- [OpenCL device qualification](#opencl-device-qualification)
- [The CUDA build story](#the-cuda-build-story)
- [Threads and OpenMP](#threads-and-openmp)
- [Worked examples](#worked-examples)
- [What is and is not verified, on which hardware](#what-is-and-is-not-verified-on-which-hardware)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

---

## The four backend selections

`ComputeOptions::compute_backend` is an integer selector defined in `cpp/include/magic_geo/native.hpp:74-79`; the string names come from `requested_backend_name` in `cpp/src/opencl_compute.cpp:494-502`, and the Python mapping is `COMPUTE_BACKEND_IDS` in `src/magic_geo/native.py:22`.

| ID | Name | Constructor path (`cpp/src/opencl_compute.cpp`) | Semantics |
| ---: | --- | --- | --- |
| 0 | `auto` | lines 821-826 set `auto_selection_pending = true` | No probe at construction. Selection is deferred to the first accelerated operation, which passes the **actual generated mesh size**. |
| 1 | `cpu` | lines 815-820 return immediately | Deterministic reference. No CUDA probe, no OpenCL `dlopen`, no device enumeration. |
| 2 | `opencl` | line 848 `probe_opencl()` then line 854 `select_opencl_or_fallback(true)` | Probes and initializes OpenCL only. Throws on any failure; never falls back. CUDA is never probed. |
| 3 | `cuda` | lines 828-845 `initialize_cuda_probe(true)` | Creates a real `CudaComputeSession`. Throws on any failure; never falls back. OpenCL is never probed. |

Any other value is rejected before a session exists: `validate_compute_options` throws `compute_backend must be auto, cpu, opencl, or cuda` (`cpp/src/engine/core.cpp:233-237`), and it runs first in every public facade entry point (`cpp/src/engine.cpp:20`, `:31`, `:42`, `:55`).

Exact throw messages for explicit requests:

| Requested | Failure condition | Message prefix (`cpp/src/opencl_compute.cpp`) |
| --- | --- | --- |
| `cuda` | no usable NVIDIA device / stub build | `explicit CUDA backend requested but initialization failed: ` + CUDA error, or `no usable NVIDIA CUDA device is available` (lines 831-838) |
| `opencl` | no qualifying device | `explicit OpenCL backend requested but initialization failed: ` + probe error or `no qualifying FP64 OpenCL device is available` (lines 916-919) |
| `opencl` | context/queue/program/kernel creation failed | same prefix + the OpenCL error string (lines 939-944) |
| `opencl` / `cuda` | runtime error during a dispatch | the original exception is rethrown unchanged (lines 2855-2857, 2889-2891, 2949-2951, 3026-3030) |

On a build without CUDA, `cuda_compute_stub.cpp` supplies the session; every kernel entry point throws `CUDA backend is unavailable because this build was compiled without CUDA support` (`cpp/src/cuda_compute_stub.cpp:8-12`) and the telemetry reports `error = "CUDA support was not compiled into the native library"` (`cpp/src/cuda_compute_stub.cpp:23-24`).

---

## Where backend policy is configured

| Surface | Field | Default | Source |
| --- | --- | --- | --- |
| YAML / Pydantic | `compute.backend` (`auto`\|`cpu`\|`opencl`\|`cuda`) | `auto` | `src/magic_geo/config.py:425-428` |
| YAML / Pydantic | `compute.threads` (0…1024) | `0` | `src/magic_geo/config.py:429-433`, bound `MAX_COMPUTE_THREADS = 1_024` at `src/magic_geo/config.py:33` |
| YAML / Pydantic | `compute.opencl_prefer_gpu` | `true` | `src/magic_geo/config.py:435-438` |
| C++ | `magic_geo::ComputeOptions{compute_backend, opencl_prefer_gpu}` | `0`, `true` | `cpp/include/magic_geo/native.hpp:74-79` |
| C ABI | `CConfigV2{CConfig base; int compute_backend; int opencl_prefer_gpu;}` | — | `cpp/src/c_api.cpp:65-70` maps it to `ComputeOptions` |
| Python ctypes | `NativeConfigV2` / `NativeConfigV3` | — | `src/magic_geo/native.py` |
| CLI | no `--backend` flag; use the config file | — | `src/magic_geo/cli/commands/generate.py:18-45` |
| CLI | `magic-geo backend` prints the capability probe | — | `src/magic_geo/cli/commands/config.py:52-55` |

`threads` lives on `Params` (`cpp/include/magic_geo/native.hpp:61`), not on `ComputeOptions`. The unversioned one-argument C++ overload `generate_world_json(const Params&)` and the v1 C entry point `magic_geo_generate_json` hardcode CPU; only the v2/v3 entry points carry `ComputeOptions`.

The `smoke` config preset pins `compute.backend: "cpu"` and `compute.threads: 1` (`src/magic_geo/config.py:526-527`).

---

## Backend truthfulness rules

These are stated as binding invariants in `cpp/src/engine/README.md` ("Preserve backend truthfulness") and implemented as follows.

| Rule | Implementation | Citation |
| --- | --- | --- |
| `cpu` must not initialize or probe CUDA or OpenCL | The constructor returns before any probe; `selection_reason = "CPU backend explicitly requested; CUDA/OpenCL probes skipped"` | `cpp/src/opencl_compute.cpp:815-820` |
| Below-threshold `auto` CPU selection is **not** a fallback | `ensure_auto_backend` sets `selected_backend = "cpu"` and a reason string but leaves `fallback_used` false | `cpp/src/opencl_compute.cpp:967-973` |
| Explicit `opencl`/`cuda` must never silently fall back | Selection failures throw; dispatch failures rethrow when `requested_backend` is 2 or 3 instead of calling `fall_back_to_cpu` | `cpp/src/opencl_compute.cpp:916-919`, `:939-944`, `:2855-2857`, `:2889-2891`, `:2949-2951`, `:3026-3030` |
| `auto` must never select a CPU OpenCL device | `choose_device_for_records` skips `CL_DEVICE_TYPE_CPU` when `requested_backend == 0` | `cpp/src/opencl_compute.cpp:1059-1062` |
| Automatic eligibility uses the **generated** mesh size, not the requested size | Every accelerated hook calls `ensure_auto_backend(cells.size())` before dispatching | `cpp/src/opencl_compute.cpp:952-965`, `:2843`, `:2875`, `:2915`, `:2970` |
| Qualifying FP64 devices must expose required numerical/runtime behavior | `DeviceRecord::qualifies()` — see [OpenCL device qualification](#opencl-device-qualification) | `cpp/src/opencl_compute.cpp:284-290` |
| Telemetry must identify actual dispatch counts, work sizes, transfer bytes/timings, allocations, device capabilities, and any fallback reason | 178 keys emitted by `Impl::json()` | `cpp/src/opencl_compute.cpp:2033-2724` |

### The one deliberate exception: the capability-only probe

`compute_backend_info_json()` builds a probe session with `compute_backend = 1` **and** `capability_only = true` when no generation is active (`cpp/src/opencl_compute.cpp:3044-3053`). In that mode the constructor's early `cpu` return is bypassed (`!capability_only && requested_backend == 1`), so the probe *does* enumerate CUDA (probe only, no session) and OpenCL, then reports:

- `requested_backend = "cpu"`,
- `selected_backend = "cpu"`,
- `backend_selection_reason = "capability-only probe; no generation is active"`.

This is exactly what `magic-geo backend` and `magic_geo.native.backend_info()` return. The "cpu never probes" rule constrains *generation sessions*; the dedicated capability query is an explicit, separately labelled probe. Inside a generation, `compute_backend_info_json()` instead returns the live session's telemetry, which is what `serialize_world` embeds under the `backend` key (`cpp/src/engine/world_serialization.cpp:85`).

---

## Automatic selection: thresholds, deferral, and the fallback chain

### The constants

```cpp
constexpr int OPENCL_AUTO_MIN_CELL_COUNT = 32768;
constexpr int CUDA_SM_120_AUTO_MIN_CELL_COUNT = 8192;
constexpr int CUDA_UNCALIBRATED_AUTO_MIN_CELL_COUNT = 32768;
```

`cpp/src/opencl_compute.cpp:99-101`.

| Candidate | Minimum **actual** cells | Basis |
| --- | ---: | --- |
| Native CUDA on an `sm_120` (compute capability 12.0) device | 8,192 | Measured crossover on one RTX 5090 (`docs/cuda_rtx5090_optimization.md:109`) |
| CUDA on a non-`sm_120` device | 32,768 | Conservative, explicitly uncalibrated policy (`docs/cuda_rtx5090_optimization.md:110`) |
| Qualifying non-CPU OpenCL device | 32,768 | Historical OpenCL calibration (`docs/gpu_simulation_audit.md:173-180`) |

`sm_120_optimized` is set only when the selected device reports `major == 12 && minor == 0` **and** the compiled kernel image reports `binaryVersion >= 120 || ptxVersion >= 120` (`cpp/src/cuda_compute.cu:556-557`). A CUDA 12.0-capability device running a build without `sm_120`/`compute_120` code therefore falls into the conservative 32,768 tier.

### Deferral

At construction, `auto` records only `selection_reason = "automatic accelerator selection is deferred until the actual mesh size is known"` and sets `auto_selection_pending` (`cpp/src/opencl_compute.cpp:821-826`). The first accelerated hook — plate assignment, scalar smoothing, fused three-field smoothing, or the shadow reconciliation — calls `ensure_auto_backend(cells.size())`, which resolves the decision once and records `automatic_planning_cell_count` (`cpp/src/opencl_compute.cpp:952-957`). This matters for `mesh.backend: geodesic_icosahedron`, whose realizable cell count differs from the requested `mesh.cell_count`.

### The decision table

`ensure_auto_backend` (`cpp/src/opencl_compute.cpp:952-1049`). `N` is the actual generated cell count.

| Condition | `selected_backend` | `backend_fallback_used` | `backend_selection_reason` |
| --- | --- | --- | --- |
| `N < 8192` (CUDA compiled) or `N < 32768` (stub build) — no probe at all | `cpu` | `false` | `automatic acceleration is below the evidence-based actual-mesh thresholds; CUDA/OpenCL probes skipped` |
| `N >= 8192`, CUDA session available, `sm_120_optimized` | `cuda` | `false` | `automatic selection chose native CUDA for an NVIDIA sm_120 device` |
| `N >= 32768`, CUDA session available, not `sm_120` | `cuda` | `false` | `automatic selection chose an uncalibrated FP64 NVIDIA CUDA device at the conservative threshold` |
| `8192 <= N < 32768`, CUDA device available but not `sm_120` | `cpu` | `false` | `automatic CUDA probe found an uncalibrated device below its conservative actual-mesh threshold; CPU retained by policy` |
| `N >= 32768`, CUDA unavailable, qualifying non-CPU OpenCL device found and initialized | `opencl` | `false` | `automatic CUDA selection was unavailable (<cuda reason>); selected qualifying OpenCL device`, or the plain OpenCL reason when CUDA was never probed |
| `N >= 32768`, OpenCL selected but runtime initialization threw | `cpu` | `true`, stage `runtime_initialization` | `automatic accelerator initialization fell back to CPU` |
| Eligible but nothing qualified | `cpu` | `true`, stage `device_selection` | `automatic accelerator selection fell back to CPU` |

Note the asymmetry that follows directly from the code: at `8192 <= N < 32768` on a CUDA-compiled build with **no usable device at all**, the CUDA probe *is* performed, `auto_offload_eligible` is false, `cuda_below_policy_threshold` is false, and control reaches the terminal block at lines 1036-1048 — so a fallback **is** recorded with `fallback_reason = "CUDA: <reason>"`. Only the "device present but uncalibrated" case is recorded as a policy retention rather than a fallback.

The composite fallback reason at lines 1039-1047 is `"CUDA: <a>; OpenCL: <b>"`, `"CUDA: <a>"`, `"OpenCL: <b>"`, or `"no qualifying accelerator is available"`.

### Selection reason strings (exhaustive)

| String | Emitted by |
| --- | --- |
| `CPU backend explicitly requested; CUDA/OpenCL probes skipped` | `:817-818` |
| `automatic accelerator selection is deferred until the actual mesh size is known` | `:823-824` |
| `native CUDA selected for an NVIDIA sm_120 device` | `:841-842` |
| `highest-scoring FP64 NVIDIA CUDA device` | `:843` |
| `capability-only probe; no generation is active` | `:851` |
| `highest-scoring qualifying GPU-preferred FP64 device` | `:931-932` (whenever `opencl_prefer_gpu` is true) |
| `highest-scoring qualifying non-CPU FP64 device` | `:934` (`auto`, `prefer_gpu=false`) |
| `highest-scoring qualifying FP64 device` | `:935` (explicit `opencl`, `prefer_gpu=false`) |
| `automatic OpenCL selection fell back to CPU` | `:925` |
| `automatic acceleration is below the evidence-based actual-mesh thresholds; CUDA/OpenCL probes skipped` | `:969-971` |
| `automatic selection chose native CUDA for an NVIDIA sm_120 device` | `:989` |
| `automatic selection chose an uncalibrated FP64 NVIDIA CUDA device at the conservative threshold` | `:990` |
| `automatic CUDA probe found an uncalibrated device below its conservative actual-mesh threshold; CPU retained by policy` | `:1008-1010` |
| `automatic CUDA selection was unavailable (…); selected qualifying OpenCL device` | `:1018-1021` |
| `automatic accelerator initialization fell back to CPU` | `:1030-1031` |
| `automatic accelerator selection fell back to CPU` | `:1048` |

### Fallback stages

`fall_back_to_cpu(stage, reason)` (`cpp/src/opencl_compute.cpp:1279-1290`) tears down the CUDA session (preserving its counters in `cuda_probe`, zeroing `allocated_device_bytes`), releases the whole OpenCL runtime, and records the stage. Stages actually emitted:

| `backend_fallback_stage` | Raised from |
| --- | --- |
| `device_selection` | `:1038`, `:923` — no qualifying device |
| `runtime_initialization` | `:946` — context/queue/program/kernel creation failed |
| `plate_assignment` | `:2859` |
| `neighbor_field_smoothing` | `:2893` |
| `batched_neighbor_field_smoothing` | `:2953-2955` |
| `crust_overlap_continuous_shadow_reconciliation` | `:3032-3034` |

If at least one accelerator dispatch already succeeded before the fallback, `active_backend` is reported as `hybrid`:

```cpp
const std::string active_backend =
    fallback_used && accelerator_dispatch_count > 0 ? "hybrid" : selected_backend;
```

`cpp/src/opencl_compute.cpp:2054-2057`, where `accelerator_dispatch_count = kernel_dispatch_count + cuda.kernel_dispatch_count` (`:2051-2052`). `initial_selected_backend` retains the first non-CPU backend that was actually selected (`:840`, `:930`, `:987`).

---

## What is actually accelerated

Exactly four kernel families exist, and only three of them feed production state. Hook call sites are in `cpp/src/engine/tectonics.cpp`.

| Operation | Hook | Call site | OpenCL kernel | CUDA kernel |
| --- | --- | --- | --- | --- |
| Nearest-plate-center assignment | `try_accelerated_assign_plates` | `cpp/src/engine/tectonics.cpp:58` | `assign_plates` (`opencl_compute.cpp:525-549`) | `assign_plates_kernel` (`cuda_compute.cu:33-63`) |
| Scalar CSR neighbor smoothing | `try_accelerated_smooth_field` | `cpp/src/engine/tectonics.cpp:104` | `smooth_neighbor_field` (`opencl_compute.cpp:551-574`) | `smooth_field_kernel` (`cuda_compute.cu:65-89`) |
| Fused three-field boundary smoothing | `try_accelerated_smooth_three_fields` | `cpp/src/engine/tectonics.cpp:163` | `smooth_three_neighbor_fields` (`opencl_compute.cpp:576-620`) | `smooth_three_fields_kernel` (`cuda_compute.cu:91-131`) |
| Crust-overlap continuous **shadow** reduction (discarded) | `reconcile_accelerated_crust_overlap_continuous_shadow` | `cpp/src/engine/tectonics.cpp:1151` | `reduce_crust_overlap_continuous_shadow` (`opencl_compute.cpp:622-663`) | `reduce_crust_overlap_continuous_shadow_kernel` (`cuda_compute.cu:133-178`) |

Semantics the device kernels are *written* to preserve. These are construction arguments plus the audited-host evidence below, not a demonstrated cross-vendor parity claim; no `*_parity_demonstrated` telemetry exists for these three families, and the audit still requires "a parity test for the exact tie and ordering rules it replaces" for any backend change (`docs/gpu_simulation_audit.md:365-368`).

- **Plate assignment** iterates centers in ascending plate order with strict `score > best`, so an exact tie keeps the earliest plate — identical to the CPU loop at `cpp/src/engine/tectonics.cpp:66-79`. Both device implementations re-validate every returned id against `[0, center_count)` and throw `… returned an invalid plate id` otherwise (`opencl_compute.cpp:1657-1662`, `cuda_compute.cu:934-940`).
- **Scalar smoothing** accumulates neighbors in stored CSR order and ping-pongs between two device buffers, matching the CPU `smooth_field` at `cpp/src/engine/tectonics.cpp:99-125`. `steps == 0` short-circuits to a copy on both paths.
- **Fused three-field smoothing** traverses the CSR row once but keeps each field's own summation order and self-weight, so it reproduces three independent scalar passes. The weights used by `classify_boundaries` are convergent `0.58`, divergent `0.58`, transform `0.62` over `params.boundary_smoothing_steps` (default 5) — `cpp/src/engine/tectonics.cpp:163-183`, `cpp/include/magic_geo/native.hpp:45`.

The two scalar-smoothing consumers outside boundary classification are the initial crust coherence field (1 step, self-weight 0.77) and the secondary relief field (4 steps, self-weight 0.58) — `cpp/src/engine/tectonics.cpp:307-318` with constants at `cpp/src/engine/constants.hpp:23-26`.

### Device resource model

| Aspect | OpenCL | CUDA |
| --- | --- | --- |
| Mesh cache key | `cells.data()` pointer + `cells.size()` (`opencl_compute.cpp:1292-1299`) | same (`cuda_compute.cu:755-763`) |
| Position layout | `double4` packed `PackedVec4`, 32 bytes, `alignas(32)` (`opencl_compute.cpp:795-801`) | structure-of-arrays `x`/`y`/`z` (`cuda_compute.cu:775-794`) |
| Adjacency | CSR `int` offsets + `int` neighbour ids, uploaded once per generation | same |
| Buffers | grow-only capacities; `create_buffer` rejects zero-byte and over-`CL_DEVICE_MAX_MEM_ALLOC_SIZE` requests (`opencl_compute.cpp:1301-1321`) | grow-only `DeviceBuffer<T>` with `cudaMalloc`/`cudaFree` accounting (`cuda_compute.cu:606-634`) |
| Queue/stream | in-order command queue with `CL_QUEUE_PROFILING_ENABLE`; all transfers blocking (`CL_TRUE`) | non-blocking stream + reusable start/stop events; `cudaMemcpyAsync` inside event-timed, event-synchronized segments (`cuda_compute.cu:545-550`, `:636-648`) |
| Launch geometry | local size = `min(256, CL_KERNEL_WORK_GROUP_SIZE, CL_DEVICE_MAX_WORK_GROUP_SIZE, max_work_item_size[0])`, rounded down to a multiple of `CL_KERNEL_PREFERRED_WORK_GROUP_SIZE_MULTIPLE`, floor 1 (`opencl_compute.cpp:1167-1208`) | fixed 256 threads = 8 warps of 32 (`cuda_compute.cu:20-22`); grid checked against `maxGridSize[0]` |
| Index width | 32-bit `cl_int`; cell and edge counts over `INT_MAX` throw | 32-bit `int`; `checked_int_count` throws `… exceeds 32-bit CUDA kernel indices` (`cuda_compute.cu:248-255`) |

`ComputeSession` is generation-scoped and thread-local (`thread_local ComputeSession::Impl* active_compute_session`, `opencl_compute.cpp:803`), with nested-session save/restore in the constructor/destructor (`:2819-2832`). Every hook checks `active_compute_session == nullptr` first — the three `try_accelerated_*` hooks return `false` and the `void` shadow reconciler returns immediately — so the CPU path runs unchanged.

---

## What stays CPU-authoritative

The world document states the scope explicitly: `backend_scope = "accelerated_native_kernels_not_end_to_end_pipeline"` (`cpp/src/opencl_compute.cpp:2061-2066`).

| Work | Placement | Evidence |
| --- | --- | --- |
| Forward spherical control-volume crust overlap (geometry, clipping, CSR, coverage arrangement, membership classes, extensive ledgers) | CPU, authoritative | `crust_transport_execution_backend = "cpu"`, `crust_transport_execution_model = "forward_spherical_control_volume_overlap_v1"`, `crust_transport_accelerator_dispatch_count = 0` (`opencl_compute.cpp:2067-2084`) |
| The production continuous remap of thickness/density/age | CPU, authoritative | `crust_overlap_continuous_production_remap_authoritative_backend = "cpu"` (`:2097-2102`) |
| Overlap geometry and the destination-major CSR | CPU, authoritative | `crust_overlap_geometry_and_csr_authoritative_backend = "cpu"` (`:2091-2096`) |
| Mesh construction, RNG, plate generation and seeding | CPU | no accelerator hook exists |
| Sea level solve, marine connectivity labelling | CPU | ordered connectivity/union-find (`docs/gpu_simulation_audit.md:379`) |
| Priority-Flood, depression correction, flow routing, sediment routing | CPU | irregular, order- and provenance-sensitive (`docs/gpu_simulation_audit.md:380-381`) |
| Climate, hydrology, cryosphere, soils, biomes, resources | CPU | no accelerator hook exists |
| Settlements, routes, civilization, history, economy | CPU | branch-heavy record assembly (`docs/gpu_simulation_audit.md:383`) |
| JSON/MessagePack serialization and the whole Python enrichment pipeline | CPU only | `docs/gpu_simulation_audit.md:384` |

The parity claims for accelerated crust transport are serialized as **explicitly false**:

| Key | Value | Meaning |
| --- | --- | --- |
| `crust_overlap_accelerator_geometry_parity_demonstrated` | `false` | No accelerator has reproduced the overlap geometry |
| `crust_overlap_accelerator_coverage_membership_parity_demonstrated` | `false` | No accelerator has reproduced coverage/membership classes |
| `crust_overlap_accelerator_categorical_parity_demonstrated` | `false` | No accelerator has reproduced crust type/lithology transitions |
| `crust_overlap_accelerator_complete_parity_demonstrated` | `false` | Complete parity is not claimed |
| `crust_overlap_accelerator_state_authoritative` | `false` | No accelerator result becomes state |

`cpp/src/opencl_compute.cpp:2145-2174`.

---

## The discarded-output crust-overlap shadow kernel

This is the project's clearest example of the authoritative/non-authoritative split, and it is worth reading in full.

### What it computes

After `build_forward_overlap_crust_transport_plan` has produced the authoritative CPU plan, `advance_plate_motion_and_crust` calls `reconcile_accelerated_crust_overlap_continuous_shadow(plan, cells, previous_crust_thickness, previous_crust_density, previous_crust_age)` (`cpp/src/engine/tectonics.cpp:1151-1157`). If the active backend is `cpu` the call returns immediately (`cpp/src/opencl_compute.cpp:2971-2973`).

Otherwise, one work item per destination cell walks the CPU-produced destination-major CSR and accumulates three raw extensive moments plus three derived continuous quantities:

```text
for edge in [destination_offsets[d], destination_offsets[d+1]):
    src         = source_cell_ids[edge]
    edge_volume = overlap_area_km2[edge] * thickness_km[src]
    volume         += edge_volume
    density_volume += edge_volume * density[src]
    age_moment     += edge_volume * age_ma[src]

output[0*N + d] = volume                                    # crust volume, km^3
output[1*N + d] = density_volume                            # density-weighted volume
output[2*N + d] = age_moment                                # age-volume moment
output[3*N + d] = volume > 0 ? volume / area_km2[d]  : 0    # remapped thickness, km
output[4*N + d] = volume > 0 ? density_volume/volume : density[d]   # remapped density
output[5*N + d] = volume > 0 ? age_moment/volume     : 0    # remapped age, Ma
```

OpenCL: `cpp/src/opencl_compute.cpp:622-663`. CUDA: `cpp/src/cuda_compute.cu:133-178`. The CPU reference replay is `replay_crust_overlap_continuous_reduction_cpu` (`cpp/src/crust_overlap_shadow.cpp:245-305`), which uses the identical accumulation order.

Its scope is serialized as `crust_overlap_continuous_shadow_scope = "raw_extensive_moments_and_derived_continuous_state_only"` and its model as `crust_overlap_continuous_shadow_model = "cpu_authoritative_overlap_csr_continuous_moment_shadow_v1"` (`cpp/src/opencl_compute.cpp:2103-2114`).

### Input preconditions (fail-closed)

`validate_crust_overlap_continuous_shadow_input` (`cpp/src/crust_overlap_shadow.cpp:152-243`) runs on both the device path and the CPU replay and throws on any of:

| Check | Message |
| --- | --- |
| empty mesh | `crust overlap continuous shadow requires a nonempty mesh` |
| cell or edge count > `INT_MAX` | `… exceeds 32-bit kernel indices` |
| `cell_count > SIZE_MAX / 6` | `… packed output cardinality overflow` |
| CSR root: `destination_offsets.size() != N+1`, `front() != 0`, `back() != edge_count`, or any operand array cardinality mismatch | `… input cardinality or CSR root is invalid` |
| non-finite/non-positive `area_km2`, negative thickness, non-positive density, negative age | `… cell area or source state is invalid` |
| `begin < 0`, `end < begin`, `end > edge_count` | `… destination offsets are invalid` |
| non-strictly-ascending source ids within a row, out-of-range source, non-finite or non-positive overlap area | `… edge order, source, or area is invalid` |

### How the result is validated against operation-count bounds

`validate_crust_overlap_continuous_shadow_result` (`cpp/src/crust_overlap_shadow.cpp:307-579`) is a deterministic, device-independent audit:

1. Re-validate the inputs, then require every device output array to be exactly `N` long and entirely finite (`require_finite_result_array`, `:15-34`).
2. Reject invalid signs: negative volume, density-weighted volume, age moment, remapped thickness, or remapped age; non-positive remapped density (`:352-372`).
3. Require the CPU authority operands to be present and finite: `remapped_crust_{thickness_km,density,age_ma}_by_cell` sized `N`, and finite `transported_crust_volume_km3`, `transported_density_weighted_crust_volume`, `transported_crust_age_volume_moment` (`:373-384`).
4. Recompute the CPU replay and compare, per destination and then globally.

Each comparison uses a **binary64 two-execution forward-error bound** rather than a tolerance constant (`two_execution_forward_error_bound`, `cpp/src/crust_overlap_shadow.cpp:57-102`):

```text
gamma_n = (n * eps) / (1 - n * eps)                  # eps = DBL_EPSILON, n = operation count
bound   = 2 * gamma_n * |operand magnitude| + 8 * ulp(max(|expected|, |actual|))
```

The bound is computed in `long double`, throws if `n * eps >= 0.5` (`… operation-count gamma is invalid`), if the ULP envelope is non-finite or non-positive, or if the resulting bound is non-finite, non-positive, or exceeds `DBL_MAX`. The operand magnitude is the `long double` sum of `|edge contribution|` over the row, i.e. the condition-number numerator for that reduction.

Operation counts per comparison (`checked_operation_count`, `:132-148`; call sites `:433-441`, `:550-570`):

| Compared quantity | Operation count `n` | Operand magnitude |
| --- | --- | --- |
| Per-destination crust volume | `2 * contributor_count` | Σ\|area·thickness\| over the row |
| Per-destination density-weighted volume | `3 * contributor_count` | Σ\|area·thickness·density\| |
| Per-destination age-volume moment | `3 * contributor_count` | Σ\|area·thickness·age\| |
| Per-destination remapped thickness / density / age | `5 * contributor_count + 2` | `max(\|expected\|, \|actual\|)` |
| Global transported crust volume | `2 * edge_count + cell_count` | global Σ of the row magnitudes |
| Global transported density-weighted volume | `3 * edge_count + cell_count` | global Σ |
| Global transported age-volume moment | `3 * edge_count + cell_count` | global Σ |

Crucially, the three **derived** per-destination quantities are compared against the CPU **production** remap (`transport.remapped_crust_thickness_km_by_cell`, `…_density_by_cell`, `…_age_ma_by_cell`), not against the replay — so the shadow is checked against the values the model actually uses. The three **global** sums are compared against the plan's own `transported_*` inventories. The raw per-destination moments are compared against the replay.

`record_comparison` (`:104-130`) tracks running maxima of error and bound per quantity, tracks `maximum_error_to_bound_ratio` (with a non-finite ratio pinned to `DBL_MAX`), and sets `validation.failure` on the **first** exceedance with the text `<label> exceeded its binary64 gamma-plus-ULP bound`. `validation.passed = failure.empty()` (`:577`).

The telemetry documents the summary semantics explicitly, because the per-quantity maxima are independent: `crust_overlap_continuous_shadow_error_summary_semantics = "per_quantity_maximum_error_and_maximum_bound_are_independent_uniform_maxima_paired_worst_case_is_maximum_error_to_bound_ratio"` (`cpp/src/opencl_compute.cpp:2115-2120`). In other words, do not divide the reported maximum error by the reported maximum bound — use `maximum_error_to_bound_ratio`.

### Why the result is thrown away

`reconcile_accelerated_crust_overlap_continuous_shadow` (`cpp/src/opencl_compute.cpp:2960-3036`) declares a local `CrustOverlapContinuousShadowResult result`, fills it from the device, validates it, merges the maxima into the session, increments counters — and lets `result` go out of scope. It is never written back into `CrustTransportPlan`, never touches `Cell`, and never participates in the crust material shadow or reservoir accounting. The header states this directly (`cpp/src/opencl_compute.hpp`, `crust_overlap_shadow.hpp`):

> Device output is validated against the CPU plan and discarded; this function never mutates the plan, cells, categorical state, or coverage geometry.

Three booleans make it machine-checkable: `crust_overlap_continuous_shadow_only = true`, `crust_overlap_continuous_shadow_authoritative = false`, `crust_overlap_continuous_shadow_result_used_for_state = false` (`cpp/src/opencl_compute.cpp:2127-2144`).

The reason it exists at all is stated in the audit: an accelerator port of the overlap transport would have to reproduce source-area closure, unnormalized destination gap/excess coverage, the global area-by-multiplicity histogram, arrangement line/fragment telemetry, all three extensive inventories, canonical ledger ordering, and fallback telemetry — "parity of a single dominant source ID is insufficient" (`docs/cuda_rtx5090_optimization.md:330-334`). The shadow is the first, narrowest, provably-safe slice of that programme: it exercises the device on the real CSR and produces evidence, without letting the device near the model.

### Failure handling

Any throw — input rejection, sign rejection, non-finite output, bound exceedance, or a device error — increments `crust_overlap_continuous_shadow_failure_count`, clears `crust_overlap_continuous_shadow_last_validation_passed`, and then either rethrows (explicit `opencl`/`cuda`) or falls back to CPU with stage `crust_overlap_continuous_shadow_reconciliation` (`cpp/src/opencl_compute.cpp:3022-3035`). The mismatch message is `accelerator crust-overlap continuous shadow mismatch: <failure>`.

`crust_overlap_continuous_shadow_validation_status` (`cpp/src/opencl_compute.cpp:2209-2228`) collapses this into one of five strings:

| Value | Condition |
| --- | --- |
| `failed_and_cpu_authority_retained` | `failure_count > 0` |
| `passed` | `validated_transition_count > 0` and equal to `cpu_conservative_crust_overlap_transition_count` |
| `partial_pass_before_cpu_fallback` | `validated_transition_count > 0` but fewer than the CPU transition count |
| `not_run_no_conservative_transition` | no validation, and `cpu_conservative_crust_overlap_transition_count == 0` |
| `not_run_no_active_accelerator` | no validation, but CPU transitions occurred |

`cpu_conservative_crust_overlap_transition_count` is measured, not derived from configuration: `record_cpu_conservative_crust_overlap_transition()` is called exactly once per successfully constructed forward-overlap plan (`cpp/src/engine/tectonics.cpp:1166`, counter at `cpp/src/opencl_compute.cpp:3038-3042`). The Python validator asserts it equals `len(plate_motion_history) - 1` — i.e. the identity step-0 checkpoint is excluded (`src/magic_geo/crust_transport_validation.py:1010-1015`).

---

## Backend telemetry in the world document

`serialize_world` embeds `backend_info_json()` under the top-level `backend` key (`cpp/src/engine/world_serialization.cpp:85`). The object is built by `ComputeSession::Impl::json()` (`cpp/src/opencl_compute.cpp:2033-2724`) and contains **178 keys**, always all of them (the selected-device block emits the same 24 keys with empty/zero values when no device was selected, `:2697-2720`). Numbers use `std::setprecision(9)` in default float format (`:727-735`); integers are exact.

### Core identity and selection

| Field | Type | Value / meaning |
| --- | --- | --- |
| `native_core` | string | Constant `"c++20"` |
| `openmp_enabled` | bool | `MAGIC_GEO_HAS_OPENMP` was defined at build time |
| `openmp_max_threads` | int | `omp_get_max_threads()` at serialization, or `1` without `_OPENMP` |
| `requested_backend` | string | `auto` \| `cpu` \| `opencl` \| `cuda` \| `invalid` |
| `selected_backend` | string | `cpu` \| `opencl` \| `cuda` after resolution |
| `active_backend` | string | `hybrid` if a fallback happened *after* at least one accelerator dispatch, otherwise `selected_backend` |
| `initial_selected_backend` | string | First non-CPU backend actually selected; `cpu` if none |
| `backend_selection_reason` | string | One of the sixteen strings tabulated above |
| `automatic_planning_cell_count` | int | Actual generated cell count that resolved `auto`; `0` for explicit backends |
| `accelerator_kernel_dispatch_count` | int | `opencl_kernel_dispatch_count + cuda_kernel_dispatch_count` |
| `opencl_prefer_gpu` | bool | Mirror of `ComputeOptions::opencl_prefer_gpu` |

### Scope and crust-transport authority

| Field | Type | Value |
| --- | --- | --- |
| `backend_scope` | string | Constant `accelerated_native_kernels_not_end_to_end_pipeline` |
| `crust_transport_execution_backend` | string | Constant `cpu` |
| `crust_transport_execution_model` | string | Constant `forward_spherical_control_volume_overlap_v1` |
| `crust_transport_accelerator_dispatch_count` | int | Constant `0` |
| `crust_transport_accelerator_dispatch_count_semantics` | string | Constant `complete_authoritative_forward_overlap_plan_dispatches_only` |
| `cpu_conservative_crust_overlap_transition_count` | int | Measured count of CPU-authoritative overlap plans built this generation |
| `crust_overlap_geometry_and_csr_authoritative_backend` | string | Constant `cpu` |
| `crust_overlap_continuous_production_remap_authoritative_backend` | string | Constant `cpu` |
| `crust_overlap_accelerator_geometry_parity_demonstrated` | bool | Constant `false` |
| `crust_overlap_accelerator_coverage_membership_parity_demonstrated` | bool | Constant `false` |
| `crust_overlap_accelerator_categorical_parity_demonstrated` | bool | Constant `false` |
| `crust_overlap_accelerator_complete_parity_demonstrated` | bool | Constant `false` |
| `crust_overlap_accelerator_state_authoritative` | bool | Constant `false` |

### Crust-overlap continuous shadow (27 keys total, counting the two per-runtime dispatch counters)

| Field | Type | Value / meaning |
| --- | --- | --- |
| `crust_overlap_continuous_shadow_model` | string | Constant `cpu_authoritative_overlap_csr_continuous_moment_shadow_v1` |
| `crust_overlap_continuous_shadow_scope` | string | Constant `raw_extensive_moments_and_derived_continuous_state_only` |
| `crust_overlap_continuous_shadow_error_summary_semantics` | string | Constant; warns that maxima are independent and the paired worst case is the ratio |
| `crust_overlap_continuous_shadow_only` | bool | Constant `true` |
| `crust_overlap_continuous_shadow_authoritative` | bool | Constant `false` |
| `crust_overlap_continuous_shadow_result_used_for_state` | bool | Constant `false` |
| `crust_overlap_continuous_shadow_device_dispatch_count` | int | OpenCL + CUDA shadow dispatches |
| `crust_overlap_continuous_shadow_validated_transition_count` | int | Transitions that passed validation |
| `crust_overlap_continuous_shadow_failure_count` | int | Validation or device failures |
| `crust_overlap_continuous_shadow_last_validation_passed` | bool | Outcome of the most recent reconciliation |
| `crust_overlap_continuous_shadow_all_validated_transitions_passed` | bool | `validated_transition_count > 0 && failure_count == 0` |
| `crust_overlap_continuous_shadow_validation_status` | string | One of the five status strings above |
| `crust_overlap_continuous_shadow_maximum_crust_volume_error_km3` | number | Running max abs error, km³ |
| `crust_overlap_continuous_shadow_maximum_crust_volume_error_bound_km3` | number | Running max of the corresponding bound |
| `crust_overlap_continuous_shadow_maximum_density_weighted_volume_error` | number | Running max abs error |
| `crust_overlap_continuous_shadow_maximum_density_weighted_volume_error_bound` | number | Running max bound |
| `crust_overlap_continuous_shadow_maximum_age_volume_moment_error` | number | Running max abs error |
| `crust_overlap_continuous_shadow_maximum_age_volume_moment_error_bound` | number | Running max bound |
| `crust_overlap_continuous_shadow_maximum_remapped_thickness_error_km` | number | Running max abs error, km |
| `crust_overlap_continuous_shadow_maximum_remapped_thickness_error_bound_km` | number | Running max bound, km |
| `crust_overlap_continuous_shadow_maximum_remapped_density_error` | number | Running max abs error |
| `crust_overlap_continuous_shadow_maximum_remapped_density_error_bound` | number | Running max bound |
| `crust_overlap_continuous_shadow_maximum_remapped_age_error_ma` | number | Running max abs error, Ma |
| `crust_overlap_continuous_shadow_maximum_remapped_age_error_bound_ma` | number | Running max bound, Ma |
| `crust_overlap_continuous_shadow_maximum_error_to_bound_ratio` | number | The only paired worst case; `< 1.0` means every comparison stayed inside its bound |
| `opencl_crust_overlap_continuous_shadow_dispatch_count` | int | OpenCL-only shadow dispatches |
| `cuda_crust_overlap_continuous_shadow_dispatch_count` | int | CUDA-only shadow dispatches |

### Automatic thresholds, eligibility, and fallback

| Field | Type | Value / meaning |
| --- | --- | --- |
| `cuda_auto_min_cell_count` | int | Effective CUDA threshold for this session: `8192` by default, raised to `32768` once a non-`sm_120` device is found available |
| `cuda_sm_120_auto_min_cell_count` | int | Constant `8192` |
| `cuda_uncalibrated_auto_min_cell_count` | int | Constant `32768` |
| `cuda_auto_offload_eligible` | bool | Actual mesh met the effective CUDA threshold |
| `opencl_auto_min_cell_count` | int | Constant `32768` |
| `opencl_auto_offload_eligible` | bool | Actual mesh met the OpenCL threshold |
| `backend_fallback_used` | bool | A fallback to CPU was recorded (below-threshold `auto` is **not** a fallback) |
| `backend_fallback_stage` | string | Empty, or one of the six stages tabulated above |
| `backend_fallback_reason` | string | Empty, or the underlying error / composite `CUDA: …; OpenCL: …` |

### CUDA capability and device identity

| Field | Type | Value / meaning |
| --- | --- | --- |
| `cuda_compiled` | bool | `MAGIC_GEO_HAS_CUDA` was defined (real `.cu` translation unit, not the stub) |
| `cuda_probe_performed` | bool | A CUDA probe or session was constructed this session |
| `cuda_capability_status` | string | `not_probed` \| `not_compiled` \| `available` \| `unavailable` |
| `cuda_runtime_initialized` | bool | Stream/events/primary context were created |
| `cuda_available` | bool | A usable device was selected |
| `cuda_nvidia_device` | bool | Selected device is NVIDIA |
| `cuda_fp64_supported` | bool | Selected device supports FP64 |
| `cuda_sm_120_optimized` | bool | `major == 12 && minor == 0` and native `sm_120` binary or `compute_120` PTX present |
| `cuda_error` | string | Last CUDA error/initialization message; empty on success |
| `cuda_device_count` | int | `cudaGetDeviceCount` |
| `cuda_selected_device_ordinal` | int | `-1` when none selected |
| `cuda_device_vendor` | string | `"NVIDIA"` when available |
| `cuda_device_name` | string | `cudaDeviceProp::name` |
| `cuda_device_uuid` | string | Hyphenated hex from `cudaDeviceProp::uuid` |
| `cuda_pci_bus_id` | string | `cudaDeviceGetPCIBusId` |
| `cuda_compute_capability_major` / `_minor` | int | Device compute capability |
| `cuda_kernel_binary_version` | int | `cudaFuncAttributes::binaryVersion` for `assign_plates_kernel` |
| `cuda_kernel_ptx_version` | int | `cudaFuncAttributes::ptxVersion` |
| `cuda_driver_version` | int | `cudaDriverGetVersion` |
| `cuda_runtime_version` | int | `cudaRuntimeGetVersion` |
| `cuda_total_global_memory_bytes` | int | `cudaMemGetInfo` total (overwrites the `cudaDeviceProp` value) |
| `cuda_free_global_memory_bytes` | int | `cudaMemGetInfo` free at initialization |
| `cuda_multiprocessor_count` | int | SM count |
| `cuda_warp_size` | int | Must equal 32 to qualify |
| `cuda_max_threads_per_block` | int | Must be ≥ 256 to qualify |
| `cuda_max_threads_per_multiprocessor` | int | Device limit |
| `cuda_max_block_dimension_x` / `_y` / `_z` | int | `maxThreadsDim[0..2]` |
| `cuda_max_grid_dimension_x` / `_y` / `_z` | int | `maxGridSize[0..2]` |
| `cuda_l2_cache_bytes` | int | `l2CacheSize` |
| `cuda_shared_memory_per_block_bytes` | int | `sharedMemPerBlock` |
| `cuda_shared_memory_per_multiprocessor_bytes` | int | `sharedMemPerMultiprocessor` |
| `cuda_registers_per_block` | int | `regsPerBlock` |
| `cuda_registers_per_multiprocessor` | int | `regsPerMultiprocessor` |
| `cuda_core_clock_khz` | int | `cudaDevAttrClockRate` |
| `cuda_memory_clock_khz` | int | `cudaDevAttrMemoryClockRate` |
| `cuda_memory_bus_width_bits` | int | `memoryBusWidth` |
| `cuda_fp_contract` | string | Constant `"off"` |

### CUDA counters, transfers, allocations, timing, launch geometry

| Field | Type | Value / meaning |
| --- | --- | --- |
| `cuda_kernel_dispatch_count` | int | All CUDA kernel launches |
| `cuda_plate_assignment_dispatch_count` | int | `assign_plates_kernel` launches |
| `cuda_smoothing_operation_count` | int | Completed scalar smoothing *operations* (not steps) |
| `cuda_smoothing_kernel_dispatch_count` | int | Scalar smoothing *steps* |
| `cuda_batched_smoothing_operation_count` | int | Completed fused three-field operations |
| `cuda_batched_smoothing_kernel_dispatch_count` | int | Fused three-field steps |
| `cuda_crust_overlap_continuous_shadow_dispatch_count` | int | Shadow reductions |
| `cuda_host_to_device_bytes` | int | Cumulative H2D bytes |
| `cuda_device_to_host_bytes` | int | Cumulative D2H bytes |
| `cuda_device_allocation_count` | int | `cudaMalloc` calls |
| `cuda_mesh_upload_count` | int | Position and adjacency upload events |
| `cuda_allocated_device_bytes` | int | Currently held device bytes (zeroed after a fallback releases the session) |
| `cuda_peak_allocated_device_bytes` | int | High-water mark |
| `cuda_kernel_time_ms` | number | Cumulative CUDA-event kernel time |
| `cuda_transfer_time_ms` | number | Cumulative CUDA-event transfer time |
| `cuda_operation_time_ms` | number | Cumulative host `steady_clock` operation wall time |
| `cuda_last_kernel_time_ms` | number | Kernel time of the last completed operation |
| `cuda_last_transfer_time_ms` | number | Transfer time of the last completed operation |
| `cuda_last_operation_time_ms` | number | Wall time of the last completed operation |
| `cuda_last_logical_work_items` | int | Logical items (cells) of the last launch |
| `cuda_last_grid_blocks` | int | Grid blocks of the last launch |
| `cuda_last_threads_per_block` | int | Always 256 while CUDA is active |
| `cuda_last_warps_per_block` | int | Always 8 while CUDA is active |

### OpenCL capability and probe outcome

| Field | Type | Value / meaning |
| --- | --- | --- |
| `opencl_probe_performed` | bool | `discover_opencl` ran |
| `opencl_capability_status` | string | `not_probed` \| `probe_failed` \| `available` \| `no_qualifying_device` |
| `opencl_loader_found` | bool | `libOpenCL.so.1` or `libOpenCL.so` was `dlopen`ed |
| `opencl_probe_ok` | bool | No unexpected `clGetDeviceIDs` error occurred |
| `opencl_platform_count` | int | `clGetPlatformIDs` count |
| `opencl_gpu_device_count` | int | Devices with `CL_DEVICE_TYPE_GPU` |
| `opencl_cpu_device_count` | int | Devices with `CL_DEVICE_TYPE_CPU` |
| `opencl_accelerator_device_count` | int | Devices with `CL_DEVICE_TYPE_ACCELERATOR` |
| `opencl_fp64_device_count` | int | Devices with any non-zero `CL_DEVICE_DOUBLE_FP_CONFIG` |
| `opencl_qualifying_device_count` | int | Devices passing the full qualification predicate |
| `opencl_qualifying_gpu_device_count` | int | Qualifying devices that are GPUs |
| `opencl_auto_preferred_gpu_available` | bool | `opencl_qualifying_gpu_device_count > 0` |
| `opencl_fp64_required` | bool | Constant `true` |
| `opencl_available` | bool | `opencl_qualifying_device_count > 0` |
| `opencl_error` | string | Probe error text, empty on success |
| `opencl_program_built` | bool | A program was built at least once this session (sticky) |
| `opencl_program_active` | bool | A built program is currently alive (cleared by release/fallback) |
| `opencl_build_options` | string | Constant `-cl-std=CL1.2` |
| `opencl_fp_contract` | string | Constant `"off"` |
| `opencl_profiling_queue_enabled` | bool | An OpenCL runtime is currently ready (queue created with `CL_QUEUE_PROFILING_ENABLE`) |

### OpenCL counters and last launch

| Field | Type | Value / meaning |
| --- | --- | --- |
| `opencl_kernel_dispatch_count` | int | All OpenCL `clEnqueueNDRangeKernel` calls |
| `opencl_plate_assignment_dispatch_count` | int | `assign_plates` dispatches |
| `opencl_smoothing_operation_count` | int | Completed scalar smoothing operations |
| `opencl_smoothing_kernel_dispatch_count` | int | Scalar smoothing steps |
| `opencl_batched_smoothing_operation_count` | int | Completed fused three-field operations |
| `opencl_batched_smoothing_kernel_dispatch_count` | int | Fused three-field steps |
| `opencl_crust_overlap_continuous_shadow_dispatch_count` | int | Shadow reductions |
| `opencl_host_to_device_bytes` | int | Cumulative bytes written via `clEnqueueWriteBuffer` |
| `opencl_device_to_host_bytes` | int | Cumulative bytes read via `clEnqueueReadBuffer` |
| `opencl_last_global_work_size` | int | Rounded-up global size of the last dispatch |
| `opencl_last_local_work_size` | int | Local size of the last dispatch |

### Selected OpenCL device (or the first qualifying candidate; empty/zero when none)

| Field | Type | Value / meaning |
| --- | --- | --- |
| `opencl_platform_name` / `_vendor` / `_version` | string | `CL_PLATFORM_NAME` / `_VENDOR` / `_VERSION` |
| `opencl_device_name` | string | `CL_DEVICE_NAME` |
| `opencl_device_vendor` | string | `CL_DEVICE_VENDOR` |
| `opencl_device_type` | string | `gpu` \| `accelerator` \| `cpu` \| `other` \| `""` |
| `opencl_driver_version` | string | `CL_DRIVER_VERSION` |
| `opencl_device_version` | string | `CL_DEVICE_VERSION` |
| `opencl_c_version` | string | `CL_DEVICE_OPENCL_C_VERSION` |
| `opencl_device_available` | bool | `CL_DEVICE_AVAILABLE` |
| `opencl_device_compiler_available` | bool | `CL_DEVICE_COMPILER_AVAILABLE` |
| `opencl_device_fp64` | bool | `CL_DEVICE_DOUBLE_FP_CONFIG != 0` |
| `opencl_device_fp64_denorm` | bool | `CL_FP_DENORM` bit |
| `opencl_device_fp64_round_to_nearest` | bool | `CL_FP_ROUND_TO_NEAREST` bit |
| `opencl_device_fp64_inf_nan` | bool | `CL_FP_INF_NAN` bit |
| `opencl_device_endian_little` | bool | `CL_DEVICE_ENDIAN_LITTLE` |
| `opencl_device_endian_matches_host` | bool | Device endianness equals host endianness |
| `opencl_device_opencl_c_1_2` | bool | Parsed `OpenCL C` version ≥ 1.2 |
| `opencl_device_address_bits` | int | `CL_DEVICE_ADDRESS_BITS` |
| `opencl_device_compute_units` | int | `CL_DEVICE_MAX_COMPUTE_UNITS` |
| `opencl_device_global_memory_bytes` | int | `CL_DEVICE_GLOBAL_MEM_SIZE` |
| `opencl_device_max_allocation_bytes` | int | `CL_DEVICE_MAX_MEM_ALLOC_SIZE` |
| `opencl_device_max_work_group_size` | int | `CL_DEVICE_MAX_WORK_GROUP_SIZE` |
| `opencl_device_max_work_item_size_0` | int | First entry of `CL_DEVICE_MAX_WORK_ITEM_SIZES` |

### Machine-checked telemetry invariants

`src/magic_geo/crust_transport_validation.py:1000-1016` fails a world whose `backend` object does not satisfy all of:

```python
backend["backend_scope"] == "accelerated_native_kernels_not_end_to_end_pipeline"
backend["crust_transport_execution_backend"] == "cpu"
backend["crust_transport_execution_model"] == "forward_spherical_control_volume_overlap_v1"
type(backend["crust_transport_accelerator_dispatch_count"]) is int
backend["crust_transport_accelerator_dispatch_count"] == 0
type(backend["cpu_conservative_crust_overlap_transition_count"]) is int
backend["cpu_conservative_crust_overlap_transition_count"] == len(plate_motion_history) - 1
```

---

## Determinism contract and legitimate cross-backend differences

The CPU implementation is the reference semantics (`docs/gpu_simulation_audit.md:328-336`). Optimizations must preserve RNG construction and consumption order; cell/plate/neighbor/candidate/graph-edge/serializer order; strict-improvement tie breaking and stable identifiers; OpenMP static schedules where output can depend on iteration ownership; floating expression and accumulation order; and complete provenance and replay relationships.

Floating-point contraction is disabled on all three paths:

| Path | Setting | Source |
| --- | --- | --- |
| C++ (GNU/Clang) | `-ffp-contract=off`, gated on `$<COMPILE_LANGUAGE:CXX>` | `CMakeLists.txt:137-142` |
| OpenCL C | `#pragma OPENCL FP_CONTRACT OFF` in the kernel source, built with `-cl-std=CL1.2` | `cpp/src/opencl_compute.cpp:523`, `:1121` |
| CUDA | `--fmad=false --ftz=false --prec-div=true --prec-sqrt=true -lineinfo` | `CMakeLists.txt:197-201` |

### Where results may legitimately differ

| Difference | Status |
| --- | --- |
| The whole `backend` object | **Expected to differ** across hosts and backends; the benchmark and the parity recipe both normalize it away before comparing (`docs/gpu_simulation_audit.md:603-605`) |
| `auto` backend choice | **Hardware-dependent by design**; only the selection and fallback must be truthfully serialized |
| CPU vs GPU physical fields | Contract is *identical discrete topology / IDs / order* and *numerically equal physical fields under explicit tolerances and invariant/replay validation* — not a portable bitwise promise across OpenCL vendors and compilers (`docs/gpu_simulation_audit.md:358-367`) |
| Same CPU build / platform / configuration | Byte-stable output remains expected |
| Different CPU compilers or optimization levels | Not promised. One historical GCC 15.2 `pow(delta, 2.0)` rewrite produced three one-ulp climate differences until the square was expressed directly (`docs/gpu_simulation_audit.md:345-352`) |

Observed exact equality on one device is recorded as evidence, not a portable guarantee: on the audited RTX 5090, CPU and OpenCL physical payloads were exactly equal after removing only the `backend` object for 128/erosion-0, 512/erosion-2, 4,096/erosion-6, 16,384/erosion-6 and 32,768/erosion-6 (`docs/gpu_simulation_audit.md:340-344`); CPU vs CUDA payload digests matched exactly at 4,096 / 8,192 / 16,384 / 32,768 cells with erosion 6 (`docs/cuda_rtx5090_optimization.md:204-212`). **Both of those measurement sets predate the current `forward_spherical_control_volume_overlap_v1` transport path and covered the since-removed nearest-source remap kernel.**

The explicit prohibition in the audit still stands: "Do not move an ordered reduction, RNG-consuming loop, priority queue, union-find tie, or graph traversal to an unordered atomic implementation and call it equivalent" (`docs/gpu_simulation_audit.md:365-368`).

---

## OpenCL device qualification

OpenCL is a pure **runtime** dependency. `cpp/src/opencl_compute.cpp` is always compiled into the library, `${CMAKE_DL_LIBS}` is always linked (`CMakeLists.txt:193`), and the ICD is discovered with `dlopen("libOpenCL.so.1")` then `dlopen("libOpenCL.so")` (`cpp/src/opencl_compute.cpp:162-165`). There is no OpenCL build-time dependency and no OpenCL header requirement — the 21 entry points are declared locally as function pointers and resolved with `dlsym` (`:112-132`, `:176-199`).

> Dynamic loading is implemented **only on Linux**. On any other platform `OpenClApi::load` returns `nullptr` with `error = "OpenCL dynamic loading is only implemented on Linux"` (`cpp/src/opencl_compute.cpp:171-174`), so explicit `opencl` always fails there and `auto` records that reason.

### Qualification predicate

`DeviceRecord::qualifies()` (`cpp/src/opencl_compute.cpp:284-290`) requires **all** of:

| Requirement | Queried via |
| --- | --- |
| `CL_DEVICE_AVAILABLE` | `CL_DEVICE_AVAILABLE` (0x1027) |
| `CL_DEVICE_COMPILER_AVAILABLE` | 0x1028 |
| FP64 supported (`CL_DEVICE_DOUBLE_FP_CONFIG != 0`) | 0x1032 |
| FP64 denormal support (`CL_FP_DENORM`) | bit 0 |
| FP64 INF/NaN support (`CL_FP_INF_NAN`) | bit 1 |
| FP64 round-to-nearest (`CL_FP_ROUND_TO_NEAREST`) | bit 2 |
| Device endianness matches host endianness | `CL_DEVICE_ENDIAN_LITTLE` vs a runtime host check |
| OpenCL C ≥ 1.2 | parsed from `CL_DEVICE_OPENCL_C_VERSION` by `supports_opencl_c_12` (`:298-309`) |
| `CL_DEVICE_ADDRESS_BITS >= 64` | 0x100D |
| `CL_DEVICE_MAX_WORK_GROUP_SIZE > 0` | 0x1004 |
| `CL_DEVICE_MAX_WORK_ITEM_SIZES[0] > 0` | 0x1005 |
| `CL_DEVICE_MAX_MEM_ALLOC_SIZE > 0` | 0x1010 |

If no device qualifies, the probe error is `no available compiler-capable 64-bit-address OpenCL device supports the required IEEE FP64 behavior` (`:461-465`). If platforms exist but expose no devices: `OpenCL platforms reported no devices`. If the loader is missing entirely: `OpenCL loader library was not found`. If platforms are zero: `OpenCL loader is present but no platforms were reported`.

### Device ranking

`device_score` (`cpp/src/opencl_compute.cpp:469-479`):

```text
score = min(compute_units, 1000)
      + 10000 if GPU and opencl_prefer_gpu
      +  3000 if GPU and not opencl_prefer_gpu
      +  2000 if ACCELERATOR
      +  1000 if CPU
```

Filtering in `choose_device_for_records` (`:1051-1074`):

| `requested_backend` | `opencl_prefer_gpu` | Eligible device types |
| --- | --- | --- |
| `auto` (0) | `true` | Qualifying **GPU** only |
| `auto` (0) | `false` | Qualifying **non-CPU** (GPU or accelerator) |
| `opencl` (2) | `true` | Any qualifying device (GPU ranked far higher) |
| `opencl` (2) | `false` | Any qualifying device |

So the "auto never picks a CPU OpenCL device" rule is scoped to `auto`: an *explicit* `opencl` request may legitimately select a CPU OpenCL implementation, and telemetry will report `opencl_device_type = "cpu"`.

### Allocation guards

`ensure_overlap_shadow_buffers` (`:1474-1582`) computes every required byte count with an overflow-checked helper, sums them with an overflow check, and rejects the whole allocation if the aggregate exceeds `CL_DEVICE_GLOBAL_MEM_SIZE` (`OpenCL crust-overlap shadow buffers exceed device global memory`). Individual buffers are rejected above `CL_DEVICE_MAX_MEM_ALLOC_SIZE` (`… exceeds CL_DEVICE_MAX_MEM_ALLOC_SIZE`, `:1309-1313`). CUDA applies the analogous aggregate check against `total_global_memory_bytes` (`cuda_compute.cu:1190-1197`).

---

## The CUDA build story

### Toolkit requirement and detection ladder

`CMakeLists.txt:21-69`, executed **before** any target exists:

1. If `MAGIC_GEO_ENABLE_CUDA` is `ON` (the default, `CMakeLists.txt:7-11`), prepend `-U_GNU_SOURCE -D_DEFAULT_SOURCE=1 -D_POSIX_C_SOURCE=200809L -D_XOPEN_SOURCE=700` to `CMAKE_CUDA_FLAGS_INIT`. The comment records why: CUDA 13.1 on glibc 2.43 hits new C23 `rsqrt` symbols that collide with CUDA's device declarations, and the flags must be visible during compiler identification (`CMakeLists.txt:22-30`).
2. `include(CheckLanguage)` + `check_language(CUDA)`.
3. `enable_language(CUDA)` if a compiler was found.
4. Require `CMAKE_CUDA_COMPILER_ID STREQUAL "NVIDIA"` **and** `CMAKE_CUDA_COMPILER_VERSION VERSION_GREATER_EQUAL 12.8`.
5. `find_package(CUDAToolkit 12.8 QUIET)`.
6. Only then: `MAGIC_GEO_CUDA_SOURCE = cpp/src/cuda_compute.cu` and `MAGIC_GEO_CUDA_ENABLED = ON`.

| Failure branch | Message | Result |
| --- | --- | --- |
| `MAGIC_GEO_ENABLE_CUDA=OFF` | STATUS `magic-geo CUDA backend: disabled by MAGIC_GEO_ENABLE_CUDA=OFF` | stub |
| No CUDA compiler | STATUS `magic-geo CUDA backend: compiler not found; building runtime stub` | stub |
| Non-NVIDIA compiler id | WARNING `… compiler '<id>' is not supported; NVIDIA nvcc 12.8+ is required` | stub |
| NVIDIA `< 12.8` | WARNING `… CUDA <version> cannot compile sm_120; CUDA 12.8+ is required` | stub |
| NVIDIA `>= 12.8`, no `CUDAToolkit` dev files | WARNING `… CUDA runtime development files were not found; building runtime stub` | stub |

CUDA 12.8 is the first toolkit release with Blackwell `sm_120` compiler support (`docs/cuda_rtx5090_optimization.md:36-38`).

### Architecture list

```cmake
set(
  MAGIC_GEO_CUDA_ARCHITECTURES
  "75-real;75-virtual;80-real;86-real;89-real;90-real;120-real;120-virtual"
  CACHE STRING
  "CUDA architectures for magic-geo (modern NVIDIA SASS, baseline forward PTX, native RTX 50 SASS, and Blackwell PTX)"
)
```

`CMakeLists.txt:12-17`. This emits SASS for `sm_75`, `sm_80`, `sm_86`, `sm_89`, `sm_90`, `sm_120`, plus forward PTX at `compute_75` and `compute_120`. The RTX 5090 audit deliberately narrowed it to `120-real;120-virtual` to prove native Blackwell code generation with a smaller artifact — that override is *not* the project default (`docs/cuda_rtx5090_optimization.md:55-61`). `sm_120a` is intentionally not used because these kernels need no architecture-specific features that would cost forward compatibility (`docs/cuda_rtx5090_optimization.md:40-42`).

### Target properties when CUDA is enabled

`CMakeLists.txt:195-215`:

| Property / definition | Value | Rationale |
| --- | --- | --- |
| `MAGIC_GEO_HAS_CUDA=1` | compile definition | Gates the CUDA branch of `ensure_auto_backend` and the `cuda_compiled` telemetry |
| CUDA compile options | `--fmad=false --ftz=false --prec-div=true --prec-sqrt=true -lineinfo` | No fast math, no FMA contraction, no flush-to-zero |
| `CUDA_ARCHITECTURES` | `${MAGIC_GEO_CUDA_ARCHITECTURES}` | See above |
| `CUDA_RUNTIME_LIBRARY` | `Static` | "Embed the small runtime support layer so a CUDA-enabled wheel can still load and use CPU/OpenCL on a host without a separately installed cudart. libcuda itself remains driver-provided" (`CMakeLists.txt:202-204`) |
| `CUDA_SEPARABLE_COMPILATION` | `OFF` | Whole-program device compilation |
| `CUDA_STANDARD` / `_REQUIRED` | `20` / `ON` | Matches the C++ standard |
| `CUDA_VISIBILITY_PRESET` | `hidden` | Keeps device-side symbols unexported |

Static `cudart` does **not** bundle the driver: CUDA execution still requires a compatible NVIDIA kernel driver (`docs/cuda_rtx5090_optimization.md:64-66`). The audit confirms the intended behavior in a driverless, GPU-masked sandbox: the installed static-runtime artifact loaded successfully and reported `cuda_compiled=true`, `cuda_available=false`, and selected CPU (`docs/cuda_rtx5090_optimization.md:308-311`).

### The stub

`cpp/src/cuda_compute_stub.cpp` (95 lines) provides the same `CudaComputeSession` ABI with `compiled = false`, `runtime_initialized = false`, `available = false`, `selected_device_ordinal = -1`, and every kernel entry point throwing. `CudaComputeSession::probe()` constructs a stub session and returns its telemetry, so a probe on a stub build is cheap and honest.

### CUDA device selection inside the session

`cpp/src/cuda_compute.cu:312-567`. A device must satisfy `meets_kernel_requirements` (`:373-382`): FP64 support (`major > 1 || (major == 1 && minor >= 3)`), compute mode not `cudaComputeModeProhibited`, `warpSize == 32`, `maxThreadsPerBlock >= 256`, and `maxThreadsDim[0] >= 256`. It must additionally have a usable executable image, proven by successfully calling `cudaFuncGetAttributes` on `assign_plates_kernel` after setting the device (`:389-408`); otherwise the session throws `selected CUDA device has no executable image for the configured MAGIC_GEO_CUDA_ARCHITECTURES` (`:484-489`).

With a negative requested ordinal (the default), ranking is lexicographic over (`:419-459`):

1. `multiProcessorCount * clockRate_kHz * 1024 / max(1, FP32:FP64 perf ratio)`;
2. `memoryClockRate_kHz * memoryBusWidth`;
3. `totalGlobalMem`;
4. `major * 100 + minor`.

Every operation is wrapped in a `ScopedCudaDevice` guard that restores the caller's previously current device (`:201-229`), and the session is documented as non-thread-safe and bound to its creating thread (`cpp/src/cuda_compute.hpp`).

### CUDA test target

`magic_geo_cuda_compute_test` is registered only when `MAGIC_GEO_CUDA_ENABLED`, built from `cpp/tests/cuda_compute_test.cpp` + `cpp/src/cuda_compute.cu` + `cpp/src/crust_overlap_shadow.cpp`, with the same precision flags and `SKIP_RETURN_CODE 77` so it skips cleanly with no device (`CMakeLists.txt:475-511`). A CPU-only counterpart, `magic_geo_crust_overlap_shadow`, always builds and exercises the shadow validator without any device (`CMakeLists.txt:298-318`).

---

## Threads and OpenMP

| Aspect | Behavior | Source |
| --- | --- | --- |
| Config field | `compute.threads`, integer `0…1024`, default `0` | `src/magic_geo/config.py:429-433` |
| Native bound | `threads must be between 0 and 1024` | `cpp/src/engine/core.cpp:427-428` |
| ABI location | `CConfig::threads` (v1 field 39), i.e. part of `Params`, not `ComputeOptions` | `cpp/include/magic_geo/native.hpp:61` |
| `threads == 0` | `omp_set_num_threads` is **not** called; host OpenMP policy is untouched | `cpp/src/engine/core.cpp:213-223` |
| `threads > 0` | `previous_max_threads_ = omp_get_max_threads()` then `omp_set_num_threads(requested)` | `cpp/src/engine/core.cpp:215-219` |
| Restoration | The destructor restores the caller's prior ICV on both normal and exceptional exit | `cpp/src/engine/core.cpp:225-231` |
| Scope | One generation. `ScopedThreadConfiguration` is constructed in every facade entry point before `ComputeSession` | `cpp/src/engine.cpp:22`, `:33`, `:44`, `:57` |
| Build linkage | `find_package(OpenMP)` is optional; when found, `OpenMP::OpenMP_CXX` is linked and `MAGIC_GEO_HAS_OPENMP=1` is defined | `CMakeLists.txt:80`, `:188-191` |
| Without OpenMP | `ScopedThreadConfiguration` is a no-op; telemetry reports `openmp_enabled=false`, `openmp_max_threads=1` | `cpp/src/engine/core.cpp:220-222`, `cpp/src/opencl_compute.cpp:2037-2046` |

CPU parallel loops use `#pragma omp parallel for schedule(static)` where output could otherwise depend on iteration ownership — for example the non-accelerated plate-assignment loop and the boundary-field commit loop (`cpp/src/engine/tectonics.cpp:67`, `:184`). Each iteration writes only its own destination slot, so the static schedule plus per-cell independence is what makes thread count irrelevant to results. The audit records CPU physical payloads matching across explicit 1-thread, explicit 4-thread and automatic-thread runs (`docs/gpu_simulation_audit.md:494`).

Threads and the accelerator backend are orthogonal: OpenMP governs the CPU reference loops (including any loop the accelerator did not take), while `compute.backend` governs whether the four kernel families are offloaded.

---

## Worked examples

### Inspect the capability probe

```bash
magic-geo backend
```

This calls `magic_geo.native.backend_info()` → `magic_geo_backend_info_json` → `compute_backend_info_json()` with no live session, so it reports `requested_backend: "cpu"`, `selected_backend: "cpu"`, `backend_selection_reason: "capability-only probe; no generation is active"`, and complete CUDA/OpenCL capability blocks.

### Pin a backend in configuration

```yaml
compute:
  backend: cuda        # auto | cpu | opencl | cuda
  threads: 16          # 0 = leave host OpenMP policy untouched
  opencl_prefer_gpu: true
```

```bash
magic-geo generate --config configs/earthlike_seed.yaml --output runs/world.json
```

An explicit `cuda` or `opencl` request that cannot be satisfied aborts with a `RuntimeError` carrying the `explicit … backend requested but initialization failed: …` text; it never silently produces a CPU world.

### Read the backend block out of a generated world

```bash
python - <<'PY'
import json, pathlib
world = json.loads(pathlib.Path("runs/world.json").read_text())
backend = world["backend"]
for key in (
    "requested_backend", "selected_backend", "active_backend",
    "initial_selected_backend", "backend_selection_reason",
    "automatic_planning_cell_count", "accelerator_kernel_dispatch_count",
    "backend_fallback_used", "backend_fallback_stage", "backend_fallback_reason",
    "crust_transport_execution_backend",
    "crust_transport_accelerator_dispatch_count",
    "cpu_conservative_crust_overlap_transition_count",
    "crust_overlap_continuous_shadow_validation_status",
    "crust_overlap_continuous_shadow_maximum_error_to_bound_ratio",
):
    print(f"{key} = {backend[key]!r}")
PY
```

### Verify CPU / accelerator physical parity yourself

On the audited RTX 5090 the complete payload was equal after removing only the `backend` object. Reproducing that on your own device is worth doing, but a pass is host-specific evidence and a failure is not automatically a bug — the supported contract is identical discrete topology/IDs/order plus numerically equal physical fields under tolerances, not portable bitwise equality:

```bash
python - <<'PY'
from copy import deepcopy
from pathlib import Path

from magic_geo.config import load_config
from magic_geo.native import generate_world

base = load_config(Path("configs/earthlike_seed.yaml")).model_dump(mode="python")

for cells, erosion in ((128, 0), (512, 2), (4096, 6)):
    cpu_config = deepcopy(base)
    cpu_config["mesh"]["cell_count"] = cells
    cpu_config["erosion"]["iterations"] = erosion
    cpu_config["compute"]["backend"] = "cpu"

    accel_config = deepcopy(cpu_config)
    accel_config["compute"]["backend"] = "cuda"   # or "opencl"

    cpu = generate_world(cpu_config)
    accel = generate_world(accel_config)
    assert accel["backend"]["crust_transport_execution_backend"] == "cpu"
    assert accel["backend"]["crust_transport_accelerator_dispatch_count"] == 0
    assert accel["backend"]["cpu_conservative_crust_overlap_transition_count"] == erosion
    cpu["backend"] = {}
    accel["backend"] = {}
    assert cpu == accel, (cells, erosion)
    print("exact physical parity", cells, erosion)
PY
```

Adapted from `docs/gpu_simulation_audit.md:570-607`, which uses `opencl`.

### Benchmark and assert automatic selection

```bash
PYTHONPATH=src python scripts/benchmark_compute_backends.py \
  --config configs/earthlike_seed.yaml \
  --cells 4096,16384,32768 \
  --backends cpu,opencl,cuda \
  --repeats 3 --warmups 1 \
  --threads 16 --erosion-iterations 6 --no-include-cells \
  --require-all \
  --output runs/backend-benchmark.json
```

```bash
PYTHONPATH=src python scripts/benchmark_compute_backends.py \
  --cells 8191,8192 --backends auto \
  --threads 16 --erosion-iterations 6 --no-include-cells \
  --repeats 1 --warmups 0 \
  --expect-auto '8191=cpu,8192=cuda' --require-all \
  --output runs/auto-boundary.json
```

Argument definitions are at `scripts/benchmark_compute_backends.py:264-315`; `--expect-auto` adds `auto` to the measured set and rejects cell counts absent from `--cells`. Capability probing happens **after** the timed generations so it cannot pre-warm an accelerator runtime (`docs/cuda_rtx5090_optimization.md:239`).

### Worked dispatch-count arithmetic

For a Fibonacci world with `erosion.iterations = 6` and `tectonics.boundary_smoothing_steps = 5` on an active accelerator, the counters follow directly from the call sites:

| Source | Operations | Steps each | Dispatches |
| --- | ---: | ---: | ---: |
| `assign_plates` — pipeline stage (`cpp/src/engine/pipeline.cpp:30`) + 6 erosion iterations (`cpp/src/engine/tectonics.cpp:1135`) | 7 | 1 | 7 |
| Fused three-field boundary smoothing — same 7 `classify_boundaries` calls (`cpp/src/engine/tectonics.cpp:163`) | 7 | 5 | 35 |
| Scalar smoothing — crust coherence (1 step) + secondary relief (4 steps), once in `derive_crust_and_topography` (`cpp/src/engine/tectonics.cpp:307-318`) | 2 | 1 and 4 | 5 |
| Crust-overlap continuous shadow — once per erosion iteration (`cpp/src/engine/tectonics.cpp:1151`) | 6 | 1 | 6 |
| **Total `accelerator_kernel_dispatch_count`** | | | **53** |

The same total, 53, was recorded for the erosion-6 workload in both audits (`docs/gpu_simulation_audit.md:167-171`, `docs/cuda_rtx5090_optimization.md:255-258`), but that measurement predates the shadow: the six per-iteration dispatches it counted were the since-removed nearest-source remap kernel, not the shadow reduction. The arithmetic above is derived from the current call sites, not measured on a device. `cpu_conservative_crust_overlap_transition_count` would be 6, and `crust_overlap_continuous_shadow_validated_transition_count` 6 with status `passed` if every reconciliation succeeded.

---

## What is and is not verified, on which hardware

### Verified

| Claim | Hardware / context | Source |
| --- | --- | --- |
| CPU/OpenCL exact non-telemetry payload parity at 128/e0, 512/e2, 4,096/e6, 16,384/e6, 32,768/e6 | One RTX 5090, NVIDIA driver 595.71.05, GCC 15.2, Release + `-ffp-contract=off` | `docs/gpu_simulation_audit.md:340-344`, host at `:60-75` |
| CPU/CUDA exact non-telemetry payload digests at 4,096 / 8,192 / 16,384 / 32,768 cells, erosion 6 | Same RTX 5090 | `docs/cuda_rtx5090_optimization.md:204-212` |
| Automatic boundary: CPU with no probe at 8,191 actual cells, CUDA with 53 dispatches at 8,192 | Same RTX 5090 | `docs/cuda_rtx5090_optimization.md:254-258` |
| Automatic boundary: CPU/no-probe at 32,767, OpenCL at 32,768 | Same host, historical OpenCL tranche | `docs/gpu_simulation_audit.md:493` |
| Compute Sanitizer memcheck/initcheck/synccheck/racecheck: zero errors and zero hazards | `magic_geo_cuda_compute_test` and `magic_geo_native_api_test` on the RTX 5090 | `docs/cuda_rtx5090_optimization.md:278-303` |
| Native `sm_120` cubin plus retained `compute_120` PTX in the audited artifact; SASS for `sm_75/80/86/89/90/120` plus `compute_75`/`compute_120` PTX in the default multi-arch build | `cuobjdump --list-elf` / `--list-ptx` | `docs/cuda_rtx5090_optimization.md:180-186` |
| Static-runtime artifact loads on a driverless, GPU-masked host and honestly reports `cuda_compiled=true`, `cuda_available=false` | Sandboxed workspace | `docs/cuda_rtx5090_optimization.md:308-311` |
| Explicit-OpenCL 80-world RSS plateau on the tested success path | Same host, 128 cells / erosion 2 | `docs/gpu_simulation_audit.md:185-193` |
| Shadow validator arithmetic itself (bounds, rejections, replay) without any device | CTest `magic_geo_crust_overlap_shadow`, CPU only | `CMakeLists.txt:298-318` |

### Not verified

| Gap | Statement |
| --- | --- |
| Device-run evidence for the crust-overlap shadow kernel | "This host has no device-run evidence for the shadow" (`README.md:314-315`) |
| Cross-vendor OpenCL parity (AMD, Intel, CPU ICDs) | Listed as an important gap; the test matrix asks for NVIDIA/AMD/Intel/CPU coverage but only NVIDIA evidence exists (`docs/gpu_simulation_audit.md:480`, `:499-505`) |
| Fault-injected OpenCL command failures and release-count verification on failed commands | Explicitly open (`docs/gpu_simulation_audit.md:499-501`, `:629-631`) |
| Per-event OpenCL kernel timing | The profiling queue is enabled but per-event timings are not collected (`docs/gpu_simulation_audit.md:453-454`) |
| Automated performance regression thresholds | Explicitly open (`docs/gpu_simulation_audit.md:501`) |
| Threshold portability | "The single device-independent automatic threshold is a portability heuristic, not a guarantee on slower or integrated GPUs" (`docs/gpu_simulation_audit.md:502-503`) |
| Statistical stability of the timings | Two to five samples per case; the benchmark's nearest-rank p95 is the observed maximum, not a tail-latency estimate (`docs/cuda_rtx5090_optimization.md:216-221`) |
| Crossover calibration for the current v3 transport path | "authoritative GPU transport, complete-ledger parity, and new crossover calibration remain pending" (`docs/cuda_rtx5090_optimization.md:12-13`) |
| Automatic initialization/runtime fallback and device kernels in ordinary CI | The sandboxed CTest run exercises only *explicit* OpenCL initialization failure (`docs/gpu_simulation_audit.md:503-505`) |
| LeakSanitizer coverage | Disabled because the ptrace environment made it unusable; documented as an environment limitation, not a claim that leak testing is unnecessary (`docs/gpu_simulation_audit.md:495-496`, `:627-631`) |
| Whether GPU offload is worth it end to end | At 4,096 cells / erosion 6 OpenCL was ~12% *slower* than CPU, and even a free native path caps the full API at roughly 1.68x (`docs/gpu_simulation_audit.md:36-40`, `:173-177`) |

---

## Limitations and unresolved claims

- **Accelerator scope is narrow and says so.** `backend_scope = accelerated_native_kernels_not_end_to_end_pipeline`. Three production kernel families (plate assignment, scalar smoothing, fused three-field smoothing) plus one discarded-output shadow are the entire accelerated surface. Everything else — mesh construction, RNG, climate, hydrology, erosion, sediment, cryosphere, society, serialization, and the whole Python enrichment pipeline — is CPU.
- **The shadow kernel's result is thrown away by design and must not be read as accelerated transport.** `crust_overlap_continuous_shadow_only = true`, `..._authoritative = false`, `..._result_used_for_state = false`.
- **Accelerator parity for crust overlap is explicitly false**, in five separate serialized booleans: geometry, coverage/membership, categorical, complete, and state authority. A future GPU transport port must reproduce source-area closure, unnormalized destination gaps and multiple coverage, the global area-by-multiplicity histogram, arrangement line/fragment telemetry, all three transported extensive inventories and the aggregate process delta, canonical ledger ordering, and fallback telemetry — "parity of a single dominant source ID is insufficient" (`docs/cuda_rtx5090_optimization.md:330-334`).
- **The 8,192-cell CUDA threshold is host-specific engineering evidence from one RTX 5090**, not a universal NVIDIA performance claim (`docs/cuda_rtx5090_optimization.md:3-5`). The 32,768-cell OpenCL and uncalibrated-CUDA thresholds are conservative policy, not measurements on your device. Re-benchmark before changing them.
- **All published crossover timings predate `forward_spherical_control_volume_overlap_v1`** and measured the since-removed nearest-source remap kernel. They are retained as a pre-v3 baseline, not as current guidance (`docs/cuda_rtx5090_optimization.md:191-193`).
- **Exact cross-backend equality was observed on one NVIDIA device.** The supported contract is identical discrete topology/IDs/order plus numerically equal physical fields under explicit tolerances and invariant/replay validation — not a portable bitwise promise across OpenCL vendors and compilers (`docs/gpu_simulation_audit.md:358-367`).
- **OpenCL is Linux-only in this implementation.** `dlopen`-based discovery is guarded by `#if defined(__linux__)`; every other platform reports `OpenCL dynamic loading is only implemented on Linux`.
- **`cuda_auto_min_cell_count` can be misread.** It defaults to `8192` and is only raised to `32768` after an *available* non-`sm_120` device is observed, so a CPU-only run reports `8192` even though nothing was probed. Interpret it together with `cuda_probe_performed` and `cuda_capability_status`.
- **`magic-geo backend` deliberately probes both runtimes** even though it reports `requested_backend: "cpu"`. That is the capability query, not a generation session; do not use it as evidence about what a `cpu` generation did.
- **Accelerating a stage does not make its physics more true.** The project's unresolved physical claims are unaffected by backend choice: subduction polarity remains explicitly `unknown`, mass provenance and dry-rock accounting remain non-authoritative counter-models with `physical_basis_resolved = false`, and physical time / process-rate calibration and whole-coupling timestep convergence remain false. Backend telemetry describes *execution*, never model validity.
- **Session caching is per generation, not per process.** Context, queue, program, kernels, and buffers are rebuilt for every world; the mesh cache key is `cells.data()` plus size rather than an explicit mesh fingerprint. A process-level device/program cache and a versioned mesh identity are recorded as future work (`docs/gpu_simulation_audit.md:443-448`).

---

## See also

- [Native Engine (C++ Core)](./08-native-engine.md) — pipeline ordering, translation units, the C ABI, and the engine invariants that backend truthfulness is one of
- [Installation and Build](./02-installation-and-build.md) — CMake options, OpenMP/CUDA discovery, and the staged shared library
- [Configuration Reference](./05-configuration-reference.md) — the full `compute` section and every other config block
- [CLI Reference](./06-cli-reference.md) — `magic-geo backend`, `magic-geo generate`
- [Python API](./07-python-api.md) — `magic_geo.api.backend_info`, `magic_geo.native.generate_world`
- [World Document Schema](./10-world-schema.md) — where the `backend` object sits in the serialized world
- [Crust Transport and Forward Overlap](./features/crust-transport-and-overlap.md) — the CPU-authoritative overlap plan the shadow kernel replays
- [Crust Material Shadow and Dry-Rock Reservoirs](./features/crust-material-and-reservoirs.md) — the other non-authoritative shadow/counter-model pair
- [Tectonics and Plates](./features/tectonics-and-plates.md) — plate assignment and boundary smoothing, the two accelerated production stages
- [Validation](./12-validation.md) — the validators that assert backend telemetry invariants
- [Testing and Quality Gates](./18-testing.md) — CTest targets including `magic_geo_crust_overlap_shadow` and `magic_geo_cuda_compute`
- [Docker Deployment](./19-docker-deployment.md) — `MAGIC_GEO_ENABLE_CUDA` as a build arg and the CPU/stub default image
- [Troubleshooting and FAQ](./22-troubleshooting.md) — what to do when an explicit backend refuses to initialize
