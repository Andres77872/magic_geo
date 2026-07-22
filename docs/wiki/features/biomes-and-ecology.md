# Biomes, Ecosystems and Disturbance

[Wiki home](../README.md) > Features

The living layer of a magic-geo world is produced in two distinct places with two distinct authority levels. A single native C++ stage, `derive_soils_biomes_resources` (`cpp/src/engine/environment.cpp:301`), writes the authoritative per-cell `biome` enum from a deterministic threshold cascade over climate, elevation, ice, water-body state and river state; `derive_landforms` (`cpp/src/engine/environment.cpp:417`) may then overwrite that enum on floodplains and deltas. Everything else on this page — biome diagnostics, ecotones, ecosystem productivity, species ranges, wildfire disturbance and the biome realism checks — is *post-hoc Python enrichment* over the serialized world, classified by `geo_layer_contracts.py` as `posthoc_diagnostic_trajectories` with `evidence_class = rule_replay_without_population_evolution`. None of it feeds back into the native simulation, none of it is time-calibrated, and no population, dispersal or evolutionary process is modelled anywhere.

## On this page

- [Where the living layer is produced](#where-the-living-layer-is-produced)
- [Native biome assignment](#native-biome-assignment)
- [Full biome class table and envelopes](#full-biome-class-table-and-envelopes)
- [Post-classification overrides](#post-classification-overrides)
- [Worked native classification examples](#worked-native-classification-examples)
- [Biome diagnostics](#biome-diagnostics)
- [The expected-biome shadow classifier](#the-expected-biome-shadow-classifier)
- [Ecotone detection](#ecotone-detection)
- [Ecosystem dynamics](#ecosystem-dynamics)
- [Species range modelling](#species-range-modelling)
- [Wildfire disturbance](#wildfire-disturbance)
- [Biome realism checks](#biome-realism-checks)
- [Complete emitted-record field tables](#complete-emitted-record-field-tables)
- [Per-cell field inventory](#per-cell-field-inventory)
- [Summary key inventory](#summary-key-inventory)
- [Ordering dependencies](#ordering-dependencies)
- [Validators](#validators)
- [Worked commands](#worked-commands)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

---

## Where the living layer is produced

### Native stage placement

`derive_soils_biomes_resources` is called from `simulate_world_impl` at `cpp/src/engine/pipeline.cpp:187`, immediately after `summarize_plates` (`pipeline.cpp:186`) and immediately before `derive_landforms` (`pipeline.cpp:188`). The engine does not number its stages, so no ordinal is claimed here — only the neighbours in the call sequence, which are exact. Everything the stage reads has already reached its terminal value:

| Native stage | Pipeline line | What it fixes that biome assignment reads |
|---|---|---|
| `stabilize_numeric_depressions(..., "cryosphere_coupling", ...)` | `pipeline.cpp:157-166` | `elevation_m`, `is_water`, `water_body`, `water_depth_m`, `temperature_c`, `precipitation_mm_y`, `temperature_monthly_c`, `precipitation_monthly_mm`, `runoff_mm_y`, `flow_to`, `is_river`, `is_lake`, `is_closed_basin` |
| `derive_cryosphere_state` (second call) | `pipeline.cpp:167` | `ice_thickness_m`, `glacial_erosion_m` |
| `summarize_plates` | `pipeline.cpp:186` | plate aggregates (not read by the classifier) |
| **`derive_soils_biomes_resources`** | **`pipeline.cpp:187`** | writes `soil_type`, `soil_depth_m`, `fertility`, `biome`, `resource`, `settlement_score`; may rewrite `water_body` for lakes |
| `derive_landforms` | `pipeline.cpp:188` | writes `landform`; **may overwrite `biome`, `soil_type`, `fertility`, `resource`, `settlement_score`** |

Crust and boundary state (`crust_type`, `lithology`, `boundary_convergent`, `boundary_divergent`, `boundary_transform`, `crust_age_ma`, `sediment_thickness_m`) is read for the soil/resource/settlement half of the same stage. The biome branch itself reads only climate, elevation, ice, water and river state.

`stabilize_numeric_depressions` is the stage that makes this true: it internally calls `apply_sea_level` and `compute_climate` and re-runs depression routing, so after the `"cryosphere_coupling"` call every climate and hydrology field the classifier reads is final.

The stage runs under `#pragma omp parallel for schedule(static)` (`environment.cpp:304`) and every cell is independent except through `local_relief` and `has_ocean_neighbor`, which are read-only neighbourhood queries.

### Python enricher placement

Six enrichers own the diagnostic living layer. They run in a fixed order inside `magic_geo.api`:

| Enricher | Module | `generate_world` line | `generate_geo_world` line |
|---|---|---|---|
| `enrich_world_with_biome_diagnostics` | `src/magic_geo/biome_dynamics.py:89` | `src/magic_geo/api.py:224` | `src/magic_geo/api.py:344` |
| `enrich_world_with_biome_ecotones` | `src/magic_geo/biome_ecotones.py:205` | `api.py:227` | `api.py:345` |
| `enrich_world_with_biome_realism` | `src/magic_geo/biome_realism.py:90` | `api.py:228` | `api.py:346` |
| `enrich_world_with_ecosystem_dynamics` | `src/magic_geo/ecosystem_dynamics.py:133` | `api.py:245` | `api.py:359` |
| `enrich_world_with_species_ranges` | `src/magic_geo/species_ranges.py:297` | `api.py:247` | `api.py:361` |
| `enrich_world_with_wildfire_disturbance` | `src/magic_geo/wildfire_disturbance.py:270` | `api.py:248` | `api.py:362` |

All six have the signature `(world: dict[str, Any]) -> dict[str, Any]`, take no tuning parameters, and every one returns `world` unchanged if `world["cells"]` is absent, not a list, or empty.

They belong to layer contract `biomes_ecosystems`, phase 11 (`src/magic_geo/geo_layer_contracts.py:237-258`), whose declared dependencies are `soils_pedogenesis`, `climate_atmosphere` and `hydrology`, whose `temporal_class` is `posthoc_diagnostic_trajectories` and whose `evidence_class` is `rule_replay_without_population_evolution`.

---

## Native biome assignment

`derive_soils_biomes_resources` computes five scalars before it branches (`environment.cpp:307-326`):

| Local | Expression | Source line | Note |
|---|---|---|---|
| `relief` | `local_relief(cells, i)` = `max(0, elevation_m - mean(neighbour elevation_m))` | `environment.cpp:307`, `climate.cpp:15` | Metres; zero if the cell has no neighbours |
| `slope_penalty` | `clamp(relief / 1800.0, 0, 1)` | `environment.cpp:308` | Used only by the soil/settlement half |
| `pet` | `max(1.0, (temperature_c + 8.0) * 31.0)` | `environment.cpp:309` | **Native PET proxy**, mm/y-scaled, no latitude term |
| `aridity` | `precipitation_mm_y / pet` | `environment.cpp:310` | **A moisture ratio (P/PET), not a deficit.** Higher = wetter |
| `latitude_pet_factor` | `0.66 + 0.34 * (1 - min(1, abs(lat) * DEG / 90))` | `environment.cpp:311-312` | `cell.lat` is radians; `DEG = 180/PI` (`constants.hpp:6`) |

The seasonality gate is computed inline over the monthly climate arrays (`environment.cpp:313-325`):

```
for month in [0, min(len(temperature_monthly_c), len(precipitation_monthly_mm))):
    monthly_pet   = max(0, temperature_monthly_c[month] + 5.0) * 3.1 * latitude_pet_factor
    dry_season_months += (precipitation_monthly_mm[month] <  monthly_pet * 0.35)
    wet_season_months += (precipitation_monthly_mm[month] >= monthly_pet * 0.75)

warm_seasonal_climate = (dry_season_months >= 2) and (wet_season_months >= 3)
```

`climate.months` is a `Literal[12]` in `src/magic_geo/config.py:324`, so both arrays always have exactly 12 entries in a configured world.

The `coast` flag is `has_ocean_neighbor(cells, i)` (`environment.cpp:5-12`), true when any neighbour has `is_water == true`. Because `is_water` is set only by the marine flood-fill in `cpp/src/engine/ocean.cpp:250`, **lakes are not `is_water`**: a lake cell has `is_lake == true` and `is_water == false`, and is classified through the *land* branch.

### Water-body enum recap

`WATER_BODY_NAMES` (`cpp/src/engine/schema_names.hpp:34-36`) and where each value comes from:

| Value | Name | Assigned by |
|---|---|---|
| 0 | `land` | `ocean.cpp:271` for non-marine, `ocean.cpp:314`, `hydrology.cpp:599` reset |
| 1 | `ocean` | `label_marine_water_bodies`: largest marine component, `water_depth_m >= 220.0` (`ocean.cpp:316`) |
| 2 | `continental_shelf` | largest marine component, `water_depth_m < 220.0` (`ocean.cpp:316`) |
| 3 | `inland_sea` | any marine component that is not the largest (`ocean.cpp:318`) |
| 4 | `fresh_lake` | `hydrology.cpp:633` when `aridity >= 0.5`, or unconditionally when the lake overflows (`hydrology.cpp:642`, `:647`); re-asserted at `environment.cpp:342` |
| 5 | `saline_basin` | `hydrology.cpp:633` when `aridity < 0.5`, and `hydrology.cpp:655` for dry geologic depressions with `aridity < 0.55`; re-asserted at `environment.cpp:342` |

---

## Full biome class table and envelopes

`BIOME_NAMES` has 16 entries (`cpp/src/engine/schema_names.hpp:21-26`). The classifier is a strictly ordered if/else cascade — **the first matching row wins** — split into a water branch (`environment.cpp:327-334`) and a land branch (`environment.cpp:341-381`). `T` = `temperature_c`, `P` = `precipitation_mm_y`, `E` = `elevation_m`, `H` = `ice_thickness_m`, `aridity` = `P / max(1, (T+8)*31)`.

| # | Enum index | `biome` name | Branch order | Exact envelope that produces it | Co-assigned `soil_type` | Source |
|---|---|---|---|---|---|---|
| W1 | 1 | `continental_shelf` | water, 1st | `is_water` and `water_body == 2` | `0` (`none`) | `environment.cpp:331` |
| W2 | 2 | `lake` | water, 2nd | `is_water` and `water_body == 3` (**inland sea**) | `0` (`none`) | `environment.cpp:331` |
| W3 | 0 | `ocean` | water, else | `is_water` and `water_body` not in `{2,3}` | `0` (`none`) | `environment.cpp:331` |
| L1a | 10 | `hot_desert` | land, 1st | `is_lake` and `aridity < 0.5` (also forces `water_body = 5`) | `10` (`saline`) | `environment.cpp:341-344` |
| L1b | 2 | `lake` | land, 1st | `is_lake` and `aridity >= 0.5` (also forces `water_body = 4`) | `9` (`wetland`) | `environment.cpp:341-344` |
| L2 | 3 | `ice_cap` | land, 2nd | `H > 180.0` **or** (`T < -8.0` and (`abs(lat)*DEG > 55.0` or `E > 1600.0`)) | `8` (`tundra`) | `environment.cpp:345-348` |
| L3 | 14 | `alpine` | land, 3rd | `E > 2800.0` and `T < 6.0` | `1` (`thin_mountain`) | `environment.cpp:349-351` |
| L4 | 4 | `tundra` | land, 4th | `T < -2.0` | `8` (`tundra`) | `environment.cpp:352-354` |
| L5a | 9 | `cold_desert` | land, 5th | `aridity < 0.32` and `T < 11.0` | `4` (`arid`) | `environment.cpp:355-357` |
| L5b | 10 | `hot_desert` | land, 5th | `aridity < 0.32` and `T >= 11.0` | `4` (`arid`) | `environment.cpp:355-357` |
| L6 | 13 | `tropical_rainforest` | land, 6th | `T > 23.0` and `P > 2100.0` | `5` (`tropical`) | `environment.cpp:358-360` |
| L7 | 12 | `tropical_seasonal_forest` | land, 7th | `T > 21.0` and `P > 950.0` | `5` (`tropical`) | `environment.cpp:361-363` |
| L8 | 11 | `savanna` | land, 8th | `T > 18.0` and `aridity < 0.82` and `warm_seasonal_climate` | `4` (`arid`) | `environment.cpp:364-366` |
| L9 | 6 | `temperate_forest` | land, 9th | `T > 8.0` and `P > 760.0` | `6` (`temperate`) | `environment.cpp:367-369` |
| L10a | 6 | `temperate_forest` | land, 10th | `T > 5.0` and `aridity > 1.1` | `6` (`temperate`) | `environment.cpp:370-372` |
| L10b | 7 | `temperate_grassland` | land, 10th | `T > 5.0` and `0.45 < aridity <= 1.1` | `6` (`temperate`) | `environment.cpp:370-372` |
| L11 | 5 | `boreal_forest` | land, 11th | `T > -1.0` and `P > 420.0` | `7` (`boreal`) | `environment.cpp:373-375` |
| L12a | 4 | `tundra` | land, else | `T < 2.0` and `P > 320.0` and `aridity > 0.55` | `4` (`arid`) | `environment.cpp:376-381` |
| L12b | 9 | `cold_desert` | land, else | not L12a and `T < 8.0` | `4` (`arid`) | `environment.cpp:376-381` |
| L12c | 10 | `hot_desert` | land, else | not L12a and `T >= 8.0` | `4` (`arid`) | `environment.cpp:376-381` |
| — | 15 | `wetland` | override | see [Post-classification overrides](#post-classification-overrides) | `3` (`alluvial`) | `environment.cpp:382-386`, `environment.cpp:476-481` |
| — | 8 | `mediterranean_scrub` | **never assigned** | No statement anywhere in the engine writes `cell.biome = 8` | — | verified by exhaustive grep over `cpp/src/engine/*.cpp` |

Notes that follow directly from the table:

- **`mediterranean_scrub` is an unreachable enum value.** It exists in `BIOME_NAMES` and it is referenced by several Python enrichers as a grassland/fuel category, but no native branch produces it, so `summary.biome_counts` can never contain it.
- **Arid closed-basin lakes are labelled `hot_desert`.** Row L1a fires for any `is_lake` cell with `aridity < 0.5` regardless of temperature, and simultaneously stamps `water_body = saline_basin` and `soil_type = saline`. A high-latitude playa is therefore a `hot_desert` biome cell.
- **Non-largest marine components are labelled `lake`.** Row W2 maps `water_body == inland_sea` onto biome `lake`, so a large enclosed sea shares a biome label with a freshwater lake.
- **`ice_cap` gets `tundra` soil.** Row L2 sets `soil_type = 8` (`tundra`), not a distinct ice class.
- **Row L12c can label a 10 °C cell `hot_desert`.** The final else-branch splits on `T < 8.0`, with no precipitation guard beyond the failed earlier rows.
- **Rows L9 and L10a both produce `temperate_forest`** through different predicates (absolute precipitation vs. a very wet moisture ratio).

---

## Post-classification overrides

Two override blocks can rewrite the biome after the cascade.

### Override A — riverine wetland, inside `derive_soils_biomes_resources`

`environment.cpp:382-389`:

| Condition | Effect |
|---|---|
| `is_river` and `relief < 450.0` and `P > 500.0` | `soil_type = 3` (`alluvial`); and if `biome not in {13 tropical_rainforest, 3 ice_cap}` then `biome = 15` (`wetland`) |
| else if `lithology == 5` (`volcanic`) and `soil_type != 8` | `soil_type = 2` (`volcanic`) — soil only, biome untouched |

### Override B — floodplain/delta wetland, inside `derive_landforms`

`derive_landforms` runs one stage later and classifies `landform` first (`environment.cpp:430-474`), then applies landform-conditioned edits (`environment.cpp:476-503`):

| Landform | Index | Edits applied |
|---|---|---|
| `delta` / `floodplain` | 12 / 11 | `soil_type = 3`; `fertility += 0.16` (delta) or `0.10` (floodplain), clamped to `[0,1]`; **if `P > 500.0` and `biome != 3` then `biome = 15` (`wetland`)**; if `fertility > 0.64` then `resource = 7`; `settlement_score += 0.08` |
| `alluvial_fan` | 13 | `soil_type = 4` unless it was `8`; `resource = 5` if it was `0` and `boundary_convergent > 0.10`; `settlement_score += 0.03` |
| `salt_flat` | 4 | `soil_type = 10`; `resource = 4`; `settlement_score *= 0.55` |
| `glacial_valley` / `moraine` / `glacial_lake` | 17 / 18 / 19 | `soil_type = 8` except for `glacial_lake`; `settlement_score *= 0.72` (glacial_lake) or `0.42` |
| `coastal_plain` | 14 | `settlement_score += 0.04` when already positive |

Override B exempts only `ice_cap`, not `tropical_rainforest`. A delta inside a rainforest therefore becomes `wetland`, while a river cell in the same rainforest that is not a delta or floodplain stays `tropical_rainforest` under Override A.

Finally, `derive_soils_biomes_resources` scales the settlement score down for hostile biomes (`environment.cpp:411-413`): `settlement_score *= 0.18` when `biome` is `ice_cap` (3), `tundra` (4), `alpine` (14) or `ocean` (0).

---

## Worked native classification examples

All four use `pet = max(1, (T+8)*31)` and `aridity = P/pet`.

| Input | `pet` | `aridity` | First matching row | Result |
|---|---|---|---|---|
| `T = 25 °C`, `P = 2500 mm/y`, `E = 40 m`, `H = 0` | `1023.0` | `2.4438` | L6 (`T > 23`, `P > 2100`) | `biome = tropical_rainforest`, `soil_type = tropical` |
| `T = 20 °C`, `P = 300 mm/y`, `E = 300 m`, `H = 0`, aseasonal | `868.0` | `0.3456` | falls past L5 (`0.3456 >= 0.32`), L6–L11 all fail | else-branch L12c (`T >= 8`) → `biome = hot_desert`, `soil_type = arid` |
| `T = 10 °C`, `P = 200 mm/y`, `E = 500 m`, `H = 0` | `558.0` | `0.3584` | same fall-through | L12c → `biome = hot_desert` at 10 °C |
| `T = -5 °C`, `P = 300 mm/y`, `E = 200 m`, `lat = 65°`, `H = 0` | `93.0` | `3.2258` | L4 (`T < -2`) — L2 fails because `T` is not `< -8` | `biome = tundra`, `soil_type = tundra` |

The third row is the clearest demonstration that the else-branch is a genuine catch-all, not a cold-only fallback: any cell that is warm enough to miss `tundra`, wet enough to miss the `aridity < 0.32` desert gate, but too dry or too cool for every forest and grassland row, is emitted as a desert.

---

## Biome diagnostics

`src/magic_geo/biome_dynamics.py` computes a Thornthwaite-style monthly water balance per cell and a set of derived seasonality and confidence indices. It is the first biome enricher and every later enricher on this page depends on its outputs.

### Monthly water balance

`_monthly_values` (`biome_dynamics.py:11-16`) reads `temperature_monthly_c` and `precipitation_monthly_mm`; if either is absent or not exactly 12 long it synthesises a flat series (temperature repeated 12×, annual precipitation divided by 12). Because `climate.months` is fixed at 12, the fallback does not trigger in a configured world.

`_monthly_pet_mm` (`biome_dynamics.py:19-21`):

```
latitude_factor = 0.66 + 0.34 * (1.0 - min(1.0, abs(lat_deg) / 90.0))
monthly_pet_mm  = max(0.0, temperature_c + 5.0) * 3.1 * latitude_factor
```

This is algebraically the same monthly PET expression the native stage uses for its seasonality gate (`environment.cpp:319-320`), but it is **not** the same as the native `pet` used for `aridity`, and it is **not** bit-for-bit reproducible. The native gate consumes the in-memory `temperature_monthly_c` / `precipitation_monthly_mm`; the Python enricher consumes the serialized arrays, which `cells_json` writes at `output.float_precision` (default `4`, maximum `8` — `src/magic_geo/config.py:450`, `cpp/src/engine/entity_serialization.cpp:190`, `:192`). Cells sitting within that rounding of a monthly threshold can therefore be counted differently by the native `dry_season_months` / `wet_season_months` and by the diagnostic ones. (`lat_deg` is not a source of drift: `cells_json` writes it at `geometry_precision = max(max_digits10, precision)`, `entity_serialization.cpp:113-116`, `:125`.)

| Derived quantity | Definition | Source |
|---|---|---|
| `annual_pet` | `sum(monthly_pet)` over 12 months | `biome_dynamics.py:114` |
| `annual_precipitation` | `sum(max(0, monthly_precipitation))` | `biome_dynamics.py:115` |
| `climatic_water_deficit_mm_y` | `max(0, annual_pet - annual_precipitation)` | `biome_dynamics.py:116` |
| `climatic_water_surplus_mm_y` | `max(0, annual_precipitation - annual_pet)` | `biome_dynamics.py:117` |
| `growing_season_months` | count of months with `T >= 5.0` **and** `P >= pet * 0.25` | `biome_dynamics.py:118-122` |
| `frost_months` | count of months with `T < 0.0` | `biome_dynamics.py:123` |
| `dry_season_months` | count of months with `P < pet * 0.35` | `biome_dynamics.py:124` |
| `wet_season_months` | count of months with `P >= pet * 0.75` | `biome_dynamics.py:125` |
| `deficit_index` (internal) | `clamp(annual_deficit / max(1, annual_pet))` | `biome_dynamics.py:128` |
| `warmth_index` (internal) | `clamp((temperature_c + 5) / 30)` | `biome_dynamics.py:129` |

### Fire frequency index

`fire_frequency_index` (`biome_dynamics.py:130-138`) — note this is the **biome-diagnostic** fire index, distinct from `wildfire_spread_risk_index` (ecosystem dynamics) and `wildfire_ignition_potential_index` (wildfire disturbance).

```
fuel_index = clamp(0.18
                 + 0.28 if biome in {savanna, temperate_grassland, mediterranean_scrub} else 0
                 + 0.16 if "forest" in biome else 0
                 + soil_organic_matter_fraction * 0.70)

fire_frequency_index = 0.0 if is_water or biome in {ice_cap, tundra, alpine}
                       else clamp(warmth_index * 0.28
                                + deficit_index * 0.34
                                + seasonal_aridity_index * 0.20
                                + fuel_index * 0.18
                                - soil_moisture_index * 0.18)
```

The `mediterranean_scrub` term is dead code with respect to the native classifier (that biome is never emitted).

### Ecotone index and biome confidence

| Quantity | Definition | Source |
|---|---|---|
| `neighbor_biomes` | set of `biome` strings over resolvable neighbours | `biome_dynamics.py:139-143` |
| `neighbor_diversity` | `clamp((len(neighbor_biomes) - 1) / 4.0)`, `0.0` if the set is empty | `biome_dynamics.py:144` |
| `climate_margin` | `clamp(1 - abs(deficit_index - 0.50) * 2)` — peaks where the moisture regime is exactly halfway | `biome_dynamics.py:145` |
| `ecotone_index` | `clamp(neighbor_diversity*0.62 + climate_margin*0.26 + seasonal_aridity_index*0.12)` | `biome_dynamics.py:146` |
| `matches` | `expected == biome` **or** (`expected == "lake"` and `biome in {"lake","wetland"}`) | `biome_dynamics.py:149` |
| `biome_confidence_index` | `clamp((0.58 if matches else 0.30) + (1-ecotone)*0.22 + (1-deficit_index)*0.08 + soil_moisture_index*0.12)` | `biome_dynamics.py:150` |
| `biome_transition_zone` | `ecotone_index >= 0.55` **or** `not matches` | `biome_dynamics.py:151` |

The three ecotone weights sum to exactly `1.00`, so `ecotone_index` is a convex combination.

---

## The expected-biome shadow classifier

`_expected_biome` (`biome_dynamics.py:24-62`) is an **independent second classifier** that reproduces a Köppen-like envelope from the diagnostic water balance. It never overwrites `cell["biome"]`; it only produces `biome_diagnostics[].expected_biome`, the `matches` flag and, through it, `biome_confidence_index`, `biome_transition_zone` and `summary.biome_expected_match_fraction`.

Its aridity variable has the **opposite polarity** to the native one: `aridity = clamp(annual_deficit / max(1, annual_pet))`, so higher = drier.

| Order | Predicate | Returned `expected_biome` |
|---|---|---|
| 1 | `is_water` and `water_body_type == "continental_shelf"` | `continental_shelf` |
| 2 | `is_water` and `water_body_type in {fresh_lake, saline_basin, inland_sea}` | `lake` |
| 3 | `is_water` (else) | `ocean` |
| 4 | `ice_thickness_m > 120.0` **or** `biome == "ice_cap"` | `ice_cap` |
| 5 | `elevation_m > 2800.0` and `T < 7.0` | `alpine` |
| 6 | `T < -3.0` **or** `frost_months >= 8` | `tundra` |
| 7 | `aridity >= 0.72` **or** `P <= 180.0`, and `T < 11.0` | `cold_desert` |
| 8 | `aridity >= 0.72` **or** `P <= 180.0`, and `T >= 11.0` | `hot_desert` |
| 9 | `T > 23.0` and `P > 1900.0` and `growing_season_months >= 10` | `tropical_rainforest` |
| 10 | `T > 20.0` and `P > 850.0` and `aridity < 0.45` | `tropical_seasonal_forest` |
| 11 | `T > 20.0` and `P > 850.0` and `aridity >= 0.45` | `savanna` |
| 12 | `T > 17.0` and `aridity >= 0.45` | `savanna` |
| 13 | `T > 8.0` and `P > 700.0` | `temperate_forest` |
| 14 | `T > 5.0` and `aridity < 0.62` | `temperate_grassland` |
| 15 | `T > -1.0` and `P > 420.0` | `boreal_forest` |
| 16 | else, `aridity >= 0.45` | `cold_desert` |
| 17 | else | `tundra` |

Consequences that are visible in every generated world:

- The shadow classifier can never return `wetland` or `mediterranean_scrub`. Every native `wetland` cell therefore has `matches == False`, `biome_transition_zone == True` and a confidence base of `0.30` rather than `0.58`.
- Rule 4 reads the *native* `biome`, so the shadow is not fully independent for ice caps.
- Native lakes are `is_water == false`, so rules 1–3 do not apply to them and a lake cell is scored against the land envelope. A native `lake`-biome cell is therefore almost always a mismatch.
- The thresholds do not match the native cascade (`P > 2100` vs. `P > 1900 + growing >= 10` for rainforest; `T >= 11` vs. `T < 11` desert split against different aridity definitions). `biome_expected_match_fraction` is therefore a cross-model agreement statistic, not a self-consistency check.

### Limiting factor

`_limiting_factor` (`biome_dynamics.py:65-86`), first match wins, recorded as `biome_diagnostics[].limiting_factor` and histogrammed into `summary.biome_limiting_factor_counts`:

| Order | Predicate | `limiting_factor` |
|---|---|---|
| 1 | `is_water` | `water_body` |
| 2 | `ice_thickness_m > 120.0` | `persistent_ice` |
| 3 | `frost_months >= 8` or `T < -3.0` | `cold` |
| 4 | `annual_deficit / max(1, annual_pet) >= 0.65` | `water_deficit` |
| 5 | `growing_season_months <= 3` | `short_growing_season` |
| 6 | `soil_moisture_index >= 0.78` | `waterlogging` |
| 7 | `elevation_m > 2800.0` | `elevation` |
| 8 | else | `balanced` |

---

## Ecotone detection

`src/magic_geo/biome_ecotones.py` identifies named transitional habitats and groups them into contiguous regions. Module constants:

| Constant | Value | Source |
|---|---|---|
| `ECOTONE_THRESHOLD` | `0.52` | `biome_ecotones.py:7` |
| `MARINE_WATER_TYPES` | `{"ocean", "continental_shelf", "inland_sea"}` | `biome_ecotones.py:8` |

### Eligibility

`_score_ecotones` (`biome_ecotones.py:49-161`) returns an **empty score dict** — which `_select_ecotone` maps to `("none", 0.0)` — when either:

| Exclusion | Source |
|---|---|
| `is_water` is true | `biome_ecotones.py:50-51` |
| `biome == "ice_cap"` or `ice_thickness_m > 80.0` | `biome_ecotones.py:55-56` |

### Neighbourhood predicates

| Predicate | Definition | Source |
|---|---|---|
| `coastal` | not `is_water` and some neighbour has `water_body_type` in `MARINE_WATER_TYPES` | `biome_ecotones.py:21-33` |
| `freshwater` | some neighbour has `water_body_type` in `{"fresh_lake", "lake"}` **or** `is_river` | `biome_ecotones.py:36-46` |

`"lake"` is not a member of `WATER_BODY_NAMES`; only `"fresh_lake"` and `is_river` can match in practice. `saline_basin` neighbours deliberately do not count as freshwater.

### Hard gates

Three ecotone types are gated; the other six are scored unconditionally for every eligible land cell.

| Type | Gate (all clauses required) | Source |
|---|---|---|
| `mangrove` | `coastal` and `T >= 18.0` and `frost_months == 0` and `elevation_m <= 80.0` and (`soil_moisture_index >= 0.58` or `P >= 900.0`) | `biome_ecotones.py:72-74` |
| `cloud_forest` | `650.0 <= elevation_m <= 3300.0` and `7.0 <= T <= 24.0` and `P >= 900.0` and (`wet_season_months >= 6` or `orographic >= 0.30` or `humidity_transport_index >= 0.45`) | `biome_ecotones.py:75-80` |
| `alpine_paramo` | `elevation_m >= 2200.0` and `-2.5 <= T <= 11.0` and `P >= 350.0` and `1 <= frost_months <= 9` and `ice_thickness_m <= 80.0` | `biome_ecotones.py:81-87` |
| `dry_forest`, `mediterranean_scrub`, `swamp`, `taiga`, `cold_steppe`, `cold_desert` | none — always scored | `biome_ecotones.py:115-160` |

Where `orographic = clamp((orographic_factor - 0.9) / 0.55)` (`biome_ecotones.py:66`), `lowland = 1 - clamp(max(0, elevation_m) / 350.0)` (`:70`), `highland = clamp((elevation_m - 700.0) / 2600.0)` (`:71`), and `aridity = clamp(climatic_water_deficit_mm_y / max(1, potential_evapotranspiration_mm_y))` (`:65`).

### Scoring terms — all nine ecotone types

Every score is a `clamp(...)` of a sum whose **weights total exactly 1.00**, so each score is a convex combination with maximum 1.0.

| Type | Terms (weight × factor) | Source |
|---|---|---|
| `mangrove` | `0.30 × coastal` + `0.20 × clamp((T-17)/12)` + `0.14 × (frost_months == 0)` + `0.18 × soil_moisture` + `0.10 × clamp(P/1800)` + `0.08 × lowland` | `biome_ecotones.py:90-97` |
| `cloud_forest` | `0.25 × clamp((P-850)/1600)` + `0.18 × clamp(1-abs(T-15)/11)` + `0.18 × clamp((E-800)/1800)` + `0.08 × clamp((2800-E)/1700)` + `0.14 × orographic` + `0.10 × humidity_transport` + `0.07 × clamp(wet_months/12)` | `biome_ecotones.py:98-106` |
| `alpine_paramo` | `0.30 × clamp((E-2600)/1800)` + `0.22 × clamp(1-abs(T-4)/9)` + `0.12 × clamp((P-450)/1200)` + `0.14 × clamp((8-abs(frost_months-4))/8)` + `0.12 × (biome ∈ {alpine, tundra, temperate_grassland})` + `0.10 × highland` | `biome_ecotones.py:107-114` |
| `dry_forest` | `0.18 × clamp((T-17)/10)` + `0.20 × clamp((P-450)/900)` + `0.12 × clamp((1400-P)/900)` + `0.20 × clamp(dry_months/7)` + `0.12 × clamp(wet_months/8)` + `0.18 × ("forest" in biome)` | `biome_ecotones.py:115-122` |
| `mediterranean_scrub` | `0.18 × clamp(1-abs(T-14)/12)` + `0.22 × clamp((dry_months-2)/6)` + `0.16 × clamp((P-280)/650)` + `0.12 × clamp((1100-P)/700)` + `0.14 × seasonal_aridity` + `0.18 × (biome ∈ {mediterranean_scrub, temperate_grassland, temperate_forest})` | `biome_ecotones.py:123-130` |
| `swamp` | `0.30 × soil_moisture` + `0.18 × freshwater` + `0.18 × (biome == wetland)` + `0.14 × clamp(wet_months/10)` + `0.10 × clamp(P/1600)` + `0.10 × lowland` | `biome_ecotones.py:131-138` |
| `taiga` | `0.26 × clamp(1-abs(T-1.5)/7.5)` + `0.16 × clamp((P-280)/800)` + `0.20 × clamp((frost_months-3)/6)` + `0.24 × (biome == boreal_forest)` + `0.14 × clamp((abs(lat_deg)-40)/32)` | `biome_ecotones.py:139-145` |
| `cold_steppe` | `0.20 × clamp(1-abs(T-2)/10)` + `0.18 × clamp((P-140)/520)` + `0.14 × clamp((620-P)/520)` + `0.16 × aridity` + `0.14 × clamp((frost_months-2)/7)` + `0.18 × (biome ∈ {temperate_grassland, cold_desert, tundra})` | `biome_ecotones.py:146-153` |
| `cold_desert` | `0.22 × clamp((8-T)/15)` + `0.28 × clamp((260-P)/260)` + `0.20 × aridity` + `0.12 × clamp(frost_months/9)` + `0.18 × (biome == cold_desert)` | `biome_ecotones.py:154-160` |

### Selection and region assembly

`_select_ecotone` (`biome_ecotones.py:164-170`) sorts by `(-score, name)` — a deterministic alphabetical tie-break — takes the best, and returns `("none", score)` if that best score is below `0.52`. Note that in the `"none"` case, `biome_ecotone_confidence` still records the *sub-threshold best score*, not zero.

Regions are then built by iterating `sorted(candidate_ids_by_type.items())` and, within each type, running a BFS over the neighbour graph restricted to cells whose `biome_ecotone_type` equals that type (`biome_ecotones.py:173-202`). Component seeds are `min(remaining)`, and member lists are sorted, so region ids are fully deterministic. Every ecotone cell belongs to exactly one region; non-ecotone cells keep `biome_ecotone_region_id = -1`.

---

## Ecosystem dynamics

`src/magic_geo/ecosystem_dynamics.py` derives net primary productivity, standing biomass, species richness, disturbance pressure, a four-phase succession trajectory, and renewable-resource records.

### Biome group constants

| Constant | Members | Source |
|---|---|---|
| `FOREST_BIOMES` | `tropical_rainforest`, `tropical_seasonal_forest`, `temperate_forest`, `boreal_forest` | `ecosystem_dynamics.py:7` |
| `GRASSLAND_BIOMES` | `savanna`, `temperate_grassland`, `mediterranean_scrub` | `ecosystem_dynamics.py:8` |
| `BARREN_BIOMES` | `ice_cap`, `tundra`, `alpine`, `hot_desert`, `cold_desert` | `ecosystem_dynamics.py:9` |
| `FISHERY_WATER_TYPES` | `ocean`, `continental_shelf`, `fresh_lake`, `inland_sea` (**not** `saline_basin`) | `ecosystem_dynamics.py:10` |

### State variables

| Variable | Branch | Formula | Source |
|---|---|---|---|
| `primary_productivity_index` | marine (`is_water`) | `clamp(0.12 + shelf_bonus + temp_suitability*0.24 + nutrient*0.22 + current*0.12)` where `shelf_bonus` = `0.20` (continental_shelf) / `0.12` (fresh_lake, inland_sea) / `0.04` (else), `nutrient = clamp(runoff_mm_y/900)`, `current = clamp(abs(ocean_current_temperature_c)/4.5)` | `ecosystem_dynamics.py:31-35` |
| `primary_productivity_index` | land (incl. lakes) | `clamp(temp_suitability*0.26 + water_balance*0.22 + soil_moisture*0.18 + fertility*0.18 + growing*0.18 - seasonal_aridity*0.14 - ice*0.18)` where `water_balance = clamp(P/PET)`, `growing = clamp(growing_season_months/12)`, `ice = clamp(ice_thickness_m/1200)` | `ecosystem_dynamics.py:36-38` |
| `temp_suitability` | all | `clamp(1 - abs(T - 18.0)/34.0)` | `ecosystem_dynamics.py:17-18` |
| `vegetation_biomass_index` | marine | `0.0` | `ecosystem_dynamics.py:42-43` |
| `vegetation_biomass_index` | land | `clamp(NPP*0.52 + organic*0.18 + soil_moisture*0.14 + biome_bonus - ice*0.22)`, `biome_bonus` = `+0.28` forest / `+0.13` grassland / `-0.16` barren / `+0.02` otherwise | `ecosystem_dynamics.py:44-49` |
| `wildfire_spread_risk_index` | marine | `0.0` | `ecosystem_dynamics.py:59` |
| `wildfire_spread_risk_index` | land | `clamp(fire_frequency_index*0.38 + biomass*0.22 + seasonal_aridity*0.22 + wind*0.10)`, `wind = clamp(hypot(wind_east, wind_north))` | `ecosystem_dynamics.py:53-59` |
| `ecosystem_disturbance_pressure_index` | all | `clamp(wildfire_spread*0.42 + ecotone_index*0.16 + erosion*0.14 + settlement_score*0.16 + seasonal_aridity*0.12)`, `erosion = clamp(abs(erosion_rate)/0.08)` | `ecosystem_dynamics.py:52-61` |
| `species_richness_index` | all | `clamp(NPP*0.34 + biomass*0.22 + ecotone_index*0.18 + temp_suitability*0.16 + soil_moisture*0.10)` | `ecosystem_dynamics.py:158` |
| `forest_growth_index` | forest biomes or `"forest" in biome` | `clamp(NPP*0.44 + biomass*0.28 + soil_moisture*0.14 + fertility*0.12 - disturbance*0.16)` | `ecosystem_dynamics.py:91-97` |
| `forest_growth_index` | grassland biomes | `clamp(NPP*0.20 + biomass*0.12)` | `ecosystem_dynamics.py:94` |
| `forest_growth_index` | anything else | `0.0` | `ecosystem_dynamics.py:94` |
| `fishery_productivity_index` | `water_body_type ∈ FISHERY_WATER_TYPES` | `clamp(shelf + NPP*0.34 + runoff_nutrient*0.20 + current_mixing*0.14 + temperature*0.12)`, `shelf` = `0.30`/`0.18`/`0.08`, `temperature = clamp(1 - abs(T-12)/32)` | `ecosystem_dynamics.py:80-88` |
| `fishery_productivity_index` | else | `0.0` | `ecosystem_dynamics.py:82-83` |
| `vegetation_recovery_years` | all | `int(round(4 + (1-NPP)*46 + disturbance*34 + (1-biomass)*18))` — range `[4, 102]` | `ecosystem_dynamics.py:161` |

`settlement_score` is read with a `0.0` default. In geo-only mode it is stripped from every cell by `_strip_native_civilization_outputs`, so the disturbance term contributed by human presence is exactly zero.

### Succession stage

`_succession_stage` (`ecosystem_dynamics.py:64-77`), first match wins:

| Order | Predicate | `vegetation_succession_stage` |
|---|---|---|
| 1 | `is_water` | `aquatic_primary_productivity` |
| 2 | `biome == "ice_cap"` or `ice_thickness_m > 120.0` | `barren_ice` |
| 3 | `biomass < 0.08` or `productivity < 0.12` | `pioneer_sparse_cover` |
| 4 | `disturbance >= 0.58` | `disturbance_mosaic` |
| 5 | `forest_growth >= 0.62` and `biomass >= 0.62` | `mature_closed_canopy` |
| 6 | `biomass >= 0.44` | `mid_successional_cover` |
| 7 | else | `early_successional_cover` |

### Succession trajectory

A history is emitted only when the cell is **not** `is_water`, its stage is **not** in `{barren_ice, pioneer_sparse_cover}`, and `biomass > 0.06` (`ecosystem_dynamics.py:185`). The trajectory is a fixed four-phase sequence (`ecosystem_dynamics.py:108`):

| index | `phase` | `years_since_start` |
|---|---|---|
| 0 | `establishment` | 0 |
| 1 | `canopy_building` | 25 |
| 2 | `mature_state` | 60 |
| 3 | `disturbance_recovery` | 90 |

With `progress = index / 3` and `start_biomass = clamp(biomass * (0.38 + (1-disturbance)*0.26))` (`ecosystem_dynamics.py:109`):

```
step_biomass      = clamp(start_biomass + (biomass - start_biomass)*progress
                          + NPP*0.04*index - disturbance*0.025*index)
step_disturbance  = clamp(disturbance * (1 - progress*0.18)
                          + wildfire * (0.08 if phase == "disturbance_recovery" else 0.0))
canopy_closure    = clamp(step_biomass * (0.50 + forest_growth*0.42))
recovery_fraction = clamp(progress * (1 - step_disturbance*0.38))
succession_stage  = _succession_stage(cell, step_biomass, NPP, step_disturbance, forest_growth)
```

The `years_since_start` values are **nominal integers with no calibrated relation to simulation time**; the world's nominal-time ledgers do not cover this enricher.

### Renewable resource records

`ecosystem_dynamics.py:204-241`:

| Condition | `resource_type` | `productivity_index` |
|---|---|---|
| `forest_growth >= 0.25` | `forest_growth` | `forest_growth` |
| `fishery >= 0.35` **and** `fishery >= productivity` (evaluated second, overrides) | `fishery_productivity` | `fishery` |
| neither | no record emitted | — |

`sustainable_yield_index = clamp(productivity*0.56 + NPP*0.20 + biomass*0.14 - disturbance*0.18)`; `regeneration_years = max(1, round(recovery_years * 0.35))` for fisheries and `max(1, round(recovery_years))` for forests. The `forest_record_count -= 1` compensation at `ecosystem_dynamics.py:215` handles the case where both conditions fire for one cell. That path is defensive rather than reachable in a standard world: every `water_body_type` in `FISHERY_WATER_TYPES` implies a biome of `ocean`, `continental_shelf`, `lake` or (for a river-crossed lake cell) `wetland`, none of which is in `FOREST_BIOMES` or `GRASSLAND_BIOMES` and none of which contains the substring `forest`, so `_forest_growth` returns `0.0` on exactly the cells that can produce a fishery record.

---

## Species range modelling

`src/magic_geo/species_ranges.py` scores a fixed set of ten guilds per cell, flood-fills contiguous above-threshold cells into range records, and back-annotates the cells.

| Constant | Value | Source |
|---|---|---|
| `SPECIES_RANGE_THRESHOLD` | `0.46` | `species_ranges.py:14` |
| dominant-guild floor | `0.25` (below it, `dominant_species_guild = "none"`) | `species_ranges.py:315-316` |
| `FOREST_BIOMES` / `GRASSLAND_BIOMES` / `DESERT_BIOMES` / `ALPINE_BIOMES` | see below | `species_ranges.py:8-11` |
| `FRESHWATER_TYPES` | `fresh_lake`, `inland_sea` | `species_ranges.py:12` |
| `MARINE_TYPES` | `ocean`, `continental_shelf` | `species_ranges.py:13` |

`ALPINE_BIOMES` is `{tundra, alpine, ice_cap}`; `DESERT_BIOMES` is `{hot_desert, cold_desert}`.

### Guild table

`GUILD_METADATA` (`species_ranges.py:16-27`) fixes the habitat class and trophic role. `non_water_gate` is `0.0` when `is_water` and `1.0` otherwise, applied as a multiplier.

| Guild | `habitat_class` | `trophic_role` | Water gate | Scoring terms | Source |
|---|---|---|---|---|---|
| `canopy_tree` | `terrestrial` | `primary_producer` | yes | `forest_bonus(0.24)` + `NPP*0.24` + `biomass*0.28` + `forest_growth*0.20` + `moisture*0.12` + `temp_temperate*0.10` − `disturbance*0.14` − `aridity*0.08` − `ice*0.26` | `species_ranges.py:142-153` |
| `grassland_grazer` | `terrestrial` | `herbivore` | yes | `grass_bonus(0.24)` + `NPP*0.24` + `richness*0.16` + `clamp(1-abs(aridity-0.45)/0.45)*0.18` + `temp_temperate*0.12` + `clamp(1-biomass)*0.08` − `disturbance*0.10` − `ice*0.22` | `species_ranges.py:154-164` |
| `desert_specialist` | `arid` | `specialist_consumer` | yes | `desert_bonus(0.30)` + `aridity*0.28` + `clamp(1-moisture)*0.16` + `clamp(1-P/420)*0.14` + `richness*0.10` − `ice*0.22` − `wetland*0.24` | `species_ranges.py:165-174` |
| `alpine_tundra_specialist` | `alpine` | `specialist_consumer` | yes | `alpine_bonus(0.28)` + `temp_cold*0.22` + `clamp((E-1200)/2600)*0.18` + `permafrost*0.18` + `richness*0.12` − `ice*0.18` | `species_ranges.py:175-183` |
| `wetland_amphibian` | `wetland` | `secondary_consumer` | no | `wetland*0.34` + `wetland_hydrology*0.18` + `moisture*0.12` + `richness*0.14` + `temp_warm*0.10` + `freshwater_bonus*0.18` − `aridity*0.10` | `species_ranges.py:184-192` |
| `large_predator` | `terrestrial` | `apex_predator` | yes | `richness*0.28` + `biomass*0.24` + `NPP*0.18` + `clamp(1-disturbance)*0.18` + `forest_bonus*0.10` + `grass_bonus*0.10` − `ice*0.26` | `species_ranges.py:193-202` |
| `freshwater_fish` | `freshwater` | `aquatic_consumer` | no | `freshwater_bonus` + `fishery*0.30` + `NPP*0.12` + `river_channel*0.14` + `river_depth*0.12` + `temp_window(T,14,24)*0.10` − `ice*0.22` | `species_ranges.py:203-211` |
| `marine_fish` | `marine` | `aquatic_consumer` | no | `marine_bonus(0.30)` + `fishery*0.42` + `NPP*0.14` + `temp_window(T,13,24)*0.10` + `0.08` if `continental_shelf` − `ice*0.18` | `species_ranges.py:212-219` |
| `reef_builder` | `reef` | `foundation_species` | no | `reef_bonus(0.34)` + `reef_growth*0.54` + `fishery*0.10` + `temp_warm*0.08` − `ice*0.22` | `species_ranges.py:220` |
| `mangrove_coastal_bird` | `wetland` | `mobile_consumer` | no | `mangrove_bonus(0.34)` + `wetland*0.22` + `coastal*0.14` + `richness*0.12` + `temp_warm*0.12` + `clamp(P/1600)*0.10` − `disturbance*0.08` | `species_ranges.py:221-229` |

Bonus and window definitions (`species_ranges.py:126-138`):

| Symbol | Definition |
|---|---|
| `temp_temperate` | `clamp(1 - abs(T - 18.0)/24.0)` |
| `temp_warm` | `clamp(1 - abs(T - 25.0)/14.0)` |
| `temp_cold` | `clamp((8.0 - T)/22.0)` |
| `coastal` | `clamp(1 - distance_to_marine_water_km / 80.0)` (default distance `9999.0`) |
| `ice` | `clamp(ice_thickness_m / 800.0)` |
| `river_channel` / `river_depth` | `clamp(river_channel_width_m / 180.0)` / `clamp(river_channel_depth_m / 9.0)` |
| `freshwater_bonus` | `0.30` if `water_body_type ∈ FRESHWATER_TYPES` else `0.22` if `is_river` else `0.0` |
| `reef_bonus` | `0.34` if `reef_type != "none"` |
| `mangrove_bonus` | `0.34` if `biome_ecotone_type == "mangrove"` or `wetland_system_type == "mangrove"` |

### Endemism and confidence

`_cell_endemism` (`species_ranges.py:234-259`):

```
same_biome_fraction = |neighbours with same biome| / |neighbours|   (0.0 if no neighbours)
island_score        = {islet: 0.42, island: 0.34, large_island: 0.24, continental_island: 0.16}
                      .get(island_class, 0.0)
species_endemism_index = clamp(island_score
                             + 0.22 if biome_ecotone_type != "none" else 0
                             + clamp(reef_growth_index)*0.16
                             + clamp(wetland_extent_index)*0.12
                             + clamp((elevation_m - 1500)/3000)*0.14
                             + clamp(1 - same_biome_fraction)*0.24
                             - clamp(disturbance)*0.10)
```

`sea_level_diagnostics._landmass_class` (`src/magic_geo/sea_level_diagnostics.py:85-92`) can only produce `continent`, `large_island`, `island` or `islet` (plus `water` / `unassigned` sentinels at `:309`), so the `continental_island` entry and the `"mainland"` default key in the endemism map are **dead** — `continent` cells receive `island_score = 0.0`.

`_cell_confidence` (`species_ranges.py:262-268`):
`clamp(biome_confidence_index*0.30 + richness*0.22 + NPP*0.20 + max(wetland_extent, reef_growth)*0.12 + (1-disturbance)*0.16)`.

### Range assembly

For each guild in `sorted(GUILD_METADATA)`, cells scoring `>= 0.46` are flood-filled into connected components over the raw neighbour graph (`species_ranges.py:44-63`); because `remaining` only ever contains that guild's candidates, the BFS is implicitly guild-restricted. Records are appended in `(guild, component)` order so ids are deterministic.

Cells accumulate **all** the range ids they belong to (`species_range_record_ids`), so ranges legitimately overlap: a cell can be in a `canopy_tree` range and a `large_predator` range simultaneously. After all records exist, each member cell's `species_range_fragmentation_index` is set to the **maximum** fragmentation over the ranges it belongs to (`species_ranges.py:416-425`).

`_range_fragmentation` (`species_ranges.py:90-101`): `clamp(external_edge_fraction*0.72 + (1/max(1,|component|))*0.28)` where `external_edge_fraction = |edges leaving the component| / |all incident edges|`.

Record-level endemism and stress (`species_ranges.py:356-358`):

```
small_range_bonus = clamp((800000.0 - area_km2) / 800000.0) * 0.18
endemism_index    = clamp(mean_cell_endemism*0.72 + fragmentation*0.18 + small_range_bonus)
conservation_stress_index = clamp(mean_disturbance*0.38 + fragmentation*0.22
                                + (1 - mean_confidence)*0.22 + endemism_index*0.18)
```

`high_endemism_species_range_count` counts `endemism_index >= 0.60`; `high_conservation_stress_species_range_count` counts `conservation_stress_index >= 0.60`.

---

## Wildfire disturbance

`src/magic_geo/wildfire_disturbance.py` scores burnability per cell, then propagates a bounded number of wind-aligned spread events.

| Constant | Value | Role | Source |
|---|---|---|---|
| `IGNITION_THRESHOLD` | `0.28` | Ignition-candidate cut and `seasonal_surface_fire` regime cut | `wildfire_disturbance.py:8` |
| `SPREAD_THRESHOLD` | `0.30` | Minimum edge probability for a neighbour to burn | `wildfire_disturbance.py:9` |
| `HIGH_FUEL_THRESHOLD` | `0.35` | Crown-fire regime cut and `high_wildfire_fuel_continuity_cell_count` | `wildfire_disturbance.py:10` |
| `HIGH_FIREBREAK_THRESHOLD` | `0.55` | `fragmented_firebreak_mosaic` cut and `high_wildfire_firebreak_cell_count` | `wildfire_disturbance.py:11` |
| `MAX_EVENT_COUNT` | `96` | Maximum spread histories per world | `wildfire_disturbance.py:12` |
| `MAX_SPREAD_STEPS` | `6` | Maximum steps per history (step 0 is the ignition cell) | `wildfire_disturbance.py:13` |
| `MAX_EVENT_CELLS` | `96` | Maximum burned cells per history | `wildfire_disturbance.py:14` |

### Fuel continuity

`_fuel_continuity` (`wildfire_disturbance.py:57-83`) returns `0.0` for `is_water`; otherwise:

```
neighbor_fuel = |neighbours with vegetation_biomass_index >= 0.20| / |neighbours|
fuel = clamp(biomass*0.32 + NPP*0.16 + wildfire_spread_risk*0.20 + seasonal_aridity*0.14
           + neighbor_fuel*0.12
           + 0.10 if "forest" in biome else 0
           + 0.08 if biome in {savanna, temperate_grassland, mediterranean_scrub} else 0
           - wetland_extent_index*0.18
           - clamp(ice_thickness_m/500)*0.34)
```

### Firebreak

`_firebreak` (`wildfire_disturbance.py:86-95`) returns exactly `1.0` for `is_water`; otherwise:

```
water_neighbor_fraction = |water neighbours| / |neighbours|
firebreak = clamp(water_neighbor_fraction*0.34
                + wetland_extent_index*0.24
                + 0.18 if is_river else 0
                + floodplain_connectivity_index*0.12
                + clamp(ice_thickness_m/500)*0.30
                + clamp(1 - fuel)*0.18)
```

### Wind alignment

`_wind_alignment(cell, neighbor)` (`wildfire_disturbance.py:31-54`) builds a unit local tangent direction from the great-circle offset (`east = dlon * cos(mean_lat)` with `dlon` wrapped to `(-π, π]`, `north = dlat`), then returns `clamp((cos θ + 1)/2) * clamp(hypot(wind_east, wind_north))` where `θ` is the angle between the surface wind and that direction. It is `0.0` when the two cells coincide or the wind is zero. The per-cell `wildfire_wind_alignment_index` is the **maximum over all neighbours** (`wildfire_disturbance.py:289`).

### Ignition potential

`_ignition_potential` (`wildfire_disturbance.py:98-117`), `0.0` for `is_water`:

```
ignition = clamp(wildfire_spread_risk_index*0.34
               + fuel*0.28
               + seasonal_aridity_index*0.16
               + ecosystem_disturbance_pressure_index*0.10
               + wind_alignment*0.08
               + settlement_score*0.08
               + clamp(climate_energy_stress_index)*0.06     # lightning proxy
               - firebreak*0.18
               - clamp(ice_thickness_m/500)*0.18)
```

`settlement_score` is absent (default `0.0`) in geo-only worlds, so the anthropogenic ignition term vanishes there and the lightning proxy plus fuel/dryness carry the whole signal.

### Disturbance regime

`_regime` (`wildfire_disturbance.py:120-133`), first match wins:

| Order | Predicate | `wildfire_disturbance_regime` |
|---|---|---|
| 1 | `is_water` | `non_burnable_water` |
| 2 | `biome == "ice_cap"` or `ice_thickness_m > 120.0` | `ice_or_barren_firebreak` |
| 3 | `fuel < 0.12` | `sparse_fuel` |
| 4 | `firebreak >= 0.55` | `fragmented_firebreak_mosaic` |
| 5 | `ignition >= 0.34` and `fuel >= 0.35` and `wind_alignment >= 0.35` | `wind_driven_crown_fire` |
| 6 | `ignition >= 0.28` | `seasonal_surface_fire` |
| 7 | else | `low_fire_activity` |

### Event selection and spread

Candidates (`wildfire_disturbance.py:311-320`) are cells with `wildfire_ignition_potential_index >= 0.28` **and** `wildfire_fuel_continuity_index >= 0.18` **and** regime not in `{non_burnable_water, ice_or_barren_firebreak}`, sorted by `(-ignition, id)`. Events are built greedily until `MAX_EVENT_COUNT` histories exist; a candidate already claimed by an earlier event is skipped, so **histories are pairwise disjoint in their cell sets**.

`_spread_probability(source, target)` (`wildfire_disturbance.py:136-151`) is `0.0` when the target is water or has regime `ice_or_barren_firebreak`; otherwise:

```
p = clamp(target.wildfire_ignition_potential_index * 0.26
        + target.wildfire_fuel_continuity_index    * 0.28
        + _wind_alignment(source, target)          * 0.20
        + source.wildfire_fuel_continuity_index    * 0.08
        + 0.06 if source.biome == target.biome else 0
        + 0.04 if target.elevation_m <= source.elevation_m else 0
        - target.wildfire_firebreak_index          * 0.22)
```

Maximum attainable value is `0.92`.

The propagation loop (`wildfire_disturbance.py:194-236`):

1. Step 0 burns only the ignition cell; `active_ids = {ignition_id}`.
2. Each later step collects every unburned, unclaimed neighbour of the active front, keeps the maximum probability per candidate, discards anything below `0.30`, sorts by `(-probability, id)`, and truncates to `MAX_EVENT_CELLS - |burned|` remaining slots.
3. If nothing qualifies, the loop breaks — so `spread_step_count ∈ [1, 6]`.
4. The new set becomes the active front (the fire advances as a front, it does not re-radiate from the whole burn scar).

Per-step `containment_index = clamp(mean_firebreak_over_newly_burned + (1 - mean_probability)*0.28)`; the history-level `containment_index = clamp(mean_firebreak_over_all_burned*0.62 + (1 - max_probability)*0.20)` (`wildfire_disturbance.py:234`, `:245`).

---

## Biome realism checks

`src/magic_geo/biome_realism.py` emits exactly five records into `world["biome_realism_checks"]`, all with `domain = "biomes"`. Each check computes a fraction `value`, clamps it to `[0,1]`, and scores it with `_score_range` (`biome_realism.py:24-29`):

```
score = 1.0                                          if target_min <= value <= target_max
      = clamp(1.0 - distance / (target_max - target_min))   otherwise
passed = (target_min <= value <= target_max)
```

**Every check returns `value = 1.0` when its population is empty** (`len(...) if ... else 1.0` at `biome_realism.py:136`, `:139`, `:151`, `:165`, `:180`). A world with no deserts passes the desert check vacuously.

| # | `name` | `metric` | Population | Numerator predicate (any clause suffices unless stated) | `target_min` | `target_max` |
|---|---|---|---|---|---|---|
| 0 | `desert_water_deficit_alignment` | `fraction_desert_cells_water_limited` | land cells with `biome ∈ {cold_desert, hot_desert}` | `P <= 320.0` **or** `P/PET <= 0.75` **or** `deficit/PET >= 0.35` **or** (`biome == cold_desert` and `P <= 450.0` and `soil_moisture_index <= 0.32`) | `0.70` | `1.0` |
| 1 | `forest_water_availability_alignment` | `fraction_forest_cells_with_water_available` | land cells with `biome ∈ {boreal_forest, temperate_forest, tropical_rainforest, tropical_seasonal_forest}` | (`P >= 600.0` **or** `climatic_water_surplus_mm_y > 0` **or** `soil_moisture_index >= 0.35`) **and** `deficit/PET <= 0.55` | `0.75` | `1.0` |
| 2 | `tundra_cold_altitude_alignment` | `fraction_tundra_cells_cold_high_or_icy` | land cells with `biome ∈ {tundra, alpine}` | `T <= 2.0` **or** `frost_months >= 6` **or** `elevation_m >= 2200.0` **or** `ice_thickness_m > 20.0` | `0.85` | `1.0` |
| 3 | `savanna_seasonality_alignment` | `fraction_savanna_cells_warm_and_seasonal` | land cells with `biome == savanna` | `T >= 17.0` **and** (`dry_season_months >= 2` **or** `seasonal_aridity_index >= 0.25`) **and** `wet_season_months >= 3` | `0.65` | `1.0` |
| 4 | `mangrove_warm_wet_coast_constraint` | `fraction_mangrove_cells_warm_wet_coastal` | land cells with `biome == "mangrove"` **or** `landform == "mangrove"` **or** `biome_ecotone_type == "mangrove"` | coastal **and** `T >= 18.0` **and** `frost_months == 0` **and** (`P >= 900.0` **or** `soil_moisture_index >= 0.65`) | `0.95` | `1.0` |

Empirical expectations these encode, and their honest scope:

- Check 3 is the one that is *guaranteed* to be near-tautological in a native world: the savanna branch `environment.cpp:364-366` requires `warm_seasonal_climate` (`dry_season_months >= 2` and `wet_season_months >= 3`) computed with the *same* monthly PET expression the diagnostic later re-derives, plus `T > 18.0` against the check's `T >= 17.0`. It measures agreement between two implementations of the same rule, not independent realism. The agreement is not exact, because the native gate reads the in-memory monthly arrays and the diagnostic reads the same arrays after `output.float_precision` rounding — see the PET note under [Biome diagnostics](#biome-diagnostics).
- Check 0 uses `P/PET` at `<= 0.75` where the native gate is `< 0.32`, so it is a genuinely looser envelope than the assignment rule — but it uses the Python PET, not the native PET.
- Check 4 has the highest bar (`0.95`) because there is **no `mangrove` biome and no `mangrove` landform** in the native enums. `BIOME_NAMES` and `LANDFORM_NAMES` (`cpp/src/engine/schema_names.hpp:21-43`) contain no such value, so the population reduces to cells whose *ecotone* type is `mangrove`. The check then re-tests that ecotone gate (`biome_ecotones.py:72-74`) — but **not with the same numbers**: it repeats `coastal`, `T >= 18.0` and `frost_months == 0` verbatim, drops the gate's `elevation_m <= 80.0` clause, and tightens the moisture alternative from `soil_moisture_index >= 0.58` to `>= 0.65`. A cell with `0.58 <= soil_moisture_index < 0.65` and `P < 900.0` therefore passes the gate and fails the check, so the check is near-tautological rather than tautological. `warm_wet_coastal_wetland_proxy_count` in the evidence block is a separate, unused population of warm coastal `wetland` cells kept as context only.
- Check 1's `deficit/PET <= 0.55` combined with `climatic_water_surplus_mm_y > 0` means that any forest cell with even a marginal annual surplus passes, which is a weak constraint.

Each record has the following shape (`biome_realism.py:60-87`):

| Field | Type | Meaning |
|---|---|---|
| `id` | int | 0-based, sequential in emission order |
| `domain` | string | Always `"biomes"` |
| `name` | string | Check identity from the table above |
| `question` | string | Human-readable statement of the hypothesis |
| `metric` | string | Name of the measured fraction |
| `value` | double, 6 dp | Clamped measured fraction |
| `target_min` / `target_max` | double, 6 dp | Acceptance interval |
| `score` | double, 6 dp | `_score_range(value, min, max)` |
| `passed` | bool | `target_min <= value <= target_max` |
| `evidence` | object | Per-check population counts and means (see below) |

| Check | `evidence` keys |
|---|---|
| 0 | `desert_cell_count`, `water_limited_desert_cell_count`, `mean_desert_precipitation_mm_y`, `mean_desert_aridity_ratio` |
| 1 | `forest_cell_count`, `water_available_forest_cell_count`, `mean_forest_precipitation_mm_y`, `mean_forest_soil_moisture_index` |
| 2 | `tundra_cell_count`, `climate_driven_tundra_cell_count`, `mean_tundra_temperature_c`, `mean_tundra_frost_months` |
| 3 | `savanna_cell_count`, `seasonal_savanna_cell_count`, `mean_savanna_dry_season_months`, `mean_savanna_wet_season_months` |
| 4 | `mangrove_cell_count`, `valid_mangrove_cell_count`, `warm_wet_coastal_wetland_proxy_count`, `explicit_mangrove_biome_available`, `explicit_mangrove_ecotone_count` |

---

## Complete emitted-record field tables

All Python-emitted floats on this page are `round(value, 6)` — six decimal places — independent of `output.float_precision`, which governs only native serialization.

### `world["biome_diagnostics"]` — one record per cell (18 fields)

| Field | Type | Definition | Source |
|---|---|---|---|
| `id` | int | Sequential emission index | `biome_dynamics.py:179` |
| `cell_id` | int | `cell["id"]` | `:180` |
| `biome` | string | The native assigned biome | `:181` |
| `expected_biome` | string | `_expected_biome(...)` shadow classification | `:182` |
| `limiting_factor` | string | `_limiting_factor(...)`, one of 8 values | `:183` |
| `potential_evapotranspiration_mm_y` | double | `sum(monthly_pet)` | `:184` |
| `climatic_water_deficit_mm_y` | double | `max(0, PET - P_annual)` | `:185` |
| `climatic_water_surplus_mm_y` | double | `max(0, P_annual - PET)` | `:186` |
| `soil_moisture_index` | double `[0,1]` | Clamped copy of the soil field | `:187` |
| `seasonal_aridity_index` | double `[0,1]` | Clamped copy of the climate field | `:188` |
| `growing_season_months` | int `[0,12]` | `T >= 5` and `P >= pet*0.25` | `:189` |
| `frost_months` | int `[0,12]` | `T < 0` | `:190` |
| `dry_season_months` | int `[0,12]` | `P < pet*0.35` | `:191` |
| `wet_season_months` | int `[0,12]` | `P >= pet*0.75` | `:192` |
| `fire_frequency_index` | double `[0,1]` | See formula above | `:193` |
| `ecotone_index` | double `[0,1]` | Neighbour-diversity convex combination | `:194` |
| `biome_confidence_index` | double `[0,1]` | Match + margin blend | `:195` |
| `biome_transition_zone` | bool | `ecotone >= 0.55` or not matched | `:196` |

### `world["biome_ecotone_regions"]` (10 fields)

| Field | Type | Definition | Source |
|---|---|---|---|
| `id` | int | Sequential, assigned in `(type, component)` order | `biome_ecotones.py:243` |
| `ecotone_type` | string | One of the 9 named types | `:244` |
| `cell_count` | int | `len(component)` | `:245` |
| `cell_ids` | int[] | Ascending member cell ids | `:246` |
| `area_km2` | double | `sum(max(0, area_km2))` over members | `:247` |
| `mean_ecotone_confidence` | double `[0,1]` | Mean `biome_ecotone_confidence` | `:248` |
| `dominant_biome` | string | Modal `biome`, ties broken alphabetically | `:249` |
| `mean_temperature_c` | double | Mean `temperature_c` | `:250` |
| `mean_precipitation_mm_y` | double | Mean `precipitation_mm_y` | `:251` |
| `coastal_cell_count` | int | Members satisfying `_is_coastal_land` | `:252` |

### `world["vegetation_succession_histories"]` (12 fields + nested `steps[]`)

| Field | Type | Definition | Source |
|---|---|---|---|
| `id` | int | Sequential | `ecosystem_dynamics.py:189` |
| `cell_id` | int | Source cell | `:190` |
| `biome` | string | Native biome of the cell | `:191` |
| `initial_succession_stage` | string | `steps[0].succession_stage` | `:192` |
| `final_succession_stage` | string | `steps[-1].succession_stage` | `:193` |
| `step_count` | int | Always `4` | `:194` |
| `recovery_years` | int `[4,102]` | `vegetation_recovery_years` | `:195` |
| `mean_biomass_index` | double `[0,1]` | Mean over steps | `:196` |
| `mean_canopy_closure_index` | double `[0,1]` | Mean over steps | `:197` |
| `mean_disturbance_pressure_index` | double `[0,1]` | Mean over steps | `:198` |
| `max_wildfire_spread_risk_index` | double `[0,1]` | Max over steps (constant across steps) | `:199` |
| `steps` | object[] | 4 step records | `:200` |

`steps[]` (9 fields, `ecosystem_dynamics.py:118-128`): `phase`, `years_since_start`, `succession_stage`, `biomass_index`, `canopy_closure_index`, `primary_productivity_index`, `disturbance_pressure_index`, `wildfire_spread_risk_index`, `recovery_fraction`.

### `world["renewable_resource_records"]` (12 fields + nested `formation_evidence`)

| Field | Type | Definition | Source |
|---|---|---|---|
| `id` | int | Sequential | `ecosystem_dynamics.py:221` |
| `cell_id` | int | Source cell | `:222` |
| `resource_type` | string | `forest_growth` or `fishery_productivity` | `:223` |
| `biome` | string | Native biome | `:224` |
| `water_body_type` | string | Native water-body class | `:225` |
| `productivity_index` | double `[0,1]` | Winning index | `:226` |
| `sustainable_yield_index` | double `[0,1]` | Yield blend | `:227` |
| `regeneration_years` | int `>= 1` | `recovery_years × 0.35` for fisheries, `×1.0` for forests | `:228` |
| `climate_dependency_index` | double `[0,1]` | `clamp(1 - temp_suitability + seasonal_aridity*0.35)` | `:229` |
| `water_dependency_index` | double `[0,1]` | `clamp(soil_moisture*0.45 + groundwater_recharge_mm_y/450*0.35 + 0.30 if is_water)` | `:230` |
| `disturbance_risk_index` | double `[0,1]` | `ecosystem_disturbance_pressure_index` | `:231` |
| `formation_evidence` | object | 6 keys: `primary_productivity_index`, `vegetation_biomass_index`, `forest_growth_index`, `fishery_productivity_index`, `runoff_mm_y`, `soil_moisture_index` | `:232-239` |

### `world["species_range_records"]` (29 fields)

| Field | Type | Definition | Source |
|---|---|---|---|
| `id` | int | Sequential in `(guild, component)` order | `species_ranges.py:367` |
| `guild_type` | string | One of the 10 guilds | `:368` |
| `habitat_class` | string | `terrestrial`/`arid`/`alpine`/`wetland`/`freshwater`/`marine`/`reef` | `:369` |
| `trophic_role` | string | From `GUILD_METADATA` | `:370` |
| `cell_count` | int | `len(component)` | `:371` |
| `cell_ids` | int[] | Ascending member cell ids | `:372` |
| `area_km2` | double | Sum of member areas | `:373` |
| `centroid_lat_deg` / `centroid_lon_deg` | double | Area-weighted 3-D unit-vector centroid projected back to lat/lon | `:374-375`, `:66-87` |
| `dominant_biome` | string | Modal `biome`, alphabetical tie-break | `:376` |
| `dominant_ecotone_type` | string | Modal `biome_ecotone_type` | `:377` |
| `dominant_water_body_type` | string | Modal `water_body_type` | `:378` |
| `mean_habitat_suitability_index` | double `[0,1]` | Mean of this guild's per-cell score | `:379-382` |
| `max_habitat_suitability_index` | double `[0,1]` | Max of this guild's per-cell score | `:383-386` |
| `mean_species_richness_index` | double `[0,1]` | Mean cell richness | `:387` |
| `mean_primary_productivity_index` | double `[0,1]` | Mean cell NPP | `:388` |
| `mean_disturbance_pressure_index` | double `[0,1]` | Mean cell disturbance | `:389` |
| `mean_composition_confidence_index` | double `[0,1]` | Mean cell confidence | `:390` |
| `mean_temperature_c` | double | Mean member temperature | `:391` |
| `mean_precipitation_mm_y` | double | Mean member precipitation (clamped at 0 per cell) | `:392` |
| `range_fragmentation_index` | double `[0,1]` | Edge-leakage + small-range blend | `:393` |
| `endemism_index` | double `[0,1]` | Record-level endemism | `:394` |
| `conservation_stress_index` | double `[0,1]` | Stress blend | `:395` |
| `climate_envelope` | object | 6 keys: `min/mean/max_temperature_c`, `min/mean/max_precipitation_mm_y` | `:396-403` |
| `habitat_evidence` | object | 7 keys: `mean_wetland_extent_index`, `mean_reef_growth_index`, `mean_fishery_productivity_index`, `mean_forest_growth_index`, `river_cell_fraction`, `water_cell_fraction`, `coastal_cell_fraction` (`distance_to_marine_water_km <= 80`) | `:281-294`, `:404` |
| `wetland_system_ids` | int[] | Sorted distinct non-negative `wetland_system_id` | `:405` |
| `reef_system_ids` | int[] | Sorted distinct non-negative `reef_system_id` | `:406` |
| `aquifer_system_ids` | int[] | Sorted distinct non-negative `aquifer_system_id` | `:407` |
| `river_basin_ids` | int[] | Sorted distinct non-negative `basin_id` | `:408` |

### `world["wildfire_spread_histories"]` (20 fields + nested `steps[]`)

| Field | Type | Definition | Source |
|---|---|---|---|
| `id` | int | Sequential | `wildfire_disturbance.py:247` |
| `ignition_cell_id` | int | Seed cell (always a member of `cell_ids`) | `:248` |
| `cell_count` | int | Burned cells | `:249` |
| `cell_ids` | int[] | Ascending burned cell ids | `:250` |
| `area_km2` | double | Sum of burned areas | `:251` |
| `centroid_lat_deg` / `centroid_lon_deg` | double | Area-weighted spherical centroid | `:252-253` |
| `dominant_biome` | string | Modal burned biome | `:254` |
| `dominant_disturbance_regime` | string | Modal burned regime | `:255` |
| `mean_wildfire_spread_risk_index` | double `[0,1]` | Mean over burned cells | `:256` |
| `mean_ignition_potential_index` | double `[0,1]` | Mean over burned cells | `:257` |
| `mean_fuel_continuity_index` | double `[0,1]` | Mean over burned cells | `:258` |
| `mean_wind_alignment_index` | double `[0,1]` | Mean over burned cells | `:259` |
| `mean_firebreak_index` | double `[0,1]` | Mean over burned cells | `:260` |
| `mean_ecosystem_disturbance_pressure_index` | double `[0,1]` | Mean over burned cells | `:261` |
| `max_spread_probability_index` | double `[0,1]` | Max recorded per-cell arrival probability | `:262` |
| `containment_index` | double `[0,1]` | `clamp(mean_firebreak*0.62 + (1-max_p)*0.20)` | `:263` |
| `spread_step_count` | int `[1,6]` | `len(steps)` | `:264` |
| `steps` | object[] | Step records | `:265` |
| `disturbance_regime_counts` | object | Sorted histogram of burned-cell regimes | `:266` |

`steps[]` (7 fields, `wildfire_disturbance.py:227-235`): `step_index`, `newly_burned_cell_ids`, `active_front_cell_ids`, `cumulative_burned_cell_count`, `burned_area_km2`, `mean_spread_probability_index`, `containment_index`.

---

## Per-cell field inventory

### Native fields written by `derive_soils_biomes_resources` / `derive_landforms`

| Cell field | Type | Serialized precision | Written at |
|---|---|---|---|
| `soil_type` | enum string, `SOIL_NAMES` (11) | string | `environment.cpp:328`, `:343`, `:347`–`:388`, `:477`–`:498` |
| `soil_depth_m` | double | `float_precision` | `environment.cpp:329`, `:338` |
| `fertility` | double `[0,1]` | `max(8, float_precision)` | `environment.cpp:330`, `:339`, `:478` |
| `biome` | enum string, `BIOME_NAMES` (16) | string | `environment.cpp:331`, `:344`–`:385`, `:480` |
| `resource` | enum string, `RESOURCE_NAMES` (9) | string | `environment.cpp:332`, `:390`–`:403`, `:483`, `:489`, `:494` |
| `settlement_score` | double `[0,1]` | `max(8, float_precision)` | `environment.cpp:333`, `:410`–`:412`, `:485`–`:502` |
| `landform` | enum string, `LANDFORM_NAMES` (20) | string | `environment.cpp:430`–`:474` |
| `water_body` | enum string, `WATER_BODY_NAMES` (6) | string | may be re-stamped for lakes at `environment.cpp:342` |

Serialization order and precision are set in `cells_json` (`cpp/src/engine/entity_serialization.cpp:110`); `biome` is emitted at `entity_serialization.cpp:342`.

### Python-added cell fields (36 total)

| Producer | Cell fields |
|---|---|
| `biome_dynamics` (11) | `potential_evapotranspiration_mm_y`, `climatic_water_deficit_mm_y`, `climatic_water_surplus_mm_y`, `growing_season_months`, `frost_months`, `dry_season_months`, `wet_season_months`, `fire_frequency_index`, `biome_confidence_index`, `ecotone_index`, `biome_transition_zone` |
| `biome_ecotones` (3) | `biome_ecotone_type`, `biome_ecotone_confidence`, `biome_ecotone_region_id` |
| `biome_realism` (0) | — writes no cell fields |
| `ecosystem_dynamics` (9) | `primary_productivity_index`, `vegetation_biomass_index`, `species_richness_index`, `wildfire_spread_risk_index`, `ecosystem_disturbance_pressure_index`, `vegetation_succession_stage`, `vegetation_recovery_years`, `forest_growth_index`, `fishery_productivity_index` |
| `species_ranges` (7) | `dominant_species_guild`, `species_habitat_suitability_index`, `species_endemism_index`, `species_range_fragmentation_index`, `species_composition_confidence_index`, `species_guild_richness_count`, `species_range_record_ids` |
| `wildfire_disturbance` (6) | `wildfire_ignition_potential_index`, `wildfire_fuel_continuity_index`, `wildfire_wind_alignment_index`, `wildfire_firebreak_index`, `wildfire_disturbance_regime`, `wildfire_spread_history_ids` |

All of these are exported by the cell CSV writer (`src/magic_geo/io/cells_csv.py:204-327`).

Two subtleties worth stating explicitly:

- `species_habitat_suitability_index` records the **best guild score**, even when that score is below `0.25` and `dominant_species_guild` was therefore set to `"none"` (`species_ranges.py:314-322`).
- `species_guild_richness_count` counts guilds at or above `0.46` (the range threshold), while `dominant_species_guild` uses the `0.25` floor, so a cell can have `dominant_species_guild != "none"` and `species_guild_richness_count == 0`.

---

## Summary key inventory

All values are `round(..., 6)`. `*_counts` keys are dicts sorted by key.

| Key | Producer | Definition |
|---|---|---|
| `biome_counts` | native `summary.cpp:516`, `:2100` | Sparse histogram over `BIOME_NAMES`, only observed classes |
| `biome_diagnostic_count` | `biome_dynamics.py:203` | `len(biome_diagnostics)` — equals `cell_count` |
| `biome_transition_zone_count` | `:204` | Cells with `biome_transition_zone` |
| `high_fire_frequency_biome_count` | `:205` | Cells with `fire_frequency_index >= 0.65` |
| `water_stressed_biome_cell_fraction` | `:206` | Fraction with `deficit_index >= 0.55` |
| `biome_expected_match_fraction` | `:207` | Fraction where `matches` |
| `mean_potential_evapotranspiration_mm_y` | `:208` | Mean annual PET |
| `mean_climatic_water_deficit_mm_y` | `:209` | Mean annual deficit |
| `mean_growing_season_months` | `:210` | Mean growing months |
| `mean_fire_frequency_index` | `:211` | Mean fire index |
| `mean_biome_confidence_index` | `:212` | Mean confidence |
| `mean_ecotone_index` | `:213` | Mean ecotone index |
| `biome_limiting_factor_counts` | `:214` | Sorted histogram over the 8 limiting factors |
| `biome_ecotone_cell_count` | `biome_ecotones.py:257` | Cells with `biome_ecotone_type != "none"` |
| `biome_ecotone_region_count` | `:258` | `len(biome_ecotone_regions)` |
| `mean_biome_ecotone_confidence` | `:259` | Mean over **all** cells, including `"none"` cells carrying sub-threshold scores |
| `biome_ecotone_type_counts` | `:260` | Sorted histogram including the `"none"` bucket, so it sums to `cell_count` |
| `mangrove_ecotone_cell_count` | `:261` | Count of `mangrove` |
| `cloud_forest_ecotone_cell_count` | `:262` | Count of `cloud_forest` |
| `alpine_paramo_ecotone_cell_count` | `:263` | Count of `alpine_paramo` |
| `desert_water_deficit_alignment_index` | `biome_realism.py:287` | Check 0 `value` |
| `forest_water_availability_index` | `:288` | Check 1 `value` |
| `tundra_cold_altitude_index` | `:289` | Check 2 `value` |
| `savanna_seasonality_index` | `:290` | Check 3 `value` |
| `mangrove_warm_wet_coast_index` | `:291` | Check 4 `value` |
| `biome_realism_check_count` | `:292` | Always `5` |
| `biome_realism_pass_count` | `:293` | Checks with `passed` |
| `biome_realism_pass_fraction` | `:294` | Pass ratio |
| `mean_biome_realism_score` | `:295` | Mean `score` |
| `vegetation_succession_history_count` | `ecosystem_dynamics.py:247` | Number of histories |
| `vegetation_succession_step_count` | `:248` | Total steps (`4 × history count`) |
| `mean_primary_productivity_index` | `:249` | Mean NPP over all cells |
| `mean_vegetation_biomass_index` | `:250` | Mean biomass |
| `mean_species_richness_index` | `:251` | Mean richness |
| `mean_wildfire_spread_risk_index` | `:252` | Mean spread risk |
| `mean_ecosystem_disturbance_pressure_index` | `:253` | Mean disturbance |
| `high_wildfire_spread_risk_cell_count` | `:254` | `wildfire_spread_risk_index >= 0.65` |
| `mature_vegetation_cell_fraction` | `:255` | Fraction with stage `mature_closed_canopy` |
| `mean_forest_growth_index` | `:256` | Mean forest growth |
| `mean_fishery_productivity_index` | `:257` | Mean fishery productivity |
| `renewable_resource_record_count` | `:258` | Number of renewable records |
| `forest_growth_resource_count` | `:259` | Forest records after fishery preemption |
| `fishery_productivity_resource_count` | `:260` | Fishery records |
| `vegetation_succession_stage_counts` | `:261` | Sorted histogram over the 7 stages |
| `renewable_resource_type_counts` | `:262` | Sorted histogram over 2 types |
| `species_range_record_count` | `species_ranges.py:434` | Number of range records |
| `species_range_cell_count` | `:435` | Cells belonging to ≥1 range |
| `terrestrial_species_range_count` | `:436` | Records with class in `{terrestrial, arid, alpine}` |
| `aquatic_species_range_count` | `:439` | Records with class in `{freshwater, marine, reef}` |
| `wetland_species_range_count` | `:442` | Records with class `wetland` |
| `high_endemism_species_range_count` | `:443` | `endemism_index >= 0.60` |
| `high_conservation_stress_species_range_count` | `:444` | `conservation_stress_index >= 0.60` |
| `species_range_total_area_km2` | `:445` | Sum of record areas (**double-counts overlapping ranges**) |
| `mean_species_habitat_suitability_index` | `:446` | Mean best-guild score per cell |
| `mean_species_endemism_index` | `:447` | Mean cell endemism |
| `mean_species_composition_confidence_index` | `:448` | Mean cell confidence |
| `species_guild_type_counts` | `:449` | Sorted record-count histogram by guild |
| `species_habitat_class_counts` | `:450` | Sorted record-count histogram by class |
| `dominant_species_guild_counts` | `:451` | Sorted cell-count histogram by dominant guild, includes `"none"` |
| `wildfire_spread_history_count` | `wildfire_disturbance.py:343` | Number of histories (`<= 96`) |
| `wildfire_disturbance_cell_count` | `:344` | Cells with a non-empty `wildfire_spread_history_ids` |
| `wildfire_spread_step_count` | `:345` | Total steps across histories |
| `high_wildfire_ignition_potential_cell_count` | `:346` | `ignition >= 0.28` |
| `high_wildfire_fuel_continuity_cell_count` | `:347` | `fuel >= 0.35` |
| `high_wildfire_firebreak_cell_count` | `:348` | `firebreak >= 0.55` |
| `wildfire_total_burned_area_km2` | `:349` | Sum of history areas (histories are disjoint, so no double count) |
| `mean_wildfire_ignition_potential_index` | `:350` | Mean over all cells |
| `mean_wildfire_fuel_continuity_index` | `:351` | Mean over all cells |
| `mean_wildfire_wind_alignment_index` | `:352` | Mean over all cells |
| `mean_wildfire_firebreak_index` | `:353` | Mean over all cells |
| `wildfire_disturbance_regime_counts` | `:354` | Sorted histogram over the 7 regimes |

Every one of these keys appears in the Markdown summary writer's key list (`src/magic_geo/io/summary_markdown.py`; the contiguous biome-diagnostics/ecotone/realism block is `:1057-1083`, with the ecosystem, species and wildfire keys listed further down).

Smoke-test coverage is high but **not** total: `tests/test_smoke_biosphere.py` independently re-derives 68 of the 70 Python-emitted keys above. It does not reference `high_endemism_species_range_count` or `high_conservation_stress_species_range_count`, and it does not touch the native `biome_counts`.

---

## Ordering dependencies

### Hard native ordering

The native classifier is the **last** stage that can be affected by climate and hydrology and the **first** stage that other environment products depend on. Its inputs are finalized by `stabilize_numeric_depressions` and the terminal `derive_cryosphere_state` call (`pipeline.cpp:157-167`); its outputs feed `derive_landforms`, `generate_settlements`, `generate_political_regions`, `generate_cultural_layers` and `generate_historical_layers` (all downstream of `pipeline.cpp:188`). Reordering it breaks engine invariant 1 (*preserve pipeline order*, `cpp/src/engine/README.md`).

### Hard Python ordering

| Consumer | Requires (produced by) | Why |
|---|---|---|
| `biome_diagnostics` | `soil_moisture_index`, `soil_organic_matter_fraction` (`soil_dynamics.py:421`, `:423`) | Fire fuel index, confidence, waterlogging limiting factor |
| `biome_diagnostics` | `seasonal_aridity_index` (`climate_dynamics.py:194`) | Fire index and ecotone index |
| `biome_ecotones` | `frost_months`, `dry_season_months`, `wet_season_months`, `climatic_water_deficit_mm_y`, `potential_evapotranspiration_mm_y` (all `biome_dynamics`) | Every gate and most scoring terms |
| `biome_realism` | `biome_ecotone_type` (`biome_ecotones`) | Mangrove population definition |
| `biome_realism` | `dry_season_months`, `wet_season_months`, `frost_months`, `climatic_water_*`, `potential_evapotranspiration_mm_y` (`biome_dynamics`) | Checks 0–4 |
| `ecosystem_dynamics` | `fire_frequency_index`, `ecotone_index`, `growing_season_months`, `potential_evapotranspiration_mm_y` (`biome_dynamics`) | NPP, biomass, wildfire spread risk, richness |
| `species_ranges` | `primary_productivity_index`, `vegetation_biomass_index`, `species_richness_index`, `ecosystem_disturbance_pressure_index`, `forest_growth_index`, `fishery_productivity_index` (`ecosystem_dynamics`) | Every guild score |
| `species_ranges` | `wetland_extent_index`, `wetland_hydrology_index`, `wetland_system_id`, `wetland_system_type` (`wetland_diagnostics`) | Wetland guilds and linkage |
| `species_ranges` | `reef_growth_index`, `reef_type`, `reef_system_id` (`reef_diagnostics`) | Reef guild and linkage |
| `species_ranges` | `permafrost_extent_index` (`permafrost_diagnostics`) | Alpine guild |
| `species_ranges` | `island_class` (`sea_level_diagnostics`), `distance_to_marine_water_km` (`climate_continentality`) | Endemism and coastal terms |
| `species_ranges` | `river_channel_width_m`, `river_channel_depth_m` (`river_channel_morphology`), `aquifer_system_id` (`aquifer_resources`) | Freshwater guild and linkage |
| `species_ranges` | `biome_confidence_index`, `biome_ecotone_type` (biome enrichers) | Composition confidence and endemism |
| `wildfire_disturbance` | `vegetation_biomass_index`, `primary_productivity_index`, `wildfire_spread_risk_index`, `ecosystem_disturbance_pressure_index` (`ecosystem_dynamics`) | Fuel and ignition |
| `wildfire_disturbance` | `wetland_extent_index` (`wetland_diagnostics`), `floodplain_connectivity_index` (`river_channel_morphology`) | Firebreak |
| `wildfire_disturbance` | `climate_energy_stress_index` (`climate_energy`) | Lightning proxy |

### Full-world versus geo-only ordering delta

Both entry points run the six enrichers in the same relative order among themselves. The only delta that touches this page is that in `generate_geo_world` the permafrost and glacial-landform enrichers run **before** `biome_diagnostics` (`api.py:342-344`) whereas in `generate_world` they run **after** (`api.py:224-226`). `biome_diagnostics` reads nothing they produce, so its own output is order-invariant; but `permafrost_diagnostics` reads `frost_months` and, in the geo-only order, that key is not yet present. Its per-cell path has an explicit fallback that recomputes frost months from the monthly temperature array (`src/magic_geo/permafrost_diagnostics.py:50`); its region aggregate `mean_frost_months` uses a plain `0.0` default (`permafrost_diagnostics.py:167`) and is therefore reported as zero in geo-only worlds. That is a cryosphere-page concern, but it is caused by the biome-enricher ordering and is stated here for completeness.

### Geo-only stripping effects on this layer

`_strip_native_civilization_outputs` (`src/magic_geo/api.py:269-284`, called at `:304`) pops `settlement_score` — one of the four members of `NATIVE_CIVILIZATION_CELL_FIELDS` (`api.py:106-113`) — from every cell before enrichment. Exactly two formulas on this page read it, both with a `0.0` default, and therefore take their no-human branch in geo-only mode:

| Formula | Term | Source | Effect when stripped |
|---|---|---|---|
| `_disturbance_pressure` | `settlement*0.16` | `ecosystem_dynamics.py:57`, `:60` | Disturbance drops by up to `0.16` |
| `_ignition_potential` | `settlement*0.08` | `wildfire_disturbance.py:104`, `:113` | Ignition drops by up to `0.08` |

The native `biome` enum itself is unaffected by stripping; only the Python diagnostic indices change.

Consequently `ecosystem_disturbance_pressure_index`, `wildfire_ignition_potential_index`, and everything downstream of them (succession stage, recovery years, species conservation stress, wildfire regimes and events) legitimately differ between a full world and a geo-only world generated from the same seed. This is intentional, not drift.

---

## Validators

| Validator | Location | Surface | What it enforces |
|---|---|---|---|
| `biome_diagnostic_coverage` | `src/magic_geo/geo_validation.py:2266-2302` | `validate-geo`, domain `soil_biome` | Exactly one diagnostic per cell; diagnostic `biome` mirrors the cell `biome`; `biome_confidence_index` finite in `[0,1]` |
| `biome_diagnostic_causal_replay` | `src/magic_geo/geo_validation.py:2304-2384` | `validate-geo`, domain `soil_biome` | **Re-runs `enrich_world_with_biome_diagnostics` on a deep copy of the cells** and requires every record field, every one of the 11 derived cell fields, and every summary key to match within `1e-6` (booleans by identity, strings by equality). This is what catches a cell biome and its diagnostic label being edited together |
| `biome_ecotone_membership_and_ranges` | `src/magic_geo/geo_validation_subsystems.py:1239-1302` | `validate-geo`, domain `soils_and_ecotones` | Sequential ids; unique non-empty `cell_ids` resolving to real cells; **no cell in two regions**; `cell_count`/`area_km2` match the member cells; each member cell mirrors `biome_ecotone_region_id` and `biome_ecotone_type`; bounded `mean_ecotone_confidence`; finite temperature and non-negative precipitation; the assignment set is exactly `{cells with biome_ecotone_region_id >= 0}`; summary mirrors for `biome_ecotone_region_count` and `biome_ecotone_cell_count` |
| `succession_and_renewable_sources` | `src/magic_geo/geo_validation_subsystems.py:2069-2120` | `validate-geo`, domain `ecosystems_reefs_species_wildfire` | Sequential ids; one history per cell at most; `step_count` matches; initial/final stage endpoints match `steps[0]`/`steps[-1]`; the 6 bounded step fields; non-negative `years_since_start`; renewable `resource_type ∈ {forest_growth, fishery_productivity}`; 5 bounded renewable fields; `regeneration_years >= 1`; the 7 bounded ecosystem cell fields on **every** cell; three summary mirrors |
| `species_range_inverse_links_and_envelopes` | `src/magic_geo/geo_validation_subsystems.py:2169-2215` | `validate-geo`, domain `ecosystems_reefs_species_wildfire` | Sequential ids; unique resolvable `cell_ids`; `cell_count`/`area_km2` match; **exact many-to-many inverse** between `record.cell_ids` and `cell.species_range_record_ids`; `wetland_system_ids`/`reef_system_ids`/`aquifer_system_ids` resolve to real system indices; 9 bounded record indices; `climate_envelope` present, finite, and **ordered** (`min <= mean <= max` for temperature, `0 <= min <= mean <= max` for precipitation); three summary mirrors |
| `wildfire_inverse_links_and_steps` | `src/magic_geo/geo_validation_subsystems.py:2217-2275` | `validate-geo`, domain `ecosystems_reefs_species_wildfire` | Sequential ids; `ignition_cell_id ∈ cell_ids`; `cell_count`/`area_km2` match; exact inverse with `cell.wildfire_spread_history_ids`; `spread_step_count == len(steps)`; every step's `active_front_cell_ids` and `newly_burned_cell_ids` are subsets of the history's cells; **`cumulative_burned_cell_count` monotonic non-decreasing and bounded by `len(cell_ids)`**; bounded per-step probability and containment; non-negative burned area; 8 bounded history indices; four summary mirrors |
| Layer contract `biomes_ecosystems` | `src/magic_geo/geo_layer_contracts.py:237-258` | `validate-geo` layer audit | Requires `biome_diagnostics` (**nonempty**), `biome_ecotone_regions`, `biome_realism_checks`, `vegetation_succession_histories`, `species_range_records`, `wetland_systems`, `reef_systems`, `wildfire_spread_histories`; dependencies `soils_pedogenesis` + `climate_atmosphere` + `hydrology` |
| Smoke assertions | `tests/test_smoke_biosphere.py` | `pytest` | Independent re-derivation of every summary aggregate on this page from the record arrays, including the ecotone type-count sum equalling `cell_count` and the ecotone cell-id set equalling the union of region membership |

Note what the validators deliberately do **not** do: only `biome_diagnostics` has a full producer replay. Ecotones, ecosystem dynamics, species ranges and wildfire disturbance are validated structurally (membership, inverse links, bounds, monotonicity, summary mirrors) but their scoring formulas are not re-executed, so a change to a weight in those four modules will pass `validate-geo` as long as the resulting values stay in `[0,1]` and the membership bookkeeping stays consistent.

---

## Worked commands

Generate a world and run both gates:

```bash
magic-geo generate --config configs/earthlike_seed.yaml --output runs/world.json
magic-geo validate --world runs/world.json
magic-geo validate-geo --world runs/world.json --profile earthlike --output runs/geo_validation.json
```

Generate a geo-only world (no `settlement_score`, so the no-human ecology branches are taken) and export the cell table:

```bash
magic-geo generate --config configs/earthlike_seed.yaml --geo-only \
  --output runs/geo_world.json --cells-csv runs/geo_cells.csv
```

Inspect the native biome histogram and the diagnostic agreement fraction:

```python
import json

world = json.load(open("runs/world.json"))
summary = world["summary"]

print(summary["biome_counts"])                       # sparse, native classifier only
print(summary["biome_expected_match_fraction"])      # native vs. Python shadow classifier
print(summary["biome_limiting_factor_counts"])
print(summary["biome_ecotone_type_counts"])          # includes the "none" bucket
print(summary["wildfire_disturbance_regime_counts"])
print(summary["vegetation_succession_stage_counts"])
```

Confirm that `mediterranean_scrub` is never emitted by the native classifier:

```python
import json
world = json.load(open("runs/world.json"))
assert "mediterranean_scrub" not in world["summary"]["biome_counts"]
assert all(cell["biome"] != "mediterranean_scrub" for cell in world["cells"])
```

Read the five biome realism checks with their targets and evidence:

```python
import json
world = json.load(open("runs/world.json"))
for check in world["biome_realism_checks"]:
    print(check["name"], check["value"], check["target_min"], check["target_max"],
          check["passed"], check["score"])
    print("   ", check["evidence"])
```

Re-run the biome diagnostic producer exactly the way the validator does:

```python
import json
from copy import deepcopy
from magic_geo.biome_dynamics import enrich_world_with_biome_diagnostics

world = json.load(open("runs/world.json"))
replay = {"cells": deepcopy(world["cells"]), "summary": {}}
enrich_world_with_biome_diagnostics(replay)

assert len(replay["biome_diagnostics"]) == len(world["biome_diagnostics"])
for expected, actual in zip(replay["biome_diagnostics"], world["biome_diagnostics"]):
    assert expected["expected_biome"] == actual["expected_biome"]
    assert abs(expected["potential_evapotranspiration_mm_y"]
               - actual["potential_evapotranspiration_mm_y"]) <= 1e-6
```

Run only the ecology validator domains:

```python
import json
from magic_geo.geo_validation import validate_geo_world

world = json.load(open("runs/world.json"))
report = validate_geo_world(world, profile="earthlike")
for check in report["checks"]:
    if check["domain"] in {"soil_biome", "soils_and_ecotones",
                           "ecosystems_reefs_species_wildfire"}:
        print(check["domain"], check["name"], check["status"])
```

Trace one wildfire event end to end:

```python
import json
world = json.load(open("runs/world.json"))
cells = {cell["id"]: cell for cell in world["cells"]}

history = world["wildfire_spread_histories"][0]
print(history["ignition_cell_id"], history["dominant_disturbance_regime"],
      history["cell_count"], history["area_km2"], history["containment_index"])
for step in history["steps"]:
    print(step["step_index"], step["cumulative_burned_cell_count"],
          round(step["mean_spread_probability_index"], 3),
          round(step["containment_index"], 3))

ignition = cells[history["ignition_cell_id"]]
print(ignition["wildfire_ignition_potential_index"],
      ignition["wildfire_fuel_continuity_index"],
      ignition["wildfire_firebreak_index"],
      ignition["wildfire_wind_alignment_index"])
```

---

## Limitations and unresolved claims

**Authority.** Only `cells[].biome`, `soil_type`, `soil_depth_m`, `fertility`, `resource`, `settlement_score` and `landform` are native simulation state. Every other field, record and summary key on this page is a **non-authoritative post-hoc diagnostic** computed in Python from the serialized world. Nothing here is read back by the native engine, and nothing here participates in the sediment, crust, hydrologic or mass ledgers.

**No time calibration.** The layer contract `biomes_ecosystems` declares `temporal_class = posthoc_diagnostic_trajectories`. The succession `years_since_start` values (`0, 25, 60, 90`), `vegetation_recovery_years`, `regeneration_years` and the wildfire step index are **nominal integers with no calibrated relation to simulation time or to physical time**. None of the six enrichers emits a time ledger of its own. In geo-only worlds the provenance enricher (`src/magic_geo/geo_evolution_provenance.py`, called at `api.py:374`) classifies `vegetation_succession_histories` and `wildfire_spread_histories` as `temporal_role = "posthoc_diagnostic_trajectory"` with `state_mutation_evidence = "no"`, `physical_time_resolved = false`, `nominal_time_coordinate_available = false`, `nominal_time_linkage = "none"` and `time_basis = "diagnostic_index_step"` (`geo_evolution_provenance.py:46-60`, `:91-125`) — that is, they are explicitly recorded as carrying *no* time coordinate at all, not even the nominal one that native mutation ledgers carry. `biome_diagnostics`, `biome_ecotone_regions`, `biome_realism_checks`, `renewable_resource_records` and `species_range_records` are not history families and are not classified there at all.

**No population or evolutionary process.** The layer's declared `evidence_class` is `rule_replay_without_population_evolution`. There is no dispersal, no competition, no colonization or extinction dynamics, no trophic mass balance and no genetics. "Species ranges" are threshold-and-flood-fill maps of a habitat suitability score over ten hand-specified guilds; they carry no claim about actual organisms.

**The realism checks are envelope-agreement checks, not empirical validation.** Every layer contract in this codebase hardcodes `empirical_realism_proven: False`. Check 3 (`savanna_seasonality_alignment`) in particular measures the agreement of two implementations of the same seasonality rule (`environment.cpp:318-325` and `biome_dynamics.py:113-125`) and is close to a tautology. Check 4 (`mangrove_warm_wet_coast_constraint`) re-tests a near-copy of the mangrove ecotone gate against the population that gate produced — it drops the gate's `elevation_m <= 80.0` clause and tightens `soil_moisture_index >= 0.58` to `>= 0.65`, so it is near-tautological rather than exactly tautological. Every check returns `1.0` on an empty population, so a world with no savannas, no deserts or no tundra passes those checks vacuously.

**Two incompatible aridity definitions coexist.** The native classifier uses `aridity = P / max(1, (T+8)*31)` — a moisture ratio where higher means wetter, with no latitude term. The Python diagnostics use `deficit_index = max(0, PET - P) / PET` with a Thornthwaite-style monthly, latitude-weighted PET. They are different quantities on different scales. `biome_expected_match_fraction` therefore measures cross-model agreement between two genuinely different classifiers, not the internal consistency of one.

**`mediterranean_scrub` is unreachable.** The enum value exists in `BIOME_NAMES` and is referenced as a grassland/fuel category by `biome_dynamics.py:132`, `ecosystem_dynamics.py:8`, `species_ranges.py:9`, `wildfire_disturbance.py:72` and `biome_ecotones.py:129`, but no native branch ever assigns it. Those terms are dead in every generated world. (The `mediterranean_scrub` *ecotone* type is separate and is reachable.)

**Shadow classifier blind spots.** `_expected_biome` can never return `wetland` or `mediterranean_scrub`, so every native `wetland` cell is permanently scored as a mismatch with a `0.30` confidence base and `biome_transition_zone == True`. It also reads the native `biome` directly for its `ice_cap` rule (`biome_dynamics.py:42`), so it is not fully independent there.

**Lakes are classified as land.** Because `is_water` is marine-only (`cpp/src/engine/ocean.cpp:250`), lake cells take the land branch everywhere: in the native cascade (rows L1a/L1b), in `_expected_biome`, and in `_primary_productivity` / `_vegetation_biomass`. A `fresh_lake` cell therefore receives a terrestrial NPP and a non-zero terrestrial biomass while simultaneously qualifying for `fishery_productivity_index` through `FISHERY_WATER_TYPES`. Arid closed-basin lakes are labelled `hot_desert` regardless of temperature.

**Enum overloading.** Marine `inland_sea` cells are labelled biome `lake` (`environment.cpp:331`); `ice_cap` cells are given `tundra` soil; the final else-branch can label a 10 °C cell `hot_desert`. These are properties of the classifier as written, not modelling claims.

**Dead lookup entries.** `species_ranges._cell_endemism` maps `continental_island → 0.16` and defaults to `"mainland"`, but `sea_level_diagnostics._landmass_class` (`:85-92`) only produces `continent`, `large_island`, `island`, `islet`, `water` and `unassigned`. `biome_ecotones._has_freshwater_neighbor` tests for `water_body_type == "lake"`, which is not a member of `WATER_BODY_NAMES`.

**Bounded, truncated disturbance.** Wildfire spread is capped at 96 events, 6 steps and 96 cells per event, with events forced disjoint by construction. These are hard implementation caps, not fire-regime physics: a world with widespread high ignition potential will have its fire footprint truncated rather than saturated. There is no fire-return interval, no fuel consumption, no post-fire state change, and the fire does not modify `vegetation_biomass_index`, `sediment_thickness_m` or anything else — it is a read-only overlay.

**Overlapping species ranges inflate area.** `summary.species_range_total_area_km2` sums record areas across ten guilds, and a cell may be in several ranges at once, so this total routinely exceeds the planet's land plus water area. `species_range_cell_count` is the non-double-counted quantity.

**Ecotone confidence for non-ecotone cells.** `biome_ecotone_confidence` retains the sub-threshold best score for cells whose type is `"none"`, and `mean_biome_ecotone_confidence` averages over **all** cells including those. It is not the mean confidence of the detected ecotones.

**Validation asymmetry.** Only the biome diagnostics have a full producer replay in `validate-geo`. Ecotones, ecosystem dynamics, species ranges and wildfire disturbance are checked for structure, membership, inverse links, bounds and summary mirrors — not for formula fidelity.

**Geo-only divergence is expected.** With `settlement_score` stripped, `ecosystem_disturbance_pressure_index` and `wildfire_ignition_potential_index` and everything downstream of them differ from a full world at the same seed. Comparing the two directly is not a drift test.

---

## See also

- [Soils and Weathering](soils.md) — the other half of `derive_soils_biomes_resources`, and the soil profile/horizon diagnostics that supply `soil_moisture_index` and `soil_organic_matter_fraction`
- [Climate and Atmosphere](climate-and-atmosphere.md) — `temperature_monthly_c`, `precipitation_monthly_mm`, `seasonal_aridity_index`, `climate_energy_stress_index` and the wind field used for fire spread
- [Hydrology, Rivers and Lakes](hydrology-and-rivers.md) — `is_river`, `is_lake`, `water_body`, depression policy and the lake water-body stamping that the biome cascade reads
- [Cryosphere: Ice Sheets, Glaciers and Permafrost](cryosphere.md) — `ice_thickness_m`, the `ice_cap` gate, and `permafrost_extent_index` consumed by the alpine guild
- [Oceans, Currents and Coasts](oceans-and-coasts.md) — the marine flood-fill that defines `is_water`, the `water_body` classes, and the reef and coastal inputs
- [Groundwater, Aquifers and Karst](groundwater-and-karst.md) — `aquifer_system_id` and `groundwater_recharge_mm_y` used by the range linkage and renewable-resource water dependency
- [Resources and Economic Geology](resources-and-economic-geology.md) — the `resource` enum written by the same native stage, and the commodity layer that consumes `fishery_productivity_index`
- [Erosion, Maturation and Landscape Evolution](erosion-and-maturation.md) — `erosion_rate`, the disturbance-pressure input
- [Settlements, Routes and Corridors](settlements-and-routes.md) — the `settlement_score` written by the same native stage and stripped in geo-only mode
- [Validation](../12-validation.md) — how the biome and ecosystem checks compose into `validate` and `validate-geo`
- [Geo Validation Suite](../13-geo-validation-suite.md) — the scenario matrix and layer-contract audit
- [World Document Schema](../10-world-schema.md) — the full native key inventory, including `BIOME_NAMES`, `SOIL_NAMES` and `LANDFORM_NAMES`
- [Python API](../07-python-api.md) — enricher call order in `generate_world` and `generate_geo_world`
- [Native Engine (C++ Core)](../08-native-engine.md) — pipeline stage ordering and the engine invariants
- [CLI Reference](../06-cli-reference.md) — `generate`, `validate`, `validate-geo`
- [Debug Exports and Visualization](../16-debug-and-visualization.md) — the `biome` debug map layer
- [Glossary](../21-glossary.md)
