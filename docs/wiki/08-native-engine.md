# Native Engine (C++ Core)

[Wiki home](./README.md) > Native Engine (C++ Core)

The whole world simulation — mesh, tectonics, crust transport, climate, hydrology, erosion, cryosphere, and every society layer — runs inside one C++20 shared library, `magic_geo_native`. Python never computes simulation state: it validates configuration, marshals it across a frozen C ABI, receives one canonical document, and enriches it. This page is the reference for the native side: the directory layout, every translation unit, the result-type and serialization boundary, the exact pipeline stage order, the complete C ABI including struct field offsets, the ctypes mirror, thread and visibility policy, the native test suite, and the rules for adding a stage.

## On this page

- [Why a native core exists](#why-a-native-core-exists)
- [Directory layout](#directory-layout)
- [Translation-unit reference](#translation-unit-reference)
- [Result-type architecture and the simulation/result/serialization boundary](#result-type-architecture-and-the-simulationresultserialization-boundary)
- [Pipeline stage order](#pipeline-stage-order)
- [Inside the maturation loop (`erode`)](#inside-the-maturation-loop-erode)
- [Inside `stabilize_numeric_depressions`](#inside-stabilize_numeric_depressions)
- [The public C++ facade](#the-public-c-facade)
- [The C ABI in full](#the-c-abi-in-full)
- [How Python mirrors the structs with ctypes](#how-python-mirrors-the-structs-with-ctypes)
- [Thread policy and the scoped OpenMP ICV restore](#thread-policy-and-the-scoped-openmp-icv-restore)
- [Symbol visibility](#symbol-visibility)
- [The native test suite](#the-native-test-suite)
- [Contributor guide: adding a new stage](#contributor-guide-adding-a-new-stage)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

## Why a native core exists

The native core owns everything that is *authoritative* about a world. Concretely:

| Concern | Owner | Where |
|---|---|---|
| Mesh construction, control volumes, neighbor graph | C++ | `cpp/src/engine/mesh.cpp` |
| Plate kinematics, crust state, forward-overlap transport | C++ | `cpp/src/engine/tectonics.cpp`, `cpp/src/engine/crust_transport.cpp` |
| Sea level, climate, hydrology, erosion, cryosphere, soils/biomes | C++ | `ocean.cpp`, `climate.cpp`, `hydrology.cpp`, `earth_system.cpp`, `environment.cpp` |
| Society/history/economy generators | C++ | `settlements.cpp`, `civilization.cpp`, `history.cpp` |
| The canonical world document (key order, precision) | C++ | `cpp/src/engine/world_serialization.cpp` |
| Config schema, validation, defaults | Python | `src/magic_geo/config.py` |
| FFI marshalling, schema gate, memory lifetime | Python | `src/magic_geo/native.py` |
| Post-hoc enrichment, geo-only stripping, CLI, rendering, validation suites | Python | `src/magic_geo/api.py` and siblings |

The C++ side declares its own contract at `cpp/src/engine/README.md:326` ("Invariants"): pipeline order, the sediment-interface authority boundary, the plate-boundary evidence boundary, RNG consumption / OpenMP schedules / floating-point expression order / serializer key order / precision, the frozen `CConfig`/`CConfigV2` layouts, symbol visibility, backend truthfulness, generation-scoped thread policy, and "new domain stages belong before `serialize_world`; serializers must be read-only over `GeneratedWorld`".

Python's boundary is deliberately narrow. `src/magic_geo/native.py` only ever calls the **v3** entry points; `magic_geo::detail` is never reachable; and the returned document is gated by `_require_current_world_schema` before any enricher touches it (`src/magic_geo/native.py:234`).

## Directory layout

```text
cpp/
  include/magic_geo/
    native.hpp                    # the ONLY public header: Params, ComputeOptions,
                                  # CConfig/V2/V3, C++ facade, extern "C" ABI
  src/
    engine.cpp                    # public C++ facade (5 generate_* functions)
    c_api.cpp                     # C ABI + config conversion + error envelopes
    opencl_compute.cpp/.hpp       # generation-scoped ComputeSession, backend telemetry
    cuda_compute.cu/.hpp          # native CUDA path (built only with CUDA 12.8+)
    cuda_compute_stub.cpp         # build-preserving stub without a CUDA toolchain
    crust_overlap_shadow.cpp/.hpp # discarded-output FP64 parity harness
    engine/
      README.md                   # module ownership, dependency flow, invariants
      internal.hpp                # private cross-TU interface (nothing exported)
      model.hpp                   # aggregates constants + schema names + types/
      constants.hpp               # physical/procedural constants, CrustProcessReason
      schema_names.hpp            # enum -> string name tables
      world.hpp                   # EarthSystemState / NaturalArtifacts /
                                  # SocietyArtifacts / GeneratedWorld
      messagepack.hpp             # sanitize_utf8 + json_to_messagepack
      types/
        core.hpp                  # Vec3, Plate, Cell
        earth_system.hpp          # process ledgers, transport plan, motion steps
        crust_reservoir.hpp       # dry-rock packet/transfer tables and caps
        world.hpp                 # natural + society entity records
      <28 domain and serializer translation units>
  tests/
    c_api_v1_layout.hpp           # frozen v1 layout, independent of native.hpp
    <13 test translation units>
CMakeLists.txt                    # single build for the library + CTest suite
src/magic_geo/                    # Python package; also the library staging dir
  libmagic_geo_native.so          # MAGIC_GEO_LIBRARY_OUTPUT_DIRECTORY default
```

`cpp/include/magic_geo/native.hpp` is the only header outside the target. Everything else — `internal.hpp`, `model.hpp`, `types/`, `constants.hpp`, `schema_names.hpp`, `world.hpp`, `messagepack.hpp` — is private to the native target and is compiled with `PRIVATE cpp/include` include scope (`CMakeLists.txt:131`).

## Translation-unit reference

The sources compiled into `magic_geo_native` are listed at `CMakeLists.txt:96-128` — 33 entries in any one configuration: `c_api.cpp`, `engine.cpp`, the 28 `engine/` translation units, `crust_overlap_shadow.cpp`, `opencl_compute.cpp`, and the single `${MAGIC_GEO_CUDA_SOURCE}` slot (line 126) that CMake resolves to either `cuda_compute.cu` or `cuda_compute_stub.cpp`. "Principal exported detail functions" means symbols with external linkage that other translation units call — those declared in `cpp/src/engine/internal.hpp`, `cpp/src/engine/world.hpp`, `cpp/src/engine/messagepack.hpp`, or forward-declared at `cpp/src/engine/world_serialization.cpp:6-21`. All of them live in `namespace magic_geo::detail` and are **hidden** in the shipped library. Line counts are `wc -l` of the file.

### `cpp/src/engine/` — domain stages

| TU | Responsibility | Principal exported `detail` functions | Lines |
|---|---|---|---|
| `core.cpp` | Vector math, spherical geometry, splitmix64 hashing, JSON scalar/key primitives, timestep scaling helpers, parameter and compute-option validation, scoped OpenMP thread policy | `add` `sub` `mul` `dot` `cross` `norm` `normalize` `rotate_about_axis` `angular_distance` `spherical_triangle_area_steradians`, `splitmix64` `hash01` `signed_noise`, `json_escape` `num` `comma` `add_raw` `add_str` `add_int` `add_u64` `add_double` `add_bool`, `mesh_backend_name` `cell_area_model_name`, `crust_age_ceiling_ma` `maturation_timestep_scale` `timestep_scaled_fraction`, four `climate_*_forcing/factor` helpers, `ScopedThreadConfiguration`, `validate_params`, `validate_compute_options` | 435 |
| `mesh.cpp` | Fibonacci-sphere and geodesic-icosahedron mesh construction, exact control-volume clipping, neighbor graph, area validation | `build_mesh` | 1054 |
| `tectonics.cpp` | Plate generation/assignment, boundary classification, initial crust and topography, plate rotation and the per-step crust evolution, plate-motion step records, plate summaries | `generate_plates` `choose_plate_seeds` `assign_plates` `classify_boundaries` `lithology_resistance` `derive_crust_and_topography` `is_oceanic_crust_state` `crust_equilibrium_elevation_m` `summarize_plate_motion_step` `advance_plate_motion_and_crust` `summarize_plates` | 1895 |
| `plate_boundary_segments.cpp` | One canonical record per cross-plate reciprocal control-volume segment: exact identity/geometry, direct unsmoothed Euler kinematics, same-step opening/remapped crust witnesses, candidate side pairs, explicit unknown physical polarity | `build_plate_boundary_segments` | 608 |
| `crust_transport.cpp` | CPU-authoritative exact spherical forward-overlap geometry, destination-major CSR, extensive-state remap, raw arrangement diagnostics, coalesced retained-area membership classes keyed by sorted contributing source IDs | `build_identity_crust_transport_plan` `build_forward_overlap_crust_transport_plan` | 1929 |
| `crust_overlap_candidate_fate.cpp` | Deterministic non-allocating crosswalk from multiplicity ≥ 2 membership classes to conservative boundary plate-pair consensus and endpoint-incidence evidence; emits candidate contributor-CSR roles or explicit unknown | `build_crust_overlap_candidate_fate_ledger` | 811 |
| `crust_material.cpp` | The non-authoritative persistent sparse dry-rock mass **shadow**: source-normalized packet allocation over raw overlap rows, final-edge remainder, canonical origin keys, ordered unresolved rule sources, proportional provenance-preserving sinks | `initialize_crust_material_shadow` `begin_crust_material_shadow_step` `apply_crust_material_shadow_transition` `finalize_crust_material_shadow_step` | 1308 |
| `crust_reservoir.cpp` | The non-authoritative finite three-reservoir dry-rock **counter-model**: ordered surface/upper-mantle proxy transfers, empty plate-owned slab tables, fail-closed packet/transfer caps | `initialize_crust_dry_rock_accounting` `advance_crust_dry_rock_accounting_step` | 1825 |
| `oceanic_age_depth.cpp` | Centralized continuity-adjusted **relative** oceanic basement-subsidence curve plus the finite/nonnegative age guard | `oceanic_age_depth_thermal_subsidence_m` | 51 |
| `initial_oceanic_age.cpp` | Deterministic multi-source ridge-graph travel-time field `multi_source_nominal_ridge_graph_travel_time_v1`: ridge seeding, one nominal half-rate, Dijkstra over the oceanic-like neighbor graph, reachable / ceiling-clamped / no-active-ridge-path statuses | `build_initial_oceanic_crust_age_field` | 327 |
| `sediment_partition.cpp` | Checked mutation primitives for the canonical bedrock-surface / mobile-sediment geometry and the cell-indexed alluvium-vs-bedrock source-partition audit | `initialize_sediment_interface` `shift_sediment_interface_datum` `apply_sediment_interface_material_change` `validate_sediment_interface` `maximum_sediment_interface_closure_residual_m` `validate_sediment_source_partition` | 380 |
| `ocean.cpp` | Volume-constrained sea-level solve via the datum-shift primitive, marine connectivity labelling, ocean distance field | `apply_sea_level` `label_marine_water_bodies` `ocean_distance` | 351 |
| `climate.cpp` | Circulation regimes, prevailing-wind upwind cache, ocean currents, moisture transport, temperature/precipitation/wind fields | `compute_climate` `wrap_angle` `local_relief` | 518 |
| `hydrology.cpp` | Water budget, priority-flood spill, basin IDs, surface conditioning, flow/rivers, depression policy, numeric-breach alternative, and the bounded stabilization loop | `hydrologic_lithology_permeability` `neighbor_distance_m` `is_geologic_depression` `stabilize_numeric_depressions` (TU-local: `compute_hydrologic_water_budget` `compute_priority_flood_spill` `compute_flow_and_rivers` `condition_hydrologic_surface` `assign_basin_ids` `derive_numeric_depression_breach_alternative` `apply_numeric_depression_correction`) | 1308 |
| `earth_system.cpp` | The maturation loop, timestep-scaled hillslope and fluvial transports, feedback references and summaries, source-partition audits | `capture_feedback_reference` `summarize_feedback_step` `erode` (TU-local: `transport_hillslope_sediment` `route_fluvial_sediment`) | 1151 |
| `environment.cpp` | Cryosphere state, terminal glacial transport, soils/biomes/resources, landforms, coastal features, sedimentary basins, stratigraphic columns, ice sheets | `has_ocean_neighbor` `has_glacier_neighbor` `derive_cryosphere_state` `transport_glacial_sediment` `derive_soils_biomes_resources` `derive_landforms` `generate_coastal_features` `generate_sedimentary_basins` `generate_stratigraphic_columns` `generate_ice_sheets` | 1158 |
| `water_features.cpp` | Lake basins with overflow staging, watersheds, boundary-ring geometry and projected-area helpers | `generate_lake_basins` `generate_watersheds` `watershed_boundary_ring` `latlon_to_vec` `ring_perimeter_km` `ring_projected_area_km2` | 373 |
| `settlements.cpp` | Settlement site selection and inter-settlement routes | `generate_settlements` `generate_routes` `route_barrier_cost` | 152 |
| `civilization.cpp` | Political regions, border segments, trade flows, cultures/languages/sacred areas/ruins | `generate_political_regions` `generate_border_segments` `generate_trade_flows` `generate_cultural_layers` | 1010 |
| `history.cpp` | Historical eras and events, population regions, conflicts, dynasties, territorial snapshots, calibration checks | `generate_historical_layers` `generate_population_regions` `generate_conflicts` `generate_dynasties` `generate_territorial_snapshots` `generate_calibration_checks` | 1090 |
| `pipeline.cpp` | **The only complete simulation-stage ordering** | `simulate_world_impl` `simulate_world` `simulate_geo_world` | 276 |

### `cpp/src/engine/` — serialization and transport

| TU | Responsibility | Principal exported `detail` functions | Lines |
|---|---|---|---|
| `world_serialization.cpp` | Top-level schema ordering and assembly; emits `schema_version: 2`, `planet_parameters`, `summary`, and `backend` | `serialize_world`, `planet_parameters_json` | 296 |
| `summary.cpp` | The `summary` object and its crust-material-shadow extension | `summary_json`, `summary_with_crust_material_shadow_json` | 2108 |
| `entity_serialization.cpp` | Read-only JSON fragments for cells, plates, and every natural/society entity array | `plates_json` `cells_json` `settlements_json` `routes_json` `trade_flows_json` `watersheds_json` `lake_basins_json` `coastal_features_json` `sedimentary_basins_json` `stratigraphic_columns_json` `ice_sheets_json` `political_regions_json` `cultures_json` `language_regions_json` `sacred_areas_json` `ruins_json` `historical_eras_json` `historical_events_json` `population_regions_json` `conflicts_json` `dynasties_json` `snapshot_regions_json` `territorial_snapshots_json`, plus `int_array_json` `double_array_json` `vec3_json` `latlon_ring_json` | 959 |
| `process_serialization.cpp` | Read-only JSON for every model contract and process ledger, plus `borders_json` and `calibration_checks_json` | `climate_model_json` `hydrologic_water_budget_model_json` `hydrologic_water_budget_history_json` `numeric_depression_correction_history_json` `glacial_/hillslope_/fluvial_*_model_json` and `*_history_json` `sediment_interface_model_json` `sediment_inventory_model_json` `simulation_clock_json` `earth_system_feedback_history_json` `initial_oceanic_crust_age_model_json` `initial_oceanic_crust_age_ledger_json` `plate_kinematic_model_json` `plate_boundary_segment_model_json` `crust_overlap_candidate_fate_model_json` `oceanic_age_depth_model_json` `sea_level_model_json` `plate_motion_history_json` `crust_material_shadow_model_json` `crust_material_shadow_history_json` `calibration_checks_json` `borders_json` | 4460 |
| `crust_reservoir_serialization.cpp` | Read-only JSON for the three-reservoir accounting model/history and its summary extension, preserving the explicit false-authority flags | `crust_dry_rock_accounting_model_json` `crust_dry_rock_accounting_history_json` `summary_with_crust_dry_rock_accounting_json` | 493 |
| `numeric_serialization.cpp` | `std::defaultfloat` + `max_digits10` serialization for replay-critical numeric state | `roundtrip_num` `roundtrip_double_array_json` | 30 |
| `messagepack.cpp` | Strict, bounded-depth (`MAX_JSON_NESTING_DEPTH = 256`, `messagepack.cpp:18`) canonical-JSON → standard MessagePack transcoding; UTF-8 sanitizer for FFI diagnostics | `json_to_messagepack` `sanitize_utf8` | 595 |

`numeric_serialization.cpp` is compiled into the library (`CMakeLists.txt:113`) but is **not** listed in the `cpp/src/engine/README.md` responsibility table — a documentation gap, not a build gap.

### `cpp/src/` — facade, ABI, and compute

| TU | Responsibility | Principal exported functions | Lines |
|---|---|---|---|
| `engine.cpp` | Public C++ facade; identical prologue for all four backend-aware entry points | `magic_geo::generate_world_json` (×2 overloads), `generate_geo_world_json`, `generate_world_msgpack`, `generate_geo_world_msgpack` | 64 |
| `c_api.cpp` | The C ABI, `params_from_c_config` / `compute_options_from_c_config`, malloc-based copies, JSON/MessagePack error envelopes | 10 `extern "C"` symbols + 3 `magic_geo::` conversion functions | 299 |
| `opencl_compute.cpp` | Generation-scoped `ComputeSession`, CPU/OpenCL/CUDA orchestration, dynamic OpenCL discovery, automatic fallback, unified telemetry | `magic_geo::backend_info_json` (`opencl_compute.cpp:3059`), `detail::compute_backend_info_json` (`:3044`), `ComputeSession`, `try_accelerated_assign_plates` / `..._smooth_field` / `..._smooth_three_fields`, `reconcile_accelerated_crust_overlap_continuous_shadow`, `record_cpu_conservative_crust_overlap_transition` | 3063 |
| `cuda_compute.cu` | Native NVIDIA discovery, persistent buffers/stream/events, FP64 kernels (compiled only when CUDA 12.8+ is found) | `detail::CudaComputeSession` | 1521 |
| `cuda_compute_stub.cpp` | Build-preserving stub substituted when no CUDA toolchain is present | `detail::CudaComputeSession` (unavailable) | 95 |
| `crust_overlap_shadow.cpp` | Separately named, **discarded-output** FP64 continuous-moment reduction validated over the exact CPU overlap CSR (parity harness only; CPU stays authoritative) | `replay_crust_overlap_continuous_reduction_cpu` `validate_crust_overlap_continuous_shadow_input` `validate_crust_overlap_continuous_shadow_result` | 581 |

### Private headers (not translation units)

| Header | Contents | Lines |
|---|---|---|
| `engine/internal.hpp` | The private cross-TU interface. None of its symbols are exported. Line 439 marks the output-rendering block with "Simulation stages do not depend on these functions." | 616 |
| `engine/world.hpp` | `EarthSystemState`, `NaturalArtifacts`, `SocietyArtifacts`, `GeneratedWorld`, plus `simulate_world` / `simulate_geo_world` / `serialize_world` | 59 |
| `engine/model.hpp` | Aggregates `constants.hpp`, `schema_names.hpp`, `types/*`, and the public header; defines `clamp` | 21 |
| `engine/constants.hpp` | Climate/tectonic/hydrologic constants, `CrustProcessReason` (10 values), `MESH_BACKEND_*`, `MATURATION_REFERENCE_TIMESTEP_MA = 5.0` | 101 |
| `engine/schema_names.hpp` | Enum → string tables used by the serializers | 136 |
| `engine/types/core.hpp` | `Vec3`, `Plate`, `Cell` | 221 |
| `engine/types/earth_system.hpp` | Process ledgers, `CrustTransportPlan`, `PlateBoundarySegment`, `PlateMotionStep`, shadow tables | 836 |
| `engine/types/crust_reservoir.hpp` | Dry-rock packet/transfer tables and the fail-closed caps | 130 |
| `engine/types/world.hpp` | Natural and society entity records | 426 |
| `engine/messagepack.hpp` | `sanitize_utf8`, `json_to_messagepack` | 21 |

## Result-type architecture and the simulation/result/serialization boundary

`cpp/src/engine/world.hpp` defines four aggregates. They are the *only* handoff between computation and output.

```cpp
// cpp/src/engine/world.hpp:10
struct EarthSystemState {
    std::vector<Cell> cells;
    InitialOceanicCrustAgeDiagnostics initial_oceanic_crust_age;
    CrustMaterialShadowState crust_material_shadow;
    CrustDryRockAccountingState crust_dry_rock_accounting;
    std::vector<Plate> plates;
    std::vector<PlateMotionStep> plate_motion_history;
    std::vector<NumericDepressionCorrectionEvent> numeric_depression_correction_history;
    std::vector<HydrologicWaterBudgetStage> hydrologic_water_budget_history;
    std::vector<EarthSystemFeedbackStep> feedback_history;
    std::vector<FluvialSedimentRoutingStage> sediment_routing_history;
    std::vector<HillslopeSedimentTransportStage> hillslope_transport_history;
    std::vector<GlacialSedimentTransportStage> glacial_transport_history;
};
```

| Aggregate | Header line | Members | Role |
|---|---|---|---|
| `EarthSystemState` | `world.hpp:10` | 12 | The evolving physical state (`cells`, `plates`) plus every append-only process ledger produced while it evolves |
| `NaturalArtifacts` | `world.hpp:25` | 6: `ice_sheets`, `lake_basins`, `watersheds`, `coastal_features`, `sedimentary_basins`, `stratigraphic_columns` | Derived natural entities, computed *after* the earth-system stages settle |
| `SocietyArtifacts` | `world.hpp:34` | 11: `settlements`, `routes`, `political_regions`, `borders`, `trade_flows`, `cultural_layers`, `historical_layers`, `population_regions`, `conflicts`, `dynasties`, `territorial_snapshots` | Everything skipped on the geo-only path; default-constructed and empty there |
| `GeneratedWorld` | `world.hpp:48` | `earth`, `natural`, `society`, `calibration_checks` | The complete result value returned by `simulate_world_impl` |

The boundary is enforced structurally, not by convention:

1. `simulate_world_impl` returns `GeneratedWorld` **by value** and takes only `const Params&` plus a `bool`.
2. `serialize_world(const Params&, const GeneratedWorld&)` (`world.hpp:57`) takes the result by const reference — it cannot mutate it.
3. Every serializer in `internal.hpp` below the comment at line 439 (`plates_json`, `cells_json`, all `*_model_json`, all `*_history_json`, `summary_json`) takes const inputs and returns `std::string`.
4. No domain stage in `pipeline.cpp` calls any `*_json` function.

The MessagePack path does **not** bypass the JSON document. `generate_world_msgpack` calls `detail::json_to_messagepack(detail::serialize_world(...))` (`cpp/src/engine.cpp:46`). Per `cpp/src/engine/README.md:27`, this is intentional: transcoding the canonical JSON preserves every decimal-quantization boundary the Python enrichers depend on.

The top-level key order is fixed by the emission order in `serialize_world` (`world_serialization.cpp:42-294`): `schema_version` (literal `2`, line 49), `name`, `planet_parameters`, `mesh_backend`, `cell_area_model`, `summary`, `backend`, then the model/history sections, then entity arrays, ending with `cells` — which is emitted as the literal `[]` when `params.include_cells` is false (`world_serialization.cpp:289-291`).

`summary` is composed by nesting, not by merging: `summary_with_crust_dry_rock_accounting_json(summary_with_crust_material_shadow_json(summary_json(...)), ...)` (`world_serialization.cpp:54-84`). The base summary block is emitted first, then the shadow extension keys, then the dry-rock extension keys.

## Pipeline stage order

`magic_geo::detail::simulate_world_impl(const Params& params, bool include_society)` in `cpp/src/engine/pipeline.cpp:6` is the single complete stage ordering in the tree. `simulate_world(params)` passes `include_society = true` (`pipeline.cpp:268`); `simulate_geo_world(params)` passes `false` (`pipeline.cpp:272`).

| # | `pipeline.cpp` | Call | Produces / mutates |
|---|---|---|---|
| 1 | 12 | `build_mesh(params)` | `earth.cells` — sphere mesh with positions, control volumes, areas, neighbor graph |
| 2 | 13–15 | guard | throws `plate_count must be smaller than generated mesh cell count` |
| 3 | 17 | `generate_plates(params)` | `earth.plates` — Euler axes, angular speeds, continental/oceanic assignment |
| 4 | 18–21 | `choose_plate_seeds(params, cell_count)` | deterministic seed cell index per plate |
| 5 | 24–29 | inline loop | sets `plate.initial_center` and `plate.center` from seed cell positions; builds `plate_centers` |
| 6 | 30 | `assign_plates(plate_centers, earth.cells)` | nearest-center `plate_id` per cell |
| 7 | 31 | `classify_boundaries(params, plates, cells)` | per-cell divergent/convergent/transform forcing (smoothed) |
| 8 | 32–37 | `derive_crust_and_topography(params, plates, cells, &earth.initial_oceanic_crust_age)` | crust type, lithology, thickness, density, initial age via the ridge-graph field, thermal-subsidence targets, initial elevation, sediment interface (`initialize_sediment_interface` at `tectonics.cpp:509`); fills `InitialOceanicCrustAgeDiagnostics` |
| 9 | 38–41 | `build_identity_crust_transport_plan(cells)` | identity (no-motion) transport plan for the step-0 checkpoint |
| 10 | 42–64 | loop of `is_oceanic_crust_state` + `crust_equilibrium_elevation_m` | `initial_isostatic_equilibrium_m` and `initial_thermal_subsidence_target_m` operand vectors |
| 11 | 69–89 | `summarize_plate_motion_step(..., id=0, erosion_iteration=-1, stage="initial_plate_domains", ...)` | first `earth.plate_motion_history` record — the identity-overlap initial checkpoint carrying all-cell initial crust age at binary64 round-trip precision |
| 12 | 90–96 | `initialize_crust_material_shadow(...)` | opening packet table of the non-authoritative sparse dry-rock mass shadow |
| 13 | 97–105 | `initialize_crust_dry_rock_accounting(...)` | three-reservoir counter-model, initial upper-mantle exchange counter-reserve, empty slab tables |
| 14 | 107–116 | `stabilize_numeric_depressions(params, cells, 0, "initial_climate_hydrology", -1, ...)` | **first ocean/climate/hydrology pass**; appends correction events and water-budget stages; returns `HydrologyStabilizationResult` |
| 15 | 117–133 | `summarize_feedback_step(cells, 0, "initial_climate_hydrology", -1, ..., all five stage flags false, 0, nullptr)` | first `earth.feedback_history` entry |
| 16 | 135–147 | `erode(...)` | **the maturation loop** — `params.erosion_iterations` passes (see below) |
| 17 | 149–150 | `capture_feedback_reference(cells)` | `pre_cryosphere_reference` snapshot |
| 18 | 151 | `derive_cryosphere_state(params, cells)` | glaciers, ice thickness, snowline, glacial erosion signal |
| 19 | 152–156 | `transport_glacial_sediment(0, feedback_history.size(), cells)` | appended to `earth.glacial_transport_history`; terminal glacial erosion/deposition through `apply_sediment_interface_material_change` (`environment.cpp:245`) |
| 20 | 157–166 | `stabilize_numeric_depressions(..., "cryosphere_coupling", -1, ...)` | re-solves sea level / climate / water budget / hydrology after glacial transport |
| 21 | 167 | `derive_cryosphere_state(params, cells)` (second call) | terminal cryosphere state recomputed after stabilization — a zero-duration endpoint operator |
| 22 | 168–184 | `summarize_feedback_step(..., "cryosphere_coupling", -1, ..., cryosphere_applied=true, ..., &pre_cryosphere_reference)` | final feedback record |
| 23 | 186 | `summarize_plates(params, cells, plates)` | per-plate aggregate statistics |
| 24 | 187 | `derive_soils_biomes_resources(params, cells)` | soils, biomes, resources |
| 25 | 188 | `derive_landforms(cells)` | landform classification |
| 26 | 189 | `generate_ice_sheets(cells)` | `natural.ice_sheets` (takes `cells` by non-const reference) |
| 27 | 190 | `generate_lake_basins(params, cells)` | `natural.lake_basins` (non-const `cells`) |
| 28 | 191 | `generate_watersheds(params, cells)` | `natural.watersheds` |
| 29 | 192 | `generate_coastal_features(params, cells)` | `natural.coastal_features` |
| 30 | 193 | `generate_sedimentary_basins(cells)` | `natural.sedimentary_basins` |
| 31 | 194–197 | `generate_stratigraphic_columns(cells, natural.sedimentary_basins)` | `natural.stratigraphic_columns` |

### Society branch — `if (include_society)` at `pipeline.cpp:199`

The guarded block spans lines 199–260. `simulate_geo_world` executes stages 1–31 identically and skips it entirely, leaving every `SocietyArtifacts` member default-constructed.

| `pipeline.cpp` | Call | Produces |
|---|---|---|
| 200 | `generate_settlements(params, cells)` | `society.settlements` |
| 201 | `generate_routes(params, cells, settlements)` | `society.routes` |
| 202–207 | `generate_political_regions(params, cells, settlements, routes)` | `society.political_regions` |
| 208 | `generate_border_segments(params, cells)` | `society.borders` |
| 209–213 | `generate_trade_flows(cells, settlements, routes)` | `society.trade_flows` |
| 214–221 | `generate_cultural_layers(params, cells, settlements, political_regions, borders, trade_flows)` | `society.cultural_layers` (cultures, languages, sacred areas, ruins) |
| 222–229 | `generate_historical_layers(cells, settlements, political_regions, borders, trade_flows, cultural_layers)` | `society.historical_layers` (eras, events) |
| 230–234 | `generate_population_regions(cells, political_regions, cultural_layers)` | `society.population_regions` |
| 235–242 | `generate_conflicts(cells, political_regions, borders, trade_flows, cultural_layers, population_regions)` | `society.conflicts` |
| 243–249 | `generate_dynasties(political_regions, cultural_layers, historical_layers, population_regions, conflicts)` | `society.dynasties` |
| 250–259 | `generate_territorial_snapshots(params, cells, political_regions, settlements, cultural_layers, historical_layers, population_regions, conflicts)` | `society.territorial_snapshots` |

After the branch rejoins, `pipeline.cpp:261-264` runs `generate_calibration_checks(earth.cells, natural.watersheds)` on **both** paths — it depends only on cells and watersheds. Line 265 returns `world`.

At the C++ layer the geo-only document has the **same shape**: the society vectors simply serialize as `[]` and derived summary counters fall to their defaults. The observable geo-only divergence (top-level key removal, per-cell field stripping, `generation_scope`) is produced in Python; see [World Document Schema](./10-world-schema.md).

## Inside the maturation loop (`erode`)

`erode` is defined at `cpp/src/engine/earth_system.cpp:914` and loops `for (int iter = 0; iter < params.erosion_iterations; ++iter)`.

| # | `earth_system.cpp` | Step | Notes |
|---|---|---|---|
| 1 | 929 | `capture_feedback_reference(cells)` → `previous` | elevation / temperature / precipitation / runoff snapshot |
| 2 | 930–938 | `advance_plate_motion_and_crust(params, iter + 1, plates, cells, plate_motion_history, crust_material_shadow, crust_dry_rock_accounting)` | returns `tectonic_elevation_change`; internally rotates plates, reassigns, reclassifies boundaries, builds the forward-overlap plan, runs the accelerator shadow reconciliation, opens/closes the material shadow step, advances the reservoir counter-model, and appends a `PlateMotionStep` |
| 3 | 939–946 | flow-accumulation percentile | `acc_scale` from the 95th-percentile land accumulation, floored at 1.0 |
| 4 | 947–958 | `transport_hillslope_sediment(...)` | `HillslopeSedimentTransportStage` plus `hillslope_production_depth_m` / `hillslope_deposition_depth_m` tendency arrays |
| 5 | 966–996 | stream-power loop (`#pragma omp parallel for schedule(static)`) | per-cell fluvial `erosion_depth_m = stream * maturation_timestep_scale(params)`. The **exported** `cell.erosion_rate` is set to the unscaled `stream` — the 5 Ma reference response — while only the applied depth is scaled (comment at `earth_system.cpp:988-992`) |
| 6 | 999–1009 | `route_fluvial_sediment(...)` | `FluvialSedimentRoutingStage` carrying the full cell-indexed routing-input snapshot |
| 7 | 1010–1097 | combined commit loop | splits each stage's source depth into `alluvium_entrainment` (bounded by opening mobile inventory, hillslope first, then fluvial) vs `bedrock_erosion`; accumulates `depth_m * area_km2 / 1000` volumes; calls **one** `apply_sediment_interface_material_change(...)` per cell for the combined tectonic + hillslope + fluvial change; then re-checks the compatibility surface and updates `sediment_net_budget_m` |
| 8 | 1098–1119 | audits | `maximum_sediment_interface_closure_residual_m(cells, "post hillslope/fluvial transport")` and two `validate_sediment_source_partition(...)` calls with contexts `"hillslope"` and `"fluvial"` |
| 9 | 1120–1121 | history push | `sediment_routing_history` and `hillslope_transport_history` |
| 10 | 1122–1130 | `stabilize_numeric_depressions(params, cells, feedback_history.size(), "erosion_iteration", iter + 1, ...)` | |
| 11 | 1131–1147 | `summarize_feedback_step(..., "erosion_iteration", iter + 1, ..., erosion_applied=true, cryosphere_applied=false, plate_motion_applied=true, crust_transport_applied=true, crust_evolution_applied=true, plate_motion_history.back().id, &previous)` | |

The mutation primitive itself (`sediment_partition.cpp:155`) is:

```cpp
bedrock'  = bedrock + vertical_displacement - bedrock_erosion
sediment' = sediment - alluvium_entrainment + deposition   // clamped at 0 within the error bound
elevation = bedrock' + sediment'                            // derived, never independently set
```

It rejects entrainment beyond the opening mobile inventory (`sediment_partition.cpp:187`) and a negative closing inventory (`:197`), both against a `forward_error_bound` of `max(1e-12, 128 * DBL_EPSILON * max(1, terms) * (1 + |sum|))` (`sediment_partition.cpp:7-20`).

## Inside `stabilize_numeric_depressions`

Defined at `cpp/src/engine/hydrology.cpp:1122`. Each call runs a bounded loop `for (recomputation_index = 0; recomputation_index <= NUMERIC_DEPRESSION_CORRECTION_MAX_PASSES; ++recomputation_index)` where the cap is `16` (`constants.hpp`, `NUMERIC_DEPRESSION_CORRECTION_MAX_PASSES = 16`).

Per pass, in this exact order (`hydrology.cpp:1140-1155`):

1. `apply_sea_level(params, cells)` — volume-constrained solve; accumulates `sea_level_adjustment_m`, increments `sea_level_recompute_count`.
2. `label_marine_water_bodies(cells)`.
3. `compute_climate(params, cells)` — increments `climate_recompute_count`.
4. `compute_hydrologic_water_budget(...)` pushed onto `water_budget_history` — increments `hydrologic_water_budget_recompute_count`.
5. `compute_flow_and_rivers(params, cells)` (which itself runs `compute_priority_flood_spill` first, `hydrology.cpp:371`) — increments `hydrology_recompute_count`.

Then it collects cells with `depression_policy == 1` grouped by `depression_component_id`. If none remain, it runs the whole-field closure audit `maximum_sediment_interface_closure_residual_m(cells, "post hydrology stabilization")` and returns (`hydrology.cpp:1168-1176`). If pass `16` is reached with candidates still present it throws `numeric depression correction did not converge within the bounded pass count` (`hydrology.cpp:1177-1179`). Otherwise, for each component it builds a `NumericDepressionCorrectionEvent`, calls `derive_numeric_depression_breach_alternative` and `apply_numeric_depression_correction`, and appends to `correction_history`.

Fill-depth validation is strict: a candidate whose `fill_depth_m <= NUMERIC_DEPRESSION_FILL_DEPTH_TOLERANCE_M` (`1.0e-9`) or whose depth disagrees with `depression_depth_m` by more than `1.0e-7` throws (`hydrology.cpp:1231-1234`).

## The public C++ facade

All four backend-aware entry points in `cpp/src/engine.cpp` share the identical prologue:

```cpp
// cpp/src/engine.cpp:16
std::string generate_world_json(const Params& params, const ComputeOptions& compute_options) {
    detail::validate_compute_options(compute_options);
    detail::validate_params(params);
    detail::ScopedThreadConfiguration thread_configuration(params.threads);
    detail::ComputeSession compute_session(params, compute_options);
    return detail::serialize_world(params, detail::simulate_world(params));
}
```

| Facade function | `engine.cpp` | Society stages | Output | Backend |
|---|---|---|---|---|
| `generate_world_json(const Params&)` | 10 | yes | JSON string | **hardcoded CPU** (`compute_backend = 1`, line 12) |
| `generate_world_json(const Params&, const ComputeOptions&)` | 16 | yes | JSON string | from `ComputeOptions` |
| `generate_geo_world_json(const Params&, const ComputeOptions&)` | 27 | no | JSON string | from `ComputeOptions` |
| `generate_world_msgpack(const Params&, const ComputeOptions&)` | 38 | yes | `std::vector<uint8_t>` via `json_to_messagepack` | from `ComputeOptions` |
| `generate_geo_world_msgpack(const Params&, const ComputeOptions&)` | 51 | no | `std::vector<uint8_t>` via `json_to_messagepack` | from `ComputeOptions` |

There is no one-argument `generate_geo_world_json(const Params&)` overload and no v1/v2 MessagePack entry point.

`validate_compute_options` (`core.cpp:233`) accepts `compute_backend` in `[0, 3]` only. `validate_params` (`core.cpp:239`) runs 29 `require_finite` checks (`core.cpp:245-285`) followed by 37 range checks (`core.cpp:287-432`); the ones a caller hits most often are:

| Parameter | Accepted range | `core.cpp` |
|---|---|---|
| `cell_count` | 128 … 200000 | 287 |
| `mesh_backend` | `0` (fibonacci) or `1` (geodesic icosahedron) | 290 |
| `plate_count` | 2 … 256 and `< cell_count` | 294 |
| `neighbor_count` | 4 … 16 | 302 |
| `radius_km` | `> 100` and `<= 100000` | 305 |
| `gravity_g` | `> 0.05` and `< 5` | 310 |
| `months` | exactly `12` | 376 |
| `maturation_timestep_ma` | `> 0` and `<= 5` | 388 |
| `erosion_iterations` | 0 … 250 | 406 |
| `river_percentile` | 0.5 … 0.995 | 403 |
| `threads` | 0 … 1024 | 427 |
| `float_precision` | 0 … 8 | 430 |

## The C ABI in full

Declared in `cpp/include/magic_geo/native.hpp:165-189`, defined in `cpp/src/c_api.cpp`. `MAGIC_GEO_API` expands to `__declspec(dllexport/dllimport)` on `_WIN32`, `__attribute__((visibility("default")))` on GCC/Clang, and nothing otherwise (`native.hpp:8-18`); it is `#undef`'d at `native.hpp:191`.

### Exported `extern "C"` symbols (10)

| Symbol | C signature | Definition | Behavior |
|---|---|---|---|
| `magic_geo_backend_info_json` | `const char* magic_geo_backend_info_json(void)` | `c_api.cpp:153` | Returns the backend telemetry object as a malloc'd JSON string. No config needed. |
| `magic_geo_generate_json` | `const char* magic_geo_generate_json(const magic_geo::CConfig* cfg)` | `c_api.cpp:163` | v1: full world, **always CPU** (delegates to the one-argument facade) |
| `magic_geo_generate_json_v2` | `const char* magic_geo_generate_json_v2(const magic_geo::CConfigV2* cfg)` | `c_api.cpp:176` | v2: full world with `ComputeOptions`; nominal timestep defaults to 5 Ma |
| `magic_geo_generate_json_v3` | `const char* magic_geo_generate_json_v3(const magic_geo::CConfigV3* cfg)` | `c_api.cpp:192` | v3: full world with `ComputeOptions` + `maturation_timestep_ma` |
| `magic_geo_generate_geo_json_v2` | `const char* magic_geo_generate_geo_json_v2(const magic_geo::CConfigV2* cfg)` | `c_api.cpp:208` | v2 geo-only (society stages skipped) |
| `magic_geo_generate_geo_json_v3` | `const char* magic_geo_generate_geo_json_v3(const magic_geo::CConfigV3* cfg)` | `c_api.cpp:226` | v3 geo-only |
| `magic_geo_generate_msgpack_v3` | `const std::uint8_t* magic_geo_generate_msgpack_v3(const magic_geo::CConfigV3* cfg, std::size_t* size)` | `c_api.cpp:244` | v3 full world as MessagePack; length via out-param |
| `magic_geo_generate_geo_msgpack_v3` | `const std::uint8_t* magic_geo_generate_geo_msgpack_v3(const magic_geo::CConfigV3* cfg, std::size_t* size)` | `c_api.cpp:267` | v3 geo-only as MessagePack |
| `magic_geo_free_string` | `void magic_geo_free_string(const char* ptr)` | `c_api.cpp:293` | `std::free` with `const_cast`; `nullptr` is safe |
| `magic_geo_free_buffer` | `void magic_geo_free_buffer(const std::uint8_t* ptr)` | `c_api.cpp:297` | `std::free` with `const_cast`; `nullptr` is safe |

Verified against the shipped library:

```bash
nm -D --defined-only src/magic_geo/libmagic_geo_native.so | grep ' T magic_geo_'
```

returns exactly those 10 symbols.

### Exported C++ symbols (9, `namespace magic_geo`)

| Signature | Header line | Notes |
|---|---|---|
| `std::string backend_info_json()` | 141 | defined in `opencl_compute.cpp:3059` |
| `std::string generate_world_json(const Params&)` | 142 | **always CPU** |
| `std::string generate_world_json(const Params&, const ComputeOptions&)` | 143 | |
| `std::string generate_geo_world_json(const Params&, const ComputeOptions&)` | 147 | |
| `std::vector<std::uint8_t> generate_world_msgpack(const Params&, const ComputeOptions&)` | 151 | |
| `std::vector<std::uint8_t> generate_geo_world_msgpack(const Params&, const ComputeOptions&)` | 155 | |
| `Params params_from_c_config(const CConfig&)` | 159 | `c_api.cpp:13`; `cfg.name == nullptr` becomes `"world"` (`c_api.cpp:16`) |
| `Params params_from_c_config(const CConfigV3&)` | 160 | `c_api.cpp:59`; delegates to the v1 overload then sets `maturation_timestep_ma` |
| `ComputeOptions compute_options_from_c_config(const CConfigV2&)` | 161 | `c_api.cpp:65` |

### `CConfig` (v1) — 41 fields

`sizeof == 304`, `alignof == 8` on LP64. Frozen twice: by `cpp/tests/c_api_v1_layout.hpp:10-51` (independent of the public header) and re-asserted against the live struct at `cpp/tests/native_api_test.cpp:36-53`.

| # | Type | Field | Offset (LP64) | Maps to `Params` |
|---|---|---|---|---|
| 1 | `std::uint64_t` | `seed` | 0 | `seed` |
| 2 | `const char*` | `name` | 8 | `name` (`nullptr` → `"world"`) |
| 3 | `double` | `radius_km` | 16 | `radius_km` |
| 4 | `double` | `gravity_g` | 24 | `gravity_g` |
| 5 | `double` | `day_length_hours` | 32 | `day_length_hours` |
| 6 | `double` | `axial_tilt_deg` | 40 | `axial_tilt_deg` |
| 7 | `double` | `orbital_eccentricity` | 48 | `orbital_eccentricity` |
| 8 | `double` | `stellar_luminosity` | 56 | `stellar_luminosity` |
| 9 | `double` | `atmosphere_pressure_bar` | 64 | `atmosphere_pressure_bar` |
| 10 | `double` | `greenhouse_factor` | 72 | `greenhouse_factor` |
| 11 | `double` | `ocean_fraction_target` | 80 | `ocean_fraction_target` |
| 12 | `double` | `ocean_water_inventory_km3` | 88 | `ocean_water_inventory_km3` |
| 13 | `double` | `internal_heat` | 96 | `internal_heat` |
| 14 | `double` | `geological_age_ga` | 104 | `geological_age_ga` |
| 15 | `int` | `cell_count` | 112 | `cell_count` |
| 16 | `int` | `mesh_backend` | 116 | `mesh_backend` |
| 17 | `int` | `neighbor_count` | 120 | `neighbor_count` |
| 18 | `int` | `plate_count` | 124 | `plate_count` |
| 19 | `double` | `continental_plate_fraction` | 128 | `continental_plate_fraction` |
| 20 | `double` | `continental_crust_fraction_target` | 136 | `continental_crust_fraction_target` |
| 21 | `double` | `min_angular_speed` | 144 | `min_angular_speed` |
| 22 | `double` | `max_angular_speed` | 152 | `max_angular_speed` |
| 23 | `int` | `boundary_smoothing_steps` | 160 | `boundary_smoothing_steps` |
| 24 | `double` | `plate_motion_scale_deg_per_step` | 168 | `plate_motion_scale_deg_per_step` |
| 25 | `double` | `oceanic_crust_aging_ma_per_step` | 176 | `oceanic_crust_aging_ma_per_step` |
| 26 | `int` | `months` | 184 | `months` (must be exactly 12) |
| 27 | `double` | `lapse_rate_c_per_km` | 192 | `lapse_rate_c_per_km` |
| 28 | `double` | `base_temperature_c` | 200 | `base_temperature_c` |
| 29 | `double` | `precipitation_scale` | 208 | `precipitation_scale` |
| 30 | `double` | `subtropical_drying_strength` | 216 | `subtropical_drying_strength` |
| 31 | `int` | `preserve_geologic_depressions` | 224 | `bool` via `!= 0` (`c_api.cpp:45`) |
| 32 | `double` | `river_percentile` | 232 | `river_percentile` |
| 33 | `int` | `erosion_iterations` | 240 | `erosion_iterations` |
| 34 | `double` | `stream_power_coefficient` | 248 | `stream_power_coefficient` |
| 35 | `double` | `drainage_exponent` | 256 | `drainage_exponent` |
| 36 | `double` | `slope_exponent` | 264 | `slope_exponent` |
| 37 | `double` | `hillslope_diffusion` | 272 | `hillslope_diffusion` |
| 38 | `double` | `tectonic_uplift_scale` | 280 | `tectonic_uplift_scale` |
| 39 | `int` | `threads` | 288 | `threads` |
| 40 | `int` | `include_cells` | 292 | `bool` via `!= 0` (`c_api.cpp:54`) |
| 41 | `int` | `float_precision` | 296 | `float_precision` |

`CConfig` carries **no** `maturation_timestep_ma`. A v1 caller therefore receives the `Params` default of `5.0` (`native.hpp:66`), which is exactly `MATURATION_REFERENCE_TIMESTEP_MA`.

### `CConfigV2` — `sizeof == 312`

```cpp
// cpp/include/magic_geo/native.hpp:128
struct CConfigV2 {
    CConfig base;          // offset 0
    int compute_backend;   // offset 304
    int opencl_prefer_gpu; // offset 308
};
```

| Field | Type | Offset | Values |
|---|---|---|---|
| `base` | `CConfig` | 0 | the frozen 304-byte v1 block |
| `compute_backend` | `int` | 304 | `0` auto, `1` cpu, `2` opencl, `3` cuda; anything else throws |
| `opencl_prefer_gpu` | `int` | 308 | `bool` via `!= 0` (`c_api.cpp:68`); retained for ABI compatibility and OpenCL device ranking |

### `CConfigV3` — `sizeof == 320`

```cpp
// cpp/include/magic_geo/native.hpp:136
struct CConfigV3 {
    CConfigV2 base;               // offset 0
    double maturation_timestep_ma; // offset 312
};
```

| Field | Type | Offset | Notes |
|---|---|---|---|
| `base` | `CConfigV2` | 0 | |
| `maturation_timestep_ma` | `double` | 312 | Nominal refinement interval relative to the shipped 5 Ma reference step; validated `> 0` and `<= 5` (`core.cpp:388`). Explicitly **not** advertised as a calibrated physical timestep (`native.hpp:64-65`) |

All three sizes/offsets are compile-time asserted in `cpp/tests/native_api_test.cpp:36-44` behind `#if INTPTR_MAX == INT64_MAX`.

### Memory ownership and free-function rules

| Return kind | Allocation | Ownership | Release with | Empty/failure signal |
|---|---|---|---|---|
| JSON (`const char*`) | `std::malloc(size + 1)` then `memcpy` including the NUL (`c_api.cpp:76-83`) | caller | `magic_geo_free_string` | `nullptr` only if `malloc` failed |
| MessagePack (`const uint8_t*` + `size_t*`) | `std::malloc(value.empty() ? 1 : value.size())` (`c_api.cpp:93`) | caller | `magic_geo_free_buffer` | `size == nullptr` → immediate `nullptr`; on failure `*size = 0` and `nullptr` |

Hard rules:

- **Never** call `free()` from your own allocator on these pointers unless it is the same `std::free` the library used. Use the provided free functions.
- Binary results may contain embedded NUL bytes; the explicit `*size` is the only valid length. The 1-byte allocation for an empty vector guarantees a non-null pointer on success.
- Both msgpack entry points zero `*size` before doing any work (`c_api.cpp:251`, `:274`) so a partially-failed call leaves a coherent length.
- `magic_geo_free_string(nullptr)` and `magic_geo_free_buffer(nullptr)` are safe (`std::free(nullptr)` is defined).

### Error envelopes

Every entry point is fully try/catch-wrapped. There are no exceptions crossing the ABI.

| Condition | JSON entry points | MessagePack entry points |
|---|---|---|
| `size == nullptr` | n/a | return `nullptr` immediately |
| `cfg == nullptr` | `{"error":"null config pointer"}` | same document transcoded to MessagePack |
| `std::exception` | `{"error":"<exc.what()>"}` | same, transcoded |
| `...` (full world) | `{"error":"unknown generation failure"}` | same, transcoded |
| `...` (geo world) | `{"error":"unknown geo generation failure"}` | same, transcoded |
| `...` (`backend_info`) | `{"error":"unknown backend_info failure"}` | n/a |
| transcoding the error itself throws | n/a | `copy_error_msgpack_noexcept` returns `nullptr` and sets `*size = 0` (`c_api.cpp:137-149`) |

Error text is run through `magic_geo::detail::sanitize_utf8` (malformed bytes → U+FFFD) and then JSON-escaped, with control characters below `0x20` emitted as `\u00XX` (`c_api.cpp:104-131`).

### ABI stability policy

From `cpp/src/engine/README.md:341-345` and `native.hpp:125-139`:

| Rule | Consequence |
|---|---|
| `CConfig` stays **byte-for-byte** unchanged (the 304-byte structure) | A client compiled against the original v1 layout stays safe when loaded against a newer shared library |
| `CConfigV2` field order, types, and 64-bit sizes stay stable | Same guarantee at the v2 level |
| New scientific knobs get a new versioned struct (v3 added `maturation_timestep_ma` at the tail) | Older callers keep working and receive the historical 5 Ma nominal reference step |
| `Params` (the C++ struct) **may grow at the tail** | Source-level C++ clients rebuild when it changes; C clients are insulated by the versioned `CConfig*` structs |
| Compute controls belong to `ComputeOptions` / `CConfigV2`; the nominal timestep belongs to `CConfigV3` | Scientific parameters and execution policy stay separated |
| The unversioned C++ `generate_world_json(const Params&)` overload and the v1 C entry point **always use CPU** | A v1 caller can never accidentally engage an accelerator |
| Python mirrors every C layout via `ctypes` | See the next section |

`cpp/tests/c_api_v1_client_test.cpp` compiles against `c_api_v1_layout.hpp` **without including `magic_geo/native.hpp`** and declares `magic_geo_generate_json` itself (`c_api_v1_client_test.cpp:6-9`). Any drift in the v1 layout fails at compile time in that target, not at runtime in a user's process.

### Worked example — a minimal C client

```c
/* build: cc client.c -L src/magic_geo -l magic_geo_native -o client */
#include <stdio.h>
#include <stdint.h>
#include <stddef.h>

/* Mirror the frozen v1 layout exactly; see cpp/tests/c_api_v1_layout.hpp. */
struct CConfig {
    uint64_t seed;   const char* name;
    double radius_km, gravity_g, day_length_hours, axial_tilt_deg;
    double orbital_eccentricity, stellar_luminosity, atmosphere_pressure_bar;
    double greenhouse_factor, ocean_fraction_target, ocean_water_inventory_km3;
    double internal_heat, geological_age_ga;
    int cell_count, mesh_backend, neighbor_count, plate_count;
    double continental_plate_fraction, continental_crust_fraction_target;
    double min_angular_speed, max_angular_speed;
    int boundary_smoothing_steps;
    double plate_motion_scale_deg_per_step, oceanic_crust_aging_ma_per_step;
    int months;
    double lapse_rate_c_per_km, base_temperature_c, precipitation_scale;
    double subtropical_drying_strength;
    int preserve_geologic_depressions;
    double river_percentile;
    int erosion_iterations;
    double stream_power_coefficient, drainage_exponent, slope_exponent;
    double hillslope_diffusion, tectonic_uplift_scale;
    int threads, include_cells, float_precision;
};

extern const char* magic_geo_generate_json(const struct CConfig*);
extern void        magic_geo_free_string(const char*);

int main(void) {
    struct CConfig cfg = {0};
    cfg.seed = 424242; cfg.name = "c_client";
    cfg.radius_km = 6371.0; cfg.gravity_g = 1.0; cfg.day_length_hours = 24.0;
    cfg.axial_tilt_deg = 23.5; cfg.orbital_eccentricity = 0.016;
    cfg.stellar_luminosity = 1.0; cfg.atmosphere_pressure_bar = 1.0;
    cfg.greenhouse_factor = 1.0; cfg.ocean_fraction_target = 0.70;
    cfg.ocean_water_inventory_km3 = 1338000000.0;
    cfg.internal_heat = 1.0; cfg.geological_age_ga = 4.5;
    cfg.cell_count = 512; cfg.mesh_backend = 0; cfg.neighbor_count = 7;
    cfg.plate_count = 8; cfg.continental_plate_fraction = 0.38;
    cfg.continental_crust_fraction_target = 0.34;
    cfg.min_angular_speed = 0.03; cfg.max_angular_speed = 0.95;
    cfg.boundary_smoothing_steps = 5;
    cfg.plate_motion_scale_deg_per_step = 2.0;
    cfg.oceanic_crust_aging_ma_per_step = 5.0;
    cfg.months = 12; cfg.lapse_rate_c_per_km = 6.5;
    cfg.base_temperature_c = 15.0; cfg.precipitation_scale = 1.0;
    cfg.subtropical_drying_strength = 0.65;
    cfg.preserve_geologic_depressions = 1; cfg.river_percentile = 0.92;
    cfg.erosion_iterations = 2; cfg.stream_power_coefficient = 7.5;
    cfg.drainage_exponent = 0.5; cfg.slope_exponent = 1.0;
    cfg.hillslope_diffusion = 0.055; cfg.tectonic_uplift_scale = 0.85;
    cfg.threads = 0; cfg.include_cells = 0; cfg.float_precision = 4;

    const char* json = magic_geo_generate_json(&cfg);   /* always CPU */
    if (json == NULL) { return 1; }
    printf("%.120s...\n", json);
    magic_geo_free_string(json);                        /* mandatory */
    return 0;
}
```

## How Python mirrors the structs with ctypes

`src/magic_geo/native.py` is the entire Python side of the FFI.

### Struct mirrors

| Python class | `native.py` | Mirrors | Notes |
|---|---|---|---|
| `NativeConfigV1` | 47 | `magic_geo::CConfig` | 41 `_fields_` in exactly the C order; `bool` fields declared as `c_int` |
| `NativeConfigV2` | 93 | `magic_geo::CConfigV2` | `_anonymous_ = ("base",)`, fields `("base", NativeConfigV1)`, `("compute_backend", c_int)`, `("opencl_prefer_gpu", c_int)` |
| `NativeConfigV3` | 102 | `magic_geo::CConfigV3` | `_anonymous_ = ("base",)`, fields `("base", NativeConfigV2)`, `("maturation_timestep_ma", c_double)` |

`_anonymous_` lets nested fields be read and written flat while preserving the exact nested memory layout — the struct is still literally a `CConfigV1` block followed by two ints followed by a double.

### Enum ID tables

| Table | `native.py` | Contents |
|---|---|---|
| `MESH_BACKEND_IDS` | 17 | `{"fibonacci_sphere": 0, "geodesic_icosahedron": 1}` |
| `COMPUTE_BACKEND_IDS` | 22 | `{"auto": 0, "cpu": 1, "opencl": 2, "cuda": 3}` |

Both are indexed with `str(...)` and raise `KeyError` on an unknown name (`native.py:307`, `:337`).

### Library discovery — `_library_path()` (`native.py:110`)

1. `MAGIC_GEO_NATIVE_LIBRARY` environment override → `Path(override).expanduser().resolve()`. If it is not a file: `RuntimeError("MAGIC_GEO_NATIVE_LIBRARY does not name a file: …")`.
2. Otherwise `Path(__file__).resolve().parent` — i.e. `src/magic_geo/`, which is exactly the CMake `MAGIC_GEO_LIBRARY_OUTPUT_DIRECTORY` default (`CMakeLists.txt:83-88`) — joined with the **host-native filename only** from `_native_library_names()` (`native.py:30`): `magic_geo_native.dll` on win32, `libmagic_geo_native.dylib` on darwin, else `libmagic_geo_native.so`. There is no cross-platform name fallback.
3. Nothing found → `RuntimeError("native library was not found. Build it with: cmake -S . -B build && cmake --build build")`.

### Loading — `_load_library()` (`native.py:130`)

`ctypes.CDLL(str(_library_path()))`, then seven symbols are resolved inside one `try`: `magic_geo_backend_info_json`, `magic_geo_generate_json_v3`, `magic_geo_generate_geo_json_v3`, `magic_geo_generate_msgpack_v3`, `magic_geo_generate_geo_msgpack_v3`, `magic_geo_free_string`, `magic_geo_free_buffer`. An `AttributeError` is re-raised as `RuntimeError("native library does not expose the current V3 JSON and MessagePack ABI; rebuild magic_geo_native from the current source tree")`.

Python calls **only** the v3 entry points. `magic_geo_generate_json`, `..._json_v2`, and `..._geo_json_v2` exist for external/legacy C callers and are never used by the package.

Every pointer-returning symbol is given `restype = ctypes.c_void_p`, **not** `c_char_p` (`native.py:147-161`). This is load-bearing: `c_char_p` would make ctypes copy the bytes and discard the raw address, and the allocation could then never be freed.

`_load_library()` is called on every public entry (`native.py:345`, `:354`, `:380`); there is no module-level CDLL cache.

### Consuming a JSON pointer — `_consume_json_pointer` (`native.py:169`)

Null/zero pointer → `RuntimeError("native library returned a null JSON pointer")`. Otherwise `ctypes.cast(ptr, c_char_p).value`; `None` → `RuntimeError("… empty JSON pointer")`; else `json.loads(raw.decode("utf-8"))`. `magic_geo_free_string(ptr)` runs in a `finally`. A dict payload containing `"error"` is raised as `RuntimeError(str(payload["error"]))`.

### Consuming a MessagePack pointer — `_consume_msgpack_pointer` (`native.py:184`)

Null pointer → `RuntimeError`. `size <= 0` → free the buffer, then `RuntimeError("… empty MessagePack buffer")`. Otherwise the native memory is wrapped **zero-copy** and unpacked with hardened options:

```python
native_array = (ctypes.c_ubyte * size).from_address(int(ptr))
view = memoryview(native_array).cast("B")
payload = msgpack.unpackb(
    view,
    raw=False,
    use_list=True,
    strict_map_key=True,
    ext_hook=_reject_msgpack_extension,
    max_str_len=size,
    max_bin_len=0,
    max_array_len=size,
    max_map_len=size,
    max_ext_len=0,
)
```

`max_bin_len=0` and `max_ext_len=0` forbid bin and ext types entirely; `_reject_msgpack_extension` (`native.py:40`) raises `ValueError("MessagePack extension type {code} is not valid in a native world")`. `ExtraData`, `FormatError`, `StackError`, `UnicodeDecodeError`, and `ValueError` are converted to `RuntimeError(f"native library returned invalid MessagePack: {exc}")`. The `finally` block releases the memoryview **before** `free_buffer(ptr)` — mandatory, because the view aliases the malloc'd block. A non-dict root → `RuntimeError("native MessagePack root is not an object")`; an `"error"` key → `RuntimeError`.

### Schema gate — `_require_current_world_schema` (`native.py:234`)

| Check | Failure |
|---|---|
| `type(schema_version) is int` (rejects `bool`) and `== CURRENT_WORLD_SCHEMA_VERSION` (which is `2`, `src/magic_geo/serialization.py:27`) | `RuntimeError("native library returned unsupported world schema_version …; rebuild magic_geo_native from the current source tree")` |
| `retired_world_schema_fields(payload)` is empty | `RuntimeError("native library returned retired fields in a schema-2 world: …")` |
| `planet_parameters` is a dict | `RuntimeError("… schema 2 without explicit planet_parameters")` |
| covers all 12 keys of `PLANET_PARAMETER_DEFAULTS` | `RuntimeError("… incomplete planet_parameters snapshot: …")` (sorted missing keys) |
| each value is a non-`bool` `int`/`float`, convertible to `float` without `OverflowError`, and `math.isfinite` | `RuntimeError(f"native library returned invalid planet_parameters.{key}")` |
| `radius_km`, `gravity_g`, `geological_age_ga` are strictly `> 0.0` | same |

### Config marshalling — `_native_config` (`native.py:281`)

Reads the nested sections `run`, `planet`, `mesh`, `tectonics`, `climate`, `hydrology`, `erosion`, `compute`, `output` from the validated config dict and builds `NativeConfigV1` **positionally** with explicit `int()` / `float()` coercion, `str(run["name"]).encode("utf-8")` for `name`, and `1 if … else 0` for `preserve_geologic_depressions`, `include_cells`, and `opencl_prefer_gpu`. It then wraps into `NativeConfigV2(base, backend_id, prefer_gpu)` and `NativeConfigV3(v2, float(erosion["maturation_timestep_ma"]))`.

Note the field-name remapping between the Python config and the C struct: `mesh.cell_count` → `cell_count`, `mesh.backend` → `mesh_backend` (via the ID table), `erosion.iterations` → `erosion_iterations`, `compute.threads` → `threads`, `output.include_cells` → `include_cells`, `output.float_precision` → `float_precision`.

### Public Python surface

| Function | `native.py` | Behavior |
|---|---|---|
| `backend_info() -> dict` | 344 | `_consume_json_pointer(lib, lib.magic_geo_backend_info_json())`. No schema gate. |
| `generate_world(data, *, serialization="auto") -> dict` | 349 | `serialization` must be one of `{"auto", "json", "msgpack"}` else `ValueError("serialization must be auto, json, or msgpack")`. `"auto"` and `"msgpack"` take `magic_geo_generate_msgpack_v3` with a `ctypes.c_size_t()` out-param passed by `byref`; `"json"` takes `magic_geo_generate_json_v3`. Result passes through `_require_current_world_schema`. |
| `generate_geo_world(data, *, serialization="auto") -> dict` | 375 | Same, against the `..._geo_...` v3 symbols. |

```python
from magic_geo.config import load_config       # see the Configuration Reference page
from magic_geo import native

data = load_config("configs/earthlike_seed.yaml").model_dump()
world = native.generate_world(data, serialization="msgpack")
print(world["schema_version"], world["summary"]["cell_count"])
print(native.backend_info()["selected_backend"])   # key set is backend-dependent
```

## Thread policy and the scoped OpenMP ICV restore

`ScopedThreadConfiguration` is declared at `internal.hpp:81` and defined at `core.cpp:213`:

```cpp
ScopedThreadConfiguration::ScopedThreadConfiguration(int requested_threads) {
#ifdef _OPENMP
    if (requested_threads > 0) {
        previous_max_threads_ = omp_get_max_threads();
        omp_set_num_threads(requested_threads);
        restore_on_destruction_ = true;
    }
#else
    (void)requested_threads;
#endif
}

ScopedThreadConfiguration::~ScopedThreadConfiguration() {
#ifdef _OPENMP
    if (restore_on_destruction_) {
        omp_set_num_threads(previous_max_threads_);
    }
#endif
}
```

| Rule | Where |
|---|---|
| `threads == 0` leaves host OpenMP policy completely untouched — no ICV is read or written | `core.cpp:215` |
| `threads > 0` saves `omp_get_max_threads()`, sets the requested count, and restores on destruction | `core.cpp:216-218`, `:227-229` |
| The object is constructed **before** the `ComputeSession` and destroyed after simulation in every facade entry point, so restore happens on the normal path *and* on exception unwind | `cpp/src/engine.cpp:22-24`, `:33-34`, `:44-45`, `:57-58` |
| Copy construction and copy assignment are deleted | `internal.hpp:86-87` |
| `threads` is validated to `0 … 1024` before the object exists | `core.cpp:427` |
| The invariant: "Explicit OpenMP thread counts are generation-scoped and restore the calling thread's prior ICV on every exit; `threads=0` leaves host policy untouched" | `cpp/src/engine/README.md:356` |

Because `omp_set_num_threads` sets a per-calling-thread ICV, this makes concurrent generations from different host threads independent with respect to thread policy. `cpp/tests/native_api_test.cpp:1090` (`thread_configuration_is_generation_scoped`) and `:1203` (`concurrent_generation_sessions_are_isolated`) are the regression gates.

Note that OpenMP is *optional*: `find_package(OpenMP)` is not `REQUIRED` (`CMakeLists.txt:80`), and `MAGIC_GEO_HAS_OPENMP=1` plus the `OpenMP::OpenMP_CXX` link are only added when it is found (`CMakeLists.txt:188-191`). Without OpenMP the constructor body compiles to nothing and `threads` has no effect.

## Symbol visibility

| Mechanism | Setting | Where |
|---|---|---|
| Default C++ visibility | `CXX_VISIBILITY_PRESET hidden` | `CMakeLists.txt:146` |
| Inline function visibility | `VISIBILITY_INLINES_HIDDEN YES` | `CMakeLists.txt:150` |
| CUDA visibility (when enabled) | `CUDA_VISIBILITY_PRESET hidden` | `CMakeLists.txt:213` |
| Explicit export | `MAGIC_GEO_API` on each declaration in `native.hpp` | `native.hpp:141-188` |
| Macro cleanup | `#undef MAGIC_GEO_API` at end of header | `native.hpp:191` |
| Private interface | `internal.hpp` symbols are never exported | `cpp/src/engine/README.md:258` |
| Invariant | "Keep all declared public symbols visible and all `magic_geo::detail` symbols hidden" | `cpp/src/engine/README.md:346` |

Verified on the shipped Linux build:

```bash
$ nm -D --defined-only src/magic_geo/libmagic_geo_native.so | grep -c '6detail'
0
$ nm -D --defined-only src/magic_geo/libmagic_geo_native.so | grep -c 'magic_geo'
19
```

Those 19 are exactly the 10 `extern "C"` symbols plus the 9 mangled `magic_geo::` functions. The remaining dynamic symbols in the table are weak libstdc++ template instantiations, not engine code.

Practical consequence: you cannot link against `magic_geo::detail::build_mesh` or any other stage. External integrations go through `native.hpp` or the C ABI. Test targets that need `detail` symbols compile the relevant `.cpp` **into the test executable** rather than linking the shared library (see the next section).

## The native test suite

Registered with CTest by the same build; `BUILD_TESTING` comes from `include(CTest)` and defaults to `ON` (`CMakeLists.txt:5`, gate at `:223`).

```bash
cmake -S . -B build
cmake --build build                          # builds the library and the test executables
ctest --test-dir build --output-on-failure   # 13 native tests on a 64-bit host without CUDA
```

| CTest name | Executable | Extra sources compiled in | Links `magic_geo_native` | Contract protected |
|---|---|---|---|---|
| `magic_geo_initial_oceanic_age` | `magic_geo_initial_oceanic_age_test` | `engine/initial_oceanic_age.cpp` | no | Ridge-graph age field: bilateral distance ÷ half-rate is exact; the single length-weighted global rate is the one used; zero-motion and disconnected components take the explicit ceiling; planet-age ceiling and invalid rates are enforced (`initial_oceanic_age_test.cpp:105,158,192,249`) |
| `magic_geo_oceanic_age_depth` | `magic_geo_oceanic_age_depth_test` | `engine/oceanic_age_depth.cpp` | no | Analytic checkpoints match `350√t` / `3200 exp(−t/62.8)`; the 70 Ma transition is C0-continuous and monotone; non-oceanic input returns 0 and domain guards throw (`oceanic_age_depth_test.cpp:39,62,110`) |
| `magic_geo_oceanic_age_depth_integration` | `magic_geo_oceanic_age_depth_integration_test` | — | yes (+ Threads, + OpenMP if found) | The serialized `oceanic_age_depth_model` and per-cell thermal targets in a real generated world agree with the analytic curve (`oceanic_age_depth_integration_test.cpp:161`) |
| `magic_geo_crust_overlap_shadow` | `magic_geo_crust_overlap_shadow_test` | `cpp/src/crust_overlap_shadow.cpp` | no | The FP64 continuous-moment reduction over the exact CPU CSR validates with zero normalized error; empty destinations retain zero volume/thickness/age and their source-snapshot density; raw gap rows are not destination-normalized; extreme finite operands stay bounded (`crust_overlap_shadow_test.cpp:129+`) |
| `magic_geo_serialization_roundtrip` | `magic_geo_serialization_roundtrip_test` | `engine/messagepack.cpp`, `engine/numeric_serialization.cpp` | no | Strictly positive area arrays and scalars round-trip binary64; non-finite values fail closed; MessagePack scalars use lossless standard encodings; strings/containers are valid; malformed JSON fails closed; FFI diagnostic UTF-8 is preserved or sanitized (`serialization_roundtrip_test.cpp:27,64,78,90,127,148,185`). This is the only test target that does **not** add `-ffp-contract=off` |
| `magic_geo_plate_boundary_segments` | `magic_geo_plate_boundary_segments_test` | `engine/plate_boundary_segments.cpp` | no | Canonical geometry, kinematics, and polarity fields are exact; analytic Euler modes and invariances hold; radius and canonical-orientation invariances hold; reciprocal matching and the malformed-geometry guards fail closed (`plate_boundary_segments_test.cpp:145,271,456,619`) |
| `magic_geo_crust_overlap_candidate_fate` | `magic_geo_crust_overlap_candidate_fate_test` | `engine/crust_overlap_candidate_fate.cpp` | no | Sparse status precedence and area partition close; resolved physical evidence outranks heuristics; mixed/conflicting physical evidence blocks heuristic fallback; heuristic unavailability and conflict are pair-wide; identity steps and tiny positive areas survive; malformed inputs fail closed (`crust_overlap_candidate_fate_test.cpp:196,260,297,326,360,377`) |
| `magic_geo_crust_reservoir` | `magic_geo_crust_reservoir_test` | `engine/crust_reservoir.cpp` | no | Exact mantle exhaustion closes; an empty surface can be explicitly reseeded; mantle depletion does not fan out returned origins; insufficient mantle rejects without publishing; age-only reason mass is rejected; the surface-owner packet cap rejects without publishing (`crust_reservoir_test.cpp:139,166,208,248,289,315`) |
| `magic_geo_crust_reservoir_integration` | `magic_geo_crust_reservoir_integration_test` | — | yes (+ Threads, + OpenMP) | In a real generated world: schema flags and the empty slab tables are truthful; the accounting history is thread-exact; the surface capacity envelope scales with surface area (`crust_reservoir_integration_test.cpp:103,162,174`) |
| `magic_geo_sediment_partition` | `magic_geo_sediment_partition_test` | `engine/sediment_partition.cpp` | yes (+ Threads, + OpenMP) | Synthetic invariants cover valid, zero, and invalid cases; interface transitions cover material and datum changes; generated histories reconstruct and are thread-exact (`sediment_partition_test.cpp:198,269,536`) |
| `magic_geo_native_api` | `magic_geo_native_api_test` | — | yes (+ Threads, + OpenMP) | Compile-time `CConfig`/V2/V3 sizes, alignment, and per-field offsets against the frozen layout; `params_from_c_config` preserves every field; the public API is usable; geodesic physics uses the actual mesh size; a half-turn crust shadow accepts fully uncovered destinations; concurrent generation sessions are isolated; thread configuration is generation-scoped; backend selection/fallback and OpenCL parity; CUDA backend failure and parity (`native_api_test.cpp:36-53,117,217,1090,1132,1203,1242,742,969`) |
| `magic_geo_fibonacci_knn_reference` | *the same* `magic_geo_native_api_test` binary | — | — | Second registration with `ENVIRONMENT "MAGIC_GEO_VALIDATE_FIBONACCI_KNN=1"` (`CMakeLists.txt:470-474`), which routes `main` to `reference_scale_membership_area_classes_close()` only — the intentionally expensive 4,096-cell reference check (`native_api_test.cpp:1151,1564-1572`) |
| `magic_geo_cuda_compute` | `magic_geo_cuda_compute_test` | `cpp/src/cuda_compute.cu`, `cpp/src/crust_overlap_shadow.cpp` | no | **Only registered when `MAGIC_GEO_CUDA_ENABLED`.** Session construction must not change the caller's current CUDA device; plate assignment matches the ordered CPU reference including exact ties; scalar and fused smoothing are bitwise-equal to the CPU reference across growing sizes and zero steps. `SKIP_RETURN_CODE 77` makes it skip cleanly with no device (`CMakeLists.txt:507-511`, `cuda_compute_test.cpp:142`) |
| `magic_geo_c_api_v1_client` | `magic_geo_c_api_v1_client_test` | — | yes | **Only registered when `CMAKE_SIZEOF_VOID_P EQUAL 8`.** Compiles against the frozen `c_api_v1_layout.hpp` **without including `magic_geo/native.hpp`** and declares `magic_geo_generate_json` itself, so any v1 layout drift becomes a compile error (`CMakeLists.txt:513-527`) |

So 14 CTest names come from 13 executables — the native-API binary is registered twice. On a 64-bit host without a CUDA toolchain, 13 tests run.

Every test target uses `cxx_std_20`. All of them add `-ffp-contract=off` under GNU/Clang **except** `magic_geo_serialization_roundtrip_test`, `magic_geo_crust_reservoir_integration_test`, `magic_geo_native_api_test`, and `magic_geo_c_api_v1_client_test`.

Note the split pattern: unit tests that need `magic_geo::detail` symbols compile the relevant `.cpp` directly into the executable (because those symbols are hidden in the shared library); integration tests link `magic_geo_native` and drive it through `magic_geo/native.hpp` only.

Per `cpp/src/engine/README.md:361-364`, `native_api_test.cpp` protects the public boundary and concurrent session behavior, `c_api_v1_client_test.cpp` protects the frozen layout, and the Python suite (see [Testing and Quality Gates](./18-testing.md)) provides the end-to-end physics, replay, schema, and mutation-rejection gates.

## Contributor guide: adding a new stage

The invariants at `cpp/src/engine/README.md:326-359` are the contract. Here is how to add a domain stage without breaking them.

### 1. Decide where the stage belongs in the order

Read `cpp/src/engine/pipeline.cpp` end to end first. Many stages deliberately *enrich* the shared `Cell` state and later stages consume those fields; ordering is behavior. A stage that reads `flow_accumulation` must be after `compute_flow_and_rivers`; a stage that reads `sediment_thickness_m` must be after the commit it depends on; a stage that reads `biome` must be after `derive_soils_biomes_resources`.

Your stage must be placed **before** `serialize_world` — which, since `serialize_world` is called by the facade in `engine.cpp` and never from `pipeline.cpp`, means anywhere in `simulate_world_impl`.

### 2. Add the translation unit and its declaration

- Create `cpp/src/engine/<your_stage>.cpp` in `namespace magic_geo::detail`.
- Declare only the cross-TU entry points in `cpp/src/engine/internal.hpp`, in the section that matches the domain. Keep helpers in an anonymous namespace or as TU-local namespace-scope functions.
- Add the file to the source list in `CMakeLists.txt:96-128`, inside the `cpp/src/engine/` block. That block is only *roughly* alphabetical — `climate.cpp` precedes `civilization.cpp`, `crust_overlap_candidate_fate.cpp` precedes `crust_material.cpp`, and `initial_oceanic_age.cpp` sits after `oceanic_age_depth.cpp` — so match the neighbourhood rather than assuming a strict sort.
- Do **not** add a header under `cpp/include/`. New public surface means new ABI, which means a new versioned config struct.

### 3. Put shared records in `types/`, not in your TU

New per-cell fields go in `cpp/src/engine/types/core.hpp` (`Cell`). New ledger record types go in `types/earth_system.hpp`. Constants go in `constants.hpp`; enum name tables go in `schema_names.hpp`. Do not define a record in a `.cpp` that another TU needs.

### 4. Mutate terrain only through the checked primitives

This is the sediment-interface authority boundary. `bedrock_surface_elevation_m` and a nonnegative `sediment_thickness_m` are canonical; `elevation_m` is **derived**. Never write all three yourself.

| Intent | Primitive | `sediment_partition.cpp` |
|---|---|---|
| Establish the interface from an opening surface + mobile thickness | `initialize_sediment_interface(cell, context)` | 91 |
| Move the whole column vertically without changing mobile thickness (sea level, datum) | `shift_sediment_interface_datum(cell, elevation_change_m, context)` | 123 |
| Apply displacement + bedrock erosion + alluvium entrainment + deposition | `apply_sediment_interface_material_change(cell, vertical_displacement_m, bedrock_erosion_depth_m, alluvium_entrainment_depth_m, deposition_depth_m, context)` | 155 |
| Assert a single cell is coherent | `validate_sediment_interface(cell, context)` | 82 |
| Assert the whole field is coherent and get the worst residual | `maximum_sediment_interface_closure_residual_m(cells, context)` | 232 |
| Assert `source = alluvium + bedrock` per cell and that the aggregate volumes reconstruct | `validate_sediment_source_partition(cells, source_depth_m_by_cell, alluvium_entrainment_depth_m_by_cell, bedrock_erosion_depth_m_by_cell, alluvium_entrainment_volume_km3, bedrock_erosion_volume_km3, context)` | 262 |

Pass a non-empty `context` string — an empty or null context throws (`sediment_partition.cpp:22-28`). If your stage produces a source depth, split it into alluvium (bounded by the opening mobile inventory) and bedrock, and run the partition audit; the pattern is in `earth_system.cpp:1010-1119`.

### 5. Emit a ledger, and make it replayable

If your stage changes authoritative state, append a record to a history vector on `EarthSystemState` so Python replay can reconstruct the transition. Follow the existing shape:

- Cell-indexed input snapshots at round-trip precision, not display precision. Use `roundtrip_num` / `roundtrip_double_array_json` (`numeric_serialization.cpp`) for anything a replay reads as an operand.
- The shared nominal-time block (`nominal_time_model`, `nominal_interval_*`, `nominal_time_calibrated`, `physical_time_resolved`, …) is injected by `add_nominal_time_fields` (`process_serialization.cpp:135`). Reuse it; do not invent a second time vocabulary.
- Keep `physical_time_resolved` and `nominal_time_calibrated` false unless you have actually calibrated something and can point at the evidence.

### 6. Write the serializer separately, and keep it read-only

Add the `*_json` fragment to `process_serialization.cpp` (ledgers/models) or `entity_serialization.cpp` (entity arrays), declare it in `internal.hpp` below the line-439 comment, and wire it into `serialize_world` at the position you want in the key order. The serializer takes const inputs and returns `std::string`. It must not call a domain function and a domain function must not call it.

Adding a top-level key changes the world schema. That means:

- Python's `retired_world_schema_fields` / schema expectations may need updating (`src/magic_geo/serialization.py`).
- Downstream enrichers, validators, and the debug exporter see the new key.
- Bumping `schema_version` (currently the literal `2` at `world_serialization.cpp:49`) requires matching `CURRENT_WORLD_SCHEMA_VERSION` in `src/magic_geo/serialization.py:27`, or `_require_current_world_schema` will reject every world.

### 7. Preserve determinism

- RNG: consume `splitmix64` / `hash01` / `signed_noise` in the same order for the same inputs. Adding a draw in the middle of an existing loop reshuffles every subsequent world.
- OpenMP: `#pragma omp parallel for schedule(static)` is the house schedule. Do not use dynamic scheduling for anything whose reduction order affects the result, and do not reduce into a shared accumulator without an ordering guarantee.
- Floating point: the library is compiled with `-ffp-contract=off` under GNU/Clang (`CMakeLists.txt:137-142`) to block FMA-induced drift. Do not reorder existing expressions.
- Serialization: key order is part of the contract. Append; do not reorder.

### 8. Respect the backend and ABI boundaries

- A new stage runs on CPU unless you add an accelerated path through `opencl_compute.hpp`. `cpu` must not initialize or probe CUDA or OpenCL; explicit `opencl`/`cuda` must never silently fall back; only `auto` may fall back, and it must report the reason in telemetry (`cpp/src/engine/README.md:348-355`).
- If your stage needs a new tunable: add it to `Params` **at the tail** (`native.hpp`), add it to the Python config model, and expose it through a **new** `CConfigV4` — never by editing `CConfig` or `CConfigV2`. Then mirror the new struct in `src/magic_geo/native.py` and update `_load_library` to resolve the v4 symbols.

### 9. Run the gates

```bash
cmake -S . -B build
cmake --build build
ctest --test-dir build --output-on-failure
python -m pytest            # the end-to-end physics, replay, and schema gates
```

If you touched the C ABI, `magic_geo_c_api_v1_client` and `magic_geo_native_api` are the first tests to fail — by design, at compile time.

## Limitations and unresolved claims

The native core is explicit about the boundary between what it computes exactly and what it merely models procedurally. These caveats are carried from the source and must not be softened:

- **Subduction polarity is unresolved.** The plate-boundary ledger supplies a *candidate* subducting/overriding pair only when exactly one side is oceanic-like at a convergent segment. The physical sides remain `unknown`, the decision source remains `none`, and the confidence remains zero. Physical subduction polarity, slab selection, slab geometry/transfer, and material fate are false (`cpp/src/engine/README.md:210-226`).
- **The exact segment ledger does not drive the simulation.** Segment geometry and direct unsmoothed kinematics are authoritative, but the degree-normalized *smoothed* per-cell boundary forcing is what drives the tectonic rules, and it does not consume the ledger. The ledger must not be described as driving cell forcing or slab transfers until such consumers exist and are independently validated (`cpp/src/engine/README.md:334-338`).
- **The km/Ma rates in the boundary ledger are uncalibrated.** They multiply intrinsic Euler velocities by `radius_km * plate_motion_scale_deg_per_step * (π/180) / 5 Ma` — a nominal reference-step scale, not a calibrated physical velocity (`cpp/src/engine/README.md:195-198`).
- **Physical time is not calibrated.** `maturation_timestep_ma` is a nominal refinement interval relative to the shipped 5 Ma reference step (`native.hpp:64-65`). Exported metadata keeps physical time, process-rate calibration, and whole-coupling timestep convergence explicitly false (`cpp/src/engine/README.md:112-113`).
- **The dry-rock mass shadow is non-authoritative.** `crust_material.cpp` implements a *shadow*, deliberately separate from the authoritative crust state and the raw-overlap inventory. It does not implement solid volume, phase, mantle, slab, or global crust-cycle conservation, and serializers must preserve the explicit false authority, physical source/sink, material-provenance, solid-volume, phase, mass-weighted-age, mantle, slab, and global crust-cycle flags (`cpp/src/engine/README.md:54-59`, `:271-273`).
- **The three-reservoir accounting is a counter-model.** Every transfer's `physical_basis_resolved` is false. The initial upper-mantle "exchange counter-reserve" fills the difference between scalar surface mass and an uncalibrated `76 km × 3.08 g/cm3` numerical surface-state envelope (`crust_reservoir.cpp:20-21`) — it is not an upper-mantle mass estimate. It is one spatially unresolved global exchange pool; no mantle transport is resolved and slab packet tables stay empty. Arithmetic closure across the three tables must never be described as physical provenance, solid-volume or phase closure, sediment/subduction coupling, or a resolved mantle/slab crust cycle (`cpp/src/engine/README.md:305-320`).
- **Fail-closed caps are memory-safety limits, not physical limits.** 64 control-volume segments per cell and 8 reciprocal mesh segments per cell (`plate_boundary_segments.cpp:7-8`); 1,024 packets per surface owner, 1,000,000 packets across live reservoirs, and 1,000,000 transfers per step (`types/crust_reservoir.hpp:16-20`). They guard against malformed geometry and resource exhaustion (`cpp/src/engine/README.md:189-191`, `:321-324`).
- **Accelerator parity is explicitly false.** When OpenCL or CUDA is active, the continuous-overlap shadow reduces the exact CPU CSR, checks the result against finite bounds, records telemetry, and **discards** it. CPU geometry, coverage, membership classes, categories, production remap, and scientific state remain authoritative. Complete parity stays false, and the repository notes the development host has no usable OpenCL platform or CUDA device, so only CPU/stub integration and pure reconciliation logic are verified there (`cpp/src/engine/README.md:294-303`).
- **Membership classes are not topology.** The coverage membership-area class ledger coalesces all arrangement atoms with the same sorted source-cell membership; a class may contain disconnected pieces. Connected-fragment topology, physical fate, local pairwise kinematics, slab selection, and subduction polarity all remain unresolved (`cpp/src/engine/README.md:44-47`, `:274-285`).
- **Initial oceanic ages are a procedural graph field.** `multi_source_nominal_ridge_graph_travel_time_v1` uses one global nominal half-rate. It is not reconstructed seafloor creation: local rates, flowlines, convergence/subduction history, and physical creation/destruction provenance remain unresolved. The 200 Ma procedural cap is not a physical maximum (`constants.hpp`, `INITIAL_OCEANIC_CRUST_MAX_AGE_MA`; `cpp/src/engine/README.md:115-132`).
- **The age-depth curve is relative, not absolute.** The implementation changes branches at 70 Ma and offsets the old branch to enforce C0 value continuity; it does not claim derivative continuity or reproduce Parsons & Sclater's absolute-depth datum. A distinct realized thermal-relief state, absolute basement calibration, sediment loading, thermal structure, heat flow, dynamic topography, flexure, and physical dynamics remain unresolved (`cpp/src/engine/README.md:143-165`).
- **The cell-column sea-level solver cannot manufacture realistic continental shelves.** At the 4,096-cell Earth reference a cell is roughly 400 km across, so one scalar elevation mixes land, shelf, slope, and deep ocean. Subcell area–elevation distributions and margin profiles are a design reference, not an implemented model (`cpp/src/engine/README.md:167-175`).
- **Payload size and RSS figures in the engine README are stale.** The quoted `178,764,102` uncompressed JSON bytes and `371,176 KB` maximum RSS were measured at a historical checkpoint; the README states "Current payload size/RSS has not been remeasured" (`cpp/src/engine/README.md:286-292`).
- **`numeric_serialization.cpp` is undocumented in the engine README responsibility table.** It is built (`CMakeLists.txt:113`) and it owns the round-trip serialization contract, but the module list does not mention it.
- **Weak libstdc++ template symbols are exported alongside the intended surface.** The visibility invariant is about `magic_geo::detail`, which is verifiably hidden; the shared library still exports weak STL instantiations as a normal consequence of the toolchain.

## See also

- [Architecture](./04-architecture.md) — where the native core sits in the overall system
- [Installation and Build](./02-installation-and-build.md) — CMake options, CUDA detection, and staging the library
- [Compute Backends (CPU, OpenCL, CUDA)](./09-compute-backends.md) — `ComputeSession`, backend selection, and telemetry
- [Python API](./07-python-api.md) — `generate_world` / `generate_geo_world` and the enrichment layer above `native.py`
- [Configuration Reference](./05-configuration-reference.md) — every field that becomes a `CConfigV3` member
- [World Document Schema](./10-world-schema.md) — the complete key inventory emitted by `serialize_world`
- [Serialization and World Formats](./11-serialization.md) — precision contracts, JSON vs MessagePack
- [Testing and Quality Gates](./18-testing.md) — the Python suite that complements the CTest targets
- [Tectonics and Plates](./features/tectonics-and-plates.md) — the domain behind `tectonics.cpp`
- [Plate Boundary Segment Ledger](./features/plate-boundary-ledger.md) — the evidence boundary in detail
- [Crust Transport and Forward Overlap](./features/crust-transport-and-overlap.md) — the CSR and membership classes
- [Crust Material Shadow and Dry-Rock Reservoirs](./features/crust-material-and-reservoirs.md) — the two non-authoritative counter-models
- [Sediment, Routing and Stratigraphy](./features/sediment-and-stratigraphy.md) — the sediment-interface authority boundary in context
- [Troubleshooting and FAQ](./22-troubleshooting.md) — library-not-found, schema-version, and ABI errors
