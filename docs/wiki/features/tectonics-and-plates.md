# Tectonics and Plates

[Wiki home](../README.md) > Features

Everything in magic-geo's solid-earth stack starts here: plates are procedurally seeded on the sphere, cells are assigned to plates by nearest rotated Euler-pole center, boundary forcing is derived from relative Euler velocities and smoothed on the mesh graph, and crust state (type, lithology, thickness, density, age) plus initial relief are derived from that forcing. Each maturation iteration rotates the plate centers with a Rodrigues rotation, re-assigns cells, re-classifies boundaries, transports crust, applies an ordered set of thresholded crust-state rules, and appends a fully replayable `plate_motion_history` record. The model is explicitly kinematic and procedural: physical time is uncalibrated, subduction polarity is unresolved, and the initial seafloor age field is a graph travel-time construction with a single global nominal half-rate, not a plate reconstruction.

## On this page

- [Where tectonics runs in the pipeline](#where-tectonics-runs-in-the-pipeline)
- [Plate seeding, plate kinds, and cell assignment](#plate-seeding-plate-kinds-and-cell-assignment)
- [The continental/oceanic split and how the target fraction is met](#the-continentaloceanic-split-and-how-the-target-fraction-is-met)
- [Boundary classification and the smoothing steps](#boundary-classification-and-the-smoothing-steps)
- [Plate motion: Rodrigues rotation of centers with the per-step scale](#plate-motion-rodrigues-rotation-of-centers-with-the-per-step-scale)
- [Initial crust derivation: type, lithology, thickness, density](#initial-crust-derivation-type-lithology-thickness-density)
- [The initial oceanic crust age field](#the-initial-oceanic-crust-age-field)
- [Initial topography derivation](#initial-topography-derivation)
- [Per-step crust evolution: the ordered rule pipeline](#per-step-crust-evolution-the-ordered-rule-pipeline)
- [Tectonic elevation change](#tectonic-elevation-change)
- [The plate motion history record](#the-plate-motion-history-record)
- [Plate aggregation and the `plates[]` entity record](#plate-aggregation-and-the-plates-entity-record)
- [Per-cell tectonic fields in the world document](#per-cell-tectonic-fields-in-the-world-document)
- [Python enrichers: tectonic zones, fault systems, geology realism](#python-enrichers-tectonic-zones-fault-systems-geology-realism)
- [Tectonics configuration reference](#tectonics-configuration-reference)
- [Worked examples](#worked-examples)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

---

## Where tectonics runs in the pipeline

The only complete stage ordering lives in `cpp/src/engine/pipeline.cpp`. Tectonics occupies stages 3–8 of world construction and then re-enters once per maturation iteration.

| Order | Call | Source | Effect |
|---|---|---|---|
| 1 | `build_mesh(params)` | `cpp/src/engine/pipeline.cpp:12` | Sphere mesh, neighbor graph, control volumes |
| 2 | plate-count guard | `cpp/src/engine/pipeline.cpp:13` | throws `plate_count must be smaller than generated mesh cell count` |
| 3 | `generate_plates(params)` | `cpp/src/engine/pipeline.cpp:17`, impl `cpp/src/engine/tectonics.cpp:14` | Euler axes, angular speeds, plate kind, nominal crust density/thickness |
| 4 | `choose_plate_seeds(params, cell_count)` | `cpp/src/engine/pipeline.cpp:18`, impl `cpp/src/engine/tectonics.cpp:41` | Distinct seed cell index per plate |
| 5 | seed → center loop | `cpp/src/engine/pipeline.cpp:24-29` | `plate.initial_center = plate.center = cells[seed].p` |
| 6 | `assign_plates(plate_centers, cells)` | `cpp/src/engine/pipeline.cpp:30`, impl `cpp/src/engine/tectonics.cpp:55` | Nearest-center plate id per cell |
| 7 | `classify_boundaries(params, plates, cells)` | `cpp/src/engine/pipeline.cpp:31`, impl `cpp/src/engine/tectonics.cpp:126` | `boundary_convergent/divergent/transform`, `boundary_type` |
| 8 | `derive_crust_and_topography(...)` | `cpp/src/engine/pipeline.cpp:32-37`, impl `cpp/src/engine/tectonics.cpp:287` | Crust type/lithology/thickness/density/age, initial relief components, initial oceanic age ledger |
| 9 | `build_identity_crust_transport_plan(cells)` | `cpp/src/engine/pipeline.cpp:38-41` | No-motion transport plan for the step-0 checkpoint |
| 10 | initial equilibrium checkpoint capture | `cpp/src/engine/pipeline.cpp:42-68` | Per-cell `crust_equilibrium_elevation_m` and `thermal_subsidence_target_m` snapshots plus the zero-change vectors passed to the step-0 summary |
| 11 | `summarize_plate_motion_step(..., id=0, erosion_iteration=-1, stage="initial_plate_domains", ...)` | `cpp/src/engine/pipeline.cpp:69-89`, impl `cpp/src/engine/tectonics.cpp:587` | First `plate_motion_history` record |
| loop | `advance_plate_motion_and_crust(...)` | `cpp/src/engine/earth_system.cpp:930`, impl `cpp/src/engine/tectonics.cpp:1050` | One motion transition per `erosion.iterations`, appends one history record |
| late | `summarize_plates(params, cells, plates)` | `cpp/src/engine/pipeline.cpp:186`, impl `cpp/src/engine/tectonics.cpp:1828` | Per-plate aggregates for the `plates[]` entity array |

Inside the maturation loop the plate-motion transition is the first *state-mutating* operation of each iteration — only the read-only `capture_feedback_reference(cells)` snapshot precedes it (`cpp/src/engine/earth_system.cpp:928-930`); the returned `tectonic_elevation_change` vector is folded into the combined sediment-interface commit later in the same iteration (`cpp/src/engine/earth_system.cpp:971` and `cpp/src/engine/earth_system.cpp:1072`), never applied to `elevation_m` directly.

---

## Plate seeding, plate kinds, and cell assignment

### `generate_plates` — `cpp/src/engine/tectonics.cpp:14`

A dedicated `std::mt19937_64` is seeded with `params.seed ^ 0xC0FFEEULL` (`cpp/src/engine/tectonics.cpp:15`). For each plate index `i` in `[0, plate_count)` exactly **four** uniform draws are consumed, in this order: the kind draw (`:21`), the two `uni(rng)` calls inside `random_unit_vector` (`cpp/src/engine/tectonics.cpp:6-12`, invoked at `:30`), and the angular-speed draw (`:31-32`). RNG consumption order is a stated engine invariant and must not be reordered (`cpp/src/engine/README.md:339`).

| Quantity | Rule | Source |
|---|---|---|
| `plate.id` | loop index `i` | `cpp/src/engine/tectonics.cpp:29` |
| `plate.axis` | `random_unit_vector(rng)` — `z = 2u−1`, `a = 2πu`, `r = sqrt(max(0, 1−z²))`, axis = `(cos a·r, sin a·r, z)` | `cpp/src/engine/tectonics.cpp:6-12`, `:30` |
| `plate.kind` | `draw < continental_plate_fraction` → `1` (continental); else `draw < continental_plate_fraction + 0.22` → `2` (mixed); else `0` (oceanic) | `cpp/src/engine/tectonics.cpp:21-27` |
| `plate.angular_speed` | `(min_angular_speed + (max_angular_speed − min_angular_speed)·u) · tectonic_activity` | `cpp/src/engine/tectonics.cpp:31-32` |
| `plate.crust_density` | kind 0 → `3.00`; kind 1 → `2.72`; kind 2 → `2.84` | `cpp/src/engine/tectonics.cpp:34` |
| `plate.crust_thickness_km` | kind 0 → `7.0`; kind 1 → `34.0`; kind 2 → `22.0` | `cpp/src/engine/tectonics.cpp:35` |

The mixed-kind band width `0.22` is a hard-coded literal, not a configuration property.

`tectonic_activity` is the shared planetary activity index used across the tectonic stack:

```
tectonic_activity = clamp(internal_heat * sqrt(4.5 / max(0.05, geological_age_ga)), 0.25, 2.25)
```

defined identically at `cpp/src/engine/tectonics.cpp:19`, `:295`, and `:1213-1217`, and echoed into the world document as `plate_kinematic_model.tectonic_activity_formula` / `.tectonic_activity_index` (`cpp/src/engine/process_serialization.cpp:2878-2887`).

### `choose_plate_seeds` — `cpp/src/engine/tectonics.cpp:41`

A second, independent `std::mt19937_64` seeded with `params.seed ^ 0xBAD5EEDULL` draws uniform cell indices in `[0, cell_count−1]` and rejects duplicates via an `unordered_set` until `plate_count` distinct seeds exist. The seed cell's unit position becomes both `plate.initial_center` and the mutable `plate.center` (`cpp/src/engine/pipeline.cpp:24-29`). Note that `plate.axis` and `plate.center` are drawn independently — a plate's Euler pole is unrelated to its domain centroid.

### `assign_plates` — `cpp/src/engine/tectonics.cpp:55`

Assignment is a spherical nearest-center (maximum dot product) classification over the *current* plate centers:

| Aspect | Behavior | Source |
|---|---|---|
| Score | `dot(cell.p, centers[p])`, maximized | `cpp/src/engine/tectonics.cpp:72-77` |
| Tie behavior | strict `>` — the lowest plate index wins ties | `cpp/src/engine/tectonics.cpp:73` |
| Parallelism | `#pragma omp parallel for schedule(static)` | `cpp/src/engine/tectonics.cpp:67` |
| Accelerator path | `try_accelerated_assign_plates(centers, cells, ids)`; if it returns a complete result it is used, with a size check that throws `accelerated plate assignment result size mismatch` | `cpp/src/engine/tectonics.cpp:58-61` |
| Empty-domain guard | any plate with zero assigned cells throws `nearest-center plate domain became empty; increase mesh.cell_count or reduce tectonics.plate_count/plate motion` | `cpp/src/engine/tectonics.cpp:85-92` |

The accelerator contract is documented at `cpp/src/opencl_compute.hpp:32-35`: a `true` return means the selected accelerator produced a *complete* host result; in `auto` mode a runtime failure atomically disables acceleration for the rest of the generation and returns `false` so the caller runs its unchanged CPU implementation, while explicit OpenCL/CUDA requests throw instead. This page does not assert bit-for-bit accelerator parity for plate assignment or field smoothing — see [Limitations](#limitations-and-unresolved-claims).

---

## The continental/oceanic split and how the target fraction is met

Two distinct knobs control continentality, and they act at different levels.

- `tectonics.continental_plate_fraction` biases **which plates** get a continental kind (the kind draw above).
- `tectonics.continental_crust_fraction_target` sets **how many cells** end up in the continental mask.

The mask is built by a global rank-and-cut inside `derive_crust_and_topography` (`cpp/src/engine/tectonics.cpp:319-350`):

1. **Score every cell** (`cpp/src/engine/tectonics.cpp:320-329`):

   ```
   wave            = 0.12 * sin(3*cell.lon + 1.7*sin(2*cell.lat))     // lat/lon in radians
   plate_bias      = 0.72 if plate.kind == 1 else 0.48 if plate.kind == 2 else 0.17
   continental_score = plate_bias
                     + 0.20 * continental_noise[i]
                     + wave
                     + 0.14 * cell.boundary_convergent
   ```

   `continental_noise` is `signed_noise(seed, i, 17)` (`cpp/src/engine/tectonics.cpp:300-302`) graph-smoothed with `INITIAL_CRUST_COHERENCE_SMOOTHING_STEPS = 1` and `INITIAL_CRUST_COHERENCE_SELF_WEIGHT = 0.77` (`cpp/src/engine/constants.hpp:23-24`, applied at `cpp/src/engine/tectonics.cpp:307-312`). `signed_noise(seed,a,b) = 2*hash01(seed,a,b) − 1` with `hash01` built on `splitmix64` (`cpp/src/engine/core.cpp:132-138`).

2. **Rank** all cell ids by descending score with `std::stable_sort`; ties break on the lower cell id (`cpp/src/engine/tectonics.cpp:332-340`).

3. **Cut** at

   ```
   continental_target_count = clamp(llround(continental_crust_fraction_target * cell_count), 0, cell_count)
   ```

   (`cpp/src/engine/tectonics.cpp:341-345`) and set `continental_mask = 1` for the top-ranked `continental_target_count` cells (`cpp/src/engine/tectonics.cpp:346-350`).

**How exactly the target is met.** The cut is on **cell count**, not on control-volume area: the target multiplies `n = cells.size()`, and the model publishes `plate_kinematic_model.initial_continental_crust_fraction` as *continental cell count / crust cell count* (`cpp/src/engine/process_serialization.cpp:2678-2681`). The configuration field description in `src/magic_geo/config.py:275-280` says "Target fraction of surface control-volume area assigned continental crust"; because mesh cells do not all have identical area, the realized area fraction can differ from the realized cell fraction. Treat `continental_crust_fraction_target` as an exact per-cell rank cut and an approximate area target.

4. **Margins.** Every non-mask cell with at least one mask neighbor is flagged `continental_margin` (one graph hop, `cpp/src/engine/tectonics.cpp:351-363`). The published model name for this is `transitional_crust_margin_model = "one_hop_graph_margin_v1"` (`cpp/src/engine/process_serialization.cpp:2740`).

The published partition model string is `initial_crust_partition_model = "ranked_graph_coherent_plate_biased_continental_mask_v2"` (`cpp/src/engine/process_serialization.cpp:2722-2723`). The serialized `plate_kinematic_model` also recomputes and exposes component structure of the initial continental mask — `initial_continental_crust_cell_count`, `initial_continental_crust_fraction`, `initial_continental_crust_component_count`, `initial_continental_crust_largest_component_cell_count`, `initial_continental_crust_boundary_edge_count` (`cpp/src/engine/process_serialization.cpp:2726-2735`) — where "continental" for that diagnostic means crust type in `{1, 4, 5, 6, 7}` (`cpp/src/engine/process_serialization.cpp:2628-2637`).

---

## Boundary classification and the smoothing steps

`classify_boundaries` (`cpp/src/engine/tectonics.cpp:126`) runs three phases: per-edge accumulation, degree normalization, and graph smoothing, followed by a categorical label.

### Phase 1 — per-edge kinematic accumulation (`cpp/src/engine/tectonics.cpp:129-153`)

For every mesh edge `(i, j)` with `j > i` and `plate_id[i] != plate_id[j]`:

| Quantity | Formula | Source line |
|---|---|---|
| `mid` | `normalize(p_i + p_j)` | `:136` |
| `delta` | `p_j − p_i` | `:137` |
| `across` | `normalize(delta − mid·dot(delta, mid))` (tangential, points i→j) | `:138` |
| `tangent` | `normalize(cross(mid, across))` | `:139` |
| `vrel` | `plate_velocity(b, mid) − plate_velocity(a, mid)` where `plate_velocity(P, x) = cross(P.axis · P.angular_speed, x)` | `:140`, `:95-97` |
| `separation` | `dot(vrel, across)` | `:141` |
| `shear` | `abs(dot(vrel, tangent))` | `:142` |
| convergent contribution `c` | `clamp(−separation · 1.25, 0, 1)` | `:143` |
| divergent contribution `d` | `clamp(separation · 1.25, 0, 1)` | `:144` |
| transform contribution `t` | `clamp((shear − abs(separation)·0.35) · 1.05, 0, 1)` | `:145` |

Each contribution is added to **both** endpoint cells (`cpp/src/engine/tectonics.cpp:146-151`). This loop is serial (no OpenMP pragma) because of the scatter-add.

Note that these are **dimensionless indices** derived from the intrinsic angular-speed index, not km/Ma. The exact directed per-segment kinematics with nominal km/Ma velocities live in the separate plate-boundary segment ledger, whose nominal velocity scale is `radius_km · plate_motion_scale_deg_per_step · (π/180) / 5.0 Ma` (`cpp/src/engine/plate_boundary_segments.cpp:199-201`).

### Phase 2 — degree normalization (`cpp/src/engine/tectonics.cpp:154-159`)

```
degree = max(1, neighbors.size())
conv[i] = clamp(conv[i] / degree * 3.2, 0, 1)   // same for div, trans
```

The `3.2` gain is a hard-coded literal.

### Phase 3 — graph smoothing (`cpp/src/engine/tectonics.cpp:160-183`)

| Field | Steps | Self weight | Source |
|---|---|---|---|
| `boundary_convergent` | `tectonics.boundary_smoothing_steps` | `0.58` | `cpp/src/engine/tectonics.cpp:169`, `:180` |
| `boundary_divergent` | `tectonics.boundary_smoothing_steps` | `0.58` | `cpp/src/engine/tectonics.cpp:170`, `:181` |
| `boundary_transform` | `tectonics.boundary_smoothing_steps` | `0.62` | `cpp/src/engine/tectonics.cpp:171`, `:182` |

`smooth_field` (`cpp/src/engine/tectonics.cpp:99-124`) is a Jacobi-style neighbor average repeated `steps` times:

```
next[i] = self_weight * current[i] + (1 - self_weight) * mean(current[neighbors of i])
```

with `next[i] = current[i]` when a cell has no neighbors, and an early return of the untouched input when `steps <= 0`. A fused three-field accelerator entry point `try_accelerated_smooth_three_fields` is attempted first and falls back to three independent `smooth_field` calls (`cpp/src/engine/tectonics.cpp:163-183`).

### Phase 4 — categorical label (`cpp/src/engine/tectonics.cpp:184-201`)

Let `m = max(convergent, divergent, transform)`.

| Condition (evaluated in order) | `boundary_type` id | Serialized name |
|---|---|---|
| `m < 0.08` | 0 | `interior` |
| `convergent == m` **and** `divergent > 0.45 * m` | 4 | `mixed` |
| `convergent == m` | 1 | `convergent` |
| `divergent == m` | 2 | `divergent` |
| otherwise | 3 | `transform` |

Names come from `BOUNDARY_NAMES` (`cpp/src/engine/schema_names.hpp:14-16`). The comparison is exact floating-point equality against the maximum, so the branch order defines the precedence when two smoothed fields coincide.

The independent per-segment classifier in the boundary ledger uses the same `0.08` activity floor and the same convergent → divergent → transform precedence, but returns `"inactive"` instead of `"interior"` and has no `mixed` class (`cpp/src/engine/plate_boundary_segments.cpp:99-115`).

---

## Plate motion: Rodrigues rotation of centers with the per-step scale

Motion is applied only to the plate **centers**. The Euler axis and the intrinsic angular speed are constant for the whole run; the mesh never moves.

Per motion step, for each plate (`cpp/src/engine/tectonics.cpp:1125-1134`):

```
rotation_deg  = plate.angular_speed * params.plate_motion_scale_deg_per_step * timestep_scale
rotation_rad  = rotation_deg / DEG                       // DEG = 180/pi
plate.center  = rotate_about_axis(plate.center, plate.axis, rotation_rad)
plate.cumulative_rotation_deg += rotation_deg
step_rotation_deg[index] = rotation_deg
```

`timestep_scale = maturation_timestep_scale(params) = erosion.maturation_timestep_ma / MATURATION_REFERENCE_TIMESTEP_MA`, with `MATURATION_REFERENCE_TIMESTEP_MA = 5.0` (`cpp/src/engine/core.cpp:44-47`, `cpp/src/engine/constants.hpp:72`).

`rotate_about_axis` is the Rodrigues rotation formula with a re-normalized axis and a re-normalized result (`cpp/src/engine/core.cpp`, `Vec3 rotate_about_axis`):

```
unit_axis = normalize(axis)
result    = normalize( v*cos(t) + cross(unit_axis, v)*sin(t) + unit_axis*dot(unit_axis, v)*(1 - cos(t)) )
```

with an exact early return for `angle_rad == 0.0`.

Immediately after rotation the step re-runs `assign_plates(centers, cells)` and `classify_boundaries(params, plates, cells)` (`cpp/src/engine/tectonics.cpp:1135-1136`), so plate domains and boundary forcing are recomputed from the rotated centers before any crust rule fires.

| Published key | Value | Source |
|---|---|---|
| `plate_kinematic_model.model_type` | `rotating_voronoi_plate_domains_v3` | `cpp/src/engine/process_serialization.cpp:2684` |
| `plate_kinematic_model.domain_assignment` | `nearest_rotated_plate_center_on_fixed_spherical_mesh` | `cpp/src/engine/process_serialization.cpp:2721` |
| `plate_kinematic_model.nominal_timestep_ma` | `erosion.maturation_timestep_ma` | `cpp/src/engine/process_serialization.cpp:2697-2698` |
| `plate_kinematic_model.reference_timestep_ma` | `5.0` | `cpp/src/engine/process_serialization.cpp:2699-2700` |
| `plate_kinematic_model.maturation_timestep_scale` | `maturation_timestep_ma / 5.0` | `cpp/src/engine/process_serialization.cpp:2701-2702` |
| `plate_kinematic_model.timestep_scaling_model` | `reference_normalized_partial_process_scaling_v1` | `cpp/src/engine/process_serialization.cpp:2703-2704` |
| `plate_kinematic_model.reference_motion_scale_deg_per_reference_step` | `plate_motion_scale_deg_per_step` | `cpp/src/engine/process_serialization.cpp:2708-2709` |
| `plate_kinematic_model.effective_motion_scale_deg_per_step` | `plate_motion_scale_deg_per_step * timestep_scale` | `cpp/src/engine/process_serialization.cpp:2710-2712` |
| `plate_kinematic_model.configured_motion_step_count` | `erosion.iterations` | `cpp/src/engine/process_serialization.cpp:2719` |
| `plate_kinematic_model.physical_time_resolved` | `false` | `cpp/src/engine/process_serialization.cpp:2686` |
| `plate_kinematic_model.nominal_time_calibrated` | `false` | `cpp/src/engine/process_serialization.cpp:2687` |
| `plate_kinematic_model.process_rate_calibration_resolved` | `false` | `cpp/src/engine/process_serialization.cpp:2688` |
| `plate_kinematic_model.time_step_convergence_demonstrated` | `false` | `cpp/src/engine/process_serialization.cpp:2689` |

---

## Initial crust derivation: type, lithology, thickness, density

`initial_crust_category_state` (`cpp/src/engine/tectonics.cpp:226-283`) is a pure function of the plate, the two mask flags, the two boundary strengths, and two independent noise samples.

Two noise draws are taken per cell in the categorization loop (`cpp/src/engine/tectonics.cpp:368-377`):

- `category_noise = signed_noise(seed, i, 23)`
- `numeric_noise = signed_noise(seed, i, 31)`

### Continental branch (`continental_mask == 1`) — `cpp/src/engine/tectonics.cpp:236-263`

| Condition (in order) | `crust_type` | id | `lithology` | id |
|---|---|---|---|---|
| `convergent > 0.40` | `orogen` | 5 | `metamorphic` | 6 |
| `divergent > 0.36` | `rift_basin` | 6 | `sandstone` | 3 |
| `category_noise > 0.55` and `convergent < 0.16` and `divergent < 0.14` | `craton` | 4 | `granite` | 1 |
| `category_noise < −0.45` | `sedimentary_basin` | 7 | `limestone` (2) if `numeric_noise > 0`, else `shale` (4) | 2 / 4 |
| otherwise | `continental` | 1 | `granite` (1) if `numeric_noise > 0.35`, else `sandstone` (3) | 1 / 3 |

Thickness: `clamp(29.0 + 17.0*convergent − 8.0*divergent + 5.0*numeric_noise, 18.0, 72.0)` km (`cpp/src/engine/tectonics.cpp:257-262`). `density_g_cm3` is left at its `0.0` default in this branch.

### Oceanic branch (`continental_mask == 0`) — `cpp/src/engine/tectonics.cpp:266-282`

| Condition (in order) | `crust_type` | id | `lithology` | id |
|---|---|---|---|---|
| `convergent > 0.35` **and** `plate.kind != 0` | `volcanic_arc` | 3 | `volcanic` | 5 |
| `continental_margin` | `transitional` | 2 | `basalt` | 0 |
| otherwise | `oceanic` | 0 | `basalt` | 0 |

Thickness: `clamp(6.5 + 3.0*convergent + 1.5*numeric_noise, 4.5, 14.0)` km (`cpp/src/engine/tectonics.cpp:276-280`). `density_g_cm3` is set to `3.00` (`cpp/src/engine/tectonics.cpp:281`).

### Density assignment (`cpp/src/engine/tectonics.cpp:394-396`)

```
cell.crust_density = state.density_g_cm3 > 0.0
                   ? state.density_g_cm3                      // oceanic branch: 3.00
                   : 2.70 + 0.08 * hash01(seed, i, 43);        // continental branch: [2.70, 2.78)
```

### Provisional age zero and the oceanic predicate

`crust_age_ma` is deliberately set to `0.0` in this first pass (`cpp/src/engine/tectonics.cpp:392`), with the in-source comment: *"The exact boundary geometry and oceanic predicate need a complete provisional state before the ridge-distance age field is built."* The published model echoes this as `provisional_age_for_oceanic_predicate_ma = 0` (`cpp/src/engine/process_serialization.cpp:2433-2434`).

### `is_oceanic_crust_state` — `cpp/src/engine/tectonics.cpp:513-530`

This is the canonical "oceanic-like" predicate used everywhere downstream (age field, thermal subsidence, isostasy, boundary-segment opening witnesses):

| `crust_type` | Result |
|---|---|
| `0` (`oceanic`) | `true` |
| `2` (`transitional`) | `true` **iff** `lithology == 0` (`basalt`) |
| `3` (`volcanic_arc`) | `true` **iff** `age_ma <= 320.0` **and** `thickness_km <= 18.0` **and** `density >= 2.84` |
| anything else | `false` |

Published as `oceanic_state_classification_model = "crust_type_with_transitional_lithology_provenance_and_arc_numeric_guard_v2"`, plus the two rule strings `transitional_oceanic_provenance_rule` and `volcanic_arc_oceanic_state_rule` (`cpp/src/engine/process_serialization.cpp:2820-2825`).

Beware of a second, looser predicate used only inside the initial-relief loop: `oceanic = (crust_type == 0 || crust_type == 2 || crust_type == 3)` (`cpp/src/engine/tectonics.cpp:425`). For the provisional initial state the two agree (transitional cells always get basalt, volcanic arcs always get density 3.00 and thickness ≤ 14 km at age 0), but they are not the same function and diverge after the maturation rules mutate lithology and density.

### Crust type and lithology name tables

| id | `crust_type` (`CRUST_NAMES`) | id | `lithology` (`LITHOLOGY_NAMES`) | `lithology_resistance` |
|---|---|---|---|---|
| 0 | `oceanic` | 0 | `basalt` | 0.85 |
| 1 | `continental` | 1 | `granite` | 1.25 |
| 2 | `transitional` | 2 | `limestone` | 0.75 |
| 3 | `volcanic_arc` | 3 | `sandstone` | 0.82 |
| 4 | `craton` | 4 | `shale` | 0.62 |
| 5 | `orogen` | 5 | `volcanic` | 0.95 |
| 6 | `rift_basin` | 6 | `metamorphic` | 1.35 |
| 7 | `sedimentary_basin` | — | (default) | 1.0 |
| 8 | `accreted_terrane` | | | |

Names: `cpp/src/engine/schema_names.hpp:7-13`. `lithology_resistance`: `cpp/src/engine/tectonics.cpp:204-215` (consumed as `1 / resistance` in the stream-power erodability term, `cpp/src/engine/earth_system.cpp:983-984`).

---

## The initial oceanic crust age field

This is the one place where seafloor age is *constructed* rather than advected. It is implemented in `cpp/src/engine/initial_oceanic_age.cpp` and named by the source, verbatim, as:

> `model_type = "multi_source_nominal_ridge_graph_travel_time_v1"` — `cpp/src/engine/process_serialization.cpp:2415-2416`

`derive_crust_and_topography` calls it after building a **provisional** identity transport plan and a **provisional** boundary-segment set from the age-zero crust state (`cpp/src/engine/tectonics.cpp:398-415`).

### Inputs and preconditions

| Requirement | Failure message | Source |
|---|---|---|
| `cells.size() <= INT_MAX` | `initial oceanic crust age cell count exceeds int range` | `cpp/src/engine/initial_oceanic_age.cpp:56-62` |
| `radius_km` finite and `> 0` | `initial oceanic crust age model requires positive finite radius` | `cpp/src/engine/initial_oceanic_age.cpp:63-67` |
| `cells[i].id == i` | `initial oceanic crust age cells are not in canonical id order` | `cpp/src/engine/initial_oceanic_age.cpp:90-95` |
| neighbor ids in range | `initial oceanic crust age neighbor id is invalid` | `cpp/src/engine/initial_oceanic_age.cpp:205-212` |
| cell area finite and `>= 0` | `initial oceanic crust age cell area is invalid` | `cpp/src/engine/initial_oceanic_age.cpp:276-280` |
| finite graph edge distance | `initial oceanic crust age graph edge distance is invalid` | `cpp/src/engine/initial_oceanic_age.cpp:30-34` |

The model ceiling is

```
maximum_age_ma = crust_age_ceiling_ma(params, INITIAL_OCEANIC_CRUST_MAX_AGE_MA)
               = max(0, min(200.0, geological_age_ga * 1000.0))
```

(`cpp/src/engine/initial_oceanic_age.cpp:68-71`, `cpp/src/engine/core.cpp:40-42`, `cpp/src/engine/constants.hpp:42`). The constant carries an explicit source caveat: *"A 200 Ma procedural ceiling covers the dominant present-day seafloor-age distribution but is not a physical maximum: the pinned Seton et al. (2020) grid contains a rare older tail to about 339 Ma"* (`cpp/src/engine/constants.hpp:37-41`).

### Ridge seeding

A boundary segment qualifies as an *eligible ridge segment* only if all of the following hold (`cpp/src/engine/initial_oceanic_age.cpp:106-141`):

| Test | Rejection behavior |
|---|---|
| `segment.direct_boundary_class == "divergent"` | skipped |
| `segment.left_opening_oceanic_like` | skipped |
| `segment.right_opening_oceanic_like` | skipped |
| valid cell ids, finite `length_km > 0`, finite `signed_opening_rate_km_per_ma >= 0` | **throws** `initial oceanic crust age divergent segment is invalid` |
| `signed_opening_rate_km_per_ma == 0.0` | skipped — a geometrically divergent boundary with zero configured motion "is not an active spreading ridge" |

Eligible segments contribute their `segment_id` to `eligible_ridge_segment_ids`, add `opening_rate * length` to `opening_rate_length_sum_km2_per_ma`, add `length_km` to `eligible_ridge_total_length_km`, and push **both** their `left_cell_id` and `right_cell_id` into the seed list. The seed list and the segment-id list are then sorted, and the seed list is de-duplicated (`cpp/src/engine/initial_oceanic_age.cpp:142-154`). Published rule: `ridge_seed_rule = "sorted_unique_left_and_right_cell_ids_of_eligible_ridge_segments"` (`cpp/src/engine/process_serialization.cpp:2441-2442`).

A seed cell that is not oceanic-like throws `initial oceanic crust age ridge seed is not oceanic` (`cpp/src/engine/initial_oceanic_age.cpp:182-186`).

### The single nominal half-rate

There is exactly **one** spreading rate for the whole planet. It is the length-weighted mean opening rate over eligible ridge segments, halved (`cpp/src/engine/initial_oceanic_age.cpp:156-172`):

```
representative_full_spreading_rate_km_per_ma =
    opening_rate_length_sum_km2_per_ma / eligible_ridge_total_length_km    (0.0 if total length == 0)

representative_half_spreading_rate_km_per_ma = 0.5 * representative_full_spreading_rate_km_per_ma
```

A non-finite or negative half-rate throws `initial oceanic crust age representative spreading rate is invalid`. Published formulas: `representative_full_spreading_rate_formula`, `representative_half_spreading_rate_factor = 0.5`, and `representative_rate_accumulation_order = "plate_motion_history_zero_boundary_segments_serialized_order"` (`cpp/src/engine/process_serialization.cpp:2443-2448`).

If the half-rate is not `> 0.0`, **no** seeds are pushed onto the queue at all (`cpp/src/engine/initial_oceanic_age.cpp:180-195`) and every oceanic-like cell ends at the ceiling with the no-active-ridge-path status.

### Multi-source Dijkstra

The relaxation is a min-heap Dijkstra over the **oceanic-like sub-graph only** (`cpp/src/engine/initial_oceanic_age.cpp:174-240`).

| Element | Implementation |
|---|---|
| Queue | `std::priority_queue<pair<double,int>, vector<...>, std::greater<>>` — ordered by ascending age, then ascending cell id |
| Initial state | non-oceanic-like: `age = 0.0`; oceanic-like: `age = +inf`; seeds: `age = 0.0`, status `ridge_seed`, `origin_ridge_seed_cell_id = self` |
| Stale-entry skip | `if (current_age_ma != ages[cell_id]) continue;` (`:200-202`) |
| Neighbor filter | non-oceanic-like neighbors are skipped entirely (`:213-215`) — the field never crosses continental crust |
| Edge weight | `great_circle_distance_km(radius_km, p_source, p_target) / representative_half_spreading_rate_km_per_ma` (`:216-222`) |
| Edge distance | `radius_km * atan2(norm(cross(a,b)), clamp(dot(a,b), −1, 1))` (`:19-36`) |
| Relaxation | strictly `<` — the first-discovered equal-age path is retained (`:223-238`) |
| Witnesses updated on relax | `predecessor_cell_id_by_cell`, `origin_ridge_seed_cell_id_by_cell` (inherited from the relaxing cell) |

Published equivalents: `shortest_path_model = "multi_source_dijkstra_over_oceanic_like_cell_neighbor_graph"`, `queue_order = "ascending_accumulated_age_ma_then_ascending_cell_id"`, `neighbor_order = "cells[].neighbors_serialized_order"`, `equal_path_tie_rule = "strictly_lower_age_updates_only_first_discovered_equal_age_path_retained"` (`cpp/src/engine/process_serialization.cpp:2455-2462`).

### Statuses

`InitialOceanicCrustAgeStatus` (`cpp/src/engine/types/earth_system.hpp:520-526`), assigned in the finalize pass (`cpp/src/engine/initial_oceanic_age.cpp:245-299`):

| id | Enum | Assigned when | Resulting `age_ma_by_cell` | `unclamped_graph_age_ma_by_cell` |
|---|---|---|---|---|
| 0 | `INITIAL_OCEANIC_AGE_NOT_OCEANIC_LIKE` | cell fails `is_oceanic_crust_state` | exactly `0.0` | `−1.0` sentinel |
| 1 | `INITIAL_OCEANIC_AGE_RIDGE_SEED` | cell is an eligible-ridge endpoint and a positive half-rate exists | `0.0` | `0.0` |
| 2 | `INITIAL_OCEANIC_AGE_RIDGE_REACHABLE` | finite graph age `<= maximum_age_ma`, not a seed | `clamp(graph_age, 0, maximum_age_ma)` | graph age |
| 3 | `INITIAL_OCEANIC_AGE_RIDGE_REACHABLE_CEILING_CLAMPED` | finite graph age `> maximum_age_ma` | `maximum_age_ma` | graph age (unclamped) |
| 4 | `INITIAL_OCEANIC_AGE_UNRESOLVED_NO_ACTIVE_RIDGE_PATH_CEILING` | oceanic-like but graph age stayed `+inf` | `maximum_age_ma` | `−1.0` sentinel |

Status 4 carries an explicit in-source justification: *"An oceanic graph component without an active divergent segment represents an unresolved extinct basin. Assigning the procedural model ceiling is explicit and avoids inventing a ridge or claiming a physical maximum seafloor age."* (`cpp/src/engine/initial_oceanic_age.cpp:251-258`). The sentinel convention is published as `unclamped_graph_age_unavailable_sentinel = "negative_one_for_non_oceanic_like_or_unreachable_cells"` (`cpp/src/engine/process_serialization.cpp:2478-2479`).

Note the status-3 subtlety: a ceiling-clamped cell counts in **both** `reachable_oceanic_like_cell_count` and `reachable_ceiling_clamped_cell_count` (`cpp/src/engine/initial_oceanic_age.cpp:260-265`), and the ledger's `ceiling_assigned_cell_count` is defined as `unreachable_oceanic_like_cell_count + reachable_ceiling_clamped_cell_count` (`cpp/src/engine/process_serialization.cpp:2562-2564`).

### Area-weighted statistics and the CDF

The same finalize pass accumulates `oceanic_like_area_km2`, `area_weighted_mean_age_ma` (`Σ area·age / Σ area`), `minimum_oceanic_like_age_ma`, `maximum_oceanic_like_age_ma`, and a ten-bin area-weighted CDF at the fixed thresholds `{20, 40, 60, 80, 100, 120, 140, 160, 180, 200}` Ma (`cpp/src/engine/initial_oceanic_age.cpp:6-17`, `:291-309`). Comparison is inclusive (`age <= threshold`). The thresholds are declared as *output for external validation, not a generation input*: `cdf_threshold_selection = "fixed_20_ma_increments_from_20_through_200_for_external_validation_output_not_generation_input"` (`cpp/src/engine/process_serialization.cpp:2485-2486`).

If `oceanic_like_cell_count == 0`, `minimum_oceanic_like_age_ma` is forced to `0.0` (`cpp/src/engine/initial_oceanic_age.cpp:300-302`). A non-finite aggregate throws `initial oceanic crust age diagnostic aggregate is invalid` (`:310-319`).

### The ledger it round-trips

Two top-level world-document keys carry this field:

- `initial_oceanic_crust_age_model` — the declarative contract (`cpp/src/engine/process_serialization.cpp:2410-2510`)
- `initial_oceanic_crust_age_ledger` — a single object, not an array (`cpp/src/engine/process_serialization.cpp:2512-2611`)

**Ledger fields, in emission order:**

| # | Field | Type | Meaning |
|---|---|---|---|
| 1 | `source_plate_motion_history_id` | int | always `0` — the identity-overlap checkpoint |
| 2 | `cell_count` | int | total mesh cells |
| 3 | `oceanic_like_cell_count` | int | cells passing `is_oceanic_crust_state` on the provisional state |
| 4 | `non_oceanic_like_cell_count` | int | complement |
| 5 | `eligible_ridge_segment_count` | int | size of `eligible_ridge_segment_ids` |
| 6 | `ridge_seed_cell_count` | int | size of `ridge_seed_cell_ids` |
| 7 | `reachable_oceanic_like_cell_count` | int | finite graph age reached (includes clamped) |
| 8 | `unreachable_oceanic_like_cell_count` | int | status 4 count |
| 9 | `reachable_ceiling_clamped_cell_count` | int | status 3 count |
| 10 | `ceiling_assigned_cell_count` | int | `#8 + #9` |
| 11 | `eligible_ridge_total_length_km` | double, round-trip | `Σ segment.length_km` |
| 12 | `opening_rate_length_sum_km2_per_ma` | double, round-trip | `Σ opening_rate · length` |
| 13 | `representative_full_spreading_rate_km_per_ma` | double, round-trip | `#12 / #11` |
| 14 | `representative_half_spreading_rate_km_per_ma` | double, round-trip | `0.5 · #13` |
| 15 | `maximum_age_ma` | double, round-trip | effective ceiling |
| 16 | `oceanic_like_area_km2` | double, round-trip | `Σ area` over oceanic-like cells |
| 17 | `area_weighted_mean_age_ma` | double, round-trip | `Σ area·age / #16` |
| 18 | `minimum_oceanic_like_age_ma` | double, round-trip | min over oceanic-like cells |
| 19 | `maximum_oceanic_like_age_ma` | double, round-trip | max over oceanic-like cells |
| 20 | `eligible_ridge_segment_ids` | int[] | sorted ascending |
| 21 | `ridge_seed_cell_ids` | int[] | sorted, unique |
| 22 | `age_ma_by_cell` | double[], round-trip | final clamped age, index = cell id |
| 23 | `unclamped_graph_age_ma_by_cell` | double[], round-trip | raw graph age or `−1.0` sentinel |
| 24 | `status_id_by_cell` | int[] | status enum per cell |
| 25 | `predecessor_cell_id_by_cell` | int[] | Dijkstra parent or `−1` |
| 26 | `origin_ridge_seed_cell_id_by_cell` | int[] | seed of the winning path or `−1` |
| 27 | `cdf_thresholds_ma` | double[10], round-trip | fixed 20…200 Ma |
| 28 | `area_weighted_cdf_le_threshold` | double[10], round-trip | area fraction at or below each threshold |

The serializer fails closed on internal inconsistency — array cardinalities mismatched, negative counts, or the two count partitions not summing correctly throw `initial oceanic crust age ledger is internally inconsistent` (`cpp/src/engine/process_serialization.cpp:2515-2543`).

**Serialization contract:** every scalar and every array uses `roundtrip_num` / `roundtrip_double_array_json`, i.e. `std::defaultfloat` at `max_digits10` significant digits, declared as `array_serialization_model = "decimal_max_digits10_binary64_round_trip"` (`cpp/src/engine/process_serialization.cpp:2481-2482`). The document therefore recovers the original binary64 values after JSON parsing.

**The round trip.** `src/magic_geo/initial_oceanic_crust_age_validation.py` (989 lines) independently re-derives the entire field from `cells[]` and `plate_motion_history[0].boundary_segments` and compares against the ledger. It re-declares the same status ids (`src/magic_geo/initial_oceanic_crust_age_validation.py:17-21`), the same `CONFIGURED_MAXIMUM_AGE_MA = 200.0` (`:14`), and the same `CDF_THRESHOLDS_MA = tuple(float(v) for v in range(20, 201, 20))` (`:15`). `validate_initial_oceanic_crust_age(world)` returns `{"passed": bool, "failures": [str], "metrics": {...}}` with per-stage replay flags:

| Metric flag | Meaning |
|---|---|
| `provisional_oceanic_mask_replayed` | the oceanic-like predicate was reproduced from serialized crust state |
| `eligible_ridge_segments_replayed` | the eligible-segment filter matched |
| `representative_spreading_rates_replayed` | full and half rates matched |
| `ridge_seed_cells_replayed` | the sorted unique seed set matched |
| `dijkstra_unclamped_ages_replayed` | the unclamped graph ages matched |
| `dijkstra_path_witness_replayed` | predecessor and origin-seed arrays matched |
| `clamped_ages_and_status_replayed` | final ages and statuses matched |
| `summary_statistics_replayed` | the nine scalar aggregates matched |
| `cdf_replayed` | thresholds and area-weighted CDF matched |
| `oceanic_history_aliases_replayed` | `plate_motion_history[0]` oceanic age aliases matched the ledger |

plus numeric residual metrics `maximum_absolute_age_replay_residual_ma`, `maximum_absolute_summary_replay_residual`, `dijkstra_queue_push_count`, and the model's own unresolved flags echoed verbatim (`src/magic_geo/initial_oceanic_crust_age_validation.py:384-417`, `:960-971`). The `magic-geo validate` command wires this in and prefixes any failure with `initial oceanic crust age replay invalid:` (`src/magic_geo/cli/commands/validate.py:6047-6055`). The independent-replay contract is explicitly conditional: `independent_replay_inputs_unconditionally_exposed = false` and `independent_replay_requires_cells_output = true` (`cpp/src/engine/process_serialization.cpp:2494-2496`) — you must generate with `output.include_cells: true` to replay it.

**Unresolved flags on this model** (all serialized `false`, `cpp/src/engine/process_serialization.cpp:2497-2503`): `physical_seafloor_creation_resolved`, `spreading_rate_calibrated`, `local_spreading_rates_resolved`, `ridge_flowlines_resolved`, `subduction_sink_history_resolved`, `convergence_history_resolved`, `seton_2020_age_grid_used_as_generation_input`. The only booleans on this model that are `true` are `procedural_authority`, `path_decision_witness_exposed`, and `independent_replay_requires_cells_output` (`cpp/src/engine/process_serialization.cpp:2492-2496`). The stated limitation string is *"procedural_graph_distance_age_initialization_using_one_global_nominal_half_spreading_rate_without_physical_plate_reconstruction_flowlines_or_crust_creation_and_destruction_history"* (`cpp/src/engine/process_serialization.cpp:2504-2505`).

### Non-oceanic initial ages

Cells the relief loop treats as non-oceanic get a hashed age instead (`cpp/src/engine/tectonics.cpp:426-435`):

```
initial_age_ceiling_ma = crust_age_ceiling_ma(params, 4200.0) = max(0, min(4200, geological_age_ga*1000))
crust_age_ma = clamp(450.0 + 900.0 * geological_age_ga * hash01(seed, i, 41),
                     min(120.0, initial_age_ceiling_ma),
                     initial_age_ceiling_ma)
```

At the default `geological_age_ga = 4.5` this yields continental ages in `[450, 4200]` Ma.

---

## Initial topography derivation

The relief loop (`cpp/src/engine/tectonics.cpp:416-507`) computes nine additive components per cell. All are stored individually so the sum is auditable.

`relief_scale = clamp(1.0 / sqrt(max(0.08, gravity_g)), 0.55, 1.60)` (`cpp/src/engine/tectonics.cpp:294`).

| Cell field | Formula | Source |
|---|---|---|
| `initial_isostatic_elevation_m` | oceanic: `−OCEANIC_RIDGE_REFERENCE_DEPTH_M` = `−2500`; else `500 + 12·(thickness_km − 30) − 1800·(density − 2.72)` | `:436-446` |
| `thermal_subsidence_target_m` | `oceanic_age_depth_thermal_subsidence_m(crust_age_ma, oceanic_like)` | `:454-457` |
| `initial_ridge_uplift_m` | `divergent · (oceanic ? 0.0 : 880.0) · relief_scale` | `:462` |
| `initial_rift_subsidence_m` | `divergent · (oceanic ? 0.0 : −820.0) · relief_scale` | `:463` |
| `initial_orogenic_uplift_m` | `(continental ? conv²·20000 : conv·1350) · relief_scale` | `:464-469` |
| `initial_trench_subsidence_m` | `(oceanic ? −conv²·S : −conv·350) · relief_scale`, `S = 1400` for `volcanic_arc`, else `17000` | `:470-477` |
| `initial_volcanic_uplift_m` | `((crust_type==3 ? 15000·conv² : 0) + 380·divergent) · relief_scale` | `:478-481` |
| `initial_transform_fault_relief_m` | `−320.0 · transform` (no `relief_scale`) | `:482` |
| `initial_secondary_roughness_m` | `(continental ? 520 : 180)·relief_noise + (oceanic ? 260 : 620)·continental_noise + 180·sin(9·lon + 4·lat)` | `:483-485` |
| `initial_elevation_m` | sum of all nine above | `:495` |

`relief_noise` is `signed_noise(seed, i, 31)` smoothed with `SECONDARY_RELIEF_SMOOTHING_STEPS = 4` and `SECONDARY_RELIEF_SELF_WEIGHT = 0.58` (`cpp/src/engine/constants.hpp:25-26`, applied at `cpp/src/engine/tectonics.cpp:313-318`); published as `secondary_relief_noise_model = "independently_graph_smoothed_signed_noise_v2"` (`cpp/src/engine/process_serialization.cpp:2741`). Note it shares its salt (`31`) with the unsmoothed `numeric_noise` used by the crust categorizer — the smoothed and unsmoothed variants of the same base field.

The absence of an oceanic ridge-uplift term is deliberate and documented in source: *"The published age-depth relation already includes the elevated zero-age ridge intercept. Adding a second oceanic ridge uplift would double-count that bathymetry; the continental divergent term remains a separate broad rift-shoulder proxy."* (`cpp/src/engine/tectonics.cpp:458-461`).

Two derived per-cell indices are also set here and recomputed identically every motion step:

```
volcanic_potential_index = clamp(0.42*div + 0.38*conv*(crust_type==3 ? 1.0 : 0.35)
                                 + 0.16*(lithology==5 ? 1.0 : 0.0) + 0.04*tectonic_activity, 0, 1)

tectonic_uplift_rate_m_per_step = tectonic_uplift_scale * tectonic_activity
                                * (1.5*div + 8.5*conv + (crust_type==3 ? 2.5 : 0.0))
                                * maturation_timestep_scale
```

(`cpp/src/engine/tectonics.cpp:496-504` for the initial pass, `:1605-1613` for the per-step pass).

`cell.elevation_m` is set to `initial_elevation_m`, `cell.initial_plate_id = cell.plate_id` (`:505-506`), and finally every cell is passed through `initialize_sediment_interface(cell, "initial topography")` (`:508-510`) so the canonical bedrock-surface / mobile-sediment split is established before any transport runs.

Published relief-model keys: `initial_relief_model = "causal_isostasy_quadratic_convergence_relief_v2"`, `isostatic_equilibrium_formula = "oceanic_like?-2500:500+12*(crust_thickness_km-30)-1800*(crust_density_g_cm3-2.72)"`, `convergence_relief_exponent = 2.0`, and the four scale constants (`cpp/src/engine/process_serialization.cpp:2745-2768`). The constants themselves: `CONTINENTAL_ISOSTATIC_FREEBOARD_M = 500.0`, `CONTINENTAL_REFERENCE_CRUST_THICKNESS_KM = 30.0`, `CONTINENTAL_CRUST_THICKNESS_FREEBOARD_M_PER_KM = 12.0`, `CONTINENTAL_REFERENCE_CRUST_DENSITY_G_CM3 = 2.72`, `CONTINENTAL_CRUST_DENSITY_FREEBOARD_M_PER_G_CM3 = 1800.0`, `OCEANIC_RIDGE_REFERENCE_DEPTH_M = 2500.0`, `CONTINENTAL_OROGEN_UPLIFT_SCALE_M = 20000.0`, `OCEANIC_TRENCH_SUBSIDENCE_SCALE_M = 17000.0`, `VOLCANIC_ARC_TRENCH_SUBSIDENCE_SCALE_M = 1400.0`, `VOLCANIC_ARC_UPLIFT_SCALE_M = 15000.0` (`cpp/src/engine/constants.hpp:27-46`).

---

## Per-step crust evolution: the ordered rule pipeline

`advance_plate_motion_and_crust` (`cpp/src/engine/tectonics.cpp:1050`) does, in order:

1. Snapshot the previous state per cell: plate id, crust type, lithology, age, thickness, density, plus the previous local isostatic equilibrium and thermal subsidence target, plus the three boundary strengths (`:1082-1120`). The thermal snapshot is **checked**: a stale or non-finite `thermal_subsidence_target_m` throws `cell thermal subsidence is non-finite or stale before plate motion` (`:1102-1108`).
2. Rotate every plate center (Rodrigues) and record `step_rotation_deg` (`:1122-1134`).
3. `assign_plates` and `classify_boundaries` on the rotated centers (`:1135-1136`).
4. `build_forward_overlap_crust_transport_plan(...)` — exact spherical forward-overlap remap of the extensive crust state (`:1139-1150`).
5. `reconcile_accelerated_crust_overlap_continuous_shadow(...)` — a diagnostic-only device replay whose output is validated then discarded; the CPU plan stays authoritative (`:1151-1157`, contract at `cpp/src/opencl_compute.hpp:64-74`).
6. `begin_crust_material_shadow_step(...)` and `record_cpu_conservative_crust_overlap_transition()` (`:1158-1166`).
7. Compute per-cell transport diagnostics: volume-weighted mean transport distance and the three transport-only deltas (`:1174-1211`).
8. Run the ordered rule pipeline (`:1247-1648`).
9. Reduce the process-reason inventory in canonical cell order with `long double` accumulators (`:1662-1770`).
10. `finalize_crust_material_shadow_step` and `advance_crust_dry_rock_accounting_step` (`:1772-1783`).
11. `summarize_plate_motion_step(...)` and push the record (`:1784-1804`).

### The rules

Every rule operates on the **transported** state (`remapped_*_by_cell`), not the pre-transport cell state. `old_oceanic` is `is_oceanic_crust_state` applied to the transported state; `local_old_oceanic` is the same predicate applied to the pre-transport local state (`cpp/src/engine/tectonics.cpp:1253-1266`). Rules fire in this fixed order and each one is wrapped by `record_reason(...)`, which both accumulates a per-cell extensive-state delta and drives one `apply_crust_material_shadow_transition` (`:1291-1324`).

| # | `CrustProcessReason` | Trigger condition | Effect |
|---|---|---|---|
| 0 | `quiet_oceanic_aging` | `old_oceanic && div < 0.10 && conv < 0.10` | `age += oceanic_crust_aging_ma_per_step · timestep_scale · quiet_fraction`, where `quiet_fraction = clamp(1 − max(div,conv)/0.10, 0, 1)` (`:1327-1336`) |
| 1 | `oceanic_ridge_rejuvenation` | `div >= 0.10 && old_oceanic` | `age *= (1 − rejuvenation)`; at `timestep_scale == 1` `rejuvenation = clamp(div·(plate_changed ? 0.72 : 0.55), 0, 0.85)`, otherwise the background reference `clamp(div·0.55, 0, 0.85)` is timestep-scaled and a plate-crossing impulse is composed multiplicatively (`:1344-1375`) |
| 2 | `oceanic_ridge_creation_relaxation` | same branch as #1 | `thickness += (7.0 − thickness)·0.34·div`; `density += (3.0 − density)·0.24·div`, both timestep-scaled off `timestep_scale == 1` (`:1376-1391`); then `div >= 0.28` sets `crust_type = 0`, `lithology = 0` |
| 3 | `divergent_continental_rifting` | `div >= 0.10 && !old_oceanic` | `thickness -= tectonic_activity·(0.45 + 0.20 if plate_changed)·div`, floored at `0.0`; `density += 0.004·div·timestep_scale` (`:1397-1419`); then `div >= 0.24` sets `crust_type = 6`, `lithology = 3` |
| 4 | `oceanic_convergence_subduction_proxy` | `conv >= 0.10 && old_oceanic` | `thickness += tectonic_activity·0.34·conv·timestep_scale`; `age *= 1 − timestep_scaled_fraction(0.12·conv)` (`:1428-1440`); then `conv >= 0.26` sets `crust_type = 3`, `lithology = 5` |
| 5 | `continental_collision_orogeny` | `conv >= 0.10 && !old_oceanic` | `thickness += tectonic_activity·0.72·conv(·timestep_scale)`; `density -= 0.006·conv·timestep_scale` (`:1446-1473`) |
| 6 | `plate_crossing_accretion_proxy` | same branch as #5, extra thickening when `plate_changed` | `thickness += tectonic_activity·0.38·conv` (`:1458-1482`); then `plate_changed && conv >= 0.18` sets `crust_type = 8`, `lithology = 6`; else `conv >= 0.28` sets `crust_type = 5`, `lithology = 6` |
| 7 | `age_bound_enforcement` | always recorded; triggered flag when out of range | `age = clamp(age, 0, crust_age_ceiling_ma(params, new_oceanic ? 320.0 : 4200.0))` (`:1501-1516`) |
| 8 | `thickness_bound_enforcement` | always recorded | `thickness = clamp(thickness, new_oceanic ? 4.5 : 16.0, new_oceanic ? 18.0 : 76.0)` (`:1517-1530`) |
| 9 | `density_bound_enforcement` | always recorded | `density = clamp(density, 2.58, 3.08)` (`:1531-1538`) |

Additionally, before the divergent branch, `plate_changed && max(conv, div) < 0.18` sets `crust_type = 2` and `lithology = old_oceanic ? 0 : 3` — a quiet plate-crossing transitional relabel (`:1338-1341`). It is *not* attributed to any reason because it changes no extensive scalar.

`timestep_scaled_fraction(f, s) = −expm1(s · log1p(−f))` for bounded `f ∈ [0,1]` and `s > 0`, with exact short-circuits for `f <= 0`, `s <= 0`, `s == 1`, and `f >= 1` (`cpp/src/engine/core.cpp:49-65`).

The rifting floor carries an in-source rationale: *"A fully uncovered overlap row can start this ordered rule at zero thickness. Divergent thinning may exhaust material but must never manufacture a negative scalar crust reservoir; the later thickness bound explicitly records any reseeding."* (`cpp/src/engine/tectonics.cpp:1409-1412`).

### Event flags

| Flag / counter | Condition | Source |
|---|---|---|
| `aged_oceanic_cell_ids`, `cell.oceanic_crust_aging_event_count` | `age_process_change > 1e−6` **and** `old_oceanic` | `:1557-1560` |
| `rejuvenated_oceanic_cell_ids`, `cell.oceanic_crust_rejuvenation_event_count` | `div >= 0.10` **and** `age_process_change < −1e−6` **and** `old_oceanic` | `:1561-1564` |
| `subducted_oceanic_cell_ids`, `cell.oceanic_crust_subduction_event_count` | `conv >= 0.18` **and** (`plate_changed && local_old_oceanic` **or** `old_oceanic && conv >= 0.26`) | `:1565-1571` |
| `cell.plate_assignment_change_count`, `cell.last_plate_assignment_change_iteration` | `plate_changed` | `:1572-1575` |

The "subducted" flag is a **label**, not a mass transfer. The model states this directly: `oceanic_convergence_subduction_proxy_semantics = "rule_adds_thickness_and_reduces_age_not_a_crust_removal_flux"` and `plate_crossing_accretion_proxy_semantics = "extra_continental_convergence_thickening_not_external_reservoir_provenance"` (`cpp/src/engine/process_serialization.cpp:2933-2936`).

### Process-inventory attribution and its checks

Each reason accumulates three extensive components — `crust_volume_km3` (`area·thickness`), `density_weighted_crust_volume` (`area·thickness·density`), and `crust_age_volume_moment_km3_ma` (`area·thickness·age`) — split into positive and negative magnitudes and reduced in canonical cell order with `long double` (`cpp/src/engine/tectonics.cpp:550-570`, `:1662-1770`).

Three fail-closed forward-error checks guard the result:

| Check | Bound | Failure message | Source |
|---|---|---|---|
| Signed reduction matches positive − negative | `64·ε·(1 + Σpositive + Σnegative)` | `crust process signed inventory reduction exceeded its forward-error bound` | `:1758-1768` |
| Reason-resolved sum matches the direct per-cell transported→final delta | `128·ε·(1 + Σ\|direct\| + Σ\|attributed\|)` | `reason-resolved crust process inventory exceeded its rule-delta forward-error bound` | `:1022-1033` |
| Serialized global inventory difference matches the direct delta | `16·ε·max(1, cell_count)·(1 + \|post\| + \|transported\|)` | `serialized crust process inventory exceeded its accumulation forward-error bound` | `:1034-1045` |

An in-source comment explains the design: *"Validate rule completeness against per-cell transported-to-final state changes. This avoids using the ill-conditioned difference between two large global inventories as the omission detector."* (`cpp/src/engine/tectonics.cpp:931-933`).

The published semantics are explicitly non-physical: `tectonic_process_source_sink_attribution_resolved = false`, `tectonic_process_material_provenance_resolved = false`, `tectonic_process_attribution_order_dependent = true`, and `tectonic_process_source_sink_attribution_semantics = "componentwise_positive_negative_ordered_rule_state_delta_not_physical_material_flux"` (`cpp/src/engine/process_serialization.cpp:2923-2932`).

---

## Tectonic elevation change

The per-cell elevation tendency returned by the motion step is a sum of three parts (`cpp/src/engine/tectonics.cpp:1577-1647`):

```
isostatic_equilibrium_change_m   = 1.0 * (new_isostatic_equilibrium_m − old_isostatic_equilibrium_m)
thermal_equilibrium_change_m     = 1.0 * (new_thermal_subsidence_m    − old_thermal_subsidence_m)

boundary_change                  = 80*(conv − prev_conv) + 55*(div − prev_div) − 30*(trans − prev_trans)
unbounded_dynamic_relief_change_m = tectonic_uplift_rate_m_per_step * 0.42 + boundary_change
bounded_dynamic_relief_change_m   = clamp(unbounded_dynamic_relief_change_m, −180.0, 220.0)

tectonic_elevation_change_m = isostatic_equilibrium_change_m
                            + thermal_equilibrium_change_m
                            + bounded_dynamic_relief_change_m
```

| Constant | Value | Source |
|---|---|---|
| `TECTONIC_ISOSTATIC_TARGET_DIFFERENCE_GAIN` | `1.0` | `cpp/src/engine/internal.hpp:33-34` |
| `OCEANIC_AGE_DEPTH_TARGET_DIFFERENCE_GAIN` | `1.0` | `cpp/src/engine/internal.hpp:31-32` |
| `TECTONIC_UPLIFT_RATE_RESPONSE_FRACTION` | `0.42` | `cpp/src/engine/internal.hpp:37` |
| `TECTONIC_DYNAMIC_RELIEF_MINIMUM_CHANGE_M` | `−180.0` | `cpp/src/engine/internal.hpp:35` |
| `TECTONIC_DYNAMIC_RELIEF_MAXIMUM_CHANGE_M` | `220.0` | `cpp/src/engine/internal.hpp:36` |

**Only the dynamic relief increment is clamped.** The equilibrium terms are applied at full gain, with an explicit in-source rationale: *"Isostatic relaxation is effectively complete on the nominal 5 Ma maturation interval, so equilibrium target changes must not share the empirical per-step relief clamp. Clipping the combined term used to leave kilometre-scale oceanic freeboard behind after a crust-state transition, with no carried residual."* (`cpp/src/engine/tectonics.cpp:1624-1629`). The document mirrors this with `equilibrium_target_difference_clamped = false` and `combined_tectonic_equilibrium_and_dynamic_clamp_present = false` (`cpp/src/engine/process_serialization.cpp:2902-2905`), a timescale-separation basis string, and the Peltier viscoelastic-relaxation reference DOI `10.1111/j.1365-246X.1971.tb01823.x` with a 3,000–4,000 year reference window (`cpp/src/engine/process_serialization.cpp:2890-2897`). Even so, `equilibrium_operator_physical_time_calibrated = false` (`:2903`).

`summarize_plate_motion_step` re-derives all four quantities and **throws** if any recorded value differs by so much as one ULP (`cpp/src/engine/tectonics.cpp:731-804`):

| Failure message | Detects |
|---|---|
| `plate-motion isostatic equilibrium change is non-finite or stale` | recomputed isostatic tendency mismatch |
| `plate-motion thermal checkpoint is non-finite or stale` | `cell.thermal_subsidence_target_m` not equal to `oceanic_age_depth_thermal_subsidence_m(age, oceanic_like)` |
| `plate-motion thermal equilibrium change is non-finite or stale` | recomputed thermal tendency mismatch |
| `plate-motion bounded dynamic relief change is non-finite or stale` | clamp not reproduced |
| `plate-motion tectonic elevation change does not replay` | the three-term sum mismatch |
| `plate-motion equilibrium checkpoint cardinality must equal cell count` | array size mismatch |
| `plate-motion summary cell count exceeds native integer capacity` | `cells.size() > INT_MAX` |

Published as `tectonic_equilibrium_application_replayable = true`, `tectonic_elevation_change_formula = "isostatic_equilibrium_change_m+thermal_equilibrium_change_m+bounded_dynamic_relief_change_m"`, `bounded_dynamic_relief_formula = "clamp(unbounded_dynamic_relief_change_m,-180,220)"` (`cpp/src/engine/process_serialization.cpp:2916-2922`).

---

## The plate motion history record

`plate_motion_history` is a top-level array; record 0 is the identity-overlap initial checkpoint (`stage = "initial_plate_domains"`, `erosion_iteration = -1`) and records 1..N are motion transitions (`stage = "plate_motion_iteration"`, `erosion_iteration = iter + 1`). Serialized by `plate_motion_history_json` (`cpp/src/engine/process_serialization.cpp:3467`).

Precision legend: **H** = `history_precision = max(6, output.float_precision)`, emitted by `add_double` in `std::fixed` notation; **MD** = the same `add_double` path at `max_digits10` digits (`num`, `cpp/src/engine/core.cpp:168-177`); **RT** = `roundtrip_num` / `roundtrip_double_array_json`, i.e. `std::defaultfloat` at `max_digits10` significant digits (exact binary64 round trip); **int** = integer. Note the distinction: inside `plate_motion_history` the *scalars* are **MD**, not **RT** — only the per-cell arrays and the `boundary_segments` records use `roundtrip_*`.

### Step scalars, in emission order

| # | Field | Type | Meaning |
|---|---|---|---|
| 1 | `id` | int | `0` for the initial checkpoint, then `1..erosion_iterations` |
| 2 | `stage` | string | `initial_plate_domains` or `plate_motion_iteration` |
| 3 | `erosion_iteration` | int | `-1` for the checkpoint, else `iter + 1` |
| 4 | `nominal_time_model` | string | `configured_maturation_timestep_nominal_elapsed_time_v1` |
| 5 | `nominal_time_unit` | string | `Ma` |
| 6 | `nominal_time_basis` | string | `configured_maturation_timestep_ma_per_erosion_transition_v1` |
| 7 | `nominal_time_source_parameter` | string | `erosion.maturation_timestep_ma` |
| 8 | `nominal_time_role` | string | `initial_plate_state_snapshot` for record 0, else `plate_motion_transition` |
| 9 | `nominal_interval_start_ma` | MD | interval start; `0` for the checkpoint |
| 10 | `nominal_interval_end_ma` | MD | interval end |
| 11 | `nominal_interval_duration_ma` | MD | `end − start` |
| 12 | `nominal_elapsed_time_ma` | MD | equals `nominal_interval_end_ma` |
| 13 | `advances_nominal_time` | bool | `duration_ma > 0` |
| 14 | `nominal_time_calibrated` | bool | always `false` |
| 15 | `physical_time_resolved` | bool | always `false` |
| 16 | `cell_count` | int | mesh cells |
| 17 | `plate_count` | int | plates |
| 18 | `reassigned_cell_count` | int | cells whose `plate_id` changed this step |
| 19 | `reassigned_cell_fraction` | H | `#18 / cell_count` |
| 20 | `plate_boundary_cell_count` | int | cells with `boundary_type != 0` |
| 21 | `plate_boundary_edge_count` | int | mesh edges crossing a plate boundary (counted once, `j > i`) |
| 22 | `reciprocal_mesh_segment_count` | int | total reciprocal control-volume mesh segments |
| 23 | `boundary_segment_count` | int | cross-plate directed boundary segments |
| 24 | `control_volume_boundary_incident_cell_count` | int | distinct cells incident to a boundary segment |
| 25 | `accreted_terrane_cell_count` | int | cells with `crust_type == 8` |
| 26 | `aged_oceanic_cell_count` | int | size of `aged_oceanic_cell_ids` |
| 27 | `rejuvenated_oceanic_cell_count` | int | size of `rejuvenated_oceanic_cell_ids` |
| 28 | `subducted_oceanic_cell_count` | int | size of `subducted_oceanic_cell_ids` |
| 29 | `mean_plate_rotation_deg` | H | mean of `abs(step_rotation_deg)` over plates |
| 30 | `max_plate_rotation_deg` | H | max of `abs(step_rotation_deg)` |
| 31 | `mean_crust_transport_distance_km` | H | mean over cells of the volume-weighted incoming transport distance |
| 32 | `max_crust_transport_distance_km` | H | max of the same |
| 33 | `mean_abs_crust_age_change_ma` | H | mean `abs(final − previous)` age |
| 34 | `mean_abs_crust_thickness_change_km` | H | mean `abs(final − previous)` thickness |
| 35 | `mean_abs_crust_density_change` | H | mean `abs(final − previous)` density |
| 36 | `mean_abs_crust_age_transport_change_ma` | H | transport-only component |
| 37 | `mean_abs_crust_thickness_transport_change_km` | H | transport-only component |
| 38 | `mean_abs_crust_density_transport_change` | H | transport-only component |
| 39 | `mean_abs_crust_age_process_change_ma` | H | rule-only component |
| 40 | `mean_abs_crust_thickness_process_change_km` | H | rule-only component |
| 41 | `mean_abs_crust_density_process_change` | H | rule-only component |
| 42 | `mean_tectonic_elevation_change_m` | MD | signed mean |
| 43 | `mean_abs_tectonic_elevation_change_m` | MD | absolute mean |
| 44 | `max_abs_tectonic_elevation_change_m` | MD | maximum magnitude |
| 45 | `cell_plate_ids` | int[] | plate id per cell **after** this step |

Field 45 is followed by the three nested ledgers and then the per-cell arrays.

### Nested ledgers, in emission order

| Key | Shape | Documented on |
|---|---|---|
| `crust_overlap_ledger` | object — destination-CSR forward-overlap plan, coverage multiplicity, membership-area classes, remapped crust state, closure residuals, four extensive-inventory objects, and `process_inventory_attribution` | [Crust Transport and Forward Overlap](crust-transport-and-overlap.md) |
| `crust_overlap_candidate_fate_ledger` | object — boundary-pair evidence and per-class candidate contributor roles, with explicit unresolved statuses | [Crust Transport and Forward Overlap](crust-transport-and-overlap.md) |
| `boundary_segments` | array of 60+ field records — exact directed reciprocal control-volume segment geometry and direct Euler kinematics | [Plate Boundary Segment Ledger](plate-boundary-ledger.md) |

Inside `crust_overlap_ledger.process_inventory_attribution.reasons[]` there is exactly one record per `CrustProcessReason`, in the fixed order of `CRUST_PROCESS_REASON_NAMES` (`cpp/src/engine/constants.hpp:86-97`), with fields `reason`, `triggered_cell_count`, `extensive_state_changed_cell_count`, `positive_delta`, `negative_delta_magnitude`, `net_delta` (`cpp/src/engine/process_serialization.cpp:3884-3925`). The reason order is also published at `plate_kinematic_model.tectonic_process_inventory_reason_order` (`cpp/src/engine/process_serialization.cpp:2856-2869`). `extensive_state_changed_cell_count` counts numeric age/thickness/density changes only and explicitly **excludes** categorical transitions (`tectonic_process_changed_cell_count_semantics`, `cpp/src/engine/process_serialization.cpp:2931-2932`).

### Per-cell arrays, in emission order

All arrays are indexed by canonical cell id and length `cell_count`. Every double array below uses **RT** (`roundtrip_double_array_json`, `cpp/src/engine/process_serialization.cpp:4321-4386`).

| # | Array | Type | Meaning |
|---|---|---|---|
| 1 | `crust_type_by_cell` | int[] | post-step crust type id |
| 2 | `lithology_by_cell` | int[] | post-step lithology id |
| 3 | `boundary_convergent_by_cell` | RT[] | post-step smoothed convergent strength |
| 4 | `boundary_divergent_by_cell` | RT[] | post-step smoothed divergent strength |
| 5 | `boundary_transform_by_cell` | RT[] | post-step smoothed transform strength |
| 6 | `crust_transport_distance_km_by_cell` | RT[] | incoming-volume-weighted mean source kinematic distance |
| 7 | `crust_age_change_ma_by_cell` | RT[] | final − previous age |
| 8 | `crust_thickness_change_km_by_cell` | RT[] | final − previous thickness |
| 9 | `crust_density_change_by_cell` | RT[] | final − previous density |
| 10 | `crust_age_transport_change_ma_by_cell` | RT[] | remapped − previous age |
| 11 | `crust_thickness_transport_change_km_by_cell` | RT[] | remapped − previous thickness |
| 12 | `crust_density_transport_change_by_cell` | RT[] | remapped − previous density |
| 13 | `crust_age_process_change_ma_by_cell` | RT[] | final − remapped age |
| 14 | `crust_thickness_process_change_km_by_cell` | RT[] | final − remapped thickness |
| 15 | `crust_density_process_change_by_cell` | RT[] | final − remapped density |
| 16 | `tectonic_elevation_change_m_by_cell` | RT[] | the three-term sum |
| 17 | `previous_local_isostatic_equilibrium_m` | RT[] | pre-step `crust_equilibrium_elevation_m` |
| 18 | `post_process_local_isostatic_equilibrium_m` | RT[] | post-rule `crust_equilibrium_elevation_m` |
| 19 | `isostatic_equilibrium_change_m` | RT[] | gain 1.0 × (18 − 17) |
| 20 | `previous_local_thermal_subsidence_target_m` | RT[] | pre-step age-depth target |
| 21 | `post_process_local_thermal_subsidence_target_m` | RT[] | post-rule age-depth target |
| 22 | `thermal_equilibrium_change_m` | RT[] | gain 1.0 × (21 − 20) |
| 23 | `unbounded_dynamic_relief_change_m` | RT[] | uplift response + boundary change |
| 24 | `bounded_dynamic_relief_change_m` | RT[] | `clamp(23, −180, 220)` |
| 25 | `aged_oceanic_cell_ids` | int[] | ascending cell ids |
| 26 | `rejuvenated_oceanic_cell_ids` | int[] | ascending cell ids |
| 27 | `subducted_oceanic_cell_ids` | int[] | ascending cell ids |

Identity `16 = 19 + 22 + 24` holds exactly, and is re-verified at serialization time by the checks listed above.

### `plates[]` snapshot inside each record

| Field | Type | Meaning |
|---|---|---|
| `plate_id` | int | plate index |
| `center` | MD[3] | rotated Euler center after this step |
| `rotation_axis` | MD[3] | constant Euler axis |
| `intrinsic_angular_speed` | MD | constant `plate.angular_speed` |
| `step_rotation_deg` | MD | this step's rotation in degrees |
| `cumulative_rotation_deg` | H | running total |
| `cell_count` | int | cells assigned to this plate after the step |
| `area_km2` | H | summed control-volume area of those cells |

(`cpp/src/engine/process_serialization.cpp:4390-4410`.)

### Nominal-time placement rules

`nominal_plate_interval` (`cpp/src/engine/process_serialization.cpp:117-132`) accepts only two shapes and throws `plate-motion history stage cannot be placed on the nominal maturation clock` otherwise:

- `id == 0 && stage == "initial_plate_domains"` → the zero interval `{0, 0}`
- `stage == "plate_motion_iteration" && id == erosion_iteration` → `nominal_erosion_interval(params, erosion_iteration)`, i.e. `{(k−1)·maturation_timestep_ma, k·maturation_timestep_ma}`

---

## Plate aggregation and the `plates[]` entity record

`summarize_plates` (`cpp/src/engine/tectonics.cpp:1828-1893`) runs once, late in the pipeline, and produces **area-weighted** means over the final cell state, plus area-argmax dominant categories.

| Aggregate | Definition |
|---|---|
| `cell_count`, `area_km2` | counts and summed `max(0, area_km2)` |
| `mean_crust_age_ma`, `mean_crust_density`, `mean_crust_thickness_km` | `Σ value·area / Σ area` |
| `mean_boundary_activity` | `Σ max(conv, div, trans)·area / Σ area` |
| `mean_heat_flow_mw_m2` | `Σ approximate_heat_flow_mw_m2·area / Σ area` |
| `dominant_crust_type` | argmax over 9 crust-type area bins |
| `dominant_lithology` | argmax over 7 lithology area bins |

`approximate_heat_flow_mw_m2` (`cpp/src/engine/tectonics.cpp:1808-1826`):

```
age_heat      = oceanic_like ? 45 + 95*exp(-age/60)     : 38 + 34*exp(-age/1400)
boundary_heat = 55*divergent + 30*convergent + 18*transform + (crust_type == 3 ? 24 : 0)
heat_flow     = clamp(internal_heat * (age_heat + boundary_heat), 18, 240)   // mW/m^2
```

The zero-area fallback (`cpp/src/engine/tectonics.cpp:1884-1891`) substitutes the plate-level nominal density and thickness, `crust_age_ceiling_ma(params, kind == 0 ? 120 : 1600)` for the mean age, and a flat `kind == 0 ? 62.0 : 54.0` mW/m² for the mean heat flow. In practice `assign_plates` already throws on an empty domain (`cpp/src/engine/tectonics.cpp:85-92`), so this is defensive only.

### `plates[]` — full field table (19 fields, emission order)

Serialized by `plates_json` (`cpp/src/engine/entity_serialization.cpp`). `G` = `geometry_precision = max(max_digits10, output.float_precision)`; `P` = `output.float_precision`.

| # | Field | Type | Notes |
|---|---|---|---|
| 1 | `id` | int | plate index |
| 2 | `kind` | string | `oceanic` (0), `continental` (1), `mixed` (2) |
| 3 | `axis` | double[3] G | Euler rotation axis (constant) |
| 4 | `initial_center` | double[3] G | seed cell position |
| 5 | `center` | double[3] G | final rotated center |
| 6 | `angular_speed` | double G | intrinsic index, already multiplied by `tectonic_activity` |
| 7 | `cumulative_rotation_deg` | double P | total degrees rotated over the run |
| 8 | `crust_density` | double P | nominal density by kind (3.00 / 2.72 / 2.84) |
| 9 | `crust_thickness_km` | double P | nominal thickness by kind (7 / 34 / 22) |
| 10 | `cell_count` | int | final assigned cells |
| 11 | `area_km2` | double P | final assigned control-volume area |
| 12 | `mean_crust_age_ma` | double P | area-weighted |
| 13 | `mean_crust_density` | double P | area-weighted |
| 14 | `mean_crust_thickness_km` | double P | area-weighted |
| 15 | `dominant_crust_type` | string | `CRUST_NAMES[argmax]` |
| 16 | `dominant_lithology` | string | `LITHOLOGY_NAMES[argmax]` |
| 17 | `mean_boundary_activity` | double P | area-weighted max of the three strengths |
| 18 | `mean_heat_flow_mw_m2` | double P | area-weighted `approximate_heat_flow_mw_m2` |
| 19 | `thermal_state` | string | `hot_active` if `>= 95`, `warm_active` if `>= 65`, else `cool_stable` |

Field 19 is a threshold label computed at serialization time, not stored on the `Plate` struct.

---

## Per-cell tectonic fields in the world document

From `cells_json` (`cpp/src/engine/entity_serialization.cpp:110-185`). `P` = `output.float_precision`; `S` = `surface_precision = max(10, P)`; `RT` = exact binary64 round trip.

| Field | Type | Set by |
|---|---|---|
| `plate_id` | int | `assign_plates` (re-run every motion step) |
| `initial_plate_id` | int | `derive_crust_and_topography` (`tectonics.cpp:506`) |
| `plate_assignment_change_count` | int | motion step, on `plate_changed` |
| `last_plate_assignment_change_iteration` | int | motion step, `erosion_iteration` value |
| `oceanic_crust_aging_event_count` | int | rule-0 event flag |
| `oceanic_crust_rejuvenation_event_count` | int | rule-1 event flag |
| `oceanic_crust_subduction_event_count` | int | subduction label flag |
| `cumulative_crust_transport_distance_km` | double P | running sum of per-step transport distance |
| `crust_type` | string | `CRUST_NAMES[id]` |
| `lithology` | string | `LITHOLOGY_NAMES[id]` |
| `boundary_type` | string | `BOUNDARY_NAMES[id]` |
| `boundary_convergent` | double P | smoothed strength |
| `boundary_divergent` | double P | smoothed strength |
| `boundary_transform` | double P | smoothed strength |
| `crust_age_ma` | RT | replay-critical |
| `crust_thickness_km` | RT | replay-critical |
| `crust_density` | RT | replay-critical |
| `cumulative_tectonic_elevation_change_m` | double S | running sum of `tectonic_elevation_change_m` |
| `initial_isostatic_elevation_m` | double S | initial pass only |
| `thermal_subsidence_target_m` | RT | recomputed every motion step |
| `initial_ridge_uplift_m` | double S | initial pass only |
| `initial_orogenic_uplift_m` | double S | initial pass only |
| `initial_volcanic_uplift_m` | double S | initial pass only |
| `initial_trench_subsidence_m` | double S | initial pass only |
| `initial_rift_subsidence_m` | double S | initial pass only |
| `initial_transform_fault_relief_m` | double S | initial pass only |
| `initial_secondary_roughness_m` | double S | initial pass only |
| `initial_elevation_m` | double S | sum of the nine components |
| `tectonic_uplift_rate_m_per_step` | double P | `cell.uplift_rate`, recomputed every step |
| `volcanic_potential_index` | double P | recomputed every step |

The eight `initial_*` relief components are frozen at generation and are **not** updated by subsequent motion steps; only `cumulative_tectonic_elevation_change_m`, `thermal_subsidence_target_m`, `tectonic_uplift_rate_m_per_step`, and `volcanic_potential_index` track the evolving state.

---

## Python enrichers: tectonic zones, fault systems, geology realism

Three Python enrichers consume the native tectonic state. They run early in both `generate_world` (positions 7–9, `src/magic_geo/api.py:206-208`) and `generate_geo_world` (positions 4–6, `src/magic_geo/api.py:313-315`), in the execution order `enrich_world_with_geology_realism` → `enrich_world_with_tectonic_zones` → `enrich_world_with_fault_systems`. All three are **diagnostic**: they add derived fields and records, and none of them mutates native crust state.

`enrich_world_with_tectonic_zones` and `enrich_world_with_fault_systems` read `world["cell_adjacency_edges"]` (`src/magic_geo/tectonic_zones.py:246`, `src/magic_geo/fault_systems.py:203`), which is produced upstream by `enrich_world_with_cell_geometry` (`src/magic_geo/cell_geometry.py:505`). If it is absent they simply see zero plate-boundary edges. `enrich_world_with_geology_realism` does not read that key at all — it works from `cells[].neighbors` only.

### `enrich_world_with_tectonic_zones` — `src/magic_geo/tectonic_zones.py:241`

Classifies each cell into three affinity scores, then connected-component-groups the qualifying cells.

**Zone strength formulas** (`src/magic_geo/tectonic_zones.py:42-76`), all clamped to `[0, 1]`. Normalizers: `orogenic = clamp(initial_orogenic_uplift_m / 2600)`, `trench = clamp(abs(initial_trench_subsidence_m) / 2600)`, `rift = clamp(abs(initial_rift_subsidence_m) / 1200)`.

| Zone type | Formula |
|---|---|
| `collision` | `0.58·convergent + 0.20·[crust_type == orogen] + 0.10·[lithology == metamorphic] + 0.08·[landform == mountain_belt] + 0.12·orogenic` |
| `subduction` | `0.50·convergent + 0.18·[crust_type == volcanic_arc] + 0.12·[landform ∈ {volcanic_arc, trench}] + 0.12·volcanic_potential_index + 0.08·trench` |
| `rift` | `0.62·divergent + 0.18·[crust_type == rift_basin] + 0.12·[landform == rift_valley] + 0.08·rift` |

**Candidacy threshold:** `strength >= 0.34` (`src/magic_geo/tectonic_zones.py:86`).

**Grouping:** BFS connected components over `cells[].neighbors`, components sorted by `(len, first_id)` descending (`src/magic_geo/tectonic_zones.py:91-109`).

**Cell fields added** (`src/magic_geo/tectonic_zones.py:249-281`):

| Field | Default | Meaning |
|---|---|---|
| `collision_zone_id` | `-1` | local id inside `collision_zones` |
| `subduction_zone_id` | `-1` | local id inside `subduction_zones` |
| `rift_zone_id` | `-1` | local id inside `rift_zones` |
| `dominant_tectonic_zone_type` | `"none"` | zone type with the highest strength on this cell |
| `tectonic_zone_strength` | `0.0` | that highest strength, rounded to 6 decimals |

**World keys added:** `collision_zones`, `subduction_zones`, `rift_zones`, and the merged `tectonic_zones` (union with a global `id` plus `local_zone_id`, iterated in `ZONE_TYPES = ("collision", "subduction", "rift")` order).

**Zone record fields** (`src/magic_geo/tectonic_zones.py:186-224`): `id`, `zone_type`, `cell_ids`, `cell_count`, `area_km2`, `boundary_edge_ids`, `boundary_edge_count`, `boundary_length_km`, `plate_ids`, `plate_pair_ids`, `mean_zone_strength`, `max_zone_strength`, `representative_cell_id`, `centroid_lat_deg`, `centroid_lon_deg`, `mean_boundary_convergent`, `mean_boundary_divergent`, `mean_boundary_transform`, `mean_elevation_m`, `mean_crust_thickness_km`, `mean_crust_age_ma`, `dominant_crust_type`, `dominant_lithology`, `dominant_landform`, and a nested `formation_evidence` object with `high_convergent_cell_count`, `high_divergent_cell_count`, `orogen_cell_count`, `volcanic_arc_cell_count`, `rift_basin_cell_count`. Means are area-weighted (`divisor = area` when positive, else the cell count). `boundary_length_km` sums `boundary_segment_length_km` (falling back to `great_circle_distance_km`) over the incident plate-boundary edges.

**Summary keys added:** `tectonic_zone_count`, `collision_zone_count`, `subduction_zone_count`, `rift_zone_count`, `collision_zone_cell_count`, `subduction_zone_cell_count`, `rift_zone_cell_count`, `tectonic_zone_total_area_km2`, `tectonic_zone_boundary_length_km`, `mean_tectonic_zone_strength` (`src/magic_geo/tectonic_zones.py:283-295`).

Note that the three zone families are computed independently, so a cell can belong to more than one zone; `dominant_tectonic_zone_type` resolves the ambiguity by picking the strongest.

### `enrich_world_with_fault_systems` — `src/magic_geo/fault_systems.py:198`

**Per-cell metrics** (`src/magic_geo/fault_systems.py:55-74`), each clamped to `[0, 1]` unless noted. Inputs: `boundary_transform/convergent/divergent`, `initial_transform_fault_relief_m`, `elevation_m`, `initial_elevation_m`, `volcanic_potential_index`, plus the fraction of a cell's adjacency edges flagged `plate_boundary`.

```
boundary_activity = max(transform, convergent, divergent)
boundary_fraction = plate_boundary_edge_count / valid_edge_count            # 0.0 when no edges
transform_relief  = clamp(abs(initial_transform_fault_relief_m) / 900)
ruggedness        = clamp(abs(elevation_m - initial_elevation_m) / 1800)

fault_slip_rate_index = clamp(0.58*transform + 0.18*max(convergent, divergent)
                              + 0.12*boundary_fraction + 0.08*transform_relief
                              + 0.04*ruggedness)

seismic_hazard_index  = clamp(0.56*slip + 0.22*convergent + 0.10*divergent
                              + 0.06*volcanic_potential_index + 0.06*boundary_activity)

earthquake_recurrence_interval_y = 0.0 if hazard < 0.08 else 35.0 + (1.0 - hazard)*965.0
```

The recurrence formula is a linear inverse map with an explicit dead band. `hazard = 1` gives exactly `35` years; the dead-band edge `hazard = 0.08` gives `35 + 0.92·965 = 922.8` years; below `0.08` the value is forced to `0.0`. The attainable non-zero range is therefore `[35, 922.8]` years — the `1000`-year `hazard = 0` limit of the linear expression is never emitted. The expression is linear in `hazard`, not a magnitude–frequency law, and the source carries no seismological citation for it.

**Cell fields added:** `fault_slip_rate_index`, `seismic_hazard_index`, `earthquake_recurrence_interval_y`, `fault_system_id` (default `-1`).

**Candidacy:** `slip >= 0.30 or hazard >= 0.35` (`src/magic_geo/fault_systems.py:226-227`), then BFS connected components on `neighbors`.

**World key added:** `fault_systems`, whose records carry `id`, `cell_ids`, `cell_count`, `area_km2`, `boundary_edge_ids`, `boundary_edge_count`, `boundary_length_km`, `plate_ids`, `plate_pair_ids`, `mean_fault_slip_rate_index`, `max_fault_slip_rate_index`, `mean_seismic_hazard_index`, `max_seismic_hazard_index`, `mean_earthquake_recurrence_interval_y`, `representative_cell_id`, `centroid_lat_deg`, `centroid_lon_deg`, `dominant_boundary_type`, `dominant_crust_type`, `dominant_landform`, `transform_fault_cell_count`, `convergent_fault_cell_count`, `divergent_fault_cell_count` (`src/magic_geo/fault_systems.py:166-195`). The three per-type counts use a `0.28` threshold (transform additionally accepts `boundary_type == "transform"`).

**Summary keys added:** `fault_system_count`, `fault_system_cell_count`, `fault_system_total_area_km2`, `fault_system_boundary_length_km`, `mean_fault_slip_rate_index`, `mean_seismic_hazard_index`, `high_seismic_hazard_cell_count` (threshold `hazard >= 0.55`), `mean_earthquake_recurrence_interval_y` (averaged over cells with a non-zero interval only) (`src/magic_geo/fault_systems.py:238-247`).

### `enrich_world_with_geology_realism` — `src/magic_geo/geology_realism.py:127`

Six pass/fail plausibility checks over the native crust and relief state. Each check is scored by `_score_range(value, target_min, target_max)`: `1.0` inside the band, otherwise `clamp(1 − distance / band_width)` (`src/magic_geo/geology_realism.py:21-26`). `passed` is the strict band test.

| Check `name` | `metric` | Value definition | `target_min` | `target_max` |
|---|---|---|---|---|
| `mountain_convergent_alignment` | `fraction_high_mountains_near_convergence` | fraction of land cells at or above `max(1600, P88 of land elevation)` that have cell-or-one-hop `boundary_convergent >= 0.25`, or `crust_type == orogen` | `0.55` | `1.0` |
| `trench_convergent_alignment` | `fraction_trenches_near_convergence` | fraction of trench candidates near convergence; a candidate is `landform == "trench"` or (water and `boundary_convergent >= 0.45` and `water_depth_m >= 700`) | `0.60` | `1.0` |
| `oceanic_ridge_divergent_alignment` | `fraction_shallow_oceanic_highs_near_divergence` | among oceanic-ish water cells (`water_body_type ∈ {ocean, continental_shelf, inland_sea}` and `crust_type ∈ {oceanic, rift_basin, transitional}`), the fraction of the shallowest quartile with `boundary_divergent >= 0.25` or `crust_type == rift_basin` | `0.20` | `1.0` |
| `volcanic_arc_trench_pairing` | `fraction_volcanic_arcs_with_trench_pairing` | fraction of volcanic-arc cells with a trench candidate within two graph hops, or (`boundary_convergent >= 0.25` and a water neighbor with `boundary_convergent >= 0.20`) | `0.35` | `1.0` |
| `transform_fault_linearity` | `fraction_transform_cells_with_two_transform_neighbors` | among cells with `boundary_transform >= 0.35` or `boundary_type == "transform"`, the fraction with at least two transform-like neighbors (`>= 0.30` or labelled transform) | `0.55` | `1.0` |
| `hypsometry_bimodality` | `between_land_ocean_elevation_variance_fraction` | between-group (land vs. water) elevation variance divided by total variance; `0.0` if either group is empty | `0.35` | `1.0` |

Empty candidate sets score `1.0` by construction (e.g. no mountain cells → `mountain_alignment = 1.0`).

Each record carries `id`, `domain: "geology"`, `name`, `question`, `metric`, `value`, `target_min`, `target_max`, `score`, `passed`, and a check-specific `evidence` object (`src/magic_geo/geology_realism.py:33-59`). All values are rounded to 6 decimals.

**World key added:** `geology_realism_checks`. **Summary keys added:** `mountain_convergent_alignment`, `trench_convergent_alignment`, `oceanic_ridge_divergent_alignment`, `volcanic_arc_trench_pairing`, `transform_fault_linearity`, `hypsometry_bimodality_index`, `geology_realism_check_count`, `geology_realism_pass_count`, `geology_realism_pass_fraction`, `mean_geology_realism_score` (`src/magic_geo/geology_realism.py:312-322`).

### Layer contract

The geo layer contract registry places these products in phase 2 and phase 3 (`src/magic_geo/geo_layer_contracts.py:56-95`):

| Layer id | Phase | Required outputs | Validator domains |
|---|---|---|---|
| `plate_tectonics` | 2 | `plates`, `plate_kinematic_model`, `plate_boundary_segment_model`, `crust_overlap_candidate_fate_model`, `plate_motion_history`, `tectonic_zones`, `fault_systems` | `tectonics`, `tectonic_zones_faults` |
| `crust_lithology` | 3 | `cells`, `plate_motion_history`, `initial_oceanic_crust_age_model`, `initial_oceanic_crust_age_ledger`, `crust_material_shadow_model`, `crust_material_shadow_history`, `crust_dry_rock_accounting_model`, `crust_dry_rock_accounting_history`, `sediment_inventory_model` | `tectonics`, `simulation` |

The `plate_tectonics` evidence class is stated verbatim as *"exact_directed_control_volume_segment_kinematics_and_pair_wide_diagnostic_overlap_candidate_crosswalk_replay_without_local_fragment_link_allocation_physical_polarity_or_slab_transfer"* (`src/magic_geo/geo_layer_contracts.py:72-76`).

---

## Tectonics configuration reference

All eight properties live under the `tectonics:` section of the YAML config, modelled by `TectonicsConfig` (`src/magic_geo/config.py:258`). The model sets `extra="forbid"` and `allow_inf_nan=False`, so unknown keys and NaN/Inf are rejected.

| Property | Type | Default | Range | Native validation | Effect |
|---|---|---|---|---|---|
| `plate_count` | int | `14` | `>= 2`, `<= 256`; cross-check `< mesh.cell_count` | `plate_count must be between 2 and 256 and smaller than cell_count`; the pipeline additionally throws `plate_count must be smaller than generated mesh cell count` against the **generated** mesh size | Number of Euler poles seeded. Higher values create more boundaries and more `plate_boundary_edge_count`; too high relative to `cell_count` risks the empty-domain throw once centers rotate. |
| `continental_plate_fraction` | float | `0.38` | `>= 0.0`, `<= 1.0` | `continental_plate_fraction must be between 0 and 1` | Probability a plate's kind draw lands on `continental` (kind 1). The next `0.22` of probability mass becomes `mixed` (kind 2); the remainder is `oceanic` (kind 0). Feeds `plate_bias` in the continental score (0.72 / 0.48 / 0.17) and the nominal per-plate density/thickness. |
| `continental_crust_fraction_target` | float | `0.34` | `>= 0.0`, `<= 0.95` | `continental_crust_fraction_target must be between 0 and 0.95` | Exact rank cut: the top `round(target · cell_count)` cells by continental score get the continental mask. Realized **cell** fraction is exact up to rounding; realized **area** fraction is approximate. |
| `min_angular_speed` | float | `0.03` | `>= 0.0`, `<= 100.0`; `<= max_angular_speed` | `angular speeds must be between 0 and 100 and max_angular_speed must be >= min_angular_speed` | Lower bound of the uniform draw for `plate.angular_speed`, before multiplication by `tectonic_activity`. Sets a floor on per-step rotation and on the magnitude of relative Euler velocities driving boundary forcing. |
| `max_angular_speed` | float | `0.95` | `>= 0.0`, `<= 100.0` | same as above; the Pydantic model validator raises `max_angular_speed must be >= min_angular_speed` (`src/magic_geo/config.py:312-316`) | Upper bound of the same draw. Widening the range increases the spread of plate speeds, boundary strength contrast, and the transport distance per step. |
| `boundary_smoothing_steps` | int | `5` | `>= 0`, `<= 32` | `boundary_smoothing_steps must be between 0 and 32` | Number of Jacobi neighbor-average passes applied to each of the three boundary strength fields (self weights 0.58 / 0.58 / 0.62). `0` returns the raw degree-normalized fields untouched. More steps widen and soften boundary belts, which in turn widens orogens, trenches and rifts in the initial relief. |
| `plate_motion_scale_deg_per_step` | float | `2.0` | `>= 0.0`, `<= 10.0` | `plate_motion_scale_deg_per_step must be between 0 and 10` | Degrees of center rotation per **five-million-year reference step**, multiplied by `plate.angular_speed` and `maturation_timestep_scale`. Also sets the nominal boundary-segment velocity scale `radius_km·scale·(π/180)/5 Ma`. `0.0` freezes the domains: centers never move, no cell is reassigned, and every eligible ridge segment has a zero opening rate — the initial oceanic age field then falls entirely into the `unresolved_no_active_ridge_path_ceiling` status. |
| `oceanic_crust_aging_ma_per_step` | float | `5.0` | `>= 0.0`, `<= 50.0` | `oceanic_crust_aging_ma_per_step must be between 0 and 50` | Ma added to quiet oceanic crust (`div < 0.10` and `conv < 0.10`) per reference step, scaled by `maturation_timestep_scale` and by `quiet_fraction = clamp(1 − max(div,conv)/0.10, 0, 1)`. Drives thermal subsidence through the age–depth target and therefore ocean-basin bathymetry. |

Native validation lives in `validate_params` (`cpp/src/engine/core.cpp:239`). The six floating-point properties — `continental_plate_fraction`, `continental_crust_fraction_target`, `min_angular_speed`, `max_angular_speed`, `plate_motion_scale_deg_per_step`, `oceanic_crust_aging_ma_per_step` — additionally pass a `require_finite` check before the range checks (`cpp/src/engine/core.cpp:257-271`), each throwing `<name> must be finite`. The two integer properties, `plate_count` and `boundary_smoothing_steps`, have no finite check; Pydantic's `allow_inf_nan=False` and the int type already exclude NaN/Inf on the Python side.

Two profiles override tectonics defaults (`src/magic_geo/config.py:513`): `earthlike` sets `tectonics.plate_motion_scale_deg_per_step = 4.0`; `smoke` sets `tectonics.plate_count = 8` and `tectonics.plate_motion_scale_deg_per_step = 4.0`.

### Cross-section interactions

| Other property | Interaction |
|---|---|
| `mesh.cell_count` | Must exceed `plate_count`; also sets the graph resolution of the age Dijkstra and the granularity of the continental rank cut. |
| `erosion.iterations` | Number of motion transitions. `plate_motion_history` has `iterations + 1` records. |
| `erosion.maturation_timestep_ma` | Divided by `5.0` to give `maturation_timestep_scale`, which scales rotation, quiet aging, uplift rate, and the continuous crust rules. |
| `erosion.tectonic_uplift_scale` | Multiplies `tectonic_uplift_rate_m_per_step`, hence the dynamic relief increment. |
| `planet.internal_heat`, `planet.geological_age_ga` | Enter `tectonic_activity`, which scales angular speeds, rifting/orogeny magnitudes, and heat flow. `geological_age_ga` also caps every crust age via `crust_age_ceiling_ma`. |
| `planet.gravity_g` | Enters `relief_scale = clamp(1/sqrt(max(0.08, g)), 0.55, 1.60)`, which multiplies **five** of the nine initial relief components — ridge uplift, rift subsidence, orogenic uplift, trench subsidence, volcanic uplift. The isostatic, thermal-subsidence, transform-fault and secondary-roughness terms are not scaled by it (`cpp/src/engine/tectonics.cpp:436-485`). |
| `planet.radius_km` | Sets the graph edge distances in the age field and the nominal boundary-segment velocity scale. |
| `output.include_cells` | Must be `true` for the initial-age replay validator to run; `generate_geo_world` raises `ValueError` if it is `false`. |
| `output.float_precision` | Sets the presentation precision of `H`- and `P`-class fields. Replay-critical tectonic fields ignore it and use `max_digits10`. |

---

## Worked examples

### Generate and inspect the tectonic layer

```bash
magic-geo init-config --profile earthlike --output magic-geo.yaml
magic-geo generate --config magic-geo.yaml --output runs/world.json
magic-geo validate --world runs/world.json
```

### Read the initial oceanic age ledger

```python
import json

world = json.load(open("runs/world.json"))
ledger = world["initial_oceanic_crust_age_ledger"]
model = world["initial_oceanic_crust_age_model"]

print(model["model_type"])                                    # multi_source_nominal_ridge_graph_travel_time_v1
print(model["shortest_path_model"])                           # multi_source_dijkstra_over_oceanic_like_cell_neighbor_graph
print(ledger["representative_half_spreading_rate_km_per_ma"])
print(ledger["eligible_ridge_segment_count"], ledger["ridge_seed_cell_count"])

from collections import Counter
status_names = ["not_oceanic_like", "ridge_seed", "ridge_reachable",
                "ridge_reachable_ceiling_clamped",
                "unresolved_no_active_ridge_path_ceiling"]
print(Counter(status_names[s] for s in ledger["status_id_by_cell"]))

# Area-weighted CDF: fraction of oceanic-like area at or below each threshold.
for threshold, fraction in zip(ledger["cdf_thresholds_ma"],
                               ledger["area_weighted_cdf_le_threshold"]):
    print(f"<= {threshold:6.1f} Ma : {fraction:.4f}")
```

### Independently replay the age field

```python
import json
from magic_geo.initial_oceanic_crust_age_validation import validate_initial_oceanic_crust_age

world = json.load(open("runs/world.json"))
result = validate_initial_oceanic_crust_age(world)
print(result["passed"])
print(result["metrics"]["maximum_absolute_age_replay_residual_ma"])
print(result["metrics"]["dijkstra_queue_push_count"])
for failure in result["failures"]:
    print("FAIL", failure)
```

### Verify the tectonic elevation identity on a motion step

```python
import json

world = json.load(open("runs/world.json"))
step = world["plate_motion_history"][1]           # first motion transition
total = step["tectonic_elevation_change_m_by_cell"]
iso   = step["isostatic_equilibrium_change_m"]
therm = step["thermal_equilibrium_change_m"]
dyn   = step["bounded_dynamic_relief_change_m"]

assert all(t == i + h + d for t, i, h, d in zip(total, iso, therm, dyn))

# The bounded term is the clamp of the unbounded one.
unb = step["unbounded_dynamic_relief_change_m"]
assert all(d == min(220.0, max(-180.0, u)) for d, u in zip(dyn, unb))
```

### Read the per-reason crust process inventory

```python
import json

world = json.load(open("runs/world.json"))
step = world["plate_motion_history"][1]
attribution = step["crust_overlap_ledger"]["process_inventory_attribution"]

print(attribution["order_dependent"])
for reason in attribution["reasons"]:
    print(f"{reason['reason']:38s} "
          f"triggered={reason['triggered_cell_count']:6d} "
          f"changed={reason['extensive_state_changed_cell_count']:6d} "
          f"net_volume_km3={reason['net_delta']['crust_volume_km3']:+.6e}")
```

### Inspect zones and faults

```python
import json

world = json.load(open("runs/world.json"))
print(world["summary"]["tectonic_zone_count"],
      world["summary"]["collision_zone_count"],
      world["summary"]["subduction_zone_count"],
      world["summary"]["rift_zone_count"])
print(world["summary"]["fault_system_count"],
      world["summary"]["mean_seismic_hazard_index"])

for check in world["geology_realism_checks"]:
    flag = "PASS" if check["passed"] else "FAIL"
    print(f"{flag} {check['name']:36s} {check['value']:.4f} "
          f"target [{check['target_min']}, {check['target_max']}]")
```

### Freeze the plates (diagnostic configuration)

```bash
magic-geo generate --config magic-geo.yaml \
  --output runs/frozen.json
# equivalently, in magic-geo.yaml:
#   tectonics:
#     plate_motion_scale_deg_per_step: 0.0
```

With `plate_motion_scale_deg_per_step: 0.0` the centers never rotate, `reassigned_cell_count` is `0` on every step, every boundary segment reports a zero opening rate, and consequently **no** eligible ridge segment exists: `representative_half_spreading_rate_km_per_ma` is `0.0` and every oceanic-like cell receives status `4` (`unresolved_no_active_ridge_path_ceiling`) at the effective age ceiling. This is a deliberate, explicit degeneracy of the model, not a bug.

---

## Limitations and unresolved claims

These are carried forward verbatim in substance from the source and the serialized model contracts. Do not upgrade any of them.

1. **Physical time is not resolved and the nominal clock is not calibrated.** `plate_kinematic_model.physical_time_resolved = false`, `nominal_time_calibrated = false`, `process_rate_calibration_resolved = false`, `time_step_convergence_demonstrated = false` (`cpp/src/engine/process_serialization.cpp:2686-2689`). Every `plate_motion_history` record repeats `nominal_time_calibrated = false` and `physical_time_resolved = false` (`cpp/src/engine/process_serialization.cpp:158-159`). The nominal clock is a bookkeeping coordinate derived from `erosion.maturation_timestep_ma`, nothing more.

2. **Subduction polarity is explicitly unknown.** The boundary-segment record separates a *candidate* pair from a physical decision; the type comment states: *"Candidate sides are deliberately separate from the physical decision. Until a supplied constraint or a physical solver exists, convergent segments stay explicitly unknown and cannot select a slab."* (`cpp/src/engine/types/earth_system.hpp:510-512`). In `plate_boundary_segment_model` the flags `polarity_candidate_is_physical_decision`, `physical_subduction_polarity_resolved`, `physical_slab_geometry_resolved`, `slab_selection_resolved`, `slab_transfer_resolved` and `physical_material_fate_resolved` are all serialized `false`, while `physical_polarity_unknown_state_explicit` is `true` (`cpp/src/engine/process_serialization.cpp:3138-3144`). Each segment record still carries `polarity_candidate_status` / `candidate_subducting_side` / `candidate_overriding_side` alongside the separate `physical_polarity_status` / `physical_subducting_side` / `physical_overriding_side` / `physical_polarity_confidence` fields (`cpp/src/engine/process_serialization.cpp:4230-4318`).

3. **The "subduction" rule is a label, not a mass sink.** `oceanic_convergence_subduction_proxy_semantics = "rule_adds_thickness_and_reduces_age_not_a_crust_removal_flux"`; `plate_crossing_accretion_proxy_semantics = "extra_continental_convergence_thickening_not_external_reservoir_provenance"` (`cpp/src/engine/process_serialization.cpp:2933-2936`). `subducted_oceanic_cell_ids` records cells that satisfied a threshold condition; no crust leaves the surface inventory because of it.

4. **Process attribution is order-dependent and is not a material flux.** `tectonic_process_attribution_order_dependent = true`, `tectonic_process_source_sink_attribution_resolved = false`, `tectonic_process_material_provenance_resolved = false`, and the semantics string reads *"componentwise_positive_negative_ordered_rule_state_delta_not_physical_material_flux"* (`cpp/src/engine/process_serialization.cpp:2923-2932`). Reordering the rules would reallocate the per-reason ledger even for an identical final state.

5. **The initial seafloor age field is a graph travel-time construction, not a reconstruction.** Stated limitation: *"procedural_graph_distance_age_initialization_using_one_global_nominal_half_spreading_rate_without_physical_plate_reconstruction_flowlines_or_crust_creation_and_destruction_history"* (`cpp/src/engine/process_serialization.cpp:2504-2505`). All of `physical_seafloor_creation_resolved`, `spreading_rate_calibrated`, `local_spreading_rates_resolved`, `ridge_flowlines_resolved`, `subduction_sink_history_resolved`, `convergence_history_resolved` are `false` (`:2497-2502`). The Seton et al. (2020) grid is **not** a generation input (`seton_2020_age_grid_used_as_generation_input = false`, `:2503`); it appears only in the calibration/validation direction.

6. **One global half-rate.** Every oceanic-like graph edge is divided by the same `representative_half_spreading_rate_km_per_ma`. There are no per-ridge, per-segment, or asymmetric spreading rates in this field (`cpp/src/engine/initial_oceanic_age.cpp:216-222`).

7. **The 200 Ma ceiling is procedural, not physical.** *"A 200 Ma procedural ceiling covers the dominant present-day seafloor-age distribution but is not a physical maximum: the pinned Seton et al. (2020) grid contains a rare older tail to about 339 Ma."* (`cpp/src/engine/constants.hpp:37-41`). Ceiling-clamped and unreachable cells stay explicitly labelled (statuses 3 and 4) rather than being silently blended in.

8. **Extinct-basin handling is an admitted gap.** *"An oceanic graph component without an active divergent segment represents an unresolved extinct basin. Assigning the procedural model ceiling is explicit and avoids inventing a ridge or claiming a physical maximum seafloor age."* (`cpp/src/engine/initial_oceanic_age.cpp:251-254`).

9. **Independent replay of the age field is conditional.** `independent_replay_inputs_unconditionally_exposed = false`, `independent_replay_requires_cells_output = true` (`cpp/src/engine/process_serialization.cpp:2494-2496`). With `output.include_cells: false` the age ledger cannot be re-derived from the document.

10. **Crust transport is first-order and diffusive.** `crust_transport_limitation = "first_order_overlap_is_diffusive_and_boundary_creation_subduction_remain_rule_based_process_inventory_changes"` (`cpp/src/engine/process_serialization.cpp:2937-2938`). Conservation is claimed only for the transport half-step: `mass_conservation_scope = "transport_only_before_rule_based_tectonic_processes"` (`:2842-2843`).

11. **The overall kinematic model limitation** is published as *"kinematic_domains_with_conservative_first_order_crust_transport_rule_based_boundary_processes_partial_reference_timestep_scaling_and_uncalibrated_physical_time"* (`cpp/src/engine/process_serialization.cpp:2939-2940`). Note *partial* reference-timestep scaling: several rules branch on `timestep_scale == 1.0` and use a different formula off the reference step (`cpp/src/engine/tectonics.cpp:1347-1352`, `:1378-1386`, `:1399-1408`, `:1447-1483`).

12. **The equilibrium operator is not time-calibrated** even though it is applied at full gain. `equilibrium_operator_physical_time_calibrated = false` (`cpp/src/engine/process_serialization.cpp:2903`). The timescale-separation argument cites a 3–4 ka viscoelastic relaxation estimate against the nominal 5 Ma step (`:2890-2897`), but that is a justification for the operator's form, not a calibration of it.

13. **Accelerator parity is not asserted here.** `assign_plates` and the boundary smoothers may run on OpenCL or CUDA when the session selects one; the contract only guarantees a *complete* host result or a clean CPU fallback (`cpp/src/opencl_compute.hpp:32-35`). Separately, `reconcile_accelerated_crust_overlap_continuous_shadow` is documented as a *diagnostic-only device replay whose output is validated against the CPU plan and discarded* — the CPU overlap plan is authoritative and the device path never mutates it (`cpp/src/opencl_compute.hpp:64-74`).

14. **The continental target is a cell-count cut, not an area cut**, despite the configuration description naming area (`cpp/src/engine/tectonics.cpp:341-345` versus `src/magic_geo/config.py:275-280`). On a mesh with non-uniform cell areas the realized area fraction will differ from `continental_crust_fraction_target`.

15. **Boundary strengths are dimensionless indices.** `boundary_convergent/divergent/transform` come from the intrinsic angular-speed index, degree-normalized by a hard-coded `3.2` gain and smoothed on the graph (`cpp/src/engine/tectonics.cpp:143-158`). They are not rates. The only nominal km/Ma kinematics in the tectonic stack are the direct, unsmoothed per-segment values in the boundary ledger, and those are explicitly uncalibrated.

16. **Zone, fault and realism enrichers are diagnostics.** They read the native state and add derived scores with hand-chosen thresholds (`0.34` zone candidacy, `0.30`/`0.35` fault candidacy, `0.55` high hazard, the six realism target bands). Nothing in these modules feeds back into crust state or elevation, and none of their indices is calibrated against an observational dataset. `earthquake_recurrence_interval_y` in particular is a linear inverse map of a bounded hazard index onto `[35, 922.8]` years above a `0.08` dead band, not a seismological recurrence estimate.

17. **`plate.axis` and `plate.center` are independent draws.** A plate's Euler pole bears no relation to its domain centroid, so per-plate motion is not a physically constrained rigid-body reconstruction.

---

## See also

- [Mesh and Geometry](mesh-and-geometry.md) — the sphere mesh, control volumes, neighbor graph, and cell areas every tectonic stage consumes
- [Plate Boundary Segment Ledger](plate-boundary-ledger.md) — exact directed cross-plate segments, nominal km/Ma Euler kinematics, and the candidate-versus-physical polarity separation
- [Crust Transport and Forward Overlap](crust-transport-and-overlap.md) — the destination-CSR forward-overlap plan, coverage multiplicity, membership-area classes, and the candidate-fate crosswalk
- [Crust Material Shadow and Dry-Rock Reservoirs](crust-material-and-reservoirs.md) — the non-authoritative sparse mass shadow and the three-reservoir counter-model driven by the crust process reasons
- [Topography, Isostasy and Thermal Subsidence](topography-and-isostasy.md) — the oceanic age–depth curve and the isostatic equilibrium operator this page's elevation change consumes
- [Erosion, Maturation and Landscape Evolution](erosion-and-maturation.md) — the maturation loop that calls `advance_plate_motion_and_crust` and commits `tectonic_elevation_change`
- [Native Engine (C++ Core)](../08-native-engine.md) — translation units, stage ordering, and the engine invariants
- [Compute Backends (CPU, OpenCL, CUDA)](../09-compute-backends.md) — accelerator eligibility, fallback semantics, and backend truthfulness
- [World Document Schema](../10-world-schema.md) — the full key inventory including `plate_motion_history`, `plate_kinematic_model`, and the initial oceanic age model/ledger
- [Serialization and World Formats](../11-serialization.md) — `roundtrip_num` versus fixed-precision fields and the replay-critical precision floors
- [Validation](../12-validation.md) — the `magic-geo validate` gate that runs the initial-age and plate-motion replays
- [Geo Validation Suite](../13-geo-validation-suite.md) — the geo layer contracts and the `tectonics` / `tectonic_zones_faults` validator domains
- [Calibration Against Real-Earth Data](../14-calibration.md) — where the Seton et al. (2020) age grid is used as a comparison target, never as a generation input
- [Configuration Reference](../05-configuration-reference.md) — all nine config sections and their validation rules
- [Glossary](../21-glossary.md) — oceanic-like, transported versus process change, nominal time, candidate versus physical polarity
