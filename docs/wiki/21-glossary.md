# Glossary

[Wiki home](./README.md) > Glossary

This page defines every domain term a reader meets in the magic-geo codebase, with the exact source location where the term is implemented or serialized, and a link to the wiki page that covers it in depth. The vocabulary is unusually load-bearing here because the project deliberately separates *authoritative* simulation state from *non-authoritative* audit shadows, counter-models, and diagnostics, and marks many physical claims explicitly unresolved in the serialized document itself. Definitions below preserve that separation exactly as the source states it; a term that names a diagnostic is described as a diagnostic, and a `false` resolution flag is reported as `false`. Numbers, defaults, field names, and formulas are taken from the files cited inline.

## On this page

- [How to read this glossary](#how-to-read-this-glossary)
- [Index of terms](#index-of-terms)
- [Terms A–C](#terms-ac)
- [Terms D–G](#terms-dg)
- [Terms H–M](#terms-hm)
- [Terms N–R](#terms-nr)
- [Terms S–Z](#terms-sz)
- [Enumerated value vocabularies](#enumerated-value-vocabularies)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

---

## How to read this glossary

Three epistemic tiers recur throughout the codebase and throughout this glossary. They are not stylistic; each is encoded as an explicit flag or naming convention in the serialized world document.

| Tier | What it means | How it is marked in the output | Example |
| --- | --- | --- | --- |
| **Authoritative** | The value *is* the simulation state; downstream stages read it and later replay reconstructs it | No negative flag; often paired with an affirmative flag such as `authoritative_interface_geometry: true` (`cpp/src/engine/process_serialization.cpp:1856`) | `cells[].bedrock_surface_elevation_m`, the forward-overlap CSR |
| **Non-authoritative** | A parallel bookkeeping structure that audits authoritative state but never drives it | `authoritative_for_cell_state: false` (`cpp/src/engine/process_serialization.cpp:206`, `cpp/src/engine/crust_reservoir_serialization.cpp:181`) | crust material shadow, dry-rock accounting counter-model |
| **Unresolved** | A physical claim the model explicitly does *not* make | A `*_resolved: false` boolean, e.g. `physical_source_sink_resolved`, `subduction_polarity_resolved`, `physical_time_resolved` | subduction polarity, mass provenance, physical time |

A fourth convention matters for validation reading: a check whose candidate population is empty is reported as `not_applicable`, never as a pass. See [`not_applicable`](#not_applicable).

Two more conventions used below:

| Convention | Meaning |
| --- | --- |
| `model_type` / `format` strings ending in `_v1`, `_v2`, `_v3` | Versioned, self-describing model identity embedded in the document, e.g. `spherical_voronoi_control_volume_v1`, `rotating_voronoi_plate_domains_v3` |
| "nominal" | Ordered and dimensionally labelled but **not** calibrated to physical time or physical rate (`physical_time_resolved: false`, `nominal_time_calibrated: false`, `cpp/src/engine/process_serialization.cpp:2083-2084`) |

---

## Index of terms

| Term | One-line gloss | Primary source | Wiki page |
| --- | --- | --- | --- |
| [atom](#atom) | One raw fragment of the destination-local overlap line arrangement | `cpp/src/engine/crust_transport.cpp:50` | [Crust Transport and Forward Overlap](./features/crust-transport-and-overlap.md) |
| [backend telemetry](#backend-telemetry) | The top-level `backend` object describing actual compute dispatch | `cpp/src/opencl_compute.cpp:2033` | [Compute Backends](./09-compute-backends.md) |
| [bedrock surface elevation](#bedrock-surface-elevation) | Canonical top of nonmobile bedrock beneath the mobile layer | `cpp/src/engine/process_serialization.cpp:1841` | [Sediment, Routing and Stratigraphy](./features/sediment-and-stratigraphy.md) |
| [boundary segment](#boundary-segment) | One directed cross-plate reciprocal control-volume contact | `cpp/src/engine/plate_boundary_segments.cpp:430` | [Plate Boundary Segment Ledger](./features/plate-boundary-ledger.md) |
| [calibration target](#calibration-target) | An external-dataset-derived `[target_min, target_max]` range for one world metric | `src/magic_geo/geo_validation_suite/empirical.py:584` | [Calibration](./14-calibration.md) |
| [cell](#cell) | One spherical control volume and its full per-cell state record | `cpp/src/engine/types/core.hpp:35` | [Mesh and Geometry](./features/mesh-and-geometry.md) |
| [control volume](#control-volume) | The exact spherical polygon owned by a cell | `cpp/src/engine/mesh.cpp:455` | [Mesh and Geometry](./features/mesh-and-geometry.md) |
| [coverage CSR](#coverage-csr) | Destination-major sparse ledger of source→destination overlap areas | `cpp/src/engine/types/earth_system.hpp:562` | [Crust Transport and Forward Overlap](./features/crust-transport-and-overlap.md) |
| [coverage vs fit](#coverage-vs-fit) | Two independent calibration verdicts: metric availability vs in-range | `src/magic_geo/calibration/evaluate.py:474` | [Calibration](./14-calibration.md) |
| [crust transport plan](#crust-transport-plan) | The whole per-step overlap + remap structure | `cpp/src/engine/types/earth_system.hpp:558` | [Crust Transport and Forward Overlap](./features/crust-transport-and-overlap.md) |
| [drainage area exponent](#drainage-area-exponent) | `erosion.drainage_exponent`, the *m* in the stream-power relation | `src/magic_geo/config.py:394` | [Erosion, Maturation and Landscape Evolution](./features/erosion-and-maturation.md) |
| [dry-rock accounting](#dry-rock-accounting) | Finite three-reservoir kg counter-model over the material shadow | `cpp/src/engine/crust_reservoir_serialization.cpp:108` | [Crust Material Shadow and Dry-Rock Reservoirs](./features/crust-material-and-reservoirs.md) |
| [dual mesh](#dual-mesh) | The geodesic backend's cell polygons, dual to the primal triangulation | `cpp/src/engine/mesh.cpp:963` | [Mesh and Geometry](./features/mesh-and-geometry.md) |
| [dynamic relief](#dynamic-relief) | The only clamped term in the per-step tectonic elevation change | `cpp/src/engine/tectonics.cpp:1632` | [Topography, Isostasy and Thermal Subsidence](./features/topography-and-isostasy.md) |
| [ecotone](#ecotone) | A named transitional habitat between two biomes | `src/magic_geo/biome_ecotones.py:7` | [Biomes, Ecosystems and Disturbance](./features/biomes-and-ecology.md) |
| [endorheic basin](#endorheic-basin) | A watershed whose outlet is not the ocean | `cpp/src/engine/water_features.cpp:321` | [Hydrology, Rivers and Lakes](./features/hydrology-and-rivers.md) |
| [Euler pole / Euler axis](#euler-pole--euler-axis) | Unit rotation axis of a plate | `cpp/src/engine/types/core.hpp:16` | [Tectonics and Plates](./features/tectonics-and-plates.md) |
| [exchange reserve](#exchange-reserve) | The initial numerical upper-mantle counter-reserve | `cpp/src/engine/crust_reservoir.cpp:20-21` | [Crust Material Shadow and Dry-Rock Reservoirs](./features/crust-material-and-reservoirs.md) |
| [Fibonacci sphere](#fibonacci-sphere) | Default mesh backend: Fibonacci site set + spherical Voronoi cells | `cpp/src/engine/mesh.cpp:776` | [Mesh and Geometry](./features/mesh-and-geometry.md) |
| [forward overlap](#forward-overlap) | Rotate every source polygon forward, intersect with fixed destinations | `cpp/src/engine/process_serialization.cpp:3534` | [Crust Transport and Forward Overlap](./features/crust-transport-and-overlap.md) |
| [geodesic icosahedron](#geodesic-icosahedron) | Alternate mesh backend: subdivided icosahedron, `10f² + 2` cells | `cpp/src/engine/mesh.cpp:909` | [Mesh and Geometry](./features/mesh-and-geometry.md) |
| [geologic depression](#geologic-depression) | A closed basin the model treats as real, not a numerical artefact | `cpp/src/engine/hydrology.cpp:213` | [Hydrology, Rivers and Lakes](./features/hydrology-and-rivers.md) |
| [hillslope diffusion](#hillslope-diffusion) | `erosion.hillslope_diffusion`, the downslope neighbour-pair transport coefficient | `src/magic_geo/config.py:406` | [Erosion, Maturation and Landscape Evolution](./features/erosion-and-maturation.md) |
| [intrinsic speed](#intrinsic-speed) | Dimensionless per-plate procedural angular-speed index | `cpp/src/engine/types/core.hpp:19` | [Tectonics and Plates](./features/tectonics-and-plates.md) |
| [isostatic equilibrium](#isostatic-equilibrium) | Local crust-thickness/density equilibrium elevation target | `cpp/src/engine/tectonics.cpp:574` | [Topography, Isostasy and Thermal Subsidence](./features/topography-and-isostasy.md) |
| [layer](#layer) | Three distinct senses: debugger layer, contract layer, stratigraphic layer | `docs/layers_reference.md:11` | [Debug Exports and Visualization](./16-debug-and-visualization.md) |
| [layer contract](#layer-contract) | One of 14 phase-ordered evidence contracts over natural generation | `src/magic_geo/geo_layer_contracts.py:26` | [Validation](./12-validation.md) |
| [manifest revision](#manifest-revision) | Opaque token identifying one immutable debug-cache manifest | `src/magic_geo/debug_server.py:564` | [Debug Exports and Visualization](./16-debug-and-visualization.md) |
| [material shadow](#material-shadow) | Non-authoritative persistent sparse dry-rock mass packet ledger | `cpp/src/engine/process_serialization.cpp:167` | [Crust Material Shadow and Dry-Rock Reservoirs](./features/crust-material-and-reservoirs.md) |
| [maturation stage](#maturation-stage) | One coupled tectonics→climate→hydrology→erosion transition | `cpp/src/engine/process_serialization.cpp:2091` | [Erosion, Maturation and Landscape Evolution](./features/erosion-and-maturation.md) |
| [membership area class](#membership-area-class) | Coalesced destination area sharing one sorted contributing-source set | `cpp/src/engine/process_serialization.cpp:3649` | [Crust Transport and Forward Overlap](./features/crust-transport-and-overlap.md) |
| [mesh segment id](#mesh-segment-id) | Stable index over all reciprocal mesh segments before cross-plate filtering | `cpp/src/engine/plate_boundary_segments.cpp:331` | [Plate Boundary Segment Ledger](./features/plate-boundary-ledger.md) |
| [mobile sediment](#mobile-sediment) | The nonnegative entrainable sediment column above bedrock | `cpp/src/engine/process_serialization.cpp:1838` | [Sediment, Routing and Stratigraphy](./features/sediment-and-stratigraphy.md) |
| [nominal timestep](#nominal-timestep) | `erosion.maturation_timestep_ma`, uncalibrated Ma per transition | `src/magic_geo/config.py:382` | [Configuration Reference](./05-configuration-reference.md) |
| [non-authoritative](#non-authoritative) | Audits authoritative state, never drives it | `cpp/src/engine/process_serialization.cpp:206` | [Architecture](./04-architecture.md) |
| [`not_applicable`](#not_applicable) | Validation status for an absent candidate population | `src/magic_geo/geo_validation.py:283` | [Validation](./12-validation.md) |
| [opening / convergence / slip index](#opening--convergence--slip-index) | Dimensionless normal/tangential components of relative Euler velocity | `cpp/src/engine/plate_boundary_segments.cpp:415-418` | [Plate Boundary Segment Ledger](./features/plate-boundary-ledger.md) |
| [packet](#packet) | One origin-keyed quantum of dry-rock mass in a shadow or reservoir table | `cpp/src/engine/types/earth_system.hpp:670` | [Crust Material Shadow and Dry-Rock Reservoirs](./features/crust-material-and-reservoirs.md) |
| [permafrost](#permafrost) | Diagnostic ground-frost extent/class enrichment | `src/magic_geo/permafrost_diagnostics.py:7` | [Cryosphere](./features/cryosphere.md) |
| [plate domain](#plate-domain) | The set of cells currently assigned to one plate | `cpp/src/engine/process_serialization.cpp:2684` | [Tectonics and Plates](./features/tectonics-and-plates.md) |
| [priority flood](#priority-flood) | Min-heap depression-filling / spill-elevation solve | `cpp/src/engine/hydrology.cpp:231` | [Hydrology, Rivers and Lakes](./features/hydrology-and-rivers.md) |
| [replay validator](#replay-validator) | Independent Python reconstruction of a native invariant | `src/magic_geo/geo_validation_physics.py:2495` | [Validation](./12-validation.md) |
| [reservoir](#reservoir) | One of the three dry-rock accounting compartments | `cpp/src/engine/crust_reservoir_serialization.cpp:118` | [Crust Material Shadow and Dry-Rock Reservoirs](./features/crust-material-and-reservoirs.md) |
| [sediment interface contract](#sediment-interface-contract) | The two-canonical-field / one-derived-field mutation rule | `cpp/src/engine/process_serialization.cpp:1836` | [Sediment, Routing and Stratigraphy](./features/sediment-and-stratigraphy.md) |
| [shadow kernel](#shadow-kernel) | Accelerator FP64 reduction whose output is checked and discarded | `cpp/src/opencl_compute.cpp:622` | [Compute Backends](./09-compute-backends.md) |
| [stencil neighbors](#stencil-neighbors) | `cells[].neighbors`, the process adjacency graph | `src/magic_geo/config.py:250` | [Mesh and Geometry](./features/mesh-and-geometry.md) |
| [stream power](#stream-power) | Fluvial incision response from drainage and slope | `cpp/src/engine/earth_system.cpp:984` | [Erosion, Maturation and Landscape Evolution](./features/erosion-and-maturation.md) |
| [thermal subsidence target](#thermal-subsidence-target) | Relative oceanic age–depth basement target | `cpp/src/engine/oceanic_age_depth.cpp:5` | [Topography, Isostasy and Thermal Subsidence](./features/topography-and-isostasy.md) |
| [unresolved claim](#unresolved-claim) | A physical statement the document explicitly declines to make | `src/magic_geo/geo_validation.py:28` | [Project Overview](./01-overview.md) |

---

## Terms A–C

### atom

One **raw fragment** of the destination-local line arrangement produced when forward-rotated source control volumes are clipped into a destination cell's gnomonic chart. Every atom carries an integer coverage multiplicity (how many source polygons cover it) and belongs to exactly one destination cell. Atoms are counted, not stored individually: `coverage_arrangement_line_count_by_cell` and `coverage_arrangement_fragment_count_by_cell` are per-destination raw telemetry (`cpp/src/engine/types/earth_system.hpp:575-576`), and the construction aborts if one destination exceeds `COVERAGE_ARRANGEMENT_LOCAL_FRAGMENT_LIMIT = 16384` (`cpp/src/engine/crust_transport.cpp:50`; also declared in metadata as `maximum_coverage_arrangement_fragments_per_cell`, `cpp/src/engine/process_serialization.cpp:3218`).

Atoms sharing an identical sorted contributing-source set are coalesced into a [membership area class](#membership-area-class); the class representative is the vertex mean of the *largest atomic piece*, with a lowest-XYZ tie-break (`representative_model = largest_atomic_arrangement_piece_unprojected_vertex_mean_lowest_xyz_tie_v1`, `cpp/src/engine/process_serialization.cpp:3656`).

Reported scale on the geometry-stable 4,096-cell, seven-step reference: `3,503,886` raw atoms reduce to `111,022` classes (about `31.6x`), with at most 14 classes per destination (`cpp/src/engine/README.md:286-289`). `docs/geo_generation_maturation_deep_audit.md:406` reports a different measurement of the same style of reference (`3,483,059` atoms → `109,777` classes, about `31.7x`); the two documents do not agree numerically and neither has been re-measured here. The repository states that "the local atom cap lacks exhaustive worst-case proof" (`README.md:347`), and that the recorded stress cases "are not an exhaustive combinatorial or worst-case proof of the bound" (`docs/geo_generation_maturation_deep_audit.md:412`).

See [Crust Transport and Forward Overlap](./features/crust-transport-and-overlap.md).

### backend telemetry

The top-level `backend` object of the world document, emitted by `ComputeSession::Impl::json()` (`cpp/src/opencl_compute.cpp:2033`) and embedded by `serialize_world`. It is the machine-readable record of what the compute layer *actually did*, not what was requested. Representative fields:

| Field | Meaning |
| --- | --- |
| `requested_backend` | The configured `compute.backend` (`auto`, `cpu`, `opencl`, `cuda`) |
| `selected_backend` / `initial_selected_backend` / `active_backend` | What was chosen, what was chosen first, and `hybrid` when a fallback occurred after accelerator dispatches |
| `backend_selection_reason` | Why that selection happened |
| `backend_scope` | Literal `accelerated_native_kernels_not_end_to_end_pipeline` (`cpp/src/opencl_compute.cpp:2065`) |
| `crust_transport_execution_backend` | Literal `cpu` — crust transport is always CPU-authoritative (`cpp/src/opencl_compute.cpp:2071`) |
| `crust_transport_accelerator_dispatch_count` | Literal `0` (`cpp/src/opencl_compute.cpp:2083`) |
| `crust_overlap_continuous_shadow_*` | Dispatch counts, validated-transition counts, failure counts, and validation status of the [shadow kernel](#shadow-kernel) |

The engine invariant is "backend truthfulness": `cpu` must not initialize or probe CUDA or OpenCL; below-threshold `auto` CPU selection is not a fallback; explicit `opencl`/`cuda` must never silently fall back; `auto` must never select a CPU OpenCL device (`cpp/src/engine/README.md:348-355`).

See [Compute Backends](./09-compute-backends.md).

### bedrock surface elevation

`cells[].bedrock_surface_elevation_m` — one of the **two canonical fields** of the [sediment interface contract](#sediment-interface-contract). Semantics are declared in the document itself: `top_of_nonmobile_bedrock_below_mobile_sediment_not_moho_or_stratigraphic_basement` (`cpp/src/engine/process_serialization.cpp:1841-1842`). It is initialized as `elevation_m - sediment_thickness_m` (`cpp/src/engine/sediment_partition.cpp:103-107`), and thereafter only moves through the two checked primitives:

```
bedrock' = bedrock + vertical_displacement_m - bedrock_erosion_depth_m     # material change
bedrock' = bedrock - sea_level_adjustment_m                                # datum shift
```

(`cpp/src/engine/process_serialization.cpp:1847-1850`). Serialized at `surface_precision = max(10, float_precision)` decimal places; the model declares `canonical_state_serialization_decimal_places = 10` (`cpp/src/engine/process_serialization.cpp:1853`).

It is explicitly **not** a Moho or stratigraphic-basement interpretation, and carries no dry-rock mass, sediment density, porosity, compaction, grain-provenance, or chemical-weathering resolution (`cpp/src/engine/process_serialization.cpp:1860-1865`, all `false`).

See [Sediment, Routing and Stratigraphy](./features/sediment-and-stratigraphy.md).

### boundary segment

One canonical record per **cross-plate reciprocal control-volume segment**: the exact shared great-circle edge between two adjacent cells whose plate assignments differ. Built by `build_plate_boundary_segments` (`cpp/src/engine/plate_boundary_segments.cpp:176`) and serialized as `plate_motion_history[].boundary_segments[]` (67 fields, emitted at `cpp/src/engine/process_serialization.cpp:4131-4317`).

Identity and orientation rules:

| Rule | Source |
| --- | --- |
| The lower cell ID is `left_cell_id`; its counter-clockwise edge supplies start and end | `cpp/src/engine/README.md:182-184` |
| The tangent follows that direction; the transverse normal points from left cell toward right cell | `cpp/src/engine/README.md:184-186` |
| Segments are **not** collapsed by neighbour pair, so two physical pieces between the same cells stay distinct | `cpp/src/engine/README.md:180-182` |
| Construction requires exactly one reverse-endpoint reciprocal edge | `cpp/src/engine/plate_boundary_segments.cpp:323-329` |

Fail-closed operational caps: `MAX_CONTROL_VOLUME_SEGMENTS_PER_CELL = 64` and `MAX_RECIPROCAL_MESH_SEGMENTS_PER_CELL = 8` (`cpp/src/engine/plate_boundary_segments.cpp:7-8`). These are malformed-geometry / resource guards, not physical limits (`cpp/src/engine/README.md:190-191`).

The ledger is authoritative for segment geometry and direct unsmoothed kinematics. It **does not** drive the smoothed per-cell boundary forcing that actually runs the tectonic rules, and it selects no slab: `physical_polarity_status` stays `unknown`, `physical_polarity_source` stays `none` (`cpp/src/engine/README.md:210-219`).

See [Plate Boundary Segment Ledger](./features/plate-boundary-ledger.md).

### calibration target

One entry of an external empirical bundle: a world metric name plus a `[target_min, target_max]` range derived from a real-Earth dataset, carrying full source provenance. Bundles are loaded with strict unknown-field rejection (`src/magic_geo/geo_validation_suite/empirical.py:584-598`).

Target object — the 14 permitted keys:

| Key | Role |
| --- | --- |
| `source_id` | Must name a declared source in the same bundle |
| `metric` | World-side metric name; must be unique in the bundle |
| `source_metric` | Dataset-side metric name |
| `source_value` | The measured dataset value the range was built around |
| `target_min`, `target_max` | The acceptance range (inverted ranges rejected) |
| `tolerance_basis` | Free text explaining how the range was chosen |
| `source_statistic`, `source_processing`, `source_variable_units` | Derivation description |
| `source_sample_cell_count`, `source_sample_record_count`, `source_sample_neighbor_count` | Sampling metadata |
| `source_minimum_upstream_area_km2` | Basin-selection threshold for river targets |

Source objects allow 18 provenance keys (`dataset`, `layer`, `source` required; `source_sha256` / `source_archive_sha256` must be SHA-256), `src/magic_geo/geo_validation_suite/empirical.py:529-548`.

The checked-in bundle `configs/geo_validation_earth_empirical_targets.json` is `canonical_earth_empirical_targets_v2`: **7 sources** (`etopo_2022`, `hydrobasins_level3`, `hydrorivers_v10`, `natural_earth_110m`, `seton_2020_oceanic_age`, `worldclim_prec`, `worldclim_tavg`) and **22 targets**.

Scoring uses `score_range(value, min, max)`: `1.0` inside the range, otherwise `1 - distance/width` clamped to `[0, 1]` with `width` floored at `1e-9` (`src/magic_geo/calibration/evaluate.py:14-23`).

See [Calibration Against Real-Earth Data](./14-calibration.md) and [Geo Validation Suite](./13-geo-validation-suite.md).

### cell

The atomic unit of the simulation: one spherical **[control volume](#control-volume)** together with its complete per-cell state record. In C++ it is `struct Cell` (`cpp/src/engine/types/core.hpp:35`); in the world document it is one element of the `cells[]` array.

| Aspect | Value | Source |
| --- | --- | --- |
| Count | `mesh.cell_count`, default `4096`, range `[128, 200000]` | `src/magic_geo/config.py:244` |
| Identity | `id` in `[0, cell_count-1]`; the primary key every table joins on | `docs/layers_reference.md:106` |
| Geometry | `position_3d` (unit sphere), `normal_3d` (aliases the same vector), `lat_deg`, `lon_deg`, `area_km2`, `control_volume_vertices_3d`, `control_volume_edge_neighbor_ids` | `cpp/src/engine/entity_serialization.cpp` |
| Process adjacency | `neighbors` — see [stencil neighbors](#stencil-neighbors) | `src/magic_geo/config.py:250` |
| Serialized field count | 155 fields in full-world mode; 151 in geo-only, where 4 civilization fields (`culture_region_id`, `language_region_id`, `political_region_id`, `settlement_score`) are stripped | `src/magic_geo/api.py` |
| Suppression | `output.include_cells: false` emits `cells: []` (key still present) | `src/magic_geo/config.py:446` |

A cell is a **coarse** object. At the 4,096-cell Earth reference a cell is roughly 400 km across, so one scalar `elevation_m` mixes land, shelf, slope, and deep ocean; the sea-level solver "cannot manufacture realistic continental shelves by lowering whole margin cells" (`cpp/src/engine/README.md:167-172`).

See [Mesh and Geometry](./features/mesh-and-geometry.md) and [World Document Schema](./10-world-schema.md).

### control volume

The exact spherical polygon a cell owns. It is the finite-volume partition of the sphere and the geometric basis for conservative crust remapping. Named by the top-level `cell_area_model` key:

| `cell_area_model` | Backend | Construction |
| --- | --- | --- |
| `spherical_voronoi_control_volume_v1` | `fibonacci_sphere` | Nearest-site half-plane intersections clipped in a gnomonic chart, with adaptive nearest-site certification of every final vertex (`cpp/src/engine/mesh.cpp:520-640`) |
| `spherical_barycentric_control_volume_v2` | `geodesic_icosahedron` | Primal-edge midpoints and primal-face centers joined into an explicit [dual mesh](#dual-mesh) (`cpp/src/engine/mesh.cpp:963-990`) |

(`cpp/src/engine/core.cpp:115-120`.)

Serialized invariants:

- `control_volume_vertices_3d` is ordered **counter-clockwise as seen from outside the sphere** (`cpp/src/engine/types/core.hpp:41-44`).
- `control_volume_edge_neighbor_ids[i]` identifies the cell across the great-circle edge from vertex `i` to vertex `(i+1) % vertex_count` (`cpp/src/engine/types/core.hpp:43-45`).
- Edge neighbours are reciprocal, endpoints must match, and `validate_control_volume_partition` rejects degenerate polygons and non-reciprocal edges (`cpp/src/engine/mesh.cpp:681-760`).
- `area_km2` is replayed from the stored vertices via signed spherical area, and all cells close to `4*pi*radius^2` (`cpp/src/engine/mesh.cpp:455-470`, `README.md:286`).

A Voronoi edge with no generating neighbour within `1.0e-10` residual is a hard error (`cpp/src/engine/mesh.cpp:617-618`).

See [Mesh and Geometry](./features/mesh-and-geometry.md).

### coverage CSR

The destination-major compressed-sparse-row ledger inside a [crust transport plan](#crust-transport-plan). Format string: `destination_csr_spherical_forward_overlap_v1` (`cpp/src/engine/process_serialization.cpp:3533-3534`).

| Array | Meaning |
| --- | --- |
| `destination_offsets` | Row starts, length `cell_count + 1` |
| `source_cell_ids` | Contributing source cell for each edge |
| `overlap_area_km2` | Raw spherical overlap area for that edge |
| `remap_residual_distance_km` | Per-edge geometric residual diagnostic |
| `source_kinematic_distance_km` | Per-edge transport distance |

(`cpp/src/engine/types/earth_system.hpp:562-566`.)

**Destination columns are intentionally not normalized.** The comment in the type is explicit: "gaps and multiple coverage represent kinematic extension and compression" (`cpp/src/engine/types/earth_system.hpp:559-561`). Extension therefore appears as `uncovered_gap_area_km2_by_cell` and compression as `overlap_excess_area_km2_by_cell`, and the two must balance globally (`global_gap_overlap_balance_residual_km2`).

The coverage model of the arrangement behind the CSR is `destination_local_gnomonic_line_arrangement_multiplicity_v1` (`cpp/src/engine/process_serialization.cpp:3535-3536`).

See [Crust Transport and Forward Overlap](./features/crust-transport-and-overlap.md).

### coverage vs fit

The deliberate separation of **two independent calibration verdicts**, so that "we cannot measure this metric" is never confused with "we measured it and it is wrong".

| Verdict | Question | Summary key | CLI policy flag |
| --- | --- | --- | --- |
| **Coverage** | Is the world metric even available? | `external_calibration_metric_coverage_fraction`, `external_calibration_missing_metric_count`, `external_calibration_complete` | `--require-all-metrics` / `--allow-missing-metrics` |
| **Fit** | Is the available value inside the target range? | `external_calibration_pass_fraction`, `external_calibration_evaluated_pass_fraction`, `external_mean_calibration_score` | `--require-all-passed` / `--allow-fit-failures` |

(`src/magic_geo/calibration/evaluate.py:470-486`; `src/magic_geo/cli/commands/calibrate.py:48-62, 81-91`.)

A missing world metric scores `0.0`, counts as failed, **and** is tracked separately in `missing_world_metrics`, which is why the report carries both `external_calibration_pass_fraction` (over all checks) and `external_calibration_evaluated_pass_fraction` (over evaluated checks only). Both policy flags default to permissive; each independently causes exit code `1` *after* the report is written.

```bash
# Fail the build only on genuine fit failures, tolerating unavailable metrics
magic-geo calibrate \
  --world runs/world.json \
  --targets configs/geo_validation_earth_empirical_targets.json \
  --output runs/calibration.json \
  --summary runs/calibration.md \
  --allow-missing-metrics --require-all-passed
```

The suite reflects the same split at the top level: `GEO_MODEL_LIMITATIONS` ends with "Earth empirical fit remains a separate calibration verdict from internal contract integrity" (`src/magic_geo/geo_validation.py:40`).

See [Calibration Against Real-Earth Data](./14-calibration.md).

### crust transport plan

`struct CrustTransportPlan` (`cpp/src/engine/types/earth_system.hpp:558-612`) — the complete per-step structure describing how crust moved from the previous plate-attached geometry to the fixed destination mesh. It bundles:

1. The [coverage CSR](#coverage-csr) (`destination_offsets`, `source_cell_ids`, `overlap_area_km2`, plus per-edge residual and distance arrays).
2. Per-destination coverage diagnostics: `contributor_count_by_cell`, `dominant_source_cell_ids`, `dominant_source_volume_fraction_by_cell`, `coverage_area_sum_km2_by_cell`, `covered_union_area_km2_by_cell`, `uncovered_gap_area_km2_by_cell`, `overlap_excess_area_km2_by_cell`, `maximum_coverage_multiplicity_by_cell`, and the raw [atom](#atom)/line counts.
3. The [membership area class](#membership-area-class) CSR plus its nested contributor CSR.
4. The **remapped extensive state**: `remapped_crust_type_by_cell`, `remapped_lithology_by_cell`, `remapped_crust_age_ma_by_cell`, `remapped_crust_thickness_km_by_cell`, `remapped_crust_density_by_cell`.
5. Closure scalars: source-area closure errors, destination-partition closure error, global gap/excess, and the three source-vs-transported inventories (crust volume `km3`, density-weighted crust volume `g_cm3_km3`, crust-age volume moment `km3_ma`).

Two builders exist: `build_identity_crust_transport_plan(cells)` for the zero-motion step-0 checkpoint, and `build_forward_overlap_crust_transport_plan(...)` for every motion step (`cpp/src/engine/crust_transport.cpp`). Both are CPU-authoritative.

See [Crust Transport and Forward Overlap](./features/crust-transport-and-overlap.md).

---

## Terms D–G

### drainage area exponent

`erosion.drainage_exponent` — the exponent applied to normalized flow accumulation in the [stream power](#stream-power) relation. Default `0.5`, range `[0.0, 2.0]` (`src/magic_geo/config.py:394-399`). It maps to the C field `drainage_exponent` in `CConfig` and to `Params::drainage_exponent`.

The quantity it exponentiates is **not** an area in km²: it is `acc_norm = clamp(flow_accumulation / acc_scale, 0.0, 3.0)`, where `acc_scale` is the 95th-percentile land flow accumulation for the step, floored at `1.0` (`cpp/src/engine/earth_system.cpp:946, 982`). `flow_accumulation` itself is measured "in cell-count units" (`docs/layers_reference.md:309`), so the exponent acts on a dimensionless, percentile-normalized, clamped drainage proxy.

See [Erosion, Maturation and Landscape Evolution](./features/erosion-and-maturation.md) and [Configuration Reference](./05-configuration-reference.md).

### dry-rock accounting

The **non-authoritative finite three-[reservoir](#reservoir) counter-model** that sits downstream of the [material shadow](#material-shadow). Model identity `finite_three_reservoir_dry_rock_accounting_v1`, mode `finite_accounting_shadow`, mass unit `kg` (`cpp/src/engine/crust_reservoir_serialization.cpp:108-114`). Implemented in `cpp/src/engine/crust_reservoir.cpp`; serialized as `crust_dry_rock_accounting_model` and `crust_dry_rock_accounting_history[]`.

What it *does* close (all declared `true`):

| Flag | Line |
| --- | --- |
| `finite_three_reservoir_accounting_present` | `cpp/src/engine/crust_reservoir_serialization.cpp:175` |
| `closed_three_reservoir_dry_rock_accounting` | `:176` |
| `per_origin_accounting_closed` | `:177` |
| `finite_exchange_inventory_enforced` | `:178` |
| `proxy_compensations_exposed` | `:179` |
| `plate_resolved_slab_accounting_state_present` | `:180` |

What it explicitly does **not** resolve (all declared `false`, `cpp/src/engine/crust_reservoir_serialization.cpp:181-192`): `authoritative_for_cell_state`, `physical_source_sink_resolved`, `material_provenance_resolved`, `upper_mantle_exchange_reservoir_resolved`, `subducted_slab_reservoir_resolved`, `global_crust_cycle_mass_conservation_resolved`, `solid_volume_resolved`, `phase_resolved`, `mass_weighted_age_resolved`, `sediment_coupled`, `coverage_membership_fate_resolved`, `subduction_polarity_resolved`.

Ordering is strict and is part of the contract: `process_reason_then_all_surface_sinks_by_ascending_cell_and_origin_key_then_all_surface_sources_by_ascending_cell_and_origin_key` (`cpp/src/engine/crust_reservoir_serialization.cpp:152-153`). Every individual transfer carries `physical_basis_resolved = false`.

See [Crust Material Shadow and Dry-Rock Reservoirs](./features/crust-material-and-reservoirs.md).

### dual mesh

The geodesic backend's cell tessellation, constructed as the **dual** of a primal triangulation. An icosahedron is subdivided at frequency `f`, producing `10f² + 2` primal vertices and `20f²` triangles (`cpp/src/engine/mesh.cpp:909, 914`); `geodesic_frequency_for_target` picks `f` from the requested `mesh.cell_count` (`cpp/src/engine/mesh.cpp:840`). Each primal vertex becomes one cell, whose boundary alternates **primal-edge midpoints** and **primal-face centers**, both re-normalized onto the sphere (`cpp/src/engine/mesh.cpp:963-990`).

A consequence that matters for downstream consumers: the geodesic dual boundary between two adjacent cells is **bent** — it is two great-circle segments meeting at a face center, not one. The Python-side `cell_adjacency_edges` schema still uses a one-segment approximation and "does not yet encode the geodesic dual's two-segment bent boundary" (`docs/deep_plan.md:84`, `README.md:286`). The exact directed `plate_motion_history[].boundary_segments` ledger *does* retain each physical piece individually.

The Fibonacci backend's cells are also a dual in the Voronoi sense (dual to the Delaunay triangulation of the sites), but the repository reserves the explicit "dual" language for the geodesic barycentric construction.

See [Mesh and Geometry](./features/mesh-and-geometry.md).

### dynamic relief

The heuristic, **clamped** part of the per-step tectonic elevation change. Computed as:

```
boundary_change            = 80*(conv - conv_prev) + 55*(div - div_prev) - 30*(trans - trans_prev)
unbounded_dynamic_relief_change_m = uplift_rate * 0.42 + boundary_change
bounded_dynamic_relief_change_m   = clamp(unbounded, -180.0, +220.0)
```

(`cpp/src/engine/tectonics.cpp:1613-1640`; `TECTONIC_UPLIFT_RATE_RESPONSE_FRACTION = 0.42` at `cpp/src/engine/internal.hpp:37`; the clamp bounds are `TECTONIC_DYNAMIC_RELIEF_MINIMUM_CHANGE_M = -180.0` and `TECTONIC_DYNAMIC_RELIEF_MAXIMUM_CHANGE_M = 220.0` at `cpp/src/engine/internal.hpp:35-36`.)

Only this term is clamped. The composition identity is:

```
tectonic_elevation_change_m_by_cell
  = isostatic_equilibrium_change_m
  + thermal_equilibrium_change_m
  + bounded_dynamic_relief_change_m
```

(`cpp/src/engine/README.md:155-157`). Both equilibrium differences are applied at gain 1 *outside* the clamp (`TECTONIC_ISOSTATIC_TARGET_DIFFERENCE_GAIN = 1.0`, `cpp/src/engine/internal.hpp:34`), because "isostatic relaxation is effectively complete on the nominal 5 Ma maturation interval" and clipping the combined term "used to leave kilometre-scale oceanic freeboard behind after a crust-state transition, with no carried residual" (`cpp/src/engine/tectonics.cpp:1624-1629`).

Both the unbounded and bounded arrays are serialized at binary64 round-trip precision, so the clamp is independently replayable.

See [Topography, Isostasy and Thermal Subsidence](./features/topography-and-isostasy.md).

### ecotone

A transitional zone between biomes. The codebase carries two related but distinct quantities:

| Field | Produced by | Definition |
| --- | --- | --- |
| `ecotone_index` | `src/magic_geo/biome_dynamics.py:146` | `clamp(neighbor_diversity*0.62 + climate_margin*0.26 + seasonal_aridity*0.12)`; `biome_transition_zone` is `true` when `ecotone_index >= 0.55` or the cell's biome does not match its expected class (`:151`) |
| `biome_ecotone_type` | `src/magic_geo/biome_ecotones.py:218` | A *named* transitional habitat selected from 9 scored candidates when the best score reaches `ECOTONE_THRESHOLD = 0.52` (`:7, :168`), else `"none"` |

The 9 named ecotone types scored per cell (`src/magic_geo/biome_ecotones.py:90-160`): `mangrove`, `cloud_forest`, `alpine_paramo`, `dry_forest`, `mediterranean_scrub`, `swamp`, `taiga`, `cold_steppe`, `cold_desert`. The first three are gated on additional preconditions (e.g. coastal-land adjacency for `mangrove`) before being scored at all. Qualifying cells are grouped into contiguous `biome_ecotone_regions` with a confidence score.

These are diagnostic index models, not calibrated ecological solvers — see the declared limitation "ecosystem, species, wildfire, and resource layers are diagnostic index models rather than calibrated population or process solvers" (`src/magic_geo/geo_validation.py:39`).

See [Biomes, Ecosystems and Disturbance](./features/biomes-and-ecology.md) and [Soils and Weathering](./features/soils.md).

### endorheic basin

A drainage basin with no path to the ocean. Operationally: a watershed whose outlet type is anything other than `ocean`.

```cpp
watershed.outlet_type = watershed_outlet_type(cells, basin_id);
watershed.is_endorheic = watershed.outlet_type != 0;
```

(`cpp/src/engine/water_features.cpp:320-321`.) Outlet type `0` is `"ocean"` in `WATERSHED_OUTLET_NAMES = {"ocean", "lake", "saline_basin", "inland_sea", "closed_land"}` (`cpp/src/engine/schema_names.hpp:50-52`), so a lake-terminating, saline-basin-terminating, inland-sea-terminating, or closed-land-terminating watershed is all counted as endorheic.

Related but distinct per-cell field: `is_closed_basin`, set by the [priority flood](#priority-flood) pass for cells that drain to an internal sink (`docs/layers_reference.md:315`). Summary keys `endorheic_basin_count` and `endorheic_watershed_count` are emitted from the *same* counter (`cpp/src/engine/summary.cpp:1783, 1785`), so they are always equal.

External calibration targets `non_antarctic_endorheic_watershed_fraction` and `non_antarctic_endorheic_watershed_area_fraction` come from HydroBASINS level 3, with Antarctica excluded below `-60.0°` centroid latitude.

See [Hydrology, Rivers and Lakes](./features/hydrology-and-rivers.md).

### Euler pole / Euler axis

The unit vector about which a plate rotates. In C++ it is `Plate::axis` (`cpp/src/engine/types/core.hpp:16`); in the world document it appears as `plates[].axis` and, per motion step, as `plate_motion_history[].plates[].rotation_axis` (`cpp/src/engine/types/earth_system.hpp:452`).

Hard requirements enforced at boundary-segment construction: the axis must be finite and unit length within `EULER_AXIS_UNIT_TOLERANCE = 1.0e-12`, else construction throws (`cpp/src/engine/plate_boundary_segments.cpp:9, 386-396`).

Both `axis` and the plate centers are serialized at `geometry_precision = max(max_digits10, float_precision)` so that Python replay can reconstruct Rodrigues center transitions exactly (`cpp/src/engine/README.md:205-209`).

Note the naming: the repository consistently says **axis**, not "pole". They denote the same object — the fixed rotation axis piercing the sphere at the Euler pole — but the serialized key is `axis` / `rotation_axis`, never `pole`.

See [Tectonics and Plates](./features/tectonics-and-plates.md).

### exchange reserve

The **initial numerical upper-mantle counter-reserve** of the [dry-rock accounting](#dry-rock-accounting) model. It fills the difference between the scalar surface dry-rock mass and a fixed numerical surface-state envelope:

```
capacity = sum(control_volume_area_km2) * 76 km * 3.08 g/cm3 * 1e12   ->  kg
```

(`capacity_formula = sum_control_volume_area_km2_times_76_km_times_3.08_g_cm3_times_1e12`, `cpp/src/engine/crust_reservoir_serialization.cpp:129-130`; constants `SURFACE_ENVELOPE_MAXIMUM_THICKNESS_KM = 76.0` and `SURFACE_ENVELOPE_MAXIMUM_DENSITY_G_CM3 = 3.08` at `cpp/src/engine/crust_reservoir.cpp:20-21`.)

Declared semantics, verbatim from the model metadata:

| Key | Value |
| --- | --- |
| `capacity_model` | `surface_state_envelope_v1` |
| `capacity_geophysically_calibrated` | `false` |
| `capacity_semantics` | `finite_numerical_surface_state_envelope_not_an_estimate_of_upper_mantle_mass` |
| `mantle_exchange_topology` | `single_global_packet_pool_shared_by_all_cells_without_spatial_coordinates_v1` |
| `instantaneous_global_mantle_mixing_assumed` | `true` |
| `mantle_spatial_transport_resolved` | `false` |
| `mantle_withdrawal_model` | `initial_exchange_reserve_first_then_largest_packet_lowest_key_tie_break_v1` |

(`cpp/src/engine/crust_reservoir_serialization.cpp:131-163`.)

The reserve's origin key is `origin_domain_id = 1` (`initial_upper_mantle_exchange_reserve`) with `origin_kind_id = INITIAL_EXCHANGE_ORIGIN_KIND_ID = -1` (`cpp/src/engine/crust_reservoir.cpp:11`), keeping it distinguishable from every surface-origin packet forever.

This is one spatially unresolved global pool. It is **not** an upper-mantle mass estimate, and no mantle transport is resolved (`cpp/src/engine/README.md:305-315`).

See [Crust Material Shadow and Dry-Rock Reservoirs](./features/crust-material-and-reservoirs.md).

### Fibonacci sphere

The default mesh backend (`mesh.backend: fibonacci_sphere`, id `0` in `MESH_BACKEND_IDS`, `src/magic_geo/native.py`). Sites are laid out by the Fibonacci/golden-angle spiral, then closed into exact spherical Voronoi [control volumes](#control-volume). Built by `build_fibonacci_mesh` (`cpp/src/engine/mesh.cpp:776`).

Two structures are produced and are deliberately kept separate:

1. The **process stencil** — `mesh.neighbor_count` nearest neighbours per cell, symmetrized (`cpp/src/engine/mesh.cpp:790-812`). See [stencil neighbors](#stencil-neighbors).
2. The **control-volume tessellation** — `spherical_voronoi_control_volume_v1`, independent of `neighbor_count` (`cpp/src/engine/mesh.cpp:816-830`).

Nearest-neighbour search uses a spherical KD-tree (`FibonacciKdTree`, `cpp/src/engine/mesh.cpp:86`) that maintains a boundary-tie and score-ascending ordering contract (`:105-107`). A brute-force cross-check is available and is registered as its own CTest case:

```bash
ctest --test-dir build -R magic_geo_fibonacci_knn_reference
# runs magic_geo_native_api_test with ENVIRONMENT MAGIC_GEO_VALIDATE_FIBONACCI_KNN=1
```

Divergence between the optimized and brute-force neighbour lists is a hard error (`cpp/src/engine/mesh.cpp:797-806`).

See [Mesh and Geometry](./features/mesh-and-geometry.md).

### forward overlap

The crust-transport geometry model: every source [control volume](#control-volume) is attached to its previous plate, **forward-rotated** by that plate's Euler step, and intersected against the *fixed* destination control volumes. Format `destination_csr_spherical_forward_overlap_v1` (`cpp/src/engine/process_serialization.cpp:3533-3534`); executed CPU-authoritatively in `cpp/src/engine/crust_transport.cpp`.

Key property: overlap areas are **not** normalized per destination. Consequently:

| Kinematic situation | How it appears |
| --- | --- |
| Extension / divergence | `uncovered_gap_area_km2_by_cell > 0` (multiplicity 0 region) |
| Compression / convergence | `overlap_excess_area_km2_by_cell > 0` (multiplicity ≥ 2 region) |
| Pure translation | Multiplicity 1 everywhere, gap and excess both ~0 |

Native construction rejects a source row that misses its source area by more than `max(1e-6 km2, 2e-10 relative)`, a destination arrangement that does not partition the destination, a mismatch in any of the three source-to-transported inventories, or an imbalance between global uncovered and overlap-excess area (`docs/geo_generation_maturation_deep_audit.md:222`).

The transport is explicitly **first-order and diffusive** (`src/magic_geo/geo_validation.py:32`), and the joint dominant categorical witness for type/lithology "is not by itself material provenance" (`cpp/src/engine/README.md:44-47`, `README.md:347`).

See [Crust Transport and Forward Overlap](./features/crust-transport-and-overlap.md).

### geodesic icosahedron

The alternate mesh backend (`mesh.backend: geodesic_icosahedron`, id `1`). An icosahedron is subdivided at a frequency `f` chosen by `geodesic_frequency_for_target(cell_count)` (`cpp/src/engine/mesh.cpp:840`), yielding exactly `10f² + 2` cells and `20f²` primal triangles (`cpp/src/engine/mesh.cpp:909, 914`). A requested `mesh.cell_count` therefore **resolves** to the nearest representable `10f² + 2`; the generated cell count, not the requested one, is what downstream logic uses (including accelerator eligibility, `cpp/src/engine/README.md:352-353`).

Cells are the [dual mesh](#dual-mesh) of that triangulation, giving `cell_area_model = spherical_barycentric_control_volume_v2`. The process stencil follows the primal triangle edges rather than a k-nearest-neighbour search, so `mesh.neighbor_count` has no effect on this backend (`docs/example_seed_gallery.md:143-145`, `docs/configuration_reference.md:112`).

Standard geodesic cell counts include 162 cells (`f = 4`), 642 (`f = 8`), and 2562 (`f = 16`); the 162-cell case is one of the two fixtures used by the independent O(N²) [replay validator](#replay-validator) `crust_coverage_geometry_replay.py`.

See [Mesh and Geometry](./features/mesh-and-geometry.md).

### geologic depression

A closed basin that the model treats as a *real* landform to be preserved, as opposed to a numerical sink to be corrected. The predicate is purely local:

```cpp
bool is_geologic_depression(const Cell& cell) {
    return cell.crust_type == 6 || cell.crust_type == 7
        || cell.boundary_divergent > 0.28 || cell.boundary_convergent > 0.42;
}
```

(`cpp/src/engine/hydrology.cpp:213-215`.) Crust type `6` is `rift_basin` and `7` is `sedimentary_basin` in `CRUST_NAMES` (`cpp/src/engine/schema_names.hpp:7-10`).

Behaviour is gated by `hydrology.preserve_geologic_depressions`, default `true` (`src/magic_geo/config.py:365-368`). A depression that is **not** geologic and is not deferred as a temporary lake is a *numeric* depression and is corrected — filled or breached — by the `stabilize_numeric_depressions` loop, bounded by `NUMERIC_DEPRESSION_CORRECTION_MAX_PASSES = 16` (`cpp/src/engine/constants.hpp:55`).

The resulting per-cell classification lands in `depression_policy`, drawn from `DEPRESSION_POLICY_NAMES = {"none", "corrected_numeric", "preserved_geologic", "overflow_spill", "dry_closed", "temporary_numeric_lake"}` (`cpp/src/engine/schema_names.hpp:53-56`). A geologic depression with mean runoff above `25.0 mm/y` and a spill destination at fill fraction ≥ 1.0 becomes `overflow_spill`; wet-but-not-overflowing becomes `preserved_geologic`; dry becomes `dry_closed` (`cpp/src/engine/hydrology.cpp:556-584`).

See [Hydrology, Rivers and Lakes](./features/hydrology-and-rivers.md).

---

## Terms H–M

### hillslope diffusion

`erosion.hillslope_diffusion` — the reference coefficient for downslope sediment transport across every **mesh-neighbour pair**, default `0.055`, range `[0.0, 1.0]` (`src/magic_geo/config.py:406-411`).

The applied per-edge computation (`cpp/src/engine/earth_system.cpp:345-376`):

```
resistance            = lithology_resistance(source.lithology)
effective_diffusivity = min(0.45, max(0, K) * maturation_timestep_scale / max(1e-12, resistance))
source_depth_m        = effective_diffusivity * elevation_drop_m / source_neighbor_count
transfer_volume_km3   = source_depth_m * source.area_km2 / 1000
target_depth_m        = transfer_volume_km3 * 1000 / target.area_km2
```

`HILLSLOPE_MAX_EFFECTIVE_DIFFUSIVITY = 0.45` caps the effective coefficient (`cpp/src/engine/constants.hpp:66`). Edges are skipped when the source is water or the drop is `<= 1.0e-12` m. Because the source depth is divided by the *source's* neighbour count, the total outflow from a cell is bounded regardless of stencil degree.

Unlike [stream power](#stream-power), the hillslope term is scaled by [maturation_timestep_scale](#nominal-timestep) directly in the coefficient, so both the reported and applied depths are timestep-integrated.

Results land in `cells[].hillslope_sediment_production_m` / `_deposition_m` / `_net_m`, plus a complete per-edge `hillslope_sediment_transport_history[].edges[]` ledger.

See [Erosion, Maturation and Landscape Evolution](./features/erosion-and-maturation.md).

### intrinsic speed

The per-plate procedural angular-speed index, `Plate::angular_speed` (`cpp/src/engine/types/core.hpp:19`), serialized as `plates[].angular_speed` and `plate_motion_history[].plates[].intrinsic_angular_speed` (`cpp/src/engine/types/earth_system.hpp:453`).

| Aspect | Value |
| --- | --- |
| Configured range | `tectonics.min_angular_speed` default `0.03`; `tectonics.max_angular_speed` default `0.95` (`src/magic_geo/config.py:281-292`) |
| Validation | Must be finite and nonnegative, else boundary-segment construction throws (`cpp/src/engine/plate_boundary_segments.cpp:397-404`); `max_angular_speed >= min_angular_speed` enforced at config load (`src/magic_geo/config.py:314-315`) |
| Units | **Dimensionless index.** It is not rad/Ma or deg/Ma |

"Intrinsic" is doing real work: the velocity `axis * intrinsic_speed × midpoint` is the *raw, unscaled* Euler velocity used to derive the dimensionless [opening / convergence / slip indices](#opening--convergence--slip-index). A separate nominal scale converts it to km/Ma only for the reported rate fields, and that conversion "is a nominal reference-step scale, not a calibrated physical velocity" (`cpp/src/engine/README.md:196-199`).

Actual per-step angular displacement is controlled by `tectonics.plate_motion_scale_deg_per_step` (default `2.0` degrees per five-million-year reference step, `src/magic_geo/config.py:299-304`), scaled by `maturation_timestep_scale`.

See [Tectonics and Plates](./features/tectonics-and-plates.md).

### isostatic equilibrium

The local crust-thickness/density equilibrium elevation each cell relaxes toward. Computed by `crust_equilibrium_elevation_m` (`cpp/src/engine/tectonics.cpp:574-585`):

```
oceanic-like:  -OCEANIC_RIDGE_REFERENCE_DEPTH_M                                  = -2500 m
otherwise:      CONTINENTAL_ISOSTATIC_FREEBOARD_M                                = 500 m
              + CONTINENTAL_CRUST_THICKNESS_FREEBOARD_M_PER_KM * (thickness_km - 30)   (12 m/km)
              - CONTINENTAL_CRUST_DENSITY_FREEBOARD_M_PER_G_CM3 * (density - 2.72)     (1800 m per g/cm3)
```

Constants at `cpp/src/engine/constants.hpp:27-36`. The document restates the formula verbatim as `isostatic_equilibrium_formula` (`cpp/src/engine/process_serialization.cpp:2757-2758`).

Per motion step the change is applied at **gain 1 and outside the [dynamic relief](#dynamic-relief) clamp**:

```
isostatic_equilibrium_change_m = 1.0 * (post_process_equilibrium - previous_equilibrium)
```

(`cpp/src/engine/tectonics.cpp:1618-1622`, `TECTONIC_ISOSTATIC_TARGET_DIFFERENCE_GAIN = 1.0` at `cpp/src/engine/internal.hpp:34`.)

Each `plate_motion_history` record preserves `previous_local_isostatic_equilibrium_m`, `post_process_local_isostatic_equilibrium_m`, and `isostatic_equilibrium_change_m` at binary64 round-trip precision, and independent replay verifies "zero unapplied equilibrium residual" (`cpp/src/engine/README.md:148-158`).

The per-cell provenance snapshot is `cells[].initial_isostatic_elevation_m`. Flexure, dynamic topography, sediment loading, and physical dynamics remain unresolved (`cpp/src/engine/README.md:162-165`).

See [Topography, Isostasy and Thermal Subsidence](./features/topography-and-isostasy.md).

### layer

Three distinct senses, all present in the repository. Disambiguate by context:

| Sense | Definition | Where |
| --- | --- | --- |
| **Debugger layer** | One scalar value per cell that the debugger can colour the globe by, discovered generically from the world-payload shape | `docs/layers_reference.md:11-27`, `src/magic_geo/debug_export.py` |
| **Contract layer** | One of 14 phase-ordered natural-generation stages audited by [layer contracts](#layer-contract) | `src/magic_geo/geo_layer_contracts.py:26` |
| **Stratigraphic layer** | One bed inside `stratigraphic_columns[].layers[]` | `cpp/src/engine/entity_serialization.cpp` |

**Debugger-layer kinds** (`src/magic_geo/debug_export.py:146, 151, 316, 466, 483`):

| Kind | Meaning |
| --- | --- |
| `numeric` | An int/float cell field; coloured viridis over the p2–p98 range |
| `categorical` | A string/bool cell field with ≤ 64 distinct values |
| `numeric_monthly` | A 12-element numeric cell field; scrub the month control (1–12) |
| `numeric_stage` | A per-cell field inside a `cell_ids` + `*_by_cell` record family; scrub the stage control, colour scale fixed across stages |
| `categorical_stage` | The same, for string/bool fields with ≤ 64 values |

**Debugger-layer roles** — how to read the values (`docs/layers_reference.md:31-42`): `measurement`, `index`, `ratio`, `classification`, `identifier`, `provenance`, `accumulator`, `diagnostic`, `seasonal`.

**Debugger-layer doc tiers** — how a description was sourced, most to least specific (`docs/layers_reference.md:45-50`): `curated`, `convention`, `unit`, `generated`. `generated` marks a documentation gap.

For the reference world profiled in `docs/layers_reference.md:54-66` (earthlike_mvp, 4,096 cells, `fibonacci_sphere`, scope `full`): **439 layers** — 361 numeric, 47 categorical, 27 per-stage, 4 monthly; coverage 174 curated (39.6%), 181 convention (41.2%), 72 unit (16.4%), 12 generated (2.7%).

**Stratigraphic layer** fields (9): `index`, `facies`, `thickness_m`, `age_top_ma`, `age_base_ma`, `grain_size_index`, `organic_potential`, `reservoir_quality`, `seal_quality`.

See [Debug Exports and Visualization](./16-debug-and-visualization.md) and [Sediment, Routing and Stratigraphy](./features/sediment-and-stratigraphy.md).

### layer contract

One of **14** declarative evidence contracts, phases 0–13, that project the geo validator's domain-grouped checks back onto the natural pipeline so "a green aggregate verdict cannot hide an unrepresented layer" (`src/magic_geo/geo_layer_contracts.py:1-13`). Schema version `1`, report type `geo_layer_contract_audit_v1`.

| Phase | `id` | Name | Dependencies |
| --- | --- | --- | --- |
| 0 | `planet_parameters` | Planet parameters and boundary conditions | — |
| 1 | `spherical_mesh` | Spherical mesh, areas, geometry, and spatial indices | `planet_parameters` |
| 2 | `plate_tectonics` | Plate domains, kinematics, boundaries, zones, and faults | `spherical_mesh` |
| 3 | `crust_lithology` | Crust type, age, thickness, density, and lithology | `plate_tectonics` |
| 4 | `relief_bathymetry` | Relief, isostatic components, bathymetry, and landforms | `crust_lithology` |
| 5 | `sea_level_ocean` | Sea level, water bodies, shelves, and ocean circulation | `relief_bathymetry` |
| 6 | `climate_atmosphere` | Climate, energy, circulation, moisture, and classification | `sea_level_ocean`, `relief_bathymetry` |
| 7 | `hydrology` | Water budget, drainage, rivers, lakes, and groundwater | `climate_atmosphere`, `relief_bathymetry` |
| 8 | `erosion_sediment` | Erosion, hillslopes, fluvial routing, sediment, and stratigraphy | `hydrology`, `plate_tectonics` |
| 9 | `cryosphere` | Cryosphere, ice transport, permafrost, and glacial landforms | `climate_atmosphere`, `erosion_sediment` |
| 10 | `soils_pedogenesis` | Soils, horizons, and pedogenesis diagnostics | `erosion_sediment`, `climate_atmosphere`, `cryosphere` |
| 11 | `biomes_ecosystems` | Biomes, ecotones, ecosystems, species, wetlands, reefs, and fire | `soils_pedogenesis`, `climate_atmosphere`, `hydrology` |
| 12 | `natural_resources` | Natural resources and geological formation evidence | `crust_lithology`, `erosion_sediment`, `hydrology`, `biomes_ecosystems` |
| 13 | `coupled_maturation` | Cross-layer coupled generation and maturation clock | `plate_tectonics`, `sea_level_ocean`, `climate_atmosphere`, `hydrology`, `erosion_sediment`, `cryosphere` |

(`src/magic_geo/geo_layer_contracts.py:26-314`.)

`contract_passed` is true **iff** all six conditions hold (`src/magic_geo/geo_layer_contracts.py:396-403`):

1. `world` is a dict.
2. Every `required_outputs` key exists with the right kind.
3. Every declared `validator_domain` supplied at least one check.
4. Every dependency layer passed.
5. At least one passing check exists.
6. Zero error-severity failures among that layer's checks.

Output kinds are themselves part of the contract: `dict` and `nonempty_str` must be non-empty, `nonempty_list` must be non-empty, and a plain `list` **may** be empty — "an empty list is valid evidence for a phenomenon that is absent in a particular scenario, while a missing or wrongly typed registry is not" (`src/magic_geo/geo_layer_contracts.py:23-25, 317-326`).

Every layer hardcodes `"empirical_realism_proven": False` (`src/magic_geo/geo_layer_contracts.py:433`), and the report interpretation says so explicitly: a passing contract "proves artifact, validator-domain, dependency, and assigned fatal-check integrity; it does not prove empirical realism or physical time calibration" (`:442-446`).

Scope adaptation: when `generation_scope != "geo_only"`, the `coupled_maturation` contract drops the `geo_evolution_provenance` output and the `evolution_provenance` domain, recording both in `scope_specific_omissions` (`src/magic_geo/geo_layer_contracts.py:344-353`).

Each layer also carries a `temporal_class` and an `evidence_class` string that name exactly what kind of evidence the layer has — for example `plate_tectonics` declares `exact_directed_control_volume_segment_kinematics_and_pair_wide_diagnostic_overlap_candidate_crosswalk_replay_without_local_fragment_link_allocation_physical_polarity_or_slab_transfer` (`:72-76`).

See [Validation](./12-validation.md).

### manifest revision

An opaque token identifying one immutable state of a debug-export cache. It is the hex-joined tuple `(st_dev, st_ino, st_size, st_mtime_ns)` of the cache's `manifest.json`:

```python
return "-".join(f"{value:x}" for value in self._fingerprint)
```

(`src/magic_geo/debug_server.py:564-567`; the same computation appears in `src/magic_geo/debug_map_export.py:1231`.)

Device and inode are included deliberately, so that "atomic replacements" are distinguished "even when generated manifests happen to retain the same byte length and timestamp" (`src/magic_geo/debug_server.py:559-561`).

Every read endpoint of the debug server accepts an optional `revision` parameter and runs the read against exactly that revision; a mismatch is rejected rather than silently served from a newer cache: `"debug cache revision changed; refresh status and retry"` (`src/magic_geo/debug_server.py:726-737`). Status responses expose the current value as `cache_revision` (`:748`).

See [Debug Exports and Visualization](./16-debug-and-visualization.md) and [Web Workbench](./15-web-workbench.md).

### material shadow

The **non-authoritative persistent sparse dry-rock mass ledger** carried alongside authoritative crust state. Model identity `persistent_sparse_surface_crust_mass_shadow_v1`, mode `shadow`, mass unit `kg` (`cpp/src/engine/process_serialization.cpp:164-170`). Implemented in `cpp/src/engine/crust_material.cpp`; serialized as `crust_material_shadow_model` and `crust_material_shadow_history[]`.

Mass definition, declared in the document:

```
dry_rock_mass_kg = cell_area_km2 * crust_thickness_km * crust_density_g_cm3 * 1e12
```

(`cpp/src/engine/process_serialization.cpp:171-172`.)

Mechanics:

| Aspect | Declared model | Line |
| --- | --- | --- |
| Advection | `source_normalized_overlap_with_final_edge_remainder_v1` | `:186-187` |
| Normalization scope | `per_source_sum_of_raw_overlap_areas` | `:188-189` |
| Remainder rule | `final_destination_edge_receives_source_mass_roundoff_remainder` | `:190-191` |
| Packet coalescing | `sorted_equal_key_sum_v1` | `:192-193` |
| Rule adjustment | `ordered_positive_unresolved_source_proportional_negative_sink_v1` | `:196-197` |
| Positive-delta origin kind | `unresolved_rule_source` (id 9) | `:198-199`, `cpp/src/engine/crust_material.cpp:10` |
| Negative-delta allocation | `proportional_across_transported_packets_with_remainder_to_largest_packet_lowest_key_tie_break` | `:200-201` |

Because transport is *source-normalized*, shadow mass closes exactly per source even though the authoritative geometric remap retains a small raw source-row residual. The difference is serialized and explicitly labelled `source_normalized_shadow_mass_minus_raw_overlap_scalar_mass_is_a_numerical_geometry_closure_diagnostic_not_a_physical_source_or_sink` (`cpp/src/engine/process_serialization.cpp:204-205`).

Declared `false`: `authoritative_for_cell_state`, `physical_source_sink_resolved`, `material_provenance_resolved`, `solid_volume_resolved`, `phase_resolved`, `mass_weighted_age_resolved`, `upper_mantle_exchange_reservoir_resolved`, `subducted_slab_reservoir_resolved`, `global_crust_cycle_mass_conservation_resolved` (`:206-215`). Declared `true`: `transport_provenance_shadow_resolved`, `ordered_rule_mass_adjustments_exposed` (`:216-217`).

"Empty transported rows and exact exhaustion remain valid intermediate states when a later positive bound rule reseeds them" (`cpp/src/engine/README.md:268-270`).

See [Crust Material Shadow and Dry-Rock Reservoirs](./features/crust-material-and-reservoirs.md).

### maturation stage

One coupled transition of the earth-system feedback loop. Stages are recorded in `earth_system_feedback_history[]` and named by the `stage` string:

| `stage` | When | `erosion_iteration` |
| --- | --- | --- |
| `initial_climate_hydrology` | Once, after crust/topography setup and before the erosion loop | `-1` |
| `erosion_iteration` | Once per configured maturation transition | `1 .. erosion.iterations` |
| `cryosphere_coupling` | Once, terminal | `-1` |

(`cpp/src/engine/process_serialization.cpp:91-105`; the parallel plate-motion checkpoint at step 0 uses `stage = "initial_plate_domains"`, `:121`.)

Inside one `erosion_iteration` the declared order is (`simulation_clock.iteration_process_order`, `cpp/src/engine/process_serialization.cpp:2121`):

```
plate_motion -> crust_transport -> crust_evolution
  -> precommit_tendency_evaluation[tectonic_elevation + hillslope_sediment + stream_power_incision;
                                   prior stabilized surface/hydrology]
  -> provisional_terrain_composition
  -> fluvial_sediment_routing[prior flow graph + provisional accommodation]
  -> finite_alluvium_bedrock_inventory_and_terrain_commit
  -> (sea_level -> climate -> causal_water_budget -> hydrology -> numeric_depression_correction)* until stable
```

then, after all iterations: `cryosphere_state -> glacial_sediment_transport -> terrain commit -> stabilization* -> cryosphere_state_recompute`.

The terminal cryosphere pass is a **zero-duration endpoint operator**: `cryosphere_advances_nominal_time: false` (`cpp/src/engine/process_serialization.cpp:2120`).

Stage count is `erosion.iterations` (default `6`, range `[0, 250]`, `src/magic_geo/config.py:376-380`) plus the initial and cryosphere stages.

See [Erosion, Maturation and Landscape Evolution](./features/erosion-and-maturation.md) and [Architecture](./04-architecture.md).

### membership area class

The **coalesced** unit of destination coverage: all [atoms](#atom) inside one destination cell that share an identical *sorted set of contributing source cell IDs* are merged into one class holding their summed area, their multiplicity, their source cell IDs, and each contributor's plate ID at the transport source snapshot.

| Metadata key | Value | Line |
| --- | --- | --- |
| `format` | `destination_membership_area_class_csr_with_class_contributor_csr_v1` | `cpp/src/engine/process_serialization.cpp:3648-3649` |
| `model` | `coalesced_destination_source_membership_area_classes_v1` | `:3650-3651` |
| `class_order` | `destination_id_then_multiplicity_then_source_cell_ids` | `:3652-3653` |
| `coalescing_key` | `sorted_contributing_source_cell_ids` | `:3654-3655` |
| `representative_model` | `largest_atomic_arrangement_piece_unprojected_vertex_mean_lowest_xyz_tie_v1` | `:3656-3657` |
| `source_plate_id_semantics` | `source_cell_plate_id_at_transport_source_snapshot` | `:3662-3663` |

Class areas independently reconstruct every overlap-CSR edge, the destination partition, the multiplicity histogram, and the destination gap/union/excess.

**A class is not a topology.** Because coalescing is by membership set, "a class may contain disconnected atomic pieces; it is not a connected topology or fate record" (`cpp/src/engine/README.md:46-47`). The metadata therefore keeps `connected_fragment_topology_resolved`, `physical_fate_resolved`, `slab_selection_resolved`, and `local_kinematics_resolved` all `false`, and `source_membership_resolved` `true`.

Cap: `MAX_MEMBERSHIP_AREA_CLASSES_PER_CELL = 16384` (`cpp/src/engine/crust_overlap_candidate_fate.cpp:7`), also declared as `maximum_membership_area_classes_per_cell` (`cpp/src/engine/process_serialization.cpp:3216`).

Multiplicity ≥ 2 classes are the input rows of the candidate-fate crosswalk (`sparse_membership_class_to_uniform_boundary_plate_pair_candidate_v1`), which partitions overlap excess against boundary plate-pair evidence or leaves it explicitly unresolved — with no local fragment-to-segment link, allocation, polarity, slab, or state mutation.

See [Crust Transport and Forward Overlap](./features/crust-transport-and-overlap.md) and [Plate Boundary Segment Ledger](./features/plate-boundary-ledger.md).

### mesh segment id

`boundary_segments[].mesh_segment_id` — the **stable** index of a reciprocal control-volume mesh segment, assigned in `(left_cell_id, left_edge_index)` order over *all* reciprocal mesh segments **before** cross-plate filtering (`cpp/src/engine/plate_boundary_segments.cpp:331`; described at `cpp/src/engine/README.md:186-189`).

Contrast with its sibling:

| Field | Domain | Stability |
| --- | --- | --- |
| `mesh_segment_id` | All reciprocal mesh segments, pre-filter | Stable across steps for a fixed mesh — identifies the *geometric* contact |
| `segment_id` | Only cross-plate segments in this step | Contiguous per-step index; changes when plate assignments change |

(`cpp/src/engine/plate_boundary_segments.cpp:431-432`.)

The counter is bounded by `MAX_RECIPROCAL_MESH_SEGMENTS_PER_CELL * cells.size()` = `8 * cell_count`, and exceeding it throws `"plate-boundary reciprocal mesh segment cap exceeded"` (`cpp/src/engine/plate_boundary_segments.cpp:332-337`).

Step-level counters `reciprocal_mesh_segment_count` and `boundary_segment_count` in `plate_motion_history[]` expose both populations.

See [Plate Boundary Segment Ledger](./features/plate-boundary-ledger.md).

### mobile sediment

`cells[].sediment_thickness_m` — the second canonical field of the [sediment interface contract](#sediment-interface-contract): the nonnegative entrainable sediment column sitting on top of [bedrock surface elevation](#bedrock-surface-elevation).

| Property | Source |
| --- | --- |
| Declared canonical | `mobile_sediment_thickness_is_canonical: true` (`cpp/src/engine/process_serialization.cpp:1858`) |
| Nonnegativity | Enforced in every checked mutation; a negative thickness is a hard error (`cpp/src/engine/sediment_partition.cpp:93-102`) |
| Entrainment bound | The material primitive "rejects entrainment beyond the opening mobile inventory" (`cpp/src/engine/README.md:236-237`) |
| Sea-level invariance | The datum-shift primitive moves bedrock and the derived surface together **without changing mobile thickness** (`cpp/src/engine/process_serialization.cpp:1849-1850`) |

Update rule: `sediment' = sediment - alluvium_entrainment_depth_m + deposition_depth_m` (`cpp/src/engine/process_serialization.cpp:1848`).

The source-partition contract splits every stage's demanded source depth into **alluvium first, bedrock second** across hillslope, fluvial, and glacial paths, audited by `validate_sediment_source_partition` in the native engine and by the `sediment_alluvium_bedrock_source_partition_replay` check in Python. Its semantics are pinned to `bulk_reference_volume_only_not_dry_rock_mass` — no provenance claim.

Mobile sediment carries **no** density, porosity, compaction, grain provenance, or chemical-weathering resolution (`cpp/src/engine/process_serialization.cpp:1861-1865`).

See [Sediment, Routing and Stratigraphy](./features/sediment-and-stratigraphy.md).

---

## Terms N–R

### nominal timestep

`erosion.maturation_timestep_ma` — the millions of years each [maturation stage](#maturation-stage) *nominally* represents. Default `5.0`, constrained `gt=0.0, le=5.0` (`src/magic_geo/config.py:382-387`). It reaches the native engine only through the v3 config struct (`CConfigV3::maturation_timestep_ma`).

| Quantity | Definition | Source |
| --- | --- | --- |
| `reference_timestep_ma` | `MATURATION_REFERENCE_TIMESTEP_MA = 5.0` | `cpp/src/engine/constants.hpp:72` |
| `maturation_timestep_scale` | `params.maturation_timestep_ma / 5.0` | `cpp/src/engine/core.cpp:44-47` |
| `nominal_elapsed_time_ma` | `maturation_timestep_ma * erosion.iterations` | `cpp/src/engine/process_serialization.cpp:2074-2077` |

Because `le=5.0`, the scale is always in `(0, 1]` — the parameter **refines** the shipped reference step, it does not coarsen it.

The clock contract is unusually explicit about what the number is not (`cpp/src/engine/process_serialization.cpp:2081-2090`):

| Key | Value |
| --- | --- |
| `clock_type` | `coupled_geodynamic_stage_clock_v12` |
| `time_unit` | `model_step` |
| `physical_time_resolved` | `false` |
| `nominal_time_calibrated` | `false` |
| `absolute_geological_age_resolved` | `false` |
| `process_rate_calibration_resolved` | `false` |
| `time_step_convergence_demonstrated` | `false` |
| `clock_limitation` | `nominal_geological_intervals_without_calibrated_physical_time_or_timestep_convergence` |

Seven process ledgers carry a shared 12-field nominal-time block (`nominal_time_model`, `nominal_time_unit`, `nominal_time_basis`, `nominal_time_source_parameter`, `nominal_time_role`, `nominal_interval_start_ma`, `nominal_interval_end_ma`, `nominal_interval_duration_ma`, `nominal_elapsed_time_ma`, `advances_nominal_time`, `nominal_time_calibrated`, `physical_time_resolved`), all at `max_digits10` (`cpp/src/engine/process_serialization.cpp:135-160`). The model string is `configured_maturation_timestep_nominal_elapsed_time_v1` and the source parameter is literally `erosion.maturation_timestep_ma` (`:7-12`).

Callers on the v1/v2 C ABI receive the historical 5 Ma nominal reference step (`cpp/src/engine/README.md:343-345`).

See [Configuration Reference](./05-configuration-reference.md) and [Erosion, Maturation and Landscape Evolution](./features/erosion-and-maturation.md).

### non-authoritative

A structure that **audits** authoritative simulation state without ever driving it. The document marks these with `authoritative_for_cell_state: false` and the `mode` value `shadow` or `finite_accounting_shadow`.

The non-authoritative structures in magic-geo:

| Structure | Model string | Flag location |
| --- | --- | --- |
| [Material shadow](#material-shadow) | `persistent_sparse_surface_crust_mass_shadow_v1` | `cpp/src/engine/process_serialization.cpp:206` |
| [Dry-rock accounting](#dry-rock-accounting) | `finite_three_reservoir_dry_rock_accounting_v1` | `cpp/src/engine/crust_reservoir_serialization.cpp:181` |
| Overlap candidate-fate crosswalk | `sparse_membership_class_to_uniform_boundary_plate_pair_candidate_v1` | `crust_overlap_candidate_fate_model` |
| [Shadow kernel](#shadow-kernel) result | `cpu_authoritative_overlap_csr_continuous_moment_shadow_v1` | `crust_overlap_continuous_shadow_authoritative: false` (`cpp/src/opencl_compute.cpp:2136-2137`) |

The engine invariant is that serializers and summaries "must preserve the explicit false authority, physical source/sink, material-provenance, solid-volume, phase, mass-weighted-age, mantle, slab, and global crust-cycle flags" (`cpp/src/engine/README.md:271-273`).

Practical reading rule: if a value appears in a `*_shadow_*`, `*_accounting_*`, or `*_candidate_fate_*` structure, it is bookkeeping. It reproduces and cross-checks the authoritative state; it never replaces it.

See [Architecture](./04-architecture.md) and [Project Overview](./01-overview.md).

### `not_applicable`

A validation check status distinct from both `passed` and `failed`, used when the phenomenon under test has no candidate population in this world — for example, river-termination checks on a world with no rivers.

```python
status = "not_applicable" if passed is None else ("passed" if passed else "failed")
```

(`src/magic_geo/geo_validation.py:283`.) The record then has `status = "not_applicable"` and `passed = False`, because `passed` is set to `passed is True` (`:290`). Consumers must read `status`, not `passed`, to distinguish a real failure from an inapplicable check.

The intent is stated in the validator docstring: "A missing candidate population is `not_applicable`, never a successful realism observation" (`src/magic_geo/geo_validation.py:811-812`).

Where it surfaces:

| Report field | Meaning |
| --- | --- |
| `summary.not_applicable_count` | Total across the report (`src/magic_geo/geo_validation.py:2821`) |
| `summary.domains.<domain>.not_applicable_count` | Per domain (`:2804`) |
| `layer_contracts.layers[].validation_not_applicable_count` | Per contract layer (`src/magic_geo/geo_layer_contracts.py:425`) |
| Suite member `not_applicable_realism_checks` | Per scenario in the suite report |
| `applicable_realism_pass_fraction` | Pass fraction computed over applicable checks only |

A `not_applicable` check does **not** satisfy a [layer contract](#layer-contract): `contract_passed` requires `bool(passed_evidence)`, i.e. at least one genuinely passing check (`src/magic_geo/geo_layer_contracts.py:388-402`).

See [Validation](./12-validation.md) and [Geo Validation Suite](./13-geo-validation-suite.md).

### opening / convergence / slip index

The three **dimensionless** kinematic components of a [boundary segment](#boundary-segment), derived from raw intrinsic Euler velocities at the segment midpoint (`cpp/src/engine/plate_boundary_segments.cpp:406-424`):

```
left_raw_velocity      = (left.axis  * left.intrinsic_speed)  x midpoint
right_raw_velocity     = (right.axis * right.intrinsic_speed) x midpoint
raw_relative_velocity  = right_raw_velocity - left_raw_velocity

signed_opening_index     =  raw_relative_velocity . left_to_right_normal
signed_convergence_index = -signed_opening_index
signed_slip_index        =  raw_relative_velocity . tangent
```

The paired **rate** fields in km/Ma multiply the same intrinsic velocities by a nominal scale (`cpp/src/engine/plate_boundary_segments.cpp:199-201`):

```
velocity_scale_km_per_ma = radius_km * plate_motion_scale_deg_per_step * (PI/180) / 5.0
```

That conversion "is a nominal reference-step scale, not a calibrated physical velocity" (`cpp/src/engine/README.md:196-199`).

Derived strengths and the direct class (`cpp/src/engine/plate_boundary_segments.cpp:453-471`):

| Field | Formula |
| --- | --- |
| `direct_convergent_strength` | `clamp(signed_convergence_index * 1.25, 0, 1)` |
| `direct_divergent_strength` | `clamp(signed_opening_index * 1.25, 0, 1)` |
| `direct_transform_strength` | `clamp((abs(slip_index) - abs(opening_index) * 0.35) * 1.05, 0, 1)` |
| `convergence_active` | `direct_convergent_strength >= 0.08` |

`convergence_active` is deliberately **independent** of the dominant class, "so an oblique transform-dominant segment is not discarded" (`cpp/src/engine/README.md:213-215`).

These direct, unsmoothed indices are authoritative evidence for the segment, but they do **not** drive the tectonic rules — the degree-normalized *smoothed* per-cell boundary forcing does (`cpp/src/engine/README.md:209-212`).

See [Plate Boundary Segment Ledger](./features/plate-boundary-ledger.md).

### packet

One origin-keyed quantum of dry-rock mass inside a shadow or reservoir table. Two packet types exist, with different keys:

**Material shadow packet** — `CrustMaterialShadowPacket` (`cpp/src/engine/types/earth_system.hpp:670-675`):

| Field | Range / meaning |
| --- | --- |
| `origin_kind_id` | `0..8` = the 9 `CRUST_NAMES` classes; `9` = `unresolved_rule_source` (`cpp/src/engine/crust_material.cpp:10, 50`) |
| `origin_plate_id` | Plate at origin |
| `origin_reason_id` | Crust process reason that created it, or `-1` |
| `dry_rock_mass_kg` | The mass carried |

Sort/coalescing order: `origin_kind_id_then_origin_plate_id_then_origin_reason_id` (`cpp/src/engine/process_serialization.cpp:194-195`).

**Reservoir packet** — `CrustDryRockPacket` (`cpp/src/engine/types/crust_reservoir.hpp:27-32`):

| Field | Range / meaning |
| --- | --- |
| `origin_domain_id` | `0` = `initial_surface_crust`, `1` = `initial_upper_mantle_exchange_reserve` (`cpp/src/engine/crust_reservoir.cpp:9-10`, `cpp/src/engine/crust_reservoir_serialization.cpp:119-120`) |
| `origin_kind_id` | `0..8` for surface origins; `-1` for the [exchange reserve](#exchange-reserve) (`cpp/src/engine/crust_reservoir.cpp:11, 46, 58`) |
| `origin_plate_id` | Plate at origin |
| `dry_rock_mass_kg` | The mass carried |

Sort order: `origin_domain_id_then_origin_kind_id_then_origin_plate_id` (`cpp/src/engine/crust_reservoir_serialization.cpp:123-124`).

Packet tables are serialized as owner-offset CSR (`cell_offsets` for the shadow, `owner_offsets` for reservoirs) with parallel key and mass arrays, all masses at `max_digits10`. Fail-closed caps: `1024` packets per surface owner, `1000000` packets across live reservoirs, `1000000` transfers per step (`cpp/src/engine/types/crust_reservoir.hpp:15-20`, declared to the document as `maximum_surface_packets_per_owner` / `maximum_live_reservoir_packets` / `maximum_proxy_transfers_per_step`, `cpp/src/engine/crust_reservoir_serialization.cpp:140-145`). "They are numerical memory-safety limits, not physical flux or capacity limits" (`cpp/src/engine/README.md:324`); the type header states the same as "not physical material-flux or reservoir-capacity limits" (`cpp/src/engine/types/crust_reservoir.hpp:12-14`).

See [Crust Material Shadow and Dry-Rock Reservoirs](./features/crust-material-and-reservoirs.md).

### permafrost

Perennially frozen ground, modelled as a **diagnostic index enrichment** in `src/magic_geo/permafrost_diagnostics.py`. Water cells short-circuit to `no_permafrost` with zeroed indices (`:41-42`).

Cell fields written: `permafrost_extent_index`, `active_layer_depth_m`, `ground_ice_content_index`, `permafrost_class`, `permafrost_region_id`; plus a `permafrost_regions` array of contiguous components.

Classification thresholds on `extent` and `ice_thickness_m`, in evaluation order (`src/magic_geo/permafrost_diagnostics.py:21-32`; `PERMAFROST_THRESHOLD = 0.45` at `:7`):

| Condition | `permafrost_class` |
| --- | --- |
| `extent < 0.15` | `no_permafrost` |
| `extent < 0.45` | `seasonal_frost` |
| `ice_thickness_m >= 120.0` and `extent >= 0.62` | `ice_cemented_permafrost` |
| `extent >= 0.78` | `continuous_permafrost` |
| `extent >= 0.62` | `discontinuous_permafrost` |
| otherwise | `sporadic_permafrost` |

Inputs include monthly ground temperature, freezing/thawing degree indices, `frost_months`, absolute latitude, elevation, ice thickness, soil moisture, soil organic-matter fraction, drainage, and seasonal aridity (`src/magic_geo/permafrost_diagnostics.py:44-58`).

Permafrost is a required output of the `cryosphere` [layer contract](#layer-contract) (`permafrost_regions`, kind `list`, `src/magic_geo/geo_layer_contracts.py:214`). Being a `list`, an empty result is valid evidence of an absent phenomenon on a hot world.

See [Cryosphere: Ice Sheets, Glaciers and Permafrost](./features/cryosphere.md).

### plate domain

The set of cells currently assigned to one plate — i.e. the plate's footprint on the fixed mesh, not a moving mesh partition. Model identity `rotating_voronoi_plate_domains_v3`, with `domain_assignment = nearest_rotated_plate_center_on_fixed_spherical_mesh` (`cpp/src/engine/process_serialization.cpp:2684, 2721`).

| Aspect | Value | Source |
| --- | --- | --- |
| Plate count | `tectonics.plate_count`, default `14`, range `[2, 256]`, must be `< mesh.cell_count` | `src/magic_geo/config.py:263-268`, `:502-503` |
| Per-cell assignment | `cells[].plate_id`; provenance snapshot `cells[].initial_plate_id` | `cpp/src/engine/entity_serialization.cpp` |
| Reassignment tracking | `plate_assignment_change_count`, `last_plate_assignment_change_iteration` | per-cell |
| Per-step record | `plate_motion_history[].cell_plate_ids` (full assignment), `reassigned_cell_count`, `reassigned_cell_fraction` | `cpp/src/engine/types/earth_system.hpp` |

Each motion step rotates every plate center by its Euler step and reassigns cells to the nearest rotated center. The **mesh itself never moves**; only the assignment changes, which is why crust must be remapped through the [forward overlap](#forward-overlap) [crust transport plan](#crust-transport-plan) rather than carried by moving geometry.

The initial continental partition uses one graph pass at self-weight `0.77` over a ranked, plate-biased continental potential to meet `tectonics.continental_crust_fraction_target` (default `0.34`); the model string is `ranked_graph_coherent_plate_biased_continental_mask_v2` (`cpp/src/engine/process_serialization.cpp:2722-2723`, `README.md:347`).

See [Tectonics and Plates](./features/tectonics-and-plates.md).

### priority flood

The depression-filling algorithm that produces `filled_elevation_m`, `spill_elevation_m`, `spill_to`, `depression_depth_m`, and `is_closed_basin`. Implemented in `compute_priority_flood_spill` (`cpp/src/engine/hydrology.cpp:231`).

Mechanics:

1. Every cell's `filled_elevation_m` is initialized to `+infinity`; depression depth, spill target, and closed-basin flag are reset (`cpp/src/engine/hydrology.cpp:234-243`).
2. Every water cell is seeded at elevation `0.0` and pushed onto a min-heap (`:239-242`).
3. If there are no water cells at all, the single lowest-elevation cell is seeded instead, so the solve is well-posed on a land world (`:245-253`).
4. The heap pops in ascending `(elevation, cell_id)` order — the cell-id tie-break makes the traversal deterministic (`FloodItemGreater`, `:222-229`).

The result is a hydrologically conditioned surface with no interior sinks, on which flow routing and the water budget then run. Cells whose `filled_elevation_m` exceeds their `elevation_m` are inside a depression; `depression_depth_m` is that difference and `spill_elevation_m` is the outlet sill (`docs/layers_reference.md:304, 329`).

Priority flood produces the *counterfactual* fill. Whether the fill is actually applied depends on the [geologic depression](#geologic-depression) policy and, for numeric depressions, on the correction selection between filling, breaching, and temporary-lake deferral — recorded per event in `numeric_depression_correction_history[]`, which retains both the applied correction and the counterfactual fill candidate.

See [Hydrology, Rivers and Lakes](./features/hydrology-and-rivers.md).

### replay validator

A Python module that **independently reconstructs** a native invariant from the serialized world and rejects any divergence. Each returns `{"passed": bool, "metrics": {...}, "failures": [...]}` and is wrapped by `validate_physics_replays` into one check whose `expected` map enumerates both what *is* replayed (`True`) and what is deliberately **not** resolved (`False`) — the mechanism that keeps replay integrity separate from physical claims (`src/magic_geo/geo_validation_physics.py:2495-2540`).

| Module (under `src/magic_geo/`) | Lines | Check name (domain) |
| --- | --- | --- |
| `plate_boundary_edge_validation.py` | 1552 | `exact_directed_plate_boundary_segment_replay` (tectonics) |
| `initial_oceanic_crust_age_validation.py` | 989 | `initial_oceanic_crust_age_graph_replay` (tectonics) |
| `crust_transport_validation.py` | 2460 | `conservative_crust_overlap_replay` (tectonics) |
| `crust_process_validation.py` | 1109 | consumed by crust transport (`validate_crust_process_reason_ledger`) |
| `crust_coverage_geometry_replay.py` | 1159 | standalone fixture-scale geometric replay (≤ 1024 cells) |
| `oceanic_age_depth_validation.py` | 1780 | `oceanic_age_depth_thermal_target_replay` (tectonics) |
| `crust_overlap_candidate_fate_validation.py` | 1140 | `overlap_candidate_fate_crosswalk_replay` (tectonics) |
| `crust_material_shadow_validation.py` | 1616 | `persistent_crust_material_shadow_replay` (tectonics) |
| `crust_dry_rock_accounting_validation.py` | 1341 | `finite_crust_dry_rock_accounting_replay` (tectonics) |
| `sediment_source_partition_validation.py` | 619 | `sediment_alluvium_bedrock_source_partition_replay` (sediment) |
| `sediment_interface_validation.py` | 2412 | `bedrock_mobile_sediment_interface_replay` (sediment) |
| `geo_evolution_provenance.py` | 408 | `history_family_temporal_semantics` (evolution_provenance) |

Check names are registered at `src/magic_geo/geo_validation_physics.py:2511, 2541, 2582, 2603, 2649, 2689, 2711, 2734, 2756`.

Two design rules distinguish a replay validator from a consistency check:

1. **It must not consume the derived field it is checking.** The boundary-segment replay "deliberately ignores the smoothed per-cell boundary arrays" and rebuilds segment identity from mesh rings, plate assignments, axes, and speeds (`cpp/src/engine/README.md:205-209`). The candidate-fate replay rebuilds its operands by first running the independent overlap-transport and boundary-segment replays it imports (`src/magic_geo/crust_overlap_candidate_fate_validation.py:8-9`) rather than trusting the serialized crosswalk summaries, and bounds candidate areas with "finite operation/operand-count gamma envelopes rather than a blanket absolute or relative tolerance" (`docs/geo_generation_maturation_deep_audit.md:98`).
2. **It must state its non-claims.** The `expected` map is where `physical_polarity_resolved: False`, `slab_selection_resolved: False`, etc. are asserted alongside the positive claims.

`crust_coverage_geometry_replay.py` goes further: it rediscovers overlap pairs by brute-force O(N²) spherical-cap filtering and gnomonic triangle clipping, never reading the serialized overlap CSR — but it is capped at 1,024 cells, so it "is not yet a 4,096-cell independent geometry certificate" (`docs/geo_generation_maturation_deep_audit.md:222`).

See [Validation](./12-validation.md) and [Testing and Quality Gates](./18-testing.md).

### reservoir

One of the three compartments of the [dry-rock accounting](#dry-rock-accounting) counter-model. Declared `reservoir_order` (`cpp/src/engine/crust_reservoir_serialization.cpp:117-118`):

| Index | Reservoir | Owner semantics | State |
| --- | --- | --- | --- |
| 0 | `surface_basement_crust` | Per cell | Populated; packet tables `opening_surface_packets` / `transported_surface_packets` / `closing_surface_packets` |
| 1 | `upper_mantle_exchange` | One global pool, no spatial coordinates | Populated; see [exchange reserve](#exchange-reserve) |
| 2 | `subducted_slab` | `subducting_source_plate_id` (`:169-170`) | **Empty.** `subducted_slab_phase_2_state = plate_resolved_empty_reservoir_no_transfer_mechanism_enabled` (`:171-172`) |

Accounting scope: `surface_basement_crust_upper_mantle_exchange_and_plate_resolved_subducted_slab` (`:115-116`).

Two behavioural rules matter when reading the ledgers:

- `exact_exhaustion_semantics = empty_reservoir_valid_and_reseed_requires_a_later_explicit_transfer` — a reservoir reaching zero is a valid state, not an error (`:165-166`).
- `insufficient_exchange_semantics = fail_closed_without_publishing_partial_accounting_state` — a withdrawal that cannot be satisfied aborts the step rather than emitting a partially reconciled history (`:167-168`).

Arithmetic closure across the three tables "must never be described as physical provenance, solid-volume or phase closure, sediment/subduction coupling, or a resolved mantle/slab crust cycle" (`cpp/src/engine/README.md:318-320`).

See [Crust Material Shadow and Dry-Rock Reservoirs](./features/crust-material-and-reservoirs.md).

---

## Terms S–Z

### sediment interface contract

The rule that **every** native terrain or material mutation must obey: two canonical fields, one derived field, and only two checked primitives may change them.

| Element | Value | Source |
| --- | --- | --- |
| `model_type` | `explicit_bedrock_surface_mobile_sediment_interface_v1` | `cpp/src/engine/process_serialization.cpp:1835-1836` |
| `canonical_state_fields` | `["bedrock_surface_elevation_m", "sediment_thickness_m"]` | `:1838-1839` |
| `derived_surface_field` | `elevation_m` | `:1840` |
| `interface_equation` | `elevation_m = bedrock_surface_elevation_m + sediment_thickness_m` | `:1843-1844` |
| `initialization_equation` | `bedrock_surface_elevation_m = elevation_m - sediment_thickness_m` | `:1845-1846` |
| `material_update_equation` | `bedrock' = bedrock + vertical_displacement - bedrock_erosion; sediment' = sediment - alluvium_entrainment + deposition; elevation' = bedrock' + sediment'` | `:1847-1848` |
| `sea_level_datum_update` | `bedrock' = bedrock - sea_level_adjustment_m; sediment' = sediment` | `:1849-1850` |
| `replay_tolerance_model` | `decimal_quantization_forward_error_by_serialized_operand_precision_v1` | `:1851-1852` |
| `canonical_state_serialization_decimal_places` | `10` | `:1853` |
| `minimum_replay_operand_serialization_decimal_places` | `8` | `:1854-1855` |

Implementing primitives, all in `cpp/src/engine/sediment_partition.cpp`:

| Primitive | Line | Purpose |
| --- | --- | --- |
| `initialize_sediment_interface` | `:91` | Derive bedrock from an opening surface and mobile thickness |
| `shift_sediment_interface_datum` | `:123` | Sea-level solve; moves bedrock and surface, leaves thickness alone |
| `apply_sediment_interface_material_change` | `:155` | The single combined tectonic + hillslope + fluvial commit, numeric-breach excavation/redeposition, and terminal glacial transport |
| `validate_sediment_interface` | `:82` | Re-checks the identity |
| `maximum_sediment_interface_closure_residual_m` | — | Reduces the worst residual for the summary |
| `validate_sediment_source_partition` | — | Audits the alluvium-vs-bedrock split |

The engine invariant is stated as a hard boundary: mutation code updates the two canonical fields **through the checked helpers** and *derives* `elevation_m`; "it must not independently mutate all three fields" (`cpp/src/engine/README.md:330-332`).

Resolution flags all `false`: `dry_rock_mass_resolved`, `sediment_density_resolved`, `porosity_resolved`, `compaction_resolved`, `grain_provenance_resolved`, `chemical_weathering_resolved` (`cpp/src/engine/process_serialization.cpp:1860-1865`).

See [Sediment, Routing and Stratigraphy](./features/sediment-and-stratigraphy.md).

### shadow kernel

The accelerator-side FP64 reduction whose result is validated against bounds and then **thrown away**. The OpenCL entry point is `reduce_crust_overlap_continuous_shadow` (`cpp/src/opencl_compute.cpp:622`); the parity harness lives in `cpp/src/crust_overlap_shadow.cpp`, built as its own CTest target `magic_geo_crust_overlap_shadow`.

Behaviour: when OpenCL or CUDA is active, one ordered FP64 work item per destination runs over the **exact CPU [coverage CSR](#coverage-csr)**, reconstructs three incoming extensive moments and derived thickness/density/age, checks the returned values against finite operand/operation-count bounds, records dedicated telemetry, and discards the result (`cpp/src/engine/README.md:294-299`).

Declared telemetry (`cpp/src/opencl_compute.cpp:2104-2150, 2176-2230`):

| Key | Value / meaning |
| --- | --- |
| `crust_overlap_continuous_shadow_model` | `cpu_authoritative_overlap_csr_continuous_moment_shadow_v1` |
| `crust_overlap_continuous_shadow_scope` | `raw_extensive_moments_and_derived_continuous_state_only` |
| `crust_overlap_continuous_shadow_only` | `true` |
| `crust_overlap_continuous_shadow_authoritative` | `false` |
| `crust_overlap_continuous_shadow_result_used_for_state` | `false` |
| `crust_overlap_accelerator_geometry_parity_demonstrated` | `false` |
| `crust_overlap_continuous_shadow_device_dispatch_count` | Actual device dispatches (OpenCL + CUDA) |
| `crust_overlap_continuous_shadow_validated_transition_count` | Transitions checked |
| `crust_overlap_continuous_shadow_failure_count` | Bound violations |
| `crust_overlap_continuous_shadow_validation_status` | Tri-state derived from the above |

CPU geometry, coverage, membership classes, categories, production remap, and scientific state remain authoritative; **complete parity stays false** (`cpp/src/engine/README.md:299-300`). The repository additionally records that the development host "has no usable OpenCL platform or CUDA compiler/device, so only CPU/stub integration and pure reconciliation logic are verified here" (`:301-303`).

See [Compute Backends](./09-compute-backends.md).

### stencil neighbors

`cells[].neighbors` — the **process adjacency graph** consumed by the climate, hydrology, and sediment operators. It is deliberately separate from the exact [control volume](#control-volume) edge topology.

| Aspect | Value | Source |
| --- | --- | --- |
| Config | `mesh.neighbor_count`, default `7`, range `[4, 16]` | `src/magic_geo/config.py:250-255` |
| Applies to | The Fibonacci backend only; geodesic derives its stencil from primal triangle edges | `docs/configuration_reference.md:112`, `docs/example_seed_gallery.md:143-145` |
| Symmetrized | Yes — each `i -> j` link is mirrored back into `j`'s list | `cpp/src/engine/mesh.cpp:808-813` |
| Does **not** change | The control-volume tessellation or `control_volume_edge_neighbor_ids` | `README.md:286` |

The distinction is architecturally significant. The exact spherical control volumes are already suitable as the geometric basis of conservative remapping — and crust transport uses them — but "the center-neighbor climate/hydrology/sediment operators still consume their older center-neighbor stencil and have no manufactured-solution convergence evidence" (`docs/geo_generation_maturation_deep_audit.md:202`). Migrating those operators onto shared-edge flux geometry is listed as future work (`:206, :472`).

Note also the downstream `cell_adjacency_edges` structure (built by `src/magic_geo/cell_geometry.py`) is a third, diagnostic structure — a one-segment approximate shared-boundary edge list, not the process stencil and not the exact dual boundary.

See [Mesh and Geometry](./features/mesh-and-geometry.md).

### stream power

The fluvial incision law. Evaluated per land cell in the maturation loop (`cpp/src/engine/earth_system.cpp:978-994`):

```
slope     = max(0, cell.hydrologic_flow_slope)                     # 0 if flow_to < 0
acc_norm  = clamp(cell.flow_accumulation / acc_scale, 0.0, 3.0)
erodability = 1.0 / lithology_resistance(cell.lithology)

stream          = stream_power_coefficient * erodability
                  * pow(acc_norm, drainage_exponent)
                  * pow(max(0, slope * 900.0), slope_exponent)

erosion_depth_m = stream * maturation_timestep_scale
cell.erosion_rate = stream                                          # NOT the applied depth
```

with `acc_scale` = the 95th-percentile land flow accumulation for the step, floored at `1.0` (`cpp/src/engine/earth_system.cpp:946`).

Parameters:

| Config field | Default | Range | Role |
| --- | --- | --- | --- |
| `erosion.stream_power_coefficient` | `7.5` | `[0.0, 1000.0]` | Reference-step incision coefficient (`src/magic_geo/config.py:388`) |
| `erosion.drainage_exponent` | `0.5` | `[0.0, 2.0]` | Exponent on normalized accumulation (`:394`) |
| `erosion.slope_exponent` | `1.0` | `[0.0, 3.0]` | Exponent on `slope * 900` (`:400`) |

**The exported `erosion_rate` is a reference-step response, not the applied depth.** The comment is explicit: only the applied incision/source depth is integrated over the configured nominal transition, "otherwise merely refining dt changes soils, ecosystems, land use, and resource diagnostics by construction" (`cpp/src/engine/earth_system.cpp:988-992`). The clock restates it as `cell_erosion_rate_semantics = stream_power_response_per_reference_step_not_applied_transition_depth` and `stream_incision_update = cell_erosion_rate_times_maturation_timestep_scale` (`cpp/src/engine/process_serialization.cpp:2101-2104`).

Water cells get `erosion_rate = 0.0` and are skipped (`cpp/src/engine/earth_system.cpp:974-977`).

See [Erosion, Maturation and Landscape Evolution](./features/erosion-and-maturation.md).

### thermal subsidence target

The **relative** oceanic basement-subsidence target, `cells[].thermal_subsidence_target_m`, computed by `oceanic_age_depth_thermal_subsidence_m` (`cpp/src/engine/oceanic_age_depth.cpp:5-48`):

```
non-oceanic-like            -> 0
age <= 70 Ma                -> -( 350 * sqrt(age) )
age >  70 Ma                -> -( 350*sqrt(70) + 3200 * ( exp(-70/62.8) - exp(-age/62.8) ) )
```

Constants (`cpp/src/engine/internal.hpp:26-30`): `OCEANIC_AGE_DEPTH_YOUNG_CUTOFF_MA = 70.0`, `..._YOUNG_COEFFICIENT_M_PER_SQRT_MA = 350.0`, `..._OLD_EXPONENTIAL_SCALE_M = 3200.0`, `..._OLD_EFOLDING_TIME_MA = 62.8`. Values are ≤ 0 (below the datum) by construction; a non-finite or negative relative subsidence is a hard error.

Provenance and honest scope, verbatim in spirit from `cpp/src/engine/README.md:143-148`: the young `350√t` and old `3200·exp(−t/62.8)` shapes come from [Parsons and Sclater (1977)](https://doi.org/10.1029/JB082i005p00803); the implementation changes branches at 70 Ma and offsets the old branch to enforce **C0 value continuity**; it "does not claim derivative continuity or reproduce the paper's absolute-depth datum."

The step-to-step difference is applied at gain 1 outside the [dynamic relief](#dynamic-relief) clamp, exactly like [isostatic equilibrium](#isostatic-equilibrium). `thermal_equilibrium_change_m` is "the sole serialized thermal-change array" (`cpp/src/engine/README.md:154`). A finite nonnegative age guard rejects invalid crust ages before evaluation.

Unresolved: a distinct realized thermal-relief state, absolute basement calibration, sediment loading, thermal structure, heat flow, dynamic topography, flexure, and physical dynamics (`cpp/src/engine/README.md:162-165`). The quasi-static choice rests on the timescale separation between the nominal 5 Ma reference interval and 3–4 ka degree-2-to-20 viscoelastic relaxation estimates from [O'Connell (1971)](https://doi.org/10.1111/j.1365-246X.1971.tb01823.x); "it does not make the nominal interval or operator physically time-calibrated" (`:158-162`).

See [Topography, Isostasy and Thermal Subsidence](./features/topography-and-isostasy.md).

### unresolved claim

A physical statement the codebase explicitly declines to make, encoded as a `*_resolved: false` boolean in the serialized document and/or as a declared model limitation.

The 12 declared `GEO_MODEL_LIMITATIONS`, carried into every geo validation report and every suite report (`src/magic_geo/geo_validation.py:28-41`):

| # | Limitation (abbreviated; full text at the cited lines) |
| --- | --- |
| 1 | The simulation clock orders procedural stages but has no calibrated physical duration |
| 2 | The diagnostic atmosphere is not a three-dimensional mass-conserving circulation solver |
| 3 | Configured ocean inventory is not a closed total-water partition across ocean, ice, groundwater, lakes, and atmosphere |
| 4 | First-order conservative crust overlap is diffusive, CPU-authoritative, guarded by a 16,384-fragment cap without exhaustive worst-case proof; accelerator geometry/category/production-state parity and device-lane evidence remain unresolved |
| 5 | The pair-wide overlap candidate crosswalk accounts for every excess class but resolves no local fragment-to-segment link, physical polarity, allocation, material fate, slab transfer, or state mutation |
| 6 | Post-transport tectonic rules expose ordered per-reason state-moment changes, not physical reservoir, material-provenance, energy, or phase fluxes |
| 7 | Initial oceanic-like crust age is a replayable ridge-distance graph field on one globally averaged nominal half-spreading rate — not local flowlines, calibrated spreading, subduction sinks, or physical seafloor creation/destruction |
| 8 | The continuity-adjusted Parsons–Sclater relation is authoritative only for a *relative* thermal-subsidence target curve; no realized thermal relief, absolute basement depth, heat flow, dynamic topography, flexure, or physical dynamics |
| 9 | Dry-rock packets and the finite three-reservoir counter-model close numerical accounting but remain non-authoritative and resolve no physical transfer basis, fate, solid volume, phase, mantle, slab, sediment coupling, or global crust cycle |
| 10 | The bedrock/mobile-sediment interface replays, but bulk reference-volume closure resolves no dry-rock mass, sediment density, porosity, compaction, grain provenance, or chemical weathering |
| 11 | Ecosystem, species, wildfire, and resource layers are diagnostic index models, not calibrated population or process solvers |
| 12 | Earth empirical fit remains a separate calibration verdict from internal contract integrity |

Recurring `*_resolved: false` flag families in the document:

| Family | Example keys |
| --- | --- |
| Time | `physical_time_resolved`, `nominal_time_calibrated`, `absolute_geological_age_resolved`, `process_rate_calibration_resolved`, `time_step_convergence_demonstrated` |
| Tectonic fate | `physical_polarity_resolved`, `slab_selection_resolved`, `slab_transfer_resolved`, `physical_material_fate_resolved`, `local_segment_link_resolved`, `connected_atom_topology_resolved` |
| Material | `physical_source_sink_resolved`, `material_provenance_resolved`, `solid_volume_resolved`, `phase_resolved`, `mass_weighted_age_resolved`, `global_crust_cycle_mass_conservation_resolved` |
| Sediment | `dry_rock_mass_resolved`, `sediment_density_resolved`, `porosity_resolved`, `compaction_resolved`, `grain_provenance_resolved`, `chemical_weathering_resolved` |
| Accelerator | `crust_overlap_continuous_shadow_authoritative`, `crust_overlap_accelerator_geometry_parity_demonstrated` |
| Contract | `empirical_realism_proven` (every layer contract) |

The engine invariant requires serializers and summaries to **preserve** these false flags (`cpp/src/engine/README.md:271-273`, `:318-320`). A consumer that drops them is misrepresenting the model.

See [Project Overview](./01-overview.md) and [Validation](./12-validation.md).

---

## Enumerated value vocabularies

Every categorical cell field draws from a fixed, ordered name table in `cpp/src/engine/schema_names.hpp` (or `constants.hpp` for process reasons). Index order matters: per-stage history ledgers serialize these as **numeric codes**, while per-cell fields serialize the **names**.

| Table | Count | Values in index order | Source |
| --- | --- | --- | --- |
| `CRUST_NAMES` | 9 | `oceanic`, `continental`, `transitional`, `volcanic_arc`, `craton`, `orogen`, `rift_basin`, `sedimentary_basin`, `accreted_terrane` | `cpp/src/engine/schema_names.hpp:7-10` |
| `LITHOLOGY_NAMES` | 7 | `basalt`, `granite`, `limestone`, `sandstone`, `shale`, `volcanic`, `metamorphic` | `:11-13` |
| `BOUNDARY_NAMES` | 5 | `interior`, `convergent`, `divergent`, `transform`, `mixed` | `:14-16` |
| `SOIL_NAMES` | 11 | `none`, `thin_mountain`, `volcanic`, `alluvial`, `arid`, `tropical`, `temperate`, `boreal`, `tundra`, `wetland`, `saline` | `:17-20` |
| `BIOME_NAMES` | 16 | `ocean`, `continental_shelf`, `lake`, `ice_cap`, `tundra`, `boreal_forest`, `temperate_forest`, `temperate_grassland`, `mediterranean_scrub`, `cold_desert`, `hot_desert`, `savanna`, `tropical_seasonal_forest`, `tropical_rainforest`, `alpine`, `wetland` | `:21-26` |
| `WATER_BODY_NAMES` | 6 | `land`, `ocean`, `continental_shelf`, `inland_sea`, `fresh_lake`, `saline_basin` | `:34-36` |
| `LANDFORM_NAMES` | 20 | `open_ocean`, `continental_shelf`, `inland_sea`, `lacustrine_basin`, `salt_flat`, `ice_field`, `mountain_belt`, `volcanic_arc`, `rift_valley`, `trench`, `river_valley`, `floodplain`, `delta`, `alluvial_fan`, `coastal_plain`, `stable_lowland`, `fjord`, `glacial_valley`, `moraine`, `glacial_lake` | `:37-43` |
| `WATERSHED_OUTLET_NAMES` | 5 | `ocean`, `lake`, `saline_basin`, `inland_sea`, `closed_land` | `:50-52` |
| `DEPRESSION_POLICY_NAMES` | 6 | `none`, `corrected_numeric`, `preserved_geologic`, `overflow_spill`, `dry_closed`, `temporary_numeric_lake` | `:53-56` |
| `CRUST_PROCESS_REASON_NAMES` | 10 | `quiet_oceanic_aging`, `oceanic_ridge_rejuvenation`, `oceanic_ridge_creation_relaxation`, `divergent_continental_rifting`, `oceanic_convergence_subduction_proxy`, `continental_collision_orogeny`, `plate_crossing_accretion_proxy`, `age_bound_enforcement`, `thickness_bound_enforcement`, `density_bound_enforcement` | `cpp/src/engine/constants.hpp:86-97` |

A known documentation hazard: `docs/layers_reference.md:173` records that the per-stage history serializes `lithology` as numeric codes 0–6 while the per-cell layer uses names, and that the debugger's alphabetical class ordering "may not match the engine enum". The engine enum order is the one in the table above.

Five of the ten process-reason names end in `_proxy` (`oceanic_convergence_subduction_proxy`, `plate_crossing_accretion_proxy`) or `_enforcement` (`age_bound_enforcement`, `thickness_bound_enforcement`, `density_bound_enforcement`). Those are rule-trigger labels for ordered state-moment bookkeeping, not physical flux mechanisms — see limitation 6 in [unresolved claim](#unresolved-claim).

---

## Limitations and unresolved claims

This glossary inherits every limitation of the systems it names. Specific to the glossary itself:

- **It is not a schema.** Field lists here are illustrative subsets chosen for definition clarity. The authoritative enumerations are `cpp/src/engine/world_serialization.cpp` (top-level key order), `cpp/src/engine/entity_serialization.cpp` (per-entity records), and `cpp/src/engine/summary.cpp` plus `cpp/src/engine/crust_reservoir_serialization.cpp` (summary keys). See [World Document Schema](./10-world-schema.md).
- **Two conflicting atom/class measurements are on record.** `cpp/src/engine/README.md:286-289` reports `3,503,886` atoms → `111,022` classes (about `31.6x`); `docs/geo_generation_maturation_deep_audit.md:406` reports `3,483,059` → `109,777` (about `31.7x`) for a reference described the same way. This page reports both and asserts neither as current. The related payload-size and RSS figures (`178,764,102` uncompressed JSON bytes, `371,176 KB` maximum RSS) belong only to a "historical pre-initial-age/expanded-round-trip checkpoint"; current payload size and RSS "have not been remeasured" (`cpp/src/engine/README.md:288-292`).
- **The 16,384-atom / 16,384-class local caps lack exhaustive worst-case proof.** The strongest recorded stress cases (180° per step, 32 plates, 512-cell Fibonacci and 642-cell geodesic) stay well below the bound, but "they are not an exhaustive combinatorial or worst-case proof of the bound" (`docs/geo_generation_maturation_deep_audit.md:412`).
- **`nominal` never means calibrated.** Every km/Ma rate on a [boundary segment](#boundary-segment), every Ma interval on a [maturation stage](#maturation-stage), and the whole [nominal timestep](#nominal-timestep) machinery are ordered and dimensionally labelled but uncalibrated. `physical_time_resolved` and `nominal_time_calibrated` are `false` throughout, and `time_step_convergence_demonstrated` is `false`.
- **Subduction polarity is unknown, not inferred.** A sole oceanic-like side at a convergent segment supplies only *candidate* subducting/overriding sides. `physical_polarity_status` stays `unknown`, `physical_polarity_source` stays `none`, confidence stays zero, and slab selection, slab geometry/transfer, and material fate remain `false` (`cpp/src/engine/README.md:213-220`).
- **The [material shadow](#material-shadow) and [dry-rock accounting](#dry-rock-accounting) are counter-models, not mass provenance.** Their arithmetic closes; that closure is explicitly not physical provenance, solid-volume or phase closure, sediment/subduction coupling, or a resolved mantle/slab crust cycle.
- **Accelerator parity is false.** Only a discarded continuous-moment CSR [shadow kernel](#shadow-kernel) has been implemented; geometry, coverage, membership classes, categories, and production state stay CPU-authoritative, `crust_overlap_accelerator_geometry_parity_demonstrated` is `false`, and the recorded development host has no usable OpenCL platform or CUDA device.
- **A passing [layer contract](#layer-contract) is not a realism claim.** `empirical_realism_proven` is hardcoded `False` on every one of the 14 layers.
- **A `not_applicable` check is not a pass**, and this page's definitions of `passed` semantics should be read together with the `status` field, never with the `passed` boolean alone.
- **Debugger-layer documentation has measured gaps.** The reference profile records 12 layers (2.7%) resolved by the `generated` fallback tier only, including `healpix_like_lon_bin`, `healpix_like_nside`, `healpix_like_ring`, `mean_neighbor_boundary_segment_quality`, `s2_like_cell_level`, `s2_like_x`, `s2_like_y`, and `last_plate_assignment_change_iteration` (`docs/layers_reference.md:143, 199`).
- **"HEALPix-like" and "S2-like" are compatibility indices**, and "must not be presented as standards-compliant implementations" (`docs/geo_generation_maturation_deep_audit.md:202`).

---

## See also

- [Project Overview](./01-overview.md) — the epistemic contract this glossary encodes
- [Architecture](./04-architecture.md) — where each term's implementation lives
- [Configuration Reference](./05-configuration-reference.md) — every configurable term with defaults and ranges
- [World Document Schema](./10-world-schema.md) — the authoritative field enumeration
- [Serialization and World Formats](./11-serialization.md) — precision contracts behind `roundtrip_num`, canonical-state decimals, and replay operands
- [Validation](./12-validation.md) — check statuses, domains, layer contracts, replay validators
- [Geo Validation Suite](./13-geo-validation-suite.md) — scenarios, relations, determinism, empirical bundles
- [Calibration Against Real-Earth Data](./14-calibration.md) — targets, coverage vs fit, ensembles
- [Debug Exports and Visualization](./16-debug-and-visualization.md) — layers, kinds, roles, manifest revisions
- [Native Engine (C++ Core)](./08-native-engine.md) — translation units and invariants
- [Compute Backends (CPU, OpenCL, CUDA)](./09-compute-backends.md) — backend telemetry and the shadow kernel
- [Mesh and Geometry](./features/mesh-and-geometry.md)
- [Tectonics and Plates](./features/tectonics-and-plates.md)
- [Plate Boundary Segment Ledger](./features/plate-boundary-ledger.md)
- [Crust Transport and Forward Overlap](./features/crust-transport-and-overlap.md)
- [Crust Material Shadow and Dry-Rock Reservoirs](./features/crust-material-and-reservoirs.md)
- [Topography, Isostasy and Thermal Subsidence](./features/topography-and-isostasy.md)
- [Erosion, Maturation and Landscape Evolution](./features/erosion-and-maturation.md)
- [Sediment, Routing and Stratigraphy](./features/sediment-and-stratigraphy.md)
- [Hydrology, Rivers and Lakes](./features/hydrology-and-rivers.md)
- [Cryosphere: Ice Sheets, Glaciers and Permafrost](./features/cryosphere.md)
- [Biomes, Ecosystems and Disturbance](./features/biomes-and-ecology.md)
- [Troubleshooting and FAQ](./22-troubleshooting.md)
