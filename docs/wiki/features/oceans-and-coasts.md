# Oceans, Currents and Coasts

[Wiki home](../README.md) > Features

The marine domain is where a *configured water volume* becomes a *discrete wet mask*. A deterministic union-find elevation sweep in `cpp/src/engine/ocean.cpp` solves for the sea-level datum at which the largest connected flooded component holds exactly `planet.ocean_water_inventory_km3`, shifts every cell's sediment-interface datum so that sea level becomes elevation zero, and marks only that one component as marine. Everything after that — shelf classification, marine regions, chokepoints, currents, coastal features, reefs and port sites — is either a thin native rule over that mask or a post-hoc Python diagnostic. The single hard physical limitation that colours the entire page is stated by the engine itself: one elevation per cell, `cell_column_volume_without_subcell_bathymetry_straits_or_exact_coast_polygons`.

## On this page

- [Where the marine stages run](#where-the-marine-stages-run)
- [The volume-constrained sea-level solver](#the-volume-constrained-sea-level-solver)
- [What `ocean_fraction_target` actually does](#what-ocean_fraction_target-actually-does)
- [The `sea_level_model` contract block](#the-sea_level_model-contract-block)
- [Marine connectivity classification](#marine-connectivity-classification)
- [How bathymetry is represented](#how-bathymetry-is-represented)
- [Landmasses, marine regions, shelves and chokepoints](#landmasses-marine-regions-shelves-and-chokepoints)
- [Ocean circulation: the native current field](#ocean-circulation-the-native-current-field)
- [Ocean circulation: the transport-graph enricher](#ocean-circulation-the-transport-graph-enricher)
- [Heat transport and the climate coupling](#heat-transport-and-the-climate-coupling)
- [Coastal feature generation](#coastal-feature-generation)
- [Reef diagnostics](#reef-diagnostics)
- [Port site suitability](#port-site-suitability)
- [Complete marine record families](#complete-marine-record-families)
- [Complete marine cell fields](#complete-marine-cell-fields)
- [Marine summary keys](#marine-summary-keys)
- [Worked examples](#worked-examples)
- [Validation of the marine domain](#validation-of-the-marine-domain)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

---

## Where the marine stages run

The sea-level solve is not a one-shot stage. It is the *first* operation inside every hydrology stabilization pass, so it is re-solved every time the surface changes.

`stabilize_numeric_depressions` (`cpp/src/engine/hydrology.cpp:1122`) loops `recomputation_index` from `0` to `NUMERIC_DEPRESSION_CORRECTION_MAX_PASSES` inclusive (`cpp/src/engine/constants.hpp:55`, value `16`) and each pass executes, in this exact order (`cpp/src/engine/hydrology.cpp:1140-1155`):

| # | Call | Source |
|---|------|--------|
| 1 | `apply_sea_level(params, cells)` — accumulates into `result.sea_level_adjustment_m`, increments `sea_level_recompute_count` | `cpp/src/engine/ocean.cpp:5` |
| 2 | `label_marine_water_bodies(cells)` | `cpp/src/engine/ocean.cpp:277` |
| 3 | `compute_climate(params, cells)` — writes `ocean_current_*` | `cpp/src/engine/climate.cpp:251` |
| 4 | `compute_hydrologic_water_budget(...)` | `cpp/src/engine/hydrology.cpp:18` |
| 5 | `compute_flow_and_rivers(params, cells)` | `cpp/src/engine/hydrology.cpp:369` |

If a pass finds no remaining numeric-depression correction candidates, the loop returns; if the loop reaches `recomputation_index == 16` with candidates still present it throws `numeric depression correction did not converge within the bounded pass count` (`cpp/src/engine/hydrology.cpp:1177-1179`).

`stabilize_numeric_depressions` is itself invoked from three call sites: the `initial_climate_hydrology` stage (`cpp/src/engine/pipeline.cpp:107-116`), once per erosion iteration inside `erode` (`cpp/src/engine/earth_system.cpp:914`, call at `earth_system.cpp:1122`), and the `cryosphere_coupling` stage (`cpp/src/engine/pipeline.cpp:157-166`). The `sea_level_model` block therefore truthfully declares `sea_level_recomputed_each_erosion_stage: true` (`cpp/src/engine/process_serialization.cpp:3460`).

The remaining native marine stages run once, late in the pipeline:

| Stage | Function | Source | Produces |
|-------|----------|--------|----------|
| Marine biome / resource | inside `derive_soils_biomes_resources` | `cpp/src/engine/environment.cpp:327-334` | `biome`, `resource` for water cells |
| Marine landform | inside `derive_landforms` | `cpp/src/engine/environment.cpp:430-442` | `landform` for water cells |
| Coastal features | `generate_coastal_features(params, cells)` | `cpp/src/engine/environment.cpp:613` | `natural.coastal_features` |

The Python marine enrichers run in this order (`src/magic_geo/api.py`):

| Enricher | Full world | Geo-only | Module |
|----------|-----------|----------|--------|
| `enrich_world_with_cell_geometry` | position 3 (`api.py:202`) | position 3 (`api.py:310`) | `src/magic_geo/cell_geometry.py` |
| `enrich_world_with_sea_level_diagnostics` | position 4 (`api.py:203`) | position 7 (`api.py:318`) | `src/magic_geo/sea_level_diagnostics.py` |
| `enrich_world_with_ocean_circulation` | position 5 (`api.py:204`) | position 8 (`api.py:319`) | `src/magic_geo/ocean_circulation.py` |
| `enrich_world_with_navigability_diagnostics` | position 42 (`api.py:241`) | **not run** | `src/magic_geo/navigability_diagnostics.py` |
| `enrich_world_with_port_sites` | position 43 (`api.py:242`) | **not run** | `src/magic_geo/port_sites.py` |
| `enrich_world_with_ecosystem_dynamics` | position 46 (`api.py:245`) | position 37 (`api.py:359`) | `src/magic_geo/ecosystem_dynamics.py` |
| `enrich_world_with_reef_diagnostics` | position 47 (`api.py:246`) | position 38 (`api.py:360`) | `src/magic_geo/reef_diagnostics.py` |

Two consequences of that ordering are load-bearing:

- `sea_level_diagnostics` runs after `cell_geometry`, so `mean_neighbor_edge_length_km` exists and the chokepoint `width_proxy_km` is computable (`src/magic_geo/sea_level_diagnostics.py:276`).
- In geo-only worlds `navigability_diagnostics` and `port_sites` never run, so `harbor_suitability_index`, `coastal_navigability_index`, `navigability_index`, `port_site_id` and `port_site_type` are **absent** from cells. `reef_diagnostics` reads `port_site_id` with a `-1` default (`src/magic_geo/reef_diagnostics.py:362-368`), so reef `port_site_ids` is always `[]` in geo-only scope.

The geo layer contract records the sea-level/ocean phase explicitly (`src/magic_geo/geo_layer_contracts.py:113-131`):

| Contract field | Value |
|---|---|
| `id` | `sea_level_ocean` |
| `phase` | `5` |
| `name` | `Sea level, water bodies, shelves, and ocean circulation` |
| `dependencies` | `("relief_bathymetry",)` |
| `required_outputs` | `sea_level_model` (dict), `marine_regions`, `continental_shelves`, `ocean_current_systems`, `ocean_current_transport_edges` (lists) |
| `validator_domains` | `sea_level`, `ocean_circulation`, `coastal_marine_landmass` |
| `temporal_class` | `native_equilibrium_recomputed_per_coupled_stage` |
| `evidence_class` | `volume_replay_with_diagnostic_circulation` |

---

## The volume-constrained sea-level solver

### What is conserved

The conserved quantity is **connected-ocean water volume**, expressed entirely in cell columns:

```
ocean_volume_km3 = sum over selected cells of ( area_km2 * water_depth_m / 1000 )
```

with `water_depth_m = -elevation_m` after the datum shift (`cpp/src/engine/ocean.cpp:270`). The target is `params.ocean_water_inventory_km3`, exposed as `planet.ocean_water_inventory_km3` (default `1_338_000_000.0` km³, bounds `[0, 10_000_000_000]`, `src/magic_geo/config.py:215-220`; the same bound is re-checked natively at `cpp/src/engine/core.cpp:344-348`). The declared bases are `area_basis: native_cell_area_km2` and `volume_basis: sum_native_cell_area_times_water_depth` (`cpp/src/engine/process_serialization.cpp:3408-3409`).

Nothing about area or cell count is conserved. Ocean *area* is an outcome, never an input.

### The algorithm, step by step

`apply_sea_level` (`cpp/src/engine/ocean.cpp:5-275`):

| Step | Lines | Behaviour |
|------|-------|-----------|
| 1 | `11-18` | Build `order`: all cell indices sorted ascending by `elevation_m`, ties broken by ascending cell id. Deterministic. |
| 2 | `20-28` | Sum `max(0, area_km2)` over all cells. If the total is not positive, throw `sea-level selection requires positive cell areas`. |
| 3 | `29-47` | **Zero-inventory branch.** If `ocean_water_inventory_km3 <= 0`, sea level is `nextafter(lowest elevation, -inf)`; every cell is datum-shifted by `-sea_level` with context `"zero-ocean sea-level datum"`; `is_water=false`, `water_depth_m=0`, `water_body=0`, `is_lake=false` for all. The function returns that sea level. No cell is marine. |
| 4 | `49-91` | Initialise a union-find over cells with per-component `area_km2`, `elevation * area` moment, size, and minimum member id. Merge is union-by-size with a `root_b < root_a` deterministic tiebreak; find uses full path compression. |
| 5 | `126-141` | Sweep `order` in **elevation ties groups**. All cells at the same `elevation_m` are activated together, then merged with any already-active neighbour. |
| 6 | `142-156` | Track `largest_component_root` by component area, tie-broken by smaller `component_min_id`. |
| 7 | `157-161` | For the current largest component, solve the interval's exact sea level analytically: `solved_sea_level = (target_volume_km3 * 1000 + sum(elev*area)) / sum(area)`. |
| 8 | `165-169` | Always consider `interval_lower = nextafter(elevation, +inf)` as a candidate. |
| 9 | `170-181` | If `solved_sea_level` lies in `[interval_lower, next_elevation)`, consider it and set `exact_solution_found`. Otherwise consider `interval_upper = nextafter(next_elevation, elevation)` when finite; when there is no next elevation and `solved_sea_level >= interval_lower`, take the solved value and set `exact_solution_found`. |
| 10 | `102-125` | `consider_candidate` computes the candidate volume `max(0, (area*sea_level - elev_area)/1000)` and its absolute error against the target, keeping the smallest error, tie-broken by the *lower* sea level. It also records `best_connected_area_km2` and `best_flood_elevation`. |
| 11 | `183-185` | The sweep stops as soon as an exact in-interval solution is found. |
| 12 | `188-231` | **Reconstruction.** Mark `below_level[i] = elevation_m <= best_flood_elevation`, BFS all components of that mask, and select the component with the largest area, tie-broken by smaller minimum id. |
| 13 | `232-237` | **Guard.** If the reconstructed component's area differs from `best_connected_area_km2` by more than `max(1e-6, best_connected_area_km2 * 1e-12)`, throw `connectivity-constrained sea-level reconstruction mismatch`. |
| 14 | `244-273` | Apply. Every cell is datum-shifted by `-sea_level` with context `"sea-level datum"`; `is_water` is set from the selected component only; `water_depth_m = is_water ? -elevation_m : 0`; `water_body = is_water ? 1 : 0`; `is_lake = false` for all. |
| 15 | `239` / `274` | The chosen `best_sea_level` is returned to the caller (accumulated into `HydrologyStabilizationResult::sea_level_adjustment_m`). |

The datum shift itself never mutates all three interface fields independently. It goes through `shift_sediment_interface_datum` (`cpp/src/engine/sediment_partition.cpp:123-153`), which validates the interface, adds the offset to `bedrock_surface_elevation_m` in `long double`, re-derives `elevation_m = bedrock_surface_elevation_m + sediment_thickness_m`, re-validates, and only then commits. This preserves the canonical interface authority contract described in [Sediment, Routing and Stratigraphy](sediment-and-stratigraphy.md).

### The strict-depth tie repair

The flood interval selects cells *strictly* below `best_sea_level`, but the two canonical operands (`bedrock_surface_elevation_m` and `sediment_thickness_m`) round independently and can cancel back to signed zero when the datum is composed. `cpp/src/engine/ocean.cpp:251-269` handles this explicitly: when a selected-ocean cell would end up with `elevation_m >= 0`, only the **bedrock operand** is moved to `nextafter(-sediment_thickness_m, -inf)`, `elevation_m` is recomposed, and `validate_sediment_interface` is re-run with context `"sea-level selected-ocean strict-depth tie"`. The in-source comment states the intent: preserve the discrete wet decision "without a finite empirical depth adjustment".

### Determinism properties

- Sort order, union-by-size tiebreak, largest-component tiebreak and candidate tiebreak are all total orders on cell id or on the value itself. There is no RNG in the solver.
- `elevation_m` and `water_depth_m` are serialized with `roundtrip_num` (`cpp/src/engine/entity_serialization.cpp:185-186`), precisely because they jointly determine the discrete ocean mask and fixed-format rounding could collapse a one-ULP-below-sea-level cell to signed zero and make the mask unreplayable. They are two of the six round-trip cell fields; the other four are `crust_age_ma`, `crust_thickness_km`, `crust_density` and `thermal_subsidence_target_m`. Note that the third canonical operand, `bedrock_surface_elevation_m`, is *not* round-tripped: it is written at `max(10, output.float_precision)` decimals (`entity_serialization.cpp:117, 180-181`), so an exact replay of the datum shift from the serialized document is not available — only the mask it produced is.

---

## What `ocean_fraction_target` actually does

`planet.ocean_fraction_target` (default `0.70`, bounds `[0, 0.95]`, `src/magic_geo/config.py:209-214`; native bound re-checked at `cpp/src/engine/core.cpp:340-341`; default mirrored in `PLANET_PARAMETER_DEFAULTS` at `src/magic_geo/planet_parameters.py:19`) **does not appear anywhere in `apply_sea_level`**. Beyond config marshalling (`cpp/src/c_api.cpp:25`) and parameter validation (`cpp/src/engine/core.cpp:253, 340-341`), the whole engine reads it in only three places:

| Reader | Source | Use |
|--------|--------|-----|
| `serialize_world` planet snapshot | `cpp/src/engine/world_serialization.cpp:34` | echoed verbatim into `planet_parameters` at `roundtrip_num` precision |
| `sea_level_model_json` | `cpp/src/engine/process_serialization.cpp:3353-3355`, `3374-3375`, `3410-3416` | computes `target_ocean_cell_count` and `target_ocean_area_km2` as **diagnostic references**, using `clamp(target, 0.0, 0.98)` |
| `summary_json` | `cpp/src/engine/summary.cpp:1624` | echoed as `summary.target_ocean_fraction` |

So `ocean_fraction_target` is a **diagnostic area reference**: it lets a consumer compute how far the volume-driven solution landed from a desired coverage, and nothing more. `docs/configuration_reference.md:82` states it directly: "Diagnostic area reference only. It does **not** drive the sea-level solve." The repository `README.md:352` repeats it: "`ocean_fraction_target` remains a diagnostic area reference rather than the sea-level control."

The resulting diagnostics — `ocean_area_target_error_km2`, `ocean_area_target_error_fraction`, `ocean_area_target_error_cell_count`, `ocean_area_target_error_cell_fraction` — are *residuals against an aspiration*, not errors of the solver. A large value means the configured water volume and the generated hypsometry disagree with the requested coverage; it does not mean the solve failed.

Note the clamp asymmetry: config validation bounds the fraction to `[0, 0.95]`, but `sea_level_model_json` re-clamps to `[0, 0.98]` before computing the target area. Both bounds are in the source; the tighter one is what a validated config can actually produce.

---

## The `sea_level_model` contract block

Emitted by `sea_level_model_json` (`cpp/src/engine/process_serialization.cpp:3348-3465`) and placed at top level by `cpp/src/engine/world_serialization.cpp:187-188`. Every numeric field except `below_sea_level_land_area_km2` uses `std::numeric_limits<double>::max_digits10`.

| Key | Type | Meaning | Line |
|---|---|---|---|
| `model_type` | string | `volume_constrained_connectivity_ocean_flood_v3` | 3405 |
| `selection_rule` | string | `solve_largest_connected_ocean_cell_column_volume_across_elevation_intervals` | 3406 |
| `area_basis` | string | `native_cell_area_km2` | 3408 |
| `volume_basis` | string | `sum_native_cell_area_times_water_depth` | 3409 |
| `ocean_fraction_target` | double | configured diagnostic fraction, unclamped echo | 3410 |
| `surface_area_km2` | double | sum of `max(0, area_km2)` over all cells | 3417 |
| `target_ocean_area_km2` | double | `clamp(target, 0, 0.98) * surface_area_km2` — diagnostic | 3419 |
| `selected_ocean_area_km2` | double | area of the selected marine component | 3421 |
| `ocean_water_inventory_km3` | double | the conserved target | 3423 |
| `selected_ocean_volume_km3` | double | reconstructed `sum(depth * area / 1000)` over marine cells | 3425 |
| `ocean_water_inventory_error_km3` | double | `abs(selected - target)` | 3427 |
| `ocean_water_inventory_error_fraction` | double | relative error; `1.0` if target is zero and volume is positive, else `0.0` | 3430 |
| `target_ocean_cell_count` | int | `llround(clamp(target,0,0.98) * cell_count)` — diagnostic | 3436 |
| `selected_ocean_cell_count` | int | marine cell count | 3437 |
| `selected_ocean_fraction` | double | `selected_ocean_area_km2 / surface_area_km2` | 3438 |
| `selected_ocean_cell_fraction` | double | `selected_ocean_cell_count / cell_count` | 3441 |
| `ocean_area_target_error_cell_count` | int | `abs(selected - target)` cell counts | 3444 |
| `ocean_area_target_error_fraction` | double | `abs(selected_area - target_area) / surface_area` | 3445 |
| `ocean_area_target_error_km2` | double | `abs(selected_area - target_area)` | 3448 |
| `ocean_area_target_error_cell_fraction` | double | `abs(selected_cells - target_cells) / cell_count` | 3451 |
| `connected_ocean_component_count` | int | independently recounted by BFS over `is_water` | 3454 (BFS at 3377-3401) |
| `below_sea_level_land_cell_count` | int | cells with `!is_water && elevation_m < 0` | 3455 |
| `below_sea_level_land_area_km2` | double | their total area — the only field at `params.float_precision` | 3456 |
| `ocean_connectivity_enforced` | bool | literal `true` | 3458 |
| `disconnected_below_sea_level_cells_remain_land` | bool | literal `true` | 3459 |
| `sea_level_recomputed_each_erosion_stage` | bool | literal `true` | 3460 |
| `model_limitation` | string | `cell_column_volume_without_subcell_bathymetry_straits_or_exact_coast_polygons` | 3461 |

`below_sea_level_land_cell_count` is the honest counterpart of `disconnected_below_sea_level_cells_remain_land`: negative-elevation cells that are not graph-connected to the selected component stay dry and are handed to the Priority-Flood depression policy, where they may become dry closed basins, fresh lakes (`water_body = 4`) or saline basins (`water_body = 5`) — see [Hydrology, Rivers and Lakes](hydrology-and-rivers.md).

---

## Marine connectivity classification

`label_marine_water_bodies` (`cpp/src/engine/ocean.cpp:277-321`) runs immediately after `apply_sea_level`:

1. BFS-label all connected components of `is_water` cells (`ocean.cpp:282-303`).
2. Find the component with the largest **cell count** (`ocean.cpp:304-311`). Note this is a count criterion, unlike the *area* criterion used inside `apply_sea_level`.
3. Assign (`ocean.cpp:312-320`):

| Condition | `water_body` | `water_body_type` |
|---|---|---|
| `!is_water` | `0` | `land` |
| in largest component and `water_depth_m >= 220.0` | `1` | `ocean` |
| in largest component and `water_depth_m < 220.0` | `2` | `continental_shelf` |
| in any other water component | `3` | `inland_sea` |

The full enum is `WATER_BODY_NAMES` (`cpp/src/engine/schema_names.hpp:34-36`):

| Index | Name | Assigned by |
|---|---|---|
| 0 | `land` | `ocean.cpp:314`, `hydrology.cpp:393`, `hydrology.cpp:599` |
| 1 | `ocean` | `ocean.cpp:271` (initial), `ocean.cpp:316` |
| 2 | `continental_shelf` | `ocean.cpp:316` |
| 3 | `inland_sea` | `ocean.cpp:318` |
| 4 | `fresh_lake` | `hydrology.cpp:642`, `647`; `environment.cpp:342` |
| 5 | `saline_basin` | `hydrology.cpp:633`, `655`; `environment.cpp:342` |

### The world ocean versus enclosed seas — an honest structural note

`is_water` is assigned in exactly one place in the whole engine: `cpp/src/engine/ocean.cpp:41` (zero-inventory, all false) and `cpp/src/engine/ocean.cpp:250` (from the single selected component). Because `apply_sea_level` marks **exactly one connected component** as water, the BFS in `label_marine_water_bodies` always finds exactly one component, and therefore the `inland_sea` branch at `ocean.cpp:318` is unreachable in a world produced by the current pipeline. The `single_connected_ocean` validator asserts this same property from the other side: it requires the marine mask to be the largest connected below-sea-level component and requires `connected_ocean_component_count == 1` (`src/magic_geo/geo_validation.py:1379-1443`).

Consequences that a consumer must not misread:

- `water_body_type == "inland_sea"` is a schema-reachable value that the current native model does not produce. Downstream Python treats it defensively — `MARINE_WATER_TYPES = {"ocean", "continental_shelf", "inland_sea"}` appears in `sea_level_diagnostics.py:8`, `ocean_circulation.py:10`, `reef_diagnostics.py:8`, `port_sites.py:7` and `navigability_diagnostics.py:7` — but the branch is dead for native-generated worlds.
- Since the marine cell set equals the `is_water` set exactly, the Python `marine_regions` partition (connected components of marine cells) yields exactly **one** region for any world with a positive water inventory. `summary.marine_region_count` is therefore `1` (or `0`), `open_ocean_marine_region_count` is `1` whenever any deep cell exists, and `inland_sea_marine_region_count` is `0`.
- What the model genuinely distinguishes is **connected marine water versus disconnected below-sea-level land**, not "world ocean versus enclosed sea". A basin that would be an enclosed sea on Earth appears here either as part of the one ocean (if a cell-centre path exists) or as a dry/lacustrine depression (if it does not). There is no third category.
- `continental_shelf` is assigned by a pure depth threshold (`water_depth_m < 220.0` m), not by crust type, margin geometry or sediment. A deep abyssal cell adjacent to a continent is `ocean`; a shallow cell in the middle of an ocean basin is `continental_shelf`.

---

## How bathymetry is represented

There is no bathymetry field. Depth is a derived scalar of the single per-cell elevation:

```
elevation_m       = bedrock_surface_elevation_m + sediment_thickness_m     (canonical interface)
water_depth_m     = is_water ? -elevation_m : 0.0                          (ocean.cpp:270)
ocean_volume_km3  = sum( area_km2 * water_depth_m / 1000 )                 (process_serialization.cpp:3367-3368)
```

| Property | Representation | Source |
|---|---|---|
| Sea surface | Implicit. After the datum shift, sea level *is* elevation zero everywhere. | `ocean.cpp:245-249` |
| Sea floor | One `elevation_m` per control volume. No sub-cell relief, no slope, no along-cell profile. | `entity_serialization.cpp:185` |
| Depth | `-elevation_m`, exact by construction, validated to a `1e-6` residual. | `ocean.cpp:270`; `geo_validation.py:1341-1346` |
| Shelf | A depth threshold (`< 220 m`) on the single value. | `ocean.cpp:316` |
| Trench | A `landform` label, not a depth field: `boundary_convergent > 0.38 && water_depth_m > 700.0` ⇒ `landform = 9` (`trench`). | `environment.cpp:433-434` |
| Fjord | `landform = 16` when a glacier neighbour exists, `water_depth_m < 1200.0` and the cell is shelf or inland sea. | `environment.cpp:431-432` |
| Straits | Not represented as geometry. Only as a per-cell chokepoint diagnostic (see below). | `sea_level_diagnostics.py:245-297` |

### The single-elevation-per-cell limitation, stated honestly

The engine names this limitation itself in the serialized document: `sea_level_model.model_limitation = "cell_column_volume_without_subcell_bathymetry_straits_or_exact_coast_polygons"` (`cpp/src/engine/process_serialization.cpp:3461-3462`).

`README.md:352` expands it and is worth carrying forward without softening:

- At 4,096 cells an Earth-sized cell is roughly 400 km across, so lowering an entire margin cell to manufacture shelf area "would replace both its land and deep-ocean portions with one elevation and is not a defensible correction."
- The required next architecture is named: "conservative subcell hypsometry: retain an area–elevation distribution and margin shelf–slope–rise profile within each coarse cell, flood fractions rather than cell centers, and expose subcell strait connectivity and volume."
- The default inventory `1,338,000,000 km³` follows the USGS estimate for oceans, seas and bays (NOAA independently reports about `1,335,000,000 km³`). It is explicitly "an ocean allocation, not a partition of total planetary water among ocean, ice, groundwater, lakes, and atmosphere."

Practical consequences at generation resolution:

- A real narrow strait cannot exist unless a *cell-centre* path exists across it. Connectivity is graph connectivity on the neighbour stencil, nothing finer.
- Shelf area is whatever fraction of the marine mask happens to fall under 220 m at the solved datum. It cannot be tuned toward an Earth-like shelf fraction without falsifying the elevation of the whole cell.
- Coastlines are cell boundaries. There are no exact coast polygons; the closest available object is the reconstructed spherical boundary ring produced by `cell_geometry` (see [Mesh and Geometry](mesh-and-geometry.md)).

---

## Landmasses, marine regions, shelves and chokepoints

`enrich_world_with_sea_level_diagnostics` (`src/magic_geo/sea_level_diagnostics.py:300-392`) is a pure post-hoc partition diagnostic. It first resets five cell fields on every cell (`sea_level_diagnostics.py:304-309`), then builds four families.

### Landmasses

Connected components of `!is_water` cells, seeded in ascending cell id (`sea_level_diagnostics.py:313-323`). Classification by total area (`_landmass_class`, `sea_level_diagnostics.py:85-92`):

| Threshold | `island_class` |
|---|---|
| `area_km2 >= 5_000_000` | `continent` |
| `area_km2 >= 500_000` | `large_island` |
| `area_km2 >= 50_000` | `island` |
| otherwise | `islet` |

Water cells receive `island_class = "water"` (`sea_level_diagnostics.py:309`).

`landmasses[]` record fields (`_landmass_record`, `sea_level_diagnostics.py:95-128`):

| Field | Type | Derivation |
|---|---|---|
| `id` | int | component index |
| `cell_ids` | int[] | sorted member ids |
| `cell_count` | int | `len(component)` |
| `area_km2` | float | sum of `max(0, area_km2)`, rounded to 6 dp |
| `centroid_lat_deg`, `centroid_lon_deg` | float | area-weighted 3-D spherical centroid, 6 dp (`_spherical_centroid`, line 60) |
| `mean_elevation_m` | float | mean `elevation_m` |
| `max_elevation_m` | float | max `elevation_m` |
| `coastal_cell_count` | int | members with ≥1 non-land neighbour |
| `shoreline_neighbor_edge_count` | int | total land→water neighbour edges |
| `island_class` | string | see table above |
| `dominant_biome` | string | modal `biome` (`_dominant_name`, line 27) |
| `dominant_lithology` | string | modal `lithology` |

### Marine regions

Connected components of cells whose `water_body_type` is in `MARINE_WATER_TYPES` (`sea_level_diagnostics.py:327-335`). As established above, this yields exactly one region for any world with water.

`marine_regions[]` record fields (`_marine_region_record`, line 131):

| Field | Type | Derivation |
|---|---|---|
| `id`, `cell_ids`, `cell_count`, `area_km2` | — | as for landmasses |
| `centroid_lat_deg`, `centroid_lon_deg` | float | area-weighted spherical centroid |
| `region_class` | string | `open_ocean` if any member is `ocean`; else `inland_sea` if any member is `inland_sea`; else `continental_shelf` (line 154) |
| `dominant_water_body_type` | string | `Counter.most_common(1)` over `water_body_type` |
| `water_body_counts` | object | sorted histogram |
| `mean_water_depth_m`, `max_water_depth_m` | float | over members |
| `coastal_cell_count` | int | members with ≥1 land neighbour |
| `adjacent_landmass_ids` | int[] | sorted `landmass_id` of land neighbours |
| `connected_to_open_ocean` | bool | `water_body_counts["ocean"] > 0` |

### Continental shelves

Connected components of cells with `water_body_type == "continental_shelf"` exactly (`sea_level_diagnostics.py:339-352`). Unlike marine regions, there can be many.

`continental_shelves[]` record fields (`_continental_shelf_record`, line 174):

| Field | Type | Derivation |
|---|---|---|
| `id`, `cell_ids`, `cell_count`, `area_km2` | — | standard |
| `centroid_lat_deg`, `centroid_lon_deg` | float | area-weighted spherical centroid |
| `mean_water_depth_m`, `max_water_depth_m` | float | over members |
| `mean_sediment_thickness_m` | float | mean `sediment_thickness_m` |
| `coastal_cell_count` | int | members with ≥1 land neighbour |
| `shelf_break_cell_count` | int | members with ≥1 marine non-shelf neighbour |
| `shoreline_neighbor_edge_count` | int | shelf→land edges |
| `shelf_break_neighbor_edge_count` | int | shelf→(marine, non-shelf) edges |
| `open_ocean_neighbor_edge_count` | int | subset of the above where the neighbour is `ocean` |
| `inland_sea_neighbor_edge_count` | int | subset where the neighbour is `inland_sea` (structurally zero, see above) |
| `adjacent_landmass_ids` | int[] | sorted |
| `marine_region_ids` | int[] | sorted; the member cells' own region ids **plus** the region ids of their marine neighbours (`sea_level_diagnostics.py:192-194, 206-210`) |

### Marine chokepoints

`_marine_chokepoints` (`src/magic_geo/sea_level_diagnostics.py:245-297`) scans marine cells in ascending id and applies these gates:

| Gate | Condition | Line |
|---|---|---|
| minimum land contact | `len(land_neighbors) >= 2` | 256 |
| minimum marine continuity | `len(marine_neighbors) >= 2` | 256 |
| constriction | `constriction = len(land_neighbors) / len(neighbors)` | 258 |
| acceptance | keep if `len(adjacent_landmass_ids) >= 2` **or** `constriction >= 0.5` | 266 |
| typing | `strait` if ≥2 distinct adjacent landmasses, else `marine_narrows` | 275 |

`marine_chokepoints[]` record fields:

| Field | Type | Derivation |
|---|---|---|
| `id` | int | insertion index; also written back to `cell["marine_chokepoint_id"]` (line 278) |
| `cell_id` | int | the marine cell |
| `type` | string | `strait` \| `marine_narrows` |
| `marine_region_id` | int | the cell's region |
| `water_body_type` | string | the cell's type |
| `lat_deg`, `lon_deg` | float | cell centre, 6 dp |
| `water_depth_m` | float | 6 dp |
| `land_neighbor_edge_count` | int | count of land neighbours |
| `marine_neighbor_edge_count` | int | count of marine neighbours |
| `constriction_index` | float | `land_neighbors / neighbors`, 6 dp |
| `width_proxy_km` | float | `mean_neighbor_edge_length_km / len(land_neighbors)`, floored at 0, 6 dp — requires `cell_geometry` to have run |
| `adjacent_landmass_ids` | int[] | sorted, `-1` filtered |
| `adjacent_marine_region_ids` | int[] | sorted, includes the cell itself |

`width_proxy_km` is a name that must be read literally: it is a mesh-edge-length proxy, not a measured strait width. At 4,096 cells the mesh edge is on the order of hundreds of kilometres.

---

## Ocean circulation: the native current field

The current vector field is produced inside `compute_climate`, not by a dedicated ocean stage. `ocean_current_components(lat, lon, day_length_hours)` (`cpp/src/engine/climate.cpp:228-249`) is a **prescribed latitude-banded gyre pattern**, not a solved circulation:

| Band (`|lat|` in degrees) | `east` before rotation | `north` | Line |
|---|---|---|---|
| `< 12` | `-1.00` | `0.16 * sin(lon)` | 233-235 |
| `< 35` | `-0.72` | `(+0.42 north / -0.42 south) * sin(lon)` | 236-238 |
| `< 62` | `+0.86` | `(-0.34 north / +0.34 south) * cos(lon)` | 239-241 |
| `>= 62` | `-0.42` | `(-0.22 north / +0.22 south)` | 242-245 |

Then `rotation = clamp(24 / max(1, day_length_hours), 0.45, 2.4)`, `east *= sqrt(rotation)` (lines 230, 246), and the pair is **normalised to unit length** (lines 247-248).

The gyre closure comes entirely from the `sin(lon)` / `cos(lon)` meridional terms alternating sign with hemisphere: an equatorward-then-westward tropical limb, a poleward subtropical limb, an eastward mid-latitude limb with an equatorward meridional component, and a westward polar limb. There is no basin geometry, no coastline, no Sverdrup balance and no continuity constraint. Land cells are not excluded from the field.

The field is then attenuated by distance from water (`cpp/src/engine/climate.cpp:365-379`):

```
dist     = ocean_distance(cells)          // BFS hop count to the nearest is_water cell, ocean.cpp:323
oceanity = exp(-dist / 7.5)               // climate.cpp:324
ocean_current_east  = current.first  * oceanity
ocean_current_north = current.second * oceanity
```

| Cell field | Formula | Line |
|---|---|---|
| `ocean_current_east` | unit east component × `oceanity` | 366 |
| `ocean_current_north` | unit north component × `oceanity` | 367 |
| `ocean_current_temperature_c` | `oceanity * clamp(3.8 * poleward_current + 1.2 * cos(lat) * sin(lon), -4.5, 4.5)` where `poleward_current = lat >= 0 ? north : -north` | 368-374 |
| `ocean_current_moisture_factor` | `clamp(1 + oceanity * (0.045 * max(0, T) - 0.035 * max(0, -T)), 0.72, 1.28)` | 375-379 |

**A magnitude caveat that matters.** `ocean_distance` sets `distance = 0` for every `is_water` cell (`cpp/src/engine/ocean.cpp:327-331`), so `oceanity == 1` on the entire marine domain. The native pair is already unit-normalised (`climate.cpp:247-248`), so in engine memory `sqrt(east² + north²) == 1.0` (to within a ULP) for every marine cell. The Python `ocean_current_speed_index` recomputes that magnitude (`src/magic_geo/ocean_circulation.py:247, 254`) — but from the *serialized* components, which are written with `std::fixed` at `output.float_precision` decimals (default `4`; `entity_serialization.cpp:203-204`, `core.cpp:168-177`). The index is therefore **1.0 only up to that component rounding — typically within about `1e-4` of `1.0`, and exactly `1.0` only when both components happen to serialize exactly.** Either way it **carries direction only, never speed**: there is no spatial contrast in it across the marine domain. Contrast exists only on land, where `oceanity` decays (a coastal land cell at one hop has `exp(-1/7.5) ≈ 0.87517`). `summary.mean_ocean_current_strength` (`cpp/src/engine/summary.cpp:2063`) is computed natively from unrounded values and averages over **all** cells, so it sits well below 1 and is dominated by the land decay, not by ocean dynamics.

---

## Ocean circulation: the transport-graph enricher

`enrich_world_with_ocean_circulation` (`src/magic_geo/ocean_circulation.py:221-382`) turns the native vector field into a directed transport graph, per-cell indices, and grouped systems. Module constants (`ocean_circulation.py:10-14`):

| Constant | Value |
|---|---|
| `MARINE_WATER_TYPES` | `{"ocean", "continental_shelf", "inland_sea"}` |
| `WARM_CURRENT_THRESHOLD_C` | `0.5` |
| `COLD_CURRENT_THRESHOLD_C` | `-0.5` |
| `MERIDIONAL_CURRENT_THRESHOLD` | `0.08` |
| `HIGH_UPWELLING_THRESHOLD` | `0.55` |

### Per-cell pass 1 — direction, heat, transport target

Every cell (marine or not) is first reset to the `non_marine` defaults (`ocean_circulation.py:231-241`); non-marine cells keep them. For marine cells (`ocean_circulation.py:245-262`):

| Field | Formula | Line |
|---|---|---|
| `ocean_current_speed_index` | `sqrt(east² + north²)` over the serialized components — `1.0` up to component rounding, see caveat above | 247, 254 |
| `ocean_current_poleward_index` | `clamp((north / max(1e-9, speed)) * hemisphere_sign, -1, 1)`, `hemisphere_sign = +1` for `lat >= 0` else `-1` | 248-249, 255 |
| `ocean_heat_transport_index` | `clamp((ocean_current_temperature_c / 4.5) * poleward, -1, 1)` | 251, 256 |
| `ocean_current_transport_alignment` | best neighbour alignment, clamped to `[0,1]`; `0.0` if no positive-alignment marine neighbour | 252, 257 |
| `ocean_current_transport_target_cell_id` | best-aligned marine neighbour id, or `-1` | 252, 258 |
| `ocean_current_transport_distance_km` | great-circle distance to the target using `planet_radius_km(world)`, else `0.0` | 252, 259 |
| `ocean_current_regime` | `f"{thermal}_{direction}_current"` | 260 |

`_transport_target` (`ocean_circulation.py:60-100`) builds the local east/north tangent basis at the cell, forms the 3-D current direction, projects each **marine** neighbour onto the tangent plane, and keeps the neighbour with the highest dot product; ties within `1e-12` prefer the lower neighbour id. If the best alignment is `<= 0`, the cell is a transport terminal and returns `(-1, 0.0, 0.0)`.

`_regime` (`ocean_circulation.py:103-116`) composes two independent labels:

| Thermal part | Condition |
|---|---|
| `warm` | `ocean_current_temperature_c >= 0.5` |
| `cold` | `<= -0.5` |
| `neutral` | otherwise |

| Direction part | Condition |
|---|---|
| `poleward` | `ocean_current_poleward_index >= 0.08` |
| `equatorward` | `<= -0.08` |
| `zonal` | otherwise |

The nine products (`warm_poleward_current`, `cold_zonal_current`, …) plus `non_marine` are the full value set of `ocean_current_regime`.

### Per-cell pass 2 — convergence and upwelling

Second loop over marine cells (`ocean_circulation.py:264-293`):

| Field | Formula | Line |
|---|---|---|
| `ocean_current_convergence_index` | `clamp((incoming_edge_count - outgoing) / max(1, marine_neighbor_count), -1, 1)`, where `outgoing ∈ {0,1}` | 270-275, 292 |
| `ocean_upwelling_index` (coastal cell — has ≥1 non-water neighbour) | `clamp(coldness*0.32 + equatorward*0.24 + divergence*0.20 + wind_divergence*0.12 + shelf*0.12)` | 289 |
| `ocean_upwelling_index` (open cell) | `clamp(equatorial*0.24 + divergence*0.28 + coldness*0.14 + equatorward*0.10)` | 291 |

with the ingredient terms (`ocean_circulation.py:282-287`):

| Term | Definition |
|---|---|
| `coldness` | `clamp(-ocean_current_temperature_c / 3.0)` |
| `equatorward` | `clamp(-ocean_current_poleward_index)` |
| `divergence` | `clamp(-ocean_current_convergence_index)` |
| `wind_divergence` | `clamp(wind_divergence_index)` — the native atmospheric field |
| `shelf` | `1.0` if `water_body_type == "continental_shelf"` else `0.0` |
| `equatorial` | `clamp(1 - abs(lat_deg) / 18.0)` |

Note the open-ocean branch cannot exceed `0.76`, so `HIGH_UPWELLING_THRESHOLD = 0.55` is reachable only through a coincidence of divergence, coldness and equatorward flow; the coastal branch can reach `1.0`.

### System grouping

`_connected_systems` (`ocean_circulation.py:139-165`) flood-fills marine cells that share the **identical `ocean_current_regime` string**, seeding from the lowest remaining id. Each component becomes one `ocean_current_systems[]` record and stamps `ocean_current_system_id` on its cells (`ocean_circulation.py:295-300`).

`ocean_current_systems[]` fields (`_system_record`, `ocean_circulation.py:168-218`), all floats rounded to 6 dp:

| Field | Derivation |
|---|---|
| `id` | component index |
| `system_class` | the regime of the component's first cell |
| `hemisphere` | `northern` if every cell has `lat_deg > 5`; `southern` if every cell has `lat_deg < -5`; else `cross_equatorial` |
| `cell_ids`, `cell_count`, `area_km2` | membership and summed area |
| `centroid_lat_deg`, `centroid_lon_deg` | area-weighted spherical centroid |
| `marine_region_ids` | sorted distinct non-negative region ids |
| `water_body_type_counts`, `dominant_water_body_type` | sorted histogram; mode by `(-count, name)` |
| `mean_current_east`, `mean_current_north` | mean native components |
| `mean_current_speed_index` | mean speed index (`1.0` up to component rounding, see caveat) |
| `mean_current_temperature_c`, `mean_current_moisture_factor` | mean native fields (`moisture_factor` defaults to `1.0`) |
| `mean_poleward_transport_index`, `mean_heat_transport_index` | means |
| `mean_transport_alignment`, `mean_convergence_index`, `mean_upwelling_index` | means |
| `transport_edge_count` | members with `target_cell_id >= 0` |
| `internal_transport_edge_count` | targets inside the system |
| `external_transport_edge_count` | targets outside the system |
| `terminal_cell_count` | members with `target_cell_id < 0` |
| `coastal_cell_count` | members with ≥1 non-water neighbour |
| `continental_shelf_cell_count` | from the water-body histogram |
| `warm_current_cell_count`, `cold_current_cell_count` | against the ±0.5 °C thresholds |
| `poleward_current_cell_count`, `equatorward_current_cell_count` | against the ±0.08 thresholds |
| `high_upwelling_cell_count` | `ocean_upwelling_index >= 0.55` |

### Transport edges

`ocean_current_transport_edges[]` (`ocean_circulation.py:302-331`), emitted in ascending source cell id, one per marine cell with a valid target:

| Field | Derivation |
|---|---|
| `id` | insertion index |
| `source_cell_id`, `target_cell_id` | the directed pair; the target is always a mesh neighbour |
| `source_system_id`, `target_system_id` | current-system ids |
| `source_marine_region_id`, `target_marine_region_id` | marine-region ids |
| `great_circle_distance_km` | mirrors `ocean_current_transport_distance_km` |
| `alignment` | mirrors `ocean_current_transport_alignment` |
| `current_speed_index`, `current_temperature_c` | source-cell values |
| `poleward_transport_index`, `heat_transport_index`, `upwelling_index` | source-cell values |
| `crosses_system_boundary` | `source_system_id != target_system_id` |
| `crosses_marine_region_boundary` | `source_marine_region_id != target_marine_region_id` |

This is a **one-outgoing-edge-per-cell functional graph**, not a mass-conserving flux field. Nothing is transported: no tracer, no volume, no heat quantity crosses the edge. The edge is an alignment-selected adjacency annotated with the source cell's own scalar diagnostics.

---

## Heat transport and the climate coupling

The influence of currents on climate is entirely native and entirely local — it flows through `ocean_current_temperature_c` and `ocean_current_moisture_factor`, both computed at the cell from the prescribed pattern. The Python `ocean_heat_transport_index` feeds **nothing**; it is a reported diagnostic only.

| Coupling | Mechanism | Source |
|---|---|---|
| Direct temperature | `current_temp` is added into the per-cell local adjustment alongside the elevation lapse and the marine offset | `cpp/src/engine/climate.cpp:280-284` (pre-pass), `407` (applied) |
| Area centering | The mean of that local adjustment over cell area is subtracted globally so currents redistribute rather than inject heat; `climate_model.local_temperature_centering_scope = "elevation_lapse_ocean_current"` | `cpp/src/engine/climate.cpp:268-291`; `cpp/src/engine/process_serialization.cpp:439-442` |
| Marine offset | `CLIMATE_MARINE_ANNUAL_TEMPERATURE_OFFSET_C` is **`0.0`** — water cells receive no annual temperature bonus of their own | `cpp/src/engine/constants.hpp:10` |
| Cold-current coastal drying | `cold_current_drying_index = clamp(-current_temp / 4.5, 0, 1)` scales the subtropical drying term by up to `1.15`: `subtropical_drying_factor = clamp(1 - subtropical_drying_strength * subtropic * (1 + 0.15 * cold_current_drying_index), CLIMATE_SUBTROPICAL_DRYING_MIN_FACTOR, 1)`, and that factor multiplies annual precipitation | `cpp/src/engine/climate.cpp:452-458`, applied at `463` |
| Warm-current moisture | `ocean_current_moisture_factor` multiplies precipitation together with the orographic and rain-shadow factors | `cpp/src/engine/climate.cpp:461` |
| Marine evaporation | `ocean_current_moisture_factor` contributes `90.0 *` factor to the water-cell evaporation term | `cpp/src/engine/climate.cpp:487` |

Two of the six `climate_realism_checks` score exactly this coupling — cold-current coastal drying and warm-current moderation (`src/magic_geo/climate_realism.py`), see [Climate and Atmosphere](climate-and-atmosphere.md).

The honest framing: the model produces the *sign and rough magnitude* of a current thermal anomaly as a function of latitude, longitude and distance from water. It does not advect heat, does not conserve energy across the current field, and `climate_model.model_limitation` remains `equilibrium_diagnostic_climate_without_mass_conserving_three_dimensional_atmosphere` with `mass_conserving_atmosphere: false` and `transient_climate_resolved: false` (`cpp/src/engine/process_serialization.cpp:443-446`).

---

## Coastal feature generation

`generate_coastal_features(params, cells)` (`cpp/src/engine/environment.cpp:613-651`) runs once, after cryosphere coupling and after `derive_landforms`. Eligibility (`environment.cpp:616-622`):

1. `!cell.is_water`, and
2. `has_ocean_neighbor(cells, cell.id)` — at least one `is_water` neighbour (`environment.cpp:5-12`), and
3. `coastal_edge_length_km > 0`.

So features are **land-side records**: one record per coastal land cell, never per water cell.

### Inputs

| Quantity | Formula | Source |
|---|---|---|
| `length_km` | sum over water neighbours of `neighbor_distance_m / 1000`, where `neighbor_distance_m = max(1, angular_distance * radius_km * 1000)` | `environment.cpp:507-515`; `hydrology.cpp:209-211` |
| `sediment_supply_index` | `clamp(0.20 * clamp(sed/3,0,1) + (is_river ? 0.34 : 0) + (landform ∈ {delta(12), floodplain(11), coastal_plain(14)} ? 0.20 : 0) + Σ_neighbours[(neighbour is_river ? 0.08 : 0) + (neighbour landform ∈ {delta, floodplain} ? 0.07 : 0) + 0.03 * clamp(neighbour sed/3,0,1)], 0, 1)` | `environment.cpp:517-537` |
| `wave_energy_index` | `clamp(0.22 + 0.40 * exposure + 0.24 * |ocean_current| + 0.14 * clamp(boundary_convergent + 0.5 * boundary_transform, 0, 1), 0, 1)` with `exposure = water_neighbour_count / max(1, neighbour_count)` | `environment.cpp:539-554` |
| `longshore_transport_index` | `clamp(0.18 + 0.46 * wave + 0.24 * |ocean_current| + 0.12 * sediment, 0, 1)` | `environment.cpp:577-583` |
| `progradation_index` | `clamp((sediment + (type == delta_lobe ? 0.22 : 0)) / (0.55 + wave), 0, 1)` | `environment.cpp:634` |
| `migration_rate_m_y` | `clamp(base + type adjustment, -2.5, 4.0)` where `base = 1.55*sediment - 1.05*wave + 0.28*longshore`; `+0.62` for `delta_lobe`; `+0.18*sediment - 0.24*wave` for `beach`/`barrier_bar`; `-0.55` for `coastal_cliff` | `environment.cpp:585-595` |

Because a coastal land cell sits one BFS hop from water, its `|ocean_current|` is `exp(-1/7.5) ≈ 0.87517`, so the current term contributes ≈ `0.210` to wave energy and ≈ `0.210` to longshore transport almost uniformly. Wave-energy contrast is therefore driven mostly by `exposure` and the tectonic term.

### Type classification

`coastal_feature_type_for_cell` (`cpp/src/engine/environment.cpp:556-575`), evaluated in this order — first match wins. `relief = local_relief(cells, i)` is `max(0, elevation - mean neighbour elevation)` (`cpp/src/engine/climate.cpp:15-25`).

| Order | Type id / name (`COASTAL_FEATURE_TYPE_NAMES`, `schema_names.hpp:116-118`) | Condition |
|---|---|---|
| 1 | `3` `delta_lobe` | `landform == delta(12)` **or** (`is_river` and `sediment > 0.58` and `elevation_m < 120`) |
| 2 | `4` `tidal_marsh` | (`landform == floodplain(11)` or `biome == wetland(15)`) and `sediment > 0.42` and `wave < 0.55` |
| 3 | `2` `barrier_island` | `sediment > 0.56` and `wave > 0.48` and `elevation_m < 90` |
| 4 | `1` `barrier_bar` | `sediment > 0.30` and `wave > 0.34` and `elevation_m < 260` |
| 5 | `5` `coastal_cliff` | `relief > 650` **or** (`elevation_m > 180` and `wave > 0.62` and `sediment < 0.45`) |
| 6 | `0` `beach` | fallback |

### Shoreline trend

`shoreline_trend_for_feature` (`cpp/src/engine/environment.cpp:597-611`), `SHORELINE_TREND_NAMES` at `schema_names.hpp:119-121`:

| Order | Trend id / name | Condition |
|---|---|---|
| 1 | `4` `delta_switching` | `type == delta_lobe` and `sediment > 0.55` and `migration > 0.45` |
| 2 | `3` `landward_migration` | `type ∈ {barrier_bar, barrier_island}` and `wave > 0.56` and `migration < 0.25` |
| 3 | `1` `prograding` | `migration > 0.34` |
| 4 | `2` `eroding` | `migration < -0.28` **or** (`type == coastal_cliff` and `wave > 0.58`) |
| 5 | `0` `stable` | fallback |

### `coastal_features[]` record

12 fields (`coastal_features_json`, `cpp/src/engine/entity_serialization.cpp:508-531`), all doubles at `params.float_precision`:

| Field | Type |
|---|---|
| `id` | int |
| `cell_id` | int |
| `type` | enum string from `COASTAL_FEATURE_TYPE_NAMES` |
| `shoreline_trend` | enum string from `SHORELINE_TREND_NAMES` |
| `lat_deg`, `lon_deg` | double |
| `length_km` | double |
| `sediment_supply_index` | double `[0,1]` |
| `wave_energy_index` | double `[0,1]` |
| `progradation_index` | double `[0,1]` |
| `migration_rate_m_y` | double `[-2.5, 4.0]` |
| `longshore_transport_index` | double `[0,1]` |

Summary aggregation (`cpp/src/engine/summary.cpp:654-664`, emitted at `1803-1808`): `coastal_bar_feature_count` counts types `barrier_bar` + `barrier_island`; `prograding_coastal_feature_count` counts trends `prograding` + `delta_switching`; `eroding_coastal_feature_count` counts trends `eroding` + `landward_migration`.

There is no wave model, no tidal range, no fetch-limited wave growth and no sediment budget closure at the shoreline. `migration_rate_m_y` is a bounded score with metre-per-year units attached, not an integrated shoreline displacement, and no stage consumes it.

---

## Reef diagnostics

`enrich_world_with_reef_diagnostics` (`src/magic_geo/reef_diagnostics.py:281-432`). Module constants (`reef_diagnostics.py:8-12`):

| Constant | Value |
|---|---|
| `REEF_GROWTH_THRESHOLD` | `0.46` |
| `REEF_THERMAL_MINIMUM_C`, `REEF_THERMAL_MAXIMUM_C` | `4`, `39`; exclusive support bounds for positive growth |
| `VOLCANIC_LANDFORMS` | `{"volcanic_arc", "island_arc", "ridge"}` |
| `REEF_COASTAL_FEATURE_TYPES` | `{"beach", "barrier_bar", "barrier_island", "coastal_cliff"}` (declared; not referenced by the scoring path) |
| `REEF_LANDMASS_CLASSES` | `{"islet", "island", "large_island"}` |

Note `VOLCANIC_LANDFORMS` contains `island_arc` and `ridge`, neither of which is a value in `LANDFORM_NAMES` (`cpp/src/engine/schema_names.hpp:37-43`); only `volcanic_arc` can ever match a native landform.

### Hard gates

`_reef_growth_index` returns all-zero unless (`reef_diagnostics.py:186-189`):

1. `water_body_type ∈ MARINE_WATER_TYPES`, **and**
2. `is_water` is true, **and**
3. the cell has ≥1 land neighbour.

So reefs only ever occur on marine cells that touch land. Open-ocean cells score zero by construction, which is why `patch_reef` (the `_reef_type` fallback for zero land neighbours, `reef_diagnostics.py:232`) is unreachable at cell level and only appears as the record-level `_primary_key` fallback default.

The `heuristic_coastal_reef_v2` model additionally requires the annual temperature and all 12 supplied monthly means to lie strictly inside `(4, 39) °C`. Otherwise growth is zero, while sediment, wave, island and bleaching diagnostics remain available. Only an absent monthly field permits an annual-only fallback; malformed, empty or nonfinite monthly input is ineligible. This fixes the earlier additive score, whose nonthermal bonuses could qualify a reef even when temperature suitability was zero. The published `reef_diagnostics_model` identifies the bounds and fallback policy.

These are the existing empirical curve's support limits, not universal coral survival limits. The model uses surface-column temperature and does not resolve brief extremes, coral species physiology or deep-water habitat temperature. Its legacy bleaching index remains a heuristic; it is not observed accumulated thermal stress.

### Sub-index formulas

| Sub-index | Formula | Line |
|---|---|---|
| `temperature` | `0` if `T < 4`; `clamp((T-4)/14) * 0.55` if `T < 18`; else `clamp(1 - abs(T-26)/13)` | 43-48 |
| `shallow` | shelf: `clamp(1 - max(0, d-5)/210)`; inland sea: `clamp(0.82 - max(0, d-5)/260)`; ocean: `clamp(0.42 - max(0, d-25)/360)` | 51-58 |
| `shelf_bonus` | `0.24` shelf, `0.14` inland sea, `0.04` ocean | 193 |
| `island` (`reef_island_support_index`) | `clamp(island*0.40 + volcanic*0.38 + young_coast*0.22)` over land neighbours, where `island = 0.62` if any neighbour `island_class ∈ {islet, island, large_island}`; `volcanic = max(clamp(volcanic_potential_index * 2.6), 0.55 if landform ∈ VOLCANIC_LANDFORMS, 0.42 if lithology ∈ {basalt, andesite})`; `young_coast = max clamp((120 - crust_age_ma)/120)` | 153-169 |
| `sediment` (`reef_sediment_stress_index`) | `clamp(0.32·[any land neighbour is_river] + 0.28·[any land neighbour landform ∈ {delta, floodplain}] + clamp(max runoff/1300)*0.18 + clamp(max sediment export/2)*0.18 + max coastal-feature `sediment_supply_index`*0.24 + clamp(own sediment_thickness_m/4)*0.10)` | 105-136 |
| `wave` (`reef_wave_exposure_index`) | max `wave_energy_index` over adjacent land coastal features; if none, `clamp(sqrt(wind_east² + wind_north²))` | 139-150 |
| `bleaching` (`reef_bleaching_risk_index`) | `clamp(clamp((T-29)/7)*0.44 + clamp(climate_energy_stress_index)*0.24 + clamp(seasonal_aridity_index)*0.16 + clamp(ocean_current_temperature_c/5)*0.16)` | 172-178 |
| `ice` | `clamp(ice_thickness_m / 60)` | 198 |
| `wave_window` | `clamp(1 - abs(wave - 0.42) / 0.58)` — an optimum band, not a monotone penalty | 199 |
| `fishery` | `clamp(fishery_productivity_index)` from `ecosystem_dynamics` | 200 |

Note `lithology ∈ {"basalt", "andesite"}`: `andesite` is not in `LITHOLOGY_NAMES` (`schema_names.hpp:11-13`), so only `basalt` can match. Note also that `sediment_export` reads `fluvial_sediment_routed_outgoing_m` with a fallback to `sediment_export_m` (`reef_diagnostics.py:109-120`).

### The growth composite

```
reef_growth_index = clamp(
      temperature   * 0.26
    + shallow       * 0.25
    + shelf_bonus                 # 0.24 / 0.14 / 0.04, not scaled
    + island        * 0.15
    + wave_window   * 0.10
    + fishery       * 0.08
    - sediment      * 0.22
    - bleaching     * 0.16
    - ice           * 0.54
)                                                   # reef_diagnostics.py:201-211
```

A cell is a reef candidate when the thermal gate passes and `reef_growth_index >= 0.46`. The weights and threshold above are unchanged for eligible cells.

### Type classification

`_reef_type` (`reef_diagnostics.py:215-232`), first match wins:

| Order | Type | Condition |
|---|---|---|
| 1 | `cold_water_reef` | `temperature_c < 18.0` |
| 2 | `atoll_reef` | some land neighbour has `island_class ∈ {islet, island}` **and** land-neighbour count `<= 2` |
| 3 | `barrier_reef` | some adjacent land coastal feature has `type ∈ {barrier_bar, barrier_island}` |
| 4 | `fringing_reef` | land-neighbour count `>= 1` |
| 5 | `patch_reef` | fallback (unreachable given the land-neighbour gate) |

### `reef_systems[]` record

Connected components of candidate cells over the raw mesh adjacency (`_connected_components`, `reef_diagnostics.py:235-254`; note the flood-fill does not re-check the candidate predicate on neighbours because `remaining` is already the candidate set). Records at `reef_diagnostics.py:386-412`:

| Field | Derivation |
|---|---|
| `id` | component index; stamped onto `cell["reef_system_id"]` |
| `reef_type` | modal cell `reef_type` by `(-count, name)`, default `patch_reef` |
| `cell_count`, `cell_ids`, `area_km2` | membership and summed area (6 dp) |
| `centroid_lat_deg`, `centroid_lon_deg` | area-weighted spherical centroid |
| `mean_reef_growth_index` | mean over members |
| `mean_reef_sediment_stress_index` | mean |
| `mean_reef_wave_exposure_index` | mean |
| `mean_reef_island_support_index` | mean |
| `mean_reef_bleaching_risk_index` | mean |
| `mean_water_depth_m`, `mean_temperature_c` | means |
| `mean_fishery_productivity_index` | mean |
| `adjacent_landmass_ids` | sorted distinct `landmass_id` of adjacent land |
| `marine_region_ids` | sorted distinct over members plus adjacent marine neighbours |
| `coastal_feature_ids` | sorted `coastal_features[].id` on adjacent land cells |
| `settlement_ids` | sorted settlement ids on adjacent land cells (empty in geo-only) |
| `port_site_ids` | sorted `port_site_id` over members and adjacent land (always empty in geo-only) |
| `fishery_resource_record_ids` | `renewable_resource_records` with `resource_type == "fishery_productivity"` on member cells |
| `adjacent_volcanic_land_cell_count` | adjacent land cells with volcanic landform, `volcanic_potential_index >= 0.20`, or `lithology ∈ {basalt, andesite}` |
| `reef_type_counts` | sorted histogram of member `reef_type` |

---

## Port site suitability

`enrich_world_with_port_sites` (`src/magic_geo/port_sites.py:176-341`) — **full-world only**. It depends on `navigability_diagnostics` (which runs immediately before it) for `harbor_suitability_index`, `coastal_navigability_index` and `navigability_index`, and on `sea_level_diagnostics` for `marine_chokepoints`.

Module constants (`port_sites.py:8-12`):

| Constant | Value |
|---|---|
| `PORT_SITE_MODEL` | `causal_navigability_coastal_port_site_selection_v1` |
| `PORT_SITE_THRESHOLD` | `0.58` |
| `PROTECTED_BAY_THRESHOLD` | `0.55` |
| `RIVER_MOUTH_THRESHOLD` | `0.50` |
| `STRAIT_ACCESS_THRESHOLD` | `0.55` |

### Upstream inputs from `navigability_diagnostics`

| Input | Formula | Source |
|---|---|---|
| `coastal_navigability_index` (land branch) | `clamp(clamp(marine_neighbours/4)*0.32 + 0.20·[any shelf/inland-sea neighbour] + 0.22·[is_river or landform == delta] + clamp(1 - abs(elevation)/1200)*0.18)` | `navigability_diagnostics.py:83-90` |
| `coastal_navigability_index` (marine branch) | `clamp(clamp(depth/180)*0.30 + shelf_bonus + clamp(land_neighbours/4)*0.20 + chokepoint_constriction*0.26)`, `shelf_bonus = 0.24` shelf/inland sea else `0.08` | `navigability_diagnostics.py:76-81` |
| `harbor_suitability_index` | `0` for water or landlocked cells; else `clamp(coastal*0.32 + 0.24·[protected neighbour] + 0.18·[river or delta] + clamp(1 - abs(elevation)/900)*0.14 + settlement_score*0.18 - clamp(ice/300)*0.22)` | `navigability_diagnostics.py:93-115` |

### Port sub-indices

| Index | Gate | Formula | Line |
|---|---|---|---|
| `protected_bay_index` | land cell with ≥1 marine neighbour | `clamp(marine_contact*0.20 + protected_water*0.25 + enclosure*0.25 + shallow*0.16 + harbor*0.14)` | 44-56 |
| `river_mouth_port_index` | land cell with ≥1 marine neighbour **and** (`is_river` or `landform ∈ {delta, floodplain, river_valley}`) | `clamp(0.28 + flow*0.22 + runoff*0.14 + delta_bonus + harbor*0.10)` | 59-69 |
| `strait_access_index` | land cell with ≥1 marine neighbour | `clamp(best_constriction*0.76 + coastal*0.24)` | 72-90 |

Sub-term definitions:

| Term | Definition | Line |
|---|---|---|
| `marine_contact` | `clamp(len(marine_neighbors) / 3.0)` | 47 |
| `protected_water` | fraction of marine neighbours whose type is `continental_shelf` or `inland_sea` | 48-50 |
| `enclosure` | mean over marine neighbours of *their* land-neighbour fraction | 51 |
| `shallow` | mean over marine neighbours of `clamp(1 - water_depth_m / 260)` | 52-54 |
| `flow` | `clamp(flow_accumulation / max(1, global max flow_accumulation))` | 65, 189 |
| `runoff` | `clamp(runoff_mm_y / 900)` | 66 |
| `delta_bonus` | `0.26` for `delta`; `0.12` for `floodplain` / `river_valley`; else `0` | 67 |
| `best_constriction` | max over marine neighbours of their chokepoint `constriction_index`, floored at `0.60` when the chokepoint `type == "strait"` | 79-88 |

### The suitability composite

```
base = max(harbor, protected_bay, river_mouth, strait_access)

port_suitability_index = clamp(
      base           * 0.40
    + protected_bay  * 0.16
    + river_mouth    * 0.14
    + strait_access  * 0.12
    + coastal        * 0.06
    + settlement     * 0.06     # settlement_score; absent ⇒ 0.0
    + climate        * 0.06     # clamp((temperature_c + 8) / 30)
    - ice_penalty    * 0.32     # clamp(ice_thickness_m / 220)
    - relief_penalty * 0.08     # clamp((abs(elevation_m) - 1200) / 1800)
)                                                       # port_sites.py:93-118
```

Water cells short-circuit to `0.0` (`port_sites.py:99-100`).

### Typing and selection

`_site_type` (`port_sites.py:121-132`), first match wins:

| Order | `port_site_type` | Condition |
|---|---|---|
| 1 | `strait_port` | `strait_access >= 0.55` |
| 2 | `river_mouth_port` | `river_mouth >= 0.50` |
| 3 | `protected_bay_port` | `protected_bay >= 0.55` |
| 4 | `harbor_port` | `harbor >= 0.62` |
| 5 | `coastal_port` | `suitability >= 0.58` |
| 6 | `none` | fallback |
| — | `port_settlement` | assigned in the record pass when a selected cell still has type `none` (`port_sites.py:233-234`) |

Selection (`port_sites.py:217-223`):

```
severe_ice = ice_thickness_m >= 80.0 or biome == "ice_cap"
selected   = (not is_water) and (
                 (port_suitability_index >= 0.58 and not severe_ice)
                 or cell_id hosts a settlement with type == "port"
             )
```

Records are emitted in **ascending candidate cell id** (`port_sites.py:229`), so `port_site_id` is a stable cell-order index. There is no minimum-separation greedy pass in this module.

### `port_sites[]` record

| Field | Derivation |
|---|---|
| `id` | record index |
| `cell_id` | the land cell |
| `site_type` | the final `port_site_type` |
| `area_km2` | cell area, 6 dp |
| `latitude_deg`, `longitude_deg` | cell centre, 6 dp |
| `port_suitability_index` | serialized (rounded) cell value |
| `protected_bay_index`, `river_mouth_port_index`, `strait_access_index` | serialized cell values |
| `harbor_suitability_index` | raw (unclamped) cell value |
| `navigability_index` | from `navigability_diagnostics` |
| `settlement_ids` | sorted settlement ids on the cell |
| `port_settlement_ids` | subset whose `type == "port"` |
| `route_ids` | sorted routes touching those settlements |
| `marine_region_ids` | sorted regions of the marine neighbours |
| `marine_chokepoint_ids` | sorted chokepoints on the marine neighbours |
| `navigable_waterway_ids` | own + neighbour `navigable_waterway_id`, sorted, `-1` filtered |
| `landform`, `biome`, `water_body_type` | echoed cell classifications |
| `is_river` | echoed |
| `selected_by_port_settlement` | `bool(port_settlement_ids)` |
| `selected_by_suitability` | `(harbor >= 0.62 or serialized port_suitability_index >= 0.58) and not severe_ice` |

### `port_site_model` block

Written to `world["port_site_model"]` (`port_sites.py:294-315`):

| Key | Value |
|---|---|
| `model_type` | `causal_navigability_coastal_port_site_selection_v1` |
| `source_navigability_model` | `causal_channel_hydraulic_coastal_navigability_v1` |
| `domain` | `all_cells_with_land_only_selection` |
| `protected_bay_model` | `marine_contact_protected_water_enclosure_depth_harbor_v1` |
| `river_mouth_model` | `river_landform_flow_runoff_delta_harbor_v1` |
| `strait_access_model` | `adjacent_marine_chokepoint_constriction_and_coastal_access_v1` |
| `suitability_model` | `harbor_bay_river_strait_coastal_settlement_climate_ice_relief_v1` |
| `classification_model` | `strait_river_mouth_protected_bay_harbor_coastal_priority_v1` |
| `selection_model` | `raw_suitability_without_severe_ice_or_port_settlement_override_v1` |
| `record_order` | `ascending_candidate_cell_id` |
| `link_model` | `cell_settlement_route_marine_region_chokepoint_nearby_waterway_links_v1` |
| `port_site_threshold` | `0.58` |
| `protected_bay_threshold` | `0.55` |
| `river_mouth_threshold` | `0.50` |
| `strait_access_threshold` | `0.55` |
| `threshold_semantics` | `unrounded_pre_serialization_values_except_record_flags_use_serialized_fields` |
| `deterministic` | `true` |
| `candidate_cell_count` | count of selected cells |
| `site_count` | number of records |
| `model_limitation` | `diagnostic_port_suitability_without_harbor_bathymetry_tides_waves_sedimentation_engineering_or_economic_optimization` |

The `threshold_semantics` string is exact: `_site_type` and `selected` use unrounded values, while the record flag `selected_by_suitability` re-reads the 6-dp serialized `port_suitability_index`. The two can disagree at the sixth decimal.

---

## Complete marine record families

| Top-level key | Producer | Scope | Record count semantics | Fields |
|---|---|---|---|---|
| `sea_level_model` | native `sea_level_model_json` | both | single object | 27 (table above) |
| `coastal_features` | native `generate_coastal_features` | both | one per coastal land cell | 12 |
| `landmasses` | `sea_level_diagnostics` | both | connected `!is_water` components | 13 |
| `marine_regions` | `sea_level_diagnostics` | both | connected marine components (structurally 1) | 14 |
| `continental_shelves` | `sea_level_diagnostics` | both | connected `continental_shelf` components | 17 |
| `marine_chokepoints` | `sea_level_diagnostics` | both | qualifying marine cells | 14 |
| `ocean_current_systems` | `ocean_circulation` | both | connected same-regime marine components | 32 |
| `ocean_current_transport_edges` | `ocean_circulation` | both | one per marine cell with a target | 16 |
| `reef_systems` | `reef_diagnostics` | both | connected reef-candidate components | 23 |
| `navigable_waterways` | `navigability_diagnostics` | full only | connected navigable components | — see [Settlements, Routes and Corridors](settlements-and-routes.md) |
| `navigability_model` | `navigability_diagnostics` | full only | single object | 21 |
| `port_sites` | `port_sites` | full only | selected land cells, ascending cell id | 24 |
| `port_site_model` | `port_sites` | full only | single object | 20 |

Adjacent families that are marine-influenced but documented elsewhere: `sedimentary_basins` and `stratigraphic_columns` ([Sediment, Routing and Stratigraphy](sediment-and-stratigraphy.md)), `watersheds` and `lake_basins` ([Hydrology, Rivers and Lakes](hydrology-and-rivers.md)), `ice_sheets` ([Cryosphere](cryosphere.md)).

---

## Complete marine cell fields

### Native (C++) marine cell fields

From `cells_json` (`cpp/src/engine/entity_serialization.cpp:110-...`). `P` = `output.float_precision` (default `4`), `S` = `max(10, float_precision)`, `RT` = `roundtrip_num` (exact binary64 round-trip).

| # | Field | Type / precision | Written by | Meaning |
|---|---|---|---|---|
| 43 | `bedrock_surface_elevation_m` | double `S` | `sediment_partition.cpp` primitives | canonical bedrock operand; the datum shift moves only this one |
| 44 | `elevation_m` | **RT** | derived, `ocean.cpp:245-249, 262-264` | signed height relative to the solved sea level; ocean-mask determinant |
| 45 | `water_depth_m` | **RT** | `ocean.cpp:270` | `-elevation_m` for marine cells, `0` otherwise; ocean-mask determinant |
| 46 | `is_water` | bool | `ocean.cpp:41, 250` | membership in the single selected marine component |
| 47 | `water_body_type` | enum string | `ocean.cpp:271, 314-319`; `hydrology.cpp`; `environment.cpp:342` | `land` \| `ocean` \| `continental_shelf` \| `inland_sea` \| `fresh_lake` \| `saline_basin` |
| 62 | `ocean_current_east` | double `P` | `climate.cpp:366` | unit east component × `oceanity` |
| 63 | `ocean_current_north` | double `P` | `climate.cpp:367` | unit north component × `oceanity` |
| 64 | `ocean_current_temperature_c` | double `P` | `climate.cpp:374` | current thermal anomaly, `[-4.5, 4.5]` × `oceanity` |
| 65 | `ocean_current_moisture_factor` | double `P` | `climate.cpp:375-379` | precipitation multiplier, `[0.72, 1.28]` |
| 114 | `sediment_thickness_m` | double `S` | sediment primitives | mobile sediment above bedrock; used by shelf and reef diagnostics |
| 149 | `landform` | enum string | `environment.cpp:430-442` | marine cells receive `open_ocean` \| `continental_shelf` \| `inland_sea` \| `trench` \| `fjord` |
| 153 | `biome` | enum string | `environment.cpp:331` | marine cells receive `ocean` (0), `continental_shelf` (1) or `lake` (2) |
| 154 | `resource` | enum string | `environment.cpp:332` | `coastal_fisheries` when the cell is coastal or shelf, else `none` |

Marine landform mapping in detail (`cpp/src/engine/environment.cpp:430-442`, first match wins):

| Order | `landform` | Condition |
|---|---|---|
| 1 | `fjord` (16) | glacier neighbour **and** `water_depth_m < 1200` **and** `water_body ∈ {shelf, inland_sea}` |
| 2 | `trench` (9) | `boundary_convergent > 0.38` **and** `water_depth_m > 700` |
| 3 | `continental_shelf` (1) | `water_body == 2` |
| 4 | `inland_sea` (2) | `water_body == 3` |
| 5 | `open_ocean` (0) | fallback |

Marine biome mapping (`cpp/src/engine/environment.cpp:331`): `water_body == 2` ⇒ `continental_shelf`; `water_body == 3` ⇒ `lake`; else `ocean`. Water cells also get `soil_type = none`, `soil_depth_m = 0`, `fertility = 0`, `settlement_score = 0` (`environment.cpp:328-333`).

### Python-added marine cell fields

| Field | Enricher | Scope | Range / values |
|---|---|---|---|
| `landmass_id` | `sea_level_diagnostics` | both | `>= 0` on land, `-1` on water |
| `marine_region_id` | `sea_level_diagnostics` | both | `>= 0` on marine cells, `-1` otherwise |
| `continental_shelf_id` | `sea_level_diagnostics` | both | `>= 0` on shelf cells, `-1` otherwise |
| `marine_chokepoint_id` | `sea_level_diagnostics` | both | `>= 0` on qualifying marine cells, `-1` otherwise |
| `island_class` | `sea_level_diagnostics` | both | `continent` \| `large_island` \| `island` \| `islet` \| `water` (`unassigned` is the pre-fill default and should not survive) |
| `ocean_current_speed_index` | `ocean_circulation` | both | `>= 0`; `1.0` on marine cells up to component rounding |
| `ocean_current_poleward_index` | `ocean_circulation` | both | `[-1, 1]` |
| `ocean_heat_transport_index` | `ocean_circulation` | both | `[-1, 1]` |
| `ocean_current_transport_alignment` | `ocean_circulation` | both | `[0, 1]` |
| `ocean_current_transport_target_cell_id` | `ocean_circulation` | both | neighbour id or `-1` |
| `ocean_current_transport_distance_km` | `ocean_circulation` | both | `>= 0` |
| `ocean_current_convergence_index` | `ocean_circulation` | both | `[-1, 1]` |
| `ocean_upwelling_index` | `ocean_circulation` | both | `[0, 1]` |
| `ocean_current_regime` | `ocean_circulation` | both | 9 regime strings, or `non_marine` |
| `ocean_current_system_id` | `ocean_circulation` | both | `>= 0` on marine cells, `-1` otherwise |
| `distance_to_marine_water_km` | `climate_continentality` | both | BFS great-circle distance to marine water |
| `reef_growth_index` | `reef_diagnostics` | both | `[0, 1]` |
| `reef_sediment_stress_index` | `reef_diagnostics` | both | `[0, 1]` |
| `reef_wave_exposure_index` | `reef_diagnostics` | both | `[0, 1]` |
| `reef_island_support_index` | `reef_diagnostics` | both | `[0, 1]` |
| `reef_bleaching_risk_index` | `reef_diagnostics` | both | `[0, 1]` |
| `reef_type` | `reef_diagnostics` | both | `none` \| `fringing_reef` \| `barrier_reef` \| `atoll_reef` \| `patch_reef` \| `cold_water_reef` |
| `reef_system_id` | `reef_diagnostics` | both | `>= 0` for candidates, `-1` otherwise |
| `coastal_navigability_index` | `navigability_diagnostics` | **full only** | `[0, 1]` |
| `harbor_suitability_index` | `navigability_diagnostics` | **full only** | `[0, 1]` |
| `transport_chokepoint_index` | `navigability_diagnostics` | **full only** | `[0, 1]` |
| `river_navigability_index` | `navigability_diagnostics` | **full only** | `[0, 1]` |
| `navigability_index` | `navigability_diagnostics` | **full only** | `[0, 1]` |
| `navigability_class` | `navigability_diagnostics` | **full only** | 6 class strings |
| `navigable_waterway_id` | `navigability_diagnostics` | **full only** | `>= 0` or `-1` |
| `protected_bay_index` | `port_sites` | **full only** | `[0, 1]` |
| `river_mouth_port_index` | `port_sites` | **full only** | `[0, 1]` |
| `strait_access_index` | `port_sites` | **full only** | `[0, 1]` |
| `port_suitability_index` | `port_sites` | **full only** | `[0, 1]` |
| `port_site_id` | `port_sites` | **full only** | `>= 0` or `-1` |
| `port_site_type` | `port_sites` | **full only** | 7 type strings including `none` and `port_settlement` |

---

## Marine summary keys

### Native summary keys

| Key | Precision | Derivation | Line |
|---|---|---|---|
| `target_ocean_fraction` | `P` | echo of `ocean_fraction_target` | `summary.cpp:1624` |
| `target_ocean_water_inventory_km3` | `max(6, P)` | echo of `ocean_water_inventory_km3` | `summary.cpp:1625` |
| `ocean_area_km2` | `max(6, P)` | summed marine area | `summary.cpp:1627` |
| `ocean_volume_km3` | `max(6, P)` | summed cell-column volume | `summary.cpp:1628` |
| `ocean_water_inventory_error_km3` | `max(6, P)` | `abs(volume - target)` | `summary.cpp:1629` |
| `ocean_fraction` | `P` | `ocean_area_km2 / surface_area_km2` | `summary.cpp:1632` |
| `ocean_cell_fraction` | `P` | marine cells / all cells | `summary.cpp:1635` |
| `mean_ocean_current_strength` | `P` | mean `|current|` over **all** cells | `summary.cpp:2063` |
| `mean_ocean_current_temperature_c` | `P` | mean over all cells | `summary.cpp:2065` |
| `mean_ocean_current_moisture_factor` | `P` | mean over all cells | `summary.cpp:2067` |
| `coastal_feature_count` | int | `coastal_features.size()` | `summary.cpp:1803` |
| `coastal_bar_feature_count` | int | types `barrier_bar` + `barrier_island` | `summary.cpp:1804` |
| `prograding_coastal_feature_count` | int | trends `prograding` + `delta_switching` | `summary.cpp:1805` |
| `eroding_coastal_feature_count` | int | trends `eroding` + `landward_migration` | `summary.cpp:1806` |
| `mean_coastal_migration_rate_m_y` | `P` | mean `migration_rate_m_y` | `summary.cpp:1807` |
| `water_body_counts` | sparse map | histogram over `WATER_BODY_NAMES` (accumulated at `summary.cpp:518`) | `summary.cpp:2102` |
| `landform_counts` | sparse map | histogram over `LANDFORM_NAMES` (accumulated at `summary.cpp:520`) | `summary.cpp:2103` |

### `sea_level_diagnostics` summary keys

(`src/magic_geo/sea_level_diagnostics.py:363-386`, all floats at 6 dp)

| Key | Derivation |
|---|---|
| `landmass_count` | number of landmass records |
| `continent_landmass_count` | records with `island_class == "continent"` |
| `island_landmass_count` | records with `island_class != "continent"` |
| `largest_landmass_area_km2` | max landmass area, `0.0` if none |
| `mean_landmass_area_km2` | mean landmass area, `0.0` if none |
| `marine_region_count` | number of marine regions (structurally `1` or `0`) |
| `open_ocean_marine_region_count` | regions classed `open_ocean` |
| `inland_sea_marine_region_count` | regions classed `inland_sea` (structurally `0`) |
| `continental_shelf_marine_region_count` | regions classed `continental_shelf` |
| `largest_marine_region_area_km2` | max region area |
| `continental_shelf_count` | number of shelf components |
| `continental_shelf_cell_count` | summed shelf record cell counts |
| `continental_shelf_total_area_km2` | summed shelf area |
| `largest_continental_shelf_area_km2` | max shelf area |
| `mean_continental_shelf_depth_m` | mean `water_depth_m` over all shelf cells |
| `continental_shelf_shoreline_edge_count` | summed shelf→land edges |
| `continental_shelf_break_edge_count` | summed shelf→(marine non-shelf) edges |
| `marine_chokepoint_count` | number of chokepoints |
| `strait_chokepoint_count` | chokepoints of type `strait` |
| `mean_marine_chokepoint_constriction_index` | mean constriction, `0.0` if none |

### `ocean_circulation` summary keys

(`src/magic_geo/ocean_circulation.py:337-379`; means divide by `max(1, marine cell count)`)

| Key | Derivation |
|---|---|
| `ocean_current_cell_count` | marine cell count |
| `ocean_current_system_count` | number of systems |
| `ocean_current_transport_edge_count` | number of edges |
| `ocean_current_transport_coverage_fraction` | edges / marine cells |
| `ocean_current_total_transport_length_km` | summed edge great-circle distances |
| `ocean_current_total_area_km2` | summed marine area |
| `mean_ocean_circulation_speed_index` | mean speed index over marine cells (`1.0` up to component rounding, see caveat) |
| `mean_ocean_current_transport_alignment` | mean alignment |
| `mean_ocean_current_poleward_index` | mean poleward index |
| `mean_ocean_heat_transport_index` | mean heat-transport index |
| `mean_ocean_current_convergence_index` | mean convergence |
| `mean_ocean_upwelling_index` | mean upwelling |
| `warm_ocean_current_cell_count` | `ocean_current_temperature_c >= 0.5` |
| `cold_ocean_current_cell_count` | `<= -0.5` |
| `poleward_ocean_current_cell_count` | `poleward_index >= 0.08` |
| `equatorward_ocean_current_cell_count` | `<= -0.08` |
| `high_ocean_upwelling_cell_count` | `upwelling >= 0.55` |
| `ocean_current_regime_counts` | sorted histogram over **all** cells (so `non_marine` appears) |
| `ocean_current_system_class_counts` | sorted histogram over systems |

### `reef_diagnostics` summary keys

(`src/magic_geo/reef_diagnostics.py:417-430`; means divide by **all** cells)

`reef_system_count`, `reef_cell_count`, `reef_total_area_km2`, `mean_reef_growth_index`, `mean_reef_sediment_stress_index`, `mean_reef_wave_exposure_index`, `mean_reef_island_support_index`, `mean_reef_bleaching_risk_index`, `fringing_reef_system_count`, `barrier_reef_system_count`, `atoll_reef_system_count`, `patch_reef_system_count`, `cold_water_reef_system_count`, `reef_type_counts`.

### `port_sites` summary keys (full world only)

(`src/magic_geo/port_sites.py:316-339`; means divide by **all** cells)

`port_site_model`, `port_site_count`, `port_candidate_cell_count`, `port_site_total_area_km2`, `mean_port_suitability_index`, `mean_protected_bay_index`, `mean_river_mouth_port_index`, `mean_strait_access_index`, `port_settlement_count`, `port_settlement_with_site_count`, `protected_bay_port_site_count`, `river_mouth_port_site_count`, `strait_port_site_count`, `port_site_type_counts`.

### `navigability_diagnostics` summary keys (full world only)

(`src/magic_geo/navigability_diagnostics.py:332-343`)

`navigability_model`, `navigable_cell_count`, `navigable_waterway_count`, `navigable_waterway_total_area_km2`, `mean_navigability_index`, `mean_river_navigability_index`, `mean_coastal_navigability_index`, `mean_harbor_suitability_index`, `mean_transport_chokepoint_index`, `high_harbor_suitability_cell_count`, `transport_chokepoint_cell_count`, `navigability_class_counts`.

---

## Worked examples

### Generate a world and inspect the sea-level closure

```bash
magic-geo init-config --output magic-geo.yaml --profile earthlike
magic-geo generate --config magic-geo.yaml --output runs/world.json --cells 4096
jq '.sea_level_model' runs/world.json
```

Expected shape of the interesting fields (values depend on seed):

```json
{
  "model_type": "volume_constrained_connectivity_ocean_flood_v3",
  "selection_rule": "solve_largest_connected_ocean_cell_column_volume_across_elevation_intervals",
  "ocean_fraction_target": 0.7,
  "ocean_water_inventory_km3": 1338000000.0,
  "selected_ocean_volume_km3": 1338000000.0,
  "ocean_water_inventory_error_km3": 0.0,
  "connected_ocean_component_count": 1,
  "ocean_connectivity_enforced": true,
  "model_limitation": "cell_column_volume_without_subcell_bathymetry_straits_or_exact_coast_polygons"
}
```

### Change the ocean water inventory, not the fraction

`magic-geo generate` has no `--set`; overrides belong to `init-config` (`src/magic_geo/cli/commands/config.py:29-35`), so write a second config first.

```bash
magic-geo init-config \
  --output wet.yaml \
  --profile earthlike \
  --set planet.ocean_water_inventory_km3=1800000000 \
  --force
magic-geo generate --config wet.yaml --output runs/wet.json
```

Raising the inventory raises sea level and therefore ocean area. Changing `planet.ocean_fraction_target` alone changes only `sea_level_model.target_ocean_area_km2`, `target_ocean_cell_count`, the four `ocean_area_target_error_*` diagnostics and `summary.target_ocean_fraction` — the mask, the datum and every downstream marine product stay bit-identical.

### A dry planet

```bash
magic-geo init-config --output dry.yaml --profile earthlike \
  --set planet.ocean_water_inventory_km3=0 --force
magic-geo generate --config dry.yaml --output runs/dry.json
```

This takes the zero-inventory branch (`cpp/src/engine/ocean.cpp:29-47`): no cell is marine, `landmasses` is one giant component, `marine_regions` and `continental_shelves` are empty, `coastal_features` is empty, and every `ocean_current_regime` is `non_marine`. `ocean_inventory_closure` still passes because the reconstructed volume and the target are both zero (`src/magic_geo/geo_validation.py:1356-1375`); the explicit zero branch lives in `single_connected_ocean`, which accepts an empty marine mask only when `target_volume == 0.0` (`src/magic_geo/geo_validation.py:1416-1419`) and expects `connected_ocean_component_count == 0` in that case (`geo_validation.py:1425-1426`). The strict `magic-geo validate` replay has the matching branch at `src/magic_geo/cli/commands/validate.py:591-598`.

### Python API

```python
from magic_geo import load_config
from magic_geo.api import generate_world

config = load_config("magic-geo.yaml")
world = generate_world(config)

model = world["sea_level_model"]
print(model["selected_ocean_volume_km3"], model["ocean_water_inventory_error_km3"])
print(world["summary"]["ocean_fraction"], world["summary"]["target_ocean_fraction"])

# Independently reconstruct the conserved quantity from the cells.
volume = sum(
    cell["area_km2"] * cell["water_depth_m"] / 1000.0
    for cell in world["cells"]
    if cell["is_water"]
)
assert abs(volume - config.planet.ocean_water_inventory_km3) < 0.01
```

### Marine domain inventory

```python
from collections import Counter

cells = world["cells"]
print(Counter(cell["water_body_type"] for cell in cells))
print(Counter(cell["ocean_current_regime"] for cell in cells))
print(len(world["marine_regions"]), len(world["continental_shelves"]))
print(Counter(record["type"] for record in world["marine_chokepoints"]))
print(Counter(record["reef_type"] for record in world["reef_systems"]))

# The speed-index caveat, checked directly: every marine cell sits at 1.0 up to the
# rounding of the two serialized components, so the field carries no speed contrast.
marine = [c for c in cells if c["water_body_type"] in {"ocean", "continental_shelf", "inland_sea"}]
speeds = [c["ocean_current_speed_index"] for c in marine]
print(min(speeds), max(speeds))                        # both ~1.0
assert all(abs(s - 1.0) < 1e-3 for s in speeds)
```

### Geo-only scope

```bash
magic-geo generate --config magic-geo.yaml --output runs/geo.json --geo-only
```

`generate_geo_world` raises `ValueError` unless `output.include_cells` is true. In this scope `port_sites`, `port_site_model`, `navigable_waterways` and `navigability_model` are absent, and every cell lacks `harbor_suitability_index`, `coastal_navigability_index`, `navigability_index`, `port_site_id` and `port_site_type`. `landmasses`, `marine_regions`, `continental_shelves`, `marine_chokepoints`, `ocean_current_systems`, `ocean_current_transport_edges`, `reef_systems` and `coastal_features` are all still produced.

### Wave energy, by hand

For a coastal land cell with 7 neighbours of which 2 are water, on an interior plate (`boundary_convergent = boundary_transform = 0`):

```
oceanity        = exp(-1 / 7.5)              = 0.875173
|ocean_current| = oceanity                   = 0.875173
exposure        = 2 / 7                      = 0.285714
wave_energy     = 0.22 + 0.40 * 0.285714 + 0.24 * 0.875173 + 0.14 * 0.0
                = 0.22 + 0.114286 + 0.210042
                = 0.544327
```

With `sediment_supply_index = 0.35`, the type cascade (`cpp/src/engine/environment.cpp:556-575`) fails `delta_lobe`, `tidal_marsh` (needs `sediment > 0.42`) and `barrier_island` (needs `sediment > 0.56`), then matches `barrier_bar` provided `elevation_m < 260`.

```
longshore = 0.18 + 0.46 * 0.544327 + 0.24 * 0.875173 + 0.12 * 0.35 = 0.681403
migration = 1.55 * 0.35 - 1.05 * 0.544327 + 0.28 * 0.681403
            + 0.18 * 0.35 - 0.24 * 0.544327
          = 0.5425 - 0.571543 + 0.190793 + 0.063 - 0.130638
          = 0.094112
```

`migration = 0.0941` is below `0.34`, above `-0.28`, and the type is not `coastal_cliff`, so `shoreline_trend = stable`.

### Reef growth, by hand

A `continental_shelf` cell at `water_depth_m = 30`, `temperature_c = 26`, one land neighbour, no rivers or deltas nearby, no ice, `fishery_productivity_index = 0.4`, `wave = 0.42`, `bleaching = 0.05`, `island = 0.3`, `sediment = 0.10`:

```
temperature  = clamp(1 - |26 - 26| / 13)              = 1.000000
shallow      = clamp(1 - (30 - 5) / 210)              = 0.880952
shelf_bonus  = 0.24
wave_window  = clamp(1 - |0.42 - 0.42| / 0.58)        = 1.000000

growth = 1.000000 * 0.26
       + 0.880952 * 0.25
       + 0.24
       + 0.300000 * 0.15
       + 1.000000 * 0.10
       + 0.400000 * 0.08
       - 0.100000 * 0.22
       - 0.050000 * 0.16
       - 0.000000 * 0.54
       = 0.26 + 0.220238 + 0.24 + 0.045 + 0.10 + 0.032 - 0.022 - 0.008
       = 0.867238
```

`0.867 >= 0.46`, so the cell is a reef candidate. With `temperature_c >= 18`, one land neighbour of class `continent` (not `islet`/`island`) and no barrier coastal feature, `_reef_type` falls through to `fringing_reef`.

---

## Validation of the marine domain

Three independent layers check the marine results. None of them re-runs the native engine; all of them recompute from the serialized document.

### `magic-geo validate` — strict replay of the solver

`src/magic_geo/cli/commands/validate.py:183-670` requires the full `sea_level_model` key set, then:

| Check | What it does | Lines |
|---|---|---|
| Independent BFS component count | Recounts connected `is_water` components from `cells[].neighbors` | 246-267 |
| Independent aggregates | Recomputes surface area, ocean area, ocean volume, target area, target cell count, selected fractions | 277-300 |
| **Solver replay** | Re-runs the union-find elevation sweep in Python — same interval-lower candidate, same `nextafter` endpoints, same exact-solution short-circuit — and compares area, volume and the resulting sea level | 490-551 |
| Tolerances | `area_tolerance = max(0.01, surface_area * 1e-10)`; `volume_tolerance = max(0.001, target * 1e-10, selected * 1e-10)` (571-576); the replayed sea level must satisfy `abs(sea_level) <= 1e-6` (it is zero by construction after the datum shift) (588) | 571-599 |
| Water-column consistency | Every `is_water` cell must have `elevation_m < 0` and `abs(water_depth_m + elevation_m) <= 1e-6` | 599-611 |
| Contract strings | `model_type`, `selection_rule`, `area_basis`, `volume_basis`, the three booleans and `model_limitation` must match exactly | 613-668 |

### `magic-geo validate-geo` — physics domains

`src/magic_geo/geo_validation.py`:

| Domain / check | Assertion | Lines |
|---|---|---|
| `sea_level` / `ocean_inventory_closure` | reconstructed volume equals `planet.ocean_water_inventory_km3` within `max(0.01, target * 1e-9)`; no marine cell with `water_depth_m <= 0`; no dry non-lake cell with `abs(water_depth_m) > 1e-6`; `max abs(depth + elevation) <= 1e-6`; zero marine cells with `elevation_m >= 0` | 1327-1373 |
| `sea_level` / `single_connected_ocean` | marine water is one connected component **and** equals the largest below-sea-level component (by area, tie-broken by minimum id); `sea_level_model` aggregates match the reconstruction; `connected_ocean_component_count == 1` when any marine cell exists, `== 0` when none | 1376-1442 |

### `validate-geo` subsystems

`src/magic_geo/geo_validation_subsystems.py`:

| Domain | Check | Assertion | Lines |
|---|---|---|---|
| `ocean_circulation` | `record_structure` | systems and edges are typed records with sequential ids | 175-186 |
| `ocean_circulation` | `system_membership_and_aggregates` | non-overlapping membership, `cell_count` and `area_km2` agree, cell `ocean_current_system_id` mirrors the record, every member is marine, and the record set exactly inverts the cell assignments | 188-226 |
| `ocean_circulation` | `transport_source_links_and_ranges` | every edge target is a **mesh neighbour** of its source, `ocean_current_transport_target_cell_id` mirrors the edge, system ids agree; `alignment`, `poleward_transport_index`, `heat_transport_index` bounded to `[-1,1]`; `current_speed_index`, `great_circle_distance_km`, `upwelling_index` non-negative with `upwelling <= 1` | 228-264 |
| `ocean_circulation` | `cell_values_and_summary_mirrors` | the six per-cell indices are within their declared bounds and four summary counts/totals mirror the records exactly | 266-300 |
| `coastal_marine_landmass` | `land_marine_shelf_partitions` | `landmasses`, `marine_regions` and `continental_shelves` each exactly partition their eligible cells, with matching `cell_count`, `area_km2`, finite centroids and matching summary counts | 741-815 |
| `coastal_marine_landmass` | `coastal_feature_and_chokepoint_sources` | one record per unique valid cell; coastal `wave_energy_index`, `sediment_supply_index`, `longshore_transport_index`, `progradation_index` bounded to `[0,1]`, `length_km >= 0`, `migration_rate_m_y` finite; chokepoint `marine_region_id` and `adjacent_landmass_ids` resolve to real records; `constriction_index` bounded, `width_proxy_km >= 0`; chokepoint summary count matches | 817-880 |

### Calibration checks

`generate_calibration_checks` (`cpp/src/engine/history.cpp`) emits two marine-relevant records:

| Metric | Dataset / layer | Value | Target range | Line |
|---|---|---|---|---|
| `ocean_fraction` | `ETOPO_reference_range` / `relief_bathymetry` | `water_area_km2 / total_area_km2` | `[0.55, 0.78]` | 1060-1067 |
| `coastal_land_fraction` | `NaturalEarth_reference_range` / `cartography` | land cells with ≥1 water neighbour ÷ land cells | `[0.03, 0.48]` | 1045-1050, 1086 |

Both are *reference ranges*, not fitted calibrations — see [Calibration Against Real-Earth Data](../14-calibration.md).

---

## Limitations and unresolved claims

1. **One elevation per cell. No sub-cell bathymetry.** The engine states this itself as `sea_level_model.model_limitation = "cell_column_volume_without_subcell_bathymetry_straits_or_exact_coast_polygons"` (`cpp/src/engine/process_serialization.cpp:3461-3462`). Ocean volume is a sum of cell columns; there is no area–elevation distribution inside a cell, no shelf–slope–rise profile, and no exact coastline polygon. `README.md:352` names the required next architecture — conservative sub-cell hypsometry with fractional flooding and sub-cell strait connectivity — as future work, and explicitly rejects the alternative of lowering whole margin cells to manufacture shelf area.

2. **Straits are graph connectivity, not geometry.** A real narrow strait cannot connect two basins unless a cell-centre path exists. `marine_chokepoints[].width_proxy_km` is `mean_neighbor_edge_length_km / land_neighbor_count` (`src/magic_geo/sea_level_diagnostics.py:276`) — a mesh-scale proxy, not a measured width.

3. **`ocean_fraction_target` does not control anything.** It is a diagnostic area reference (`docs/configuration_reference.md:82`, `README.md:352`). The four `ocean_area_target_error_*` fields measure disagreement between an aspiration and a volume-driven result, not solver error.

4. **The water inventory is an ocean allocation, not a planetary water budget.** `README.md:352`: "This is an ocean allocation, not a partition of total planetary water among ocean, ice, groundwater, lakes, and atmosphere." Ice sheets, aquifers, lakes and atmospheric vapour are configured or derived independently and are not deducted from `ocean_water_inventory_km3`.

5. **`inland_sea` is structurally unreachable.** `is_water` is written only in `cpp/src/engine/ocean.cpp` and always marks exactly one connected component, so `label_marine_water_bodies` never enters its non-largest-component branch (`ocean.cpp:318`). Consequently `marine_regions` always contains at most one record, and `summary.inland_sea_marine_region_count` is always `0`. The enum value and the Python defensive handling remain in the schema. This is a reading of the two functions, not a documented claim in the source.

6. **`continental_shelf` is a depth threshold, not geology.** `water_depth_m < 220.0 m` (`cpp/src/engine/ocean.cpp:316`). Crust type, margin type, sediment thickness and passive/active margin state play no part in the classification.

7. **The current field is prescribed, not solved.** `ocean_current_components` (`cpp/src/engine/climate.cpp:228-249`) is a four-band latitude pattern with `sin(lon)` / `cos(lon)` meridional terms. There is no basin geometry, no coastal boundary condition, no Sverdrup or Ekman balance, no continuity constraint and no gyre closure enforced by mass. Land cells are inside the field domain.

8. **`ocean_current_speed_index` carries no speed information over the ocean.** The native components are unit-normalised and `oceanity == 1` for every `is_water` cell, so the magnitude is `1.0` everywhere on the marine domain (`cpp/src/engine/climate.cpp:246-248, 366-367`; `src/magic_geo/ocean_circulation.py:247`). The Python index recomputes it from the components as serialized at `output.float_precision` decimals, so it sits within roughly `1e-4` of `1.0` rather than being bit-exactly `1.0`; either way it has no spatial contrast and is not a current speed. Any spatial contrast in `mean_ocean_current_strength` comes from land cells.

9. **The transport graph transports nothing.** `ocean_current_transport_edges` is a one-outgoing-edge-per-cell functional graph selected by tangent alignment (`src/magic_geo/ocean_circulation.py:60-100`). No tracer, volume or heat quantity crosses an edge; `ocean_heat_transport_index` is a per-cell scalar with no consumer. `ocean_current_convergence_index` counts in-degree minus out-degree of that graph, not a divergence of any flux.

10. **Heat transport influence on climate is local and equilibrium.** Currents affect climate only through the per-cell `ocean_current_temperature_c` and `ocean_current_moisture_factor` terms, with a global area-mean subtraction so they redistribute rather than inject energy (`cpp/src/engine/climate.cpp:268-291`). `climate_model` declares `mass_conserving_atmosphere: false`, `transient_climate_resolved: false`, and `model_limitation = equilibrium_diagnostic_climate_without_mass_conserving_three_dimensional_atmosphere` (`cpp/src/engine/process_serialization.cpp:443-446`). `CLIMATE_MARINE_ANNUAL_TEMPERATURE_OFFSET_C` is `0.0` (`cpp/src/engine/constants.hpp:10`), so water cells receive no annual thermal-inertia bonus of their own.

11. **Coastal features carry no wave, tide or sediment-budget model.** `wave_energy_index` is a weighted score of neighbour exposure, current magnitude and boundary forcing (`cpp/src/engine/environment.cpp:539-554`). There is no fetch-limited wave growth, no tidal range and no shoreline sediment budget. `migration_rate_m_y` is a bounded score with units attached and no stage consumes it — it never displaces a shoreline.

12. **Coastal features are land-cell records.** One record per coastal land cell (`cpp/src/engine/environment.cpp:613-651`), not per shoreline segment. `length_km` is the sum of great-circle distances to water neighbours, which is a cell-scale quantity and not a coastline length in any cartographic sense.

13. **Reef, port and navigability layers are post-hoc diagnostics.** They are computed in Python from the final state, mutate no native field, and feed nothing back into the simulation. Their model blocks say so: `port_site_model.model_limitation = "diagnostic_port_suitability_without_harbor_bathymetry_tides_waves_sedimentation_engineering_or_economic_optimization"` (`src/magic_geo/port_sites.py:314`), `navigability_model.model_limitation = "diagnostic_transport_suitability_without_vessel_classes_seasonal_discharge_bathymetric_channels_or_route_cost_optimization"` (`src/magic_geo/navigability_diagnostics.py:330`).

14. **Reef scoring contains unreachable branches.** `VOLCANIC_LANDFORMS` includes `island_arc` and `ridge`, which are not values in `LANDFORM_NAMES`; the lithology test accepts `andesite`, which is not in `LITHOLOGY_NAMES`; `REEF_COASTAL_FEATURE_TYPES` is declared but never referenced by the scoring path; and `patch_reef` cannot be produced at cell level because the growth gate already requires a land neighbour. These are observations from reading `src/magic_geo/reef_diagnostics.py:8-12, 156-169, 215-232` against `cpp/src/engine/schema_names.hpp:11-13, 37-43`, not source-documented statements.

15. **Reef and port thresholds are uncalibrated.** `REEF_GROWTH_THRESHOLD = 0.46`, `PORT_SITE_THRESHOLD = 0.58` and the three port sub-thresholds are declared constants with no external validation dataset behind them. The port model declares `threshold_semantics` precisely so a consumer knows which comparisons use unrounded values and which use serialized ones — that is a reproducibility statement, not an accuracy claim.

16. **Physical time is not resolved anywhere in this domain.** The sea-level solve is an equilibrium operator re-applied per coupled stage (`temporal_class: native_equilibrium_recomputed_per_coupled_stage`, `src/magic_geo/geo_layer_contracts.py:130`). Sea-level history, eustatic curves, transgression/regression timing and coastal migration over time are not simulated; the nominal-time framework carries `physical_time_resolved: false` throughout — see [Architecture](../04-architecture.md).

17. **Ocean area is an outcome and can land far from Earth-like.** The `ocean_fraction` calibration check accepts `[0.55, 0.78]` (`cpp/src/engine/history.cpp:1060-1067`) and is a reference-range pass/fail, not a control loop. Nothing in the pipeline adjusts topography or the inventory to hit it.

---

## See also

- [Topography, Isostasy and Thermal Subsidence](topography-and-isostasy.md) — where `elevation_m` comes from and how the oceanic age–depth curve sets basement depth
- [Hydrology, Rivers and Lakes](hydrology-and-rivers.md) — the depression policy that consumes disconnected below-sea-level cells, and the `fresh_lake` / `saline_basin` water bodies
- [Climate and Atmosphere](climate-and-atmosphere.md) — `compute_climate`, the wind and moisture fields, and the current-driven climate realism checks
- [Sediment, Routing and Stratigraphy](sediment-and-stratigraphy.md) — the canonical sediment interface, marine deposition terminals, and the shelf sediment record
- [Cryosphere: Ice Sheets, Glaciers and Permafrost](cryosphere.md) — fjord formation, marine glacial deposition, and the ice penalties in reef and port scoring
- [Biomes, Ecosystems and Disturbance](biomes-and-ecology.md) — `fishery_productivity_index` and the marine biome assignment
- [Settlements, Routes and Corridors](settlements-and-routes.md) — navigable waterways, port settlements, and the coastal-sea route type
- [Mesh and Geometry](mesh-and-geometry.md) — control volumes, `area_km2`, boundary rings and the neighbour graph that defines marine connectivity
- [World Document Schema](../10-world-schema.md) — the full 57-key top-level document and the 155-field cell record
- [Serialization and World Formats](../11-serialization.md) — why `elevation_m` and `water_depth_m` are round-trip serialized
- [Validation](../12-validation.md) and [Geo Validation Suite](../13-geo-validation-suite.md) — the sea-level replay and the marine subsystem domains
- [Configuration Reference](../05-configuration-reference.md) — `planet.ocean_water_inventory_km3` and `planet.ocean_fraction_target`
- [Native Engine (C++ Core)](../08-native-engine.md) — `ocean.cpp` in the translation-unit map and the pipeline stage order
- [Glossary](../21-glossary.md)
