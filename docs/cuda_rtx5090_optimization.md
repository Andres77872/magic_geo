# Native CUDA support for NVIDIA Blackwell / RTX 5090

This document records the CUDA implementation, RTX 5090 calibration, and
validation evidence collected on 2026-07-10. The thresholds and timings are
host-specific engineering evidence, not universal NVIDIA performance claims.

> **Current crust-transport boundary:** the calibration below predates
> `forward_spherical_control_volume_overlap_v1`. Production v3 crust transport
> now runs authoritatively on CPU for `cpu`, `opencl`, and `cuda` backends. The
> CUDA nearest-source kernel measured below has since been removed; no current
> generation or low-level API exposes it. None of the historical remap speedups
> below measures the overlap path; GPU implementation, complete-ledger parity,
> telemetry, fallback behavior, and new crossover calibration remain pending.

## Audited target

The development host contains one NVIDIA GeForce RTX 5090 (GB202, PCI
`0000:01:00.0`, UUID `GPU-b5eba8af-1392-0ca9-bcb6-962e4338f350`) with compute
capability 12.0. NVIDIA's `nvidia-smi` interface reported 32,607 MiB, while
the CUDA runtime reported 33,667,612,672 bytes, or approximately 32,108 MiB,
of total device memory. Both raw values are retained because the interfaces
and driver accounting differ; neither was substituted for the other.

The tested driver is 595.71.05. Runtime telemetry reported CUDA driver API
13.2 (`13020`), CUDA runtime 13.1 (`13010`), 170 SMs, 32-thread warps, 1,536
threads per SM, a 96 MiB L2 cache, and a 512-bit memory bus. NVIDIA's
[compute-capability table](https://developer.nvidia.com/cuda/gpus) identifies
the RTX 5090 as compute capability 12.0, and the
[Blackwell tuning guide](https://docs.nvidia.com/cuda/blackwell-tuning-guide/index.html)
documents the architecture constraints used here.

[CUDA 12.8 was the first toolkit release with Blackwell `sm_120` compiler
support](https://docs.nvidia.com/cuda/archive/12.8.0/cuda-toolkit-release-notes/index.html).
The audited build uses CUDA 13.1 and emits both a native `sm_120` cubin and
`compute_120` PTX. The native image avoids first-use JIT compilation on this
GPU; PTX retains a forward-compatible path. `sm_120a` is intentionally not
used because these graph kernels do not require architecture-specific
features that would sacrifice forward compatibility.

## Build and runtime contract

CUDA is optional and does not weaken the dependency-free CPU path:

- `MAGIC_GEO_ENABLE_CUDA=ON` is the default, but CMake enables the CUDA
  translation unit only when it finds NVIDIA `nvcc` 12.8+ and the matching
  `CUDAToolkit` runtime development files.
- `MAGIC_GEO_ENABLE_CUDA=OFF`, a missing `nvcc`/`CUDAToolkit`, or an older or
  unsupported compiler builds `cuda_compute_stub.cpp`. CPU and OpenCL remain
  loadable; an explicit `compute.backend: cuda` request fails with an
  actionable error.
- The distributable `MAGIC_GEO_CUDA_ARCHITECTURES` default is
  `75-real;75-virtual;80-real;86-real;89-real;90-real;120-real;120-virtual`.
  It provides SASS for `sm_75`, `sm_80`, `sm_86`, `sm_89`, `sm_90`, and
  `sm_120`, plus forward PTX at the 7.5 and 12.0 baselines.
- The RTX 5090 audit overrides that broad default with
  `120-real;120-virtual`. This makes the audited artifact smaller and proves
  native Blackwell code generation; it is not the project-wide default.
- CUDA-enabled targets set `CUDA_RUNTIME_LIBRARY=Static`. The audited shared
  library has no `libcudart.so` (or `libcuda.so`) dynamic-loader dependency,
  so its CPU/OpenCL paths can load without a separately installed CUDA
  runtime. CUDA execution still requires a compatible NVIDIA kernel driver;
  static `cudart` does not bundle the driver.
- The original 304-byte v1 C configuration and 312-byte v2 extension are
  unchanged. Backend ID 3 fits the existing `compute_backend` field, so this
  addition does not change either ABI layout. The legacy one-argument C++ API
  and v1 C API remain CPU-only.

Reproduce the audited Blackwell build while keeping its artifact separate from
the package-tree library:

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

Omit the architecture override for the portable project default. A normal
CPU-only configure needs no CUDA arguments and automatically builds the stub
when `nvcc` or `CUDAToolkit` is absent.

The CUDA translation unit is compiled without fast math, FMA contraction, or
flush-to-zero behavior. CPU code retains `-ffp-contract=off`; CUDA uses
`--fmad=false --ftz=false --prec-div=true --prec-sqrt=true`. NVIDIA's
[`nvcc` documentation](https://docs.nvidia.com/cuda/cuda-compiler-driver-nvcc/)
describes those precision controls and the different behavior implied by
`--use_fast_math`.

## Selection policy and failure behavior

`compute.backend` accepts `auto`, `cpu`, `opencl`, and `cuda`. Automatic
planning is deferred until an operation sees the **actual generated mesh
size**, rather than the requested size. This distinction matters for mesh
backends such as geodesic subdivision, whose realizable cell count can differ
from the request.

The calibrated automatic thresholds are:

| Candidate | Minimum actual cells | Basis |
| --- | ---: | --- |
| Native CUDA on an `sm_120` device | 8,192 | Measured crossover on this RTX 5090 |
| CUDA on a non-`sm_120` device | 32,768 | Conservative, uncalibrated policy |
| Qualifying non-CPU OpenCL device | 32,768 | Existing OpenCL calibration |

Below 8,192 actual cells, `auto` selects CPU without probing CUDA or OpenCL. At
8,192 or more it can probe CUDA; an `sm_120` device is selected immediately,
whereas an available non-`sm_120` device remains on CPU until 32,768. At
32,768 or more, the automatic chain is usable CUDA, then a qualifying non-CPU
OpenCL device, then CPU. Thus an unavailable CUDA runtime does not prevent the
OpenCL fallback at its own threshold. This chain describes automatic
selection only:

- explicit `cpu` probes neither accelerator runtime;
- explicit `cuda` initializes CUDA and never silently falls back;
- explicit `opencl` retains the existing qualifying IEEE-FP64 device policy
  and never silently falls back;
- an automatic failure after a successful accelerator dispatch reports the
  active backend as `hybrid`, releases the failed device resources, and
  reruns that operation on the unchanged CPU reference path.

Capability and per-generation telemetry report compilation/runtime status,
NVIDIA identity, UUID/PCI ID, compute capability, native binary/PTX versions,
memory/cache/shared-memory/register limits, launch geometry, dispatch counts,
host/device bytes, current/peak allocations, mesh uploads, CUDA event timings,
actual-mesh planning count and thresholds, selection reasons, and fallback
stage/reason.

## Kernel design and compiled-resource evidence

The measured first CUDA tranche accelerated four deterministic operation
families as the established OpenCL path while retaining ordered host inputs
and complete host results:

1. Plate assignment scans centers in ascending plate order and uses strict
   `>` comparison so an exact score tie keeps the earliest plate.
2. Scalar neighbor smoothing keeps CSR neighbor order, uses device ping-pong
   buffers for all configured steps, and transfers only the initial and final
   fields.
3. Three-field smoothing fuses the three fields so each thread reads the CSR
   row once while preserving each field's original summation order.
4. The former crust-source primitive assigned one warp to each nearest-source
   query. Warp lanes scanned ascending candidate positions cooperatively and
   reduced `(score, position)` pairs so an exact tie selected the earliest
   candidate. This historical kernel has since been removed.

The session owns a nonblocking stream, reusable CUDA events and capacity
buffers, structure-of-arrays mesh coordinates, and CSR adjacency. Mesh uploads
happen once per generation. Coordinate SoA removes the unused fourth lane from
the OpenCL `double4` representation and coalesces warp coordinate loads.
Blocks use 256 threads (eight warps), consistent with the 32-thread warp and
1,536-thread-per-SM limits reported by the device. The implementation does not
use Tensor Cores or reduced precision; it preserves ordered FP64 model results.

For compute capability 12.0, NVIDIA documents a 128 KiB **unified L1/shared
memory subsystem**, not 128 KiB of wholly programmer-managed shared memory.
On this device the CUDA runtime reported 102,400 bytes (100 KiB) of shared
memory capacity per SM and a 99 KiB opt-in maximum per block. The implementation
currently needs no dynamic shared memory. The
[compute-capability limits](https://docs.nvidia.com/cuda/cuda-programming-guide/05-appendices/compute-capabilities.html)
and [CUDA best-practices guide](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html)
support the launch-limit, transfer-minimization, and coalescing choices.

`cuobjdump --dump-resource-usage` on the final `sm_120` artifact reports:

| Kernel | Registers/thread | Shared | Local | Stack |
| --- | ---: | ---: | ---: | ---: |
| Plate assignment | 37 | 0 | 0 | 0 |
| Scalar smoothing | 40 | 0 | 0 | 0 |
| Fused three-field smoothing | 40 | 0 | 0 | 0 |
| Historical crust-source primitive | 40 | 0 | 0 | 0 |

`cuobjdump --list-elf` identifies `cuda_compute.sm_120.cubin`, and
`--list-ptx` identifies `cuda_compute.sm_120.ptx`. This is direct artifact
evidence that the audited build contains native `sm_120` code and retained PTX,
not merely a build-setting assertion. Inspection of the separate default
multi-architecture build also found SASS for `sm_75`, `sm_80`, `sm_86`,
`sm_89`, `sm_90`, and `sm_120`, plus `compute_75` and `compute_120` PTX, matching
the distributable CMake policy.

## Measured parity and performance

The measurements in this section are retained as the pre-v3 accelerator
baseline. They cover the former nearest-source production path and must be
rerun before assigning a crossover threshold to spherical overlap transport.

The reusable benchmark calls the native ctypes boundary directly. Its timer
starts before `generate_world(config)`, so it covers construction of the ctypes
native configuration, library loading/call overhead, native generation and
native JSON serialization, the C-pointer-to-bytes transfer, UTF-8 decode, and
Python `json.loads`. It excludes the caller's configuration deepcopy and the
later Python world-enrichment pipeline. The cases below use the Earth-like
seed, Fibonacci mesh, 16 CPU threads, six erosion iterations, compact output
with final cell records disabled, warm runs, and explicit backends on the
audited RTX 5090:

| Actual cells | CPU median (s) | OpenCL median (s) | CUDA median (s) | CUDA speedup over CPU | Complete non-telemetry payload |
| ---: | ---: | ---: | ---: | ---: | --- |
| 4,096 | 1.10336 | — | 1.11279 | 0.9915x | Exact |
| 8,192 | 2.13535 | — | 2.10252 | 1.0156x | Exact |
| 16,384 | 4.38823 | 4.32613 | 4.15470 | 1.0562x | Exact |
| 32,768 | 9.3938276 | 8.979922 | 8.841675 | 1.06245x | Exact |

“Exact” means the SHA-256 digest of the complete result after replacing only
backend telemetry matched the CPU result. The 4,096 case demonstrates why
automatic CUDA begins at 8,192 on this host: explicit CUDA remains available
for testing, but transfer/setup overhead made it slightly slower there.

These measurements used only two to five repeated samples per case. The
benchmark's nearest-rank p95 is consequently the observed maximum for these
small samples, not a stable tail-latency estimate. Medians are suitable for the
RTX 5090 crossover decision, but all figures should be rerun before changing a
threshold, treating them as a release budget, or extrapolating them to another
GPU, driver, toolkit, power state, mesh family, output mode, or workload.

Reproduce the explicit-backend comparison against the pinned build artifact:

```bash
MAGIC_GEO_NATIVE_LIBRARY="$PWD/build-cuda/lib/libmagic_geo_native.so" \
PYTHONPATH=src .venv/bin/python scripts/benchmark_compute_backends.py \
  --cells 4096,8192,16384,32768 \
  --backends cpu,opencl,cuda \
  --threads 16 --erosion-iterations 6 --no-include-cells \
  --repeats 5 --warmups 1 --require-all \
  --output "$PWD/build-cuda/rtx5090-explicit-backends.json"
```

The JSON report records the absolute native-library and config paths and their
SHA-256 digests, Git revision/dirty state, Python/platform identity, effective
configuration digests, requested and actual cell counts, per-repeat payload
digests, and complete backend telemetry. Capability probing happens after the
timed generations so it cannot pre-warm an accelerator runtime.

The automatic boundary has its own assertion so a timing run cannot silently
exercise the wrong backend:

```bash
MAGIC_GEO_NATIVE_LIBRARY="$PWD/build-cuda/lib/libmagic_geo_native.so" \
PYTHONPATH=src .venv/bin/python scripts/benchmark_compute_backends.py \
  --cells 8191,8192 --backends auto \
  --threads 16 --erosion-iterations 6 --no-include-cells \
  --repeats 1 --warmups 0 \
  --expect-auto '8191=cpu,8192=cuda' --require-all \
  --output "$PWD/build-cuda/rtx5090-auto-boundary.json"
```

The final hardened boundary run passed both assertions. At 8,191 actual cells,
`auto` selected CPU, skipped both CUDA and OpenCL probes, and recorded zero
accelerator dispatches. At 8,192 actual cells, it selected CUDA, recorded 53
CUDA kernel dispatches, and produced a complete non-telemetry payload exactly
equal to the CPU reference.

## Validation evidence

The default multi-architecture CUDA Release build passed all four CTest targets
on the RTX 5090, including the raw-kernel test, for the audited pre-v3 tree. The integrated native API test
exercised complete CPU/CUDA payload parity, odd-sized 129-cell legacy remapping,
repeated erosion dispatches, explicit failure behavior, telemetry, and
concurrent CPU/CUDA sessions. A CUDA-disabled/stub build separately passed its
three CPU/ABI tests.

The dedicated `magic_geo_cuda_compute_test` calls the raw CUDA session rather
than the world pipeline. It compares all four kernels with ordered CPU
references using 129- and 513-cell non-block multiples; covers an isolated CSR
row and a degree-65 row; exact plate and remap ties; an empty candidate plate;
zero-step, scalar, and fused multi-step smoothing; buffer growth/reuse; empty
remap output; invalid-input rejection and error recovery; dispatch counters;
the 256-thread launch policy; caller-device preservation; and invalid-device
ordinal handling. FP64 smoothing values are compared bit-for-bit.

On the final hardened `magic_geo_cuda_compute_test`, Compute Sanitizer reported
zero memcheck errors, zero initcheck errors, zero synccheck errors, and a
racecheck summary of zero hazards, errors, or warnings. Final hardened
`magic_geo_native_api_test` memcheck also reported zero errors. The integrated
test's initcheck, synccheck, and racecheck runs against the unchanged kernels
likewise reported zero errors or hazards before the final host-device-control
hardening. The exact validation commands are:

```bash
compute-sanitizer --tool memcheck --error-exitcode 99 \
  build-cuda/magic_geo_native_api_test
compute-sanitizer --tool initcheck --error-exitcode 99 \
  build-cuda/magic_geo_native_api_test
compute-sanitizer --tool racecheck --error-exitcode 99 \
  build-cuda/magic_geo_native_api_test
compute-sanitizer --tool synccheck --error-exitcode 99 \
  build-cuda/magic_geo_native_api_test
compute-sanitizer --tool memcheck --error-exitcode 99 \
  build-cuda/magic_geo_cuda_compute_test
compute-sanitizer --tool initcheck --error-exitcode 99 \
  build-cuda/magic_geo_cuda_compute_test
compute-sanitizer --tool racecheck --error-exitcode 99 \
  build-cuda/magic_geo_cuda_compute_test
compute-sanitizer --tool synccheck --error-exitcode 99 \
  build-cuda/magic_geo_cuda_compute_test
```

The normal workspace sandbox masks `/dev/nvidia*`; GPU execution, sanitizer
validation, and performance calibration must run in a device-enabled context.
A loader or driver visible without a usable device is reported as unavailable,
not mistaken for CUDA execution. The installed static-runtime artifact also
loaded successfully in the driverless, GPU-masked sandbox without a dynamic
`cudart`: telemetry correctly reported `cuda_compiled=true`,
`cuda_available=false`, and selected CPU for the tested generation.

## Profile-driven CPU optimization and remaining limits

Historical sampling showed that, after nearest-source crust remapping, repeated
climate humidity paths were the next native bottleneck. The CPU reference
replaces a heap-allocated
`std::set` per cell with a fixed 35-ID visited array and precomputes the strict
upwind neighbor/alignment for the six prevailing-wind regimes once per climate
recomputation. Complete physical payload hashes remain identical. Warm native
CPU time improved by 1.7% at 4,096 cells/erosion 6 with 16 threads, 2.2% at
16,384 cells/erosion 2 with 16 threads, and 7.5% at 4,096 cells/erosion 6 with
one thread.

The v3 overlap path adds CPU spherical candidate search, clipping, canonical
CSR construction, and destination coverage arrangements. The latter fails
closed above 16,384 local fragments. Legal 180°/step, 32-plate Fibonacci-512
and geodesic-642 stress cases pass, but they are not an exhaustive worst-case
complexity proof. This path must be profiled independently. A valid CUDA port
must reproduce source-area closure, unnormalized destination gaps and multiple
coverage, the global area-by-multiplicity histogram, arrangement line/fragment
telemetry, all three transported extensive inventories and the aggregate
process delta, canonical ledger ordering, and fallback telemetry; parity of a
single dominant source ID is insufficient.

Ordered Priority-Flood, sea-level union/find, flow accumulation, sediment
topology, RNG, and serialization remain on the CPU. Moving those stages with
atomics or unordered reductions would change the model, not merely accelerate
it. The full Python API also spends substantial time after the native/JSON
boundary, so the native speedups above should not be interpreted as equivalent
end-to-end API speedups. The historical
[GPU simulation audit](gpu_simulation_audit.md) retains the broader pipeline
profile, determinism contract, and structural optimization opportunities.
