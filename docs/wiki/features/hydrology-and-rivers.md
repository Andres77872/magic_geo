# Hydrology, Rivers and Lakes

[Wiki home](../README.md) > Features

Surface water in magic-geo is a two-tier system. The **native C++ core** owns the authoritative state: a per-cell annual water budget that must close exactly, a priority-flood depression solve, a drainage graph with flow accumulation, and river extraction by flow-accumulation percentile — all re-solved inside a bounded convergence loop that runs at every coupled maturation stage — plus lake basins and watersheds, which are derived once, terminally, *after* that loop has finished. On top of that, **Python enrichers** add non-authoritative diagnostics: channel geometry, Manning hydraulics, wetlands, navigability, lake-overflow trajectories and river-reorganization trajectories. This page documents both tiers exhaustively, keeps the authoritative/diagnostic split explicit at every step, and carries forward the codebase's own refusals — physical time is never resolved, the nominal Ma coordinate is never calibrated, and no diagnostic trajectory here is a timed simulation.

## On this page

- [Where hydrology runs in the pipeline](#where-hydrology-runs-in-the-pipeline)
- [The water budget on the sphere](#the-water-budget-on-the-sphere)
- [Priority-flood depression handling](#priority-flood-depression-handling)
- [The `preserve_geologic_depressions` policy, both branches](#the-preserve_geologic_depressions-policy-both-branches)
- [Numeric depression correction: breach or temporary lake](#numeric-depression-correction-breach-or-temporary-lake)
- [Drainage directions, accumulation and the conditioned surface](#drainage-directions-accumulation-and-the-conditioned-surface)
- [River extraction and `river_percentile`](#river-extraction-and-river_percentile)
- [Lakes and lake basins](#lakes-and-lake-basins)
- [The lake overflow history](#the-lake-overflow-history)
- [Watersheds and endorheic basins](#watersheds-and-endorheic-basins)
- [The hydrologic water budget history record](#the-hydrologic-water-budget-history-record)
- [River network evolution](#river-network-evolution)
- [River channel morphology](#river-channel-morphology)
- [River hydraulics](#river-hydraulics)
- [Wetlands](#wetlands)
- [Navigability diagnostics](#navigability-diagnostics)
- [Deltas](#deltas)
- [Complete world-key and cell-field table](#complete-world-key-and-cell-field-table)
- [Configuration](#configuration)
- [Validation and closure checks](#validation-and-closure-checks)
- [Worked examples](#worked-examples)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

---

## Where hydrology runs in the pipeline

Every hydrology solve in the native engine happens inside `stabilize_numeric_depressions` (`cpp/src/engine/hydrology.cpp:1122`). That function is the *only* caller of `compute_hydrologic_water_budget` and `compute_flow_and_rivers`; nothing else in the tree invokes them. It is called from exactly three sites:

| Call site | File:line | `stage` string | `erosion_iteration` |
|---|---|---|---|
| Initial climate/hydrology solve, after crust and topography | `cpp/src/engine/pipeline.cpp:107` | `"initial_climate_hydrology"` | `-1` |
| Once per maturation iteration, after tectonics/hillslope/fluvial commit | `cpp/src/engine/earth_system.cpp:1122` | `"erosion_iteration"` | `iter + 1` |
| After glacial sediment transport, before the terminal cryosphere solve | `cpp/src/engine/pipeline.cpp:157` | `"cryosphere_coupling"` | `-1` |

Inside one call, each pass of the bounded loop executes this fixed order (`hydrology.cpp:1137`-`1155`):

```
apply_sea_level            -> volume-constrained sea-level datum solve
label_marine_water_bodies  -> ocean / continental_shelf / inland_sea labels
compute_climate            -> temperature, precipitation, winds
compute_hydrologic_water_budget -> PET, loss partition, runoff  (pushes one history stage)
compute_flow_and_rivers    -> priority flood, depressions, flow graph, rivers, basins
```

The loop then looks for depression units whose policy is `corrected_numeric`; if there are none it returns, otherwise it applies one correction pass and repeats. The bound is `NUMERIC_DEPRESSION_CORRECTION_MAX_PASSES = 16` (`cpp/src/engine/constants.hpp:55`); exceeding it throws `numeric depression correction did not converge within the bounded pass count` (`hydrology.cpp:1178`).

Lake basins and watersheds are *not* built inside the loop. They are derived once, terminally, after the maturation loop and the cryosphere coupling have finished:

```
natural.lake_basins = generate_lake_basins(params, earth.cells);   // pipeline.cpp:190
natural.watersheds  = generate_watersheds(params, earth.cells);    // pipeline.cpp:191
```

The Python enrichers then run in `src/magic_geo/api.py`, in this order:

| # | Enricher | `generate_world` line | `generate_geo_world` line |
|---|---|---|---|
| 1 | `enrich_world_with_lake_overflow_history` | `api.py:213` | `api.py:329` |
| 2 | `enrich_world_with_watershed_diagnostics` | `api.py:214` | `api.py:330` |
| 3 | `enrich_world_with_hydrology_realism` | `api.py:216` | `api.py:331` |
| 4 | `enrich_world_with_river_network_evolution` | `api.py:217` | `api.py:333` |
| 5 | `enrich_world_with_hydrology_budget` | `api.py:230` | `api.py:350` |
| 6 | `enrich_world_with_wetland_diagnostics` | `api.py:231` | `api.py:351` |
| 7 | `enrich_world_with_river_channel_morphology` | `api.py:233` | `api.py:353` |
| 8 | `enrich_world_with_river_hydraulics` | `api.py:234` | `api.py:354` |
| 9 | `enrich_world_with_navigability_diagnostics` | `api.py:241` | **not called** |

Note the ordering delta: in the geo-only path `hydrology_realism` runs *before* `sediment_routing_history`, and `navigability_diagnostics` is omitted entirely (it depends on `settlement_score`, `settlements` and `routes`, which geo-only strips).

---

## The water budget on the sphere

`compute_hydrologic_water_budget` (`cpp/src/engine/hydrology.cpp:18`-`207`) evaluates one deterministic annual loss partition per cell and returns a fully cell-indexed `HydrologicWaterBudgetStage` record. Its declared model type is `causal_land_climate_loss_partition_v1` (`cpp/src/engine/process_serialization.cpp:473`), domain `non_marine_cells`, execution order `climate_then_pet_then_loss_partition_then_runoff_then_flow_routing`.

### Constants

| Constant | Value | Declared at | Serialized as |
|---|---|---|---|
| `HYDROLOGIC_PET_TEMPERATURE_OFFSET_C` | `8.0` | `constants.hpp:48` | `pet_temperature_offset_c` |
| `HYDROLOGIC_PET_SCALE_MM_Y_PER_C` | `31.0` | `constants.hpp:49` | `pet_scale_mm_y_per_c` |
| `HYDROLOGIC_CLIMATE_LOSS_FRACTION` | `0.68` | `constants.hpp:50` | `climate_loss_fraction` |
| `HYDROLOGIC_INFILTRATION_BASE_SHARE` | `0.10` | `constants.hpp:51` | `infiltration_base_share` |
| `HYDROLOGIC_INFILTRATION_CAPACITY_SHARE` | `0.50` | `constants.hpp:52` | `infiltration_capacity_share` |
| `HYDROLOGIC_MIN_INFILTRATION_CAPACITY` | `0.02` | `constants.hpp:53` | `minimum_infiltration_capacity_index` |
| `HYDROLOGIC_MAX_INFILTRATION_CAPACITY` | `0.90` | `constants.hpp:54` | `maximum_infiltration_capacity_index` |
| `HYDROLOGIC_FLAT_GRADIENT_STEP_M` | `0.001` | `constants.hpp:47` | `summary.hydrologic_flat_gradient_step_m` |

### Lithology permeability

`hydrologic_lithology_permeability(int lithology)` (`hydrology.cpp:5`-`16`) is a pure switch, serialized under `hydrologic_water_budget_model.lithology_permeability` keyed by `LITHOLOGY_NAMES` (`cpp/src/engine/schema_names.hpp:11`):

| Lithology index | Name | Permeability |
|---|---|---|
| 0 | `basalt` | 0.46 |
| 1 | `granite` | 0.31 |
| 2 | `limestone` | 0.82 |
| 3 | `sandstone` | 0.76 |
| 4 | `shale` | 0.18 |
| 5 | `volcanic` | 0.48 |
| 6 | `metamorphic` | 0.30 |
| any other | (default branch) | 0.34 |

The default branch is unreachable for well-formed worlds because the lithology enum has exactly seven members; the CLI validator mirror `HYDROLOGIC_LITHOLOGY_PERMEABILITY` (`src/magic_geo/cli/_constants.py:113`) carries only the seven named entries.

### The partition, term by term (land cells only)

For a non-marine cell, with `P = max(0, precipitation_mm_y)`, `T = temperature_c`, `relief = local_relief(cells, i)` (`cpp/src/engine/climate.cpp:15`, mean-neighbour relief clamped at zero):

| Term | Formula | Source line |
|---|---|---|
| `potential_evapotranspiration_mm_y` | `max(0, T + 8.0) * 31.0` | `hydrology.cpp:73` |
| `terrain_retention` | `1 - clamp(relief / 2500, 0, 1)` | `hydrology.cpp:80` |
| `sediment_index` | `clamp(sediment_thickness_m / 3, 0, 1)` | `hydrology.cpp:85` |
| `frozen_index` | `clamp((-T - 2) / 18, 0, 1)` | `hydrology.cpp:90` |
| `infiltration_capacity_index` | `clamp(0.62*perm + 0.16*sediment_index + 0.12*terrain_retention - 0.10*frozen_index, 0.02, 0.90)` | `hydrology.cpp:95` |
| `climate_loss_mm_y` | `min(P, 0.68 * PET)` | `hydrology.cpp:103` |
| `infiltration_share` | `clamp(0.10 + 0.50*capacity, 0.10, 0.10 + 0.50*0.90)` → `[0.10, 0.55]` | `hydrology.cpp:108` |
| `infiltration_mm_y` | `climate_loss_mm_y * infiltration_share` | `hydrology.cpp:117` |
| `actual_evapotranspiration_mm_y` | `climate_loss_mm_y - infiltration_mm_y` | `hydrology.cpp:118` |
| `hydrologic_water_balance_mm_y` | `P - climate_loss_mm_y` | `hydrology.cpp:123` |
| `water_budget_runoff_mm_y` / `runoff_mm_y` | `max(0, water_balance)` | `hydrology.cpp:125`, `140`-`141` |
| `runoff_budget_residual_mm_y` | `P - AET - infiltration - runoff` | `hydrology.cpp:126` |
| `runoff_budget_consistency_index` | `clamp(1 - abs(residual) / max(1, P), 0, 1)` | `hydrology.cpp:143` |
| `hydrologic_deficit_mm_y` | `max(0, PET - AET)` | `hydrology.cpp:149` |
| `runoff_generation_fraction` | `clamp(runoff / max(1, P), 0, 1)` | `hydrology.cpp:154` |

For marine cells (`cell.is_water`) every one of those terms is left at `0.0` — the `if (!is_marine)` guard at `hydrology.cpp:72` skips the whole block. The serialized model records this as `marine_cell_treatment = "excluded_from_land_budget_with_zero_partition_terms"` (`process_serialization.cpp:507`).

### The closure requirement

The partition is constructed so that, analytically,

```
precipitation = actual_evapotranspiration + infiltration + runoff
```

holds exactly whenever `water_balance >= 0`. Because `runoff = max(0, P - climate_loss)` and `AET + infiltration = climate_loss`, and `climate_loss = min(P, 0.68·PET) <= P`, the `max` never clips: `water_balance` is nonnegative by construction, so `residual == 0.0` for every land cell up to floating-point rounding. `residual_mm_y` is nevertheless computed and stored per cell, aggregated to `mass_balance_residual_km3_y`, and tracked as `max_abs_cell_residual_mm_y` — it is a *measured* residual, not an assumed zero.

Area weighting to volumes uses `mm/y × km² × 1.0e-6 = km³/y` (`hydrology.cpp:190`-`199`), which is dimensionally exact (1 mm = 1e-6 km).

Two independent gates enforce closure, and one enricher re-reports it:

- `geo_validation.hydrology.land_water_budget_closure` requires `max |P - (AET + infiltration + runoff)| <= 2.0e-3 mm/y` over land cells, **zero** marine cells with any nonzero partition term, and **zero** negative terms (`src/magic_geo/geo_validation.py:1526`).
- The CLI replay validator `_validate_hydrologic_water_budget` recomputes every term of every cell of every history stage from the stage's own operand arrays and compares against the recorded arrays with `close(actual, expected, 1.0e-6)` (`src/magic_geo/cli/validators/hydrology.py:37`-`420`).
- The Python enricher `enrich_world_with_hydrology_budget` re-aggregates the residual into `summary.total_hydrologic_water_budget_residual_km3_y` and `summary.mean_abs_runoff_budget_residual_mm_y` (`src/magic_geo/hydrology_budget.py:216`-`224`). This is a *report*, not a gate — it asserts nothing and cannot fail a run.

### Budget classification and regions

`enrich_world_with_hydrology_budget` (`src/magic_geo/hydrology_budget.py:138`) is purely diagnostic — it writes no new physical quantity, only a class label and a region id. The classifier `_budget_class` (`hydrology_budget.py:29`) is a first-match ladder:

| Order | Condition | `hydrologic_budget_class` |
|---|---|---|
| 1 | `water_body_type ∈ {ocean, continental_shelf, inland_sea}` | `marine_budget` |
| 2 | `deficit >= 250.0` and `budget_runoff < 35.0` | `water_deficit` |
| 3 | `budget_runoff >= 250.0`, or (`>= 100.0` and `>= infiltration` and `>= 0.6·AET`) | `runoff_surplus` |
| 4 | `infiltration >= AET` and `infiltration >= 50.0` | `infiltration_dominated` |
| 5 | `AET >= 1.2·infiltration` and `AET >= budget_runoff` | `evapotranspiration_dominated` |
| 6 | otherwise | `balanced_budget` |

Contiguous same-class cells are flood-filled over the mesh neighbour graph into `hydrologic_budget_regions` records (`hydrology_budget.py:108`, `71`), each carrying `cell_ids`, `area_km2`, an area-weighted `centroid_lat_deg`/`centroid_lon_deg`, per-term means, `river_cell_count`, `lake_cell_count`, `closed_basin_cell_count` and `dominant_basin_id`.

---

## Priority-flood depression handling

`compute_priority_flood_spill` (`cpp/src/engine/hydrology.cpp:231`-`281`) is a standard priority-flood fill with a deterministic tie-break.

1. Every cell gets `filled_elevation_m = +inf`, `depression_depth_m = 0`, `spill_to = -1`, `is_closed_basin = false`.
2. Every water cell is seeded at `filled_elevation_m = 0.0` and pushed onto the min-heap.
3. **Land-only worlds**: if no water cell exists, the single globally lowest cell (lowest `elevation_m`, first index wins) is seeded at its own elevation (`hydrology.cpp:245`-`254`). This is the only fallback; there is no other special case.
4. Pop the lowest queued item; for each unvisited neighbour set `filled = max(neighbour.elevation_m, item.elevation)`, `depression_depth_m = max(0, filled - elevation_m)`, `spill_to = item.cell`, and push.
5. Any cell still at `+inf` afterwards (disconnected from every seed) falls back to `filled = elevation_m`, `depth = 0`, `spill_to = -1` (`hydrology.cpp:274`-`280`).

The heap comparator `FloodItemGreater` (`hydrology.cpp:222`) breaks equal elevations by *higher cell index first* under `std::priority_queue`'s "greater = lower priority" convention, so the lowest cell id is popped first. This is what makes the fill deterministic across runs and backends.

### Depression units

Priority flood alone does not tell you *which* depression a cell belongs to. `compute_flow_and_rivers` builds that separately, and the identity it uses is deliberately **the raw-downhill drainage terminal**, not the fill elevation:

- A raw steepest-descent receiver `raw_flow_to[i]` is computed on unfilled `elevation_m` with tie-break on lowest neighbour index (`hydrology.cpp:397`-`408`).
- Each cell is labelled by walking `raw_flow_to` to its terminal sink; water cells are labelled `-1` (`hydrology.cpp:446`-`486`). Non-termination throws `raw hydrology drainage labeling did not terminate`.
- A **depression unit** is the set of non-water cells sharing one raw sink and having `depression_depth_m > 1.0e-9` (`hydrology.cpp:488`-`495`). The in-source comment states the intent explicitly: *"A terminal with Priority-Flood depth is one model depression unit, even when it shares a final fill elevation with neighboring sinks."*

Units are iterated in ascending sink-cell-id order (`std::map`), and each gets a sequential `depression_component_id` (`hydrology.cpp:497`-`657`). The serialized `summary.depression_routing_model` is `raw_downhill_sink_units_with_priority_flood_spill_corridors_v1` (`cpp/src/engine/summary.cpp:1324`).

### Per-unit aggregates

For each unit (`hydrology.cpp:503`-`532`):

| Aggregate | Definition |
|---|---|
| `area_km2` | sum of member `area_km2` |
| `mean_runoff_mm_y` | area-weighted mean of `runoff_mm_y` |
| `mean_precipitation_mm_y` | area-weighted mean of `precipitation_mm_y` |
| `mean_pet_mm_y` | area-weighted mean of `hydrologic_potential_evapotranspiration_mm_y` |
| `aridity` | `mean_precipitation / max(1, mean_pet)` |
| `max_depression_depth_m` | max member `depression_depth_m` |
| `fill_fraction` | `clamp((mean_runoff / 220) · clamp(aridity, 0.08, 2.5) / (1 + max_depth / 120), 0, 1.5)` |

`fill_fraction` is written to every member cell as `lake_fill_fraction` and can legitimately exceed 1.0 (up to 1.5) — the subsystem validator explicitly bounds it to `[0, 1.5]` rather than `[0, 1]` (`src/magic_geo/geo_validation_subsystems.py:1355`).

### The spill corridor

From the sink, follow `spill_to` while staying inside the same raw-sink label; stop and record `spill_destination` when the next cell is water or belongs to a different raw sink (`hydrology.cpp:534`-`553`). A unit with no such exit has `spill_destination = -1`.

---

## The `preserve_geologic_depressions` policy, both branches

The policy gate is one line (`hydrology.cpp:555`-`556`):

```cpp
const bool geologic_depression =
    params.preserve_geologic_depressions && is_geologic_depression(sink_cell);
```

`is_geologic_depression` (`hydrology.cpp:213`-`215`) is evaluated **on the sink cell only**:

```cpp
return cell.crust_type == 6 || cell.crust_type == 7
    || cell.boundary_divergent > 0.28 || cell.boundary_convergent > 0.42;
```

Crust index 6 is `rift_basin` and 7 is `sedimentary_basin` (`cpp/src/engine/schema_names.hpp:7`). The serialized `summary.depression_geology_model` is `raw_sink_cell_crust_or_active_boundary_v1` (`summary.cpp:1326`).

### Branch A — `preserve_geologic_depressions: true` (the default)

A depression whose sink satisfies `is_geologic_depression` is never a fill candidate. Its policy is one of three, selected by wetness and spill availability:

| Condition | `depression_policy` | Enum name |
|---|---|---|
| `wet_geologic` (mean runoff > 25 mm/y) **and** `spill_destination >= 0` **and** `fill_fraction >= 1.0` | `3` | `overflow_spill` |
| `wet_geologic` but not overflowing | `2` | `preserved_geologic` |
| geologic but `mean_runoff <= 25.0` | `4` | `dry_closed` |

Non-geologic depressions in this branch still follow the numeric path (policy `1` or `5`). The ladder at `hydrology.cpp:577`-`590` is strictly first-match — `geologic_overflows → 3`, `wet_geologic → 2`, `geologic → 4`, `temporary → 5`, `spill_destination >= 0 → 1`, `else → 4` — so `spill_destination < 0` only forces `4` for a depression that is *neither* geologic *nor* carrying a deferred temporary-lake flag. A wet geologic basin with no spill exit stays at policy `2`, and a deferred unit with no spill exit stays at policy `5`.

### Branch B — `preserve_geologic_depressions: false`

`geologic_depression` is forced false for *every* unit, so no depression can ever reach policy 2, 3 or the geologic-4 case. Every depression is instead classified as:

| Condition | `depression_policy` | Enum name |
|---|---|---|
| any member carries a deferred temporary-lake flag from a previous pass | `5` | `temporary_numeric_lake` |
| otherwise, `spill_destination >= 0` | `1` | `corrected_numeric` |
| otherwise (no spill exit at all) | `4` | `dry_closed` |

Policy `1` is exactly the correction-candidate class, so turning the flag off routes rift basins, sedimentary basins and active-boundary sinks into the breach/temporary-lake machinery described below. The practical consequence: with the flag off you get more open drainage and more numeric correction events; with it on the model's own four-clause geology heuristic keeps those sinks as closed basins. Neither branch fills a depression by adding unsourced material — see the next section.

### Policy → routing and water body

| Policy | Enum | `flow_to` rewiring | Sink `flow_to` | Lake? |
|---|---|---|---|---|
| `1` `corrected_numeric` | numeric fill candidate | spill corridor cells rerouted to their `spill_to` | keeps corridor link | no |
| `2` `preserved_geologic` | wet, non-overflowing geologic basin | members reset to raw receivers | `-1`, `is_closed_basin = true` | yes |
| `3` `overflow_spill` | wet geologic basin at capacity | spill corridor cells rerouted to `spill_to` | keeps corridor link | yes, `lake_overflows = true` |
| `4` `dry_closed` | dry geologic or spill-less | members reset to raw receivers | `-1`, `is_closed_basin = true` | no |
| `5` `temporary_numeric_lake` | deferred numeric depression | corridor if it overflows, else raw receivers | `-1` if closed | yes if wet |

Source: `hydrology.cpp:603`-`630`. Policy names come from `DEPRESSION_POLICY_NAMES` (`cpp/src/engine/schema_names.hpp:53`): `{none, corrected_numeric, preserved_geologic, overflow_spill, dry_closed, temporary_numeric_lake}`.

Closed-branch routing is defensive: if a non-sink member's raw receiver leaves the unit footprint or has no depression depth, the engine throws `closed depression raw routing leaves its footprint` (`hydrology.cpp:623`).

### Lake water surface for wet units

For `wet_geologic_depression || wet_temporary_numeric_depression` (`hydrology.cpp:632`-`653`):

```
water_surface_m = sink.elevation_m
                + min(1, fill_fraction) * max(0, sink.spill_elevation_m - sink.elevation_m)
depth_m         = max(0, water_surface_m - cell.elevation_m)     // per member
cell.water_depth_m = clamp(depth_m, 0.2, 240.0)                  // if depth_m > 1e-9
```

Water-body assignment: `water_body = (aridity < 0.5) ? 5 : 4`, overridden to `4` when the basin overflows. Index 4 is `fresh_lake`, 5 is `saline_basin` (`WATER_BODY_NAMES`, `schema_names.hpp:34`). A *dry* geologic depression with `aridity < 0.55` still gets `water_body = 5` on the sink cell without becoming a lake (`hydrology.cpp:654`-`656`) — that is the salt-flat signature `derive_landforms` later picks up.

---

## Numeric depression correction: breach or temporary lake

When a pass finds cells with `depression_policy == 1`, the loop groups them by `depression_component_id` and builds one `NumericDepressionCorrectionEvent` per component (`hydrology.cpp:1157`-`1301`). Two mutually exclusive outcomes are possible, and *neither one fills the depression with unsourced rock*.

### Step 1 — the fill candidate

The event first records the counterfactual full fill: per-cell `elevation_before_fill_m`, `fill_depth_m` (`= filled_elevation_m - elevation_m`, cross-checked against `depression_depth_m` to 1e-7), `elevation_after_fill_m`, plus `area_km2`, `fill_volume_km3` and `max_fill_depth_m` (`hydrology.cpp:1220`-`1246`). The serialized event marks `fill_candidate_applied = false` unconditionally (`process_serialization.cpp:709`) — the fill is *never* applied; it exists only as the volume yardstick.

### Step 2 — the breach diagnostic

`derive_numeric_depression_breach_alternative` (`hydrology.cpp:725`-`894`) runs a Dijkstra search from the sink over the pre-correction elevation field. Cost is excavation volume in km³: `excavation_depth_m · area_km2 / 1000`. A monotone descending corridor is required — at hop count `k` the target elevation is `sink_elevation - 0.001·k`, using `NUMERIC_DEPRESSION_BREACH_GRADIENT_STEP_M = 0.001 m` (`constants.hpp:57`).

| Rule | Line |
|---|---|
| Search terminates at the first non-source cell already at or below the required elevation for its hop count | `hydrology.cpp:770`-`776` |
| A neighbour that is water, or that belongs to a *different* depression component, is skipped unless it is itself a naturally-lower outlet | `hydrology.cpp:790`-`799` |
| Ties in cost break on lowest parent cell id | `hydrology.cpp:809`-`811` |
| `breach_to_fill_volume_ratio` = excavation / fill volume (`+inf` when fill volume is zero) | `hydrology.cpp:888` |
| `breach_has_lower_adjustment_volume` = feasible **and** excavation volume + 1e-9 < fill volume | `hydrology.cpp:891` |

The declared model string is `weighted_graph_excavation_proxy_monotone_lower_outlet_v1` (`summary.cpp:1332`).

### Step 3 — selection

`apply_numeric_depression_correction` (`hydrology.cpp:896`-`1120`) evaluates four gates:

| Gate | Field | Rule | Line |
|---|---|---|---|
| Cheaper than filling | `breach_has_lower_adjustment_volume` | excavation volume strictly below fill volume | `hydrology.cpp:891` |
| Depth bounded | `breach_depth_bound_passed` | `max_breach_excavation_depth_m <= 50.0 + 1e-9` (`NUMERIC_DEPRESSION_SELECTED_BREACH_MAX_DEPTH_M`, `constants.hpp:58`) | `hydrology.cpp:936` |
| Local sink for the spoil | `breach_deposition_capacity_sufficient` | in-depression deposition capacity (bounded by a 5000 m sediment-thickness ceiling per cell) at least equals excavation volume | `hydrology.cpp:941` |
| No same-pass conflict | `breach_same_pass_conflict_free` | no excavation or deposition cell was already mutated this pass | `hydrology.cpp:945`-`959` |

`breach_selected = all four`. Otherwise `temporary_numeric_lake_selected = true`.

### Step 4a — breach applied

Excavation splits **alluvium first, bedrock second** (`hydrology.cpp:1002`-`1013`) and is committed through the shared checked primitive `apply_sediment_interface_material_change(cell, 0.0, bedrock_erosion, alluvium_entrainment, 0.0, "numeric depression breach excavation")`. The resulting elevation is re-verified against the planned target to 1e-7 or the engine throws `numeric depression breach sediment-interface target mismatch`.

The excavated volume is then deposited back inside the depression, proportional to each candidate's capacity, with the last candidate absorbing the remainder so nothing is lost to rounding (`hydrology.cpp:1050`-`1106`). Failure to place it all throws `numeric depression breach deposition capacity was not realized`. Finally `maximum_sediment_interface_closure_residual_m(cells, "post numeric depression breach correction")` re-audits the bedrock/mobile interface, and `correction_mass_balance_residual_km3 = |applied excavation − applied deposition|` is recorded.

### Step 4b — temporary numeric lake

If any gate fails, **no material moves at all**. Every member cell gets `numeric_depression_temporary_lake_deferred = true` and `numeric_depression_temporary_lake_event_count++`, and `correction_mass_balance_residual_km3` is set to `0.0` (`hydrology.cpp:968`-`983`). On the next pass that deferred flag promotes the unit to policy `5` (`temporary_numeric_lake`), where it may become a real lake if wet. Any elevation drift detected at deferral time throws `numeric depression deferral conflicts with an earlier correction`.

This is the mechanism behind the serialized selection reason (`summary.cpp:1340`):

> `apply_only_lower_volume_depth_bounded_capacity_sufficient_conflict_free_breaches_else_defer_without_material`

and the correction model string `bounded_mass_conserving_breach_or_zero_material_temporary_lake_with_coupled_recomputation_v3` (`summary.cpp:1328`).

### Event record fields

`numeric_depression_correction_history[]` entries (`cpp/src/engine/process_serialization.cpp:650`-`797`) carry, in serialized order: `id`, `feedback_stage_id`, `stage`, `erosion_iteration`, `stabilization_pass`, the twelve nominal-time fields emitted by `add_nominal_time_fields` (`process_serialization.cpp:135`-`160`, here with `nominal_time_role = "stage_end_stabilization_event"`), `correction_method`, `fill_candidate_model`, `source_depression_policy`, `source_depression_component_id`, `sink_cell_id`, `sink_crust_type`, `sink_is_geologic`, `sink_boundary_divergent`, `sink_boundary_convergent`, `cell_count`, `cell_ids`, `elevation_before_fill_m_by_cell`, `sediment_thickness_before_correction_m_by_cell`, `fill_depth_m_by_cell`, `elevation_after_fill_m_by_cell`, `area_km2`, `fill_volume_km3`, `max_fill_depth_m`, `fill_candidate_applied` (always `false`), `temporary_numeric_lake_selected`, `breach_diagnostic_model`, `breach_gradient_step_m`, `breach_feasible`, `breach_outlet_cell_id`, `breach_path_cell_ids`, the six `breach_*_by_cell` arrays, `breach_path_length_km`, `breach_excavation_area_km2`, `breach_excavation_volume_km3`, `max_breach_excavation_depth_m`, `breach_to_fill_volume_ratio`, the four gate booleans, `breach_deposition_capacity_km3`, `breach_deposition_cell_count`, `breach_deposition_cell_ids`, `breach_deposition_depth_m_by_cell`, the four `applied_*_volume_km3` totals, `correction_mass_balance_residual_km3`, `lower_adjustment_volume_method` (`"breach"` or `"fill"`), and finally `selected_correction_method` (`"mass_conserving_breach"` or `"temporary_numeric_lake"`).

The provenance registry classifies this family as `native_mixed_mutation_and_counterfactual_event_ledger` with `state_mutation_evidence = "mixed"` — the only family so marked — precisely because deferral events record a counterfactual that was *not* applied (`src/magic_geo/geo_evolution_provenance.py:36`-`42`, `74`-`80`).

---

## Drainage directions, accumulation and the conditioned surface

### Receiver selection

`compute_flow_and_rivers` (`hydrology.cpp:369`) selects each land cell's receiver in two stages:

1. **Raw receiver** — steepest descent on unfilled `elevation_m`, requiring `raw_drop > 1e-9`, ties broken by lowest neighbour index (`hydrology.cpp:397`-`408`). Stored only in a local vector; used for depression-unit labelling and closed-basin routing.
2. **Filled receiver** — steepest descent on `filled_elevation_m`, requiring `drop > 1e-9`; ties broken first by larger *raw* drop and then by lowest neighbour index (`hydrology.cpp:415`-`431`).
3. **Spill fallback** — if no filled-surface descent exists, use `spill_to`. When the fallback is taken and the filled elevations are equal within 1e-9 while the raw drop exceeds 1e-9, the cell is flagged `equal_filled_raw_downhill_rerouted = true` (`hydrology.cpp:432`-`438`). This flag exists purely so the flat-surface reroute is auditable.

Water cells always keep `flow_to = -1` and `flow_accumulation = 0.0`.

### Flow accumulation

Land cells are seeded with `flow_accumulation = runoff_mm_y * area_km2` (`hydrology.cpp:394`) — units are mm·km²/y, deliberately *not* converted to a volume. Accumulation is then propagated by Kahn topological order over `flow_to`, using a min-heap on cell id so the traversal is deterministic (`hydrology.cpp:660`-`700`). Water cells do not contribute their own accumulation downstream (`hydrology.cpp:688`). If fewer than `n` cells are processed the engine throws `hydrology flow graph contains a cycle`.

### Surface conditioning

`condition_hydrologic_surface` (`hydrology.cpp:325`-`367`) exists because the priority-flood surface is flat inside filled areas, which makes slope-driven downstream physics undefined. Walking the topological order in reverse (downstream first):

```
hydrologic_surface_elevation_m = max(filled_elevation_m,
                                     receiver.hydrologic_surface_elevation_m + 0.001)
```

with `HYDROLOGIC_FLAT_GRADIENT_STEP_M = 0.001 m`. Then per cell:

| Field | Definition |
|---|---|
| `hydrologic_surface_conditioned` | `hydrologic_surface_elevation_m > filled_elevation_m + 1e-12` |
| `hydrologic_flow_drop_m` | `self.hydrologic_surface_elevation_m − receiver.hydrologic_surface_elevation_m` |
| `hydrologic_flow_slope` | `hydrologic_flow_drop_m / neighbor_distance_m(params, self, receiver)` |

`neighbor_distance_m` is `max(1.0, angular_distance(a,b) · radius_km · 1000)` metres (`hydrology.cpp:209`). Two hard invariants throw on violation: `Priority-Flood routing surface rises downstream` and `conditioned hydrologic surface is not downhill`. The serialized model name is `priority_flood_fill_with_deterministic_flat_gradient_v1` (`summary.cpp:1346`).

Every downstream consumer that needs an elevation for a flow link reads `hydrologic_surface_elevation_m` first, falling back to `filled_elevation_m` then `elevation_m` — see `src/magic_geo/river_channel_morphology.py:58`, `src/magic_geo/watershed_diagnostics.py:64`, `src/magic_geo/river_network_evolution.py:19`, `src/magic_geo/hydrology_realism.py:42`.

### Basin ids

`assign_basin_ids` (`hydrology.cpp:283`-`323`) labels every water cell with its own index as basin id, then walks each land cell downstream until it hits a labelled cell, a revisit, a water cell, a closed/flow-less lake cell, or `flow_to < 0`. The terminal is the basin id for the entire traced path. So **`basin_id` is the id of the terminal cell**, which is why `watershed.outlet_cell_id == watershed.basin_id` in the native watershed record (`cpp/src/engine/water_features.cpp:280`).

---

## River extraction and `river_percentile`

River classification is the last step of `compute_flow_and_rivers` (`hydrology.cpp:702`-`721`):

```cpp
// collect strictly positive land accumulations
std::sort(accum.begin(), accum.end());
const auto idx = static_cast<std::size_t>(
    clamp(params.river_percentile, 0.5, 0.999) * static_cast<double>(accum.size() - 1));
const double threshold = std::max(1.0, accum[idx]);
...
cells[i].is_river = cells[i].flow_accumulation >= threshold
    && cells[i].hydrologic_flow_slope > 0.0
    && cells[i].runoff_mm_y > 10.0;
```

Points worth stating precisely:

| Property | Behaviour |
|---|---|
| Sample population | only non-water cells with `flow_accumulation > 0.0` |
| Percentile clamp | the engine clamps to `[0.5, 0.999]` before indexing. Because the config schema already bounds `river_percentile` to `[0.50, 0.995]`, this clamp is a **no-op for any schema-valid config**; it only binds if the native ABI is driven directly with an out-of-range value |
| Index | truncating cast of `p·(N−1)`, i.e. a nearest-lower order statistic with no interpolation |
| Floor | threshold is at least `1.0` |
| Exclusions | `is_water` cells and cells with `flow_to < 0` are skipped entirely, so a terminal sink is never a river |
| Extra gates | a strictly positive conditioned slope **and** `runoff_mm_y > 10.0` |
| Empty case | if no land cell has positive accumulation, the function returns before river labelling and before `assign_basin_ids` (`hydrology.cpp:708`-`710`) |

`summary.river_extraction_model = "flow_accumulation_percentile_on_conditioned_hydrologic_surface_v1"`, and `summary.river_extraction_percentile` plus `summary.river_flow_accumulation_threshold` are emitted at `summary.cpp:1354`-`1359`. The summary threshold is recomputed independently over the final field (`summary.cpp:1300`), so a mismatch between it and the routing-time threshold is observable.

Because the threshold is a percentile of the *surviving* land accumulation distribution, raising `river_percentile` weakly raises the threshold and so weakly shrinks the candidate set. The candidate set is roughly `(1 − river_percentile)` of the positive-accumulation land cells — it can exceed that when many cells tie at exactly the threshold value — and the `runoff > 10 mm/y` and `slope > 0` gates then remove a further subset. The realised river-cell fraction is therefore an emergent number, not a configured one; read it from `summary.river_count` rather than deriving it from the percentile.

---

## Lakes and lake basins

Lake *cells* are produced inside `compute_flow_and_rivers` (see the policy table above). Lake *basins* are produced terminally by `generate_lake_basins` (`cpp/src/engine/water_features.cpp:53`-`162`).

### Construction

1. Reset `lake_basin_id = -1` on every cell.
2. Group non-water cells by `depression_component_id >= 0` (so **every** depression component becomes a basin record, including dry closed ones — not just lakes).
3. Copy the sink cell's `spill_to`, `depression_policy`, `water_body`, `is_geologic`, `lake_overflows`, `elevation_m`, `spill_elevation_m` and `lake_fill_fraction` onto the basin. Metadata inconsistency inside the component throws `depression component metadata is inconsistent`.
4. Accumulate `depression_cell_count`, `depression_area_km2`, `max_depression_depth_m`, `storage_capacity_km3 = Σ depression_depth_m · area_km2 / 1000`, and `geologic_area_fraction`.
5. **Catchment attribution**: every non-water cell is walked downstream along `flow_to` until it reaches a cell whose `depression_component_id` maps to a basin. That cell joins the basin's `cell_count`, `area_km2`, `annual_runoff_km3 = Σ runoff_mm_y · area_km2 · 1e-6`, and — if it is a lake cell — `lake_cell_count`, `lake_area_km2` and the area-weighted `mean_water_depth_m` (`water_features.cpp:114`-`147`).
6. `overflow_index = clamp(annual_runoff_km3 / max(0.001, storage_capacity_km3), 0, 50)`, computed **only when `overflows` is true**, otherwise left at zero (`water_features.cpp:156`-`158`).

### Overflow staging

`derive_lake_overflow_stages` (`water_features.cpp:5`-`51`) walks the outlet's spill/flow path for at most 16 steps, stopping at water, at a different depression component, or at a foreign lake:

| Field | Definition |
|---|---|
| `overflow_path_cell_ids` | outlet, then each successive `spill_to`/`flow_to` hop |
| `overflow_path_length_km` | sum of `neighbor_distance_m / 1000` along the path |
| `overflow_stage_count` | `max(0, len(path) − 1)` |
| `avulsion_risk` | `clamp(0.42·pressure + 0.24·short_path + 0.20·incision + 0.14·relief_factor, 0, 1)` |

with `pressure = clamp(overflow_index/4, 0, 1)`, `short_path = 1/(1 + length_km/180)`, `incision = clamp(max_depression_depth_m/180, 0, 1)`, `relief_factor = clamp(local_relief(outlet)/1400, 0, 1)`.

### Serialized `lake_basins[]` fields

Emitted by `lake_basins_json` (`cpp/src/engine/entity_serialization.cpp:467`-`506`) in this order: `id`, `depression_component_id`, `outlet_cell_id`, `spill_to_cell_id`, `depression_policy`, `water_body_type`, `is_geologic`, `overflows`, `depression_cell_count`, `cell_count`, `lake_cell_count`, `depression_area_km2`, `geologic_area_fraction`, `area_km2`, `lake_area_km2`, `mean_runoff_mm_y`, `outlet_elevation_m`, `spill_elevation_m`, `max_depression_depth_m`, `mean_water_depth_m`, `fill_fraction`, `storage_capacity_km3`, `annual_runoff_km3`, `overflow_index`, `overflow_stage_count`, `overflow_path_length_km`, `avulsion_risk`, `overflow_path_cell_ids`.

---

## The lake overflow history

`enrich_world_with_lake_overflow_history(world, simulation_years=12)` (`src/magic_geo/hydrology_dynamics.py:292`) is a **post-hoc diagnostic trajectory**, classified as such in the provenance registry (`geo_evolution_provenance.py:48`). It does not mutate any native field and it is not physically timed — the "years" are a bookkeeping index.

Only basins with `lake_cell_count > 0` are simulated (`hydrology_dynamics.py:296`-`298`).

### Per-basin storage loop

Initial volume is `min(capacity, capacity · min(fill_fraction, 1))`. Each of the 12 steps:

```
available = start_volume + annual_runoff_km3
evaporation = min(evaporation_loss_km3, available);  available -= evaporation
if capacity > 0 and available > capacity:
    excess = available - capacity
    if overflows: spill_volume = excess          else: sink_loss = excess
    available = capacity
elif capacity <= 0 and available > 0:
    sink_loss = available;  available = 0
end_volume = max(0, available)
```

The evaporation depth is `clamp(0.35 + mean_water_depth_m/2500, 0.35, 1.20)` metres, times `lake_area_km2`, divided by 1000 to give km³ (`hydrology_dynamics.py:19`-`25`).

Per-step fields: `year`, `start_volume_km3`, `inflow_km3`, `evaporation_loss_km3`, `spill_volume_km3`, `sink_loss_km3`, `end_volume_km3`, `fill_fraction`, `overflow_stage`, `avulsion_risk`, `avulsion_triggered`. `overflow_stage` is `min(stage_count, max(1, ceil(spill/max(1,runoff) · stage_count)))` (`hydrology_dynamics.py:28`). `avulsion_triggered` fires when `spill > 0` and step risk `>= 0.65`.

Per-history fields: `id`, `lake_basin_id`, `depression_policy`, `overflows`, `simulation_year_count`, `time_step_count`, `storage_capacity_km3`, `annual_runoff_km3`, `total_inflow_km3`, `total_spill_km3`, `total_sink_loss_km3`, `max_fill_fraction`, `first_overflow_year`, `avulsion_triggered`, `max_avulsion_risk`, `overflow_path_cell_ids`, `steps`.

### Overflow channel histories

`_enrich_world_with_overflow_channel_history` (`hydrology_dynamics.py:70`) rides the same step sequence to incise a channel along `overflow_path_cell_ids` (paths shorter than two cells are skipped). Key relations:

| Quantity | Formula | Line |
|---|---|---|
| `bed_slope` | `path_drop_m / max(1, channel_length_km·1000)` | `hydrology_dynamics.py:123` |
| `stream_power_index` | `clamp(0.18·min(1,spill_pressure) + 0.48·slope_factor + 0.22·stage_factor + 0.12·overflow_pressure, 0, 1)` (0 when no spill) | `hydrology_dynamics.py:149` |
| `incision_m` | `clamp(stream_power · (0.04 + min(1,spill_pressure)·0.24) · (1 + base_avulsion_risk·0.65), 0, 1.5)` | `hydrology_dynamics.py:167` |
| `bank_widening_m` | `incision_m · (1.4 + base_avulsion_risk·2.6 + stage_factor)` | `hydrology_dynamics.py:172` |
| `channel_width_m` | running `clamp(width + widening, 6, 260)`, seeded at `clamp(6 + sqrt(annual_runoff_km3)·0.18, 6, 180)` | `hydrology_dynamics.py:131`, `173` |
| `sediment_evacuated_km3` | `channel_length_km · channel_width_m · incision_m / 1e6` | `hydrology_dynamics.py:174` |
| `dominant_process` | `no_flow` \| `avulsion` \| `spillway_widening` \| `spillway_incision` | `hydrology_dynamics.py:190`-`197` |

Cell back-annotation writes `overflow_channel_active`, `overflow_channel_incision_m` (max), `overflow_channel_sediment_evacuated_km3` (accumulated, divided evenly across path cells) and `overflow_channel_avulsion_risk` (max) — `hydrology_dynamics.py:226`-`244`.

---

## Watersheds and endorheic basins

### Native construction

`generate_watersheds` (`cpp/src/engine/water_features.cpp:269`-`371`) aggregates non-water cells with a valid `basin_id`:

| Field | Definition |
|---|---|
| `basin_id`, `outlet_cell_id` | both equal the terminal cell id |
| `cell_count`, `area_km2` | membership counts and area sum |
| `mean_runoff_mm_y`, `mean_elevation_m` | **unweighted** per-cell means |
| `max_flow_accumulation` | max member accumulation |
| `river_cell_count` | members with `is_river` |
| `centroid_lat_deg` / `centroid_lon_deg` | normalized area-weighted 3-D centroid |
| `min_lat_deg` … `max_lon_deg`, `lon_span_deg`, `crosses_antimeridian` | longitude unwrapped about the centroid |
| `boundary_cell_ids` | members with at least one neighbour that is water or in another basin |
| `boundary_ring` | up to 64 boundary cells, angle-sorted in the tangent plane, closed | 
| `boundary_perimeter_km` | great-circle ring perimeter |
| `dissolved_polygon_area_km2` | orthographic shoelace area of the ring |
| `polygon_area_error_fraction` | `abs(polygon − true) / max(1, true)` |
| `compactness_index` | `clamp(4π·polygon_area / perimeter², 0, 1)` |
| `geometry_quality` | `clamp(0.62·area_quality + 0.38·ring_quality, 0, 1)` where `ring_quality = clamp(len(ring)/24, 0, 1)` |

Records are sorted by descending `area_km2` with `basin_id` as tie-break, then re-`id`ed sequentially (`water_features.cpp:361`-`369`).

### Outlet types and endorheism

`watershed_outlet_type` (`water_features.cpp:163`-`184`) inspects the outlet cell and returns an index into `WATERSHED_OUTLET_NAMES = {ocean, lake, saline_basin, inland_sea, closed_land}` (`schema_names.hpp:50`):

| Outlet cell state | `outlet_type` |
|---|---|
| `is_lake` and `water_body == 5` | `saline_basin` |
| `is_lake` otherwise | `lake` |
| `is_water` and `water_body == 3` | `inland_sea` |
| `is_water` otherwise | `ocean` |
| land, `water_body == 5` | `saline_basin` |
| land, `water_body == 4` | `lake` |
| anything else | `closed_land` |

`is_endorheic = (outlet_type != 0)`, i.e. **anything that does not terminate in the connected ocean/shelf counts as endorheic**, including inland seas and lakes. `summary.endorheic_watershed_count` and `summary.endorheic_basin_count` are both set from that same counter (`summary.cpp:1783`, `1785`).

### Python watershed diagnostics

`enrich_world_with_watershed_diagnostics` (`src/magic_geo/watershed_diagnostics.py:94`) annotates the existing `watersheds[]` records in place; it adds **no** new world key. For each watershed it traces the longest downstream path that stays inside the basin, from every non-water member (`watershed_diagnostics.py:120`-`131`), tie-breaking equal lengths on higher `flow_accumulation`.

| Added field | Definition | Line |
|---|---|---|
| `main_channel_cell_ids` | the winning downstream path | `watershed_diagnostics.py:164` |
| `main_channel_source_cell_id` / `main_channel_outlet_cell_id` | first / last path cell | `165`-`166` |
| `main_channel_length_km` | great-circle path length using `planet_radius_km(world)` | `167` |
| `main_channel_drop_m` | conditioned-surface drop from first to last | `168` |
| `main_channel_gradient` | `drop / max(1, length_km·1000)` | `169` |
| `main_channel_sinuosity_index` | `path_length / max(1, straight-line length)` | `170` |
| `total_river_length_km` | Σ great-circle edges between in-basin river cells and their receivers | `171` |
| `drainage_density_km_per_1000_km2` | `total_river_length / max(1, area_km2) · 1000` | `172` |
| `hack_exponent` | fixed `0.6` (`HACK_EXPONENT`) | `173` |
| `hack_coefficient` | `main_channel_length / area_km2^0.6` | `174` |
| `hack_expected_main_channel_length_km` | `fit_coefficient · area^0.6` | `202` |
| `hack_residual_fraction` | `abs(actual − expected) / max(1, expected)` | `203` |

A free log-log power-law fit is also run over basins at or above `HACK_FIT_MINIMUM_BASIN_AREA_KM2 = 1_000_000.0` (`src/magic_geo/scaling.py`), producing `summary.watershed_hack_fitted_exponent`, `..._coefficient`, `..._log_rmse` and `..._observation_count`. These are the world-side metrics the external HydroRIVERS calibration target compares against.

---

## The hydrologic water budget history record

`world["hydrologic_water_budget_history"]` is a native, replay-critical, cell-indexed ledger — one record per stabilization recomputation, appended in `stabilize_numeric_depressions` (`hydrology.cpp:1145`). It is classified `native_state_mutation_ledger` with `state_mutation_evidence = "yes"` (`geo_evolution_provenance.py:28`).

Emitted by `hydrologic_water_budget_history_json` (`cpp/src/engine/process_serialization.cpp:550`-`648`). Scalar fields use `max(10, float_precision)` decimals; volume fields use `max(12, float_precision)`.

### Field table

| Field | Type | Meaning |
|---|---|---|
| `id` | int | sequential index; must equal the array position |
| `feedback_stage_id` | int | id of the `earth_system_feedback_history` step this stage belongs to |
| `stage` | string | `initial_climate_hydrology` \| `erosion_iteration` \| `cryosphere_coupling` |
| `erosion_iteration` | int | `iter+1` inside the maturation loop, `-1` otherwise |
| `stabilization_recomputation_index` | int | 0-based pass counter within the stabilization call |
| `nominal_time_model` | string | `configured_maturation_timestep_nominal_elapsed_time_v1` |
| `nominal_time_unit` | string | `Ma` |
| `nominal_time_basis` | string | `configured_maturation_timestep_ma_per_erosion_transition_v1` |
| `nominal_time_source_parameter` | string | `erosion.maturation_timestep_ma` |
| `nominal_time_role` | string | `stage_end_stabilization_recomputation_snapshot` |
| `nominal_interval_start_ma` / `nominal_interval_end_ma` | double | both equal `min(feedback_stage_id, erosion_iterations)·timestep` — a zero-duration endpoint |
| `nominal_interval_duration_ma` | double | `0.0` |
| `nominal_elapsed_time_ma` | double | equals the interval end |
| `advances_nominal_time` | bool | `false` (zero duration) |
| `nominal_time_calibrated` | bool | **always `false`** |
| `physical_time_resolved` | bool | **always `false`** |
| `cell_count` | int | total cells |
| `land_cell_count` / `marine_cell_count` | int | partition of `cell_count` |
| `land_precipitation_volume_km3_y` | double | Σ over land of `P · area · 1e-6` |
| `actual_evapotranspiration_volume_km3_y` | double | Σ over land of `AET · area · 1e-6` |
| `infiltration_volume_km3_y` | double | Σ over land of `infiltration · area · 1e-6` |
| `runoff_volume_km3_y` | double | Σ over land of `runoff · area · 1e-6` |
| `mass_balance_residual_km3_y` | double | Σ over land of `residual · area · 1e-6` |
| `max_abs_cell_residual_mm_y` | double | max land `abs(residual)` |
| `cell_ids` | int[] | cell index order for every array below |
| `is_marine_by_cell` | int[] | 0/1 |
| `lithology_by_cell` | int[] | index into `LITHOLOGY_NAMES` |
| `cell_area_km2_by_cell` | double[] | operand |
| `elevation_m_by_cell` | double[] | operand (also used to replay `local_relief`) |
| `temperature_c_by_cell` | double[] | operand |
| `precipitation_mm_y_by_cell` | double[] | operand |
| `local_relief_m_by_cell` | double[] | operand, replayable from elevations + neighbours |
| `sediment_thickness_m_by_cell` | double[] | operand |
| `ice_thickness_m_by_cell` | double[] | recorded operand snapshot (not used by the budget formula) |
| `potential_evapotranspiration_mm_y_by_cell` | double[] | result |
| `infiltration_capacity_index_by_cell` | double[] | result |
| `actual_evapotranspiration_mm_y_by_cell` | double[] | result |
| `infiltration_mm_y_by_cell` | double[] | result |
| `water_balance_mm_y_by_cell` | double[] | result |
| `runoff_mm_y_by_cell` | double[] | result |
| `residual_mm_y_by_cell` | double[] | result |

### The paired model record

`world["hydrologic_water_budget_model"]` (`process_serialization.cpp:451`-`548`) publishes every constant, every sub-model string, `history_stage_count`, and a `final_*` mirror of the last stage: `final_history_stage_id`, `final_land_cell_count`, `final_marine_cell_count`, `final_land_precipitation_volume_km3_y`, `final_actual_evapotranspiration_volume_km3_y`, `final_infiltration_volume_km3_y`, `final_runoff_volume_km3_y`, `final_mass_balance_residual_km3_y`, `final_max_abs_cell_residual_mm_y`. It also declares `cell_mass_balance_closed: true`, `runoff_computed_before_flow_routing: true`, and `physical_time_resolved: false`.

### Feedback-history cross-links

Each `earth_system_feedback_history` step mirrors the *final* budget stage of its own stabilization call, and the CLI validator enforces the identity for six aggregates (`src/magic_geo/cli/validators/hydrology.py:342`-`358`):

| Feedback field | Budget-stage field |
|---|---|
| `hydrologic_land_precipitation_volume_km3_y` | `land_precipitation_volume_km3_y` |
| `hydrologic_actual_evapotranspiration_volume_km3_y` | `actual_evapotranspiration_volume_km3_y` |
| `hydrologic_infiltration_volume_km3_y` | `infiltration_volume_km3_y` |
| `hydrologic_runoff_volume_km3_y` | `runoff_volume_km3_y` |
| `hydrologic_water_budget_residual_km3_y` | `mass_balance_residual_km3_y` |
| `max_abs_hydrologic_water_budget_cell_residual_mm_y` | `max_abs_cell_residual_mm_y` |

It additionally requires `hydrologic_water_budget_recompute_count == hydrology_recompute_count == (number of stages for that feedback id)`.

---

## River network evolution

`enrich_world_with_river_network_evolution` (`src/magic_geo/river_network_evolution.py:217`) is a **diagnostic risk scoring plus a synthetic reorganization trajectory**. It changes no native drainage field; `river_reorganization_histories` is registered as a `posthoc_diagnostic_trajectory` (`geo_evolution_provenance.py:50`).

### Per-cell risks (river cells only)

| Index | Formula | Line |
|---|---|---|
| `accumulation_index` | `clamp(log1p(accum) / log1p(max_accum))` | `river_network_evolution.py:37` |
| `low_gradient_index` | `clamp(1 − gradient/0.018)` where gradient is the conditioned-surface drop over great-circle distance | `274` |
| `sediment_index` | `clamp(local / max_local)` with `local = sediment_deposition_m + fluvial_sediment_routed_outgoing_m` (falls back to `sediment_export_m`); if the global max is 0, `clamp(sediment_thickness_m/250)` | `57`-`69` |
| `water_index` | fraction of neighbours that are water | `72` |
| `river_avulsion_risk` | `clamp(0.20·accum + 0.26·low_gradient + 0.24·sediment + 0.14·water + 0.12·overflow_channel_avulsion_risk + landform_bonus)` | `278` |
| landform bonus | `+0.22` for `delta`/`floodplain`; `+0.12` for `river_valley`/`coastal_plain`/`lacustrine_basin` | `84`-`90` |
| `river_capture_risk` | best over cross-basin neighbours of `clamp(0.30·accum + 0.30·low_divide + 0.22·downhill_pull + 0.12·target_accum + 0.06·target_channel)` | `305` |
| `low_divide_index` | `clamp(1 − abs(Δelevation)/750)` | `301` |
| `downhill_pull` | `clamp((self − target + 75)/650)` | `302` |
| `target_channel_index` | `1.0` river, `0.35` water, else `0.0` | `304` |
| `river_network_instability_index` | `max(capture_risk, avulsion_risk)` | `324` |

Capture candidates are only evaluated against neighbours whose `basin_id` is valid and **different** from the source's.

Cells also receive `river_capture_target_cell_id`, `river_capture_target_basin_id`, `river_capture_divide_relief_m` and `river_capture_target_distance_km` for the winning candidate.

### Events and trajectories

Candidates at or above `EVENT_RISK_THRESHOLD = 0.25` become events, sorted by descending risk then type then source cell id, truncated to `MAX_EVENT_COUNT = 64`, and re-`id`ed 0..n−1 (`river_network_evolution.py:385`-`388`). Two event types exist: `river_capture_candidate` and `river_avulsion_candidate`.

Each event gets exactly one `river_reorganization_histories` record with `REORGANIZATION_STEP_COUNT = 4` steps. Step fields: `stage_index`, `elapsed_years` (`round(progress·4000)` — a synthetic index, not a physical time), `active_process` (`headward_capture` or `avulsion_channelization`), `divide_relief_m`, `divide_lowering_m`, `channel_gradient`, `channelization_index`, `diversion_probability_index`, `sediment_reworking_m`, `capture_headward_erosion_index`, `avulsion_belt_width_index`, `basin_connectivity_change_index`, `reorganization_confidence_index`. `high_reorganization_pressure` is set when `risk >= HIGH_RISK_THRESHOLD (0.65)` or the final diversion probability is `>= 0.65`.

The subsystem validator `river_evolution_channels.evolution_event_history_links` enforces the one-to-one event↔history mapping, valid cell references, bounded indices and the three summary mirrors (`src/magic_geo/geo_validation_subsystems.py:1547`).

---

## River channel morphology

`enrich_world_with_river_channel_morphology` (`src/magic_geo/river_channel_morphology.py:144`) runs on `is_river && !is_water` cells; everything else is reset to zeros and `channel_morphology_class = "non_channel"`, `river_channel_system_id = -1`. Model type: `causal_flow_sediment_wetland_baseflow_channel_morphology_v1`.

### Normalizations and drivers

| Quantity | Definition | Line |
|---|---|---|
| `flow_norm` | `clamp(flow_accumulation / max(1, global max flow_accumulation))` | `178` |
| `runoff_norm` | `clamp(runoff_mm_y / 2200.0)` | `179` |
| `slope_index` | `clamp(downstream_slope / 0.028)` | `181` |
| `sediment_index` | `clamp(routed/85·0.45 + sediment_deposition_m/18·0.35 + sediment_thickness_m/30·0.20)` | `188` |
| `lowland` | 1.0 if landform ∈ `{delta, floodplain, river_valley, coastal_plain, lacustrine_basin}` | `193` |
| `wetland`, `groundwater`, `aridity` | `wetland_extent_index`, `baseflow_support_index`, `seasonal_aridity_index`, each clamped | `194`-`196` |
| `ice` | `clamp(ice_thickness_m / 450)` | `197` |
| `floodplain_connectivity_index` | `clamp(0.34·lowland + 0.22·(1−slope_index) + 0.18·sediment + 0.14·wetland + 0.12·groundwater)` | `198` |

`downstream_slope` uses the conditioned surface (`hydrologic_surface_elevation_m` → `filled_elevation_m` → `elevation_m`) divided by great-circle distance in metres with a 1 m floor (`river_channel_morphology.py:47`-`71`).

### Geometry (as actually computed)

```
bankfull_discharge_m3_s = max(0, 8.0
    + 4600·flow_norm^0.82 · (0.30 + 0.62·runoff_norm + 0.08·groundwater)
    - 420·ice - 120·aridity)

river_channel_width_m   = max(0, 5.0
    + 210·flow_norm^0.56 · (0.42 + 0.36·runoff_norm + 0.22·floodplain)
    + 36·sediment_index - 14·slope_index - 18·ice)

river_channel_depth_m   = max(0, 0.35
    + 7.6·flow_norm^0.42 · (0.36 + 0.34·runoff_norm + 0.12·groundwater + 0.18·(1-sediment_index))
    + 0.55·slope_index - 0.36·aridity - 0.45·ice)

stream_power_index = clamp(0.42·(Q/4200) + 0.34·slope_index + 0.12·runoff_norm
                         + 0.08·sediment_index + 0.04·flow_norm)
```

These are power-law-shaped empirical relations, not solutions of a hydraulic-geometry regression against data. The record itself declares `model_limitation = "empirical_diagnostic_channel_geometry_without_subcell_cross_sections_calibrated_bankfull_frequency_or_transient_morphodynamics"` (`river_channel_morphology.py:325`).

### Classification (first match wins)

| Order | Condition | `channel_morphology_class` |
|---|---|---|
| 1 | `ice >= 0.28` | `glacial_outwash_channel` |
| 2 | `aridity >= 0.58` and `runoff_norm < 0.22` | `ephemeral_wadi` |
| 3 | `sediment_index >= 0.55` and `flow_norm >= 0.18` | `braided_sediment_rich_channel` |
| 4 | `slope_index >= 0.46` and `sediment_index < 0.38` | `incised_bedrock_channel` |
| 5 | `depth >= 3.2` and `floodplain >= 0.45` | `deep_alluvial_channel` |
| 6 | `depth >= 1.8` and `width >= 42.0` and `slope_index <= 0.32` | `navigable_lowland_channel` |
| 7 | otherwise | `small_headwater` |

Source: `river_channel_morphology.py:74`-`97`; mirrored exactly in the replay validator at `src/magic_geo/cli/validators/rivers.py:112`-`135`.

### Channel systems

River cells are grouped into **undirected mesh-connected components** (`river_channel_morphology.py:100`-`119`), not flow trees — so a confluence and its two tributaries are one system. Per system: `id`, `channel_type` (modal class, ties by name), `cell_count`, `cell_ids` (sorted), `basin_ids`, `source_cell_id` (highest conditioned surface, tie to lowest id), `outlet_cell_id` (highest accumulation among cells whose receiver leaves the component; falls back to all members), `length_km` (Σ great-circle over internal `flow_to` edges), `area_km2`, six `mean_*` fields, `navigable_depth_cell_count` (`depth >= 1.8 && width >= 35.0`), `floodplain_connected_cell_count` (`>= 0.45`), `high_stream_power_cell_count` (`>= 0.62`), and `channel_morphology_class_counts`.

---

## River hydraulics

`enrich_world_with_river_hydraulics` (`src/magic_geo/river_hydraulics.py:111`) consumes the morphology output and applies Manning's equation per channel cell. Model type: `manning_blended_diagnostic_river_hydraulics_v1`. Gravity is `surface_gravity_m_s2(world) = planet_parameters.gravity_g · 9.80665`, so hydraulics genuinely responds to configured planetary gravity.

### The computation chain, exactly as implemented

| Step | Expression | Line |
|---|---|---|
| Slope | `slope = max(1.0e-5, clamp(channel_slope_index) · 0.028)` | `148` |
| Cross-section | `area_m2 = max(0.001, width·depth)` (rectangular) | `149` |
| Wetted perimeter | `max(0.001, width + 2·depth)` | `150` |
| `hydraulic_radius_m` | `area_m2 / wetted_perimeter_m` | `151` |
| `manning_roughness_n` | `max(0.022, min(0.080, base + 0.006·sediment + 0.004·wetland + 0.010·ice))` | `39`-`45` |
| Discharge velocity | `bankfull_discharge_m3_s / area_m2` | `153` |
| Manning velocity | `R^(2/3) · sqrt(slope) / n` | `154` |
| `flow_velocity_m_s` | `max(0, min(12.0, 0.55·discharge_velocity + 0.45·manning_velocity))` | `155` |
| `froude_number` | `velocity / max(0.001, sqrt(g · max(0.001, depth)))` | `156` |
| `bed_shear_stress_pa` | `1000 · g · hydraulic_radius · slope` | `157` |
| `channel_capacity_index` | `clamp(0.38·A/450 + 0.34·Q/2400 + 0.16·R/4.5 + 0.12·v/4)` | `158` |
| `hydraulic_navigability_index` | see below | `160` |

The velocity is a **55 % / 45 % blend** of a continuity estimate and a Manning estimate — it is not a solved continuity or momentum equation. The model record says so: `velocity_model = "55_percent_discharge_plus_45_percent_manning_bounded_v1"`, `model_limitation = "steady_diagnostic_rectangular_hydraulics_without_solved_continuity_backwater_flood_frequency_or_transient_flow"`.

### Roughness base by morphology class

| Class | Base `n` |
|---|---|
| `small_headwater` | 0.045 |
| `incised_bedrock_channel` | 0.038 |
| `braided_sediment_rich_channel` | 0.048 |
| `deep_alluvial_channel` | 0.032 |
| `navigable_lowland_channel` | 0.030 |
| `ephemeral_wadi` | 0.052 |
| `glacial_outwash_channel` | 0.046 |
| unknown class | 0.044 (dict default) |

Source: `river_hydraulics.py:16`-`24`, mirrored at `src/magic_geo/cli/_constants.py:174`.

### Regime and navigability

```
_flow_regime(froude, velocity, shear):
    froude >= 1.0                              -> "supercritical"
    froude >= 0.80                             -> "transitional"
    velocity >= 2.6 or shear >= 120.0 Pa       -> "swift_subcritical"
    otherwise                                  -> "subcritical"

_hydraulic_navigability = clamp(
      0.30·clamp((depth-1)/3)
    + 0.22·clamp((width-25)/90)
    + 0.20·clamp(1 - abs(velocity-1.25)/2.5)
    + 0.14·clamp(1 - max(0, froude-0.45)/0.75)
    + 0.10·clamp(1 - slope_index/0.65)
    - 0.18·clamp(ice_thickness_m/300))
```

Thresholds: `WATER_DENSITY_KG_M3 = 1000.0`, `HYDRAULIC_NAVIGABILITY_THRESHOLD = 0.55`, `HIGH_SHEAR_STRESS_PA = 120.0` (`river_hydraulics.py:8`-`10`). The `12.0 m/s` velocity cap is an inline literal at `river_hydraulics.py:155`, republished as `river_hydraulics_model.maximum_velocity_m_s`.

### Reaches

`river_hydraulic_reaches` is a strict one-reach-per-`river_channel_systems` mapping (`reach_model = "one_reach_per_river_channel_system_v1"`). A system whose cells are all non-channel produces no reach. Each reach carries `id` (= the system id), `river_channel_system_id`, `cell_count`, `cell_ids`, `basin_ids`, `source_cell_id`, `outlet_cell_id`, `length_km`, `area_km2`, `dominant_hydraulic_flow_regime`, seven `mean_*` fields, `hydraulically_navigable_cell_count`, `supercritical_flow_cell_count`, `high_shear_stress_cell_count` and `hydraulic_flow_regime_counts`.

---

## Wetlands

`enrich_world_with_wetland_diagnostics` (`src/magic_geo/wetland_diagnostics.py:262`) scores every cell, then types and groups the qualifying ones. Marine cells and `biome == "ice_cap"` cells are hard-zeroed and forced to `wetland_system_type = "none"` (`wetland_diagnostics.py:147`, `291`).

### Indices

| Index | Formula | Line |
|---|---|---|
| `wetland_hydrology_index` | `clamp(0.24·soil_moisture + 0.24·(1−soil_drainage) + 0.16·wet_months + 0.16·runoff_generation_fraction + 0.12·balance + water_bonus)` | `155` |
| `wetland_soil_saturation_index` | `clamp(0.38·soil_moisture + 0.28·(1−drainage) + 0.18·organic + 0.70·water_bonus − 0.10·salinity)` | `159` |
| `wetland_ecotone_index` | `clamp(0.30·[biome==wetland] + 0.28·[ecotone∈{swamp,mangrove}] + 0.22·[landform∈{delta,floodplain,river_valley,lacustrine_basin,coastal_plain}] + 0.20·[coastal feature∈{tidal_marsh,delta_lobe,barrier_bar}])` | `165` |
| `wetland_connectivity_index` | `clamp(0.18·[is_river∨is_lake] + 0.34·(lake/river neighbours ÷ n) + 0.18·(water neighbours ÷ n) + 0.18·[coastal] + 0.12·clamp(flow_accumulation/25 000 000))` | `181` |
| `wetland_extent_index` | `clamp(0.34·hydrology + 0.28·saturation + 0.22·ecotone + 0.16·connectivity)` | `188` |

where `wet_months = clamp(wet_season_months/10)`, `balance = clamp(hydrologic_water_balance_mm_y / 1200)`, `water_bonus = 0.18` when the cell or a neighbour is fresh water, `organic = clamp(soil_organic_matter_fraction / 0.22)`.

### Typing

A cell becomes a wetland when `wetland_extent_index >= WETLAND_THRESHOLD (0.54)` **or** it carries a direct label (`biome == wetland`, ecotone ∈ `{swamp, mangrove}`, landform ∈ `{delta, floodplain, lacustrine_basin}`, or a `tidal_marsh`/`delta_lobe` coastal feature) — `wetland_diagnostics.py:284`-`290`. `_wetland_type` (`wetland_diagnostics.py:107`) is a first-match ladder producing `mangrove`, `tidal_marsh`, `delta_wetland`, `floodplain_wetland`, `lacustrine_wetland`, `peatland`, or `freshwater_swamp` (the terminal fallback appears twice — the `biome == wetland`/`swamp` branch and the default both return `freshwater_swamp`).

Same-type contiguous cells are grouped into `wetland_systems` records with `id`, `wetland_type`, `cell_ids`, `cell_count`, `area_km2`, centroid, five `mean_wetland_*` indices, `mean_precipitation_mm_y`, `mean_runoff_mm_y`, `mean_soil_moisture_index`, `river_cell_count`, `lake_cell_count`, `coastal_cell_count`, `delta_cell_count`, `mangrove_cell_count`, `linked_basin_ids`, `linked_watershed_ids`, `dominant_biome`, `dominant_landform`.

> **Known dead input.** `_region_record` reads a per-cell `watershed_id` field (`wetland_diagnostics.py:196`), but no producer in the tree writes `watershed_id` onto a cell — `graph_diagnostics.py:289` only uses that name as a *node* key inside the watershed graph. In practice `linked_watershed_ids` is therefore always an empty list. `linked_basin_ids` (from `basin_id`) is the populated equivalent.

---

## Navigability diagnostics

`enrich_world_with_navigability_diagnostics` (`src/magic_geo/navigability_diagnostics.py:251`) runs over **all** cells and is the only hydrology-adjacent enricher omitted from `generate_geo_world`. Model type `causal_channel_hydraulic_coastal_navigability_v1`; declared thresholds `NAVIGABLE_THRESHOLD = 0.52`, `HIGH_HARBOR_THRESHOLD = 0.62`, `TRANSPORT_CHOKEPOINT_THRESHOLD = 0.55`.

| Component | Domain | Formula | Line |
|---|---|---|---|
| `river_navigability_index` | `is_river && !is_water` | `clamp(0.24·flow + 0.13·runoff + 0.12·low_relief + lowland + 0.06·sediment_load + 0.14·channel_depth + 0.08·channel_width + 0.17·hydraulic − 0.24·ice − aridity_penalty)` | `43`-`67` |
| `coastal_navigability_index` (marine cell) | `water_body_type` marine | `clamp(0.30·depth + shelf + 0.20·land_contact + 0.26·chokepoint)` | `76`-`81` |
| `coastal_navigability_index` (land cell) | has marine neighbour | `clamp(0.32·neighbor_score + protected + river_mouth + 0.18·low_relief)` | `83`-`90` |
| `harbor_suitability_index` | land with marine neighbour | `clamp(0.32·coastal + protected + river_mouth + 0.14·low_relief + 0.18·settlement_score − 0.22·ice)` | `93`-`115` |
| `transport_chokepoint_index` | cells listed in `marine_chokepoints` | `clamp(0.72·constriction + 0.28·coastal)` | `118`-`127` |
| `navigability_index` | all | `max(river, coastal, harbor, chokepoint)` | `278` |

Class priority (`_navigability_class`, `navigability_diagnostics.py:130`): `transport_chokepoint` → `harbor` → `river_mouth` (both river and coastal at/above 0.52) → `river_corridor` → `coastal_corridor` → `non_navigable`.

Cells at or above `NAVIGABLE_THRESHOLD` are grouped into raw undirected connected components; each becomes a `navigable_waterways` record typed `transport_chokepoint` > `river_mouth_corridor` > `harbor_cluster` > `river_corridor` > `coastal_corridor`, carrying `cell_ids`, `area_km2`, mean indices, `max_harbor_suitability_index`, `transport_chokepoint_cell_count`, `settlement_ids`, `route_ids`, `marine_region_ids` and `watershed_ids` (which are actually `basin_id` values — `navigability_diagnostics.py:223`).

The model record declares `threshold_semantics = "unrounded_pre_serialization_values"` — thresholds are applied to the full-precision values before the 6-decimal rounding is written to the cell. It also declares `model_limitation = "diagnostic_transport_suitability_without_vessel_classes_seasonal_discharge_bathymetric_channels_or_route_cost_optimization"`.

Because `settlement_score`, `settlements` and `routes` are stripped in geo-only mode, harbor suitability would silently fall to its no-human baseline there; the enricher is simply not called on that path.

---

## Deltas

There is no separate delta model. Deltas are a **landform class** assigned by `derive_landforms` (`cpp/src/engine/environment.cpp:417`), which runs after the final hydrology solve. Landform index 12 is `delta` (`LANDFORM_NAMES`, `schema_names.hpp:37`). The condition (`environment.cpp:454`-`456`):

```cpp
cell.is_river && cell.elevation_m < 180.0
  && (coast || flows_to_water || flows_to_lake)
  && cell.sediment_thickness_m > 0.6
```

where `coast = has_ocean_neighbor(cells, i)`, `flows_to_water = cells[flow_to].is_water`, `flows_to_lake = cells[flow_to].is_lake`. The branch sits sixth in a first-match cascade, *after* the lake, closed-basin/saline, ice-field (`ice_thickness_m > 180` or `biome == ice_cap`), glacial-valley and moraine branches — so a lake cell, a closed basin, or a heavily glaciated cell never becomes a delta no matter how the delta predicate evaluates.

Delta cells receive downstream side-effects in the same function (`environment.cpp:476`-`485`): `soil_type = alluvial`, `fertility += 0.16`, `biome = wetland` if `precipitation > 500` and not an ice cap, `resource = fertile_alluvium` if `fertility > 0.64`, and `settlement_score += 0.08`.

Delta plausibility is scored by `hydrology_realism_checks.delta_lowland_sediment_terminal_water` (`src/magic_geo/hydrology_realism.py:325`), which counts a delta cell as qualifying when its terminal environment is `marine` or `lacustrine`, `elevation_m <= 300`, `sediment_thickness_m >= 0.5` **or** `sediment_deposition_m >= 0.5`, and it is a river cell or has positive runoff. The target band is `[0.75, 1.0]`. `_delta_terminal_environment` (`hydrology_realism.py:62`) classifies the downstream cell as `lacustrine` if it is a lake, `marine` if it is water, else falls back to marine when any neighbour is water, else `unrecognized`.

---

## Complete world-key and cell-field table

### World keys

| World key | Kind | Producer | Source |
|---|---|---|---|
| `hydrologic_water_budget_model` | dict | native serializer over the budget history | `cpp/src/engine/world_serialization.cpp:87`, `process_serialization.cpp:451` |
| `hydrologic_water_budget_history` | list (native ledger) | `compute_hydrologic_water_budget` via `stabilize_numeric_depressions` | `world_serialization.cpp:92`, `hydrology.cpp:1145` |
| `numeric_depression_correction_history` | list (native mixed ledger) | `stabilize_numeric_depressions` | `world_serialization.cpp:121`, `hydrology.cpp:1301` |
| `watersheds` | list | `generate_watersheds` (native), annotated in place by `enrich_world_with_watershed_diagnostics` and `enrich_world_with_physical_boundary_geometry` | `world_serialization.cpp:205`, `water_features.cpp:269`, `watershed_diagnostics.py:164`, `boundary_geometry.py:133` |
| `lake_basins` | list | `generate_lake_basins` | `world_serialization.cpp:207`, `water_features.cpp:53` |
| `lake_overflow_histories` | list (diagnostic) | `enrich_world_with_lake_overflow_history` | `hydrology_dynamics.py:404` |
| `lake_overflow_channel_histories` | list (diagnostic) | same enricher, channel sub-pass | `hydrology_dynamics.py:277` |
| `hydrology_realism_checks` | list | `enrich_world_with_hydrology_realism` | `hydrology_realism.py:381` |
| `river_network_evolution_events` | list (diagnostic) | `enrich_world_with_river_network_evolution` | `river_network_evolution.py:390` |
| `river_reorganization_histories` | list (diagnostic) | same enricher | `river_network_evolution.py:392` |
| `hydrologic_budget_regions` | list (diagnostic) | `enrich_world_with_hydrology_budget` | `hydrology_budget.py:232` |
| `wetland_systems` | list (diagnostic) | `enrich_world_with_wetland_diagnostics` | `wetland_diagnostics.py:335` |
| `river_channel_morphology_model` | dict | `enrich_world_with_river_channel_morphology` | `river_channel_morphology.py:307` |
| `river_channel_systems` | list | same enricher | `river_channel_morphology.py:342` |
| `river_hydraulics_model` | dict | `enrich_world_with_river_hydraulics` | `river_hydraulics.py:200` |
| `river_hydraulic_reaches` | list | same enricher | `river_hydraulics.py:238` |
| `navigability_model` | dict | `enrich_world_with_navigability_diagnostics` (full worlds only) | `navigability_diagnostics.py:309` |
| `navigable_waterways` | list | same enricher | `navigability_diagnostics.py:344` |

Closely coupled keys owned by other pages: `groundwater_recharge_model`, `aquifer_systems`, `groundwater_flow_model`, `groundwater_flow_systems` (see [Groundwater, Aquifers and Karst](groundwater-and-karst.md)); `sediment_routing_histories`, `fluvial_sediment_routing_model` (see [Sediment, Routing and Stratigraphy](sediment-and-stratigraphy.md)).

### Cell fields — native

Serialized by `cells_json` (`cpp/src/engine/entity_serialization.cpp`), `precision = float_precision`, `surface_precision = max(10, float_precision)`.

| Cell field | Producer | Serializer line |
|---|---|---|
| `water_depth_m` | `apply_sea_level` / lake fill in `compute_flow_and_rivers` | `:186` (round-trip `max_digits10`) |
| `is_water` | `apply_sea_level` | `:187` |
| `water_body_type` | `label_marine_water_bodies` (`ocean.cpp:277`) and the lake branch of `compute_flow_and_rivers` | `:188` |
| `hydrologic_potential_evapotranspiration_mm_y` | `compute_hydrologic_water_budget` | `:218` |
| `actual_evapotranspiration_mm_y` | same | `:220` |
| `infiltration_capacity_index` | same | `:222` |
| `infiltration_mm_y` | same | `:224` |
| `hydrologic_water_balance_mm_y` | same | `:226` |
| `water_budget_runoff_mm_y` | same | `:228` |
| `runoff_budget_residual_mm_y` | same | `:230` (surface precision) |
| `runoff_budget_consistency_index` | same | `:232` |
| `hydrologic_deficit_mm_y` | same | `:234` |
| `runoff_generation_fraction` | same | `:236` |
| `runoff_mm_y` | same (alias of `water_budget_runoff_mm_y`) | `:238` |
| `flow_to` | `compute_flow_and_rivers` | `:239` |
| `equal_filled_raw_downhill_rerouted` | same (spill fallback audit flag) | `:240` |
| `spill_to` | `compute_priority_flood_spill` | `:241` |
| `depression_component_id` | `compute_flow_and_rivers` | `:242` |
| `depression_sink_cell_id` | same | `:243` |
| `lake_basin_id` | reset by `compute_flow_and_rivers`, assigned by `generate_lake_basins` | `:244` |
| `depression_policy` | `compute_flow_and_rivers` | `:245` |
| `flow_accumulation` | same | `:246` |
| `filled_elevation_m` | `compute_priority_flood_spill` | `:247` |
| `hydrologic_surface_elevation_m` | `condition_hydrologic_surface` | `:248` (surface precision) |
| `hydrologic_flow_drop_m` | same | `:250` (surface precision) |
| `hydrologic_flow_slope` | same | `:252` (`max(12, surface_precision)`) |
| `hydrologic_surface_conditioned` | same | `:254` |
| `depression_depth_m` | `compute_priority_flood_spill` | `:256` |
| `spill_elevation_m` | `compute_flow_and_rivers` | `:257` |
| `lake_fill_fraction` | same | `:258` |
| `basin_id` | `assign_basin_ids` | `:259` |
| `is_river` | `compute_flow_and_rivers` (percentile gate) | `:260` |
| `is_lake` | same (wet depression branch) | `:261` |
| `is_closed_basin` | same (closed policy branch) | `:262` |
| `lake_overflows` | same | `:263` |
| `cumulative_numeric_depression_breach_excavation_m` | `apply_numeric_depression_correction` | `:265` |
| `cumulative_numeric_depression_breach_deposition_m` | same | `:269` |
| `numeric_depression_breach_event_count` | same | `:272` |
| `numeric_depression_temporary_lake_event_count` | same (deferral branch) | `:274` |
| `fluvial_sediment_depression_fill_m` | `route_fluvial_sediment` (sediment page) | `:309` |
| `landform` (`delta`, `floodplain`, `river_valley`, `lacustrine_basin`, `salt_flat`, …) | `derive_landforms` | `environment.cpp:417` |

### Cell fields — Python enrichers

| Cell field | Producer enricher | Source |
|---|---|---|
| `overflow_channel_active`, `overflow_channel_incision_m`, `overflow_channel_sediment_evacuated_km3`, `overflow_channel_avulsion_risk` | lake overflow history | `hydrology_dynamics.py:81`-`84`, `231`-`244` |
| `river_capture_risk`, `river_capture_target_cell_id`, `river_capture_target_basin_id`, `river_capture_divide_relief_m`, `river_capture_target_distance_km`, `river_avulsion_risk`, `river_network_instability_index` | river network evolution | `river_network_evolution.py:257`-`263`, `326`-`333` |
| `hydrologic_budget_class`, `hydrologic_budget_region_id` | hydrology budget | `hydrology_budget.py:180`-`181`, `133` |
| `wetland_extent_index`, `wetland_hydrology_index`, `wetland_soil_saturation_index`, `wetland_ecotone_index`, `wetland_connectivity_index`, `wetland_coastal_flag`, `wetland_system_type`, `wetland_system_id` | wetland diagnostics | `wetland_diagnostics.py:293`-`300`, `257` |
| `river_channel_width_m`, `river_channel_depth_m`, `bankfull_discharge_m3_s`, `channel_slope_index`, `stream_power_index`, `floodplain_connectivity_index`, `channel_morphology_class`, `river_channel_system_id` | river channel morphology | `river_channel_morphology.py:164`-`171`, `225`-`231`, `248` |
| `hydraulic_radius_m`, `flow_velocity_m_s`, `froude_number`, `bed_shear_stress_pa`, `manning_roughness_n`, `channel_capacity_index`, `hydraulic_navigability_index`, `hydraulic_flow_regime`, `river_hydraulic_reach_id` | river hydraulics | `river_hydraulics.py:131`-`139`, `163`-`171` |
| `river_navigability_index`, `coastal_navigability_index`, `harbor_suitability_index`, `transport_chokepoint_index`, `navigability_index`, `navigability_class`, `navigable_waterway_id` | navigability diagnostics | `navigability_diagnostics.py:280`-`286`, `212` |
| `sediment_routing_load_m` (read by hydraulics roughness and navigability) | sediment routing history | `sediment_routing.py:94`, `159` |

### Native summary keys (hydrology)

| Summary key | Source line in `cpp/src/engine/summary.cpp` |
|---|---|
| `depression_routing_model`, `depression_geology_model` | `:1324`, `:1326` |
| `numeric_depression_correction_model`, `..._selection_model`, `..._breach_diagnostic_model`, `..._breach_mass_transfer_model`, `..._selection_reason` | `:1328`-`:1341` |
| `numeric_depression_breach_gradient_step_m`, `numeric_depression_selected_breach_max_depth_m`, `numeric_depression_correction_max_pass_count`, `numeric_depression_fill_depth_tolerance_m` | `:1334`-`:1345` |
| `hydrologic_surface_model`, `hydrologic_water_budget_model`, `hydrologic_water_budget_execution_order`, `hydrologic_flat_gradient_step_m` | `:1346`-`:1353` |
| `river_extraction_model`, `river_extraction_percentile`, `river_flow_accumulation_threshold` | `:1354`-`:1359` |
| `simulation_clock_hydrologic_water_budget_recompute_count`, `simulation_clock_hydrology_recompute_count` | `:1374`-`:1377` |
| `river_count`, `lake_count`, `flow_cycle_cell_count` | `:1641`, `:1657`, `:1656` |
| `equal_filled_raw_downhill_reroute_count`, `hydrologic_surface_conditioned_cell_count`, `equal_filled_flow_edge_count`, `raw_uphill_flow_edge_count`, `non_downhill_hydrologic_flow_edge_count`, `max_hydrologic_surface_adjustment_m`, `max_raw_uphill_flow_step_m` | `:1642`-`:1652` |
| `terminal_land_sink_count`, `avoidable_equal_filled_raw_downhill_sink_count` | `:1653`-`:1655` |
| `depression_component_count`, `depression_component_cell_count`, `lake_basin_count`, `overflowing_lake_basin_count`, `staged_overflow_lake_basin_count`, `high_avulsion_risk_lake_basin_count` | `:1658`-`:1663` |
| `preserved_geologic_depression_count`, `corrected_numeric_depression_count`, `temporary_numeric_lake_depression_count`, `closed_depression_count` | `:1664`-`:1667`, `:1773` |
| `numeric_depression_correction_pass_count`, `..._event_count`, `..._fill_candidate_*`, `..._temporary_lake_*`, `..._breach_*` (feasible / lower-volume / depth-bound / capacity / selected counts and volumes) | `:1668`-`:1767` |
| `mean_lake_fill_fraction`, `lake_storage_capacity_km3`, `lake_annual_runoff_km3`, `mean_lake_overflow_path_length_km`, `mean_lake_avulsion_risk` | `:1774`-`:1781` |
| `basin_count`, `endorheic_basin_count`, `watershed_count`, `endorheic_watershed_count`, `largest_watershed_area_km2`, `watershed_geometry_count`, `largest_watershed_boundary_cell_count`, `watershed_polygon_count`, `largest_watershed_polygon_area_km2`, `mean_watershed_polygon_area_error_fraction`, `mean_watershed_compactness_index`, `mean_watershed_geometry_quality`, `mean_watershed_boundary_perimeter_km` | `:1782`-`:1801` |
| `spill_corrected_cell_count`, `closed_basin_cell_count`, `max_depression_depth_m` | `:1820`-`:1822` |
| `river_downhill_fraction` | `:2087` |

---

## Configuration

The `hydrology` section has exactly two properties (`HydrologyConfig`, `src/magic_geo/config.py:354`-`368`):

| YAML path | Type | Default | Constraints | Description (verbatim) |
|---|---|---|---|---|
| `hydrology.river_percentile` | float | `0.92` | `ge=0.50`, `le=0.995` | "Flow-accumulation percentile threshold used to classify river cells." |
| `hydrology.preserve_geologic_depressions` | bool | `true` | — | "Keep geologic closed basins instead of filling every depression to an outlet." |

Both are marshalled into the flat native config struct — note that the frozen v1 layout orders them **`preserve_geologic_depressions` before `river_percentile`**, the reverse of the YAML order (`cpp/include/magic_geo/native.hpp:112`-`113`; mirrored by `src/magic_geo/native.py:79`-`80` and marshalled at `native.py:322`-`323`). `preserve_geologic_depressions` crosses the C ABI as `int` (`1 if ... else 0`).

Hydrology also responds to configuration it does not own:

| Path | Effect on hydrology |
|---|---|
| `planet.radius_km` | `neighbor_distance_m` → every slope, every path length, every drainage density |
| `planet.gravity_g` | `surface_gravity_m_s2` → Froude number and bed shear stress in `river_hydraulics` |
| `planet.ocean_water_inventory_km3`, `planet.ocean_fraction_target` | `apply_sea_level`, hence the `is_water` mask that seeds the priority flood |
| `climate.*` | temperature and precipitation, hence PET and the entire loss partition |
| `erosion.iterations`, `erosion.maturation_timestep_ma` | number of stabilization calls and the nominal Ma coordinate on every stage record |
| `mesh.cell_count`, `mesh.neighbor_count` | the graph the flood, flow routing and river percentile operate on |

The number of `stabilize_numeric_depressions` calls is always `erosion.iterations + 2` (one initial, one per maturation iteration, one cryosphere coupling), and each call appends at least one water-budget stage — more if a numeric correction pass is needed. The `earthlike` profile changes `climate.precipitation_scale` to `0.8`, which shifts the whole budget; the `smoke` profile drops `mesh.cell_count` to 128 and `erosion.iterations` to 1, so it produces three stabilization groups.

Both `hydrology.*` overrides are applied when the config file is created, not at generation time: `magic-geo generate` has no `--set`, and its only config-overriding flag is `--cells` (which overrides `mesh.cell_count`, not anything under `hydrology`). Its other options — `--config`/`-c`, `--output`/`-o`, `--summary`, `--cells-csv`, `--geo-only`, `--world-format` — are I/O and pipeline selectors (`src/magic_geo/cli/commands/generate.py:18`).

```bash
magic-geo init-config \
  --profile earthlike \
  --set hydrology.river_percentile=0.88 \
  --set hydrology.preserve_geologic_depressions=false \
  --output magic-geo.yaml --force

magic-geo generate --config magic-geo.yaml --output runs/world.json
```

---

## Validation and closure checks

### `validate-geo`, domain `hydrology` (4 checks)

| Check | Pass condition | Source |
|---|---|---|
| `land_water_budget_closure` | max land residual `<= 2.0e-3 mm/y`; zero marine cells with any nonzero AET/infiltration/runoff; zero negative terms | `src/magic_geo/geo_validation.py:1526` |
| `groundwater_partition_closure` | recharge, volume-conversion and routing partitions all close within their tolerances (groundwater page) | `geo_validation.py:1638` |
| `configured_gravity_propagation` | `river_hydraulics_model.gravity_m_s2 == gravity_g · 9.80665` within 1e-9 | `geo_validation.py:1672` |
| `acyclic_downhill_drainage` | every `flow_to` is a mesh neighbour; strictly downhill on the conditioned surface; no cycles; topological sort covers all cells; reconstructed accumulation matches within a precision-aware tolerance; every `is_river` cell is non-water with a receiver and `runoff > 10`; every land terminal is water, lake, closed basin, `closed_land` or endorheic; `land_basin_ids == watershed_basin_ids` | `geo_validation.py:1795` |

The accumulation tolerance is `max(0.001, max_accum·1e-8, surface_area · 0.5 · 10^(−output_float_precision))` — i.e. it explicitly accounts for the serializer's decimal quantization (`geo_validation.py:1740`-`1748`).

### `validate-geo`, domain `lakes_watersheds` (3 checks)

| Check | Enforces | Source |
|---|---|---|
| `lake_basin_membership_and_storage` | sequential ids; `cell_count`/`area_km2` invert `lake_basin_id`; overflow paths unique, resolvable and mesh-adjacent; nonnegative storage fields; `geologic_area_fraction`/`avulsion_risk` in [0,1]; `fill_fraction` in [0,1.5]; `overflow_index` in [0,50] **and** replayed as `min(50, max(0, annual_runoff/max(0.001, capacity)))` when `overflows`, else exactly 0 | `geo_validation_subsystems.py:1362` |
| `lake_overflow_history_conservation` | one history per basin id; step continuity (`start == previous end`); per-step closure `end == start + inflow − evaporation − spill − sink` to 2e-3 km³; bounded `fill_fraction`/`avulsion_risk`; the three aggregate totals; channel paths adjacent with `segment_count == len(path) − 1`; four summary mirrors | `geo_validation_subsystems.py:1427` |
| `watershed_internal_topology_and_aggregates` | `cell_count`/`area_km2` invert land `basin_id`; main-channel cells all in-basin, adjacent, endpoints matching; reciprocal `neighbor_watershed_ids`; nonnegative lengths/gradients/densities; bounded compactness and geometry quality; three summary mirrors | `geo_validation_subsystems.py:1481` |

### `validate-geo`, domain `river_evolution_channels` (3 checks)

`evolution_event_history_links` (`:1547`), `channel_system_membership_and_geometry` (`:1595`), `hydraulic_reach_source_links_and_ranges` (`:1641`). The latter two enforce that the system/reach `cell_ids` partitions are exact inverses of the per-cell `river_channel_system_id` / `river_hydraulic_reach_id` assignments, with no overlaps.

### Layer contract `hydrology` (phase 7)

Declared in `src/magic_geo/geo_layer_contracts.py:150`-`174`:

- **Dependencies**: `climate_atmosphere`, `relief_bathymetry`.
- **Required outputs**: `hydrologic_water_budget_model` (dict), `hydrologic_water_budget_history` (nonempty list), `lake_basins` (list), `watersheds` (list), `river_channel_systems` (list), `groundwater_recharge_model` (dict), `groundwater_flow_model` (dict), `groundwater_flow_systems` (list), `hydrology_realism_checks` (list).
- **Validator domains**: `hydrology`, `lakes_watersheds`, `river_evolution_channels`, `aquifers_wetlands_karst`.
- `temporal_class`: `annual_diagnostic_budget_recomputed_per_coupled_stage`.
- `evidence_class`: `mass_balance_replay_and_partial_external_network_fit`.
- `empirical_realism_proven`: **`False`**, like every layer.

### `validate` (monolithic CLI), hydrology-relevant replays

| Validator | What it replays | Source |
|---|---|---|
| `_validate_hydrologic_water_budget` | every constant in the model record; every stage's `id`/`feedback_stage_id`/`stabilization_recomputation_index`/`stage`/`erosion_iteration` against the feedback ledger; the twelve nominal-time fields (via `_nominal_time_record_valid`, `src/magic_geo/cli/validators/_shared.py:16`) against `min(feedback_stage_id, configured_erosion_iterations)·nominal_timestep_ma`; `local_relief` from elevations and neighbours; every one of the seven per-cell results; the six aggregates; the final-stage → cell-field mirror for eight fields; nine `final_*` model values | `src/magic_geo/cli/validators/hydrology.py:37` |
| `_validate_river_channel_morphology` | all 12 model strings plus `runoff_normalization_mm_y`, `slope_normalization` and `planet_radius_km`, the six per-cell geometry values, the classification tree, the connected-component system list field-for-field, and 13 summary keys | `src/magic_geo/cli/validators/rivers.py:24` |
| `_validate_river_hydraulics` | all 14 model strings, gravity/density/thresholds/`maximum_velocity_m_s`, the seven per-cell hydraulic values, the regime tree, the one-reach-per-system list, and 14 summary keys | `src/magic_geo/cli/validators/rivers.py:517` |
| `_validate_navigability` | the navigability model record, per-cell components, class assignment and the exact waterway records | `src/magic_geo/cli/validators/navigability.py:21` |
| hydrology realism block | each `hydrology_realism_checks` record's id/domain/bounds/`passed` consistency, and the five summary mirrors | `src/magic_geo/cli/commands/validate.py:7900`-`7945` |

### `hydrology_realism_checks` (5 records, domain `hydrology`)

Produced by `enrich_world_with_hydrology_realism` (`src/magic_geo/hydrology_realism.py:151`). Each record carries `id`, `domain`, `name`, `question`, `metric`, `value`, `target_min`, `target_max`, `score`, `passed`, `evidence`; `score` is `1.0` inside the band and decays linearly by `distance/width` outside it.

| Name | Metric | Target band | Definition |
|---|---|---|---|
| `river_terminal_sink_validity` | `fraction_river_cells_reaching_valid_sink` | 0.95 – 1.0 | trace each river cell downstream (max `len(cells)+1` steps); valid when no cycle and the terminal matches one of five accepted reasons: terminal water body ∈ `{ocean, continental_shelf, inland_sea, fresh_lake, saline_basin}`, `is_lake`, watershed `outlet_type` ∈ `{ocean, lake, saline_basin, inland_sea, closed_land}`, `is_endorheic`, or `is_closed_basin` |
| `river_downhill_flow` | `fraction_river_edges_with_nonincreasing_filled_elevation` | 0.95 – 1.0 | conditioned-surface elevation of the receiver `<= source + 1e-6` |
| `tributary_merge_coherence` | `accumulation_monotonicity_and_no_cycle_index` | 0.85 – 1.0 | `0.75·(fraction of edges with non-decreasing accumulation) + 0.25·(1 − cycle fraction)` |
| `delta_lowland_sediment_terminal_water` | `fraction_delta_cells_low_sediment_river_at_marine_or_lacustrine_terminal` | 0.75 – 1.0 | see [Deltas](#deltas) |
| `watershed_divide_alignment` | `mean_fraction_boundary_cells_above_basin_mean_or_outlet` | 0.55 – 1.0 | per watershed, fraction of `boundary_cell_ids` whose conditioned elevation is at or above `max(basin mean elevation, outlet elevation)`; unweighted mean across watersheds |

Empty populations short-circuit to `1.0` (no rivers ⇒ perfect sink validity, no deltas ⇒ perfect delta score), which is a deliberate no-phenomenon convention, **not** evidence of correctness.

### Native fail-closed invariants

These throw and abort generation rather than degrade:

| Message | Trigger |
|---|---|
| `Priority-Flood routing surface rises downstream` | filled surface increases along a flow link |
| `conditioned hydrologic surface is not downhill` | a conditioned drop is not strictly positive |
| `hydrology flow receiver is invalid` | `flow_to` out of range or self-referencing |
| `hydrology flow graph contains a cycle` | topological sort covers fewer than `n` cells |
| `raw hydrology receiver is invalid` / `raw hydrology drainage labeling did not terminate` | raw-downhill labelling failure |
| `hydrology depression unit is invalid` / `... has no area` | malformed depression unit |
| `open depression unit has no spill corridor` / `depression spill corridor is invalid` | corridor rewiring failure |
| `closed depression raw routing leaves its footprint` | closed-branch raw receiver escapes the unit |
| `numeric depression correction candidate is invalid` / `... metadata is inconsistent` / `... depth is invalid` / `... component is empty` / `... sink is invalid` | correction candidate integrity |
| `numeric depression breach conflicts with an earlier correction` / `numeric depression deferral conflicts with an earlier correction` | intra-pass elevation drift |
| `numeric depression breach sediment-interface target mismatch` | committed elevation ≠ planned target |
| `numeric depression breach deposition capacity was not realized` | leftover excavated volume |
| `numeric depression correction did not converge within the bounded pass count` | more than 16 stabilization passes |
| `empty depression component` / `depression component sink is invalid` / `depression component metadata is inconsistent` | `generate_lake_basins` integrity |

---

## Worked examples

### Generate and inspect the water budget closure

```bash
magic-geo init-config --profile earthlike --output magic-geo.yaml --force
magic-geo generate --config magic-geo.yaml --output runs/world.json
python - <<'PY'
import json
world = json.load(open("runs/world.json"))
model = world["hydrologic_water_budget_model"]
print("stages:", model["history_stage_count"])
print("closure declared:", model["cell_mass_balance_closed"])
print("physical time resolved:", model["physical_time_resolved"])
print("final land P  km3/y:", model["final_land_precipitation_volume_km3_y"])
print("final AET     km3/y:", model["final_actual_evapotranspiration_volume_km3_y"])
print("final infilt  km3/y:", model["final_infiltration_volume_km3_y"])
print("final runoff  km3/y:", model["final_runoff_volume_km3_y"])
print("final residual km3/y:", model["final_mass_balance_residual_km3_y"])
print("max cell residual mm/y:", model["final_max_abs_cell_residual_mm_y"])
PY
```

### Replay one cell's budget by hand

```python
import json, math

world = json.load(open("runs/world.json"))
stage = world["hydrologic_water_budget_history"][-1]
perm  = world["hydrologic_water_budget_model"]["lithology_permeability"]
names = ["basalt","granite","limestone","sandstone","shale","volcanic","metamorphic"]

i = next(k for k, m in enumerate(stage["is_marine_by_cell"]) if m == 0)
T    = stage["temperature_c_by_cell"][i]
P    = stage["precipitation_mm_y_by_cell"][i]
rel  = stage["local_relief_m_by_cell"][i]
sed  = stage["sediment_thickness_m_by_cell"][i]
k    = perm[names[stage["lithology_by_cell"][i]]]

clamp = lambda v, lo, hi: max(lo, min(hi, v))
pet   = max(0.0, T + 8.0) * 31.0
cap   = clamp(0.62*k + 0.16*clamp(sed/3.0, 0, 1)
              + 0.12*(1.0 - clamp(rel/2500.0, 0, 1))
              - 0.10*clamp((-T - 2.0)/18.0, 0, 1), 0.02, 0.90)
loss  = min(P, 0.68 * pet)
share = clamp(0.10 + 0.50*cap, 0.10, 0.10 + 0.50*0.90)
inf   = loss * share
aet   = loss - inf
run   = max(0.0, P - loss)

assert math.isclose(pet, stage["potential_evapotranspiration_mm_y_by_cell"][i], abs_tol=1e-6)
assert math.isclose(cap, stage["infiltration_capacity_index_by_cell"][i],       abs_tol=1e-6)
assert math.isclose(inf, stage["infiltration_mm_y_by_cell"][i],                 abs_tol=1e-6)
assert math.isclose(aet, stage["actual_evapotranspiration_mm_y_by_cell"][i],    abs_tol=1e-6)
assert math.isclose(run, stage["runoff_mm_y_by_cell"][i],                       abs_tol=1e-6)
assert abs(P - aet - inf - run) <= 2e-3          # the closure requirement
print("cell", stage["cell_ids"][i], "closes")
```

### Depression policy census

```python
import json
from collections import Counter

world = json.load(open("runs/world.json"))
print(Counter(b["depression_policy"] for b in world["lake_basins"]))
print("overflowing:", sum(1 for b in world["lake_basins"] if b["overflows"]))
print("endorheic watersheds:",
      sum(1 for w in world["watersheds"] if w["is_endorheic"]),
      "of", len(world["watersheds"]))
print(Counter(w["outlet_type"] for w in world["watersheds"]))
```

### Compare both branches of the depression policy

```bash
magic-geo init-config --profile earthlike \
  --set hydrology.preserve_geologic_depressions=true \
  --output preserve.yaml --force
magic-geo init-config --profile earthlike \
  --set hydrology.preserve_geologic_depressions=false \
  --output fill.yaml --force

magic-geo generate --config preserve.yaml --output runs/preserve.json
magic-geo generate --config fill.yaml     --output runs/fill.json

python - <<'PY'
import json
for path in ("runs/preserve.json", "runs/fill.json"):
    s = json.load(open(path))["summary"]
    print(path,
          "preserved:", s["preserved_geologic_depression_count"],
          "corrected:", s["corrected_numeric_depression_count"],
          "temp lakes:", s["temporary_numeric_lake_depression_count"],
          "closed:",    s["closed_depression_count"],
          "passes:",    s["numeric_depression_correction_pass_count"],
          "lakes:",     s["lake_count"])
PY
```

### Run the hydrology gates

```bash
magic-geo validate-geo --world runs/world.json --profile earthlike --output runs/geo-report.json
python - <<'PY'
import json
report = json.load(open("runs/geo-report.json"))
for check in report["checks"]:
    if check["domain"] in {"hydrology", "lakes_watersheds", "river_evolution_channels"}:
        print(f"{check['status']:<15} {check['domain']}.{check['name']}")
layer = next(l for l in report["layer_contracts"]["layers"] if l["id"] == "hydrology")
print("contract passed:", layer["contract_passed"],
      "| empirical realism proven:", layer["empirical_realism_proven"])
PY
```

---

## Limitations and unresolved claims

**Time.** Nothing on this page is physically timed. Every water-budget stage record carries `nominal_time_calibrated: false` and `physical_time_resolved: false`, with a **zero-duration** nominal interval (`nominal_interval_duration_ma = 0.0`, `advances_nominal_time = false`) whose value is derived only from the configured `erosion.maturation_timestep_ma`. The `year` axis in `lake_overflow_histories` and the `elapsed_years` axis in `river_reorganization_histories` are bookkeeping indices with no calibrated relationship to anything, and both families are classified `posthoc_diagnostic_trajectory` in `geo_evolution_provenance`.

**The budget is an annual empirical loss partition, not a soil-moisture model.** The model record states its own limitation verbatim: `empirical_annual_loss_partition_without_transient_soil_moisture_groundwater_return_flow_or_calibrated_time`. There is no storage state, no return flow, no seasonality inside the budget (the monthly climate exists but the budget consumes the annual means), and the "closure" that validation enforces is the closure of *this partition*, not of a physical hydrologic cycle.

**Runoff never returns to the ocean inventory.** Runoff is routed and accumulated, but no mass is transferred from land runoff back into `planet.ocean_water_inventory_km3`; sea level is solved independently by `apply_sea_level`. There is no coupled global water mass budget across the atmosphere, land and ocean.

**Depression handling is a numerical policy, not a geomorphic one.** `is_geologic_depression` is a four-clause heuristic on a single sink cell (`crust_type ∈ {rift_basin, sedimentary_basin}` or boundary forcing above fixed thresholds). The breach alternative is explicitly a *diagnostic proxy* — `weighted_graph_excavation_proxy_monotone_lower_outlet_v1` — with a 1 mm/hop synthetic gradient and a 50 m depth cap; it selects by adjustment *volume*, not by any erosional rate law. Every non-selected breach is recorded as a counterfactual with `fill_candidate_applied: false`, and the deferral path moves **zero** material by design.

**Lake depths and areas are parametric.** Lake water depth is `clamp(depth, 0.2, 240.0)` metres around a fill-fraction-scaled surface; the fill fraction is an empirical index `(mean_runoff/220)·clamp(aridity, 0.08, 2.5)/(1 + max_depth/120)` that can exceed 1. There is no lake energy balance, no bathymetric hypsometry below cell resolution, and evaporation appears only inside the diagnostic overflow history (`clamp(0.35 + depth/2500, 0.35, 1.20)` m/y), never in the native state.

**Watershed geometry is an approximation.** The boundary ring is at most 64 boundary *cell centres* angle-sorted in a tangent plane, and `dissolved_polygon_area_km2` is an orthographic shoelace area over that ring — hence `polygon_area_error_fraction` is a first-class output. `compactness_index` and `geometry_quality` are derived from that approximation, not from a true dissolved polygon. Watershed `mean_runoff_mm_y` and `mean_elevation_m` are **unweighted** cell means, unlike the area-weighted centroid.

**Endorheism is a topological label, not a climatic verdict.** `is_endorheic` is simply `outlet_type != ocean`, so watersheds draining to an inland sea or a freshwater lake are counted endorheic. Any comparison with HydroBASINS endorheic fractions must account for that definition.

**Channel geometry and hydraulics are diagnostics, not solved flow.** Both modules publish their own limitation strings: `empirical_diagnostic_channel_geometry_without_subcell_cross_sections_calibrated_bankfull_frequency_or_transient_morphodynamics` and `steady_diagnostic_rectangular_hydraulics_without_solved_continuity_backwater_flood_frequency_or_transient_flow`. Cross-sections are rectangular; the slope is `channel_slope_index · 0.028` with a 1e-5 floor rather than a measured bed slope; velocity is a fixed 55/45 blend of two independent estimates and is capped at 12 m/s; `bankfull_discharge_m3_s` has no calibrated recurrence interval attached. Nothing here has been validated against gauged discharge.

**River extraction is a percentile, not a physical channel-initiation threshold.** The threshold is an order statistic of the world's own accumulation distribution, so the river-cell fraction is largely set by configuration rather than by a drainage-area/slope channel-head criterion. There is no drainage-area/slope channel-head law, no channel-initiation length scale, and no calibration of the resulting drainage density against any observed network — the `river_percentile` knob is a *selection* control, and moving it changes how much of the same drainage graph gets labelled a river, not how the drainage graph itself behaves.

**Navigability, wetlands and river-evolution risks carry no external validation.** They are index compositions with hand-set weights and thresholds. `navigability_model` states it lacks vessel classes, seasonal discharge, bathymetric channels and route-cost optimization. Wetland extent uses a single global threshold of 0.54 and a first-match type ladder. River capture/avulsion "risks" are static scores over the final state, never applied to the drainage graph — no capture or avulsion ever occurs.

**One dead input.** `wetland_systems[].linked_watershed_ids` reads a per-cell `watershed_id` field that no producer writes, so it is always empty in practice (see [Wetlands](#wetlands)).

**Contract passes are not realism claims.** The `hydrology` layer contract hardcodes `empirical_realism_proven: False`, and the `hydrology_realism_checks` family is emitted at `severity="warning"` inside `validate-geo`'s `realism_evidence` domain — a passing hydrology check band is evidence of internal plausibility against an Earth-analogue expectation, not a measurement.

---

## See also

- [Climate and Atmosphere](climate-and-atmosphere.md) — the precipitation and temperature fields the budget consumes, recomputed in the same stabilization pass
- [Groundwater, Aquifers and Karst](groundwater-and-karst.md) — where `infiltration_mm_y` goes next, and the recharge/vadose partition
- [Sediment, Routing and Stratigraphy](sediment-and-stratigraphy.md) — fluvial routing along `flow_to`, lake-trap deposition, and `sediment_routing_load_m`
- [Erosion, Maturation and Landscape Evolution](erosion-and-maturation.md) — the stream-power loop that consumes `flow_accumulation` and the maturation loop that calls hydrology once per iteration
- [Oceans, Currents and Coasts](oceans-and-coasts.md) — `apply_sea_level`, `label_marine_water_bodies`, coastal features and marine chokepoints
- [Topography, Isostasy and Thermal Subsidence](topography-and-isostasy.md) — the elevation field the priority flood operates on
- [Cryosphere: Ice Sheets, Glaciers and Permafrost](cryosphere.md) — the `cryosphere_coupling` stabilization stage and ice penalties in channel and navigability models
- [Biomes, Ecosystems and Disturbance](biomes-and-ecology.md) — wetland biome coupling and fire/water interactions
- [Settlements, Routes and Corridors](settlements-and-routes.md) — how navigability, ports and river corridors feed human geography
- [World Document Schema](../10-world-schema.md) — the authoritative key ordering for every record described here
- [Validation](../12-validation.md) — the `validate` and `validate-geo` gates in full
- [Geo Validation Suite](../13-geo-validation-suite.md) — the scenario matrix and paired hydrologic responses
- [Calibration Against Real-Earth Data](../14-calibration.md) — HydroBASINS endorheic fractions and HydroRIVERS Hack-law targets
- [Configuration Reference](../05-configuration-reference.md) — every `hydrology.*` and coupled property
- [Native Engine (C++ Core)](../08-native-engine.md) — stage ordering, invariants and the sediment-interface primitives
- [Glossary](../21-glossary.md) — depression unit, spill corridor, conditioned surface, endorheic
