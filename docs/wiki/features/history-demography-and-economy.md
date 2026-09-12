# History, Demography, Economy and Markets

[Wiki home](../README.md) > Features

**Current seasonal scope.** The [settlement and social availability contract](../../settlement_social_availability.md) governs current native social2 and Python social-tail2 output. The detailed equations below describe available inputs; explicitly labelled legacy branches retain the historical fallback behavior. Current records preserve IDs, era slots and independent descriptors, publish unavailable dependent estimates as null with typed flags, and distinguish recorded counts from complete inferred counts. Existing subequation labels ending in `_v1` do not by themselves make a whole model legacy. Original source-line references describe the earlier implementation layout rather than current line numbers.

This page documents the temporal social layer of magic-geo: the fixed four-era historical partition and its seven-type event vocabulary, the native population-region capacity model, the border-pair conflict model, the dynastic lineage chain, and the Python enrichers that project those static records forward into population, economy, agent, logistics, campaign and market-clearing trajectories. The native half lives entirely in `cpp/src/engine/history.cpp` and runs only inside the `include_society` branch of the pipeline; the Python consumers follow the audited source order linked above. Every model in this layer declares its own `model_limitation` string in the serialized document, and none of them claims empirical calibration, physical time, or observed-history validation — this page carries those declarations forward verbatim and never upgrades them.

## On this page

- [Source map](#source-map)
- [Scope: full-world only](#scope-full-world-only)
- [Ordering dependencies](#ordering-dependencies)
- [Historical eras and the event vocabulary](#historical-eras-and-the-event-vocabulary)
- [Population regions: the native capacity model](#population-regions-the-native-capacity-model)
- [Population history: the era trajectory](#population-history-the-era-trajectory)
- [Conflicts](#conflicts)
- [Dynasties and the genealogy model](#dynasties-and-the-genealogy-model)
- [Territorial snapshots as the era coupling](#territorial-snapshots-as-the-era-coupling)
- [Economy history](#economy-history)
- [Demographic agents](#demographic-agents)
- [Logistics networks and market exchanges](#logistics-networks-and-market-exchanges)
- [Campaign operations](#campaign-operations)
- [Market clearing](#market-clearing)
- [Native calibration checks](#native-calibration-checks)
- [In-place annotations written back onto existing records](#in-place-annotations-written-back-onto-existing-records)
- [Validation and replay](#validation-and-replay)
- [Worked examples](#worked-examples)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

## Source map

| Concern | File | Key symbols / lines |
| --- | --- | --- |
| Era partition and event generation | `cpp/src/engine/history.cpp` | `historical_era_for_year_bp` `:5`, `default_historical_eras` `:18`, `add_historical_event` `:39`, `generate_historical_layers` `:70`–`:338` |
| Population regions | `cpp/src/engine/history.cpp` | `population_water_security` `:350`, `generate_population_regions` `:367`–`:451` |
| Conflicts | `cpp/src/engine/history.cpp` | `generate_conflicts` `:453`–`:639` |
| Dynasties | `cpp/src/engine/history.cpp` | `generate_dynasties` `:641`–`:758` |
| Territorial snapshots | `cpp/src/engine/history.cpp` | `sampled_ids` `:760`, `generate_territorial_snapshots` `:773`–`:957` |
| Native calibration checks | `cpp/src/engine/history.cpp` | `calibration_score_for_range` `:959`, `add_calibration_check` `:968`, `generate_calibration_checks` `:990`–`:1088` |
| Record structs and defaults | `cpp/src/engine/types/world.hpp` | `HistoricalEra` `:115`, `HistoricalEvent` `:128`, `PopulationRegion` `:149`, `ConflictRecord` `:166`, `DynastyRecord` `:192`, `SnapshotRegion` `:218`, `TerritorialSnapshot` `:239` |
| Enum name tables | `cpp/src/engine/schema_names.hpp` | `HISTORY_EVENT_TYPE_NAMES` `:83`, `HISTORICAL_PROCESS_NAMES` `:87`, `CONFLICT_CAUSE_NAMES` `:90`, `CONFLICT_OUTCOME_NAMES` `:94`, `DYNASTY_COLLAPSE_REASON_NAMES` `:98`, `CALIBRATION_*_NAMES` `:102`–`:115` |
| Record serializers | `cpp/src/engine/entity_serialization.cpp` | `historical_eras_json` `:761`, `historical_events_json` `:784`, `population_regions_json` `:810`, `conflicts_json` `:837`, `dynasties_json` `:873`, `snapshot_regions_json` `:904`, `territorial_snapshots_json` `:935` |
| Calibration-check serializer | `cpp/src/engine/process_serialization.cpp` | `calibration_checks_json` `:4417` |
| Summary aggregation | `cpp/src/engine/summary.cpp` | event/population/conflict/dynasty/snapshot rollups `:700`–`:753`, emission `:1834`–`:1895` |
| Stage ordering | `cpp/src/engine/pipeline.cpp` | society branch `:199`–`:260`, history calls `:222`–`:259`, calibration `:261` |
| Model declarations (events) | `src/magic_geo/historical_geography.py` | `enrich_world_with_historical_geography_model` `:9`–`:79` |
| Model declarations (population/conflict/dynasty) | `src/magic_geo/civilization_geography.py` | `:11`–`:74` |
| Model declarations (snapshots) | `src/magic_geo/territorial_geography.py` | `:9`–`:32` |
| Population history | `src/magic_geo/history_dynamics.py` | `_growth_multiplier` `:81`, `_logistic_projection` `:96`, `enrich_world_with_population_history` `:107`–`:235` |
| Economy history | `src/magic_geo/economy_dynamics.py` | `_resource_value` `:34`, `_trade_by_region` `:57`, `_conflict_by_era_region` `:76`, `enrich_world_with_economy_history` `:119`–`:320` |
| Ruler genealogy | `src/magic_geo/dynasty_genealogy.py` | `_dynasty_ruler_count` `:104`, `enrich_world_with_dynasty_genealogy` `:110`–`:308` |
| Demographic agents | `src/magic_geo/demographic_agents.py` | `_cohort_specs` `:114`, `enrich_world_with_demographic_agents` `:152`–`:602` |
| Logistics, exchange, campaigns | `src/magic_geo/logistics_history.py` | `_campaign_terrain_cost` `:163`, `_shortest_campaign_path` `:206`, `_build_tactical_engagements` `:356`, `_build_strategic_campaign_plans` `:552`, `enrich_world_with_logistics_history` `:746`–`:1345` |
| Market clearing | `src/magic_geo/market_clearing.py` | `ROUTE_CAPACITY_MULTIPLIER` `:6`, `ORDER_KIND_BY_SECTOR` `:15`, `enrich_world_with_market_clearing` `:120`–`:615` |
| Campaign replay validator | `src/magic_geo/campaign_operations_validation.py` | `_expected_campaign_operations` `:813`, `_contains_expected` `:1403`, `validate_campaign_operations_replay` `:1421`–`:1485` |
| Enricher ordering | `src/magic_geo/api.py` | model declarations `:238`–`:240`, trajectory enrichers `:257`–`:262` |
| CLI gate | `src/magic_geo/cli/commands/validate.py` | replay validator calls `:10591`–`:10599` |

## Scope: full-world only

Everything on this page exists only in a **full world**. `simulate_geo_world` calls `simulate_world_impl(params, include_society = false)` and skips the entire `if (include_society)` block at `cpp/src/engine/pipeline.cpp:199`, so `generate_historical_layers`, `generate_population_regions`, `generate_conflicts`, `generate_dynasties` and `generate_territorial_snapshots` never run. The serializer still emits the keys (as `[]`), and the Python `generate_geo_world` then pops them entirely via `_strip_native_civilization_outputs` before any enricher runs, and none of the six trajectory enrichers on this page is in the geo-only call list.

`generate_calibration_checks` (`cpp/src/engine/history.cpp:990`) is the exception: it lives in the same translation unit but is called **outside** the branch at `pipeline.cpp:261`, so `calibration_checks` is present in geo-only worlds too.

| World scope | Native history stages | `calibration_checks` | Trajectory enrichers |
| --- | --- | --- | --- |
| `generate_world` (full) | run | present | all 6 run |
| `generate_geo_world` | skipped (`include_society = false`) | present | none run; the 15 native civilization arrays are popped |

## Ordering dependencies

The layer has a strict two-phase ordering: a native phase (C++, inside one `simulate_world_impl` call) and a Python enricher phase. Neither phase re-enters the other.

### Native ordering (`cpp/src/engine/pipeline.cpp:199`–`:260`)

| Order | Call | Line | Reads | Writes |
| --- | --- | --- | --- | --- |
| 1 | `generate_settlements` | `:200` | cells | `society.settlements` |
| 2 | `generate_routes` | `:201` | cells, settlements | `society.routes` |
| 3 | `generate_political_regions` | `:202` | cells, settlements, routes | `society.political_regions` |
| 4 | `generate_border_segments` | `:208` | cells | `society.borders` |
| 5 | `generate_trade_flows` | `:209` | cells, settlements, routes | `society.trade_flows` |
| 6 | `generate_cultural_layers` | `:214` | cells, settlements, regions, borders, flows | `society.cultural_layers` |
| 7 | `generate_historical_layers` | `:222` | cells (unused, `(void)cells` at `history.cpp:78`), settlements, regions, borders, flows, cultural layers | `historical_layers.eras`, `.events` |
| 8 | `generate_population_regions` | `:230` | cells, regions, cultural layers | `society.population_regions` |
| 9 | `generate_conflicts` | `:235` | cells, regions, borders, flows, cultural layers, **population regions** | `society.conflicts` |
| 10 | `generate_dynasties` | `:243` | regions, cultural layers, **historical layers**, **population regions**, **conflicts** | `society.dynasties` |
| 11 | `generate_territorial_snapshots` | `:250` | params, cells, regions, settlements, cultural layers, **historical layers**, **population regions**, **conflicts** | `society.territorial_snapshots` |
| 12 | `generate_calibration_checks` | `:261` | cells, watersheds | `world.calibration_checks` (both scopes) |

The hard edges are: conflicts require population regions (for `population_pressure` and `estimated_population`); dynasties require the type-`state_foundation` events, population regions and conflicts; territorial snapshots require eras (one snapshot per era), population regions and conflicts.

### Python enricher ordering (`src/magic_geo/api.py`)

| Order | Line | Enricher | Depends on |
| --- | --- | --- | --- |
| a | `:238` | `enrich_world_with_historical_geography_model` | `historical_eras`, `historical_events` (declaration only) |
| b | `:239` | `enrich_world_with_civilization_geography_models` | `population_regions`, `conflicts` (declaration only) |
| c | `:240` | `enrich_world_with_territorial_geography_model` | `territorial_snapshots` (declaration only) |
| 1 | `:257` | `enrich_world_with_population_history` | `population_regions`, `historical_eras`, `territorial_snapshots`, `conflicts` |
| 2 | `:258` | `enrich_world_with_economy_history` | **`population_histories`**, `political_regions`, `population_regions`, `trade_flows`, `conflicts`, `historical_eras`, `territorial_snapshots` |
| 3 | `:259` | `enrich_world_with_dynasty_genealogy` | `dynasties`, `conflicts`, **`economy_histories`** |
| 4 | `:260` | `enrich_world_with_logistics_history` | `political_regions`, `routes`, `trade_flows`, `settlements`, `borders`, `conflicts`, **`economy_histories`**, `cells`, `planet_parameters.radius_km` |
| 5 | `:261` | `enrich_world_with_demographic_agents` | `population_regions`, **`population_histories`**, **`economy_histories`**, `settlements`, `political_regions`, **`logistics_networks`**, **`market_exchanges`**, `historical_eras` |
| 6 | `:262` | `enrich_world_with_market_clearing` | **`market_exchanges`**, **`logistics_networks`**, `routes`, **`household_cohorts`**, **`firm_agents`** |

Notable consequences of this order:

- The economy trajectory is a strict function of the population trajectory; there is no back-coupling from economy to population.
- `enrich_world_with_demographic_agents` reads `market_exchanges` **before** market clearing runs, so household vulnerability sees only pre-clearing indices. The model declares this explicitly: `"market_feedback_model": "preclearing_market_exchange_pressure_v1"` (`src/magic_geo/demographic_agents.py:25`).
- `enrich_world_with_market_clearing` reads `household_cohorts` and `firm_agents`, which only exist because step 5 already ran; markets therefore see agents that never saw market outcomes. There is no second pass.
- `enrich_world_with_dynasty_genealogy` reads `economy_histories`, so ruler legitimacy and patronage depend on the economy trajectory but not on logistics or markets.

## Historical eras and the event vocabulary

### The fixed four-era partition

`default_historical_eras` (`cpp/src/engine/history.cpp:18`–`:37`) always returns exactly four eras with hardcoded boundaries. `historical_era_for_year_bp` (`:5`–`:16`) is the only classifier and uses strict `>` comparisons, so an event exactly on a boundary falls into the *younger* era.

| `id` | `dominant_process` | `start_year_bp` | `end_year_bp` | Assignment predicate (`historical_era_for_year_bp`) |
| --- | --- | --- | --- | --- |
| 0 | `founding` | 4200.0 | 2400.0 | `year_bp > 2400.0` |
| 1 | `expansion` | 2400.0 | 1300.0 | `year_bp > 1300.0` |
| 2 | `fragmentation` | 1300.0 | 450.0 | `year_bp > 450.0` |
| 3 | `integration` | 450.0 | 0.0 | otherwise |

`dominant_process` is serialized through `HISTORICAL_PROCESS_NAMES` (`schema_names.hpp:87`). The classifier is unbounded above — any `year_bp` greater than 2400 maps to era 0 even if it exceeds 4200 — but no generator on this page emits a year above 3800, so in practice every event lands inside the declared partition.

If `political_regions` is empty **or** `cultural_layers.cultures` is empty, `generate_historical_layers` returns the four eras with zero events (`history.cpp:81`–`:83`).

### `historical_eras[]` record fields

The aggregate formulas below describe complete available event scopes. Current era flags and recorded counts distinguish an unavailable full count or mean from the number of events actually emitted; incomplete families cannot use the zero-event formula to claim a known-zero mean. Era IDs and fixed times remain present.

| Field | Type | Source | Meaning |
| --- | --- | --- | --- |
| `id` | int | `history.cpp:20`,`24`,`28`,`32` | 0–3 |
| `dominant_process` | enum string | `HISTORICAL_PROCESS_NAMES` | `founding` / `expansion` / `fragmentation` / `integration` |
| `event_count` | int | `:320` | events assigned to this era |
| `state_event_count` | int | `:324` | events of type 0 or 1 |
| `migration_event_count` | int | `:326` | events of type 2 |
| `language_event_count` | int | `:328` | events of type 3 |
| `start_year_bp` | double | `:22`… | era start (fixed) |
| `end_year_bp` | double | `:23`… | era end (fixed) |
| `mean_instability` | double | `:321`,`:333` | mean `pressure_index` of the era's events (0 when `event_count == 0`) |
| `mean_connectivity` | double | `:322`,`:334` | mean `continuity_index` of the era's events |

Serialized by `historical_eras_json` (`entity_serialization.cpp:761`) at `params.float_precision`.

### The event vocabulary

`HISTORY_EVENT_TYPE_NAMES` (`schema_names.hpp:83`) declares seven types. The numerical path clamps available `pressure_index` and `continuity_index` to `[0, 1]` and assigns an `era_id` from the raw year. Current family coverage is field-granular: language and trade events retain their independent inputs; migration and sacred events retain identity, time and pressure with nullable dependent continuity. Foundation/dynastic chronology requiring unavailable culture age is suppressed, as is ruin-history inference when its selection is unavailable. Per-family and per-era coverage distinguishes emitted event counts from unavailable full counts and means; a recorded zero does not certify a complete empty family.

| # | `type` string | Generated once per | Trigger condition | `year_bp` formula | `pressure_index` | `continuity_index` | Source |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | `state_foundation` | eligible political region | requires available culture age on the current path | `clamp(380 + 0.72·culture.estimated_age_years, 260, 3800)`; missing-culture age 1800 is a legacy default | region pressure (below) | `culture.continuity_index`; missing-culture 0.5 is a legacy default | `:123`–`:137` |
| 1 | `dynastic_change` | political region | `pressure > 0.34` **or** `trade_contact > 0.55` **or** `region.route_count == 0` | `clamp(foundation_year·0.48 + 180·(region.id + 1), 180, 2100)` | `clamp(pressure + 0.18·trade_contact, 0, 1)` | same as type 0 | `:139`–`:154` |
| 2 | `migration` | culture region | `culture.migration_pressure ≥ 0.42` **or** `culture.trade_contact_index ≥ 0.28` | `clamp(260 + 2100·migration_pressure + 220·culture.id, 120, 2600)` | `culture.migration_pressure` | `culture.continuity_index` | `:157`–`:194` |
| 3 | `language_split` | child language region | `language.parent_language_region_id ≥ 0` | `clamp(language.divergence_age_years, 80, 3400)` | `language.change_rate` | `clamp(1 − change_rate, 0, 1)` | `:196`–`:227` |
| 4 | `trade_boom` | top-ranked trade flow | first `min(12, flows)` by volume desc, id asc | `clamp(140 + 820·(1 − clamp(friction/2, 0, 1)) + 42·rank, 70, 1300)` | `clamp(volume_index/100, 0, 1)` | `clamp(1 − friction/2, 0, 1)` | `:229`–`:259` |
| 5 | `sacred_founding` | sacred area | first `min(12, sacred_areas)` in record order | `clamp(220 + 1800·significance + 35·i, 120, 2400)` | `site.significance` | culture continuity, else 0.5 | `:261`–`:281` |
| 6 | `ruin_abandonment` | ruin | first `min(16, ruins)` in record order | `clamp(90 + 1500·significance + 28·i, 80, 1900)` | `ruin.significance` | `ruin.preservation_score` | `:283`–`:303` |

The state-foundation/dynastic-change `pressure` term is (`history.cpp:116`–`:122`):

```
pressure = clamp(
      0.18
    + region.barrier_pressure * 0.32
    + (border_length[region] > 0 ? border_pressure[region] / border_length[region] : 0) * 0.28
    + (region.settlement_count <= 2 ? 0.18 : 0),
    0.0, 1.0)
```

where `border_pressure[r] = Σ border.barrier_score · border.length_km` and `border_length[r] = Σ border.length_km` over every `BorderSegment` incident on `r` (`:91`–`:96`), and `trade_contact = region_trade_volume[r] / (100 · max(1, region.settlement_count))` with `region_trade_volume[r] = Σ flow.volume_index` over incident flows (`:97`–`:105`, `:138`).

Type-2 migration events also carry a `related_culture_region_id`: among cultures sharing the same `language_region_id`, the one maximizing `1 − |other.trade_contact_index − culture.trade_contact_index|` (`:168`–`:179`).

### Event ordering and era aggregation

After all generators run, events are sorted **descending by raw `year_bp`, ties broken by ascending `type`** (`:305`–`:310`), then `id` is reassigned `0..n-1` in that order and `era_id` is recomputed from the final year (`:311`–`:314`). Era counters are then accumulated in that order (`:315`–`:330`) and the two means are divided by `event_count` (`:331`–`:336`).

The declaration enricher records the same contract as `"event_order": "descending_raw_year_bp_then_native_event_enum_v1"` (`src/magic_geo/historical_geography.py:74`).

### `historical_events[]` record fields

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `id` | int | reassigned after sort | dense `0..n-1` |
| `era_id` | int | recomputed after sort | 0–3 |
| `type` | enum string | — | `HISTORY_EVENT_TYPE_NAMES` |
| `region_id` | int | −1 | political region; −1 for orphan sacred/ruin events |
| `related_region_id` | int | −1 | only set for `trade_boom` (`flow.region_to`) |
| `culture_region_id` | int | −1 | |
| `related_culture_region_id` | int | −1 | set for `migration` and `trade_boom` |
| `language_region_id` | int | −1 | |
| `related_language_region_id` | int | −1 | set for `language_split` (parent language) |
| `cell_id` | int | −1 | capital / first settlement / site cell |
| `year_bp` | double | 0.0 | raw generator year, not re-clamped to the era |
| `pressure_index` | double | 0.0 | clamped `[0,1]` in `add_historical_event` |
| `continuity_index` | double or null | legacy default 0.0 | available value clamped `[0,1]`; current flag distinguishes unavailable continuity |

Serialized by `historical_events_json` (`entity_serialization.cpp:784`).

### `historical_event_model` declaration

`enrich_world_with_historical_geography_model` (`src/magic_geo/historical_geography.py:9`) adds a read-only declaration object under `world["historical_event_model"]` plus `summary.historical_event_model`. It publishes the exact parameter set used by the native generator.

| Declaration key | Value | Line |
| --- | --- | --- |
| `model_type` | `causal_region_culture_language_trade_site_timeline_v2` | `:6`,`:16` |
| `era_model` | `fixed_four_era_strict_year_bp_partition_v1` | `:18` |
| `eras` | the four `{id, dominant_process, start_year_bp, end_year_bp}` objects | `:19`–`:24` |
| `state_foundation_model` | `region_barrier_pressure_and_culture_age_v1` | `:25` |
| `state_foundation_parameters` | `base_pressure 0.18`, `region_barrier_weight 0.32`, `border_barrier_weight 0.28`, `small_region_pressure_bonus 0.18`, `small_region_settlement_maximum 2`, `base_year_bp 380.0`, `culture_age_weight 0.72`, `minimum_year_bp 260.0`, `maximum_year_bp 3800.0` | `:26`–`:36` |
| `dynastic_change_model` | `foundation_age_region_order_pressure_trade_or_isolation_trigger_v1` | `:37` |
| `dynastic_change_parameters` | `pressure_threshold 0.34`, `trade_contact_threshold 0.55`, `route_count_trigger 0`, `foundation_year_weight 0.48`, `region_order_year_step 180.0`, `minimum_year_bp 180.0`, `maximum_year_bp 2100.0`, `trade_pressure_weight 0.18` | `:38`–`:47` |
| `migration_model` | `culture_pressure_or_trade_trigger_same_language_contact_link_v1` | `:48` |
| `migration_parameters` | `migration_pressure_threshold 0.42`, `trade_contact_threshold 0.28`, `base_year_bp 260.0`, `migration_pressure_year_weight 2100.0`, `culture_order_year_step 220.0`, `minimum_year_bp 120.0`, `maximum_year_bp 2600.0` | `:49`–`:57` |
| `language_split_model` | `child_language_divergence_age_change_rate_v1`; min 80.0, max 3400.0 | `:58`–`:60` |
| `trade_boom_model` | `top_volume_then_id_trade_flow_friction_timeline_v1`; max 12 events; `base_year_bp 140.0`, `friction_year_weight 820.0`, `rank_year_step 42.0`, min 70.0, max 1300.0 | `:61`–`:69` |
| `sacred_founding_model` | `first_twelve_ranked_sacred_sites_significance_timeline_v1`; max 12 | `:70`–`:71` |
| `ruin_abandonment_model` | `first_sixteen_ranked_ruins_significance_timeline_v1`; max 16 | `:72`–`:73` |
| `event_order` | `descending_raw_year_bp_then_native_event_enum_v1` | `:74` |
| `era_aggregate_model` | `event_count_and_mean_pressure_continuity_v1` | `:75` |
| `model_limitation` | `diagnostic_single-timeline_events_without_agent_causation_duration_uncertainty_or_observed_historical_calibration` | `:76` |

## Population regions: the native capacity model

`generate_population_regions` (`cpp/src/engine/history.cpp:367`) emits exactly one `PopulationRegion` per `PoliticalRegion`, in region order. Membership is every **non-water** cell whose `political_region_id` equals the region (`:394`–`:396`); all inputs are area-weighted means over that set.

### Per-cell inputs

| Quantity | Formula | Source |
| --- | --- | --- |
| Water security | `clamp(runoff_mm_y / 1300, 0, 0.70)` `+ 0.24` if `is_river` `+ 0.18` if `is_lake` or `water_body == 4` (`fresh_lake`) `+ 0.08` if `has_ocean_neighbor` `− 0.18` if `water_body == 5` (`saline_basin`) or `soil_type == 10` (`saline`), then clamped `[0,1]` | `population_water_security` `:350`–`:365` |
| Climate suitability | `clamp(1 − |T − 17| / 42 − max(0, 360 − P) / 1400 − ice_thickness_m / 2800, 0, 1)` | `:399`–`:405` |
| Hazard | `clamp(0.35·boundary_convergent + 0.25·boundary_transform + local_relief / 4200 + ice_thickness_m / 3200, 0, 1)` | `:406`–`:411` |
| Fertility | `cell.fertility` (native soil/biome output) | `:413` |
| Site strength | `cell.settlement_score` | `:417` |

`local_relief` is declared at `cpp/src/engine/internal.hpp:243` and defined at `cpp/src/engine/climate.cpp:15`; `has_ocean_neighbor` at `cpp/src/engine/environment.cpp:5`.

### Region-level derivation (`:424`–`:447`)

```
fertility       = Σ fertility·area / Σ area
water           = Σ water·area    / Σ area
climate         = Σ climate·area  / Σ area
hazard          = Σ hazard·area   / Σ area
site_strength   = Σ settlement_score·area / Σ area
route_factor    = clamp(region.route_count / max(1, region.settlement_count), 0, 1)

density_capacity            = clamp(1.5 + 64·fertility·water·climate + 12·site_strength, 0.2, 90.0)   [people/km²]
agricultural_capacity_index = clamp(fertility·climate·(0.55 + 0.45·water), 0, 1)
water_security_index        = water
hazard_mortality_index      = hazard
urbanization_fraction       = clamp(0.04 + 0.025·settlement_count + 0.16·route_factor + 0.12·site_strength, 0.02, 0.62)
carrying_capacity           = Σ area · density_capacity
occupancy                   = clamp(0.22 + 0.30·continuity + 0.26·urbanization_fraction
                                       + 0.18·route_factor − 0.18·hazard, 0.05, 0.93)
estimated_population        = carrying_capacity · occupancy
population_pressure         = clamp(estimated_population / carrying_capacity, 0, 1.4)
growth_rate_per_year        = clamp(0.0015 + 0.0065·agricultural_capacity_index + 0.0025·water_security_index
                                       − 0.0030·population_pressure − 0.0045·hazard, −0.012, 0.018)
migration_balance           = clamp(0.5 − culture.migration_pressure, −1, 1)   (0 when the region has no culture)
```

On the available branch, `estimated_population` is defined as `carrying_capacity · occupancy` and occupancy is already clamped to `[0.05, 0.93]`, so the `[0, 1.4]` pressure clamp cannot bind. The original all-default zero record for zero land area or zero member cells (`:420`–`:423`) is a legacy branch. Current records preserve identity and coverage while marking estimates that lack a positive physical denominator unavailable; independent migration and physical descriptors are not masked by an unrelated settlement-input failure.

### `population_regions[]` record fields

The table gives numerical values and historical defaults, not a current missing-input policy. Current carrying capacity, total population and other dependent fields have separate availability flags and are null when unavailable. In particular `site_input_complete` and `population_estimate_available` describe different scopes. Supported zero contributions and structural water zeros remain known zero; unavailable dry-cell settlement inputs are not zeros, and physical territory denominators are retained.

| Field | Type | Default | Source |
| --- | --- | --- | --- |
| `id` | int | sequential | `:377` |
| `region_id` | int | −1 | political region id (`:378`) |
| `culture_region_id` | int | −1 | homeland culture of the region (`:381`) |
| `language_region_id` | int | −1 | culture's language (`:383`) |
| `settlement_count` | int | 0 | copied from `region.settlement_count` (`:379`) |
| `carrying_capacity` | double | 0.0 | people |
| `estimated_population` | double | 0.0 | people |
| `agricultural_capacity_index` | double | 0.0 | `[0,1]` |
| `water_security_index` | double | 0.0 | `[0,1]` |
| `urbanization_fraction` | double | 0.0 | `[0.02, 0.62]` |
| `growth_rate_per_year` | double | 0.0 | `[−0.012, 0.018]` |
| `population_pressure` | double | 0.0 | `[0, 1.4]` (in practice `≤ 0.93`) |
| `migration_balance` | double | 0.0 | `[−1, 1]` |
| `hazard_mortality_index` | double | 0.0 | `[0,1]` |

Emission order and precision: `population_regions_json` (`entity_serialization.cpp:810`), all doubles at `params.float_precision`.

### `population_region_model` declaration

`enrich_world_with_civilization_geography_models` (`src/magic_geo/civilization_geography.py:17`–`:37`) publishes the contract:

| Key | Value |
| --- | --- |
| `model_type` | `causal_area_weighted_capacity_occupancy_population_regions_v2` |
| `membership_model` | `nonwater_political_region_cells_v1` |
| `water_security_model` | `runoff_river_lake_water_neighbor_saline_penalty_v1` |
| `climate_suitability_model` | `temperature_precipitation_ice_bounded_index_v1` |
| `hazard_mortality_model` | `tectonic_local_relief_ice_bounded_index_v1` |
| `density_capacity_model` | `fertility_water_climate_and_site_strength_v1` |
| `density_capacity_parameters` | `base_people_per_km2 1.5`, `agricultural_weight 64.0`, `site_strength_weight 12.0`, `minimum_people_per_km2 0.2`, `maximum_people_per_km2 90.0` |
| `urbanization_model` | `settlement_route_and_site_strength_v1` |
| `occupancy_model` | `continuity_urbanization_routes_hazard_v1` |
| `growth_model` | `agriculture_water_pressure_hazard_bounded_rate_v1` |
| `migration_balance_model` | `one_half_minus_culture_migration_pressure_v1` |
| `model_limitation` | `static_diagnostic_capacity_and_occupancy_without_age_structure_land_use_feedback_disease_or_observed_demographic_calibration` |

## Population history: the era trajectory

`enrich_world_with_population_history` (`src/magic_geo/history_dynamics.py:107`) projects each population region across the four eras.

### Preconditions and empty branches

The following table and original line references document **retained v1 branches**. Current history2 first validates its complete native sources, retains valid region/era slots with field availability maps, and does not replace unknown state with a zero summary or omit a required era trajectory.

| Condition | Behaviour | Line |
| --- | --- | --- |
| `population_regions` is not a list | return unchanged, no keys written | `:110`–`:111` |
| `population_regions` empty | writes `population_histories = []`, zeroed summary (`population_history_count`, `population_history_step_count`, `historical_final_population`, `historical_peak_population_pressure`, `max_population_decline_fraction`) and the model | `:112`–`:121` |
| `historical_eras` empty (with non-empty regions) | **returns without writing `population_histories` or `population_history_model` at all** | `:122`–`:123` |

The guard on line `:110` also tests `isinstance(eras, list)`, but `eras` is the result of `sorted(...)` on line `:109`, so that half of the predicate can never be false — a non-list `historical_eras` raises out of `sorted` / `_era_sort_key` instead of returning cleanly.

Eras are sorted by `-start_year_bp` (`_era_sort_key`, `:34`), i.e. oldest first.

### The step recurrence

For each region, current history2 uses the **first era's territorial snapshot** and propagates unavailable state without resetting it. The original fallback `max(1.0, estimated_population · 0.22)` (`:144`–`:149`) is legacy behavior. The following original recurrence preserves the numerical derivation for comparison; its `else projected` missing-snapshot branch and positive-input floors must not be read as current permission to repair unavailable inputs.

```
duration_years   = max(1, |start_year_bp − end_year_bp|)
instability      = clamp(era.mean_instability, 0, 1)

pressure_drag    = max(0, population_pressure − 0.85) · 0.00018
hazard_drag      = hazard_mortality_index · 0.00010
instability_drag = instability · 0.00014
effective_rate   = clamp(growth_rate_per_year − pressure_drag − hazard_drag − instability_drag, −0.006, 0.008)
multiplier       = exp(clamp(effective_rate · duration_years, −4, 4))

grown            = max(0, start_population · multiplier)
projected        = grown                                      if grown ≤ carrying_capacity
                 = min(grown, K + (grown − K)·0.32)           otherwise      (K = carrying_capacity)

snapshot_pop     = territorial_snapshots[era][region].estimated_population, else projected
migration_delta  = snapshot_pop · migration_balance · 0.035 · (duration_years / 1000)
conflict_loss    = min(Σ ½·estimated_casualties over conflicts of (era, region), snapshot_pop · 0.35)
end_population   = max(0, snapshot_pop + migration_delta − conflict_loss)
```

For an available era snapshot, `snapshot_pop` **replaces** the logistic projection entirely, and the logistic result survives only as an unrecorded intermediate. The declaration retains `"snapshot_model": "era_region_territorial_population_override_v1"` (`:18`). A current null snapshot estimate remains unavailable rather than selecting the historical projection fallback.

`population_pressure` used in the drag term is clamped to `[0, 2.5]` on read (`:141`), so the `pressure − 0.85` term only contributes above 0.85. For native input it is inert, but not because of the `[0.05, 0.93]` occupancy clamp: the unclamped occupancy expression is bounded above by `0.22 + 0.30·continuity + 0.26·urbanization + 0.18·route_factor`, and `continuity_index` is itself capped at 0.90 by its own generator (`cpp/src/engine/civilization.cpp:767`), `urbanization_fraction` at 0.62 and `route_factor` at 1.0, giving `≤ 0.8312`. That is a derived bound on the current generator, not an invariant the code enforces — a hand-edited or third-party `population_regions` record can supply a higher pressure and activate the drag.

The original v1 read floored `carrying_capacity` at 1.0 (`:136`), preventing its `K ≤ 0` branch. That historical floor is not a current missing-value or known-zero conversion rule.

### `population_histories[].steps[]` fields

Current steps keep era identity and publish per-field availability; the numerical entries below can be null when their actual dependency chain is unavailable. A known zero remains zero. History and summary availability is separate from the number of retained slots.

| Field | Type | Rounding | Meaning |
| --- | --- | --- | --- |
| `era_id` | int | — | `era.id`, else the loop index |
| `dominant_process` | str | — | `era.dominant_process` (default `"unknown"`) |
| `start_year_bp` | float | raw | era start |
| `end_year_bp` | float | raw | era end |
| `duration_years` | float | raw | `max(1, |Δyear|)` |
| `start_population` | float | 6 dp | previous step's `end_population` |
| `end_population` | float | 6 dp | after snapshot override, migration and conflict loss |
| `population_change` | float | 6 dp | `end − start` |
| `growth_rate_per_year` | float | 8 dp | region's rate, constant across steps |
| `migration_delta` | float | 6 dp | signed |
| `conflict_loss` | float | 6 dp | capped at 35 % of `snapshot_pop` |
| `carrying_capacity` | float | 6 dp | constant across steps |
| `carrying_capacity_used_fraction` | float | 6 dp | `clamp(end/K, 0, 2.5)` |
| `pressure_index` | float | 6 dp | identical expression to the previous row |
| `instability_index` | float | 6 dp | era `mean_instability` |
| `hazard_mortality_index` | float | 6 dp | region hazard, constant |

For available inputs, `carrying_capacity_used_fraction` and `pressure_index` are computed from the same expression at `:174`–`:175` and are equal.

### `population_histories[]` record fields

| Field | Type | Source |
| --- | --- | --- |
| `id` | int | `population.id` (`:135`) |
| `population_region_id` | int | same value as `id` |
| `region_id` | int | political region |
| `culture_region_id` | int | |
| `language_region_id` | int | |
| `time_step_count` | int | `len(steps)` = number of eras |
| `initial_population` | float | first step's `start_population` |
| `final_population` | float | last step's `end_population` |
| `peak_population` | float | max over the seed and every `end_population` |
| `carrying_capacity` | float | |
| `peak_pressure_index` | float | max step `pressure_index` |
| `steps` | list | above |

### Summary keys

| Key | Definition | Line |
| --- | --- | --- |
| `population_history_count` | number of histories | `:229` |
| `population_history_step_count` | total steps across regions | `:230` |
| `historical_final_population` | Σ final population | `:231` |
| `historical_peak_population_pressure` | max step `pressure_index` worldwide | `:232` |
| `max_population_decline_fraction` | max `max(0, −Δpop) / max(1, start_pop)` | `:233` |
| `population_history_model` | `causal_era_snapshot_logistic_migration_conflict_population_history_v2` | `:27` |

### `population_history_model` declaration (`:10`–`:22`)

| Key | Value |
| --- | --- |
| `era_order` | `descending_start_year_bp_v1` |
| `initial_population_model` | `first_era_territorial_snapshot_or_22_percent_base_v1` |
| `growth_model` | `bounded_exponential_rate_with_pressure_hazard_instability_drag_v1` |
| `carrying_capacity_model` | `overshoot_retains_32_percent_excess_v1` |
| `snapshot_model` | `era_region_territorial_population_override_v1` |
| `migration_model` | `snapshot_population_times_balance_times_0_035_per_millennium_v1` |
| `conflict_loss_model` | `half_region_casualties_capped_at_35_percent_snapshot_population_v1` |
| `model_limitation` | `aggregate_era_projection_without_age_structure_birth_death_cohorts_disease_or_endogenous_migration_feedback` |

## Conflicts

`generate_conflicts` (`cpp/src/engine/history.cpp:453`) proposes one candidate per `BorderSegment`, keeps the best candidate per unordered region pair, then truncates.

### Candidate scoring (`:484`–`:536`)

| Term | Formula | Line |
| --- | --- | --- |
| `pressure` | `0.5·(pop_a.population_pressure ?? 0.35 + pop_b.population_pressure ?? 0.35)` | `:495` |
| `resource_pressure` | `0.72` if either border cell has `resource != none`, else `0.0` | `:499` |
| `water_stress` | `clamp(1 − 0.5·(water_security(a) + water_security(b)), 0, 1)` | `:500`–`:502` |
| `fertility_pressure` | `clamp(0.5·(a.fertility + b.fertility), 0, 1)` | `:503` |
| `trade_chokepoint_index` | `clamp(pair_flow·0.24 + (border.type ∈ {river, mountain, coastal} ? 0.34 : 0), 0, 1)` where `pair_flow = Σ volume_index·friction/100` over **interregional** flows on that pair | `:470`–`:477`, `:504`–`:509` |
| `intensity` | `clamp(0.12 + 0.28·pressure + 0.22·border.barrier_score + 0.18·resource_pressure + 0.16·water_stress + 0.18·trade_chokepoint, 0, 1)` | `:527`–`:532` |
| candidate `score` | `intensity + 0.08·fertility_pressure`; candidate discarded when `score < 0.24` | `:533`–`:536` |

### Cause selection (`:510`–`:526`)

The cause is a running argmax with a final override:

```
cause_score = water_stress;      cause = 0   (water_rights)
if fertility_pressure > cause_score: cause_score = fertility_pressure; cause = 1  (fertile_plain)
if resource_pressure  > cause_score: cause_score = resource_pressure;  cause = 2  (mining_claim)
if trade_chokepoint   > cause_score: cause_score = trade_chokepoint;   cause = 3  (trade_chokepoint)
if border.barrier_score > cause_score AND border.type != open_lowland: cause = 4  (border_fragmentation)
```

`CONFLICT_CAUSE_NAMES[5]` is `sacred_site` and is **never assigned** by this generator — the enum value exists in the schema but is unreachable from `generate_conflicts`. The final override does not update `cause_score`, so it is an unconditional last-writer once its predicate holds.

### Chronology, forces and diagnostics (`:544`–`:613`)

```
contested_cell_id      = intensity ≥ 0.5 ? border.cell_a : border.cell_b
start_year_bp          = clamp(160 + 1850·intensity + 17·(pairs_stored_so_far + 1), 90, 2600)
duration               = clamp(12 + 90·intensity + 18·trade_chokepoint, 8, 160)
end_year_bp            = max(0, start_year_bp − duration)
war_duration_years     = start_year_bp − end_year_bp
era_id                 = historical_era_for_year_bp(start_year_bp)

logistics_strain_index = clamp(0.24·barrier + 0.22·water_stress + 0.20·trade_chokepoint
                                 + 0.18·intensity + (border.type ∈ {river, mountain} ? 0.10 : 0), 0, 1)
mobilization_rate      = clamp(0.012 + 0.070·intensity + 0.022·trade_chokepoint + 0.015·pressure
                                 − 0.018·logistics_strain, 0.004, 0.16)
region_x_force_estimate= max(0, pop_x · mobilization_rate · (0.72 + 0.28·urban_x + 0.14·route_factor_x
                                 − 0.22·logistics_strain))
mobilized_population   = force_a + force_b
estimated_casualties   = ½(pop_a + pop_b) · intensity · (0.006 + 0.025·intensity)
casualty_rate          = clamp(estimated_casualties / (pop_a + pop_b), 0, 1)   (0 when total is 0)
economic_disruption_index = clamp(0.18·intensity + 0.18·logistics_strain + 0.18·trade_chokepoint
                                 + 0.16·resource_pressure + 0.14·water_stress
                                 + 0.16·(war_duration_years / 160), 0, 1)
```

The missing-record defaults `urban_x = 0.05` and `route_factor_x = 0.0` are legacy branches. Current conflict inference requires complete inputs over the actual global border-pair candidate ranking; incomplete selection emits no partial ranked list and cannot claim a known-zero conflict total.

The `start_year_bp` term `17 · (best_by_pair.size() + 1)` depends on how many *distinct region pairs* have already been inserted into the candidate map at that moment, i.e. it is insertion-order dependent within the border loop.

### Outcome (`:599`–`:613`)

```
effectiveness_x = force_x · (1 + 0.26·route_factor_x + 0.18·urban_x − 0.38·logistics_strain)
force_scale     = max(1, mobilized_population)
advantage       = (effectiveness_a − effectiveness_b) / force_scale
```

| Predicate (in order) | `outcome` | Enum |
| --- | --- | --- |
| `logistics_strain > 0.72 && intensity > 0.58` | 4 | `exhaustion` |
| `|advantage| < 0.08` | 0 | `stalemate` |
| `|advantage| < 0.20 && trade_chokepoint > 0.38` | 3 | `border_shift` |
| `advantage > 0` | 1 | `region_a_victory` |
| otherwise | 2 | `region_b_victory` |

### Selection and truncation (`:614`–`:638`)

The best-scoring candidate per unordered `(min, max)` region pair is retained (`:614`–`:616`). Candidates are then sorted by descending raw `score`, ties broken by ascending `(region_a, region_b)` (`:624`–`:629`), and truncated to `min(candidates, max(0, political_region_count · 2))` (`:630`). Ids are reassigned `0..target-1`.

### `conflicts[]` record fields

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `id` | int | 0 | dense after truncation |
| `era_id` | int | 0 | from `start_year_bp` |
| `region_a`, `region_b` | int | −1 | sorted pair (`region_a < region_b`) |
| `culture_a`, `culture_b` | int | −1 | homeland culture of each region |
| `cause` | enum string | `water_rights` | `CONFLICT_CAUSE_NAMES` (`sacred_site` unreachable) |
| `outcome` | enum string | `stalemate` | `CONFLICT_OUTCOME_NAMES` |
| `contested_cell_id` | int | −1 | one of the two border cells |
| `start_year_bp`, `end_year_bp` | double | 0.0 | `end` floored at 0 |
| `war_duration_years` | double | 0.0 | `start − end` |
| `intensity` | double | 0.0 | `[0,1]` |
| `resource_pressure` | double | 0.0 | 0.0 or 0.72 |
| `water_stress` | double | 0.0 | `[0,1]` |
| `trade_chokepoint_index` | double | 0.0 | `[0,1]` |
| `region_a_force_estimate`, `region_b_force_estimate` | double | 0.0 | people |
| `mobilized_population` | double | 0.0 | sum of the two |
| `casualty_rate` | double | 0.0 | `[0,1]` |
| `logistics_strain_index` | double | 0.0 | `[0,1]` |
| `economic_disruption_index` | double | 0.0 | `[0,1]` |
| `estimated_casualties` | double | 0.0 | people |

Emission order: `conflicts_json` (`entity_serialization.cpp:837`), all doubles at `params.float_precision`.

### `conflict_model` declaration (`src/magic_geo/civilization_geography.py:38`–`:56`)

| Key | Value |
| --- | --- |
| `model_type` | `causal_border_pair_pressure_trade_conflict_selection_v2` |
| `candidate_model` | `highest_score_border_per_sorted_region_pair_v1` |
| `minimum_candidate_score` | `0.24` |
| `maximum_conflicts_per_region` | `2` |
| `cause_model` | `water_fertility_resource_trade_then_nonopen_border_priority_v1` |
| `resource_pressure_if_present` | `0.72` |
| `trade_chokepoint_model` | `interregional_pair_flow_volume_times_friction_plus_hard_border_v1` |
| `hard_border_trade_bonus` | `0.34` |
| `intensity_model` | `population_border_resource_water_trade_weighted_index_v1` |
| `candidate_score_fertility_weight` | `0.08` |
| `record_order` | `descending_raw_candidate_score_then_region_pair_v1` |
| `contested_cell_model` | `border_cell_a_if_intensity_at_least_one_half_else_cell_b_v1` |
| `chronology_model` | `intensity_candidate_map_size_duration_and_era_v1` |
| `war_diagnostics_model` | `population_route_urbanization_logistics_mobilization_casualty_disruption_v1` |
| `outcome_model` | `exhaustion_stalemate_border_shift_or_force_advantage_v1` |
| `model_limitation` | `one_diagnostic_conflict_per_adjacent_region_pair_without_strategy_diplomacy_uncertainty_or_observed_war_calibration` |

### Conflict summary keys (`cpp/src/engine/summary.cpp:1843`–`:1857`)

| Key | Definition |
| --- | --- |
| `conflict_count` | record count |
| `high_intensity_conflict_count` | count where the **serialization-quantized** intensity `round(intensity·10^clamp(float_precision,0,8))/10^…` is `≥ 0.65` (`:712`, `:721`–`:724`) |
| `mean_conflict_intensity` | arithmetic mean of raw intensities |
| `mean_war_duration_years` | mean `war_duration_years` |
| `total_mobilized_population` | Σ `mobilized_population` |
| `mean_conflict_logistics_strain_index` | mean |
| `mean_conflict_economic_disruption_index` | mean |
| `high_economic_disruption_conflict_count` | count where raw `economic_disruption_index ≥ 0.65` (no quantization) |
| `mean_conflict_casualty_rate` | mean |
| `max_conflict_casualty_rate` | max |

The asymmetry is deliberate and load-bearing: `high_intensity_conflict_count` genuinely depends on `output.float_precision` because the threshold is applied to the value as it will be *emitted*, while `high_economic_disruption_conflict_count` is applied to the raw double.

## Dynasties and the genealogy model

### Native dynasty chains (`cpp/src/engine/history.cpp:641`–`:758`)

Per political region:

```
conflict_pressure = clamp(Σ intensity over conflicts touching the region / 3.0, 0, 1)
founding_year     = year_bp of the OLDEST (largest year_bp) type-0 state_foundation event for the region,
                    else clamp(620 + 240·(region.id + 1), 260, 3200)
founding_event_id = that event's id, else −1

base_succession_pressure = clamp(0.18 + 0.34·population_pressure + 0.36·conflict_pressure
                                   + (region.route_count == 0 ? 0.10 : 0) − 0.24·continuity, 0, 1)
dynasty_count            = 1 + (bsp > 0.36) + (bsp > 0.66)          →  1, 2 or 3
```

The absent-record defaults `population_pressure = 0.4`, `continuity = 0.5` (`:678`–`:680`) and synthetic missing-foundation date above are legacy branches. Current dynasty inference reports per-region lineage coverage and does not manufacture chronology from unavailable age or pressure.

For dynasty index `i ∈ [0, n)` with `n = dynasty_count` and `F = founding_year`:

| Field | Formula | Line |
| --- | --- | --- |
| `lineage_depth` | `i` | `:707` |
| `start_year_bp` | `F · (1 − i/n)` | `:708` |
| `end_year_bp` | `0` when `i = n−1`, else `F · (1 − (i+1)/n)` | `:709`–`:711` |
| `duration_years` | `max(0, start − end)` = `F/n` | `:712` |
| `succession_pressure` | `clamp(bsp + 0.10·i, 0, 1)` | `:713` |
| `legitimacy_index` | `clamp(0.34 + 0.42·continuity + 0.18·region.mean_settlement_score − 0.22·succession_pressure − 0.10·conflict_pressure, 0, 1)` | `:714`–`:719` |
| `dynastic_continuity_index` | `clamp(0.26 + 0.34·legitimacy + 0.22·(duration/max(1, F)) + 0.18·(1 − succession_pressure), 0, 1)` | `:720`–`:726` |
| `parent_dynasty_id` | previous dynasty in the same region, `−1` for `i = 0` | `:704`, `:741` |
| `founder_dynasty_id` | the `i = 0` dynasty id of that region | `:698`–`:705` |
| `founding_event_id` | the region's foundation event id for `i = 0`, else `−1` | `:706` |

`collapse_reason` priority (`:727`–`:739`):

| Predicate (first match) | Value | Enum |
| --- | --- | --- |
| `i == n − 1` (the surviving terminal dynasty) | 0 | `continuity` |
| `conflict_pressure > 0.45` | 5 | `conflict_defeat` |
| `population_pressure > 0.68` | 4 | `migration_pressure` |
| `region.dominant_resource != none && region.type == mining_domain` | 2 | `resource_shock` |
| `region.route_count == 0` | 3 | `trade_decline` |
| otherwise | 1 | `succession_crisis` |

A post-pass (`:744`–`:756`) fills `child_dynasty_ids` / `child_dynasty_count` on the parent and sets `successor_dynasty_id` to the child with the largest `start_year_bp`. Because the chain is strictly linear (one child per parent), the successor is always that single child.

### `dynasties[]` record fields

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `id` | int | 0 | globally sequential across regions |
| `region_id` | int | −1 | |
| `culture_region_id` | int | −1 | |
| `language_region_id` | int | −1 | |
| `parent_dynasty_id` | int | −1 | −1 marks a root |
| `founder_dynasty_id` | int | −1 | the `lineage_depth = 0` dynasty of the region |
| `successor_dynasty_id` | int | −1 | set in the post-pass |
| `founding_event_id` | int | −1 | only on the root |
| `collapse_reason` | enum string | `continuity` | `DYNASTY_COLLAPSE_REASON_NAMES` |
| `lineage_depth` | int | 0 | 0-based index within the region chain |
| `child_dynasty_count` | int | 0 | 0 or 1 |
| `child_dynasty_ids` | int[] | `[]` | |
| `start_year_bp`, `end_year_bp` | double | 0.0 | |
| `duration_years` | double | 0.0 | |
| `legitimacy_index` | double | 0.0 | `[0,1]` |
| `succession_pressure` | double | 0.0 | `[0,1]` |
| `dynastic_continuity_index` | double | 0.0 | `[0,1]` |

Emission order: `dynasties_json` (`entity_serialization.cpp:873`).

Summary rollups (`summary.cpp:729`–`:739`, emitted `:1858`–`:1864`): `dynasty_count`, `dynastic_lineage_count` (records with `parent_dynasty_id ≥ 0`), `dynasty_root_count` (records with `parent_dynasty_id < 0`), `dynasty_successor_link_count`, `max_dynasty_lineage_depth`, `mean_dynastic_continuity_index`.

### `dynasty_model` declaration (`src/magic_geo/civilization_geography.py:57`–`:69`)

| Key | Value |
| --- | --- |
| `model_type` | `causal_foundation_continuity_pressure_dynasty_lineages_v2` |
| `foundation_model` | `oldest_state_foundation_event_per_region_v1` |
| `succession_pressure_model` | `population_conflict_route_and_culture_continuity_v1` |
| `dynasty_count_thresholds` | `[0.36, 0.66]` |
| `lineage_model` | `contiguous_region_chain_with_root_parent_child_successor_links_v1` |
| `duration_model` | `equal_foundation_year_partition_by_region_dynasty_count_v1` |
| `legitimacy_model` | `continuity_settlement_succession_and_conflict_v1` |
| `dynastic_continuity_model` | `legitimacy_duration_and_inverse_succession_pressure_v1` |
| `collapse_reason_model` | `continuity_conflict_migration_resource_trade_then_succession_priority_v1` |
| `model_limitation` | `single_linear_dynasty_chain_per_region_without_person_level_succession_branch_competition_or_observed_genealogy_calibration` |

### Named rulers (`src/magic_geo/dynasty_genealogy.py`)

`enrich_world_with_dynasty_genealogy` (`:110`) expands every dynasty into individual rulers. Ruler count (`_dynasty_ruler_count`, `:104`–`:107`):

```
count = max(2, min(6, floor(duration_years / 420) + 2 + (1 if succession_pressure ≥ 0.55 else 0)))
reign_span = duration_years / count
```

Per-ruler derivation (`:147`–`:198`), with `economy_strength = clamp(peak_gross_output_index / 1200)`, `treasury_strength = clamp(peak_treasury_index / 250)` and `conflict_pressure = clamp(mean intensity over the region's conflicts)`:

| Field | Formula |
| --- | --- |
| `reign_start_year_bp` | `max(end_year_bp, start_year_bp − i·reign_span)` |
| `reign_end_year_bp` | `max(end_year_bp, start_year_bp − (i+1)·reign_span)`; forced to `end_year_bp` for the last ruler |
| `reign_length_years` | `max(0, reign_start − reign_end)` |
| `birth_year_bp` | `reign_start + 24 + succession_pressure·18` |
| `ruler_lineage_depth` | `dynasty.lineage_depth + i` |
| `legitimacy_index` | `clamp(0.45·dynasty.legitimacy_index + 0.24·continuity + 0.12·economy_strength + 0.07·treasury_strength + 0.12·(1 − pressure))` |
| `succession_claim_strength` | `clamp(0.72·legitimacy + 0.28·continuity)` |
| `military_prestige_index` | `clamp(0.48·conflict_pressure + 0.32·(max_army_capacity_population / 60 000 000) + 0.20·pressure)` |
| `economic_patronage_index` | `clamp(0.50·economy_strength + 0.30·treasury_strength + 0.20·continuity)` |
| `succession_crisis_risk` | `clamp(0.42·pressure + 0.24·conflict_pressure + 0.24·(1 − legitimacy) + 0.10·(i / max(1, count−1)))` |
| `name` | `NAME_ROOTS[(dynasty_id·7 + i·3 + lineage_depth) mod 25] + " " + roman(i+1)` (`_ruler_name` `:80`; `_roman` clamps to `[1,20]`) |

Succession links (`:191`–`:198`): `predecessor_ruler_id` is the immediately preceding ruler and `successor_ruler_id` is back-filled onto that predecessor. `parent_ruler_id` is different: it is assigned at the *end* of each iteration as `previous_ruler_id if previous_ruler_id >= 0 else ruler_id` (`:197`) and read at the *start* of the next, so it lags the predecessor chain by one link.

| Ruler index `i` within the dynasty | `predecessor_ruler_id` | `parent_ruler_id` |
| --- | --- | --- |
| 0 | −1 | −1 |
| 1 | ruler 0 | ruler 0 |
| ≥ 2 | ruler `i−1` | ruler `i−2` |

| `rulers[]` field | Type | Notes |
| --- | --- | --- |
| `id` | int | global sequential |
| `dynasty_id`, `region_id`, `culture_region_id`, `language_region_id` | int | copied from the dynasty |
| `name` | str | deterministic root + Roman regnal number |
| `regnal_number` | int | `i + 1` |
| `parent_ruler_id`, `predecessor_ruler_id`, `successor_ruler_id` | int | −1 when absent |
| `spouse_ruler_id`, `marriage_alliance_id`, `cadet_branch_id` | int | −1 unless assigned later |
| `birth_year_bp`, `reign_start_year_bp`, `reign_end_year_bp`, `reign_length_years` | float | 6 dp |
| `ruler_lineage_depth` | int | |
| `legitimacy_index`, `succession_claim_strength`, `military_prestige_index`, `economic_patronage_index`, `succession_crisis_risk` | float | 6 dp, `[0,1]` |

**Cadet branches** (`:206`–`:225`) are created only when a dynasty has `≥ 3` rulers: founder is ruler index 1, heirs are ruler indices 2–4 (`ruler_ids[2:min(len, 5)]`).

| `cadet_branches[]` field | Formula |
| --- | --- |
| `id`, `dynasty_id`, `parent_dynasty_id` | ids |
| `founder_ruler_id` | `ruler_ids[min(1, len−1)]` |
| `heir_ruler_ids` | `ruler_ids[2:min(len,5)]` |
| `branch_start_year_bp` | founder's `reign_start_year_bp` |
| `branch_end_year_bp` | last heir's `reign_end_year_bp`, else founder's |
| `claim_strength` | `clamp(0.72·founder.succession_claim_strength + 0.28·succession_pressure)` |
| `cadet_legitimacy_index` | `clamp(0.80·founder.legitimacy_index + 0.20·dynastic_continuity_index)` |

**Marriage alliances** (`:227`–`:283`) iterate dynasties sorted by `(region_id asc, −start_year_bp, id asc)`. For each, the first later dynasty in that order with rulers and a *different* `region_id` is the partner; if none, the first other dynasty with rulers is used. Spouses are `ruler_ids[min(1, len−1)]` on each side; a pair is skipped when either spouse is already married.

| `marriage_alliances[]` field | Formula |
| --- | --- |
| `id`, `dynasty_a_id`, `dynasty_b_id`, `ruler_a_id`, `ruler_b_id`, `region_a_id`, `region_b_id` | ids |
| `alliance_year_bp` | `max(ruler_a.reign_end, min(a.reign_start, b.reign_start) − max(a.reign_length, 1)·0.35)` |
| `alliance_strength` | `clamp(0.32·(legit_a + legit_b) + 0.18·(patronage_a + patronage_b))` |
| `trade_pact_index` | `clamp(0.65·alliance_strength + 0.18)` |
| `succession_dispute_risk` | `clamp(0.45·(risk_a + risk_b))` |

Genealogy summary keys (`:288`–`:307`): `ruler_count`, `named_ruler_dynasty_count`, `ruler_marriage_alliance_count`, `cadet_branch_count`, `married_ruler_count`, `max_ruler_lineage_depth`, `mean_ruler_legitimacy_index`, `mean_succession_crisis_risk`, `mean_marriage_alliance_strength`, `mean_cadet_branch_claim_strength`, plus `ruler_genealogy_model`. Current genealogy2 separates regional lineage coverage from complete global alliance selection. Unavailable dependent estimates, spouse/alliance inferences and inferred counts are null with typed coverage; emitted record counts do not certify complete selection. Independent identity and lineage structure are retained where their own inputs are available.

Declaration (`:39`–`:51`): `ruler_count_model = dynasty_duration_pressure_bounded_two_to_six_rulers_v1`, `reign_model = equal_dynasty_duration_partition_v1`, `succession_model = ordered_predecessor_successor_and_parent_links_v1`, `cadet_branch_model = second_ruler_founder_with_next_three_heirs_v1`, `marriage_model = sorted_dynasty_first_available_cross_region_second_ruler_pair_v1`, `name_model = deterministic_root_and_regnal_number_v1`, `model_limitation = synthetic_regnal_genealogy_without_age_consistent_reproduction_competing_heirs_gender_demography_or_observed_calibration`.

## Territorial snapshots as the era coupling

`generate_territorial_snapshots` (`cpp/src/engine/history.cpp:773`) produces **one snapshot per era**. It is the coupling record that carries region area and population into each era, and it is the direct input to both the population override and the economy `stability_index`.

Base regions are built once from the non-water cells of each political region (`:810`–`:840`): `cell_count`, `area_km2`, area-weighted `centroid_lat_deg` / `centroid_lon_deg`, a Cartesian area-weighted centre used for ring construction, and `boundary_cell_ids` for cells with a water or foreign-region neighbour. Geometry is derived with `watershed_boundary_ring(cells, boundary_cell_ids, weighted_center, 64)` (tangent-plane angle sort, capped at 64 ring points), `ring_perimeter_km` and `ring_projected_area_km2` (centred orthographic shoelace), and `boundary_cell_ids` is finally down-sampled by `sampled_ids(..., 64)` (uniform floor stride, `:760`–`:771`).

Per era, each base region is copied and scaled on the available branch (`:887`–`:942`). Current snapshots preserve `base_area_km2`, `base_dissolved_polygon_area_km2` and `base_boundary_perimeter_km` independently. Scaled geometry/stability and population use separate availability flags; unavailable scaled fields and dependent aggregates are null, while membership, era identity and base geometry remain:

```
era_area_factors       = {0.48, 0.78, 0.64, 1.0}    (index = era.id)
era_population_factors = {0.34, 0.58, 0.74, 1.0}
region_conflict        = clamp(Σ intensity over conflicts of (region, era) / 2, 0, 1)
stability_index        = clamp(0.42 + 0.42·continuity − 0.30·region_conflict + 0.10·era.mean_connectivity, 0, 1)
region_area_factor     = era_area_factors[era] · (0.82 + 0.18·stability)

area_km2                    *= region_area_factor
dissolved_polygon_area_km2  *= region_area_factor
boundary_perimeter_km       *= sqrt(region_area_factor)
polygon_area_error_fraction  = |dissolved − area| / area
compactness_index            = clamp(4π·dissolved / max(1, perimeter²), 0, 1)
geometry_quality             = clamp(0.62·clamp(1 − area_error, 0, 1) + 0.38·clamp(ring_points/24, 0, 1), 0, 1)
estimated_population         = population_region.estimated_population · era_population_factors[era] · (0.82 + 0.22·stability)
```

Snapshot aggregates (`:934`–`:953`):

```
year_bp               = ½(era.start_year_bp + era.end_year_bp)
assigned_land_fraction= clamp(Σ scaled region area / total land area, 0, 1)
largest_share         = largest_region_area_km2 / (assigned_land_fraction · land_area)
fragmentation_index   = clamp(0.72·(region_count > 1 ? 1 − largest_share : 0) + 0.28·(Σ region_conflict / region_count), 0, 1)
```

Note the `0.82 + 0.18·stability` area scaling and the `0.82 + 0.22·stability` population scaling use different second coefficients; that asymmetry is in the source (`:912` vs `:932`).

| `territorial_snapshots[]` field | Type | Notes |
| --- | --- | --- |
| `id` | int | sequential, one per era |
| `era_id` | int | |
| `dominant_process` | enum string | `HISTORICAL_PROCESS_NAMES` |
| `region_count` | int | regions with `cell_count > 0` |
| `largest_region_id` | int | −1 when empty |
| `regions` | `SnapshotRegion[]` | below |
| `year_bp` | double | era midpoint |
| `assigned_land_fraction` | double | `[0,1]` |
| `estimated_population` | double | Σ over regions |
| `largest_region_area_km2` | double | |
| `fragmentation_index` | double | `[0,1]` |

| `territorial_snapshots[].regions[]` field | Type | Notes |
| --- | --- | --- |
| `region_id`, `capital_settlement_id`, `culture_region_id`, `language_region_id` | int | −1 defaults |
| `cell_count` | int | unscaled member cell count |
| `crosses_antimeridian` | bool | true when the ring longitude span exceeds 180° |
| `boundary_cell_ids` | int[] | at most 64, uniform stride sample |
| `boundary_ring` | `[lat_deg, lon_deg][]` | at most 64 points before closure |
| `area_km2` | double | era-scaled |
| `boundary_perimeter_km` | double | era-scaled by `sqrt` |
| `dissolved_polygon_area_km2` | double | era-scaled |
| `polygon_area_error_fraction` | double | |
| `compactness_index` | double | `[0,1]` |
| `geometry_quality` | double | `[0,1]` |
| `estimated_population` | double | era-scaled |
| `stability_index` | double | `[0,1]` |
| `centroid_lat_deg`, `centroid_lon_deg` | double | area-weighted, capital-cell fallback |

Emission order: `snapshot_regions_json` (`entity_serialization.cpp:904`), `territorial_snapshots_json` (`:935`). Snapshot summary rollups only count regions with `dissolved_polygon_area_km2 > 0` (`summary.cpp:741`–`:752`).

The declaration is `territorial_snapshot_model` (`src/magic_geo/territorial_geography.py:13`–`:30`), which restates the era factors, the 64-point ring/cell caps, `dissolved_area_model = centered_orthographic_shoelace_proxy_v1`, and `model_limitation = scaled_static_regions_with_sampled_centroid_ordered_rings_not_exact_dynamic_cell_edge_territories`.

## Economy history

`enrich_world_with_economy_history` (`src/magic_geo/economy_dynamics.py:119`) steps one economy per population history, on the same era grid.

### Preconditions

This table records the **legacy economy1 branches**. Current economy2 validates its declared parents, retains valid region/era slots, and propagates unavailable sequential state instead of silently resetting treasury or publishing a known-zero aggregate. Its record, step and summary availability maps identify the actual dependent fields.

| Condition | Behaviour | Line |
| --- | --- | --- |
| `population_histories` / `historical_eras` not lists | return unchanged | `:122`–`:123` |
| `population_histories` empty | write `economy_histories = []`, 12 zeroed summary keys and the model | `:124`–`:140` |
| `historical_eras` empty | **return without writing `economy_histories` or `economy_history_model`** | `:141`–`:142` |
| a population history has `region_id < 0`, or produces zero steps | that region is skipped entirely (`continue`) | `:165`–`:166`, `:283`–`:284` |

### Region-constant inputs

| Quantity | Source |
| --- | --- |
| `agricultural_capacity`, `water_security`, `urbanization`, `pressure` (clamped to `[0,2.5]`) | `population_regions[region]` |
| `resource_value` | `_resource_value(political_region.dominant_resource)` — a 17-entry lookup (`:34`–`:54`) with fallback `0.16` |
| `route_count`, `barrier_pressure` | `political_regions[region]` |
| `settlement_count` | population region, falling back to political region |
| `trade["volume"]` | Σ `volume_index / (1 + clamp(friction,0,4)·0.35)` over incident flows (`_trade_by_region`, `:57`–`:73`) |
| `interregional_fraction` | `interregional_volume / volume` |
| `average_trade_friction` | `friction_sum / count` |

`_resource_value` accepts 17 names; the native `RESOURCE_NAMES` enum only ever emits `none`, `volcanic_arc_metals`, `craton_iron_gold`, `sedimentary_fuels`, `evaporites`, `placer_metals`, `geothermal`, `fertile_alluvium`, `coastal_fisheries`. Of these only `none` (0.08), `sedimentary_fuels` (0.38) and `geothermal` (0.26) match a table key; the remaining six fall through to the `0.16` default. The other table entries (`salt`, `iron`, `copper`, `diamonds`, …) are unreachable from native output.

### Per-step state variables (`:187`–`:267`)

For available inputs, let `pm = end_population / 1 000 000`, `stability = snapshot_region.stability_index`, `fragmentation = 1 − stability`. The missing-snapshot fallback `1 − era_instability` is legacy behavior, not a replacement for a current null stability estimate.

| Variable | Formula |
| --- | --- |
| `agricultural_output_index` | `pm · agricultural_capacity · (0.45 + water_security·0.85) · (1 − min(0.35, pressure·0.08))` |
| `resource_output_index` | `pm · resource_value · (0.45 + urbanization·0.45 + settlement_count·0.025)` |
| `trade_output_index` | `trade_volume · (0.35 + era_connectivity·0.35 + interregional_fraction·0.20) + route_count·1.75` |
| `urban_services_index` | `pm · urbanization · (0.35 + settlement_count·0.035 + stability·0.30)` |
| `gross_output_index` | `max(0, agricultural + resource + trade + urban_services)` |
| `tax_revenue_index` | `gross · (0.055 + stability·0.055 + urbanization·0.025)` |
| `trade_revenue_index` | `trade_output · (0.035 + interregional_fraction·0.035) / (1 + average_trade_friction·0.15)` |
| `army_capacity_population` | `end_population · (0.009 + pressure·0.004 + stability·0.003 + resource_value·0.002)` |
| `mobilized_force_population` | Σ `region_x_force_estimate` over conflicts of `(era, region)` (`_conflict_by_era_region`, `:76`–`:103`) |
| `administration_cost_index` | `gross · (0.035 + barrier_pressure·0.025 + fragmentation·0.035)` |
| `army_maintenance_cost_index` | `army_capacity / 100 000 · (0.045 + pressure·0.018)` |
| `war_cost_index` | `mobilized_force / 100 000 · (0.11 + mean_conflict_logistics·0.10 + mean_conflict_disruption·0.14)` |
| `insolvency_adjustment_index` | `max(0, −raw_treasury_end)` |
| `treasury_end_index` | `max(0, raw_treasury_end)` where `raw = prev + tax + trade_rev − admin − army_maint − war` |
| `balance_residual_index` | `prev + tax + trade_rev + insolvency − admin − army_maint − war − treasury_end` |
| `prosperity_index` | `clamp(gross / max(1, pm) / 1.6, 0, 1)` |
| `food_security_index` | `clamp(agricultural_output / max(1, pm·0.42), 0, 1)` |
| `trade_dependency_index` | `clamp(trade_output / max(1, gross), 0, 1)` |
| `military_burden_index` | `clamp((army_maint + war) / max(1, tax + trade_rev), 0, 1)` |

Initial treasury (`:183`): `max(0, initial_population / 1 000 000 · 0.08)`.

For available treasury inputs, `balance_residual_index` is **zero by the algebraic identity** — it is a closure witness, not an independent quantity: substituting `treasury_end = max(0, raw)` and `insolvency = max(0, −raw)` gives `raw + max(0,−raw) − max(0,raw) = 0` in both branches. Its published residual checks serialization closure. An unavailable current step publishes null rather than a zero closure claim.

The `max(1.0, …)` denominators in `prosperity_index`, `food_security_index`, `trade_dependency_index` and `military_burden_index` are unit floors, not economics: for a region below one million people, or with gross output below 1.0 index unit, the ratio degenerates to the numerator. These are index quantities with no currency, no price level and no deflator.

**Era indexing subtlety** (`:192`): the step reads `era = eras[index]` positionally from the **raw** `world["historical_eras"]` list, while `era_id` comes from the population history step (which iterated eras sorted by descending `start_year_bp`). With native output the two orders coincide, because `default_historical_eras` already emits ids `0..3` in descending-start order. A hand-edited world with permuted eras would decouple them.

### Record fields

| `economy_histories[].steps[]` field | Type | Rounding |
| --- | --- | --- |
| `era_id` | int | — |
| `dominant_process` | str | — |
| `start_year_bp`, `end_year_bp` | float | raw |
| `duration_years` | float | 6 dp |
| `population` | float | 6 dp |
| `gross_output_index` | float | 6 dp |
| `agricultural_output_index`, `resource_output_index`, `trade_output_index`, `urban_services_index` | float | 6 dp |
| `treasury_start_index`, `tax_revenue_index`, `trade_revenue_index` | float | 6 dp |
| `administration_cost_index`, `army_maintenance_cost_index`, `war_cost_index` | float | 6 dp |
| `insolvency_adjustment_index`, `treasury_end_index`, `balance_residual_index` | float | 6 dp |
| `army_capacity_population`, `mobilized_force_population` | float | 6 dp |
| `prosperity_index`, `food_security_index`, `trade_dependency_index`, `military_burden_index`, `stability_index` | float | 6 dp |

| `economy_histories[]` field | Source |
| --- | --- |
| `id` | sequential |
| `region_id` | political region |
| `population_region_id`, `culture_region_id`, `language_region_id` | copied from the population history |
| `dominant_resource` | political region string |
| `time_step_count` | `len(steps)` |
| `final_gross_output_index`, `final_treasury_index` | last step |
| `peak_gross_output_index`, `peak_treasury_index` | running maxima (peak treasury is seeded with the initial treasury) |
| `max_army_capacity_population` | max step `army_capacity_population` |
| `steps` | above |

### Economy summary keys (`:306`–`:318`)

| Key | Definition |
| --- | --- |
| `economy_history_count` | histories written |
| `economy_history_step_count` | total steps |
| `historical_final_gross_output_index` | Σ last-step gross output |
| `historical_final_treasury_index` | Σ last-step treasury |
| `historical_total_tax_revenue_index` | Σ over all steps |
| `historical_total_trade_revenue_index` | Σ over all steps |
| `historical_total_war_cost_index` | Σ over all steps |
| `historical_peak_army_capacity_population` | max over all steps |
| `mean_historical_prosperity_index` | mean over steps |
| `mean_historical_trade_dependency_index` | mean over steps |
| `mean_historical_military_burden_index` | mean over steps |
| `high_military_burden_economy_step_count` | steps with `military_burden_index ≥ 0.65` |
| `economy_history_model` | `causal_population_trade_conflict_treasury_economy_history_v2` |

Declaration (`:9`–`:22`): `trade_model = incident_friction_discounted_trade_volume_v1`, `conflict_model = era_region_force_casualty_logistics_disruption_aggregate_v1`, `output_model = agriculture_resource_trade_and_urban_services_sum_v1`, `revenue_model = stability_urbanization_tax_and_interregional_trade_v1`, `cost_model = administration_army_maintenance_and_conflict_war_cost_v1`, `treasury_model = nonnegative_balance_with_explicit_insolvency_adjustment_v1`, `army_model = population_pressure_stability_resource_capacity_v1`, `diagnostic_model = prosperity_food_trade_dependency_and_military_burden_v1`, `model_limitation = aggregate_index_economy_without_prices_inventory_production_functions_agent_equilibrium_or_empirical_calibration`.

## Demographic agents

`enrich_world_with_demographic_agents` (`src/magic_geo/demographic_agents.py:152`) downscales the aggregate trajectories into four record families plus a life-event ledger. An "agent" here is a **representative record**, not a simulated individual with autonomous behaviour. Current demographic2 retains fixed household/era slots with nullable dependent estimates. Person sampling uses six records only for known positive population; known zero gives a complete empty sample, while unknown population gives an unavailable empty sample. Firm selection separately reports whether all five actual sector predicates are known.

### Household cohorts

Exactly three cohorts per population region, in the order `rural_household`, `urban_household`, `mobile_household` (`_cohort_specs`, `:114`–`:123`):

```
migrant_fraction = clamp(|migration_balance|·0.55 + pressure·0.035, 0.02, 0.18)
urban_fraction   = clamp(urbanization_fraction, 0.05, 0.88)
rural_fraction   = max(0.05, 1 − urban_fraction − migrant_fraction)
total            = rural + urban + migrant                    (renormalization divisor)
household sizes  = 5.1 (rural), 3.8 (urban), 4.2 (mobile)
```

Population allocation (`:201`–`:206`): the first two cohorts take `final_population · fraction/total`; the **last** cohort receives the exact residual `final_population − allocated`, so the three cohort populations sum to `final_population` without rounding drift.

| Field | Formula |
| --- | --- |
| `population` | as above |
| `household_count` | `population / max(1, average_household_size)` |
| `vulnerability_index` | `clamp(hazard·0.30 + pressure·0.24 + (1−water_security)·0.20 + (1−food_security)·0.14 + market_pressure·0.08 + modifier)` with `modifier` = `+0.04` rural, `−0.02` urban, `+0.10` mobile |
| `migration_propensity_index` | `clamp(|migration_balance|·0.38 + pressure·0.18 + vulnerability·0.22 + (1−logistics_resilience)·0.14 + (0.12 if mobile))` |
| `consumption_pressure_index` | `clamp(pressure·0.34 + (1−food_security)·0.24 + (1−prosperity)·0.18 + trade_dependency·0.14 + vulnerability·0.10)` |
| `income_index` | `clamp(prosperity·0.42 + (1−vulnerability)·0.22 + urbanization·0.16 + logistics_resilience·0.20)` |
| `labor_participation_index` | `clamp(0.43 + prosperity·0.18 − vulnerability·0.12 + (0.07 if urban))` |
| `fertility_rate_per_year` | `max(0, 0.0007 + (1−urbanization)·0.0007 + pressure·0.0004 − vulnerability·0.00025)` (8 dp) |
| `mortality_risk_index` | `clamp(hazard·0.44 + vulnerability·0.38 + pressure·0.18)` |

`market_pressure` is the per-region max of `clamp(disruption_risk·0.62 + market_access·0.18 + friction·0.20)` over incident **pre-clearing** market exchanges (`_market_pressure_by_region`, `:97`–`:107`). `food_security`, `prosperity` and `trade_dependency` come from the **final** economy step (`_final_step`, `:78`–`:82`).

Other fields: `id`, `population_region_id`, `region_id`, `culture_region_id`, `language_region_id`, `cohort_type`, `average_household_size`, `urbanization_fraction`, `water_security_index`, `food_security_index`.

### Firm agents

Firms are selected per economy history, iterating regions sorted by `region_id` (`:270`–`:329`). A known strictly positive final-sector output contributes a firm; known nonpositive output does not, while an unknown sector predicate is reported as unavailable selection rather than false:

| Sector | Output driver (final economy step) | `base_dependency` |
| --- | --- | --- |
| `agriculture` | `agricultural_output_index` | 0.30 |
| `resource` | `resource_output_index` | 0.44 |
| `trade` | `trade_output_index` | 0.82 |
| `urban_services` | `urban_services_index` | 0.56 |
| `administration` | `administration_cost_index` | 0.24 |

The `administration` firm's `output_index` is the region's administration **cost** line reused as an output quantity (`:291`); that is what the source does and the resulting "firm" is a bookkeeping artifact, not a producing entity. The original `or history.final_gross_output_index` expression below is a historical fallback; current missing-value handling is determined by the exact field availability contract, not Python truthiness.

```
gross_output      = max(1, final_step.gross_output_index or history.final_gross_output_index)
output_share      = clamp(output / gross_output)
market_dependency = clamp(base_dependency·0.52 + trade_dependency·0.34 + output_share·0.14)
productivity      = clamp(output_share·0.42 + prosperity·0.30 + stability·0.18 + logistics_resilience·0.10)
supply_chain_risk = clamp(chokepoint_exposure·0.32 + market_dependency·0.26 + (1−logistics_resilience)·0.24 + military_burden·0.18)
employment        = population · output_share · (0.30 + productivity·0.28)
wage_index        = clamp(prosperity·0.45 + productivity·0.35 + (1−supply_chain_risk)·0.20)
capital_stock     = clamp(output/260·0.48 + prosperity·0.26 + logistics_resilience·0.26)
tax_contribution  = output · (0.07 + market_dependency·0.025) · (1 − supply_chain_risk·0.16)
settlement_id     = capital_settlement_id when index == 0 or the region has no settlements,
                    else settlement_ids[index mod len(settlement_ids)]
```

Fields: `id`, `region_id`, `population_region_id`, `settlement_id`, `sector`, `output_index`, `employment_capacity`, `wage_index`, `productivity_index`, `market_dependency_index`, `capital_stock_index`, `supply_chain_risk_index`, `tax_contribution_index`.

### Demographic agent histories

One per population region (`:331`–`:391`), stepping the population-history steps:

```
labor_average         = Σ cohort.labor_participation·cohort.population / Σ cohort.population   (0.45 with no cohorts)
loss_fraction         = clamp(conflict_loss / max(1, start_population))
migration_propensity  = clamp(|migration_delta| / max(1, start_population)·8 + pressure·0.20 + hazard·0.18 + loss_fraction·0.28)
vulnerability         = clamp(hazard·0.32 + pressure·0.26 + loss_fraction·0.28 + migration_propensity·0.14)
working_population    = end_population · labor_average
dependent_population  = max(0, end_population − working_population)
consumption_pressure  = clamp(pressure·0.42 + dependent/max(1, end)·0.24 + vulnerability·0.22 + loss_fraction·0.12)
```

Step fields: `era_id`, `stage_index` (1-based), `start_year_bp`, `end_year_bp`, `start_population`, `end_population`, `working_population`, `dependent_population`, `migration_propensity_index`, `consumption_pressure_index`, `vulnerability_index`, `labor_participation_index`.
Record fields: `id`, `population_region_id`, `region_id`, `household_cohort_ids`, `firm_agent_ids`, `step_count`, `final_agent_population`, `mean_labor_participation_index`, `steps`.

### Individual agents and life events

In the known-positive population branch, `sample_count = min(6, max(2, len(cohort_ids)·2))` (`:411`), giving **6** with the standard three cohorts. Cohorts are cycled `cohort_ids[index mod 3]`; eras are cycled for the birth era, and the last sorted era supplies the death-era slot. Current identities and birth scheduling can remain available while dependent death, lifespan or property estimates are null. A dominant-firm role substitution requires its own complete selection inputs; unrelated roles are retained. The numerical formulas below apply only where those inputs are available.

```
life_expectancy = max(18, 78 − mortality_risk·26 − vulnerability·18 + income·10)
birth_year_bp   = max(death_era.end_year_bp, birth_era.start_year_bp − 16 − index·7)
death_year_bp   = max(death_era.end_year_bp, birth_year_bp − life_expectancy)
household_share = cohort.population / cohort.household_count
property_value  = max(0, household_share · (0.24 + income·0.46) · (1 − vulnerability·0.22))
role            = ROLE_SEQUENCE[(region_id + index) mod 6]   -- farmer, artisan, merchant, soldier, administrator, healer
                  (replaced by the region's dominant firm sector when role == "farmer",
                   the dominant sector is not "agriculture", and index mod 3 == 0)
```

Relationship graph (`:483`–`:495`): for `index ≥ 2`, `parent_person_ids = [person[index−2]]` plus `person[index−3]` when `index ≥ 3`; children are back-filled. For odd `index`, the person marries `person[index−1]`, producing **two** marriage events (one per participant).

| `individual_life_events[]` `event_type` | Count per region (6 samples) | `year_bp` | `era_id` |
| --- | --- | --- | --- |
| `birth` | 6 | `birth_year_bp` | birth era |
| `marriage` | 6 (2 per odd index, 3 odd indices) | `max(death_year_bp, birth_year_bp − 22 − vulnerability·6)` | birth era |
| `property_transfer` | 6 | `max(death_year_bp, birth_year_bp − max(1, life_expectancy·0.72))` | death era |
| `death` | 6 | `death_year_bp` | death era |

`property_transfer` sets `related_person_id = person[index−2]` when `index ≥ 2` (else −1) and `inheritance_fraction = 0.48` when a recipient exists, `0.20` otherwise; `property_value_index = property_value · inheritance_fraction`.

Event fields: `id`, `person_id`, `related_person_id`, `population_region_id`, `region_id`, `household_cohort_id`, `era_id`, `event_type`, `year_bp`, `property_value_index`, `demographic_pressure_index`, `mortality_risk_index`, `inheritance_fraction`.
Person fields: `id`, `population_region_id`, `region_id`, `household_cohort_id`, `culture_region_id`, `language_region_id`, `name` (`_person_name`, `:146`–`:149`), `role`, `birth_year_bp`, `death_year_bp`, `lifespan_years`, `married_person_id`, `parent_person_ids`, `child_person_ids`, `property_value_index`, `mobility_index`, `vulnerability_index`, `event_ids`, `event_count`.

### Demographic summary keys (`:575`–`:601`)

`household_cohort_count`, `firm_agent_count`, `demographic_agent_history_count`, `demographic_agent_step_count`, `individual_agent_count`, `individual_life_event_count`, `individual_birth_event_count`, `individual_death_event_count`, `individual_marriage_event_count`, `property_transfer_event_count`, `total_household_cohort_population`, `total_firm_employment_capacity`, `total_property_transfer_value_index`, `mean_household_resilience_index` (mean of `1 − vulnerability`), `mean_household_migration_propensity_index`, `mean_household_consumption_pressure_index`, `mean_firm_productivity_index`, `mean_firm_market_dependency_index`, `mean_firm_supply_chain_risk_index`, `mean_demographic_vulnerability_index`, `mean_individual_lifespan_years`, `high_vulnerability_household_count` (cohorts with `vulnerability_index ≥ 0.65`), plus `demographic_agent_model` and `individual_life_event_model`.

## Logistics networks and market exchanges

`enrich_world_with_logistics_history` (`src/magic_geo/logistics_history.py:746`) writes seven arrays. It reads the configured planet radius first (`planet_radius_km(world)`, `:747`); a world without a valid finite positive `planet_parameters.radius_km` raises `ValueError` out of the enricher.

### Logistics networks (one per political region, `:805`–`:876`)

```
route_efficiency        = clamp(Σ route.distance_km / max(Σ route.cost, 1))
route_density           = clamp(route_count / max(1, max_route_count_over_all_regions))
transport_efficiency    = clamp(route_efficiency·0.72 + route_density·0.28)
supply_capacity         = clamp(peak_gross_output/1200·0.34 + peak_army/25 000 000·0.24
                                  + route_density·0.24 + trade_dependency·0.18)
logistics_resilience    = clamp(transport_efficiency·0.34 + prosperity·0.24
                                  + peak_treasury/180·0.18 + (1 − conflict_pressure)·0.24)
chokepoint_exposure     = clamp(mean_trade_friction·0.36
                                  + border_count/max(1, border_count + route_count)·0.22
                                  + conflict_pressure·0.42)
```

`conflict_pressure` is the per-region **maximum** of `clamp(0.35·intensity + 0.35·economic_disruption + 0.30·logistics_strain)` over incident conflicts (`_conflict_pressure_by_region`, `:82`–`:93`).

Fields: `id`, `region_id`, `route_ids`, `trade_flow_ids`, `border_ids`, `route_count`, `trade_flow_count`, `border_count`, `total_route_distance_km`, `total_route_cost`, `total_trade_volume_index`, `interregional_trade_volume_index`, `army_capacity_population`, `supply_capacity_index`, `transport_efficiency_index`, `logistics_resilience_index`, `chokepoint_exposure_index`.

### Market exchanges (one per trade flow, `:882`–`:943`)

```
supply_index          = clamp(source.resource_output/260·0.30 + source.prosperity·0.32
                                + volume/140·0.20 + (1 − friction)·0.18)
demand_index          = clamp(target.population/1e9·0.28 + target.trade_dependency·0.34
                                + volume/140·0.18 + target.urban_services/260·0.20)
disruption_risk_index = clamp(friction·0.36 + max(regional conflict pressure)·0.44 + distance/9000·0.20)
price_spread_index    = clamp(friction·0.48 + |demand − supply|·0.28 + distance/9000·0.24)
network_access        = ½(source.transport_efficiency + target.transport_efficiency)
market_access_index   = clamp((1 − friction)·0.32 + volume/140·0.24 + network_access·0.28
                                + (1 − disruption_risk)·0.16)
food_security_link    = clamp(½(source.food_security + target.food_security))
tax_revenue_index     = max(0, volume·(0.035 + 0.018 if interregional)·(1 − disruption_risk·0.20))
```

Fields: `id`, `trade_flow_id`, `route_id`, `from_settlement_id`, `to_settlement_id`, `region_from`, `region_to`, `primary_good`, `interregional`, `distance_km`, `volume_index`, `friction`, `supply_index`, `demand_index`, `price_spread_index`, `market_access_index`, `tax_revenue_index`, `food_security_link_index`, `disruption_risk_index`.

### Logistics/exchange summary keys

`logistics_network_count`, `logistics_route_link_count`, `market_exchange_count`, `interregional_market_exchange_count`, `total_market_exchange_volume_index`, `mean_logistics_transport_efficiency_index`, `mean_logistics_resilience_index`, `mean_market_access_index`, `mean_market_disruption_risk_index` (`:1304`–`:1322`), plus `logistics_exchange_model` = `causal_region_route_trade_economy_logistics_exchange_v2` with `model_limitation = aggregate_static_logistics_and_exchange_indices_without_inventory_vehicle_fleet_or_dynamic_congestion` (`:16`–`:26`).

## Campaign operations

Campaigns are generated in the same enricher, one per conflict with two distinct valid regions (`:976`–`:1273`).

### Endpoint and path selection

Attacker/defender assignment (`:984`–`:992`): `region_b_victory` → origin `b`; `region_a_victory` → origin `a`; otherwise the larger force estimate is the origin, ties to `a`.

`_campaign_endpoint_cells` (`:282`–`:353`) resolves the start cell from the route endpoint in the origin region, falling back to the origin region's capital cell. Target candidates are appended in this priority order, skipping duplicates and the start cell:

1. `conflict.contested_cell_id` when that cell's `political_region_id` equals the target region.
2. Start-cell neighbours in the target region.
3. Route endpoint settlements in the target region.
4. The target region's capital cell.
5. `conflict.contested_cell_id` again, this time without the target-region test (it still has to resolve to a real cell, `:328`).
6. If still empty: the nearest cell (great-circle) whose `political_region_id` is the target region.
7. If still empty: any neighbour of the start cell.

`_shortest_campaign_path` (`:206`–`:255`) is a Dijkstra over the cell neighbour graph with edge cost

```
step_cost = haversine_distance_km(cell, next, radius_km) · (0.45 + terrain·1.65 + water_penalty)
water_penalty = 1.85 when next is water and route_type ∉ {coastal_sea, river, river_corridor}, else 0
```

and `_campaign_terrain_cost` (`:163`–`:189`):

```
terrain = 0.18 + clamp(|Δelevation|/2200)·0.30 + clamp(seasonal_aridity_index)·0.14 + clamp(ice_thickness_m/1200)·0.16
        + water_cost if next is water        (0.18 coastal_sea, 0.28 river/river_corridor, 0.62 otherwise)
        + 0.18 if "mountain" or "glacial_valley" in next.landform
        + 0.12 if "desert" in next.biome or next.landform
        + 0.06 if "forest" or "wetland" in next.biome
        − 0.10 if next.is_river and route_type ∈ {river, river_corridor}
        − 0.04 if route_type == "overland" and next is not water
then clamped to [0,1]
```

`route_type` is the type of the highest-volume trade flow on the region pair, or the literal string `"border_crossing"` when no such flow exists (`:997`). `border_crossing` is not a member of `ROUTE_TYPE_NAMES`, so it takes the generic `water_cost = 0.62` branch. If the path has fewer than two cells the enricher retries with the first available neighbour of the origin cell, and skips the conflict entirely if that also fails (`:1020`–`:1030`).

### Campaign aggregates

```
path_length      = Σ segment distances (falls back to trade distance, route distance, 1.6·border length, or 320 km)
terrain_mean     = clamp(Σ terrain_cost·distance / max(1, path_length))
daily_km         = max(6, 30·(1 − friction·0.35)·(1 − terrain_mean·0.45))
travel_time_days = path_length / daily_km
supply_required  = clamp(force/army_capacity·0.46 + war_duration/900·0.22 + path_length/8000·0.20 + terrain_mean·0.12)
attrition_risk   = clamp(logistics_strain·0.42 + friction·0.22 + supply_required·0.24 + war_duration/1200·0.12)
operational_reach= clamp((1 − attrition_risk)·0.42 + logistics_resilience·0.34 + transport_efficiency·0.24)
success_base     = 0.70 for a decisive outcome, else 0.50
campaign_success = clamp(success_base·0.45 + reach·0.34 + (1 − attrition_risk)·0.21)
```

`campaign_movements[]` fields: `id`, `conflict_id`, `era_id`, `origin_region_id`, `target_region_id`, `origin_cell_id`, `target_cell_id`, `contested_cell_id`, `route_id`, `border_id`, `path_cell_ids`, `path_cell_count`, `path_segment_ids`, `path_segment_count`, `path_length_km`, `path_terrain_cost_index`, `path_supply_loss_index`, `path_attrition_index`, `campaign_front_history_id`, `start_year_bp`, `end_year_bp`, `distance_km` (same value as `path_length_km`), `travel_time_days`, `force_estimate`, `supply_required_index`, `attrition_risk_index`, `logistics_strain_index`, `operational_reach_index`, `campaign_success_index`, `outcome`.

`campaign_path_segments[]` fields (`:1106`–`:1123`): `id`, `campaign_movement_id`, `sequence_index`, `from_cell_id`, `to_cell_id`, `route_mode`, `distance_km`, `elapsed_days`, `terrain_cost_index`, `barrier_cost_index` (`clamp(terrain·0.48 + border_barrier·0.26 + friction·0.26)`), `supply_loss_index` (`clamp(supply_required·0.34 + terrain·0.30 + barrier·0.18 + segment_share·0.18)`), `attrition_index` (`clamp(attrition_risk·0.44 + terrain·0.26 + supply_loss·0.30)`), `elevation_gain_m`, `water_crossing`.

`campaign_front_histories[]` step fields (`:1187`–`:1206`): `sequence_index`, `cell_id`, `days_elapsed`, `occupied_cell_ids`, `occupied_cell_count`, `front_line_cell_ids` (up to 6 unoccupied neighbours), `front_line_cell_count`, `supply_line_length_km`, `supply_integrity_index`, `attacking_force_estimate`, `defending_force_estimate`, `attrition_loss_population`, `local_attrition_index`, `occupation_control_index`, `front_width_index`, `contested`. Record fields add `id`, `campaign_movement_id`, `conflict_id`, `origin_region_id`, `target_region_id`, `attacking_force_initial`, `defending_force_initial`, `final_attacking_force_estimate`, `final_defending_force_estimate`, `start_year_bp`, `end_year_bp`, `route_mode`, `path_cell_ids`, `path_segment_ids`, `step_count`, `captured_cell_count`, `final_occupied_cell_id`, `max_supply_line_length_km`, `mean_supply_integrity_index`, `mean_occupation_control_index`, `outcome_projection` (`breakthrough` at `success ≥ 0.66`, `contested_front` at `≥ 0.48`, else `stalled`).

Force attrition per front step (`:1159`–`:1162`): `attacker_loss = remaining_attacker · local_attrition · 0.018`, `defender_loss = remaining_defender · clamp(local_attrition·0.014 + success·0.008)`.

`tactical_engagements[]` (`_build_tactical_engagements`, `:356`–`:537`) re-projects each front history onto the fixed `region_a`/`region_b` axes, adds `front_pressure_index`, `counter_maneuver_index`, `supply_contest_index`, `encirclement_risk_index`, `withdrawal_pressure_index`, `control_region_id`, `control_balance_index`, and classifies `tactical_outcome` as `breakthrough` / `counter_maneuver` / `attritional_stalemate` / `contested_advance` (`:490`–`:498`).

`strategic_campaign_plans[]` (`_build_strategic_campaign_plans`, `:552`–`:743`) builds a reversed counter-axis, a reserve split, and decision points at path indices `{0, len//2, len−1}` — at most three, and fewer when those indices collide on a short axis, because `_strategic_decision_indices` (`:540`–`:549`) deduplicates. Phases are `mobilization` for the first point, `counterstroke` when the point is the last path index, and `contested_front` otherwise (`:677`). `strategic_posture` is `counteroffensive` at `counter_viability ≥ 0.62`, `mobile_defense` at `≥ 0.45`, else `delaying_defense`.

Campaign summary keys (`:1308`–`:1344`): `campaign_movement_count`, `campaign_path_segment_count`, `campaign_front_history_count`, `tactical_engagement_count`, `strategic_campaign_plan_count`, `campaign_front_step_count`, `tactical_engagement_step_count`, `strategic_decision_point_count`, `total_campaign_mobilized_population`, `total_campaign_path_length_km`, `mean_campaign_travel_time_days`, `mean_campaign_attrition_risk_index`, `mean_campaign_operational_reach_index`, `mean_campaign_path_length_km`, `mean_campaign_path_terrain_cost_index`, `mean_campaign_path_supply_loss_index`, `mean_campaign_path_attrition_index`, `mean_campaign_front_supply_integrity_index`, `mean_campaign_front_control_index`, `total_campaign_front_attrition_loss_population`, `tactical_total_attrition_loss_population`, `mean_tactical_counter_maneuver_index`, `mean_tactical_front_pressure_index`, `mean_tactical_supply_contest_index`, `high_pressure_tactical_step_count`, `independent_counter_campaign_plan_count`, `mean_counter_campaign_viability_index`, `mean_strategic_plan_confidence_index`, `mean_strategic_force_reserve_fraction`, `high_escalation_strategic_plan_count`, `high_attrition_campaign_count`, `high_attrition_campaign_path_segment_count`.

The declared limitation is `single_deterministic_axis_per_conflict_without_adaptive_replanning_uncertainty_simultaneous_fronts_or_observed_calibration` (`:40`).

## Market clearing

`enrich_world_with_market_clearing` (`src/magic_geo/market_clearing.py:120`) writes five arrays. The model declaration is set unconditionally at the top (`:121`), so `market_clearing_model` is present even when the payload has no exchanges.

### Route capacity constraints

One record per route that carries at least one market exchange, iterating `sorted(exchange_ids_by_route)` (`:149`).

```
base_capacity   = 28.0 + route_multiplier·48.0 + mean_transport_efficiency·32.0
                       + mean_logistics_resilience·28.0 + Σ firm output_index·0.035
capacity_volume = max(8.0, base_capacity / (1 + distance/7000 + mean_friction·0.38
                                              + cost/max(1, distance+1)·0.08))
cleared_volume  = min(requested_volume, capacity_volume)
unmet_volume    = max(0, requested − cleared)
utilization     = clamp(cleared / max(1, capacity))
shortage        = clamp(unmet / max(1, requested))
congestion      = clamp(utilization·0.52 + shortage·0.38 + mean_friction·0.10)
spoilage        = clamp(mean_friction·0.28 + shortage·0.34 + mean_household_pressure·0.20 + distance/12000·0.18)
```

| `route.type` | `ROUTE_CAPACITY_MULTIPLIER` | Reachable from native routes? |
| --- | --- | --- |
| `coastal_sea` | 1.35 | yes |
| `river` | 1.18 | **no** — not a member of `ROUTE_TYPE_NAMES` |
| `river_corridor` | 1.18 | yes |
| `overland` | 0.82 | yes |
| `mountain_pass` | 0.62 | yes |
| `desert_track` | 0.56 | **no** — not a member of `ROUTE_TYPE_NAMES` |
| any other `type` string | 0.76 (`ROUTE_CAPACITY_MULTIPLIER.get` fallback, `:117`) | only for a route whose `type` is not a table key |

`ROUTE_TYPE_NAMES` (`cpp/src/engine/schema_names.hpp:47`) is exactly `{overland, river_corridor, coastal_sea, mountain_pass}`, so the `river` and `desert_track` entries of the multiplier table are unreachable for native worlds.

`_route_multiplier` (`:115`–`:117`) reads `route.get("type", "overland")`, so a **missing** route record does not take the 0.76 fallback — it resolves to the literal `"overland"` and therefore to 0.82. The 0.76 branch is reached only by a route that carries an unrecognised `type` string. The emitted `route_type` field on the constraint uses a different default and reports `"unknown"` in that same missing-route case (`:201`).

Fields: `id`, `route_id`, `route_type`, `market_exchange_ids`, `market_exchange_count`, `distance_km`, `requested_volume_index`, `capacity_volume_index`, `cleared_volume_index`, `unmet_volume_index`, `utilization_index`, `congestion_index`, `shortage_index`, `spoilage_loss_index`.

### Clearing records

Per exchange, in ascending `id` order, allocation is **proportional to the route's clearance ratio** (`:251`):

```
cleared            = min(requested, requested · route_cleared / max(1, route_requested))
unmet              = max(0, requested − cleared)
clearance_fraction = clamp(cleared / max(1, requested))
rationing          = clamp(unmet / max(1, requested))
price_adjustment   = clamp(price_spread_index·0.36 + congestion·0.30 + rationing·0.24 + disruption_risk·0.10)
producer_surplus   = clamp(supply_index · clearance_fraction · (1 + price_adjustment·0.16))
consumer_welfare   = clamp(market_access_index · (1 − rationing·0.72) · (1 − price_adjustment·0.18))
```

Note the `max(1.0, requested)` denominators: an exchange with `volume_index < 1` reports a `clearance_fraction` below the true ratio.

### Agent orders

Up to seven orders per exchange on the available branch (`:265`–`:370`). Current market2 uses the first-firm/fallback selection below only when its actual candidate scope is complete. Unknown firm selection or a state-demand predicate with unavailable inputs cannot be interpreted as a known empty order set. Recorded orders and full selection coverage are separate:

| Order group | Agents | Volume | Limit price | Fulfilment |
| --- | --- | --- | --- | --- |
| Firm supply | first 3 firms of `region_from` (or first 1 of `region_to` if none) | `requested·(0.20 + productivity·0.20)·(1 − supply_risk·0.35) / n` | `clamp(0.26 + dependency·0.20 + supply_risk·0.28 + price_spread·0.26)` | `clamp(clearance_fraction·(1 − supply_risk·0.28) + productivity·0.16)` |
| Household demand | first 3 cohorts of `region_to` (or first 1 of `region_from`) | `requested·(0.22 + consumption·0.24 + vulnerability·0.10) / n` | `clamp(0.44 + income·0.24 − vulnerability·0.10 + market_access·0.18)` | `clamp(clearance_fraction·(1 − rationing·0.28) + income·0.10)` |
| State demand | 1, only when `requested·tax_revenue_index·0.08 > 0` | `requested·tax_revenue_index·0.08` | `clamp(0.42 + price_adjustment·0.24)` | `clearance_fraction` |

Order fields: `id`, `market_exchange_id`, `market_clearing_record_id`, `agent_type` (`firm` / `household_cohort` / `state`), `agent_id`, `region_id`, `order_side` (`supply` / `demand`), `order_kind`, `primary_good`, `requested_volume_index`, `cleared_volume_index`, `limit_price_index`, `price_acceptance_index`, `rationing_index`, `inventory_change_index` (negative for household demand, 0 for state).

`order_kind` for firms comes from `ORDER_KIND_BY_SECTOR` (`:15`–`:21`) keyed on the firm's sector: `agriculture`/`resource` → `producer_supply`, `trade` → `broker_supply`, `urban_services` → `service_supply`, `administration` → **`state_demand`**, unknown → `producer_supply`. An `administration` firm therefore carries `order_side = "supply"` and `order_kind = "state_demand"` simultaneously; that combination is what the source produces. Household and state orders do not consult the table: household orders are always `order_kind = "consumer_demand"` (`:329`) and the state order is always `order_kind = "tax_collection"` (`:356`), both with `order_side = "demand"`. The state order's `agent_id` is the destination region id, not a record id in any agent array (`:353`).

### Price iterations

Exactly **three** iteration slots per exchange (`:380`–`:403`). Current clearing, price and inventory slots retain identity when dependent numerical fields are unavailable; their availability maps accompany null estimates. With available inputs,

```
equilibrium_price = clamp(mean(firm limit prices)·0.36 + mean(demand limit prices)·0.38 + price_adjustment·0.26)
residual          = clamp(|endogenous_demand − endogenous_supply| / max(1, demand + supply))     (computed once)

progress          = (i + 1) / 3                              i ∈ {0, 1, 2}
price             = clamp(equilibrium_price·progress + price_spread_index·(1 − progress))
supply_volume     = endogenous_supply · clamp(0.72 + price·0.18 + progress·0.10)
demand_volume     = endogenous_demand · clamp(1.02 − price·0.16 − rationing·0.12 + progress·0.04)
imbalance         = demand_volume − supply_volume
```

**Convergence behaviour, stated precisely.** This is *not* a tâtonnement search and there is no convergence test. The price path is a fixed-length deterministic linear interpolation from `price_spread_index` toward `equilibrium_price`; at `i = 2`, `progress = 1` and the iteration price is exactly `equilibrium_price`. The reported `imbalance_index`, `excess_demand_index` and `price_adjustment_index` are diagnostics only — no iteration output feeds the next iteration's price. `price_residual_index` is a field of the **clearing record**, not of the iterations: it is `residual`, computed once at `:378` from the endogenous supply/demand totals before the loop starts, and it is never recomputed or refined by the iterations (the iteration record has no residual field at all). The declaration calls this `"price_model": "three_step_supply_demand_price_interpolation_v1"` (`:35`), and the model limitation is `single_deterministic_clearing_episode_without_repeated_period_equilibrium_entry_exit_bargaining_or_empirical_calibration` (`:38`).

Iteration fields: `id`, `market_exchange_id`, `market_clearing_record_id`, `iteration_index` (1-based), `order_ids`, `order_count`, `price_index`, `supply_volume_index`, `demand_volume_index`, `imbalance_index`, `excess_demand_index`, `price_adjustment_index`.

### Inventory histories

One per exchange, with one step per price iteration (three steps), `:404`–`:533`:

```
net_inventory_delta = Σ order.inventory_change_index over the exchange's orders
initial_inventory   = clamp(supply_index·0.28 + clearance_fraction·0.24 + (1 − rationing)·0.18
                              + utilization·0.16 + producer_surplus·0.14)
target_inventory    = clamp(0.26 + demand_index·0.22 + market_access·0.16 + (1 − rationing)·0.16
                              + consumer_welfare·0.20)
learning_rate       = clamp(0.16 + price_adjustment·0.24 + residual·0.22 + rationing·0.20
                              + |net_inventory_delta|·0.18)             (constant across steps)
inventory          ← clamp(inventory + (target − inventory)·learning_rate·0.35
                              + net_inventory_delta·0.28
                              + (supply_response − demand_adjustment)·0.08)
```

`learning_rate` does not decay: it is recomputed inside the loop but every one of its inputs (`price_adjustment`, `residual`, `rationing`, `net_inventory_delta`) is step-invariant, so it takes the same value on all three steps, and the record-level `learning_rate_index` is the mean of three identical numbers. The inventory update adds a damped move toward `target_inventory`, a step-invariant `net_inventory_delta · 0.28` term, and a per-step `(supply_response − demand_adjustment) · 0.08` term. Because the two additive terms are not driven to zero as the gap closes, this is not a convergence process and there is no reason for `inventory_index` to arrive at `target_inventory` — `inventory_gap_index` on the record is simply the residual distance after three fixed steps, not a convergence error.

Step fields: `sequence_index`, `price_iteration_id`, `price_index`, `inventory_index`, `target_inventory_index`, `inventory_gap_index`, `supply_response_index`, `demand_adjustment_index`, `learning_rate_index`, `producer_expectation_index`, `consumer_expectation_index`, `rationing_memory_index`, `clearance_memory_index`.

History fields: `id`, `market_clearing_record_id`, `market_exchange_id`, `trade_flow_id`, `route_id`, `region_from`, `region_to`, `primary_good`, `initial_inventory_index`, `target_inventory_index`, `final_inventory_index`, `inventory_gap_index`, `learning_rate_index`, `mean_inventory_pressure_index`, `mean_price_expectation_index`, `mean_supply_response_index`, `mean_demand_adjustment_index`, `high_inventory_stress` (`mean_pressure ≥ 0.60` **or** `final_gap ≥ 0.45`), `step_count`, `steps`.

### Clearing record fields

`id`, `market_exchange_id`, `trade_flow_id`, `route_id`, `route_capacity_constraint_id`, `region_from`, `region_to`, `primary_good`, `requested_volume_index`, `cleared_volume_index`, `unmet_demand_index`, `clearance_fraction`, `route_utilization_index`, `price_adjustment_index`, `rationing_index`, `producer_surplus_index`, `consumer_welfare_index`, `agent_order_ids`, `agent_order_count`, `price_iteration_ids`, `price_iteration_count`, `market_inventory_history_id`, `endogenous_supply_index`, `endogenous_demand_index`, `equilibrium_price_index`, `price_residual_index`.

### Market summary keys (`:592`–`:614`)

`route_capacity_constraint_count`, `market_clearing_record_count`, `market_agent_order_count`, `market_price_iteration_count`, `market_inventory_history_count`, `market_inventory_step_count`, `producer_market_order_count`, `consumer_market_order_count`, `constrained_market_exchange_count`, `total_market_requested_volume_index`, `total_market_cleared_volume_index`, `total_market_unmet_demand_index`, `total_endogenous_market_supply_index`, `total_endogenous_market_demand_index`, `mean_market_clearance_fraction`, `mean_route_capacity_utilization_index`, `mean_market_price_adjustment_index`, `mean_market_rationing_index`, `mean_market_equilibrium_residual_index`, `mean_market_inventory_gap_index`, `mean_market_learning_rate_index`, `mean_market_inventory_pressure_index`, `high_inventory_stress_market_count`, plus `market_clearing_model`.

## Native calibration checks

`generate_calibration_checks` (`cpp/src/engine/history.cpp:990`) is the only *built-in* calibration surface. It emits exactly twelve checks from cells and watersheds, with no configuration switch and no thresholds derived from the world — the one guard is an empty cell list, which short-circuits to zero checks (`:995`–`:997`). It runs in both full and geo-only scope. `calibration_score_for_range` (`:959`) returns 1.0 inside the range and otherwise `clamp(1 − distance/max(1e-9, target_max − target_min), 0, 1)`.

| id | `dataset` | `layer` | `metric` | Value | `target_min` | `target_max` | Line |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | `ETOPO_reference_range` | `relief_bathymetry` | `ocean_fraction` | area-weighted water fraction (cell-count fraction if total area is 0) | 0.55 | 0.78 | `:1059` |
| 1 | `ETOPO_reference_range` | `relief_bathymetry` | `mean_land_elevation_m` | mean `elevation_m` over land cells | 120.0 | 1800.0 | `:1068` |
| 2 | `ETOPO_reference_range` | `relief_bathymetry` | `hypsometric_span_m` | `max_elevation − min_elevation` over **all** cells | 3500.0 | 17000.0 | `:1069` |
| 3 | `WorldClim_reference_range` | `climate` | `global_mean_temperature_c` | mean `temperature_c` over all cells | −5.0 | 28.0 | `:1070` |
| 4 | `WorldClim_reference_range` | `climate` | `mean_land_precipitation_mm_y` | mean over land cells | 250.0 | 2300.0 | `:1071` |
| 5 | `WorldClim_reference_range` | `climate` | `mean_monthly_temperature_range_c` | mean of per-cell `max−min` of `temperature_monthly_c`, divided by **all** cells | 2.0 | 38.0 | `:1072` |
| 6 | `HydroSHEDS_reference_range` | `hydrology` | `river_cell_fraction` | `is_river` land cells / land cells | 0.005 | 0.14 | `:1073` |
| 7 | `HydroSHEDS_reference_range` | `hydrology` | `endorheic_watershed_fraction` | endorheic watersheds / watersheds (0 when none) | 0.0 | 0.55 | `:1074` |
| 8 | `WorldClim_reference_range` | `biomes` | `desert_land_fraction` | land cells with `biome ∈ {cold_desert, hot_desert}` / land | 0.04 | 0.48 | `:1083` |
| 9 | `WorldClim_reference_range` | `biomes` | `ice_land_fraction` | land cells with `biome == ice_cap` or `ice_thickness_m > 25` / land | 0.0 | 0.38 | `:1084` |
| 10 | `WorldClim_reference_range` | `biomes` | `forest_land_fraction` | land cells with `biome ∈ {boreal_forest, temperate_forest, tropical_seasonal_forest, tropical_rainforest}` / land | 0.08 | 0.58 | `:1085` |
| 11 | `NaturalEarth_reference_range` | `cartography` | `coastal_land_fraction` | land cells with ≥1 water neighbour / land | 0.03 | 0.48 | `:1086` |

`calibration_checks[]` fields (`process_serialization.cpp:4417`): `id`, `dataset`, `layer`, `metric`, `passed`, `value`, `target_min`, `target_max`, `score`.

These twelve ranges are **hardcoded plausibility bands, not measured datasets**. The dataset names are labels for the intended reference family; no external file is read. The separate, genuinely external calibration path — SHA-256-pinned target bundles from ETOPO 2022, WorldClim 2.1, HydroBASINS/HydroRIVERS, Natural Earth and Seton 2020 — is described on [Calibration Against Real-Earth Data](../14-calibration.md) and is distinct from this built-in surface.

## In-place annotations written back onto existing records

Several enrichers mutate records that were emitted by earlier stages. Consumers reading a serialized world must expect these extra keys on the native record families.

| Target record family | Added key(s) | Written by | Line |
| --- | --- | --- | --- |
| `dynasties[]` | `founder_ruler_id`, `ruler_count`, `marriage_alliance_count`, `cadet_branch_count` | `dynasty_genealogy` | `:201`–`:204`, `:223`, `:282`–`:283` |
| `population_regions[]` | `household_cohort_ids`, `household_cohort_count`, `representative_household_population` | `demographic_agents` | `:262`–`:264` |
| `population_regions[]` | `demographic_agent_history_id` | `demographic_agents` | `:391` |
| `population_regions[]` | `individual_agent_ids`, `individual_agent_count` | `demographic_agents` | `:566`–`:567` |
| `political_regions[]` | `firm_agent_ids`, `firm_agent_count` | `demographic_agents` | `:328`–`:329` |
| `conflicts[]` | `campaign_movement_id` | `logistics_history` | `:1266` |
| `conflicts[]` | `tactical_engagement_id` | `logistics_history` | `:525` |
| `conflicts[]` | `strategic_campaign_plan_id` | `logistics_history` | `:725` |
| `routes[]` | `route_capacity_constraint_id`, `market_capacity_volume_index`, `market_capacity_utilization_index` | `market_clearing` | `:214`–`:216` |
| `market_exchanges[]` | `market_clearing_record_id`, `cleared_volume_index`, `unmet_demand_index`, `clearance_fraction`, `market_inventory_history_id` | `market_clearing` | `:567`–`:571` |

## Validation and replay

Every model family on this page has an **independent second implementation** used as a replay validator. Current dispatch audits declared sources and availability before replaying available formulas; an invalid native parent can stop dependent tail validation. The table records the original public entry points and legacy failure messages, not an exhaustive current error vocabulary. Current strict owned-field and coverage checks supplement the historical containment replay.

| Validator module | Public function | Failure string | Replays |
| --- | --- | --- | --- |
| `src/magic_geo/historical_geography_validation.py` | `validate_historical_geography_replay` (`:492`) | `historical geography model or causal replay invalid` | `historical_eras`, `historical_events`, `historical_event_model` |
| `src/magic_geo/civilization_geography_validation.py` | `validate_civilization_geography_replay` (`:800`) | `population, conflict, or dynasty model causal replay invalid` | native population regions, conflicts, dynasties |
| `src/magic_geo/territorial_geography_validation.py` | `validate_territorial_geography_replay` (`:500`) | `territorial snapshot model or causal replay invalid` | `territorial_snapshots`, `territorial_snapshot_model` |
| `src/magic_geo/history_economy_validation.py` | `validate_history_economy_replay` (`:521`) | `population or economy history model causal replay invalid` | `population_histories`, `economy_histories` |
| `src/magic_geo/demographic_agents_validation.py` | `validate_demographic_agents_replay` (`:825`) | `demographic agent or individual life-event causal replay invalid` | cohorts, firms, agent histories, individuals, life events |
| `src/magic_geo/dynasty_genealogy_validation.py` | `validate_dynasty_genealogy_replay` (`:417`) | `ruler genealogy model or causal replay invalid` | rulers, marriage alliances, cadet branches |
| `src/magic_geo/logistics_exchange_validation.py` | `validate_logistics_exchange_replay` (`:375`) | `logistics exchange model or causal replay invalid` | logistics networks, market exchanges |
| `src/magic_geo/campaign_operations_validation.py` | `validate_campaign_operations_replay` (`:1421`) | `campaign operations model or causal replay invalid` | movements, path segments, front histories, tactical engagements, strategic plans, conflict annotations |
| `src/magic_geo/market_clearing_validation.py` | `validate_market_clearing_replay` (`:859`) | `market clearing model or causal replay invalid` | route constraints, clearing records, orders, price iterations, inventory histories |

CLI wiring: `validate_historical_geography_replay` runs at `src/magic_geo/cli/commands/validate.py:10591`, then `:10592`–`:10599` run civilization geography → territorial geography → history/economy → demographic agents → dynasty genealogy → logistics exchange → campaign operations → market clearing.

### Campaign operations validation in detail

The following sequence describes the **retained v1 campaign replay** (`src/magic_geo/campaign_operations_validation.py:1421`–`:1485`). Current campaign2 dispatch additionally requires audited logistics sources, exact model/coverage and owned nullable outputs; the legacy containment rule below is not its complete publication contract.

1. `planet_radius_km(payload)` is called first (`:1423`). A missing or non-positive radius returns `["campaign operations replay rejected: <reason>"]` — a *different*, more specific message than the generic replay failure.
2. Thirteen payload keys must all be lists (`:1428`–`:1445`): `political_regions`, `routes`, `trade_flows`, `conflicts`, `cells`, `borders`, `settlements`, `economy_histories`, `campaign_movements`, `campaign_path_segments`, `campaign_front_histories`, `tactical_engagements`, `strategic_campaign_plans`.
3. `payload["campaign_operations_model"]` must equal the validator's own `_campaign_operations_model()` dict **exactly**, and `summary.campaign_operations_model` must equal the model-type string (`:1446`–`:1447`).
4. `_expected_campaign_operations(payload)` (`:813`) re-derives everything. It works on **copies** of the conflicts with `campaign_movement_id`, `tactical_engagement_id` and `strategic_campaign_plan_id` popped (`:826`–`:830`), so the annotations cannot feed their own replay. It calls `_expected_logistics_exchanges(payload)` (imported from `logistics_exchange_validation`) to rebuild the logistics networks the campaign model depends on, rather than reading the serialized `logistics_networks`.
5. `_contains_expected` (`:1403`–`:1418`) compares recursively: dicts must contain every expected key (extra keys are allowed), lists must match in length element-wise, scalars must be `==`. There is no floating-point tolerance — comparison relies on the enricher's 6-decimal `round()` calls producing bit-identical values under replay.
6. Every expected summary key must match exactly (`:1464`–`:1466`), and every expected conflict annotation must be present on the conflict of that id (`:1467`–`:1474`).
7. Any of `AttributeError`, `IndexError`, `KeyError`, `OverflowError`, `TypeError`, `ValueError`, `ZeroDivisionError` raised anywhere in the replay is caught and collapsed into `valid = False` (`:1475`–`:1484`).

The validator gives one bit of information, and a narrow one. A pass means every key the replay computes is present on the serialized record with a bit-identical value; extra keys are tolerated, so it is a containment check, not an equality check. It does **not** attest that the campaign model is physically or historically meaningful, and it does not detect additional fields a downstream tool may have injected.

## Worked examples

### Generate a full world and run the replay gate

```bash
magic-geo generate --config magic-geo.yaml --output runs/world.json
magic-geo validate --world runs/world.json
```

`validate` accumulates every complaint and emits one `FAIL <message>` line per failure, exiting 1 if any remain. A clean world prints no `FAIL` lines from the nine validators above. Note that `validate` short-circuits before the replay validators run if `schema_version`, retired schema fields or `planet_parameters` already failed (`validate.py:119`–`:122`), so a world that fails those basic gates reports nothing about this layer.

### Inspect the temporal layer from Python

```python
import json
from pathlib import Path

world = json.loads(Path("runs/world.json").read_text())

# Era partition and event histogram.
for era in world["historical_eras"]:
    print(era["id"], era["dominant_process"], era["start_year_bp"], "->", era["end_year_bp"],
          "events:", era["event_count"], "instability:", era["mean_instability"])

from collections import Counter
print(Counter(event["type"] for event in world["historical_events"]))

# Retained population trajectories; an empty modeled-region scope has no rows.
for history in world["population_histories"]:
    for step in history["steps"]:
        print(history["region_id"], step["era_id"], step["start_population"], "->", step["end_population"],
              "migration", step["migration_delta"], "conflict", step["conflict_loss"])

# Treasury closure is meaningful only for available steps.
for economy in world["economy_histories"]:
    for step in economy["steps"]:
        if step["estimate_availability"]["balance_residual_index"] is True:
            print(economy["region_id"], step["era_id"], abs(step["balance_residual_index"]))
        else:
            print(economy["region_id"], step["era_id"], "treasury closure unavailable")
```

### Regenerate and re-validate one family in memory

```python
from magic_geo import load_config
from magic_geo.api import generate_world
from magic_geo.campaign_operations_validation import validate_campaign_operations_replay
from magic_geo.market_clearing_validation import validate_market_clearing_replay

world = generate_world(load_config("magic-geo.yaml"))
assert validate_campaign_operations_replay(world) == []
assert validate_market_clearing_replay(world) == []
```

### Trace: era boundary assignment

`historical_era_for_year_bp` uses strict `>`:

| `year_bp` | `> 2400`? | `> 1300`? | `> 450`? | Result |
| --- | --- | --- | --- | --- |
| 3800.0 | yes | — | — | era 0 (`founding`) |
| 2400.0 | no | yes | — | era 1 (`expansion`) |
| 1300.0 | no | no | yes | era 2 (`fragmentation`) |
| 450.0 | no | no | no | era 3 (`integration`) |
| 0.0 | no | no | no | era 3 |

Every boundary value belongs to the *younger* era.

### Trace: a three-dynasty region chain

Take a region with `base_succession_pressure = 0.70` and a `state_foundation` event at `year_bp = 1200`. Then `dynasty_count = 1 + 1 + 1 = 3`, `F = 1200`, and:

| `i` | `lineage_depth` | `start_year_bp` = `F(1−i/3)` | `end_year_bp` | `duration_years` | `succession_pressure` = `0.70 + 0.10i` | `collapse_reason` |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | 0 | 1200 | 800 | 400 | 0.70 | first matching non-terminal rule |
| 1 | 1 | 800 | 400 | 400 | 0.80 | first matching non-terminal rule |
| 2 | 2 | 400 | 0 | 400 | 0.90 | `continuity` (terminal) |

Dynasty 0 has `parent_dynasty_id = −1` (a root), `founder_dynasty_id` equal to its own id and `founding_event_id` set; dynasties 1 and 2 have `parent_dynasty_id` pointing at their predecessor and `founding_event_id = −1`. Each parent has `child_dynasty_count = 1` and `successor_dynasty_id` equal to that single child.

Feeding dynasty 0 into `_dynasty_ruler_count`: `floor(400/420) + 2 + (1 if 0.70 ≥ 0.55) = 0 + 2 + 1 = 3` rulers, `reign_span = 400/3 ≈ 133.33` years, so reigns run 1200→1066.67, 1066.67→933.33, 933.33→800 (the last reign end is forced to the dynasty's `end_year_bp`). With three rulers the dynasty also produces one cadet branch: founder = ruler index 1, heirs = ruler index 2.

### Trace: proportional market rationing

Suppose one route carries three exchanges with `volume_index` 40, 30 and 30 (`requested_volume = 100`) and the computed `capacity_volume = 60`. Then `cleared_volume = 60`, `unmet_volume = 40`, `utilization = 1.0`, `shortage = 0.4`. Each exchange clears `requested · 60/100`:

| Exchange | `requested_volume_index` | `cleared_volume_index` | `unmet_demand_index` | `clearance_fraction` | `rationing_index` |
| --- | --- | --- | --- | --- | --- |
| A | 40 | 24 | 16 | 0.6 | 0.4 |
| B | 30 | 18 | 12 | 0.6 | 0.4 |
| C | 30 | 18 | 12 | 0.6 | 0.4 |

The three price iterations for exchange A then run at `progress` 1/3, 2/3, 1, ending exactly at `equilibrium_price_index`. None of the three carries a residual field; `price_residual_index` appears once, on exchange A's clearing record, and was computed before the loop ran.

## Limitations and unresolved claims

These are the declared limitations, quoted from the model objects the generator itself writes into the document, plus structural facts established above. None of them is softened here.

| Model | Declared `model_limitation` | Source |
| --- | --- | --- |
| `historical_event_model` | `diagnostic_single-timeline_events_without_agent_causation_duration_uncertainty_or_observed_historical_calibration` | `historical_geography.py:76` |
| `population_region_model` | `static_diagnostic_capacity_and_occupancy_without_age_structure_land_use_feedback_disease_or_observed_demographic_calibration` | `civilization_geography.py:36` |
| `conflict_model` | `one_diagnostic_conflict_per_adjacent_region_pair_without_strategy_diplomacy_uncertainty_or_observed_war_calibration` | `civilization_geography.py:55` |
| `dynasty_model` | `single_linear_dynasty_chain_per_region_without_person_level_succession_branch_competition_or_observed_genealogy_calibration` | `civilization_geography.py:68` |
| `territorial_snapshot_model` | `scaled_static_regions_with_sampled_centroid_ordered_rings_not_exact_dynamic_cell_edge_territories` | `territorial_geography.py:29` |
| `population_history_model` | `aggregate_era_projection_without_age_structure_birth_death_cohorts_disease_or_endogenous_migration_feedback` | `history_dynamics.py:21` |
| `economy_history_model` | `aggregate_index_economy_without_prices_inventory_production_functions_agent_equilibrium_or_empirical_calibration` | `economy_dynamics.py:21` |
| `ruler_genealogy_model` | `synthetic_regnal_genealogy_without_age_consistent_reproduction_competing_heirs_gender_demography_or_observed_calibration` | `dynasty_genealogy.py:50` |
| `demographic_agent_model` | `representative_aggregate_cohorts_and_firms_without_endogenous_entry_exit_household_formation_or_general_equilibrium` | `demographic_agents.py:26` |
| `individual_life_event_model` | `small_deterministic_representative_sample_not_a_population_micro_simulation_or_empirical_genealogy` | `demographic_agents.py:40` |
| `logistics_exchange_model` | `aggregate_static_logistics_and_exchange_indices_without_inventory_vehicle_fleet_or_dynamic_congestion` | `logistics_history.py:25` |
| `campaign_operations_model` | `single_deterministic_axis_per_conflict_without_adaptive_replanning_uncertainty_simultaneous_fronts_or_observed_calibration` | `logistics_history.py:40` |
| `market_clearing_model` | `single_deterministic_clearing_episode_without_repeated_period_equilibrium_entry_exit_bargaining_or_empirical_calibration` | `market_clearing.py:38` |

Additional unresolved and structural points established by reading the source:

- **The economic models are uncalibrated index systems.** `gross_output_index`, `treasury_end_index`, `tax_revenue_index`, `supply_index`, `price_index`, `inventory_index` and every other `*_index` on this page are dimensionless constructs with no currency, no price level, no deflator and no unit of account. Several are made non-degenerate by hard `max(1.0, …)` denominators (`prosperity_index`, `trade_dependency_index`, `military_burden_index`, `food_security_index`, market `clearance_fraction`), which are unit floors, not economics. No number on this page has been compared against any observed economy.
- **Market clearing does not converge to anything.** The three price iterations are a fixed-length interpolation whose terminal value is the closed-form `equilibrium_price_index`; `imbalance_index` never feeds back into the price; `price_residual_index` is computed once before the loop; `learning_rate_index` is constant across steps. Reading the sequence as evidence of an equilibrium search would be incorrect.
- **The temporal coordinate is a nominal `year_bp` axis with no physical or calibrated basis.** The four-era partition (4200 → 0 BP) is hardcoded; event years are analytic functions of pressure/significance/friction indices with hardcoded coefficients and clamps; conflict start years even depend on candidate-map insertion order. The nominal-time contract that the geological ledgers carry (`nominal_time_calibrated: false`, `physical_time_resolved: false`) has no counterpart here — these records carry no nominal-time block at all.
- **Available territorial snapshots override the population projection.** The available snapshot value replaces the projected value entirely (`era_region_territorial_population_override_v1`). Missing-snapshot projection fallback is historical; a current unavailable snapshot does not reset the trajectory to a numerical projection.
- **The three-index chain population → economy → agents → markets is strictly one-directional.** There is no feedback from prices to consumption, from markets to firms, from economy to population, or from campaigns to territory. Demographic agents are built before market clearing and therefore read pre-clearing exchange indices by construction (`preclearing_market_exchange_pressure_v1`).
- **Three lookup entries are unreachable from the generators.** `CONFLICT_CAUSE_NAMES[5]` (`sacred_site`) exists in the schema enum but is never assigned by `generate_conflicts`; the `river` and `desert_track` keys of `ROUTE_CAPACITY_MULTIPLIER` cannot match any member of `ROUTE_TYPE_NAMES`. Separately, fourteen of the seventeen keys in `_resource_value` never match a native `dominant_resource` string, so six of the nine `RESOURCE_NAMES` values silently take the `0.16` default. None of these is a bug the schema declares; they are unused capacity in the tables.
- **Available derived quantities include redundant diagnostics.** Population pressure derives from the occupancy fraction; `carrying_capacity_used_fraction` and `pressure_index` on an available history step use the same expression. Treasury `balance_residual_index` is an algebraic closure witness rather than a state variable. None of these identities turns an unavailable estimate into zero.
- **A cost line is modelled as a firm output.** The `administration` firm's `output_index` is the region's `administration_cost_index`, and its `order_kind` is `state_demand` while its `order_side` is `supply`. Both are what the source does; neither should be read as an economic claim.
- **Legacy empty-input branches are not current availability rules.** The original enrichers could omit outputs for missing eras or emit zero summaries for empty upstream arrays. Current dispatch requires exact declared sources and coverage; it retains valid region/era slots and does not turn unknown inputs into known zero. An empty selected family needs its coverage declaration before a consumer can interpret it as complete.
- **Replay validation checks declared provenance and equations, not realism.** Current validators check exact model/source contracts, record identities, coverage and owned nullable maps before replaying available equations. Legitimate unowned descendant annotations are preserved; that does not permit malformed or extra owned availability fields. Historical containment-only replay remains specific to explicit legacy paths. Neither path establishes empirical demographic, economic, military or dynastic realism.
- **The twelve built-in `calibration_checks` are hardcoded plausibility bands, not measured targets.** The dataset labels (`ETOPO_reference_range`, `WorldClim_reference_range`, `HydroSHEDS_reference_range`, `NaturalEarth_reference_range`) name the intended reference family; no external file is read by `generate_calibration_checks`. External, SHA-256-pinned empirical calibration is a separate subsystem.
- **Ruler parent links lag the succession chain.** `parent_ruler_id` is assigned at the end of each ruler iteration and read at the start of the next (`dynasty_genealogy.py:197`), so ruler 0 has no parent, ruler 1's parent is ruler 0, and ruler `i ≥ 2` points at ruler `i − 2` while its `predecessor_ruler_id` points at ruler `i − 1`. The two link families therefore describe different graphs. This is the observed behaviour of the code, not a documented intent; the declaration only says `ordered_predecessor_successor_and_parent_links_v1`.

## See also

- [Political, Cultural and Linguistic Geography](political-and-cultural-geography.md) — political regions, borders, cultures, languages, trade flows, and territorial snapshot geometry, all of which are inputs here
- [Settlements, Routes and Corridors](settlements-and-routes.md) — the settlement and route graph that supplies `route_count`, `settlement_score` and every route the logistics and campaign models traverse
- [Resources and Economic Geology](resources-and-economic-geology.md) — the `dominant_resource` and per-cell `resource` fields that drive `_resource_value` and conflict `resource_pressure`
- [World Document Schema](../10-world-schema.md) — the full top-level key list, record families and per-cell field table
- [Serialization and World Formats](../11-serialization.md) — precision contracts, `float_precision`, and the MessagePack transcoding boundary
- [Validation](../12-validation.md) — the `validate` CLI gate and the complete replay-validator inventory
- [Calibration Against Real-Earth Data](../14-calibration.md) — the external empirical target bundles, distinct from the twelve built-in `calibration_checks`
- [Architecture](../04-architecture.md) — the native-stage / Python-enricher split and where this layer sits
- [Python API](../07-python-api.md) — `generate_world`, `generate_geo_world` and the enricher call sequence
- [CLI Reference](../06-cli-reference.md) — `magic-geo generate`, `magic-geo validate`
- [Native Engine (C++ Core)](../08-native-engine.md) — `cpp/src/engine/history.cpp` in the translation-unit map
- [Glossary](../21-glossary.md) — era, `year_bp`, carrying capacity, clearance fraction, and the index vocabulary
