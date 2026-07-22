# Crust Transport and Forward Overlap

[Wiki home](../README.md) > Features

Crust transport is the stage that moves per-cell crust state (age, thickness, density, crust type, lithology) across a *moving* plate partition on a fixed spherical mesh, without ever resampling onto a raster. It is implemented as an exact spherical **forward-overlap** operator: every source control volume is rigidly rotated by its plate's Euler step, clipped against every candidate destination control volume in a destination-local gnomonic chart, and the resulting sparse destination-major CSR of positive overlap areas becomes the transport plan. The plan is CPU-authoritative by construction and by declared contract; accelerators only ever run a separately named, discarded-output continuous-moment shadow over the *already computed* CPU CSR. Everything downstream — the coverage multiplicity arrangement, the coalesced membership-area class ledger, and the candidate-fate crosswalk — is a diagnostic built on that same exact geometry, and each of those diagnostics carries explicit `*_resolved: false` flags for the physical claims it deliberately does not make.

## On this page

- [The problem](#the-problem)
- [Where transport runs](#where-transport-runs)
- [Exact spherical forward-overlap geometry](#exact-spherical-forward-overlap-geometry)
- [Why the geometry stays on CPU](#why-the-geometry-stays-on-cpu)
- [The transport plan structure](#the-transport-plan-structure)
- [The extensive-state remap](#the-extensive-state-remap)
- [Raw arrangement diagnostics: lines and atoms](#raw-arrangement-diagnostics-lines-and-atoms)
- [The coverage membership area class ledger](#the-coverage-membership-area-class-ledger)
- [What a membership class is not](#what-a-membership-class-is-not)
- [The candidate fate crosswalk](#the-candidate-fate-crosswalk)
- [Reduction ratio, payload and RSS figures](#reduction-ratio-payload-and-rss-figures)
- [Replay validators](#replay-validators)
- [Worked example: reading one destination row](#worked-example-reading-one-destination-row)
- [Running the validators](#running-the-validators)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

---

## The problem

The mesh is **fixed**. Cells never move, never split, never merge; each cell owns a spherical control volume whose vertices are serialized as `cells[].control_volume_vertices_3d` and whose area is `cells[].area_km2`. What *does* move is the plate partition: at every motion step each plate rotates about its Euler axis by `step_rotation_deg`, cells are re-assigned to the nearest rotated plate center, and the crust that was attached to the old domain must end up somewhere.

Three constraints shape the design:

| Constraint | Consequence |
|---|---|
| No raster, no re-meshing | The operator must be a **cell-to-cell** mapping on the sphere, expressed as a sparse matrix over the fixed mesh |
| Crust state is *extensive* (a volume, a density-weighted volume, an age-volume moment), not intensive | The mapping must move **moments**, and closure must be checked on the moments, not on the per-cell means |
| Plate motion physically extends and compresses crust | Destination columns must **not** be normalized: a destination that receives less than its own area is a genuine gap, and one that receives more is genuine overlap |

The last point is stated directly in the declared model: `destination_overlap_areas_normalized` is `false` (`cpp/src/engine/process_serialization.cpp:2844`) and the plan struct's comment says destination columns are "intentionally not normalized because gaps and multiple coverage represent kinematic extension and compression" (`cpp/src/engine/types/earth_system.hpp:559-561`).

The consequence is that a single destination cell can be covered zero times (a gap), once, or many times, and the *coverage* of a destination is not a partition of unity. Making that measurable — exactly, in area — is what the coverage arrangement and the membership-area class ledger exist for.

## Where transport runs

| Call site | Source | What it builds |
|---|---|---|
| Step-0 checkpoint | `cpp/src/engine/pipeline.cpp:39` | `build_identity_crust_transport_plan(cells)` — the identity (no-motion) plan carried by `plate_motion_history[0]` |
| Provisional identity | `cpp/src/engine/tectonics.cpp:398-399` | `provisional_identity_transport` built inside `derive_crust_and_topography` so that `build_plate_boundary_segments` can produce the provisional segment set that feeds `build_initial_oceanic_crust_age_field` (`tectonics.cpp:400-415`). It is discarded afterwards and never enters `plate_motion_history` |
| Every maturation iteration | `cpp/src/engine/tectonics.cpp:1139` | `build_forward_overlap_crust_transport_plan(...)` inside `advance_plate_motion_and_crust`, immediately after `assign_plates` + `classify_boundaries` (`cpp/src/engine/tectonics.cpp:1135-1136`) |

Plate rotation happens first (`cpp/src/engine/tectonics.cpp:1122-1134`): each plate's `step_rotation_deg = angular_speed * params.plate_motion_scale_deg_per_step * timestep_scale`, the plate center is rotated, and `cumulative_rotation_deg` accumulates. Only then is the transport plan built from the **previous** per-cell plate assignment (`previous_plate_ids`) and the **previous** crust state arrays.

Immediately after the plan is built, three consumers run in fixed order:

1. `reconcile_accelerated_crust_overlap_continuous_shadow(...)` (`cpp/src/engine/tectonics.cpp:1151`) — the discarded accelerator shadow.
2. `begin_crust_material_shadow_step(...)` (`cpp/src/engine/tectonics.cpp:1158`) — the non-authoritative dry-rock mass shadow, which advects its packets using the same overlap areas.
3. `record_cpu_conservative_crust_overlap_transition()` (`cpp/src/engine/tectonics.cpp:1166`) — increments the backend telemetry counter `cpu_conservative_crust_overlap_transition_count`.

The plan is copied into the history step at `cpp/src/engine/tectonics.cpp:635`, boundary segments are built from it at `:636`, and the candidate-fate ledger is derived at `:646-653`.

**Zero-rotation shortcut.** If every entry of `step_rotation_deg` is exactly `0.0`, the forward-overlap builder returns the identity plan verbatim (`cpp/src/engine/crust_transport.cpp:1513-1517`).

## Exact spherical forward-overlap geometry

Every geometric helper stage lives in the anonymous namespace of `cpp/src/engine/crust_transport.cpp` (it closes at `:1429`); only the two entry points `build_identity_crust_transport_plan` and `build_forward_overlap_crust_transport_plan` are visible, in `magic_geo::detail`. Planar predicates and the spherical-excess accumulation are carried in `long double`; only the exported areas are `double`.

### Stage-by-stage

| # | Stage | Source | Behaviour |
|---|---|---|---|
| 1 | Cap radii | `crust_transport.cpp:898-904`, `:1520-1526` | `cell_cap_radius(cell)` = max angular distance from the cell center to any control-volume vertex; `maximum_cap_radius` over all cells |
| 2 | Destination index | `crust_transport.cpp:779-896`, `:1528` | A 3-D k-d tree over cell centers (`SphericalPointIndex`) with an interval-bound `maximum_dot_bound` pruning test padded by `128 * eps * (1 + |terms|)` (`:867-869`); results are sorted ascending (`:794`) |
| 3 | Source rotation | `crust_transport.cpp:1537-1555` | Source center and every control-volume vertex rotated about `plates[plate_id].axis` by `step_rotation_deg[plate_id] / DEG`; `source_kinematic_distance_km = angular_distance(original, rotated) * radius_km` |
| 4 | Candidate query | `crust_transport.cpp:1556-1559` | `within_angle(rotated_center, cap_radii[source] + maximum_cap_radius + 1.0e-10)` |
| 5 | Pairwise cap rejection | `crust_transport.cpp:1562-1568` | Exact per-pair test: skip if `angular_distance > cap_radii[source] + cap_radii[destination] + 1.0e-10` |
| 6 | Gnomonic chart | `crust_transport.cpp:66-94` | `tangent_basis(destination.p)` picks reference `+Z` when `|center.z| < 0.8`, else `+X`; `project_gnomonic` throws `"crust-remap overlap candidate left the destination gnomonic hemisphere"` if `dot(center, point) <= 1.0e-10` |
| 7 | Triangle-fan clipping | `crust_transport.cpp:1572-1617` | Every source fan triangle `(rotated_center, v_i, v_{i+1})` is clipped against every destination fan triangle `(destination.p, w_j, w_{j+1})` with Sutherland–Hodgman (`intersect_convex_polygons`, `:339-354`) |
| 8 | Spherical area | `crust_transport.cpp:356-407` | Vertices are un-projected back to the sphere, and area is the Kahan-compensated sum of `2*atan2(det, 1 + three dots)` spherical-excess terms relative to the normalized vertex-sum reference; a signed area below `-5.0e-15 sr` throws `"crust-remap intersection polygon is reversed"` |
| 9 | Piece filter | `crust_transport.cpp:1612-1614` | Pieces with `area <= 1.0e-12 km2` are discarded |
| 10 | Edge filter | `crust_transport.cpp:1619-1625` | An edge is emitted only if the summed area exceeds `max(1.0e-10, source_area_km2 * 1.0e-13)` |
| 11 | Source-row closure | `crust_transport.cpp:1635-1650` | Throws `"forward spherical crust-remap source overlaps do not close"` if `|sum(edge areas) - source area| > max(1.0e-6 km2, source_area * 2.0e-10)` |
| 12 | Canonical ordering | `crust_transport.cpp:1653-1658` | Edges sorted destination-major, source-minor |

### Numeric predicates and tolerances

| Predicate / guard | Value | Source |
|---|---|---|
| Degenerate-vector rejection (`checked_normalize`) | squared norm `<= 1.0e-28` (long double) | `crust_transport.cpp:58-64` |
| Gnomonic hemisphere denominator floor | `1.0e-10` | `crust_transport.cpp:84-89` |
| Half-plane inside test tolerance | `512 * eps_binary64 * planar_scale(a,b) * (1 + |px| + |py|)` | `crust_transport.cpp:147-151` |
| Segment/line intersection degenerate denominator | `1.0e-30` | `crust_transport.cpp:167-169` |
| Duplicate-vertex merge distance² | `1.0e-28` | `crust_transport.cpp:182` |
| Degenerate arrangement line | length `<= 1.0e-16` throws `"crust-remap coverage arrangement has a degenerate line"` | `crust_transport.cpp:247-249` |
| Coincident-line dedup tolerance (same **or** opposite orientation) | `2.0e-12` on each of `a`, `b`, `c` | `crust_transport.cpp:313-324` |
| Arrangement split predicate tolerance | `128 * eps_binary64 * coordinate_scale` | `crust_transport.cpp:492-494` |
| Local arrangement complexity bound | `COVERAGE_ARRANGEMENT_LOCAL_FRAGMENT_LIMIT = 16384` | `crust_transport.cpp:50`, `:516-521` |
| Destination partition closure tolerance | `max(1.0e-7 km2, destination_area * 5.0e-10)` | `crust_transport.cpp:717` |
| Global gap/excess balance tolerance | `max(1.0e-6 km2, 4πR² * 5.0e-10)` | `crust_transport.cpp:1880-1883` |
| Inventory closure tolerance (each of three moments) | `max(1.0e-7, \|initial value\| * 5.0e-10)` | `crust_transport.cpp:1841-1879` |

### Fail-closed exceptions raised by the geometry

| Message | Trigger | Source |
|---|---|---|
| `crust-remap tangent axis is geometrically degenerate` | degenerate basis vector | `crust_transport.cpp:70-76` |
| `crust-remap overlap candidate left the destination gnomonic hemisphere` | source vertex more than ~90° from destination center | `crust_transport.cpp:86-88` |
| `crust-remap intersection polygon is reversed` | negative spherical excess beyond `-5e-15 sr` | `crust_transport.cpp:396-402` |
| `crust-remap coverage arrangement has a degenerate line` | zero-length arrangement line | `crust_transport.cpp:248` |
| `crust-remap coverage arrangement exceeded its local complexity bound` | more than 16,384 atoms in one destination | `crust_transport.cpp:518-520` |
| `crust-remap coverage sources are not canonical` | contributing source ids not strictly ascending / negative | `crust_transport.cpp:571-573` |
| `crust-remap coverage multiplicity arrangement did not close` | destination partition residual over tolerance | `crust_transport.cpp:718-722` |
| `forward spherical crust-remap source overlaps do not close` | source-row area residual over tolerance | `crust_transport.cpp:1646-1650` |
| `forward spherical crust-remap volume did not close` | transported vs. source crust volume | `crust_transport.cpp:1845-1851` |
| `forward spherical crust-remap density-weighted volume did not close` | transported vs. source density-weighted volume | `crust_transport.cpp:1856-1865` |
| `forward spherical crust-remap age-volume moment did not close` | transported vs. source age-volume moment | `crust_transport.cpp:1870-1879` |
| `forward spherical crust-remap global gap/overlap areas do not balance` | `\|global gap − global excess\|` over tolerance | `crust_transport.cpp:1884-1893` |
| `forward spherical crust-remap multiplicity histogram did not close` | histogram total ≠ 4πR², or histogram gap/excess ≠ scalars | `crust_transport.cpp:1911-1922` |

## Why the geometry stays on CPU

The declared contract pins the execution backend in three independent places:

| Key | Value | Source |
|---|---|---|
| `plate_kinematic_model.crust_transport_execution_backend` | `"cpu"` | `cpp/src/engine/process_serialization.cpp:2828` |
| `backend.crust_transport_execution_backend` | `"cpu"` | `cpp/src/opencl_compute.cpp:2067-2072` |
| `backend.crust_transport_execution_model` | `"forward_spherical_control_volume_overlap_v1"` | `cpp/src/opencl_compute.cpp:2073-2078` |
| `backend.crust_transport_accelerator_dispatch_count` | `0` (literal) | `cpp/src/opencl_compute.cpp:2079-2084` |
| `backend.crust_overlap_geometry_and_csr_authoritative_backend` | `"cpu"` | `cpp/src/opencl_compute.cpp:2091-2096` |
| `backend.crust_overlap_continuous_production_remap_authoritative_backend` | `"cpu"` | `cpp/src/opencl_compute.cpp:2097-2102` |
| `backend.crust_overlap_continuous_shadow_only` | `true` | `cpp/src/opencl_compute.cpp:2127-2132` |
| `backend.crust_overlap_continuous_shadow_authoritative` | `false` | `cpp/src/opencl_compute.cpp:2133-2138` |
| `backend.crust_overlap_continuous_shadow_result_used_for_state` | `false` | `cpp/src/opencl_compute.cpp:2139-2144` |
| `backend.crust_overlap_accelerator_geometry_parity_demonstrated` | `false` | `cpp/src/opencl_compute.cpp:2145-2149` |

When OpenCL or CUDA is active, the kernel `reduce_crust_overlap_continuous_shadow` (`cpp/src/opencl_compute.cpp:622`) launches one ordered FP64 work item per destination **over the exact CPU CSR**, reconstructs the three incoming moments and the derived thickness/density/age, is checked against finite operand/operation-count bounds by `cpp/src/crust_overlap_shadow.cpp`, records dedicated telemetry, and the result is **discarded** (`cpp/src/engine/README.md:294-303`). Its declared scope is `"raw_extensive_moments_and_derived_continuous_state_only"` (`cpp/src/opencl_compute.cpp:2109-2114`).

The engine README states the boundary explicitly: "CPU geometry, coverage, membership classes, categories, production remap, and scientific state remain authoritative. Complete parity stays false." It further notes that the host on which those notes were written "has no usable OpenCL platform or CUDA compiler/device, so only CPU/stub integration and pure reconciliation logic are verified here" (`cpp/src/engine/README.md:298-303`). Treat accelerator parity as **unresolved**, not as demonstrated-and-equal.

The Python replay enforces the same facts as hard failures: it rejects the world if `backend.crust_transport_execution_backend != "cpu"`, if `crust_transport_accelerator_dispatch_count != 0`, or if `cpu_conservative_crust_overlap_transition_count != len(plate_motion_history) - 1` (`src/magic_geo/crust_transport_validation.py:1001-1017`).

## The transport plan structure

`CrustTransportPlan` is defined at `cpp/src/engine/types/earth_system.hpp:558-612` and serialized as `plate_motion_history[].crust_overlap_ledger` by `cpp/src/engine/process_serialization.cpp:3531-3787`. Every numeric field in that ledger uses `transport_precision = max_digits10` (`process_serialization.cpp:3530`); the strictly-positive area columns additionally use general-format binary64 round-trip (`roundtrip_double_array_json`) so that sub-`1e-17 km2` slivers are not serialized as zero — the comment at `process_serialization.cpp:3555-3558` documents exactly that.

### Edge (CSR) columns — length = number of overlap edges

| Field | Type | Meaning | Serializer |
|---|---|---|---|
| `destination_offsets` | int[cell_count+1] | CSR row starts, destination-major | `process_serialization.cpp:3551` |
| `source_cell_ids` | int[] | Contributing source cell per edge; strictly ascending within a row | `:3553` |
| `overlap_area_km2` | double[] | Raw, unnormalized spherical overlap area; always `> 0` | `:3559` (round-trip) |
| `remap_residual_distance_km` | double[] | `angular_distance(rotated source center, destination center) * radius_km` | `:3561`, computed at `crust_transport.cpp:1631` |

### Per-cell columns — length = cell_count

| Field | Type | Meaning | Source |
|---|---|---|---|
| `source_kinematic_distance_km` | double | How far this cell's own center moved under its plate's rotation | `crust_transport.cpp:1544-1546` |
| `dominant_source_cell_ids` | int | Source contributing the largest incoming crust volume; falls back to the destination id when the row is empty | `crust_transport.cpp:1704-1731` |
| `contributor_count_by_cell` | int | Number of CSR edges in the row | `crust_transport.cpp:1724-1728` |
| `dominant_source_volume_fraction_by_cell` | double | `dominant_volume / total incoming volume`, `0.0` when volume is zero | `crust_transport.cpp:1732-1734` |
| `coverage_area_sum_km2_by_cell` | double | Σ of raw overlap areas in the row (may exceed the cell area) | `crust_transport.cpp:1711` |
| `covered_union_area_km2_by_cell` | double | Area covered at least once | `crust_transport.cpp:1789-1790` |
| `uncovered_gap_area_km2_by_cell` | double | Area covered zero times | `crust_transport.cpp:1791-1792` |
| `overlap_excess_area_km2_by_cell` | double | `Σ (multiplicity − 1) × atom area` | `crust_transport.cpp:1793-1794` |
| `maximum_coverage_multiplicity_by_cell` | int | Largest integer coverage count observed inside the cell | `crust_transport.cpp:1795-1796` |
| `coverage_arrangement_line_count_by_cell` | int | Raw distinct arrangement lines | `crust_transport.cpp:1797-1798` |
| `coverage_arrangement_fragment_count_by_cell` | int | Raw arrangement **atoms** before coalescing | `crust_transport.cpp:1799-1800` |
| `coverage_membership_area_class_count_by_cell` | int | Retained classes after coalescing | `crust_transport.cpp:998-999` |
| `remapped_crust_type_by_cell` | int | Categorical remap result | `crust_transport.cpp:1765-1766` |
| `remapped_lithology_by_cell` | int | Categorical remap result | `crust_transport.cpp:1767-1768` |
| `remapped_crust_age_ma_by_cell` | double | Volume-weighted mean incoming age | `crust_transport.cpp:1741-1742` |
| `remapped_crust_thickness_km_by_cell` | double | `incoming volume / destination area` | `crust_transport.cpp:1737-1738` |
| `remapped_crust_density_by_cell` | double | Volume-weighted mean incoming density | `crust_transport.cpp:1739-1740` |

### Scalars and aggregates

| Field | Meaning | Source |
|---|---|---|
| `global_coverage_area_km2_by_multiplicity` | Global area histogram indexed by integer coverage count; index 0 is the gap bin | `crust_transport.cpp:1801-1812` |
| `total_coverage_arrangement_line_count` / `..._fragment_count` | int64 sums of the per-cell raw counts | `process_serialization.cpp:3614-3629` |
| `total_coverage_membership_area_class_count` | int64 sum of retained class counts | `process_serialization.cpp:3635-3642` |
| `maximum_coverage_membership_area_class_count` | Max retained classes for any destination | `crust_transport.cpp:1000-1002` |
| `maximum_coverage_arrangement_line_count` / `..._fragment_count` | Maxima of the raw counts | `crust_transport.cpp:1817-1824` |
| `maximum_source_area_closure_error_km2`, `maximum_source_area_relative_closure_error` | Worst source-row area residual | `crust_transport.cpp:1639-1645` |
| `maximum_destination_partition_closure_error_km2` | Worst destination arrangement residual (a **three-term maximum**, see below) | `crust_transport.cpp:707-716`, `:1813-1816` |
| `global_uncovered_gap_area_km2`, `global_overlap_excess_area_km2` | Global gap and excess | `crust_transport.cpp:1825-1826` |
| `global_gap_overlap_balance_residual_km2` | Serialized as `excess − gap` | `process_serialization.cpp:3782-3787` |
| `source_inventory`, `transported_inventory`, `post_process_inventory`, `process_inventory_delta` | Four `{crust_volume_km3, density_weighted_crust_volume, crust_age_volume_moment_km3_ma}` records | `process_serialization.cpp:3788+` |
| `process_inventory_attribution` | Ten ordered rule-reason records with positive/negative/net extensive deltas | see [Erosion / tectonics pages](tectonics-and-plates.md) |

Declared units and semantics live alongside them: `crust_volume_unit = "km3"`, `crust_density_unit = "g_cm3"`, `density_weighted_crust_volume_unit = "g_cm3_km3"`, `density_weighted_crust_volume_to_mass_kg_factor = 1.0e12`, `crust_age_volume_moment_unit = "km3_ma"`, `transport_conservation_scope = "source_to_transported_pre_process"`, and `post_process_inventory_semantics = "state_snapshot_not_transport_conservation_target"` (`process_serialization.cpp:3537-3550`).

### The identity plan

`build_identity_crust_transport_plan` (`crust_transport.cpp:1431-1488`) emits exactly one edge per cell (source = destination = self), area = cell area, zero residual and kinematic distance, `dominant_source_volume_fraction = 1.0`, `maximum_coverage_multiplicity = 1`, `arrangement_fragment_count = 1`, arrangement **line** count left at `0`, one membership class of multiplicity 1 whose representative is the cell center, and a two-bin histogram `[0.0, total area]` (`:1439-1469`). The Python validator asserts every one of those identity properties at `step_index == 0` (`src/magic_geo/crust_transport_validation.py:1532-1555`, `:2208-2218`).

## The extensive-state remap

Everything moved by transport is a **moment over volume**, accumulated per destination row at `crust_transport.cpp:1682-1723`:

```
edge_volume            = overlap_area_km2 * previous_crust_thickness_km[source]
volume                += edge_volume
density_weighted_volume += edge_volume * previous_crust_density[source]
age_volume_moment      += edge_volume * previous_crust_age_ma[source]
category_pair_volumes[previous_crust_type[source]][previous_lithology[source]] += edge_volume
```

The destination state is then derived (`crust_transport.cpp:1736-1768`):

| Output | Formula | Note |
|---|---|---|
| `remapped_crust_thickness_km` | `volume / destination.area_km2` | thickness is *derived*, not averaged |
| `remapped_crust_density` | `density_weighted_volume / volume` | volume-weighted mean |
| `remapped_crust_age_ma` | `age_volume_moment / volume` | volume-weighted mean |
| `remapped_crust_type`, `remapped_lithology` | joint mode over the 9 × 7 `category_pair_volumes` table | scan order is ascending crust type then ascending lithology, and only a **strictly greater** volume replaces the incumbent (`crust_transport.cpp:1746-1764`), so the tie-break is `lowest_crust_type_then_lowest_lithology` (`process_serialization.cpp:2816-2819`) |

**Empty row fallback** (`crust_transport.cpp:1769-1777`): if no crust arrives, crust type, lithology, and density are carried over from the destination's own *previous* state, and `remapped_crust_age_ma` is set to `0.0`. Thickness stays at its initialized `0.0`.

**Dominant source tie-break** (`crust_transport.cpp:1704-1710`): the incumbent is replaced when `edge_volume > dominant_volume`, or when `edge_volume == dominant_volume` and the candidate's source id is lower.

### The three closure identities

| Identity | Enforced where | Tolerance |
|---|---|---|
| `Σ_destinations volume == Σ_sources area × thickness` | `crust_transport.cpp:1845-1851` | `max(1e-7, initial_volume * 5e-10)` |
| `Σ density-weighted volume` conserved | `crust_transport.cpp:1856-1865` | `max(1e-7, \|initial\| * 5e-10)` |
| `Σ age-volume moment` conserved | `crust_transport.cpp:1870-1879` | `max(1e-7, \|initial\| * 5e-10)` |

The declared model asserts these as `crust_volume_conserving_transport`, `density_weighted_volume_conserving_transport`, `crust_age_volume_moment_conserving_transport`, and `mass_conserving_crust_transport`, all `true`, but with `mass_conservation_scope = "transport_only_before_rule_based_tectonic_processes"` (`process_serialization.cpp:2838-2843`). Conservation is a claim about the **advection operator**, not about the whole tectonic step: the ordered rule chain that runs afterwards changes the inventory, and that change is ledgered separately as `process_inventory_delta` plus a ten-reason attribution.

### Transport / process split

Downstream, `advance_plate_motion_and_crust` records the split per cell (`cpp/src/engine/tectonics.cpp:1199-1211`):

```
crust_age_transport_change_ma_by_cell[i]        = remapped_crust_age_ma[i]        - previous_crust_age[i]
crust_thickness_transport_change_km_by_cell[i]  = remapped_crust_thickness_km[i]  - previous_crust_thickness[i]
crust_density_transport_change_by_cell[i]       = remapped_crust_density[i]       - previous_crust_density[i]
crust_transport_distance_km_by_cell[i]          = Σ(edge_volume × source_kinematic_distance) / Σ(edge_volume)   (0 when volume is 0)
```

and the `*_process_change_*` arrays carry the ordered-rule remainder, so that `final = remapped + process_change` holds cell-by-cell. The Python validator checks both halves of that split and the total (`src/magic_geo/crust_transport_validation.py:1942-1985`) and then checks the final serialized `cells[].crust_age_ma` / `crust_thickness_km` / `crust_density` against the reconstruction with a four-operand binary64 forward-error bound (`:2288-2331`, bound at `src/magic_geo/crust_process_validation.py:175-205`).

## Raw arrangement diagnostics: lines and atoms

To turn "how many sources cover this piece of the destination?" into an exact area, the destination control volume is cut into a **line arrangement** in its own gnomonic chart (`build_coverage_arrangement`, `crust_transport.cpp:432-525`):

1. Seed fragments: the destination's own triangle fan `(center, w_j, w_{j+1})`, projected into the chart (`:439-455`).
2. Collect lines: every edge of every overlap piece of every contributing source becomes a candidate `NormalizedLine (a, b, c)` with `a² + b² = 1`; edges shorter than `1e-14` (squared `1e-28`) are skipped, and a candidate is dropped when it is coincident with an existing line in either orientation within `2e-12` (`:456-475`).
3. Split: for each line, every fragment whose signed values straddle the line beyond `128 * eps * coordinate_scale` is split into its positive and negative halves; intersection points are re-projected onto the line by subtracting `residual * (a, b)` (`:476-514`, `:294-299`).
4. Bound: if the fragment count exceeds `16384`, throw (`:516-521`).

The resulting fragments are the **raw arrangement atoms**. For each atom, the vertex-mean point (`planar_fragment_representative`, `:527-543`) is tested against every source's overlap pieces with `point_in_convex_polygon` (`:409-424`, `:618-636`); the set of sources whose pieces contain it is the atom's **membership**, and `|membership|` is its integer multiplicity.

| Serialized diagnostic | Meaning | Location |
|---|---|---|
| `coverage_arrangement_line_count_by_cell[i]` | distinct arrangement lines used for destination `i` | `crust_overlap_ledger` |
| `coverage_arrangement_fragment_count_by_cell[i]` | raw atoms produced for destination `i` (always `>= 1`) | `crust_overlap_ledger` |
| `total_coverage_arrangement_line_count`, `total_coverage_arrangement_fragment_count` | int64 sums | `crust_overlap_ledger` |
| `maximum_coverage_arrangement_line_count`, `maximum_coverage_arrangement_fragment_count` | maxima | `crust_overlap_ledger` |
| `summary.maximum_crust_coverage_arrangement_line_count`, `summary.maximum_crust_coverage_arrangement_fragment_count` | maxima over the moving steps only — the accumulator is guarded by `if step_index > 0:` (`src/magic_geo/crust_transport_validation.py:2220-2235`), and the mirror is asserted at `:2339-2344` | `crust_overlap_ledger` + `summary` |
| `plate_kinematic_model.crust_transport_coverage_arrangement_fragment_limit` | `16384` | `process_serialization.cpp:2826-2827` |

**These counts describe one particular arrangement execution, not a physical result.** The independent geometry replay deliberately does *not* require them to match, because native `long double` predicates and Python `binary64` predicates can take different but area-equivalent split paths at a coincident boundary (`src/magic_geo/crust_coverage_geometry_replay.py:1042-1045`). Only the integer multiplicity and the areas are required to agree.

## The coverage membership area class ledger

Raw atoms are far too numerous to serialize. `coverage_diagnostics` (`crust_transport.cpp:545-765`) coalesces them into **membership-area classes** and serializes those as `crust_overlap_ledger.coverage_membership_area_class_ledger` (`process_serialization.cpp:3646-3730`).

### The coalescing rule

The key is a `std::map<std::vector<int>, MembershipAreaClassAccumulator>` (`crust_transport.cpp:607-608`) keyed by the atom's **sorted contributing source cell ids**. Every atom with the same membership vector — no matter where it sits inside the destination, and no matter whether the pieces touch — is merged into one class. The declared key string is `sorted_contributing_source_cell_ids` (`process_serialization.cpp:3654-3655`).

| Property | Rule | Source |
|---|---|---|
| Coalescing key | the exact sorted vector of contributing source cell ids | `crust_transport.cpp:646` |
| Stored area | Kahan-compensated sum of the merged atoms' spherical areas | `crust_transport.cpp:679-685`, `:734-736` |
| Stored source ids | the sorted contributing source cell ids | `crust_transport.cpp:629-631` |
| Stored source plate ids | each contributor's plate id **at the transport source snapshot** | `crust_transport.cpp:632-634`; semantics string `source_cell_plate_id_at_transport_source_snapshot` (`process_serialization.cpp:3661-3663`) |
| Plate-id consistency | merging an atom whose plate-id vector differs from the incumbent throws `"crust-remap coverage membership-area-class plate IDs are inconsistent"` | `crust_transport.cpp:649-656` |
| Multiplicity | `source_cell_ids.size()`; asserted equal to the contributor-CSR span | `crust_transport.cpp:641-643`, `:949-960` |
| Representative | unit vector of the **largest single atom**'s un-projected vertex mean | `crust_transport.cpp:657-678` |
| Representative tie-break | on exactly equal atomic area, the lexicographically **lowest** `(x, y, z)` wins | `crust_transport.cpp:657-672` |
| `representative_available` | `1` for every v1 class; `0` is reserved | `crust_transport.cpp:976-978`; semantics `one_for_every_v1_membership_area_class_zero_reserved_for_future_unavailable_representatives` (`process_serialization.cpp:3658-3660`) |
| Class order within a destination | multiplicity, then source-id vector, then representative x/y/z, then area | `crust_transport.cpp:741-763`; declared as `destination_id_then_multiplicity_then_source_cell_ids` (`process_serialization.cpp:3652-3653`) |

The declared representative model string is `largest_atomic_arrangement_piece_unprojected_vertex_mean_lowest_xyz_tie_v1` (`process_serialization.cpp:3656-3657`).

**Empty-coverage destination.** When a destination receives no overlap at all, one class is emitted with `multiplicity = 0`, area = the full destination area, empty source vectors, `representative = destination.p`, `representative_available = true`, and `arrangement_fragment_count = 1` (`crust_transport.cpp:578-591`).

### The nested class CSR

The class ledger is two nested CSRs. All fields are listed here in serialization order (`process_serialization.cpp:3648-3727`).

| Field | Type | Length | Meaning |
|---|---|---|---|
| `format` | str | — | `destination_membership_area_class_csr_with_class_contributor_csr_v1` |
| `model` | str | — | `coalesced_destination_source_membership_area_classes_v1` |
| `class_order` | str | — | `destination_id_then_multiplicity_then_source_cell_ids` |
| `coalescing_key` | str | — | `sorted_contributing_source_cell_ids` |
| `representative_model` | str | — | `largest_atomic_arrangement_piece_unprojected_vertex_mean_lowest_xyz_tie_v1` |
| `representative_available_semantics` | str | — | `one_for_every_v1_membership_area_class_zero_reserved_for_future_unavailable_representatives` |
| `source_plate_id_semantics` | str | — | `source_cell_plate_id_at_transport_source_snapshot` |
| `edge_area_reconstruction_tolerance_basis` | str | — | `max_1e-7_km2_or_destination_control_volume_area_km2_times_5e-10` |
| `raw_arrangement_fragment_count_location` | str | — | `sibling_coverage_arrangement_fragment_count_by_cell` |
| `area_unit` | str | — | `km2` |
| `destination_offsets` | int[] | cell_count + 1 | class-CSR row starts |
| `area_km2` | double[] | class_count | coalesced class area (round-trip serialized) |
| `multiplicity` | int[] | class_count | integer coverage count |
| `representative_unit_x` / `_y` / `_z` | double[] | class_count | unit representative direction |
| `representative_available` | int[] | class_count | `1` in v1 |
| `contributor_offsets` | int[] | class_count + 1 | contributor-CSR row starts |
| `source_cell_ids` | int[] | contributor_count | contributing source cells, ascending within a class |
| `source_plate_ids` | int[] | contributor_count | contributor plate ids at the source snapshot |
| `source_membership_resolved` | bool | — | **`true`** |
| `connected_fragment_topology_resolved` | bool | — | **`false`** |
| `physical_fate_resolved` | bool | — | **`false`** |
| `slab_selection_resolved` | bool | — | **`false`** |
| `local_kinematics_resolved` | bool | — | **`false`** |

The same five flags are mirrored on `plate_kinematic_model` as `crust_transport_coverage_membership_area_class_source_membership_resolved` (true) and `..._connected_fragment_topology_resolved` / `..._physical_fate_resolved` / `..._slab_selection_resolved` / `..._local_kinematics_resolved` (all false) at `process_serialization.cpp:2801-2815`. The Python validator rejects any world in which those booleans are not exactly those values (`src/magic_geo/crust_transport_validation.py:240-246`, `:884-903`).

### What the class CSR reconstructs

The native builder re-derives, from the classes alone, everything the aggregate columns claim — `validate_coverage_membership_area_class_ledger` (`crust_transport.cpp:1010-1427`):

| Reconstruction | Rule | Tolerance | Source |
|---|---|---|---|
| Every overlap-CSR edge area | for each class, add its area to each of its contributors' edge slots; the total must equal `overlap_area_km2[edge]` | `max(1e-7, destination_area * 5e-10)` — deliberately the destination-level bound, *not* an edge-relative bound (comment at `:1344-1349`) | `crust_transport.cpp:1268-1273`, `:1337-1379` |
| Destination partition | `Σ class areas == destination.area_km2` | `max(1e-7, destination_area * 5e-10)` | `crust_transport.cpp:1323-1336` |
| Gap | classes with `multiplicity == 0` | — | `crust_transport.cpp:699-701` |
| Union | classes with `multiplicity >= 1` | — | `crust_transport.cpp:702` |
| Excess | `Σ (multiplicity − 1) × class area` | — | `crust_transport.cpp:703-704` |
| Multiplicity histogram | per-multiplicity class-area sums vs. `global_coverage_area_km2_by_multiplicity` | `max(1e-6, max(\|a\|,\|b\|) * 5e-10)` | `crust_transport.cpp:1382-1406` |
| Per-cell and global max multiplicity | must equal `maximum_coverage_multiplicity_by_cell` and its max | exact | `crust_transport.cpp:1330-1332`, `:1407-1418` |
| Max class count | must equal `maximum_coverage_membership_area_class_count` | exact | `crust_transport.cpp:1419-1426` |

Structural invariants enforced in the same pass: class-CSR offsets monotone and terminated correctly; every destination has **at least one** class (`class_end == class_begin` is rejected, `:1136`); the class count never exceeds the raw fragment count (`:1137-1140`); each row's `source_cell_ids` are sorted and duplicate-free (`:1154-1162`); adjacent classes may never share an identical membership vector, i.e. coalescing actually happened (`:1212-1237`); every contributor's `source_plate_id` equals `source_plate_ids[source_cell_id]` (`:1256-1267`); each class area is finite and strictly positive (`:1191`); every available representative has unit norm within `2e-12` (`:1292-1304`).

The destination partition closure scalar deserves a specific note. `partition_closure_error_km2` is the **maximum of three** residuals (`crust_transport.cpp:707-716`): `|Σ atoms − destination area|`, `|union + gap − destination area|`, and `|union + excess − coverage sum|`. Only the last two can be reconstructed from serialized aggregates; the first uses an unexported ordered sum of raw atoms. The Python validator therefore brackets it rather than equating it — a lower bound from the two replayable identities and an upper bound derived from the exported class sums and raw fragment counts (`src/magic_geo/crust_transport_validation.py:100-163`, `:1827-1839`).

## What a membership class is not

This is stated in the source, in the schema, and in the engine README, and it must not be softened.

> "Disconnected arrangement atoms with the same source membership are intentionally coalesced; no connected topology or physical fate is implied." — `cpp/src/engine/types/earth_system.hpp:577-580`

> "Coalescing means the class does not preserve connected-fragment topology. The membership-class metadata must continue to keep topology, physical fate, local pairwise kinematics, slab selection, and subduction polarity unresolved." — `cpp/src/engine/README.md:281-285`

| Claim | Status | Where the negative is recorded |
|---|---|---|
| The class's contributing-source set is exact | **resolved** | `source_membership_resolved: true` |
| The class is one connected region | **not resolved** — one class may hold several disconnected pieces | `connected_fragment_topology_resolved: false` |
| The class records what physically happened to that crust | **not resolved** | `physical_fate_resolved: false` |
| The class identifies which contributor subducts | **not resolved** | `slab_selection_resolved: false` |
| The class carries local relative plate kinematics | **not resolved** | `local_kinematics_resolved: false` |

A class is an **area bookkeeping object**: "the total destination area covered by exactly this set of source cells". Its representative point is a single witness location on the largest of its pieces, chosen for determinism — it is not a centroid of the class, and it is explicitly never used to assign fate (`representative_usage = "membership_area_class_representatives_are_never_used_for_pair_assignment_or_incidence"`, `process_serialization.cpp:3207-3208`).

## The candidate fate crosswalk

`build_crust_overlap_candidate_fate_ledger` (`cpp/src/engine/crust_overlap_candidate_fate.cpp:376-809`) is a deterministic, read-only crosswalk from multiplicity ≥ 2 membership classes to same-step plate-boundary evidence. It reads only the transport plan and the boundary-segment array; it allocates no *material*, mutates no simulation state, and touches no reservoir (`candidate_allocation_authoritative`, `state_mutation_performed`, `crust_reservoir_mutation_performed` are all serialized `false`).

### Preconditions and caps

| Guard | Value | Source |
|---|---|---|
| `step_id >= 0`, `cell_count > 0` | — | `crust_overlap_candidate_fate.cpp:383-390` |
| `2 <= plate_count <= 256` and `plate_count < cell_count` | `PERSISTENT_PAIR_ID_BASE = 256` | `:6`, `:383-390` |
| Boundary segments per cell | `MAX_BOUNDARY_SEGMENTS_PER_CELL = 8` | `:8`, `:392-399` |
| Membership classes per cell | `MAX_MEMBERSHIP_AREA_CLASSES_PER_CELL = 16384` | `:7`, `:401-439` |
| Persistent pair id | `256 * plate_low_id + plate_high_id` | `:62-73` |
| Step linkage | source = `step_id == 0 ? 0 : step_id − 1`; boundary = `step_id` | `:479-480` |

These are declared as fail-closed resource guards, not physical limits: `operational_cap_semantics = "fail_closed_nonphysical_resource_and_integer_conversion_guards"` (`process_serialization.cpp:3219-3220`).

### Step 1 — boundary plate-pair consensus

All same-step boundary segments are grouped by their **sorted unordered plate-id pair** (`crust_overlap_candidate_fate.cpp:441-476`). Each group accumulates two independent consensuses.

**Physical consensus** (`consume_physical_evidence`, `:160-223`) — a segment with `convergence_active == false` sets `all_active = false` (and its whole inactive tuple must be exactly `not_applicable_no_active_convergence` / `none` / `none` / `none` / confidence `0.0`, else throw). An active segment must be either the exact unknown tuple (`unknown_unresolved`, `none`, `unknown`, `unknown`, `0.0`) or the exact resolved tuple (`resolved`, source in {`supplied_constraint`, `physical_solver`}, opposite left/right sides, confidence in `(0, 1]`).

| `physical_consensus_status` | Condition | Source |
|---|---|---|
| `not_all_segments_have_active_convergence` | any segment inactive | `:301-305` |
| `all_active_mixed_resolved_and_unknown` | both unknown and resolved segments present | `:307-311` |
| `all_active_all_physical_polarities_unknown` | all active, all unknown | `:312-313` |
| `all_active_resolved_polarities_conflict` | resolved segments disagree on roles | `:314-315` |
| `all_active_resolved_polarity_uniform` | all active, all resolved, roles agree → emits `physical_subducting_plate_id` / `physical_overriding_plate_id` | `:316-321` |

**Heuristic consensus** (`consume_heuristic_evidence`, `:225-298`) uses the boundary ledger's oceanic-side candidate status.

| `heuristic_consensus_status` | Condition | Source |
|---|---|---|
| `not_all_segments_have_active_convergence` | inherited from `all_active` | `:301-305` |
| `all_active_one_or_more_unique_oceanic_candidates_unavailable` | any segment is `unresolved_missing_opening_crust_state`, `ambiguous_both_oceanic`, or `unresolved_no_oceanic_side` | `:277-293`, `:328-329` |
| `all_active_unique_oceanic_candidates_conflict` | `left_oceanic_only` / `right_oceanic_only` segments disagree | `:330-331` |
| `all_active_unique_oceanic_candidate_uniform` | all agree → emits `heuristic_subducting_plate_id` / `heuristic_overriding_plate_id` | `:332-337` |

Every group also records the set of endpoint cell ids of its segments (`:472-473`).

### Step 2 — per-class assignment

Every membership class with `multiplicity >= 2` produces exactly one `overlap_class_candidates[]` record, in ascending class id (`:536-698`). Classes with `multiplicity < 2` are skipped entirely (`:591-593`).

| `assignment_status` | Condition | Emits roles? | Source |
|---|---|---|---|
| `unknown_nonbinary_membership` | `multiplicity != 2` | no | `:610-611` |
| `unknown_non_distinct_source_plate_pair` | the two contributors share a plate id | no | `:621-622` |
| `unknown_no_same_step_boundary_pair` | no same-step boundary group exists for that plate pair | no | `:632-633` |
| `unknown_no_same_step_endpoint_incidence` | the **destination cell id** is not an endpoint of any segment in the pair | no (but `boundary_pair_evidence_id` is set) | `:637-641` |
| `unknown_no_uniform_pair_polarity_evidence` | incident, but neither the uniform-physical nor the all-unknown-plus-uniform-heuristic case holds | no | `:682-685` |
| `uniform_oceanic_side_heuristic_candidate` | physical status is `all_active_all_physical_polarities_unknown` **and** heuristic status is `all_active_unique_oceanic_candidate_uniform` | yes | `:661-681` |
| `uniform_resolved_physical_polarity_backed_candidate` | physical status is `all_active_resolved_polarity_uniform` | yes | `:642-660` |

When roles are emitted, `candidate_subducting_contributor_id` and `candidate_overriding_contributor_id` are **global indices into the membership contributor CSR**, resolved by `contributor_for_plate` (`:345-372`), which throws if the plate role is absent or non-unique within the class. The declared semantics string is `global_index_into_coverage_membership_area_class_ledger_contributor_csr_arrays` (`process_serialization.cpp:3209-3210`).

### Step 3 — the diagnostic area partition

Each candidate contributes `excess = (multiplicity − 1) × class area` (`:598-608`) to exactly one of three totals, which are then serialized:

| Ledger field | Meaning |
|---|---|
| `physical_polarity_backed_candidate_excess_area_km2` | Σ excess with status `uniform_resolved_physical_polarity_backed_candidate` |
| `oceanic_heuristic_candidate_excess_area_km2` | Σ excess with status `uniform_oceanic_side_heuristic_candidate` |
| `unresolved_candidate_excess_area_km2` | Σ excess for every `unknown_*` status |
| `accounted_overlap_excess_area_km2` | the sum of the three |
| `candidate_partition_residual_km2` | `accounted − crust_overlap_ledger.global_overlap_excess_area_km2` |

Closure is enforced with explicit operation-count gamma bounds rather than a blanket tolerance (`binary64_operation_roundoff_bound`, `:96-120`):

| Check | Bound | Source |
|---|---|---|
| Per-destination class-excess vs. `overlap_excess_area_km2_by_cell[i]` | `gamma(fragment_count × 8 + row_class_count × 8 + 16)` over the two operands | `:732-745` |
| Global row replay | **exact binary64 equality**: sequentially summed rows must equal `global_overlap_excess_area_km2` bit-for-bit | `:751-758` |
| Category partition vs. all-class excess, and partition residual | `gamma(class_count × 16 + cell_count × 16 + 64)` over a scaled operand sum, plus the accumulated validated row discrepancy | `:760-796` |

### What the crosswalk explicitly does *not* do

Every one of these is a serialized `false` in `crust_overlap_candidate_fate_model` (`cpp/src/engine/process_serialization.cpp:3227-3254`) and is re-asserted by the validator's `MODEL_BOOLEAN_VALUES` table (`src/magic_geo/crust_overlap_candidate_fate_validation.py:144-166`).

| Model flag | Value |
|---|---|
| `deterministic_crosswalk_authoritative` | `true` — but scoped to `serialized_pair_consensus_and_membership_class_diagnostic_mapping_only` |
| `pair_wide_consensus_only` | `true` |
| `destination_endpoint_incidence_resolved` | `true` |
| `upstream_segment_physical_source_and_confidence_required_for_interpretation` | `true` |
| `candidate_allocation_authoritative` | `false` |
| `pair_evidence_standalone_physical_provenance_complete` | `false` |
| `physical_polarity_authoritative` | `false` |
| `physical_polarity_resolved` | `false` |
| `physical_material_fate_authoritative` | `false` |
| `physical_material_fate_resolved` | `false` |
| `slab_selection_authoritative` | `false` |
| `slab_selection_resolved` | `false` |
| `slab_transfer_authoritative` | `false` |
| `slab_transfer_resolved` | `false` |
| `state_mutation_performed` | `false` |
| `crust_material_shadow_mutation_performed` | `false` |
| `crust_reservoir_mutation_performed` | `false` |
| `swept_area_calculated` | `false` |
| `local_segment_link_resolved` | `false` |
| `connected_atom_topology_resolved` | `false` |
| `local_fragment_topology_resolved` | `false` |

Two model strings pin the interpretation precisely:

- `pair_endpoint_incidence_semantics = "destination_cell_id_is_an_endpoint_of_at_least_one_segment_in_the_pair_not_a_local_atom_or_fragment_to_segment_link"` (`process_serialization.cpp:3205-3206`) — incidence is **coarse, pair-wide** evidence.
- `candidate_area_semantics = "diagnostic_partition_of_overlap_excess_not_allocated_material_fate_or_transfer"` (`process_serialization.cpp:3211-3212`).
- `model_limitation = "diagnostic_candidate_crosswalk_only_without_connected_fragment_localization_physical_fate_slab_geometry_swept_area_or_state_transfer"` (`process_serialization.cpp:3253-3254`).
- `physical_pair_evidence_provenance_limitation` records that pair evidence is **not** standalone: per-segment physical polarity source and confidence are not propagated, and the candidate cannot promote or replace upstream evidence (`process_serialization.cpp:3213-3214`).

**Observed outcome in the current reference.** The deep audit reports that for the 4,096-cell, seven-snapshot reference the crosswalk contains 252 persistent plate-pair evidence rows and 6,685 multiplicity-two-or-greater class rows, and that "the conservative pair-wide gate assigns zero area to both physical-polarity-backed and oceanic-heuristic candidates in this reference: all `56,423,783.10296976 km2` of excess remains explicit unknown. This is a useful fail-closed result, not a missing-data pass." (`docs/geo_generation_maturation_deep_audit.md:116-121`).

## Reduction ratio, payload and RSS figures

These are the repository's own numbers. They are reported here verbatim, including the fact that two documents disagree and that the size/RSS measurement is explicitly stale.

| Figure | Value | Source |
|---|---|---|
| Reference fixture | geometry-stable 4,096-cell, seven-step | `cpp/src/engine/README.md:285-287` |
| Raw arrangement atoms | `3,503,886` | `cpp/src/engine/README.md:287`, `README.md:347`, `docs/configuration_reference.md:395` |
| Retained membership-area classes | `111,022` | same three sources |
| Coalescing ratio | about `31.6x` | same three sources |
| Maximum classes per destination | 14 | same three sources |
| **Alternate figures in the deep audit** | `3,483,059` raw atoms → `109,777` classes, about `31.7x`, max 14 per destination | `docs/geo_generation_maturation_deep_audit.md:222`, `:406` |
| Uncompressed JSON payload | `178,764,102` bytes | `cpp/src/engine/README.md:290`, `docs/geo_generation_maturation_deep_audit.md:123` |
| Maximum RSS (direct native process) | `371,176 KB` | `cpp/src/engine/README.md:291`, `docs/geo_generation_maturation_deep_audit.md:124` |
| Wall time at that checkpoint | `10.50 s` | `docs/geo_generation_maturation_deep_audit.md:124` |

**Caveats, stated by the repository itself:**

- The payload and RSS numbers belong **only** to "the historical pre-initial-age/expanded-round-trip checkpoint" — measured with the exact segment, candidate-crosswalk, sediment, and thermal-target replay witnesses in place (`cpp/src/engine/README.md:288-291`).
- "Current payload size/RSS has not been remeasured." (`cpp/src/engine/README.md:291-292`; repeated at `README.md:347`, `docs/configuration_reference.md:400`, `docs/geo_generation_maturation_deep_audit.md:124-125`, `:406`).
- The deep audit also records historical auditability-cost deltas at that same checkpoint (a 25.5% JSON / 6.6% peak-RSS increase relative to a 142,396,448-byte/348,200-KB measurement, and 3.239% JSON / 2.57% peak RSS relative to a 173,155,844-byte/361,876-KB reference) and labels them "historical auditability-cost deltas, not current payload measurements" (`docs/geo_generation_maturation_deep_audit.md:127-134`).
- The two atom/class counts above differ between documents. This page does not resolve which is current; treat the ratio (~31.6–31.7×) and the "at most 14 classes per destination" bound as the stable claims and both absolute counts as fixture-checkpoint-specific.

## Replay validators

Four independent Python validators cover this subsystem, plus the native self-checks already listed.

| Validator | Module | Wired in as | What it replays |
|---|---|---|---|
| Conservative overlap replay | `src/magic_geo/crust_transport_validation.py:823` (`validate_crust_overlap_transport`) | `tectonics.conservative_crust_overlap_replay` (`src/magic_geo/geo_validation_physics.py:2578-2598`) | destination CSR shape, source-row closure, coverage multiplicity, transported extensive moments, transport/process split, summary mirrors |
| Membership-class sub-replay | `src/magic_geo/crust_transport_validation.py:269` (`_validate_coverage_membership_area_classes`) | called from the above | class CSR shape, ordering, plate linkage, edge/partition/aggregate/histogram reconstruction |
| Independent geometry replay | `src/magic_geo/crust_coverage_geometry_replay.py:713` / `:959` | `tests/test_crust_coverage_geometry_replay.py` (fixture-scale; **not** part of `validate-geo`) | rediscovers pairs and areas from scratch without reading the CSR |
| Candidate-fate crosswalk replay | `src/magic_geo/crust_overlap_candidate_fate_validation.py:571` | `tectonics.overlap_candidate_fate_crosswalk_replay` (`src/magic_geo/geo_validation_physics.py:2645-2684`) | every pair consensus and every multiplicity ≥ 2 class assignment, plus the closed excess partition |

### `validate_crust_overlap_transport`

Declared model constants it demands verbatim (`src/magic_geo/crust_transport_validation.py:13-79`, checked at `:848-967`):

| Constant | Value |
|---|---|
| `CRUST_OVERLAP_FORMAT` | `destination_csr_spherical_forward_overlap_v1` |
| `CRUST_COVERAGE_MODEL` | `destination_local_gnomonic_line_arrangement_multiplicity_v1` |
| `CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_MODEL` | `coalesced_destination_source_membership_area_classes_v1` |
| `CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_LEDGER_FORMAT` | `destination_membership_area_class_csr_with_class_contributor_csr_v1` |
| `CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_ORDER` | `destination_id_then_multiplicity_then_source_cell_ids` |
| `CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_COALESCING_KEY` | `sorted_contributing_source_cell_ids` |
| `CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_REPRESENTATIVE_MODEL` | `largest_atomic_arrangement_piece_unprojected_vertex_mean_lowest_xyz_tie_v1` |
| `CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_SOURCE_PLATE_SEMANTICS` | `source_cell_plate_id_at_transport_source_snapshot` |
| `CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_EDGE_TOLERANCE_BASIS` | `max_1e-7_km2_or_destination_control_volume_area_km2_times_5e-10` |
| `CRUST_EXTENSIVE_FIELDS` | `crust_volume_km3`, `density_weighted_crust_volume`, `crust_age_volume_moment_km3_ma` |

Independent reconstructions it performs, per step:

| Reconstruction | Acceptance | Source |
|---|---|---|
| Source kinematic distance from canonical plate axes and `step_rotation_deg` | `rel_tol=2e-10`, `abs_tol=1e-7` | `:1557-1585` |
| Every edge's `remap_residual_distance_km` from the rotated source center | `rel_tol=2e-10`, `abs_tol=1e-7` | `:1621-1636` |
| Per-source area sum → relative closure | fails above `2.0e-10` | `:1733-1746`, `:1801` |
| Three-moment inventory vs. `source_inventory` / `transported_inventory` | relative error fails above `5.0e-10` | `:1754-1774`, `:1802` |
| Destination identity `union + gap == area` and `union + excess == coverage sum` | fails above `max(0.01, max(areas) * 1e-9)` | `:1679-1719`, `:1803-1804` |
| Remapped age/thickness/density/type/lithology/dominant source/dominant fraction | `_close` (2e-9 relative) / exact for integers | `:1840-1867` |
| Global gap == global excess | fails above `max(0.01, Σareas * 5e-10)` | `:2204` |
| Histogram identities (total area, gap bin, union, coverage, excess, max multiplicity) | `_close` / exact | `:2154-2205` |
| Step-0 identity ledger and identity class ledger | exact | `:1532-1555`, `:2208-2218` |
| 20 summary mirrors (`total_crust_overlap_sparse_edge_count` … `maximum_tectonic_process_attribution_relative_closure_residual`) | exact for the 7 integers; `rel_tol=2e-9, abs_tol=1e-8` for the other 13 | `:2333-2425` |
| Final `cells[].crust_age_ma` / `crust_thickness_km` / `crust_density` vs. history | four-operand binary64 alias bound | `:2288-2331` |

The check's `expected` map is deliberately minimal and honest about scope (`src/magic_geo/geo_validation_physics.py:2590-2596`): `source_area_rows_close`, `crust_volume_conserved_during_transport`, `density_weighted_volume_conserved_during_transport`, `age_volume_moment_conserved_during_transport`, `gap_equals_overlap_excess_globally` — all `True`. Nothing physical is claimed.

### `crust_coverage_geometry_replay`

A second, deliberately independent implementation. Its module docstring states the design: it "does not read the serialized overlap CSR while it discovers source/destination pairs or computes overlap polygons"; pair discovery is a brute-force `O(N²)` cap search (`src/magic_geo/crust_coverage_geometry_replay.py:1-17`).

| Constant | Value | Source |
|---|---|---|
| `ARRANGEMENT_FRAGMENT_LIMIT` | `16_384` | `:32` |
| `DEFAULT_MAX_CELL_COUNT` | `1_024` | `:33` |
| `_CAP_ANGLE_PADDING_RAD` | `1.0e-10` | `:36` |
| `_PIECE_AREA_MIN_KM2` | `1.0e-12` | `:37` |
| `_EDGE_AREA_ABSOLUTE_MIN_KM2` / `_EDGE_AREA_RELATIVE_MIN` | `1.0e-10` / `1.0e-13` | `:38-39` |
| `_GNOMONIC_DENOMINATOR_MIN` | `1.0e-10` | `:40` |
| `_COINCIDENT_LINE_TOLERANCE` | `2.0e-12` | `:42` |
| `_GEOMETRY_FORWARD_ERROR_OPERATION_BUDGET` | `256` | `:51` |

`compare_crust_coverage_geometry` (`:959`) compares against one serialized ledger with a `gamma_n` forward-error bound scaled by the **whole sphere area**, where `n = 256 + cell_count + max fragment count` (`:542-575`):

| Compared exactly | Compared within the area bound | Reported but not required to match |
|---|---|---|
| `destination_offsets`, `source_cell_ids` (`:977-980`) | `overlap_area_km2`, `coverage_area_sum_km2_by_cell`, `covered_union_area_km2_by_cell`, `uncovered_gap_area_km2_by_cell`, `overlap_excess_area_km2_by_cell`, `global_coverage_area_km2_by_multiplicity` (`:981-1001`) | `coverage_arrangement_line_count_by_cell`, `coverage_arrangement_fragment_count_by_cell` — mismatch counts are metrics only (`:1042-1080`) |
| `maximum_coverage_multiplicity_by_cell` (`:1046-1050`) | per-contributor-set membership areas decoded from the native class CSR (`:1003-1040`) | |
| | five scalar closure witnesses compared directly, so a stale telemetry scalar fails on its own (`:1086-1108`) | |

The identity (zero-rotation) step takes an explicit shortcut labelled `identity_shortcut_matching_native_zero_rotation_semantics` (`:741-772`), and a single-source destination takes a closed-form shortcut with `arrangement_line_count = 0` (`:404-424`) — which is precisely why raw line/fragment counts are excluded from the equality set.

The reported fixture results, from the deep audit (`docs/geo_generation_maturation_deep_audit.md:222`): "Fibonacci 128 and geodesic 162 match native edge pairs and multiplicity exactly, with at most `2.21e-6 km2` native-area difference and `6.39e-7 km2` destination closure error." The same passage records the standing gap: "The replay is explicitly capped at 1,024 cells and is not yet a 4,096-cell independent geometry certificate."

### `validate_crust_overlap_candidate_fate`

Runs **both** upstream root replays first and fails if either does not pass (`src/magic_geo/crust_overlap_candidate_fate_validation.py:606-619`): `validate_plate_boundary_edges` and `validate_crust_overlap_transport`. It then re-derives every pair record and every class candidate from the boundary segments and the membership CSR — it never accepts the serialized pair or area summaries as operands (docstring at `:574-580`). Records are compared field-by-field with exact type and value equality (`_compare_exact_record`, `:426-450`). A preflight pass enforces the resource caps before any work (`:453-525`).

## Worked example: reading one destination row

Suppose destination cell `d = 512` has `area_km2 = 12,500.0` and the ledger contains:

```
crust_overlap_ledger.destination_offsets[512]   = 4000
crust_overlap_ledger.destination_offsets[513]   = 4003
crust_overlap_ledger.source_cell_ids[4000:4003] = [488, 512, 517]
crust_overlap_ledger.overlap_area_km2[4000:4003] = [4200.0, 7000.0, 2100.0]
crust_overlap_ledger.coverage_area_sum_km2_by_cell[512]      = 13300.0
crust_overlap_ledger.covered_union_area_km2_by_cell[512]     = 12300.0
crust_overlap_ledger.uncovered_gap_area_km2_by_cell[512]     =   200.0
crust_overlap_ledger.overlap_excess_area_km2_by_cell[512]    =  1000.0
crust_overlap_ledger.maximum_coverage_multiplicity_by_cell[512] = 2
```

and the class CSR for that destination holds six classes (ordered by multiplicity, then by source-id vector, as the declared `class_order` requires):

| class | `multiplicity` | `source_cell_ids` | `area_km2` |
|---|---|---|---|
| 0 | 0 | `[]` | 200.0 |
| 1 | 1 | `[488]` | 3400.0 |
| 2 | 1 | `[512]` | 6100.0 |
| 3 | 1 | `[517]` | 1800.0 |
| 4 | 2 | `[488, 512]` | 800.0 |
| 5 | 2 | `[512, 517]` | 200.0 |

The identities the ledger asserts, all reconstructible from the classes alone:

```
destination partition : 200 + 3400 + 6100 + 1800 + 800 + 200            = 12500.0  == area_km2
gap                   : classes with multiplicity 0                     =   200.0
union                 : 3400 + 6100 + 1800 + 800 + 200                  = 12300.0
excess                : (2-1)*800 + (2-1)*200                           =  1000.0
coverage sum          : Σ multiplicity * area = 3400+6100+1800+2*800+2*200 = 13300.0
edge 488              : 3400 (class 1) + 800 (class 4)                  =  4200.0  == overlap_area_km2[4000]
edge 512              : 6100 (class 2) + 800 (class 4) + 200 (class 5)  =  7000.0  == overlap_area_km2[4001]
edge 517              : 1800 (class 3) + 200 (class 5)                  =  2100.0  == overlap_area_km2[4002]
union + gap           : 12300 + 200                                     = 12500.0  == area_km2
union + excess        : 12300 + 1000                                    = 13300.0  == coverage sum
```

Class 4 (`[488, 512]`, 800 km²) is a *class*, not a region: those 800 km² may be split across several disconnected slivers of the arrangement. Its representative unit vector points at the largest single such sliver, chosen with the lowest-XYZ tie-break — nothing more.

The candidate-fate ledger would then emit two `overlap_class_candidates` records (classes 4 and 5, the only ones with `multiplicity >= 2`), each contributing `(2 − 1) × area` to one of the three excess buckets: `800.0` and `200.0`, summing to the row's `overlap_excess_area_km2_by_cell[512] = 1000.0`.

The extensive remap for the same row, given the previous-state arrays:

```
volume        = 4200*T[488] + 7000*T[512] + 2100*T[517]
thickness_out = volume / 12500.0
density_out   = (4200*T[488]*D[488] + 7000*T[512]*D[512] + 2100*T[517]*D[517]) / volume
age_out       = (4200*T[488]*A[488] + 7000*T[512]*A[512] + 2100*T[517]*A[517]) / volume
```

Note the crucial asymmetry: because the row's coverage sum (13,300) exceeds the cell area (12,500), the destination receives *more* crust volume than one cell-area worth. That is compression, and it shows up as an increase in `remapped_crust_thickness_km`, not as a discarded remainder.

## Running the validators

The transport and candidate-fate replays run inside the geo validation report:

```bash
magic-geo generate --config configs/earthlike_seed.yaml --output world.json
magic-geo validate-geo --world world.json --profile earthlike --output geo_report.json
```

The relevant check ids in the report are `tectonics.conservative_crust_overlap_replay` and `tectonics.overlap_candidate_fate_crosswalk_replay` (`src/magic_geo/geo_validation_physics.py:2582`, `:2649`). `validate-geo` accepts `--profile generic|earthlike`, `--output`, and `--fail-on-warnings/--allow-warnings` (`src/magic_geo/cli/commands/validate_geo.py:23-88`); only `status == "failed"` checks with `severity == "error"` are fatal by default.

The transport replay is also invoked from the full `validate` command (`src/magic_geo/cli/commands/validate.py:6037-6039`).

Direct Python use:

```python
from magic_geo.crust_transport_validation import validate_crust_overlap_transport
from magic_geo.crust_overlap_candidate_fate_validation import (
    validate_crust_overlap_candidate_fate,
)
from magic_geo.io import read_world

world = read_world("world.json")

transport = validate_crust_overlap_transport(world)
print(transport["passed"], transport["failures"])
print(transport["metrics"]["maximum_source_relative_closure_error"])
print(transport["metrics"]["coverage_membership_area_class_count"])

fate = validate_crust_overlap_candidate_fate(world)
print(fate["passed"], fate["metrics"]["assignment_status_counts"])
```

The independent geometry replay is fixture-scale only and is bounded to 1,024 cells unless the cap is raised explicitly:

```python
from magic_geo.crust_coverage_geometry_replay import compare_crust_coverage_geometry

# step_index 0 is the identity checkpoint; use a moving step.
comparison = compare_crust_coverage_geometry(world, 1)
print(comparison["passed"])
print(comparison["metrics"]["maximum_native_area_difference_km2"])
print(comparison["metrics"]["arrangement_fragment_count_mismatch_count"])  # informational only
```

Native-side unit coverage is registered as the CTest targets `magic_geo_crust_overlap_candidate_fate` (`cpp/tests/crust_overlap_candidate_fate_test.cpp`) and `magic_geo_crust_overlap_shadow` (`cpp/tests/crust_overlap_shadow_test.cpp`).

## Limitations and unresolved claims

- **First-order overlap is diffusive.** The root README states this directly among the remaining limits of the transport subsystem (`README.md:347`). Each step re-averages incoming moments over the destination control volume; repeated steps smear gradients. No anti-diffusive or higher-order reconstruction is implemented.
- **Conservation is scoped to advection only.** `mass_conservation_scope = "transport_only_before_rule_based_tectonic_processes"` (`process_serialization.cpp:2842-2843`). The ordered rule chain that follows changes the inventory; that change is ledgered, not conserved.
- **A membership class is not a connected region and not a fate record.** `connected_fragment_topology_resolved`, `physical_fate_resolved`, `slab_selection_resolved`, `local_kinematics_resolved` are all serialized `false` (`process_serialization.cpp:3720-3727`). One class may hold several disconnected pieces.
- **Subduction polarity is unresolved.** In the current reference the crosswalk assigns zero area to both the physical-polarity-backed and the oceanic-heuristic buckets; the entire `56,423,783.10296976 km2` of overlap excess is classified as explicit unknown, which the audit calls "a useful fail-closed result, not a missing-data pass" (`docs/geo_generation_maturation_deep_audit.md:118-121`).
- **The candidate crosswalk cannot localize.** Pair endpoint incidence is coarse pair-wide evidence, not an atom- or fragment-to-segment link; no swept area is calculated; no state, material shadow, or reservoir is mutated (`process_serialization.cpp:3205-3206`, `:3246-3252`).
- **Reason records are ordered rule-state changes, not material provenance.** `tectonic_process_source_sink_attribution_resolved` and `tectonic_process_material_provenance_resolved` are `false`; the attribution is explicitly `order_dependent` (`src/magic_geo/crust_transport_validation.py:953-958`).
- **The accelerator shadow provides no device-run evidence on the documented host.** `crust_overlap_accelerator_geometry_parity_demonstrated` is `false` (`cpp/src/opencl_compute.cpp:2145-2149`), and the engine README records that the host "has no usable OpenCL platform or CUDA compiler/device, so only CPU/stub integration and pure reconciliation logic are verified here" (`cpp/src/engine/README.md:300-303`). Geometry, coverage, membership classes, categories, production state, scientific state, and complete accelerator parity remain outside the shadow and CPU-authoritative.
- **The 16,384-atom local cap lacks an exhaustive worst-case proof.** The README lists this among the remaining limits (`README.md:347`); the cap is a fail-closed numerical memory-safety limit, not a physical bound.
- **The independent geometry replay does not certify the production mesh.** It is capped at 1,024 cells (`crust_coverage_geometry_replay.py:33`, docstring `:10-16`), and "Scaling that independent pair discovery to the 4,096-cell reference remains a validation-evidence blocker" (`README.md:347`, `docs/geo_generation_maturation_deep_audit.md:222`).
- **Raw arrangement line and fragment counts are execution telemetry, not invariants.** Native `long double` and Python `binary64` predicates can take different, area-equivalent split paths, so the cross-language comparison intentionally excludes them (`crust_coverage_geometry_replay.py:1042-1045`).
- **The maximum destination partition closure scalar cannot be reproduced exactly from the serialized document.** Its third term uses an unexported ordered sum of raw atoms, so the replay brackets it between a lower and an upper bound rather than asserting equality (`crust_transport_validation.py:100-163`, `:1827-1839`).
- **The moving-domain diagnostic does not demonstrate convergence, and physical-time calibration is unresolved.** Stated in the root README's summary of remaining limits (`README.md:347`). Every `plate_motion_history` record emits its nominal interval through `add_nominal_time_fields` (`process_serialization.cpp:3482-3489`), which always writes `nominal_time_calibrated: false` and `physical_time_resolved: false` (`process_serialization.cpp:158-159`). No step duration on this page is a calibrated physical time.
- **Payload size and RSS figures are stale.** The `178,764,102`-byte / `371,176 KB` numbers belong to a historical checkpoint; "Current payload size/RSS has not been remeasured" (`cpp/src/engine/README.md:288-292`). The atom/class counts also differ between `cpp/src/engine/README.md:287` (`3,503,886` → `111,022`) and `docs/geo_generation_maturation_deep_audit.md:222` (`3,483,059` → `109,777`).

## See also

- [Tectonics and Plates](tectonics-and-plates.md) — plate generation, Euler kinematics, the ordered crust-rule chain and its ten reason records
- [Plate Boundary Segment Ledger](plate-boundary-ledger.md) — the exact directed segment geometry and polarity-candidate evidence the fate crosswalk consumes
- [Crust Material Shadow and Dry-Rock Reservoirs](crust-material-and-reservoirs.md) — the non-authoritative packet shadow that advects on the same overlap areas
- [Mesh and Geometry](mesh-and-geometry.md) — control-volume construction, cell areas, neighbor rings
- [Topography, Isostasy and Thermal Subsidence](topography-and-isostasy.md) — the consumer of remapped thickness, density and age
- [Native Engine (C++ Core)](../08-native-engine.md) — translation units, invariants, fail-closed caps
- [Compute Backends (CPU, OpenCL, CUDA)](../09-compute-backends.md) — the discarded continuous-moment shadow and backend telemetry
- [World Document Schema](../10-world-schema.md) — full key inventory for `plate_motion_history[]`
- [Serialization and World Formats](../11-serialization.md) — round-trip vs. display precision contracts
- [Validation](../12-validation.md) — how the replay checks are composed into the geo report
- [Glossary](../21-glossary.md)
