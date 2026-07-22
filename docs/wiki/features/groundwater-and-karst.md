# Groundwater, Aquifers and Karst

[Wiki home](../README.md) > Features

magic-geo's subsurface water stack is four independent Python enrichers layered on top of the native C++ hydrologic water budget: a mass-conserving recharge partition of native infiltration, a diagnostic aquifer resource classifier, a descending-head lateral routing model that closes locally per cell, and a karst dissolution classifier. Every one of these is an **annual diagnostic** — none of them solve a transient saturated-flow equation, none maintain storage state between steps, and none feed water back into the surface routing that produced their source term. This page enumerates every formula, threshold, emitted record, and cell field, along with the ordering dependencies that make the results reproducible and the places where the model explicitly declines to claim physical fidelity.

## On this page

- [Where subsurface water sits in the pipeline](#where-subsurface-water-sits-in-the-pipeline)
- [Upstream dependencies and geo-only mode](#upstream-dependencies-and-geo-only-mode)
- [The recharge partition: `infiltration_bounded_aquifer_recharge_v1`](#the-recharge-partition-infiltration_bounded_aquifer_recharge_v1)
- [The aquifer resource model: `finite_recharge_causal_aquifer_resources_v1`](#the-aquifer-resource-model-finite_recharge_causal_aquifer_resources_v1)
- [Aquifer classification and system grouping](#aquifer-classification-and-system-grouping)
- [The groundwater flow system: `descending_head_recharge_conserving_groundwater_flow_v1`](#the-groundwater-flow-system-descending_head_recharge_conserving_groundwater_flow_v1)
- [Flow regimes, springs and baseflow](#flow-regimes-springs-and-baseflow)
- [Karst diagnostics](#karst-diagnostics)
- [Permafrost interaction](#permafrost-interaction)
- [Interaction with the surface water budget and closure](#interaction-with-the-surface-water-budget-and-closure)
- [Complete cell field tables](#complete-cell-field-tables)
- [Complete emitted record tables](#complete-emitted-record-tables)
- [Summary keys](#summary-keys)
- [Validation coverage](#validation-coverage)
- [Worked examples](#worked-examples)
- [Exports and inspection](#exports-and-inspection)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

## Where subsurface water sits in the pipeline

Four modules produce the subsurface layers. They are invoked in a fixed order from `src/magic_geo/api.py`, once for `generate_world()` and once (in a different order) for `generate_geo_world()`.

| Module | Entry point | `generate_world()` position | `generate_geo_world()` position |
|---|---|---|---|
| `src/magic_geo/permafrost_diagnostics.py` | `enrich_world_with_permafrost_diagnostics(world)` | 26 (`api.py:225`) | 25 (`api.py:342`) |
| `src/magic_geo/aquifer_resources.py` | `enrich_world_with_aquifer_resources(world)` | 30 (`api.py:229`) | 30 (`api.py:349`) |
| `src/magic_geo/groundwater_flow.py` | `enrich_world_with_groundwater_flow(world)` | 33 (`api.py:232`) | 33 (`api.py:352`) |
| `src/magic_geo/karst_diagnostics.py` | `enrich_world_with_karst_diagnostics(world)` | 45 (`api.py:244`) | 36 (`api.py:355`) |

All four have the signature `(world: dict[str, Any]) -> dict[str, Any]`, mutate `world` in place, and take no extra arguments. All four return `world` unchanged if `world["cells"]` is missing, is not a list, or is empty (`aquifer_resources.py:59-61`, `groundwater_flow.py:116-118`, `karst_diagnostics.py:122-124`, `permafrost_diagnostics.py:130-132`).

The immediate neighbours in the water-systems block are ordered as follows in both pipelines (`api.py:229-234` / `api.py:349-354`):

```
enrich_world_with_aquifer_resources(world)        # recharge partition + aquifer properties
enrich_world_with_hydrology_budget(world)         # audits the native surface budget
enrich_world_with_wetland_diagnostics(world)      # produces wetland_extent_index
enrich_world_with_groundwater_flow(world)         # head field, routing, discharge
enrich_world_with_river_channel_morphology(world) # consumes baseflow_support_index
enrich_world_with_river_hydraulics(world)
```

The only ordering difference between full-world and geo-only mode for this feature is **karst**: in `generate_world()` it runs at position 45, after `route_corridors`; in `generate_geo_world()` it moves up to position 36, inside the water-systems block. Karst reads no settlement-derived field, so the two positions produce the same values — the move exists because the intervening civilization enrichers do not run in geo-only mode.

## Upstream dependencies and geo-only mode

### Fields read, and which layer produces them

| Consumer | Field read | Produced by | Fallback if absent |
|---|---|---|---|
| `aquifer_resources` | `infiltration_mm_y` | native C++ budget (`cpp/src/engine/hydrology.cpp:138`) | `0.0` (`aquifer_resources.py:111-114`) |
| `aquifer_resources` | `lithology`, `landform`, `water_body_type`, `area_km2`, `sediment_thickness_m`, `ice_thickness_m`, `flow_accumulation`, `is_closed_basin`, `basin_id`, `id` | native | per-field `.get` defaults |
| `aquifer_resources` | `soil_drainage_index`, `soil_moisture_index`, `soil_salinity_index` | `soil_diagnostics` (`soil_dynamics.py`) | `0.0` |
| `aquifer_resources` | `seasonal_aridity_index` | `seasonal_climate_history` (`climate_dynamics.py`) | `0.0` |
| `aquifer_resources` | `settlement_score` | native, stripped in geo-only | `0.0` (`aquifer_resources.py:107`) |
| `groundwater_flow` | `aquifer_class`, `aquifer_system_id`, `aquifer_storage_index`, `aquifer_quality_index`, `aquifer_productivity_index`, `aquifer_extraction_risk_index`, `groundwater_recharge_mm_y`, `groundwater_recharge_km3_y`, `world["aquifer_systems"]` | `aquifer_resources` | `0.0` / `-1` / `""` |
| `groundwater_flow` | `wetland_extent_index` | `wetland_diagnostics` | `0.0` (`groundwater_flow.py:83`) |
| `groundwater_flow` | `distance_to_marine_water_km` | `climate_continentality` | `9999.0` (`groundwater_flow.py:87`) |
| `groundwater_flow` | `elevation_m`, `water_depth_m`, `is_water`, `is_lake`, `is_river`, `is_closed_basin`, `water_body_type`, `neighbors`, `area_km2` | native | per-field `.get` defaults |
| `groundwater_flow` | `soil_moisture_index`, `soil_salinity_index`, `seasonal_aridity_index` | `soil_diagnostics`, `seasonal_climate_history` | `0.0` |
| `karst_diagnostics` | `soil_ph`, `soil_moisture_index`, `soil_drainage_index`, `soil_profile_development_index` | `soil_diagnostics` | `7.0` for pH, `0.0` otherwise (`karst_diagnostics.py:58-61`) |
| `karst_diagnostics` | `groundwater_recharge_mm_y`, `aquifer_productivity_index`, `aquifer_storage_index`, `aquifer_class`, `aquifer_system_id` | `aquifer_resources` | `0.0` / `"unknown"` / `-1` |
| `karst_diagnostics` | `lithology`, `precipitation_mm_y`, `runoff_mm_y`, `temperature_c`, `elevation_m`, `ice_thickness_m`, `neighbors`, `area_km2`, `is_water`, `water_body_type` | native | per-field `.get` defaults |
| `karst_diagnostics` | `seasonal_aridity_index` | `seasonal_climate_history` | `0.0` |
| `permafrost_diagnostics` | `temperature_monthly_c`, `temperature_c`, `lat_deg`, `elevation_m`, `ice_thickness_m`, `is_water`, `biome`, `neighbors`, `area_km2` | native | per-field `.get` defaults |
| `permafrost_diagnostics` | `frost_months` | `biome_diagnostics` (`biome_dynamics.py:158`) | recomputed in-module (see below) |
| `permafrost_diagnostics` | `soil_moisture_index`, `soil_organic_matter_fraction`, `soil_drainage_index` | `soil_diagnostics` | `0.0` |
| `permafrost_diagnostics` | `seasonal_aridity_index` | `seasonal_climate_history` | `0.0` |

### The `frost_months` ordering asymmetry

`frost_months` is written in exactly one place in the codebase: `src/magic_geo/biome_dynamics.py:158`. In `generate_world()` `biome_diagnostics` runs at position 25 and permafrost at 26, so permafrost reads the biome-written value. In `generate_geo_world()` the order is inverted — permafrost runs at 25 and `biome_diagnostics` at 27 — so **`frost_months` is absent when permafrost reads it in geo-only mode** and the in-module fallback fires:

```python
frost_months = int(cell.get("frost_months", sum(1 for temperature in monthly_temperature if temperature < 0.0)))
```
`src/magic_geo/permafrost_diagnostics.py:50`

The fallback is numerically identical to the biome computation (`biome_dynamics.py:123` computes `sum(1 for temperature in monthly_temperature if temperature < 0.0)` over the same `_monthly_values(cell, "temperature_monthly_c", "temperature_c")` 12-element list, and `permafrost_diagnostics.py:14-18` uses the same 12-element list with the same `temperature_c`-replicated fallback). The two orders therefore agree in value; the difference is a real dependency asymmetry, not a numerical divergence.

### Geo-only mode

`generate_geo_world()` calls `_strip_native_civilization_outputs(world)` (`api.py:269-284`) before any enricher, which pops `settlement_score` from every cell (`api.py:106-113`). The only subsurface consumer of `settlement_score` is the aquifer extraction-risk term:

```python
settlement = _clamp(float(cell.get("settlement_score", 0.0)))
...
extraction_risk = _clamp(
    0.14 + aridity * 0.30 + settlement * 0.18 + ... )
```
`src/magic_geo/aquifer_resources.py:107,157-165`

In geo-only mode `settlement * 0.18` is therefore always `0.0`, which lowers `aquifer_extraction_risk_index`, raises `aquifer_productivity_index` (which subtracts `extraction_risk * 0.16`), raises `groundwater_hydraulic_head_m` (which subtracts `extraction_risk * 45.0` metres of depth-to-water), and raises the `export_fraction` and `surface_fraction` terms in the flow model. This is the documented no-human baseline branch, not a defect. Nothing else in the subsurface stack changes between scopes: `aquifer_systems`, `groundwater_flow_systems`, `karst_systems` and `permafrost_regions` are all emitted in both modes, and `generate_geo_world()` raises `ValueError` unless `output.include_cells` is true (`api.py:296-300`).

The geo layer-contract registry places all groundwater artefacts in the `hydrology` layer (phase 7) with required outputs `groundwater_recharge_model`, `groundwater_flow_model` and `groundwater_flow_systems`, and validator domains including `aquifers_wetlands_karst` (`src/magic_geo/geo_layer_contracts.py:150-173`). `permafrost_regions` is a required output of the `cryosphere` layer (phase 9) with validator domain `cryosphere_permafrost_glacial` (`geo_layer_contracts.py:204-217`).

## The recharge partition: `infiltration_bounded_aquifer_recharge_v1`

The recharge model consumes exactly one source term — the native `infiltration_mm_y` — and splits it into aquifer recharge and vadose-zone retention. It cannot manufacture water from precipitation or runoff.

### Domain and marine exclusion

```python
MARINE_WATER_TYPES = {"ocean", "continental_shelf", "inland_sea"}
```
`src/magic_geo/aquifer_resources.py:7`

A cell whose `water_body_type` is in that set takes the marine branch (`aquifer_resources.py:85-97`): every recharge, retention, storage, quality, productivity and risk term is set to exactly `0.0` and `aquifer_class` becomes `"marine_excluded"`. Fresh lakes and saline basins are **not** marine-excluded; they are treated as land for this model, and they genuinely receive recharge.

This turns on a native distinction that is easy to get backwards. In a natively generated world `is_water` is set **only** for ocean-derived cells — `ocean.cpp:271` assigns `water_body = is_water ? 1 : 0`, and `ocean.cpp:314-318` refines those water cells into `ocean` / `continental_shelf` / `inland_sea`. Lake cells are stamped later by the hydrology solve, which sets `is_lake = true` and `water_body` to `fresh_lake` (4) or `saline_basin` (5) **without** setting `is_water` (`cpp/src/engine/hydrology.cpp:633-655`). So in a native world:

```
is_water  ⇔  water_body_type ∈ {ocean, continental_shelf, inland_sea}
is_lake   ⇒  water_body_type ∈ {fresh_lake, saline_basin}  and  is_water == False
```

Because the native land budget excludes on `is_water` (`cpp/src/engine/hydrology.cpp:56,72`), **lake cells are inside the land budget** and carry non-zero `infiltration_mm_y`. Consequently a fresh-lake or saline-basin cell has non-zero recharge, is a groundwater-flow candidate, can join an aquifer system, and can both send and receive lateral flow. That is exactly why the `fresh_lake` bonuses in the recharge fraction (`+0.04`) and storage (`+0.16 × 0.7`) are reachable at all.

### Permeability

| Lithology | Base permeability | Source |
|---|---|---|
| `limestone` | 0.82 | `aquifer_resources.py:23` |
| `sandstone` | 0.76 | `aquifer_resources.py:24` |
| `basalt` | 0.44 | `aquifer_resources.py:25` |
| `volcanic` | 0.48 | `aquifer_resources.py:26` |
| `granite` | 0.30 | `aquifer_resources.py:27` |
| `metamorphic` | 0.28 | `aquifer_resources.py:28` |
| `shale` | 0.18 | `aquifer_resources.py:29` |
| anything else | 0.34 (unreachable for native worlds) | `aquifer_resources.py:30` |

Landform adjustments, applied additively before a `[0, 1]` clamp (`aquifer_resources.py:31-35`):

| Condition | Adjustment |
|---|---|
| `landform ∈ {rift_valley, glacial_valley}` | `+0.10` |
| `landform ∈ ALLUVIAL_LANDFORMS` | `+0.08` |

```python
ALLUVIAL_LANDFORMS = {"floodplain", "delta", "river_valley", "coastal_plain", "lacustrine_basin", "glacial_lake"}
```
`src/magic_geo/aquifer_resources.py:8`

Note that `alluvial_fan` — a real value in `LANDFORM_NAMES` (`cpp/src/engine/schema_names.hpp:37-43`) — is **not** in `ALLUVIAL_LANDFORMS` and therefore receives no alluvial permeability or storage bonus. The seven lithology names in `LITHOLOGY_NAMES` (`cpp/src/engine/schema_names.hpp:11-13`) are all explicitly covered, so the `0.34` default is unreachable for a well-formed native world.

This Python permeability table is **not** the same table the native budget uses for infiltration capacity. The C++ `hydrologic_lithology_permeability` (`cpp/src/engine/hydrology.cpp:5-16`) returns `basalt 0.46`, `granite 0.31`, `limestone 0.82`, `sandstone 0.76`, `shale 0.18`, `volcanic 0.48`, `metamorphic 0.30` — it disagrees with the Python table on basalt (0.46 vs 0.44), granite (0.31 vs 0.30) and metamorphic (0.30 vs 0.28). The two tables are independent parameterizations of two different steps; nothing in the source declares them to be the same quantity.

### Recharge fraction

```python
recharge_fraction = _clamp(
    0.08
    + permeability * 0.45
    + drainage * 0.18
    + sediment * 0.12
    + (0.04 if water_body == "fresh_lake" else 0.0)
    - salinity * 0.10
    - ice * 0.12
    - aridity * 0.06,
    MIN_RECHARGE_FRACTION,
    MAX_RECHARGE_FRACTION,
)
```
`src/magic_geo/aquifer_resources.py:115-126`

| Term | Input | Normalization | Weight |
|---|---|---|---|
| intercept | — | — | `+0.08` |
| permeability | `lithology`, `landform` | table above, clamped `[0,1]` | `+0.45` |
| drainage | `soil_drainage_index` | clamped `[0,1]` | `+0.18` |
| sediment | `sediment_thickness_m` | `/3.0`, clamped `[0,1]` (`aquifer_resources.py:100`) | `+0.12` |
| fresh-lake bonus | `water_body_type == "fresh_lake"` | boolean | `+0.04` |
| salinity | `soil_salinity_index` | clamped `[0,1]` | `-0.10` |
| ice | `ice_thickness_m` | `/1600.0`, clamped `[0,1]` (`aquifer_resources.py:105`) | `-0.12` |
| aridity | `seasonal_aridity_index` | clamped `[0,1]` | `-0.06` |

| Bound | Constant | Value | Source |
|---|---|---|---|
| minimum recharge fraction | `MIN_RECHARGE_FRACTION` | `0.05` | `aquifer_resources.py:11` |
| maximum recharge fraction | `MAX_RECHARGE_FRACTION` | `0.85` | `aquifer_resources.py:12` |

### The partition identity

```python
source_infiltration_mm_y = max(0.0, float(cell.get("infiltration_mm_y", 0.0)))
recharge_mm_y            = source_infiltration_mm_y * recharge_fraction
recharge_km3_y           = recharge_mm_y * area_km2 * 0.000001
vadose_retention_mm_y    = source_infiltration_mm_y - recharge_mm_y
vadose_retention_km3_y   = vadose_retention_mm_y * area_km2 * 0.000001
recharge_residual_mm_y   = source_infiltration_mm_y - recharge_mm_y - vadose_retention_mm_y
```
`src/magic_geo/aquifer_resources.py:111-137`

The residual is exactly zero by construction in exact arithmetic; it is serialized at `round(..., 10)` (`aquifer_resources.py:185-187`) specifically so a replayer can confirm no term was tampered with. Global volumes are accumulated only over non-marine cells (`aquifer_resources.py:196-206`) and published in `groundwater_recharge_model`. Because both the `mm/y` and `km3/y` terms are computed from the same `area_km2 * 1e-6` factor, the volumetric partition closes at the same precision.

`km3/y` conversion uses the literal `0.000001` factor, i.e. `mm/y × km² × 10⁻⁶ = km³/y` (1 mm over 1 km² is 10⁻⁶ km³).

## The aquifer resource model: `finite_recharge_causal_aquifer_resources_v1`

Four bounded indices are derived per non-marine cell. All are clamped to `[0, 1]` and rounded to 6 decimals.

### Storage

```python
storage = _clamp(
    0.08
    + permeability * 0.34
    + sediment * 0.26
    + moisture * 0.12
    + alluvial_bonus
    + fresh_lake_bonus * 0.7
    - aridity * 0.10
    - ice * 0.12
)
```
`src/magic_geo/aquifer_resources.py:138-147`

| Term | Input | Weight | Notes |
|---|---|---|---|
| intercept | — | `+0.08` | |
| permeability | lithology/landform table | `+0.34` | |
| sediment | `sediment_thickness_m / 3.0` clamped | `+0.26` | |
| moisture | `soil_moisture_index` clamped | `+0.12` | |
| `alluvial_bonus` | `landform ∈ ALLUVIAL_LANDFORMS` | `+0.15` | `aquifer_resources.py:110` |
| `fresh_lake_bonus * 0.7` | `water_body_type == "fresh_lake"` → `0.16 * 0.7 = 0.112` | `+0.112` | `aquifer_resources.py:109` |
| aridity | `seasonal_aridity_index` clamped | `-0.10` | |
| ice | `ice_thickness_m / 1600.0` clamped | `-0.12` | |

### Quality

```python
quality = _clamp(
    0.80
    + _clamp(recharge_mm_y / 360.0) * 0.16
    + (0.05 if lithology == "limestone" else 0.0)
    - salinity * 0.50
    - (0.18 if closed_basin else 0.0)
    - (0.18 if water_body == "saline_basin" else 0.0)
    - aridity * 0.08
)
```
`src/magic_geo/aquifer_resources.py:148-156`

Quality starts optimistic at `0.80` and is degraded by soil salinity (the dominant term at `-0.50`), endorheic closure, saline-basin water bodies, and aridity. `closed_basin` is `bool(cell["is_closed_basin"])` (`aquifer_resources.py:108`).

### Extraction risk

```python
extraction_risk = _clamp(
    0.14
    + aridity * 0.30
    + settlement * 0.18
    + (1.0 - _clamp(recharge_mm_y / 240.0)) * 0.20
    + salinity * 0.18
    + ice * 0.10
    + (0.08 if closed_basin else 0.0)
)
```
`src/magic_geo/aquifer_resources.py:157-165`

The `settlement * 0.18` term is identically zero in geo-only mode (see above). The `(1 - recharge/240)` term means a cell with zero recharge starts at `0.14 + 0.20 = 0.34` risk before any other penalty.

### Productivity

```python
productivity = _clamp(
    storage * 0.38
    + _clamp(recharge_mm_y / 320.0) * 0.34
    + quality * 0.18
    + flow * 0.08
    - extraction_risk * 0.16
)
```
`src/magic_geo/aquifer_resources.py:166-172`

where `flow = _clamp(float(cell.get("flow_accumulation", 0.0)) / 40_000_000.0)` (`aquifer_resources.py:106`). Productivity is the only index that consumes drainage-network context.

### Normalization constants

| Constant | Value | Used for | Source |
|---|---|---|---|
| sediment normalizer | `3.0` m | `sediment` index | `aquifer_resources.py:100` |
| ice normalizer | `1600.0` m | `ice` index | `aquifer_resources.py:105` |
| flow-accumulation normalizer | `40 000 000.0` | `flow` index | `aquifer_resources.py:106` |
| quality recharge normalizer | `360.0` mm/y | quality | `aquifer_resources.py:150` |
| risk recharge normalizer | `240.0` mm/y | extraction risk | `aquifer_resources.py:161` |
| productivity recharge normalizer | `320.0` mm/y | productivity | `aquifer_resources.py:168` |

## Aquifer classification and system grouping

### The class decision tree

`_aquifer_class(productivity, storage, quality, recharge_mm_y, salinity)` (`src/magic_geo/aquifer_resources.py:38-49`) evaluates in strict order and returns on the first match:

| Order | Condition | Class |
|---|---|---|
| 0 | `water_body_type ∈ {ocean, continental_shelf, inland_sea}` (short-circuited before the tree, `aquifer_resources.py:97`) | `marine_excluded` |
| 1 | `quality < 0.34` **or** `salinity >= 0.58` | `brackish_or_saline_aquifer` |
| 2 | `productivity >= 0.66` **and** `quality >= 0.55` | `major_fresh_aquifer` |
| 3 | `storage >= 0.54` **and** `recharge_mm_y < 65.0` | `fossil_or_slow_recharge_aquifer` |
| 4 | `productivity >= 0.38` | `local_fresh_aquifer` |
| 5 | `recharge_mm_y >= 80.0` | `perched_recharge_zone` |
| 6 | otherwise | `poor_aquifer` |

`salinity` here is the clamped `soil_salinity_index`, not a groundwater chemistry variable — there is no dissolved-solids transport anywhere in the model.

### System eligibility and grouping

```python
if (
    productivity >= MIN_SYSTEM_PRODUCTIVITY_INDEX
    or recharge_mm_y >= MIN_SYSTEM_RECHARGE_MM_Y
):
    basin_id = int(cell.get("basin_id", -1))
    basin_groups.setdefault(basin_id, []).append(cell)
```
`src/magic_geo/aquifer_resources.py:214-219`

| Constant | Value | Source |
|---|---|---|
| `MIN_SYSTEM_PRODUCTIVITY_INDEX` | `0.18` | `aquifer_resources.py:13` |
| `MIN_SYSTEM_RECHARGE_MM_Y` | `25.0` | `aquifer_resources.py:14` |

Systems are **not** connected components. Grouping is a pure `basin_id` bucket, iterated in `sorted(basin_groups.items())` order (`aquifer_resources.py:222`), with `system_id = len(systems)` assigned in that order. Two consequences follow directly from the source:

- An aquifer system is only as spatially contiguous as the native drainage basin it mirrors.
- Cells whose `basin_id` is `-1` are grouped into a single system with `basin_id = -1`, if any qualify.

Cells that fail eligibility keep `aquifer_system_id = -1` from the initialization at `aquifer_resources.py:193`.

Marine cells never enter `basin_groups` because the eligibility test lives inside the `if aquifer_class != "marine_excluded"` block (`aquifer_resources.py:196-219`).

## The groundwater flow system: `descending_head_recharge_conserving_groundwater_flow_v1`

### Candidate domain

```python
def _is_aquifer_cell(cell):
    return str(cell.get("aquifer_class", "")) != "marine_excluded" and str(cell.get("water_body_type", "land")) not in MARINE_WATER_TYPES
```
`src/magic_geo/groundwater_flow.py:36-37`

Both conditions are checked, so a world where `aquifer_resources` never ran (leaving `aquifer_class` unset, i.e. `""`) would still admit non-marine cells as candidates with zero recharge. Candidate count is published as `groundwater_flow_model.candidate_cell_count`.

### Hydraulic head

Heads are computed for **every** cell (`groundwater_flow.py:122`), including marine ones, and every cell receives a `groundwater_hydraulic_head_m` field (`groundwater_flow.py:137`).

For a non-candidate cell the head is the water-surface head:

```python
def _water_surface_head(cell):
    elevation = float(cell.get("elevation_m", 0.0))
    if bool(cell.get("is_water", False)):
        return elevation + max(0.0, float(cell.get("water_depth_m", 0.0)))
    return elevation
```
`src/magic_geo/groundwater_flow.py:40-44`

For a candidate cell the head is terrain minus a diagnostic depth-to-water:

```python
saturation = _clamp(
    recharge * 0.28 + storage * 0.26 + quality * 0.10 + moisture * 0.18
    + water_bonus + river_bonus
    - aridity * 0.12 - salinity * 0.08 - extraction_risk * 0.08
)
depth_to_water_m = max(0.0, 12.0 + (1.0 - saturation) * 210.0 + aridity * 70.0 + extraction_risk * 45.0 - storage * 35.0)
return elevation - depth_to_water_m
```
`src/magic_geo/groundwater_flow.py:61-73`

| Term | Input | Normalization | Weight |
|---|---|---|---|
| recharge | `groundwater_recharge_mm_y` | `/360.0`, clamped | `+0.28` |
| storage | `aquifer_storage_index` | clamped | `+0.26` |
| quality | `aquifer_quality_index` | clamped | `+0.10` |
| moisture | `soil_moisture_index` | clamped | `+0.18` |
| `water_bonus` | `is_lake` **or** `water_body_type ∈ {fresh_lake, saline_basin}` | boolean | `+0.18` (`groundwater_flow.py:59`) |
| `river_bonus` | `is_river` | boolean | `+0.10` (`groundwater_flow.py:60`) |
| aridity | `seasonal_aridity_index` | clamped | `-0.12` |
| salinity | `soil_salinity_index` | clamped | `-0.08` |
| extraction risk | `aquifer_extraction_risk_index` | clamped | `-0.08` |

Depth-to-water terms: `+12.0 m` intercept, `+210.0 m × (1 − saturation)`, `+70.0 m × aridity`, `+45.0 m × extraction_risk`, `−35.0 m × storage`, floored at `0.0`. Depth-to-water therefore ranges from `0` to `12 + 210 + 70 + 45 = 337 m` below terrain.

```python
SURFACE_WATER_TYPES = {"fresh_lake", "saline_basin"}
```
`src/magic_geo/groundwater_flow.py:8`

### Receiver selection

For each candidate, in ascending cell-id order (`groundwater_flow.py:161`), the enricher scans `cell["neighbors"]` and keeps the largest strictly-positive head drop (`groundwater_flow.py:167-179`). A neighbour is eligible if either:

- `same_system` — the neighbour is itself a candidate **and** `neighbour.aquifer_system_id == cell.aquifer_system_id`; or
- `surface_sink` — the neighbour is not a candidate at all (marine or `marine_excluded`).

```python
if best_drop >= MINIMUM_RECEIVER_HEAD_DROP_M:
    flow_to_by_id[cell_id] = best_neighbor_id
    gradient_by_id[cell_id] = _clamp(best_drop / GROUNDWATER_GRADIENT_SCALE_M)
else:
    flow_to_by_id[cell_id] = -1
    gradient_by_id[cell_id] = 0.0
```
`src/magic_geo/groundwater_flow.py:180-185`

| Constant | Value | Source |
|---|---|---|
| `MINIMUM_RECEIVER_HEAD_DROP_M` | `0.5` m | `groundwater_flow.py:19` |
| `GROUNDWATER_GRADIENT_SCALE_M` | `900.0` m | `groundwater_flow.py:20` |
| `MAXIMUM_LATERAL_EXPORT_FRACTION` | `0.82` | `groundwater_flow.py:21` |

`groundwater_gradient_index` is therefore a **normalized head drop over one cell edge**, `clamp(drop_m / 900)`, not a dimensionless slope — no edge length enters the calculation.

A consequence of the `same_system` test that is worth stating explicitly: every candidate cell that failed aquifer system eligibility carries `aquifer_system_id == -1`, so two such cells compare equal and are mutually eligible receivers **regardless of basin**. Lateral exchange between system-ineligible cells is therefore not basin-confined, unlike exchange inside a real aquifer system.

### Routing order and lateral export

Cells are processed in descending head, ties broken by ascending id:

```python
for cell_id in sorted(candidate_ids, key=lambda item: (-heads[item], item)):
```
`src/magic_geo/groundwater_flow.py:187`

Because every link goes to a strictly lower head, this is a valid topological order and the resulting graph is acyclic; the model advertises this with `acyclic_flow_required: True` (`groundwater_flow.py:408`).

```python
export_fraction = _clamp(
    0.12 + gradient * 0.56 + productivity * 0.18 + storage * 0.08 - extraction_risk * 0.12,
    0.0, MAXIMUM_LATERAL_EXPORT_FRACTION,
)
export = available * export_fraction if flow_to >= 0 else 0.0
```
`src/magic_geo/groundwater_flow.py:194-204`

If the receiver is itself a candidate, the export is added to the receiver's throughput and lateral inflow and recorded as the sender's *internal* lateral outflow (`groundwater_flow.py:206-209`). If the receiver is a surface sink, the export leaves the aquifer domain and `groundwater_internal_lateral_outflow_km3_y` stays `0.0` for that cell — the difference between the two bookkeeping lines is the entire reason both `groundwater_lateral_flow_km3_y` (gross) and `groundwater_internal_lateral_outflow_km3_y` (aquifer-internal) exist.

### Discharge and local closure

```python
local_available  = max(0.0, available - (export if flow_to >= 0 else 0.0))
surface_fraction = _clamp(surface_connection * 0.58 + (1.0 - gradient) * 0.10 + productivity * 0.08 - extraction_risk * 0.12)
if flow_to >= 0 and not flow_to_candidate:
    discharge_km3_y = min(available, export + local_available * surface_fraction)
else:
    discharge_km3_y = min(available, local_available * surface_fraction)
retained_storage_km3_y = max(0.0, available - internal_lateral_outflow - discharge_km3_y)
mass_balance_residual_km3_y = available - internal_lateral_outflow - discharge_km3_y - retained_storage_km3_y
```
`src/magic_geo/groundwater_flow.py:225-240`

The surface-connection index is a max over five independent evidence channels (`groundwater_flow.py:76-89`):

| Evidence | Condition | Connection value |
|---|---|---|
| river | `is_river` | `0.62` |
| lake / surface water body | `is_lake` or `water_body_type ∈ {fresh_lake, saline_basin}` | `0.56` |
| wetland | `wetland_extent_index >= 0.35` | `0.42` |
| closed basin | `is_closed_basin` | `0.24` |
| near-coast | `distance_to_marine_water_km <= 160.0` | `0.28` |
| none of the above | — | `0.0` |

`available` is the cell's own recharge plus everything routed in from higher heads (`groundwater_flow.py:153,207`); it is published as `groundwater_available_volume_km3_y`. The declared local balance is:

```
recharge + lateral_inflow − internal_lateral_outflow − discharge − retained_storage = 0
```
`groundwater_flow_model.local_mass_balance_equation` (`groundwater_flow.py:406`)

`discharge_mm_y = discharge_km3_y / (area_km2 * 0.000001)` when `area_km2 > 0`, else `0.0` (`groundwater_flow.py:241`).

## Flow regimes, springs and baseflow

### Spring and baseflow indices

```python
spring_index = _clamp(discharge_mm_y / 260.0 * 0.42 + gradient * 0.20 + surface_connection * 0.18 + productivity * 0.12 + quality * 0.08)
baseflow_index = _clamp(
    discharge_mm_y / 260.0 * 0.42
    + float(cell.get("groundwater_recharge_mm_y", 0.0)) / 340.0 * 0.16
    + storage * 0.16
    + productivity * 0.16
    + (0.12 if bool(cell.get("is_river", False)) else 0.0)
    - extraction_risk * 0.10
)
```
`src/magic_geo/groundwater_flow.py:242-250`

Note that the `discharge_mm_y / 260.0` and `recharge_mm_y / 340.0` terms are **not** clamped individually before weighting — only the final sum is clamped — so a very high discharge saturates both indices on its own.

### Regime classification

`_flow_regime(cell, gradient, discharge_mm_y, spring_index, flow_to)` (`src/magic_geo/groundwater_flow.py:92-106`) evaluates in strict order:

| Order | Condition | Regime |
|---|---|---|
| 1 | not a candidate cell | `excluded` |
| 2 | `spring_index >= 0.45` **and** `discharge_mm_y >= 20.0` | `discharge_zone` |
| 3 | `recharge_mm_y >= 60.0` **and** `gradient >= 0.08` **and** `flow_to >= 0` | `recharge_throughflow` |
| 4 | `recharge_mm_y >= 60.0` | `recharge_mound` |
| 5 | `gradient >= 0.05` **and** `flow_to >= 0` | `throughflow` |
| 6 | `discharge_mm_y >= 12.0` | `lowland_discharge` |
| 7 | otherwise | `stagnant_or_low_yield` |

The complete regime vocabulary is declared as a module-level set (`groundwater_flow.py:9-17`) and re-declared verbatim in the strict validator (`src/magic_geo/cli/validators/hydrology.py:1046-1054`):

```
excluded, recharge_mound, recharge_throughflow, throughflow,
discharge_zone, lowland_discharge, stagnant_or_low_yield
```

`gradient >= 0.08` at the `900.0 m` scale corresponds to a head drop of `72 m` across one cell edge; `gradient >= 0.05` corresponds to `45 m`.

### Flow-system grouping

Flow systems are keyed on `aquifer_system_id >= 0` (`groundwater_flow.py:282-287`) and renumbered densely into `groundwater_flow_system_id`. Candidate cells that were never system-eligible in the aquifer pass therefore carry complete head/flux fields but `groundwater_flow_system_id = -1`.

Per system, the outlet is chosen as follows (`groundwater_flow.py:314-329`):

1. `discharge_cell_ids` — members with `groundwater_discharge_mm_y >= 25.0` **or** `spring_discharge_index >= 0.45`;
2. else `terminal_cell_ids` — members whose `groundwater_flow_to_cell_id` is `< 0` or points outside the member set;
3. else all members;

then the candidate list is sorted by `(-groundwater_discharge_km3_y, cell_id)` and the first element becomes `outlet_cell_id`. `recharge_cell_ids` are members with `groundwater_recharge_mm_y >= 50.0`.

## Karst diagnostics

Karst is a pure dissolution-potential classifier. It emits four cell fields, one record array, and six summary keys — and **no model contract record**, unlike the recharge, aquifer and flow layers.

### Domain

```python
if bool(cell.get("is_water", False)) or water_body in MARINE_WATER_TYPES:
    return 0.0, 0.0, 0.0
```
`src/magic_geo/karst_diagnostics.py:51-52`

The guard is `is_water` **or** a marine `water_body_type`, and in a native world those two conditions coincide (see [the `is_water` note above](#domain-and-marine-exclusion)). Only marine cells are zeroed. Fresh-lake and saline-basin cells are neither `is_water` nor marine-typed, so they **do** receive karst indices — and they are counted as limestone land by `is_limestone_land = lithology == "limestone" and not is_water` (`karst_diagnostics.py:144`).

### Carbonate factor

```python
def _carbonate_factor(lithology, soil_ph):
    base = {"limestone": 1.0, "sandstone": 0.18, "shale": 0.12, "metamorphic": 0.08,
            "volcanic": 0.04, "basalt": 0.03, "granite": 0.02}.get(lithology, 0.04)
    acidity_bonus = _clamp((7.8 - soil_ph) / 3.0) * 0.12
    return _clamp(base + acidity_bonus)
```
`src/magic_geo/karst_diagnostics.py:21-32`

| Lithology | Base | Max with acidity bonus |
|---|---|---|
| `limestone` | 1.00 | 1.00 (clamped) |
| `sandstone` | 0.18 | 0.30 |
| `shale` | 0.12 | 0.24 |
| `metamorphic` | 0.08 | 0.20 |
| `volcanic` | 0.04 | 0.16 |
| `basalt` | 0.03 | 0.15 |
| `granite` | 0.02 | 0.14 |
| unknown | 0.04 | 0.16 |

The acidity bonus reaches its `0.12` maximum at `soil_ph <= 4.8` and is zero at `soil_ph >= 7.8`. The default `soil_ph` when the field is missing is `7.0` (`karst_diagnostics.py:61`), giving a bonus of `(7.8 − 7.0)/3.0 × 0.12 = 0.032`.

### Water-solution, thermal and relief terms

```python
water_solution = _clamp(
    _clamp(precipitation / 1800.0) * 0.38
    + _clamp(runoff / 900.0) * 0.18
    + _clamp(recharge / 520.0) * 0.28
    + soil_moisture * 0.16
)
thermal_activity = _clamp((temperature + 6.0) / 24.0, 0.18, 1.0)
```
`src/magic_geo/karst_diagnostics.py:70-76`

`thermal_activity` is clamped to `[0.18, 1.0]`, so even a deeply frozen surface retains 18 % of the dissolution rate; it saturates at `temperature_c >= 18.0` and floors at `temperature_c <= -1.68`.

Relief is a **local neighbour maximum**, not a slope:

```python
max_relief = max over neighbours of abs(elevation - neighbour_elevation)
return _clamp(max_relief / 1800.0)
```
`src/magic_geo/karst_diagnostics.py:35-46`

### The karst indices

```python
karst = _clamp(
    carbonate
    * (0.22 + water_solution * 0.36 + relief * 0.16 + soil_drainage * 0.12
       + soil_profile * 0.10 + aquifer_storage * 0.04)
    * thermal_activity
    - aridity * 0.06
    - ice * 0.20
)
cave = _clamp(karst * (0.34 + relief * 0.30 + aquifer_storage * 0.22 + soil_profile * 0.14))
subterranean = _clamp(karst * (0.28 + aquifer_productivity * 0.32 + soil_drainage * 0.22 + relief * 0.18))
```
`src/magic_geo/karst_diagnostics.py:77-93`

where `ice = _clamp(ice_thickness_m / 800.0)` (`karst_diagnostics.py:65`) — note the **800 m** normalizer here versus **1600 m** in the aquifer model.

| Constant | Value | Source |
|---|---|---|
| `KARST_THRESHOLD` | `0.45` | `karst_diagnostics.py:7` |
| precipitation normalizer | `1800.0` mm/y | `karst_diagnostics.py:71` |
| runoff normalizer | `900.0` mm/y | `karst_diagnostics.py:72` |
| recharge normalizer | `520.0` mm/y | `karst_diagnostics.py:73` |
| relief normalizer | `1800.0` m | `karst_diagnostics.py:46` |
| ice normalizer | `800.0` m | `karst_diagnostics.py:65` |

### A structural consequence: karst is limestone-only

The inner bracket sums to at most `0.22 + 0.36 + 0.16 + 0.12 + 0.10 + 0.04 = 1.00`, and `thermal_activity <= 1.0`, so `karst_potential_index <= carbonate_factor` for every cell. Because `KARST_THRESHOLD = 0.45` exceeds the maximum achievable carbonate factor for every non-limestone lithology (`sandstone` tops out at `0.30`), **no non-limestone cell can ever be a karst candidate**. Every member of every `karst_systems` record is therefore a non-marine limestone cell (dry land, or a limestone lake cell — see the domain note above), `dominant_lithology` is always `"limestone"`, and `limestone_cell_fraction` is always `1.0`. Correspondingly, `summary["limestone_karst_cell_fraction"]` reduces to `karst_cell_count / limestone_land_count`.

### System grouping

Karst systems are true connected components over the mesh neighbour graph (`karst_diagnostics.py:96-118`), seeded from the lowest remaining cell id, with members stored in sorted-id order. `aquifer_system_ids` on each record is the sorted set of non-negative `aquifer_system_id` values among the component's cells (`karst_diagnostics.py:164-170`), which is the only cross-link karst emits.

### What karst does *not* do

`subterranean_drainage_fraction` is read by nothing downstream. A repository-wide search for consumers of `karst_potential_index`, `cave_development_index` and `subterranean_drainage_fraction` outside `karst_diagnostics.py` returns only the CSV exporter (`src/magic_geo/io/cells_csv.py:227-229`), the Markdown summary (`src/magic_geo/io/summary_markdown.py:1118-1120`) and the two validators (`src/magic_geo/cli/commands/validate.py:15116-15118`, `src/magic_geo/geo_validation_subsystems.py:2042`). **No surface runoff is diverted underground anywhere in the pipeline.** The field names a diagnostic score, not a routed flux.

## Permafrost interaction

`permafrost_diagnostics` is documented in full on the [Cryosphere](cryosphere.md) page; only its interaction with subsurface water is covered here.

### What it computes

`_permafrost_components(cell)` (`src/magic_geo/permafrost_diagnostics.py:41-101`) short-circuits every `is_water` cell to `(0.0, 0.0, 0.0, "no_permafrost")` and otherwise derives:

```python
extent = _clamp(
    coldness * 0.34 + persistent_freeze * 0.24 + lat_abs * 0.12 + high_cold * 0.11
    + soil_moisture * 0.08 + organic * 0.05 + snow_or_ice * 0.12
    - summer_thaw_penalty * 0.12 - thaw_penalty * 0.08 - aridity * 0.06
)
```
`src/magic_geo/permafrost_diagnostics.py:65-76`

| Sub-term | Definition | Source |
|---|---|---|
| `coldness` | `clamp((−annual_temperature + 1.5) / 16.0)` | `permafrost_diagnostics.py:60` |
| `persistent_freeze` | `clamp(frost_months / 12.0)` | `permafrost_diagnostics.py:61` |
| `lat_abs` | `abs(lat_deg) / 90.0` | `permafrost_diagnostics.py:51` |
| `high_cold` | `clamp(elevation / 4200.0)` | `permafrost_diagnostics.py:62` |
| `organic` | `clamp(soil_organic_matter_fraction / 0.18)` | `permafrost_diagnostics.py:55` |
| `snow_or_ice` | `clamp(ice_thickness_m / 650.0)` | `permafrost_diagnostics.py:57` |
| `summer_thaw_penalty` | `clamp((warmest_month − 6.0) / 22.0)` | `permafrost_diagnostics.py:63` |
| `thaw_penalty` | `clamp(thawing_degree_index / 18.0)` | `permafrost_diagnostics.py:64` |
| `freezing_degree_index` | `mean(max(0, −T_month))` | `permafrost_diagnostics.py:48` |
| `thawing_degree_index` | `mean(max(0, T_month))` | `permafrost_diagnostics.py:49` |

Below the `PERMAFROST_THRESHOLD = 0.45` (`permafrost_diagnostics.py:7`) both `active_layer_depth_m` and `ground_ice_content_index` are hard-set to `0.0` (`permafrost_diagnostics.py:78-80`). Above it:

```python
ground_ice = _clamp(extent * 0.35 + soil_moisture * 0.22 + snow_or_ice * 0.20 + organic * 0.12 + (1.0 - drainage) * 0.11)
active_layer_depth = _clamp(
    0.28 + thawing_degree_index / 5.6 + drainage * 0.42 + aridity * 0.26
    - ground_ice * 0.52 - organic * 0.22 - snow_or_ice * 0.32,
    0.05, 4.5,
)
```
`src/magic_geo/permafrost_diagnostics.py:82-99`

`_permafrost_class(extent, ice_thickness_m)` (`permafrost_diagnostics.py:21-32`), in strict order:

| Order | Condition | Class |
|---|---|---|
| 1 | `extent < 0.15` | `no_permafrost` |
| 2 | `extent < 0.45` | `seasonal_frost` |
| 3 | `ice_thickness_m >= 120.0` **and** `extent >= 0.62` | `ice_cemented_permafrost` |
| 4 | `extent >= 0.78` | `continuous_permafrost` |
| 5 | `extent >= 0.62` | `discontinuous_permafrost` |
| 6 | otherwise | `sporadic_permafrost` |

Regions are connected components over the mesh neighbour graph, seeded from the lowest remaining id (`permafrost_diagnostics.py:104-126,159-162`).

### The coupling that does not exist

Despite running before the aquifer and flow layers in both pipelines, **no permafrost field is read by any subsurface water module**. `aquifer_resources.py`, `groundwater_flow.py` and `karst_diagnostics.py` contain no reference to `permafrost_extent_index`, `active_layer_depth_m`, `ground_ice_content_index` or `permafrost_class`.

Frozen-ground influence on subsurface water enters only through two independent channels, neither of which is the permafrost diagnostic:

| Channel | Where | Mechanism |
|---|---|---|
| Native infiltration capacity | `cpp/src/engine/hydrology.cpp:90-102` | `frozen_index = clamp((−temperature_c − 2.0) / 18.0)` subtracts `0.10 × frozen_index` from `infiltration_capacity_index`, reducing the infiltration source before Python ever sees it |
| `ice_thickness_m` penalties | `aquifer_resources.py:105`, `karst_diagnostics.py:65` | Glacier/ice-sheet thickness (not permafrost) reduces the recharge fraction, storage, and karst potential and raises extraction risk |

Permafrost fields *are* consumed elsewhere — `glacial_landforms.py:229-236` and `species_ranges.py:125` read `permafrost_extent_index` — but never by groundwater. Any statement that magic-geo models permafrost-confined aquifers, supra-permafrost/sub-permafrost flow, or talik hydrology would be unsupported by the source.

## Interaction with the surface water budget and closure

### The native budget the recharge model consumes

The native `causal_land_climate_loss_partition_v1` (`cpp/src/engine/hydrology.cpp:18-158`) runs before flow routing and produces `infiltration_mm_y`:

```
PET               = max(0, temperature_c + 8.0) * 31.0
frozen_index      = clamp((-temperature_c - 2.0) / 18.0)
capacity          = clamp(0.62*permeability + 0.16*sediment_index + 0.12*terrain_retention - 0.10*frozen_index, 0.02, 0.90)
climate_loss      = min(precipitation, 0.68 * PET)
infiltration_share= clamp(0.10 + 0.50*capacity, 0.10, 0.10 + 0.50*0.90)
infiltration      = climate_loss * infiltration_share
AET               = climate_loss - infiltration
runoff            = max(0, precipitation - climate_loss)
```

Constants: `HYDROLOGIC_PET_TEMPERATURE_OFFSET_C = 8.0`, `HYDROLOGIC_PET_SCALE_MM_Y_PER_C = 31.0`, `HYDROLOGIC_CLIMATE_LOSS_FRACTION = 0.68`, `HYDROLOGIC_INFILTRATION_BASE_SHARE = 0.10`, `HYDROLOGIC_INFILTRATION_CAPACITY_SHARE = 0.50`, `HYDROLOGIC_MIN_INFILTRATION_CAPACITY = 0.02`, `HYDROLOGIC_MAX_INFILTRATION_CAPACITY = 0.90` (`cpp/src/engine/constants.hpp:48-54`). The land budget closes as `precipitation = AET + infiltration + runoff` on every non-marine cell; `is_marine` in this routine is `cell.is_water` (`hydrology.cpp:56`), which in a native world means only `ocean` / `continental_shelf` / `inland_sea` cells are excluded — **lake cells are inside the land budget** and therefore supply a real `infiltration_mm_y` to the recharge partition.

### Where groundwater enters closure — and where it does not

The subsurface stack forms a strictly **downstream, one-way chain** off the infiltration term:

```
precipitation ──► AET
              ├─► infiltration ──► groundwater recharge ──► lateral flow ──► discharge
              │                └─► vadose retention                     └─► retained storage
              └─► runoff ──► surface routing, rivers, lakes
```

Three separate closures are declared and independently verified:

| Closure | Equation | Declared where | Verified where |
|---|---|---|---|
| Native land budget | `precipitation = AET + infiltration + runoff` | `hydrologic_water_budget_model` | `geo_validation.py:1524-1538` (`land_water_budget_closure`, tolerance `2.0e-3 mm/y`) |
| Recharge partition | `infiltration = recharge + vadose_retention` | `groundwater_recharge_model.mass_conserving_source_partition = True` (`aquifer_resources.py:296`) | `geo_validation.py:1636-1663`; `cli/validators/hydrology.py:530-557` |
| Flow partition | `recharge + lateral_inflow = internal_lateral_outflow + discharge + retained_storage` | `groundwater_flow_model.local_mass_balance_equation` (`groundwater_flow.py:406`) | `geo_validation.py:1590-1597`; `cli/validators/hydrology.py:995+` |

**Groundwater discharge is never returned to `runoff_mm_y`, `flow_accumulation`, lake storage, or any river record.** The surface budget closes without it, and the groundwater budget closes without touching the surface. `groundwater_flow_model.model_limitation` says so explicitly:

> `annual_diagnostic_head_and_flux_routing_without_transient_aquifer_storage_or_groundwater_surface_water_feedback`
> `src/magic_geo/groundwater_flow.py:429`

The only downstream *use* of a groundwater output by another physical layer is `baseflow_support_index`, read by `river_channel_morphology.py:195` as one of the floodplain-connectivity inputs, and by `cli/validators/rivers.py:214`. This influences channel geometry classification; it does not add water to any discharge.

Other consumers of `groundwater_recharge_mm_y` and `aquifer_productivity_index` are non-hydrologic scoring layers: `route_corridors.py:149-150` (oasis corridor index), `land_use_zones.py:52` (agricultural potential), `ecosystem_dynamics.py:230` (renewable-resource water dependency), and `human_geography_validation.py:154`.

### Global volume aggregates

| Aggregate | Key | Emitted by |
|---|---|---|
| Total infiltration | `summary.total_infiltration_km3_y` | `hydrology_budget.py:220` |
| Total recharge source | `summary.total_groundwater_recharge_source_infiltration_km3_y` | `aquifer_resources.py:323-325` |
| Total recharge | `summary.total_groundwater_recharge_km3_y` | `aquifer_resources.py:322` |
| Total vadose retention | `summary.total_vadose_zone_retention_km3_y` | `aquifer_resources.py:326-328` |
| Total discharge | `summary.total_groundwater_discharge_km3_y` | `groundwater_flow.py:440` |
| Gross lateral throughput | `summary.total_groundwater_lateral_flow_km3_y` | `groundwater_flow.py:441` |
| Aquifer-internal lateral flow | `summary.total_groundwater_internal_lateral_flow_km3_y` | `groundwater_flow.py:442-445` |
| Retained storage | `summary.total_groundwater_retained_storage_km3_y` | `groundwater_flow.py:446-449` |

Note the ordering subtlety: `aquifer_resources` (position 30) computes its own recharge-source volume from `infiltration_mm_y` directly, while `hydrology_budget` (position 31) computes `total_infiltration_km3_y` afterwards. The strict validator cross-checks the two against each other (`cli/validators/hydrology.py:583-586`), so both must be present and agree to within `max(0.001, source_volume * 0.0001)`.

The project documentation reports the following reference volumes. These are **documentation snapshots that were not regenerated for this page** — treat them as illustrative magnitudes, not as verified current output:

| Quantity | Reported value (km³/y) | Reported in |
|---|---|---|
| Native land budget | `121,262.764483 = 23,264.643618 + 13,709.184591 + 84,288.936273` | `README.md:344` |
| Recharge partition | `13,709.184796 = 7,207.789123 + 6,501.395673` | `README.md:362`, `docs/deep_plan.md:181` |
| Flow partition | `7,207.789138 = 2,436.341671 + 4,771.447467` | `README.md:364`, `docs/deep_plan.md:185` |
| Internal lateral inflow = outflow | `2,194.480748` | `README.md:364` |
| Gross lateral throughput | `3,246.584888` | `README.md:364` |

Two inconsistencies in that documentation are visible on inspection and are carried forward here rather than smoothed over: the native infiltration total (`13,709.184591`) and the recharge-model source total (`13,709.184796`) differ in the fourth decimal, as do the recharge total (`7,207.789123`) and the flow-model source total (`7,207.789138`); and `README.md:363` reports "329 systems and 1,594 eligible memberships" while `docs/deep_plan.md:183` reports "1,165 aquifer cells, 1,148 eligible cells, and 307 systems" for the same v32 reference. Neither figure was reproduced here.

## Complete cell field tables

All values are written unconditionally to every cell (including marine cells, which receive explicit zeros and sentinel classes), so the field set is scope-independent.

### `aquifer_resources` — 13 cell fields

| Field | Type | Range / units | Rounding | Marine value | Source |
|---|---|---|---|---|---|
| `groundwater_recharge_source_infiltration_mm_y` | float | `>= 0`, mm/y | 6 | `0.0` | `aquifer_resources.py:175-177` |
| `groundwater_recharge_fraction` | float | `[0.05, 0.85]` (land), `0.0` (marine) | 6 | `0.0` | `aquifer_resources.py:178` |
| `groundwater_recharge_mm_y` | float | `>= 0`, mm/y | 6 | `0.0` | `aquifer_resources.py:179` |
| `groundwater_recharge_km3_y` | float | `>= 0`, km³/y | 6 | `0.0` | `aquifer_resources.py:180` |
| `vadose_zone_retention_mm_y` | float | `>= 0`, mm/y | 6 | `0.0` | `aquifer_resources.py:181` |
| `vadose_zone_retention_km3_y` | float | `>= 0`, km³/y | 6 | `0.0` | `aquifer_resources.py:182-184` |
| `groundwater_recharge_mass_balance_residual_mm_y` | float | `≈ 0`, mm/y | **10** | `0.0` | `aquifer_resources.py:185-187` |
| `aquifer_storage_index` | float | `[0, 1]` | 6 | `0.0` | `aquifer_resources.py:188` |
| `aquifer_quality_index` | float | `[0, 1]` | 6 | `0.0` | `aquifer_resources.py:189` |
| `aquifer_productivity_index` | float | `[0, 1]` | 6 | `0.0` | `aquifer_resources.py:190` |
| `aquifer_extraction_risk_index` | float | `[0, 1]` | 6 | `0.0` | `aquifer_resources.py:191` |
| `aquifer_class` | string | 7-value enum (table above) | — | `"marine_excluded"` | `aquifer_resources.py:192` |
| `aquifer_system_id` | int | `>= 0` or `-1` | — | `-1` | `aquifer_resources.py:193,227` |

### `groundwater_flow` — 15 cell fields

| Field | Type | Range / units | Rounding | Non-candidate value | Source |
|---|---|---|---|---|---|
| `groundwater_hydraulic_head_m` | float | metres (may be negative) | 6 | water-surface head, still written | `groundwater_flow.py:137` |
| `groundwater_gradient_index` | float | `[0, 1]`, `drop_m / 900` | 6 | `0.0` | `groundwater_flow.py:138,256` |
| `groundwater_lateral_flow_km3_y` | float | `>= 0`, km³/y — gross export | 6 | `0.0` | `groundwater_flow.py:139,257` |
| `groundwater_lateral_inflow_km3_y` | float | `>= 0`, km³/y | 6 | `0.0` | `groundwater_flow.py:140,258-261` |
| `groundwater_available_volume_km3_y` | float | `>= 0`, km³/y — recharge + inflow | 6 | `0.0` | `groundwater_flow.py:141,262` |
| `groundwater_internal_lateral_outflow_km3_y` | float | `>= 0`, km³/y — aquifer-to-aquifer only | 6 | `0.0` | `groundwater_flow.py:142,263-266` |
| `groundwater_discharge_mm_y` | float | `>= 0`, mm/y | 6 | `0.0` | `groundwater_flow.py:143,267` |
| `groundwater_discharge_km3_y` | float | `>= 0`, km³/y | 6 | `0.0` | `groundwater_flow.py:144,268` |
| `groundwater_retained_storage_km3_y` | float | `>= 0`, km³/y | 6 | `0.0` | `groundwater_flow.py:145,269-272` |
| `groundwater_flow_mass_balance_residual_km3_y` | float | `≈ 0`, km³/y | **12** | `0.0` | `groundwater_flow.py:146,273-276` |
| `groundwater_flow_to_cell_id` | int | receiver cell id or `-1` | — | `-1` | `groundwater_flow.py:147,277` |
| `spring_discharge_index` | float | `[0, 1]` | 6 | `0.0` | `groundwater_flow.py:148,278` |
| `baseflow_support_index` | float | `[0, 1]` | 6 | `0.0` | `groundwater_flow.py:149,279` |
| `groundwater_flow_regime` | string | 7-value enum | — | `"excluded"` | `groundwater_flow.py:150,280` |
| `groundwater_flow_system_id` | int | `>= 0` or `-1` | — | `-1` | `groundwater_flow.py:151,293` |

### `karst_diagnostics` — 4 cell fields

Zeroed on marine cells only (`is_water` or a marine `water_body_type`); lake cells receive computed values.

| Field | Type | Range | Rounding | Marine value | Source |
|---|---|---|---|---|---|
| `karst_potential_index` | float | `[0, 1]` | 6 | `0.0` | `karst_diagnostics.py:136` |
| `cave_development_index` | float | `[0, 1]` | 6 | `0.0` | `karst_diagnostics.py:137` |
| `subterranean_drainage_fraction` | float | `[0, 1]` | 6 | `0.0` | `karst_diagnostics.py:138` |
| `karst_system_id` | int | `>= 0` or `-1` | — | `-1` | `karst_diagnostics.py:139,157` |

### `permafrost_diagnostics` — 5 cell fields

Zeroed on `is_water` cells only — which in a native world is the marine set, so lake cells are evaluated normally.

| Field | Type | Range / units | Rounding | `is_water` value | Source |
|---|---|---|---|---|---|
| `permafrost_extent_index` | float | `[0, 1]` | 6 | `0.0` | `permafrost_diagnostics.py:144` |
| `active_layer_depth_m` | float | `0.0` or `[0.05, 4.5]` m | 6 | `0.0` | `permafrost_diagnostics.py:145` |
| `ground_ice_content_index` | float | `[0, 1]` | 6 | `0.0` | `permafrost_diagnostics.py:146` |
| `permafrost_class` | string | 6-value enum | — | `"no_permafrost"` | `permafrost_diagnostics.py:147` |
| `permafrost_region_id` | int | `>= 0` or `-1` | — | `-1` | `permafrost_diagnostics.py:148,162` |

## Complete emitted record tables

### `world["groundwater_recharge_model"]` — 13 keys (`aquifer_resources.py:286-312`)

| Key | Type | Value / meaning |
|---|---|---|
| `model_type` | string | `"infiltration_bounded_aquifer_recharge_v1"` |
| `source_field` | string | `"infiltration_mm_y"` |
| `domain` | string | `"non_marine_cells"` |
| `recharge_fraction_model` | string | `"lithology_soil_drainage_sediment_lake_salinity_ice_aridity_v1"` |
| `minimum_recharge_fraction` | float | `0.05` |
| `maximum_recharge_fraction` | float | `0.85` |
| `marine_cell_treatment` | string | `"zero_source_recharge_and_vadose_retention"` |
| `mass_conserving_source_partition` | bool | `True` |
| `total_source_infiltration_volume_km3_y` | float | non-marine sum, `round(..., 9)` |
| `total_groundwater_recharge_volume_km3_y` | float | non-marine sum, `round(..., 9)` |
| `total_vadose_zone_retention_volume_km3_y` | float | non-marine sum, `round(..., 9)` |
| `mass_balance_residual_km3_y` | float | `round(..., 12)` |
| `model_limitation` | string | `"annual_diagnostic_partition_without_transient_vadose_storage_or_groundwater_return_flow"` |

### `world["aquifer_resource_model"]` — 18 keys (`aquifer_resources.py:264-285`)

| Key | Type | Value / meaning |
|---|---|---|
| `model_type` | string | `"finite_recharge_causal_aquifer_resources_v1"` |
| `source_recharge_model` | string | `"infiltration_bounded_aquifer_recharge_v1"` |
| `domain` | string | `"non_marine_cells"` |
| `permeability_model` | string | `"lithology_with_rift_glacial_and_alluvial_landform_adjustments_v1"` |
| `storage_model` | string | `"permeability_sediment_moisture_alluvium_lake_aridity_ice_v1"` |
| `quality_model` | string | `"recharge_limestone_salinity_closed_basin_aridity_v1"` |
| `extraction_risk_model` | string | `"aridity_settlement_low_recharge_salinity_ice_closed_basin_v1"` |
| `productivity_model` | string | `"storage_recharge_quality_flow_extraction_risk_v1"` |
| `classification_model` | string | `"quality_salinity_productivity_storage_recharge_thresholds_v1"` |
| `system_grouping_model` | string | `"basin_id_over_productivity_or_recharge_eligible_cells_v1"` |
| `minimum_system_productivity_index` | float | `0.18` |
| `minimum_system_recharge_mm_y` | float | `25.0` |
| `marine_cell_treatment` | string | `"zero_properties_marine_excluded_class_and_no_system"` |
| `deterministic` | bool | `True` |
| `aquifer_cell_count` | int | non-marine cell count |
| `system_eligible_cell_count` | int | `sum(len(group) for group in basin_groups.values())` |
| `aquifer_system_count` | int | `len(systems)` |
| `model_limitation` | string | `"diagnostic_annual_resource_properties_without_transient_saturated_flow_storage_drawdown_or_geochemistry"` |

### `world["aquifer_systems"][]` — 19 fields (`aquifer_resources.py:239-261`)

| Field | Type | Meaning |
|---|---|---|
| `id` | int | dense index, assignment order |
| `basin_id` | int | native `basin_id` the system mirrors |
| `aquifer_class` | string | modal member class, ties by name (`_primary_key`, `aquifer_resources.py:52-55`) |
| `primary_lithology` | string | modal member lithology |
| `dominant_landform` | string | modal member landform |
| `cell_count` | int | member count |
| `cell_ids` | int[] | member ids in append order |
| `area_km2` | float | sum of member `area_km2`, `round(..., 6)` |
| `mean_groundwater_recharge_mm_y` | float | member mean |
| `total_groundwater_recharge_km3_y` | float | member sum |
| `mean_aquifer_storage_index` | float | member mean |
| `mean_aquifer_quality_index` | float | member mean |
| `mean_aquifer_productivity_index` | float | member mean |
| `mean_aquifer_extraction_risk_index` | float | member mean |
| `recharge_cell_count` | int | members with `groundwater_recharge_mm_y >= 50.0` |
| `high_productivity_cell_count` | int | members with `aquifer_productivity_index >= 0.65` |
| `stressed_cell_count` | int | members with `aquifer_extraction_risk_index >= 0.65` |
| `closed_basin_fraction` | float | fraction of members with `is_closed_basin` |
| `aquifer_class_counts` | dict | name-sorted class histogram |

### `world["groundwater_flow_model"]` — 23 keys (`groundwater_flow.py:394-430`)

| Key | Type | Value / meaning |
|---|---|---|
| `model_type` | string | `"descending_head_recharge_conserving_groundwater_flow_v1"` |
| `source_field` | string | `"groundwater_recharge_km3_y"` |
| `domain` | string | `"non_marine_aquifer_cells"` |
| `hydraulic_head_model` | string | `"terrain_minus_diagnostic_depth_to_water_v1"` |
| `receiver_model` | string | `"steepest_head_drop_within_aquifer_system_or_surface_sink_v1"` |
| `minimum_receiver_head_drop_m` | float | `0.5` |
| `gradient_scale_m` | float | `900.0` |
| `routing_order` | string | `"descending_hydraulic_head_then_cell_id"` |
| `lateral_export_model` | string | `"bounded_gradient_productivity_storage_extraction_fraction_v1"` |
| `maximum_lateral_export_fraction` | float | `0.82` |
| `surface_discharge_model` | string | `"surface_target_export_plus_fraction_of_remaining_volume_v1"` |
| `local_mass_balance_equation` | string | `"recharge_plus_lateral_inflow_minus_internal_lateral_outflow_minus_discharge_minus_retained_storage"` |
| `mass_conserving` | bool | `True` |
| `acyclic_flow_required` | bool | `True` |
| `candidate_cell_count` | int | count of `_is_aquifer_cell` cells |
| `total_source_recharge_volume_km3_y` | float | `round(..., 9)` |
| `total_internal_lateral_inflow_volume_km3_y` | float | `round(..., 9)` |
| `total_internal_lateral_outflow_volume_km3_y` | float | `round(..., 9)` |
| `total_lateral_throughput_volume_km3_y` | float | gross export incl. surface sinks, `round(..., 9)` |
| `total_groundwater_discharge_volume_km3_y` | float | `round(..., 9)` |
| `total_retained_storage_volume_km3_y` | float | `round(..., 9)` |
| `mass_balance_residual_km3_y` | float | `round(..., 12)` |
| `model_limitation` | string | `"annual_diagnostic_head_and_flux_routing_without_transient_aquifer_storage_or_groundwater_surface_water_feedback"` |

### `world["groundwater_flow_systems"][]` — 31 fields (`groundwater_flow.py:332-378`)

| Field | Type | Meaning |
|---|---|---|
| `id` | int | dense flow-system index |
| `aquifer_system_id` | int | source aquifer system |
| `basin_id` | int | from the matching `aquifer_systems` record, else first member's `basin_id` |
| `flow_regime` | string | modal member regime, ties by name |
| `cell_count` | int | member count |
| `cell_ids` | int[] | sorted member ids |
| `recharge_cell_ids` | int[] | members with `groundwater_recharge_mm_y >= 50.0` |
| `discharge_cell_ids` | int[] | members with `groundwater_discharge_mm_y >= 25.0` **or** `spring_discharge_index >= 0.45` |
| `terminal_cell_ids` | int[] | members whose receiver is `-1` or outside the system |
| `outlet_cell_id` | int | see outlet rule above |
| `area_km2` | float | member area sum |
| `total_groundwater_recharge_km3_y` | float | member sum |
| `total_groundwater_lateral_inflow_km3_y` | float | member sum |
| `total_groundwater_internal_lateral_outflow_km3_y` | float | member sum |
| `total_groundwater_discharge_km3_y` | float | member sum |
| `total_groundwater_lateral_flow_km3_y` | float | member sum of gross export |
| `total_groundwater_retained_storage_km3_y` | float | member sum |
| `groundwater_flow_mass_balance_residual_km3_y` | float | member sum, `round(..., 12)` |
| `groundwater_balance_residual_km3_y` | float | `recharge_sum − discharge_sum` (**not** a conservation residual) |
| `discharge_to_recharge_ratio` | float | `discharge_sum / recharge_sum`, `0.0` when recharge is `0` |
| `mean_hydraulic_head_m` | float | member mean |
| `mean_groundwater_gradient_index` | float | member mean |
| `mean_groundwater_discharge_mm_y` | float | member mean |
| `mean_spring_discharge_index` | float | member mean |
| `mean_baseflow_support_index` | float | member mean |
| `mean_aquifer_extraction_risk_index` | float | member mean |
| `river_cell_count` | int | members with `is_river` |
| `lake_cell_count` | int | members with `is_lake` |
| `wetland_cell_count` | int | members with `wetland_extent_index >= 0.35` |
| `closed_basin_cell_count` | int | members with `is_closed_basin` |
| `flow_regime_counts` | dict | name-sorted regime histogram |

`groundwater_balance_residual_km3_y` is *not* the closure residual — it is the recharge-minus-discharge difference, which is expected to be strongly positive because retained storage and lateral export to surface sinks also consume recharge. The conservation residual is `groundwater_flow_mass_balance_residual_km3_y`.

### `world["karst_systems"][]` — 11 fields (`karst_diagnostics.py:172-189`)

| Field | Type | Meaning |
|---|---|---|
| `id` | int | dense component index |
| `cell_count` | int | member count |
| `cell_ids` | int[] | sorted member ids |
| `area_km2` | float | member area sum |
| `dominant_lithology` | string | modal member lithology (always `"limestone"` in practice, see above) |
| `primary_aquifer_class` | string | modal member `aquifer_class` |
| `aquifer_system_ids` | int[] | sorted non-negative member `aquifer_system_id` values |
| `mean_karst_potential_index` | float | member mean |
| `mean_cave_development_index` | float | member mean |
| `mean_subterranean_drainage_fraction` | float | member mean |
| `limestone_cell_fraction` | float | fraction of members with `lithology == "limestone"` (always `1.0` in practice) |

Karst emits **no** `karst_model` contract record — unlike recharge, aquifers and flow, there is no declared model-type string, threshold export, or model-limitation string for karst in the world document.

### `world["permafrost_regions"][]` — 12 fields (`permafrost_diagnostics.py:171-186`)

| Field | Type | Meaning |
|---|---|---|
| `id` | int | dense component index |
| `cell_count` | int | member count |
| `cell_ids` | int[] | sorted member ids |
| `area_km2` | float | member area sum |
| `dominant_permafrost_class` | string | modal class, fallback `"sporadic_permafrost"` |
| `dominant_biome` | string | modal native `biome`, fallback `"tundra"` |
| `mean_permafrost_extent_index` | float | member mean |
| `mean_active_layer_depth_m` | float | member mean |
| `mean_ground_ice_content_index` | float | member mean |
| `mean_frost_months` | float | member mean |
| `ice_covered_cell_count` | int | members with `ice_thickness_m > 25.0` |
| `permafrost_class_counts` | dict | name-sorted class histogram |

Like karst, permafrost emits no model contract record.

## Summary keys

All four modules write into `world.setdefault("summary", {})`. These keys are **Python-added**; they are not part of the 412-key native `summary` object emitted by `cpp/src/engine/summary.cpp`.

### From `aquifer_resources` — 17 keys (`aquifer_resources.py:314-337`)

| Key | Definition |
|---|---|
| `aquifer_resource_model` | `"finite_recharge_causal_aquifer_resources_v1"` |
| `groundwater_recharge_model` | `"infiltration_bounded_aquifer_recharge_v1"` |
| `aquifer_cell_count` | non-marine cell count |
| `aquifer_system_count` | `len(world["aquifer_systems"])` |
| `groundwater_recharge_cell_count` | non-marine cells with `recharge_mm_y >= 50.0` |
| `high_productivity_aquifer_cell_count` | non-marine cells with `productivity >= 0.65` |
| `groundwater_stressed_cell_count` | non-marine cells with `extraction_risk >= 0.65` |
| `total_groundwater_recharge_km3_y` | `round(..., 6)` |
| `total_groundwater_recharge_source_infiltration_km3_y` | `round(..., 6)` |
| `total_vadose_zone_retention_km3_y` | `round(..., 6)` |
| `groundwater_recharge_mass_balance_residual_km3_y` | `round(..., 9)` |
| `mean_groundwater_recharge_mm_y` | mean over non-marine cells, `0.0` if none |
| `mean_aquifer_storage_index` | mean over non-marine cells |
| `mean_aquifer_quality_index` | mean over non-marine cells |
| `mean_aquifer_productivity_index` | mean over non-marine cells |
| `mean_aquifer_extraction_risk_index` | mean over non-marine cells |
| `aquifer_class_counts` | name-sorted histogram over **all** cells |

`aquifer_class_counts` is the only aggregate taken over all cells rather than the non-marine subset, so `sum(aquifer_class_counts.values()) == summary["cell_count"]` (asserted at `tests/test_smoke_hydrology.py:617`).

### From `groundwater_flow` — 17 keys (`groundwater_flow.py:432-459`)

| Key | Definition |
|---|---|
| `groundwater_flow_model` | `"descending_head_recharge_conserving_groundwater_flow_v1"` |
| `groundwater_flow_cell_count` | candidates with `groundwater_flow_system_id >= 0` |
| `groundwater_flow_system_count` | `len(world["groundwater_flow_systems"])` |
| `groundwater_discharge_cell_count` | candidates with `groundwater_discharge_mm_y >= 25.0` |
| `spring_candidate_cell_count` | candidates with `spring_discharge_index >= 0.45` |
| `baseflow_supported_river_cell_count` | candidates with `is_river` **and** `baseflow_support_index >= 0.35` |
| `total_groundwater_discharge_km3_y` | `round(..., 6)` |
| `total_groundwater_lateral_flow_km3_y` | gross export sum, `round(..., 6)` |
| `total_groundwater_internal_lateral_flow_km3_y` | aquifer-internal outflow sum, `round(..., 6)` |
| `total_groundwater_retained_storage_km3_y` | `round(..., 6)` |
| `groundwater_flow_mass_balance_residual_km3_y` | `round(..., 12)` |
| `total_groundwater_flow_balance_residual_km3_y` | `total_recharge − total_discharge`, `round(..., 6)` |
| `mean_groundwater_gradient_index` | mean over candidates |
| `mean_groundwater_discharge_mm_y` | mean over candidates |
| `mean_spring_discharge_index` | mean over candidates |
| `mean_baseflow_support_index` | mean over candidates |
| `groundwater_flow_regime_counts` | name-sorted histogram over **all** cells |

### From `karst_diagnostics` — 6 keys (`karst_diagnostics.py:191-200`)

| Key | Definition |
|---|---|
| `karst_cell_count` | cells with `karst_potential_index >= 0.45` |
| `karst_system_count` | `len(world["karst_systems"])` |
| `mean_karst_potential_index` | mean over **all** cells |
| `mean_cave_development_index` | mean over **all** cells |
| `mean_subterranean_drainage_fraction` | mean over **all** cells |
| `limestone_karst_cell_fraction` | `limestone_karst_count / limestone_land_count`, `0.0` when there is no limestone land |

### From `permafrost_diagnostics` — 8 keys (`permafrost_diagnostics.py:188-197`)

| Key | Definition |
|---|---|
| `permafrost_cell_count` | cells with `permafrost_extent_index >= 0.45` |
| `permafrost_region_count` | `len(world["permafrost_regions"])` |
| `mean_permafrost_extent_index` | mean over **all** cells |
| `mean_active_layer_depth_m` | mean over permafrost cells only, `0.0` if none |
| `mean_ground_ice_content_index` | mean over permafrost cells only, `0.0` if none |
| `continuous_permafrost_cell_count` | count of class `continuous_permafrost` |
| `ice_cemented_permafrost_cell_count` | count of class `ice_cemented_permafrost` |
| `permafrost_class_counts` | name-sorted class histogram over all cells |

## Validation coverage

### Strict replay validators (`magic-geo validate`)

Three dedicated replay validators are invoked from the `validate` command (`src/magic_geo/cli/commands/validate.py:14592-14594`):

| Validator | Function | What it independently recomputes |
|---|---|---|
| Recharge | `_validate_groundwater_recharge` (`cli/validators/hydrology.py:423-587`) | Every model-contract string and bound; per cell: expected source, permeability incl. landform adjustments, expected fraction, recharge, vadose, residual, and both `km³/y` conversions; global model totals; four summary totals; and the cross-check `source_volume ≈ summary["total_infiltration_km3_y"]` |
| Aquifers | `_validate_aquifer_resources` (`cli/validators/hydrology.py:590-992`) | Every property formula, the class decision tree, eligibility, deterministic basin grouping, all system aggregate fields, the cell-to-system mirror, and raw summary aggregates |
| Flow | `_validate_groundwater_flow` (`cli/validators/hydrology.py:995+`) | Model contract; candidate set and `candidate_cell_count`; head field for all cells; receiver selection with the exact `same_system` / `surface_sink` eligibility; descending-head routing; export fractions; discharge; spring/baseflow indices; regimes; local closure; systems; and model totals |

Tolerances used by the recharge replay: `0.001` on `mm/y` quantities, `1.0e-8` on the per-cell residual, `max(0.001, expected * 0.0001)` on `km³/y` quantities and all model/summary totals (`cli/validators/hydrology.py:537-586`). Model-contract constants are compared at `1.0e-12` (`cli/validators/hydrology.py:446-455`, `1026-1040`).

Karst and permafrost are validated inline in the same command rather than by dedicated modules: karst at `cli/commands/validate.py:15101-15230+` (bounded ranges, water-cell zeroing, `karst_system_id >= 0 ⇒ karst >= 0.45`, dense sequential ids, membership mirror, area/mean reconstruction, `aquifer_system_ids` reconstruction) and permafrost at `cli/commands/validate.py:12700-12850+` (summary key presence, bounded fields, water-cell zeroing, region membership and mean reconstruction to `0.001`).

### Geo validation (`magic-geo validate-geo`)

`geo_validation.py` runs two relevant gates:

| Check | Domain | Conditions |
|---|---|---|
| `finite_core_geo_fields` (`geo_validation.py:973-1010`) | `contract` | Requires finite values for `groundwater_recharge_source_infiltration_mm_y`, `groundwater_recharge_mm_y`, `groundwater_recharge_km3_y`, `vadose_zone_retention_mm_y`, `groundwater_available_volume_km3_y`, `groundwater_lateral_inflow_km3_y`, `groundwater_internal_lateral_outflow_km3_y`, `groundwater_discharge_km3_y`, `groundwater_retained_storage_km3_y` on every cell |
| `groundwater_partition_closure` (`geo_validation.py:1636-1663`) | `hydrology` | See tolerance table below |

| Residual checked | Formula | Tolerance |
|---|---|---|
| Source infiltration | `abs(source − infiltration_mm_y)` | `2.0e-4` mm/y |
| Recharge partition | `abs(source − recharge − vadose)` | `2.0e-4` mm/y |
| Volume conversion | `abs(recharge_km3 − recharge_mm × area × 1e-6)` | `2.0e-5` km³/y |
| Available volume | `abs(available − recharge_km3 − lateral_inflow)` | `2.0e-5` km³/y |
| Local flow closure | `abs(available − internal_outflow − discharge − retained)` | `2.0e-5` km³/y |
| Global transfer | `abs(Σ internal_outflow − Σ lateral_inflow)` | `1.0e-3` km³/y |
| Per-receiver inflow | `abs(Σ upstream internal_outflow − lateral_inflow)` | `1.0e-3` km³/y |
| Negative terms | any of nine terms `< −1.0e-10` | must be `0` |
| Invalid links | receiver missing, non-integer, or with head `>=` sender head | must be `0` |
| Marine leakage | any `is_water` cell with a non-zero groundwater term (`> 1.0e-8`) | must be `0` |

Note the last row: the marine-leakage gate keys on **`is_water`**, and in a natively generated world `is_water` is exactly the `MARINE_WATER_TYPES` set used by the enrichers (`ocean.cpp:271,314-318`), so the two domains coincide and the gate is consistent with the enricher branch. Fresh-lake and saline-basin cells are *not* `is_water`; they carry non-zero recharge, lateral inflow, discharge and retained storage without touching this gate.

`geo_validation_subsystems.py:1940-2064` adds two subsystem checks in domain `aquifers_wetlands_karst`:

- `aquifer_membership_models_and_ranges` — sequential ids, unique non-overlapping `cell_ids`, exact area reconstruction, every member's `basin_id` equal to the system's, cell-to-system mirror, bounded indices, non-negative volumes, summary mirrors, model total agreement, and `abs(recharge_model.mass_balance_residual_km3_y) <= 1.0e-6`.
- `wetland_karst_membership_and_sources` — for karst: structure and sequential ids, membership inverse (`{cells with karst_system_id >= 0}` equals the union of `cell_ids`), area/count reconstruction, bounded cell diagnostics, and `aquifer_system_ids ⊆ range(len(aquifer_systems))`.

`geo_validation_subsystems.py:1888-1938` covers permafrost membership in domain `cryosphere_permafrost_glacial`, using the same `permafrost_extent_index >= 0.45` candidate rule.

## Worked examples

### Generating and inspecting a world

```bash
# Full world (all 66 enrichers)
magic-geo generate --config configs/earthlike_seed.yaml --output runs/world.json

# Natural systems only; requires output.include_cells = true
magic-geo generate --config configs/earthlike_seed.yaml --output runs/geo.json --geo-only

# Full consistency gate, including the three groundwater replay validators
magic-geo validate --world runs/world.json

# Natural-system gate only
magic-geo validate-geo --world runs/geo.json --profile earthlike --output runs/geo-report.json
```

Programmatic use — the enrichers are imported from their own modules, not re-exported from the `magic_geo` package root:

```python
from magic_geo import load_config
from magic_geo.api import generate_geo_world

world = generate_geo_world(load_config("configs/earthlike_seed.yaml"))

print(world["groundwater_recharge_model"]["total_groundwater_recharge_volume_km3_y"])
print(world["groundwater_flow_model"]["mass_balance_residual_km3_y"])
print(len(world["aquifer_systems"]), len(world["groundwater_flow_systems"]), len(world["karst_systems"]))
print(world["summary"]["aquifer_class_counts"])
print(world["summary"]["groundwater_flow_regime_counts"])
```

Re-running a single enricher on an already-enriched world is idempotent for these modules because each one recomputes every field it owns from upstream inputs:

```python
from magic_geo.aquifer_resources import enrich_world_with_aquifer_resources
from magic_geo.groundwater_flow import enrich_world_with_groundwater_flow
from magic_geo.karst_diagnostics import enrich_world_with_karst_diagnostics
from magic_geo.permafrost_diagnostics import enrich_world_with_permafrost_diagnostics

enrich_world_with_aquifer_resources(world)
enrich_world_with_groundwater_flow(world)
enrich_world_with_karst_diagnostics(world)
enrich_world_with_permafrost_diagnostics(world)
```

### Hand-worked recharge and flow trace

The following is computed by hand from the published formulas with **assumed** inputs; it is an illustration of the arithmetic, not output from a generated world.

Assume one limestone `floodplain` land cell with `area_km2 = 40000`, `infiltration_mm_y = 180.0`, `soil_drainage_index = 0.60`, `sediment_thickness_m = 2.4`, `soil_moisture_index = 0.55`, `soil_salinity_index = 0.05`, `seasonal_aridity_index = 0.20`, `ice_thickness_m = 0`, `flow_accumulation = 8_000_000`, `settlement_score = 0` (geo-only), `is_closed_basin = False`, `elevation_m = 220`.

| Step | Computation | Result |
|---|---|---|
| permeability | `0.82 + 0.08` (alluvial) | `0.90` |
| `sediment` | `clamp(2.4 / 3.0)` | `0.80` |
| `flow` | `clamp(8e6 / 4e7)` | `0.20` |
| recharge fraction | `0.08 + 0.90·0.45 + 0.60·0.18 + 0.80·0.12 − 0.05·0.10 − 0.20·0.06` | `0.672` |
| `groundwater_recharge_mm_y` | `180.0 × 0.672` | `120.96` |
| `vadose_zone_retention_mm_y` | `180.0 − 120.96` | `59.04` |
| `groundwater_recharge_km3_y` | `120.96 × 40000 × 1e-6` | `4.8384` |
| `vadose_zone_retention_km3_y` | `59.04 × 40000 × 1e-6` | `2.3616` |
| partition check | `4.8384 + 2.3616` | `7.2 = 180 × 40000 × 1e-6` ✓ |
| `aquifer_storage_index` | `0.08 + 0.90·0.34 + 0.80·0.26 + 0.55·0.12 + 0.15 − 0.20·0.10` | `0.79` |
| `aquifer_quality_index` | `0.80 + clamp(120.96/360)·0.16 + 0.05 − 0.05·0.50 − 0.20·0.08` | `0.86276` |
| `aquifer_extraction_risk_index` | `0.14 + 0.20·0.30 + 0 + (1 − clamp(120.96/240))·0.20 + 0.05·0.18` | `0.3082` |
| `aquifer_productivity_index` | `0.79·0.38 + clamp(120.96/320)·0.34 + 0.86276·0.18 + 0.20·0.08 − 0.3082·0.16` | `≈ 0.550705` |
| `aquifer_class` | quality ≥ 0.34, salinity < 0.58, productivity < 0.66, recharge ≥ 65, productivity ≥ 0.38 | `local_fresh_aquifer` |
| system eligibility | productivity `0.5507 ≥ 0.18` | eligible |

Continuing into the flow model with `is_river = False`, `is_lake = False`, `wetland_extent_index = 0.20`, `distance_to_marine_water_km = 400`, and a best neighbour head drop of `45 m`:

| Step | Computation | Result |
|---|---|---|
| `saturation` | `0.336·0.28 + 0.79·0.26 + 0.86276·0.10 + 0.55·0.18 − 0.20·0.12 − 0.05·0.08 − 0.3082·0.08` | `≈ 0.4321` |
| depth to water | `12 + (1 − 0.4321)·210 + 0.20·70 + 0.3082·45 − 0.79·35` | `≈ 131.478 m` |
| `groundwater_hydraulic_head_m` | `220 − 131.478` | `≈ 88.522` |
| `groundwater_gradient_index` | `clamp(45 / 900)` | `0.05` |
| `export_fraction` | `clamp(0.12 + 0.05·0.56 + 0.550705·0.18 + 0.79·0.08 − 0.3082·0.12, 0, 0.82)` | `≈ 0.273343` |
| `groundwater_lateral_flow_km3_y` | `4.8384 × 0.273343` | `≈ 1.322542` |
| `local_available` | `4.8384 − 1.322542` | `≈ 3.515858` |
| surface connection | no river/lake, wetland `0.20 < 0.35`, not closed, `400 > 160` | `0.0` |
| `surface_fraction` | `clamp(0·0.58 + (1 − 0.05)·0.10 + 0.550705·0.08 − 0.3082·0.12)` | `≈ 0.102072` |
| `groundwater_discharge_km3_y` (receiver is a candidate) | `min(4.8384, 3.515858 × 0.102072)` | `≈ 0.358872` |
| `groundwater_retained_storage_km3_y` | `4.8384 − 1.322542 − 0.358872` | `≈ 3.156986` |
| `groundwater_discharge_mm_y` | `0.358872 / (40000 × 1e-6)` | `≈ 8.972` |
| `spring_discharge_index` | `8.972/260·0.42 + 0.05·0.20 + 0 + 0.550705·0.12 + 0.86276·0.08` | `≈ 0.1596` |
| `baseflow_support_index` | `8.972/260·0.42 + 120.96/340·0.16 + 0.79·0.16 + 0.550705·0.16 − 0.3082·0.10` | `≈ 0.2551` |
| `groundwater_flow_regime` | spring `< 0.45`; recharge `≥ 60` but gradient `0.05 < 0.08` | `recharge_mound` |
| local closure | `4.8384 − 1.322542 − 0.358872 − 3.156986` | `0` ✓ |

## Exports and inspection

### `cells.csv`

`write_cells_csv` (`src/magic_geo/io/cells_csv.py:11`) uses a fixed `fieldnames` list with `extrasaction="ignore"`, so exported columns are exactly the listed ones. All 37 subsurface cell fields are present, split across four positions in the header:

| Block | Columns | Header lines |
|---|---|---|
| Permafrost | `permafrost_extent_index`, `active_layer_depth_m`, `ground_ice_content_index`, `permafrost_class`, `permafrost_region_id` | `cells_csv.py:187-191` |
| Aquifers + karst | `groundwater_recharge_mm_y`, `groundwater_recharge_km3_y`, `aquifer_storage_index`, `aquifer_quality_index`, `aquifer_productivity_index`, `aquifer_extraction_risk_index`, `aquifer_class`, `aquifer_system_id`, `karst_potential_index`, `cave_development_index`, `subterranean_drainage_fraction`, `karst_system_id` | `cells_csv.py:219-230` |
| Flow | `groundwater_hydraulic_head_m`, `groundwater_gradient_index`, `groundwater_lateral_flow_km3_y`, `groundwater_discharge_mm_y`, `groundwater_discharge_km3_y`, `groundwater_flow_to_cell_id`, `spring_discharge_index`, `baseflow_support_index`, `groundwater_flow_regime`, `groundwater_flow_system_id` | `cells_csv.py:288-297` |
| Conservation operands (tail block) | `groundwater_recharge_source_infiltration_mm_y`, `groundwater_recharge_fraction`, `vadose_zone_retention_mm_y`, `vadose_zone_retention_km3_y`, `groundwater_recharge_mass_balance_residual_mm_y`, `groundwater_lateral_inflow_km3_y`, `groundwater_available_volume_km3_y`, `groundwater_internal_lateral_outflow_km3_y`, `groundwater_retained_storage_km3_y`, `groundwater_flow_mass_balance_residual_km3_y` | `cells_csv.py:401-410` |

### Debug layers

`export-debug` promotes every scalar cell field into a layer named `cells/<field>` (`src/magic_geo/debug_export.py:225-232`), so any subsurface field can be rendered directly:

```bash
magic-geo export-debug --world runs/world.json --output runs/debug
magic-geo export-debug-map --debug-dir runs/debug --layer cells/groundwater_recharge_mm_y --projection mollweide
magic-geo export-debug-map --debug-dir runs/debug --layer cells/aquifer_class
magic-geo export-debug-map --debug-dir runs/debug --layer cells/karst_potential_index
magic-geo export-debug-map --debug-dir runs/debug --layer cells/permafrost_class
```

Categorical layers (`aquifer_class`, `groundwater_flow_regime`, `permafrost_class`) are only promoted if they have at most `_CATEGORY_LIMIT = 64` distinct values (`debug_export.py:34,136`); otherwise the column is still written to `tables/cells.parquet` and the reason is recorded in `manifest["cells"]["skipped_layers"]` (`debug_export.py:229-239`). All three of these enums are far below the limit, so they always promote.

### Markdown summary

`write_summary_markdown` groups the groundwater keys into its hydrology block (`src/magic_geo/io/summary_markdown.py:1084-1121`), the permafrost keys into its cryosphere block (`summary_markdown.py:1002-1009`), and treats `aquifer_class_counts` and `groundwater_flow_regime_counts` as histogram tables (`summary_markdown.py:1288-1289`).

## Limitations and unresolved claims

These are the model's own declared limitations plus what the source demonstrably does and does not do. None of them should be read as a hedge on an otherwise-physical model — the model is diagnostic by design and says so in the world document.

### Declared model limitations, verbatim

| Model | `model_limitation` string | Source |
|---|---|---|
| `infiltration_bounded_aquifer_recharge_v1` | `annual_diagnostic_partition_without_transient_vadose_storage_or_groundwater_return_flow` | `aquifer_resources.py:309-311` |
| `finite_recharge_causal_aquifer_resources_v1` | `diagnostic_annual_resource_properties_without_transient_saturated_flow_storage_drawdown_or_geochemistry` | `aquifer_resources.py:284` |
| `descending_head_recharge_conserving_groundwater_flow_v1` | `annual_diagnostic_head_and_flux_routing_without_transient_aquifer_storage_or_groundwater_surface_water_feedback` | `groundwater_flow.py:429` |
| karst | *(none — no model record is emitted)* | — |
| permafrost | *(none — no model record is emitted)* | — |

### Diagnostic classification versus simulated flow

| Claim | Status |
|---|---|
| Recharge is bounded by a finite, upstream-produced infiltration source | **True, and enforced here** — but the source is not a physical simulation. `infiltration_mm_y` comes from the native `causal_land_climate_loss_partition_v1`, which the project itself describes as "an empirical annual partition without transient soil moisture, groundwater return flow, storm timing, or calibrated duration" (`README.md:344`). The Python partition of that source is exact and independently replayed. |
| The recharge/vadose split is mass-conserving | **True and verified**, to `2.0e-4 mm/y` per cell and `1.0e-6 km³/y` globally. |
| The per-cell groundwater budget closes | **True and verified**, to `2.0e-5 km³/y` per cell. |
| Lateral flow is acyclic and directed down the head field | **True and verified** — routing is a single steepest-head-drop link per cell, processed in descending head order. |
| The head field is a solved potentiometric surface | **False.** It is `elevation_m` minus an empirical depth-to-water score built from recharge, storage, quality, moisture, aridity, salinity and extraction-risk indices. No hydraulic conductivity, transmissivity, porosity, specific yield, or Darcy law appears anywhere in the module. |
| `groundwater_gradient_index` is a hydraulic gradient | **False.** It is `clamp(head_drop_m / 900.0)` — a dimensionless normalized drop with no edge length in the denominator. |
| Lateral flux is Darcian | **False.** It is `available_volume × export_fraction`, where `export_fraction` is a weighted sum of gradient, productivity, storage and extraction-risk indices, capped at `0.82`. |
| Aquifer storage is a volume | **False.** `aquifer_storage_index` is a dimensionless `[0, 1]` score. There is no aquifer thickness, saturated volume, or specific storage anywhere. |
| `groundwater_retained_storage_km3_y` accumulates between steps | **False.** It is a per-run residual sink term. Nothing carries it forward; there is no timestep. |
| Water quality / salinity is a groundwater chemistry variable | **False.** `aquifer_quality_index` is derived from `soil_salinity_index`, closed-basin status, lithology and aridity. There is no solute transport, no total-dissolved-solids field, and no geochemical reaction. |
| Groundwater discharge feeds rivers, lakes or the ocean | **False.** Discharge is computed and reported but never added to `runoff_mm_y`, `flow_accumulation`, lake storage, or any river or coastal record. |
| `baseflow_support_index` supplies baseflow to channels | **Partly.** It is read by `river_channel_morphology.py:195` as a *morphology classification* input and by `cli/validators/rivers.py:214`. It adds no water to any discharge. |
| `subterranean_drainage_fraction` diverts surface drainage underground | **False.** No module outside `karst_diagnostics.py` reads it. Surface routing is unaffected by karst. |
| Karst records speleogenesis or conduit flow | **False.** `cave_development_index` is a scalar score; no conduit geometry, cave passage, sinkhole, or turbulent conduit flow is represented. |
| Karst can develop on non-carbonate rock | **False by construction.** The `0.45` threshold exceeds the maximum carbonate factor of every non-limestone lithology, so karst systems are limestone-only. |
| Permafrost constrains aquifers or groundwater flow | **False.** No permafrost field is read by any subsurface water module. Frozen-ground influence enters only via the native `frozen_index` temperature proxy in the infiltration-capacity term and via `ice_thickness_m` penalties. |
| Permafrost active-layer depth is a Stefan solution | **Not verified in source as such.** It is a bounded weighted sum of thawing-degree index, drainage, aridity, ground ice, organic matter and ice thickness (`permafrost_diagnostics.py:89-99`), clamped to `[0.05, 4.5]` m. |
| Aquifer systems are hydrogeologically contiguous units | **Only as contiguous as the native basins.** Grouping is a pure `basin_id` bucket, not a connected-component pass; karst and permafrost, by contrast, do use connected components. |
| Lateral exchange respects aquifer boundaries | **Only for system-eligible cells.** All ineligible candidates share `aquifer_system_id = -1`, so they are mutually eligible receivers across basin boundaries. |
| Physical time is resolved for these layers | **No.** These are per-cell annual rates attached to a world whose `geo_evolution_provenance` records `physical_time_resolved` as always `False`; there is no calibrated timestep behind "per year" here. |
| Confined vs. unconfined behaviour, artesian pressure, aquitards, aquicludes | **Not represented.** There is no vertical layering — one cell holds one scalar aquifer state. |
| Pumping, drawdown, cones of depression, mining of fossil water | **Not represented.** `aquifer_extraction_risk_index` is a *score* that reads `settlement_score`; it removes no water. `fossil_or_slow_recharge_aquifer` is a class label, not a depleting reservoir. |
| Seasonality | **Not represented.** All groundwater quantities are annual; only `seasonal_aridity_index` (a scalar) enters, and permafrost's monthly temperature series is used only to derive scalars. |
| Lake cells are excluded from the subsurface stack | **False.** `is_water` is set only for `ocean` / `continental_shelf` / `inland_sea`; `fresh_lake` and `saline_basin` cells are `is_lake` with `is_water == False` (`cpp/src/engine/ocean.cpp:271,314-318`, `cpp/src/engine/hydrology.cpp:633-655`). They stay inside the native land budget, receive recharge, become flow candidates and can join aquifer systems, and receive karst indices. There is no lake-bed seepage, no lake stage, and no lake-storage coupling behind this — it is the same land formula applied to a cell that happens to be flagged as a lake. |
| Lake and aquifer water are distinguished | **No.** A `fresh_lake` cell's recharge, head, discharge and retained storage are computed with the identical land equations plus fixed bonuses (`+0.04` recharge fraction, `+0.16 × 0.7` storage, `+0.18` saturation, `0.56` surface connection). Nothing reconciles that with the cell's surface water body. |

### Reproducibility and numerical notes

- All four modules are deterministic and use no RNG; iteration is over sorted ids or sorted dict keys throughout (`aquifer_resources.py:222`, `groundwater_flow.py:161,187,211,283,290`, `karst_diagnostics.py:99,117`, `permafrost_diagnostics.py:107,125`). `aquifer_resource_model.deterministic` is `True` (`aquifer_resources.py:278`).
- All modal-value selections use `_primary_key`, which sorts by `(-count, name)` — ties resolve by lexicographic name, not by id (`aquifer_resources.py:52-55`, `groundwater_flow.py:109-112`, `karst_diagnostics.py:15-18`, `permafrost_diagnostics.py:35-38`).
- Cell values are rounded to 6 decimals with two exceptions: the recharge residual at 10 decimals and the flow residual at 12 decimals. That extra precision exists so a replayer can distinguish a genuine closure from a rounding artifact.
- The Python permeability table (`aquifer_resources.py:22-30`) and the native infiltration-capacity permeability table (`cpp/src/engine/hydrology.cpp:5-16`) disagree on `basalt`, `granite` and `metamorphic`. Nothing in the source declares them to be the same quantity; they are separate parameterizations of separate steps.
- The reference volume totals reproduced from `README.md` and `docs/deep_plan.md` in the closure section are documentation snapshots that were not regenerated for this page, and the two documents disagree on aquifer system and eligible-cell counts for the same "v32" reference. Treat both as unverified.

## See also

- [Hydrology, Rivers and Lakes](hydrology-and-rivers.md) — the surface water budget, routing, depression handling, and lake basins that produce `infiltration_mm_y` and `runoff_mm_y`
- [Cryosphere: Ice Sheets, Glaciers and Permafrost](cryosphere.md) — the full permafrost, glacial landform and ice dynamics treatment
- [Soils and Weathering](soils.md) — `soil_drainage_index`, `soil_moisture_index`, `soil_salinity_index`, `soil_ph`, `soil_organic_matter_fraction` and `soil_profile_development_index`
- [Climate and Atmosphere](climate-and-atmosphere.md) — `seasonal_aridity_index`, `temperature_monthly_c` and the continentality distance field
- [Resources and Economic Geology](resources-and-economic-geology.md) — how aquifer productivity and recharge enter commodity and land-use scoring
- [Settlements, Routes and Corridors](settlements-and-routes.md) — the oasis corridor index built on `groundwater_recharge_mm_y` and `aquifer_productivity_index`
- [World Document Schema](../10-world-schema.md) — the native 57-key document and 155-field cell record these layers extend
- [Validation](../12-validation.md) — the `magic-geo validate` strict replay gate
- [Geo Validation Suite](../13-geo-validation-suite.md) — `validate-geo`, layer contracts and the `aquifers_wetlands_karst` domain
- [Debug Exports and Visualization](../16-debug-and-visualization.md) — `cells/<field>` layers and map export
- [Configuration Reference](../05-configuration-reference.md) — why these thresholds are module constants rather than config keys
- [Glossary](../21-glossary.md)
