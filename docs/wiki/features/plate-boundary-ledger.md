# Plate Boundary Segment Ledger

[Wiki home](../README.md) > Features > Plate Boundary Segment Ledger

The plate boundary segment ledger is the exact, directed, per-step record of every cross-plate **reciprocal control-volume segment** in the mesh, emitted at `plate_motion_history[].boundary_segments` and described by the top-level `plate_boundary_segment_model` contract object. It is authoritative for segment geometry and for direct unsmoothed Euler kinematics, and it carries same-step opening/remapped crust witnesses and a subducting/overriding *candidate* pair. It is deliberately **not** authoritative for physical subduction polarity, slab geometry, slab transfers, or material fate, and the degree-normalized smoothed per-cell boundary forcing that actually drives the tectonic rules does not consume it. Claims on this page are cited to the source that implements them, and every hedge the codebase makes is carried forward rather than softened.

## On this page

- [What one record represents](#what-one-record-represents)
- [Canonical orientation rules](#canonical-orientation-rules)
- [Segment identity: mesh_segment_id versus segment_id](#segment-identity-mesh_segment_id-versus-segment_id)
- [Construction preconditions and fail-closed guards](#construction-preconditions-and-fail-closed-guards)
- [Operational caps are resource guards, not physical limits](#operational-caps-are-resource-guards-not-physical-limits)
- [Intrinsic Euler kinematics and the dimensionless indices](#intrinsic-euler-kinematics-and-the-dimensionless-indices)
- [Direct strengths, class, and convergence activity](#direct-strengths-class-and-convergence-activity)
- [The nominal km/Ma conversion and why it is uncalibrated](#the-nominal-kmma-conversion-and-why-it-is-uncalibrated)
- [Opening crust witnesses and the unavailable-state sentinel](#opening-crust-witnesses-and-the-unavailable-state-sentinel)
- [Polarity: candidate pair versus explicit unknown](#polarity-candidate-pair-versus-explicit-unknown)
- [Complete record field table](#complete-record-field-table)
- [The `plate_boundary_segment_model` contract object](#the-plate_boundary_segment_model-contract-object)
- [Step-level counters in `plate_motion_history`](#step-level-counters-in-plate_motion_history)
- [Where the ledger is built and who consumes it](#where-the-ledger-is-built-and-who-consumes-it)
- [The smoothed cell forcing that does not consume this ledger](#the-smoothed-cell-forcing-that-does-not-consume-this-ledger)
- [Strict Python replay](#strict-python-replay)
- [Worked examples](#worked-examples)
- [Reproducing and inspecting the ledger](#reproducing-and-inspecting-the-ledger)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

---

## What one record represents

One record is **one cross-plate reciprocal control-volume segment**: a single directed great-circle arc of the spherical control-volume (dual) mesh whose two sides belong to different plates at that step. It is not a neighbor pair, and it is not collapsed to a neighbor pair.

The distinction is load-bearing. In a spherical control-volume tessellation two cells can share **more than one** disjoint arc of their control-volume boundaries. The mesh builder explicitly supports and validates this: `cpp/src/engine/mesh.cpp:701-731` counts the forward multiplicity of a neighbor id in `control_volume_edge_neighbor_ids` and requires the reverse multiplicity to match exactly, throwing `"control-volume shared-edge multiplicity is not reciprocal"` otherwise, and then requires each individual local edge to have a reverse-endpoint reciprocal partner (`cpp/src/engine/mesh.cpp:747-760`). A neighbor-pair-keyed ledger would silently merge those physically distinct pieces of boundary, destroying their separate lengths, midpoints, tangents, and normals.

`build_plate_boundary_segments` therefore iterates local control-volume **edges**, not neighbor ids (`cpp/src/engine/plate_boundary_segments.cpp:267-285`), and matches each one to exactly one *unused* reciprocal edge on the other cell (`cpp/src/engine/plate_boundary_segments.cpp:295-329`). The engine README states the rule directly: it "does not collapse by neighbor pair, so the two physical pieces that a geodesic dual can place between the same cells remain distinct" (`cpp/src/engine/README.md:180-182`).

The native regression fixture is a minimal, deliberately degenerate demonstration: two cells at the poles, each with a three-vertex equatorial control-volume ring, every edge naming the other cell (`cpp/tests/plate_boundary_segments_test.cpp:45-65`). Both cells are mutual neighbors exactly once as a *pair*, but they share **three** distinct reciprocal segments. The test asserts `mesh_segment_count == 3` and `segments.size() == 3` (`cpp/tests/plate_boundary_segments_test.cpp:157-158`), i.e. three records for one neighbor pair.

The Python replay reports the phenomenon as a first-class metric, `duplicate_neighbor_pair_segment_count`, computed as `sum(count - 1 for count in pair_counts.values() if count > 1)` over `(left_cell_id, right_cell_id)` keys (`src/magic_geo/plate_boundary_edge_validation.py:1273-1279`).

| Property | Value | Source |
| --- | --- | --- |
| Record granularity | one cross-plate reciprocal control-volume segment | `plate_boundary_segments.cpp:267-342` |
| Collapsed by neighbor pair? | no | `README.md:180-182`; `plate_boundary_edge_validation.py:1273-1279` |
| Segment curve | shorter great-circle arc | model key `segment_curve = "shorter_great_circle_arc"`, `process_serialization.cpp:2995` |
| Geometry source | `cells[].control_volume_vertices_3d` + `cells[].control_volume_edge_neighbor_ids` | model key `geometry_source`, `process_serialization.cpp:2993-2994` |
| Ledger location | `plate_motion_history[].boundary_segments` | `process_serialization.cpp:2978-2979`, `:4320` |
| Record layout | `flat_record_array_v2` (one flat object per segment; no nested vectors) | `process_serialization.cpp:2980` |
| Emitted per step | filtered to cross-plate segments only | `plate_boundary_segments.cpp:340-342` |

Same-plate segments are enumerated and counted (they consume a `mesh_segment_id`) but produce no record: the `left.plate_id == right.plate_id` `continue` sits *after* the mesh id is issued (`cpp/src/engine/plate_boundary_segments.cpp:331-342`). The fixture confirms it: an all-one-plate mesh returns an empty vector while still reporting `count == 3` (`cpp/tests/plate_boundary_segments_test.cpp:625-630`).

---

## Canonical orientation rules

Four rules make every sign in the record canonical and reproducible.

| # | Rule | Implementation | Failure mode |
| --- | --- | --- | --- |
| 1 | **Lower cell id is the left side.** The outer loop only emits when `right_cell_id >= left_index`; lower-id edges are skipped and consumed as reciprocals. | `plate_boundary_segments.cpp:283-285` | n/a (structural) |
| 2 | **The left cell's counter-clockwise control-volume edge supplies `start` -> `end`.** `start = vertices[left_edge_index]`, `end = vertices[(left_edge_index + 1) % n]`. Counter-clockwise is verified as `dot(left.p, normalize(cross(start, end))) > 0`. | `plate_boundary_segments.cpp:288-291`, `:344-351` | throws `plate-boundary canonical left edge is not counter-clockwise` |
| 3 | **The tangent follows that direction.** `tangent = normalize(cross(edge_plane_normal, midpoint))` where `edge_plane_normal = normalize(cross(start, end))` and `midpoint = normalize(start + end)`. | `plate_boundary_segments.cpp:352-357` | throws `plate-boundary segment tangent is degenerate` |
| 4 | **The transverse normal points from the left cell toward the right cell.** `left_to_right_normal = normalize(cross(tangent, midpoint))`, verified as `dot(normal, right.p - left.p) > 0`. | `plate_boundary_segments.cpp:358-370` | throws `plate-boundary normal does not point left-to-right` |

Rules 3 and 4 give an orthonormal right-handed triad at the segment midpoint, `tangent x midpoint = left_to_right_normal`, with all three vectors mutually orthogonal and unit length (asserted in `cpp/tests/plate_boundary_segments_test.cpp:173-186`). Note that rule 1's skip test is written as "skip when `right_cell_id < left_index`"; the equality case cannot occur because a self-referencing neighbor id is rejected earlier (`plate_boundary_segments.cpp:274-282`).

### Text diagram

Viewed from *outside* the sphere, looking down on the left cell (whose control-volume ring is counter-clockwise, so its polygon normal equals its own position `left.p`):

```text
                       ^ tangent_unit  =  normalize(cross(edge_plane_normal, midpoint_unit))
                       |
        end_unit  *----+
                  |    |
                  |    |                      left_to_right_normal_unit
  LEFT  cell      |    * midpoint_unit  ---------------------------->    RIGHT cell
  (lower id)      |    |   = normalize(start_unit + end_unit)            (higher id)
  left.p  O       |    |                                                 O  right.p
  plate = L       |    |                                                 plate = R
                  |    |
      start_unit  *----+

  edge_plane_normal = normalize(cross(start_unit, end_unit));  dot(left.p, edge_plane_normal) > 0
  left_to_right_normal_unit = normalize(cross(tangent_unit, midpoint_unit))
  dot(left_to_right_normal_unit, right.p - left.p) > 0
```

Walking `start -> end` along `tangent_unit` keeps the left cell on your left; `left_to_right_normal_unit` is the outward-in-plane transverse direction crossing the boundary from the left cell into the right cell.

### Exact worked triad

For the polar two-cell fixture, edge 0 has `start = (1, 0, 0)`, `end = (-1/2, sqrt(3)/2, 0)`, `left.p = (0, 0, 1)`, `right.p = (0, 0, -1)`:

| Quantity | Value | Verified at |
| --- | --- | --- |
| `edge_plane_normal` | `(0, 0, 1)` | implied by `dot(left.p, n) = 1 > 0`, `plate_boundary_segments.cpp:347` |
| `midpoint_unit` | `(1/2, sqrt(3)/2, 0)` | `plate_boundary_segments_test.cpp:281-283, 301` |
| `tangent_unit` | `(-sqrt(3)/2, 1/2, 0)` | `plate_boundary_segments_test.cpp:283` |
| `left_to_right_normal_unit` | `(0, 0, -1)` | `plate_boundary_segments_test.cpp:187` (`normal.z < -0.999999999999`) |
| `angular_length_rad` | `2*pi/3` | `plate_boundary_segments_test.cpp:188` |

### Orientation reversal is exactly antisymmetric

Reversing which cell holds the lower id (by swapping positions, rings, plates, and crust arrays) reverses exactly the direction-carrying fields and leaves the direction-free ones alone. The regression asserts, for the mirrored ledger read back-to-front (`cpp/tests/plate_boundary_segments_test.cpp:514-607`):

| Field family | Behaviour under left/right reversal |
| --- | --- |
| `start_unit` / `end_unit` | swapped |
| `midpoint_unit` | unchanged |
| `tangent_unit`, `left_to_right_normal_unit` | negated |
| `left_euler_velocity_*` / `right_euler_velocity_*` | swapped |
| `relative_velocity_*` | negated |
| `signed_opening_index`, `signed_convergence_index`, `signed_slip_index` | unchanged (double sign flip cancels) |
| `signed_opening_rate_km_per_ma`, `signed_convergence_rate_km_per_ma`, `signed_slip_rate_km_per_ma` | unchanged |
| `direct_boundary_class` | unchanged |
| `left_opening_*` / `right_opening_*` | swapped |
| `candidate_subducting_side` / `candidate_overriding_side` | `left` <-> `right`, `none` stays `none` |
| `physical_polarity_status`, `physical_subducting_side`, `physical_overriding_side` | unchanged |

---

## Segment identity: mesh_segment_id versus segment_id

Two distinct ids appear in every record, and they answer different questions.

| Field | Semantics | Counter reset | Stability | Source |
| --- | --- | --- | --- | --- |
| `mesh_segment_id` | Stable index over **all** reciprocal mesh segments — cross-plate and same-plate alike — in `(left_cell_id, left_edge_index)` order, assigned *before* the cross-plate filter | per call; the mesh graph is fixed for the run, so the same segment keeps the same id in every step | stable across steps for a fixed mesh | `plate_boundary_segments.cpp:266`, `:331`; model key `mesh_segment_id_semantics`, `process_serialization.cpp:2989-2990` |
| `segment_id` | Zero-based contiguous index **within each step's cross-plate ledger**; equals the record's position in `boundary_segments` | per step | shifts whenever plate assignment changes which mesh segments are cross-plate | `plate_boundary_segments.cpp:431`; model key `segment_id_semantics`, `process_serialization.cpp:2991-2992` |

In the polar fixture, where every mesh segment is cross-plate and there are exactly three of them, the two ids coincide (`segment.segment_id == index` and `segment.mesh_segment_id == index`, `cpp/tests/plate_boundary_segments_test.cpp:165-166`). In a real run they diverge as soon as any interior (same-plate) control-volume segment exists, which is the overwhelming majority.

Consequences for consumers:

- `segment_id` is what `crust_overlap_candidate_fate_ledger.boundary_pair_evidence[].segment_ids` refers to, and the ledger requires `segment.segment_id == index` (`cpp/src/engine/crust_overlap_candidate_fate.cpp:444-457`).
- `segment_id` is what `initial_oceanic_crust_age_ledger.eligible_ridge_segment_ids` refers to, sorted ascending (`cpp/src/engine/initial_oceanic_age.cpp:135, 142-145`).
- `mesh_segment_id` is the only id that lets you correlate the *same physical arc* across steps. Nothing in the schema does that today; it is exposed so downstream tooling can.

The step also records the total mesh segment count separately from the cross-plate count — see [Step-level counters](#step-level-counters-in-plate_motion_history). The model object asserts that the total never changes across steps: `plate_boundary_segment_model_json` throws `"plate-boundary reciprocal mesh segment count changed"` if any step disagrees (`cpp/src/engine/process_serialization.cpp:2962-2972`).

---

## Construction preconditions and fail-closed guards

`build_plate_boundary_segments(const Params&, const std::vector<Cell>&, const std::vector<Plate>&, const CrustTransportPlan&, int* reciprocal_mesh_segment_count)` (`cpp/src/engine/plate_boundary_segments.cpp:176-182`) validates everything before and during construction and throws `std::runtime_error` on any violation. There is no tolerant path and no partial result.

### Output-parameter and parameter guards

| Precondition | Threshold / rule | Exception message | Line |
| --- | --- | --- | --- |
| Out-parameter is non-null | `reciprocal_mesh_segment_count != nullptr` | `plate-boundary reciprocal mesh segment count output is null` | `:183-187` |
| Radius finite and positive | `isfinite(radius_km) && radius_km > 0` | `plate-boundary nominal velocity scale inputs are invalid` | `:190-198` |
| Reference motion scale finite and nonnegative | `isfinite(plate_motion_scale_deg_per_step) && >= 0` | same as above | `:190-198` |
| Derived velocity scale finite | `isfinite(velocity_scale_km_per_ma)` | `plate-boundary nominal velocity scale is not finite` | `:202-206` |

### Opening/remapped crust array guards (`validate_opening_crust_arrays`, `:117-172`)

| Precondition | Threshold / rule | Exception message | Line |
| --- | --- | --- | --- |
| All five remapped arrays are cell-count length | `size == cells.size()` for type, lithology, age, thickness, density | `plate-boundary opening/remapped crust array size mismatch` | `:121-133` |
| Crust type in range | `0 <= crust_type < CRUST_NAMES.size()` (= 9) | `plate-boundary opening/remapped crust category is invalid` | `:145-154` |
| Lithology in range | `0 <= lithology < LITHOLOGY_NAMES.size()` (= 7) | same as above | `:145-154` |
| Age finite and nonnegative | `isfinite(age_ma) && age_ma >= 0` | `plate-boundary opening/remapped crust state is invalid` | `:155-163` |
| Thickness finite and nonnegative | `isfinite(thickness_km) && thickness_km >= 0` | same as above | `:155-163` |
| Density finite and strictly positive | `isfinite(density) && density > 0` | same as above | `:155-163` |
| No partial state | if not (`age == 0 && thickness == 0`) then `thickness > 0` | `plate-boundary opening/remapped crust state is partial` | `:164-170` |

The last rule is what makes the unavailable sentinel unambiguous: the *only* legal way to have zero thickness is to also have zero age. Density must be positive in both cases.

### Per-cell mesh guards (`:210-263`)

| Precondition | Threshold / rule | Exception message | Line |
| --- | --- | --- | --- |
| Canonical cell ordering | `cell.id == index` | `plate-boundary cells are not in canonical id order` | `:212-216` |
| Cell position finite | all three components finite | `plate-boundary cell position is not finite` | `:217` |
| Cell position on unit sphere | `abs(norm(p) - 1) <= 3.0e-12` | `plate-boundary cell position is not on the unit sphere` | `:218-225` |
| Ring is complete | `vertices.size() == edge_neighbor_ids.size()` and `>= 3` | `plate-boundary control-volume geometry is incomplete` | `:226-234` |
| Per-cell segment cap | `vertices.size() <= 64` | `plate-boundary per-cell control-volume segment cap exceeded` | `:235-242` |
| Plate id in range | `0 <= plate_id < plates.size()` | `plate-boundary plate id is invalid` | `:243-248` |
| Vertices finite | all components finite | `plate-boundary control-volume vertex is not finite` | `:249-250` |
| Vertices on unit sphere | `abs(norm(v) - 1) <= 3.0e-12` | `plate-boundary control-volume vertex is not on the unit sphere` | `:251-258` |

### Per-segment guards (`:272-428`)

| Precondition | Threshold / rule | Exception message | Line |
| --- | --- | --- | --- |
| Edge neighbor id valid | `0 <= id < cells.size()` and `id != left_index` | `plate-boundary control-volume neighbor id is invalid` | `:274-282` |
| Endpoints finite | `start`, `end` all components finite | `plate-boundary segment start/end is not finite` | `:292-293` |
| Exactly one unused reverse-endpoint reciprocal | `max(norm(start - reciprocal_end), norm(end - reciprocal_start)) <= 1.0e-10`, matched exactly once | `plate-boundary segment lacks one unique reciprocal edge` | `:295-327` |
| Reciprocal mesh segment cap | `mesh_segment_id <= 8 * cells.size()` | `plate-boundary reciprocal mesh segment cap exceeded` | `:332-339` |
| Left edge counter-clockwise | `dot(left.p, edge_plane_normal) > 0` | `plate-boundary canonical left edge is not counter-clockwise` | `:347-351` |
| Non-degenerate normalizations | `norm > 1.0e-14` and finite, for edge plane normal, midpoint, tangent, left-to-right normal | `plate-boundary <context> is degenerate` | `:48-55`, `:344-360` |
| Normal points left-to-right | `dot(normal, right.p - left.p) > 0` | `plate-boundary normal does not point left-to-right` | `:361-370` |
| Angular length valid | `isfinite(angular_length) && angular_length > 0` | `plate-boundary angular segment length is invalid` | `:371-379` |
| Euler axes finite | both plate axes finite | `plate-boundary left/right Euler axis is not finite` | `:385-386` |
| Euler axes unit length | `abs(norm(axis) - 1) <= 1.0e-12` | `plate-boundary Euler axis is not unit length` | `:387-396` |
| Intrinsic speeds finite and nonnegative | `isfinite(speed) && speed >= 0` for both plates | `plate-boundary intrinsic angular speed is not finite` | `:397-406` |

### Post-pass reciprocity audit (`:588-603`)

After the main loop, every local edge whose neighbor id is **lower** than its own cell id must have been consumed as somebody's reciprocal. Any unconsumed lower-id edge throws `plate-boundary reciprocal edge was not consumed`. This closes the loop: the union of emitted segments plus their reciprocals is exactly the set of local edges, with no orphan and no double-count.

### Guards exercised by the native regression

`cpp/tests/plate_boundary_segments_test.cpp:619-728` asserts fail-closed behaviour for: a perturbed reciprocal endpoint (`z = 0.01`), non-unit cell positions and vertices (all scaled by 2), a NaN cell position, a two-vertex ring, an out-of-range crust type (`= CRUST_NAMES.size()`), a negative lithology, a non-unit Euler axis (`{0, 2, 0}`), a negative angular speed (`-0.1`), a partial crust state (`thickness = 0` with nonzero age), and a 65-vertex ring. All are expected to throw.

The suite is registered as the CTest target `magic_geo_plate_boundary_segments` (`CMakeLists.txt:338-358`), built from the test plus `cpp/src/engine/plate_boundary_segments.cpp` alone, without linking `magic_geo_native`, and compiled with `-ffp-contract=off` under GCC/Clang (`CMakeLists.txt:350-354`).

---

## Operational caps are resource guards, not physical limits

Two caps appear in the construction path and both are exported in the model contract.

| Cap | Value | Scope | Enforced at | Model key |
| --- | --- | --- | --- | --- |
| `MAX_CONTROL_VOLUME_SEGMENTS_PER_CELL` | 64 | per cell, on `control_volume_vertices.size()` | `plate_boundary_segments.cpp:7`, `:235-242` | `maximum_control_volume_segments_per_cell` (`process_serialization.cpp:3007`) |
| `MAX_RECIPROCAL_MESH_SEGMENTS_PER_CELL` | 8 | global, as `mesh_segment_id <= 8 * cell_count` | `plate_boundary_segments.cpp:8`, `:332-339` | `maximum_reciprocal_mesh_segment_count_multiplier` (`process_serialization.cpp:3008-3009`) plus the formula key `reciprocal_mesh_segment_count_cap_formula = "reciprocal_mesh_segment_count_le_8_times_cell_count"` (`:3010-3011`) |

The document states their semantics explicitly, in a dedicated key: `operational_cap_semantics = "nonphysical_fail_closed_resource_and_malformed_geometry_guards"` (`cpp/src/engine/process_serialization.cpp:3012-3013`). The engine README repeats it: "The caps are malformed-geometry/resource guards, not physical limits" (`cpp/src/engine/README.md:190-191`).

Read them that way. A cap of 8 reciprocal segments per cell does **not** assert that a plate boundary cannot be more complex; it asserts that a mesh producing more than that per cell on average is malformed or adversarial, and the engine will refuse rather than allocate. This is the same fail-closed posture the crust reservoir uses for its 1,024-per-owner / 1,000,000-across-reservoirs packet and 1,000,000-per-step transfer caps, which the README calls "numerical memory-safety limits, not physical flux or capacity limits" (`cpp/src/engine/README.md:321-324`).

The Python replay mirrors both caps independently rather than trusting the document: it rejects rings outside `3 <= len <= 64` (`src/magic_geo/plate_boundary_edge_validation.py:522-529`), caps cumulative local edges at `16 * cell_count` — i.e. `8 * cell_count` segments, since each segment consumes two local edges (`:530-534`) — and re-checks `len(mesh_segments) <= 8 * cell_count` after enumeration (`:1129-1132`). It also verifies that the serialized model reports exactly `64` and `8` (`:1080-1095`).

---

## Intrinsic Euler kinematics and the dimensionless indices

Everything kinematic in the record derives from one primitive evaluated at the segment midpoint.

### Intrinsic Euler velocity

```text
intrinsic_euler_velocity(plate) = cross(plate.rotation_axis * plate.intrinsic_angular_speed,
                                        segment.midpoint_unit)
```

Implemented at `cpp/src/engine/plate_boundary_segments.cpp:407-412`; declared as the model key `intrinsic_euler_velocity_formula = "cross(rotation_axis*intrinsic_angular_speed,segment_midpoint_unit)"` (`cpp/src/engine/process_serialization.cpp:3027-3028`).

`rotation_axis` and `intrinsic_angular_speed` are per-plate constants for the whole run. The model asserts this in two keys — `intrinsic_angular_speed_snapshot_semantics` and `rotation_axis_snapshot_semantics`, both `"constant_per_plate_across_all_history_steps_including_initial_snapshot"` (`process_serialization.cpp:3029-3036`) — and gives the cross-checks against the top-level `plates[]` array (`plate_motion_history[].plates[].intrinsic_angular_speed == plates[].angular_speed` by plate id, and likewise for the axis). The speeds themselves are procedural indices drawn in `generate_plates` as `(min_angular_speed + (max_angular_speed - min_angular_speed) * U) * tectonic_activity` (`cpp/src/engine/tectonics.cpp:31-32`), with configured defaults `min_angular_speed = 0.03` and `max_angular_speed = 0.95` (`src/magic_geo/config.py:281-292`).

### The three dimensionless indices

The **relative** intrinsic velocity is `right - left`, and the indices are its projections onto the canonical triad:

| Index | Formula | Sign convention | Line | Model key |
| --- | --- | --- | --- | --- |
| `signed_opening_index` | `dot(raw_relative_velocity, left_to_right_normal_unit)` | positive = the two sides separate | `:415-416` | `signed_opening_index_formula` (`:3075-3076`) |
| `signed_convergence_index` | `-signed_opening_index` | positive = the two sides approach | `:453` | `signed_convergence_index_formula` (`:3077-3078`) |
| `signed_slip_index` | `dot(raw_relative_velocity, tangent_unit)` | signed along `start -> end` | `:417-418` | `signed_slip_index_formula` (`:3079-3080`) |

Their unit is declared as `intrinsic_kinematic_index_unit = "unit_sphere_tangent_velocity_per_intrinsic_angular_speed_unit"` (`cpp/src/engine/process_serialization.cpp:3000-3001`). They are dimensionless in the sense that they carry no length or time: they are pure functions of the unit-sphere geometry and the procedural angular-speed indices, and they are invariant under both planetary radius and the nominal timestep.

### Invariances the native regression proves

`analytic_euler_modes_and_invariances_are_exact` (`cpp/tests/plate_boundary_segments_test.cpp:271-453`) and `radius_and_canonical_orientation_invariances_are_exact` (`:456-617`) assert:

| Invariance | Statement | Line |
| --- | --- | --- |
| Rigid-motion cancellation | two plates with identical axis and speed give zero relative velocity, zero indices, and class `inactive` | `:354-378` |
| Angular-velocity offset invariance | adding a common angular-velocity vector to two unequal plates changes absolute velocities but leaves every relative field, index, rate, strength, and class unchanged | `:381-437` |
| Euler-pole degeneracy | a plate whose axis equals the segment midpoint contributes zero velocity there even at nonzero speed | `:439-451` |
| Radius invariance of indices | scaling `radius_km` by 2.5 leaves `angular_length_rad`, all three indices, and the class unchanged | `:479-487` |
| Radius linearity of rates | `length_km`, all three velocity vectors, and all three signed rates scale exactly by the radius factor | `:480, :488-511` |

---

## Direct strengths, class, and convergence activity

The three strengths are computed from the **dimensionless indices**, not from the km/Ma rates. They are therefore invariant to radius and to the nominal velocity scale.

| Strength | Formula | Line | Model key |
| --- | --- | --- | --- |
| `direct_convergent_strength` | `clamp(signed_convergence_index * 1.25, 0, 1)` | `:455-457` | `direct_convergent_strength_formula` (`:3081-3082`) |
| `direct_divergent_strength` | `clamp(signed_opening_index * 1.25, 0, 1)` | `:458-460` | `direct_divergent_strength_formula` (`:3083-3084`) |
| `direct_transform_strength` | `clamp((abs(signed_slip_index) - abs(signed_opening_index) * 0.35) * 1.05, 0, 1)` | `:461-468` | `direct_transform_strength_formula` (`:3085-3086`) |

`direct_boundary_class` is then the arg-max of the three strengths, with an inactive floor (`cpp/src/engine/plate_boundary_segments.cpp:99-115`):

| Condition (evaluated in order) | `direct_boundary_class` |
| --- | --- |
| `max(convergent, divergent, transform) < 0.08` | `inactive` |
| `convergent == max` | `convergent` |
| `divergent == max` | `divergent` |
| otherwise | `transform` |

The tie-break order is declared as `direct_boundary_class_tie_break = "convergent_then_divergent_then_transform"` and the threshold as `direct_boundary_class_inactive_threshold = 0.08` (`cpp/src/engine/process_serialization.cpp:3087-3092`).

`convergence_active` is a **separate** predicate: `direct_convergent_strength >= 0.08` (`cpp/src/engine/plate_boundary_segments.cpp:474-475`). It is deliberately independent of which class won, declared as `polarity_convergence_applicability_rule = "direct_convergent_strength_ge_0_08_independent_of_winning_boundary_class"` (`process_serialization.cpp:3093-3094`). The consequence, spelled out in the README and proved by the fixture, is that an oblique transform-dominant segment with real normal convergence is **not** discarded from polarity consideration. The test constructs exactly that case — angular velocity `(0.4*sqrt(3)/2, -0.2, 0.8)` giving `signed_convergence_index = 0.4`, `signed_slip_index = 0.8`, class `transform`, `convergence_active = true` — and asserts the candidate pair is still produced (`cpp/tests/plate_boundary_segments_test.cpp:324-340`).

Because the floor and the activity threshold are both `0.08`, a `convergent`-class segment always has `convergence_active = true`, but the converse does not hold.

---

## The nominal km/Ma conversion and why it is uncalibrated

The record also carries velocity vectors and rates labelled km/Ma. They are the intrinsic quantities multiplied by one scalar:

```text
velocity_scale_km_per_ma = radius_km
                         * plate_motion_scale_deg_per_step   (the REFERENCE scale)
                         * (pi / 180)
                         / MATURATION_REFERENCE_TIMESTEP_MA  (= 5.0)
```

Implemented at `cpp/src/engine/plate_boundary_segments.cpp:199-206`; recomputed identically for the model key `nominal_velocity_scale_km_per_ma` at `cpp/src/engine/process_serialization.cpp:2950-2952`; declared as `nominal_velocity_scale_formula = "radius_km*reference_motion_scale_deg_per_reference_step*(pi/180)/reference_timestep_ma"` (`:3025-3026`). `MATURATION_REFERENCE_TIMESTEP_MA = 5.0` is defined at `cpp/src/engine/constants.hpp:72`.

| Derived field | Formula | Line |
| --- | --- | --- |
| `left_euler_velocity_*_km_per_ma` | `left intrinsic velocity * velocity_scale_km_per_ma` | `:419-420` |
| `right_euler_velocity_*_km_per_ma` | `right intrinsic velocity * velocity_scale_km_per_ma` | `:421-422` |
| `relative_velocity_*_km_per_ma` | `right_euler_velocity - left_euler_velocity` | `:423-424` |
| `signed_opening_rate_km_per_ma` | `dot(relative_velocity, left_to_right_normal_unit)` | `:425-426` |
| `signed_convergence_rate_km_per_ma` | `-signed_opening_rate_km_per_ma` | `:450` |
| `signed_slip_rate_km_per_ma` | `dot(relative_velocity, tangent_unit)` | `:427-428` |
| `length_km` | `radius_km * angular_length_rad` | `:445` |

### Why it is uncalibrated

Four independent reasons, all stated in the source rather than inferred:

1. **The angular speed is a procedural index, not a physical rotation rate.** `plate.angular_speed` is a uniform draw between `min_angular_speed` and `max_angular_speed` scaled by a `tectonic_activity` factor (`cpp/src/engine/tectonics.cpp:19, 31-32`). The config field descriptions call them "procedural plate angular-speed index" values (`src/magic_geo/config.py:281-292`). Nothing ties them to observed plate motions.
2. **`plate_motion_scale_deg_per_step` is a displacement *scale*, not a measured rate.** Its config description is "Plate displacement scale in degrees per five-million-year reference step", default `2.0`, bounded `[0, 10]` (`src/magic_geo/config.py:299-304`).
3. **The 5 Ma denominator is a nominal reference interval, not physical time.** The model object carries `nominal_time_calibrated = false` and `physical_time_resolved = false` (`cpp/src/engine/process_serialization.cpp:3135-3136`), and `plate_kinematic_model` sets `physical_time_resolved`, `nominal_time_calibrated`, `process_rate_calibration_resolved`, and `time_step_convergence_demonstrated` all false (`cpp/src/engine/process_serialization.cpp:2686-2689`).
4. **The document says so directly.** `physical_plate_velocity_calibrated = false` (`cpp/src/engine/process_serialization.cpp:3137`); `velocity_unit = "km_per_Ma_nominal"` (`:2999`). The engine README: "That conversion is a nominal reference-step scale, not a calibrated physical velocity" (`cpp/src/engine/README.md:196-198`), and the binding invariant "nominal km/Ma is uncalibrated" (`cpp/src/engine/README.md:334-336`).

### The scale uses the *reference* motion scale, not the effective one

This is a subtlety worth stating explicitly. The actual per-step plate rotation uses the **effective** motion scale, `reference_motion_scale_deg_per_reference_step * maturation_timestep_scale` where `maturation_timestep_scale = maturation_timestep_ma / 5.0` (`cpp/src/engine/core.cpp:44-47`; `plate_kinematic_model.effective_motion_scale_deg_per_step`, `cpp/src/engine/process_serialization.cpp:2710-2712`). The ledger's velocity scale does **not** apply `maturation_timestep_scale`: it uses `params.plate_motion_scale_deg_per_step` raw over the fixed 5 Ma reference (`cpp/src/engine/plate_boundary_segments.cpp:199-201`). So refining `erosion.maturation_timestep_ma` (default `5.0`, bounded `(0, 5]`, `src/magic_geo/config.py:382-387`) changes how far plates actually rotate per step but leaves every serialized boundary velocity and rate unchanged. Read the km/Ma numbers as a *fixed reference-step scale attached to the segment*, never as "the velocity realised during this step".

### km/Ma and mm/yr are numerically equal

The regression closes with a static assertion that `1 km/Ma == 1 mm/yr` numerically, since `1e6 mm/km / 1e6 yr/Ma == 1` (`cpp/tests/plate_boundary_segments_test.cpp:609-615`). Convenient for reading the numbers against published plate-velocity figures — but the equality is dimensional, not evidence of calibration.

---

## Opening crust witnesses and the unavailable-state sentinel

Each record carries five crust fields per side, read from the **same-step** `CrustTransportPlan` handed to the builder (`cpp/src/engine/plate_boundary_segments.cpp:477-531`). The declared source is `opening_crust_state_source = "same_step_crust_overlap_ledger_remapped_pre_process_state"` (`cpp/src/engine/process_serialization.cpp:3095-3096`), i.e. the arrays serialized at `plate_motion_history[].crust_overlap_ledger.remapped_*_by_cell`. These are the **pre-process** (post-transport, pre-crust-rule) values: the state the cell holds at the opening of the step's tectonic rules, indexed by destination cell id.

| Record field | Transport-plan array | Unit |
| --- | --- | --- |
| `left/right_opening_crust_type` | `remapped_crust_type_by_cell` | enum index into `CRUST_NAMES` (9 names, `cpp/src/engine/schema_names.hpp:7-10`) |
| `left/right_opening_lithology` | `remapped_lithology_by_cell` | enum index into `LITHOLOGY_NAMES` (7 names, `:11-13`) |
| `left/right_opening_crust_age_ma` | `remapped_crust_age_ma_by_cell` | Ma (`opening_crust_age_unit`, `process_serialization.cpp:3002`) |
| `left/right_opening_crust_thickness_km` | `remapped_crust_thickness_km_by_cell` | km (`:3003`) |
| `left/right_opening_crust_density_g_cm3` | `remapped_crust_density_by_cell` | g/cm3 (`:3004`) |

### The unavailable-state sentinel

```text
opening_crust_state_available  ==  NOT (age_ma == 0.0 AND thickness_km == 0.0)
```

Implemented at `cpp/src/engine/plate_boundary_segments.cpp:492-495` (left) and `:519-522` (right); declared as `opening_crust_state_availability_rule = "unavailable_iff_age_ma_and_thickness_km_are_both_zero_density_always_positive_available_states_require_positive_thickness"` (`process_serialization.cpp:3097-3098`).

Exactly-zero age **and** exactly-zero thickness means the forward overlap supplied that destination cell with **no incoming crust volume at all**. The producing branch is explicit: when the accumulated incoming volume is not positive, `crust_transport.cpp` sets `remapped_crust_age_ma_by_cell = 0.0`, leaves thickness at its `0.0` initialization, and *retains the previous* crust type, lithology, and density for that destination (`cpp/src/engine/crust_transport.cpp:926-927`, `:1768-1776`).

That retention is why the categorical and density values in an unavailable record are meaningless as material state. The document says so in its own key: `unavailable_opening_crust_sentinel_semantics = "retained_categorical_and_density_values_are_fixed_shape_unavailable_state_sentinels_not_material_state"` (`cpp/src/engine/process_serialization.cpp:3099-3100`). The engine README says the same: "retained category and density values in that case are fixed-shape unavailable-state sentinels" (`cpp/src/engine/README.md:200-203`).

| Case | `age_ma` | `thickness_km` | `density` | `type` / `lithology` | `..._state_available` | `..._oceanic_like` |
| --- | --- | --- | --- | --- | --- | --- |
| Available | `>= 0` | `> 0` | `> 0` | meaningful (volume-dominant category pair) | `true` | predicate evaluated |
| Unavailable sentinel | `== 0` exactly | `== 0` exactly | `> 0` but a retained previous value | retained previous values, not material state | `false` | forced `false` |
| Partial (rejected) | any | `== 0` with `age != 0` | any | any | n/a | construction throws |

### The oceanic-like predicate

`oceanic_like_opening_state` (`cpp/src/engine/plate_boundary_segments.cpp:70-85`) is byte-for-byte the same rule as the shared `is_oceanic_crust_state` (`cpp/src/engine/tectonics.cpp:513-530`):

| Crust type | Name | Rule |
| --- | --- | --- |
| `0` | `oceanic` | always oceanic-like |
| `2` | `transitional` | oceanic-like iff `lithology == 0` (`basalt`) |
| `3` | `volcanic_arc` | oceanic-like iff `age_ma <= 320.0` **and** `thickness_km <= 18.0` **and** `density_g_cm3 >= 2.84` |
| `1`, `4`-`8` | `continental`, `craton`, `orogen`, `rift_basin`, `sedimentary_basin`, `accreted_terrane` | never oceanic-like |

Declared as `opening_oceanic_like_predicate = "crust_type_0_or_crust_type_2_with_lithology_0_or_crust_type_3_with_age_le_320_ma_thickness_le_18_km_density_ge_2_84_g_cm3"` (`cpp/src/engine/process_serialization.cpp:3101-3102`).

Evaluation is gated on availability: `..._opening_oceanic_like = ..._opening_crust_state_available && oceanic_like_opening_state(...)` (`cpp/src/engine/plate_boundary_segments.cpp:496-504`, `:523-531`), declared as `opening_oceanic_like_evaluation_scope = "available_opening_crust_states_only_unavailable_states_are_false"` (`process_serialization.cpp:3103-3104`). An unavailable side is never oceanic-like, regardless of the retained sentinel category.

---

## Polarity: candidate pair versus explicit unknown

The ledger carries **two disjoint polarity concepts** in every record. Conflating them is the single most likely misreading of this schema.

### Concept 1 — the kinematic + crust-state CANDIDATE pair

`polarity_candidate_status` is assigned by a strict ordered cascade (`cpp/src/engine/plate_boundary_segments.cpp:532-559`). The serialized `polarity_candidate_status_order` array pins that order (`cpp/src/engine/process_serialization.cpp:3105-3106`), and the Python replay asserts the array literally (`src/magic_geo/plate_boundary_edge_validation.py:1005-1016`).

| Order | `polarity_candidate_status` | Condition | `candidate_subducting_side` | `candidate_overriding_side` |
| --- | --- | --- | --- | --- |
| 1 | `no_active_convergence` | `convergence_active == false` | `none` | `none` |
| 2 | `unresolved_missing_opening_crust_state` | active, but either side's opening crust state is unavailable | `none` | `none` |
| 3 | `left_oceanic_only` | active, both available, left oceanic-like, right not | `left` | `right` |
| 4 | `right_oceanic_only` | active, both available, right oceanic-like, left not | `right` | `left` |
| 5 | `ambiguous_both_oceanic` | active, both available, both oceanic-like | `none` | `none` |
| 6 | `unresolved_no_oceanic_side` | active, both available, neither oceanic-like | `none` | `none` |

The side mapping is at `cpp/src/engine/plate_boundary_segments.cpp:560-571` and declared in two model keys, `candidate_subducting_side_mapping` and `candidate_overriding_side_mapping` (`process_serialization.cpp:3107-3110`).

The semantics key is unambiguous about what this is: `candidate_side_semantics = "oceanic_side_heuristic_is_subducting_candidate_and_opposite_side_is_overriding_candidate_not_physical_polarity"` (`process_serialization.cpp:3111-3112`). It is a **heuristic**: "the sole oceanic-like side at an actively converging segment is the subduction candidate, and the other side is the overriding candidate." That is all. The engine README puts it as "A sole oceanic-like side at a convergent segment supplies candidate subducting and inverse overriding sides only" (`cpp/src/engine/README.md:213-214`).

### Concept 2 — the explicit unknown PHYSICAL state

The physical tuple is assigned unconditionally and never derived from the candidate (`cpp/src/engine/plate_boundary_segments.cpp:572-583`):

| `convergence_active` | `physical_polarity_status` | `physical_polarity_source` | `physical_subducting_side` | `physical_overriding_side` | `physical_polarity_confidence` |
| --- | --- | --- | --- | --- | --- |
| `true` | `unknown_unresolved` | `none` | `unknown` | `unknown` | `0.0` |
| `false` | `not_applicable_no_active_convergence` | `none` | `none` | `none` | `0.0` |

Note that `physical_polarity_source` is `"none"` and `physical_polarity_confidence` is `0.0` in **both** rows — the source is set once before the branch (`:572-573`). The confidence is exact zero, and the Python replay demands exact zero rather than an approximate comparison: `_require(observed == 0.0, f"{label}.{field} must remain exact zero while polarity is unknown")` (`src/magic_geo/plate_boundary_edge_validation.py:970-974`).

The declared rules:

| Model key | Value | Line |
| --- | --- | --- |
| `physical_polarity_status_rule` | `active_convergence_unknown_unresolved_else_not_applicable_no_active_convergence` | `process_serialization.cpp:3113-3114` |
| `physical_polarity_source_rule` | `none_until_supplied_constraint_or_physical_solver_is_implemented` | `:3115-3116` |
| `polarity_candidate_is_physical_decision` | `false` | `:3139` |
| `physical_subduction_polarity_resolved` | `false` | `:3140` |
| `physical_polarity_unknown_state_explicit` | `true` | `:3138` |

The type comment states the intent: "Candidate sides are deliberately separate from the physical decision. Until a supplied constraint or a physical solver exists, convergent segments stay explicitly unknown and cannot select a slab" (`cpp/src/engine/types/earth_system.hpp:510-512`).

### The reserved future shape

`crust_overlap_candidate_fate.cpp` already validates a *resolved* physical tuple shape that the segment builder never produces today: `physical_polarity_status == "resolved"` with `physical_polarity_source` in `{"supplied_constraint", "physical_solver"}` and `0 < confidence <= 1` (`cpp/src/engine/crust_overlap_candidate_fate.cpp:192-201`). The Python replay does **not** accept it: `PHYSICAL_POLARITY_STATUS_NAMES` is exactly `{"not_applicable_no_active_convergence", "unknown_unresolved"}` (`src/magic_geo/plate_boundary_edge_validation.py:25-27`) and `physical_polarity_source` must equal `"none"` (`:959-963`). So the resolved branch is dead code from the ledger's perspective and would fail the replay gate if it ever fired without a coordinated schema change.

### The GPGIM alignment caveat

The model exports a convention for how a *supplied* polarity would have to be interpreted: `gpgim_supplied_polarity_convention = "align_supplied_feature_direction_to_canonical_segment_then_left_or_right_names_overriding_side_and_opposite_names_subducting_side"` (`cpp/src/engine/process_serialization.cpp:3117-3118`). The README expands it: "GPGIM left/right supplied polarity names the overriding side, but its feature direction must first be aligned to the canonical segment before selecting the opposite side as subducting" (`cpp/src/engine/README.md:216-219`). This is a *declared* convention for a future consumer, not an implemented import path. No GPGIM/GPlates data is read anywhere in the generation path.

---

## Complete record field table

Each element of `plate_motion_history[].boundary_segments` is a flat object with exactly **67** keys, in the emission order below (`cpp/src/engine/process_serialization.cpp:4117-4317`). Every floating-point field is written with `roundtrip_num`, i.e. general-format `max_digits10` (17 significant digits) that recovers the original binary64 after JSON parsing (`add_segment_double`, `:4123-4130`; `cpp/src/engine/numeric_serialization.cpp`). The model advertises this as `serialized_float_decimal_significant_digits = 17` (`:3126-3127`). The Python replay requires the field set to match exactly — `set(actual) == RECORD_FIELDS`, no extra and no missing keys (`src/magic_geo/plate_boundary_edge_validation.py:924-927`).

| # | Field | JSON type | Meaning | Computed at |
| --- | --- | --- | --- | --- |
| 1 | `segment_id` | int | contiguous index within this step's cross-plate ledger | `plate_boundary_segments.cpp:431` |
| 2 | `mesh_segment_id` | int | stable index over all reciprocal mesh segments, pre-filter | `:331-332` |
| 3 | `left_cell_id` | int | lower cell id | `:433` |
| 4 | `right_cell_id` | int | higher cell id | `:434` |
| 5 | `left_edge_index` | int | index into the left cell's control-volume ring | `:435` |
| 6 | `right_edge_index` | int | index into the right cell's ring (the matched reciprocal) | `:436` |
| 7 | `left_plate_id` | int | left cell's plate at this step's assignment snapshot | `:437` |
| 8 | `right_plate_id` | int | right cell's plate at this step's assignment snapshot | `:438` |
| 9-11 | `start_unit_x/_y/_z` | float | segment start vertex, unit-sphere Cartesian | `:288`, `:439` |
| 12-14 | `midpoint_unit_x/_y/_z` | float | `normalize(start + end)` | `:352-354`, `:440` |
| 15-17 | `end_unit_x/_y/_z` | float | segment end vertex | `:289-291`, `:441` |
| 18-20 | `tangent_unit_x/_y/_z` | float | `normalize(cross(edge_plane_normal, midpoint))` | `:355-357`, `:442` |
| 21-23 | `left_to_right_normal_unit_x/_y/_z` | float | `normalize(cross(tangent, midpoint))`, points left cell -> right cell | `:358-360`, `:443` |
| 24 | `angular_length_rad` | float | `atan2(norm(cross(start,end)), clamp(dot(start,end), -1, 1))` | `:371-374`, `:444` |
| 25 | `length_km` | float | `radius_km * angular_length_rad` | `:445` |
| 26-28 | `left_euler_velocity_x/_y/_z_km_per_ma` | float | left intrinsic velocity * nominal scale | `:419-420`, `:446` |
| 29-31 | `right_euler_velocity_x/_y/_z_km_per_ma` | float | right intrinsic velocity * nominal scale | `:421-422`, `:447` |
| 32-34 | `relative_velocity_x/_y/_z_km_per_ma` | float | `right_euler_velocity - left_euler_velocity` | `:423-424`, `:448` |
| 35 | `signed_opening_rate_km_per_ma` | float | `dot(relative_velocity, normal)` | `:425-426`, `:449` |
| 36 | `signed_convergence_rate_km_per_ma` | float | `-signed_opening_rate_km_per_ma` | `:450` |
| 37 | `signed_slip_rate_km_per_ma` | float | `dot(relative_velocity, tangent)` | `:427-428`, `:451` |
| 38 | `signed_opening_index` | float | `dot(raw_relative_velocity, normal)`, dimensionless | `:415-416`, `:452` |
| 39 | `signed_convergence_index` | float | `-signed_opening_index` | `:453` |
| 40 | `signed_slip_index` | float | `dot(raw_relative_velocity, tangent)`, dimensionless | `:417-418`, `:454` |
| 41 | `direct_convergent_strength` | float | `clamp(signed_convergence_index * 1.25, 0, 1)` | `:455-457` |
| 42 | `direct_divergent_strength` | float | `clamp(signed_opening_index * 1.25, 0, 1)` | `:458-460` |
| 43 | `direct_transform_strength` | float | `clamp((abs(slip) - abs(opening) * 0.35) * 1.05, 0, 1)` | `:461-468` |
| 44 | `direct_boundary_class` | string | `inactive` \| `convergent` \| `divergent` \| `transform` | `:99-115`, `:469-473` |
| 45 | `convergence_active` | bool | `direct_convergent_strength >= 0.08` | `:474-475` |
| 46 | `left_opening_crust_type` | int | index into `CRUST_NAMES` | `:480-481` |
| 47 | `left_opening_lithology` | int | index into `LITHOLOGY_NAMES` | `:482-483` |
| 48 | `left_opening_crust_age_ma` | float | remapped pre-process age | `:484-485` |
| 49 | `left_opening_crust_thickness_km` | float | remapped pre-process thickness | `:486-489` |
| 50 | `left_opening_crust_density_g_cm3` | float | remapped pre-process density | `:490-491` |
| 51 | `left_opening_crust_state_available` | bool | `!(age == 0 && thickness == 0)` | `:492-495` |
| 52 | `left_opening_oceanic_like` | bool | available **and** oceanic-like predicate | `:496-504` |
| 53 | `right_opening_crust_type` | int | index into `CRUST_NAMES` | `:505-506` |
| 54 | `right_opening_lithology` | int | index into `LITHOLOGY_NAMES` | `:507-508` |
| 55 | `right_opening_crust_age_ma` | float | remapped pre-process age | `:509-510` |
| 56 | `right_opening_crust_thickness_km` | float | remapped pre-process thickness | `:511-514` |
| 57 | `right_opening_crust_density_g_cm3` | float | remapped pre-process density | `:515-518` |
| 58 | `right_opening_crust_state_available` | bool | `!(age == 0 && thickness == 0)` | `:519-522` |
| 59 | `right_opening_oceanic_like` | bool | available **and** oceanic-like predicate | `:523-531` |
| 60 | `polarity_candidate_status` | string | one of the six ordered statuses | `:532-559` |
| 61 | `candidate_subducting_side` | string | `left` \| `right` \| `none` | `:560-571` |
| 62 | `candidate_overriding_side` | string | `left` \| `right` \| `none` | `:560-571` |
| 63 | `physical_polarity_status` | string | `unknown_unresolved` \| `not_applicable_no_active_convergence` | `:574-583` |
| 64 | `physical_polarity_source` | string | always `none` | `:572` |
| 65 | `physical_subducting_side` | string | `unknown` (active) \| `none` (inactive) | `:574-583` |
| 66 | `physical_overriding_side` | string | `unknown` (active) \| `none` (inactive) | `:574-583` |
| 67 | `physical_polarity_confidence` | float | always exact `0.0` | `:573` |

The in-memory record is `struct PlateBoundarySegment` at `cpp/src/engine/types/earth_system.hpp:463-517`; the field order there matches the serialized order, with the five `Vec3` members expanded into `_x/_y/_z` triples at serialization time.

Field-set partitions used by the replay: 12 integer fields, 42 float fields, 5 boolean fields, 8 string fields (`src/magic_geo/plate_boundary_edge_validation.py:35-121`).

---

## The `plate_boundary_segment_model` contract object

The top-level `plate_boundary_segment_model` key (emitted at `cpp/src/engine/world_serialization.cpp:166-167`, built by `plate_boundary_segment_model_json` at `cpp/src/engine/process_serialization.cpp:2945-3150`) is a **100-key** self-describing contract. The Python replay requires an exact set match — `set(model) == MODEL_FIELDS` — and pins the value of every string and boolean key literally (`src/magic_geo/plate_boundary_edge_validation.py:991-1000`, constants at `:126-335`).

### Identity, layout, and ordering keys (11 strings)

| Key | Fixed value |
| --- | --- |
| `model_type` | `exact_directed_reciprocal_control_volume_boundary_segments_v2` |
| `ledger_location` | `plate_motion_history[].boundary_segments` |
| `record_layout` | `flat_record_array_v2` |
| `canonical_side_rule` | `lower_cell_id_is_left_side` |
| `canonical_direction_rule` | `left_cell_counter_clockwise_control_volume_edge_start_to_end` |
| `record_order` | `left_cell_id_then_left_edge_index_filtered_to_cross_plate_segments` |
| `segment_selection` | `one_record_per_cross_plate_reciprocal_control_volume_segment` |
| `mesh_segment_id_semantics` | `stable_index_over_all_reciprocal_mesh_segments_in_left_cell_id_then_left_edge_index_order` |
| `segment_id_semantics` | `zero_based_contiguous_index_within_each_steps_cross_plate_ledger` |
| `geometry_source` | `canonical_spherical_control_volume_vertices_and_reciprocal_edge_neighbor_ids` |
| `segment_curve` | `shorter_great_circle_arc` |

### Unit keys (8 strings)

| Key | Fixed value |
| --- | --- |
| `position_unit` | `unit_sphere_cartesian` |
| `angular_length_unit` | `rad` |
| `length_unit` | `km` |
| `velocity_unit` | `km_per_Ma_nominal` |
| `intrinsic_kinematic_index_unit` | `unit_sphere_tangent_velocity_per_intrinsic_angular_speed_unit` |
| `opening_crust_age_unit` | `Ma` |
| `opening_crust_thickness_unit` | `km` |
| `opening_crust_density_unit` | `g_cm3` |

### Numeric tolerance, cap, and scale keys (8 floats + 2 caps)

| Key | Type | Value | Replay assertion |
| --- | --- | --- | --- |
| `reciprocal_endpoint_match_tolerance_chord` | float | `1.0e-10` | exact equality (`plate_boundary_edge_validation.py:1017-1024`) |
| `euler_axis_unit_tolerance` | float | `1.0e-12` | exact equality (`:1033-1040`) |
| `unit_sphere_vector_norm_tolerance` | float | `3.0e-12` | exact equality (`:1041-1048`) |
| `direct_boundary_class_inactive_threshold` | float | `0.08` | exact equality (`:1025-1032`) |
| `radius_km` | float | mirrors `planet_parameters.radius_km` | exact equality (`:1196-1199`) |
| `reference_motion_scale_deg_per_reference_step` | float | mirrors `plate_kinematic_model` | exact equality (`:1200-1203`) |
| `reference_timestep_ma` | float | `5.0` | exact equality, and must equal `MATURATION_REFERENCE_TIMESTEP_MA` (`:1184-1187`, `:1204-1207`) |
| `nominal_velocity_scale_km_per_ma` | float | derived product | 8-ULP closeness (`:1208-1224`) |
| `maximum_control_volume_segments_per_cell` | int | `64` | exact equality (`:1080-1087`) |
| `maximum_reciprocal_mesh_segment_count_multiplier` | int | `8` | exact equality (`:1088-1095`) |

### Formula and rule keys (32 strings)

`reciprocal_mesh_segment_count_cap_formula`, `operational_cap_semantics`, `nominal_velocity_scale_formula`, `intrinsic_euler_velocity_formula`, `intrinsic_angular_speed_snapshot_semantics`, `intrinsic_angular_speed_top_level_cross_check`, `rotation_axis_snapshot_semantics`, `rotation_axis_top_level_cross_check`, `initial_snapshot_step_rotation_semantics`, `noninitial_step_rotation_formula`, `assignment_center_snapshot_semantics`, `cell_plate_assignment_formula`, `cell_plate_assignment_tie_break`, `cell_plate_ids_semantics`, `boundary_segment_plate_id_semantics`, `initial_center_top_level_cross_check`, `center_transition_formula`, `final_center_top_level_cross_check`, `nominal_euler_velocity_formula`, `relative_velocity_formula`, `signed_opening_rate_formula`, `signed_convergence_rate_formula`, `signed_slip_rate_formula`, `signed_opening_index_formula`, `signed_convergence_index_formula`, `signed_slip_index_formula`, `direct_convergent_strength_formula`, `direct_divergent_strength_formula`, `direct_transform_strength_formula`, `direct_boundary_class_rule`, `direct_boundary_class_tie_break`, `polarity_convergence_applicability_rule`. Exact values are at `cpp/src/engine/process_serialization.cpp:3010-3094` and are pinned verbatim in `MODEL_STRING_VALUES` (`src/magic_geo/plate_boundary_edge_validation.py:126-286`).

The key groups above sum to the advertised 100: 11 + 8 + 10 + 32 + 12 + 5 + 4 + 17 + 1 (`model_limitation`).

Five of these deserve emphasis because they describe the *root operand chain* the replay must reproduce:

| Key | Value | Why it matters |
| --- | --- | --- |
| `cell_plate_assignment_formula` | `argmax_dot_cell_position_3d_and_same_step_plate_snapshot_center` | plate ids are derived, not stored independently |
| `cell_plate_assignment_tie_break` | `plate_id_ascending_with_strict_greater_than_update_exact_tie_keeps_lowest_plate_id` | makes the argmax deterministic on exact ties |
| `center_transition_formula` | `normalize_rodrigues_rotate_previous_center_about_rotation_axis_by_step_rotation_deg_times_pi_over_180` | the whole center history is reconstructible from step 0 |
| `noninitial_step_rotation_formula` | `intrinsic_angular_speed*reference_motion_scale_deg_per_reference_step*maturation_timestep_scale` | uses the **effective** scale, unlike the velocity scale |
| `initial_snapshot_step_rotation_semantics` | `zero_state_snapshot_rotation_with_nonzero_intrinsic_angular_speed_allowed` | step 0 is a checkpoint, not a transition |

### Opening-crust and polarity keys (11 strings + 1 array)

`opening_crust_state_source`, `opening_crust_state_availability_rule`, `unavailable_opening_crust_sentinel_semantics`, `opening_oceanic_like_predicate`, `opening_oceanic_like_evaluation_scope`, `polarity_candidate_status_order` (a six-element JSON array), `candidate_subducting_side_mapping`, `candidate_overriding_side_mapping`, `candidate_side_semantics`, `physical_polarity_status_rule`, `physical_polarity_source_rule`, `gpgim_supplied_polarity_convention`. Values at `cpp/src/engine/process_serialization.cpp:3095-3118`.

### Precision keys (5 ints)

| Key | Value | Line |
| --- | --- | --- |
| `serialized_float_decimal_significant_digits` | `17` (`max_digits10`) | `:3126-3127` |
| `intrinsic_angular_speed_serialized_significant_digits` | `17` | `:3041-3042` |
| `rotation_axis_serialized_significant_digits` | `17` | `:3043-3044` |
| `assignment_center_serialized_significant_digits` | `17` | `:3047-3048` |
| `top_level_plate_center_serialized_significant_digits` | `17` | `:3063-3064` |

The replay checks all five equal `17` (`src/magic_geo/plate_boundary_edge_validation.py:1062-1079`).

### Aggregate counters (4 ints)

| Key | Definition | Line | Replay check |
| --- | --- | --- | --- |
| `history_step_count` | `history.size()` | `:3119` | equals `len(plate_motion_history)` (`:1049-1053`) |
| `total_boundary_segment_count` | sum of `boundary_segment_count` over all steps (int64) | `:2957`, `:3120-3121` | recomputed from the replayed segments (`:1507-1514`) |
| `maximum_boundary_segment_count` | per-step maximum | `:2958-2961`, `:3122-3123` | recomputed (`:1515-1522`) |
| `reciprocal_mesh_segment_count` | the (invariant) mesh segment total | `:2962-2972`, `:3124-3125` | equals the replay's independently enumerated segment count (`:1054-1061`) |

### Authority and resolution flags (17 booleans)

This is the block that encodes the epistemic contract. Every value is fixed and asserted by the replay (`src/magic_geo/plate_boundary_edge_validation.py:314-332`, `:998-1000`).

| Key | Value | Reading |
| --- | --- | --- |
| `authoritative_for_segment_geometry` | `true` | segment geometry is the authoritative representation |
| `authoritative_for_direct_unsmoothed_kinematics` | `true` | the direct indices/rates/class are authoritative for *that* quantity |
| `reciprocal_segment_identity_resolved` | `true` | the one-to-one edge pairing is resolved |
| `opening_remapped_crust_state_recorded` | `true` | the opening crust witness is recorded |
| `smoothed_cell_boundary_forcing_active` | `true` | a separate smoothed per-cell forcing exists and is active |
| `boundary_segments_drive_smoothed_cell_boundary_forcing` | **`false`** | this ledger does not feed that forcing |
| `nominal_time_calibrated` | **`false`** | |
| `physical_time_resolved` | **`false`** | |
| `physical_plate_velocity_calibrated` | **`false`** | the km/Ma numbers are nominal |
| `physical_polarity_unknown_state_explicit` | `true` | the unknown state is explicit, not implicit |
| `polarity_candidate_is_physical_decision` | **`false`** | |
| `physical_subduction_polarity_resolved` | **`false`** | |
| `physical_slab_geometry_resolved` | **`false`** | |
| `slab_selection_resolved` | **`false`** | |
| `slab_transfer_resolved` | **`false`** | |
| `physical_material_fate_resolved` | **`false`** | |
| `boundary_segments_drive_slab_transfers` | **`false`** | |

Plus one summary string: `model_limitation = "kinematic_candidate_evidence_only_without_physical_polarity_slab_geometry_material_fate_or_feedback_into_smoothed_cell_boundary_forcing"` (`cpp/src/engine/process_serialization.cpp:3146-3147`).

---

## Step-level counters in `plate_motion_history`

Each `plate_motion_history[]` step carries five counters that describe the boundary population: three are control-volume based, one is neighbor-graph based, and one is derived from the smoothed per-cell labels. They are not interchangeable.

| Step field | Basis | Definition | Emitted at | Computed at |
| --- | --- | --- | --- | --- |
| `reciprocal_mesh_segment_count` | control volume | total reciprocal mesh segments, cross-plate and interior alike; invariant across steps | `process_serialization.cpp:3496-3497` | `plate_boundary_segments.cpp:604` |
| `boundary_segment_count` | control volume | `boundary_segments.size()` for this step | `:3498-3499` | `tectonics.cpp:643-645` |
| `control_volume_boundary_incident_cell_count` | control volume | size of the set of distinct `left_cell_id`/`right_cell_id` values over this step's records | `:3500-3501` | `tectonics.cpp:654-661` |
| `plate_boundary_edge_count` | **neighbor graph** | count of `cells[i].neighbors` pairs with `neighbor > i` and different plate ids | `:3495` | `tectonics.cpp:883-887` |
| `plate_boundary_cell_count` | **smoothed labels** | count of cells whose smoothed `boundary_type != 0` | `:3494` | `tectonics.cpp:838-840` |

`plate_boundary_edge_count` counts unordered adjacency-graph edges, so it collapses duplicate boundary arcs; `boundary_segment_count` does not. `plate_boundary_cell_count` is derived from the *smoothed* per-cell classification and has no direct relationship to the ledger at all. The Python replay recomputes `reciprocal_mesh_segment_count`, `boundary_segment_count`, and `control_volume_boundary_incident_cell_count` from first principles and requires exact equality (`src/magic_geo/plate_boundary_edge_validation.py:1440-1470`); it does not read the other two.

---

## Where the ledger is built and who consumes it

### Two call sites

| Call site | Purpose | Transport plan supplied | Serialized? |
| --- | --- | --- | --- |
| `cpp/src/engine/tectonics.cpp:398-408`, inside `derive_crust_and_topography` | build a **provisional** segment set purely so the initial oceanic-crust age field can find ridges before ages exist | `build_identity_crust_transport_plan(cells)` over the provisional crust state, with `cell.crust_age_ma` deliberately set to `0.0` first (`tectonics.cpp:390-397`) | **no** — discarded after age construction |
| `cpp/src/engine/tectonics.cpp:636-645`, inside `summarize_plate_motion_step` | the ledger for the step | `step.transport_plan` — the identity plan at step 0, the forward-overlap plan afterwards | **yes**, as `plate_motion_history[].boundary_segments` |

The provisional call is why the initial-age model declares `provisional_age_for_oceanic_predicate_ma = 0.0` and `provisional_crust_state_source = "initial_identity_overlap_categories_thickness_density_with_age_zero"` (`cpp/src/engine/process_serialization.cpp:2431-2435`). Because thickness is positive at that point, every provisional side is `available`; the zero age only affects the `volcanic_arc` branch of the oceanic-like predicate (which it satisfies trivially).

At step 0 the transport plan is the identity plan, whose remapped arrays are copies of the current cell state (`cpp/src/engine/crust_transport.cpp:1470-1474`), so step 0's opening crust witnesses equal the initial crust state exactly.

### Consumer 1 — initial oceanic crust age ridge seeding

`build_initial_oceanic_crust_age_field` consumes the provisional segments (`cpp/src/engine/initial_oceanic_age.cpp:105-140`). Its eligibility rule, declared as `eligible_ridge_segment_rule = "direct_divergent_segment_with_both_provisional_opening_sides_oceanic_like_positive_finite_nominal_opening_rate_and_positive_finite_length"` (`cpp/src/engine/process_serialization.cpp:2437-2438`):

| Requirement | Field read | Line |
| --- | --- | --- |
| class is divergent | `direct_boundary_class == "divergent"` | `initial_oceanic_age.cpp:107-113` |
| both sides oceanic-like | `left_opening_oceanic_like && right_opening_oceanic_like` | `:108-112` |
| finite positive length | `length_km` | `:114-125` |
| finite nonnegative opening rate | `signed_opening_rate_km_per_ma >= 0` (negative throws) | `:114-125` |
| **strictly positive** rate to seed | `signed_opening_rate_km_per_ma != 0.0` — zero-rate divergent segments are skipped as "not an active spreading ridge" | `:128-134` |

Eligible segments contribute `segment_id` to `eligible_ridge_segment_ids`, `signed_opening_rate_km_per_ma * length_km` to a length-weighted sum, `length_km` to the total, and both endpoint cells to the sorted-unique `ridge_seed_cell_ids` (`:135-153`). The single representative full spreading rate is the length-weighted mean (`:155-159`), halved into `representative_half_spreading_rate_km_per_ma` (`:161-162`). Ridge seeding is the **only** production consumer of `direct_boundary_class` and `signed_opening_rate_km_per_ma`.

### Consumer 2 — the crust overlap candidate-fate crosswalk

`build_crust_overlap_candidate_fate_ledger` reads the same-step segments (`cpp/src/engine/crust_overlap_candidate_fate.cpp:376-476`). It:

- caps input at `8 * cell_count` segments — a second, independent copy of the same resource guard (`:8`, `:392-399`);
- re-validates segment identity (`segment_id == index`, distinct in-range cells, distinct in-range plates) (`:442-457`);
- groups every segment by the **sorted unordered plate pair** `(min(left,right), max(left,right))` (`:458-473`);
- consumes the physical tuple, requiring the inactive tuple to be exactly `(not_applicable_no_active_convergence, none, none, none, 0.0)` and counting active-unknown segments (`:160-224`);
- consumes the heuristic tuple, requiring the inactive tuple to be exactly `(no_active_convergence, none, none)` and merging unique-oceanic candidate roles into a pair-level consensus (`:225-299`);
- finalizes each pair into consensus statuses: not-all-active, all-unknown, mixed, conflict, or uniform (`:300-343`).

Because every convergent segment reports `unknown_unresolved` today, the physical consensus for any all-active pair is always `PHYSICAL_ALL_UNKNOWN`, serialized as `"all_active_all_physical_polarities_unknown"` (`cpp/src/engine/crust_overlap_candidate_fate.cpp:12-13`). The crosswalk is pair-wide only; the candidate-fate model itself keeps `local_segment_link_resolved`, `local_fragment_topology_resolved`, `swept_area_calculated`, and both mutation flags false (`src/magic_geo/crust_overlap_candidate_fate_validation.py:596-601`). See [Crust Transport and Forward Overlap](./crust-transport-and-overlap.md).

### Non-consumers

Nothing else reads `boundary_segments`. In particular there is no path from a segment to a crust rule, an elevation change, a slab, a reservoir transfer, or the material shadow.

---

## The smoothed cell forcing that does not consume this ledger

The tectonic rules — crust type/lithology assignment, ridge/rift/orogen/trench relief, aging and rejuvenation — are driven by the per-cell scalars `boundary_convergent`, `boundary_divergent`, `boundary_transform`, and `boundary_type`, produced by `classify_boundaries` (`cpp/src/engine/tectonics.cpp:126-202`). That function is a **different algorithm on a different graph**, and it never touches `PlateBoundarySegment`.

| Aspect | Segment ledger | `classify_boundaries` smoothed forcing |
| --- | --- | --- |
| Graph | control-volume reciprocal edges, duplicates preserved | `cells[i].neighbors` adjacency, one contribution per unordered pair (`tectonics.cpp:130-133`) |
| Evaluation point | segment midpoint `normalize(start + end)` | cell-pair midpoint `normalize(cells[i].p + cells[j].p)` (`:136`) |
| Transverse direction | `cross(tangent, midpoint)` from the CCW edge | `normalize(delta - midpoint * dot(delta, midpoint))` where `delta = cells[j].p - cells[i].p` (`:137-138`) |
| Tangent | `cross(edge_plane_normal, midpoint)` | `cross(midpoint, across)` (`:139`) |
| Strength coefficients | `1.25`, `1.25`, `(0.35, 1.05)` | identical `1.25`, `1.25`, `(0.35, 1.05)` (`:143-145`) |
| Accumulation | none — per segment | summed into **both** incident cells (`:146-151`) |
| Normalization | none | divided by `max(1, neighbor count)` then multiplied by `3.2` and clamped (`:154-159`) |
| Smoothing | none | `boundary_smoothing_steps` diffusion passes, self-weights `0.58 / 0.58 / 0.62` (`:160-183`); default 5 steps (`src/magic_geo/config.py:293-298`) |
| Class rule | 3-way arg-max with `0.08` floor | 5-way including a `mixed` class when `convergent == max && divergent > 0.45 * max` (`:189-200`) |
| Serialized as | `boundary_segments[]` | `cells[].boundary_convergent/_divergent/_transform/_type`, and per-step `boundary_*_by_cell` arrays |

So the same coefficients appear in both, but the graph, the geometry, the degree normalization, the smoothing, and the class vocabulary all differ. The two are **not** consistent by construction and the codebase does not claim they are.

The document states the split in three places: `boundary_segments_drive_smoothed_cell_boundary_forcing = false` alongside `smoothed_cell_boundary_forcing_active = true` (`cpp/src/engine/process_serialization.cpp:3132-3134`); the README's "the degree-normalized smoothed cell forcing drives the tectonic rules and does not consume it" (`cpp/src/engine/README.md:210-213`); and the binding invariant "the ledger must not be described as driving smoothed cell forcing or slab transfers until those consumers are implemented and independently validated" (`cpp/src/engine/README.md:334-338`).

---

## Strict Python replay

`validate_plate_boundary_edges(world)` in `src/magic_geo/plate_boundary_edge_validation.py:1099-1549` is an independent reimplementation. It returns `{"passed": bool, "failures": [str], "metrics": {...}}` and is invoked from three places:

| Caller | Check / effect |
| --- | --- |
| `src/magic_geo/geo_validation_physics.py:2507-2536` | the `tectonics` domain check `exact_directed_plate_boundary_segment_replay` inside `validate-geo` |
| `src/magic_geo/crust_overlap_candidate_fate_validation.py:606-620` | a hard prerequisite: the candidate-fate crosswalk replay refuses to proceed unless this root replay passes |
| `src/magic_geo/cli/commands/validate.py:6056-6062` | the full-world `validate` command, prefixing failures with `plate boundary segment replay invalid:` |

### What it reconstructs, in order

| Stage | What is rebuilt | Lines |
| --- | --- | --- |
| 1 | Cell rings from `cells[].position_3d`, `control_volume_vertices_3d`, `control_volume_edge_neighbor_ids`; unit-length and 3-to-64 ring checks; running `16 * cell_count` local-edge cap | `:494-555` |
| 2 | The full reciprocal mesh segment enumeration, independently, with its own reverse-endpoint tolerance `1.0e-10`, exactly-one-candidate requirement, no-double-match set, and the closing identity `len(matched_edges) == total local edges` and `2 * len(segments) == total local edges` | `:558-622` |
| 3 | The `plate_boundary_segment_model` contract, field-set exact, every string/bool pinned, every tolerance and cap exact | `:983-1096` |
| 4 | `radius_km` from `planet_parameters`; `reference_motion_scale_deg_per_reference_step`, `reference_timestep_ma`, `maturation_timestep_scale`, `effective_motion_scale_deg_per_step` from `plate_kinematic_model`; checks `effective == reference * scale` to 4 ULP and `reference_timestep_ma == 5.0` | `:1145-1187` |
| 5 | `nominal_velocity_scale_km_per_ma` recomputed and compared to 8 ULP | `:1208-1224` |
| 6 | Top-level `plates[]`: unit axes, nonnegative speeds, unit `initial_center` and `center` | `:1226-1265` |
| 7 | Per step: snapshot axis/speed must equal the top-level values **exactly** (`==`, not approximately); `step_rotation_deg == 0` at step 0 else `speed * effective_motion_scale` to 4 ULP; the center by exact equality at step 0 and by Rodrigues rotation of the previous center thereafter | `:1318-1395` |
| 8 | `cell_plate_ids` re-derived by argmax of `dot(cell position, plate center)` with strict-greater update (lowest plate id wins exact ties); requires no empty plate domain and matching per-plate snapshot cell counts | `:1397-1420` |
| 9 | Opening crust arrays from `crust_overlap_ledger.remapped_*_by_cell`, with the canonical-unavailable-or-valid-available disjunction enforced per cell | `:641-705` |
| 10 | The expected cross-plate segment list, filtered from the independently enumerated mesh segments by the replayed plate ids, and its length compared to `len(records)` | `:1426-1439` |
| 11 | Step counters `reciprocal_mesh_segment_count`, `boundary_segment_count`, `control_volume_boundary_incident_cell_count` | `:1440-1470` |
| 12 | Every record, field by field, via `_expected_record` + `_compare_record` | `:724-980`, `:1471-1496` |
| 13 | Final plate centers equal the top-level `plates[].center`; model totals `total_boundary_segment_count` and `maximum_boundary_segment_count` recomputed | `:1502-1522` |

### Comparison tolerances

| Field class | Rule | Line |
| --- | --- | --- |
| Integers | exact equality, and `type(value) is int` (rejects `bool`) | `:358-361`, `:929-931` |
| Booleans | `type(value) is bool` and identity comparison | `:932-939` |
| Strings | membership in the allowed vocabulary **and** equality to the replayed value | `:940-964` |
| Floats (general) | `abs(actual - expected) <= max(2.0e-12 * scale, 256 * eps * ops * (1 + sum of abs operands))` | `:448-463` |
| `physical_polarity_confidence` | **exact** `== 0.0` | `:970-974` |
| Plate axes / speeds vs top level | **exact** `==` | `:1346-1353` |
| Step rotation, effective motion scale | 4 ULP | `:1177-1183`, `:1361-1368` |
| Nominal velocity scale | 8 ULP | `:1214-1224` |
| Step-0 center | **exact** `==`; later steps componentwise `_close` | `:1378-1386` |

### What it deliberately ignores

The docstring is explicit: "The replay deliberately does not read per-cell `boundary_convergent`, `boundary_divergent`, `boundary_transform`, or `boundary_type`. It reconstructs direct segment kinematics from authoritative mesh rings, plate-assignment snapshots, Euler axes/speeds, and opening crust state" (`src/magic_geo/plate_boundary_edge_validation.py:1100-1106`).

| Deliberately ignored | Why |
| --- | --- |
| `cells[].boundary_convergent` / `_divergent` / `_transform` / `_type` | these are the *smoothed* forcing; reading them would make the replay circular and would silently import the smoothing model |
| `plate_motion_history[].boundary_convergent_by_cell` and siblings | same reason |
| `plate_motion_history[].plate_boundary_edge_count` / `plate_boundary_cell_count` | neighbor-graph and smoothed-label counters, outside this ledger's scope |
| Physical polarity beyond the two allowed statuses | the vocabulary is closed at `{not_applicable_no_active_convergence, unknown_unresolved}`; a "resolved" value fails |
| Any slab, swept-area, or material-fate claim | the ledger asserts none, so the replay checks none |

The wrapping check's `expected` map carries the negative assertions as first-class expectations: `smoothed_cell_boundary_fields_used: False`, `subduction_polarity_resolved: False`, `subducted_slab_geometry_resolved: False` (`src/magic_geo/geo_validation_physics.py:2531-2533`).

### Metrics returned

| Metric | Meaning |
| --- | --- |
| `authoritative_reciprocal_control_volume_geometry_replayed` | true only on full success |
| `direct_unsmoothed_euler_kinematics_replayed` | true only on full success |
| `opening_crust_state_and_polarity_candidate_replayed` | true only on full success |
| `explicit_unknown_physical_polarity_replayed` | true only on full success |
| `top_level_euler_parameters_cross_checked` | axes/speeds mirrored between snapshots and `plates[]` |
| `step_rotations_replayed` | per-step rotation reproduced from speed and timestep scale |
| `plate_center_history_replayed` | full Rodrigues center chain reproduced |
| `cell_plate_assignments_replayed` | every `cell_plate_ids` entry reproduced by nearest-center argmax |
| `smoothed_cell_boundary_fields_used` | permanently `False` |
| `subduction_polarity_resolved` | permanently `False` |
| `subducted_slab_geometry_resolved` | permanently `False` |
| `cell_count`, `history_step_count`, `mesh_reciprocal_segment_count` | scale |
| `duplicate_neighbor_pair_segment_count` | how many segments exceed one per neighbor pair |
| `total_boundary_segment_count`, `maximum_boundary_segment_count_per_step` | population |
| `maximum_record_replay_residual` | largest absolute float discrepancy over all records |
| `direct_boundary_class_counts` | sorted histogram over the four classes |
| `polarity_candidate_status_counts` | sorted histogram over the six candidate statuses |
| `physical_polarity_status_counts` | sorted histogram over the two physical statuses |

Because the replay reads `world["cells"]`, it requires `output.include_cells: true`. With cells stripped it fails with `cells must be nonempty` rather than passing vacuously.

---

## Worked examples

All values below are asserted in `cpp/tests/plate_boundary_segments_test.cpp` against the polar two-cell, three-segment fixture with `radius_km = 6371.0` and `plate_motion_scale_deg_per_step = 2.0`.

### Example 1 — pure opening

Left plate stationary (`axis = (1,0,0)`, `speed = 0`); right plate rotating about the segment tangent `(-sqrt(3)/2, 1/2, 0)` at speed `0.6`:

| Field | Value | Line |
| --- | --- | --- |
| `midpoint_unit` | `(1/2, sqrt(3)/2, 0)` | `:301` |
| `signed_opening_index` | `+0.6` | `:302` |
| `signed_convergence_index` | `-0.6` | `:303` |
| `signed_slip_index` | `0.0` | `:304` |
| `direct_divergent_strength` | `clamp(0.6 * 1.25) = 0.75` | derived from `:458-460` |
| `direct_boundary_class` | `divergent` | `:305` |
| `convergence_active` | `false` | `:306` |
| `polarity_candidate_status` | `no_active_convergence` | `:307` |

### Example 2 — pure convergence

Same, with the right plate's axis negated:

| Field | Value | Line |
| --- | --- | --- |
| `signed_opening_index` | `-0.6` | `:314` |
| `signed_convergence_index` | `+0.6` | `:315` |
| `direct_convergent_strength` | `clamp(0.6 * 1.25) = 0.75` | derived |
| `direct_boundary_class` | `convergent` | `:317` |
| `convergence_active` | `true` | `:318` |

### Example 3 — oblique transform with real convergence

Right plate angular velocity `(0.4 * sqrt(3)/2, -0.2, 0.8)`:

| Field | Value | Line |
| --- | --- | --- |
| `signed_convergence_index` | `0.4` | `:331` |
| `signed_slip_index` | `0.8` | `:332` |
| `direct_convergent_strength` | `clamp(0.4 * 1.25) = 0.5` | derived |
| `direct_transform_strength` | `clamp((0.8 - 0.4 * 0.35) * 1.05) = clamp(0.693) = 0.693` | derived |
| `direct_boundary_class` | `transform` (`0.693 > 0.5`) | `:333` |
| `convergence_active` | `true` (`0.5 >= 0.08`) | `:334` |
| `polarity_candidate_status` | `left_oceanic_only` | `:335` |
| `candidate_subducting_side` / `candidate_overriding_side` | `left` / `right` | `:336-337` |
| `physical_polarity_status` | `unknown_unresolved` | `:338` |
| `physical_subducting_side` / `physical_overriding_side` | `unknown` / `unknown` | `:339-340` |

This is the case the `polarity_convergence_applicability_rule` exists for: the winning class is `transform`, yet the segment is still a polarity candidate.

### Example 4 — pure strike-slip

Right plate axis `(0,0,1)`, speed `0.6`:

| Field | Value | Line |
| --- | --- | --- |
| `signed_opening_index` | `0.0` | `:348` |
| `signed_convergence_index` | `0.0` | `:349` |
| `signed_slip_index` | `0.6` | `:350` |
| `direct_boundary_class` | `transform` | `:351` |
| `convergence_active` | `false` | `:352` |
| `polarity_candidate_status` | `no_active_convergence` | `:353` |

### Example 5 — the unavailable-state sentinel

Setting the right cell's remapped age and thickness both to `0.0` while keeping type/lithology/density (`cpp/tests/plate_boundary_segments_test.cpp:692-712`):

| Field | Value |
| --- | --- |
| `left_opening_crust_state_available` | `true` |
| `right_opening_crust_state_available` | `false` |
| `right_opening_oceanic_like` | `false` |
| `polarity_candidate_status` (on the convergent segment) | `unresolved_missing_opening_crust_state` |
| `candidate_subducting_side` / `candidate_overriding_side` | `none` / `none` |

Setting thickness to `0.0` while leaving a nonzero age instead **throws** (`:714-718`) — a partial state is never representable.

### Example 6 — one segment's opening-crust fixture

`opening_crust()` (`cpp/tests/plate_boundary_segments_test.cpp:100-108`) supplies:

| Cell | type | lithology | age (Ma) | thickness (km) | density (g/cm3) | available | oceanic-like |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 (left) | `0` = `oceanic` | `0` = `basalt` | `20.0` | `7.0` | `3.00` | yes | **yes** (type 0) |
| 1 (right) | `1` = `continental` | `1` = `granite` | `1200.0` | `35.0` | `2.72` | yes | no (type 1) |

Hence `left_oceanic_only` on every convergent segment (`:237-250`).

---

## Reproducing and inspecting the ledger

### Generate a world with cells

```bash
magic-geo generate \
  --config magic-geo.yaml \
  --output runs/world.json \
  --cells 4096 \
  --geo-only
```

`--geo-only` keeps every geological ledger, including `plate_motion_history` and `plate_boundary_segment_model`, and only strips civilization layers. `output.include_cells` must be true — the geo-only path raises `ValueError` otherwise, and the boundary replay needs `cells[].control_volume_vertices_3d`.

### Run the replay directly

```python
import json
from magic_geo.plate_boundary_edge_validation import validate_plate_boundary_edges

with open("runs/world.json", encoding="utf-8") as handle:
    world = json.load(handle)

result = validate_plate_boundary_edges(world)
print(result["passed"])
print(result["metrics"]["duplicate_neighbor_pair_segment_count"])
print(result["metrics"]["direct_boundary_class_counts"])
print(result["metrics"]["polarity_candidate_status_counts"])
print(result["metrics"]["physical_polarity_status_counts"])
print(result["metrics"]["maximum_record_replay_residual"])
for failure in result["failures"]:
    print(failure)
```

### Run it as part of geo validation

```bash
magic-geo validate-geo --world runs/world.json --profile earthlike --output runs/geo-validation.json
```

The relevant record is the check named `exact_directed_plate_boundary_segment_replay` in domain `tectonics`.

```bash
python - <<'PY'
import json
report = json.load(open("runs/geo-validation.json", encoding="utf-8"))
check = next(
    item for item in report["checks"]
    if item["name"] == "exact_directed_plate_boundary_segment_replay"
)
print(check["status"], check["severity"])
print(json.dumps(check["expected"], indent=2))
PY
```

### Inspect the ledger by hand

```python
import json

world = json.load(open("runs/world.json", encoding="utf-8"))
model = world["plate_boundary_segment_model"]
print(model["model_type"])
print(model["reciprocal_mesh_segment_count"], model["total_boundary_segment_count"])
print(model["nominal_velocity_scale_km_per_ma"], model["reference_timestep_ma"])

step = world["plate_motion_history"][-1]
print(step["boundary_segment_count"], step["control_volume_boundary_incident_cell_count"])

candidates = [
    segment for segment in step["boundary_segments"]
    if segment["candidate_subducting_side"] != "none"
]
print(len(candidates), "candidate pairs")
print({segment["physical_polarity_status"] for segment in candidates})
print({segment["physical_subducting_side"] for segment in candidates})
print({segment["physical_polarity_confidence"] for segment in candidates})
```

The last three lines will print `{'unknown_unresolved'}`, `{'unknown'}`, and `{0.0}` for every candidate. That is the intended, permanent result of the current model.

### Run the native unit test

```bash
cmake -S . -B build
cmake --build build --target magic_geo_plate_boundary_segments_test
ctest --test-dir build -R magic_geo_plate_boundary_segments --output-on-failure
```

### Disambiguation: `boundary_geometry.py` is unrelated

`src/magic_geo/boundary_geometry.py` is a Python enricher that builds `watershed_boundary_segments` (and, in full-world mode, `territorial_boundary_segments`) from `cell_adjacency_edges`. Despite the similar name it has nothing to do with plate boundaries: it keys on `basin_id`/`political_region_id`, works on the neighbor-adjacency edge list, and rounds every emitted value to 6 decimals (`src/magic_geo/boundary_geometry.py:7-8`, `:41-99`, `:152-196`). The geo-only path runs only `enrich_world_with_physical_boundary_geometry`, which builds the watershed segments alone (`:261-272`). Do not confuse `watershed_boundary_segments` with `plate_motion_history[].boundary_segments`.

---

## Limitations and unresolved claims

These are the codebase's own positions, not this page's editorial hedging. Where the source states a flag or a phrase, it is quoted or cited.

### Physical subduction polarity is unresolved, by construction

- Every actively converging segment reports `physical_polarity_status = "unknown_unresolved"`, `physical_subducting_side = "unknown"`, `physical_overriding_side = "unknown"`, `physical_polarity_source = "none"`, and `physical_polarity_confidence = 0.0` (`cpp/src/engine/plate_boundary_segments.cpp:572-583`).
- `physical_subduction_polarity_resolved = false` and `polarity_candidate_is_physical_decision = false` in the model (`cpp/src/engine/process_serialization.cpp:3139-3140`).
- The candidate pair is a **heuristic** — sole-oceanic-side-subducts — declared as such (`candidate_side_semantics`, `:3111-3112`). It is not evidence of polarity and must not be relabelled as one. Four of the six candidate statuses produce `none/none` and carry no candidate at all.
- The GPGIM convention key documents how a *supplied* polarity would have to be aligned before use; nothing supplies one today (`:3117-3118`; `cpp/src/engine/README.md:216-219`).

### Slab selection, geometry, transfer, and material fate are unresolved

- `physical_slab_geometry_resolved`, `slab_selection_resolved`, `slab_transfer_resolved`, `physical_material_fate_resolved`, and `boundary_segments_drive_slab_transfers` are all `false` (`cpp/src/engine/process_serialization.cpp:3141-3145`).
- The type comment: convergent segments "cannot select a slab" (`cpp/src/engine/types/earth_system.hpp:511-512`).
- Downstream, the crust dry-rock accounting keeps plate-owned slab packet tables **empty** and every transfer's `physical_basis_resolved` false (`cpp/src/engine/README.md:317-320`). Nothing in this ledger changes that.

### The smoothed cell forcing does not consume this ledger

- `boundary_segments_drive_smoothed_cell_boundary_forcing = false` while `smoothed_cell_boundary_forcing_active = true` (`cpp/src/engine/process_serialization.cpp:3132-3134`).
- The tectonic rules read the neighbor-graph, degree-normalized, diffusion-smoothed per-cell scalars from `classify_boundaries` (`cpp/src/engine/tectonics.cpp:126-202`), not the segments. The two models share coefficients but not graph, normalization, smoothing, or class vocabulary.
- The invariant is binding: the ledger "must not be described as driving smoothed cell forcing or slab transfers until those consumers are implemented and independently validated" (`cpp/src/engine/README.md:334-338`).
- Practical consequence: a segment classified `convergent` here does **not** imply the incident cells were classified convergent by the forcing that actually shaped their crust and relief, and vice versa.

### The km/Ma numbers are nominal, not calibrated

- `physical_plate_velocity_calibrated = false`, `nominal_time_calibrated = false`, `physical_time_resolved = false` (`cpp/src/engine/process_serialization.cpp:3135-3137`); `velocity_unit = "km_per_Ma_nominal"` (`:2999`).
- The scale is built from a procedural angular-speed *index*, a configured degree-per-reference-step displacement *scale*, and a fixed 5 Ma nominal reference interval (`cpp/src/engine/plate_boundary_segments.cpp:199-201`).
- It does **not** track `maturation_timestep_ma`. Refining the timestep changes the realised per-step rotation but leaves every serialized velocity and rate untouched.
- `km/Ma` is numerically equal to `mm/yr` (`cpp/tests/plate_boundary_segments_test.cpp:609-615`). Reading the numbers against published plate velocities is a unit convenience, not a validation.

### Opening crust is a same-step witness, not a mass or provenance claim

- The values are the remapped **pre-process** state from the same step's transport plan (`opening_crust_state_source`, `cpp/src/engine/process_serialization.cpp:3095-3096`). They describe what the destination cell held at the opening of the rules, not what crossed the boundary.
- The unavailable sentinel is a *fixed-shape* marker: retained category and density are explicitly "not material state" (`:3099-3100`). Treating a sentinel's `crust_type` or `density` as physical will be wrong.
- Nothing here asserts dry-rock mass, solid volume, phase, porosity, compaction, grain provenance, or mass-weighted age; those flags stay false across the crust material shadow and reservoir models (`cpp/src/engine/README.md:271-273`, `:317-324`).

### Scope boundaries the ledger does not cross

| Not claimed | Where the negation lives |
| --- | --- |
| Segment-level material transfer or swept area | candidate-fate model keeps `swept_area_calculated` false (`crust_overlap_candidate_fate_validation.py:599`) |
| A link from a segment to a specific overlap fragment | `local_segment_link_resolved` false (`:596`) |
| Connected-fragment topology of the overlap classes | `connected_fragment_topology_resolved` false; coalescing is by sorted membership only (`cpp/src/engine/README.md:281-285`) |
| Cross-step tracking of a physical boundary | `mesh_segment_id` is stable for a fixed mesh, but no schema field asserts continuity of a *plate* boundary through time |
| A `mixed` boundary class | the segment vocabulary is exactly four values; only the smoothed per-cell classifier emits `mixed` (`cpp/src/engine/tectonics.cpp:192-193`) |

### Caps are guards, not physics

64 control-volume segments per cell and 8 reciprocal mesh segments per cell are declared `nonphysical_fail_closed_resource_and_malformed_geometry_guards` (`cpp/src/engine/process_serialization.cpp:3012-3013`). Do not read them as statements about achievable boundary complexity, and do not treat hitting one as a physical result — it is a refusal to proceed on malformed or adversarial geometry.

### Replay proves reproducibility, not realism

`exact_directed_plate_boundary_segment_replay` passing means the serialized ledger is exactly reconstructible from the mesh, plate snapshots, Euler parameters, and opening crust state. It says nothing about whether the resulting boundary population resembles Earth's. That is the same separation the geo layer-contract audit makes when it hardcodes `"empirical_realism_proven": False` for every layer.

### Accelerator parity remains false

Production crust transport — which supplies the opening crust arrays the ledger witnesses — is CPU-authoritative; the OpenCL/CUDA continuous-moment shadow is a discarded-output parity harness, and "Complete parity stays false" (`cpp/src/engine/README.md:294-303`). `build_plate_boundary_segments` itself has no accelerated path.

---

## See also

- [Tectonics and Plates](./tectonics-and-plates.md) — plate generation, Euler axes and speeds, the smoothed per-cell boundary forcing, and the crust rules that actually consume it
- [Crust Transport and Forward Overlap](./crust-transport-and-overlap.md) — the `CrustTransportPlan` that supplies the opening crust witnesses, the membership-class ledger, and the candidate-fate crosswalk
- [Mesh and Geometry](./mesh-and-geometry.md) — control-volume construction, ring orientation, and the shared-edge reciprocity guarantees this ledger depends on
- [Crust Material Shadow and Dry-Rock Reservoirs](./crust-material-and-reservoirs.md) — the non-authoritative mass shadow and the empty slab tables
- [Topography, Isostasy and Thermal Subsidence](./topography-and-isostasy.md) — the age-depth curve and the tectonic elevation change composition
- [Native Engine (C++ Core)](../08-native-engine.md) — translation-unit responsibilities and the engine invariants
- [World Document Schema](../10-world-schema.md) — where `plate_boundary_segment_model` and `plate_motion_history` sit in the document
- [Serialization and World Formats](../11-serialization.md) — the `roundtrip_num` binary64 round-trip contract used by every float in this ledger
- [Validation](../12-validation.md) — the `validate` and `validate-geo` command surfaces and the replay-validator family
- [Geo Validation Suite](../13-geo-validation-suite.md) — the scenario matrix that exercises this replay across seeds, resolutions, and timesteps
- [Testing and Quality Gates](../18-testing.md) — the `magic_geo_plate_boundary_segments` CTest target and the Python gates
- [Configuration Reference](../05-configuration-reference.md) — `tectonics.plate_motion_scale_deg_per_step`, `tectonics.min/max_angular_speed`, `tectonics.boundary_smoothing_steps`, `erosion.maturation_timestep_ma`
- [Glossary](../21-glossary.md) — reciprocal control-volume segment, opening crust state, candidate polarity, nominal time
