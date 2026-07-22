# Cryosphere: Ice Sheets, Glaciers and Permafrost

[Wiki home](../README.md) > Features

The cryosphere is the last physical process the native engine applies before it hands the world to the entity generators. It is a **terminal, zero-duration endpoint operator**: `derive_cryosphere_state` runs once after the maturation loop, drives a single bulk glacial sediment transfer, and is then recomputed a second time after the sea-level/climate/hydrology stabilization has re-solved the surface. Everything above that — ice-sheet histories, stability trajectories, flowlines, permafrost classes and glacial landform systems — is a **post-hoc Python diagnostic** layered on top of the native per-cell ice state; none of it is a time-stepped ice-dynamics solver, and the codebase says so explicitly (`multi_step_ice_dynamics_resolved: false`, `physical_time_resolved: false`).

## On this page

- [Where the cryosphere sits in the pipeline](#where-the-cryosphere-sits-in-the-pipeline)
- [Native cryosphere state derivation](#native-cryosphere-state-derivation)
- [Snow and ice mass balance inputs](#snow-and-ice-mass-balance-inputs)
- [Glacial sediment transport](#glacial-sediment-transport)
- [The glacial transport stage record](#the-glacial-transport-stage-record)
- [Coupling back into sea level, hydrology and elevation](#coupling-back-into-sea-level-hydrology-and-elevation)
- [Glacial landforms in the native landform classifier](#glacial-landforms-in-the-native-landform-classifier)
- [Ice sheet generation](#ice-sheet-generation)
- [The ice sheet record](#the-ice-sheet-record)
- [Ice sheet history and maturation stages](#ice-sheet-history-and-maturation-stages)
- [Ice sheet stability analysis](#ice-sheet-stability-analysis)
- [Ice flowline construction](#ice-flowline-construction)
- [Permafrost diagnostics](#permafrost-diagnostics)
- [Glacial landform classification](#glacial-landform-classification)
- [Sea ice](#sea-ice)
- [Per-cell cryosphere field table](#per-cell-cryosphere-field-table)
- [Summary keys](#summary-keys)
- [Downstream consumers of cryosphere state](#downstream-consumers-of-cryosphere-state)
- [Validation](#validation)
- [Worked example](#worked-example)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

---

## Where the cryosphere sits in the pipeline

The complete stage ordering lives in `cpp/src/engine/pipeline.cpp` (`simulate_world_impl`). The cryosphere block is lines 149–184, immediately after `erode(...)` returns and immediately before `summarize_plates` / `derive_soils_biomes_resources` / `derive_landforms`.

| Order | Line | Call | Effect |
|---|---|---|---|
| 1 | `pipeline.cpp:149-150` | `capture_feedback_reference(earth.cells)` | Snapshots pre-cryosphere state into `pre_cryosphere_reference` for the delta fields of the final feedback record |
| 2 | `pipeline.cpp:151` | `derive_cryosphere_state(params, earth.cells)` | First pass: ice thickness, glacier flow graph, SMB, sliding, velocity, glacial erosion potential |
| 3 | `pipeline.cpp:152-156` | `transport_glacial_sediment(0, feedback_history.size(), earth.cells)` | One bulk glacial erosion/deposition step; appended to `earth.glacial_transport_history` |
| 4 | `pipeline.cpp:157-166` | `stabilize_numeric_depressions(..., "cryosphere_coupling", -1, ...)` | Re-solves sea level → marine labelling → climate → water budget → flow/rivers → numeric depression fills, to convergence |
| 5 | `pipeline.cpp:167` | `derive_cryosphere_state(params, earth.cells)` **again** | Terminal cryosphere state recomputed on the stabilized surface — this is what the world document serializes |
| 6 | `pipeline.cpp:168-184` | `summarize_feedback_step(..., "cryosphere_coupling", -1, ..., cryosphere_applied=true, ...)` | Final `earth_system_feedback_history` record |
| 7 | `pipeline.cpp:187-188` | `derive_soils_biomes_resources`, `derive_landforms` | Consume the terminal ice state to set biome `ice_cap`, soil `tundra`, and the glacial landform codes |
| 8 | `pipeline.cpp:189` | `generate_ice_sheets(earth.cells)` | Flood-fills ice sheets, assigns peripheral cells, derives moraine and deglaciation memory; takes `cells` by non-const reference |

Two consequences follow from this ordering and are load-bearing for anyone reading the document:

- **The serialized `glacial_erosion_m`, `ice_velocity_m_y`, `basal_sliding_index`, `ice_surface_mass_balance_m_y`, `glacier_flow_to` and `ice_thickness_m` are the values from the *second* call**, computed on the post-transport, post-stabilization terrain. The values that actually *drove* the sediment transfer are preserved separately in `glacial_sediment_transport_history[0].input_cells[]` (`environment.cpp:123-134`). The two can legitimately differ.
- **The glacial sediment ledger fields on the cell (`glacial_sediment_production_m`, `glacial_sediment_deposition_m`, `glacial_sediment_net_m`, and the two transfer counters) are *not* reset by `derive_cryosphere_state`** — only the six state fields listed at `environment.cpp:27-32` are zeroed. The ledger therefore survives the recompute intact.

### Nominal time

The cryosphere stage carries a **zero-duration** nominal interval. `nominal_feedback_interval` (`cpp/src/engine/process_serialization.cpp:87-115`) returns `{elapsed_ma, elapsed_ma}` for the `cryosphere_coupling` step, so `advances_nominal_time` is `false` and `nominal_time_role` is `"final_cryosphere_coupling_snapshot"`. The glacial transport record uses the role `"final_cryosphere_coupling_bulk_transport"` with the same collapsed interval (`process_serialization.cpp:956-964`). The clock contract states this directly:

| Key | Value | Source |
|---|---|---|
| `simulation_clock.cryosphere_advances_nominal_time` | `false` | `process_serialization.cpp:2117` |
| `simulation_clock.configured_cryosphere_coupling_stage_count` | `1` | `process_serialization.cpp:2122` |
| `simulation_clock.physical_time_resolved` | `false` | `process_serialization.cpp:2083` |
| `simulation_clock.nominal_time_calibrated` | `false` | `process_serialization.cpp:2084` |
| `simulation_clock.time_step_convergence_demonstrated` | `false` | `process_serialization.cpp:2087` |
| `summary.simulation_clock_cryosphere_coupling_stage_count` | count of feedback steps with `cryosphere_applied` | `summary.cpp:1370-1371` |

The declared process order string (`iteration_process_order`, `process_serialization.cpp:2118-2119`) ends with `... ->cryosphere_state->glacial_sediment_transport->finite_alluvium_bedrock_inventory_and_terrain_commit->(sea_level->climate->causal_water_budget->hydrology->numeric_depression_correction)*until_stable->cryosphere_state_recompute`.

---

## Native cryosphere state derivation

`derive_cryosphere_state(const Params&, std::vector<Cell>&)` — `cpp/src/engine/environment.cpp:23-100`. Serial loop over all cells (no OpenMP pragma), fully deterministic.

**Step 0 — reset (all cells, water included), `environment.cpp:27-32`:**

```
ice_thickness_m = 0.0
glacier_flow_to = -1
ice_surface_mass_balance_m_y = 0.0
basal_sliding_index = 0.0
ice_velocity_m_y = 0.0
glacial_erosion_m = 0.0
```

**Step 1 — water short-circuit (`environment.cpp:33-35`):** `if (cell.is_water) continue;`. Water cells never receive ice. See [Sea ice](#sea-ice).

**Step 2 — glaciation persistence (`environment.cpp:37-50`):**

| Term | Formula | Clamp | Line |
|---|---|---|---|
| `lat_factor` | `(abs(lat_deg) - 50.0) / 32.0` | `[0.0, 1.25]` | 37 |
| `elevation_factor` | `(elevation_m - 1250.0) / 2500.0` | `[0.0, 1.25]` | 38 |
| `cold_index` | `(-temperature_c - 3.0) / 22.0` | `[0.0, 1.25]` | 39 |
| `moisture` | `(precipitation_mm_y - 140.0) / 1500.0` | `[0.05, 1.15]` | 40 |
| `persistence` | `cold_index * moisture * (0.42 + max(lat_factor, elevation_factor))` | — | 41 |

`cell.lat` is stored in radians; `abs(cell.lat) * DEG` converts to degrees, with `DEG = 180.0 / PI` (`cpp/src/engine/constants.hpp:6`).

Thickness assignment (`environment.cpp:42-50`):

```
if persistence > 0.16:
    ice_thickness_m = clamp((persistence - 0.16) * 1350.0, 0.0, 3200.0)
    if temperature_c > -2.0 and elevation_m < 1900.0:
        ice_thickness_m *= 0.35          # warm low-elevation ice penalty
    if ice_thickness_m < 25.0:
        ice_thickness_m = 0.0            # 25 m minimum-existence floor
```

The 25 m floor is the single most reused number in the whole cryosphere: it is the ice-sheet membership threshold (`environment.cpp:1038`, `1067`), the peripheral-cell threshold (`environment.cpp:1090`, `1093`, `1098`), the glaciated-land counter in the summary (`summary.cpp:475`), the ice-covered counter in permafrost and glacial-landform regions (`permafrost_diagnostics.py:183`, `glacial_landforms.py:232`), the glacial-landform ice test (`glacial_landforms.py:123`, `125`, `129`), and the validator's ice/sheet coherence rule (`geo_validation.py:2136`, `2157`).

**Step 3 — mass balance, flow target and dynamics (`environment.cpp:52-98`):** only for cells that survived with `ice_thickness_m > 0`.

| Quantity | Formula | Clamp | Line |
|---|---|---|---|
| `accumulation_m_y` | `(precipitation_mm_y / 1000.0) * clamp((-temperature_c + 1.0) / 18.0, 0.0, 1.4)` | `[0.0, 3.2]` | 55-59 |
| `ablation_m_y` | `max(0.0, temperature_c + 1.5) * 0.075` | `[0.0, 4.0]` | 60 |
| `ice_surface_mass_balance_m_y` | `accumulation_m_y - ablation_m_y` | `[-4.0, 3.2]` | 61 |
| `glacier_flow_to` | neighbor with the **largest strictly positive** elevation drop; `-1` if none | — | 62-71 |

If a downhill neighbor exists (`environment.cpp:72-89`), with `distance = neighbor_distance_m(params, cell, target)` (great-circle metres, floored at 1.0 m — `hydrology.cpp:209-211`) and `slope = best_drop / distance`:

| Quantity | Formula | Clamp | Line |
|---|---|---|---|
| `basal_sliding_index` | `0.18 + 0.32·clamp(H/1800,0,1) + 0.22·clamp((T+8)/10,0,1) + 0.14·clamp(P/1600,0,1) + 0.24·clamp(slope·900,0,1)` | `[0, 1]` | 75-82 |
| `ice_velocity_m_y` | `4.0 + 110.0·basal_sliding_index + 85.0·clamp(H/2200,0,1)·clamp(slope·1200,0,1.4)` | `[0, 420]` | 83-88 |
| `glacial_erosion_m` | `(H/1000.0) · max(0, slope·900.0) · 12.0` | `[0, 85]` | 89 |

If **no** downhill neighbor exists (a local ice minimum, `environment.cpp:90-98`):

| Quantity | Formula | Clamp | Line |
|---|---|---|---|
| `basal_sliding_index` | `0.12 + 0.30·clamp(H/1800,0,1) + 0.18·clamp((T+8)/10,0,1)` | `[0, 1]` | 91-96 |
| `ice_velocity_m_y` | `2.0 + 52.0·basal_sliding_index` | `[0, 120]` | 97 |
| `glacial_erosion_m` | stays `0.0` | — | (not assigned) |

`glacial_erosion_m` is described in the model contract as an `"ice_thickness_times_local_slope_proxy_bounded_85m_v1"` erosion **potential**, not a calibrated erosion rate (`process_serialization.cpp:854-855`).

---

## Snow and ice mass balance inputs

The cryosphere reads no dedicated snow field. Every input is an already-stabilized cell field produced by earlier stages.

| Input field | Produced by | Used for |
|---|---|---|
| `is_water` | `apply_sea_level` / `label_marine_water_bodies` (`cpp/src/engine/ocean.cpp`) | Water short-circuit (`environment.cpp:33`) |
| `lat` (radians) | `build_mesh` (`cpp/src/engine/mesh.cpp`) | `lat_factor` |
| `elevation_m` | sediment-interface primitive; derived as `bedrock_surface_elevation_m + sediment_thickness_m` | `elevation_factor`, flow target, slope |
| `temperature_c` | `compute_climate` (`cpp/src/engine/climate.cpp`) | `cold_index`, accumulation, ablation, sliding |
| `precipitation_mm_y` | `compute_climate` | `moisture`, accumulation, sliding |
| `neighbors` | `build_mesh` | Steepest-descent flow target |
| `area_km2` | `build_mesh` | Volume conversions in the transport stage |
| `sediment_thickness_m` | sediment-interface primitive (`cpp/src/engine/sediment_partition.cpp`) | Alluvium-vs-bedrock source partition; moraine memory |

There is no separate snowpack reservoir, no firn densification, no refreezing term, and no seasonal snow variable. Accumulation is a single annual quantity derived from annual precipitation scaled by a temperature window; ablation is a single linear degree-day-like term in the annual mean temperature. The 12-month `temperature_monthly_c` / `precipitation_monthly_mm` arrays are **not** consulted by the native cryosphere (they are consulted by the Python permafrost diagnostic).

---

## Glacial sediment transport

`transport_glacial_sediment(int id, int feedback_stage_id, std::vector<Cell>& cells)` — `cpp/src/engine/environment.cpp:102-299`. Returns a `GlacialSedimentTransportStage`; one stage per world (`id = 0`).

**Declared model** (`glacial_sediment_transport_model`, `process_serialization.cpp:846-906`):

| Key | Value |
|---|---|
| `model_type` | `downhill_area_conserving_glacial_sediment_transport_v2` |
| `routing_graph` | `single_steepest_downhill_mesh_neighbor_v1` |
| `source_state` | `post_erosion_pre_cryosphere_feedback_cell_state_v1` |
| `erosion_potential_model` | `ice_thickness_times_local_slope_proxy_bounded_85m_v1` |
| `mobile_sediment_fraction` | `0.28` (`GLACIAL_SEDIMENT_MOBILE_FRACTION`, `cpp/src/engine/constants.hpp:67`) |
| `source_depth_model` | `glacial_erosion_potential_times_mobile_sediment_fraction` |
| `source_material_partition_model` | `available_alluvium_first_then_bedrock_erosion_v1` |
| `volume_transfer_model` | `source_depth_times_source_area_equals_target_depth_times_target_area` |
| `stage_input_snapshot` | `complete_cell_cryosphere_terrain_and_sediment_inventory_before_transport_v2` |
| `mass_conserving` | `true` |
| `mass_conserving_semantics` | `bulk_reference_volume_only_not_dry_rock_mass` |
| `finite_sediment_inventory_resolved` | `true` |
| `terrain_elevation_coupled` | `true` |
| `earth_system_recomputed_after_transport` | `true` |
| `physical_time_resolved` | `false` |
| `multi_step_ice_dynamics_resolved` | `false` |
| `model_limitation` | `single_post_erosion_bulk_transfer_without_calibrated_time_multistep_ice_dynamics_or_grain_classes` |
| `per_cell_source_partition_audit_present` | `true` |
| `source_partition_audit_is_mass_claim` | `false` |
| `source_partition_audit_is_provenance_claim` | `false` |

**Algorithm.**

1. **Input snapshot** (`environment.cpp:123-134`): every cell, in cell-id order, contributes a `GlacialSedimentTransportInputCell` carrying `cell_id`, `glacier_flow_to_cell_id`, `is_water`, `elevation_m`, `ice_thickness_m`, `glacial_erosion_m`, `sediment_thickness_m`. This is the replay operand set; the serializer refuses to emit the stage if the array is not exactly cell-id indexed (`process_serialization.cpp:946-955`).
2. **Transfer loop** (`environment.cpp:136-212`). A cell contributes a transfer only if `glacier_flow_to >= 0` **and** `glacial_erosion_m > 0.0`. It then hard-fails if the target is out of range or not a mesh neighbor (`"glacial sediment transfer target is invalid"`), and hard-fails if the source is water, has no ice, has a non-positive elevation drop, or either area is non-positive (`"glacial sediment transfer source state is invalid"`).
3. **Volume identity** (`environment.cpp:166-173`):
   ```
   source_depth_m     = glacial_erosion_m * 0.28
   transfer_volume_km3 = source_depth_m * source.area_km2 / 1000.0
   target_depth_m      = transfer_volume_km3 * 1000.0 / target.area_km2
   deposited_volume_km3 = target_depth_m * target.area_km2 / 1000.0
   ```
   `mass_balance_residual_km3` per transfer is `abs(transfer_volume_km3 - deposited_volume_km3)` — a pure floating-point round-trip residual, not a physical loss term.
4. **Per-cell source partition** (`environment.cpp:214-238`): the accumulated `source_depth_m` for a cell is split, alluvium first:
   ```
   alluvium_entrainment_depth_m = min(sediment_thickness_m, source_depth_m)
   bedrock_erosion_depth_m      = max(0.0, source_depth_m - alluvium_entrainment_depth_m)
   ```
5. **Interface commit** (`environment.cpp:245-252`): a single `apply_sediment_interface_material_change(cell, 0.0, bedrock_erosion_depth_m, alluvium_entrainment_depth_m, deposition_depth_m, "glacial sediment interface")` per cell. The tectonic-displacement argument is `0.0` — the cryosphere never moves the bedrock datum.
6. **Compatibility assertion** (`environment.cpp:239-263`): the code precomputes `elevation_m + deposition - production` and throws `"glacial sediment-interface update changed the compatibility surface"` if the committed `elevation_m` deviates by more than `max(1e-9, |surface| * 1e-12)`. This is a runtime assertion that forces the interface primitive and the naive surface arithmetic to agree on every generated world; it is not a proof about the model.
7. **Post-commit audits** (`environment.cpp:276-297`): `maximum_sediment_interface_closure_residual_m(cells, "post glacial transport")` and `validate_sediment_source_partition(..., "glacial")`.

Because each source cell has exactly one steepest-descent target, `stage.source_cell_count` is assigned identically to `stage.transfer_count` (`environment.cpp:281`), while `stage.target_cell_count` is the size of the distinct-target set (`environment.cpp:282`). `terrain_volume_change_residual_km3` is assigned the same value as `mass_balance_residual_km3` (`environment.cpp:286-287`).

---

## The glacial transport stage record

`glacial_sediment_transport_history` is an array with exactly one element. Serializer: `glacial_sediment_transport_history_json` (`process_serialization.cpp:911`). The serializer throws `"glacial sediment history is not linked to the final cryosphere stage"` unless `feedback_stage_id == params.erosion_iterations + 1` (`process_serialization.cpp:925-929`).

| Field | Type | Meaning |
|---|---|---|
| `id` | int | Always `0` |
| `feedback_stage_id` | int | `erosion_iterations + 1` (the terminal `cryosphere_coupling` feedback record) |
| *(nominal time block, 12 fields)* | — | `nominal_time_role = "final_cryosphere_coupling_bulk_transport"`, zero duration, `advances_nominal_time=false` |
| `transfer_count` | int | Number of accepted source→target transfers |
| `cell_count` | int | Mesh cell count |
| `source_cell_count` | int | Equals `transfer_count` (one target per source) |
| `target_cell_count` | int | Distinct deposition targets |
| `land_target_transfer_count` | int | Transfers whose target is land |
| `marine_target_transfer_count` | int | Transfers whose target is water |
| `production_volume_km3` | double | Σ `transfer_volume_km3` |
| `deposition_volume_km3` | double | Σ `deposited_volume_km3` |
| `alluvium_entrainment_volume_km3` | double | Σ alluvium-sourced volume |
| `bedrock_erosion_volume_km3` | double | Σ bedrock-sourced volume |
| `source_production_depth_m_by_cell` | double[cell_count] | Per-cell mobilized depth, `max_digits10` |
| `alluvium_entrainment_depth_m_by_cell` | double[cell_count] | Per-cell alluvium share, `max_digits10` |
| `bedrock_erosion_depth_m_by_cell` | double[cell_count] | Per-cell bedrock share, `max_digits10` |
| `mass_balance_residual_km3` | double | `abs(production - deposition)` |
| `terrain_volume_change_residual_km3` | double | Same value as above |
| `max_source_production_depth_m` | double | Stage maximum |
| `max_target_deposition_depth_m` | double | Stage maximum |
| `input_cell_count` | int | `= cell_count` (`process_serialization.cpp:1006-1007`) |
| `input_cells[]` | array | Pre-transport snapshot, 7 fields (below) |
| `transfers[]` | array | Per-transfer evidence, 15 fields (below) |
| `post_transport_elevation_m_by_cell` | double[] | Elevation after the interface commit |

**`input_cells[]` (7 fields)** — `environment.cpp:125-133`: `cell_id`, `glacier_flow_to_cell_id`, `is_water`, `elevation_m`, `ice_thickness_m`, `glacial_erosion_m`, `sediment_thickness_m`.

**`transfers[]` (15 fields)** — `environment.cpp:185-203`: `id`, `source_cell_id`, `target_cell_id`, `target_is_water`, `source_area_km2`, `target_area_km2`, `source_elevation_m`, `target_elevation_m`, `elevation_drop_m`, `source_ice_thickness_m`, `source_glacial_erosion_m`, `source_production_depth_m`, `target_deposition_depth_m`, `transfer_volume_km3`, `mass_balance_residual_km3`.

Precision: volumes at `max(10, float_precision)`, surface depths at `max(8, float_precision)`, and the three `*_by_cell` arrays at `max_digits10` binary64 round-trip (`process_serialization.cpp:915-916`, `983-996`). Two scalar replay operands also use `max_digits10` rather than the surface floor: `input_cells[].sediment_thickness_m` (`process_serialization.cpp:1028-1030`) and `transfers[].source_production_depth_m` (`process_serialization.cpp:1063-1065`). `post_transport_elevation_m_by_cell` uses the surface floor (`process_serialization.cpp:1076-1080`).

The glacial process also appears as its own bucket in `sediment_inventory_model.process_source_partition.glacial`, with `gross_mobilization_volume_km3`, `alluvium_entrainment_volume_km3`, `bedrock_erosion_volume_km3` and `source_partition_residual_km3` (`process_serialization.cpp:2046-2047`).

---

## Coupling back into sea level, hydrology and elevation

The cryosphere touches the rest of the earth system through exactly one mechanism: **it changes `elevation_m` via the sediment interface**, and the stabilization loop then re-solves everything that depends on elevation.

`stabilize_numeric_depressions(params, cells, feedback_stage_id, "cryosphere_coupling", -1, ...)` at `pipeline.cpp:157-166` runs the bounded convergence loop implemented in `cpp/src/engine/hydrology.cpp`. Per pass it executes `apply_sea_level` → `label_marine_water_bodies` → `compute_climate` → `compute_hydrologic_water_budget` → `compute_flow_and_rivers`, then fills numeric (non-geologic) depressions; it throws `"numeric depression correction did not converge within the bounded pass count"` if it does not converge within `NUMERIC_DEPRESSION_CORRECTION_MAX_PASSES` (`16`, `cpp/src/engine/constants.hpp:55`; loop and throw at `hydrology.cpp:1137-1179`).

| Coupling | Direction | Mechanism |
|---|---|---|
| Ice → elevation | forward | `apply_sediment_interface_material_change` on erosion sources and deposition targets (`environment.cpp:245-252`) |
| Elevation → sea level | forward | `apply_sea_level` re-solves the volume-constrained datum for the new hypsometry |
| Sea level → ice | feedback | The second `derive_cryosphere_state` skips any cell that is now `is_water` |
| Elevation → climate | feedback | `compute_climate` re-derives `temperature_c` / `precipitation_mm_y` from the new relief, which re-drives `persistence` |
| Elevation → hydrology | feedback | New flow graph, runoff, lakes, depressions; the glacier flow graph is recomputed against the same new surface |
| Ice → sediment inventory | forward | Alluvium-first partition draws down `sediment_thickness_m`; bedrock share lowers `bedrock_surface_elevation_m` |

Note what is **not** coupled: ice mass is never removed from or added to the ocean water inventory. Sea level is solved from `planet.ocean_water_inventory_km3` and hypsometry only; there is no glacio-eustatic term and no ice-load isostasy term anywhere in the cryosphere path. Ice thickness is a diagnostic surface layer that does not enter the isostatic equilibrium calculation in `crust_equilibrium_elevation_m`.

The terminal feedback record is written with `cryosphere_applied = true` and `erosion_applied = plate_motion_applied = crust_transport_applied = crust_evolution_applied = false` (`pipeline.cpp:177-181`, matching the boolean parameter order declared at `internal.hpp:267-271`), so it is distinguishable from every erosion iteration.

---

## Glacial landforms in the native landform classifier

`derive_landforms(std::vector<Cell>&)` — `cpp/src/engine/environment.cpp:417-505`, OpenMP-parallel over cells. It runs **after** the terminal cryosphere recompute, so it sees the final ice field. The helper `has_glacier_neighbor(cells, i)` uses the **default threshold of 80.0 m** (`cpp/src/engine/internal.hpp:317-321`), which is distinct from the 25 m membership floor used elsewhere.

Glacial branches, in evaluation order:

| Code | `LANDFORM_NAMES` | Condition | Line |
|---|---|---|---|
| 16 | `fjord` | water cell **and** `has_glacier_neighbor` (80 m) **and** `water_depth_m < 1200.0` **and** `water_body ∈ {continental_shelf(2), inland_sea(3)}` | 431-432 |
| 19 | `glacial_lake` | `is_lake` **and** `has_glacier_neighbor` (80 m) | 446 |
| 5 | `ice_field` | `ice_thickness_m > 180.0` **or** `biome == ice_cap(3)` | 449-450 |
| 17 | `glacial_valley` | `glacial_erosion_m > 8.0` **and** `local_relief > 320.0` | 451-452 |
| 18 | `moraine` | `has_glacier_neighbor` (80 m) **and** `sediment_thickness_m > 0.35` **and** `elevation_m > 120.0` | 453-454 |

Post-classification edits (`environment.cpp:496-500`): for landforms 17, 18 and 19, `soil_type` is forced to `tundra(8)` **except** for 19, and `settlement_score` is multiplied by `0.72` for `glacial_lake(19)` and `0.42` for `glacial_valley(17)` / `moraine(18)`.

`derive_soils_biomes_resources` (`environment.cpp:301-415`) also has an ice branch at `environment.cpp:345-348`: `ice_thickness_m > 180.0` **or** (`temperature_c < -8.0` **and** (`|lat_deg| > 55.0` **or** `elevation_m > 1600.0`)) ⇒ `soil_type = tundra(8)`, `biome = ice_cap(3)`. The hazard term of `settlement_score` includes `clamp(ice_thickness_m / 2200, 0, 1) * 0.22` (`environment.cpp:408-409`), and cells whose biome ends up `ice_cap(3)`, `tundra(4)`, `alpine(14)` or `ocean(0)` have their settlement score multiplied by `0.18` (`environment.cpp:411-413`).

Glacial cells also steer stratigraphy: `stratigraphic_facies_for_layer` (`environment.cpp:786-788`) returns `glacial_till(8)` for the topmost layer and `lacustrine_mud(4)` below it whenever the representative cell has `ice_thickness_m > 25.0` or `landform ∈ {moraine(18), glacial_lake(19)}`.

---

## Ice sheet generation

`generate_ice_sheets(std::vector<Cell>& cells)` — `cpp/src/engine/environment.cpp:1027-1156`. Called at `pipeline.cpp:189`, after landforms.

**Phase 1 — reset (`environment.cpp:1028-1032`):** every cell gets `ice_sheet_id = -1`, `moraine_deposition_m = 0.0`, `deglaciation_age_ka = 0.0`.

**Phase 2 — BFS flood fill (`environment.cpp:1037-1086`).** A cell seeds a new sheet if it is unvisited, not water, and `ice_thickness_m > 25.0`. The queue expands to unvisited, non-water neighbors with `ice_thickness_m > 25.0`. Per sheet the loop accumulates area-weighted sums:

| Accumulator | Weight | Line |
|---|---|---|
| `cell_count` | +1 | 1052 |
| `area_km2` | `+area_km2` | 1053 |
| `mean_ice_thickness_m` | `ice_thickness_m * area_km2` | 1054 |
| `max_ice_thickness_m` | running max | 1055 |
| `mean_glacial_erosion_m` | `glacial_erosion_m * area_km2` | 1056 |
| `mean_surface_mass_balance_m_y` | `ice_surface_mass_balance_m_y * area_km2` | 1057 |
| `mean_basal_sliding_index` | `basal_sliding_index * area_km2` | 1058 |
| `mean_ice_velocity_m_y` | `ice_velocity_m_y * area_km2` | 1059 |
| `accumulation_area_fraction` | `+area_km2` if `precipitation_mm_y > 260.0` **and** `temperature_c < -1.0` | 1060-1062 |

All are divided by `area_km2` at `environment.cpp:1073-1080`.

**Equilibrium line altitude (`environment.cpp:1081-1084`):** member elevations are sorted ascending and `equilibrium_line_altitude_m = elevations[(size_t)(0.42 * (n - 1))]` — the truncated 42nd-percentile index, not an interpolated percentile and not a mass-balance-derived ELA.

**Phase 3 — peripheral assignment and glacial memory (`environment.cpp:1088-1102`).** A cell with `ice_sheet_id < 0` is adopted by `nearest_neighbor_ice_sheet` (`environment.cpp:992-1006`, which picks the neighbor sheet maximizing `ice_thickness_m + 0.8 * glacial_erosion_m`) when it is `landform ∈ {moraine(18), glacial_valley(17), glacial_lake(19)}`, **or** when `ice_thickness_m <= 25.0` and `has_glacier_neighbor(cells, id, 25.0)` — note the explicit 25 m threshold here, overriding the 80 m default.

For any cell with `ice_sheet_id >= 0` and `ice_thickness_m <= 25.0` (i.e. deglaciated members):

```
cold_memory     = clamp((-temperature_c + 4.0) / 18.0, 0, 1)
erosion_memory  = clamp(glacial_erosion_m / 18.0, 0, 1)
sediment_memory = clamp(sediment_thickness_m / 2.5, 0, 1)
deglaciation_age_ka = clamp(2.0 + 80.0*cold_memory + 22.0*erosion_memory, 0.0, 120.0)
if landform == moraine(18) or has_glacier_neighbor(cells, id, 25.0):
    moraine_deposition_m = clamp(0.18 + 1.4*sediment_memory + 0.18*local_relief(cells,id)/700.0, 0.0, 4.0)
```

`sediment_memory` is computed unconditionally but only consumed inside the moraine branch. `deglaciation_age_ka` is therefore a *cold-and-erosion memory index expressed in ka*, not a dated deglaciation.

**Phase 4 — sheet-level moraine and deglaciation aggregates (`environment.cpp:1104-1129`).** `moraine_cell_count` counts members with `moraine_deposition_m > 0.0` **or** `landform == moraine(18)`; `mean_moraine_deposition_m` divides the moraine sum by that count. `mean_deglaciation_age_ka` averages only over members with `deglaciation_age_ka > 0.0`.

**Phase 5 — retreat rate and stage (`environment.cpp:1130-1138`):**

```
retreat_rate_m_y = clamp(
      4.0
    + 42.0 * max(0.0, 0.45 - accumulation_area_fraction)
    + 16.0 * mean_basal_sliding_index
    - 22.0 * mean_surface_mass_balance_m_y,
    0.0, 120.0)
```

`retreat_stage_for_ice_sheet` (`environment.cpp:1008-1025`) evaluates in this exact order and returns an index into `ICE_RETREAT_STAGE_NAMES` (`cpp/src/engine/schema_names.hpp:132-134`):

| Order | Condition | Emitted stage | Index |
|---|---|---|---|
| 1 | `cell_count <= 0` | `relict` | 4 |
| 2 | `max_ice_thickness_m < 80.0` | `relict` | 4 |
| 3 | `accumulation_area_fraction < 0.28` | `retreating` | 2 |
| 4 | `moraine_cell_count > cell_count / 4` **and** `accumulation_area_fraction < 0.52` | `stagnant` | 3 |
| 5 | `accumulation_area_fraction > 0.66` **and** `mean_ice_thickness_m > 420.0` | `advancing` | 0 |
| 6 | otherwise | `stable` | 1 |

Note `cell_count / 4` is integer division.

**Phase 6 — canonical ordering (`environment.cpp:1139-1154`):** sheets are sorted by `area_km2` descending, ties broken by the pre-sort id; ids are then reassigned `0..n-1` and every cell's `ice_sheet_id` is remapped through the permutation. Ice-sheet id `0` is always the largest sheet by area.

---

## The ice sheet record

Struct: `cpp/src/engine/types/world.hpp:381-398`. Serializer: `ice_sheets_json` (`cpp/src/engine/entity_serialization.cpp:601-628`), emitted at `cpp/src/engine/world_serialization.cpp:221-222`. All doubles use plain `params.float_precision` (default `4`).

| # | Field | Type | Derivation | Line |
|---|---|---|---|---|
| 1 | `id` | int | Rank by `area_km2` descending, `0`-based | `environment.cpp:1146-1149` |
| 2 | `retreat_stage` | enum str | `advancing` / `stable` / `retreating` / `stagnant` / `relict` | `environment.cpp:1008-1025` |
| 3 | `cell_count` | int | BFS component size (thickness > 25 m cells only) | `environment.cpp:1052` |
| 4 | `moraine_cell_count` | int | Members with `moraine_deposition_m > 0` or `landform == moraine` | `environment.cpp:1112-1115` |
| 5 | `area_km2` | double | Σ member `area_km2` | `environment.cpp:1053` |
| 6 | `mean_ice_thickness_m` | double | Area-weighted mean | `environment.cpp:1054`, `1074` |
| 7 | `max_ice_thickness_m` | double | Member maximum | `environment.cpp:1055` |
| 8 | `mean_glacial_erosion_m` | double | Area-weighted mean | `environment.cpp:1056`, `1075` |
| 9 | `mean_surface_mass_balance_m_y` | double | Area-weighted mean | `environment.cpp:1057`, `1076` |
| 10 | `mean_basal_sliding_index` | double | Area-weighted mean | `environment.cpp:1058`, `1077` |
| 11 | `mean_ice_velocity_m_y` | double | Area-weighted mean | `environment.cpp:1059`, `1078` |
| 12 | `accumulation_area_fraction` | double | Area fraction with `P > 260 mm/y` and `T < -1 °C` | `environment.cpp:1060-1062`, `1079` |
| 13 | `equilibrium_line_altitude_m` | double | Sorted member elevation at truncated index `0.42·(n-1)` | `environment.cpp:1081-1084` |
| 14 | `retreat_rate_m_y` | double | Clamped `[0, 120]` composite of accumulation deficit, sliding, SMB | `environment.cpp:1130-1136` |
| 15 | `mean_deglaciation_age_ka` | double | Mean over members with nonzero deglaciation memory | `environment.cpp:1126-1129` |
| 16 | `mean_moraine_deposition_m` | double | Moraine sum ÷ `moraine_cell_count` | `environment.cpp:1122-1125` |

The Python stability enricher **mutates these records in place**, adding seven more keys — see [Ice sheet stability analysis](#ice-sheet-stability-analysis).

---

## Ice sheet history and maturation stages

`enrich_world_with_ice_sheet_history(world, step_count=8)` — `src/magic_geo/cryosphere_dynamics.py:11-151`. Called at `api.py:220` (full world) and `api.py:338` (geo-only), always with the default `step_count=8`. Writes `world["ice_sheet_histories"]`.

This is a **post-hoc reconstruction**, not a replay of anything the native engine did. It runs *backwards in ka* from `mean_deglaciation_age_ka` to 0 in `step_count` equal-duration slices, inflating the observed present-day volume into an assumed past maximum and then bleeding it back down.

**Per-sheet setup (`cryosphere_dynamics.py:26-54`):**

| Quantity | Formula | Line |
|---|---|---|
| `current_volume_km3` | `area_km2 * mean_ice_thickness_m / 1000.0` | 29 |
| `deglaciation_age_ka` | `max(1.0, mean_deglaciation_age_ka)` | 30 |
| `duration_ka` (per step) | `deglaciation_age_ka / max(1, step_count)` | 31 |
| `stage_retreat_bias` | lookup by `retreat_stage` (below), default `0.70` | 40-45 |
| `initial_multiplier` | `1 + stage_retreat_bias * (0.20 + max(0, 0.85 - accumulation_area_fraction) * 0.15)` | 46 |
| starting `volume_km3` | `current_volume_km3 * initial_multiplier` | 47 |
| starting `working_area_km2` | `area_km2 * (1 + stage_retreat_bias * 0.08)` | 48 |

**`stage_retreat_bias` by maturation stage** (`cryosphere_dynamics.py:40-45`):

| `retreat_stage` | bias |
|---|---|
| `advancing` | `0.20` |
| `stable` | `0.55` |
| `retreating` | `1.00` |
| `relict` | `1.25` |
| anything else (including `stagnant`) | `0.70` |

Note that `stagnant` — a stage the native engine genuinely emits (`environment.cpp:1018-1020`) — is **not** in the lookup table and therefore falls through to the `0.70` default.

**Per-step integration (`cryosphere_dynamics.py:56-114`):**

```
start_age_ka  = max(0, deglaciation_age_ka - index*duration_ka)
end_age_ka    = max(0, deglaciation_age_ka - (index+1)*duration_ka)
duration_years = max(1.0, (start_age_ka - end_age_ka) * 1000.0)
climate_warming = (index + 1) / step_count

effective_smb_m_y = mean_surface_mass_balance_m_y - stage_retreat_bias * climate_warming * 0.18
surface_balance_km3 = effective_smb_m_y * working_area_km2 * duration_years / 1000.0 * 0.035

velocity_loss_m_y     = mean_ice_velocity_m_y * (0.004 + basal_sliding * 0.010)
negative_smb_loss_m_y = max(0, -effective_smb_m_y) * 0.10
dynamic_loss_km3 = (velocity_loss_m_y + negative_smb_loss_m_y) * working_area_km2 * duration_years / 1000.0 * 0.035

retreat_distance_km = retreat_rate_m_y * stage_retreat_bias * duration_years / 1000.0
                    + max(0, 0.60 - accumulation_area_fraction) * duration_years * 0.000025
front_width_km   = sqrt(max(1.0, working_area_km2))
retreat_loss_km3 = retreat_distance_km * front_width_km * mean_ice_thickness_m / 1000.0 * 0.08

raw_delta      = surface_balance_km3 - dynamic_loss_km3 - retreat_loss_km3
max_gain       = max(1.0, volume_km3 * 0.16)
max_loss       = max(1.0, volume_km3 * 0.22)
bounded_delta  = clamp(raw_delta, -max_loss, max_gain)
stabilization_adjustment_km3 = bounded_delta - raw_delta
end_volume_km3 = max(0.0, volume_km3 + bounded_delta)
```

Area evolution (`cryosphere_dynamics.py:79-82`): `area_loss_fraction = clamp(retreat_distance_km / max(1, front_width_km) * 0.08, 0, 0.18)`; if `bounded_delta > 0` and the stage is `advancing`, the fraction becomes negative (area *gain*) capped at `-0.04`. `end_area_km2 = max(area_km2 * 0.10, working_area_km2 * (1 - area_loss_fraction))` — an ice sheet can never shrink below 10 % of its native area in this reconstruction.

The literal `0.035` scale factor applied to both `surface_balance_km3` and `dynamic_loss_km3` (`cryosphere_dynamics.py:62`, `65`) and the `0.08` on `retreat_loss_km3` (line 70) are unlabelled tuning constants with no stated physical derivation in the source.

**`ice_sheet_histories[]` record fields:**

| Field | Type | Meaning | Line |
|---|---|---|---|
| `id` | int | Equal to `ice_sheet_id` | 125 |
| `ice_sheet_id` | int | Source sheet | 126 |
| `retreat_stage` | str | Copied from the sheet | 127 |
| `time_step_count` | int | `len(steps)` (= `step_count` = 8) | 128 |
| `initial_volume_km3` | double | `steps[0].start_volume_km3` | 129 |
| `final_volume_km3` | double | Volume after the last step | 130 |
| `peak_volume_km3` | double | Max over start and every end volume | 131 |
| `total_surface_balance_km3` | double | Σ step `surface_balance_km3` | 132 |
| `total_dynamic_loss_km3` | double | Σ step `dynamic_loss_km3` | 133 |
| `total_retreat_loss_km3` | double | Σ step `retreat_loss_km3` | 134 |
| `total_retreat_distance_km` | double | Σ step `retreat_distance_km` | 135 |
| `mean_deglaciation_age_ka` | double | Clamped source value | 136 |
| `steps[]` | array | 18 fields each (below) | 137 |

**`steps[]` (18 fields)** — `cryosphere_dynamics.py:85-106`, all rounded to 6 decimals: `step`, `start_age_ka`, `end_age_ka`, `duration_years`, `start_area_km2`, `end_area_km2`, `start_volume_km3`, `end_volume_km3`, `surface_mass_balance_m_y`, `surface_balance_km3`, `dynamic_loss_km3`, `retreat_loss_km3`, `stabilization_adjustment_km3`, `retreat_distance_km`, `basal_sliding_index`, `ice_velocity_m_y`, `accumulation_area_fraction`, `moraine_deposition_m`.

The `stabilization_adjustment_km3` field exists precisely so the validator can close the volume budget on a clamped integration: `end_volume ≈ start_volume + surface - dynamic - retreat + adjustment` is checked to `3.0e-3` absolute (`geo_validation_subsystems.py:1781-1782`).

---

## Ice sheet stability analysis

`enrich_world_with_ice_sheet_stability(world)` — `src/magic_geo/cryosphere_stability.py:64-237`. Called at `api.py:221` / `api.py:339`, after the history enricher (it re-walks those steps). Writes `world["ice_sheet_stability_histories"]` and mutates each `ice_sheets[]` record.

**Sheet-level criteria (`cryosphere_stability.py:100-118`):**

| Criterion | Formula | Notes |
|---|---|---|
| `marine_margin` | fraction of sheet cells with at least one `is_water` neighbor, clamped `[0,1]` | `cryosphere_stability.py:32-45` |
| `thermal_pressure` | `clamp((mean cell temperature_c + 8.0) / 14.0)`, default `-8.0` when the sheet has no cells | line 103 |
| `mean_cell_elevation_m` | mean member `elevation_m`, defaulting to `equilibrium_line_altitude_m` | line 101 |
| `ela_offset_m` | `equilibrium_line_altitude_m - mean_cell_elevation_m + (0.5 - accumulation_area_fraction) * 650.0` | line 104 |
| `calving_susceptibility` | `clamp(marine_margin*0.46 + min(1, v/220)*0.22 + basal_sliding*0.18 + thermal_pressure*0.10 + max(0,-mean_smb)*0.04)` | lines 105-111 |
| `grounding_instability` | `clamp(marine_margin*0.42 + basal_sliding*0.22 + min(1, max(0,ela_offset)/1400)*0.18 + min(1, retreat_rate/85)*0.12 + thermal_pressure*0.06)` | lines 112-118 |

Both indices are constant across the sheet's steps — they are sheet-level properties, re-emitted on every step record.

**Per-step criteria (`cryosphere_stability.py:130-156`):**

```
loss                = dynamic_loss_km3 + retreat_loss_km3
mass_balance_ratio  = surface_balance_km3 / max(1.0, loss)
deficit_index       = clamp((loss - surface_balance) / max(1.0, loss + abs(surface_balance)))
area_loss           = max(0, start_area_km2 - end_area_km2)
area_loss_fraction  = clamp(area_loss / max(1.0, start_area_km2))
retreat_pace_index  = clamp((retreat_distance_km / max(1, sqrt(area_km2))) * 4.0 + area_loss_fraction * 2.0)

retreat_threshold_index = clamp(
      deficit_index          * 0.42
    + calving_susceptibility * 0.22
    + grounding_instability  * 0.20
    + retreat_pace_index     * 0.16)

retreat_threshold_crossed = retreat_threshold_index >= THRESHOLD_RISK   # 0.65
projected_calving_loss_km3          = loss * calving_susceptibility * marine_margin * 0.18
projected_grounding_line_retreat_km = retreat_distance_km * grounding_instability * (0.4 + marine_margin*0.6)
```

`THRESHOLD_RISK = 0.65` is defined at `cryosphere_stability.py:7`.

**States emitted** — `_stability_class(index)` at `cryosphere_stability.py:54-61`, applied to `max(sheet_max_stability, mean_stability)` (line 181):

| Condition on the index | `stability_class` |
|---|---|
| `>= 0.75` | `unstable` |
| `>= 0.50` and `< 0.75` | `threshold_sensitive` |
| `>= 0.25` and `< 0.50` | `sensitive` |
| `< 0.25` | `stable` |

**Fields added to each `ice_sheets[]` record (`cryosphere_stability.py:194-200`):** `ice_sheet_stability_index` (mean threshold index), `ice_sheet_stability_class`, `calving_susceptibility_index`, `grounding_line_instability_index`, `equilibrium_line_offset_m`, `retreat_threshold_event_count`, `first_retreat_threshold_step` (`-1` if never crossed).

**`ice_sheet_stability_histories[]` record (`cryosphere_stability.py:202-221`):**

| Field | Type | Meaning |
|---|---|---|
| `id` | int | Sequential record index |
| `ice_sheet_id` | int | Source sheet id |
| `time_step_count` | int | Number of stability steps (mirrors the history) |
| `stability_class` | str | One of the four states above |
| `mean_stability_index` | double | Mean `retreat_threshold_index` across steps |
| `max_stability_index` | double | Max `retreat_threshold_index` |
| `calving_susceptibility_index` | double | Sheet-level constant |
| `grounding_line_instability_index` | double | Sheet-level constant |
| `marine_margin_fraction` | double | Sheet-level constant |
| `equilibrium_line_offset_m` | double | `ela_offset_m` |
| `retreat_threshold_event_count` | int | Steps with `retreat_threshold_index >= 0.65` |
| `first_retreat_threshold_step` | int | 1-based step, `-1` if none |
| `years_to_retreat_threshold` | double | Elapsed years to the first crossing, `-1.0` if none |
| `total_projected_calving_loss_km3` | double | Σ step projections |
| `total_projected_grounding_line_retreat_km` | double | Σ step projections |
| `steps[]` | array | 13 fields (below) |

**`steps[]` (13 fields)** — `cryosphere_stability.py:157-173`: `step`, `start_age_ka`, `end_age_ka`, `duration_years`, `mass_balance_ratio`, `balance_deficit_index`, `retreat_pace_index`, `calving_susceptibility_index`, `grounding_line_instability_index`, `retreat_threshold_index`, `retreat_threshold_crossed` (bool), `projected_calving_loss_km3`, `projected_grounding_line_retreat_km`.

A sheet whose ice-sheet history is missing (or empty) still produces a stability record — with zero steps, `mean_stability_index = 0.0` and class `stable`.

---

## Ice flowline construction

`enrich_world_with_ice_flowline_history(world, flowline_limit=10, max_path_length=48)` — `src/magic_geo/cryosphere_flow.py:86-249`. Called at `api.py:222` / `api.py:340` with defaults. Writes `world["ice_flowline_histories"]` plus four per-cell fields.

**Planet coupling (`cryosphere_flow.py:95-99`):** `radius_km = planet_radius_km(world)` and `gravity_m_s2 = surface_gravity_m_s2(world, earth_reference_m_s2=ICE_FLOW_REFERENCE_GRAVITY_M_S2)` with `ICE_FLOW_REFERENCE_GRAVITY_M_S2 = 9.81` (`cryosphere_flow.py:9`). `surface_gravity_m_s2` returns `planet.gravity_g * 9.81` (`src/magic_geo/planet_parameters.py:85-90`), so the driving stress genuinely scales with configured planetary gravity.

**Source selection (`_select_flowline_sources`, `cryosphere_flow.py:25-60`):**

1. Candidates: cells with `ice_thickness_m > 0.0` **and** `glacier_flow_to >= 0`.
2. Sort descending by the tuple `(ice_thickness_m * (1 + ice_velocity_m_y/100) * (1 + basal_sliding_index), ice_surface_mass_balance_m_y)`.
3. First pass: take at most one candidate per distinct `ice_sheet_id`, up to `flowline_limit`. (`-1` counts as a distinct sheet id here.)
4. Second pass: fill any remaining slots from the same ranked list, skipping already-selected cell ids.

**Path following (`_follow_flowline`, `cryosphere_flow.py:63-83`):** walk `glacier_flow_to` for at most `max_path_length = 48` hops. The walk stops on a negative id, a revisited cell, a self-loop, a missing cell, or when the next cell's `ice_sheet_id` is neither the source sheet id nor `-1`. Paths shorter than 2 cells are discarded entirely (`cryosphere_flow.py:120-121`).

**Per-step physics (`cryosphere_flow.py:133-204`):**

| Quantity | Formula | Line |
|---|---|---|
| `segment_length_km` | Haversine great-circle to the next path cell, radius `planet_radius_km` | 16-22, 135 |
| `surface_slope` | `max(0, (elev_here - elev_next) / (segment_length_km * 1000))` | 143-145 |
| `driving_stress_kpa` | `917.0 * gravity_m_s2 * ice_thickness_m * max(0.0002, slope) / 1000.0` | 146 |
| `accumulation_flux_km3_y` | `max(0, smb) * area_km2 / 1000.0` | 147 |
| `ablation_loss_km3_y` | `max(0, -smb) * area_km2 / 1000.0` | 148 |
| `dynamic_capacity_km3_y` | `velocity * thickness * sqrt(area_km2) / 1_000_000 * (0.55 + basal_sliding)` | 149 |
| `available_flux_km3_y` | `start_flux + accumulation_flux` | 150 |
| `dynamic_flux_km3_y` | `min(available, dynamic_capacity)` | 151 |
| `dynamic_loss_km3_y` | `min(dynamic_flux * (0.03 + basal_sliding*0.04), available)` | 152 |
| `melt_loss_km3_y` | `min(max(0, available - dynamic_loss), ablation_loss)` | 153 |
| `end_flux_km3_y` | `max(0, available - dynamic_loss - melt_loss)`; forced to `0.0` at the terminal cell | 154-160 |
| `balance_residual_km3_y` | `available - dynamic_loss - melt_loss - end_flux` | 161 |
| `strain_heating_index` | `clamp(driving_stress/450 * (velocity/220) * (0.4 + basal_sliding), 0, 1)` | 162 |
| `glacial_erosion_m` (step) | `max(0, cell.glacial_erosion_m) * (0.25 + 0.75 * strain_heating_index)` | 163 |

`917.0` is used as an ice density in kg/m³; the expression has the algebraic shape of the shallow-ice driving stress `τ = ρ g H sin α` with the small-angle substitution `sin α ≈ slope`, converted from Pa to kPa. The *shape* is standard; the *inputs* are not solved ice geometry — `ice_thickness_m` is the bounded persistence score of [Native cryosphere state derivation](#native-cryosphere-state-derivation) and the slope is a two-cell great-circle finite difference, so the emitted `driving_stress_kpa` is a diagnostic index and not a resolved stress field. The `max(0.0002, slope)` floor means a perfectly flat reach still reports a nonzero stress. At the terminal cell the residual flux is swept into `dynamic_loss_km3_y` (`cryosphere_flow.py:154-158`) so the balance closes exactly — the validator enforces `abs(balance_residual_km3_y) <= 2.0e-5` (`geo_validation_subsystems.py:1864-1865`).

**Per-cell fields written (max across all paths that touch the cell), `cryosphere_flow.py:101-105`, `165-174`:**

| Cell field | Semantics |
|---|---|
| `ice_flowline_flux_km3_y` | Max `end_flux_km3_y` seen at the cell |
| `ice_flowline_driving_stress_kpa` | Max `driving_stress_kpa` |
| `ice_flowline_strain_heating_index` | Max `strain_heating_index`, bounded `[0,1]` |
| `ice_flowline_path_count` | Number of traced flowlines passing through the cell |

Every cell is initialized to `0.0 / 0.0 / 0.0 / 0` first (`cryosphere_flow.py:101-105`), so these four fields exist on all cells regardless of ice.

**`ice_flowline_histories[]` record (`cryosphere_flow.py:216-233`):**

| Field | Type | Meaning |
|---|---|---|
| `id` | int | Sequential record index |
| `source_cell_id` | int | Head of the path |
| `ice_sheet_id` | int | Source cell's sheet (`-1` possible) |
| `flowline_cell_ids` | int[] | The traced path, in order |
| `time_step_count` | int | `len(steps)` = path length |
| `path_length_km` | double | Σ segment great-circle lengths |
| `total_dynamic_flux_km3_y` | double | Σ step `dynamic_flux_km3_y` |
| `total_dynamic_loss_km3_y` | double | Σ step `dynamic_loss_km3_y` |
| `total_melt_loss_km3_y` | double | Σ step `melt_loss_km3_y` |
| `total_glacial_erosion_m` | double | Σ step stress-modulated erosion |
| `max_driving_stress_kpa` | double | Path maximum |
| `max_strain_heating_index` | double | Path maximum |
| `final_ice_flux_km3_y` | double | `steps[-1].end_flux_km3_y` (always `0.0` for a completed path) |
| `steps[]` | array | 18 fields (below) |

**`steps[]` (18 fields)** — `cryosphere_flow.py:176-197`: `step`, `cell_id`, `flow_to_cell_id`, `segment_length_km`, `surface_slope` (8 decimals), `ice_thickness_m`, `start_flux_km3_y`, `accumulation_flux_km3_y`, `dynamic_flux_km3_y`, `dynamic_loss_km3_y`, `melt_loss_km3_y`, `end_flux_km3_y`, `balance_residual_km3_y`, `driving_stress_kpa`, `basal_sliding_index`, `ice_velocity_m_y`, `strain_heating_index`, `glacial_erosion_m`.

The "time" axis of a flowline history is **spatial**, not temporal: `time_step_count` counts cells along the path, and `steps[].step` is a path index. The fluxes are steady-state per-year quantities, not an integration through time.

---

## Permafrost diagnostics

`enrich_world_with_permafrost_diagnostics(world)` — `src/magic_geo/permafrost_diagnostics.py:129-199`. Called at `api.py:225` (full world, **after** `biome_diagnostics`) and `api.py:342` (geo-only, **before** `biome_diagnostics`). Writes `world["permafrost_regions"]` plus five per-cell fields.

**Water short-circuit (`permafrost_diagnostics.py:42-43`):** any cell with `is_water` returns `(0.0, 0.0, 0.0, "no_permafrost")` immediately — there is no subsea permafrost.

**Ground-temperature inputs (`permafrost_diagnostics.py:45-58`):**

| Input | Source | Fallback |
|---|---|---|
| `monthly_temperature` | `temperature_monthly_c` if it is a 12-element list | 12 copies of `temperature_c` (`permafrost_diagnostics.py:14-18`) |
| `annual_temperature` | mean of the 12 monthly values | — |
| `warmest_month` | max of the 12 | — |
| `freezing_degree_index` | `Σ max(0, -T_month) / 12` | computed but **not used** in any output term |
| `thawing_degree_index` | `Σ max(0, T_month) / 12` | — |
| `frost_months` | cell field `frost_months` (written by `biome_dynamics.py:158`) | count of months with `T < 0` |
| `lat_abs` | `abs(lat_deg) / 90.0` | — |
| `elevation` | `max(0, elevation_m)` | — |
| `soil_moisture` | `clamp(soil_moisture_index)` | `0.0` |
| `organic` | `clamp(soil_organic_matter_fraction / 0.18)` | `0.0` |
| `drainage` | `clamp(soil_drainage_index)` | `0.0` |
| `snow_or_ice` | `clamp(ice_thickness_m / 650.0)` | `0.0` |
| `aridity` | `clamp(seasonal_aridity_index)` | `0.0` |

**Extent (`permafrost_diagnostics.py:60-76`):**

```
coldness             = clamp((-annual_temperature + 1.5) / 16.0)
persistent_freeze    = clamp(frost_months / 12.0)
high_cold            = clamp(elevation / 4200.0)
summer_thaw_penalty  = clamp((warmest_month - 6.0) / 22.0)
thaw_penalty         = clamp(thawing_degree_index / 18.0)

permafrost_extent_index = clamp(
      coldness           * 0.34
    + persistent_freeze  * 0.24
    + lat_abs            * 0.12
    + high_cold          * 0.11
    + soil_moisture      * 0.08
    + organic            * 0.05
    + snow_or_ice        * 0.12
    - summer_thaw_penalty* 0.12
    - thaw_penalty       * 0.08
    - aridity            * 0.06)
```

**Ground ice and active layer (`permafrost_diagnostics.py:78-99`):** if `extent < PERMAFROST_THRESHOLD` (`0.45`, defined at `permafrost_diagnostics.py:7`), both are set to `0.0`. Otherwise:

```
ground_ice_content_index = clamp(
      extent*0.35 + soil_moisture*0.22 + snow_or_ice*0.20 + organic*0.12 + (1 - drainage)*0.11)

active_layer_depth_m = clamp(
      0.28
    + thawing_degree_index / 5.6
    + drainage * 0.42
    + aridity  * 0.26
    - ground_ice_content_index * 0.52
    - organic     * 0.22
    - snow_or_ice * 0.32,
    lower=0.05, upper=4.5)
```

The active-layer expression is described in the enricher digest as "Stefan-like"; in the source it is a bounded linear combination of a thawing-degree proxy and soil/ice modifiers, not a solution of the Stefan equation.

**Classification thresholds (`_permafrost_class`, `permafrost_diagnostics.py:21-32`), evaluated in order:**

| Order | Condition | Class |
|---|---|---|
| 1 | `extent < 0.15` | `no_permafrost` |
| 2 | `extent < 0.45` | `seasonal_frost` |
| 3 | `ice_thickness_m >= 120.0` **and** `extent >= 0.62` | `ice_cemented_permafrost` |
| 4 | `extent >= 0.78` | `continuous_permafrost` |
| 5 | `extent >= 0.62` | `discontinuous_permafrost` |
| 6 | otherwise (`0.45 <= extent < 0.62`) | `sporadic_permafrost` |

**Region assembly (`permafrost_diagnostics.py:104-186`):** cells with `permafrost_extent_index >= 0.45` become region candidates; `_connected_components` BFS-groups them over the mesh `neighbors` graph, always starting from the smallest remaining cell id so the output is deterministic. Region ids are assigned in discovery order and mirrored back onto `cell["permafrost_region_id"]`; non-member cells keep `-1`.

**`permafrost_regions[]` record (12 fields, `permafrost_diagnostics.py:171-186`):**

| Field | Type | Meaning |
|---|---|---|
| `id` | int | Sequential region id |
| `cell_count` | int | Member count |
| `cell_ids` | int[] | Sorted member ids |
| `area_km2` | double | Σ member `area_km2` |
| `dominant_permafrost_class` | str | Most common class, ties broken alphabetically; fallback `sporadic_permafrost` |
| `dominant_biome` | str | Most common biome, ties alphabetical; fallback `tundra` |
| `mean_permafrost_extent_index` | double | Mean over members |
| `mean_active_layer_depth_m` | double | Mean over members |
| `mean_ground_ice_content_index` | double | Mean over members |
| `mean_frost_months` | double | Mean over members |
| `ice_covered_cell_count` | int | Members with `ice_thickness_m > 25.0` |
| `permafrost_class_counts` | dict | Sorted class histogram |

**Per-cell fields written (`permafrost_diagnostics.py:144-148`):** `permafrost_extent_index`, `active_layer_depth_m`, `ground_ice_content_index`, `permafrost_class`, `permafrost_region_id`.

### Full-world vs geo-only ordering divergence

In `generate_world` the call order is `biome_diagnostics` (`api.py:224`) → `permafrost_diagnostics` (`api.py:225`), so `cell["frost_months"]` already exists. In `generate_geo_world` the order is `permafrost_diagnostics` (`api.py:342`) → `biome_diagnostics` (`api.py:344`), so `frost_months` does **not** exist yet and the permafrost enricher takes its fallback branch, counting months with `T < 0` from `temperature_monthly_c` itself (`permafrost_diagnostics.py:50`). `biome_dynamics` derives `frost_months` from the same monthly array, so the two paths are expected to agree closely, but they are computed by different code and this equivalence is **not asserted anywhere in the source**.

---

## Glacial landform classification

`enrich_world_with_glacial_landforms(world)` — `src/magic_geo/glacial_landforms.py:279-340`. Called at `api.py:226` / `api.py:343`, after permafrost and after the flowline enricher (it reads `ice_flowline_driving_stress_kpa` and `ice_flowline_path_count`). Writes `world["glacial_landform_systems"]` plus six per-cell fields.

**Complete landform vocabulary** — `GLACIAL_LANDFORM_TYPES` at `glacial_landforms.py:8-16`:

| `glacial_landform_type` | Assigned when |
|---|---|
| `none` | No rule matched (the default) |
| `ice_cap` | Ice-covered and `_ice_cover_type` says broad/low-relief polar ice |
| `mountain_glacier` | Ice-covered and `_ice_cover_type` says otherwise |
| `fjord` | Native `landform == "fjord"` (passthrough only) |
| `glacial_valley` | Native `landform == "glacial_valley"`, or the erosion/relief/drainage rule |
| `glacial_lake` | Native `landform == "glacial_lake"`, or the freshwater + glacial-memory rule |
| `moraine` | Native `landform == "moraine"`, or the moraine-deposit + deglaciation rule |

**Assignment rules, in evaluation order** (`_glacial_landform_type`, `glacial_landforms.py:109-133`):

| Order | Condition | Result | Line |
|---|---|---|---|
| 1 | native `landform ∈ {fjord, glacial_valley, glacial_lake, moraine}` | that same string | 110-112 |
| 2 | native `landform == "ice_field"` **and** `ice_thickness_m >= 25.0` | `_ice_cover_type(...)` | 123-124 |
| 3 | `ice_thickness_m >= 25.0` **and** not `is_water` | `_ice_cover_type(...)` | 125-126 |
| 4 | not `is_water` **and** `moraine_deposition_m >= 0.65` **and** `deglaciation_age_ka >= 5.0` | `moraine` | 127-128 |
| 5 | freshwater **and** (`deglaciation_age_ka >= 5.0` **or** `moraine_deposition_m >= 0.35` **or** `ice_thickness_m >= 25.0`) | `glacial_lake` | 129-130 |
| 6 | not `is_water` **and** `glacial_erosion_m >= 7.0` **and** `relief >= 0.08` **and** (`runoff_mm_y >= 450.0` **or** `flow_accumulation >= 1.0e8`) | `glacial_valley` | 131-132 |
| 7 | otherwise | `none` | 133 |

`_ice_cover_type` (`glacial_landforms.py:98-106`) returns `ice_cap` when either `abs(lat_deg) >= 60.0 and elevation_m < 1800.0` (broad polar ice) or `abs(lat_deg) >= 50.0 and ice_thickness_m >= 420.0 and relief_index < 0.42 and elevation_m < 1700.0` (thick low-relief ice); otherwise `mountain_glacier`. `relief_index = clamp(max |Δelevation to any neighbor| / 1800, 0, 1)` (`glacial_landforms.py:52-57`).

Water-body vocabularies used by the rules: `MARINE_WATER_TYPES = {ocean, continental_shelf, inland_sea}` and `FRESHWATER_TYPES = {fresh_lake, lake}` (`glacial_landforms.py:17-18`); `_is_freshwater` also accepts `is_lake == true` (`glacial_landforms.py:41-42`).

**Four per-cell indices (`_glacial_indices`, `glacial_landforms.py:136-193`).** All four are computed for **every** cell, including non-glacial ones.

Normalizations: `ice_presence = ice_thickness_m/850`, `erosion_raw = glacial_erosion_m/75`, `deposition_raw = moraine_deposition_m/2.2`, `deglaciation = deglaciation_age_ka/82`, `velocity = ice_velocity_m_y/220`, `stress = ice_flowline_driving_stress_kpa/450`, `flowline_presence = ice_flowline_path_count/3`, `runoff = runoff_mm_y/2200`, `flow_accumulation = flow_accumulation/1.2e9`, all clamped `[0,1]`.

`landform_signal` is a lookup on the **native** landform (`glacial_landforms.py:143-149`): `ice_field → 0.86`, `fjord → 0.92`, `glacial_valley → 0.88`, `glacial_lake → 0.82`, `moraine → 0.78`, anything else `0.0`; then raised to at least `0.72` whenever the assigned glacial type is not `none` (`glacial_landforms.py:150-151`).

| Index | Formula |
|---|---|
| `glacial_erosion_intensity_index` | `clamp(erosion_raw*0.42 + stress*0.20 + velocity*0.12 + relief*0.12 + (0.15 if type ∈ {fjord, glacial_valley, glacial_lake} else 0) + flowline_presence*0.08)` |
| `glacial_deposition_index` | `clamp(deposition_raw*0.55 + deglaciation*0.18 + (0.22 if type == moraine else 0) + (0.08 if type ∈ {fjord, glacial_lake} else 0))` |
| `glacial_meltwater_index` | `clamp(runoff*0.34 + flow_accumulation*0.24 + water_contact*0.18 + (0.18 if freshwater or is_river else 0) + deglaciation*0.06)` |
| `glacial_landform_index` | `clamp(landform_signal*0.44 + ice_presence*0.20 + erosion_index*0.16 + deposition_index*0.10 + meltwater_index*0.10)` |

`water_contact` is `1.0` when the cell or any neighbor is freshwater/river **or** marine (`glacial_landforms.py:163`).

**System assembly (`_connected_regions`, `glacial_landforms.py:245-276`):** candidates are cells with `glacial_landform_type != "none"`. BFS from the smallest remaining id, expanding **only to neighbors with the identical `glacial_landform_type`** — so a system is homogeneous in type by construction. `cell["glacial_landform_system_id"]` mirrors the region id; non-members keep `-1`.

**`glacial_landform_systems[]` record (27 fields, `glacial_landforms.py:208-242`):**

| Field | Type | Meaning |
|---|---|---|
| `id` | int | Sequential region id |
| `glacial_landform_type` | str | The homogeneous type of the component |
| `cell_ids` | int[] | Sorted member ids |
| `cell_count` | int | Member count |
| `area_km2` | double | Σ member `area_km2` |
| `centroid_lat_deg` | double | Area-weighted 3-D unit-vector centroid, back-projected |
| `centroid_lon_deg` | double | Same |
| `mean_glacial_landform_index` | double | Mean over members |
| `mean_glacial_erosion_intensity_index` | double | Mean over members |
| `mean_glacial_deposition_index` | double | Mean over members |
| `mean_glacial_meltwater_index` | double | Mean over members |
| `mean_ice_thickness_m` | double | Mean over members |
| `mean_glacial_erosion_m` | double | Mean over members |
| `mean_moraine_deposition_m` | double | Mean over members |
| `mean_deglaciation_age_ka` | double | Mean over members |
| `mean_runoff_mm_y` | double | Mean over members |
| `mean_permafrost_extent_index` | double | Mean over members |
| `ice_covered_cell_count` | int | Members with `ice_thickness_m > 25.0` |
| `river_cell_count` | int | Members with `is_river` |
| `lake_cell_count` | int | Members passing `_is_freshwater` |
| `coastal_cell_count` | int | Members with marine contact |
| `permafrost_cell_count` | int | Members with `permafrost_extent_index >= 0.45` |
| `tundra_cell_count` | int | Members with `biome == "tundra"` |
| `linked_ice_sheet_ids` | int[] | Sorted distinct non-negative `ice_sheet_id` |
| `linked_basin_ids` | int[] | Sorted distinct non-negative `basin_id` |
| `dominant_biome` | str | Most common biome, ties alphabetical |
| `dominant_landform` | str | Most common **native** landform, ties alphabetical |

**Empty-world contract (`glacial_landforms.py:282-292`):** if `cells` is missing, not a list, or empty, the enricher writes `glacial_landform_systems = []` and explicitly writes eight summary keys rather than leaving them absent — seven numeric keys set to `0` / `0.0` plus `glacial_landform_type_counts = {}`. This is deliberate: downstream validators check the mirrors unconditionally. It is also **not** shared by the other cell-driven cryosphere enrichers — `enrich_world_with_ice_flowline_history` and `enrich_world_with_permafrost_diagnostics` return early on a missing or empty `cells` list and write no summary keys at all (`cryosphere_flow.py:91-93`, `permafrost_diagnostics.py:130-132`).

---

## Sea ice

**There is no sea-ice model.** `derive_cryosphere_state` returns immediately for any cell with `is_water == true` (`cpp/src/engine/environment.cpp:33-35`) after zeroing the six ice state fields, so a serialized water cell always has `ice_thickness_m == 0.0`, `glacier_flow_to == -1`, `ice_surface_mass_balance_m_y == 0.0`, `basal_sliding_index == 0.0`, `ice_velocity_m_y == 0.0` and `glacial_erosion_m == 0.0`. `generate_ice_sheets` likewise excludes water cells from both the seed test and the BFS expansion (`environment.cpp:1038`, `1066`).

Two consequences worth knowing:

- Marine ice-adjacent morphology exists only as a *land- or shelf-side* signal: the native `fjord(16)` landform requires a **water** cell with a glaciated (≥ 80 m) neighbor (`environment.cpp:431-432`), and `marine_margin_fraction` in the stability enricher counts sheet cells touching water (`cryosphere_stability.py:32-45`). Neither implies floating ice.
- Some downstream enrichers *do* contain ice-suppression terms keyed on `ice_thickness_m` at marine cells — for example the reef growth score subtracts `clamp(ice_thickness_m / 60.0) * 0.54` (`src/magic_geo/reef_diagnostics.py:198`, `211`), which the unit test `test_sea_ice_suppresses_reef_growth` (`tests/test_enrichers_terrain_biome.py:1189-1205`) exercises with a hand-built marine cell. In a generated world that branch is unreachable because the engine never puts ice on water.

Calving is likewise diagnostic only: `calving_susceptibility_index` and `projected_calving_loss_km3` are scores derived from marine-margin fraction, velocity, sliding and thermal pressure (`cryosphere_stability.py:105-111`, `154`). No iceberg mass leaves the system and no floating tongue is represented.

---

## Per-cell cryosphere field table

Native fields, from `cpp/src/engine/types/core.hpp:187-200`, serialized at `cpp/src/engine/entity_serialization.cpp:319-337`. `P` = `output.float_precision` (default `4`); `S` = `surface_precision` = `max(10, float_precision)`.

| # | Field | Type | Precision | Written by | Notes |
|---|---|---|---|---|---|
| 135 | `ice_thickness_m` | double | `P` | `derive_cryosphere_state` (2nd call) | `0` on water; `0` or `>= 25` on land |
| 136 | `ice_sheet_id` | int | — | `generate_ice_sheets` | `-1` if unassigned; includes peripheral non-ice members |
| 137 | `glacier_flow_to` | int | — | `derive_cryosphere_state` | Steepest-descent mesh neighbor; `-1` at local minima |
| 138 | `ice_surface_mass_balance_m_y` | double | `P` | `derive_cryosphere_state` | Clamped `[-4.0, 3.2]` |
| 139 | `basal_sliding_index` | double | `P` | `derive_cryosphere_state` | Clamped `[0, 1]` |
| 140 | `ice_velocity_m_y` | double | `P` | `derive_cryosphere_state` | `[0, 420]` with a flow target, `[0, 120]` without |
| 141 | `glacial_erosion_m` | double | `P` | `derive_cryosphere_state` | Erosion **potential**, clamped `[0, 85]`; `0` at local minima |
| 142 | `glacial_sediment_production_m` | double | `S` | `transport_glacial_sediment` | Not reset by the second cryosphere pass |
| 143 | `glacial_sediment_deposition_m` | double | `S` | `transport_glacial_sediment` | Same |
| 144 | `glacial_sediment_net_m` | double | `S` | `transport_glacial_sediment` | `deposition - production` |
| 145 | `glacial_sediment_outgoing_transfer_count` | int | — | `transport_glacial_sediment` | `0` or `1` (single downhill target) |
| 146 | `glacial_sediment_incoming_transfer_count` | int | — | `transport_glacial_sediment` | Number of upstream contributors |
| 147 | `moraine_deposition_m` | double | `P` | `generate_ice_sheets` | Clamped `[0, 4]`; only on deglaciated sheet members |
| 148 | `deglaciation_age_ka` | double | `P` | `generate_ice_sheets` | Clamped `[0, 120]`; memory index, not a date |

Python-added cryosphere cell fields:

| Field | Type | Range | Added by |
|---|---|---|---|
| `ice_flowline_flux_km3_y` | double | `>= 0` | `cryosphere_flow.py:165` |
| `ice_flowline_driving_stress_kpa` | double | `>= 0` | `cryosphere_flow.py:166-169` |
| `ice_flowline_strain_heating_index` | double | `[0, 1]` | `cryosphere_flow.py:170-173` |
| `ice_flowline_path_count` | int | `>= 0` | `cryosphere_flow.py:174` |
| `permafrost_extent_index` | double | `[0, 1]` | `permafrost_diagnostics.py:144` |
| `active_layer_depth_m` | double | `0.0` or `[0.05, 4.5]` | `permafrost_diagnostics.py:145` |
| `ground_ice_content_index` | double | `[0, 1]` | `permafrost_diagnostics.py:146` |
| `permafrost_class` | str | 6-value vocabulary | `permafrost_diagnostics.py:147` |
| `permafrost_region_id` | int | `-1` or region id | `permafrost_diagnostics.py:148`, `162` |
| `glacial_landform_index` | double | `[0, 1]` | `glacial_landforms.py:307` |
| `glacial_erosion_intensity_index` | double | `[0, 1]` | `glacial_landforms.py:308` |
| `glacial_deposition_index` | double | `[0, 1]` | `glacial_landforms.py:309` |
| `glacial_meltwater_index` | double | `[0, 1]` | `glacial_landforms.py:310` |
| `glacial_landform_type` | str | 7-value vocabulary | `glacial_landforms.py:311` |
| `glacial_landform_system_id` | int | `-1` or system id | `glacial_landforms.py:312`, `274` |

---

## Summary keys

**Native (`cpp/src/engine/summary.cpp:2069-2086`)**, all at `float_precision`:

| Key | Denominator / definition |
|---|---|
| `mean_ice_thickness_m` | Σ `ice_thickness_m` ÷ **all** cells |
| `mean_glacial_erosion_m` | Σ `glacial_erosion_m` ÷ **all** cells |
| `mean_ice_surface_mass_balance_m_y` | Σ over glacier cells ÷ glacier cell count (`0.0` if none) |
| `mean_basal_sliding_index` | Σ over glacier cells ÷ glacier cell count |
| `mean_ice_velocity_m_y` | Σ over glacier cells ÷ glacier cell count |
| `glaciated_land_fraction` | glacier cells ÷ land cells |
| `ice_sheet_count` | `ice_sheets.size()` |
| `mean_ice_sheet_retreat_rate_m_y` | Σ sheet `retreat_rate_m_y` ÷ sheet count |
| `moraine_deposition_cell_count` | cells with `moraine_deposition_m > 0.0` |
| `mean_moraine_deposition_m` | Σ `moraine_deposition_m` ÷ **all** cells |
| `mean_deglaciation_age_ka` | Σ ÷ cells with `deglaciation_age_ka > 0.0` |

"Glacier cell" here is `!is_water && ice_thickness_m > 25.0` (`summary.cpp:475`). Related glacial-sediment aggregates are derived from the stage history but emitted in **two other** summary blocks, not this one: `glacial_sediment_transport_stage_count`, `glacial_sediment_transfer_count`, `glacial_sediment_source_cell_count`, `glacial_sediment_target_cell_count`, `glacial_sediment_land_target_transfer_count`, `glacial_sediment_marine_target_transfer_count`, `glacial_sediment_production_volume_km3`, `glacial_sediment_deposition_volume_km3`, `glacial_sediment_mass_balance_residual_km3`, `glacial_sediment_terrain_volume_change_residual_km3`, `max_glacial_sediment_source_production_depth_m` and `max_glacial_sediment_target_deposition_depth_m` at `summary.cpp:1467-1499`; `glacial_sediment_alluvium_entrainment_volume_km3` and `glacial_sediment_bedrock_erosion_volume_km3` at `summary.cpp:2000-2004`.

**Python enricher summary keys:**

| Key | Enricher | Source line |
|---|---|---|
| `ice_sheet_history_count` | `cryosphere_dynamics` | 143 |
| `ice_sheet_history_step_count` | `cryosphere_dynamics` | 144 |
| `ice_sheet_history_total_surface_balance_km3` | `cryosphere_dynamics` | 145 |
| `ice_sheet_history_total_dynamic_loss_km3` | `cryosphere_dynamics` | 146 |
| `ice_sheet_history_total_retreat_loss_km3` | `cryosphere_dynamics` | 147 |
| `ice_sheet_history_total_retreat_distance_km` | `cryosphere_dynamics` | 148 |
| `ice_sheet_history_peak_volume_km3` | `cryosphere_dynamics` | 149 |
| `ice_sheet_history_final_volume_km3` | `cryosphere_dynamics` | 150 |
| `ice_sheet_stability_history_count` | `cryosphere_stability` | 226 |
| `ice_sheet_stability_step_count` | `cryosphere_stability` | 227 |
| `ice_sheet_retreat_threshold_event_count` | `cryosphere_stability` | 228 |
| `high_ice_sheet_instability_count` | `cryosphere_stability` | 229 |
| `mean_ice_sheet_stability_index` | `cryosphere_stability` | 230 |
| `max_ice_sheet_stability_index` | `cryosphere_stability` | 231 |
| `mean_calving_susceptibility_index` | `cryosphere_stability` | 232 |
| `mean_grounding_line_instability_index` | `cryosphere_stability` | 233 |
| `ice_sheet_total_projected_calving_loss_km3` | `cryosphere_stability` | 234 |
| `ice_sheet_total_projected_grounding_line_retreat_km` | `cryosphere_stability` | 235 |
| `ice_sheet_stability_class_counts` | `cryosphere_stability` | 236 |
| `ice_flowline_history_count` | `cryosphere_flow` | 237 |
| `ice_flowline_step_count` | `cryosphere_flow` | 238 |
| `ice_flowline_cell_count` | `cryosphere_flow` | 239 |
| `ice_flowline_total_dynamic_flux_km3_y` | `cryosphere_flow` | 240 |
| `ice_flowline_total_dynamic_loss_km3_y` | `cryosphere_flow` | 241 |
| `ice_flowline_total_melt_loss_km3_y` | `cryosphere_flow` | 242 |
| `ice_flowline_total_glacial_erosion_m` | `cryosphere_flow` | 243 |
| `ice_flowline_total_path_length_km` | `cryosphere_flow` | 244 |
| `ice_flowline_mean_path_length_km` | `cryosphere_flow` | 245 |
| `ice_flowline_max_driving_stress_kpa` | `cryosphere_flow` | 246 |
| `ice_flowline_max_final_flux_km3_y` | `cryosphere_flow` | 247 |
| `ice_flowline_max_strain_heating_index` | `cryosphere_flow` | 248 |
| `permafrost_cell_count` | `permafrost_diagnostics` | 190 |
| `permafrost_region_count` | `permafrost_diagnostics` | 191 |
| `mean_permafrost_extent_index` | `permafrost_diagnostics` | 192 |
| `mean_active_layer_depth_m` | `permafrost_diagnostics` | 193 |
| `mean_ground_ice_content_index` | `permafrost_diagnostics` | 194 |
| `continuous_permafrost_cell_count` | `permafrost_diagnostics` | 195 |
| `ice_cemented_permafrost_cell_count` | `permafrost_diagnostics` | 196 |
| `permafrost_class_counts` | `permafrost_diagnostics` | 197 |
| `glacial_landform_cell_count` | `glacial_landforms` | 325 |
| `glacial_landform_system_count` | `glacial_landforms` | 326 |
| `glacial_landform_area_km2` | `glacial_landforms` | 327 |
| `mean_glacial_landform_index` | `glacial_landforms` | 328 |
| `mean_glacial_erosion_intensity_index` | `glacial_landforms` | 329 |
| `mean_glacial_deposition_index` | `glacial_landforms` | 330 |
| `mean_glacial_meltwater_index` | `glacial_landforms` | 331 |
| `glacial_landform_type_counts` | `glacial_landforms` | 332 |
| `ice_cap_landform_cell_count` | `glacial_landforms` | 333 |
| `mountain_glacier_landform_cell_count` | `glacial_landforms` | 334 |
| `fjord_landform_cell_count` | `glacial_landforms` | 335 |
| `glacial_valley_landform_cell_count` | `glacial_landforms` | 336 |
| `glacial_lake_landform_cell_count` | `glacial_landforms` | 337 |
| `moraine_landform_cell_count` | `glacial_landforms` | 338 |

Note the divisor asymmetry: `mean_permafrost_extent_index` divides by **all** cells (`permafrost_diagnostics.py:192`), while `mean_active_layer_depth_m` and `mean_ground_ice_content_index` divide by the **permafrost cell count** (`permafrost_diagnostics.py:193-194`). The four `mean_glacial_*` keys all divide by **all** cells (`glacial_landforms.py:324`, `328-331`).

---

## Downstream consumers of cryosphere state

Cryosphere fields are read far outside the cryosphere layer. The table below lists the reads that carry model semantics: the enrichers that write world state, plus the four `*_validation.py` replay validators that re-derive human-geography scores from ice (those four are not imported by `api.py` and write nothing — they only recompute and compare). Mechanical reads are listed after the table.

| Consumer | Field read | Effect | Line |
|---|---|---|---|
| `climate_energy.py` | `ice_thickness_m` | Surface albedo: `ice > 20 or biome == ice_cap` ⇒ base `0.58 + clamp(ice/2500)*0.12`, regime label | 37, 48-50 |
| `climate_energy.py` | `ice_thickness_m` | Energy-stress penalty `clamp(ice/1800) * 3.0` | 84 |
| `biome_dynamics.py` | `ice_thickness_m` | `> 120.0` ⇒ expected biome `ice_cap`; limiting factor `persistent_ice` | 42, 74 |
| `biome_ecotones.py` | `ice_thickness_m` | Ecotone eligibility | 54 |
| `biome_realism.py` | `ice_thickness_m` | `> 20.0` in the tundra/cold check | 148 |
| `species_ranges.py` | `ice_thickness_m`, `permafrost_extent_index` | Guild habitat envelope (`ice/800`, permafrost clamp) | 124-125 |
| `reef_diagnostics.py` | `ice_thickness_m` | Growth penalty `clamp(ice/60) * 0.54` | 198, 211 |
| `wildfire_disturbance.py` | `ice_thickness_m` | Fuel/ignition suppression `clamp(ice/500)` | 65, 93, 106 |
| `ecosystem_dynamics.py` | `ice_thickness_m` | Productivity/disturbance terms `clamp(ice/1200)`; `> 120.0` cold gate | 36, 47, 67 |
| `karst_diagnostics.py` | `ice_thickness_m` | Dissolution suppression `clamp(ice/800)` | 65 |
| `aquifer_resources.py` | `ice_thickness_m` | Recharge modifier `clamp(ice/1600)` | 105 |
| `river_hydraulics.py` | `ice_thickness_m` | Manning roughness `+ clamp(ice/300) * 0.010` | 44, 159 |
| `river_channel_morphology.py` | `ice_thickness_m` | Channel morphology term `clamp(ice/450)` | 197 |
| `navigability_diagnostics.py` | `ice_thickness_m` | Navigability penalty `clamp(ice/350)`, `clamp(ice/300)` | 54, 107 |
| `port_sites.py` | `ice_thickness_m` | Port penalty `clamp(ice/220)`; `severe_ice` at `>= 80.0` or `biome == ice_cap` | 105, 217, 258 |
| `route_corridors.py` | `ice_thickness_m` | Traversal cost `clamp(ice/280)`, `/260`, `/200`, neighbor `/320` | 93, 113, 155, 180 |
| `resource_dynamics.py` | `ice_thickness_m` | Accessibility `clamp(ice/1600)` | 92 |
| `natural_frontiers.py` | `ice_thickness_m`, `permafrost_class` | `ice > 40` ⇒ barrier type `ice`; barrier score `clamp(ice/420)` with a `0.58` floor | 30-34, 57-59 |
| `logistics_history.py` | `ice_thickness_m` | Movement cost `clamp(ice/1200)` | 168 |
| `campaign_operations_validation.py` | `ice_thickness_m` | Movement cost `clamp(ice/1200)` | 106 |
| `human_geography_validation.py` | `ice_thickness_m`, `permafrost_class` | Frontier typing and scoring; `clamp(ice/400)`, `clamp(ice/420)` with a `0.58` floor | 158, 395, 419-421 |
| `cultural_geography_validation.py` | `ice_thickness_m` | `> 20.0` gates several cultural checks | 306, 329, 342, 356 |
| `civilization_geography_validation.py` | `ice_thickness_m` | Population capacity terms | 189, 195 |
| `land_use_zones.py` | `ice_thickness_m` | Zone suitability penalty `clamp(ice/400)` | 56 |
| `glacial_landforms.py` | `ice_flowline_driving_stress_kpa`, `ice_flowline_path_count` | Erosion-intensity index | 159-160 |

Three further groups read `ice_thickness_m` and are excluded from the table because they only inspect or re-serialize it: the geo validators (`geo_validation.py:474`, `:2133`, `:2157`; `geo_validation_physics.py:1088`, `:1156`), the CLI replay validators (`cli/commands/validate.py` and `cli/validators/{corridors,hydrology,navigability,ports,rivers,sediment,settlement}.py`), and the exporters (`io/cells_csv.py`, `io/raster_map.py`, `io/summary_markdown.py`, `io/svg_map.py`).

The native settlement/landform coupling is described in [Glacial landforms in the native landform classifier](#glacial-landforms-in-the-native-landform-classifier).

---

## Validation

Three independent validators cover the cryosphere.

**1. `geo_validation.py` — `cryosphere / ice_sheet_and_flow_coherence`** (`src/magic_geo/geo_validation.py:2124-2194`). Fails unless:

| Rule | Line |
|---|---|
| Every cell has `ice_thickness_m >= 0.0` | 2135 |
| Every land cell with `ice_thickness_m > 25.0` has an `ice_sheet_id` present in `ice_sheets[]` | 2135-2140 |
| `glacier_flow_to` is an int; if `>= 0` it is a mesh neighbor, the cell has `ice_thickness_m > 0`, and the target elevation is not higher than the source by more than `1e-6` | 2141-2149 |
| Each sheet's `cell_count`, `area_km2` (tolerance `max(0.01, area*1e-6)`) and `mean_ice_thickness_m` (tolerance `1e-3`) exactly reproduce the area-weighted member aggregate over `ice_thickness_m > 25.0` non-water cells | 2151-2176 |
| `len(ice_sheet_records) == len(ice_sheets)` (no duplicate ids) | 2184 |

**2. `geo_validation_subsystems.py` — domain `cryosphere_permafrost_glacial`** (`_validate_cryosphere`, `src/magic_geo/geo_validation_subsystems.py:1739-1939`), three checks:

| Check | Enforces |
|---|---|
| `ice_sheet_history_conservation` | `history.id == history.ice_sheet_id`; sheet coverage is exact; `time_step_count == len(steps)`; every step's start volume/area tightly equals the previous end; `end_volume ≈ start + surface - dynamic - retreat + adjustment` within `3.0e-3`; volumes and areas are nonnegative; `basal_sliding_index` and `accumulation_area_fraction` are bounded; endpoint aggregates and the four `total_*` sums match; three summary mirrors |
| `stability_and_flowline_sources` | Sequential ids on both families; stability histories cover exactly the source sheets; five sheet-level and five step-level indices are bounded `[0,1]`; every flowline path is unique, adjacency-valid and cell-resolvable; `source_cell_id == path[0]`; `ice_sheet_id ∈ sheet_ids`; step `cell_id` sequence equals the path; all five flux terms finite and `>= 0`; `abs(balance_residual_km3_y) <= 2.0e-5`; four summary mirrors |
| `permafrost_and_glacial_membership` | Sequential region ids; non-overlapping, exact, invertible cell partitions for both `permafrost_region_id` and `glacial_landform_system_id`; `cell_count` and `area_km2` reconstruct from members; the eligibility predicate holds for every member (`permafrost_extent_index >= 0.45`; `glacial_landform_type != "none"`); six per-cell indices bounded and `active_layer_depth_m` nonnegative; four summary mirrors |

**3. `geo_layer_contracts.py` — layer `cryosphere`, phase 9** (`src/magic_geo/geo_layer_contracts.py:202-220`):

| Contract key | Value |
|---|---|
| `dependencies` | `("climate_atmosphere", "erosion_sediment")` |
| `required_outputs` | `glacial_sediment_transport_model` (dict), `glacial_sediment_transport_history` (nonempty list), `ice_sheets`, `ice_sheet_histories`, `ice_sheet_stability_histories`, `ice_flowline_histories`, `permafrost_regions`, `glacial_landform_systems` (lists) |
| `validator_domains` | `("cryosphere", "cryosphere_permafrost_glacial")` |
| `temporal_class` | `single_native_bulk_coupling_plus_diagnostic_histories` |
| `evidence_class` | `mass_replay_without_dynamic_ice_solver` |

The `soils_pedogenesis` layer declares `cryosphere` as a dependency (`geo_layer_contracts.py:225`).

Native-side hard failures that abort generation entirely (not soft validator findings): `"glacial sediment transfer target is invalid"` (`environment.cpp:150-152`), `"glacial sediment transfer source state is invalid"` (`environment.cpp:162-164`), `"glacial sediment-interface update changed the compatibility surface"` (`environment.cpp:260-262`), `"glacial sediment history is not linked to the final cryosphere stage"` (`process_serialization.cpp:926-928`), `"glacial sediment source-partition linkage is malformed"` (`process_serialization.cpp:942-944`), `"glacial sediment input cells are not cell-id indexed"` (`process_serialization.cpp:951-953`).

---

## Worked example

Generate a geo-only world and inspect the whole cryosphere layer:

```bash
magic-geo init-config --output magic-geo.yaml
magic-geo generate --config magic-geo.yaml --output runs/world.json --geo-only
magic-geo validate-geo --world runs/world.json --profile earthlike
```

Read the layer from Python:

```python
import json

world = json.load(open("runs/world.json"))

# 1. The stage is terminal and zero-duration.
clock = world["simulation_clock"]
assert clock["configured_cryosphere_coupling_stage_count"] == 1
assert clock["cryosphere_advances_nominal_time"] is False
assert clock["physical_time_resolved"] is False

# 2. Exactly one glacial transport stage, linked to the final feedback record.
stage = world["glacial_sediment_transport_history"][0]
assert stage["id"] == 0
assert stage["advances_nominal_time"] is False
print(stage["transfer_count"], stage["production_volume_km3"], stage["mass_balance_residual_km3"])

# 3. The pre-transport operands, not the serialized cell state.
row = stage["input_cells"][123]
print(row["ice_thickness_m"], row["glacial_erosion_m"], row["sediment_thickness_m"])

# 4. Sheet 0 is always the largest by area, and carries the stability annotations.
sheet = world["ice_sheets"][0]
print(sheet["retreat_stage"], sheet["area_km2"], sheet["equilibrium_line_altitude_m"])
print(sheet["ice_sheet_stability_class"], sheet["calving_susceptibility_index"])

# 5. Its 8-step reconstructed history closes on volume.
history = next(h for h in world["ice_sheet_histories"] if h["ice_sheet_id"] == 0)
for step in history["steps"]:
    closed = (step["start_volume_km3"] + step["surface_balance_km3"]
              - step["dynamic_loss_km3"] - step["retreat_loss_km3"]
              + step["stabilization_adjustment_km3"])
    assert abs(closed - step["end_volume_km3"]) <= 3.0e-3
```

Reproduce one glacial transfer by hand from the stage record:

```python
GLACIAL_SEDIMENT_MOBILE_FRACTION = 0.28   # cpp/src/engine/constants.hpp:67

t = world["glacial_sediment_transport_history"][0]["transfers"][0]
source_depth = t["source_glacial_erosion_m"] * GLACIAL_SEDIMENT_MOBILE_FRACTION
volume       = source_depth * t["source_area_km2"] / 1000.0
target_depth = volume * 1000.0 / t["target_area_km2"]

assert abs(source_depth - t["source_production_depth_m"]) < 1e-9
assert abs(volume       - t["transfer_volume_km3"])       < 1e-9
assert abs(target_depth - t["target_deposition_depth_m"]) < 1e-9
```

Recompute one flowline driving stress:

```python
import math

g = world["planet_parameters"]["gravity_g"] * 9.81   # ICE_FLOW_REFERENCE_GRAVITY_M_S2
s = world["ice_flowline_histories"][0]["steps"][0]
tau_kpa = 917.0 * g * s["ice_thickness_m"] * max(0.0002, s["surface_slope"]) / 1000.0
assert math.isclose(tau_kpa, s["driving_stress_kpa"], abs_tol=1e-5)
```

Note the `--geo-only` path requires `output.include_cells` to be true; `generate_geo_world` raises `ValueError` otherwise. The permafrost and glacial-landform enrichers need `cells` to produce anything at all.

---

## Limitations and unresolved claims

**The native layer is a diagnostic classifier, not an ice-dynamics solver.** The model contract states this in the document itself: `multi_step_ice_dynamics_resolved: false` and `model_limitation: "single_post_erosion_bulk_transfer_without_calibrated_time_multistep_ice_dynamics_or_grain_classes"` (`cpp/src/engine/process_serialization.cpp:880-882`). There is no continuity equation for ice, no Glen flow law, no thermomechanical coupling, no time-stepped thickness evolution. `ice_thickness_m` is a bounded score of temperature, precipitation, latitude and elevation evaluated once per cell; `ice_velocity_m_y` and `basal_sliding_index` are bounded scores, not solutions of a momentum balance; `glacial_erosion_m` is explicitly labelled an `ice_thickness_times_local_slope_proxy_bounded_85m_v1` potential.

**Physical time is unresolved everywhere in this layer.** `simulation_clock.physical_time_resolved`, `nominal_time_calibrated`, `absolute_geological_age_resolved`, `process_rate_calibration_resolved` and `time_step_convergence_demonstrated` are all `false` (`process_serialization.cpp:2083-2087`). The cryosphere stage does not advance even the nominal clock (`cryosphere_advances_nominal_time: false`). The `_ka` and `_years` axes of the ice-sheet, stability and flowline histories are reconstructed diagnostic coordinates with no calibration to the maturation clock or to any absolute age.

**`deglaciation_age_ka` is not a date.** It is `clamp(2 + 80·cold_memory + 22·erosion_memory, 0, 120)` (`environment.cpp:1097`) — a monotone function of present-day temperature and glacial erosion potential. It carries the unit `ka` but encodes no chronology.

**`equilibrium_line_altitude_m` is not a mass-balance ELA.** It is the member-elevation value at the truncated index `0.42·(n−1)` of the sorted elevation list (`environment.cpp:1081-1084`) — a fixed order statistic, unrelated to where `ice_surface_mass_balance_m_y` crosses zero.

**Mass conservation is bulk-reference-volume only.** `glacial_sediment_transport_model.mass_conserving: true` is immediately qualified by `mass_conserving_semantics: "bulk_reference_volume_only_not_dry_rock_mass"` (`process_serialization.cpp:873-875`). No dry-rock mass, density, porosity, compaction, grain-size class or provenance claim is made; `source_partition_audit_is_mass_claim: false` and `source_partition_audit_is_provenance_claim: false` (`process_serialization.cpp:867`, `868`).

**No glacio-eustasy and no ice-load isostasy.** Ice mass is never exchanged with the ocean inventory, and `ice_thickness_m` never enters the isostatic equilibrium calculation. Sea level after the cryosphere stage changes only because the *sediment interface* moved, never because ice grew or melted.

**No sea ice, no ice shelves, no calving flux.** `derive_cryosphere_state` returns before assigning anything to water cells (`environment.cpp:33-35`). `calving_susceptibility_index` and `projected_calving_loss_km3` are risk scores computed from marine-margin fraction and sheet state; no mass is removed and no floating ice is represented. `grounding_line_instability_index` likewise names a process the model does not simulate.

**The two `derive_cryosphere_state` calls produce different fields.** The serialized cell ice state is the *second* call's output, on the stabilized post-transport surface; the transport was driven by the *first* call's output, preserved only in `glacial_sediment_transport_history[0].input_cells[]`. Any analysis that multiplies the serialized `glacial_erosion_m` by `0.28` and expects `glacial_sediment_production_m` will not close.

**The ice-sheet history is a reconstruction, not a replay.** `enrich_world_with_ice_sheet_history` inflates the present-day volume by `initial_multiplier` and integrates backwards; nothing in that trajectory was ever computed by the engine. The scale factors `0.035` (surface balance and dynamic loss), `0.08` (retreat loss), `0.16` / `0.22` (per-step gain/loss caps) and the `area_km2 * 0.10` area floor are unlabelled tuning constants with no stated derivation. The `stabilization_adjustment_km3` term exists to absorb the clamp, so a "closed" volume budget in this family means "the clamp was recorded", not "the physics balanced".

**`stagnant` sheets fall through the history bias table.** `stage_retreat_bias` (`cryosphere_dynamics.py:40-45`) enumerates `advancing`, `stable`, `retreating` and `relict`, but the native classifier also emits `stagnant` (`environment.cpp:1018-1020`, `schema_names.hpp:132-134`). Stagnant sheets therefore receive the `0.70` default bias rather than a stage-specific one.

**`permafrost_class` vocabulary mismatch downstream.** `permafrost_diagnostics.py:21-32` emits `no_permafrost`, `seasonal_frost`, `sporadic_permafrost`, `discontinuous_permafrost`, `continuous_permafrost`, `ice_cemented_permafrost`. Two consumer modules, at four call sites, test for the strings `"continuous"` and `"ice_sheet"` instead — `natural_frontiers.py:30-34` and `:57-59`, and `human_geography_validation.py:395` and `:419-421`. Those branches cannot fire on the vocabulary the permafrost enricher actually writes; the ice-barrier signal in those consumers therefore reduces to the `ice_thickness_m > 40.0` / `clamp(ice/420)` terms alone. This is stated as an observation of the current source, not as a known-intended behavior.

**Permafrost `frost_months` provenance differs between scopes.** In `generate_world`, `frost_months` comes from `biome_dynamics.py:158`; in `generate_geo_world`, `permafrost_diagnostics` runs first and recomputes it from `temperature_monthly_c` (`permafrost_diagnostics.py:50`). No test or validator asserts the two agree.

**The `freezing_degree_index` is dead code.** It is computed at `permafrost_diagnostics.py:48` and never used in any emitted term.

**Flowline "steps" are spatial, not temporal.** `time_step_count` counts path cells; `steps[].step` is a path index; the fluxes are per-year steady-state quantities. The exact `balance_residual_km3_y ≈ 0` closure is an algebraic identity of the construction (the terminal cell sweeps the remainder into `dynamic_loss_km3_y`, `cryosphere_flow.py:154-158`), not evidence of a conserved physical budget.

**The flowline sample is small and non-exhaustive.** At most `flowline_limit = 10` paths of at most `max_path_length = 48` cells are traced, one per distinct `ice_sheet_id` first (with `-1` counting as a sheet), then by rank. `ice_flowline_*` per-cell fields are maxima over whatever paths happened to touch the cell; cells off every traced path keep `0.0`.

**The flowline source selector and its validator disagree about unassigned ice.** `_select_flowline_sources` admits a candidate whose `ice_sheet_id` is `-1` and copies that value onto the emitted record (`cryosphere_flow.py:44-48`, `220`), while `stability_and_flowline_sources` requires `flowline.ice_sheet_id ∈ sheet_ids` — a set that only ever contains non-negative `ice_sheets[].id` values (`geo_validation_subsystems.py:1848`). In a natively generated world the tension is latent, because `generate_ice_sheets` assigns a sheet to every non-water cell above the 25 m floor and only such cells can be candidates; the mismatch is reachable only for hand-built or externally edited worlds. Nothing in the source asserts that the two agree.

**Glacial landform systems are homogeneous by construction.** `_connected_regions` only expands to neighbors with an identical `glacial_landform_type` (`glacial_landforms.py:268-269`), so a physically continuous glaciated massif spanning `ice_cap` and `mountain_glacier` cells is reported as two disjoint systems, not one.

**Two different glacier-neighbor thresholds are in play.** `has_glacier_neighbor` defaults to `80.0` m (`internal.hpp:317-321`) and is used with the default in `derive_landforms` (`environment.cpp:428`), but with an explicit `25.0` m in `generate_ice_sheets` (`environment.cpp:1090`, `1098`). A cell can therefore be a peripheral ice-sheet member without qualifying for the `fjord`/`glacial_lake`/`moraine` landform codes, and vice versa.

**Accelerator parity is not claimed for this layer.** Per the engine invariants, the CPU path is authoritative; accelerators only run separately named, discarded-output shadows over already-computed CPU results. Nothing in the cryosphere path is dispatched to OpenCL or CUDA.

---

## See also

- [Architecture](../04-architecture.md) — where the cryosphere block sits in the whole run
- [Native Engine (C++ Core)](../08-native-engine.md) — `environment.cpp` and the stage ordering contract
- [World Document Schema](../10-world-schema.md) — the 155-field cell record and the top-level key order
- [Serialization and World Formats](../11-serialization.md) — precision floors for the `*_by_cell` replay arrays
- [Validation](../12-validation.md) — `validate-geo` and the `cryosphere` domain
- [Geo Validation Suite](../13-geo-validation-suite.md) — the `cryosphere_permafrost_glacial` subsystem checks
- [Climate and Atmosphere](climate-and-atmosphere.md) — the `temperature_c` / `precipitation_mm_y` inputs and the ice-albedo energy term
- [Hydrology, Rivers and Lakes](hydrology-and-rivers.md) — the stabilization loop the cryosphere re-triggers
- [Sediment, Routing and Stratigraphy](sediment-and-stratigraphy.md) — the sediment interface, source partition and glacial-till facies
- [Erosion, Maturation and Landscape Evolution](erosion-and-maturation.md) — the maturation loop the cryosphere terminates
- [Topography, Isostasy and Thermal Subsidence](topography-and-isostasy.md) — why ice load does not enter isostasy
- [Oceans, Currents and Coasts](oceans-and-coasts.md) — the sea-level solve and marine labelling
- [Soils and Weathering](soils.md) — tundra soil forcing and the pedogenesis dependency on the cryosphere layer
- [Biomes, Ecosystems and Disturbance](biomes-and-ecology.md) — `ice_cap` biome, `frost_months`, and the permafrost/species coupling
- [Glossary](../21-glossary.md)
