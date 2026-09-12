# Resources and Economic Geology

[Wiki home](../README.md) > Features

magic-geo does not sprinkle ore bodies onto a finished map. A cell only carries a resource because the native simulation put it there from crust type, crust age, boundary kinematics, lithology, sediment thickness, soil type, fertility and aridity — and every Python resource product downstream is a *derivation* over that native state plus the tectonic, sediment, hydrologic and ecological diagnostics that ran before it. This page is the reference for the six resource enrichers (`resource_dynamics`, `ore_genesis`, `sedimentary_resource_systems`, `petroleum_migration`, `commodity_resources`, `land_use_zones`), their record schemas, their exact scoring formulas and thresholds, and the commodity-to-precondition cross-reference. Everything here is bounded-index plausible-pattern generation: the two published resource model records (`resource_deposit_model`, `ore_genesis_model`) both declare `physical_time_resolved: False`, and neither grade, tonnage, reserve volume, nor geochemical transport is simulated anywhere in the stack.

## On this page

- [Where resources come from: the native causal chain](#where-resources-come-from-the-native-causal-chain)
- [Pipeline placement and generation scope](#pipeline-placement-and-generation-scope)
- [Resource deposit generation](#resource-deposit-generation)
- [The deposit record](#the-deposit-record)
- [Ore genesis](#ore-genesis)
- [Sedimentary resource systems: coal and evaporites](#sedimentary-resource-systems-coal-and-evaporites)
- [Petroleum systems](#petroleum-systems)
- [Commodity occurrences](#commodity-occurrences)
- [Land use zones and agricultural zoning](#land-use-zones-and-agricultural-zoning)
- [Renewable resource records](#renewable-resource-records)
- [Commodity cross-reference](#commodity-cross-reference)
- [Per-cell fields written by the resource layer](#per-cell-fields-written-by-the-resource-layer)
- [Summary keys](#summary-keys)
- [Worked example: one arc cell, end to end](#worked-example-one-arc-cell-end-to-end)
- [Inspecting resources](#inspecting-resources)
- [Validation surfaces](#validation-surfaces)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

---

## Where resources come from: the native causal chain

The per-cell `resource` field is a nine-valued enum defined in `cpp/src/engine/schema_names.hpp:27`:

```
none, volcanic_arc_metals, craton_iron_gold, sedimentary_fuels,
evaporites, placer_metals, geothermal, fertile_alluvium, coastal_fisheries
```

It is assigned by the native C++ engine inside `derive_soils_biomes_resources` (`cpp/src/engine/environment.cpp:301`), *after* soil type, soil depth, fertility and biome have themselves been derived from lithology, climate, relief and river state, and then refined by `derive_landforms` (`cpp/src/engine/environment.cpp:417`). Nothing in the assignment is random: it is a strict first-match cascade over already-simulated physical state.

The local aridity term used by the cascade is defined at `cpp/src/engine/environment.cpp:309-310` as

```
pet     = max(1.0, (temperature_c + 8.0) * 31.0)
aridity = precipitation_mm_y / pet
```

### Water cells

`cpp/src/engine/environment.cpp:327-334`: any water cell short-circuits. It gets `resource = coastal_fisheries` if it has an ocean neighbour **or** its `water_body` is `continental_shelf`, otherwise `none`. Water cells also get `soil_type = none`, `soil_depth_m = 0`, `fertility = 0`, `settlement_score = 0`.

### Land cells — the first-match cascade

`cpp/src/engine/environment.cpp:390-404`. Evaluated top to bottom; the first satisfied predicate wins.

| Order | Native predicate | Resource assigned | Physical reading |
|---|---|---|---|
| 1 | `boundary_convergent > 0.38` **and** (`crust_type == volcanic_arc` **or** `lithology == volcanic`) | `volcanic_arc_metals` | Strongly convergent margin with arc crust or volcanic host rock |
| 2 | `crust_type == craton` **and** `crust_age_ma > 1800.0` | `craton_iron_gold` | Ancient stable continental nucleus |
| 3 | `crust_type == sedimentary_basin` **or** `lithology == shale` **or** `lithology == limestone` **or** `sediment_thickness_m > 1.4` | `evaporites` when `aridity < 0.45`, else `sedimentary_fuels` | Basin fill; arid basins evaporate, humid basins bury organics |
| 4 | `is_river` **and** `boundary_convergent > 0.16` | `placer_metals` | Channel draining an actively uplifting convergent source region |
| 5 | `boundary_divergent > 0.42` **or** (`lithology == volcanic` **and** `temperature_c > 0.0`) | `geothermal` | Rift/spreading heat, or volcanic rock outside a frozen surface |
| 6 | `soil_type == alluvial` **and** `fertility > 0.62` | `fertile_alluvium` | Well-developed fertile alluvial soil |
| 7 | — (fall-through) | `none` | |

### Landform post-pass overrides

`derive_landforms` re-runs after landform classification and can overwrite the cascade result (`cpp/src/engine/environment.cpp:476-503`):

| Landform | Override |
|---|---|
| `delta` or `floodplain` | if the (already bonus-adjusted) `fertility > 0.64` → `fertile_alluvium` (`environment.cpp:482-484`) |
| `alluvial_fan` | if `resource == none` **and** `boundary_convergent > 0.10` → `placer_metals` (`environment.cpp:488-490`) |
| `salt_flat` | unconditionally → `evaporites` (`environment.cpp:492-494`) |

Because the same field feeds back into `settlement_score` (`environment.cpp:407-410`, `resource_score = 0.18` for any non-`none` resource), resources also participate in the native settlement selection — see [Settlements, Routes and Corridors](settlements-and-routes.md).

### What "derived, not sprinkled" concretely means here

Every Python enricher on this page reads the native `resource` field and the physical fields that produced it, and *re-expresses* them as bounded indices. No enricher creates a resource where the native cascade produced `none`; `resource_dynamics` skips such cells outright (`src/magic_geo/resource_dynamics.py:163-165`), and the entire deposit/commodity chain hangs off that skip. Ore, sedimentary, petroleum and land-use models can raise a *potential index* on a `none` cell, but they cannot mint a deposit record there.

---

## Pipeline placement and generation scope

Both entry points in `src/magic_geo/api.py` run the resource block as a contiguous, strictly ordered group, immediately after the ecology block:

| # (full) | # (geo-only) | Enricher | Module |
|---|---|---|---|
| 50 | 41 | `enrich_world_with_resource_deposits` | `src/magic_geo/resource_dynamics.py:148` |
| 51 | 42 | `enrich_world_with_ore_genesis` | `src/magic_geo/ore_genesis.py:323` |
| 52 | 43 | `enrich_world_with_sedimentary_resource_systems` | `src/magic_geo/sedimentary_resource_systems.py:152` |
| 53 | 44 | `enrich_world_with_petroleum_migration` | `src/magic_geo/petroleum_migration.py:281` |
| 54 | 45 | `enrich_world_with_commodity_occurrences` | `src/magic_geo/commodity_resources.py:195` |
| 55 | *(not run)* | `enrich_world_with_land_use_zones` | `src/magic_geo/land_use_zones.py:205` |

Call sites: `src/magic_geo/api.py:249-254` (`generate_world`) and `src/magic_geo/api.py:365-369` (`generate_geo_world`). The order is load-bearing — each stage consumes the previous stage's output:

```
native cell.resource
  └─> resource_deposits            (resource_dynamics)
        ├─> ore_genesis_systems    (ore_genesis, filters ORE_RESOURCES)
        ├─> sedimentary_resource_systems (filters sedimentary_fuels + evaporites)
        │     └─> petroleum_migration_systems
        ├─> commodity_occurrences  (reads deposits; joins a sedimentary system when the basin has one)
        └─> agricultural_zones / mining_zones  (full world only)
```

### Geo-only differences

`generate_geo_world` calls `_strip_native_civilization_outputs` before any enricher runs, removing four per-cell fields: `culture_region_id`, `language_region_id`, `political_region_id`, `settlement_score`. Concrete consequences for this layer:

| Consumer | Field read | Geo-only effect |
|---|---|---|
| `resource_dynamics._accessibility` (`resource_dynamics.py:83`) | `settlement_score` | Defaults to `0.0`, so accessibility collapses to `clamp(0.28 + water_access − relief·0.20)` |
| Deposit record (`resource_dynamics.py:193-194`) | `political_region_id`, `culture_region_id` | Both serialize as `-1` |
| Commodity record (`commodity_resources.py:250-251`) | same | Both serialize as `-1` |
| `land_use_zones` | `settlement_score`, `settlements`, `routes` | Enricher is not invoked at all in geo-only mode |

The geo layer contract registers this whole block as phase 12, layer id `natural_resources` (`src/magic_geo/geo_layer_contracts.py:259-282`), with `temporal_class: "posthoc_causal_diagnostic"` and `evidence_class: "source_link_replay_without_geochemical_solver"`, dependencies `crust_lithology`, `erosion_sediment`, `hydrology`, `biomes_ecosystems`, and required outputs `resource_deposit_model`, `resource_deposits`, `ore_genesis_model`, `ore_genesis_systems`, `sedimentary_resource_systems`, `petroleum_migration_systems`, `commodity_occurrences`, `renewable_resource_records`.

---

## Resource deposit generation

`enrich_world_with_resource_deposits` (`src/magic_geo/resource_dynamics.py:148`) walks every cell, skips `resource == "none"`, and emits one deposit record per remaining cell. It writes no per-cell fields.

### Resource classing

`_resource_class` (`resource_dynamics.py:27-36`) and `_formation_process` (`resource_dynamics.py:39-50`):

| Resource | `deposit_class` | `formation_process` |
|---|---|---|
| `volcanic_arc_metals` | `metal` | `subduction_arc_hydrothermal` |
| `craton_iron_gold` | `metal` | `ancient_craton_metallogeny` |
| `placer_metals` | `metal` | `fluvial_placer_concentration` |
| `sedimentary_fuels` | `energy` | `buried_sedimentary_basin` |
| `geothermal` | `energy` | `rift_or_volcanic_heat` |
| `evaporites` | `industrial_mineral` | `closed_basin_evaporation` |
| `fertile_alluvium` | `bioproductive` | `alluvial_soil_resource` |
| `coastal_fisheries` | `bioproductive` | `shelf_coastal_bioproductivity` |
| *(anything else)* | `other` | `undifferentiated_resource` |

Set membership is defined at `resource_dynamics.py:7-9`: `METAL_RESOURCES`, `ENERGY_RESOURCES`, `AGRICULTURAL_RESOURCES = {"fertile_alluvium", "coastal_fisheries"}`.

### Flow-accumulation normalisation

Placer scoring needs a scale-free drainage measure. `_flow_accumulation_scale` (`resource_dynamics.py:16-24`) sorts all strictly positive `flow_accumulation` values and takes the index-based 95th percentile, floored at 1.0:

```python
positive = sorted(v for v in flow_accumulations if v > 0.0)
scale = max(1.0, positive[int(0.95 * (len(positive) - 1))])
```

The published model record names this `positive_cell_p95_v1` and declares the units as `runoff_mm_y_times_upstream_area_km2` (`resource_dynamics.py:211-213`). The identical function is re-implemented in `ore_genesis.py:29-37` and re-derived independently by the validator at `src/magic_geo/geo_validation_subsystems.py:2283-2292`.

### `reserve_potential_index`

`_reserve_potential` (`resource_dynamics.py:53-79`). Shared normalised inputs: `sediment = clamp(sediment_thickness_m / 3.0)`, `crust_age = clamp(crust_age_ma / 2500.0)`, `runoff = clamp(runoff_mm_y / 900.0)`, `flow = clamp(flow_accumulation / max(1, scale))`, plus clamped `boundary_convergent`, `boundary_divergent`, `fertility`, `soil_salinity_index`.

| Resource | Formula (all clamped to `[0,1]`) |
|---|---|
| `volcanic_arc_metals` | `0.34 + convergent·0.42 + (0.18 if landform == volcanic_arc)` |
| `craton_iron_gold` | `0.28 + crust_age·0.46 + (0.20 if crust_type == craton)` |
| `sedimentary_fuels` | `0.26 + sediment·0.48 + (0.12 if "basin" in landform)` |
| `evaporites` | `0.30 + salinity·0.36 + (0.24 if landform == salt_flat)` |
| `placer_metals` | `0.24 + flow·0.34 + convergent·0.20 + sediment·0.14` |
| `geothermal` | `0.26 + divergent·0.34 + convergent·0.20 + (0.18 if landform ∈ {volcanic_arc, rift_valley})` |
| `fertile_alluvium` | `0.24 + fertility·0.42 + runoff·0.16 + (0.16 if landform ∈ {floodplain, delta})` |
| `coastal_fisheries` | `0.30 + (0.26 if water_body_type == continental_shelf) + runoff·0.12` |
| *(unlisted)* | `0.18` |

Note the `"basin" in landform` substring test for `sedimentary_fuels` — it is a string-containment test, not an enum-set test. Against the twenty native `LANDFORM_NAMES` (`cpp/src/engine/schema_names.hpp:37`) exactly one value contains `"basin"`: `lacustrine_basin`. (`rift_basin` and `sedimentary_basin` are `crust_type` values, not landforms, so they never reach this test.)

### `accessibility_index`, `extraction_hazard_index`, `geologic_confidence_index`, `renewability_index`

| Index | Source | Formula |
|---|---|---|
| `accessibility_index` | `resource_dynamics.py:82-86` | `clamp(0.28 + settlement_score·0.42 + water_access − relief·0.20)` where `water_access = 0.20` if `is_river` or `water_body_type ∈ {continental_shelf, fresh_lake}`, else `0.0`; `relief = clamp(abs(elevation_m) / 3000.0)` |
| `extraction_hazard_index` | `resource_dynamics.py:89-95` | `clamp(tectonic + relief·0.20 + ice·0.20 + aridity·0.10 + salinity·0.08)` where `tectonic = clamp(convergent·0.42 + transform·0.30)`, `relief = clamp(abs(elevation_m)/3600)`, `ice = clamp(ice_thickness_m/1600)`, `aridity = clamp(seasonal_aridity_index)`, `salinity = clamp(soil_salinity_index)` |
| `geologic_confidence_index` | `resource_dynamics.py:98-132` | `clamp(evidence·0.72 + reserve·0.28)`; `evidence` starts at `0.18` and takes a resource-specific pair of terms (see below) |
| `renewability_index` | `resource_dynamics.py:172` | `0.78` for `fertile_alluvium`/`coastal_fisheries`; `0.32` for `geothermal`; `0.02` otherwise |

Evidence terms per resource (`resource_dynamics.py:105-131`), added to the `0.18` base:

| Resource | Continuous term | Categorical term |
|---|---|---|
| `volcanic_arc_metals` | `convergent · 0.36` | `+0.22` if `landform == volcanic_arc` |
| `craton_iron_gold` | `clamp(crust_age_ma/2500) · 0.34` | `+0.24` if `crust_type == craton` |
| `sedimentary_fuels` | `clamp(sediment_thickness_m/3) · 0.38` | `+0.18` if `"basin" in landform` |
| `evaporites` | `clamp(soil_salinity_index) · 0.32` | `+0.22` if `landform == salt_flat` |
| `placer_metals` | `clamp(flow/scale) · 0.26` | `+0.22` if `is_river` |
| `geothermal` | `clamp(max(divergent, convergent)) · 0.34` | `+0.18` if `landform ∈ {volcanic_arc, rift_valley}` |
| `fertile_alluvium` | `clamp(fertility) · 0.32` | `+0.20` if `landform ∈ {floodplain, delta}` |
| `coastal_fisheries` | `clamp(runoff_mm_y/900) · 0.12` | `+0.32` if `water_body_type == continental_shelf` |

### `economic_viability_index`

`resource_dynamics.py:173`:

```
viability = clamp( reserve·0.46 + accessibility·0.30 + confidence·0.20
                   − hazard·0.18 + renewability·0.10 )
```

A deposit counts toward `high_viability_resource_deposit_count` at `viability >= 0.65` (`resource_dynamics.py:180-181`).

### The published model record

`world["resource_deposit_model"]` (`resource_dynamics.py:209-216`):

| Key | Value |
|---|---|
| `model_type` | `causal_geologic_resource_deposit_diagnostics_v2` |
| `flow_accumulation_normalization_model` | `positive_cell_p95_v1` |
| `flow_accumulation_scale` | the computed p95, rounded to 6 dp |
| `flow_accumulation_units` | `runoff_mm_y_times_upstream_area_km2` |
| `physical_time_resolved` | `False` |
| `model_limitation` | `"diagnostic formation evidence without geochemical transport or reserve-volume simulation"` |

---

## The deposit record

One record per non-`none` resource cell, in cell iteration order, with sequential `id` starting at `0` (`resource_dynamics.py:182-206`). All floats are rounded to 6 decimal places.

| Field | Type | Meaning / source |
|---|---|---|
| `id` | int | Sequential index into `world["resource_deposits"]` |
| `cell_id` | int | Source cell (`cell["id"]`); `-1` if absent |
| `resource` | str | Verbatim native `cell["resource"]` enum value |
| `deposit_class` | str | `metal` \| `energy` \| `industrial_mineral` \| `bioproductive` \| `other` |
| `formation_process` | str | See the formation-process table above |
| `host_crust_type` | str | Native `crust_type` (`CRUST_NAMES`), `"unknown"` fallback |
| `host_lithology` | str | Native `lithology` (`LITHOLOGY_NAMES`), `"unknown"` fallback |
| `landform` | str | Native `landform` (`LANDFORM_NAMES`), `"unknown"` fallback |
| `basin_id` | int | Native drainage `basin_id`; `-1` if none |
| `political_region_id` | int | `-1` in geo-only (field stripped) |
| `culture_region_id` | int | `-1` in geo-only (field stripped) |
| `latitude_deg` | float | Cell `lat_deg`, rounded 6 dp |
| `longitude_deg` | float | Cell `lon_deg`, rounded 6 dp |
| `area_km2` | float | Cell `area_km2`, floored at `0.0` |
| `reserve_potential_index` | float `[0,1]` | Resource-specific formula above |
| `accessibility_index` | float `[0,1]` | Settlement + water access − relief |
| `extraction_hazard_index` | float `[0,1]` | Tectonic + relief + ice + aridity + salinity |
| `economic_viability_index` | float `[0,1]` | Weighted combination minus hazard |
| `renewability_index` | float | `0.78` / `0.32` / `0.02` |
| `geologic_confidence_index` | float `[0,1]` | Evidence-weighted |
| `formation_evidence` | object | 8-field provenance block, below |

### `formation_evidence` sub-object

`_formation_evidence` (`resource_dynamics.py:135-145`). This is the audit trail that lets a downstream consumer (or the validator) re-derive why the deposit exists without re-reading the cell.

| Field | Source cell field | Transform |
|---|---|---|
| `boundary_type` | `boundary_type` | str, `"unknown"` fallback |
| `boundary_convergent` | `boundary_convergent` | clamped `[0,1]`, 6 dp |
| `boundary_divergent` | `boundary_divergent` | clamped `[0,1]`, 6 dp |
| `crust_age_ma` | `crust_age_ma` | floored at 0, 6 dp |
| `sediment_thickness_m` | `sediment_thickness_m` | floored at 0, 6 dp |
| `flow_accumulation` | `flow_accumulation` | floored at 0, 6 dp |
| `fertility` | `fertility` | clamped `[0,1]`, 6 dp |
| `salinity_index` | `soil_salinity_index` | clamped `[0,1]`, 6 dp |

Note that `soil_salinity_index` is itself an enricher product (from soil diagnostics, which runs at pipeline position 24 in both scopes), not a native field.

---

## Ore genesis

`enrich_world_with_ore_genesis` (`src/magic_geo/ore_genesis.py:323`) is the metallogenic model. Unlike deposits, it scores **every** cell, writes six per-cell fields, and then groups qualifying cells into contiguous ore systems.

### Constants

`ore_genesis.py:8-14`:

| Constant | Value | Role |
|---|---|---|
| `ORE_RESOURCES` | `{volcanic_arc_metals, craton_iron_gold, placer_metals, geothermal}` | Which deposits are pulled into ore systems |
| `METAL_RESOURCES` | `{volcanic_arc_metals, craton_iron_gold, placer_metals}` | Counted as `metal_deposit_count` |
| `ORE_SYSTEM_THRESHOLD` | `0.34` | Candidacy cutoff on `ore`; also the tie-break floor in mixed-province typing |
| `HIGH_ORE_THRESHOLD` | `0.50` | A deposit-free component must exceed this to survive |
| `HIGH_HYDROTHERMAL_THRESHOLD` | `0.34` | Hydrothermal step membership and summary counter |
| `HIGH_FERTILITY_THRESHOLD` | `0.42` | Source-fertility step membership and summary counter |
| `HIGH_PLACER_THRESHOLD` | `0.32` | Placer step membership and summary counter |

### The four process indices plus the composite

`_cell_indices` (`ore_genesis.py:91-182`). Normalised inputs: `crust_age = clamp(crust_age_ma/2500)`, `crust_thickness = clamp(crust_thickness_km/55)`, `sediment = clamp(sediment_thickness_m/5)`, `flow = clamp(flow_accumulation/max(1, p95_scale))`, `relief = clamp(abs(elevation_m − filled_elevation_m)/1200)`, `river = 1.0 if is_river else 0.0`, and clamped `boundary_convergent`/`divergent`/`transform`, `tectonic_zone_strength`, `volcanic_potential_index`, `fault_slip_rate_index`, `seismic_hazard_index`.

Categorical bonuses (`ore_genesis.py:116-125`):

| Term | Condition | Value |
|---|---|---|
| `arc_lithology` | `lithology ∈ {andesite, basalt, metamorphic}` / `== granite` | `0.12` / `0.04`, else `0.0` |
| `craton_lithology` | `lithology ∈ {granite, metamorphic}` / `== sandstone` | `0.14` / `0.04`, else `0.0` |
| `placer_lithology` | `lithology ∈ {sandstone, metamorphic, granite}` | `0.08` |
| `volcanic_landform` | `landform ∈ {volcanic_arc, rift_valley}` | `0.14` |
| `craton_landform` | `landform ∈ {stable_lowland, mountain_belt}` | `0.08` |
| `placer_landform` | `landform ∈ {river_valley, floodplain, delta, alluvial_fan}` | `0.18` |
| `arc_deposit` | `resource == volcanic_arc_metals` | `0.24` |
| `craton_deposit` | `resource == craton_iron_gold` | `0.24` |
| `placer_deposit` | `resource == placer_metals` | `0.26` |
| `geothermal_deposit` | `resource == geothermal` | `0.18` |

> `arc_lithology` tests for `"andesite"`, which is **not** a member of `LITHOLOGY_NAMES` (`basalt, granite, limestone, sandstone, shale, volcanic, metamorphic`, `cpp/src/engine/schema_names.hpp:11`). On worlds produced by this engine that alternative can never match; only `basalt` and `metamorphic` (0.12) and `granite` (0.04) are reachable. Reported as observed, not repaired.

| Index | Cell field | Formula (clamped `[0,1]`) |
|---|---|---|
| Hydrothermal alteration | `hydrothermal_alteration_index` | `convergent·0.25 + divergent·0.14 + volcanic·0.24 + fault·0.14 + zone_strength·0.10 + volcanic_landform + arc_lithology + arc_deposit + geothermal_deposit` |
| Metallogenic fertility | `metallogenic_fertility_index` | `crust_age·0.20 + crust_thickness·0.12 + (0.18 if crust_type == craton) + convergent·0.12 + volcanic·0.10 + craton_lithology + craton_landform + arc_deposit·0.50 + craton_deposit` |
| Structural control | `ore_structural_control_index` | `fault·0.24 + seismic·0.16 + transform·0.14 + zone_strength·0.16 + relief·0.08 + (0.08 if boundary_type ∈ {convergent, transform, divergent}) + arc_deposit·0.20 + craton_deposit·0.14` |
| Placer concentration | `placer_concentration_index` | `flow·0.24 + river·0.18 + sediment·0.14 + placer_landform + placer_lithology + placer_deposit + clamp(convergent + fertility·0.5)·0.08` |
| Composite ore potential | `ore_genesis_potential_index` | `max(hydro, fert, placer)·0.34 + hydro·0.20 + fert·0.20 + structural·0.14 + placer·0.12 + (0.12 if resource ∈ ORE_RESOURCES)` |

The `placer` formula's last term reuses the *fertility index computed above it in the same function* (`ore_genesis.py:166`), i.e. metallogenic fertility, not the soil `fertility` field.

### System assembly

1. **Candidacy** (`ore_genesis.py:345-349`): a cell is a candidate if `ore >= 0.34` **or** its native `resource ∈ ORE_RESOURCES`.
2. **Components** (`ore_genesis.py:224-243`): BFS over `cell["neighbors"]` restricted to candidates, seeded from the minimum remaining id; components are returned sorted by `(min(ids), len)`, and member ids are sorted.
3. **Survival filter** (`ore_genesis.py:362-363`): a component is discarded if it contains **no** ore-resource deposit **and** its maximum `ore` is below `HIGH_ORE_THRESHOLD = 0.50`.
4. **Typing** (`_system_type`, `ore_genesis.py:185-221`), see below.
5. **Assignment**: surviving components write `ore_genesis_system_id` onto every member cell; non-members keep the initialised `-1` (`ore_genesis.py:343`, `:437-438`).

### The deposit-type vocabulary

`_system_type` resolves in this exact order:

| Rank | Condition | `system_type` | Tectonic / magmatic / hydrothermal setting |
|---|---|---|---|
| 1 | geothermal-resource count strictly greater than each of the arc/craton/placer counts | `rift_geothermal_hydrothermal` | Divergent or volcanic heat-driven fluid circulation (`boundary_divergent > 0.42` or warm volcanic lithology at the native cascade) |
| 2 | placer count strictly greater than each of the arc/craton/geothermal counts | `fluvial_placer_system` | Mechanical concentration in channels draining a convergent, actively eroding source (`is_river` + `boundary_convergent > 0.16`) |
| 3 | any `craton_iron_gold` present | `ancient_craton_metallogenic` | Archean-analogue craton nucleus, `crust_age_ma > 1800` |
| 4 | any `volcanic_arc_metals` present | `subduction_arc_hydrothermal` | Convergent arc, `boundary_convergent > 0.38` with arc crust or volcanic host |
| 5 | any `geothermal` present | `rift_geothermal_hydrothermal` | Reachable when geothermal ties with another type at rank 1 |
| 6 | no ore deposits: rank means of `hydrothermal`, `fertility`, `placer`; runner-up `>= 0.34` and gap `<= 0.05` | `mixed_metallogenic_province` | Ambiguous province — the model refuses to pick |
| 7 | no ore deposits, unambiguous | `subduction_arc_hydrothermal` \| `ancient_craton_metallogenic` \| `fluvial_placer_system` | Named by the highest mean index; ties broken lexicographically |

There are exactly **five** `system_type` values in the vocabulary. Note what is *absent*: there is no porphyry / VMS / SEDEX / IOCG / epithermal / orogenic-gold vocabulary, no metal speciation, and no distinction between magmatic-hydrothermal and metamorphic-hydrothermal fluids. The five names describe *tectonic settings*, not deposit models in the economic-geology sense.

### Formation steps

`_formation_steps` (`ore_genesis.py:273-320`) attaches a three-step pseudo-paragenesis to every system. Membership per step is `index >= threshold` **or** a resource match:

| Step | `process` | `process_metric` | Membership rule |
|---|---|---|---|
| 0 | `source_fertility` | `metallogenic_fertility` | `metallogenic_fertility_index >= 0.42` or `resource ∈ {volcanic_arc_metals, craton_iron_gold}` |
| 1 (placer systems) | `erosion_transport` | `placer_concentration` | `placer_concentration_index >= 0.32` or `resource == placer_metals` |
| 2 (placer systems) | `placer_concentration` | `placer_concentration` | same rule as step 1 |
| 1 (all other systems) | `hydrothermal_mobilization` | `hydrothermal_alteration` | `hydrothermal_alteration_index >= 0.34` or `resource ∈ {volcanic_arc_metals, geothermal}` |
| 2 (all other systems) | `structural_concentration` | `ore_structural_control` | `ore_structural_control_index >= 0.30` or `resource ∈ {volcanic_arc_metals, craton_iron_gold}` |

If a step selects no cells, it falls back to the whole component (`selected_ids = active_ids or cell_ids`, `ore_genesis.py:256`). Steps carry no time coordinate — `step_index` is an ordering label only, and the model record declares `physical_time_resolved: False`.

Step record fields (`ore_genesis.py:261-270`): `step_index`, `process`, `active_cell_ids`, `active_cell_count`, `linked_resource_deposit_ids`, `mean_ore_genesis_potential_index`, `mean_process_intensity_index`, `process_metric`.

### The ore system record

`ore_genesis.py:388-432`, 30 fields:

| Field | Type | Meaning |
|---|---|---|
| `id` | int | Sequential |
| `system_type` | str | One of the five names above |
| `cell_ids` | int[] | Sorted component membership |
| `cell_count` | int | `len(cell_ids)` |
| `area_km2` | float | Sum of member `area_km2` |
| `centroid_lat_deg`, `centroid_lon_deg` | float | Area-weighted 3-D unit-vector centroid (`ore_genesis.py:46-67`) |
| `representative_cell_id` | int | Highest `ore_genesis_potential_index`, ties by lowest cell id |
| `resource_deposit_ids` | int[] | Ore-resource deposits inside the component, ordered by deposit id |
| `resource_deposit_count` | int | `len(resource_deposit_ids)` |
| `metal_deposit_count` | int | Deposits whose `resource ∈ METAL_RESOURCES` |
| `geothermal_deposit_count` | int | Deposits whose `resource == geothermal` |
| `placer_deposit_count` | int | Deposits whose `resource == placer_metals` |
| `dominant_resource` | str | Most common member `resource`; ties lexicographic; fallback `"none"` |
| `dominant_lithology` | str | Most common member `lithology`; fallback `"unknown"` |
| `dominant_landform` | str | Most common member `landform`; fallback `"unknown"` |
| `dominant_tectonic_context` | str | Most common member `boundary_type`; fallback `"unknown"` |
| `plate_ids` | int[] | Sorted distinct non-negative `plate_id` |
| `tectonic_zone_ids` | int[] | Sorted distinct non-negative ids drawn from `collision_zone_id`, `subduction_zone_id`, `rift_zone_id` |
| `fault_system_ids` | int[] | Sorted distinct non-negative `fault_system_id` |
| `mean_ore_genesis_potential_index` | float | Component mean |
| `max_ore_genesis_potential_index` | float | Component max (drives the survival filter) |
| `mean_hydrothermal_alteration_index` | float | Component mean |
| `mean_metallogenic_fertility_index` | float | Component mean |
| `mean_ore_structural_control_index` | float | Component mean |
| `mean_placer_concentration_index` | float | Component mean |
| `mean_resource_viability_index` | float | Mean `economic_viability_index` of linked deposits; `0.0` when there are none |
| `ore_genesis_confidence_index` | float `[0,1]` | `clamp(mean_ore·0.34 + mean_hydro·0.14 + mean_fert·0.16 + mean_struct·0.12 + clamp(deposits/cells)·0.16 + clamp(plates/3)·0.08)` |
| `formation_step_count` | int | Always 3 |
| `formation_steps` | object[] | The three step records |

> The `tectonic_zone_ids` list deliberately merges collision, subduction and rift zone ids into one flat integer list, so an id in that array is only unambiguous when cross-referenced against the three zone arrays. Subduction polarity itself remains explicitly unresolved upstream — see [Plate Boundary Segment Ledger](plate-boundary-ledger.md).

### Grade and tonnage

There is none. Every ore output is a dimensionless index in `[0,1]`, plus an area in km². No mass, no volume, no ore grade (weight %, g/t), no cut-off grade, no metal endowment, and no depth extent. `area_km2` is the map footprint of the component's cells, not an orebody dimension. The published model record (`ore_genesis.py:444-451`) states the limitation as `"diagnostic metallogenic potential without reactive geochemical transport"` and sets `physical_time_resolved: False`.

---

## Sedimentary resource systems: coal and evaporites

`enrich_world_with_sedimentary_resource_systems` (`src/magic_geo/sedimentary_resource_systems.py:152`) is a per-basin join. It writes no per-cell fields; it produces one record per qualifying native sedimentary basin.

### Inputs joined

| Input | Key | Provider |
|---|---|---|
| Basin geometry and state | `world["sedimentary_basins"]` | Native, `cpp/src/engine/entity_serialization.cpp:533` — fields `id`, `basin_id`, `type`, `dominant_resource`, `cell_count`, `is_active`, `area_km2`, `mean_sediment_thickness_m`, `max_sediment_thickness_m`, `mean_subsidence_index`, `depositional_age_ma` |
| Stratigraphy | `world["stratigraphic_columns"]` | Native, `cpp/src/engine/entity_serialization.cpp:557` — with nested `layers[]` carrying `facies`, `thickness_m`, `organic_potential`, `reservoir_quality`, `seal_quality`, `grain_size_index`, `age_top_ma`, `age_base_ma` |
| Accommodation ratio | `column["mean_accommodation_to_deposition_ratio"]` | Added by the sequence-stratigraphy enricher at `src/magic_geo/sequence_stratigraphy.py:191` — **not** a native field |
| Basin fill trajectory | `world["sediment_transport_histories"]` | `src/magic_geo/sediment_dynamics.py:148-167`, keyed by `basin_id`, field `final_accommodation_fill_fraction` |
| Deposits | `world["resource_deposits"]` filtered to `{sedimentary_fuels, evaporites}` | `sedimentary_resource_systems.py:85-98` |
| Member cells | cells grouped by native `basin_id` | `sedimentary_resource_systems.py:48-54` |

Basins are matched to drainage basins by `basin["basin_id"]`; a basin with `basin_id < 0` or no member cells is skipped (`sedimentary_resource_systems.py:177-182`).

### Member-cell selection

`_system_cells` (`sedimentary_resource_systems.py:101-112`) keeps cells with `sediment_thickness_m > 0`, or a sedimentary lithology, or a sedimentary landform, or a sedimentary-resource assignment; if that filter empties the group it falls back to the entire basin group. Sorted by cell id.

| Set | Members |
|---|---|
| `SEDIMENTARY_LITHOLOGIES` | `shale`, `sandstone`, `limestone` |
| `SEDIMENTARY_LANDFORMS` | `coastal_plain`, `continental_shelf`, `delta`, `floodplain`, `inland_sea`, `lacustrine_basin`, `rift_valley`, `river_valley`, `stable_lowland` |
| `SEDIMENTARY_DEPOSIT_RESOURCES` | `sedimentary_fuels`, `evaporites` |

### Facies sets

`sedimentary_resource_systems.py:21-25` (the wet-organic biome/landform sets used further down are separate, `:26-27`). Facies fractions are thickness-weighted over the column's layers (`_weighted_facies_fraction`, `:130-142`), and layer-quality averages are thickness-weighted too (`_weighted_layer_average`, `:115-127`), with each layer thickness floored at `0.001 m`.

| Set | Facies |
|---|---|
| `ORGANIC_FACIES` | `deep_marine`, `lacustrine_mud`, `floodplain_mud`, `deltaic_sand` |
| `RESERVOIR_FACIES` | `deltaic_sand`, `fluvial_channel`, `shallow_marine`, `alluvial_fan` |
| `SEAL_FACIES` | `deep_marine`, `lacustrine_mud`, `floodplain_mud` |
| `COAL_FACIES` | `deltaic_sand`, `floodplain_mud`, `fluvial_channel`, `lacustrine_mud` |
| `MARINE_FACIES` | `deep_marine`, `shallow_marine`, `deltaic_sand` |

The full native facies vocabulary is nine values (`cpp/src/engine/schema_names.hpp:125`): `alluvial_fan`, `fluvial_channel`, `floodplain_mud`, `deltaic_sand`, `lacustrine_mud`, `evaporite`, `shallow_marine`, `deep_marine`, `glacial_till`. Note that the `evaporite` facies is not a member of any of the five sets above — evaporite potential is scored from cell-level salinity, closed-basin fraction and salt-flat fraction instead, and the column only contributes through the complement `(1 − marine_facies)`.

### Basin-level normalisations

`sedimentary_resource_systems.py:191-197`, plus `age_window` at `:258`:

| Term | Definition |
|---|---|
| `sediment_index` | `clamp(basin.mean_sediment_thickness_m / 8.0)` |
| `subsidence` | `clamp(basin.mean_subsidence_index)` |
| `depositional_age_ma` | `max(0, basin.depositional_age_ma)` |
| `maturity_age` | `clamp(depositional_age_ma / 180.0)` |
| `preservation` | `clamp(column.preservation_potential)`, default `0.45` when no column |
| `accommodation_ratio` | `clamp(column.mean_accommodation_to_deposition_ratio / 1.8)`, default `1.0` before division |
| `final_fill_fraction` | `clamp(history.final_accommodation_fill_fraction / 1.25)` |
| `age_window` | `clamp(1 − abs(maturity_age − 0.55) / 0.55)` — a triangular window peaking at `depositional_age_ma ≈ 99 Ma` |

Deposit evidence is normalised by cell count: `basin_cell_divisor = max(1, basin.cell_count, len(system_cells))`, then `fuel_deposit_evidence = clamp(fuel_count / divisor)` and likewise for evaporites (`sedimentary_resource_systems.py:189, 199-203`).

Cell-derived depositional-condition terms (`sedimentary_resource_systems.py:214-225`):

| Term | Definition |
|---|---|
| `salinity` | mean of `clamp(soil_salinity_index)` over member cells |
| `closed_basin_fraction` | fraction of member cells with `is_closed_basin` true |
| `salt_flat_fraction` | fraction of member cells with `landform == salt_flat` |
| `wet_organic_fraction` | fraction of member cells whose `biome ∈ {wetland, temperate_forest, tropical_seasonal_forest}` **or** `landform ∈ {delta, floodplain, lacustrine_basin, river_valley}` |

### The four petroleum-system elements and the four potentials

`sedimentary_resource_systems.py:226-288`. All clamped `[0,1]`. The `(x or default)` idiom means the default is used when the weighted layer average is exactly `0.0` (no column, or all-zero layers).

| Index | Formula |
|---|---|
| `source_rock_index` | `(layer_organic or 0.35)·0.40 + organic_facies·0.18 + sediment_index·0.14 + subsidence·0.10 + fuel_deposit_evidence·0.12 + (0.06 if basin.dominant_resource == sedimentary_fuels)` |
| `reservoir_quality_index` | `(layer_reservoir or 0.28)·0.50 + reservoir_facies·0.24 + sediment_index·0.10 + marine_facies·0.08 + fuel_deposit_evidence·0.08` |
| `seal_quality_index` | `(layer_seal or 0.30)·0.56 + seal_facies·0.16 + subsidence·0.10 + evaporite_deposit_evidence·0.10 + salinity·0.05 + closed_basin_fraction·0.03` |
| `structural_trap_index` | `subsidence·0.34 + preservation·0.18 + accommodation_ratio·0.14 + final_fill_fraction·0.10 + closed_basin_fraction·0.10 + fuel_deposit_evidence·0.10 + evaporite_deposit_evidence·0.04` |
| `petroleum_potential_index` | `source·0.34 + reservoir·0.24 + seal·0.20 + trap·0.15 + maturity_age·0.07` |
| `gas_potential_index` | `source·0.25 + seal·0.24 + trap·0.18 + sediment_index·0.15 + maturity_age·0.18` |
| `coal_potential_index` | `(layer_organic or 0.35)·0.24 + coal_facies·0.24 + wet_organic_fraction·0.18 + sediment_index·0.12 + fuel_deposit_evidence·0.16 + age_window·0.06` |
| `evaporite_salt_potential_index` | `salinity·0.30 + closed_basin_fraction·0.22 + salt_flat_fraction·0.22 + evaporite_deposit_evidence·0.18 + seal_quality·0.05 + (1 − marine_facies)·0.03` |

**Coal — the depositional conditions required.** Coal potential is high only where the column is dominated by the four `COAL_FACIES` (deltaic sand, floodplain mud, fluvial channel, lacustrine mud), the layers carry organic potential, the member cells are wet-organic (wetland/forest biomes or delta/floodplain/lacustrine/river-valley landforms), and the basin has accumulated sediment. The `age_window` term additionally rewards mid-range depositional ages. No peat-to-rank progression, vitrinite reflectance, coal seam thickness, or ash/sulfur content is modelled.

**Evaporites — the depositional conditions required.** Evaporite/salt potential requires cell-level salinity, endorheic closure (`is_closed_basin`), and salt-flat landforms, plus evaporite deposits already assigned by the native cascade — with a small penalty for marine facies dominance via `(1 − marine_facies)`. This traces back to the native cascade's arid branch (`aridity < 0.45` in a basin lithology) and the unconditional `salt_flat → evaporites` override. No brine chemistry, mineral sequence (gypsum → halite → potash), or evaporation-rate budget is simulated.

### System typing and survival

`_petroleum_system_type` (`sedimentary_resource_systems.py:145-149`) ranks the four potentials; if the runner-up is `>= SEDIMENTARY_SYSTEM_THRESHOLD = 0.42` and within `0.06` of the leader, the type is `mixed_sedimentary_resource`, otherwise it is the leader's key.

| `system_type` | Meaning |
|---|---|
| `petroleum_system` | Oil-leaning basin |
| `gas_system` | Gas-leaning basin |
| `coal_basin` | Coal-leaning basin |
| `evaporite_salt_system` | Salt/evaporite-leaning basin |
| `mixed_sedimentary_resource` | Top two potentials are close and both above 0.42 |

A basin is dropped entirely if `max(potentials) < 0.42` **and** it has no sedimentary deposits (`sedimentary_resource_systems.py:295-297`).

`system_confidence_index` (`:299-308`):

```
clamp( 0.16 + deposit_evidence·0.24 + preservation·0.18
       + clamp(cell_count/12)·0.14 + source·0.10
       + reservoir·0.08 + seal·0.06 + trap·0.04 )
```

### The sedimentary system record

`sedimentary_resource_systems.py:322-350`, 27 fields:

| Field | Type | Meaning |
|---|---|---|
| `id` | int | Sequential |
| `sedimentary_basin_id` | int | Native `sedimentary_basins[].id` |
| `basin_id` | int | Native drainage basin id (the join key) |
| `system_type` | str | Five-value vocabulary above |
| `cell_ids` | int[] | Selected member cells, ascending |
| `cell_count` | int | `len(cell_ids)` |
| `area_km2` | float | Sum of member cell areas |
| `resource_deposit_ids` | int[] | Fuel + evaporite deposits in this basin, by deposit id |
| `resource_deposit_count` | int | `len(resource_deposit_ids)` |
| `sedimentary_fuel_deposit_count` | int | Subset with `resource == sedimentary_fuels` |
| `evaporite_deposit_count` | int | Subset with `resource == evaporites` |
| `mean_sediment_thickness_m` | float | Echoed from the native basin record |
| `mean_subsidence_index` | float | Clamped native basin value |
| `depositional_age_ma` | float | Floored native basin value |
| `source_rock_index` | float | Formula above |
| `reservoir_quality_index` | float | Formula above |
| `seal_quality_index` | float | Formula above |
| `structural_trap_index` | float | Formula above |
| `coal_potential_index` | float | Formula above |
| `petroleum_potential_index` | float | Formula above |
| `gas_potential_index` | float | Formula above |
| `evaporite_salt_potential_index` | float | Formula above |
| `system_confidence_index` | float | Formula above |
| `dominant_lithology` | str | Most common member lithology; count-then-lexicographic |
| `dominant_landform` | str | Most common member landform |
| `stratigraphic_column_id` | int | `-1` when the basin has no column |
| `sediment_transport_history_id` | int | `-1` when the basin has no transport history |

---

## Petroleum systems

`enrich_world_with_petroleum_migration` (`src/magic_geo/petroleum_migration.py:281`) is the only resource enricher that performs an explicit path search (the others do connected-component breadth-first grouping only). It runs per sedimentary resource system, scores five per-cell petroleum indices, then routes least-cost migration paths from source cells to trap cells.

### Constants

`petroleum_migration.py:11-19`:

| Constant | Value | Role |
|---|---|---|
| `SOURCE_ROCK_THRESHOLD` | `0.42` | Source candidacy; also the summary source-cell counter |
| `MATURE_SOURCE_THRESHOLD` | `0.42` | Summary mature-source counter |
| `TRAP_THRESHOLD` | `0.34` | Trap-cell membership and summary trap counter |
| `HIGH_ACCUMULATION_THRESHOLD` | `0.50` | Summary high-accumulation counter |
| `MAX_PATHS_PER_SYSTEM` | `4` | Cap on migration steps per system |
| `SOURCE_LANDFORMS` | `{delta, floodplain, lacustrine_basin, inland_sea, continental_shelf, stable_lowland}` | `+0.10` source bonus |
| `RESERVOIR_LANDFORMS` | `{delta, floodplain, river_valley, coastal_plain, continental_shelf, rift_valley}` | `+0.12` reservoir bonus |
| `SEAL_LANDFORMS` | `{lacustrine_basin, inland_sea, salt_flat, stable_lowland, continental_shelf}` | `+0.10` seal bonus |

All cells are initialised to zeroed defaults with `petroleum_system_id = -1` before any system runs (`petroleum_migration.py:290-296`), so cells outside every fairway carry explicit zeros rather than missing keys.

### Lithology and landform bonuses

`petroleum_migration.py:125-132`:

| Bonus | `shale` | `limestone` | `sandstone` | other |
|---|---|---|---|---|
| `source_lithology` | `0.16` | `0.10` | `0.06` | `0.0` |
| `reservoir_lithology` | `0.04` | `0.12` | `0.18` | `0.0` |
| `seal_lithology` | `0.18` | `0.08` | `0.02` | `0.02` |

Plus `source_landform = 0.10` if `landform ∈ SOURCE_LANDFORMS` **or** `"basin" in landform`; `reservoir_landform = 0.12` if in `RESERVOIR_LANDFORMS`; `seal_landform = 0.10` if in `SEAL_LANDFORMS` **or** `is_closed_basin`; `fuel_evidence = 0.10` if `resource == sedimentary_fuels`; `evaporite_evidence = 0.08` if `resource == evaporites`.

> The `"basin" in landform` clause in `source_landform` (`petroleum_migration.py:128`) adds nothing on engine-generated worlds: the only native landform containing `"basin"` is `lacustrine_basin`, which is already a member of `SOURCE_LANDFORMS`. Reported as observed, not repaired.

### Maturation windows and thermal terms

`petroleum_migration.py:134-137`, driven by the *system's* `depositional_age_ma`:

| Term | Formula | Reading |
|---|---|---|
| `oil_window` | `clamp(1 − abs(age_ma − 95.0) / 130.0)` | Triangular window peaking at 95 Ma, non-zero on `(−35, 225)` Ma |
| `gas_window` | `clamp((age_ma − 55.0) / 185.0)` | Ramp from 55 Ma, saturating at 240 Ma |
| `burial_heat` | `clamp(sediment·0.65 + subsidence·0.22 + (divergent + convergent + volcanic)·0.08)` where `sediment = clamp(sediment_thickness_m/6)` | Burial + tectonic heat proxy |
| `thermal_overprint` | `clamp((seismic + fault_slip + volcanic) / 2.2)` | Over-cooking / structural disturbance proxy |

### The eight computed indices (five of which reach the cells)

`petroleum_migration.py:139-170`. All clamped `[0,1]` **after** the arithmetic, so negative intermediate sums floor at zero.

| Element | Cell field | Formula |
|---|---|---|
| Source rock | `petroleum_source_rock_index` | `system_source·0.42 + sediment·0.18 + source_lithology + source_landform + fuel_evidence + petroleum·0.08` |
| Maturation | `petroleum_maturation_index` | `burial_heat·0.32 + oil_window·0.24 + gas_window·0.12 + subsidence·0.14 + system_source·0.10 + gas·0.08 − max(0, thermal_overprint − 0.70)·0.16` |
| Reservoir | *(not written to cells)* | `system_reservoir·0.46 + reservoir_lithology + reservoir_landform + sediment·0.08 + petroleum·0.08` |
| Seal | *(not written to cells)* | `system_seal·0.50 + seal_lithology + seal_landform + salinity·0.08 + salt·0.08 + evaporite_evidence` |
| Leakage pressure | *(not written to cells)* | `seismic·0.16 + fault_slip·0.14 + volcanic·0.10` |
| Trap integrity | `petroleum_trap_integrity_index` | `system_trap·0.36 + seal·0.26 + reservoir·0.12 + subsidence·0.10 + clamp(1 − erosion_rate/0.08)·0.08 + evaporite_evidence·0.08 − leakage_pressure` |
| Migration pathway | `petroleum_migration_path_index` | `maturation·0.20 + reservoir·0.20 + max(petroleum, gas)·0.20 + source·0.12 + seal·0.08 + trap·0.10 + clamp(1 − leakage_pressure)·0.10` |
| Accumulation | `petroleum_accumulation_index` | `source·0.20 + maturation·0.20 + reservoir·0.18 + seal·0.16 + trap·0.18 + migration·0.08` |

`reservoir`, `seal` and `leakage_pressure` exist only inside the per-system metric dictionary; they surface on records as `mean_reservoir_quality_index`, `mean_seal_quality_index` and inside the step-level `leakage_risk_index`. Because a cell can belong to more than one system's `cell_ids`, the per-cell write is guarded by "highest accumulation wins", with `>=` so a later system overwrites a tie (`petroleum_migration.py:313-320`).

### Source and trap candidacy

`petroleum_migration.py:326-341`:

| Role | Primary rule | Fallback |
|---|---|---|
| Source | `source >= 0.42` **and** `maturation >= 0.36` | If empty: the first single cell (by dict order) with `source >= 0.36`, `maturation >= 0.30`, and system `max(petroleum, gas) >= 0.42` |
| Trap | `trap >= 0.30` **and** `reservoir >= 0.24` **and** `seal >= 0.18` **and** `accumulation >= 0.34` | none |

If either list ends up empty, the system is skipped. Sources are then ranked by descending `source × maturation` (ties by cell id) and traps by descending `accumulation`, then `trap`, then cell id.

### The migration path search

`_best_path` (`petroleum_migration.py:183-223`) is a Dijkstra search over the cell adjacency graph restricted to `allowed_ids = set(system_cell_ids)`, i.e. migration cannot leave the sedimentary system:

```
step_cost(cell → neighbor)
  = 1.0
  + clamp(abs(neighbor.elevation_m − cell.elevation_m) / 3500.0) · 0.20   # relief penalty
  + clamp(neighbor.seismic_hazard_index) · 0.08                            # fault leakage penalty
  − neighbor.migration_index · 0.42                                        # migration-affinity bonus
```

Every edge cost lies in `[0.58, 1.28]`, so weights stay strictly positive and the priority-queue search is well-posed. Path search is bounded by the system's cell set, and at most `3 sources × 4 traps` pairs are tried per system, stopping at `MAX_PATHS_PER_SYSTEM = 4` accepted steps (`petroleum_migration.py:359-383`).

> This is a *least-cost* path over a graph, weighted by an elevation-difference penalty. It is not a buoyancy-driven updip carrier-bed migration solve: there is no capillary entry pressure, no carrier-bed permeability, no fluid phase, no pressure field, and the path is not constrained to be monotonically updip.

An assembled step is rejected if `accumulation_probability_index < 0.34` **and** the system's `max(petroleum, gas) < 0.48` (`petroleum_migration.py:376-377`). A system with zero accepted steps is skipped entirely.

### Migration step record fields

`_step_record` (`petroleum_migration.py:226-264`), 11 fields:

| Field | Type | Definition |
|---|---|---|
| `step_index` | int | Position within `migration_steps` |
| `source_cell_id` | int | Charge origin |
| `target_trap_cell_id` | int | Charge destination |
| `path_cell_ids` | int[] | Ordered cell ids, source first, trap last |
| `path_length_cell_count` | int | `len(path_cell_ids)` |
| `migration_distance_km` | float | Sum of great-circle hops along the path (haversine, `petroleum_migration.py:40-63`), using the configured planet radius via `planet_radius_km(world)` (`src/magic_geo/planet_parameters.py:73`) |
| `mean_path_migration_index` | float | Mean `migration` over path cells |
| `mean_path_trap_integrity_index` | float | Mean `trap` over path cells |
| `hydrocarbon_charge_index` | float | `clamp(src.source·0.30 + src.maturation·0.26 + max(system petroleum, gas)·0.18 + mean_migration·0.18 + trap.accumulation·0.08)` |
| `leakage_risk_index` | float | `clamp(mean_leakage·0.42 + (1 − mean_trap)·0.36 + (1 − mean_seal)·0.18)` |
| `accumulation_probability_index` | float | `clamp(charge·0.44 + mean_migration·0.30 + trap.accumulation·0.26 − leakage·0.22)` |

### Fairway assembly and system typing

The fairway is the union of source, migration-path, reservoir (`reservoir >= 0.42`), seal (`seal >= 0.40`) and trap (`trap >= 0.34`) cells (`petroleum_migration.py:387-413`). If the candidate fairway intersects an already-assigned fairway, the whole system is skipped — fairways are disjoint by construction.

`_system_type` (`petroleum_migration.py:267-278`), resolved in order:

| Rank | Condition | `system_type` |
|---|---|---|
| 1 | `mean_source >= 0.42` and `mean_maturation < 0.34` | `immature_source_basin` |
| 2 | mean step `leakage_risk >= 0.58` | `breached_trap_complex` |
| 3 | `gas > petroleum + 0.04` **or** `mean_maturation >= 0.68` | `gas_migration_fairway` |
| 4 | `abs(petroleum − gas) <= 0.05` | `mixed_hydrocarbon_fairway` |
| 5 | fall-through | `oil_migration_fairway` |

`confidence_index` (`petroleum_migration.py:433-441`):

```
clamp( system_confidence·0.30 + mean_source·0.14 + mean_maturation·0.14
       + mean_migration·0.16 + mean_trap·0.16
       + clamp(step_count/4)·0.10 − leakage_risk·0.10 )
```

### The petroleum migration record

`petroleum_migration.py:450-491`, 40 fields:

| Field | Type | Meaning |
|---|---|---|
| `id` | int | Sequential |
| `sedimentary_resource_system_id` | int | Parent system |
| `sedimentary_basin_id` | int | Native basin record id |
| `basin_id` | int | Native drainage basin id |
| `system_type` | str | Five-value vocabulary above |
| `cell_ids` | int[] | Full fairway, ascending |
| `cell_count` | int | `len(cell_ids)` |
| `area_km2` | float | Sum of fairway cell areas |
| `centroid_lat_deg`, `centroid_lon_deg` | float | Area-weighted unit-vector centroid |
| `source_cell_ids`, `source_cell_count` | int[], int | Source candidates with `source >= 0.42`, plus every cell that is a step source, restricted to the fairway (`petroleum_migration.py:388-394`) |
| `migration_cell_ids`, `migration_cell_count` | int[], int | Union of all path cells |
| `reservoir_cell_ids`, `reservoir_cell_count` | int[], int | `reservoir >= 0.42` |
| `seal_cell_ids`, `seal_cell_count` | int[], int | `seal >= 0.40` |
| `trap_cell_ids`, `trap_cell_count` | int[], int | `trap >= 0.34` |
| `resource_deposit_ids` | int[] | Parent system deposits filtered to `sedimentary_fuels` only |
| `sedimentary_fuel_deposit_count` | int | `len(resource_deposit_ids)` |
| `stratigraphic_column_id` | int | Inherited from the parent system |
| `sediment_transport_history_id` | int | Inherited from the parent system |
| `mean_source_rock_index` | float | Fairway mean |
| `mean_maturation_index` | float | Fairway mean |
| `mean_migration_path_index` | float | Fairway mean |
| `mean_reservoir_quality_index` | float | Fairway mean |
| `mean_seal_quality_index` | float | Fairway mean |
| `mean_trap_integrity_index` | float | Fairway mean |
| `mean_accumulation_index` | float | Fairway mean |
| `petroleum_potential_index` | float | Echoed from parent system |
| `gas_potential_index` | float | Echoed from parent system |
| `migration_efficiency_index` | float | Mean step `accumulation_probability_index` |
| `leakage_risk_index` | float | Mean step `leakage_risk_index` |
| `confidence_index` | float | Formula above |
| `dominant_lithology` | str | Count-then-lexicographic over fairway cells |
| `dominant_landform` | str | Count-then-lexicographic over fairway cells |
| `path_step_count` | int | `len(migration_steps)`, at most 4 |
| `migration_steps` | object[] | The 11-field step records above |

---

## Commodity occurrences

`enrich_world_with_commodity_occurrences` (`src/magic_geo/commodity_resources.py:195`) fans each deposit out into one record per commodity that the deposit's resource can host. It writes no per-cell fields.

### Deposit → commodity mapping

`COMMODITY_BY_RESOURCE` (`commodity_resources.py:7-16`). Commodity names are emitted sorted within each deposit.

| Native resource | Commodities |
|---|---|
| `volcanic_arc_metals` | `copper`, `gold`, `silver`, `sulfide_ore` |
| `craton_iron_gold` | `diamond`, `gold`, `iron` |
| `sedimentary_fuels` | `coal`, `natural_gas`, `petroleum` |
| `evaporites` | `gypsum`, `potash`, `salt` |
| `placer_metals` | `placer_gold`, `tin` |
| `geothermal` | `geothermal_heat`, `obsidian`, `sulfur` |
| `fertile_alluvium` | `fertile_soils` |
| `coastal_fisheries` | `fishery_biomass` |

19 commodities total. A deposit whose resource is absent from this map (only possible for a non-enum value) produces no occurrence records (`commodity_resources.py:215-217`).

### Commodity group and market value

`COMMODITY_GROUPS` (`commodity_resources.py:18-38`) and `COMMODITY_VALUE_INDEX` (`commodity_resources.py:40-60`):

| Commodity | `commodity_group` | `market_value_index` |
|---|---|---|
| `gold` | `precious_metal` | `0.92` |
| `diamond` | `gemstone` | `0.88` |
| `placer_gold` | `precious_metal` | `0.86` |
| `copper` | `base_metal` | `0.78` |
| `petroleum` | `fuel` | `0.76` |
| `sulfide_ore` | `base_metal` | `0.74` |
| `silver` | `precious_metal` | `0.72` |
| `potash` | `industrial_mineral` | `0.70` |
| `natural_gas` | `fuel` | `0.68` |
| `tin` | `base_metal` | `0.66` |
| `fertile_soils` | `agricultural` | `0.64` |
| `iron` | `ferrous_metal` | `0.64` |
| `geothermal_heat` | `geothermal` | `0.62` |
| `fishery_biomass` | `fishery` | `0.58` |
| `coal` | `fuel` | `0.50` |
| `sulfur` | `industrial_mineral` | `0.48` |
| `gypsum` | `industrial_mineral` | `0.42` |
| `salt` | `industrial_mineral` | `0.38` |
| `obsidian` | `volcanic_material` | `0.36` |

`market_value_index` is a hard-coded constant table with no supply, demand, transport-cost, or era dependence. It is a static ranking, not a price.

### Base index vector

`_base_indices` (`commodity_resources.py:115-130`) re-clamps five deposit indices and seven cell-derived terms:

| Key | Source |
|---|---|
| `reserve`, `confidence`, `accessibility`, `hazard`, `viability` | The parent deposit's four indices plus viability |
| `convergent`, `divergent`, `volcanic` | `boundary_convergent`, `boundary_divergent`, `volcanic_potential_index` |
| `crust_age` | `clamp(crust_age_ma / 3000.0)` — note the **3000 Ma** scale here, versus 2500 Ma in `resource_dynamics` and `ore_genesis` |
| `flow` | `clamp(flow_accumulation / 600_000_000.0)` — a fixed absolute scale, **not** the p95 normalisation used upstream |
| `salinity`, `sediment`, `fertility` | `soil_salinity_index`, `clamp(sediment_thickness_m / 8.0)`, `fertility` |

### Occurrence potential formulas

`_commodity_potential` (`commodity_resources.py:133-192`). All clamped `[0,1]`.

| Commodity | Formula |
|---|---|
| `copper` | `reserve·0.42 + convergent·0.30 + volcanic·0.18 + confidence·0.10` |
| `gold` | `reserve·0.36 + max(crust_age, convergent)·0.26 + confidence·0.22 + flow·0.08` |
| `silver` | `reserve·0.34 + convergent·0.28 + volcanic·0.16 + confidence·0.16` |
| `sulfide_ore` | `reserve·0.34 + convergent·0.28 + volcanic·0.22 + (0.08 if crust_type == volcanic_arc)` |
| `iron` | `reserve·0.38 + crust_age·0.30 + (0.18 if crust_type == craton) + confidence·0.14` |
| `diamond` | `reserve·0.28 + crust_age·0.34 + (0.24 if crust_type == craton) + (0.08 if lithology == granite)` |
| `coal` | `reserve·0.28 + system.coal_potential_index·0.50 + sediment·0.12 + confidence·0.10` |
| `petroleum` | `reserve·0.24 + system.petroleum_potential_index·0.54 + sediment·0.10 + confidence·0.12` |
| `natural_gas` | `reserve·0.24 + system.gas_potential_index·0.56 + sediment·0.10 + confidence·0.10` |
| `salt` | `reserve·0.34 + salinity·0.26 + system.evaporite_salt_potential_index·0.22 + (0.12 if landform == salt_flat)` |
| `gypsum` | `reserve·0.42 + salinity·0.22 + sediment·0.16 + confidence·0.14` |
| `potash` | `reserve·0.36 + salinity·0.30 + sediment·0.12 + confidence·0.16` |
| `placer_gold` | `reserve·0.34 + flow·0.34 + convergent·0.16 + (0.08 if is_river)` |
| `tin` | `reserve·0.34 + flow·0.24 + convergent·0.16 + sediment·0.10 + confidence·0.10` |
| `geothermal_heat` | `reserve·0.36 + max(divergent, convergent)·0.30 + volcanic·0.22 + confidence·0.10` |
| `sulfur` | `reserve·0.26 + max(divergent, convergent)·0.22 + volcanic·0.30 + (0.10 if landform == volcanic_arc)` |
| `obsidian` | `reserve·0.20 + volcanic·0.38 + divergent·0.16 + (0.18 if lithology ∈ {volcanic, basalt}) + (0.08 if landform ∈ {volcanic_arc, rift_valley})` |
| `fertile_soils` | `reserve·0.24 + fertility·0.42 + (0.16 if landform ∈ {floodplain, delta, river_valley}) + confidence·0.12` |
| `fishery_biomass` | `reserve·0.30 + (0.24 if water_body ∈ {ocean, continental_shelf, inland_sea}) + (0.16 if water_body == continental_shelf) + confidence·0.18 + fishery_productivity_index·0.20` |
| *(fall-through)* | `reserve·0.70 + confidence·0.30` if `resource != "none"`, else `0.0` |

The three fuel commodities are the only ones whose dominant weight comes from a *basin-level* index rather than the cell deposit — this is exactly how coal, oil and gas inherit the sedimentary-system chain.

### How occurrences relate to deposits

The relationship is strict and one-directional:

| Property | Behaviour |
|---|---|
| Cardinality | 1 deposit → 1..4 occurrences (exactly `len(COMMODITY_BY_RESOURCE[resource])`) |
| Back-link | `resource_deposit_id` is the parent deposit's `id`; `cell_id`, `basin_id`, `political_region_id`, `culture_region_id`, `formation_process`, `host_crust_type`, `host_lithology`, `landform`, `area_km2`, `accessibility_index`, `extraction_hazard_index` are copied verbatim from the deposit |
| Area | Every occurrence carries the **full** deposit `area_km2`, so `commodity_occurrence_total_area_km2` multiply-counts the same cells |
| Sedimentary context | Attached only when the deposit's `basin_id` matches a sedimentary system; the system chosen per basin is the highest `system_confidence_index` (`commodity_resources.py:71-86`) |
| Confidence | Recomputed: `clamp(deposit.geologic_confidence_index·0.54 + potential·0.30 + deposit.reserve_potential_index·0.16)` (`commodity_resources.py:223-227`) |
| High-potential flag | `occurrence_potential_index >= 0.62` increments `high_potential_commodity_occurrence_count` |

### Occurrence record

`commodity_resources.py:238-259`, 20 fields: `id`, `resource_deposit_id`, `cell_id`, `commodity`, `commodity_group`, `source_resource`, `formation_process`, `host_crust_type`, `host_lithology`, `landform`, `basin_id`, `political_region_id`, `culture_region_id`, `area_km2`, `occurrence_potential_index`, `market_value_index`, `accessibility_index`, `extraction_hazard_index`, `geologic_confidence_index`, `formation_evidence`.

The occurrence-level `formation_evidence` (`commodity_resources.py:89-112`) always carries nine fields — `boundary_type`, `boundary_convergent`, `boundary_divergent`, `volcanic_potential_index`, `crust_age_ma`, `sediment_thickness_m`, `flow_accumulation`, `salinity_index`, `fertility` — preferring the deposit's evidence block and falling back to the live cell. When a sedimentary system was matched, five more keys are appended: `sedimentary_resource_system_id`, `petroleum_potential_index`, `gas_potential_index`, `coal_potential_index`, `evaporite_salt_potential_index`.

---

## Land use zones and agricultural zoning

`enrich_world_with_land_use_zones` is the only resource-layer enricher that is **not** run in geo-only mode. Fresh full worlds publish v2: four numeric/id fields, four availability booleans and two zone arrays. Exact declared v1 archives retain their original behavior. Earlier source line numbers below identify the unchanged historical equations; [the v2 contract review](../../agricultural_availability_review.md) records current publication and validation.

| Availability field | V2 meaning |
|---|---|
| `agricultural_habitat_applicable` | Exposed land: neither `is_water`, `is_lake`, nor an ocean/shelf/inland-sea/fresh-lake category |
| `agricultural_climate_supported` | Finite nonboolean annual air temperature strictly in (-9, 43)°C, independently of habitat |
| `agricultural_potential_supported` | Applicable habitat, supported own climate proxy and available typed consumed descriptors |
| `mining_surface_applicable` | Exposed land only; no complete economic-access or mine-capacity claim |

Unsupported agriculture carries numeric zero, support=false and zone ID -1. Supported zero remains a visible valid value. Surface-inapplicable mining also has no zone, while material resource labels and deposits remain intact. V2 requires explicit reciprocal neighbour lists, primary-resource categories, and deposit/settlement/route collections with valid links. Explicit empty collections are valid; omitted inputs cannot silently erase candidates or links.

### Agricultural potential

`_agricultural_potential` retains the historical weighted equation below. The v2 wrapper evaluates it only on supported exposed land; unsupported cells receive zero with a false support flag. The retained fresh-lake term is inapplicable on aquatic v2 cells and is not transferred to neighbouring land.

| Term | Definition | Weight |
|---|---|---|
| `fertility` | `clamp(fertility)` | `+0.27` |
| `soil_depth` | `clamp(soil_depth_m / 3.2)` | `+0.14` |
| `soil_moisture` | `clamp(soil_moisture_index)` | `+0.15` |
| `climate` | `clamp(1 − abs(temperature_c − 17.0)/26.0)` | `+0.14` |
| `growing` | `clamp(growing_season_months / 10.0)` | `+0.12` |
| `water` | `clamp(runoff_mm_y/650 + (0.20 if is_river) + (0.16 if water_body_type == fresh_lake) + clamp(groundwater_recharge_mm_y/300)·0.18)` | `+0.12` |
| `alluvial` | `0.18` if `landform ∈ {floodplain, delta, river_valley, coastal_plain, lacustrine_basin}` | flat |
| `biome_bonus` | `0.10` if `biome ∈ {temperate_forest, temperate_grassland, tropical_seasonal_forest, savanna, wetland}` | flat |
| `salinity_penalty` | `clamp(soil_salinity_index)` | `−0.18` |
| `erosion_penalty` | `clamp(soil_erodibility_index·0.5 + erosion_rate/140.0)` | `−0.10` |
| `ice_penalty` | `clamp(ice_thickness_m / 400.0)` | `−0.22` |
| `aridity_penalty` | `clamp(seasonal_aridity_index)·0.12` | `−1.0` (the 0.12 is inside the term) |

Inputs span the native engine plus four upstream enricher layers: native (`fertility`, `runoff_mm_y`, `erosion_rate`, `ice_thickness_m`, `is_river`, `is_water`, `water_body_type`, `landform`, `biome`, `temperature_c`, `soil_depth_m`), soils (`soil_moisture_index`, `soil_salinity_index`, `soil_erodibility_index`, `src/magic_geo/soil_dynamics.py`), biome diagnostics (`growing_season_months`, `src/magic_geo/biome_dynamics.py`), climate (`seasonal_aridity_index`, `src/magic_geo/climate_dynamics.py`), and groundwater (`groundwater_recharge_mm_y`, `src/magic_geo/aquifer_resources.py`).

### Mining potential

`_mining_potential` retains the equation below. The v2 wrapper first excludes standing water, independently of agricultural climate support. The equation also returns `0.0` for any cell whose `resource ∉ MINING_RESOURCES` — that set is the six non-bioproductive resources: `volcanic_arc_metals`, `craton_iron_gold`, `sedimentary_fuels`, `evaporites`, `placer_metals`, `geothermal` (`land_use_zones.py:10-17`). `fertile_alluvium` and `coastal_fisheries` are structurally excluded from mining.

```
geology = clamp( convergent·0.26 + divergent·0.20 + volcanic_potential·0.18
                 + clamp(sediment_thickness_m/3.0)·0.18
                 + clamp(crust_age_ma/2500.0)·0.18 )

mining  = clamp( deposit.reserve·0.28 + deposit.viability·0.24
                 + deposit.confidence·0.18 + deposit.accessibility·0.12
                 + geology·0.10 + settlement_score·0.08
                 − deposit.hazard·0.12 )
```

If a mining-eligible cell has no deposit record, all five deposit terms default to `0.0` and only `geology·0.10 + settlement_score·0.08` survive — which cannot reach the `0.52` threshold.

### Zoning

`land_use_zones.py:234-256`:

| Zone | Threshold constant | Value | Candidate rule |
|---|---|---|---|
| Agricultural | `AGRICULTURAL_THRESHOLD` | `0.58` | raw (pre-rounding) `agricultural >= 0.58` |
| Mining | `MINING_THRESHOLD` | `0.52` | raw (pre-rounding) `mining >= 0.52` |

Candidates are grouped by BFS over `neighbors` restricted to candidates, seeded from the minimum remaining id (`_connected_components`, `land_use_zones.py:106-128`); component member lists are sorted by cell id. Zone ids are assigned in component discovery order, independently per zone type. Non-member cells keep `agricultural_zone_id = -1` / `mining_zone_id = -1`.

The published model explicitly names the threshold semantics `raw_pre_serialization_greater_than_or_equal_v1` (`land_use_zones.py:275`): the comparison uses the unrounded float, while `cell["agricultural_potential_index"]` and `cell["mining_potential_index"]` are stored rounded to 6 decimals. A replaying consumer must reproduce the raw value, not the stored one.

### Zone record

`land_use_zones.py:186-200`, 13 fields. Agricultural zones are published to `world["agricultural_zones"]` and mining zones to `world["mining_zones"]` (`land_use_zones.py:330-331`); `id` restarts at `0` in each array.

| Field | Type | Meaning |
|---|---|---|
| `id` | int | Sequential within its own zone array |
| `zone_type` | str | `agricultural` or `mining` |
| `cell_count` | int | Component size |
| `cell_ids` | int[] | Ascending |
| `area_km2` | float | Sum of member cell areas |
| `mean_potential_index` | float | Mean of the corresponding potential field over members |
| `mean_fertility_index` | float | Mean clamped `fertility` |
| `dominant_resource` | str | Count-then-lexicographic; fallback `"none"` |
| `dominant_landform` | str | Count-then-lexicographic; fallback `"unknown"` |
| `dominant_biome` | str | Count-then-lexicographic; fallback `"unknown"` |
| `settlement_ids` | int[] | Settlements located on member cells |
| `route_ids` | int[] | Routes incident to those settlements (`from`/`to`) |
| `resource_deposit_ids` | int[] | One deposit id per member cell that has a deposit |

### `world["land_use_zone_model"]`

`land_use_zones.py` publishes the full parameter set as data — fresh `model_type = causal_soil_climate_resource_connected_land_use_zones_v2` (exact historical v1 retained), `deterministic: True`, both thresholds, `threshold_semantics`, `cell_index_serialization_decimals: 6`, the 23-key `agricultural_parameters` block, the 14-key `mining_parameters` block, the sorted `agricultural_landforms`/`agricultural_biomes`/`mining_resources` lists, `component_model = candidate_induced_mesh_components_min_cell_breadth_first_v1`, `record_order = agricultural_then_mining_components_by_minimum_cell_id_v1`, `dominant_field_model = count_then_lexicographic_order_v1`, `record_link_model = member_cell_settlement_route_and_primary_resource_deposit_links_v1`, and

```
model_limitation:
  "diagnostic_static_potential_and_connected_zones_without_land_market_
   crop_mine_capacity_or_development_feedback"
```

---

## Renewable resource records

`world["renewable_resource_records"]` is a required output of the `natural_resources` layer contract, but it is produced earlier by the ecosystem enricher (`src/magic_geo/ecosystem_dynamics.py:204-241`), not by any module on this page. One record per cell that qualifies:

| Rule | Effect |
|---|---|
| `forest_growth_index >= 0.25` | `resource_type = forest_growth`, `productivity = forest_growth` |
| `fishery_productivity_index >= 0.35` and `>= productivity` | overrides to `resource_type = fishery_productivity` |
| neither | no record |

Record fields (12): `id`, `cell_id`, `resource_type`, `biome`, `water_body_type`, `productivity_index`, `sustainable_yield_index`, `regeneration_years`, `climate_dependency_index`, `water_dependency_index`, `disturbance_risk_index`, `formation_evidence` (6 keys: `primary_productivity_index`, `vegetation_biomass_index`, `forest_growth_index`, `fishery_productivity_index`, `runoff_mm_y`, `soil_moisture_index`).

`sustainable_yield_index = clamp(productivity·0.56 + primary·0.20 + biomass·0.14 − disturbance·0.18)`; `regeneration_years = max(1, round(recovery_years × 0.35))` for fisheries and `max(1, round(recovery_years))` for forests. See [Biomes, Ecosystems and Disturbance](biomes-and-ecology.md).

---

## Commodity cross-reference

Every commodity, the model that produces its potential index, and the geological precondition chain that must hold for it to exist at all. "Native precondition" is the `derive_soils_biomes_resources` / `derive_landforms` predicate that must fire for the parent deposit to be created.

| Commodity | Group | Producing model(s) | Parent resource | Native precondition (must be true for any occurrence) | Dominant secondary driver |
|---|---|---|---|---|---|
| `copper` | `base_metal` | `commodity_resources` on `resource_deposits`; province context from `ore_genesis` | `volcanic_arc_metals` | `boundary_convergent > 0.38` **and** (`crust_type == volcanic_arc` **or** `lithology == volcanic`) | `boundary_convergent` (0.30) + `volcanic_potential_index` (0.18) |
| `gold` | `precious_metal` | `commodity_resources`; `ore_genesis` | `volcanic_arc_metals` **or** `craton_iron_gold` | arc predicate above, **or** `crust_type == craton` and `crust_age_ma > 1800` | `max(crust_age, convergent)` (0.26) |
| `silver` | `precious_metal` | `commodity_resources`; `ore_genesis` | `volcanic_arc_metals` | arc predicate | `boundary_convergent` (0.28) |
| `sulfide_ore` | `base_metal` | `commodity_resources`; `ore_genesis` | `volcanic_arc_metals` | arc predicate | `boundary_convergent` (0.28) + `volcanic` (0.22) + `crust_type == volcanic_arc` (0.08) |
| `iron` | `ferrous_metal` | `commodity_resources`; `ore_genesis` | `craton_iron_gold` | `crust_type == craton` **and** `crust_age_ma > 1800` | `crust_age` (0.30) + craton flag (0.18) |
| `diamond` | `gemstone` | `commodity_resources`; `ore_genesis` | `craton_iron_gold` | craton predicate | `crust_age` (0.34) + craton flag (0.24) + `lithology == granite` (0.08) |
| `placer_gold` | `precious_metal` | `commodity_resources`; `ore_genesis` (placer index) | `placer_metals` | `is_river` **and** `boundary_convergent > 0.16`, **or** `alluvial_fan` landform with `boundary_convergent > 0.10` and no prior assignment | `flow_accumulation` (0.34) |
| `tin` | `base_metal` | `commodity_resources`; `ore_genesis` | `placer_metals` | placer predicate | `flow_accumulation` (0.24) |
| `geothermal_heat` | `geothermal` | `commodity_resources`; `ore_genesis` (`rift_geothermal_hydrothermal`) | `geothermal` | `boundary_divergent > 0.42` **or** (`lithology == volcanic` **and** `temperature_c > 0`) | `max(divergent, convergent)` (0.30) |
| `sulfur` | `industrial_mineral` | `commodity_resources`; `ore_genesis` | `geothermal` | geothermal predicate | `volcanic_potential_index` (0.30) |
| `obsidian` | `volcanic_material` | `commodity_resources` | `geothermal` | geothermal predicate | `volcanic_potential_index` (0.38) + volcanic/basalt lithology (0.18) |
| `coal` | `fuel` | `sedimentary_resource_systems` → `commodity_resources` | `sedimentary_fuels` | basin lithology/thickness predicate **and** `aridity >= 0.45` | `coal_potential_index` (0.50) — requires coal facies, wet-organic cells, sediment |
| `petroleum` | `fuel` | `sedimentary_resource_systems` → `petroleum_migration` → `commodity_resources` | `sedimentary_fuels` | same, plus a surviving sedimentary system in that basin | `petroleum_potential_index` (0.54) — source + reservoir + seal + trap + maturity |
| `natural_gas` | `fuel` | `sedimentary_resource_systems` → `petroleum_migration` → `commodity_resources` | `sedimentary_fuels` | same | `gas_potential_index` (0.56) — source + seal + trap + thickness + maturity |
| `salt` | `industrial_mineral` | `sedimentary_resource_systems` → `commodity_resources` | `evaporites` | basin predicate with `aridity < 0.45`, **or** unconditional `landform == salt_flat` | `soil_salinity_index` (0.26) + `evaporite_salt_potential_index` (0.22) + salt-flat flag (0.12) |
| `gypsum` | `industrial_mineral` | `commodity_resources` | `evaporites` | same | `soil_salinity_index` (0.22) |
| `potash` | `industrial_mineral` | `commodity_resources` | `evaporites` | same | `soil_salinity_index` (0.30) |
| `fertile_soils` | `agricultural` | `commodity_resources`; zoning via `land_use_zones` | `fertile_alluvium` | `soil_type == alluvial` **and** `fertility > 0.62`, **or** delta/floodplain landform with `fertility > 0.64` | `fertility` (0.42) + alluvial landform (0.16) |
| `fishery_biomass` | `fishery` | `commodity_resources`; productivity from `ecosystem_dynamics` | `coastal_fisheries` | water cell with an ocean neighbour **or** `water_body == continental_shelf` | marine + shelf bonuses (0.24 + 0.16) + `fishery_productivity_index` (0.20) |

Cross-cutting: `ore_genesis` also assigns a five-value province type to metal- and geothermal-bearing regions; `land_use_zones` gates any commodity into a **mining zone** only if its parent resource is in `MINING_RESOURCES` (all except `fertile_alluvium` and `coastal_fisheries`).

---

## Per-cell fields written by the resource layer

| Field | Written by | Range / sentinel | Notes |
|---|---|---|---|
| `ore_genesis_potential_index` | `ore_genesis.py:338` | `[0,1]`, 6 dp | Every cell |
| `hydrothermal_alteration_index` | `ore_genesis.py:339` | `[0,1]`, 6 dp | Every cell |
| `metallogenic_fertility_index` | `ore_genesis.py:340` | `[0,1]`, 6 dp | Every cell |
| `ore_structural_control_index` | `ore_genesis.py:341` | `[0,1]`, 6 dp | Every cell |
| `placer_concentration_index` | `ore_genesis.py:342` | `[0,1]`, 6 dp | Every cell |
| `ore_genesis_system_id` | `ore_genesis.py:343`, `:438` | `-1` when unassigned | Every cell |
| `petroleum_source_rock_index` | `petroleum_migration.py:291`, `:316` | `[0,1]`, 6 dp; `0.0` outside systems | Every cell |
| `petroleum_maturation_index` | `petroleum_migration.py:292`, `:317` | as above | Every cell |
| `petroleum_migration_path_index` | `petroleum_migration.py:293`, `:318` | as above | Every cell |
| `petroleum_trap_integrity_index` | `petroleum_migration.py:294`, `:319` | as above | Every cell |
| `petroleum_accumulation_index` | `petroleum_migration.py:295`, `:320` | as above | Every cell |
| `petroleum_system_id` | `petroleum_migration.py:296`, `:496` | `-1` when outside every fairway | Every cell |
| `agricultural_potential_index` | `land_use_zones.py:227` | `[0,1]`, 6 dp; unsupported v2 zero has a false support flag | Full world only |
| `mining_potential_index` | `land_use_zones.py:228` | `[0,1]`, 6 dp; `0.0` on surface-inapplicable cells or ineligible resources | Full world only |
| `agricultural_zone_id` | `land_use_zones.py:229`, `:167` | `-1` when unassigned | Full world only |
| `mining_zone_id` | `land_use_zones.py:230`, `:167` | `-1` when unassigned | Full world only |

These derived numeric fields exist after Python enrichment. Current resource/commodity stages also publish biological availability flags, and land-use v2 appends the four booleans listed above. Their flags accompany the values in CSV and determine unavailable display values without erasing raw geological records.

---

## Summary keys

All keys below are added to `world["summary"]` by the Python enrichers; none belong to the native `summary_json` block.

### `resource_dynamics` (10 keys, `resource_dynamics.py:219-228`)

| Key | Definition |
|---|---|
| `resource_deposit_count` | Number of deposit records |
| `metal_resource_deposit_count` | Deposits with `deposit_class == metal` |
| `energy_resource_deposit_count` | `deposit_class == energy` |
| `agricultural_resource_deposit_count` | `deposit_class == bioproductive` (note the name/class mismatch) |
| `high_viability_resource_deposit_count` | `economic_viability_index >= 0.65` |
| `resource_deposit_total_area_km2` | Sum of deposit cell areas |
| `mean_resource_reserve_potential_index` | Mean over deposits; `0.0` when empty |
| `mean_resource_economic_viability_index` | Mean over deposits; `0.0` when empty |
| `mean_resource_geologic_confidence_index` | Mean over deposits; `0.0` when empty |
| `resource_deposit_class_counts` | Sorted `{deposit_class: count}` map |

### `ore_genesis` (14 keys, `ore_genesis.py:452-483`)

`ore_genesis_system_count`, `ore_genesis_cell_count` (cells with `ore_genesis_system_id >= 0`), `ore_resource_deposit_count`, `high_ore_genesis_potential_cell_count` (`>= 0.50`), `high_hydrothermal_alteration_cell_count` (`>= 0.34`), `high_metallogenic_fertility_cell_count` (`>= 0.42`), `high_placer_concentration_cell_count` (`>= 0.32`), `ore_genesis_total_area_km2`, `mean_ore_genesis_potential_index`, `mean_hydrothermal_alteration_index`, `mean_metallogenic_fertility_index`, `mean_ore_structural_control_index`, `mean_placer_concentration_index` (all five means are over **all** cells, not just system members), `ore_genesis_system_type_counts`.

### `sedimentary_resource_systems` (13 keys, `sedimentary_resource_systems.py:356-368`)

`sedimentary_resource_system_count`, `petroleum_system_count`, `coal_system_count`, `gas_system_count`, `evaporite_salt_system_count` (these four count `system_type` occurrences; `mixed_sedimentary_resource` has no dedicated counter), `sedimentary_resource_system_cell_count` (unique member cell ids), `sedimentary_resource_system_total_area_km2`, `mean_petroleum_potential_index`, `mean_gas_potential_index`, `mean_coal_potential_index`, `mean_evaporite_salt_potential_index`, `mean_sedimentary_resource_confidence_index` (all means over systems), `sedimentary_resource_system_type_counts`.

### `petroleum_migration` (13 keys, `petroleum_migration.py:501-535`)

`petroleum_migration_system_count`, `petroleum_migration_cell_count`, `petroleum_source_rock_cell_count` (`petroleum_source_rock_index >= 0.42`), `petroleum_mature_source_cell_count` (source `>= 0.42` **and** maturation `>= 0.42`), `petroleum_trap_cell_count` (`>= 0.34`), `high_petroleum_accumulation_cell_count` (`>= 0.50`), `petroleum_migration_total_area_km2`, `mean_petroleum_source_rock_index`, `mean_petroleum_maturation_index`, `mean_petroleum_migration_path_index`, `mean_petroleum_trap_integrity_index`, `mean_petroleum_accumulation_index` (means over **all** cells), `petroleum_migration_system_type_counts`.

### `commodity_resources` (13 keys, `commodity_resources.py:265-279`)

`commodity_occurrence_count`, `metallic_commodity_occurrence_count` (sum of `base_metal + ferrous_metal + precious_metal`), `fuel_commodity_occurrence_count`, `industrial_mineral_commodity_occurrence_count`, `gemstone_commodity_occurrence_count`, `geothermal_commodity_occurrence_count`, `bioproductive_commodity_occurrence_count` (`agricultural + fishery`), `high_potential_commodity_occurrence_count` (`>= 0.62`), `commodity_occurrence_total_area_km2`, `mean_commodity_occurrence_potential_index`, `mean_commodity_occurrence_confidence_index`, `commodity_occurrence_type_counts`, `commodity_occurrence_group_counts`. Note that `volcanic_material` (obsidian) is counted in neither the metallic, fuel, industrial-mineral, gemstone, geothermal, nor bioproductive rollups.

### `land_use_zones` (9 historical keys plus 6 v2 availability metrics)

`agricultural_zone_count`, `agricultural_zone_cell_count`, `agricultural_zone_total_area_km2`, `mean_agricultural_potential_index` (mean over **all** cells, using the raw pre-rounding values), `mining_zone_count`, `mining_zone_cell_count`, `mining_zone_total_area_km2`, `mean_mining_potential_index`, `land_use_zone_model`.

V2 also publishes the four availability-field `_cell_count` metrics, `agricultural_potential_supported_area_km2` and `unsupported_terrestrial_agricultural_cell_count`. The legacy means remain over all cells, including unavailable zero sentinels; the counts/area explain their coverage. Worldbuilding and the economy do not consume these zone scores: native regional agricultural capacity is a separate model.

---

## Worked example: one arc cell, end to end

This is a hand evaluation of the published formulas, not the output of an observed run. Take a land cell with:

```
resource                 = volcanic_arc_metals
boundary_convergent      = 0.60      boundary_transform      = 0.00
landform                 = volcanic_arc
crust_type               = volcanic_arc
elevation_m              = 2400
settlement_score         = 0.30
is_river                 = false     water_body_type         = land
ice_thickness_m          = 0.0
seasonal_aridity_index   = 0.20      soil_salinity_index     = 0.05
volcanic_potential_index = 0.55
```

**1. Deposit** (`resource_dynamics`):

```
reserve       = clamp(0.34 + 0.60·0.42 + 0.18)                       = 0.772
accessibility = clamp(0.28 + 0.30·0.42 + 0.00 − (2400/3000)·0.20)    = 0.246
hazard        = clamp(0.60·0.42) + (2400/3600)·0.20
              + 0·0.20 + 0.20·0.10 + 0.05·0.08                        = 0.409333
evidence      = 0.18 + 0.60·0.36 + 0.22                               = 0.616
confidence    = clamp(0.616·0.72 + 0.772·0.28)                        = 0.65968
renewability  = 0.02                       (not agricultural, not geothermal)
viability     = clamp(0.772·0.46 + 0.246·0.30 + 0.65968·0.20
                      − 0.409333·0.18 + 0.02·0.10)                    = 0.489176
```

The record is emitted with `deposit_class = "metal"`, `formation_process = "subduction_arc_hydrothermal"`. Viability `0.489176 < 0.65`, so it does **not** count toward `high_viability_resource_deposit_count`.

**2. Ore genesis.** `arc_deposit = 0.24` and `volcanic_landform = 0.14` both fire, so `hydrothermal_alteration_index` picks up at least `0.60·0.25 + 0.55·0.24 + 0.14 + 0.24 = 0.662` before the fault/zone terms. The cell clears `ORE_SYSTEM_THRESHOLD = 0.34` on the resource-membership clause alone and joins a component; with a `volcanic_arc_metals` deposit present, `_system_type` reaches rank 4 and types the province `subduction_arc_hydrothermal` unless a geothermal- or placer-dominated neighbourhood outvotes it at rank 1 or 2.

**3. Commodities.** The deposit fans out to `{copper, gold, silver, sulfide_ore}`. For copper:

```
copper potential = clamp(0.772·0.42 + 0.60·0.30 + 0.55·0.18 + 0.65968·0.10)
                 = 0.32424 + 0.18 + 0.099 + 0.065968 = 0.669208
occurrence conf. = clamp(0.65968·0.54 + 0.669208·0.30 + 0.772·0.16)
                 = 0.3562272 + 0.2007624 + 0.12352   = 0.680510  (6 dp)
market_value_index = 0.78          commodity_group = base_metal
```

Potential `0.669208 >= 0.62`, so this occurrence increments `high_potential_commodity_occurrence_count`.

**4. Land use.** `resource ∈ MINING_RESOURCES`, so `_mining_potential` runs:

```
geology = clamp(0.60·0.26 + 0.00·0.20 + 0.55·0.18 + sediment·0.18 + crust_age·0.18)
mining  = clamp(0.772·0.28 + 0.489176·0.24 + 0.65968·0.18 + 0.246·0.12
                + geology·0.10 + 0.30·0.08 − 0.409333·0.12)
```

With the four leading deposit terms alone the sum is `0.216160 + 0.117402 + 0.118742 + 0.029520 = 0.481824`; adding `0.30·0.08 = 0.024` and subtracting `0.409333·0.12 = 0.049120` gives `0.456704 + geology·0.10`. Since `geology <= 1`, this cell reaches the `MINING_THRESHOLD = 0.52` only if `geology >= 0.633`. Zoning is therefore genuinely marginal for a high-relief arc site — the hazard and accessibility penalties bite.

---

## Inspecting resources

Generate a full world (all six enrichers) from the bundled seed config:

```bash
python -m magic_geo generate \
  --config configs/earthlike_seed.yaml \
  --output runs/world.json
```

Geo-only scope (five enrichers; `land_use_zones` is skipped, `settlement_score` is stripped):

```bash
python -m magic_geo generate \
  --config configs/earthlike_seed.yaml \
  --output runs/geo.json \
  --geo-only
```

From Python:

```python
from magic_geo.api import generate_world, generate_geo_world
from magic_geo.config import load_config

config = load_config("configs/earthlike_seed.yaml")
world = generate_world(config)

print(world["resource_deposit_model"]["flow_accumulation_scale"])
print(world["summary"]["resource_deposit_class_counts"])
print(world["summary"]["ore_genesis_system_type_counts"])
print(world["summary"]["sedimentary_resource_system_type_counts"])
print(world["summary"]["petroleum_migration_system_type_counts"])
print(world["summary"]["commodity_occurrence_group_counts"])
```

Walk one commodity back to its physical cause:

```python
occurrence = world["commodity_occurrences"][0]
deposit = world["resource_deposits"][occurrence["resource_deposit_id"]]
cell = next(c for c in world["cells"] if c["id"] == deposit["cell_id"])

print(occurrence["commodity"], occurrence["occurrence_potential_index"])
print(deposit["formation_process"], deposit["formation_evidence"])
print(cell["resource"], cell["crust_type"], cell["lithology"],
      cell["landform"], cell["boundary_convergent"], cell["crust_age_ma"])
print(cell["ore_genesis_system_id"], cell["petroleum_system_id"])
```

Run a single enricher against an already-generated world (each is a pure `dict -> dict` mutation):

```python
from magic_geo.resource_dynamics import enrich_world_with_resource_deposits
from magic_geo.ore_genesis import enrich_world_with_ore_genesis
from magic_geo.sedimentary_resource_systems import (
    enrich_world_with_sedimentary_resource_systems,
)
from magic_geo.petroleum_migration import enrich_world_with_petroleum_migration
from magic_geo.commodity_resources import enrich_world_with_commodity_occurrences
from magic_geo.land_use_zones import enrich_world_with_land_use_zones

enrich_world_with_resource_deposits(world)
enrich_world_with_ore_genesis(world)
enrich_world_with_sedimentary_resource_systems(world)
enrich_world_with_petroleum_migration(world)
enrich_world_with_commodity_occurrences(world)
enrich_world_with_land_use_zones(world)
```

The order above is mandatory — each stage reads the previous stage's arrays, and `enrich_world_with_ore_genesis` in particular reads `world["resource_deposits"]` to decide component survival.

---

## Validation surfaces

| Validator | Domain / check name | What it asserts | Source |
|---|---|---|---|
| Geo subsystem suite | `geologic_resources` / `resource_deposit_sources_and_ranges` | Sequential deposit ids, valid cell links, bounded indices, and a `resource_deposit_model` whose `model_type`, `flow_accumulation_normalization_model`, independently re-derived `flow_accumulation_scale` (abs tol `1e-4`) and `physical_time_resolved is False` all match | `src/magic_geo/geo_validation_subsystems.py:2281-2420` |
| Geo subsystem suite | `geologic_resources` / `ore_system_membership_and_formation_sources` | Exact `ore_genesis_system_id` inverse mapping, valid geological sources, `ore_genesis_model` fields including the same re-derived flow scale and `physical_time_resolved is False` | `geo_validation_subsystems.py:2424+` |
| Geo subsystem suite | `geologic_resources` / `sedimentary_system_source_chain` | Basin, column, transport-history, cell and deposit links are mutually consistent; system diagnostics bounded | `geo_validation_subsystems.py:2644+` |
| Geo subsystem suite | `geologic_resources` / `petroleum_migration_source_paths` | Exact `petroleum_system_id` inverse mapping, basin-consistent and **adjacent** migration paths | `geo_validation_subsystems.py:2709+` |
| Geo subsystem suite | `geologic_resources` / `commodity_occurrence_deposit_links` | Occurrences exactly mirror their deposit sources; summary aggregates match | `geo_validation_subsystems.py:2776+` |
| World validation | `natural_resources` / `deposit_and_commodity_linkage` | Deposit `resource` equals the source cell's `resource`; `reserve_potential_index`, `extraction_hazard_index`, `renewability_index`, `geologic_confidence_index` are finite and in `[0,1]`; every occurrence links to a real deposit and cell | `src/magic_geo/geo_validation.py:2386-2441` |
| Worldbuilding realism | `resource_geology_dependency` | Fraction of deposits with resource-specific geological support must fall in `[0.85, 1.0]` | `src/magic_geo/worldbuilding_realism.py:95-142`, `:304-329` |
| Human geography replay | Land-use replay | Dispatches exact own versions; v2 independently replays required inputs, availability, both raw potentials/thresholds, components, links and all 15 summary keys before eager full-CLI consumers | `src/magic_geo/human_geography_validation.py:255-350` |

The realism check's per-resource support predicate (`worldbuilding_realism.py:112-142`) is deliberately *looser* than the native cascade — e.g. `volcanic_arc_metals` is supported by `crust_type == volcanic_arc` **or** `landform == volcanic_arc` **or** `convergent >= 0.28`, while the native cascade required `> 0.38` — so a passing check is evidence of consistency, not of exact provenance.

---

## Limitations and unresolved claims

- **Both published resource models declare `physical_time_resolved: False`.** `resource_deposit_model` (`resource_dynamics.py:214`) and `ore_genesis_model` (`ore_genesis.py:449`) both set it explicitly. (`land_use_zone_model` is the layer's third published model record; it carries no time flag at all, because it has no time dimension to resolve.) No resource output on this page carries a calibrated physical time coordinate. `formation_steps[].step_index` and `migration_steps[].step_index` are ordering labels, not times, and the underlying maturation clock inherits the unresolved physical-time calibration of the whole simulation.
- **Declared model limitations, verbatim.** `resource_deposit_model.model_limitation`: `"diagnostic formation evidence without geochemical transport or reserve-volume simulation"`. `ore_genesis_model.model_limitation`: `"diagnostic metallogenic potential without reactive geochemical transport"`. `land_use_zone_model.model_limitation`: `"diagnostic_static_potential_and_connected_zones_without_land_market_crop_mine_capacity_or_development_feedback"`. The geo layer contract classifies the whole layer as `evidence_class: "source_link_replay_without_geochemical_solver"` (`geo_layer_contracts.py:281`).
- **No grade, no tonnage, no reserve volume.** Every economic quantity in this layer is a dimensionless index in `[0,1]` plus a map footprint in km². There is no ore grade, cut-off grade, metal endowment, hydrocarbon volume, coal seam thickness, recoverable reserve, or depth extent anywhere in the six modules. `area_km2` is the sum of member cell areas; for commodity occurrences it is the parent deposit's full cell area, replicated once per commodity, so `commodity_occurrence_total_area_km2` deliberately multiply-counts.
- **`market_value_index` is a static constant table.** `COMMODITY_VALUE_INDEX` (`commodity_resources.py:40-60`) has no supply, demand, transport-cost, technology or era dependence. It is a fixed ranking, not a price and not a market.
- **Ore "deposit types" are tectonic settings, not deposit models.** The five `system_type` values name settings (arc-hydrothermal, craton, placer, rift-geothermal, mixed). There is no porphyry/VMS/SEDEX/IOCG/epithermal/orogenic-gold vocabulary, no metal speciation, no alteration mineralogy, no fluid chemistry, no temperature/salinity of the mineralising fluid, and no distinction between magmatic-hydrothermal and metamorphic fluids.
- **Petroleum migration is a least-cost graph search, not a physical migration solve.** `_best_path` (`petroleum_migration.py:183-223`) minimises a hop count plus an elevation-difference and seismic-hazard penalty minus a migration-affinity bonus. There is no fluid phase, pressure field, capillary entry pressure, carrier-bed permeability, or buoyancy; paths are not required to be monotonically updip. Migration is also hard-confined to `system_cell_ids`, so no cross-basin charge is possible. At most 4 paths per system are recorded (`MAX_PATHS_PER_SYSTEM`).
- **Maturation windows are age-triangles, not thermal histories.** `oil_window` and `gas_window` (`petroleum_migration.py:134-135`) are piecewise-linear functions of the basin's `depositional_age_ma`. There is no burial history curve, geothermal gradient, kinetic kerogen transformation, vitrinite reflectance, or expulsion efficiency; `burial_heat` and `thermal_overprint` are proxies built from sediment thickness, subsidence, boundary flags and volcanic/seismic indices.
- **Evaporite and coal chemistry is absent.** The `evaporite` facies is not a member of any of the five facies sets used by `sedimentary_resource_systems`, so column evaporite content does not directly drive `evaporite_salt_potential_index`; that index runs off soil salinity, closed-basin fraction, salt-flat fraction and existing evaporite deposits. There is no brine evolution, no mineral precipitation sequence, no evaporation-rate budget, and no peat-to-rank coalification model.
- **`ore_genesis` tests a lithology (`andesite`) that the native enum cannot produce.** `LITHOLOGY_NAMES` has seven values and does not include `andesite` (`cpp/src/engine/schema_names.hpp:11`), so that branch of `arc_lithology` (`ore_genesis.py:116`) is unreachable on engine-generated worlds. Reported as observed.
- **Scale constants are inconsistent across modules on purpose or by accident — either way, do not assume they agree.** Sediment thickness is normalised by 3.0 m in `resource_dynamics`, 5.0 m in `ore_genesis`, 6.0 m in `petroleum_migration`, and 8.0 m for the basin mean in both `sedimentary_resource_systems` and `commodity_resources`. Crust age uses 2500 Ma in `resource_dynamics`, `ore_genesis` and `land_use_zones` but 3000 Ma in `commodity_resources`. Flow accumulation uses the p95 normalisation in `resource_dynamics` and `ore_genesis` but a fixed `600_000_000` divisor in `commodity_resources` (`commodity_resources.py:126`) — the two are not comparable.
- **Multi-membership resolution is order-dependent.** A cell can appear in several sedimentary systems' `cell_ids`; the per-cell petroleum indices are written by whichever system yields the highest accumulation, with `>=` breaking ties in favour of the *later* system (`petroleum_migration.py:315`). Ore components and petroleum fairways are disjoint by construction, but that disjointness is enforced by a skip rule, not by a partition.
- **Upstream physical claims carry through unchanged.** The tectonic inputs to ore genesis (`boundary_convergent`, `boundary_divergent`, `crust_age_ma`, `crust_type`, `plate_id`) inherit the engine's explicitly unresolved claims about subduction polarity and mass provenance; the merged `tectonic_zone_ids` list cannot distinguish collision, subduction and rift zone ids without cross-referencing the source arrays. Nothing on this page upgrades those hedges.
- **Land use zoning is static.** `land_use_zones` computes a one-shot potential field and connected components. There is no land market, no crop choice, no mine capacity, no depletion, no development feedback, and no time dimension — as its own `model_limitation` states. It is also absent entirely from geo-only worlds.
- **Deposit accessibility depends on human geography in full-world mode and not at all in geo-only mode.** `accessibility_index` weights `settlement_score` at `0.42`; in geo-only that field is stripped, so accessibility (and therefore `economic_viability_index`) is systematically lower and not comparable across scopes.
- **`resource_deposit_class_counts` and the summary counter names disagree.** `agricultural_resource_deposit_count` counts the `bioproductive` class, not an `agricultural` class (`resource_dynamics.py:222`). Similarly, `volcanic_material` occurrences (obsidian) are counted in none of the six commodity rollup counters.

---

## See also

- [Tectonics and Plates](tectonics-and-plates.md) — plate kinematics, boundary flags and crust type, the primary drivers of the ore-genesis indices
- [Plate Boundary Segment Ledger](plate-boundary-ledger.md) — boundary segments and the explicitly unresolved subduction polarity
- [Crust Material Shadow and Dry-Rock Reservoirs](crust-material-and-reservoirs.md) — crust age, thickness and mass bookkeeping behind `metallogenic_fertility_index`
- [Sediment, Routing and Stratigraphy](sediment-and-stratigraphy.md) — sedimentary basins, stratigraphic columns, facies and transport histories consumed by the sedimentary and petroleum models
- [Erosion, Maturation and Landscape Evolution](erosion-and-maturation.md) — erosion rate and relief inputs to hazard, trap integrity and placer scoring
- [Hydrology, Rivers and Lakes](hydrology-and-rivers.md) — `flow_accumulation`, `is_river`, `basin_id` and the drainage basins that key every sedimentary system
- [Groundwater, Aquifers and Karst](groundwater-and-karst.md) — `groundwater_recharge_mm_y`, an input to agricultural potential
- [Soils and Weathering](soils.md) — `soil_salinity_index`, `soil_moisture_index`, `soil_erodibility_index`, `soil_depth_m`
- [Biomes, Ecosystems and Disturbance](biomes-and-ecology.md) — `growing_season_months`, `fishery_productivity_index`, `forest_growth_index` and the renewable resource records
- [Settlements, Routes and Corridors](settlements-and-routes.md) — how `resource` feeds `settlement_score`, and how zones link to settlements and routes
- [History, Demography, Economy and Markets](history-demography-and-economy.md) — where commodity and zone outputs surface in the economic layer
- [World Document Schema](../10-world-schema.md) — the native 155-field cell record and the enum name tables
- [Geo Validation Suite](../13-geo-validation-suite.md) — the `geologic_resources` and `natural_resources` validator domains
- [Validation](../12-validation.md) — the realism check framework and score targets
- [Python API](../07-python-api.md) — enricher signatures and generation entry points
- [CLI Reference](../06-cli-reference.md) — `generate`, `--geo-only`, and output formats
