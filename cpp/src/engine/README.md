# Native engine architecture

The native core is organized around one behavior-preserving pipeline and a
separate serialization boundary. `cpp/src/engine.cpp` is the public C++ facade;
the C ABI remains in `cpp/src/c_api.cpp`.

## Data flow

```text
public generate_world_json(params[, compute_options])
  -> validate options/params -> scoped thread policy -> per-generation ComputeSession
  -> simulate_world
       mesh -> tectonics -> ocean/climate/hydrology
       -> erosion and earth-system feedback
       -> environment and water features
       -> settlements/civilization/history
  -> serialize_world
       summary + entity serializers + process-ledger serializers
```

`world.hpp` groups the result into `EarthSystemState`, `NaturalArtifacts`, and
`SocietyArtifacts`. This is the handoff between computation and output. Domain
stages must not depend on JSON serializers.

## Source responsibilities

- `core.cpp`: math, hashing, JSON primitives, parameter checks, and scoped thread policy.
- `mesh.cpp`: Fibonacci and geodesic mesh construction.
- `tectonics.cpp`: plates, crust, topography, and plate motion.
- `ocean.cpp`: volume-constrained sea level and marine connectivity.
- `climate.cpp`: circulation, currents, moisture transport, and climate fields.
- `hydrology.cpp`: water budget, priority flood, drainage, and depression policy.
- `earth_system.cpp`: sediment transports, feedback summaries, and erosion-stage coordination.
- `environment.cpp`: cryosphere, soils, biomes, landforms, coasts, basins, and ice sheets.
- `water_features.cpp`: lakes, watersheds, and boundary-ring geometry.
- `settlements.cpp`: settlement selection and routes.
- `civilization.cpp`: regions, borders, trade, cultures, languages, and sites.
- `history.cpp`: history, population, conflict, dynasties, snapshots, and calibration checks.
- `pipeline.cpp`: the only complete simulation-stage ordering.
- `opencl_compute.cpp`: dynamic OpenCL capability discovery, per-generation
  backend selection/resources/telemetry, and FP64 plate-assignment,
  fixed-order scalar/fused-three-field neighbor-smoothing, and crust-remap
  kernels. CPU execution remains the reference path; explicit OpenCL failures
  are fatal and only `auto` may fall back.
- `summary.cpp`, `entity_serialization.cpp`, and `process_serialization.cpp`: read-only JSON fragments.
- `world_serialization.cpp`: top-level schema ordering and assembly.

Shared records are private to the native target under `types/`. Constants and
schema-name tables live separately from those records. `internal.hpp` is the
private cross-translation-unit interface; none of its symbols are exported from
the shared library.

## Invariants

- Preserve pipeline order: many stages deliberately enrich the shared `Cell`
  state, and later stages consume those fields.
- Preserve RNG consumption, OpenMP schedules, floating-point expression order,
  serializer key order, and precision unless a schema/behavior change is intended.
- Keep the original `Params` and v1 `CConfig` field order, types, and 64-bit
  sizes stable. The legacy C++ overload and v1 C entry point always use CPU.
  New compute controls belong to `ComputeOptions`, the nested `CConfigV2`
  extension, and `magic_geo_generate_json_v2`; Python mirrors both C layouts
  via `ctypes`.
- Keep all declared legacy public symbols visible and all `magic_geo::detail`
  symbols hidden.
- Preserve backend truthfulness: `cpu` must not initialize or probe OpenCL,
  below-threshold `auto` CPU selection is not a fallback, explicit `opencl`
  must never silently fall back, and `auto` must never select a CPU OpenCL
  device. Qualifying FP64 devices must report denorm, INF/NAN, and
  round-to-nearest support. Serialized telemetry must identify actual dispatch
  counts, work sizes, transfer bytes, device capabilities, and any automatic
  fallback reason.
- Explicit OpenMP thread counts are generation-scoped and restore the calling
  thread's prior ICV on every exit; `threads=0` leaves host policy untouched.
- New domain stages belong before `serialize_world`; serializers must be
  read-only over `GeneratedWorld`.

`cpp/tests/native_api_test.cpp` protects the public boundary and concurrent
session behavior. `legacy_v1_client_test.cpp` compiles against a frozen layout
without including the current header. The Python suite provides the end-to-end
physics, replay, schema, and mutation-rejection gates.
