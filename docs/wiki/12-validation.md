# Validation

[Wiki home](./README.md) > Validation

magic-geo ships two independent validation gates: `validate`, a monolithic pass/fail consistency check over the *entire* world document including every civilization layer, and `validate-geo`, a structured, machine-readable audit restricted to natural geography that emits per-check records, a metric surface, and a 14-layer contract audit. The two differ in scope, output shape, and epistemic ambition: `validate` answers "does this document contradict itself anywhere", while `validate-geo` answers "which natural layer supplied which evidence, and what does that evidence deliberately *not* prove". A third command, `validate-geo-suite`, drives `validate-geo` across a scenario matrix and is documented separately. Throughout this page, note the codebase's own separation of authoritative results from non-authoritative shadows, counter-models and diagnostics — a passing report is a contract-integrity verdict, never an empirical-realism claim.

## On this page

- [The two validation commands](#the-two-validation-commands)
- [The check result model](#the-check-result-model)
- [Report JSON structure](#report-json-structure)
- [`validate`: validator families](#validate-validator-families)
- [`validate-geo`: top-level domains](#validate-geo-top-level-domains)
- [`validate-geo`: subsystem groups](#validate-geo-subsystem-groups)
- [The geo layer-contract system](#the-geo-layer-contract-system)
- [The replay validator family](#the-replay-validator-family)
- [Profiles and the earthlike regime gates](#profiles-and-the-earthlike-regime-gates)
- [Exit codes and policy semantics](#exit-codes-and-policy-semantics)
- [Reading and triaging a failing report](#reading-and-triaging-a-failing-report)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

---

## The two validation commands

Both commands are registered on the same Typer app and share one world loader, `_load_world_for_cli` in `src/magic_geo/cli/_app.py:16`, which reads `.json` or `.mgeo` with strict JSON-model validation and exits `2` with `Invalid world file: <exc>` on `OSError | UnicodeError | ValueError`.

| | `validate` | `validate-geo` |
|---|---|---|
| Defined at | `src/magic_geo/cli/commands/validate.py:91` | `src/magic_geo/cli/commands/validate_geo.py:23` |
| Help string | `Run the full world-consistency gate on a generated world file.` | `Validate only natural geography, conservation, and selected realism gates.` |
| Options | `--world` / `-w` only | `--world`/`-w`, `--profile`, `--output`/`-o`, `--fail-on-warnings`/`--allow-warnings` |
| Output | `OK` on stdout, or `FAIL <message>` lines on stderr | one summary line on stdout plus optional JSON report; `FAIL <domain>.<name>: <message>` lines on stderr |
| Report artifact | none — there is no `--output` | full JSON report via `--output` |
| Severity model | none; every one of the 1,089 `failures.append(...)` sites is fatal | `error` vs `warning`, plus `not_applicable` |
| Scope | whole world document (129 distinct top-level payload keys are read) | natural geography only |
| Implementation size | a 22,333-line module that is essentially one function (`def validate` at `validate.py:92` runs to end of file) plus delegated validators | `geo_validation.py` (2,826) + `geo_validation_subsystems.py` (2,909) + `geo_validation_physics.py` (2,779) + 11 replay modules |

### What `validate-geo` deliberately ignores

The excluded scope is a first-class declared field of the report, `excluded_scope` at `src/magic_geo/geo_validation.py:2812`, reproduced verbatim:

> settlements, navigation/ports/routes, politics, territory, culture, history, population, economy, conflict, logistics, markets, campaigns, and language

Concretely, `validate-geo` never reads or asserts anything about:

| Ignored area | World keys never inspected by the geo path | Covered instead by |
|---|---|---|
| Settlements and routes | `settlements`, `routes`, `route_corridors`, `route_capacity_constraints`, `port_sites`, `navigable_waterways` | `validate` |
| Politics and territory | `political_regions`, `borders`, `territorial_snapshots`, `territorial_boundary_segments`, `natural_frontiers` | `validate` |
| History and dynasties | `historical_eras`, `historical_events`, `rulers`, `dynasties`, `cadet_branches`, `marriage_alliances` | `validate` |
| Population and agents | `population_regions`, `population_histories`, `individual_agents`, `individual_life_events`, `household_cohorts`, `firm_agents`, `demographic_agent_histories` | `validate` |
| Economy and markets | `trade_flows`, `economy_histories`, `market_clearing_records`, `market_agent_orders`, `market_exchanges`, `market_price_iterations`, `market_inventory_histories`, `logistics_networks` | `validate` |
| Conflict and campaigns | `conflicts`, `campaign_movements`, `campaign_front_histories`, `campaign_path_segments`, `strategic_campaign_plans`, `tactical_engagements` | `validate` |
| Culture and language | `cultures`, `language_regions`, `phonological_rules`, `phonological_histories`, `lexical_correspondences`, `lexical_diffusion_histories`, `speaker_population_histories` | `validate` |
| Human-geography realism | `worldbuilding_realism_checks`, `sacred_areas`, `ruins`, `mining_zones`, `agricultural_zones` | `validate` |

The subsystem module states the same boundary in its own docstring: "Civilization layers are not read or validated here." (`src/magic_geo/geo_validation_subsystems.py:1-9`).

Beyond record scope, `validate-geo` also declines several *epistemic* scopes. It carries a fixed list of 12 `model_limitations` (`GEO_MODEL_LIMITATIONS`, `src/magic_geo/geo_validation.py:28-41`) into every report, and each replay check's `expected` map explicitly enumerates what is **not** resolved (see [The replay validator family](#the-replay-validator-family)).

### Worked example

```bash
# generate a small geo-only world
magic-geo init-config -o smoke.yaml -p smoke --force
magic-geo generate -c smoke.yaml -o geo.json --geo-only --cells 512

# structured geo audit, machine-readable report
magic-geo validate-geo --world geo.json --output geo-report.json
# OK geo | checks=150 errors=0 warnings=0 not_applicable=3

# the same world under the full world gate fails: civilization layers are absent
magic-geo validate --world geo.json
# FAIL settlement selection model or causal replay invalid
# FAIL route network model or causal replay invalid
# ... (184 FAIL lines)
```

A full-scope world passes both:

```bash
magic-geo generate -c smoke.yaml -o full.json --cells 512
magic-geo validate --world full.json          # OK
magic-geo validate-geo --world full.json      # OK geo | checks=149 errors=0 warnings=0 not_applicable=3
```

The 150 vs 149 difference is the `evolution_provenance.history_family_temporal_semantics` check, which is only appended when `generation_scope == "geo_only"` or the `geo_evolution_provenance` key is present (`src/magic_geo/geo_validation.py:2718-2724`).

---

## The check result model

Every geo check is a flat dictionary carrying the same ten fields, produced by one of three constructors: `_check` (`src/magic_geo/geo_validation.py:271`), `_add` (`src/magic_geo/geo_validation_subsystems.py:31`) and `_append_check` (`src/magic_geo/geo_validation_physics.py:95`). `_check` and `_add` are identical, including the `passed: bool | None` argument and the `severity` keyword. `_append_check` is deliberately narrower: it takes `passed: bool` and hardcodes `"severity": "error"`, so no physics replay check can ever be `not_applicable` or a warning. `validate_geo_evolution_provenance` builds the same record by hand (`src/magic_geo/geo_evolution_provenance.py:366-393`).

| Field | Type | Meaning |
|---|---|---|
| `id` | int | Sequential index within the final `checks` array. Sub-validators number locally and are renumbered on append (`geo_validation.py:2710-2724`). |
| `domain` | str | Grouping key; also the join key used by the layer-contract audit. |
| `name` | str | Check name, unique within its domain. |
| `status` | str | One of `passed`, `failed`, `not_applicable`. |
| `passed` | bool | `passed is True` only — `false` for both `failed` **and** `not_applicable`. |
| `severity` | str | `error` or `warning`. |
| `message` | str | Human-readable statement of the invariant, or of the violation. |
| `observed` | any | What the world actually contained. Often a nested object of counts/residuals. |
| `expected` | any | What the invariant required. For replay checks this is a map of explicit resolved/unresolved claims. |
| `evidence` | dict | Supporting counters. For replay checks it is `{"violations": [...]}`; for realism checks it is the producer's own evidence counters. |

### Status values

| `passed` argument | `status` | `passed` field | Counted in | Fatal? |
|---|---|---|---|---|
| `True` | `passed` | `true` | `summary.passed_count` | no |
| `False` | `failed` | `false` | `summary.error_failure_count` or `summary.warning_failure_count` by severity | fatal only when `severity == "error"` |
| `None` | `not_applicable` | `false` | `summary.not_applicable_count` | no |

The mapping is a single expression: `status = "not_applicable" if passed is None else ("passed" if passed else "failed")` (`geo_validation.py:283`).

### Severity

`severity="warning"` appears exactly once in the whole source tree — `src/magic_geo/geo_validation.py:745` — and applies only to the `realism_evidence` domain. Everything else is `severity="error"`. On a healthy 512-cell geo-only world the split is 124 error-severity and 26 warning-severity checks out of 150; under `--profile earthlike` it becomes 134 and 26 out of 160, because all 10 added profile gates are error-severity. `report["passed"]` is computed as "no error-severity failures" (`geo_validation.py:2815`); warnings are promoted to fatal only by the CLI flag `--fail-on-warnings`.

### Why `not_applicable` exists instead of a vacuous pass

The realism checks embedded in the world document (`planet_realism_checks`, `climate_realism_checks`, `geology_realism_checks`, `hydrology_realism_checks`, `biome_realism_checks`) report a *perfect score of 1.0 when their candidate population is empty*. The comment above `REALISM_EVIDENCE_REQUIREMENTS` states the design decision directly (`geo_validation.py:132-133`):

> These checks currently report a perfect score when their candidate set is empty. Deep validation treats that state as not-applicable instead of positive evidence.

`_realism_record_applicable` (`geo_validation.py:557`) gates each realism record against a declared set of evidence counters and per-counter minimum counts. `REALISM_EVIDENCE_REQUIREMENTS` (`geo_validation.py:134-208`) maps 22 `(family, check)` pairs — every check outside `planet_realism_checks` — to the counters they must carry, 29 `(family, check, counter)` triples in total. `REALISM_EVIDENCE_MINIMUM_COUNTS` (`geo_validation.py:210-223`) defaults every counter to a minimum of 3 and then overrides five of them:

| Family | Check | Evidence counter | Minimum |
|---|---|---|---|
| `geology_realism_checks` | `mountain_convergent_alignment` | `high_mountain_cell_count` | 5 |
| `geology_realism_checks` | `oceanic_ridge_divergent_alignment` | `shallow_oceanic_high_cell_count` | 5 |
| `geology_realism_checks` | `transform_fault_linearity` | `transform_candidate_cell_count` | 5 |
| `hydrology_realism_checks` | `watershed_divide_alignment` | `boundary_cell_count` | 10 |
| `biome_realism_checks` | `mangrove_warm_wet_coast_constraint` | `mangrove_cell_count` | 1 |
| all other declared counters | — | — | 3 (default) |

A real `not_applicable` record from a generated report shows the mechanism precisely — a declared value of `1.0` inside a `[0.75, 1.0]` target range that is nevertheless *not* accepted as evidence, because there were zero delta cells:

```json
{
  "id": 135,
  "domain": "realism_evidence",
  "name": "hydrology_realism_checks.delta_lowland_sediment_terminal_water",
  "status": "not_applicable",
  "passed": false,
  "severity": "warning",
  "message": "realism claim has no eligible evidence; a vacuous score is not a pass",
  "observed": 1.0,
  "expected": { "target_min": 0.75, "target_max": 1.0 },
  "evidence": {
    "delta_cell_count": 0,
    "marine_terminal_delta_count": 0,
    "lacustrine_terminal_delta_count": 0,
    "qualifying_marine_terminal_delta_count": 0,
    "qualifying_lacustrine_terminal_delta_count": 0,
    "lowland_sediment_terminal_water_delta_count": 0,
    "unrecognized_terminal_delta_count": 0
  }
}
```

`not_applicable` also feeds two derived metrics used by the `earthlike` profile: `realism_evidence_coverage_fraction` (applicable records / all records) and `applicable_realism_pass_fraction` (in-range records / applicable records) — see `extract_geo_metrics` at `geo_validation.py:539-550`. Splitting these two is what stops an evidence-free world from claiming a perfect realism score.

### Realism check registry

`REALISM_FAMILIES` (`geo_validation.py:75-81`) and `REALISM_EXPECTED_NAMES` (`geo_validation.py:83-130`) pin the exact registry that must be present:

| Family | Expected check names | Count |
|---|---|---|
| `planet_realism_checks` | `liquid_water_temperature_window`, `atmosphere_gravity_stability`, `rotation_circulation_plausibility`, `surface_water_inventory` | 4 |
| `climate_realism_checks` | `subtropical_dry_belt`, `equatorial_ocean_humidity`, `orographic_rain_shadow`, `continental_interior_extremes`, `cold_current_coastal_drying`, `warm_current_climate_moderation` | 6 |
| `geology_realism_checks` | `mountain_convergent_alignment`, `trench_convergent_alignment`, `oceanic_ridge_divergent_alignment`, `volcanic_arc_trench_pairing`, `transform_fault_linearity`, `hypsometry_bimodality` | 6 |
| `hydrology_realism_checks` | `river_terminal_sink_validity`, `river_downhill_flow`, `tributary_merge_coherence`, `delta_lowland_sediment_terminal_water`, `watershed_divide_alignment` | 5 |
| `biome_realism_checks` | `desert_water_deficit_alignment`, `forest_water_availability_alignment`, `tundra_cold_altitude_alignment`, `savanna_seasonality_alignment`, `mangrove_warm_wet_coast_constraint` | 5 |

Each family yields five *kinds* of fatal integrity check in domain `realism_evidence_integrity` (`_validate_realism_evidence`, `geo_validation.py:595`):

| Check name pattern | Emitted when | Asserts |
|---|---|---|
| `<family>_records` | family missing or empty | family must be a non-empty list |
| `<family>.registry` | always | complete, unique, integer-id registry matching `REALISM_EXPECTED_NAMES` |
| `<family>.summary` | always | `summary.<prefix>_check_count`, `_pass_count`, `_pass_fraction`, `mean_<prefix>_score` mirror the records within 1e-6 |
| `<family>.record_shape` | a record is not an object | records must be objects |
| `<family>.<name>` | per record | value/target range/declared `passed`/`score` must agree, `score ∈ [0,1]`, `score == 1.0` iff in range |

and one *warning*-severity check per record in domain `realism_evidence`. On the reference world this is 36 integrity checks (5 registry + 5 summary + 26 per-name) and 26 realism-evidence checks.

---

## Report JSON structure

`_finalize_report` (`src/magic_geo/geo_validation.py:2787`) builds the envelope; `validate_geo_world` (`geo_validation.py:2743`) attaches the layer-contract audit and folds it into the top-level verdict; the CLI adds `requested_policy` (`validate_geo.py:62-65`).

| Field | Type | Source | Meaning |
|---|---|---|---|
| `schema_version` | int, `1` | `GEO_VALIDATION_SCHEMA_VERSION`, `geo_validation.py:20` | Report schema version. |
| `report_type` | str, `"geo_world_validation_v1"` | `geo_validation.py:2810` | Report discriminator. |
| `scope` | str | `GEO_VALIDATION_SCOPE`, `geo_validation.py:22-26` | What was validated, in prose. |
| `excluded_scope` | str | `geo_validation.py:2812` | What was deliberately not validated. |
| `model_limitations` | list[str], 12 entries | `GEO_MODEL_LIMITATIONS`, `geo_validation.py:28-41` | Declared unresolved model claims, carried into every report. |
| `profile` | str | argument | `generic` or `earthlike` (any other value also produces a failing `contract.known_validation_profile` check). |
| `passed` | bool | `geo_validation.py:2815`, then `2781-2783` | No error-severity failures **and** all layer contracts passed. |
| `summary` | dict | see below | Aggregates. |
| `metrics` | dict | `extract_geo_metrics`, `geo_validation.py:339` | 37 natural-system observables (below). |
| `checks` | list[dict] | all validators | Every check record, in emission order. |
| `layer_contracts` | dict | `evaluate_geo_layer_contracts`, `geo_layer_contracts.py:329` | 14-layer contract audit envelope. |
| `requested_policy` | dict | `validate_geo.py:62` | **CLI-only.** `{fail_on_warnings, policy_passed}`; absent when `validate_geo_world` is called from Python. |

### `summary`

| Field | Type | Meaning |
|---|---|---|
| `check_count` | int | Total checks. |
| `passed_count` | int | `status == "passed"`. |
| `error_failure_count` | int | `status == "failed"` and `severity == "error"`. |
| `warning_failure_count` | int | `status == "failed"` and `severity == "warning"`. |
| `not_applicable_count` | int | `status == "not_applicable"`. |
| `domains` | dict[str, dict] | Per-domain `{check_count, passed_count, failed_count, not_applicable_count}`. |
| `layer_contract_count` | int | Always 14. Added by `validate_geo_world` (`geo_validation.py:2771`). |
| `layer_contract_pass_count` | int | Layers whose `contract_passed` is true. |
| `layer_contract_failure_count` | int | Layers that failed. |
| `all_layer_contracts_passed` | bool | Conjunction over all 14 layers. |

Note the per-domain sub-dict is seeded with exactly the four keys above and incremented by `domain[f"{check['status']}_count"] += 1` (`geo_validation.py:2807`), so `failed_count` mixes error and warning failures — use the top-level counters or filter `checks` when you need the split.

### `metrics` — `extract_geo_metrics`

37 keys, all derived without reading civilization layers (`geo_validation.py:339-554`). Values are `round(..., 6)`; land-conditional metrics are `None` when the world has no land cells.

| Metric | Definition |
|---|---|
| `cell_count` | Number of cells (`0` alone is returned when the cell payload is unusable). |
| `surface_area_km2` | Sum of `area_km2`. |
| `land_area_fraction` / `ocean_fraction` | Area fraction of non-water / water cells. |
| `ocean_volume_km3` | `Σ area_km2 · water_depth_m / 1000` over water cells. |
| `global_mean_temperature_c` | Area-weighted `temperature_c` over all cells. |
| `mean_land_temperature_c` | Area-weighted `temperature_c` over land. |
| `mean_land_precipitation_mm_y` | Area-weighted `precipitation_mm_y` over land. |
| `mean_land_runoff_mm_y` | Area-weighted `runoff_mm_y` over land. |
| `mean_land_seasonal_temperature_range_c` | Area-weighted (max − min) of `temperature_monthly_c` over land. |
| `minimum_elevation_m`, `maximum_elevation_m`, `elevation_span_m` | Extremes and span of `elevation_m`. |
| `river_cell_fraction`, `lake_cell_fraction` | Fraction of cells with `is_river` / `is_lake`. |
| `ice_cell_fraction` | Fraction with `ice_thickness_m > 25.0` or `biome == "ice_cap"`. |
| `desert_land_fraction` | Land fraction in `{hot_desert, cold_desert}`. |
| `forest_land_fraction` | Land fraction in `{boreal_forest, temperate_forest, tropical_rainforest, tropical_seasonal_forest}`. |
| `biome_class_count` | Distinct `biome` values across all cells. |
| `continent_landmass_count` | `len(world["landmasses"])`. |
| `simulation_stage_count` | `len(world["earth_system_feedback_history"])`. |
| `maturation_timestep_ma` | `simulation_clock.nominal_timestep_ma`. |
| `nominal_maturation_duration_ma` | `simulation_clock.final_nominal_elapsed_time_ma`. |
| `maturation_timestep_scale` | `simulation_clock.maturation_timestep_scale`. |
| `plate_motion_transition_count` | Records in `plate_motion_history` with `stage == "plate_motion_iteration"`. |
| `crust_evolved_cell_fraction` | Cells whose age/thickness/density differ from the step-0 overlap-ledger remap by > 1e-6. |
| `plate_reassigned_cell_fraction` | Cells with `plate_assignment_change_count > 0`. |
| `mean_plate_cumulative_rotation_deg` | Mean `cumulative_rotation_deg` over plates. |
| `mean_erosion_iteration_elevation_change_m` | Mean `mean_abs_elevation_change_m_from_previous_stage` over erosion-applied feedback stages. |
| `sediment_gross_mobilization_volume_km3` | `sediment_inventory_model.gross_mobilization_volume_km3`. |
| `mountain_convergent_alignment` | Value of that geology realism record. |
| `valid_river_sink_fraction` | Value of `hydrology_realism_checks.river_terminal_sink_validity`. |
| `delta_lowland_sediment_terminal_water_index` | Value of the corresponding hydrology realism record. |
| `realism_record_count` | Total realism records across the 5 families. |
| `realism_evidence_coverage_fraction` | Applicable records / total records. |
| `applicable_realism_pass_fraction` | In-range records / applicable records. |
| `calibration_pass_fraction` | In-range records / total records in `world["calibration_checks"]` (`_calibration_pass_fraction`, `geo_validation.py:585`). |

### Failure containment

`validate_geo_world` wraps the implementation in `try/except Exception` (`geo_validation.py:2754-2767`). Any exception collapses the entire report into a single failing check `contract.malformed_optional_payload`, whose `observed` carries `{"exception_type", "detail"}`. The docstring is explicit that this exists because the entry point also validates externally supplied JSON: "Any unexpected coercion or shape error is therefore a failed contract check, never an exception escaping to the caller."

Similarly, `validate_natural_subsystems` wraps each of its 13 subsystem validators. On exception it **deletes** that validator's partial checks and replaces them with a single failing `<domain>.validator_completed` (`geo_validation_subsystems.py:2888-2903`).

> Caveat, not verified as intended behavior: writing the report with `--output` uses `write_json`, which raises `ValueError: Out of range float values are not JSON compliant: inf` if any check's `observed`/`evidence` contains a non-finite float. This was observed on a stale world; running `validate-geo` without `--output` still produces the console verdict.

---

## `validate`: validator families

`validate` accumulates a `list[str]` of failure strings and prints them all at the end. It has two exit gates:

1. **Early gate** (`validate.py:119-122`): `schema_version != 2`, retired schema fields present, or invalid planet parameters. This short-circuits *before* every other check, so a schema mismatch masks all other diagnostics.
2. **Final gate** (`validate.py:22328-22331`): any accumulated failure at all.

### Delegated to `src/magic_geo/cli/validators/`

The package docstring is the contract: "Every function takes the world payload plus derived lookups and returns a list of failure strings; none of them raise or exit." (`src/magic_geo/cli/validators/__init__.py:1-5`). Most of them are all-or-nothing: on any deviation they return one fixed sentinel string. The four sediment validators are the exception and return itemized, stage-scoped messages.

| Family | Module (`src/magic_geo/cli/validators/`) | What it asserts | Typical failure |
|---|---|---|---|
| Hydrologic water budget | `hydrology.py:37` | Replays every native climate-loss partition before routed hydrology: model type `causal_land_climate_loss_partition_v1`, domain `non_marine_cells`, PET/loss/infiltration/AET sub-model identifiers, and per-stage volume closure of `P − AET − infiltration = runoff` | `hydrologic water budget model or replay invalid` |
| Groundwater recharge | `hydrology.py:423` | Replays the infiltration-bounded aquifer/vadose source partition: model `infiltration_bounded_aquifer_recharge_v1`, source field `infiltration_mm_y`, recharge fraction clamped to `[0.05, 0.85]`, mass-conserving split, marine cells zeroed | `groundwater recharge model or source partition invalid` |
| Aquifer resources | `hydrology.py:590` | Replays aquifer properties, classification and basin grouping under `finite_recharge_causal_aquifer_resources_v1` (system thresholds `productivity ≥ 0.18`, `recharge ≥ 25.0 mm/y`) | `aquifer resource model or causal replay invalid` |
| Groundwater flow | `hydrology.py:995` | Replays deterministic descending-head routing and every local recharge-volume split under `descending_head_recharge_conserving_groundwater_flow_v1` | `groundwater flow model or routing replay invalid` |
| River channel morphology | `rivers.py:24` | Replays causal channel geometry, morphologic classes and connected channel systems | `river channel morphology model or causal replay invalid` |
| River hydraulics | `rivers.py:517` | Replays Manning-blended channel hydraulics and one-to-one channel-system reaches (`manning_blended_diagnostic_river_hydraulics_v1`) | `river hydraulics model or causal replay invalid` |
| Fluvial sediment routing | `sediment.py:28` | Per-stage replay of routed volumes (local source, incoming, outgoing, local/terminal deposition), feedback links, aggregates and cumulative cell fields | `fluvial sediment routing stage {i} does not close`, `... feedback metrics invalid`, `... cumulative cell fields invalid` |
| Hillslope sediment transport | `sediment.py:1059` | Per-cell production/deposition and edge counts replayed from the declared diffusivity and lithology-resistance model | itemized `hillslope sediment transport ...` messages |
| Glacial sediment transport | `sediment.py:1916` | Per-cell production/deposition and transfer counts replayed from the glacial mobile fraction | itemized `glacial sediment transport ...` messages |
| Sediment inventory | `sediment.py:2583` | Replays the finite mobile-sediment inventory in native stage order (`finite_alluvium_bedrock_sediment_inventory_v1`) across feedback, numeric-depression, hillslope, fluvial and glacial histories | itemized `sediment inventory ...` messages |
| Settlement selection | `settlement.py:22` | Replays native settlement score, selection threshold (`0.48`), type assignment and record mirrors | `settlement selection model or causal replay invalid` |
| Route network | `settlement.py:465` | Replays endpoint ranking, pair selection, cost and route type (`causal_endpoint_barrier_ranked_route_network_v1`) | `route network model or causal replay invalid` |
| Political regions | `political.py:121` | Replays capital selection and settlement/cell partitions (`causal_capital_barrier_partition_political_regions_v1`) | `political region model or causal replay invalid` |
| Political borders | `political.py:506` | Replays every cross-region adjacency edge, its type, length and score | `political border model or causal replay invalid` |
| Trade flows | `political.py:698` | Replays one endpoint-driven trade flow for every valid native route | `trade flow model or causal replay invalid` |
| Navigability | `navigability.py:21` | Replays navigability components, classes and exact waterway records (threshold `0.52`) | `navigability model or causal replay invalid` |
| Port sites | `ports.py:21` | Replays port suitability, selection (threshold `0.58`), type priority, records and links | `port site model or causal replay invalid` |
| Route corridors | `corridors.py:24` | Replays feature fields, weighted Dijkstra paths, assignment and records (feature threshold `0.45`) | `route corridor model or causal replay invalid` |

Shared helper: `_nominal_time_record_valid` (`_shared.py:16`) validates the nominal-interval record schema common to all maturation histories, requiring `nominal_time_calibrated is False` and `physical_time_resolved is False`. All threshold and model-identifier constants live in `src/magic_geo/cli/_constants.py`.

Call sites, all `failures.extend(...)` or tuple-unpacked: `validate.py:7948, 9101, 9107, 9113, 9116, 10127, 10129, 10584-10588, 10601, 10856, 14592-14594, 17996`.

### Delegated to top-level `magic_geo.*_validation` modules

| Family | Module | Call site | Failure prefix |
|---|---|---|---|
| Conservative crust overlap transport | `crust_transport_validation.py` | `validate.py:6037` | contributes to `plate kinematic model or motion history invalid` |
| Oceanic age–depth equilibrium | `oceanic_age_depth_validation.py` | `validate.py:6040` | `oceanic age-depth equilibrium replay invalid: …` |
| Initial oceanic crust age | `initial_oceanic_crust_age_validation.py` | `validate.py:6047` | `initial oceanic crust age replay invalid: …` |
| Plate boundary segments | `plate_boundary_edge_validation.py` | `validate.py:6056` | `plate boundary segment replay invalid: …` |
| Crust material shadow | `crust_material_shadow_validation.py` | `validate.py:6063` | `crust material shadow: …` |
| Bedrock/mobile sediment interface | `sediment_interface_validation.py` | `validate.py:9119` | `sediment interface replay invalid: …` |
| Human geography | `human_geography_validation.py` | `validate.py:10589` | module-supplied strings |
| Cultural geography | `cultural_geography_validation.py` | `validate.py:10590` | module-supplied strings |
| Historical geography | `historical_geography_validation.py` | `validate.py:10591` | module-supplied strings |
| Civilization geography | `civilization_geography_validation.py` | `validate.py:10592` | module-supplied strings |
| Territorial geography | `territorial_geography_validation.py` | `validate.py:10593` | module-supplied strings |
| History and economy | `history_economy_validation.py` | `validate.py:10594` | module-supplied strings |
| Demographic agents | `demographic_agents_validation.py` | `validate.py:10595` | module-supplied strings |
| Dynasty genealogy | `dynasty_genealogy_validation.py` | `validate.py:10596` | module-supplied strings |
| Logistics exchange | `logistics_exchange_validation.py` | `validate.py:10597` | module-supplied strings |
| Campaign operations | `campaign_operations_validation.py` | `validate.py:10598` | module-supplied strings |
| Market clearing | `market_clearing_validation.py` | `validate.py:10599` | module-supplied strings |
| Phonology history | `phonology_history_validation.py` | `validate.py:10600` | module-supplied strings |

Note that three replay modules are reachable **only** from the geo path and are not imported by `validate.py`: `crust_overlap_candidate_fate_validation.py`, `crust_dry_rock_accounting_validation.py`, `sediment_source_partition_validation.py`.

### Inline families

The bulk of that module is inline. Grouped by the 129 top-level payload keys the command reads via `payload.get("…")`:

| Inline family | Representative keys |
|---|---|
| Schema and planet | `schema_version`, `planet_parameters`, `planet_realism_checks`, `mesh_backend`, `mesh_lod`, `cells`, `cell_adjacency_edges`, `cell_area_model`, `spherical_spatial_index`, `summary`, `simulation_clock` |
| Tectonics | `plates`, `plate_motion_history`, `plate_kinematic_model`, `tectonic_zones`, `subduction_zones`, `collision_zones`, `rift_zones`, `fault_systems`, `geology_realism_checks` |
| Sea level and ocean | `sea_level_model`, `continental_shelves`, `marine_regions`, `marine_chokepoints`, `ocean_current_systems`, `ocean_current_transport_edges`, `reef_systems`, `coastal_features` |
| Hydrology | `hydrology_realism_checks`, `hydrologic_budget_regions`, `watersheds`, `watershed_boundary_segments`, `lake_basins`, `lake_overflow_histories`, `lake_overflow_channel_histories`, `numeric_depression_correction_history`, `wetland_systems`, `navigable_waterways`, `groundwater_flow_systems`, `aquifer_systems`, `karst_systems` |
| Rivers | `river_channel_systems`, `river_hydraulic_reaches`, `river_network_evolution_events`, `river_reorganization_histories` |
| Sediment and stratigraphy | `sediment_routing_histories`, `sediment_transport_histories`, `sedimentary_basins`, `sedimentary_resource_systems`, `sequence_stratigraphy_histories`, `stratigraphic_columns`, `soil_profiles`, `soil_horizons`, `soil_profile_histories` |
| Cryosphere | `ice_sheets`, `ice_sheet_histories`, `ice_sheet_stability_histories`, `ice_flowline_histories`, `glacial_landform_systems`, `permafrost_regions` |
| Climate and biosphere | `climate_model`, `climate_classification`, `climate_realism_checks`, `climate_energy_balance_records`, `climate_seasonal_histories`, `climate_continentality_regions`, `biome_diagnostics`, `biome_ecotone_regions`, `biome_realism_checks`, `vegetation_succession_histories`, `species_range_records`, `wildfire_spread_histories`, `earth_system_feedback_history` |
| Resources | `resource_deposits`, `ore_genesis_systems`, `petroleum_migration_systems`, `commodity_occurrences`, `renewable_resource_records`, `mining_zones`, `agricultural_zones` |
| Civilization and settlement | `settlements`, `routes`, `route_corridors`, `route_capacity_constraints`, `port_sites`, `borders`, `political_regions`, `territorial_snapshots`, `territorial_boundary_segments`, `natural_frontiers`, `landmasses`, `population_regions`, `population_histories`, `trade_flows`, `logistics_networks`, `sacred_areas`, `ruins`, `worldbuilding_realism_checks` |
| History, agents, economy | `historical_eras`, `historical_events`, `rulers`, `dynasties`, `cadet_branches`, `marriage_alliances`, `individual_agents`, `individual_life_events`, `household_cohorts`, `firm_agents`, `demographic_agent_histories`, `economy_histories`, `conflicts`, `campaign_movements`, `campaign_front_histories`, `campaign_path_segments`, `strategic_campaign_plans`, `tactical_engagements` |
| Markets | `market_clearing_records`, `market_agent_orders`, `market_exchanges`, `market_price_iterations`, `market_inventory_histories` |
| Language | `cultures`, `language_regions`, `phonological_rules`, `phonological_histories`, `lexical_correspondences`, `lexical_diffusion_histories`, `speaker_population_histories` |
| Graph contracts | `_validate_graph_record(graph_name, expected_node_count)` (`validate.py:21996`) applied to `plate_graph` (`:22017`), `river_graph` (`:22059`), `watershed_graph` (`:22088`), `trade_route_graph` (`:22144`), `political_region_graph` (`:22180`) |
| Calibration tail | `calibration_checks` count/pass-count/fraction/score-range plus per-check field presence (`validate.py:22306-22326`) |

---

## `validate-geo`: top-level domains

These are the checks emitted directly by `_validate_geo_world_impl` (`src/magic_geo/geo_validation.py:803`), before the sub-validators are appended. Domains marked *conditional* are only emitted on a failure path.

| Domain | Check name | Line | Asserts |
|---|---|---|---|
| `contract` | `world_object` | `:818` *(conditional)* | Root JSON must be an object; returns immediately. |
| `contract` | `world_schema_version` | `:830` | `schema_version` is `int` and equals `CURRENT_WORLD_SCHEMA_VERSION` (2). |
| `contract` | `retired_world_schema_fields` | `:843` | Schema-1 compatibility fields must not reappear. |
| `contract` | `summary_object` | `:853` *(conditional)* | `world.summary` must be an object. |
| `contract` | `cell_payload_available` | `:864` *(conditional)* | Requires `output.include_cells=true` and a non-empty cell list; returns immediately. |
| `contract` | `cell_count` | `:879` | `summary.cell_count` equals the exported mesh size. |
| `contract` | `explicit_planet_and_physics_models` | `:913` | 12 required planet parameters present and finite (`radius_km`, `gravity_g`, `day_length_hours`, `axial_tilt_deg`, `orbital_eccentricity`, `stellar_luminosity`, `atmosphere_pressure_bar`, `greenhouse_factor`, `ocean_fraction_target`, `ocean_water_inventory_km3`, `internal_heat`, `geological_age_ga`), plus non-empty `climate_model` and `sea_level_model`. |
| `contract` | `current_climate_model` | `:947` | `climate_model` declares `equilibrium_latitude_circulation_climate_v5` with the current precipitation semantics. |
| `contract` | `finite_core_geo_fields` | `:1006` | 23 core numeric cell fields exist and are finite (`area_km2`, `lat_deg`, `lon_deg`, `elevation_m`, `water_depth_m`, `temperature_c`, `precipitation_mm_y`, `actual_evapotranspiration_mm_y`, `infiltration_mm_y`, `runoff_mm_y`, `flow_accumulation`, `hydrologic_surface_elevation_m`, `crust_age_ma`, `ice_thickness_m`, and 9 `groundwater_*`/`vadose_*` fields). |
| `contract` | `cell_types_enums_and_nonnegative_states` | `:1041` | Cell flags are booleans, crust/biome enums are known, conserved magnitudes non-negative. |
| `contract` | `known_validation_profile` | `:2733` *(conditional)* | Profile is `generic` or `earthlike`. |
| `contract` | `malformed_optional_payload` | `:2760` *(conditional)* | Emitted by the outer exception handler. |
| `mesh` | `unique_cell_ids` | `:963` | Each cell has one unique integer id; otherwise the report is finalized early. |
| `mesh` | `spherical_surface_area_closure` | `:1059` | Positive areas summing near `4πR²` for the configured radius. |
| `mesh` | `unit_sphere_positions` | `:1102` | Exported cell centers lie on the unit sphere. |
| `mesh` | `coordinate_position_consistency` | `:1112` | Lat/lon match the unique exported unit-sphere positions. |
| `mesh` | `adjacency_graph_integrity` | `:1152` | Adjacency is valid, symmetric, self-loop free and connected. |
| `mesh` | `native_cell_area_model_replay` | `:1181` | Areas independently replay the declared Fibonacci or geodesic spherical area model. |
| `mesh` | `configured_radius_distance_scaling` | `:1255` | Great-circle distances use the configured planet radius. |
| `tectonics` | `plate_assignment_coverage` | `:1289` | Every cell belongs to an exported plate. |
| `tectonics` | `initial_crust_identity_checkpoint` | `:1299` | Plate-motion step 0 provides complete numeric initial crust state. |
| `tectonics` | `crust_age_within_planet_age` | `:1315` | Crust cannot predate the configured planet. |
| `sea_level` | `ocean_inventory_closure` | `:1358` | Connected marine columns close the configured ocean inventory. |
| `sea_level` | `single_connected_ocean` | `:1436` | Marine water is the largest connected below-sea component and matches sea-level aggregates. |
| `climate` | `monthly_annual_climate_closure` | `:1471` | Twelve monthly values reconstruct annual temperature and precipitation. |
| `climate` | `configured_global_temperature_response` | `:1498` | Area-mean temperature responds to configured stellar, greenhouse and pressure forcing. |
| `climate` | `climate_energy_record_coverage` | `:2112` | One finite climate-energy diagnostic per cell, tied to its generated temperature. |
| `hydrology` | `land_water_budget_closure` | `:1526` | Land precipitation partitions into AET, infiltration and runoff; marine cells excluded. |
| `hydrology` | `groundwater_partition_closure` | `:1638` | Infiltration-to-recharge, volume conversion and groundwater routing partitions must close (residual tolerances 2e-4 / 2e-5 / 1e-3, zero negative terms, zero invalid links, zero non-zero marine groundwater). |
| `hydrology` | `configured_gravity_propagation` | `:1672` | River dynamics use configured relative surface gravity. |
| `hydrology` | `acyclic_downhill_drainage` | `:1795` | Drainage is adjacent, strictly downhill, acyclic, accumulation-conserving, terminating in valid basins. |
| `sediment` | `sediment_mass_conservation` | `:2027` | Reported and independently reconstructed sediment transport/inventory ledgers close. |
| `simulation` | `coupled_stage_clock` | `:2063` | Clock contains initial, configured-erosion and final cryosphere stages. |
| `cryosphere` | `ice_sheet_and_flow_coherence` | `:2179` | Ice is non-negative, assigned to coherent sheets, and flows to lower adjacent cells. |
| `soil_biome` | `soil_profile_coverage_and_bounds` | `:2251` | Every eligible land/soil/depth cell has one bounded soil profile mirroring cell state. |
| `soil_biome` | `biome_diagnostic_coverage` | `:2293` | Every cell has one bounded biome diagnostic mirroring its assigned biome. |
| `soil_biome` | `biome_diagnostic_causal_replay` | `:2371` | Biome diagnostics, cell derivatives and aggregates replay from climate and soil inputs. |
| `natural_resources` | `deposit_and_commodity_linkage` | `:2431` | Deposits mirror source cells and every commodity links to a valid deposit. |
| `natural_graphs` | `physical_graph_coverage` | `:2546` | Plate, river and watershed graph counts mirror their natural source records. |
| `natural_graphs` | `watershed_boundary_ledger` | `:2642` | Watershed boundary segments exactly mirror cross-basin physical adjacency edges. |
| `earth_calibration` | `built_in_calibration_integrity` | `:2698` | The 12 built-in Earth comparison records (`CALIBRATION_EXPECTED_METRICS`, `geo_validation.py:43-58`), their ranges, declared results and summary all agree. |

`CALIBRATION_EXPECTED_METRICS` is the *built-in* Earth comparison set: `ocean_fraction`, `mean_land_elevation_m`, `hypsometric_span_m`, `global_mean_temperature_c`, `mean_land_precipitation_mm_y`, `mean_monthly_temperature_range_c`, `river_cell_fraction`, `endorheic_watershed_fraction`, `desert_land_fraction`, `ice_land_fraction`, `forest_land_fraction`, `coastal_land_fraction`. It is distinct from external dataset calibration, which is a separate verdict — see [Calibration](./14-calibration.md).

### Physics replay checks contributed by `geo_validation_physics.py`

`validate_physics_replays` (`src/magic_geo/geo_validation_physics.py:2495`) contributes 13 checks: 8 `tectonics`, 2 `simulation`, 2 `sediment`, 1 `climate`. Four are computed in-file rather than delegated to a replay module:

| Domain | Check name | Line | Asserts |
|---|---|---|---|
| `tectonics` | `plate_aggregate_replay` | `:1059` | Plate counts, areas, area-weighted crust/heat aggregates, categories and finite physical fields replay from assigned cells. |
| `climate` | `climate_energy_balance_replay` | `:1607` | Per-cell monthly insolation, albedo, greenhouse, longwave, net balance, stress, cell mirrors and global aggregates replay the producer equations. Uses `SOLAR_CONSTANT_W_M2 = 1361.0`, `STEFAN_BOLTZMANN_W_M2_K4 = 5.670374419e-8`, `SURFACE_LONGWAVE_EMISSIVITY = 0.96` (`:26-28`). |
| `simulation` | `coupled_stage_feedback_replay` | `:2332` | Clock and every complete feedback stage follow the configured initial/erosion/cryosphere sequence; the final stage replays from cells; nominal intervals match the configured timestep. `expected` declares `"physical_time_and_convergence_claims": False`. |
| `simulation` | `coupled_stage_summary_mirrors` | `:2471` | Simulation-clock counters and summary feedback metrics reconstruct from the exported stage history. |

The nominal-time semantics used by these checks are pinned by module constants (`geo_validation_physics.py:29-55`): `NOMINAL_TIME_MODEL = "configured_maturation_timestep_nominal_elapsed_time_v1"`, `NOMINAL_TIME_BASIS = "configured_maturation_timestep_ma_per_erosion_transition_v1"`, `NOMINAL_TIME_SOURCE_PARAMETER = "erosion.maturation_timestep_ma"`, `MATURATION_REFERENCE_TIMESTEP_MA = 5.0`, plus the full `ITERATION_PROCESS_ORDER` coupling string and `EROSION_TRANSITION_COUPLING_SEMANTICS`.

---

## `validate-geo`: subsystem groups

`validate_natural_subsystems` (`src/magic_geo/geo_validation_subsystems.py:2816`) runs 13 subsystem validators in a fixed order, each pinned to exactly one domain (`geo_validation_subsystems.py:2850-2887`), plus two root-context checks in domain `natural_pipeline`. On the reference world this contributes 38 checks. Every group compares record membership, source links, value ranges, and `summary` mirrors.

| Group (domain) | Function (`geo_validation_subsystems.py`) | Checks | What it asserts | Typical failure |
|---|---|---|---|---|
| `natural_pipeline` | `validate_natural_subsystems` root, `:2816` | 2 | `world_root` is an object; `cell_and_summary_context` has non-empty unique cells and an object summary | `Natural subsystem validation requires non-empty unique cells and an object summary.` |
| `geometry_indices` | `_validate_geometry_indices`, `:303` | 2 | Mesh LOD tiles exactly aggregate cell ancestry at every level; HEALPix-like and S2-like index records exactly aggregate all generated cells; both mirror their summaries | `Mesh LOD cell ancestry, tile aggregates, or summary mirrors are inconsistent.` |
| `seasonal_climate` | `_validate_seasonal_climate`, `:456` | 2 | Seasonal histories cover each atmospheric cell with continuous monthly records and exact totals; climate classes use the declared legend and continentality regions exactly mirror cells | `Seasonal climate grouping, monthly records, aggregates, or summary mirrors are inconsistent.` |
| `coastal_marine_landmass` | `_validate_surface_geography`, `:734` | 2 | Landmasses, marine regions and shelves exactly partition their cell assignments; coastal features and marine chokepoints link unique valid cells and natural regions | `Landmass, marine-region, or shelf memberships, aggregates, or summaries are inconsistent.` |
| `soils_and_ecotones` | `_validate_soils_ecotones`, `:884` | 2 | Soil profiles link contiguous horizons and continuous pedogenesis histories without orphans; biome ecotone regions exactly mirror typed cells and bounded confidence | `Soil profile, horizon, history, range, or summary links are inconsistent.` |
| `ocean_circulation` | `_validate_ocean`, `:172` | 4 | Typed system/edge records with stable ids; membership and area aggregates; transport edges link adjacent marine cells with bounded diagnostics; cell values and summary mirrors | `Ocean-current transport links or diagnostic ranges are inconsistent.` |
| `tectonic_zones_faults` | `_validate_tectonics`, `:606` | 3 | Typed zone registries (`collision_zones`, `subduction_zones`, `rift_zones`) agree with the combined `tectonic_zones` registry; zones link valid cells, plates, boundary edges and bounded strengths; fault memberships and hazards mirror the tectonic summary | `Tectonic zone membership, source links, or values are inconsistent.` |
| `lakes_watersheds` | `_validate_lakes_watersheds`, `:1305` | 3 | Lake basins mirror cell membership, storage bounds and adjacent overflow paths; overflow histories conserve volume and keep continuous stages; watersheds mirror land-basin membership, channel paths, neighbors and aggregates | `Lake basin membership, storage, or overflow-path records are inconsistent.` |
| `river_evolution_channels` | `_validate_rivers`, `:1489` | 3 | Reorganization histories link one-to-one to bounded evolution events; channel systems mirror river cells, geometry and totals; hydraulic reaches mirror channel cells, source systems and bounded indices | `River evolution events, histories, or summary mirrors are inconsistent.` |
| `sequence_stratigraphy` | `_validate_sequence_stratigraphy`, `:1649` | 1 | Sequence histories cover their source sediment histories and reproduce categorical surface/tract/trajectory aggregates | `Sequence-stratigraphy source links, step values, or aggregates are inconsistent.` |
| `cryosphere_permafrost_glacial` | `_validate_cryosphere`, `:1739` | 3 | Ice-sheet histories conserve bounded volume changes and cover each source sheet; stability and flowline histories link valid sheets/cells; permafrost and glacial-landform regions mirror eligible bounded cell diagnostics | `Ice-sheet history conservation, source coverage, or summary mirrors are inconsistent.` |
| `aquifers_wetlands_karst` | `_validate_subsurface_water`, `:1942` | 2 | Aquifer systems mirror basin cells, bounded properties and conservative recharge metadata; wetland and karst systems mirror bounded cell diagnostics with valid watershed/aquifer sources | `Aquifer membership, properties, recharge metadata, or summary mirrors are inconsistent.` |
| `ecosystems_reefs_species_wildfire` | `_validate_ecosystems`, `:2065` | 4 | Succession and renewable-resource records link valid cells with bounded trajectories; reef systems (including a valid empty registry) mirror bounded cells; species ranges invert cell assignments with ordered climate envelopes; wildfire histories invert cell links with bounded monotonic spread steps | `Species range assignments, habitat sources, envelopes, or summary mirrors are inconsistent.` |
| `geologic_resources` | `_validate_resources`, `:2278` | 5 | Deposits link valid cells with bounded formation/viability diagnostics; ore systems mirror candidate cells and link deposits, tectonics, faults and formation steps; sedimentary systems link coherent basin/column/transport/cell/deposit chains; petroleum systems retain basin-consistent adjacent migration paths; commodity occurrences mirror their deposit sources | `Ore-system memberships, formation sources, values, or summary mirrors are inconsistent.` |
| *(any group)* | exception wrapper, `:2888-2903` | 1 (replacing that group's checks) | The validator must complete without exception on malformed data | `Subsystem validation could not safely inspect malformed data: <ExcType>.` |

Two subsystem validators branch on `generation_scope == "geo_only"`, and in both cases the geo-only branch is the *stronger* one. `_validate_soils_ecotones` (`geo_validation_subsystems.py:898`) additionally requires the pedogenesis model to declare `time_basis == "natural_simulation_stage"` with `stage_source == "earth_system_feedback_history"` and a matching stage count, and requires history step counts to equal the feedback stage count (`:925-931`, `:1031`). `_validate_resources` (`geo_validation_subsystems.py:2282`) additionally replays accessibility, renewability and viability indices against `resource_dynamics` (`:2335-2350`, `:2377`, `:2392`, `:2497`, `:2545`). In both, the pedogenesis model must always declare `physical_time_resolved is False` and `state_mutation_evidence is False`, and the model type must be `posthoc_final_state_profile_reconstruction_v2` (`:918-924`).

---

## The geo layer-contract system

`src/magic_geo/geo_layer_contracts.py` (459 lines) projects the flat check list back onto the 14 planned natural pipeline layers, so a green aggregate cannot hide an unrepresented layer. Schema version `1`, report type `geo_layer_contract_audit_v1`.

### What a contract asserts

`contract_passed` is a conjunction of six conditions (`geo_layer_contracts.py:396-403`):

1. `world` is a `dict`;
2. every key in `required_outputs` exists **and** matches its declared kind;
3. every declared `validator_domain` supplied at least one check;
4. every layer in `dependencies` passed;
5. at least one *passing* check exists among the layer's evidence;
6. zero error-severity failures among the layer's evidence.

What it explicitly does **not** assert is stated in the audit envelope itself (`geo_layer_contracts.py:442-446`):

> A passing layer contract proves artifact, validator-domain, dependency, and assigned fatal-check integrity; it does not prove empirical realism or physical time calibration.

Every emitted layer hardcodes `"empirical_realism_proven": False` (`geo_layer_contracts.py:433`).

Output kinds are themselves part of the contract (`_output_matches_kind`, `:317`). Note the deliberate asymmetry — an empty list is valid evidence for a phenomenon absent in a scenario, while a missing or wrongly typed registry is not:

| Kind | Accepts |
|---|---|
| `dict` | a non-empty dict |
| `list` | any list, **including empty** |
| `nonempty_list` | a list with at least one element |
| `nonempty_str` | a string with non-whitespace content |

### Declaration fields

| Field | Type | Meaning |
|---|---|---|
| `id` | str | Layer identifier, referenced by other layers' `dependencies`. |
| `phase` | int | Pipeline phase, 0–13. |
| `name` | str | Human-readable layer name. |
| `dependencies` | tuple[str] | Upstream layer ids that must have passed. |
| `required_outputs` | dict[str, str] | World key → output kind. |
| `validator_domains` | tuple[str] | Check domains that must each supply ≥1 check. |
| `temporal_class` | str | What kind of time the layer's outputs live in. |
| `evidence_class` | str | What kind of evidence backs the layer. |

### Emitted per-layer fields

Each entry in `layer_contracts.layers` carries the declaration plus:

| Field | Meaning |
|---|---|
| `scope_specific_omissions` | Outputs/domains dropped for this world's `generation_scope`. |
| `missing_or_invalid_outputs` | Required keys absent or of the wrong kind. |
| `validation_domain_coverage` | `{domain: check_count}` for the layer's domains. |
| `missing_validation_domains` | Domains that supplied zero checks. |
| `failed_dependencies` | Upstream layer ids that did not pass. |
| `validation_check_count` / `validation_pass_count` | Totals over the layer's evidence. |
| `validation_error_failure_count` / `validation_warning_count` / `validation_not_applicable_count` | Split by severity and status. |
| `failed_check_names` | `"<domain>.<name>"` for each fatal failure. |
| `contract_passed` | The six-condition conjunction. |
| `temporal_class`, `evidence_class` | Carried through from the declaration. |
| `empirical_realism_proven` | Always `false`. |

### The 14 contracts

`GEO_LAYER_CONTRACTS` (`geo_layer_contracts.py:26-314`), phases 0–13:

| Phase | Id | Dependencies | Validator domains | Temporal class | Evidence class |
|---|---|---|---|---|---|
| 0 | `planet_parameters` | — | `contract` | `configuration_boundary_condition` | `internal_contract_and_broad_regime_checks` |
| 1 | `spherical_mesh` | `planet_parameters` | `mesh`, `geometry_indices`, `natural_graphs` | `static_simulation_domain` | `independent_geometry_replay` |
| 2 | `plate_tectonics` | `spherical_mesh` | `tectonics`, `tectonic_zones_faults` | `native_nominal_maturation_intervals` | `exact_directed_control_volume_segment_kinematics_and_pair_wide_diagnostic_overlap_candidate_crosswalk_replay_without_local_fragment_link_allocation_physical_polarity_or_slab_transfer` |
| 3 | `crust_lithology` | `plate_tectonics` | `tectonics`, `simulation` | `native_nominal_maturation_intervals` | `initial_age_graph_witness_state_sparse_overlap_membership_shadow_and_finite_counter_accounting_replay` |
| 4 | `relief_bathymetry` | `crust_lithology` | `tectonics`, `coastal_marine_landmass` | `native_evolved_then_diagnostic` | `partial_external_relief_calibration` |
| 5 | `sea_level_ocean` | `relief_bathymetry` | `sea_level`, `ocean_circulation`, `coastal_marine_landmass` | `native_equilibrium_recomputed_per_coupled_stage` | `volume_replay_with_diagnostic_circulation` |
| 6 | `climate_atmosphere` | `sea_level_ocean`, `relief_bathymetry` | `climate`, `seasonal_climate` | `equilibrium_climatology_not_transient_weather` | `formula_replay_and_partial_external_climatology` |
| 7 | `hydrology` | `climate_atmosphere`, `relief_bathymetry` | `hydrology`, `lakes_watersheds`, `river_evolution_channels`, `aquifers_wetlands_karst` | `annual_diagnostic_budget_recomputed_per_coupled_stage` | `mass_balance_replay_and_partial_external_network_fit` |
| 8 | `erosion_sediment` | `hydrology`, `plate_tectonics` | `sediment`, `simulation`, `river_evolution_channels`, `sequence_stratigraphy` | `native_nominal_transport_intervals_plus_diagnostic_reconstructions` | `canonical_bedrock_mobile_interface_and_bulk_volume_source_partition_replay_without_dry_rock_mass_or_physical_calibration` |
| 9 | `cryosphere` | `climate_atmosphere`, `erosion_sediment` | `cryosphere`, `cryosphere_permafrost_glacial` | `single_native_bulk_coupling_plus_diagnostic_histories` | `mass_replay_without_dynamic_ice_solver` |
| 10 | `soils_pedogenesis` | `erosion_sediment`, `climate_atmosphere`, `cryosphere` | `soil_biome`, `soils_and_ecotones` | `posthoc_diagnostic_history` | `causal_source_links_without_pedogenic_process_calibration` |
| 11 | `biomes_ecosystems` | `soils_pedogenesis`, `climate_atmosphere`, `hydrology` | `soil_biome`, `soils_and_ecotones`, `ecosystems_reefs_species_wildfire` | `posthoc_diagnostic_trajectories` | `rule_replay_without_population_evolution` |
| 12 | `natural_resources` | `crust_lithology`, `erosion_sediment`, `hydrology`, `biomes_ecosystems` | `natural_resources`, `geologic_resources` | `posthoc_causal_diagnostic` | `source_link_replay_without_geochemical_solver` |
| 13 | `coupled_maturation` | `plate_tectonics`, `sea_level_ocean`, `climate_atmosphere`, `hydrology`, `erosion_sediment`, `cryosphere` | `simulation`, `tectonics`, `hydrology`, `sediment`, `cryosphere`, `evolution_provenance` | `reference_scaled_nominal_maturation_intervals_without_physical_time` | `cross_layer_replay_with_unproven_timestep_convergence_and_no_physical_calibration` |

Required outputs per layer are listed inline in `geo_layer_contracts.py`; for example phase 3 `crust_lithology` requires `cells` (nonempty_list), `plate_motion_history` (nonempty_list), `initial_oceanic_crust_age_model` (dict), `initial_oceanic_crust_age_ledger` (dict), `crust_material_shadow_model` (dict), `crust_material_shadow_history` (nonempty_list), `crust_dry_rock_accounting_model` (dict), `crust_dry_rock_accounting_history` (nonempty_list), `sediment_inventory_model` (dict).

### Scope adaptation

When `generation_scope != "geo_only"`, phase 13 `coupled_maturation` drops the `geo_evolution_provenance` required output and the `evolution_provenance` validator domain, and records both in `scope_specific_omissions` (`geo_layer_contracts.py:344-353`). Verified on a full-scope world:

```json
{
  "id": "coupled_maturation",
  "phase": 13,
  "scope_specific_omissions": ["geo_evolution_provenance", "evolution_provenance"],
  "validator_domains": ["simulation", "tectonics", "hydrology", "sediment", "cryosphere"],
  "validation_domain_coverage": {"simulation": 3, "tectonics": 11, "hydrology": 4, "sediment": 3, "cryosphere": 1},
  "contract_passed": true,
  "empirical_realism_proven": false
}
```

### Audit envelope

| Field | Meaning |
|---|---|
| `schema_version` | `1` (`LAYER_CONTRACT_SCHEMA_VERSION`, `:20`). |
| `report_type` | `"geo_layer_contract_audit_v1"`. |
| `scope` | `"natural generation and maturation layers only"`. |
| `interpretation` | The prose disclaimer quoted above. |
| `layer_count` / `passed_layer_count` / `failed_layer_count` | 14 / passed / failed. |
| `all_layer_contracts_passed` | Conjunction over all layers; ANDed into `report["passed"]`. |
| `layers` | The 14 per-layer records. |

---

## The replay validator family

Each replay module is a self-contained, independent reconstruction of one native invariant. All return the same shape:

```python
{"passed": bool, "metrics": {...}, "failures": [str, ...]}
```

`validate_physics_replays` (`geo_validation_physics.py:2495`) wraps each into one check whose `expected` map explicitly enumerates both what **is** replayed (`True`) and what is deliberately **not** resolved (`False`). That asymmetric map is the mechanism that keeps replay integrity separate from physical claims — read it before treating any replay as a physical result.

| Module (`src/magic_geo/`) | Lines | Check (`domain.name`) | Invariant independently reconstructed | Declared unresolved (`expected: False`) |
|---|---|---|---|---|
| `plate_boundary_edge_validation.py` | 1,552 | `tectonics.exact_directed_plate_boundary_segment_replay` (`:2510`) | Every cross-plate reciprocal control-volume segment, including duplicate neighbor segments, in canonical order from mesh rings, per-step plate assignments, Euler axes/speeds, plate-center history and opening crust state. Model `exact_directed_reciprocal_control_volume_boundary_segments_v2` (`:11`). | `smoothed_cell_boundary_fields_used`, `subduction_polarity_resolved`, `subducted_slab_geometry_resolved` |
| `initial_oceanic_crust_age_validation.py` | 989 | `tectonics.initial_oceanic_crust_age_graph_replay` (`:2540`) | Provisional oceanic-like mask, eligible nominal ridge segments, one globally representative half-spreading rate, ridge seeds, multi-source Dijkstra unclamped ages with a path witness, the `CONFIGURED_MAXIMUM_AGE_MA = 200.0` ceiling policy, five status codes (`0` not-oceanic-like, `1` ridge seed, `2` ridge reachable, `3` ridge reachable ceiling-clamped, `4` unresolved no-active-ridge-path ceiling; `:17-21`), area-weighted summaries, and the CDF at `CDF_THRESHOLDS_MA = 20…200 step 20`. | `physical_seafloor_creation_resolved`, `spreading_rate_calibrated`, `local_spreading_rates_resolved`, `ridge_flowlines_resolved`, `subduction_sink_history_resolved`, `convergence_history_resolved`, `seton_2020_age_grid_used_as_generation_input` |
| `crust_transport_validation.py` | 2,460 | `tectonics.conservative_crust_overlap_replay` (`:2581`) | Forward spherical destination-CSR overlap (`destination_csr_spherical_forward_overlap_v1`), source-area row closure, coverage multiplicity, transported extensive moments (volume, density-weighted volume, age-volume), gap == overlap excess globally, and the process split. Invokes `validate_crust_process_reason_ledger` at `:827`. | (all five listed `expected` keys are `True`; the non-claims live in `GEO_MODEL_LIMITATIONS`) |
| `crust_process_validation.py` | 1,109 | *(no own check; consumed by `crust_transport_validation.py:827`)* | Ordered crust-rule transitions in `CRUST_PROCESS_REASON_ORDER` — `quiet_oceanic_aging`, `oceanic_ridge_rejuvenation`, `oceanic_ridge_creation_relaxation`, `divergent_continental_rifting`, `oceanic_convergence_subduction_proxy`, `continental_collision_orogeny`, `plate_crossing_accretion_proxy`, `age_bound_enforcement`, `thickness_bound_enforcement`, `density_bound_enforcement` — with per-reason positive/negative/net extensive state-moment deltas accumulated per cell and reduced in ascending cell order. | physical reservoir/material-provenance/energy/phase fluxes (declared in `GEO_MODEL_LIMITATIONS`) |
| `oceanic_age_depth_validation.py` | 1,780 | `tectonics.oceanic_age_depth_thermal_target_replay` (`:2602`) | Continuity-adjusted Parsons–Sclater relative basement subsidence (`350·√age` below the `70.0 Ma` cutoff; `3200 m` exponential scale, `62.8 Ma` e-folding above it) plus continental isostatic equilibrium targets (`500 m` freeboard, `2500 m` ridge reference depth), replayed from round-trip transport/process age, thickness, density, type and lithology; target differences applied outside the bounded dynamic-relief clamp must compose exactly into each tectonic elevation change. `analytical_checkpoint_count: 7`. | `authoritative_for_realized_thermal_relief_component`, `realized_thermal_relief_state_tracked`, `thermal_relaxation_timescale_calibrated`, `unapplied_thermal_tendency_residual_carried_forward`, `absolute_basement_depth_calibrated`, `physical_crust_creation_age_provenance`, `ridge_age_distance_consistency`, `thermal_structure_represented`, `heat_flow_represented`, `dynamic_topography_represented`, `flexure_represented`, `physical_dynamics_represented` |
| `crust_overlap_candidate_fate_validation.py` | 1,140 | `tectonics.overlap_candidate_fate_crosswalk_replay` (`:2648`) | Every same-step unordered boundary plate-pair consensus and every multiplicity ≥ 2 overlap-membership class replays into a **closed** diagnostic overlap-excess partition (`sparse_membership_class_to_uniform_boundary_plate_pair_candidate_v1`). Requires both upstream root replays (boundary + transport) to pass first. Caps: `MAXIMUM_PLATE_COUNT = 256`, `MAXIMUM_MEMBERSHIP_CLASSES_PER_CELL = 16384`. | `candidate_allocation_authoritative`, `local_segment_link_resolved`, `connected_atom_topology_resolved`, `local_fragment_topology_resolved`, `swept_area_calculated`, `crust_material_shadow_mutation_performed`, `crust_reservoir_mutation_performed`, `physical_material_fate_resolved`, `slab_selection_resolved`, `slab_transfer_resolved`, `state_mutation_performed` |
| `crust_material_shadow_validation.py` | 1,616 | `tectonics.persistent_crust_material_shadow_replay` (`:2688`) | Persistent sparse surface-crust dry-rock mass packets (`persistent_sparse_surface_crust_mass_shadow_v1`): normalized overlap advection, ordered rule deltas adding unresolved-origin packets (origin kind id `9`) or removing proportionally; closing packets must match scalar crust mass. 10 origin kinds; `DENSITY_VOLUME_TO_MASS_KG = 1.0e12`. | `physical_source_sink_resolved`, `global_crust_cycle_mass_conservation_resolved` |
| `crust_dry_rock_accounting_validation.py` | 1,341 | `tectonics.finite_crust_dry_rock_accounting_replay` (`:2710`) | Bounded three-reservoir counter-model `finite_three_reservoir_dry_rock_accounting_v1` — surface basement crust (id 0), upper-mantle exchange (id 1), plate-resolved subducted slab (id 2) — with finite exchange inventory (`CAPACITY_THICKNESS_KM = 76.0`, `CAPACITY_DENSITY_G_CM3 = 3.08`), source-normalized transport and ordered rule-derived proxy compensation transactions; global per-origin and per-reservoir accounting must close and subducted-slab tables must be empty. | `physical_source_sink_resolved`, `material_provenance_resolved`, `global_crust_cycle_mass_conservation_resolved` |
| `sediment_source_partition_validation.py` | 619 | `sediment.sediment_alluvium_bedrock_source_partition_replay` (`:2733`) | Hillslope, fluvial and glacial per-cell production demand partitions **alluvium first, bedrock second**; every bulk-volume aggregate reconstructs. Semantics pinned as `bulk_reference_volume_only_not_dry_rock_mass` (`:12-14`). | `dry_rock_mass_claim`, `material_provenance_claim` |
| `sediment_interface_validation.py` | 2,412 | `sediment.bedrock_mobile_sediment_interface_replay` (`:2755`) | Canonical bedrock surface (`explicit_bedrock_surface_mobile_sediment_interface_v1`) replayed from initial terrain + tectonic displacement + bedrock-only erosion + sea-level datum changes, then the independent identity `elevation_m = bedrock_surface_elevation_m + sediment_thickness_m`; all native sediment mutation paths (hillslope, fluvial, glacial, numeric breach) replay. | `dry_rock_mass_resolved`, `porosity_resolved`, `grain_provenance_resolved` |
| `geo_evolution_provenance.py` | 408 | `evolution_provenance.history_family_temporal_semantics` (`:161`) | Registry `geo_evolution_provenance_registry_v2` asserting that all 20 `*_history`/`*_histories` families declare whether they record native state mutation or a post-hoc diagnostic trajectory: 7 native (`plate_motion_history`, `earth_system_feedback_history`, `hydrologic_water_budget_history`, `numeric_depression_correction_history`, `hillslope_sediment_transport_history`, `fluvial_sediment_routing_history`, `glacial_sediment_transport_history`) and 13 diagnostic; family counts and mirrors must match. | `physical_time_resolved: False`, `nominal_time_calibrated: False` on every family, and on the registry root |
| `crust_coverage_geometry_replay.py` | 1,159 | *(none — not wired into either CLI command)* | Independent small-mesh geometric replay of native crust coverage: rotates spherical control volumes, brute-force O(N²) cap pair discovery, gnomonic triangle clipping, destination-local line arrangement for integer coverage multiplicity — never reads the serialized overlap CSR. `DEFAULT_MAX_CELL_COUNT = 1_024` "to prevent this diagnostic implementation from being used accidentally as a production remapper" (`:13-16`). | It is a fixture-scale diagnostic only; referenced solely from `tests/test_crust_coverage_geometry_replay.py` |

`numeric_depression_correction_history` is the one native family whose declared `state_mutation_evidence` is `"mixed"` and whose `temporal_role` is `native_mixed_mutation_and_counterfactual_event_ledger` (`geo_evolution_provenance.py:36-42`, `:248-256`).

---

## Profiles and the earthlike regime gates

Exactly two profiles exist. The CLI hand-validates the value at `validate_geo.py:50-52` and exits `2` on anything else; the library also emits a failing `contract.known_validation_profile` check rather than raising (`geo_validation.py:2730-2739`).

| Profile | Effect |
|---|---|
| `generic` (default) | No additional checks. All structural, replay, subsystem and realism-evidence checks run. |
| `earthlike` | Adds 10 checks in domain `earthlike_profile` via `_validate_earthlike_profile` (`geo_validation.py:764`). |

The 10 `earthlike` gates, all error-severity, all evaluated against `extract_geo_metrics` output (`geo_validation.py:768-800`):

| Check name (`earthlike_profile.*`) | Minimum | Maximum | Message |
|---|---|---|---|
| `ocean_fraction` | 0.55 | 0.85 | Earth-like `<metric>` must fall in the declared broad validation envelope |
| `global_mean_temperature_c` | 8.0 | 22.0 | " |
| `mean_land_precipitation_mm_y` | 350.0 | 1800.0 | " |
| `elevation_span_m` | 8000.0 | 25000.0 | " |
| `river_cell_fraction` | 0.002 | 0.08 | " |
| `ice_cell_fraction` | 0.005 | 0.45 | " |
| `calibration_pass_fraction` | 0.75 | 1.0 | " |
| `realism_evidence_coverage_fraction` | 0.65 | 1.0 | " |
| `applicable_realism_pass_fraction` | 0.75 | 1.0 | " |
| `biome_diversity` | 6 classes | — | Earth-like worlds need multiple climate-linked biome classes |

A non-finite or missing metric fails the gate (the predicate is `numeric and lower <= float(value) <= upper`). These are deliberately *broad regime* envelopes, not calibration: the report's own limitation list ends with "Earth empirical fit remains a separate calibration verdict from internal contract integrity". A world can pass all 10 gates and still fail external dataset calibration, and vice versa.

Observed behavior on the 512-cell smoke world (small mesh, few realism candidates):

```
$ magic-geo validate-geo --world geo.json
OK geo | checks=150 errors=0 warnings=0 not_applicable=3

$ magic-geo validate-geo --world geo.json --profile earthlike
FAIL geo | checks=160 errors=1 warnings=0 not_applicable=3
FAIL earthlike_profile.calibration_pass_fraction: Earth-like calibration_pass_fraction must fall in the declared broad validation envelope
```

---

## Exit codes and policy semantics

### `validate-geo`

Policy is computed in the CLI, not the library (`validate_geo.py:55-65`):

```python
failed_checks = [
    check for check in report["checks"]
    if check["status"] == "failed"
    and (check["severity"] == "error" or fail_on_warnings)
]
policy_passed = bool(report["passed"]) and not failed_checks
report["requested_policy"] = {"fail_on_warnings": fail_on_warnings, "policy_passed": policy_passed}
```

Because `report["passed"]` already folds in `all_layer_contracts_passed`, a layer-contract failure alone is enough to fail the command even when every individual check passed.

| Flag | Default | Effect |
|---|---|---|
| `--allow-warnings` | on | Failed `realism_evidence` checks are reported but non-fatal. |
| `--fail-on-warnings` | off | Failed `realism_evidence` checks become fatal. `not_applicable` checks are **never** promoted — only `status == "failed"` is considered. |

| Condition | Exit | Stream |
|---|---|---|
| `policy_passed` true | 0 | `OK geo | checks=… errors=… warnings=… not_applicable=…` on stdout |
| `policy_passed` false | 1 | same summary line with `FAIL`, plus `FAIL <domain>.<name>: <message>` per failed check and `FAIL layer_contract.<id>: required artifacts, validation domains, or dependencies failed` per failed layer, all on stderr |
| `--profile` not in `{generic, earthlike}` | 2 | `--profile must be generic or earthlike` on stderr |
| World file unreadable or invalid | 2 | `Invalid world file: <exc>` on stderr (`_app.py:22`) |

The report is written *before* the nonzero exit when `--output` is given (`validate_geo.py:66-67`), so a failing run still produces a full artifact.

### `validate`

| Condition | Exit | Stream |
|---|---|---|
| No failures | 0 | `OK` on stdout |
| Early gate: schema version ≠ 2, retired fields present, or invalid planet parameters | 1 | `FAIL <message>` per failure on stderr, then immediate exit — **all other diagnostics are masked** |
| Final gate: any accumulated failure | 1 | `FAIL <message>` per failure on stderr |
| World file unreadable or invalid | 2 | `Invalid world file: <exc>` on stderr |

There is no `--output`, no per-domain enable/disable flag, and no severity policy switch: every failure is fatal.

---

## Reading and triaging a failing report

### 1. Read the verdict line first

```
FAIL geo | checks=160 errors=1 warnings=0 not_applicable=3
```

`errors` is the only count that can fail the default policy. `not_applicable` is neither good nor bad on its own — it means an invariant had no eligible evidence in this world.

### 2. Separate the three failure classes

There are three structurally different reasons `validate-geo` can fail, and they need different responses:

| Class | How to spot it | What it means |
|---|---|---|
| Contract/structural failure | A `contract.*` or `mesh.*` failure, especially `world_schema_version`, `cell_payload_available`, `unique_cell_ids` | The world is stale, truncated, or generated with `output.include_cells=false`. Several of these short-circuit the whole report — fix them first, everything downstream is unreliable. |
| Replay failure | A `*_replay` check name with a populated `evidence.violations` array | An independent reconstruction disagreed with the serialized ledger. The violation strings name the exact field and index. |
| Layer-contract failure | `FAIL layer_contract.<id>` lines with no matching check failure | Usually a *missing required output* or a *missing validator domain*, not a bad value. Inspect `missing_or_invalid_outputs` and `missing_validation_domains`. |

### 3. Triage with `jq`

```bash
magic-geo validate-geo --world runs/world.json --profile earthlike -o runs/geo-report.json

# every fatal failure, most useful fields only
jq '[.checks[] | select(.status=="failed" and .severity=="error")
     | {domain, name, message, observed, expected}]' runs/geo-report.json

# non-fatal realism deviations
jq '[.checks[] | select(.status=="failed" and .severity=="warning") | {name, observed, expected}]' \
   runs/geo-report.json

# which realism claims had no eligible evidence, and why
jq '[.checks[] | select(.status=="not_applicable") | {name, evidence}]' runs/geo-report.json

# the exact violation strings from a replay check
jq '.checks[] | select(.name=="conservative_crust_overlap_replay") | .evidence.violations' \
   runs/geo-report.json

# what a replay check does NOT claim (always read this before acting on a replay result)
jq '.checks[] | select(.name=="oceanic_age_depth_thermal_target_replay")
    | .expected | with_entries(select(.value == false))' runs/geo-report.json

# domains ranked by failure count
jq '.summary.domains | to_entries | map(select(.value.failed_count > 0))
    | sort_by(-.value.failed_count)' runs/geo-report.json

# failing layers with the reason
jq '[.layer_contracts.layers[] | select(.contract_passed == false)
     | {id, phase, missing_or_invalid_outputs, missing_validation_domains,
        failed_dependencies, failed_check_names}]' runs/geo-report.json

# declared model limitations, always worth re-reading before drawing conclusions
jq -r '.model_limitations[]' runs/geo-report.json
```

### 4. Follow the dependency cascade before fixing anything

Layer contracts are evaluated in phase order and each one ANDs in `failed_dependencies` (`geo_layer_contracts.py:391-395`). One phase-0 failure cascades into all 14 layers. A run against a stale world produced exactly that pattern: three `contract.*` failures plus assorted replay failures, and *all fourteen* `layer_contract.*` lines. Fix the lowest failing phase first and re-run; do not triage phase 13 while phase 0 is red.

The same ordering exists inside the replay family. `crust_overlap_candidate_fate_validation` requires **both** `validate_plate_boundary_edges` and `validate_crust_overlap_transport` to pass first, so `overlap_candidate_fate_crosswalk_replay` failing alongside its two roots is one bug, not three.

### 5. Watch the two `passed` fields

- `check["passed"]` is `True` **only** when `status == "passed"`. A `not_applicable` record has `passed: false`. Filtering on `passed == false` will sweep in every non-applicable check.
- `report["passed"]` is *not* just "no failed checks" — it is `no error-severity failures AND all_layer_contracts_passed`.
- `report["requested_policy"]["policy_passed"]` is the value the CLI actually exited on, and it exists only when the report came from the CLI.

### 6. Cross-check `validate` when `validate-geo` is clean

A geo-clean world can still fail `validate` on civilization layers, and a `validate`-clean world can still fail `validate-geo`'s earthlike regime gates. They are independent verdicts by construction. Run both.

---

## Limitations and unresolved claims

These are the codebase's own declarations, not editorial hedging. The full 12-entry list is `GEO_MODEL_LIMITATIONS` (`src/magic_geo/geo_validation.py:28-41`) and is embedded verbatim in every geo report.

- **A passing report is not a realism claim.** The layer-contract audit states it directly: a passing contract "proves artifact, validator-domain, dependency, and assigned fatal-check integrity; it does not prove empirical realism or physical time calibration" (`geo_layer_contracts.py:442-446`). Every layer carries `empirical_realism_proven: false`.
- **Physical time is unresolved.** "the simulation clock orders procedural stages but has no calibrated physical duration". The nominal-time record schema requires `nominal_time_calibrated is False` and `physical_time_resolved is False` on every native history record (`cli/validators/_shared.py:34-35`, `geo_evolution_provenance.py:174-180`). `coupled_stage_feedback_replay` declares `"physical_time_and_convergence_claims": False`.
- **Subduction polarity is explicitly unknown.** The boundary-segment replay reconstructs candidate sides but declares `subduction_polarity_resolved: False` and `subducted_slab_geometry_resolved: False`. The candidate-fate crosswalk "may reflect independently validated upstream physical polarity but cannot originate or promote it".
- **Mass provenance is unresolved.** The crust material shadow and the three-reservoir dry-rock counter-model both declare `physical_source_sink_resolved: False` and `global_crust_cycle_mass_conservation_resolved: False`; the accounting model additionally declares `material_provenance_resolved: False`. Sediment source partitions declare `dry_rock_mass_claim: False` and `material_provenance_claim: False`, with semantics pinned to `bulk_reference_volume_only_not_dry_rock_mass`.
- **Accelerator parity is unresolved.** "first-order conservative crust overlap is diffusive, CPU-authoritative, and guarded by a 16,384-fragment local arrangement cap without exhaustive worst-case proof; an accelerator may validate and discard only a continuous-moment CSR shadow, while geometry, categories, production state, complete parity, and device-lane evidence remain unresolved".
- **Oceanic crust age is procedural, not physical.** "initial oceanic-like crust age is a replayable multi-source ridge-distance graph field using one globally averaged nominal half-spreading rate; it does not reconstruct local flowlines, calibrated spreading, subduction sinks, convergence history, or physical seafloor creation and destruction". The check further declares `seton_2020_age_grid_used_as_generation_input: False` — the Seton grid is a calibration witness, never an input.
- **Parsons–Sclater is a relative target curve only.** Authoritative for "a relative oceanic thermal-subsidence target curve"; not a calibrated transient relaxation, and it does not separately track realized thermal relief or resolve absolute basement depth, heat flow, thermal structure, dynamic topography, flexure, or physical dynamics.
- **The bedrock/sediment interface is geometric, not material.** Bulk reference-volume closure "still does not resolve dry-rock mass, sediment density, porosity, compaction, grain provenance, or chemical weathering".
- **The atmosphere and water inventory are diagnostic.** "the diagnostic atmosphere is not a three-dimensional mass-conserving circulation solver"; "configured ocean inventory is not a closed total-water partition across ocean, ice, groundwater, lakes, and atmosphere".
- **Ecosystem, species, wildfire and resource layers "are diagnostic index models rather than calibrated population or process solvers."**
- **Empirical fit is a separate verdict.** "Earth empirical fit remains a separate calibration verdict from internal contract integrity". `earth_calibration.built_in_calibration_integrity` only checks that the *built-in* 12-metric comparison record set is internally consistent; it does not evaluate against external datasets.
- **A perfect realism score is not evidence.** By design, `not_applicable` replaces a vacuous pass whenever the candidate population is below the declared minimum. Treat `realism_evidence_coverage_fraction` as the gate on whether the realism verdict means anything at all.
- **Timestep convergence is unproven.** Phase 13's declared evidence class is `cross_layer_replay_with_unproven_timestep_convergence_and_no_physical_calibration`.
- **`crust_coverage_geometry_replay.py` is a fixture-scale diagnostic**, bounded to 1,024 cells by default and not wired into either CLI command; it is exercised only from the test suite.
- **Not verified in source:** whether the report-writing `inf` serialization error observed on a stale world is intended containment behavior or a defect. It was reproduced but not traced to an explicit design decision.

---

## See also

- [CLI Reference](./06-cli-reference.md) — full option tables and exit codes for every command
- [Geo Validation Suite](./13-geo-validation-suite.md) — `validate-geo-suite`, the scenario matrix, paired relations and determinism fingerprints
- [Calibration Against Real-Earth Data](./14-calibration.md) — `calibrate`, `derive-targets`, `calibrate-ensemble` and the external empirical verdict
- [Testing and Quality Gates](./18-testing.md) — the native and Python test suites behind these validators
- [World Document Schema](./10-world-schema.md) — the keys each contract requires
- [Architecture](./04-architecture.md) — where validation sits in the pipeline
- [Python API](./07-python-api.md) — calling `validate_geo_world`, `extract_geo_metrics` and the replay validators directly
- [Troubleshooting and FAQ](./22-troubleshooting.md) — common validation failures
- [Tectonics and Plates](./features/tectonics-and-plates.md), [Plate Boundary Segment Ledger](./features/plate-boundary-ledger.md), [Crust Transport and Forward Overlap](./features/crust-transport-and-overlap.md), [Crust Material Shadow and Dry-Rock Reservoirs](./features/crust-material-and-reservoirs.md) — the subsystems the tectonics replays reconstruct
- [Sediment, Routing and Stratigraphy](./features/sediment-and-stratigraphy.md), [Erosion, Maturation and Landscape Evolution](./features/erosion-and-maturation.md) — the subsystems the sediment replays reconstruct
- [Glossary](./21-glossary.md) — `not_applicable`, layer contract, replay, shadow, counter-model
