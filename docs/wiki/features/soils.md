# Soils and Weathering

[Wiki home](../README.md) > Features

magic-geo produces soil in two clearly separated places. The native C++ engine writes three per-cell soil fields — `soil_type`, `soil_depth_m` and `fertility` — inside a single non-iterative, embarrassingly-parallel stage in `cpp/src/engine/environment.cpp`. These are the engine-owned source values every downstream consumer mirrors, but none of them is canonical geometric state and none participates in a conservation closure: unlike `bedrock_surface_elevation_m` / `sediment_thickness_m`, no `authoritative_*` flag is emitted for soil (see [Interactions with the sediment system](#interactions-with-the-sediment-system)). The stage derives them using final-state climate, lithology, relief, river/lake state and ice as inputs. Everything else you see about soil in a generated world (texture, drainage, pH, organic matter, salinity, erodibility, profile development, O/A/B/C horizons, pedogenesis trajectories) is added afterwards in Python by `enrich_world_with_soil_diagnostics` in `src/magic_geo/soil_dynamics.py`, which explicitly declares itself a *post-hoc final-state reconstruction* with `physical_time_resolved = false` and `state_mutation_evidence = false`. This page documents both layers exhaustively, and keeps their epistemic separation intact: no chemical weathering is modelled anywhere in the codebase, and the serialized `sediment_interface_model` / `sediment_inventory_model` say so with `chemical_weathering_resolved = false`.

## On this page

- [Where soils are produced in the pipeline](#where-soils-are-produced-in-the-pipeline)
- [Inputs consumed by the native soil stage](#inputs-consumed-by-the-native-soil-stage)
- [Native soil property fields](#native-soil-property-fields)
- [Soil classification vocabulary](#soil-classification-vocabulary)
- [The classification rules](#the-classification-rules)
- [Landform post-adjustments that overwrite soil state](#landform-post-adjustments-that-overwrite-soil-state)
- [Soil depth and development](#soil-depth-and-development)
- [Fertility and its downstream consumers](#fertility-and-its-downstream-consumers)
- [Weathering: what is and is not modelled](#weathering-what-is-and-is-not-modelled)
- [The soil diagnostics enricher](#the-soil-diagnostics-enricher)
- [Texture, parent material and profile class](#texture-parent-material-and-profile-class)
- [Per-cell fields added by the enricher](#per-cell-fields-added-by-the-enricher)
- [The soil_profiles records](#the-soil_profiles-records)
- [The soil_horizons records](#the-soil_horizons-records)
- [The soil_profile_histories records](#the-soil_profile_histories-records)
- [The soil_pedogenesis_model contract](#the-soil_pedogenesis_model-contract)
- [Summary keys](#summary-keys)
- [Interactions with the sediment system](#interactions-with-the-sediment-system)
- [Validation](#validation)
- [Export surfaces](#export-surfaces)
- [Worked examples](#worked-examples)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

---

## Where soils are produced in the pipeline

Soils are derived **once**, near the end of the native simulation, after all maturation iterations, after the cryosphere coupling pass, and after the final hydrology stabilization. There is no soil state inside the erosion loop, and no soil field participates in any feedback stage.

| Order | Call | File:line | Effect on soil state |
|---|---|---|---|
| … | `erode(...)` maturation loop | `cpp/src/engine/pipeline.cpp:135` | none — soil fields are untouched throughout maturation |
| … | `derive_cryosphere_state(params, cells)` (terminal) | `cpp/src/engine/pipeline.cpp:167` | sets `ice_thickness_m`, which the soil stage reads |
| 1 | `summarize_plates(params, cells, plates)` | `cpp/src/engine/pipeline.cpp:186` | none |
| 2 | **`derive_soils_biomes_resources(params, cells)`** | `cpp/src/engine/pipeline.cpp:187` | writes `soil_type`, `soil_depth_m`, `fertility` (plus `biome`, `resource`, `settlement_score`, and `water_body` on lake cells) |
| 3 | **`derive_landforms(cells)`** | `cpp/src/engine/pipeline.cpp:188` | **overwrites** `soil_type` and increments `fertility` on six landform classes |
| 4 | `generate_ice_sheets` / `generate_lake_basins` / … | `cpp/src/engine/pipeline.cpp:189-197` | none |

Both functions are declared in `cpp/src/engine/internal.hpp:328-329` and defined in `cpp/src/engine/environment.cpp:301` and `cpp/src/engine/environment.cpp:417`. Both are `#pragma omp parallel for schedule(static)` over cells (`environment.cpp:304`, `environment.cpp:419`) and are single-pass: each cell's soil state is a pure function of that cell's final state plus its immediate neighbours' elevations, `is_water` flags and (in `derive_landforms`) ice thickness. `derive_soils_biomes_resources` ignores its `params` argument entirely (`(void)params;` at `environment.cpp:302`), so **no configuration knob tunes soils directly** — soils only respond to configuration through the climate, tectonic and hydrology fields they read.

The Python diagnostic layer runs later, once per generated world:

| Entry point | Enricher call | File:line |
|---|---|---|
| `generate_world()` | `enrich_world_with_soil_diagnostics(world)` — 24th of 66 enrichers | `src/magic_geo/api.py:223` |
| `generate_geo_world()` | `enrich_world_with_soil_diagnostics(world)` — 24th of 48 enrichers | `src/magic_geo/api.py:341` |

In both entry points it runs *after* `enrich_world_with_seasonal_climate_history` (`api.py:209` / `api.py:323`), which is what supplies `seasonal_aridity_index`, and *before* every consumer of the soil indices. In `generate_world()` the immediate successors are `enrich_world_with_biome_diagnostics` (`api.py:224`) and `enrich_world_with_permafrost_diagnostics` (`api.py:225`); in `generate_geo_world()` permafrost comes first (`api.py:342`) and biomes later (`api.py:344`).

---

## Inputs consumed by the native soil stage

`derive_soils_biomes_resources` reads the following per-cell state. Everything in this table is a *final* value: soils see the end of the simulation, not a time series.

| Input | Source system | Where used | Role |
|---|---|---|---|
| `elevation_m` of self and neighbours | topography / erosion | `local_relief(cells, i)` at `environment.cpp:307`, defined `cpp/src/engine/climate.cpp:15-25` | `relief = max(0, elev − mean(neighbour elev))`; drives `slope_penalty` |
| `temperature_c` | climate | `environment.cpp:309` | annual PET proxy and every temperature threshold |
| `precipitation_mm_y` | climate | `environment.cpp:310`, `:337` | aridity ratio, `climate_soil` term, biome thresholds |
| `temperature_monthly_c[12]`, `precipitation_monthly_mm[12]` | climate | `environment.cpp:315-323` | dry/wet month counts for the savanna guard |
| `lat` | mesh | `environment.cpp:311-312`, `:346` | latitude PET factor, polar ice-cap guard |
| `lithology` | tectonics / crust | `environment.cpp:336`, `:387`, `:394`, `:398` | `litho_base` fertility floor; volcanic soil override |
| `crust_type`, `crust_age_ma`, `boundary_convergent`, `boundary_divergent`, `boundary_transform` | tectonics | `environment.cpp:390-399`, `:408` | resource assignment and settlement hazard (not soil itself) |
| `is_water`, `water_body` | oceans / hydrology | `environment.cpp:327-334`, `:341-344` | marine short-circuit; lake reclassification |
| `is_lake` | hydrology | `environment.cpp:341` | lake soil/biome branch |
| `is_river` | hydrology | `environment.cpp:338-339`, `:382`, `:396`, `:405` | depth bonus, fertility bonus, alluvial override |
| `runoff_mm_y` | hydrology | `environment.cpp:405` | settlement water access only |
| `ice_thickness_m` | cryosphere | `environment.cpp:345`, `:409` | ice-cap guard; settlement hazard |
| `sediment_thickness_m` | sediment | `environment.cpp:394` | resource assignment only |
| neighbour `is_water` | mesh + oceans | `has_ocean_neighbor(cells, i)` at `environment.cpp:326`, defined `environment.cpp:5-12` | coastal flag |

`derive_landforms` additionally reads `flow_to`, `is_closed_basin`, `glacial_erosion_m`, `water_depth_m` and neighbour `ice_thickness_m` (via `has_glacier_neighbor`, `environment.cpp:14-21`) before it rewrites soil state (`environment.cpp:422-503`).

Two derived quantities recur and are worth naming precisely, because their orientation is the opposite of the Python enricher's:

```text
pet     = max(1.0, (temperature_c + 8.0) * 31.0)          // environment.cpp:309
aridity = precipitation_mm_y / pet                        // environment.cpp:310
```

Native `aridity` is a **precipitation-over-PET humidity ratio**: *higher means wetter*. `aridity < 0.32` is the desert guard (`environment.cpp:355`). The Python enricher's local variable of the same name (`soil_dynamics.py:352`) is a **dryness index** where higher means drier. They are unrelated numbers; do not cross-read them.

The monthly seasonality guard used by the savanna rule is:

```text
latitude_pet_factor = 0.66 + 0.34 * (1 - min(1, |lat_deg| / 90))    // environment.cpp:311-312
monthly_pet[m]      = max(0, temperature_monthly_c[m] + 5.0) * 3.1 * latitude_pet_factor
dry_season_months  += precipitation_monthly_mm[m] <  0.35 * monthly_pet[m]
wet_season_months  += precipitation_monthly_mm[m] >= 0.75 * monthly_pet[m]
warm_seasonal_climate = dry_season_months >= 2 && wet_season_months >= 3
```

(`environment.cpp:318-325`.) The month loop runs over `min(len(temperature_monthly_c), len(precipitation_monthly_mm))` (`environment.cpp:315-317`), so a cell with empty or unequal-length monthly arrays still evaluates safely — it simply scores zero dry and wet months, and `warm_seasonal_climate` is false. This is a defensive guard, not a configuration surface: `climate.months` is declared `Literal[12]` in `ClimateConfig` (`src/magic_geo/config.py:324-327`), so 12 is the only value the config schema accepts.

---

## Native soil property fields

These are the only soil-bearing fields the C++ engine owns. All three are declared on `Cell` in `cpp/src/engine/types/core.hpp:62` (`soil_type`) and `:201-202` (`soil_depth_m`, `fertility`).

| Field | Type / units | Range | Meaning | Written at |
|---|---|---|---|---|
| `soil_type` | enum string from `SOIL_NAMES` | one of 11 names (see next section) | Categorical soil class. Marine cells are forced to `none`. | `environment.cpp:328`, `:343-389`, and overwritten at `:477`, `:487`, `:493`, `:498` |
| `soil_depth_m` | metres | exactly `0.0` on marine cells; `[0.02, 5.0]` on all other cells | Total soil column thickness. Clamped by `clamp(..., 0.02, 5.0)`. Never modified by `derive_landforms`. | `environment.cpp:329`, `:338` |
| `fertility` | dimensionless index | `[0.0, 1.0]`; exactly `0.0` on marine cells | Agronomic capability index. Clamped at write; the landform bonus is re-clamped. | `environment.cpp:330`, `:339-340`, `:478` |

Formulae, verbatim in structure:

```text
relief        = max(0, elevation_m − mean(neighbour elevation_m))     // climate.cpp:15-25
slope_penalty = clamp(relief / 1800.0, 0.0, 1.0)                      // environment.cpp:308
climate_soil  = clamp(precipitation_mm_y / 1300.0, 0.0, 1.2)
              * clamp((temperature_c + 8.0) / 30.0, 0.0, 1.1)         // environment.cpp:337

soil_depth_m  = clamp(0.12 + 1.8 * climate_soil
                      + (is_river ? 0.85 : 0.0)
                      − 1.5 * slope_penalty,
                      0.02, 5.0)                                      // environment.cpp:338

litho_base    = lithology == volcanic ? 0.78
              : lithology == granite  ? 0.50
              : lithology == shale    ? 0.44
              :                         0.58                          // environment.cpp:336

fertility     = clamp(litho_base
                      + 0.20 * climate_soil
                      + (is_river ? 0.24 : 0.0)
                      − 0.35 * slope_penalty
                      − (aridity < 0.45 ? 0.28 : 0.0),
                      0.0, 1.0)                                       // environment.cpp:339-340
```

Note that `litho_base` distinguishes only four cases out of the seven lithologies: `volcanic` (0.78), `granite` (0.50), `shale` (0.44) and everything else — `basalt`, `limestone`, `sandstone`, `metamorphic` — at 0.58.

### Fields co-produced by the same stage

`derive_soils_biomes_resources` also writes four non-soil fields in the same loop. They are documented on their own pages, but their values are entangled with the soil branch and are listed here for completeness.

| Field | Written at | Note |
|---|---|---|
| `biome` | `environment.cpp:331`, `:344-386`, `:480` | assigned in the same `if/else` chain as `soil_type` |
| `resource` | `environment.cpp:332`, `:390-404`, `:483`, `:489`, `:494` | one branch is soil-conditioned: `soil_type == alluvial && fertility > 0.62 → fertile_alluvium` (`:400-401`) |
| `settlement_score` | `environment.cpp:333`, `:405-413`, `:485`, `:491`, `:495`, `:500`, `:502` | weights `fertility` at 0.30 |
| `water_body` | `environment.cpp:342` | lake cells are reclassified to `saline_basin` when `aridity < 0.5`, else `fresh_lake` |

Serialization precision (`cpp/src/engine/entity_serialization.cpp:338-343`, `:347-348`): `landform`, `soil_type`, `biome` and `resource` are enum strings; `soil_depth_m` uses the configured `output.float_precision`; `fertility` and `settlement_score` use `max(8, float_precision)` decimal places.

---

## Soil classification vocabulary

`SOIL_NAMES` is fixed at 11 entries in `cpp/src/engine/schema_names.hpp:17-20`. The array index is the on-`Cell` integer; the string is what appears in the serialized world.

| Index | Name | Assigned by |
|---|---|---|
| 0 | `none` | marine short-circuit (`environment.cpp:328`) |
| 1 | `thin_mountain` | high-cold branch, `elevation_m > 2800 && temperature_c < 6` (`:349-350`) |
| 2 | `volcanic` | override when `lithology == volcanic` and the class is not `tundra` (`:387-388`) |
| 3 | `alluvial` | river override (`:382-383`); delta/floodplain landform override (`:477`) |
| 4 | `arid` | desert branch (`:355-356`), savanna branch (`:364-365`), fallback branch (`:377`), alluvial-fan landform override (`:487`) |
| 5 | `tropical` | rainforest and tropical seasonal forest branches (`:358-363`) |
| 6 | `temperate` | temperate forest / grassland branches (`:367-372`) |
| 7 | `boreal` | boreal forest branch (`:373-374`) |
| 8 | `tundra` | ice-cap guard (`:345-347`), cold guard (`:352-353`), glacial-valley and moraine landform override (`:496-499`) |
| 9 | `wetland` | non-saline lake cells (`:343`) |
| 10 | `saline` | saline lake cells (`:343`); salt-flat landform override (`:493`) |

Adjacent vocabularies referenced by the rules below: `LITHOLOGY_NAMES` (7, `schema_names.hpp:11-13`), `LANDFORM_NAMES` (20, `:37-42`), `BIOME_NAMES` (16, `:21-26`), `RESOURCE_NAMES` (9, `:27-30`), `WATER_BODY_NAMES` (6, `:34-36`), `DEPRESSION_POLICY_NAMES` (6, `:53-56`), `CRUST_NAMES` (9, `:7-10`).

---

## The classification rules

The assignment is a single ordered `if / else if` chain; **the first matching guard wins** and no later guard is evaluated. Read the table top-down.

| # | Guard | `soil_type` | `biome` | Line |
|---|---|---|---|---|
| 0 | `is_water` (marine) — short-circuits the whole stage | `none` | `continental_shelf` if `water_body == continental_shelf`, `lake` if `inland_sea`, else `ocean` | `:327-334` |
| 1 | `is_lake` | `saline` if `aridity < 0.5` else `wetland` | `hot_desert` if `aridity < 0.5` else `lake` | `:341-344` |
| 2 | `ice_thickness_m > 180` **or** (`temperature_c < −8` **and** (`\|lat_deg\| > 55` **or** `elevation_m > 1600`)) | `tundra` | `ice_cap` | `:345-348` |
| 3 | `elevation_m > 2800` **and** `temperature_c < 6` | `thin_mountain` | `alpine` | `:349-351` |
| 4 | `temperature_c < −2` | `tundra` | `tundra` | `:352-354` |
| 5 | `aridity < 0.32` | `arid` | `cold_desert` if `temperature_c < 11` else `hot_desert` | `:355-357` |
| 6 | `temperature_c > 23` **and** `precipitation_mm_y > 2100` | `tropical` | `tropical_rainforest` | `:358-360` |
| 7 | `temperature_c > 21` **and** `precipitation_mm_y > 950` | `tropical` | `tropical_seasonal_forest` | `:361-363` |
| 8 | `temperature_c > 18` **and** `aridity < 0.82` **and** `warm_seasonal_climate` | `arid` | `savanna` | `:364-366` |
| 9 | `temperature_c > 8` **and** `precipitation_mm_y > 760` | `temperate` | `temperate_forest` | `:367-369` |
| 10 | `temperature_c > 5` **and** `aridity > 0.45` | `temperate` | `temperate_forest` if `aridity > 1.1` else `temperate_grassland` | `:370-372` |
| 11 | `temperature_c > −1` **and** `precipitation_mm_y > 420` | `boreal` | `boreal_forest` | `:373-375` |
| 12 | fallback | `arid` | `tundra` if (`temperature_c < 2` and `precipitation_mm_y > 320` and `aridity > 0.55`); else `cold_desert` if `temperature_c < 8`; else `hot_desert` | `:376-381` |

Two mutually exclusive overrides then apply to the result of the chain (`environment.cpp:382-389`):

| Override | Guard | Effect |
|---|---|---|
| Alluvial | `is_river` **and** `relief < 450` **and** `precipitation_mm_y > 500` | `soil_type = alluvial`; and if `biome` is neither `tropical_rainforest` nor `ice_cap`, `biome = wetland` |
| Volcanic | (else) `lithology == volcanic` **and** `soil_type != tundra` | `soil_type = volcanic` |

Because these are `if / else if`, a volcanic river floodplain becomes `alluvial`, not `volcanic`. Because the volcanic override tests `soil_type != tundra` and not the biome, a `thin_mountain` alpine cell on volcanic rock becomes `volcanic`.

Note that `savanna` (rule 8) is the only rule that consumes the monthly climatology; every other guard is annual. The savanna rule is also the only place `warm_seasonal_climate` is used in the whole stage.

---

## Landform post-adjustments that overwrite soil state

`derive_landforms` runs immediately after and rewrites soil state on six landform classes (`environment.cpp:476-503`). This is the reason a serialized `soil_type` can disagree with what the classification chain above would predict.

| Landform (index, name) | `soil_type` after | `fertility` after | Other soil-adjacent effect | Line |
|---|---|---|---|---|
| 12 `delta` | `alluvial` | `clamp(fertility + 0.16, 0, 1)` | `biome = wetland` if `precipitation_mm_y > 500` and `biome != ice_cap`; `resource = fertile_alluvium` if new `fertility > 0.64`; `settlement_score += 0.08` | `:476-485` |
| 11 `floodplain` | `alluvial` | `clamp(fertility + 0.10, 0, 1)` | same three effects as `delta` | `:476-485` |
| 13 `alluvial_fan` | `arid`, unless it is already `tundra` (then unchanged) | unchanged | `resource = placer_metals` if `resource == none` and `boundary_convergent > 0.10`; `settlement_score += 0.03` | `:486-491` |
| 4 `salt_flat` | `saline` | unchanged | `resource = evaporites`; `settlement_score *= 0.55` | `:492-495` |
| 17 `glacial_valley` | `tundra` | unchanged | `settlement_score *= 0.42` | `:496-500` |
| 18 `moraine` | `tundra` | unchanged | `settlement_score *= 0.42` | `:496-500` |
| 19 `glacial_lake` | **unchanged** (explicitly excluded by `if (cell.landform != 19)`) | unchanged | `settlement_score *= 0.72` | `:496-500` |

`soil_depth_m` is never touched by `derive_landforms`. A delta cell therefore keeps the depth the climate/relief formula gave it, while its class and fertility change.

There is a deliberate ordering consequence worth internalising: `settlement_score` is computed at `environment.cpp:410` using the **pre-landform-bonus** `fertility`, and only then does `derive_landforms` add `+0.16` / `+0.10` to `fertility` and separately add `+0.08` to the score. The independent Python replay in `src/magic_geo/cli/validators/settlement.py:182-188` reproduces exactly this: it computes fertility without the landform delta, uses it in the score at `:291`, and applies the landform score adjustments afterwards at `:298-308`. Any consumer reading `fertility` from a serialized delta cell is reading a value that the serialized `settlement_score` did *not* see.

---

## Soil depth and development

There are two distinct notions of "development" in the codebase and they must not be conflated.

**Native depth** (`soil_depth_m`) is a static climate–relief–river function, clamped to `[0.02, 5.0]`. It has no time dimension, no production/erosion balance, and no dependence on `erosion_rate`, `sediment_thickness_m`, or elapsed nominal time. The formula is at `environment.cpp:338`. Marine cells are exactly `0.0` (`environment.cpp:329`).

Reading the terms:

| Term | Contribution to depth | Effect |
|---|---|---|
| constant | `+0.12` m | floor before clamping |
| `1.8 * climate_soil` | `0` … `+2.376` m | `climate_soil` maxes at `1.2 * 1.1 = 1.32` |
| `is_river` | `+0.85` m | binary river bonus |
| `−1.5 * slope_penalty` | `0` … `−1.5` m | full penalty once `relief >= 1800` m |
| clamp | `[0.02, 5.0]` | the upper bound is unreachable from the terms above (max is `0.12 + 2.376 + 0.85 = 3.346` m); the lower bound is reachable on steep dry terrain |

**Diagnostic development** (`soil_profile_development_index`, and the `development_index` mirror on each `soil_profiles` record) is a Python-side bounded index, `soil_dynamics.py:401-411`:

```text
profile = clamp( depth / 5.0 * 0.34
               + fertility * 0.18
               + temperature_factor * wetness * 0.22
               + min(1, sediment_thickness_m / 4.0) * 0.10
               + max(0, 1 − relief) * 0.16
               − salinity * 0.10
               − (landform in {moraine, glacial_lake, ice_field} ? 0.18 : 0.0),
               0.0, 1.0 )
```

where `temperature_factor = clamp((temperature_c + 8) / 32, 0, 1)` (`:362`) and `relief` here is the *normalized* neighbour relief `clamp(max|Δelev| / 1800, 0, 1)` from `_neighbor_relief` (`soil_dynamics.py:148-156`) — note this is the maximum absolute neighbour difference, **not** the native `local_relief`'s mean-difference definition.

A third quantity, `profile_age_ka`, is a pure algebraic label with no clock behind it (`soil_dynamics.py:417`):

```text
profile_age_ka = max(0, depth * 18.0 + profile * 36.0 + max(0, 1 − relief) * 16.0 − erosion_rate * 120.0)
```

The `ka` suffix is nominal. `erosion_rate` here is the native stream-power response exported at `cpp/src/engine/earth_system.cpp:993`, which is documented in that file's own comment as "the 5 Ma reference response" and is *not* scaled by the configured maturation timestep. `profile_age_ka` is therefore not a calibrated age; it is used only to seed `initial_depth` in the pedogenesis trajectory via `age_fraction = clamp(profile_age / 85, 0, 1)` (`soil_dynamics.py:554`).

---

## Fertility and its downstream consumers

`fertility` is the single most widely consumed soil output. Its direct consumers, all verified:

| Consumer | Where | How `fertility` is used |
|---|---|---|
| Native settlement score | `cpp/src/engine/environment.cpp:410` | weight `0.30` in `0.38 * water_access + 0.30 * fertility + 0.18 * climate_score + resource_bonus − hazard`; the model declaration mirrors the weight at `src/magic_geo/settlement_routes.py:77` |
| Native resource assignment | `cpp/src/engine/environment.cpp:400-401`, `:482-484` | `soil_type == alluvial && fertility > 0.62 → fertile_alluvium`; landform delta/floodplain re-tests `fertility > 0.64` |
| Native political / cultural geography | `cpp/src/engine/civilization.cpp:19`, `:317`, `:344`, `:510`, `:544`, `:671`, `:673` | region typing, border affinity, culture aggregates (thresholds `0.62`, `0.68`, `0.74`) |
| Agricultural zones | `src/magic_geo/land_use_zones.py:41`, `:59` | weight `0.27` in `_agricultural_potential`, the largest single term |
| Resource deposits | `src/magic_geo/resource_dynamics.py:62`, `:76`, `:127`, `:143` | `fertile_alluvium` reserve formula `0.24 + fertility * 0.42 + …`; geological-confidence evidence |
| Commodity occurrences | `src/magic_geo/commodity_resources.py:102`, `:129`, `:187` | agricultural commodity potential `… + fertility * 0.42 + …` |
| Ecosystem dynamics | `src/magic_geo/ecosystem_dynamics.py:27`, `:38`, `:96`, `:97` | NPP weight `0.18`; forest-growth weight `0.12` |
| Route corridors (oasis) | `src/magic_geo/route_corridors.py:153`, `:155` | oasis support weight `0.12` |
| Worldbuilding realism | `src/magic_geo/worldbuilding_realism.py:105`, `:138` | settlement-site plausibility gate at `fertility >= 0.62` |
| Soil diagnostics itself | `src/magic_geo/soil_dynamics.py:322`, `:367`, `:397`, `:403`, `:416`, `:457` | organic matter, erodibility, development, bioturbation, root density |

`soil_depth_m` has a narrower audience: `_agricultural_potential` normalizes it as `clamp(soil_depth_m / 3.2)` with weight `0.14` (`land_use_zones.py:42`, `:60`), the soil enricher uses it as `depth` throughout, and `geo_validation.py:1036` includes it in the non-negativity contract check.

The enricher's derived indices fan out further:

| Index | Consumed by | Reference |
|---|---|---|
| `soil_moisture_index` | biomes, permafrost, wetlands, aquifers, karst, ecosystems, species, ecotones, biome realism, groundwater, route corridors, land use | `biome_dynamics.py:82`, `:126`; `permafrost_diagnostics.py:54`; `wetland_diagnostics.py:120`, `:149`; `aquifer_resources.py:102`; `karst_diagnostics.py:58`; `ecosystem_dynamics.py:26`, `:95`, `:158`; `species_ranges.py:112`; `biome_ecotones.py:63`; `biome_realism.py:56`, `:118`, `:132`, `:176`; `groundwater_flow.py:55`; `route_corridors.py:151`; `land_use_zones.py:43` |
| `soil_drainage_index` | aquifers, permafrost, wetlands, karst | `aquifer_resources.py:101`, `:118`; `permafrost_diagnostics.py:56`; `wetland_diagnostics.py:150`; `karst_diagnostics.py:59`. `groundwater_flow.py` does **not** read it — that module reads only `soil_moisture_index` (`:55`) and `soil_salinity_index` (`:57`) |
| `soil_salinity_index` | aquifers, resources, petroleum, sedimentary systems, wetlands, groundwater, commodities, worldbuilding realism, land use | `aquifer_resources.py:103`; `resource_dynamics.py:63`, `:94`, `:115`, `:144`; `petroleum_migration.py:118`; `sedimentary_resource_systems.py:214`; `wetland_diagnostics.py:158`; `groundwater_flow.py:57`; `commodity_resources.py:101`, `:127`; `worldbuilding_realism.py:106`; `land_use_zones.py:44` |
| `soil_organic_matter_fraction` | biomes, permafrost, wetlands, ecosystems | `biome_dynamics.py:134`; `permafrost_diagnostics.py:55`; `wetland_diagnostics.py:133`, `:157`; `ecosystem_dynamics.py:45` |
| `soil_ph` | karst | `karst_diagnostics.py:31`, `:61`, `:69` (`acidity_bonus = clamp((7.8 − soil_ph) / 3.0) * 0.12`) |
| `soil_erodibility_index` | agricultural zones, and their replay validator | `land_use_zones.py:45`; `human_geography_validation.py:145` |
| `soil_profile_development_index` | karst | `karst_diagnostics.py:60`, `:84`, `:91` |
| `soil_texture_class` | wetlands | `wetland_diagnostics.py:117`, `:133` (`texture == "peat"` is a wetland indicator) |

`enrich_world_with_land_use_zones` and `enrich_world_with_worldbuilding_realism` are **not** run in geo-only mode (`api.py` omits them from the geo sequence), so the agricultural consumer of `fertility`/`soil_depth_m` exists only in full worlds.

---

## Weathering: what is and is not modelled

### What exists

| Quantity | Where | What it actually is |
|---|---|---|
| `weathering_index` (profile) | `soil_dynamics.py:414` | `clamp(profile*0.46 + temperature_factor*wetness*0.22 + fertility*0.16 + min(1, depth/3)*0.16 − salinity*0.10, 0, 1)` — a bounded dimensionless score |
| `weathering_index` (horizon) | `soil_dynamics.py:437` | `clamp(profile_weathering * (1 − mid_fraction*0.48) + (horizon == "B" ? 0.10 : 0), 0, 1)` — a depth-decay of the profile score with a B-horizon bump |
| `leaching_index` | `soil_dynamics.py:415` | `clamp(wetness*0.58 + drainage*0.24 + temperature_factor*0.10 − salinity*0.22 − aridity*0.12, 0, 1)` |
| `carbonate_index` (horizon) | `soil_dynamics.py:455` | `clamp((soil_ph − 6.9)/2.3 + salinity*0.20, 0, 1)` — a pH proxy, not a carbonate mass |
| `carbonate_mobilization_index` (step) | `soil_dynamics.py:637-641` | `clamp(max(0, soil_ph − 6.6)/2.8*0.30 + salinity*0.26 + leaching*0.22 + (1 − moisture)*0.10, 0, 1)` |
| `soil_ph` | `soil_dynamics.py:390` | `clamp(lithology_ph + salinity*1.20 − organic*2.40 + aridity*0.35 − wetness*0.18, 3.8, 9.2)` from a 7-entry lithology lookup (`_lithology_ph`, `:26-35`) |
| `_carbonate_factor` (karst) | `src/magic_geo/karst_diagnostics.py:21-32` | a 7-entry lithology lookup plus `acidity_bonus = clamp((7.8 − soil_ph) / 3.0) * 0.12` (`:31`); a dissolution-potential index, not a dissolution rate |

### What does not exist

There is **no chemical weathering model anywhere in the engine or the enrichers**. Specifically:

- No mineral inventory, no primary/secondary mineral pools, no cation exchange capacity, no base saturation, no clay mineralogy.
- No dissolution flux, no solute transport, no alkalinity, no CO₂ consumption, no silicate/carbonate weathering rate law.
- No coupling from any weathering index back into `soil_depth_m`, `sediment_thickness_m`, `bedrock_surface_elevation_m`, lithology, or any native field. The indices are read-only outputs.
- No temperature/runoff-driven weathering rate calibration; every index above is a bounded 0–1 blend of already-derived fields.

The codebase states this explicitly rather than leaving it implicit. `chemical_weathering_resolved` is emitted as literal `false` in two serialized model objects:

| Model object | Emitted at | Neighbouring false flags |
|---|---|---|
| `sediment_interface_model` | `cpp/src/engine/process_serialization.cpp:1865` | `dry_rock_mass_resolved`, `sediment_density_resolved`, `porosity_resolved`, `compaction_resolved`, `grain_provenance_resolved` (`:1860-1864`) |
| `sediment_inventory_model` | `cpp/src/engine/process_serialization.cpp:1987` | the same five plus `physical_time_resolved` (`:1982-1988`); `mass_conserving_semantics = "bulk_reference_volume_only_not_dry_rock_mass"` (`:1980-1981`) |

The Python-side mirror of the expected flag set lives at `src/magic_geo/sediment_interface_validation.py:54`, and the strict CLI validator rejects any world where the flag is not exactly `false` (`src/magic_geo/cli/validators/sediment.py:2611`, `:2663`). The `validate-geo` suite carries the same sentence forward in its declared scope string (`src/magic_geo/geo_validation.py:38`): "bulk reference-volume closure still does not resolve dry-rock mass, sediment density, porosity, compaction, grain provenance, or chemical weathering".

So: the word "weathering" appears in soil output field names as a *diagnostic index name*. It is never a chemical flux, and it never modifies state.

---

## The soil diagnostics enricher

`enrich_world_with_soil_diagnostics(world)` (`src/magic_geo/soil_dynamics.py:262`) is the only soil enricher. It takes no extra arguments and returns the mutated `world`.

### The empty-cells early return

If `world["cells"]` is absent, not a list, or empty (`soil_dynamics.py:263-291`), the enricher writes three empty arrays, a stub model, and **15** summary keys, then returns. The stub model is:

```json
{
  "model_type": "posthoc_final_state_profile_reconstruction_v2",
  "time_basis": "unavailable_without_cells",
  "stage_source": "none",
  "physical_time_resolved": false,
  "state_mutation_evidence": false
}
```

This path emits `soil_diagnostic_cell_count`, `soil_texture_counts`, `soil_profile_count`, `soil_horizon_count`, `soil_profile_history_count`, `soil_pedogenesis_step_count`, `total_soil_production_m`, `total_soil_erosion_loss_m`, `mean_pedogenic_weathering_index`, `mean_pedogenic_leaching_index`, `mean_pedogenic_bioturbation_index`, `mean_horizon_differentiation_index`, `mean_pedogenic_flux_index`, `high_erosion_pedogenesis_count`, `soil_profile_class_counts` — and **not** the 20 other keys the normal path writes. Consumers must not assume the full key set is always present.

### The eligibility gate

```python
water_body = str(cell.get("water_body_type", "land"))
soil_type  = str(cell.get("soil_type", "none"))
depth      = max(0.0, float(cell.get("soil_depth_m", 0.0)))
is_soil    = water_body == "land" and soil_type != "none" and depth > 0.0
```

(`soil_dynamics.py:319-323`.) Ineligible cells get an explicit zeroed record — `soil_texture_class = "none"`, all indices `0.0`, `soil_ph = 7.0`, `soil_profile_id = -1`, `soil_horizon_count = 0` — and increment `texture_counts["none"]` (`:325-337`).

Two consequences follow directly from that gate and are easy to miss:

1. **Lake cells never get a soil profile.** Native lake cells are not `is_water` (the ocean labeller sets `is_water` for marine cells only, `cpp/src/engine/ocean.cpp:250`), so they reach the lake branch of the soil stage and receive `soil_type = wetland | saline` and a positive `soil_depth_m`. But that same branch sets `water_body` to `fresh_lake` or `saline_basin` (`environment.cpp:342`, and `cpp/src/engine/hydrology.cpp:642`, `:647`), so `water_body_type != "land"` and the enricher excludes them.
2. **Dry geologic depression sinks are also excluded** when they carry `water_body = saline_basin` from `cpp/src/engine/hydrology.cpp:654-655`.

`geo_validation.py:2196-2202` uses the identical three-part predicate to build its expected profile set, so the validator and the enricher agree by construction.

### Derived intermediates, in evaluation order

Every soil-eligible cell computes the following before any record is emitted (`soil_dynamics.py:339-417`).

| Symbol | Formula | Range | Line |
|---|---|---|---|
| `relief` | `clamp(max over neighbours of \|Δelevation_m\| / 1800, 0, 1)` | `[0,1]` | `:341`, `_neighbor_relief` at `:148-156` |
| `wetness` | `clamp(P/1600*0.55 + runoff/900*0.25 + (is_river ? 0.20 : 0), 0, 1)` | `[0,1]` | `:351` |
| `aridity` | `clamp(seasonal_aridity_index*0.65 + (1 − wetness)*0.35, 0, 1)` — **dryness**, higher = drier | `[0,1]` | `:352` |
| `salinity` | `clamp((saline_water ? 0.48 : 0) + (is_closed_basin ? 0.24 : 0) + max(0, aridity − 0.55)*0.70 + (soil_type == "arid" ? 0.10 : 0) − wetness*0.18, 0, 1)` | `[0,1]` | `:353-361` |
| `temperature_factor` | `clamp((temperature_c + 8)/32, 0, 1)` | `[0,1]` | `:362` |
| `cool_storage` | `clamp((12 − temperature_c)/24, 0, 0.45)` | `[0,0.45]` | `:363` |
| `organic` | `clamp(0.018 + fertility*0.055 + wetness*0.065 + clamp(depth/5,0,1)*0.035 + cool_storage − salinity*0.045 − relief*0.030, 0, 0.35)` | `[0,0.35]` | `:364-374` |
| `texture` | `_classify_texture(...)` — see next section | 12 classes | `:375` |
| `drainage` | `clamp(0.42 + relief*0.32 + sandy_bonus − clay_penalty − wetness*0.22 − (landform in {river_valley, glacial_lake} ? 0.18 : 0) − (soil_type == "wetland" ? 0.25 : 0), 0, 1)` | `[0,1]` | `:376-388` |
| `moisture` | `clamp(wetness*0.74 + (1 − drainage)*0.20 + (soil_type == "wetland" ? 0.08 : 0), 0, 1)` | `[0,1]` | `:389` |
| `soil_ph` | `clamp(_lithology_ph(lithology) + salinity*1.20 − organic*2.40 + aridity*0.35 − wetness*0.18, 3.8, 9.2)` | `[3.8, 9.2]` | `:390` |
| `erodibility` | `clamp(_texture_factor(texture)*0.48 + relief*0.24 + clamp(runoff/1200,0,1)*0.15 + clamp(erosion_rate*90,0,1)*0.10 − organic*0.34 − fertility*0.08, 0, 1)` | `[0,1]` | `:391-400` |
| `profile` | see [Soil depth and development](#soil-depth-and-development) | `[0,1]` | `:401-411` |
| `parent_material` | `_parent_material(lithology, landform, sediment_thickness_m)` | 8 classes | `:412` |
| `profile_class` | `_profile_class(...)` | 7 classes | `:413` |
| `weathering` | `clamp(profile*0.46 + temperature_factor*wetness*0.22 + fertility*0.16 + min(1, depth/3)*0.16 − salinity*0.10, 0, 1)` | `[0,1]` | `:414` |
| `leaching` | `clamp(wetness*0.58 + drainage*0.24 + temperature_factor*0.10 − salinity*0.22 − aridity*0.12, 0, 1)` | `[0,1]` | `:415` |
| `bioturbation` | `clamp(fertility*0.38 + organic*1.60 + moisture*0.20 + temperature_factor*0.18 − salinity*0.18 − relief*0.12, 0, 1)` | `[0,1]` | `:416` |
| `profile_age` | `max(0, depth*18 + profile*36 + max(0, 1 − relief)*16 − erosion_rate*120)` | `>= 0`, labelled ka | `:417` |

`sandy_bonus = 0.18` for `{sand, loamy_sand, sandy_loam, volcanic_ash}` and `clay_penalty = 0.18` for `{clay, clay_loam, alluvial_silt, peat}` (`:376-377`).

`saline_water` is defined at `:349` as `water_body == "saline_basin" or depression_policy == "preserve_geologic_sink"`. Both disjuncts are unreachable in native output: the first contradicts the `water_body == "land"` eligibility gate that has already passed, and `"preserve_geologic_sink"` is not a member of `DEPRESSION_POLICY_NAMES` (which contains `none`, `corrected_numeric`, `preserved_geologic`, `overflow_spill`, `dry_closed`, `temporary_numeric_lake` — `cpp/src/engine/schema_names.hpp:53-56`, serialized at `cpp/src/engine/entity_serialization.cpp:245`). The value is exercised only by synthetic unit-test fixtures (`tests/test_enrichers_terrain_biome.py:142`, `:247`). The practical consequence, from the salinity formula's remaining terms, is that on a native world `salinity >= 0.55` requires `is_closed_basin` to be true — without it the maximum attainable value is `0.315 + 0.10 = 0.415`.

---

## Texture, parent material and profile class

### Texture classification

`_classify_texture` (`soil_dynamics.py:229-259`) is an ordered chain; first match wins.

| # | Guard | Texture |
|---|---|---|
| 1 | `salinity >= 0.62` | `saline_crust` |
| 2 | `landform in {moraine, glacial_lake, ice_field, fjord}` **or** `soil_type == "tundra"` | `glacial_till` |
| 3 | `landform in {river_valley, delta, floodplain}` **or** `soil_type == "alluvial"` | `alluvial_silt` if `sediment_thickness_m >= 0.35`, else `silt_loam` |
| 4 | `soil_type == "wetland"` **or** `organic >= 0.18` | `peat` |
| 5 | `lithology == "volcanic"` | `volcanic_ash` |
| 6 | `lithology == "sandstone"` | `sand` if `aridity >= 0.72`, else `sandy_loam` |
| 7 | `lithology in {shale, limestone}` | `clay` if `aridity < 0.35`, else `clay_loam` |
| 8 | `lithology == "basalt"` | `loam` |
| 9 | `lithology == "granite"` | `sandy_loam` |
| 10 | `sediment_thickness_m >= 1.0` **and** `fertility >= 0.45` | `silt_loam` |
| 11 | fallback | `loam` |

Rule 4's `soil_type == "wetland"` disjunct is unreachable from native output for the same reason lakes are excluded — `wetland` is only ever assigned to lake cells (`environment.cpp:343`), which the eligibility gate rejects. `peat` is still reachable through `organic >= 0.18`. `metamorphic` lithology falls through to rules 10/11.

`TEXTURE_FRACTIONS` (`soil_dynamics.py:6-19`) — the base (sand, silt, clay) triple per class — and `_texture_factor` (`:38-52`) — the erodibility multiplier — together define the full texture vocabulary:

| Texture | sand | silt | clay | `_texture_factor` |
|---|---|---|---|---|
| `sand` | 0.82 | 0.10 | 0.08 | 0.22 |
| `loamy_sand` | 0.74 | 0.16 | 0.10 | 0.30 |
| `sandy_loam` | 0.62 | 0.26 | 0.12 | 0.42 |
| `loam` | 0.42 | 0.40 | 0.18 | 0.55 |
| `silt_loam` | 0.20 | 0.62 | 0.18 | 0.72 |
| `clay_loam` | 0.30 | 0.34 | 0.36 | 0.68 |
| `clay` | 0.18 | 0.32 | 0.50 | 0.76 |
| `peat` | 0.12 | 0.70 | 0.18 | 0.38 |
| `volcanic_ash` | 0.56 | 0.34 | 0.10 | 0.48 |
| `alluvial_silt` | 0.18 | 0.68 | 0.14 | 0.70 |
| `saline_crust` | 0.35 | 0.45 | 0.20 | 0.58 |
| `glacial_till` | 0.48 | 0.32 | 0.20 | 0.52 |
| *(unlisted / `none`)* | 0.42 | 0.40 | 0.18 (fallback) | 0.0 |

Every listed triple sums to exactly 1.0. `_texture_fractions(texture, horizon_name)` (`:99-112`) then perturbs and renormalizes per horizon:

| Horizon | Perturbation | Then |
|---|---|---|
| `O` | `sand *= 0.35`; `silt = max(silt, 0.52)`; `clay *= 0.65` | normalize by the sum |
| `A` | none | normalize by the sum |
| `B` | `clay = min(0.70, clay + 0.08)`; `sand = max(0.05, sand − 0.05)` | normalize by the sum |
| `C` | `clay = max(0.04, clay − 0.04)`; `sand = min(0.90, sand + 0.06)` | normalize by the sum |

Normalization divides by `max(0.001, sand + silt + clay)`, so the three emitted fractions always sum to 1 within rounding — which is exactly what the validator checks (`geo_validation_subsystems.py:984-989`).

### Parent material

`_parent_material(lithology, landform, sediment_thickness_m)` (`soil_dynamics.py:55-70`), ordered:

| # | Guard | `parent_material` |
|---|---|---|
| 1 | `landform in {moraine, glacial_lake, ice_field, fjord}` | `glacial_till` |
| 2 | `landform in {river_valley, delta, floodplain}` **or** `sediment_thickness_m >= 1.5` | `alluvium` |
| 3 | `landform in {coastal_plain, beach, barrier_bar, barrier_island}` | `marine_sediment` |
| 4 | `lithology == "volcanic"` | `volcanic_ash` |
| 5 | `lithology in {sandstone, shale, limestone}` | `sedimentary_regolith` |
| 6 | `lithology in {granite, metamorphic}` | `crystalline_regolith` |
| 7 | `lithology == "basalt"` | `mafic_regolith` |
| 8 | fallback | `mixed_regolith` |

Of rule 3's four names, only `coastal_plain` is a member of `LANDFORM_NAMES` (`cpp/src/engine/schema_names.hpp:37-42`); `beach`, `barrier_bar` and `barrier_island` belong to `COASTAL_FEATURE_TYPE_NAMES` and never appear in a cell's `landform` field. In a native world, rule 3 therefore fires only on `coastal_plain`. The fallback `mixed_regolith` is unreachable, because rules 4–7 exhaust all seven lithology names.

### Profile class

`_profile_class(soil_type, texture, salinity, drainage, moisture, development, parent_material)` (`soil_dynamics.py:73-96`), ordered:

| # | Guard | `profile_class` |
|---|---|---|
| 1 | `salinity >= 0.55` | `saline_arid_profile` |
| 2 | `soil_type == "wetland"` **or** `texture == "peat"` **or** (`drainage <= 0.25` **and** `moisture >= 0.60`) | `histic_wetland_profile` |
| 3 | `parent_material == "glacial_till"` | `glacial_young_profile` |
| 4 | `parent_material == "alluvium"` | `alluvial_profile` |
| 5 | `parent_material == "volcanic_ash"` | `volcanic_andic_profile` |
| 6 | `development >= 0.62` | `mature_weathered_profile` |
| 7 | `development <= 0.25` | `thin_weakly_developed_profile` |
| 8 | fallback | `moderately_developed_profile` |

The `(drainage <= 0.25 and moisture >= 0.60)` clause in rule 2 is the same predicate the summary uses for `waterlogged_soil_cell_fraction` (`soil_dynamics.py:505`), and rule 6's threshold is the same `0.62` as `mature_soil_profile_fraction` (`:512`).

---

## Per-cell fields added by the enricher

Ten fields are written on every cell, eligible or not (`soil_dynamics.py:326-335` for the ineligible path, `:419-426` and `:490-491` for the eligible path). All floating-point values are `round(x, 6)`.

| Field | Units | Range (eligible) | Value when ineligible | Meaning | Line |
|---|---|---|---|---|---|
| `soil_texture_class` | enum string | one of the 12 texture names | `"none"` | USDA-style texture class from lithology, landform, soil type, salinity, organic content and aridity | `:419` |
| `soil_drainage_index` | dimensionless | `[0, 1]` | `0.0` | higher = better internal drainage | `:420` |
| `soil_moisture_index` | dimensionless | `[0, 1]` | `0.0` | higher = wetter root zone | `:421` |
| `soil_ph` | pH units | `[3.8, 9.2]` | `7.0` | bulk profile pH | `:422` |
| `soil_organic_matter_fraction` | mass fraction | `[0, 0.35]` | `0.0` | bulk profile organic matter | `:423` |
| `soil_salinity_index` | dimensionless | `[0, 1]` | `0.0` | higher = more saline | `:424` |
| `soil_erodibility_index` | dimensionless | `[0, 1]` | `0.0` | higher = more erodible | `:425` |
| `soil_profile_development_index` | dimensionless | `[0, 1]` | `0.0` | horizon-differentiation potential | `:426` |
| `soil_profile_id` | int | index into `world["soil_profiles"]` | `-1` | back-pointer | `:490` |
| `soil_horizon_count` | int | `1`–`4` in practice | `0` | number of horizons owned | `:491` |

`soil_ph` is the one field whose ineligible sentinel is not zero; `7.0` is a neutral placeholder, not a measurement.

---

## The soil_profiles records

`world["soil_profiles"]` is a dense list; `id` equals the list index (`soil_dynamics.py:428`, `:464-489`). One record per eligible cell.

| Field | Type | Range / meaning |
|---|---|---|
| `id` | int | list index; sequential from 0 |
| `cell_id` | int | owning cell |
| `soil_type` | string | mirrors the native `soil_type` exactly (validator-enforced) |
| `texture_class` | string | one of the 12 texture names |
| `lithology` | string | mirrors the native `lithology` |
| `landform` | string | mirrors the native `landform` |
| `parent_material` | string | one of 8 (7 reachable) |
| `profile_class` | string | one of 7 |
| `horizon_ids` | int[] | ids into `world["soil_horizons"]`, in top-down order |
| `horizon_count` | int | `len(horizon_ids)` |
| `total_depth_m` | m | mirrors the native `soil_depth_m` to within `1e-5` (validator-enforced) |
| `profile_age_ka` | nominal ka | `>= 0`; algebraic label, not a calibrated age |
| `drainage_index` | — | `[0,1]` |
| `moisture_index` | — | `[0,1]` |
| `ph` | pH | `[3.8, 9.2]` |
| `organic_matter_fraction` | fraction | `[0, 0.35]` |
| `salinity_index` | — | `[0,1]` |
| `erodibility_index` | — | `[0,1]` |
| `development_index` | — | `[0,1]` |
| `weathering_index` | — | `[0,1]`; a bounded score, not a flux |
| `leaching_index` | — | `[0,1]` |
| `bioturbation_index` | — | `[0,1]` |
| `soil_profile_history_id` | int | added after the history pass at `:789`; id into `world["soil_profile_histories"]` |

---

## The soil_horizons records

`world["soil_horizons"]` is a dense list shared by all profiles; `id` equals the list index (`soil_dynamics.py:438-460`).

### Horizon partition algorithm

`_horizon_thicknesses(depth, organic, development, soil_type)` (`soil_dynamics.py:115-145`) allocates the profile depth top-down. `remaining` starts at `max(0, depth)`.

| Step | Condition | Thickness | Notes |
|---|---|---|---|
| `O` | `(organic >= 0.12 or soil_type == "wetland")` **and** `remaining > 0.12` | `min(max(depth*0.10, 0.04), 0.18, remaining*0.35)` | absolute cap 0.18 m |
| `A` | `remaining > 0` | `min(max(depth*0.20, 0.06), 0.42, remaining)`; if the leftover would be `< 0.08` m, `A` absorbs all of `remaining` | absolute cap 0.42 m |
| `B` | `remaining > 0.12` **and** `development >= 0.22` | `min(max(depth*0.34, 0.10), remaining*0.72)` | skipped on weakly developed profiles |
| `C` | `remaining > 0` | `remaining`; but if `remaining < 0.04` m and at least one horizon exists, the leftover is folded into the **last** horizon instead of creating a `C` | guarantees `sum(thickness) == depth` |

Because `A` can absorb the remainder, a very shallow profile collapses to a single `A` horizon — which is exactly the case a dedicated test pins (`tests/test_enrichers_terrain_biome.py:351`).

### Horizon fields

`mid_fraction = clamp((top_depth + bottom_depth) / max(0.001, depth * 2), 0, 1)` (`soil_dynamics.py:433`) — the normalized mid-depth of the horizon within the profile.

| Field | Type | Range / formula |
|---|---|---|
| `id` | int | list index |
| `soil_profile_id` | int | owning profile |
| `cell_id` | int | owning cell |
| `horizon_name` | string | `"O"`, `"A"`, `"B"` or `"C"` |
| `sequence_index` | int | 0-based position within the profile, top-down |
| `top_depth_m` | m | cumulative from the surface; the first horizon starts at `0.0` |
| `bottom_depth_m` | m | `top_depth_m + thickness_m` |
| `thickness_m` | m | from the partition table above |
| `texture_class` | string | the profile texture (identical across horizons) |
| `sand_fraction` / `silt_fraction` / `clay_fraction` | fraction | per-horizon perturbed and renormalized; sum to 1 |
| `organic_matter_fraction` | fraction | `clamp(organic * f, 0, 0.70)` with `f = 1.85` (O), `1.00` (A), `0.38` (B), `0.12` (C) — `:435` |
| `ph` | pH | `clamp(soil_ph + (C ? +0.20 : O ? −0.12 : 0) + salinity*mid_fraction*0.18, 3.5, 9.5)` — `:436` |
| `carbonate_index` | — | `clamp((soil_ph − 6.9)/2.3 + salinity*0.20, 0, 1)` — identical across horizons — `:455` |
| `salinity_index` | — | `clamp(salinity * (0.78 + mid_fraction*0.32), 0, 1)` — increases with depth — `:456` |
| `root_density_index` | — | `clamp((1 − mid_fraction)*0.72 + fertility*0.20 + moisture*0.08 − salinity*0.18, 0, 1)` — `:457` |
| `weathering_index` | — | `clamp(weathering*(1 − mid_fraction*0.48) + (B ? 0.10 : 0), 0, 1)` — `:437` |

Note the horizon `ph` clamp is `[3.5, 9.5]`, wider than the profile clamp `[3.8, 9.2]`.

---

## The soil_profile_histories records

One history per profile, dense `id` (`soil_dynamics.py:765-788`). This is a **reconstruction**, not a simulation: the trajectory is fitted backwards from the final depth, and no step mutates any pool.

### Where the time axis comes from

`_pedogenesis_stages(world)` (`soil_dynamics.py:159-226`) picks one of three sources:

| Condition | `time_basis` | Stage source | Stage count |
|---|---|---|---|
| `world["generation_scope"] == "geo_only"` **and** `world["earth_system_feedback_history"]` is a non-empty list of dicts | `"natural_simulation_stage"` | `earth_system_feedback_history` | one stage per feedback record |
| otherwise, `world["historical_eras"]` is a non-empty list | `"historical_year_bp"` | `historical_eras`, sorted by descending `start_year_bp` then ascending `id` | one stage per era |
| otherwise | `"undated_diagnostic_step"` | synthetic single stage with `start_year_bp = 1.0`, `end_year_bp = 0.0`, `dominant_process = "undated"` | 1 |

In the natural-stage branch each stage carries `natural_stage_id`, `natural_stage_name`, `start_model_step`, `end_model_step`, `physical_time_resolved = False`, `nominal_time_calibrated = False`, and mirrors the feedback record's `nominal_time_basis`, `nominal_time_source_parameter`, `nominal_interval_start_ma`, `nominal_interval_end_ma`, `nominal_interval_duration_ma`. `nominal_time_link_available` is true only if all four probed keys — `nominal_time_basis`, `nominal_interval_start_ma`, `nominal_interval_end_ma` and `nominal_interval_duration_ma` — are present on the feedback step (`:174-182`). Note `nominal_time_source_parameter` is copied but **not** probed, so its absence does not clear the flag.

### Depth reconstruction

```text
age_fraction  = clamp(profile_age_ka / 85, 0, 1)
initial_depth = total_depth * clamp(0.34 + age_fraction*0.18 + development*0.12 − erodibility*0.08, 0.18, 0.86)
```
(`soil_dynamics.py:554-559`.) If the stage set is natural and **no** stage advances nominal time, `initial_depth` is forced to `total_depth`, so the whole trajectory is flat (`:560-561`).

Per stage (`:574-751`):

```text
advances_natural_time = time_basis == "natural_simulation_stage"
                        and nominal_interval_duration_ma > 0
progress   = advancing_stage_index / max(1, natural_advancing_stage_count)      # natural basis
           = stage_index / max(1, len(time_stages))                            # otherwise
end_depth  = initial_depth + (total_depth − initial_depth) * progress

erosion_pressure = clamp(erodibility*0.42 + relief*0.20 + runoff_norm*0.18
                         + erosion_rate_norm*0.14 + (1 − organic)*0.06, 0, 1)

erosion_loss = natural basis:  advances ? total_depth * erosion_pressure * 0.0035 / natural_advancing_stage_count : 0
             = otherwise:      total_depth * erosion_pressure * (0.0035 + 0.0015 * era_span_ky)

soil_production = max(0, end_depth − start_depth + erosion_loss)
```

with `runoff_norm = clamp(runoff_mm_y/1200, 0, 1)` and `erosion_rate_norm = clamp(erosion_rate*90, 0, 1)` (`:552-553`), and `era_span_ky = max(0.001, (start_year_bp − end_year_bp)/1000)` on the historical basis (`:599-610`). The last step's `end_depth_m` is forced to `total_depth` (`:753-754`).

### History record fields

| Field | Type | Meaning |
|---|---|---|
| `id` | int | list index |
| `soil_profile_id` | int | owning profile |
| `cell_id` | int | owning cell |
| `horizon_ids` | int[] | copy of the profile's horizon ids |
| `horizon_count` | int | copy |
| `parent_material` | string | copy |
| `profile_class` | string | copy |
| `initial_depth_m` | m | reconstructed starting depth |
| `final_depth_m` | m | equals `total_depth_m` |
| `final_profile_age_ka` | nominal ka | copy of `profile_age_ka` |
| `total_soil_production_m` | m | sum of `soil_production_m` over steps |
| `total_erosion_loss_m` | m | sum of `erosion_loss_m` over steps |
| `mean_weathering_index` | — | mean over *counted* steps (see divisor rule below) |
| `mean_leaching_index` | — | " |
| `mean_bioturbation_index` | — | " |
| `mean_horizon_differentiation_index` | — | " |
| `mean_pedogenic_flux_index` | — | " |
| `high_erosion_pressure` | bool | true iff some counted step has `erosion_pressure_index >= 0.65` |
| `step_count` | int | `len(steps)` |
| `steps` | object[] | see below |

The mean divisor is `max(1, natural_advancing_stage_count)` when the stage set is natural, else `len(steps)` (`:755-759`). Zero-duration natural stages contribute nothing to any of the five sums (`:744-751`) — so a world whose feedback ledger contains non-advancing stages still produces means normalized against advancing stages only.

### Step record fields

Common to every step (`soil_dynamics.py:671-698`):

| Field | Type | Notes |
|---|---|---|
| `era_id` | int | the era id on the historical basis; `-1` otherwise |
| `stage_index` | int | 1-based |
| `time_basis` | string | `natural_simulation_stage` \| `historical_year_bp` \| `undated_diagnostic_step` |
| `physical_time_resolved` | bool | always `false` |
| `start_depth_m`, `end_depth_m` | m | continuous: each step's start equals the previous step's end |
| `soil_production_m`, `erosion_loss_m` | m | `production == max(0, end − start + erosion_loss)` by construction |
| `weathering_index` | — | `clamp(weathering * (0.74 + progress*0.26), 0, 1)` |
| `leaching_index` | — | `clamp(leaching * (0.78 + progress*0.22), 0, 1)` |
| `bioturbation_index` | — | `clamp(bioturbation * (0.82 + progress*0.18), 0, 1)` |
| `organic_accumulation_index` | — | `clamp(organic*1.45 + bioturbation*0.18 + moisture*0.14 − salinity*0.18 − erosion_pressure*0.08, 0, 1)` |
| `horizon_differentiation_index` | — | `clamp(development*0.36 + min(1, horizon_count/4)*0.20 + weathering*0.16 + clay_translocation*0.14 + progress*0.14, 0, 1)` |
| `clay_translocation_index` | — | `clamp(leaching*0.40 + development*0.24 + moisture*0.14 + (1 − drainage)*0.12 + progress*0.10, 0, 1)` |
| `carbonate_mobilization_index` | — | `clamp(max(0, ph − 6.6)/2.8*0.30 + salinity*0.26 + leaching*0.22 + (1 − moisture)*0.10, 0, 1)` |
| `salinization_index` | — | `clamp(salinity*0.62 + (1 − leaching)*0.18 + (1 − moisture)*0.12 + max(0, ph − 7.2)/2.3*0.08, 0, 1)` |
| `erosion_pressure_index` | — | see formula above |
| `pedogenic_flux_index` | — | `clamp(production/max(0.001, total_depth)*0.32 + weathering*0.20 + leaching*0.16 + bioturbation*0.14 + horizon_differentiation*0.10 + organic_accumulation*0.08, 0, 1)`; **forced to `0.0`** on a non-advancing natural stage (`:666-667`) |

On the `natural_simulation_stage` basis the step additionally carries (`:700-728`): `natural_stage_id`, `natural_stage_name`, `start_model_step`, `end_model_step`, `nominal_time_link_available`, `nominal_time_basis`, `nominal_time_source_parameter`, `nominal_interval_start_ma`, `nominal_interval_end_ma`, `nominal_interval_duration_ma`, `nominal_time_calibrated = False`, plus `start_year_bp = None` and `end_year_bp = None` (explicit nulls — there is deliberately no fabricated calendar year). On the other bases it carries only rounded `start_year_bp` and `end_year_bp` (`:730-739`).

---

## The soil_pedogenesis_model contract

Written at `soil_dynamics.py:806-838`. This object is the page's central honesty artefact — read it before trusting any pedogenesis number.

| Key | Value | Meaning |
|---|---|---|
| `model_type` | `"posthoc_final_state_profile_reconstruction_v2"` | fixed string; validator-enforced |
| `time_basis` | `"natural_simulation_stage"` \| `"historical_year_bp"` \| `"undated_diagnostic_step"` | copied from the first stage |
| `stage_source` | `"earth_system_feedback_history"` \| `"historical_eras"` \| `"synthetic_fallback"` | derived from `time_basis` |
| `stage_count` | int | `len(time_stages)` |
| `physical_time_resolved` | **`false`** | always |
| `linked_nominal_time_coordinate_available` | bool | true only on the natural basis **and** when every stage's `nominal_time_link_available` is true (the four probed keys above). It records that a link exists, not that the nominal coordinate is calibrated — `nominal_time_calibrated` stays `false` regardless |
| `nominal_time_calibrated` | **`false`** | always |
| `state_mutation_evidence` | **`false`** | always — the steps do not mutate anything |
| `natural_stage_flux_partition` | `"normalized_across_nominally_advancing_erosion_intervals"` on the natural basis, else `"not_applicable"` | how the means are divided |
| `limitation` | `"depth and process indices are reconstructed from final cell state; steps do not mutate soil, water, vegetation, or climate pools"` | verbatim from `:834-837` |

`enrich_world_with_geo_evolution_provenance` (geo-only) reads this object to classify `soil_profile_histories` as a `posthoc_diagnostic_trajectory` and to decide whether a linked nominal time coordinate may be claimed (`src/magic_geo/geo_evolution_provenance.py:57`, `:94-96`, `:263-298`), and its declared limitation list includes "soil, vegetation, species, and wildfire diagnostics do not feed back into the native physical clock" (`:154`).

---

## Summary keys

The normal path writes 35 keys into `world["summary"]` (`soil_dynamics.py:840-886`). `divisor = float(soil_count)` when `soil_count > 0`, else the listed fallback is used.

| Key | Type | Meaning | Fallback when no soil cells |
|---|---|---|---|
| `soil_diagnostic_cell_count` | int | eligible cells | — |
| `soil_texture_counts` | map | sorted histogram of `soil_texture_class`, including `"none"` for ineligible cells | — |
| `soil_profile_count` | int | `len(soil_profiles)` | — |
| `soil_horizon_count` | int | `len(soil_horizons)` | — |
| `soil_profile_history_count` | int | `len(soil_profile_histories)` | — |
| `soil_pedogenesis_step_count` | int | sum of per-history `step_count` | — |
| `soil_pedogenesis_time_basis` | string | mirrors the model | — |
| `soil_pedogenesis_stage_count` | int | `len(time_stages)` | — |
| `soil_profile_class_counts` | map | sorted histogram of `profile_class` | — |
| `mean_soil_drainage_index` | float | mean over eligible cells | `0.0` |
| `mean_soil_moisture_index` | float | " | `0.0` |
| `mean_soil_ph` | float | " | **`7.0`** |
| `mean_soil_organic_matter_fraction` | float | " | `0.0` |
| `mean_soil_salinity_index` | float | " | `0.0` |
| `mean_soil_erodibility_index` | float | " | `0.0` |
| `mean_soil_profile_development_index` | float | " | `0.0` |
| `saline_soil_cell_fraction` | float | fraction with `salinity >= 0.55` | `0.0` |
| `high_erodibility_soil_fraction` | float | fraction with `erodibility >= 0.65` | `0.0` |
| `waterlogged_soil_cell_fraction` | float | fraction with `drainage <= 0.25` **and** `moisture >= 0.60` | `0.0` |
| `mean_soil_profile_depth_m` | float | mean `soil_depth_m` over eligible cells | `0.0` |
| `mean_soil_horizon_count` | float | mean horizons per profile | `0.0` |
| `mean_topsoil_organic_matter_fraction` | float | mean `organic_matter_fraction` of each profile's **first** horizon | `0.0` |
| `mean_soil_weathering_index` | float | mean profile weathering | `0.0` |
| `mean_soil_leaching_index` | float | mean profile leaching | `0.0` |
| `mean_soil_bioturbation_index` | float | mean profile bioturbation | `0.0` |
| `mature_soil_profile_fraction` | float | fraction with `development >= 0.62` | `0.0` |
| `shallow_soil_profile_fraction` | float | fraction with `depth <= 0.55` m | `0.0` |
| `total_soil_production_m` | float | sum over histories | `0.0` |
| `total_soil_erosion_loss_m` | float | sum over histories | `0.0` |
| `mean_pedogenic_weathering_index` | float | mean of per-history `mean_weathering_index` | `0.0` |
| `mean_pedogenic_leaching_index` | float | " | `0.0` |
| `mean_pedogenic_bioturbation_index` | float | " | `0.0` |
| `mean_horizon_differentiation_index` | float | " | `0.0` |
| `mean_pedogenic_flux_index` | float | " | `0.0` |
| `high_erosion_pedogenesis_count` | int | histories with `high_erosion_pressure == true` | `0` |

Only five keys — `mean_pedogenic_weathering_index`, `mean_pedogenic_leaching_index`, `mean_pedogenic_bioturbation_index`, `mean_horizon_differentiation_index` and `mean_pedogenic_flux_index` — use `history_divisor = len(soil_profile_histories)` instead of `soil_count`, so they are per-profile means (`:868`, `:871-885`). The two adjacent totals `total_soil_production_m` / `total_soil_erosion_loss_m` are plain undivided sums (`:869-870`) and `high_erosion_pedogenesis_count` is a count (`:886`); none of the three is divided by anything.

---

## Interactions with the sediment system

Soils and sediment touch at exactly four points, and every one of them is one-directional.

| Direction | Coupling | Where |
|---|---|---|
| sediment → soil | `sediment_thickness_m` enters the native resource rule (`sediment_thickness_m > 1.4` → sedimentary fuels / evaporites) | `cpp/src/engine/environment.cpp:394-395` |
| sediment → soil | `sediment_thickness_m` enters the diagnostic development index at weight `0.10` (normalized by `/4.0`) | `src/magic_geo/soil_dynamics.py:405` |
| sediment → soil | `sediment_thickness_m` selects `alluvial_silt` vs `silt_loam` (`>= 0.35`) and gates the `silt_loam` fallback (`>= 1.0` with `fertility >= 0.45`); `>= 1.5` forces `parent_material = alluvium` | `soil_dynamics.py:244`, `:257`, `:58` |
| sediment → soil | `erosion_rate` — the exported stream-power response — enters `erodibility` (weight `0.10` after `clamp(erosion_rate*90, 0, 1)`), `profile_age_ka` (`−120 ×`), and `erosion_pressure_index` (weight `0.14`) | `soil_dynamics.py:395`, `:417`, `:553`, `:594` |
| soil → sediment | **none** | — |

There is no soil → sediment path at all. `soil_depth_m` is not part of the canonical sediment interface, is not a term in `bedrock_surface_elevation_m` or `sediment_thickness_m`, and never enters `apply_sediment_interface_material_change`. The two "depths" are separate quantities on the same cell:

| | `sediment_thickness_m` | `soil_depth_m` |
|---|---|---|
| Authority | canonical geometric state; `elevation_m = bedrock_surface_elevation_m + sediment_thickness_m` | derived diagnostic |
| Mutated by | hillslope, fluvial, glacial transport, numeric-breach correction, sea-level datum shifts, tectonic displacement | nothing after `environment.cpp:338` |
| Replayed by validators | yes, cell by cell | no |
| Range | unbounded above, nonnegative | `[0.02, 5.0]` m on land |

Likewise, the pedogenesis `soil_production_m` and `erosion_loss_m` in `soil_profile_histories` are **not** mass fluxes and are not reconciled against the sediment budget. They sum to a depth change fitted to the final `soil_depth_m`, and the sediment inventory closure (`summary.sediment_inventory_mass_balance_residual_km3` and friends) does not see them.

The glacial transport that *does* move real material is `transport_glacial_sediment` in the same file (`cpp/src/engine/environment.cpp:102-299`), using `GLACIAL_SEDIMENT_MOBILE_FRACTION = 0.28` (`cpp/src/engine/constants.hpp:67`) and routing through `apply_sediment_interface_material_change` (`environment.cpp:245-252`). It runs at `pipeline.cpp:152`, long before soils exist, and interacts with soils only indirectly through the `sediment_thickness_m` value soils later read.

---

## Validation

Soil products are checked by two independent validators and one layer-contract gate.

### `geo_validation.py` — coverage and bounds

`soil_profile_coverage_and_bounds`, domain `soil_biome` (`src/magic_geo/geo_validation.py:2195-2264`). It rebuilds the eligible cell set with the identical `water_body_type == "land"` / `soil_type != "none"` / `soil_depth_m > 0` predicate and requires:

- exactly one profile per eligible cell, no duplicates, no profile on an ineligible cell;
- `total_depth_m` finite, `>= 0`, and within `1e-5` of the cell's `soil_depth_m`;
- `ph` finite and in `[0, 14]`;
- `drainage_index`, `moisture_index`, `organic_matter_fraction`, `salinity_index`, `erodibility_index`, `development_index` all finite and in `[0, 1]`;
- `profile_record["soil_type"] == cell["soil_type"]` and `profile_record["id"] == cell["soil_profile_id"]`;
- every ineligible cell carries `soil_profile_id == -1` **and** `soil_horizon_count == 0`.

`soil_depth_m` is also in the global non-negativity contract check `cell_types_enums_and_nonnegative_states` (`geo_validation.py:1036`).

### `geo_validation_subsystems.py` — link and replay integrity

`soil_profile_horizon_history_links`, domain `soils_and_ecotones` (`src/magic_geo/geo_validation_subsystems.py:884-1232`). Checks, in order:

| Check | Detail | Line |
|---|---|---|
| Structure and dense ids | `soil_profiles`, `soil_horizons`, `soil_profile_histories` are record lists with sequential ids | `:908-916` |
| Model metadata | `model_type == "posthoc_final_state_profile_reconstruction_v2"`, `physical_time_resolved is False`, `state_mutation_evidence is False` | `:917-924` |
| Geo-only stage ledger | `time_basis == "natural_simulation_stage"`, `stage_source == "earth_system_feedback_history"`, `stage_count == len(earth_system_feedback_history)`, `natural_stage_flux_partition == "normalized_across_nominally_advancing_erosion_intervals"`, `linked_nominal_time_coordinate_available is True`, `nominal_time_calibrated is False` | `:925-938` |
| Cell source and mirror | one profile per existing cell, no duplicates; `cell["soil_profile_id"] == profile["id"]` | `:948-955` |
| Horizon ownership | `horizon_ids` unique, `horizon_count == len(horizon_ids)`, every id resolvable | `:956-963` |
| Horizon contiguity | `sequence_index` matches position; `top == previous_bottom`; `bottom − top == thickness`; all nonnegative | `:964-983` |
| Texture closure | `sand + silt + clay == 1` and each in `[0,1]` | `:984-989` |
| Bounded horizon fields | `organic_matter_fraction`, `salinity_index`, `root_density_index`, `weathering_index`, `carbonate_index` in `[0,1]` | `:990-998` |
| Depth closure | `sum(thickness) == total_depth_m` | `:1001-1002` |
| Bounded profile fields | nine indices in `[0,1]` | `:1003-1015` |
| History mirror | `soil_profile_id`, `cell_id`, `step_count == len(steps)`, one history per profile | `:1016-1029` |
| Geo-only stage coverage | `len(steps) == len(earth_system_feedback_history)` | `:1031-1032` |
| Step continuity | `stage_index == index + 1`; each step's `start_depth_m` equals the previous `end_depth_m`; `soil_production_m == max(0, end − start + erosion_loss)` within `3e-5` | `:1043-1070` |
| Natural time provenance | `start_year_bp`/`end_year_bp` are `None`; `natural_stage_id`/`natural_stage_name`/`start_model_step`/`end_model_step` and all five nominal-time fields match the feedback record | `:1072-1109` |
| Zero-duration invariance | when `nominal_interval_duration_ma == 0`: `start == end`, `production == 0`, `erosion_loss == 0`, `pedogenic_flux_index == 0` (each within `1e-9`) | `:1114-1125` |
| Bounded step indices | ten indices in `[0,1]` | `:1127-1140` |
| History totals | `initial_depth_m`, `final_depth_m` match the first/last step; `final_depth_m == total_depth_m`; production and erosion totals within `2e-4` | `:1147-1163` |
| History means | each of the five means equals the mean of the counted step values (natural basis counts only advancing stages) | `:1164-1178` |
| High-erosion mirror | `high_erosion_pressure` equals "some counted step has `erosion_pressure_index >= 0.65`" | `:1180-1192` |
| No orphans | every profile cell is inverse-mapped; every horizon and every history is referenced exactly once | `:1193-1199` |
| Summary mirrors | eight summary keys re-derived from the records | `:1200-1225` |

### Layer contract

`geo_layer_contracts.py:221-235` registers the `soils_pedogenesis` layer at phase 10, depending on `erosion_sediment`, `climate_atmosphere` and `cryosphere`, requiring `soil_pedogenesis_model` (dict) plus the three lists, mapping to validator domains `("soil_biome", "soils_and_ecotones")`, with:

- `temporal_class = "posthoc_diagnostic_history"`
- `evidence_class = "causal_source_links_without_pedogenic_process_calibration"`

The `biomes_ecosystems` layer (phase 11) declares `soils_pedogenesis` as a dependency (`:240`), which is the formal statement that biomes read soil, not the reverse.

### Tests

Dedicated soil coverage lives in `tests/test_validate_cli_biosphere_resources.py:390-668` (14 soil test methods), `tests/test_geo_validation_subsystems.py:142-233` and `:1143-1240`, `tests/test_enrichers_terrain_biome.py:86-360`, `tests/test_smoke_biosphere.py:232`, `:405`, and `tests/test_geo_evolution_provenance.py:215`, `:728`.

---

## Export surfaces

| Surface | Soil content | Reference |
|---|---|---|
| World document (`.json` / `.mgeo`) | `soil_type`, `soil_depth_m`, `fertility` per cell; the 10 enricher cell fields; `soil_profiles`, `soil_horizons`, `soil_profile_histories`, `soil_pedogenesis_model`; 35 summary keys | `cpp/src/engine/entity_serialization.cpp:338-343`; `src/magic_geo/soil_dynamics.py:800-886` |
| Cells CSV (`--cells-csv`) | `soil_type`, `soil_texture_class`, `soil_drainage_index`, `soil_moisture_index`, `soil_ph`, `soil_organic_matter_fraction`, `soil_salinity_index`, `soil_erodibility_index`, `soil_profile_development_index`, `soil_profile_id`, `soil_horizon_count` | `src/magic_geo/io/cells_csv.py:193-203` |
| Summary Markdown (`--summary`) | 31 scalar soil keys plus the `soil_texture_counts` and `soil_profile_class_counts` histograms | `src/magic_geo/io/summary_markdown.py:863-893`, `:1273-1274` |
| Debug export (`export-debug`) | every scalar cell column becomes a `cells/<field>` layer in `manifest.json` and a column in `tables/cells.parquet`; `soil_profiles` / `soil_horizons` are exported as record families | `src/magic_geo/debug_export.py:220-236`, `:868-886` |
| SVG render (`render`) | none — the map renderer has no soil layer | `src/magic_geo/cli/commands/render.py` |

Note the CSV asymmetry: `soil_depth_m` and `fertility` are **not** columns of the cells CSV. Its `fieldnames` list is fixed (`cells_csv.py:14-413`, written with `extrasaction="ignore"` at `:414`), and neither field appears in it. Read them from the world document or the debug parquet instead.

---

## Worked examples

Generate a full world and a geo-only world from the shipped earthlike seed:

```bash
python -m magic_geo generate \
  --config configs/earthlike_seed.yaml \
  --output runs/world.json \
  --summary runs/summary.md \
  --cells-csv runs/cells.csv

python -m magic_geo generate \
  --config configs/earthlike_seed.yaml \
  --output runs/geo.json \
  --geo-only
```

Validate the natural-geography layers, which is where the two soil check families live:

```bash
python -m magic_geo validate-geo --world runs/geo.json --profile earthlike --output runs/geo-report.json
```

Read the soil model contract and the pedogenesis time basis out of a generated world:

```bash
python - <<'PY'
import json
world = json.load(open("runs/geo.json"))
print(json.dumps(world["soil_pedogenesis_model"], indent=2))
print("profiles:", len(world["soil_profiles"]))
print("horizons:", len(world["soil_horizons"]))
print("histories:", len(world["soil_profile_histories"]))
PY
```

Cross-check that native `soil_depth_m` and the profile's `total_depth_m` agree, and confirm the eligibility gate:

```bash
python - <<'PY'
import json
world = json.load(open("runs/geo.json"))
by_id = {c["id"]: c for c in world["cells"]}
eligible = {
    c["id"] for c in world["cells"]
    if c["water_body_type"] == "land" and c["soil_type"] != "none" and c["soil_depth_m"] > 0.0
}
covered = {p["cell_id"] for p in world["soil_profiles"]}
assert eligible == covered, (len(eligible), len(covered))
worst = max(
    abs(p["total_depth_m"] - by_id[p["cell_id"]]["soil_depth_m"])
    for p in world["soil_profiles"]
)
print("eligible cells:", len(eligible), "max depth mismatch:", worst)
PY
```

Confirm the chemical-weathering flag is exactly `false` in both model objects:

```bash
python - <<'PY'
import json
world = json.load(open("runs/geo.json"))
for key in ("sediment_interface_model", "sediment_inventory_model"):
    print(key, world[key]["chemical_weathering_resolved"])
PY
```

Use the Python API directly instead of the CLI:

```python
from magic_geo.api import generate_geo_world
from magic_geo.config import load_config

world = generate_geo_world(load_config("configs/earthlike_seed.yaml"))
print(world["summary"]["soil_pedogenesis_time_basis"])   # "natural_simulation_stage"
print(world["summary"]["soil_texture_counts"])
```

Render a soil field as a diagnostic map:

```bash
python -m magic_geo export-debug --world runs/geo.json --output runs/debug
python -m magic_geo export-debug-map --debug-dir runs/debug --layer cells/soil_ph --projection mollweide
```

---

## Limitations and unresolved claims

1. **Chemical weathering is not modelled, and the codebase says so.** `chemical_weathering_resolved` is emitted as literal `false` in `sediment_interface_model` (`cpp/src/engine/process_serialization.cpp:1865`) and `sediment_inventory_model` (`:1987`). There is no mineral pool, no dissolution flux, no solute balance and no weathering rate law anywhere in the engine or the enrichers. The fields named `weathering_index` (profile, horizon and step) are bounded 0–1 blends of already-derived quantities; they are diagnostic scores, not fluxes, and they never modify state. Do not describe magic-geo as modelling chemical weathering.

2. **Pedogenesis has no physical time.** `soil_pedogenesis_model.physical_time_resolved` is always `false`, `nominal_time_calibrated` is always `false`, and the declared limitation is verbatim: *"depth and process indices are reconstructed from final cell state; steps do not mutate soil, water, vegetation, or climate pools"* (`src/magic_geo/soil_dynamics.py:819-837`). Even on the geo-only natural basis, where each step is linked to a real feedback stage and inherits that stage's nominal interval, the nominal timestep itself is uncalibrated across the whole engine. The layer contract classifies this as `posthoc_diagnostic_history` with `evidence_class = "causal_source_links_without_pedogenic_process_calibration"` (`geo_layer_contracts.py:233-234`).

3. **The pedogenesis trajectory is fitted, not simulated.** `initial_depth` is a fraction of the *final* depth (`soil_dynamics.py:554-559`) and `end_depth` is a linear interpolation toward the final depth by `progress`. `soil_production_m` is defined as whatever closes `max(0, end − start + erosion_loss)`. `state_mutation_evidence` is `false`. No step writes back to `soil_depth_m` or anything else.

4. **`profile_age_ka` is a label, not an age.** It is `depth*18 + development*36 + (1 − relief)*16 − erosion_rate*120` (`soil_dynamics.py:417`), and `erosion_rate` is itself the un-timestep-scaled 5 Ma reference stream-power response documented at `cpp/src/engine/earth_system.cpp:988-992`. The `ka` suffix carries no calibration.

5. **Soil is a single-pass terminal derivation, not an evolving state.** `derive_soils_biomes_resources` runs once at `pipeline.cpp:187`, after every maturation iteration has finished. No soil field appears in `earth_system_feedback_history`, in any transport ledger, or in any conservation closure. Soils do not affect erosion, hydrology, climate, sediment or tectonics — the coupling is strictly one-way.

6. **`soil_depth_m` has no mass, density or porosity.** It is a clamped algebraic depth in `[0.02, 5.0]` m with no relation to `sediment_thickness_m`, `bedrock_surface_elevation_m` or the sediment inventory. The sediment interface's own flags (`dry_rock_mass_resolved`, `sediment_density_resolved`, `porosity_resolved`, `compaction_resolved`, `grain_provenance_resolved`) are all `false`; the soil layer inherits every one of those gaps and adds none of its own resolution.

7. **`derive_landforms` silently overwrites the classification chain.** On `delta`, `floodplain`, `alluvial_fan`, `salt_flat`, `glacial_valley` and `moraine` cells, the serialized `soil_type` is the landform's, not the climate chain's (`cpp/src/engine/environment.cpp:476-500`). `glacial_lake` is exempt from the soil override but not from the settlement multiplier. Anyone re-deriving `soil_type` from climate alone will disagree with the world document on those cells.

8. **The serialized `fertility` is not the `fertility` that produced `settlement_score`.** Landform bonuses of `+0.16` (delta) and `+0.10` (floodplain) are applied at `environment.cpp:478`, after `settlement_score` was already computed at `:410`. The independent replay in `src/magic_geo/cli/validators/settlement.py:182-188`, `:291`, `:298-308` reproduces this ordering deliberately.

9. **Lake cells receive native soil state that no diagnostic ever uses.** The native lake branch assigns `soil_type = wetland | saline` and a positive `soil_depth_m` (`environment.cpp:341-344`), but because the same branch sets `water_body` to `fresh_lake`/`saline_basin`, the enricher's `water_body_type == "land"` gate (`soil_dynamics.py:323`) excludes them and stamps `soil_texture_class = "none"`, `soil_profile_id = -1`. `geo_validation.py:2196-2202` uses the same predicate, so this is consistent, not a validation gap — but a consumer reading `soil_type` directly will see `wetland`/`saline` on cells that have no profile.

10. **Two guards in the enricher are unreachable from native output.** `saline_water` (`soil_dynamics.py:349`) requires either `water_body_type == "saline_basin"` — contradicted by the eligibility gate that already passed — or `depression_policy == "preserve_geologic_sink"`, a string absent from `DEPRESSION_POLICY_NAMES` (`cpp/src/engine/schema_names.hpp:53-56`); it is exercised only by synthetic fixtures (`tests/test_enrichers_terrain_biome.py:142`, `:247`). Consequently `salinity >= 0.55` is attainable on a native world only with `is_closed_basin` true. Separately, `_parent_material`'s marine branch lists `beach`, `barrier_bar` and `barrier_island` (`soil_dynamics.py:60`), which are `COASTAL_FEATURE_TYPE_NAMES` and never appear as a cell `landform`; only `coastal_plain` can match. The `mixed_regolith` fallback (`:70`) is likewise unreachable because rules 4–7 cover all seven lithologies. These are observations from the source, stated so that consumers do not expect those code paths to fire.

11. **`litho_base` is coarse.** Four of the seven lithologies (`basalt`, `limestone`, `sandstone`, `metamorphic`) share the same fertility base of `0.58` (`environment.cpp:336`). Lithological control on fertility is therefore effectively three-valued.

12. **The two `aridity` variables are opposites.** Native `aridity = precipitation / PET` is a humidity ratio where higher means wetter (`environment.cpp:310`); the enricher's `aridity` is a dryness index where higher means drier (`soil_dynamics.py:352`). They share a name and nothing else.

13. **The two `relief` definitions differ.** Native `local_relief` is `elevation − mean(neighbour elevation)`, clamped at zero (`cpp/src/engine/climate.cpp:15-25`); the enricher's `_neighbor_relief` is `max |elevation − neighbour elevation|` normalized by 1800 m (`soil_dynamics.py:148-156`). Only the second is bounded to `[0,1]`.

14. **The empty-cells path emits a different summary key set.** With no cells, only 15 of the 35 summary keys are written, and the model degrades to `time_basis = "unavailable_without_cells"`, `stage_source = "none"` (`soil_dynamics.py:264-291`). Downstream code must use `.get(...)` with defaults.

15. **Soil is not calibrated against any real-Earth dataset.** `CALIBRATION_METRIC_NAMES` (`cpp/src/engine/schema_names.hpp`, 12 entries) contains no soil metric, and `generate_calibration_checks` produces no soil check. Nothing in the calibration suite constrains `soil_type`, `soil_depth_m`, `fertility` or any diagnostic index.

16. **No soil layer exists in the map renderer.** Soil fields are visualizable only through the generic debug-export layer catalog (`cells/<field>`) or the cells CSV subset.

---

## See also

- [Erosion, Maturation and Landscape Evolution](erosion-and-maturation.md) — where `erosion_rate` comes from and why it is a 5 Ma reference response
- [Sediment, Routing and Stratigraphy](sediment-and-stratigraphy.md) — the canonical bedrock/mobile-sediment interface and the `chemical_weathering_resolved = false` contract
- [Biomes, Ecosystems and Disturbance](biomes-and-ecology.md) — the classification chain that shares the soil `if/else` and the largest consumer of the soil indices
- [Climate and Atmosphere](climate-and-atmosphere.md) — `temperature_c`, `precipitation_mm_y`, the monthly climatology and `seasonal_aridity_index`
- [Hydrology, Rivers and Lakes](hydrology-and-rivers.md) — `is_river`, `is_lake`, `is_closed_basin`, `runoff_mm_y`, `depression_policy` and the lake `water_body` reclassification
- [Groundwater, Aquifers and Karst](groundwater-and-karst.md) — the aquifer and karst models that consume `soil_drainage_index`, `soil_ph` and `soil_profile_development_index`
- [Cryosphere: Ice Sheets, Glaciers and Permafrost](cryosphere.md) — `ice_thickness_m` and the permafrost model's use of the soil indices
- [Resources and Economic Geology](resources-and-economic-geology.md) — `fertile_alluvium`, land-use zones and the soil-conditioned resource rules
- [Settlements, Routes and Corridors](settlements-and-routes.md) — the settlement score's `0.30` fertility weight and its replay
- [Tectonics and Plates](tectonics-and-plates.md) — the `lithology` and `crust_type` fields the soil stage reads
- [Native Engine (C++ Core)](../08-native-engine.md) — stage ordering and the pipeline invariants
- [World Document Schema](../10-world-schema.md) — the full per-cell field list and precision contracts
- [Validation](../12-validation.md) — the strict validators and mutation-rejection gates
- [Geo Validation Suite](../13-geo-validation-suite.md) — the `soil_biome` and `soils_and_ecotones` domains
- [Debug Exports and Visualization](../16-debug-and-visualization.md) — the `cells/<field>` layer catalog
- [Glossary](../21-glossary.md) — resolution flags and unresolved-claim vocabulary
