# Native engine architecture

The native core is organized around one behavior-preserving pipeline and a
separate serialization boundary. `cpp/src/engine.cpp` is the public C++ facade;
the C ABI remains in `cpp/src/c_api.cpp`.

## Data flow

```text
public generate_world_json / generate_world_msgpack(params, compute_options)
or generate_geo_world_json / generate_geo_world_msgpack(params, compute_options)
  -> validate options/params -> scoped thread policy -> per-generation ComputeSession
  -> simulate_world / simulate_geo_world
       mesh -> tectonics -> ocean/climate/hydrology
       -> erosion and earth-system feedback
       -> environment and water features
       -> settlements/civilization/history (full-world path only)
  -> serialize_world
       summary + entity serializers + process-ledger serializers
  -> optional strict JSON-to-MessagePack transport transcoder
```

`world.hpp` groups the result into `EarthSystemState`, `NaturalArtifacts`, and
`SocietyArtifacts`. This is the handoff between computation and output. Domain
stages must not depend on JSON serializers.

The MessagePack facade intentionally transcodes the canonical JSON document.
This preserves every established decimal-quantization boundary consumed by the
Python enrichers. The C ABI exposes binary as pointer plus byte length and frees
it with `magic_geo_free_buffer`; the supported NUL-terminated JSON symbols are
unchanged.

## Source responsibilities

- `core.cpp`: math, hashing, JSON primitives, parameter checks, and scoped thread policy.
- `messagepack.cpp`: strict, bounded-depth canonical-JSON to standard
  MessagePack transport transcoding.
- `mesh.cpp`: Fibonacci and geodesic mesh construction.
- `tectonics.cpp`: plates, crust, topography, and plate motion.
- `plate_boundary_segments.cpp`: exact directed cross-plate control-volume
  segment identity, geometry, direct Euler kinematics, same-step opening/remapped
  crust witnesses, candidate side pairs, and an explicit unknown physical
  polarity state.
- `crust_transport.cpp`: CPU-authoritative spherical forward-overlap geometry,
  extensive-state remap, raw arrangement diagnostics, and coalesced retained
  area classes keyed by sorted contributing source IDs. A class may contain
  disconnected atomic pieces; it is not a connected topology or fate record.
- `crust_overlap_candidate_fate.cpp`: deterministic, non-allocating crosswalk
  from every multiplicity-two-or-greater membership class to conservative
  same-step boundary plate-pair consensus and endpoint-incidence evidence. It
  emits candidate contributor-CSR roles or an explicit unknown and performs no
  physical polarity, local-fragment, slab, swept-area, reservoir, or state
  mutation.
- `crust_material.cpp`: the non-authoritative persistent sparse dry-rock mass
  shadow. It source-normalizes packet allocation over raw overlap rows, assigns
  the final-edge remainder, preserves canonical origin keys, and records ordered
  unresolved rule sources and proportional provenance-preserving sinks. It does
  not implement solid volume, phase, mantle, slab, or global crust-cycle
  conservation.
- `crust_reservoir.cpp`: the non-authoritative finite three-reservoir dry-rock
  accounting counter-model. It replays rule-derived shadow adjustments as ordered
  surface/mantle proxy transfers while maintaining empty plate-owned slab
  tables; no transfer has a resolved physical basis.
- `oceanic_age_depth.cpp`: the centralized continuity-adjusted relative
  oceanic basement-subsidence curve and its finite, nonnegative age guard.
- `sediment_partition.cpp`: checked mutation primitives for the canonical
  bedrock-surface/mobile-sediment geometry and native aggregation checks for the
  cell-indexed alluvium-versus-bedrock source partitions.
- `ocean.cpp`: volume-constrained sea level and marine connectivity.
- `climate.cpp`: circulation, currents, moisture transport, and climate fields.
- `hydrology.cpp`: water budget, priority flood, drainage, and depression policy.
- `earth_system.cpp`: timestep-scaled sediment transports, feedback summaries,
  maturation-stage coordination, and cell-indexed hillslope/fluvial/glacial
  alluvium-versus-bedrock source-partition depth audits. Their native
  `depth_m * area_km2 / 1000` reductions reconstruct stage volumes; the arrays
  are explicitly neither mass nor provenance claims.
- `environment.cpp`: cryosphere, soils, biomes, landforms, coasts, basins, and ice sheets.
- `water_features.cpp`: lakes, watersheds, and boundary-ring geometry.
- `settlements.cpp`: settlement selection and routes.
- `civilization.cpp`: regions, borders, trade, cultures, languages, and sites.
- `history.cpp`: history, population, conflict, dynasties, snapshots, and calibration checks.
- `pipeline.cpp`: the only complete simulation-stage ordering.
  `simulate_geo_world` uses the same natural sequence and stops before all
  settlement and civilization generators.
- `opencl_compute.cpp`: generation-scoped CPU/OpenCL/CUDA orchestration,
  dynamic OpenCL discovery/resources, automatic fallback, and unified
  telemetry. `cuda_compute.cu` owns native NVIDIA discovery, persistent
  CUDA buffers/stream/events and FP64 kernels. `crust_overlap_shadow.cpp`
  validates a separately named discarded-output FP64 continuous-moment
  reduction over the exact CPU overlap CSR. Production v3 crust transport uses
  the CPU-authoritative exact spherical forward-overlap implementation in
  `crust_transport.cpp`. `cuda_compute_stub.cpp` preserves builds without a CUDA
  toolchain. CPU execution remains the reference path; explicit
  OpenCL/CUDA failures are fatal and only `auto` may fall back.
- `summary.cpp`, `entity_serialization.cpp`, `process_serialization.cpp`, and
  `crust_reservoir_serialization.cpp`: read-only JSON fragments.
- `world_serialization.cpp`: top-level schema ordering and assembly.

The maturation coordinator treats `Params::maturation_timestep_ma` as a
nominal refinement interval relative to the shipped 5 Ma reference step.
Selected continuous reference-step responses are scaled, authoritative
histories carry nominal start/end/duration metadata, and the terminal
cryosphere pass remains a zero-duration endpoint operator. Tectonic, hillslope,
and stream tendencies are evaluated before a combined terrain commit from the
prior stabilized surface/hydrology; routing retains the prior flow graph, and
the terminal cryosphere state is recomputed after stabilization. Exported
metadata explicitly keeps physical time, process-rate calibration, and
whole-coupling timestep convergence false.

Initial oceanic-like ages come from
`multi_source_nominal_ridge_graph_travel_time_v1`, not independent random-old
draws. Positive-rate direct divergent segments with two provisional
oceanic-like sides seed their endpoint cells at age zero. One
segment-length-weighted nominal full spreading rate is halved, and deterministic
multi-source Dijkstra propagates great-circle edge distance divided by that
rate over the oceanic-like neighbor graph. The round-trip
`initial_oceanic_crust_age_ledger` preserves every age, unclamped age, status,
predecessor, origin seed, eligible segment, seed cell, rate operand, area-weighted
summary, and inclusive 20–200 Ma CDF. A reachable age above the procedural cap is
clamped with a distinct status; a component without an active-ridge path gets
the cap with an unresolved status. The identity-overlap initial checkpoint at
`plate_motion_history[0].crust_overlap_ledger.remapped_crust_age_ma_by_cell`
carries all-cell initial crust age and matches the oceanic-age ledger where its
status is nonzero. This is a procedural graph field using one global nominal
rate, not reconstructed seafloor creation: local rates, flowlines,
convergence/subduction history, and physical creation and destruction
provenance remain unresolved.

Replay-critical numerical state is not truncated to the configured display
precision. Initial/final cell crust age, thickness, and density; remapped crust
roots; boundary forcing, transport, process-change, equilibrium, dynamic-relief,
and tectonic-change arrays; and final elevation/water depth use general-format
`max_digits10` serialization and therefore recover the original binary64 value
after JSON parsing. This exact round-trip contract is distinct from the sediment
interface's intentional 10-decimal canonical-state and 8-decimal replay-operand
contract described below.

Oceanic-like cells use a relative thermal-subsidence target based on the young
`350 sqrt(t)` relation and old `3200 exp(-t / 62.8)` shape from
[Parsons and Sclater (1977)](https://doi.org/10.1029/JB082i005p00803). The
implementation changes branches at 70 Ma and offsets the old branch to enforce
C0 value continuity; it does not claim derivative continuity or reproduce the
paper's absolute-depth datum. Each plate-motion record preserves old and new
local isostatic equilibria, old and new thermal targets, their gain-1
differences, unbounded and bounded dynamic relief, and the total tectonic
elevation change at binary64 round-trip precision. Full isostatic and thermal
target differences are applied outside the empirical dynamic clamp; only
`unbounded_dynamic_relief_change_m` is clamped to `[-180, 220]` m.
`thermal_equilibrium_change_m` is the sole serialized thermal-change array, and
`tectonic_elevation_change_m_by_cell = isostatic_equilibrium_change_m +
thermal_equilibrium_change_m + bounded_dynamic_relief_change_m`. Independent
replay verifies the operands, gain-1 changes, dynamic formula/clamp, application,
composition, and zero unapplied equilibrium residual. The quasi-static choice
uses the timescale separation between the nominal 5 Ma reference interval and
3–4 ka degree-2-to-20 viscoelastic relaxation estimates from
[O'Connell (1971)](https://doi.org/10.1111/j.1365-246X.1971.tb01823.x); it does
not make the nominal interval or operator physically time-calibrated. A distinct
realized thermal-relief state, absolute basement calibration, sediment loading,
thermal structure, heat flow, dynamic topography, flexure, and physical dynamics
remain unresolved.

The cell-column sea-level solver cannot manufacture realistic continental
shelves by lowering whole margin cells. At the 4,096-cell Earth reference a
cell is roughly 400 km across, so one scalar elevation mixes land, shelf, slope,
and deep ocean. The next bathymetric architecture must carry conservative
subcell area–elevation distributions and margin shelf–slope–rise profiles, flood
fractional cell area/volume, and retain subcell narrow-channel connectivity.
[Goswami et al. (2015)](https://doi.org/10.5194/gmd-8-2735-2015) is the cited
reference for combining plate cooling, sediment, and generalized continental
margin structures; it is a design reference, not an implemented model claim.

## Exact directed plate-boundary ledger

`build_plate_boundary_segments` constructs one canonical record per cross-plate
**reciprocal control-volume segment**. It does not collapse by neighbor pair, so
the two physical pieces that a geodesic dual can place between the same cells
remain distinct. The lower cell ID is `left_cell_id`; its counter-clockwise edge
supplies start and end, the tangent follows that direction, and the transverse
normal must point from the left cell toward the right cell. `mesh_segment_id` is
the stable `(left_cell_id, left_edge_index)`-ordered index over all reciprocal
mesh segments before filtering, while `segment_id` is the contiguous per-step
cross-plate index. Native construction requires exactly one reverse-endpoint
reciprocal edge, a unit Euler axis, nonnegative finite intrinsic speed, valid
opening/remapped crust arrays, at most 64 control-volume segments per cell, and
at most eight reciprocal mesh segments per cell globally. The caps are
malformed-geometry/resource guards, not physical limits.

The ledger uses intrinsic Euler velocities
`axis * intrinsic_speed x segment_midpoint` to derive dimensionless opening,
convergence, and slip indices and the direct unsmoothed class. Its vectors and
rates labeled km/Ma multiply those intrinsic velocities by
`radius_km * plate_motion_scale_deg_per_step * pi/180 / 5 Ma`. That conversion
is a nominal reference-step scale, not a calibrated physical velocity. The
same-step `CrustTransportPlan` supplies remapped pre-process age, thickness,
density, type, and lithology for each side. Exactly zero age plus zero thickness
means that remap supplied no opening crust volume; retained category and density
values in that case are fixed-shape unavailable-state sentinels, and `opening_oceanic_like` is
false.

Strict Python replay deliberately ignores the smoothed per-cell boundary
arrays. Starting from high-precision centers, axes, and intrinsic speeds, it
reconstructs Rodrigues center transitions, nearest-center cell assignments,
reciprocal segment identity/orientation, geometry, velocities, signed rates and
indices, strengths/classes, and opening-crust/polarity-candidate fields. The
ledger is authoritative for segment geometry and direct unsmoothed kinematics,
but the degree-normalized smoothed cell forcing drives the tectonic rules and
does not consume it. A sole oceanic-like side at a convergent
segment supplies candidate subducting and inverse overriding sides only.
Thresholded normal convergence is independent of the dominant class, so an
oblique transform-dominant segment is not discarded. The physical sides remain
`unknown`, the decision source remains `none`, and the confidence remains zero;
GPGIM left/right supplied polarity names the overriding side, but its feature
direction must first be aligned to the canonical segment before selecting the
opposite side as subducting. Physical subduction polarity, slab selection,
slab geometry/transfer, and material fate remain false. This split is
consistent with the separate reconstruction, boundary-statistic, and explicit
polarity concepts documented by [GPlates](https://www.gplates.org/docs/user-manual/reconstructions/),
[pyGPlates](https://www.gplates.org/docs/pygplates/generated/pygplates.plateboundarystatistic),
and [GPGIM](https://www.gplates.org/docs/gpgim/), and with the directed
left/right segment representation of [Bird (2003)](https://doi.org/10.1029/2001GC000252).

Every native terrain/material mutation preserves one interface contract:
`bedrock_surface_elevation_m` and nonnegative `sediment_thickness_m` are the
canonical fields, while
`elevation_m = bedrock_surface_elevation_m + sediment_thickness_m` is derived.
The bedrock field is the top of nonmobile bedrock below the mobile layer, not a
Moho or stratigraphic-basement interpretation. Initialization subtracts mobile
thickness from the opening surface. The shared material-update primitive uses
`bedrock' = bedrock + vertical_displacement - bedrock_erosion` and
`sediment' = sediment - alluvium_entrainment + deposition`, rejects entrainment
beyond the opening mobile inventory, and rederives elevation. It is used for
the combined tectonic/hillslope/fluvial commit, applied numeric-breach
excavation and redeposition, and terminal glacial transport. Sea-level solving
uses the datum-shift primitive, which moves bedrock elevation and the derived
surface together without changing mobile thickness. Native checks run after
each path; the strict Python replay separately rebuilds final bedrock from
initial terrain and linked plate-motion, sediment, numeric-correction, glacial,
and sea-level histories before checking final bedrock, mobile thickness, and
surface closure. Fluvial stages retain a complete cell-indexed routing-input
snapshot at round-trip precision; replay derives the acyclic active graph,
environmental branch, terminal footprint (including inactive targets),
proportional allocation, and aggregate volumes from those inputs. Selected
numeric-breach deposition capacity, target order, and depths are reconstructed
the same way. Model metadata declares 10-decimal canonical-state serialization,
an 8-decimal minimum for
replay operands, and the decimal-quantization forward-error model independently
of general display precision; it must keep dry-rock mass, sediment density,
porosity, compaction, grain provenance, and chemical weathering resolution
false.

Shared records are private to the native target under `types/`. Constants and
schema-name tables live separately from those records. `internal.hpp` is the
private cross-translation-unit interface; none of its symbols are exported from
the shared library.

The shadow material history is deliberately separate from the authoritative
crust state and raw-overlap inventory. Every step links its opening packet table
exactly to the prior closing table. Source-normalized advection conserves each
packet within the native forward-error bound; the residual against raw
density-weighted overlap transport remains serialized as a geometry diagnostic.
Rules execute in native order. Positive implied-mass deltas merge a packet keyed
as `unresolved_rule_source/current_plate/reason`; negative deltas remove all
current keys proportionally, assigning arithmetic correction to the largest
packet with lowest-key tie-break. Empty transported rows and exact exhaustion
remain valid intermediate states when a later positive bound rule reseeds them.
Serializers and summaries must preserve the explicit false authority, physical
source/sink, material-provenance, solid-volume, phase, mass-weighted-age,
mantle, slab, and global crust-cycle flags.

The overlap arrangement retains raw line/atom telemetry separately from
`coverage_membership_area_class_ledger`. The latter coalesces all atoms with
the same sorted source-cell membership, stores their summed area and source
plate IDs at the transport source snapshot, and chooses the representative of
the largest atomic piece with a lowest-XYZ tie-break. Its class CSR reconstructs
each overlap edge and the destination gap/union/excess and multiplicity
histogram. Coalescing means the class does not preserve connected-fragment
topology. The membership-class metadata must continue to keep topology,
physical fate, local pairwise kinematics, slab selection, and subduction
polarity unresolved; the separate segment ledger supplies direct local
kinematic evidence without upgrading those other claims. The geometry-stable
4,096-cell, seven-step reference reduces
`3,483,059` raw atoms to `109,777` classes (about `31.7x`), with at most 14
classes per destination. At the historical pre-initial-age/expanded-round-trip
checkpoint, with the exact segment, candidate-crosswalk, sediment, and
thermal-target replay witnesses, it wrote `178,764,102` uncompressed JSON bytes
and reached `371,176 KB` maximum RSS in the direct native process. Current
payload size/RSS has not been remeasured.

When OpenCL or CUDA is active, the continuous-overlap shadow launches one
ordered FP64 work item per destination over the exact CPU CSR. It reconstructs
three incoming moments and derived thickness/density/age, checks the returned
values against finite operand/operation-count bounds, records dedicated
backend telemetry, and discards the result. CPU geometry, coverage,
membership classes, categories, production remap, and scientific state remain
authoritative. Complete parity stays false. This host has no usable OpenCL
platform or CUDA compiler/device, so only CPU/stub integration and pure
reconciliation logic are verified here; device-enabled compilation/execution
belongs in the accelerator lane.

The finite accounting history is deliberately downstream of the material
shadow. Packet tables are owner-offset CSR keyed by
`(origin_domain_id, origin_kind_id, origin_plate_id)`. The initial
upper-mantle exchange counter-reserve fills the difference between scalar
surface mass and the uncalibrated `76 km * 3.08 g/cm3` numerical surface-state
envelope; it is not an upper-mantle mass estimate. Reason-major proxy
transactions apply all surface sinks in ascending cell/key order before all
surface sources. Surface sinks withdraw proportionally; source transactions
consume the initial exchange-reserve packet first, then the largest packet with
lowest-key tie-break. This is one spatially unresolved global exchange pool
shared by every cell: instantaneous global access is assumed while packet
origin keys remain distinct, and no mantle transport is resolved. Slab packet
tables remain empty, and every transfer's
`physical_basis_resolved` value is false. Arithmetic closure across the three
tables must never be described as physical provenance, solid-volume or phase
closure, sediment/subduction coupling, or a resolved mantle/slab crust cycle.
Packet creation and transfer append paths enforce fail-closed operational caps:
1,024 packets per surface owner, 1,000,000 packets across live reservoirs, and
1,000,000 transfers per step. The model exports these constants and peak usage.
They are numerical memory-safety limits, not physical flux or capacity limits.

## Invariants

- Preserve pipeline order: many stages deliberately enrich the shared `Cell`
  state, and later stages consume those fields.
- Preserve the sediment-interface authority boundary: mutation code updates the
  two canonical interface fields through the checked helpers and derives
  `elevation_m`; it must not independently mutate all three fields.
- Preserve plate-boundary evidence boundaries: exact segment geometry and direct
  unsmoothed kinematics are authoritative, nominal km/Ma is uncalibrated, the
  oceanic-side result is only a subducting/overriding candidate pair, physical
  sides remain explicitly unknown, and the ledger must not be described as
  driving smoothed cell forcing or slab transfers until those consumers are implemented
  and independently validated.
- Preserve RNG consumption, OpenMP schedules, floating-point expression order,
  serializer key order, and precision unless a schema/behavior change is intended.
- Keep the v1 `CConfig` and v2 `CConfigV2` field order, types, and 64-bit sizes
  stable. `Params` may grow at the tail for source-level C++ use; C++ clients
  rebuild when it changes. The unversioned C++ overload and v1 C entry point always
  use CPU. Compute controls belong to `ComputeOptions`/`CConfigV2`; the nominal
  timestep belongs to `CConfigV3`. Python mirrors every C layout via `ctypes`.
- Keep all declared public symbols visible and all `magic_geo::detail`
  symbols hidden.
- Preserve backend truthfulness: `cpu` must not initialize or probe CUDA or
  OpenCL, below-threshold `auto` CPU selection is not a fallback, explicit
  `opencl`/`cuda` must never silently fall back, and `auto` must never select a
  CPU OpenCL device. Automatic eligibility uses the generated mesh size, not
  only the requested size. Qualifying FP64 devices must expose the required
  numerical/runtime behavior. Serialized telemetry must identify actual
  dispatch counts, work sizes, transfer bytes/timings, allocations, device
  capabilities, and any automatic fallback reason.
- Explicit OpenMP thread counts are generation-scoped and restore the calling
  thread's prior ICV on every exit; `threads=0` leaves host policy untouched.
- New domain stages belong before `serialize_world`; serializers must be
  read-only over `GeneratedWorld`.

`cpp/tests/native_api_test.cpp` protects the public boundary and concurrent
session behavior. `c_api_v1_client_test.cpp` compiles against a frozen layout
without including the current header. The Python suite provides the end-to-end
physics, replay, schema, and mutation-rejection gates.
