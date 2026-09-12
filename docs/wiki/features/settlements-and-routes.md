# Settlements, Routes and Corridors

[Wiki home](../README.md) > Features

This page documents the entire human-settlement stack: the native per-cell `settlement_score` field and every term that feeds it, the greedy separated site selector that turns that field into `settlements[]`, the endpoint-ranked route network, and the four Python enrichers that build on top of them — navigability-derived port sites, feature-weighted Dijkstra route corridors, and border-derived natural frontiers. Everything here is a static, deterministic suitability-and-cost construction: there is no population dynamics, no land market, no capacity, congestion or network equilibrium, and the model declarations in the world document say so explicitly. The whole layer is absent from geo-only worlds, and the last section explains exactly which downstream models change branch as a result.

Current seasonal generation uses settlement selection **v3**, native routes **v1**, and navigation/ports/corridors **v3**. The route and transport declarations identify their actual source versions. Explicit historical selection v2 and transport v1/v2 retain their original paths, including genuine seasonal-climate archives with selection v2; climate ownership alone does not select the settlement version. The equations below describe available inputs. Current unavailable derived values use null and strict flags, while supported zero remains zero. The native settlement score retains its documented zero sentinel, explained below. See [Settlement and social estimate availability](../../settlement_social_availability.md) for the current native-social and downstream publication contracts.

## On this page

- [Where the settlement layer runs](#where-the-settlement-layer-runs)
- [The `settlement_score` field: every input term](#the-settlement_score-field-every-input-term)
- [Settlement site selection](#settlement-site-selection)
- [Settlement type classification](#settlement-type-classification)
- [The settlement record](#the-settlement-record)
- [Route generation: barrier cost, ranking, pair selection](#route-generation-barrier-cost-ranking-pair-selection)
- [The route record and route types](#the-route-record-and-route-types)
- [The declaration blocks: `settlement_selection_model` and `route_network_model`](#the-declaration-blocks-settlement_selection_model-and-route_network_model)
- [Navigability inputs consumed by ports and corridors](#navigability-inputs-consumed-by-ports-and-corridors)
- [Port sites and marine access](#port-sites-and-marine-access)
- [Route corridors](#route-corridors)
- [How corridors differ from routes](#how-corridors-differ-from-routes)
- [Natural frontiers](#natural-frontiers)
- [Validators](#validators)
- [Geo-only mode: what disappears and what it implies](#geo-only-mode-what-disappears-and-what-it-implies)
- [Worked examples](#worked-examples)
- [Summary keys contributed by this layer](#summary-keys-contributed-by-this-layer)
- [Configuration surface](#configuration-surface)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

---

## Where the settlement layer runs

The native settlement and route stages are the first two generation calls inside the society branch of `cpp/src/engine/pipeline.cpp`, guarded by `if (include_society)`:

```cpp
society.settlements = generate_settlements(params, earth.cells);
society.routes      = generate_routes(params, earth.cells, society.settlements);
society.political_regions = generate_political_regions(
    params, earth.cells, society.settlements, society.routes);
```

Both are declared in `cpp/src/engine/internal.hpp` and defined in `cpp/src/engine/settlements.cpp`. Before this branch, the native pipeline derives soils/biomes/resources and landforms, then finalizes settlement climate applicability. `simulate_geo_world` skips society generation, so `society.settlements` and `society.routes` stay empty vectors. Native political, cultural, population and historical stages follow the pair in full generation.

After native generation, `generate_world` in `src/magic_geo/api.py` retains cells internally, even for summary-only output. The relevant Python phases run in this order:

| Order | Call or phase | Module | Purpose |
|---|---|---|---|
| 1 | `_enrich_physical_foundation` | `api.py` | Shared natural water, seasonal and terrain prerequisites |
| 2 | Settlement/route and native social annotations | `settlement_routes.py` and social annotation modules | Audited source declarations before human consumers |
| 3 | `enrich_world_with_navigability_diagnostics` | `navigability_diagnostics.py` | Waterway selection and marine transport indices |
| 4 | `enrich_world_with_port_sites` | `port_sites.py` | Supported local port sites and selection coverage |
| 5 | `enrich_world_with_route_corridors` | `route_corridors.py` | Paths, diagnostics and membership coverage |
| 6 | `_enrich_ecosystems_and_resources` | `api.py` | Ecology/resources; physical reefs receive separate port-link annotations |
| 7 | Land use, natural frontiers, worldbuilding | Their corresponding Python modules | Human land-use/terrain diagnostics and five realism checks |
| 8 | Social histories and later human consumers | `api.py` | Population/economy, genealogy, logistics, demographics, markets, graphs and phonology |

Ordering is load-bearing: ports consume navigation, corridors consume navigation and ports, and reef port links follow port publication without changing physical reef equations. Cell suppression happens only after the full sequence finishes.

`generate_geo_world` shares the physical-foundation and ecology/resource phases and skips the human stages in this table.

---

## The `settlement_score` field: every input term

`settlement_score` is a native per-cell field written by `derive_soils_biomes_resources`, adjusted by `derive_landforms`, and finally gated by `finalize_settlement_climate_applicability`. It is serialized at precision `max(8, float_precision)`.

### Shared intermediates

| Symbol | Definition | Source |
|---|---|---|
| `relief` | `max(0, elevation_m − mean(neighbour elevation_m))`; `0` if the cell has no neighbours | `cpp/src/engine/climate.cpp:15` (`local_relief`) |
| `slope_penalty` | `clamp(relief / 1800.0, 0, 1)` | `environment.cpp:308` |
| `pet` | `max(1.0, (temperature_c + 8.0) * 31.0)` | `environment.cpp:309` |
| `aridity` | `precipitation_mm_y / pet` | `environment.cpp:310` |
| `coast` | `has_ocean_neighbor(cells, i)` — true if **any** neighbour has `is_water` true | `environment.cpp:5`–`:12` |
| `climate_soil` | `clamp(precip/1300, 0, 1.2) * clamp((T+8)/30, 0, 1.1)` | `environment.cpp:337` |
| `litho_base` | `volcanic → 0.78`, `granite → 0.50`, `shale → 0.44`, otherwise `0.58` | `environment.cpp:336` |
| `fertility` | `clamp(litho_base + 0.20·climate_soil + (is_river ? 0.24 : 0) − 0.35·slope_penalty − (aridity < 0.45 ? 0.28 : 0), 0, 1)` | `environment.cpp:339` |

`is_water` identifies marine cells; standing inland lakes use `is_lake` instead.
Both have zero settlement score and are excluded from candidate selection.
`has_ocean_neighbor` tests only marine neighbors, so its coastal bonus does not
include inland lake shores. Lake shore suitability still depends on terrestrial
runoff, river access, fertility and climate.

### The four positive terms, the hazard term and the biome multiplier

`environment.cpp:405`–`:413`:

| Term | Formula | Weight | Notes |
|---|---|---|---|
| `water_access` | `is_river → 1.0`; else `coast → 0.78`; else `clamp(runoff_mm_y / 550, 0, 0.55)` | `0.38` | Applies only to exposed terrestrial cells; marine and standing lake scores are zero |
| `fertility` | as above | `0.30` | Uses the same value serialized as `cells[].fertility` |
| `climate_score` | `clamp(1 − |temperature_c − 17| / 31, 0, 1)` | `0.18` | Peaks at 17 °C, reaches 0 at −14 °C and +48 °C |
| `resource_score` | `resource == none ? 0.0 : 0.18` | `0.18` (flat) | Any non-`none` resource contributes the same bonus |
| `hazard` | `clamp(0.28·boundary_convergent + 0.18·boundary_transform + 0.24·slope_penalty + 0.22·clamp(ice_thickness_m/2200, 0, 1), 0, 0.65)` | subtracted | Hard cap at `0.65` |

```
settlement_score = clamp(0.38·water_access + 0.30·fertility + 0.18·climate_score
                         + resource_score − hazard, 0, 1)
```

Then a cold/hostile-biome multiplier at `environment.cpp:411`: if the biome is `ice_cap`, `tundra`, `alpine` or `ocean` (indices 3, 4, 14, 0 of `BIOME_NAMES`, `cpp/src/engine/schema_names.hpp:21`), `settlement_score *= 0.18`.

Water cells short-circuit at `environment.cpp:327`–`:334`: `settlement_score = 0.0`, `fertility = 0.0`.

### Landform adjustments applied afterwards

`derive_landforms` re-classifies each cell and then modifies `settlement_score` (`environment.cpp:476`–`:503`). These are the values the enricher publishes as `landform_score_adjustments`:

| Landform (index in `LANDFORM_NAMES`) | Adjustment | Source |
|---|---|---|
| `delta` (12) or `floodplain` (11) | `score = clamp(score + 0.08, 0, 1)` | `environment.cpp:485` |
| `alluvial_fan` (13) | `score = clamp(score + 0.03, 0, 1)` | `environment.cpp:491` |
| `salt_flat` (4) | `score *= 0.55` | `environment.cpp:495` |
| `glacial_valley` (17) or `moraine` (18) | `score *= 0.42` | `environment.cpp:500` |
| `glacial_lake` (19) | `score *= 0.72` | `environment.cpp:500` |
| `coastal_plain` (14), only when `score > 0` | `score = clamp(score + 0.04, 0, 1)` | `environment.cpp:501`–`:502` |

The branches are `else if`-chained, so at most one applies. Note that `derive_landforms` also mutates other cell state *before* adjusting the score: `soil_type`, `fertility`, `biome` and `resource` on delta/floodplain cells (`environment.cpp:477`–`:484`), `soil_type` and `resource` on alluvial-fan cells (`:487`–`:490`) and on salt-flat cells (`:493`–`:494`), and `soil_type` on glacial-valley/moraine cells (`:497`–`:499`). Only the delta/floodplain branch touches `fertility`, so for those cells the serialized `fertility` is not the value that entered the score expression.

For the current seasonal path, finalization runs **after all landform adjustments**. The annual proxy is supported only when the native temperature lies strictly inside **(-14, 48) °C**; outside that interval the final score is zero and bonuses cannot restore eligibility. `settlement_climate_temperature_c` retains the native annual value at round-trip precision, and `settlement_climate_supported` is a strict boolean. An unsupported dry zero is an unavailable proxy value; a supported dry zero is a valid zero; marine/lake zero is a known structural zero. The score itself is never made null. This interval limits this particular suitability proxy, not human survival or universal habitability. Explicit historical selection v2 retains its original ungated score path.

---

## Settlement site selection

`generate_settlements` in `cpp/src/engine/settlements.cpp` uses `params.temperature_model` to select the seasonal applicability prerequisite. Its ranking, target and spacing equations are unchanged.

| Step | Rule | Source |
|---|---|---|
| 1. Candidacy | Skip marine (`is_water`) and standing lake (`is_lake`) cells, unsupported seasonal proxy inputs, and cells with `settlement_score < 0.48`. A candidate must be a **local maximum** among eligible exposed terrestrial neighbors. Marine, lake and unsupported neighbors never disqualify it. | `settlements.cpp` |
| 2. Ranking | Sort candidates by `settlement_score` **descending**, tie-broken by ascending cell id. Comparator is a strict total order, so the (unstable) `std::sort` is deterministic. | `settlements.cpp:44`–`:49` |
| 3. Target count | `target = clamp(cell_count / 180, 8, 64)` (integer division) | `settlements.cpp:51` |
| 4. Greedy spacing | Walk the ranked list; skip a candidate if its great-circle angular distance to **any already-selected** site is `< min_sep`; otherwise accept. Stop when `settlements.size() >= target`. | `settlements.cpp:52`–`:76` |

The minimum separation is a pure function of mesh resolution:

```
min_sep = 2.4 * sqrt(4π / max(1, cell_count))     // settlements.cpp:52-54, PI at constants.hpp:5
```

`sqrt(4π/N)` is the angular scale of a mean control volume (mean solid angle `4π/N`), so `min_sep` is about 2.4 mean cell widths, in radians. `angular_distance` is `acos(clamp(dot(a,b), −1, 1))` on the unit-sphere positions (`cpp/src/engine/core.cpp:94`).

Resulting spacing for a 6371 km planet:

| `cell_count` | `target` | `min_sep` (rad) | `min_sep` (km) |
|---|---|---|---|
| 1 000 | 8 | 0.269040 | 1714.1 |
| 8 000 | 44 | 0.095120 | 606.0 |
| 20 000 | 64 | 0.060159 | 383.3 |
| 40 000 | 64 | 0.042539 | 271.0 |

Because the spacing constraint can exhaust the candidate list before the target is met, `settlements.size()` is `min(target, number of candidates surviving spacing)` — it is a ceiling, not a guarantee. The lower clamp of 8 is likewise not a floor on the produced count.

Settlement ids are assigned in selection order (`settlement.id = settlements.size()` at `settlements.cpp:68`), so record order is descending score modulo the spacing rejections.

---

## Settlement type classification

`settlement_type_for_cell` (`cpp/src/engine/settlements.cpp:5`) is a first-match priority chain over the six `SETTLEMENT_TYPE_NAMES` (`cpp/src/engine/schema_names.hpp:44`).

| Priority | Condition | Returned index | Serialized name |
|---|---|---|---|
| 1 | `has_ocean_neighbor(cells, cell.id)` (any marine neighbor) | 1 | `port` |
| 2 | `cell.is_river` | 0 | `river_city` |
| 3 | `resource ∈ {1, 2, 5, 6}` = `volcanic_arc_metals`, `craton_iron_gold`, `placer_metals`, `geothermal` | 2 | `mining_town` |
| 4 | `fertility > 0.66` **or** `resource == 7` (`fertile_alluvium`) | 3 | `agricultural_town` |
| 5 | `biome ∈ {9, 10}` = `cold_desert`, `hot_desert` **and** (`runoff_mm_y > 120.0` **or** `is_lake`) | 4 | `oasis` |
| 6 | otherwise | 5 | `frontier_town` |

Because rule 1 fires first, a river mouth on the marine coast is typed `port`.
An inland lakeside settlement proceeds through the remaining rules. The
mining-resource and desert-biome sets are mirrored in the Python replay.

---

## The settlement record

Serialized by `settlements_json` (`cpp/src/engine/entity_serialization.cpp:357`). Fourteen fields, in emission order. Seven are copied from the host cell at serialization time — the `Settlement` struct itself (`cpp/src/engine/types/world.hpp:9`) holds only seven values.

| # | Field | Type | Precision | Source |
|---|---|---|---|---|
| 1 | `id` | int | — | selection order index (`settlements.cpp:68`) |
| 2 | `cell_id` | int | — | host cell |
| 3 | `region_id` | int | — | political region; `-1` until `generate_political_regions` fills it (`internal.hpp:373` takes `settlements` by non-const ref) |
| 4 | `culture_region_id` | int | — | `-1` until `generate_cultural_layers` fills it (`internal.hpp:388`) |
| 5 | `language_region_id` | int | — | as above |
| 6 | `type` | enum string | — | `SETTLEMENT_TYPE_NAMES[type]` |
| 7 | `score` | double | `max(8, float_precision)` | copy of `cells[cell_id].settlement_score` at selection time |
| 8 | `lat_deg` | double | `float_precision` | `cell.lat * DEG` |
| 9 | `lon_deg` | double | `float_precision` | `cell.lon * DEG` |
| 10 | `biome` | enum string | — | `BIOME_NAMES[cell.biome]` |
| 11 | `resource` | enum string | — | `RESOURCE_NAMES[cell.resource]` |
| 12 | `water_body_type` | enum string | — | `WATER_BODY_NAMES[cell.water_body]` |
| 13 | `fertility` | double | `max(8, float_precision)` | `cell.fertility` |
| 14 | `is_river` | bool | — | `cell.is_river` |

There is **no tier, size, population, or rank field** on the settlement record. `score` is the only intensity-like value, and the closest thing to a size classification is `type`, which is a functional/situational label, not a hierarchy. Downstream consumers that need a "large settlement" notion construct one themselves — `worldbuilding_realism.py:77` defines `_large_settlements` as the top `max(1, min(n, max(5, (n+3)//4)))` settlements by `score`, i.e. roughly the top quarter with a floor of five. That is a local convention in one diagnostic, not a schema field.

---

## Route generation: barrier cost, ranking, pair selection

`generate_routes` (`cpp/src/engine/settlements.cpp:103`) builds a sparse graph over settlement **endpoints only**. It never touches the cells between the two endpoints — no path is computed at this stage.

### The barrier multiplier

`route_barrier_cost(a, b)` (`settlements.cpp:80`–`:86`) is a symmetric dimensionless multiplier evaluated on the two **endpoint cells**:

| Term | Formula | Source |
|---|---|---|
| `mountain` | `clamp((max(a.elevation_m, b.elevation_m) − 1200.0) / 2600.0, 0, 1)` | `settlements.cpp:81` |
| `tectonic_hazard` | `0.50·(a.boundary_convergent + b.boundary_convergent) + 0.25·(a.boundary_transform + b.boundary_transform)` | `settlements.cpp:82`–`:83` |
| `arid` | `0.18` if either endpoint biome is `cold_desert` (9) or `hot_desert` (10), else `0.0` | `settlements.cpp:84` |
| **result** | `1.0 + 0.95·mountain + 0.45·clamp(tectonic_hazard, 0, 1) + arid` | `settlements.cpp:85` |

Range: `[1.0, 1.0 + 0.95 + 0.45 + 0.18] = [1.0, 2.58]`. The published parameter block names these `mountain_start_m`, `mountain_scale_m`, `mountain_weight`, `convergent_pair_weight`, `transform_pair_weight`, `tectonic_weight`, `desert_addition` (`src/magic_geo/settlement_routes.py:117`–`:125`).

### Ranking and pair selection

For each settlement, in id order (`settlements.cpp:106`):

1. For every other settlement, compute `distance_km = angular_distance(a.p, b.p) * params.radius_km` and `cost = distance_km * route_barrier_cost(a, b)` (`settlements.cpp:114`–`:115`).
2. Apply a **ranking discount** (`settlements.cpp:116`–`:120`):
   - `×0.68` if both settlements have `type == 1` (`port`);
   - else `×0.78` if the two endpoint cells share `basin_id` **and at least one** is `is_river`.
3. Sort ascending by `(cost, other_id)` — `std::pair` lexicographic ordering makes the tie-break deterministic (`settlements.cpp:123`).
4. Take the `min(2, n−1)` best (`settlements.cpp:124`).
5. Normalise each link to the unordered pair `(min(id), max(id))` and insert into a `std::set`; if the pair was already present, skip it (`settlements.cpp:126`–`:130`).
6. Emit the route with `from = min(id)`, `to = max(id)` — so `from < to` always, and `from` is not necessarily the settlement whose ranking produced the link.

The final `cost` is **recomputed** at `settlements.cpp:140` from `route_barrier_cost` and then discounted by **route type**, not by the ranking rule (`settlements.cpp:141`–`:145`): `×0.68` for `coastal_sea`, `×0.78` for `river_corridor`, no discount otherwise.

These two discount rules do not coincide. The ranking discount for a shared-basin pair fires when **either** endpoint is a river cell; the `river_corridor` route type (and therefore the cost discount) requires **both** endpoints to be river cells in the same basin. A pair that was ranked with the 0.78 discount can end up typed `overland` or `mountain_pass` and carry the undiscounted cost. The replay validator reproduces both rules separately (`src/magic_geo/cli/validators/settlement.py:632`–`:645` for ranking, `:664`–`:667` for cost), so the asymmetry is locked in by the gate rather than being an unnoticed drift. Whether it was *intended* is not recorded anywhere in the tree, and this page does not resolve that.

The route count is at most `2 * settlement_count` and typically less, because a settlement's two preferred links may already have been claimed. Route ids are assigned in emission order (`settlements.cpp:135`).

---

## The route record and route types

`route_type_for_pair` (`cpp/src/engine/settlements.cpp:88`) is another first-match chain over `ROUTE_TYPE_NAMES` (`cpp/src/engine/schema_names.hpp:47`):

| Priority | Condition | Index | Name | Cost discount |
|---|---|---|---|---|
| 1 | both settlement types are `port` | 2 | `coastal_sea` | `×0.68` |
| 2 | both endpoint cells `is_river` **and** equal `basin_id` | 1 | `river_corridor` | `×0.78` |
| 3 | either endpoint `elevation_m > 1300.0` **or** either endpoint `boundary_convergent > 0.24` | 3 | `mountain_pass` | none |
| 4 | otherwise | 0 | `overland` | none |

`routes_json` (`cpp/src/engine/entity_serialization.cpp:385`) emits six fields:

| # | Field | Type | Precision | Meaning |
|---|---|---|---|---|
| 1 | `id` | int | — | emission order |
| 2 | `from` | int | — | settlement id, always `min(a, b)` |
| 3 | `to` | int | — | settlement id, always `max(a, b)` |
| 4 | `type` | enum string | — | one of the four above |
| 5 | `distance_km` | double | `float_precision` | great-circle endpoint distance, `angular_distance × planet_parameters.radius_km` |
| 6 | `cost` | double | `float_precision` | `distance_km × barrier × type discount` |

Current `route_corridors` publication adds `route_corridor_id`, `route_corridor_type`, `path_cell_ids`, `route_path_supported` and `route_corridor_diagnostics_supported` to each route dict after auditing its prerequisites and staged outputs. These are Python annotations, not native route fields. Historical transport v1/v2 retains its original three-field annotation.

---

## The declaration blocks: `settlement_selection_model` and `route_network_model`

`enrich_world_with_settlement_route_models` (`src/magic_geo/settlement_routes.py:41`) computes **nothing physical**. It republishes the native algorithm contract as two top-level objects plus two summary strings, and independently recomputes the candidate count and target count as a cross-check.

Current seasonal `world["settlement_selection_model"]` (`settlement_routes.py`):

| Key | Value | Meaning |
|---|---|---|
| `model_type` | `causal_native_score_local_max_separated_settlement_selection_v3` | Explicit historical v2 remains independently replayable |
| `score_model` | `native_soil_biome_resource_water_climate_hazard_landform_score_with_annual_proxy_support_v3` | Unsupported seasonal scores are zero after all adjustments |
| `candidate_model` | `nonmarine_nonlake_annual_proxy_supported_raw_score_threshold_neighbor_local_max_v3` | Only supported exposed neighbors can suppress a local maximum |
| `annual_climate_applicability` | Exact `native_annual_settlement_suitability_proxy_support_v1` declaration in `settlement_climate_support.py` | Retained annual input, open interval, separate surface eligibility and unavailable-zero policy |
| `rank_model` | `descending_raw_score_then_cell_id_v1` | |
| `selection_model` | `greedy_spherical_minimum_separation_until_target_v1` | |
| `target_model` | `clamp_floor_cell_count_divisor_minimum_maximum_v1` | |
| `type_model` | `adjacent_water_river_mining_agriculture_oasis_frontier_priority_v1` | |
| `score_threshold` | `0.48` | mirrors `settlements.cpp:30` |
| `target_cell_divisor` | `180` | mirrors `settlements.cpp:51` |
| `target_minimum` / `target_maximum` | `8` / `64` | |
| `minimum_separation_factor` | `2.4` | |
| `score_weights` | `{water_access: 0.38, fertility: 0.30, climate: 0.18, resource_bonus: 0.18}` | |
| `hazard_weights` | `{convergent: 0.28, transform: 0.18, relief: 0.24, ice: 0.22, maximum: 0.65}` | |
| `cold_biome_multiplier` | `0.18` | |
| `landform_score_adjustments` | `{delta_or_floodplain_add: 0.08, alluvial_fan_add: 0.03, salt_flat_multiplier: 0.55, glacial_valley_or_moraine_multiplier: 0.42, glacial_lake_multiplier: 0.72, coastal_plain_add: 0.04}` | |
| `threshold_and_rank_semantics` | `unrounded_native_scores` | the 0.48 test happens before serialization rounding |
| `selection_score_precision` | `max(8, summary.output_float_precision)` | |
| `formula_replay_tolerance_model` | `max_16_selection_units_one_output_unit` | |
| `record_order` | `selection_order_with_sequential_ids` | |
| `deterministic` | `true` | |
| `candidate_cell_count` | recomputed by `_candidate_count` (`settlement_routes.py:18`) | |
| `target_count` | recomputed `max(8, min(64, len(cells)//180))` | |
| `settlement_count` | `len(world["settlements"])` | |
| `model_limitation` | `static_suitability_selection_without_population_growth_land_market_or_infrastructure_feedback` | |

`world["route_network_model"]` (`settlement_routes.py:107`–`:133`):

| Key | Value |
|---|---|
| `model_type` | `causal_endpoint_barrier_ranked_route_network_v1` |
| `source_settlement_model` | the settlement model string above |
| `ranking_model` | `endpoint_great_circle_distance_times_barrier_with_port_or_river_discount_v1` |
| `barrier_model` | `endpoint_mountain_tectonic_hazard_and_desert_multiplier_v1` |
| `selection_model` | `two_lowest_ranked_neighbors_per_settlement_then_unique_unordered_pair_v1` |
| `route_type_model` | `port_pair_river_basin_mountain_hazard_overland_priority_v1` |
| `record_order` | `source_settlement_order_then_rank_with_first_unique_pair_v1` |
| `links_per_settlement` | `2` |
| `planet_radius_source` | `planet_parameters.radius_km` |
| `barrier_parameters` | `{mountain_start_m: 1200.0, mountain_scale_m: 2600.0, mountain_weight: 0.95, convergent_pair_weight: 0.50, transform_pair_weight: 0.25, tectonic_weight: 0.45, desert_addition: 0.18}` |
| `ranking_discounts` | `{port_pair: 0.68, shared_basin_river: 0.78}` |
| `mountain_route_elevation_threshold_m` | `1300.0` |
| `mountain_route_convergence_threshold` | `0.24` |
| `deterministic` | `true` |
| `settlement_count` / `route_count` | lengths of the corresponding arrays |
| `model_limitation` | `endpoint_only_network_selection_before_downstream_cell_path_routing_capacity_congestion_and_equilibrium` |

Both strings are also written into `summary` (`settlement_routes.py:134`–`:136`).

The current transport declarations are:

| Key | `model_type` | Required current source families |
|---|---|---|
| `navigability_model` | `causal_channel_hydraulic_coastal_navigability_v3` | Settlement v3 and physical channel morphology/hydraulics v2 |
| `port_site_model` | `causal_navigability_coastal_port_site_selection_v3` | Settlement v3 and navigation v3 |
| `route_corridor_model` | `causal_feature_weighted_dijkstra_route_corridors_v3` | Settlement v3, navigation/ports v3, native routes v1 and aquifer v2 |

Exact own and parent declarations are checked before mutation. Explicit transport v1/v2 uses its historical replay; missing or malformed current metadata is not a request to use a historical default.

---

## Navigability inputs consumed by ports and corridors

Three cell fields produced by `enrich_world_with_navigability_diagnostics` are the primary marine inputs to the port and corridor models. They are listed here because port and corridor scoring is unintelligible without them.

| Field | Formula | Source |
|---|---|---|
| `coastal_navigability_index` (marine cell) | `clamp(clamp(water_depth_m/180)·0.30 + shelf + clamp(land_neighbours/4)·0.20 + constriction·0.26)` where `shelf = 0.24` for `continental_shelf`/`inland_sea`, else `0.08` | `src/magic_geo/navigability_diagnostics.py:76`–`:81` |
| `coastal_navigability_index` (land cell with marine neighbours) | `clamp(clamp(marine_neighbours/4)·0.32 + protected + river_mouth + low_relief·0.18)`; `protected = 0.20` if any marine neighbour is shelf/inland sea; `river_mouth = 0.22` if `is_river` or `landform == "delta"`; `low_relief = clamp(1 − |elev|/1200)` | `navigability_diagnostics.py:83`–`:90` |
| `harbor_suitability_index` | `0` for water cells and for land cells with no marine neighbour; else `clamp(coastal_nav·0.32 + protected(0.24) + river_mouth(0.18) + low_relief(|elev|/900)·0.14 + settlement_score·0.18 − clamp(ice/300)·0.22)` | `navigability_diagnostics.py:93`–`:115` |
| `transport_chokepoint_index` | `0` unless the cell is in a `marine_chokepoints` record; else `clamp(constriction·0.72 + coastal_nav·0.28)` | `navigability_diagnostics.py:118`–`:127` |

The harbor formula runs only when its actual settlement input is available. Current coastal-land harbor inputs expose `harbor_site_applicable` and `harbor_suitability_supported`; unsupported harbor, overall `navigability_index` and classification are null with false support flags. Water or no-marine-contact harbor contributions remain known structural zeros. River/coastal/chokepoint components remain numeric. The old missing-`settlement_score=0.0` fallback belongs to historical replay; current full consumers require the declared source, and geo-only generation skips navigation entirely.

`navigable_waterway_selection_complete` and `navigability_estimates_complete` describe whole-family coverage. Incomplete navigation withholds waterway components, publishes null membership IDs and unavailable aggregate estimates, and keeps the literal emitted-record count. An empty emitted list therefore needs its completeness flag before it can mean known absence.

---

## Port sites and marine access

`enrich_world_with_port_sites` (`src/magic_geo/port_sites.py:176`) scores **every** cell, selects land cells, and emits `world["port_sites"]` plus `world["port_site_model"]`. Marine water types are `{ocean, continental_shelf, inland_sea}` (`port_sites.py:7`); a "marine neighbour" is a neighbour whose `water_body_type` is in that set (`port_sites.py:19`).

### The three access indices

All three have known `0.0` contributions for water cells and for cells with no marine neighbour. On applicable land, the bay and river-mouth formulas require their actual supported harbor input; otherwise those indices are null. Strait access remains physical and numeric.

**`protected_bay_index`** (`port_sites.py:44`–`:56`):

| Term | Formula | Weight |
|---|---|---|
| `marine_contact` | `clamp(len(marine_neighbours)/3)` | `0.20` |
| `protected_water` | fraction of marine neighbours whose `water_body_type` is `continental_shelf` or `inland_sea` | `0.25` |
| `enclosure` | mean over marine neighbours of their own land-neighbour fraction | `0.25` |
| `shallow` | mean over marine neighbours of `clamp(1 − water_depth_m/260)` | `0.16` |
| `harbor` | `clamp(harbor_suitability_index)` | `0.14` |

**`river_mouth_port_index`** (`port_sites.py:59`–`:69`). Additionally returns `0.0` unless the cell `is_river` or has `landform ∈ {delta, floodplain, river_valley}`:

| Term | Formula | Weight |
|---|---|---|
| base | constant | `0.28` |
| `flow` | `clamp(flow_accumulation / max(1, global max flow_accumulation))` | `0.22` |
| `runoff` | `clamp(runoff_mm_y / 900)` | `0.14` |
| `delta_bonus` | `0.26` for `delta`, `0.12` for `floodplain`/`river_valley`, else `0.0` | additive |
| `harbor` | `clamp(harbor_suitability_index)` | `0.10` |

**`strait_access_index`** (`port_sites.py:72`–`:90`): over the marine neighbours, take the best `constriction_index` of the `marine_chokepoints` record the neighbour belongs to, raised to at least `0.60` when that chokepoint's `type` is `"strait"`; then `clamp(best_constriction·0.76 + clamp(coastal_navigability_index)·0.24)`.

### Suitability and selection

`_port_suitability` (`port_sites.py:93`–`:118`) — `0.0` for water cells:

```
base = max(harbor, protected_bay, river_mouth, strait_access)
port_suitability_index = clamp(
      base            * 0.40
    + protected_bay   * 0.16
    + river_mouth     * 0.14
    + strait_access   * 0.12
    + coastal_nav     * 0.06
    + settlement_score* 0.06
    + climate         * 0.06
    - ice_penalty     * 0.32
    - relief_penalty  * 0.08 )
```
with `climate = clamp((temperature_c + 8)/30)`, `ice_penalty = clamp(ice_thickness_m/220)`, `relief_penalty = clamp((|elevation_m| − 1200)/1800)`.

Selection (`port_sites.py:217`–`:223`):

```
severe_ice = ice_thickness_m >= 80.0  or  biome == "ice_cap"
selected   = port_site_selection_supported and (not is_water) and (
                                 (port_suitability_index >= 0.58 and not severe_ice)
                                  or cell_id hosts a settlement of type "port" )
```

After the support prerequisite, the `port` settlement override bypasses both the suitability threshold and the ice veto. It does not bypass input availability. Supported selected cells are walked in **ascending cell id** and given dense `port_site_id = len(records)` IDs. They remain emitted even when other cells make `port_site_selection_complete=false`.

### Site typing

`_site_type` (`port_sites.py:121`–`:132`) is a first-match priority chain on the **unrounded** indices:

| Priority | Condition | `port_site_type` |
|---|---|---|
| 1 | `strait_access >= 0.55` | `strait_port` |
| 2 | `river_mouth >= 0.50` | `river_mouth_port` |
| 3 | `protected_bay >= 0.55` | `protected_bay_port` |
| 4 | `harbor_suitability >= 0.62` | `harbor_port` |
| 5 | `port_suitability >= 0.58` | `coastal_port` |
| 6 | otherwise | `none` |

A supported cell keeps its raw type only if selected; known nonselection uses `"none"`. Unsupported selection has null type and ID. A selected cell whose raw type resolved to `"none"` — which can only happen through the port-settlement override — is relabelled `port_settlement`. The available type vocabulary remains `{none, protected_bay_port, river_mouth_port, strait_port, harbor_port, coastal_port, port_settlement}`.

### Cell fields and the port site record

Cell fields written for every cell; available numeric indices are rounded to 6 decimals:

| Cell field | Range | Notes |
|---|---|---|
| `protected_bay_index` | `[0, 1]` or null | `protected_bay_supported`; known `0` on water |
| `river_mouth_port_index` | `[0, 1]` or null | `river_mouth_port_supported`; known `0` on water and outside the fluvial branch |
| `strait_access_index` | `[0, 1]` | `0` on water |
| `port_suitability_index` | `[0, 1]` or null | `port_suitability_supported`; known `0` on water |
| `port_site_type` | enum string or null | `"none"` for supported nonselection; null when selection is unsupported |
| `port_site_id` | int or null | `-1` for supported nonselection; null when `port_site_selection_supported=false` |

`world["port_sites"][]` retains supported selected-site records. Its existing fields and the current waterway-link annotation are:

| Field | Type | Definition |
|---|---|---|
| `id` | int | index in ascending-cell-id order |
| `cell_id` | int | host cell |
| `site_type` | string | final `port_site_type` |
| `area_km2` | float | `max(0, cell.area_km2)`, 6 dp |
| `latitude_deg`, `longitude_deg` | float | cell `lat_deg` / `lon_deg`, 6 dp |
| `port_suitability_index` | float | mirror of the cell field |
| `protected_bay_index` | float | mirror |
| `river_mouth_port_index` | float | mirror |
| `strait_access_index` | float | mirror |
| `harbor_suitability_index` | float | from navigability, 6 dp |
| `navigability_index` | float | from navigability, 6 dp |
| `settlement_ids` | int[] | sorted ids of all settlements on this cell |
| `port_settlement_ids` | int[] | subset with `type == "port"` |
| `route_ids` | int[] | union of routes incident on those settlements |
| `marine_region_ids` | int[] | distinct `marine_region_id` of marine neighbours |
| `marine_chokepoint_ids` | int[] | distinct `marine_chokepoint_id` of marine neighbours |
| `navigable_waterway_ids` | int[] or null | IDs on this cell and neighbors when the parent waterway selection is complete |
| `navigable_waterway_links_complete` | bool | False means the link family is unavailable, not a known empty list |
| `landform`, `biome`, `water_body_type` | string | cell mirrors |
| `is_river` | bool | cell mirror |
| `selected_by_port_settlement` | bool | `bool(port_settlement_ids)` |
| `selected_by_suitability` | bool | `(harbor >= 0.62 or port_suitability_index >= 0.58) and not severe_ice` |

`world["port_site_model"]` publishes the thresholds (`0.58` / `0.55` / `0.50` / `0.55`), the model strings, `record_order = "ascending_candidate_cell_id"`, `threshold_semantics = "unrounded_pre_serialization_values_except_record_flags_use_serialized_fields"`, `deterministic: true`, `candidate_cell_count`, `site_count`, and `model_limitation = "diagnostic_port_suitability_without_harbor_bathymetry_tides_waves_sedimentation_engineering_or_economic_optimization"` (`port_sites.py:294`–`:315`).

---

## Route corridors

`enrich_world_with_route_corridors` (`src/magic_geo/route_corridors.py:380`) is the only place in the codebase where a route is turned into an actual sequence of mesh cells. It runs a per-route Dijkstra over the cell neighbour graph under a route-type-specific traversal cost.

### The four feature indices

Written on **every** cell, rounded to 6 decimals (`route_corridors.py:406`–`:413`).

**`mountain_pass_route_index`** (`route_corridors.py:72`–`:100`) — `0.0` for water cells and for cells with no land neighbours:

```
mountain_context = max( clamp((max(neighbour elev) − 700)/2300),
                        clamp(boundary_convergent · 1.9),
                        0.68 if landform ∈ MOUNTAIN_LANDFORMS else 0 )
if mountain_context <= 0.05 and no neighbour elevation >= 900:  return 0
high_mean     = mean of neighbour elevations >= 900, else max neighbour elevation
saddle_gap    = clamp((high_mean − elevation + 260)/1150)
pass_elevation= clamp((elevation − 180)/1700)
relief_window = clamp((max neighbour elev − min neighbour elev)/1900)
ice_penalty   = clamp(ice_thickness_m/280)
index = clamp(0.38·mountain_context + 0.32·saddle_gap + 0.18·relief_window
              + 0.12·pass_elevation − 0.30·ice_penalty)
```

**`river_valley_route_index`** (`route_corridors.py:103`–`:114`) — `0.0` for marine water cells:

| Term | Formula | Weight |
|---|---|---|
| `flow` | `clamp(flow_accumulation / max(1, global max))` | `0.22` |
| `runoff` | `clamp(runoff_mm_y / 850)` | `0.14` |
| `river` | `0.34` if `is_river` | additive |
| `valley` | `0.28` if `landform ∈ RIVER_VALLEY_LANDFORMS` | additive |
| `low_relief` | `clamp(1 − |elevation_m|/1900)` | `0.12` |
| `navigability` | `clamp(river_navigability_index)` | `0.16` |
| `ice_penalty` | `clamp(ice_thickness_m/260)` | `−0.24` |

**`coastal_route_index`** (`route_corridors.py:117`–`:134`) has two branches. For a marine cell: `clamp(shelf + land_contact·0.22 + coastal_nav·0.30 + chokepoint·0.18 + depth_access·0.15)` with `shelf = 0.25` for shelf/inland sea else `0.10`, `land_contact = clamp(land_neighbours/4)`, `depth_access = clamp(1 − water_depth_m/700)`. For a land cell with at least one marine neighbour: `clamp(marine_contact·0.24 + low_relief·0.18 + harbor·0.20 + port·0.18 + coastal_nav·0.20)` with `marine_contact = clamp(marine_neighbours/3)`, `low_relief = clamp(1 − |elev|/1200)`, `port = clamp(port_suitability_index)`. Land cells with no marine neighbour return `0.0`.

**`oasis_route_index`** (`route_corridors.py:137`–`:155`) — `0.0` for water cells. `arid_context = max(clamp(seasonal_aridity_index), 0.72 if biome ∈ DESERT_BIOMES else 0)`; if `arid_context < 0.45` and the cell does not host an `oasis` settlement, return `0.0`. Otherwise:

```
water_access = max( 0.85 if is_river, 0.70 if is_lake,
                    clamp(runoff_mm_y/220), clamp(groundwater_recharge_mm_y/180),
                    clamp(aquifer_productivity_index), clamp(soil_moisture_index) )
index = clamp(0.32·arid_context + 0.43·water_access + 0.12·clamp(fertility)
              + (0.25 if cell hosts an oasis settlement else 0)
              − clamp(ice_thickness_m/200))
```

This is the one feature index with an explicit human input: the set of cells hosting `oasis`-typed settlements both unlocks the index and adds `0.25` (`route_corridors.py:398`–`:404`, `:143`, `:154`).

### The movement cost

`_movement_cost(current, neighbor, route_type, …)` (`route_corridors.py:167`–`:204`) is **directed** — it is evaluated on the destination cell plus the elevation delta, so `cost(a→b) != cost(b→a)` in general.

Shared terms, all computed on `neighbor`: `slope = clamp(|Δelevation|/2000)`, `ice = clamp(ice_thickness_m/320)`, `aridity = clamp(seasonal_aridity_index)`, `mountain = clamp((elevation_m − 1000)/2200)`.

| Route type | `support` | `water_penalty` |
|---|---|---|
| `coastal_sea` | `max(coastal_route_index, navigability_index)` | `0.08` marine · `0.72` coastal land · `1.80` otherwise |
| `river_corridor` | `max(river_valley_route_index, river_navigability_index)` | `1.45` marine · `0.18` if `is_river` · `0.42` otherwise |
| `mountain_pass` | `max(mountain_pass_route_index, 0.45·river_valley_route_index)` | `1.70` if `is_water` · `0.20` otherwise |
| anything else (`overland`) | `max(0.72·river_valley, 0.62·coastal, 0.72·oasis, 0.46·mountain_pass)` | `1.65` marine · `0.20` if `is_river` · `0.34` otherwise |

```
terrain = 0.64 + 0.42·slope + 0.55·ice + 0.18·aridity + 0.20·mountain
          + water_penalty − 0.50·support
edge_cost = great_circle_distance_km(current, neighbor) * max(0.12, terrain)
```

Distance uses the haversine formula against `planet_parameters.radius_km`, with a floor of `0.001` km (`route_corridors.py:26`–`:45`, radius from `src/magic_geo/planet_parameters.py:73`). Because `support <= 1` and the smallest `water_penalty` is `0.08`, `terrain >= 0.22` in practice; the `max(0.12, …)` floor is a non-negativity guard for Dijkstra, and is not expected to bind.

### The path search

`_shortest_route_path` (`route_corridors.py:207`–`:257`) is a standard binary-heap Dijkstra with strict improvement (`next_cost < best_cost.get(neighbor, inf)`), a `visited` set, early exit when the target is popped, and parent-pointer reconstruction. Heap entries are `(cost, cell_id)` so ties break on ascending cell id. Declared as `path_model = "strict_improvement_dijkstra_cost_then_cell_id_heap_v1"`. A degenerate route whose two settlements share a cell returns the single-cell path.

Routes are processed in **ascending route id** (`route_corridors.py:419`). A route whose `from`/`to` settlement is missing, or whose search returns no path, gets `route_corridor_id = -1`, `route_corridor_type = "none"`, `path_cell_ids = []` and produces **no** corridor record.

Current v3 also refuses to infer a path when a competing movement cost is unavailable; an unknown competitor is not silently skipped. The route states are:

| State | `route_path_supported` | `path_cell_ids` | Corridor ID |
|---|---|---|---|
| Known nonempty path | true | Ordered cell IDs | Dense emitted record ID |
| Known absent path | true | `[]` | `-1` |
| Unavailable path | false | null | null |

A known path can still have `route_corridor_diagnostics_supported=false`, retaining its physical path record with null classification and affected feature diagnostics. Thus known path, complete diagnostics and complete membership are separate claims.

### Corridor classification and cell assignment

`_primary_corridor_type` (`route_corridors.py:274`–`:288`) counts path cells whose feature index is `>= 0.45` (one shared threshold, `MOUNTAIN_PASS_THRESHOLD = RIVER_VALLEY_THRESHOLD = COASTAL_ROUTE_THRESHOLD = OASIS_ROUTE_THRESHOLD = 0.45`, `route_corridors.py:13`–`:16`), then:

1. `route_type == "coastal_sea"` and `coastal_corridor` count `> 0` → `coastal_corridor`;
2. `route_type == "river_corridor"` and `river_valley_corridor` count `> 0` → `river_valley_corridor`;
3. `route_type == "mountain_pass"` and `mountain_pass_corridor` count `> 0` → `mountain_pass_corridor`;
4. otherwise the highest count, ties broken lexicographically by name; if the best count is `0` → `overland_corridor`.

When all route paths and required diagnostics are complete, each accepted path contributes cell membership using the unchanged equation:

```
feature_support = max of the four feature indices on that cell
membership      = clamp(0.35 + feature_support * 0.65)          # in [0.35, 1.0]
if membership >= cell.route_corridor_index:                      # note >=, not >
    cell.route_corridor_index = round(membership, 6)
    cell.route_corridor_type  = corridor_type
    cell.route_corridor_id    = corridor_id
```

The `>=` comparison means a **later** route wins equal ties, which is why the declared `cell_assignment_model` is `maximum_membership_with_later_route_winning_equal_ties_v1`. Under complete membership, untouched cells keep `route_corridor_index = 0.0`, `route_corridor_type = "none"`, `route_corridor_id = -1`. If `route_corridor_membership_complete=false`, all three cell membership fields are null; a known local path cannot establish global ownership by itself.

### The corridor record

`world["route_corridors"][]` contains one record per supported nonempty path. Existing physical fields remain known; current diagnostic and link fields carry separate coverage:

| Field | Type | Definition |
|---|---|---|
| `id` | int | corridor index, equals position in the array |
| `route_id` | int | the source route |
| `route_type` | string | the native route type string |
| `corridor_type` | string or null | Available vocabulary: `mountain_pass_corridor`, `river_valley_corridor`, `coastal_corridor`, `oasis_corridor`, `overland_corridor` |
| `from_settlement_id`, `to_settlement_id` | int | route `from` / `to` |
| `start_cell_id`, `end_cell_id` | int | host cells of those settlements |
| `cell_count` | int | `len(cell_ids)` |
| `cell_ids` | int[] | the ordered path, start first |
| `path_length_km` | float | sum of haversine step distances, 6 dp |
| `straight_distance_km` | float | `max(0.001, route.distance_km)`, 6 dp |
| `detour_ratio` | float | `path_length_km / straight_distance_km`, 6 dp |
| `mean_route_corridor_index`, `max_route_corridor_index` | float or null | Over path cells after complete membership assignment |
| `mean_mountain_pass_route_index` | float | over path cells |
| `mean_river_valley_route_index` | float | over path cells |
| `mean_coastal_route_index` | float or null | Over path cells when coastal diagnostics are supported |
| `mean_oasis_route_index` | float | over path cells |
| `mountain_pass_cell_count` | int | path cells with that index `>= 0.45` |
| `river_valley_cell_count` | int | as above |
| `coastal_cell_count` | int or null | As above, when coastal diagnostics are supported |
| `oasis_cell_count` | int | as above |
| `named_feature_cell_count` | int or null | Path cells where any feature is `>= 0.45`, when diagnostics are supported |
| `settlement_ids` | int[] | sorted `{from, to}` minus `-1` |
| `region_ids` | int[] | sorted political region ids of the two settlements, minus `-1` |
| `route_ids` | int[] | always `[route_id]` |
| `navigable_waterway_ids` | int[] or null | Known parent waterway IDs, with `navigable_waterway_links_complete` |
| `port_site_ids` | int[] or null | Known parent port IDs, with `port_site_links_complete` |
| `route_path_supported` | bool | True for every emitted nonempty-path record |
| `route_corridor_diagnostics_supported` | bool | Whether the record's full classification/feature diagnostics are available |
| `route_corridor_membership_complete` | bool | Whether global cell ownership and its derived means are available |
| `navigable_waterway_links_complete`, `port_site_links_complete` | bool | Whether each linked source family is known along this path |

`world["route_corridor_model"]` publishes the sub-model strings (`mountain_pass_model`, `river_valley_model`, `coastal_model`, `oasis_model`, `movement_cost_model`, `path_model`, `corridor_classification_model`, `cell_assignment_model`), the source model links to navigability / port / aquifer, `planet_radius_km`, `feature_threshold: 0.45`, `threshold_semantics: "serialized_feature_indices"`, `deterministic: true`, `route_count`, `corridor_count`, and `model_limitation = "diagnostic_static_corridors_without_capacity_congestion_seasonality_construction_cost_network_equilibrium_or_multimodal_scheduling"` (`route_corridors.py:470`–`:492`).

Note the threshold semantics differ from the port model: corridor feature counts are evaluated against the **serialized (6-decimal rounded)** indices, while port typing uses the unrounded pre-serialization values.

---

## How corridors differ from routes

| Aspect | `routes[]` (native) | `route_corridors[]` (Python) |
|---|---|---|
| Produced by | `generate_routes`, `cpp/src/engine/settlements.cpp:103` | `enrich_world_with_route_corridors`, `src/magic_geo/route_corridors.py:380` |
| Present in geo-only worlds | no (society stage skipped, and the key is stripped) | no |
| Geometry | two endpoints only; no intermediate cells | full ordered cell path over the mesh neighbour graph |
| Cost model | endpoint-pair barrier multiplier × great-circle distance | per-edge directed terrain cost accumulated by Dijkstra |
| Selection | 2 nearest-by-cost links per settlement, deduplicated to unordered pairs | One record per supported nonempty path; unknown competing inputs withhold the inferred path |
| Distance | `distance_km` = straight great-circle | `path_length_km` = summed steps; `detour_ratio` relates the two |
| Type vocabulary | `overland`, `river_corridor`, `coastal_sea`, `mountain_pass` | `overland_corridor`, `river_valley_corridor`, `coastal_corridor`, `mountain_pass_corridor`, `oasis_corridor` |
| Cell footprint | none | `route_corridor_index/_type/_id` after complete path/diagnostic membership; otherwise null |
| Cardinality | `<= 2 · settlement_count` | Current emitted count equals supported nonempty paths and is `<= route_count`; historical v1 inline validation required equality |

The corridor layer is explicitly a **diagnostic overlay on top of** the route network, not a replacement for it: the route decides *which* settlements are connected and by what mode, the corridor decides *where the connection goes*. The route's `cost` is never recomputed from the corridor path.

---

## Natural frontiers

`enrich_world_with_natural_frontiers` (`src/magic_geo/natural_frontiers.py:166`) is the only model in this layer whose *input* is a political product: it consumes `world["borders"]`, the native `BorderSegment` array. It answers "which stretches of political border are actually physical geography?".

### Input: the native border segment

`generate_border_segments` (`cpp/src/engine/civilization.cpp:242`) emits one segment per adjacent land cell pair belonging to different political regions. Its two load-bearing fields:

`type` from `border_type_for_cells` (`civilization.cpp:222`), first match wins:

| Priority | Condition | `BORDER_TYPE_NAMES` value |
|---|---|---|
| 1 | either cell `is_river` | `river` |
| 2 | either landform is `mountain_belt` (6) or `glacial_valley` (17), or either `elevation_m > 1400` | `mountain` |
| 3 | either biome is `cold_desert` (9) or `hot_desert` (10) | `desert` |
| 4 | either landform is `ice_field` (5) or either biome is `ice_cap` (3) | `ice` |
| 5 | either landform is `coastal_plain` (14) | `coastal` |
| 6 | otherwise | `open_lowland` |

`barrier_score` (`civilization.cpp:264`–`:272`):

```
relief = |a.elevation_m − b.elevation_m|
hazard = 0.5·(a.conv + b.conv) + 0.25·(a.trans + b.trans)
barrier_score = clamp(0.18 + relief/2500 + 0.45·hazard
                      + (type ∈ {mountain, desert, ice} ? 0.34 : 0.0), 0, 1)
```

### Candidate borders and per-cell scoring

A border is a frontier candidate when `type != "open_lowland"` **or** `barrier_score >= 0.45` (`natural_frontiers.py:74`–`:75`, threshold at `:7`). Both endpoint cells of every candidate border become candidate cells.

`_cell_barrier_type` (`natural_frontiers.py:26`–`:47`), first match:

| Priority | Condition | Type |
|---|---|---|
| 1 | `ice_thickness_m > 40` or `permafrost_class ∈ {continuous, ice_sheet}` | `ice` |
| 2 | `is_river` or `landform ∈ RIVER_LANDFORMS` (`delta`, `floodplain`, `river_valley`, `alluvial_fan`) | `river` |
| 3 | `water_body_type ∈ {ocean, continental_shelf, inland_sea}` | `coastal` |
| 4 | `landform ∈ MOUNTAIN_LANDFORMS` or `|elevation_m| >= 1600` | `mountain` |
| 5 | `biome ∈ DESERT_BIOMES` or `seasonal_aridity_index >= 0.72` | `desert` |
| 6 | `biome ∈ DENSE_FOREST_BIOMES` | `dense_forest` |
| 7 | `biome == "wetland"` or `landform == "wetland"` | `wetland` |
| 8 | otherwise | `open_lowland` |

`_cell_barrier_score` (`natural_frontiers.py:50`–`:67`) is a **maximum**, not a sum:

| Signal | Value |
|---|---|
| `mountain` | `clamp((|elevation_m| − 700)/2400)`, raised to at least `0.76` if `landform ∈ MOUNTAIN_LANDFORMS` |
| `ice` | `clamp(ice_thickness_m/420)`, raised to at least `0.58` for `continuous`/`ice_sheet` permafrost |
| `river` | `0.62` if `is_river` or fluvial landform |
| `coast` | `0.54` for marine `water_body_type` |
| `desert` | `clamp(seasonal_aridity_index)`, raised to at least `0.66` for a desert biome |
| `forest` | `0.58` for a dense-forest biome |
| `wetland` | `0.52` for wetland biome or landform |
| result | `clamp(max(all of the above))` |

`_frontier_index` (`natural_frontiers.py:87`–`:91`):

```
natural_floor = 0.45 if border.type != "open_lowland" else 0.0
frontier_index = clamp(max( 0.72·border.barrier_score + 0.28·mean(cell_a, cell_b barrier scores),
                            border.barrier_score,
                            natural_floor ))
```

Because a candidate either has a non-`open_lowland` type (floor `0.45`) or `barrier_score >= 0.45`, every candidate cell ends with `frontier_index >= 0.45`. Cell assignment uses **strict** improvement in border iteration order (`natural_frontiers.py:206`), so the first border wins ties — the declared `cell_assignment_model` is `maximum_frontier_index_strict_improvement_in_border_order_v1`.

Frontier type per border (`natural_frontiers.py:78`–`:84`): if the border type is not `open_lowland`, use it verbatim; otherwise count the two cells' barrier types, drop `open_lowland`, and take the highest count with a lexicographic tie-break, falling back to `terrain_barrier`.

### Components and the frontier record

Candidate cells are grouped into connected components of the mesh neighbour graph by BFS seeded from the smallest remaining id, and records are emitted in ascending minimum-cell-id order (`natural_frontiers.py:94`–`:116`, `:214`). A component's "borders" are all candidate borders with **either** endpoint inside the component (`natural_frontiers.py:219`–`:221`).

`world["natural_frontiers"][]` — 17 fields (`natural_frontiers.py:250`–`:270`):

| Field | Type | Definition |
|---|---|---|
| `id` | int | component index |
| `frontier_type` | string | most common border frontier type in the component, lexicographic tie-break, fallback `terrain_barrier` |
| `cell_count` | int | member cells |
| `cell_ids` | int[] | sorted member cell ids |
| `border_segment_count` | int | number of touching candidate borders |
| `border_ids` | int[] | sorted, non-negative |
| `region_ids` | int[] | sorted distinct `region_a`/`region_b` of those borders |
| `area_km2` | float | sum of member `area_km2`, 6 dp |
| `total_border_length_km` | float | sum of touching border `length_km`, 6 dp |
| `mean_barrier_score` | float | mean native `barrier_score` over touching borders (`0.0` if none) |
| `mean_frontier_index` | float | mean `natural_frontier_index` over member cells |
| `dominant_landform` | string | most common member landform, lexicographic tie-break |
| `dominant_biome` | string | most common member biome |
| `settlement_ids` | int[] | settlements hosted on member cells |
| `route_ids` | int[] | routes whose two endpoint settlements sit in the two regions of a touching border (`natural_frontiers.py:132`–`:149`) |
| `route_crossing_count` | int | `len(route_ids)` |
| `navigable_waterway_ids` | int[] | waterways covering member cells |

Cell fields: `natural_frontier_index` (`[0,1]`, `0.0` off-frontier), `natural_frontier_type` (`"none"` off-frontier), `natural_frontier_id` (`-1` off-frontier).

`world["natural_frontier_model"]` publishes `natural_border_threshold: 0.45`, the full `cell_barrier_parameters` block (`mountain_base_elevation_m: 700`, `mountain_elevation_scale_m: 2400`, `mountain_landform_floor: 0.76`, `mountain_type_elevation_m: 1600`, `ice_thickness_scale_m: 420`, `ice_type_thickness_m: 40`, `permafrost_ice_floor: 0.58`, `river_score: 0.62`, `coastal_score: 0.54`, `desert_biome_floor: 0.66`, `desert_type_aridity_threshold: 0.72`, `dense_forest_score: 0.58`, `wetland_score: 0.52`), `frontier_index_parameters` (`border_weight: 0.72`, `local_weight: 0.28`, `hard_type_floor: 0.45`), and `model_limitation = "diagnostic_border_endpoint_components_without_exact_native_edge_polygons_boundary_negotiation_or_historical_change"` (`natural_frontiers.py:290`–`:324`).

---

## Validators

All of the below run inside the single full-world gate:

```bash
magic-geo validate --world runs/world.json
```

(`src/magic_geo/cli/commands/validate.py:92`; the command exits non-zero on any failure.) They do **not** run under `validate-geo` — that command calls `validate_geo_world` on the natural-only report (`src/magic_geo/cli/commands/validate_geo.py:23`–`:88`).

Current transport v3 goes through `validate_public_human_water_transport` and the independent versioned replay in `human_water_transport_validation.py`, after natural-parent validation. It audits matching own/source declarations, strict support flags, nullable values, complete record coverage and path linkage. Emitted corridor count equals supported **nonempty** paths, not necessarily native route count. Explicit historical v1 uses the inline scalar checks described below; explicit v2 retains its own independent numerical path. These historical descriptions do not impose numeric or known-absence assumptions on unavailable v3 output.

### `_validate_settlement_selection`

`src/magic_geo/cli/validators/settlement.py:22`, invoked at `validate.py:10584`. Emits the single failure string `"settlement selection model or causal replay invalid"`.

| Stage | What it asserts |
|---|---|
| Metadata | Exact own-version dispatch and matching summary identity select current v3 or explicit historical v2. Each family's expected score/candidate descriptors, all weights/adjustments and precision policy are checked. V3 additionally requires the exact typed `annual_climate_applicability` declaration; historical v2 rejects successor markers. Candidate, target and settlement counts are checked against replay |
| Annual support | V3 independently reconstructs the retained annual source, verifies the round-trip temperature and strict open-interval flag, and requires unavailable score zero. Genuine historical seasonal-v2 archives retain native source/coverage audits but use their original score replay inputs |
| Score replay | Independently recomputes local relief, aridity, monthly PET dry/wet month counts, soil/biome/resource decisions, water access, climate score, hazard, cold-biome multiplier and landform adjustments; current v3 then applies the final annual-support gate before comparing `cells[].settlement_score` |
| Score tolerance | `max(1e-9, 16·10^-selection_score_precision, 10^-output_float_precision)`; with the default `float_precision = 4` this is `1e-4` (`settlement.py:312`–`:314`) |
| Selection replay | Recomputes each family's eligible candidates/neighbors, descending-score/ascending-id sort, `target`, `min_sep = 2.4·sqrt(4π/N)` and the greedy pass using `position_3d` and `acos(clamp(dot))`; requires `[s.cell_id for s in settlements] == selected_ids` exactly |
| Counts | `model.candidate_cell_count`, `model.target_count`, `model.settlement_count`, `summary.settlement_count` all match the replay |
| Record mirrors | For each settlement: `id == index`, `type` matches the replayed type chain, `score` matches the cell's score exactly, coordinates/fertility meet the existing serialization tolerance, and biome/resource/water/river/culture/language mirrors match the host cell. `region_id` instead matches the political region's settlement-membership list; settlement allegiance can differ from the host cell's territorial assignment |
| Summary | `summary.top_settlement_score` equals `settlements[0].score` exactly, or `0.0` when there are no settlements (`settlement.py:457`–`:461`) |

The score replay is the reason this validator is a genuine gate on the native engine and not just a schema check: any change to `derive_soils_biomes_resources` or `derive_landforms` that is not mirrored in `settlement.py` fails the world.

### `_validate_route_network`

`src/magic_geo/cli/validators/settlement.py:465`, invoked at `validate.py:10585`. Failure string `"route network model or causal replay invalid"`.

| Stage | What it asserts |
|---|---|
| Metadata | All 15 `route_network_model` keys, including the exact `barrier_parameters` and `ranking_discounts` dicts and the two mountain-route thresholds |
| Structure | `sorted(settlement ids) == list(range(len(settlements)))` — dense, zero-based settlement ids |
| Replay | Re-runs the whole endpoint ranking with `radius = planet_parameters.radius_km` (must be `> 0`), the barrier function, both ranking discounts, the 2-link cut, the unordered-pair dedup, the route type chain and the type-based cost discount, producing an expected route list |
| Counts | `len(routes)`, `model.settlement_count`, `model.route_count`, `summary.route_count` |
| Per-route | `id`, `from`, `to`, `type` exact; `distance_km` within `10^-precision`; `cost` within `max(output_unit, distance·0.45·0.75·output_unit + output_unit)` — a forward-error bound derived from the barrier's tectonic term against the serialized-input quantization grid (`settlement.py:691`–`:707`) |

### Historical v1 `_validate_port_sites`

`src/magic_geo/cli/validators/ports.py:21`, invoked at `validate.py:10856`. Failure string `"port site model or causal replay invalid"`. It re-derives `protected_bay`, `river_mouth`, `strait_access`, `port_suitability`, `severe_ice`, `selected` and the type chain for every cell, then the record list in ascending candidate cell id, then compares:

- the four cell indices within `1e-9` of the 6-decimal replay, plus exact `port_site_type` and `port_site_id`;
- `len(port_sites)` and every one of the 24 record fields by exact equality (`ports.py:436`–`:440`);
- `model.candidate_cell_count`, `model.site_count`;
- 14 summary keys including `port_site_total_area_km2`, the four `mean_*` indices, `port_settlement_count`, `port_settlement_with_site_count`, the three per-type counts and `port_site_type_counts`.

A separate structural block starting at `validate.py:10858` independently checks the port cell-field invariants: all four indices in `[0,1]`; water cells must have all four indices exactly `0.0`, type `"none"` and id `-1`; `site_id == -1 ⟺ site_type == "none"`; `site_type` drawn from the seven-value allowed set; and the candidate set recomputed from `port_suitability >= 0.58 and not severe_ice` or port-settlement membership must equal the assigned set.

### Historical v1 `_validate_route_corridors`

`src/magic_geo/cli/validators/corridors.py:24`, invoked at `validate.py:17996`. Failure string `"route corridor model or causal replay invalid"`. This is the heaviest replay in the layer: it re-implements all four feature indices, the directed movement cost, the Dijkstra, the classification chain and the cell-assignment `>=` rule, then checks:

- `model.planet_radius_km` within `1e-9` of the configured radius, `feature_threshold` within `1e-12` of `0.45`, and all 16 string-valued model keys (`model_type`, the three `source_*_model` links, `domain`, the four feature sub-models, `movement_cost_model`, `path_model`, `corridor_classification_model`, `cell_assignment_model`, `record_order`, `threshold_semantics`, `model_limitation`) plus `deterministic` and `summary.route_corridor_model` (`corridors.py:43`–`:79`);
- the five per-cell corridor fields within `1e-9`, plus exact `route_corridor_type` and `route_corridor_id`;
- the three in-place route mutations (`route_corridor_id`, `route_corridor_type`, `path_cell_ids`) for **every** route, including the not-found branches;
- every corridor record field by exact equality;
- `model.route_count`, `model.corridor_count`;
- 15 summary keys, compared by exact equality against a fully recomputed `expected_summary` dict (`corridors.py:669`–`:728`).

The structural block that follows adds assertions the replay does not: `route_corridor_count` must equal `len(routes)` (`validate.py:18004`); consecutive `cell_ids` must be **mesh-adjacent** (`validate.py:18125`); `cell_ids[0] == start_cell_id == source settlement cell`; `cell_ids[-1] == end_cell_id`; and the cell invariant `route_corridor_id == -1 ⟺ (type == "none" and index ≈ 0)`.

### Natural frontier checks

There is no separate frontier validator module; the checks are inline at `validate.py:17661`–`:17889`. They assert:

- 15 summary keys present (`validate.py:17662`–`:17678`): eight base keys plus the seven `{type}_frontier_count` keys. The `natural_frontier_model` summary string is written by the enricher (`natural_frontiers.py:325`) but is not part of this presence set;
- the three cell fields present and internally consistent: `0 <= index <= 1`, `id >= -1`, `id == -1 ⟹ index == 0 and type == "none"`, `id >= 0 ⟹ index >= 0.45 and type != "none"`;
- `natural_frontier_count == len(natural_frontiers)`, `natural_frontier_cell_count == #{cells with index >= 0.45}`, `mean_natural_frontier_index` within `0.001`;
- per record: `id == index`, non-empty non-`"none"` `frontier_type`, unique `cell_ids`, `cell_count`, `border_segment_count`, `route_crossing_count`, membership subset of the candidate set, every member cell's `natural_frontier_id == id`, `region_ids` equal to the union over the record's borders, `area_km2` and `total_border_length_km` within `max(0.001, 0.01%)`, `mean_barrier_score` and `mean_frontier_index` within `0.001`, and referential integrity of `border_ids` (each must be a natural border touching the component), `settlement_ids` (each must be hosted on a member cell), `route_ids`, `navigable_waterway_ids` and `region_ids`;
- the component partition is exact: assigned cells `==` candidate cells;
- `mean_natural_frontier_barrier_score` equals the mean over the union of assigned border ids, or `0.0` when there are none.

### Worldbuilding realism checks touching this layer

`enrich_world_with_worldbuilding_realism` (`src/magic_geo/worldbuilding_realism.py:145`) emits five checks; two are settlement/route checks, gated by the block starting at `validate.py:17891`.

| Check `name` | Metric | Value | Target |
|---|---|---|---|
| `large_settlement_water_access` | `fraction_top_settlements_with_water_access` | fraction of the top `max(1, min(n, max(5, (n+3)//4)))` settlements by score whose cell is `is_river`, `is_lake`, in a water-access water body, has `runoff_mm_y >= 120`, or is coastal land | `[0.85, 1.0]` |
| `route_barrier_avoidance` | `fraction_routes_below_type_specific_barrier_cost` | fraction of routes whose friction `cost/max(1, distance_km)` is `<= 0.95` (`coastal_sea`), `1.10` (`river_corridor`), `1.75` (`mountain_pass`) or `1.35` (otherwise) | `[0.8, 1.0]` |

Thresholds at `worldbuilding_realism.py:85`–`:92`, records at `:175`–`:218`. With no settlements or no routes the fractions default to `1.0`, so an empty layer trivially passes — these checks cannot detect a missing layer.

---

## Geo-only mode: what disappears and what it implies

Native geo generation skips society. Some historical civilization arrays/counters are still emitted as empty/default schema fields, but the current native social availability envelope is conditional and is absent in geo scope. Raw full and geo shapes therefore already differ.

Python `_strip_native_civilization_outputs` removes civilization fields before the shared natural enrichment phases, then sets `world["generation_scope"] = "geo_only"`. Missing social inference is an explicit scope, not an observed empty society.

| Removed scope | Settlement-layer entries |
|---|---|
| Top-level keys | `settlements`, `routes`, other civilization arrays/declarations and any native social availability envelope |
| Per-cell fields | `settlement_score`, `settlement_climate_supported`, `settlement_climate_temperature_c`, `political_region_id`, `culture_region_id`, `language_region_id` |
| Summary keys | Settlement/route/social counts, estimates, model mirrors and availability markers |

`generate_geo_world` additionally raises `ValueError` unless `output.include_cells` is true (`api.py:296`–`:300`).

Because `enrich_world_with_navigability_diagnostics`, `enrich_world_with_port_sites`, `enrich_world_with_route_corridors`, `enrich_world_with_natural_frontiers`, `enrich_world_with_land_use_zones`, `enrich_world_with_worldbuilding_realism` and `enrich_world_with_settlement_route_models` are all absent from the geo-only sequence (`api.py:307`–`:374`), a geo-only world contains **none** of the following:

| Absent top-level keys | Absent cell fields |
|---|---|
| `settlement_selection_model`, `route_network_model` | `settlement_score` |
| `navigable_waterways`, `navigability_model` | `river_navigability_index`, `coastal_navigability_index`, `harbor_suitability_index`, `transport_chokepoint_index`, `navigability_index`, `navigability_class`, `navigable_waterway_id` |
| `port_sites`, `port_site_model` | `protected_bay_index`, `river_mouth_port_index`, `strait_access_index`, `port_suitability_index`, `port_site_id`, `port_site_type` |
| `route_corridors`, `route_corridor_model` | `mountain_pass_route_index`, `river_valley_route_index`, `coastal_route_index`, `oasis_route_index`, `route_corridor_index`, `route_corridor_type`, `route_corridor_id` |
| `natural_frontiers`, `natural_frontier_model` | `natural_frontier_index`, `natural_frontier_type`, `natural_frontier_id` |
| `agricultural_zones`, `mining_zones`, `land_use_zone_model` | `agricultural_potential_index`, `mining_potential_index`, `agricultural_zone_id`, `mining_zone_id` |
| `worldbuilding_realism_checks`, `worldbuilding_realism_model` | — |

Current natural water v2, ecosystem E5 and native wildfire v7 do not read settlement score in either scope; removing S does not select a separate pristine natural formula. Both API paths share the physical foundation and ecology/resource sequence. Current resource v5 economic access/viability are unavailable in geo scope (null with false support), while separately named geographic baseline fields remain numeric. Human transport, land-use and worldbuilding stages are skipped. Explicit older models retain their historical default behavior when independently replayed. See the [current availability and geo contract](../../settlement_social_availability.md#reading-unknown-and-empty-results); `enrich_world_with_geo_evolution_provenance` records the natural-only scope.

---

## Worked examples

### Generate both scopes and validate the full world

```bash
magic-geo generate --config configs/earthlike_seed.yaml --output runs/world.json
magic-geo validate --world runs/world.json

magic-geo generate --config configs/earthlike_seed.yaml --geo-only --output runs/geo.json
magic-geo validate-geo --world runs/geo.json --profile earthlike
```

### Read the settlement layer from Python

```python
from magic_geo.api import generate_from_file

world = generate_from_file("configs/earthlike_seed.yaml")

model = world["settlement_selection_model"]
print(model["candidate_cell_count"], model["target_count"], model["settlement_count"])

for s in world["settlements"][:5]:
    print(s["id"], s["type"], round(s["score"], 4), s["biome"], s["resource"])

for r in world["routes"][:5]:
    # Unknown inferred paths remain distinct from known empty paths.
    path_size = (len(r["path_cell_ids"]) if r["route_path_supported"] is True
                 else "unavailable")
    print(r["id"], r["from"], "->", r["to"], r["type"],
          round(r["distance_km"], 1), round(r["cost"], 1),
          "corridor", r["route_corridor_id"], r["route_corridor_type"],
          "cells", path_size)

for c in world["route_corridors"][:5]:
    print(c["id"], c["corridor_type"], c["cell_count"],
          round(c["path_length_km"], 1), round(c["detour_ratio"], 3))

for p in world["port_sites"][:5]:
    print(p["id"], p["site_type"], round(p["port_suitability_index"], 3),
          p["selected_by_port_settlement"], p["selected_by_suitability"])

for f in world["natural_frontiers"][:5]:
    print(f["id"], f["frontier_type"], f["cell_count"],
          round(f["mean_barrier_score"], 3), f["route_crossing_count"])
```

### A route cost by hand

Two settlements 900 km apart on a 6371 km planet. Endpoint A: `elevation_m = 400`, `boundary_convergent = 0.30`, `boundary_transform = 0.0`, biome `temperate_forest`, `is_river = false`. Endpoint B: `elevation_m = 2400`, `boundary_convergent = 0.10`, `boundary_transform = 0.0`, biome `alpine`.

```
mountain        = clamp((2400 − 1200)/2600)          = 0.461538
tectonic_hazard = 0.50·(0.30 + 0.10) + 0.25·(0 + 0)  = 0.200000
arid            = 0.0                                 (neither biome is a desert)
barrier         = 1 + 0.95·0.461538 + 0.45·0.200000  = 1.528462
route type      : B elevation 2400 > 1300            → mountain_pass  (no discount)
cost            = 900 · 1.528462                     = 1375.62
friction        = cost/distance = 1.528462           ≤ 1.75  → counts as a low-barrier route
```

### Site spacing by hand

`mesh.cell_count = 8000`, `planet.radius_km = 6371`:

```
target  = clamp(8000 // 180, 8, 64) = clamp(44, 8, 64) = 44
min_sep = 2.4 · sqrt(4π / 8000)     = 0.095120 rad     = 606.0 km
```

So at most 44 settlements, each at least ~606 km from every other. Doubling the mesh to 16 000 cells divides the spacing by `sqrt(2)` — to ~428 km, not half of 606 — and raises the target to 64, where it saturates.

---

## Summary keys contributed by this layer

Native (`cpp/src/engine/summary.cpp`), all stripped in geo-only mode:

| Key | Value | Source |
|---|---|---|
| `settlement_count` | `settlements.size()` | `summary.cpp:1823` |
| `route_count` | `routes.size()` | `summary.cpp:1824` |
| `top_settlement_score` | `settlements.front().score`, or `0.0` when empty; precision `max(8, float_precision)` | `summary.cpp:1908`–`:1914` |

Python enricher summary keys (all absent in geo-only mode):

| Key | Producer |
|---|---|
| `settlement_selection_model`, `route_network_model` | `settlement_routes.py:135`–`:136` |
| `port_site_model`, `port_site_count`, `port_candidate_cell_count`, `port_site_total_area_km2`, `mean_port_suitability_index`, `mean_protected_bay_index`, `mean_river_mouth_port_index`, `mean_strait_access_index`, `port_settlement_count`, `port_settlement_with_site_count`, `protected_bay_port_site_count`, `river_mouth_port_site_count`, `strait_port_site_count`, `port_site_type_counts` | `port_sites.py:316`–`:339` |
| `route_corridor_model`, `route_corridor_count`, `route_corridor_cell_count`, `route_corridor_total_path_length_km`, `mean_route_corridor_index`, `mean_mountain_pass_route_index`, `mean_river_valley_route_index`, `mean_coastal_route_index`, `mean_oasis_route_index`, `route_feature_coverage_index`, `mountain_pass_route_corridor_count`, `river_valley_route_corridor_count`, `coastal_route_corridor_count`, `oasis_route_corridor_count`, `route_corridor_type_counts` | `route_corridors.py:493`–`:516` |
| `natural_frontier_model`, `natural_frontier_count`, `natural_frontier_cell_count`, `natural_frontier_border_segment_count`, `natural_frontier_total_area_km2`, `natural_frontier_total_length_km`, `mean_natural_frontier_index`, `mean_natural_frontier_barrier_score`, `natural_frontier_type_counts`, and `mountain_frontier_count`, `river_frontier_count`, `desert_frontier_count`, `coastal_frontier_count`, `ice_frontier_count`, `dense_forest_frontier_count`, `wetland_frontier_count` | `natural_frontiers.py:279`–`:325` |
| `large_settlement_water_access_index`, `route_barrier_avoidance_index` (plus three non-settlement checks) | `worldbuilding_realism.py` |

Current summary coverage includes `navigable_waterway_selection_complete`, `navigability_estimates_complete`, `port_site_selection_complete`, the three port mean-support flags, `route_path_selection_complete`, `route_corridor_diagnostics_complete`, `route_corridor_membership_complete` and `coastal_route_estimates_complete`. Emitted record counts remain literal; unavailable family estimates/counts are null rather than supported-only renormalizations. `route_feature_coverage_index` is the fraction of records with a named-feature cell when diagnostics are complete. A complete empty diagnostic family yields `1.0`; incomplete diagnostics yield null, even if no records were emitted.

---

## Configuration surface

There is **no settlement, route, port, corridor or frontier tuning section in the configuration schema**. `generate_settlements` reads `params.temperature_model` to choose its applicability prerequisite, and `generate_routes` reads `params.radius_km`. The thresholds and weights documented here remain source constants.

Resolution, radius and output precision affect these outputs directly:

| Config key | Effect | Source |
|---|---|---|
| `mesh.cell_count` | drives `target = clamp(N/180, 8, 64)` and `min_sep = 2.4·sqrt(4π/N)`, and therefore the number and spacing of settlements | `src/magic_geo/config.py:244`; `settlements.cpp:51`–`:54` |
| `planet.radius_km` | scales `distance_km` and `cost` on every route, and every corridor path length | `src/magic_geo/config.py:161`; `settlements.cpp:114` |
| `output.float_precision` (default `4`, range `0–8`) | the serialization grid for `distance_km`/`cost` and the corridor/port indices; also sets `selection_score_precision = max(8, p)` and the validator tolerances | `src/magic_geo/config.py:450` |

Everything else — climate, tectonics, hydrology, erosion — reaches this layer only through `settlement_score` and the cell fields the enrichers read.

---

## Limitations and unresolved claims

- **No population, size, or tier.** The settlement record has no population, size class, tier, or rank field. `score` is a static suitability index in `[0, 1]`, not a demographic quantity. The `settlement_selection_model` states its own limitation verbatim: `static_suitability_selection_without_population_growth_land_market_or_infrastructure_feedback`.
- **Routes are endpoint-only.** The native route network never looks at the terrain between its endpoints. `route_network_model.model_limitation` says so: `endpoint_only_network_selection_before_downstream_cell_path_routing_capacity_congestion_and_equilibrium`. The barrier multiplier is evaluated on the two endpoint cells alone, so a route can cross an unmodelled mountain range at low cost if both endpoints are low.
- **Corridors are diagnostic, not authoritative.** `route_corridor_model.model_limitation` is `diagnostic_static_corridors_without_capacity_congestion_seasonality_construction_cost_network_equilibrium_or_multimodal_scheduling`. The corridor path never feeds back into the route's `cost` or into any native state.
- **Port suitability is not a harbour engineering model.** `port_site_model.model_limitation` is `diagnostic_port_suitability_without_harbor_bathymetry_tides_waves_sedimentation_engineering_or_economic_optimization`. There is no tidal range, wave climate, siltation rate, dredging, or berth-depth reasoning anywhere in the layer.
- **Natural frontiers are endpoint components, not polygons.** `natural_frontier_model.model_limitation` is `diagnostic_border_endpoint_components_without_exact_native_edge_polygons_boundary_negotiation_or_historical_change`. A frontier record is a connected component of border-endpoint **cells**, so its `area_km2` is the area of those cells, not the area of a boundary strip, and its `total_border_length_km` double-counts nothing but also does not correspond to a simplified polyline.
- **Several enum branches in the Python layer can never fire.** The landform and biome name sets in the enrichers include values that are not in the native enums (`cpp/src/engine/schema_names.hpp:21`, `:37`):

  | Set | Members that are real native values | Members that can never match |
  |---|---|---|
  | `route_corridors.MOUNTAIN_LANDFORMS` (`:17`) | `volcanic_arc`, `glacial_valley` | `mountain`, `mountain_range`, `highland`, `ridge` |
  | `natural_frontiers.MOUNTAIN_LANDFORMS` (`:9`) | `volcanic_arc` | `mountain`, `mountain_range`, `highland`, `ridge` |
  | `route_corridors.RIVER_VALLEY_LANDFORMS` (`:18`) | `delta`, `floodplain`, `river_valley`, `alluvial_fan` | `wetland` (a biome name, not a landform) |
  | `route_corridors.DESERT_BIOMES` (`:19`), `natural_frontiers.DESERT_BIOMES` (`:10`) | `hot_desert`, `cold_desert` | `desert`, `semi_arid_desert` |
  | `natural_frontiers.DENSE_FOREST_BIOMES` (`:11`) | `tropical_rainforest`, `tropical_seasonal_forest` | `temperate_rainforest` |
  | `natural_frontiers._cell_barrier_type` `landform == "wetland"` (`:45`) | — | `wetland` is not in `LANDFORM_NAMES` |

  Most consequentially, **`mountain_belt` — the native landform for a mountain range (`LANDFORM_NAMES[6]`) — is in neither mountain-landform set.** A cell on a genuine orogenic belt therefore receives no landform-based mountain bonus in `_mountain_pass_index` or `_cell_barrier_score`; it can only reach those signals through the elevation and `boundary_convergent` terms. The mirrored constants in `src/magic_geo/cli/_constants.py:199`–`:219` reproduce the same sets, so the validators confirm the behaviour rather than flag it. This is reported as observed source behaviour; the intent behind these sets is not documented in the tree and is not resolved here.
- **Inland lake shore access is indirect.** The coastal score and port type use marine neighbors. Terrestrial cells near lakes depend on runoff, river access and the other suitability inputs; there is no dedicated freshwater-shore bonus.
- **Ranking discount and cost discount disagree by construction.** A shared-basin pair with only one river endpoint is ranked with the `0.78` discount but priced without it. The replay validator reproduces both rules separately, so the divergence is enforced rather than accidental drift — but no source comment or model declaration states an intent behind it, and it means `cost` is not a monotone function of the ranking key.
- **Corridor cell membership is order-dependent.** The assignment rule uses `>=`, so on exactly equal membership the highest-numbered route wins. Changing route ordering — which changes with settlement ordering, which changes with the score field — reshuffles corridor ownership of shared cells without any physical meaning attached to the change.
- **Empty diagnostics do not prove a populated layer.** `large_settlement_water_access` and `route_barrier_avoidance` retain their `1.0` empty-source defaults. Current `route_feature_coverage_index` is `1.0` only for complete empty diagnostics and null for incomplete diagnostics. Inspect emitted counts and source coverage before drawing a conclusion.
- **No physical time.** Nothing in this layer carries a time coordinate. There is no founding date, no growth trajectory, no route construction epoch. The world's nominal timestep and elapsed time apply to the earth-system ledgers only, and the world document keeps `physical_time_resolved = false` and `nominal_time_calibrated = false` on those ledgers. Any narrative reading of settlement or route "history" comes from the separate historical layer, not from here.
- **Determinism, not realism.** Every model in this layer declares `deterministic: true` and is byte-reproducible for a given seed and configuration. That guarantees replayability; it makes no claim that the resulting settlement pattern, route topology, port distribution or frontier geometry matches any real-world statistics. There is no calibration of this layer against empirical settlement or transport data anywhere in the tree.

---

## See also

- [Political, Cultural and Linguistic Geography](political-and-cultural-geography.md) — how `region_id`, `culture_region_id`, `language_region_id` get filled in, and how `borders[]` (the input to natural frontiers) is built
- [History, Demography, Economy and Markets](history-demography-and-economy.md) — the logistics networks, market exchanges and campaign movements that run on top of `routes[]`
- [Oceans, Currents and Coasts](oceans-and-coasts.md) — marine regions, continental shelves and `marine_chokepoints`, the inputs to `strait_access_index`
- [Hydrology, Rivers and Lakes](hydrology-and-rivers.md) — `is_river`, `basin_id`, `flow_accumulation`, `runoff_mm_y` and the river channel/hydraulics chain feeding `river_navigability_index`
- [Biomes, Ecosystems and Disturbance](biomes-and-ecology.md) — the biome classification that gates settlement types, the cold-biome multiplier and the desert route penalty
- [Soils and Weathering](soils.md) — `fertility` and `soil_moisture_index`
- [Resources and Economic Geology](resources-and-economic-geology.md) — the `resource` enum behind `mining_town` / `agricultural_town` and the flat `0.18` resource bonus
- [Cryosphere: Ice Sheets, Glaciers and Permafrost](cryosphere.md) — `ice_thickness_m` and `permafrost_class`, the penalty terms across this whole layer
- [World Document Schema](../10-world-schema.md) — the complete key inventory and where these arrays sit in emission order
- [Validation](../12-validation.md) — the full-world gate that runs the four replay validators on this page
- [Geo Validation Suite](../13-geo-validation-suite.md) — the geo-only gate, which never sees this layer
- [Native Engine (C++ Core)](../08-native-engine.md) — the pipeline stage ordering and the society branch
- [Python API](../07-python-api.md) — `generate_world` versus `generate_geo_world`
- [CLI Reference](../06-cli-reference.md) — `generate --geo-only`, `validate`, `validate-geo`
- [Configuration Reference](../05-configuration-reference.md) — `mesh.cell_count`, `planet.radius_km`, `output.float_precision`
- [Glossary](../21-glossary.md)
