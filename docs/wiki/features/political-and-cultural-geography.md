# Political, Cultural and Linguistic Geography

[Wiki home](../README.md) > Features

**Current seasonal scope.** Read the [settlement and social availability contract](../../settlement_social_availability.md) alongside the formulas below. Current native social estimates use an explicit availability envelope and seven own contracts at v2; the native language, political-region, border and trade-flow contracts retain their v1 identities. Numeric estimates are finite only when their actual inputs are available; otherwise they are null with typed flags. Recorded counts and base geography remain distinct from unavailable inferred totals or scaled geometry. Explicit historical declarations retain their original branches, including the legacy fallbacks identified below. Original source-line references describe the earlier implementation layout rather than current line numbers.

The civilization geography layer turns the native settlement and route graph into political regions, border segments, trade flows, cultures, language regions, sacred areas, ruins and era-scaled territorial snapshots — in `cpp/src/engine/civilization.cpp` plus `generate_territorial_snapshots` in `cpp/src/engine/history.cpp`. Every one of these products is a *deterministic single-pass function of already-computed cell, settlement and route state*: there is no agent simulation, no time stepping, no contiguity constraint and no population feedback anywhere in this layer. On the Python side four modules (`political_geography.py`, `cultural_geography.py`, `civilization_geography.py`, `territorial_geography.py`) publish model metadata and audit current sources without recomputing the native equations; `phonology_history.py` is the one genuinely generative enricher in this layer, and its linguistics is explicitly synthetic template linguistics with no empirical calibration. Four further Python modules (`natural_frontiers.py`, `boundary_geometry.py`, `graph_diagnostics.py`, `worldbuilding_realism.py`) derive products *from* this layer and are covered under [Downstream consumers](#downstream-consumers-of-the-political-layer). This page is the field-level reference for all of it, and it never upgrades any of those hedges.

## On this page

- [Where this layer runs](#where-this-layer-runs)
- [Political region formation](#political-region-formation)
- [Political region record fields](#political-region-record-fields)
- [The border segment model](#the-border-segment-model)
- [Border segment record fields](#border-segment-record-fields)
- [The natural-border fraction](#the-natural-border-fraction)
- [Trade flows and interregional trade](#trade-flows-and-interregional-trade)
- [Trade flow record fields](#trade-flow-record-fields)
- [Cultural layer generation](#cultural-layer-generation)
- [Culture region record fields](#culture-region-record-fields)
- [Language regions, families and lineages](#language-regions-families-and-lineages)
- [Language region record fields](#language-region-record-fields)
- [Sacred areas and ruins](#sacred-areas-and-ruins)
- [Sacred area and ruin record fields](#sacred-area-and-ruin-record-fields)
- [Territorial snapshots and polygon geometry quality](#territorial-snapshots-and-polygon-geometry-quality)
- [Snapshot region record fields](#snapshot-region-record-fields)
- [Declaration-only model records](#declaration-only-model-records)
- [The phonology history model](#the-phonology-history-model)
- [Phonology record families](#phonology-record-families)
- [Downstream consumers of the political layer](#downstream-consumers-of-the-political-layer)
- [Summary keys published by this layer](#summary-keys-published-by-this-layer)
- [Validators](#validators)
- [Worked commands](#worked-commands)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

## Where this layer runs

The whole layer lives inside the `if (include_society)` block of `simulate_world_impl` (`cpp/src/engine/pipeline.cpp:199`–`260`). `generate_geo_world` skips the block entirely, and `_strip_native_civilization_outputs` in `src/magic_geo/api.py` then removes the stable-empty civilization schema fields so that mixed natural models take their documented no-human branches.

| Order | Call | Source | Mutates `cells`? | Produces |
|---|---|---|---|---|
| 1 | `generate_settlements(params, cells)` | `pipeline.cpp:200` | no | `society.settlements` |
| 2 | `generate_routes(params, cells, settlements)` | `pipeline.cpp:201` | no | `society.routes` |
| 3 | `generate_political_regions(params, cells, settlements, routes)` | `pipeline.cpp:202` | **yes** — writes `cell.political_region_id`, `settlement.region_id` | `society.political_regions` |
| 4 | `generate_border_segments(params, cells)` | `pipeline.cpp:208` | no (reads `political_region_id`) | `society.borders` |
| 5 | `generate_trade_flows(cells, settlements, routes)` | `pipeline.cpp:209` | no (reads `settlement.region_id`) | `society.trade_flows` |
| 6 | `generate_cultural_layers(params, cells, settlements, political_regions, borders, trade_flows)` | `pipeline.cpp:214` | **yes** — writes `cell.culture_region_id`, `cell.language_region_id`, `settlement.culture_region_id`, `settlement.language_region_id` | `society.cultural_layers` (cultures, languages, sacred areas, ruins) |
| 7 | `generate_historical_layers(...)` | `pipeline.cpp:222` | no | eras and events |
| 8 | `generate_population_regions(cells, political_regions, cultural_layers)` | `pipeline.cpp:230` | no | `society.population_regions` |
| 9 | `generate_conflicts(...)` | `pipeline.cpp:235` | no | `society.conflicts` |
| 10 | `generate_dynasties(...)` | `pipeline.cpp:243` | no | `society.dynasties` |
| 11 | `generate_territorial_snapshots(params, cells, political_regions, settlements, cultural_layers, historical_layers, population_regions, conflicts)` | `pipeline.cpp:250`, implemented at `cpp/src/engine/history.cpp:773` | no | `society.territorial_snapshots` |

Stages 3 and 6 are the only ones in this layer that write back into the shared `Cell` array, and both do so *before* any consumer reads those fields — stage 4 reads `political_region_id` written by stage 3, stage 6 reads it again, and `generate_territorial_snapshots` reads it once more. That ordering is load-bearing and is one of the stated engine invariants ("preserve pipeline order").

The Python declaration wrappers do not recompute the native physical equations, but on the current path they audit exact native social sources, coverage and owned outputs before publishing metadata. The historical call-site references below describe the original layout; the current dependency order is summarized in the [availability contract](../../settlement_social_availability.md#source-order), including the later social consumers and final graph links.

## Political region formation

`generate_political_regions` (`cpp/src/engine/civilization.cpp:85`) has five phases.

**Phase 0 — reset.** Every `settlement.region_id` and every `cell.political_region_id` is set to `-1` (`civilization.cpp:91`–`96`). With no settlements the function returns an empty vector immediately (`civilization.cpp:97`).

**Phase 1 — target region count.** `civilization.cpp:101`:

```
target_regions = clamp(settlement_count / 5 + 1, 1, min(10, settlement_count))
```

with the engine's `clamp(v, lo, hi) = max(lo, min(hi, v))` (`cpp/src/engine/model.hpp:17`). Integer division truncates. The Python mirror is `max(1, min(min(10, len(settlements)), len(settlements) // 5 + 1))` (`src/magic_geo/political_geography.py:30`–`34`).

**Phase 2 — greedy capital selection.** Settlements are walked in id order. A settlement becomes a capital unless it is within **0.18 rad** angular distance of an already-chosen capital (`civilization.cpp:103`–`118`). Selection stops as soon as `target_regions` capitals exist. If the loop somehow selects none, the first settlement is forced in (`civilization.cpp:119`–`121`). Region ids are assigned in capital-selection order, and each region's `type` comes from `political_region_type_for_capital` (`civilization.cpp:5`):

| Priority | Condition (capital settlement + its cell) | Region type |
|---|---|---|
| 1 | `settlement.type == port` | `maritime_league` |
| 2 | `settlement.type == river_city` **or** `cell.is_river` | `river_realm` |
| 3 | `settlement.type == mining_town` **or** `cell.resource` ∈ {`volcanic_arc_metals`, `craton_iron_gold`, `placer_metals`, `geothermal`} | `mining_domain` |
| 4 | `cell.elevation_m > 1200.0` **or** `cell.landform` ∈ {`mountain_belt`, `glacial_valley`} | `mountain_march` |
| 5 | `settlement.type == agricultural_town` **or** `cell.fertility > 0.68` **or** `cell.resource == fertile_alluvium` | `agrarian_state` |
| 6 | otherwise | `frontier_territory` |

Enum strings come from `POLITICAL_REGION_TYPE_NAMES` (`cpp/src/engine/schema_names.hpp:57`).

**Phase 3 — non-capital settlement assignment.** Each remaining settlement is assigned to the region whose capital minimizes `settlement_region_cost` (`civilization.cpp:25`):

```
cost = angular_distance(a.p, b.p) * radius_km * route_barrier_cost(a, b)
cost *= 0.76   if a.basin_id == b.basin_id and (a.is_river or b.is_river)
cost *= 0.72   if both endpoints have a water neighbour
cost *= 0.45   if a direct route of type coastal_sea links the pair
cost *= 0.58   if a direct route of any other type links the pair
```

The route discount uses the **first** matching route found in `routes` order and breaks (`civilization.cpp:41`–`48`). `route_barrier_cost` is the shared settlement-layer barrier (`cpp/src/engine/settlements.cpp:80`):

```
mountain        = clamp((max(a.elevation_m, b.elevation_m) - 1200.0) / 2600.0, 0, 1)
tectonic_hazard = 0.5*(a.boundary_convergent + b.boundary_convergent)
                + 0.25*(a.boundary_transform + b.boundary_transform)
arid            = 0.18 if either biome is cold_desert or hot_desert else 0.0
barrier         = 1.0 + 0.95*mountain + 0.45*clamp(tectonic_hazard, 0, 1) + arid
```

**Phase 4 — cell partition.** `assign_cell_regions` (`civilization.cpp:52`) is an OpenMP `parallel for schedule(static)` over all cells. Water cells get `-1`. Land cells take the region of the *cheapest capital* under the same great-circle × barrier cost, but with different discounts and **no** route discount (`civilization.cpp:69`–`75`):

```
cost *= 0.80   if same basin and either endpoint is a river cell
cost *= 0.76   if both endpoints have a water neighbour
```

Because each capital's own cell has zero angular distance to itself, every region ends up with at least one land cell in practice. The partition is a pure nearest-capital Voronoi in a barrier-weighted metric — **there is no contiguity constraint**, so a region's territory may be disconnected.

**Phase 5 — aggregation.** `civilization.cpp:158`–`218` accumulates per-region statistics: settlement membership and count, `mean_settlement_score` (arithmetic mean of member settlement scores), `route_count` (routes whose *both* endpoints are in the region), area-weighted `mean_elevation_m`, area-weighted `barrier_pressure` = mean of `clamp(local_relief(cell)/1800, 0, 1)`, and the dominant biome/resource. `local_relief` is `max(0, elevation - mean neighbour elevation)` (`cpp/src/engine/climate.cpp:15`).

Dominant-field resolution walks a `std::map<int,int>` histogram in ascending native enum order and takes the first strict maximum, so ties resolve to the **lowest enum index**. `dominant_resource` skips index 0 (`none`) and stays `none` when no non-zero resource occurs (`civilization.cpp:209`–`217`). The declared contract name is `count_then_native_enum_order_with_nonzero_resource_v1`.

## Political region record fields

Serialized by `political_regions_json` (`cpp/src/engine/entity_serialization.cpp:630`) under top-level key `political_regions` (`cpp/src/engine/world_serialization.cpp:223`). All doubles use plain `output.float_precision`.

| Field | Type | Meaning | Source |
|---|---|---|---|
| `id` | int | Sequential region id in capital-selection order | `civilization.cpp:129` |
| `capital_settlement_id` | int | Settlement id of the capital | `civilization.cpp:130` |
| `type` | enum str | One of `POLITICAL_REGION_TYPE_NAMES` (6 values) | `civilization.cpp:131` |
| `dominant_biome` | enum str | Modal biome over assigned land cells, lowest-enum tiebreak | `civilization.cpp:200`–`208` |
| `dominant_resource` | enum str | Modal non-`none` resource, `none` if all cells are `none` | `civilization.cpp:209`–`217` |
| `settlement_count` | int | Member settlements | `civilization.cpp:166` |
| `route_count` | int | Routes with both endpoints inside the region | `civilization.cpp:169`–`179` |
| `settlement_ids` | int[] | Member settlement ids in settlement id order | `civilization.cpp:165` |
| `area_km2` | double | Sum of assigned land cell areas | `civilization.cpp:186` |
| `mean_settlement_score` | double | Arithmetic mean of member `settlement.score` | `civilization.cpp:167`, `194` |
| `mean_elevation_m` | double | Area-weighted mean elevation | `civilization.cpp:187`, `197` |
| `barrier_pressure` | double | Area-weighted mean of `clamp(local_relief/1800, 0, 1)` | `civilization.cpp:188`, `198` |

## The border segment model

`generate_border_segments` (`cpp/src/engine/civilization.cpp:242`) enumerates **undirected mesh adjacency edges between non-water cells assigned to different regions**. Cells are walked in ascending id and neighbours in exported neighbour order, with `neighbor_id <= cell.id` skipped so each edge appears once (`civilization.cpp:248`–`249`). Record order is therefore `ascending_cell_id_then_exported_neighbor_order_v1`.

Segment type comes from `border_type_for_cells` (`civilization.cpp:222`), evaluated in strict priority order on the *pair* — either side satisfying the predicate is enough:

| Priority | Condition | Border type |
|---|---|---|
| 1 | either cell `is_river` | `river` |
| 2 | either `landform` ∈ {`mountain_belt`, `glacial_valley`} **or** either `elevation_m > 1400.0` | `mountain` |
| 3 | either `biome` ∈ {`cold_desert`, `hot_desert`} | `desert` |
| 4 | either `landform == ice_field` **or** either `biome == ice_cap` | `ice` |
| 5 | either `landform == coastal_plain` | `coastal` |
| 6 | otherwise | `open_lowland` |

Length is the great-circle distance between the two cell centres, floored at 1 m by the shared helper: `length_km = neighbor_distance_m(params, a, b) / 1000.0` where `neighbor_distance_m = max(1.0, angular_distance * radius_km * 1000)` (`cpp/src/engine/hydrology.cpp:209`), i.e. effectively `max(0.001, angular_distance * radius_km)`.

Barrier score (`civilization.cpp:264`–`272`):

```
relief  = |a.elevation_m - b.elevation_m|
hazard  = 0.50*(a.boundary_convergent + b.boundary_convergent)
        + 0.25*(a.boundary_transform  + b.boundary_transform)
score   = clamp(0.18 + relief/2500.0 + 0.45*hazard
                + (0.34 if type in {mountain, desert, ice} else 0.0), 0, 1)
```

Note the hard-type bonus fires for `mountain`, `desert` and `ice` only — **not** for `river` or `coastal`. The published parameter block (`src/magic_geo/political_geography.py:78`–`85`) names these exactly: `base` 0.18, `relief_scale_m` 2500.0, `convergent_pair_weight` 0.50, `transform_pair_weight` 0.25, `tectonic_weight` 0.45, `hard_type_bonus` 0.34, plus `mountain_elevation_threshold_m` 1400.0.

This is a **cell-centre adjacency model**, not an exact polygon boundary. The declared limitation string is verbatim `cell_center_adjacency_segments_without_exact_native_edge_polygons_or_negotiated_boundaries`. Exact cell-edge polylines between political regions exist only as a separate Python product, `territorial_boundary_segments` (see [Downstream consumers](#downstream-consumers-of-the-political-layer)).

## Border segment record fields

Serialized by `borders_json` (`cpp/src/engine/process_serialization.cpp:4439`) under top-level key `borders` (`cpp/src/engine/world_serialization.cpp:277`). Eight fields: five ints, one enum string, and two doubles (`length_km`, `barrier_score`) emitted at `output.float_precision`.

| Field | Type | Meaning |
|---|---|---|
| `id` | int | Sequential in enumeration order |
| `region_a` | int | `min` of the two region ids |
| `region_b` | int | `max` of the two region ids |
| `cell_a` | int | The lower-id cell of the edge (the outer-loop cell) |
| `cell_b` | int | The higher-id neighbour |
| `type` | enum str | One of `BORDER_TYPE_NAMES` = `open_lowland`, `river`, `mountain`, `desert`, `ice`, `coastal` (`schema_names.hpp:61`) |
| `length_km` | double | `max(0.001, angular_distance * radius_km)` |
| `barrier_score` | double | Formula above, clamped to `[0, 1]` |

## The natural-border fraction

The native summary metric `natural_border_fraction` is the **unweighted count fraction of border segments whose `type` is not `open_lowland`** (`cpp/src/engine/summary.cpp:760`–`765`, emitted at `summary.cpp:1898`). It ignores `barrier_score` and ignores segment length.

Two other "natural border" quantities exist and are **not** the same number:

| Quantity | Definition | Where |
|---|---|---|
| `summary.natural_border_fraction` | count fraction of segments with `type != open_lowland` | `cpp/src/engine/summary.cpp:763` |
| `worldbuilding_realism_checks[natural_border_alignment].value` | **length-weighted** fraction of segments with `type != open_lowland` **or** `barrier_score >= 0.45`; target interval `[0.4, 1.0]` | `src/magic_geo/worldbuilding_realism.py:273`–`303` |
| `natural_frontiers` candidacy | a border is a frontier candidate when `type != open_lowland` **or** `barrier_score >= NATURAL_FRONTIER_THRESHOLD = 0.45` | `src/magic_geo/natural_frontiers.py:7`, `74` |

## Trade flows and interregional trade

`generate_trade_flows` (`cpp/src/engine/civilization.cpp:323`) emits exactly **one flow per valid route, in route order** (`one_flow_per_valid_route_in_route_order_v1`). A route with an out-of-range endpoint index is skipped without emitting a record (`civilization.cpp:331`–`335`).

Primary good (`primary_trade_good`, `civilization.cpp:299`) scans the two endpoint cells in the order `(from_cell.resource, to_cell.resource)` and keeps the non-`none` resource with the strictly highest priority, so a tie favours the *from* endpoint:

| Resource | Priority | Resource | Priority |
|---|---|---|---|
| `volcanic_arc_metals` | 6 | `geothermal` | 4 |
| `craton_iron_gold` | 6 | `fertile_alluvium` | 3 |
| `placer_metals` | 6 | `coastal_fisheries` | 2 |
| `sedimentary_fuels` | 5 | `none` | 0 |
| `evaporites` | 5 | | |

If no endpoint carries a resource, two fallbacks fire in order (`civilization.cpp:314`–`319`): either settlement being a `port` **or** either cell having a water neighbour yields `coastal_fisheries`; otherwise either cell with `fertility > 0.62` yields `fertile_alluvium`; otherwise `none`.

Volume (`civilization.cpp:340`–`352`):

```
friction            = route.cost / max(1.0, route.distance_km)
resource_bonus      = 0.00                     if primary_good == none
                    = 0.16                     if primary_good in {fertile_alluvium, coastal_fisheries}
                    = 0.30                     otherwise
fertility_complement= |a.fertility - b.fertility|
climate_complement  = clamp(|a.temperature_c - b.temperature_c| / 45.0, 0.0, 0.55)
region_bonus        = 0.22 if interregional else 0.0
route_bonus         = 0.25 coastal_sea | 0.18 river_corridor | -0.10 mountain_pass | 0.0 overland
endpoint_strength   = 0.5 * (from.score + to.score)
volume              = 80.0 * endpoint_strength
                      * (1 + resource_bonus + 0.35*fertility_complement
                           + 0.25*climate_complement + region_bonus + route_bonus)
                      / (0.55 + friction)
volume_index        = clamp(volume, 0.0, 100.0)
```

`interregional` requires **both** endpoint `region_id` values `>= 0` and different (`civilization.cpp:346`). The derived summary metric `interregional_trade_fraction` is the count fraction of flows with `interregional == true` (`cpp/src/engine/summary.cpp:769`–`771`, emitted at `summary.cpp:1827`), and `mean_trade_friction` is the arithmetic mean of `friction` (`summary.cpp:1829`).

The interregional flag and volume threshold matter downstream: language-region union in `generate_cultural_layers` only merges cultures across a flow with `volume_index >= 70.0` **and** `friction <= 0.92`.

## Trade flow record fields

Serialized by `trade_flows_json` (`cpp/src/engine/entity_serialization.cpp:404`) under top-level key `trade_flows` (`world_serialization.cpp:287`). Struct at `cpp/src/engine/types/world.hpp:28`.

| Field | Type | Meaning |
|---|---|---|
| `id` | int | Sequential in flow-emission order |
| `route_id` | int | The originating `routes[]` id |
| `from` | int | Source settlement id (equals `route.from`) |
| `to` | int | Target settlement id |
| `region_from` | int | `settlement.region_id` of the source, `-1` if unassigned |
| `region_to` | int | `settlement.region_id` of the target |
| `primary_good` | enum str | One of `RESOURCE_NAMES` (9 values, `schema_names.hpp:27`) |
| `interregional` | bool | Both regions valid and different |
| `distance_km` | double | Copied from `route.distance_km` |
| `friction` | double | `route.cost / max(1.0, route.distance_km)` |
| `volume_index` | double | Clamped to `[0, 100]` |

## Cultural layer generation

`generate_cultural_layers` (`cpp/src/engine/civilization.cpp:608`) ignores `params` entirely (`(void)params;` at line 616) and returns a `CulturalLayers` aggregate of four vectors (`cpp/src/engine/types/world.hpp:108`). If `political_regions` is empty it returns immediately with all four vectors empty (`civilization.cpp:626`).

**Cultures do not spread.** There is exactly **one culture per political region**, created in political-region record order (`one_culture_per_political_region_in_record_order_v1`, `civilization.cpp:636`–`649`). Each culture's `homeland_region_id` is its political region, and every non-water cell inherits its region's culture verbatim (`civilization.cpp:651`–`657`). The culture map is therefore *identical* to the political map by construction — there is no diffusion kernel, no frontier advance and no identity change. The declared limitation is verbatim `static_political_homelands_without_cultural_diffusion_identity_change_or_population_feedback`.

Culture type (`culture_type_for_region`, `civilization.cpp:371`) is derived from the political region, not from the cells:

| Priority | Condition on the political region | Culture type |
|---|---|---|
| 1 | `region.type == maritime_league` | `maritime` |
| 2 | `region.type == river_realm` | `river_valley` |
| 3 | `region.type == mountain_march` **or** `region.mean_elevation_m > 1100.0` | `highland` |
| 4 | `region.dominant_biome` ∈ {`cold_desert`, `hot_desert`} | `desert_oasis` |
| 5 | `region.type == mining_domain` **or** `region.dominant_resource` ∈ {`volcanic_arc_metals`, `craton_iron_gold`, `placer_metals`, `geothermal`} | `mining_frontier` |
| 6 | `region.dominant_biome` ∈ {`tundra`, `boreal_forest`} | `boreal_frontier` |
| 7 | `region.dominant_biome` ∈ {`savanna`, `tropical_seasonal_forest`, `tropical_rainforest`} | `forest_realm` |
| 8 | otherwise | `agrarian_lowland` |

Per-cell aggregation (`civilization.cpp:665`–`681`) adds area, area-weighted fertility and elevation, plus two land-use sub-areas:

| Sub-area | Predicate | Line |
|---|---|---|
| `agricultural_area_km2` | `fertility > 0.62` **or** `resource == fertile_alluvium` **or** `landform` ∈ {`floodplain`, `delta`} | `civilization.cpp:673` |
| `mining_area_km2` | `resource` ∈ {`volcanic_arc_metals`, `craton_iron_gold`, `placer_metals`, `geothermal`} | `civilization.cpp:676` |

The published model records `agricultural_fertility_threshold: 0.62` with `agricultural_fertility_threshold_semantics: "raw_strict_greater_than_v1"` and `source_fertility_serialization_decimals: 8` (`src/magic_geo/cultural_geography.py:27`–`29`) — the threshold applies to the *raw* double, and consumers replaying it from the serialized world must account for `cells[].fertility` being emitted at `max(8, float_precision)` decimals.

Two contact indices are then derived:

```
barrier_isolation   = Σ(border.barrier_score * border.length_km) / Σ(border.length_km)
                      over borders whose two regions map to different cultures,
                      accumulated on *both* sides                     (civilization.cpp:683–698)
trade_contact_index = clamp(Σ incident flow volume_index
                            / (100.0 * max(1, settlement_count)), 0, 1)  (civilization.cpp:740)
```

`trade_volume` accumulates on both endpoint cultures for **every** flow whose two regions map to valid cultures, including intra-culture flows where `a == b` — in that case the culture is credited twice (`civilization.cpp:713`–`714`). `barrier_sum` and `border_length` accumulate only when `a != b`.

Then, per culture (`civilization.cpp:734`–`792`):

```
migration_pressure = clamp(0.18 + 0.28*(1 - barrier_isolation) + 0.22*trade_contact_index
                           + 0.16*(1 - mean_fertility)
                           + 0.12*clamp(mean_elevation_m/1800, 0, 1), 0, 1)
continuity_index   = clamp(0.30 + 0.22*barrier_isolation + 0.18*mean_fertility
                           + 0.10*min(1, settlement_count/6)
                           + 0.10*min(1, sacred_area_count/3)
                           - 0.16*min(1, ruin_count/4), 0, 1)
estimated_age_years= clamp(420 + 1900*continuity_index + 520*barrier_isolation
                           + 260*min(1, settlement_count/8), 120, 4200)
```

**Cultural continuity is computed twice on the available path.** The original first evaluation at `civilization.cpp:767`–`782` precedes site placement; the second evaluation includes the real sacred/ruin counts. Current publication uses that second-pass value only when the relevant ruin inference is available; otherwise `ruin_count`, `continuity_index` and `estimated_age_years` are null under their dedicated flags. `recorded_ruin_count` remains the emitted count. A culture with no eligible local ruin candidates has a known zero even if another culture makes global selection incomplete. Independent `migration_pressure`, sacred-site and language quantities are retained.

Note also the sequencing consequence: site placement uses `culture_region_id`, which depends on the political partition; culture continuity then depends on site counts; and territorial-snapshot stability depends on culture continuity. The chain is one-directional — nothing feeds back into the political partition.

## Culture region record fields

Serialized by `cultures_json` (`cpp/src/engine/entity_serialization.cpp:655`) under top-level key `cultures` (`world_serialization.cpp:228`). Struct at `cpp/src/engine/types/world.hpp:42`. 20 fields.

| Field | Type | Meaning |
|---|---|---|
| `id` | int | Sequential in political-region order |
| `language_region_id` | int | Assigned by the trade-union pass |
| `homeland_region_id` | int | The political region this culture is the culture of |
| `type` | enum str | One of `CULTURE_TYPE_NAMES` (8 values, `schema_names.hpp:64`) |
| `dominant_biome` | enum str | Modal biome recomputed over the culture's own cells; the political region's value survives only if the culture has no cells (`civilization.cpp:741`) |
| `dominant_resource` | enum str | Modal non-`none` resource over the culture's own cells |
| `settlement_count` | int | Copied from the political region |
| `sacred_area_count` | int | Sacred sites placed inside this culture |
| `ruin_count` | int or null | Inferred count when `ruin_count_available`; `recorded_ruin_count` separately counts emitted ruins |
| `settlement_ids` | int[] | Copied from the political region |
| `area_km2` | double | Sum of assigned non-water cell areas |
| `agricultural_area_km2` | double | Sub-area under the agricultural predicate |
| `mining_area_km2` | double | Sub-area under the mining predicate |
| `mean_fertility` | double | Area-weighted mean of `cells[].fertility` |
| `mean_elevation_m` | double | Area-weighted mean elevation |
| `barrier_isolation` | double | Border-length-weighted mean barrier score across cross-culture borders |
| `trade_contact_index` | double | `clamp(incident volume / (100 × max(1, settlements)), 0, 1)` |
| `migration_pressure` | double | First-pass formula, never recomputed |
| `continuity_index` | double or null | **Second-pass** value when `continuity_estimate_available` |
| `estimated_age_years` | double or null | Available second-pass value bounded `[120, 4200]`; shares the continuity flag |

`mean_fertility` and `mean_elevation_m` are divided by `area_km2` only when `area_km2 > 0` (`civilization.cpp:735`–`738`); `barrier_isolation` is `0.0` when the culture has no cross-culture border length.

## Language regions, families and lineages

Language regions are formed by **union-find over high-volume, low-friction trade** (`minimum_root_union_on_high_volume_low_friction_interregional_trade_v1`).

**Union pass** (`civilization.cpp:700`–`718`). `parent` is initialized to identity over cultures. For every trade flow whose two regions map to valid, *different* cultures with `volume_index >= 70.0` **and** `friction <= 0.92`, the two culture roots are unioned. `union_roots` (`civilization.cpp:488`) always attaches the **larger** root to the smaller, so a component's representative is its minimum culture id. `find_root` (`civilization.cpp:475`) does full path compression.

**Language ids** (`civilization.cpp:720`–`732`). Cultures are walked in id order; each new root gets the next sequential language id (`union_root_first_culture_order_v1`). `layers.language_regions` is then `resize`d to the number of roots, so every field starts at its struct default — notably `phoneme_inventory_size = 0` and `inherited_phonology_fraction = 1.0` (`types/world.hpp:65`).

**Aggregation** (`civilization.cpp:784`–`808`). Each language accumulates `culture_count`, `settlement_count`, `area_km2`, area-weighted `barrier_isolation` and `trade_contact_index`, and `culture_ids`. Family area is accumulated per language as `language_family_area[lang][family_of(culture)] += culture.area_km2` using `language_family_for_culture` (`civilization.cpp:397`):

| Culture type | Language family | Base phoneme inventory |
|---|---|---|
| `river_valley` | `riverine` | 27 |
| `maritime` | `coastal` | 31 |
| `highland` | `highland` | 34 |
| `desert_oasis` | `arid` | 24 |
| `agrarian_lowland` | `lowland` | 29 |
| `mining_frontier`, `boreal_frontier`, `forest_realm` | `frontier` | 30 |

Base inventories are from `base_phoneme_inventory_for_family` (`civilization.cpp:414`) and are republished verbatim in `language_region_model.base_phoneme_inventory_by_family` (`src/magic_geo/cultural_geography.py:80`–`87`). The language's `family` is the family with the largest accumulated area, with ties resolving to the **lowest family enum index** (map iteration order, strict `>` at `civilization.cpp:802`).

**Lineage** (`civilization.cpp:809`–`866`). Languages are grouped by family in ascending family id; within each family, members are sorted by **descending area, ties by ascending id**. The first member becomes the family root (`parent_language_region_id = -1`, `lineage_depth = 0`); every other member of the same family gets that root as parent with `lineage_depth = 1`. **The lineage is exactly one generation deep — there is no deeper tree.** For all members:

```
change_rate = clamp(0.16 + 0.48*barrier_isolation - 0.26*trade_contact_index
                    + 0.08*min(1, culture_count/4), 0, 1)
divergence_age_years (root)  = clamp(900 + 2100*(1 - change_rate)
                                     + 380*barrier_isolation, 250, 4200)
divergence_age_years (child) = clamp(220 + 1700*barrier_isolation
                                     + 820*(1 - trade_contact_index), 120, 3200)
```

**Global fallback** (`civilization.cpp:838`–`866`). If *no* language ended up with a parent (every family has exactly one member) and there is more than one language, the largest-area language becomes a global root — ties keep the earliest id, because the scan uses a strict `>` starting from index 0. Every other language then gets `lineage_depth = 1`, `change_rate += 0.08` (clamped) and

```
divergence_age_years = clamp(280 + 1500*barrier_isolation
                             + 680*(1 - trade_contact_index), 120, 3000)
```

**Phonology derivation** — `derive_language_phonology` (`civilization.cpp:431`), called once at `civilization.cpp:868`:

```
sound_shift_index (root)  = clamp(0.04 + 0.16*change_rate, 0.0, 0.28)
sound_shift_index (child) = clamp(0.10 + 0.42*change_rate
                                  + 0.28*clamp(divergence_age_years/3200, 0, 1)
                                  + 0.18*barrier_isolation
                                  - 0.14*trade_contact_index, 0, 1)
inherited_phonology_fraction = 1.0                          if root
                             = clamp(1 - 0.78*sound_shift_index, 0, 1)  if child
parent_inventory = parent's phoneme_inventory_size if the parent id is in range
                   AND that value is already > 0; else the family base inventory
innovation = 8.0*sound_shift_index + 4.0*barrier_isolation
           - 3.0*trade_contact_index + 1.6*lineage_depth
phoneme_inventory_size = clamp(lround(parent_inventory
                               * (0.72 + 0.28*inherited_phonology_fraction)
                               + innovation), 16, 58)
phonological_complexity = clamp(0.20 + 0.44*(phoneme_inventory_size/58)
                                + 0.20*barrier_isolation + 0.10*sound_shift_index
                                - 0.10*trade_contact_index
                                + 0.04*lineage_depth, 0, 1)
```

`derive_language_phonology` iterates in **language id order**, and `phoneme_inventory_size` defaults to `0`. Consequently, when a child's record id precedes its parent's, the `> 0` guard fails and the child falls back to its **family base inventory** rather than the parent's derived inventory. That is the implemented behaviour, mirrored exactly by the validator (`src/magic_geo/cultural_geography_validation.py:678`–`680`); it is a real ordering dependency, not a bug report.

Finally, `cell.language_region_id` is set from the cell's culture (`civilization.cpp:870`–`874`) and each settlement copies both ids from its own cell (`civilization.cpp:875`–`879`).

## Language region record fields

Serialized by `language_regions_json` (`cpp/src/engine/entity_serialization.cpp:688`) under top-level key `language_regions` (`world_serialization.cpp:233`). Struct at `types/world.hpp:65`. 16 fields.

| Field | Type | Meaning |
|---|---|---|
| `id` | int | Sequential union-root discovery order |
| `parent_language_region_id` | int | Family root, or `-1` for a root |
| `family` | enum str | One of `LANGUAGE_FAMILY_NAMES` = `riverine`, `coastal`, `highland`, `arid`, `lowland`, `frontier` (`schema_names.hpp:68`) |
| `lineage_depth` | int | `0` for roots, `1` for children — never deeper |
| `culture_count` | int | Cultures merged into this language |
| `settlement_count` | int | Sum of member culture settlement counts |
| `culture_ids` | int[] | Member culture ids in culture id order |
| `area_km2` | double | Sum of member culture areas |
| `barrier_isolation` | double | Area-weighted mean of member culture isolation |
| `trade_contact_index` | double | Area-weighted mean of member culture contact |
| `divergence_age_years` | double | Root or child formula, bounded per branch |
| `change_rate` | double | `[0, 1]` |
| `phoneme_inventory_size` | int | Bounded `[16, 58]` |
| `phonological_complexity` | double | `[0, 1]` |
| `sound_shift_index` | double | Roots bounded `[0, 0.28]`; children `[0, 1]` |
| `inherited_phonology_fraction` | double | Exactly `1.0` for roots; `clamp(1 - 0.78·shift)` for children |

The Python `phonology_history` enricher **annotates these same records in place** with fourteen further keys — see [The phonology history model](#the-phonology-history-model).

## Sacred areas and ruins

Both site families retain the ranked-greedy-with-minimum-separation equations (`causal_terrain_culture_ranked_sacred_ruin_sites_v2`). Sacred-site inputs remain independent. Current ruin selection additionally requires complete support over its actual global candidate domain; an incomplete ranking emits no partial selected list and publishes unavailable inference rather than a known-zero ruin result.

Shared minimum separation (`civilization.cpp:898`–`900`):

```
site_min_sep = 1.4 * sqrt(4π / max(1, cell_count))     # radians
```

For comparison, settlement selection uses factor **2.4** with the same expression (`cpp/src/engine/settlements.cpp:51`). Sacred areas and ruins are separated **only within their own family** — a ruin may sit arbitrarily close to a sacred area.

**Sacred candidates.** Non-water cells with `culture_region_id >= 0` and `significance >= 0.30`. `sacred_significance_for_cell` (`civilization.cpp:496`) is an additive score clamped to `[0, 1]`:

| Term | Condition | Contribution |
|---|---|---|
| High terrain | `elevation_m > 1700.0` or `landform` ∈ {`mountain_belt`, `glacial_valley`} | +0.34 |
| Water | `is_river` or `is_lake` or `water_body_type` ∈ {`fresh_lake`, `saline_basin`} | +0.18 |
| Geothermal / volcanic | `resource == geothermal` or `landform == volcanic_arc` | +0.26 |
| Salt / closed basin | `landform == salt_flat` or `is_closed_basin` | +0.22 |
| Fertile and wet | `fertility > 0.74` **and** `precipitation_mm_y > 650.0` | +0.16 |
| Coastal | any water neighbour | +0.12 |
| Relief | `0.12 * clamp(local_relief/1700, 0, 1)` | 0 … +0.12 |

`sacred_area_type_for_cell` (`civilization.cpp:520`), strict priority:

| Priority | Condition | Sacred type |
|---|---|---|
| 1 | `resource == geothermal` or `landform == volcanic_arc` | `volcanic_sanctuary` |
| 2 | `elevation_m > 1700.0` or `landform` ∈ {`mountain_belt`, `glacial_valley`} | `mountain_shrine` |
| 3 | `is_river` or `is_lake` or `water_body_type` ∈ {`fresh_lake`, `saline_basin`} | `spring_oracle` |
| 4 | `biome` ∈ {`boreal_forest`, `temperate_forest`, `tropical_rainforest`, `wetland`} | `sacred_grove` |
| 5 | `biome` ∈ {`cold_desert`, `hot_desert`} or `landform == salt_flat` | `desert_sanctuary` |
| 6 | any water neighbour | `ancestral_coast` |
| 7 | otherwise | `sacred_grove` |

**Ruin candidates.** Non-water cells with `culture_region_id >= 0`, **not** currently occupied by a settlement (`active_settlement_cell`, `civilization.cpp:929`–`937`), and `significance >= 0.32`. `ruin_significance_for_cell` (`civilization.cpp:542`) is a product of two terms:

```
historical_potential = 0.18 + 0.38*settlement_score + 0.24*fertility
                     + 0.14   if is_river or is_lake or coastal
                     + 0.16   if resource in {volcanic_arc_metals, craton_iron_gold,
                                              sedimentary_fuels, evaporites,
                                              placer_metals, geothermal, fertile_alluvium}
abandonment_pressure = 0.24   if biome in {cold_desert, hot_desert} or precipitation_mm_y < 220
                     + 0.22   if ice_thickness_m > 20 or biome == ice_cap
                     + 0.18   if water_body_type == saline_basin or landform == salt_flat
                               or is_closed_basin
                     + 0.18 * clamp(boundary_convergent + boundary_transform, 0, 1)
                     + 0.12 * clamp(local_relief/1800, 0, 1)
                     + 0.10   if settlement_score < 0.52
significance = clamp(historical_potential * (0.55 + abandonment_pressure), 0, 1)
```

`ruin_type_for_cell` (`civilization.cpp:570`) and `abandonment_reason_for_cell` (`civilization.cpp:589`), both strict priority:

| Priority | Ruin type condition | Ruin type | Abandonment condition | Reason |
|---|---|---|---|---|
| 1 | `resource` ∈ {`volcanic_arc_metals`, `craton_iron_gold`, `placer_metals`, `geothermal`} | `abandoned_mine` | `biome` ∈ {`cold_desert`, `hot_desert`} or `precipitation_mm_y < 220` | `aridity` |
| 2 | `biome` ∈ {`cold_desert`, `hot_desert`} or `landform == salt_flat` | `desert_outpost` | `boundary_convergent + boundary_transform > 0.45` | `tectonic_hazard` |
| 3 | `elevation_m > 1300.0` or `landform` ∈ {`mountain_belt`, `glacial_valley`} | `mountain_fortress` | `ice_thickness_m > 20` or `biome == ice_cap` | `glaciation` |
| 4 | any water neighbour | `old_harbor` | `water_body_type == saline_basin` or `landform == salt_flat` or `is_closed_basin` | `salinization` |
| 5 | `ice_thickness_m > 20` or `biome == ice_cap` | `glacial_relic` | `settlement_score < 0.48` | `trade_decline` |
| 6 | otherwise | `ruined_city` | otherwise | `frontier_isolation` |

Ruin preservation (`civilization.cpp:972`–`978`):

```
preservation_score = clamp(0.35 + 0.20*[biome is cold_desert or hot_desert]
                                + 0.20*[ice_thickness_m > 20]
                                - 0.18*[precipitation_mm_y > 1200], 0, 1)
```

**Targets.** Both are upper caps, not guarantees — if candidates run out the loop simply ends with fewer records.

| Family | Target | Source | Candidate threshold | Order |
|---|---|---|---|---|
| Sacred areas | `clamp(2 × culture_count, 2, 24)` | `civilization.cpp:897` | `>= 0.30` | descending raw significance, ties ascending cell id |
| Ruins | `clamp(culture_count + settlement_count/4, 2, 32)` | `civilization.cpp:951` | `>= 0.32` | descending raw significance, ties ascending cell id |

Each accepted site increments its culture's `sacred_area_count` / `ruin_count` (`civilization.cpp:923`, `982`), which is precisely why culture continuity is recomputed afterwards.

## Sacred area and ruin record fields

`sacred_areas_json` (`entity_serialization.cpp:717`) and `ruins_json` (`entity_serialization.cpp:738`); top-level keys `sacred_areas` (`world_serialization.cpp:267`) and `ruins` (`world_serialization.cpp:272`).

| Field | Sacred | Ruin | Meaning |
|---|---|---|---|
| `id` | ✓ | ✓ | Sequential in placement order |
| `cell_id` | ✓ | ✓ | Host cell |
| `culture_region_id` | ✓ | ✓ | Host cell's culture |
| `language_region_id` | ✓ | ✓ | Host cell's language |
| `type` | ✓ | ✓ | `SACRED_AREA_TYPE_NAMES` (6) / `RUIN_TYPE_NAMES` (6), `schema_names.hpp:71`, `:75` |
| `abandonment_reason` | — | ✓ | `ABANDONMENT_REASON_NAMES` (6), `schema_names.hpp:79` |
| `significance` | ✓ | ✓ | Raw candidate score, `[0, 1]` |
| `preservation_score` | — | ✓ | `[0, 1]` |
| `lat_deg` | ✓ | ✓ | `cell.lat * DEG` |
| `lon_deg` | ✓ | ✓ | `cell.lon * DEG` |

`DEG = 180/π` (`cpp/src/engine/constants.hpp:6`).

## Territorial snapshots and polygon geometry quality

`generate_territorial_snapshots` (`cpp/src/engine/history.cpp:773`) builds the region geometry **once** from the final political partition, then emits one snapshot per historical era by *scaling* that base geometry. The four eras are a fixed partition (`default_historical_eras`, `history.cpp:18`): `[4200, 2400]`, `[2400, 1300]`, `[1300, 450]`, `[450, 0]` years BP, with dominant processes `founding`, `expansion`, `fragmentation`, `integration`.

**Base geometry per region** (`history.cpp:794`–`885`):

1. Membership is every non-water cell whose `political_region_id` equals the region (`history.cpp:810`–`828`).
2. A cell is a *boundary cell* if any neighbour is water or belongs to a different region (`history.cpp:829`–`839`).
3. Centroid is the area-weighted mean of `lat_deg` and `lon_deg` (**not** a spherical mean); if a region somehow has zero area weight, the capital settlement's cell coordinates are used (`history.cpp:841`–`853`).
4. The boundary ring is built by `watershed_boundary_ring` (`cpp/src/engine/water_features.cpp:187`) — the same helper watersheds use. Boundary cells are projected onto a tangent plane whose normal is the area-weighted cartesian centre, sorted by `atan2` angle, then **uniformly floor-sampled** down to `min(64, count)` points; if more than two points survive, the first is appended to close the ring. So a ring is at most **65** entries.
5. `boundary_perimeter_km` = `ring_perimeter_km` (`water_features.cpp:235`), the sum of great-circle segment lengths along the closed ring.
6. `dissolved_polygon_area_km2` = `ring_projected_area_km2` (`water_features.cpp:246`), a **centred orthographic shoelace proxy**: ring points are projected onto the same tangent-plane axes scaled by `radius_km` and the shoelace sum is taken; rings shorter than 4 points give `0.0`.
7. `boundary_cell_ids` is uniformly floor-sampled to at most 64 ids by `sampled_ids` (`history.cpp:760`).

**Geometry quality metrics** (`history.cpp:859`–`882`):

| Metric | Formula | Note |
|---|---|---|
| `polygon_area_error_fraction` | `abs(dissolved − area) / area`, only when both `> 0` | Watersheds instead divide by `max(1.0, area)` (`water_features.cpp:345`); snapshots do **not** |
| `compactness_index` | `clamp(4π·dissolved / max(1.0, perimeter²), 0, 1)` | Isoperimetric ratio of the sampled ring |
| `geometry_quality` | `clamp(0.62·area_quality + 0.38·ring_quality, 0, 1)` | `area_quality = clamp(1 − polygon_area_error_fraction, 0, 1)`, `ring_quality = clamp(ring_size/24, 0, 1)` |
| `crosses_antimeridian` | `max(ring lon) − min(ring lon) > 180.0` | Flag only; no ring splitting is performed |

Because `ring_quality` saturates at a ring of 24 points and rings are capped at 64 sampled points, `geometry_quality` is a **sampling-density-and-area-agreement diagnostic**, not a measure of true territorial shape fidelity.

**Per-era scaling** (`history.cpp:887`–`954`). Each snapshot copies the base regions by value and applies:

```
region_conflict    = clamp(Σ conflict.intensity for (region, era) / 2.0, 0, 1)
continuity         = culture.continuity_index  (legacy missing-culture default: 0.5)
stability          = clamp(0.42 + 0.42*continuity - 0.30*region_conflict
                           + 0.10*era.mean_connectivity, 0, 1)
region_area_factor = area_factors[clamp(era.id, 0, 3)] * (0.82 + 0.18*stability)
area_km2                  *= region_area_factor
dissolved_polygon_area_km2*= region_area_factor
boundary_perimeter_km     *= sqrt(region_area_factor)
estimated_population = population.estimated_population
                     * population_factors[clamp(era.id, 0, 3)] * (0.82 + 0.22*stability)
```

with `area_factors = {0.48, 0.78, 0.64, 1.0}` and `population_factors = {0.34, 0.58, 0.74, 1.0}` (`history.cpp:887`–`888`), republished in `territorial_snapshot_model` (`src/magic_geo/territorial_geography.py:25`–`26`). Regions with `cell_count == 0` are skipped entirely (`history.cpp:901`).

Note the algebra: because area and dissolved area scale by the same factor and perimeter by its square root, both `polygon_area_error_fraction` and `compactness_index` are **invariant** under the era scaling except where the `max(1.0, perimeter²)` guard or the `[0, 1]` clamp binds. They are recomputed anyway (`history.cpp:916`–`930`).

Snapshot-level aggregates (`history.cpp:943`–`953`):

```
assigned_land_fraction = clamp(Σ scaled region area / total land area, 0, 1)
largest_share          = largest_region_area_km2 / (assigned_land_fraction * land_area)
fragmentation_index    = clamp(0.72*(region_count > 1 ? 1 - largest_share : 0)
                             + 0.28*(conflict_sum / region_count), 0, 1)
```

`region_area_factor` is at most `1.0 × (0.82 + 0.18 × 1.0) = 1.0`, so the summed scaled area can never exceed the true land area and the `clamp(…, 0, 1)` on `assigned_land_fraction` (`history.cpp:944`) is purely defensive.

## Snapshot region record fields

The scaled numerical fields below describe the available branch. Current records also preserve separately named `base_area_km2`, `base_dissolved_polygon_area_km2` and `base_boundary_perimeter_km` with the physical geometry. Unavailable scaled area, perimeter, polygon diagnostics and stability are null under `geometry_estimate_available`; population has its own `population_estimate_available` flag. IDs, physical membership and base geometry do not become unavailable merely because an era estimate is unavailable.

`snapshot_regions_json` (`entity_serialization.cpp:904`) nested inside `territorial_snapshots_json` (`entity_serialization.cpp:935`); top-level key `territorial_snapshots` (`world_serialization.cpp:257`). Structs at `types/world.hpp:218` and `:239`.

**`territorial_snapshots[]`** — selected fields (numerical rows describe the available branch):

| Field | Type | Meaning |
|---|---|---|
| `id` | int | Sequential in era order |
| `era_id` | int | Source `historical_eras[].id` |
| `dominant_process` | enum str | `HISTORICAL_PROCESS_NAMES` = `founding`, `expansion`, `fragmentation`, `integration` |
| `region_count` | int | Regions with at least one cell |
| `largest_region_id` | int | Region id with the largest scaled area, `-1` if none |
| `regions` | object[] | Snapshot region records (below) |
| `year_bp` | double | `0.5 * (era.start_year_bp + era.end_year_bp)` |
| `assigned_land_fraction` | double | Scaled area over total land area, clamped |
| `estimated_population` | double | Sum of scaled region populations |
| `largest_region_area_km2` | double | Scaled |
| `fragmentation_index` | double | `[0, 1]` |

**`territorial_snapshots[].regions[]`** — selected fields (numerical rows describe the available branch):

| Field | Type | Meaning |
|---|---|---|
| `region_id` | int | Political region id |
| `capital_settlement_id` | int | Copied from the political region |
| `culture_region_id` | int | Via `region_to_culture_map` (`history.cpp:340`), `-1` if absent |
| `language_region_id` | int | The culture's language, `-1` if no culture |
| `cell_count` | int | Base (unscaled) member cell count |
| `crosses_antimeridian` | bool | Ring longitude span `> 180°` |
| `boundary_cell_ids` | int[] | Uniform floor sample, at most 64 |
| `boundary_ring` | `[lat, lon][]` | At most 65 entries including the closing point |
| `area_km2` | double | **Era-scaled** |
| `boundary_perimeter_km` | double | Era-scaled by `sqrt(factor)` |
| `dissolved_polygon_area_km2` | double | Era-scaled orthographic shoelace proxy |
| `polygon_area_error_fraction` | double | `abs(dissolved − area)/area` |
| `compactness_index` | double | `clamp(4π·dissolved / max(1, perimeter²), 0, 1)` |
| `geometry_quality` | double | `0.62·area_quality + 0.38·ring_quality` |
| `estimated_population` | double | Era-scaled population-region value |
| `stability_index` | double | `[0, 1]` |
| `centroid_lat_deg` | double | Area-weighted mean latitude |
| `centroid_lon_deg` | double | Area-weighted mean longitude |

The Python `boundary_geometry` enricher adds six further keys to each of these region records — see below.

## Declaration-only model records

These Python wrappers publish model contracts, parameters, counts and limitations without replacing the native equations. Current social metadata publication first audits its actual native sources and output coverage; missing or malformed current declarations cannot select a historical branch. The table's original absent-input branches describe the retained legacy path. Geography-only generation has its separately declared no-social scope, and successful full publication mirrors each `model_type` into `summary`.

| Enricher | Module | World keys written | Summary keys written | Guard |
|---|---|---|---|---|
| `enrich_world_with_political_geography_models` | `src/magic_geo/political_geography.py:14` | `political_region_model`, `political_border_model`, `trade_flow_model` | same three names → model-type strings | returns unchanged if `cells` is absent or empty (`political_geography.py:17`–`19`) |
| `enrich_world_with_cultural_geography_models` | `src/magic_geo/cultural_geography.py:11` | `culture_region_model`, `language_region_model`, `cultural_site_model` | same three | returns unchanged unless all four of `cultures`, `language_regions`, `sacred_areas`, `ruins` are lists (`cultural_geography.py:16`) |
| `enrich_world_with_civilization_geography_models` | `src/magic_geo/civilization_geography.py:11` | `population_region_model`, `conflict_model`, `dynasty_model` | same three | returns unchanged unless `population_regions` and `conflicts` are lists |
| `enrich_world_with_territorial_geography_model` | `src/magic_geo/territorial_geography.py:9` | `territorial_snapshot_model` | `territorial_snapshot_model` | returns unchanged unless `territorial_snapshots` is a list |

Current model-type strings (unchanged submodel equation labels can still end in `_v1`):

| Key | `model_type` |
|---|---|
| `political_region_model` | `causal_capital_barrier_partition_political_regions_v1` |
| `political_border_model` | `causal_adjacent_region_terrain_border_segments_v1` |
| `trade_flow_model` | `causal_route_endpoint_complement_trade_flows_v1` |
| `culture_region_model` | `causal_political_homeland_barrier_trade_culture_regions_v2` |
| `language_region_model` | `causal_trade_union_family_lineage_phonology_v1` |
| `cultural_site_model` | `causal_terrain_culture_ranked_sacred_ruin_sites_v2` |
| `population_region_model` | `causal_area_weighted_capacity_occupancy_population_regions_v2` |
| `conflict_model` | `causal_border_pair_pressure_trade_conflict_selection_v2` |
| `dynasty_model` | `causal_foundation_continuity_pressure_dynasty_lineages_v2` |
| `historical_event_model` | `causal_region_culture_language_trade_site_timeline_v2` |
| `territorial_snapshot_model` | `causal_era_scaled_spherical_region_territorial_snapshots_v2` |
| `phonology_history_model` | `causal_language_era_sound_rule_lexical_diffusion_speaker_history_v2` |
| `natural_frontier_model` | `causal_border_terrain_connected_natural_frontiers_v1` |
| `worldbuilding_realism_model` | `causal_upstream_evidence_worldbuilding_realism_checks_v4` |

The `political_region_model` record additionally carries three *recomputed cross-checks* — `target_count` (recomputed from `len(settlements)`), `capital_count` and `region_count` (both `len(regions)`) — at `political_geography.py:59`–`61`. `political_border_model` carries `border_count` and a sorted `border_type_counts` histogram; `trade_flow_model` carries `route_count`, `flow_count`, `interregional_flow_count`, a sorted `primary_good_counts` histogram and `total_volume_index` rounded to 6 decimals (`political_geography.py:131`–`147`).

Declared limitation strings, carried verbatim into the world document:

| Model | `model_limitation` |
|---|---|
| `political_region_model` | `static_nearest_capital_partition_without_contiguity_constraint_population_feedback_or_state_dynamics` |
| `political_border_model` | `cell_center_adjacency_segments_without_exact_native_edge_polygons_or_negotiated_boundaries` |
| `trade_flow_model` | `diagnostic_static_flow_without_supply_demand_inventory_price_capacity_or_equilibrium_feedback` |
| `culture_region_model` | `static_political_homelands_without_cultural_diffusion_identity_change_or_population_feedback` |
| `language_region_model` | `diagnostic_language_union_and_single_generation_lineage_without_speaker_interaction_or_observed_linguistic_calibration` |
| `cultural_site_model` | `ranked_diagnostic_sites_without_settlement_lifecycle_archaeology_or_temporal_land_use` |
| `population_region_model` | `static_diagnostic_capacity_and_occupancy_without_age_structure_land_use_feedback_disease_or_observed_demographic_calibration` |
| `conflict_model` | `one_diagnostic_conflict_per_adjacent_region_pair_without_strategy_diplomacy_uncertainty_or_observed_war_calibration` |
| `dynasty_model` | `single_linear_dynasty_chain_per_region_without_person_level_succession_branch_competition_or_observed_genealogy_calibration` |
| `territorial_snapshot_model` | `scaled_static_regions_with_sampled_centroid_ordered_rings_not_exact_dynamic_cell_edge_territories` |
| `phonology_history_model` | `synthetic_template_linguistics_without_empirical_language_calibration_individual_speaker_interaction_or_stochastic_transmission` |
| `natural_frontier_model` | `diagnostic_border_endpoint_components_without_exact_native_edge_polygons_boundary_negotiation_or_historical_change` |
| `worldbuilding_realism_model` | `internal_generated_evidence_checks_without_external_historical_geographic_calibration` |

**What civilization geography adds beyond political geography.** `civilization_geography.py` publishes the contracts for three *native* record families that consume the political layer but are generated in `cpp/src/engine/history.cpp`: population regions (density-capacity bounded to `[0.2, 90]` people/km² with `base_people_per_km2 = 1.5`, `agricultural_weight = 64.0`, `site_strength_weight = 12.0`), conflicts (one candidate per sorted region pair with `minimum_candidate_score = 0.24`, `maximum_conflicts_per_region = 2`, `resource_pressure_if_present = 0.72`, `hard_border_trade_bonus = 0.34`, `candidate_score_fertility_weight = 0.08`), and dynasties (`dynasty_count_thresholds = [0.36, 0.66]`, one linear chain per region). Those record families are documented on the [history, demography and economy page](history-demography-and-economy.md); what matters here is the direction of the dependency — borders and trade flows feed conflicts, and culture continuity feeds dynasties and snapshot stability.

The population summary is over modeled regions under `nonwater_political_region_cells_v1`. With no such regions, `estimated_world_population` can be an available zero empty sum even when unsupported dry land exists; a mean without a contributing region can still be unavailable. This is neither a claim that the world is uninhabited nor a human-survival inference. Read the declared membership and [availability scope](../../settlement_social_availability.md#reading-unknown-and-empty-results) before interpreting that zero.

**What territorial geography adds.** `territorial_geography.py` publishes the snapshot geometry contract, including `maximum_boundary_ring_points_before_closure: 64`, `maximum_boundary_cell_ids: 64`, `perimeter_model: great_circle_closed_ring_length_v1`, `dissolved_area_model: centered_orthographic_shoelace_proxy_v1`, the era factor arrays and current availability policies.

## The phonology history model

`enrich_world_with_phonology_history` generates records rather than only declarations. It reads `language_regions`, `historical_eras` and `population_regions`, writes five top-level arrays, annotates the language records in place, and publishes summary values with availability. Its original last-call position (`api.py:265`) is historical; current final graph links follow the audited social consumers.

**Era handling.** `_sorted_eras` (`phonology_history.py:228`) sorts eras by descending `start_year_bp` then ascending `id`. Its synthetic `undated` era for a missing/empty history is a retained legacy fallback, not permission for a current payload to omit required native era coverage.

**Rule count per language** (`_rule_count`, `phonology_history.py:248`):

```
raw = 1 + round(change_rate*4.0 + sound_shift_index*3.0
                + (1 - inherited_phonology_fraction)*2.0 + lineage_depth*0.6)
raw += 1 if trade_contact_index >= 0.70
raw += 1 if barrier_isolation   >= 0.70
count = max(1, min(max(2, era_count + 2), raw))
```

With the standard four native eras the ceiling is 6 rules per language.

**Template selection** is a deterministic index walk over the 12 `RULE_TEMPLATES` (`phonology_history.py:6`–`19`):

```
template[index] = RULE_TEMPLATES[(language_id*5 + index*3 + lineage_depth) % 12]
```

so a language may draw the same template more than once. Each template is `(rule_type, source_segment, target_segment, environment, conditioned_by, inventory_delta)`:

| # | Rule type | Source → target | Environment | Conditioned by | Inventory Δ |
|---|---|---|---|---|---|
| 0 | `lenition` | `p` → `f` | `between_vowels` | `intervocalic_weakening` | −1 |
| 1 | `lenition` | `t` → `th` | `between_vowels` | `intervocalic_weakening` | −1 |
| 2 | `palatalization` | `k` → `ch` | `before_front_vowels` | `front_vowel_contact` | 0 |
| 3 | `vowel_shift` | `a` → `e` | `stressed_open_syllable` | `chain_shift` | 0 |
| 4 | `vowel_shift` | `u` → `o` | `unstressed_syllable` | `vowel_lowering` | 0 |
| 5 | `nasal_assimilation` | `n` → `m` | `before_labials` | `place_assimilation` | 0 |
| 6 | `final_devoicing` | `b` → `p` | `word_final` | `coda_devoicing` | 0 |
| 7 | `vowel_reduction` | `e` → `schwa` | `unstressed_syllable` | `centralization` | −1 |
| 8 | `cluster_simplification` | `kt` → `t` | `coda_cluster` | `cluster_loss` | −1 |
| 9 | `rhotic_change` | `r` → `l` | `after_vowels` | `liquid_merger` | 0 |
| 10 | `epenthesis` | `tr` → `tir` | `complex_onset` | `vowel_epenthesis` | +1 |
| 11 | `affrication` | `d` → `dz` | `before_front_vowels` | `coronal_affrication` | 0 |

**Inventory evolution.** The *final* inventory is the native `phoneme_inventory_size`; the *initial* inventory is back-derived (`phonology_history.py:308`–`309`):

```
net_inventory_delta = Σ chosen template inventory_delta
initial_inventory   = max(8, min(72, final_inventory - net_inventory_delta))
```

Per-era steps then linearly interpolate `round(initial + (final − initial)·progress)` with `progress = (index+1)/era_count`, and the last step is forced to exactly the final inventory (`phonology_history.py:355`, `374`–`377`).

**Sound-shift indexing.** Each step carries `cumulative_sound_shift_index = clamp(native sound_shift_index × progress)` and `inherited_phonology_fraction = clamp(1 − (1 − native inherited)·progress)`, with the last step forced to exactly the native values. So the enricher does **not** re-derive the sound shift — it interpolates the native scalar across eras. The native scalar itself comes from `derive_language_phonology` (see above), and the native `summary.mean_sound_shift_index` / `mean_inherited_phonology_fraction` are plain arithmetic means over language records (`cpp/src/engine/summary.cpp:1890`, `:1892`).

**Rule-level indices** (`phonology_history.py:318`–`321`), with `progress = stage_index / count`:

```
probability_index        = clamp(0.30 + 0.28*change_rate + 0.22*shift + 0.10*contact + 0.10*progress)
lexical_replacement_index= clamp(0.34*(1-inherited) + 0.22*contact + 0.24*change_rate + 0.10*progress)
regularity_index         = clamp(0.82 - 0.16*contact - 0.08*lexical_replacement
                                 + 0.12*isolation + 0.10*inherited)
contact_influence_index  = clamp(0.56*contact + 0.24*(1-isolation)
                                 + (0.10 if parent_id >= 0 else 0.0) + 0.04*progress)
```

**Syllable profile** (`_language_syllable_profile`, `phonology_history.py:143`):

```
profile_score = clamp(0.50*phonological_complexity + 0.18*contact
                      + 0.16*isolation + 0.16*min(1, lineage_depth/6))
syllable_template = first of [(0.22,"CV"), (0.42,"CVC"), (0.58,"CVV"),
                              (0.74,"CCVC"), (1.01,"CVCC")] with profile_score <= threshold
stress_system     = "mobile_contact_stress" if contact >= 0.72
                  | "weight_sensitive"      if profile_score >= 0.66
                  | "initial_stress"        if isolation >= 0.62
                  | "penultimate_stress"    if (language_id + lineage_depth) % 2 == 0
                  | "final_stress"
allowed_coda_count       = 1 + round(profile_score * 5.0)
prosodic_complexity_index= clamp(0.72*profile_score
                                 + (0.10 if weight_sensitive else 0.0) + 0.08*contact)
```

**Lexical correspondence and diffusion.** Twelve proto-roots (`LEXICAL_ROOTS`, `phonology_history.py:21`–`34`) — `water/pana`, `river/taran`, `mountain/kartu`, `stone/bakar`, `sun/sala`, `moon/luma`, `fire/pira`, `grain/naku`, `salt/tasa`, `king/raku`, `road/traka`, `house/domu` — are carried through each language's rules in `stage_index` order by `_derive_form` (`phonology_history.py:215`). Child languages first get a suffix: `proto_form + ("i" if (language_id + index) % 2 == 0 else "a")` (`phonology_history.py:428`). `_apply_rule` (`phonology_history.py:180`) applies at most one replacement per rule, with environment-specific matching for `word_final`, `between_vowels`, `after_vowels` and `before_front_vowels`; any other environment falls through to a single unconditioned `replace(source, target, 1)`. If no rule applied and `replacement_pressure > 0.42`, one vowel is forcibly mutated (`phonology_history.py:430`–`435`).

Retention and the derived indices:

```
similarity  = matching characters at equal positions / max(len(inherited), len(derived))
retention   = clamp(0.62*similarity + 0.28*inherited_phonology_fraction
                    + 0.10*(1 - replacement_pressure))
replacement_pressure = clamp(0.44*change_rate + 0.36*(1 - inherited) + 0.20*contact)
regular_correspondence_fraction = retention
lexical_replacement_index       = clamp(1 - retention)
diffusion_stage_index = 1 + min(era_count - 1, floor(index * era_count / 12))
borrowed = (parent_id >= 0) and contact >= 0.62
           and semantic_shift_index >= 0.34 and retention < inherited
```

Per-era diffusion steps aggregate every correspondence whose `diffusion_stage_index <= stage_index`, producing `adoption_fraction`, `innovation_fraction`, `contact_borrowing_index`, `regularization_index` and `semantic_shift_index` (`phonology_history.py:476`–`518`).

**Speaker population histories** join languages to `population_regions` by `language_region_id`. The original `max(1.0, language.area_km2 * 0.5)` fallback (`phonology_history.py:598`–`599`) belongs to the explicit legacy path. Current speaker estimates require their actual associated population inputs; they do not substitute an area proxy for unavailable population. Global speaker-share quantities require the complete relevant language-population denominator, while independent sound rules and lexical structure remain available. The following interpolation applies only to available inputs. Initial speakers are

```
initial = estimated_speakers * clamp(0.70 + 0.10*inherited - 0.08*drift
                                     - 0.06*|migration_balance|, 0.45, 0.95)
```

and each era step interpolates linearly to the final value, with the last step forced to exactly `estimated_speakers`. Nine per-step indices are derived (`allophonic_variation_index`, `syllable_pressure_index`, `phonetic_reduction_index`, `contact_pressure_index`, `lexical_diffusion_pressure_index`, `population_adoption_index`, `register_divergence_index`, `pronunciation_regularization_index`, plus `speaker_fraction_index`). A history is flagged `high_contact_speaker_history` when its mean contact index is `>= 0.65` or any step reaches `>= 0.75` (`phonology_history.py:734`).

Available emitted floats in this module are rounded to six decimal places. Current speaker records and steps carry field availability maps; an unavailable estimate is null, including the nullable `high_contact_speaker_history` boolean. Summary availability is published separately from the number of retained history slots.

## Phonology record families

| Top-level key | Record count | Key fields |
|---|---|---|
| `phonological_rules` | one per selected template per language | `id`, `language_region_id`, `parent_language_region_id`, `era_id`, `stage_index`, `rule_type`, `source_segment`, `target_segment`, `source_features`, `target_features`, `articulatory_shift`, `environment`, `conditioned_by`, `prosodic_domain`, `start_year_bp`, `end_year_bp`, `probability_index`, `regularity_index`, `lexical_replacement_index`, `contact_influence_index`, `inventory_delta` |
| `phonological_histories` | one per language | `id`, `language_region_id`, `parent_language_region_id`, `initial_phoneme_inventory_size`, `final_phoneme_inventory_size`, `sound_change_rule_ids`, `sound_change_rule_count`, `step_count`, `cumulative_sound_shift_index`, `phonological_drift_index`, `syllable_template`, `stress_system`, `allowed_coda_count`, `prosodic_complexity_index`, `phonotactic_complexity_index`, `steps[]` |
| `phonological_histories[].steps[]` | one per era | `era_id`, `stage_index`, `start_year_bp`, `end_year_bp`, `rule_ids`, `rule_count`, `inventory_size`, `cumulative_sound_shift_index`, `inherited_phonology_fraction`, `contact_influence_index`, `syllable_template`, `stress_system`, `phonotactic_complexity_index`, `prosodic_weight_index` |
| `lexical_correspondences` | 12 per language | `id`, `language_region_id`, `parent_language_region_id`, `meaning`, `semantic_domain`, `proto_form`, `inherited_form`, `derived_form`, `applied_rule_ids`, `applied_rule_count`, `replacement_count`, `regular_correspondence_fraction`, `lexical_replacement_index`, `stress_pattern`, `syllable_count`, `syllable_pattern`, `mora_count`, `prosodic_weight_index`, `diffusion_stage_index`, `diffusion_adoption_index`, `semantic_shift_index`, `borrowed` |
| `lexical_diffusion_histories` | one per language | `id`, `language_region_id`, `parent_language_region_id`, `phonological_history_id`, `lexical_correspondence_ids`, `lexical_correspondence_count`, `step_count`, `syllable_template`, `stress_system`, `mean_diffusion_adoption_index`, `mean_lexical_innovation_index`, `mean_semantic_shift_index`, `contact_borrowing_index`, `steps[]` |
| `lexical_diffusion_histories[].steps[]` | one per era | `era_id`, `stage_index`, `start_year_bp`, `end_year_bp`, `affected_correspondence_ids`, `affected_correspondence_count`, `affected_meanings`, `affected_domain_count`, `adoption_fraction`, `innovation_fraction`, `contact_borrowing_index`, `regularization_index`, `semantic_shift_index` |
| `speaker_population_histories` | one per language | `id`, `language_region_id`, `parent_language_region_id`, `population_region_id`, `population_region_ids`, `population_region_count`, `phonological_history_id`, `lexical_diffusion_history_id`, `initial_speaker_population`, `final_speaker_population`, `estimated_speaker_population`, `mean_allophonic_variation_index`, `mean_syllable_pressure_index`, `mean_speaker_contact_index`, `mean_population_adoption_index`, `mean_phonetic_reduction_index`, `mean_lexical_diffusion_pressure_index`, `high_contact_speaker_history`, `step_count`, `steps[]` |
| `speaker_population_histories[].steps[]` | one per era | `era_id`, `stage_index`, `start_year_bp`, `end_year_bp`, `speaker_population`, `speaker_fraction_index`, `allophonic_variation_index`, `syllable_pressure_index`, `phonetic_reduction_index`, `contact_pressure_index`, `lexical_diffusion_pressure_index`, `population_adoption_index`, `register_divergence_index`, `pronunciation_regularization_index` |

**Keys written back onto `language_regions[]` records** (these are Python annotations, not native schema fields):

| Annotation | Set at |
|---|---|
| `phonological_history_id` | `phonology_history.py:400` |
| `sound_change_rule_ids`, `sound_change_rule_count` | `:401`–`402` |
| `final_phoneme_inventory_size` | `:403` |
| `phonological_drift_index` | `:404` |
| `syllable_template`, `stress_system`, `allowed_coda_count` | `:405`–`407` |
| `prosodic_complexity_index`, `phonotactic_complexity_index` | `:408`–`409` |
| `lexical_correspondence_ids`, `lexical_correspondence_count` | `:474`–`475` |
| `lexical_diffusion_history_id` | `:553` |
| `speaker_population_history_id` | `:762` |

`phonological_drift_index = clamp(0.54·sound_shift + 0.26·change_rate + 0.14·(1 − inherited) + 0.06·isolation)` (`phonology_history.py:301`).

## Downstream consumers of the political layer

| Product | Module | What it derives from this layer |
|---|---|---|
| `natural_frontiers`, `natural_frontier_model`, cell fields `natural_frontier_index` / `natural_frontier_type` / `natural_frontier_id` | `src/magic_geo/natural_frontiers.py:166` | Border segments are candidates when `type != open_lowland` **or** `barrier_score >= 0.45`; endpoint cells are scored with an independent terrain barrier (`max` over mountain/ice/river/coastal/desert/dense-forest/wetland signals), blended `0.72·border + 0.28·local` with a hard-type floor of 0.45, then grouped into mesh-connected components |
| `territorial_boundary_segments` and six per-snapshot-region annotations | `src/magic_geo/boundary_geometry.py:152`, `:199` | Walks `cell_adjacency_edges` and keeps edges whose two cells have different non-negative `political_region_id`; each segment carries `region_a_id`/`region_b_id` (ordered `min`,`max`), the exact edge polyline endpoints, `length_km`, `boundary_segment_quality`, `edge_class` and a `natural_boundary` flag. Snapshot regions gain `cell_edge_boundary_segment_ids`, `cell_edge_boundary_segment_count`, `cell_edge_boundary_length_km`, `mean_cell_edge_boundary_segment_quality`, `neighbor_region_ids`, `cell_edge_dissolved_area_km2` |
| `political_region_graph`, `trade_route_graph` | `src/magic_geo/graph_diagnostics.py:391`, `:313` | One region-pair edge per pair that appears in *any* of route, trade-flow, border or natural-frontier adjacency, carrying `border_length_km`, `mean_barrier_score` (barrier sum ÷ border count, `graph_diagnostics.py:477`), `dominant_border_type` and a sorted `border_type_counts`; the trade graph has one edge per valid route (nodes are settlements) with `total_trade_volume_index` and `total_route_distance_km` roll-ups. The geo-only variant `enrich_world_with_physical_graph_diagnostics` (`:513`) emits neither and builds only the plate, river and watershed graphs |
| `worldbuilding_realism_checks.political_region_connectivity` | `src/magic_geo/worldbuilding_realism.py:220`–`272` | Fraction of each region's settlements reachable from its capital over *internal* routes; target interval `[0.55, 1.0]`, region counted "connected" at reachability `>= 0.6` |
| `worldbuilding_realism_checks.natural_border_alignment` | `src/magic_geo/worldbuilding_realism.py:273`–`303` | Length-weighted natural-border fraction, target interval `[0.4, 1.0]` |
| `resource_deposits[].political_region_id` / `.culture_region_id` | `src/magic_geo/resource_dynamics.py:193`–`194` | Copied from the host cell with a `-1` default, so geo-only worlds (where the cell fields are stripped) record `-1` |

The exact cell-edge territorial segments are the correct product to use when you need real boundary geometry: the native `borders[]` records are cell-centre adjacency pairs, not polygon edges.

## Summary keys published by this layer

All native keys below are emitted by `summary_json` (`cpp/src/engine/summary.cpp`) at `output.float_precision`, and **all of them are popped in geo-only mode** by `NATIVE_CIVILIZATION_SUMMARY_FIELDS` in `src/magic_geo/api.py`.

| Summary key | Definition | Line |
|---|---|---|
| `political_region_count` | `political_regions.size()` | `summary.cpp:1831` |
| `culture_region_count` | `cultures.size()` | `:1832` |
| `language_region_count` | `language_regions.size()` | `:1833` |
| `language_lineage_count` | languages with `parent_language_region_id >= 0` | `:693`, `:1838` |
| `sacred_area_count` / `ruin_count` | Sacred vector size / available inferred ruin total; `recorded_ruin_count` is always the emitted ruin count | `:1894`–`:1895` |
| `border_segment_count` | `borders.size()` | `:1896` |
| `border_total_length_km` | Σ `length_km` | `:761`, `:1897` |
| `natural_border_fraction` | count fraction with `type != open_lowland` | `:763`, `:1898` |
| `largest_region_area_km2` | max political region area | `:685`, `:1900` |
| `largest_culture_area_km2` | max culture area | `:688`, `:1901` |
| `politically_assigned_land_fraction` | non-water cells with `political_region_id >= 0` ÷ land cells | `:483`, `:1902` |
| `culturally_assigned_land_fraction` | non-water cells with `culture_region_id >= 0` ÷ land cells | `:486`, `:1904` |
| `linguistically_assigned_land_fraction` | non-water cells with `language_region_id >= 0` ÷ land cells | `:489`, `:1906` |
| `mean_cultural_continuity` | mean `continuity_index` over cultures | `:689`, `:1884` |
| `mean_language_change_rate` | mean `change_rate` over languages | `:695`, `:1886` |
| `mean_phonological_complexity` | mean over languages | `:696`, `:1888` |
| `mean_sound_shift_index` | mean over languages | `:697`, `:1890` |
| `mean_inherited_phonology_fraction` | mean over languages | `:698`, `:1892` |
| `trade_flow_count` | `trade_flows.size()` | `:1825` |
| `trade_total_volume_index` | Σ `volume_index` | `:767`, `:1826` |
| `interregional_trade_fraction` | count fraction of interregional flows | `:770`, `:1827` |
| `mean_trade_friction` | mean `friction` | `:768`, `:1829` |
| `territorial_snapshot_count` | snapshots emitted | `:1865` |
| `snapshot_region_record_count` | Σ regions across snapshots | `:742`, `:1866` |
| `snapshot_polygon_region_count` | snapshot regions with `dissolved_polygon_area_km2 > 0` | `:746`, `:1867` |
| `mean_snapshot_fragmentation_index` | mean over snapshots | `:1868` |
| `mean_snapshot_polygon_area_error_fraction` | mean over **polygon** regions | `:1870` |
| `mean_snapshot_compactness_index` | mean over polygon regions | `:1873` |
| `mean_snapshot_geometry_quality` | mean over polygon regions | `:1876` |
| `mean_snapshot_boundary_perimeter_km` | mean over polygon regions | `:1879` |

Python-added summary keys from this layer (present only in full worlds): `political_region_model`, `political_border_model`, `trade_flow_model`, `culture_region_model`, `language_region_model`, `cultural_site_model`, `population_region_model`, `conflict_model`, `dynasty_model`, `territorial_snapshot_model`, `phonology_history_model`, `natural_frontier_model` plus the `natural_frontier_*` counters, `territorial_cell_edge_boundary_segment_count`, `territorial_cell_edge_boundary_length_km`, `snapshot_region_with_cell_edge_boundary_count`, `mean_snapshot_cell_edge_boundary_segment_count`, `mean_snapshot_cell_edge_boundary_length_km`, `mean_snapshot_cell_edge_boundary_quality`, and ~35 phonology keys (`phonological_history_count`, `phonological_rule_count`, `mean_phonological_rule_probability_index`, `mean_regular_correspondence_fraction`, `speaker_population_history_count`, `total_estimated_speaker_population`, `high_contact_speaker_history_count`, …; full list at `src/magic_geo/phonology_history.py:782`–`875`).

## Validators

**This entire layer is outside the scope of `validate-geo`.** The geo report declares `excluded_scope: "settlements, navigation/ports/routes, politics, territory, culture, history, population, economy, conflict, logistics, markets, campaigns, and language"` (`src/magic_geo/geo_validation.py:2812`). The civilization-layer guards live in the `magic-geo validate` command instead, which fails closed on the first collected failure list being non-empty.

| Validator | Entry point | Invoked at | What it replays |
|---|---|---|---|
| Political regions | `_validate_political_regions` | `src/magic_geo/cli/validators/political.py:121`; called at `cli/commands/validate.py:10586` | Frozen `political_region_model` dictionary (every key and value, including the two discount blocks and the limitation string); recomputes `target_count`, greedy capital selection at 0.18 rad, per-settlement region assignment cost with the route discounts, the full per-cell nearest-capital partition, then every region record: `type`, dominant biome/resource under `POLITICAL_BIOME_ORDER` / `POLITICAL_RESOURCE_ORDER`, `settlement_ids`, `route_count`, area (tolerance `max(0.01, area·1e-8)`), `mean_settlement_score` and `barrier_pressure` (2 quantization units), `mean_elevation_m` (`max(0.001, 2 units)`) |
| Political borders | `_validate_political_borders` | `political.py:506`; `validate.py:10587` | Frozen `political_border_model`; re-enumerates every cross-region non-water adjacency edge in ascending cell order, replays the six-way type priority, `length_km = max(0.001, angular·radius)` and the barrier formula; compares `border_count`, the sorted `border_type_counts` histogram, `summary.border_segment_count`, and per-record length (`max(0.001, 2 units)`) and barrier score (2 units) |
| Trade flows | `_validate_trade_flows` | `political.py:698`; `validate.py:10588` | Frozen `trade_flow_model` including the full `volume_parameters` block and `TRADE_RESOURCE_PRIORITY`; replays one flow per valid route, the primary-good priority scan with both fallbacks, friction, and the volume expression; checks `route_count`, `flow_count`, `interregional_flow_count`, sorted `primary_good_counts`, `summary.trade_flow_count`, `total_volume_index` (tolerance `max(1e-6, flow_count·0.02)` against the *serialized-precision* sum), and per-record `distance_km` exactly, `friction` at `max(0.001, 4 units)`, `volume_index` at `max(0.02, 4 units)` |
| Cultural geography | `validate_cultural_geography_replay` | `src/magic_geo/cultural_geography_validation.py:845`; `validate.py:10590` | Frozen `culture_region_model`, `language_region_model` and `cultural_site_model` compared by full dictionary equality; then an independent replay of culture creation, per-cell culture and language assignment (checked against every cell *and* every settlement), barrier isolation, trade contact, union-find language formation at the 70.0/0.92 thresholds, family assignment, one-generation lineage plus the global fallback, the whole phonology derivation, sacred and ruin candidate ranking with the `1.4·sqrt(4π/N)` separation, both targets, and the seven summary values |
| Territorial snapshots | `validate_territorial_geography_replay` | `src/magic_geo/territorial_geography_validation.py:500`; `validate.py:10593` | Frozen `territorial_snapshot_model`; rebuilds base region membership, boundary cells, area-weighted centroids, the tangent-plane angle-sorted 64-point sampled ring, great-circle perimeter and orthographic shoelace area from a radius re-derived as `sqrt(summary.surface_area_km2 / 4π)`, then applies both era factor arrays and compares every snapshot and every region record — including the boundary ring point-by-point at 2e-4 degrees |
| Civilization geography | `validate_civilization_geography_replay` | `src/magic_geo/civilization_geography_validation.py:800`; `validate.py:10592` | Frozen `population_region_model`, `conflict_model`, `dynasty_model` plus a full replay of the three native record families that consume this layer |
| Phonology history | `validate_phonology_history_replay` | `src/magic_geo/phonology_history_validation.py:1283`; `validate.py:10600` | Frozen `phonology_history_model`; re-derives rules, histories, correspondences, diffusion histories, speaker histories, the language annotations and ~35 summary values, then requires **exact structural containment** (`_contains_expected`) — every expected key must be present with an equal value, and lists must match element-for-element |
| Human geography (borders → frontiers) | `validate_human_geography_replay` | `src/magic_geo/human_geography_validation.py:956`; `validate.py:10589` | Land-use zones, natural frontiers (border candidacy at threshold 0.45, endpoint barrier scores, component grouping) and the five `worldbuilding_realism_checks` with their target intervals |
| Historical geography | `validate_historical_geography_replay` | `validate.py:10591` | The four-era partition and the seven event generators that consume culture, language, trade and site records |

The two tolerance idioms used throughout are worth internalizing: `unit = 10**(-summary.output_float_precision)` is the serialization quantization step, and comparisons are stated as small multiples of it (2 or 4 units) with an absolute floor. `_relative_close` in the territorial validator uses `max(0.5, |expected|·0.001)`.

## Worked commands

Generate a full world (civilization layer included) and run the full consistency gate:

```bash
magic-geo generate --config magic-geo.yaml --output runs/world.json
magic-geo validate --world runs/world.json
```

`validate` prints `OK` on success; on failure it writes one `FAIL <reason>` line per collected failure to stderr and exits 1 (`src/magic_geo/cli/commands/validate.py:22330`–`22333`).

Generate in-process and inspect the political and cultural layer:

```python
from magic_geo import load_config
from magic_geo.api import generate_world

world = generate_world(load_config("magic-geo.yaml"))

print(world["summary"]["political_region_count"],
      world["summary"]["culture_region_count"],
      world["summary"]["language_region_count"])
print(world["summary"]["natural_border_fraction"],
      world["summary"]["interregional_trade_fraction"])

for region in world["political_regions"]:
    print(region["id"], region["type"], region["dominant_biome"],
          round(region["area_km2"], 1), region["settlement_count"])
```

Inspect the language lineage and the phonology annotations the enricher wrote back onto each language record:

```python
for language in world["language_regions"]:
    print(language["id"], language["family"],
          "parent=", language["parent_language_region_id"],
          "depth=", language["lineage_depth"],
          "inventory=", language["phoneme_inventory_size"],
          "shift=", language["sound_shift_index"],
          "inherited=", language["inherited_phonology_fraction"],
          "syllable=", language["syllable_template"],
          "stress=", language["stress_system"])
```

Trace one lexical correspondence from proto-form to derived form through its applied rules:

```python
rules_by_id = {rule["id"]: rule for rule in world["phonological_rules"]}
for record in world["lexical_correspondences"]:
    if record["language_region_id"] != 0 or record["meaning"] != "mountain":
        continue
    print(record["proto_form"], "->", record["inherited_form"], "->", record["derived_form"])
    for rule_id in record["applied_rule_ids"]:
        rule = rules_by_id[rule_id]
        print("  stage", rule["stage_index"], rule["rule_type"],
              rule["source_segment"], "->", rule["target_segment"],
              "/", rule["environment"], "|", rule["articulatory_shift"])
```

Compare the native cell-centre border segments against the exact cell-edge territorial segments:

```python
native_length = sum(border["length_km"] for border in world["borders"])
edge_length = sum(segment["length_km"] for segment in world["territorial_boundary_segments"])
print("cell-centre border length_km:", round(native_length, 2))
print("cell-edge boundary length_km:", round(edge_length, 2))
```

Verify the two different natural-border numbers do not get conflated:

```python
checks = {check["name"]: check for check in world["worldbuilding_realism_checks"]}
print("count fraction  :", world["summary"]["natural_border_fraction"])
print("length fraction :", checks["natural_border_alignment"]["value"])
```

A geo-only world has none of this. `generate_geo_world` raises `ValueError` unless `output.include_cells` is true, and removes all 15 civilization top-level keys, the 4 civilization cell fields and the 58 civilization summary keys before enrichment:

```python
from magic_geo.api import generate_geo_world

geo = generate_geo_world(load_config("magic-geo.yaml"))
assert geo["generation_scope"] == "geo_only"
assert "political_regions" not in geo and "cultures" not in geo
assert "political_region_id" not in geo["cells"][0]
```

## Limitations and unresolved claims

These are the layer's own declared limitations plus the structural consequences that follow directly from the implemented code. None of them is softened elsewhere on this page.

1. **The political partition is a static barrier-weighted nearest-capital Voronoi.** Declared verbatim as `static_nearest_capital_partition_without_contiguity_constraint_population_feedback_or_state_dynamics`. There is no contiguity constraint, so a region's cells may be disconnected; there is no state formation, expansion, collapse, conquest or negotiation; and nothing downstream (population, conflict, dynasty, snapshot) feeds back into the partition.
2. **Borders are cell-centre adjacency pairs, not polygon edges.** Declared verbatim as `cell_center_adjacency_segments_without_exact_native_edge_polygons_or_negotiated_boundaries`. `length_km` is a great-circle distance between two cell *centres*, so it is not the length of the shared control-volume edge. The exact edge polylines exist only as the Python `territorial_boundary_segments` product.
3. **`natural_border_fraction` is a count fraction, not a length fraction, and ignores `barrier_score` entirely.** Three distinct "natural border" numbers coexist in a full world; they are not interchangeable.
4. **Trade flows are static diagnostics.** Declared verbatim as `diagnostic_static_flow_without_supply_demand_inventory_price_capacity_or_equilibrium_feedback`. `volume_index` is a bounded index in `[0, 100]`, not a quantity of goods; `friction` is a dimensionless cost ratio; there is no inventory, price, capacity or clearing anywhere in this stage. (Market clearing exists, but as a separate downstream enricher over a different record family.)
5. **Cultures do not spread.** One culture per political region, cell-identical to the political map. Declared verbatim as `static_political_homelands_without_cultural_diffusion_identity_change_or_population_feedback`. `migration_pressure` is a scalar index; nothing migrates.
6. **The language layer is a union-find over trade plus a one-generation lineage.** Declared verbatim as `diagnostic_language_union_and_single_generation_lineage_without_speaker_interaction_or_observed_linguistic_calibration`. `lineage_depth` is 0 or 1 and never deeper; family assignment is area dominance over culture types; and there is no phylogenetic reconstruction, no borrowing network between families and no observed-language calibration of any kind.
7. **Phoneme inventories, sound shift indices and phonological complexity are bounded synthetic indices.** `phoneme_inventory_size` is clamped to `[16, 58]` by construction; `sound_shift_index` is clamped to `[0, 0.28]` for roots and `[0, 1]` for children; `inherited_phonology_fraction` is exactly `1.0` for every root by definition, not by measurement. Parent inventories are inherited only when the parent's record id precedes the child's; otherwise the family base inventory is used.
8. **The phonology history is synthetic template linguistics.** Declared verbatim as `synthetic_template_linguistics_without_empirical_language_calibration_individual_speaker_interaction_or_stochastic_transmission`. Twelve hard-coded rule templates, twelve hard-coded proto-roots, a fixed segment feature table, deterministic modular template selection, and a single non-conditioned replacement per rule application. Sound changes are not exceptionless in the historical-linguistics sense, `regularity_index` is a derived index rather than a measured regularity, and the year-BP stamps come from the fixed four-era partition, which itself carries no calibrated physical duration.
9. **Sacred areas and ruins are ranked diagnostic sites.** Declared verbatim as `ranked_diagnostic_sites_without_settlement_lifecycle_archaeology_or_temporal_land_use`. A ruin is a *currently unoccupied* cell with a high composite score; there is no settlement that was founded, grew and was abandoned. `significance` and `preservation_score` are bounded indices with no physical units. The target counts are upper caps; the lower bound of 2 is never enforced when candidates are exhausted.
10. **Territorial snapshots are scaled static regions, not dynamic territories.** Declared verbatim as `scaled_static_regions_with_sampled_centroid_ordered_rings_not_exact_dynamic_cell_edge_territories`. Region membership is identical in every era; only area, perimeter and population are multiplied by era factors. `polygon_area_error_fraction` and `compactness_index` are therefore invariant under the scaling (up to the guards), which means they measure the *sampling fidelity of the base ring*, not any temporal change.
11. **Snapshot polygon geometry is a proxy.** The ring is a uniformly floor-sampled angle-ordered sequence of boundary cell centres, capped at 64 points plus a closing point; the area is a centred orthographic shoelace on a tangent plane, not a spherical polygon area; the centroid is an area-weighted mean of latitude and longitude in degrees, not a spherical centroid, so it is biased near the poles and across the antimeridian (`crosses_antimeridian` flags the latter but nothing corrects it). `geometry_quality` saturates its ring term at 24 points.
12. **Cultural continuity is order-dependent by construction.** It is computed once before sites exist and again afterwards; the serialized value is the second. `migration_pressure` is computed only in the first pass and therefore never reflects sacred-site or ruin counts. This is the implemented behaviour and both the C++ and the Python replay agree on it.
13. **Everything in this layer is timeless with respect to the simulation clock.** The four historical eras are a hard-coded year-BP partition (4200 → 0 BP) with no relationship to the tectonic/erosion nominal timestep, and the shared geo limitation "the simulation clock orders procedural stages but has no calibrated physical duration" applies a fortiori here: the civilization layer runs once, after the final maturation state, and no part of it is integrated forward in time.
14. **No empirical calibration exists for any product on this page.** The external calibration bundle (`configs/geo_validation_earth_empirical_targets.json`) targets physical metrics only; `validate-geo` explicitly excludes politics, territory, culture and language from its scope; and `worldbuilding_realism_model` declares itself `internal_generated_evidence_checks_without_external_historical_geographic_calibration`. Passing `magic-geo validate` proves that the serialized records replay exactly from the serialized inputs — it makes no claim that the resulting geography is historically or anthropologically plausible.

## See also

- [Settlements, Routes and Corridors](settlements-and-routes.md) — the settlement scoring, selection and route network this layer consumes
- [History, Demography, Economy and Markets](history-demography-and-economy.md) — eras, events, population regions, conflicts, dynasties and the market/logistics enrichers
- [Resources and Economic Geology](resources-and-economic-geology.md) — the resource enum that drives region type, culture type, trade goods and ruin type
- [Biomes, Ecosystems and Disturbance](biomes-and-ecology.md) — the biome enum used by border, culture and site classification
- [Mesh and Geometry](mesh-and-geometry.md) — control-volume cells, neighbour graph and `cell_adjacency_edges`
- [World Document Schema](../10-world-schema.md) — full top-level key order and per-record field counts
- [Validation](../12-validation.md) — the `magic-geo validate` gate that owns this layer
- [Geo Validation Suite](../13-geo-validation-suite.md) — the geo-only suite that explicitly excludes this layer
- [Native Engine (C++ Core)](../08-native-engine.md) — translation units and pipeline invariants
- [Python API](../07-python-api.md) — `generate_world` / `generate_geo_world` and the enricher chain
- [CLI Reference](../06-cli-reference.md) — `generate`, `validate`, `export`
- [Glossary](../21-glossary.md)
