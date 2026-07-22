# Erosion, Maturation and Landscape Evolution

[Wiki home](../README.md) > Features

The maturation loop is the coupled tectonics-climate-hydrology-erosion transition engine of magic-geo. It runs `erosion.iterations` transitions inside `magic_geo::detail::erode` (`cpp/src/engine/earth_system.cpp:914`), each of which advances plate motion and crust state, evaluates tectonic, hillslope and stream-power tendencies against the *prior stabilized* surface and flow graph, commits all three through one checked material-update primitive per cell, and then re-stabilizes sea level, climate, the water budget, drainage and numeric depressions. Everything on this page is deliberately expressed on a **nominal** geological coordinate: the document exports `physical_time_resolved`, `process_rate_calibration_resolved` and `time_step_convergence_demonstrated` as `false`, and this page never upgrades those claims.

## On this page

- [Source map](#source-map)
- [The maturation coordinator and the nominal timestep](#the-maturation-coordinator-and-the-nominal-timestep)
- [Exactly which responses are timestep-scaled](#exactly-which-responses-are-timestep-scaled)
- [The stage and iteration model](#the-stage-and-iteration-model)
- [Ordering inside one maturation transition](#ordering-inside-one-maturation-transition)
- [Stream-power incision](#stream-power-incision)
- [Hillslope diffusion](#hillslope-diffusion)
- [Tectonic uplift scaling](#tectonic-uplift-scaling)
- [The shared material-update primitive](#the-shared-material-update-primitive)
- [The combined terrain commit and source partition](#the-combined-terrain-commit-and-source-partition)
- [Fluvial routing inside the transition](#fluvial-routing-inside-the-transition)
- [The coupled stage ledger and feedback summaries](#the-coupled-stage-ledger-and-feedback-summaries)
- [The geo evolution provenance enricher](#the-geo-evolution-provenance-enricher)
- [Erosion configuration reference](#erosion-configuration-reference)
- [Worked examples](#worked-examples)
- [Failure modes and native guards](#failure-modes-and-native-guards)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

## Source map

| Concern | File | Key symbols / lines |
| --- | --- | --- |
| Maturation loop coordinator | `cpp/src/engine/earth_system.cpp` | `erode` at `:914`, per-iteration body `:928`–`:1148` |
| Hillslope transport | `cpp/src/engine/earth_system.cpp` | `transport_hillslope_sediment` at `:289`–`:446` |
| Fluvial routing | `cpp/src/engine/earth_system.cpp` | `route_fluvial_sediment` at `:448`–`:912` |
| Feedback snapshots / summaries | `cpp/src/engine/earth_system.cpp` | `capture_feedback_reference` `:5`, `summarize_feedback_step` `:20`–`:287` |
| Nominal timestep scale | `cpp/src/engine/core.cpp` | `maturation_timestep_scale` `:44`–`:47`, `timestep_scaled_fraction` `:49`–`:65` |
| Reference step and process constants | `cpp/src/engine/constants.hpp` | `MATURATION_REFERENCE_TIMESTEP_MA` `:72`, `HILLSLOPE_MAX_EFFECTIVE_DIFFUSIVITY` `:66`, fluvial fractions `:59`–`:65` |
| Material-update primitive | `cpp/src/engine/sediment_partition.cpp` | `apply_sediment_interface_material_change` `:155`–`:230` |
| Source-partition audit | `cpp/src/engine/sediment_partition.cpp` | `validate_sediment_source_partition` `:262`–`:378` |
| Tectonic tendency and uplift | `cpp/src/engine/tectonics.cpp` | `advance_plate_motion_and_crust` `:1050`, uplift/dynamic relief `:1611`–`:1646` |
| Erodability by lithology | `cpp/src/engine/tectonics.cpp` | `lithology_resistance` `:204`–`:215` |
| Loop placement in the pipeline | `cpp/src/engine/pipeline.cpp` | `erode(...)` `:135`–`:147`, terminal cryosphere block `:149`–`:184` |
| Clock and ledger serialization | `cpp/src/engine/process_serialization.cpp` | nominal-time helpers `:46`–`:160`, `simulation_clock_json` `:2056`, feedback history `:2139` |
| Config schema | `src/magic_geo/config.py` | `ErosionConfig` `:371`–`:417` |
| Native parameter validation | `cpp/src/engine/core.cpp` | erosion bounds `:388`–`:425` |
| Provenance enricher | `src/magic_geo/geo_evolution_provenance.py` | whole module |

## The maturation coordinator and the nominal timestep

`erosion.maturation_timestep_ma` is a **nominal refinement interval measured against a shipped reference step**, not a physical integration timestep. The reference is fixed in source:

```cpp
// cpp/src/engine/constants.hpp:68-72
// Existing per-step coefficients are reference-normalized to the shipped 5 Ma
// crust-aging setting. Other nominal timesteps scale continuous mutations
// against this reference so temporal refinement changes resolution rather than
// only the number of process applications. This is not physical calibration.
constexpr double MATURATION_REFERENCE_TIMESTEP_MA = 5.0;
```

The single conversion used everywhere is:

```cpp
// cpp/src/engine/core.cpp:44-47
double maturation_timestep_scale(const Params& params) {
    return params.maturation_timestep_ma /
        MATURATION_REFERENCE_TIMESTEP_MA;
}
```

| Quantity | Symbol used below | Definition | Source |
| --- | --- | --- | --- |
| Reference step | `reference_timestep_ma` | `5.0` Ma, compile-time constant | `cpp/src/engine/constants.hpp:72` |
| Nominal step | `nominal_timestep_ma` | `erosion.maturation_timestep_ma`, `0 < v <= 5.0` | `src/magic_geo/config.py:382`, `cpp/src/engine/core.cpp:388` |
| Timestep scale | `maturation_timestep_scale` | `nominal_timestep_ma / 5.0`, so always in `(0, 1]` | `cpp/src/engine/core.cpp:44` |

Because the config caps `maturation_timestep_ma` at `5.0` (`config.py:382`) and the native validator repeats the same bound (`core.cpp:388-389`, message `maturation_timestep_ma must be greater than 0 and at most 5`), the scale can only *refine* below the reference, never coarsen above it.

A second helper exists for quantities that are **bounded fractions** rather than linear rates, so that repeated application over a refined step composes correctly instead of over-applying:

```cpp
// cpp/src/engine/core.cpp:49-65
double timestep_scaled_fraction(double reference_fraction, double timestep_scale) {
    const double bounded_fraction = clamp(reference_fraction, 0.0, 1.0);
    const double bounded_scale = std::max(0.0, timestep_scale);
    if (bounded_fraction <= 0.0 || bounded_scale <= 0.0) { return 0.0; }
    if (bounded_scale == 1.0) { return bounded_fraction; }
    if (bounded_fraction >= 1.0) { return 1.0; }
    return -std::expm1(bounded_scale * std::log1p(-bounded_fraction));
}
```

This is `1 - (1 - f)^scale`, i.e. the survival-fraction composition of a per-reference-step fractional change. It is used by the crust-state rules in `cpp/src/engine/tectonics.cpp` (for example `:1347`–`:1352`, `:1383`–`:1385`, `:1432`–`:1434`); it is *not* used by the erosion tendencies described on this page, which are linear in the scale.

The engine README states the coordinator contract directly (`cpp/src/engine/README.md:104-113`): the coordinator "treats `Params::maturation_timestep_ma` as a nominal refinement interval relative to the shipped 5 Ma reference step", "selected continuous reference-step responses are scaled", "authoritative histories carry nominal start/end/duration metadata", "the terminal cryosphere pass remains a zero-duration endpoint operator", and "exported metadata explicitly keeps physical time, process-rate calibration, and whole-coupling timestep convergence false".

## Exactly which responses are timestep-scaled

`maturation_timestep_scale` is applied at exactly the following sites. Nothing else in the maturation loop multiplies by it.

| Response | Formula site | Scaling applied | Notes |
| --- | --- | --- | --- |
| Plate rotation per transition | `cpp/src/engine/tectonics.cpp:1127-1128` | `angular_speed * plate_motion_scale_deg_per_step * scale` | Linear; exported as `plate_kinematic_model.effective_motion_scale_deg_per_step` (`process_serialization.cpp:2710`) |
| Quiet oceanic crust aging | `cpp/src/engine/tectonics.cpp:1329-1330` | `oceanic_crust_aging_ma_per_step * scale * quiet_fraction` | Linear; exported as `effective_oceanic_crust_aging_ma_per_step` (`process_serialization.cpp:2716`) |
| Bounded crust-rule fractions (rejuvenation, rifting, subduction proxy, orogeny …) | `cpp/src/engine/tectonics.cpp:1347`–`:1468` | `timestep_scaled_fraction(reference_fraction, scale)` and linear `* scale` terms | Mixed linear / survival-fraction composition; see [Tectonics and Plates](tectonics-and-plates.md) |
| Tectonic uplift rate index (`cell.uplift_rate`) | `cpp/src/engine/tectonics.cpp:1611-1613` (and initial state `:502-504`) | `tectonic_uplift_scale * tectonic_activity * (…) * scale` | Linear; serialized per cell as `tectonic_uplift_rate_m_per_step` |
| Hillslope effective diffusivity | `cpp/src/engine/earth_system.cpp:358-363` | `hillslope_diffusion * scale / lithology_resistance`, then `min(0.45, …)` | Linear before the stability cap |
| Applied stream incision depth | `cpp/src/engine/earth_system.cpp:986-987` | `erosion_depth_m = stream * scale` | Linear; **only the applied depth** is scaled |
| Exported stream-power response (`cell.erosion_rate`) | `cpp/src/engine/earth_system.cpp:993` | **not scaled** | Deliberately left at the 5 Ma reference response |
| Isostatic / thermal equilibrium target differences | `cpp/src/engine/tectonics.cpp:1618-1631` | **not scaled** | Gain-1 quasi-static application; see [Topography, Isostasy and Thermal Subsidence](topography-and-isostasy.md) |
| Boundary-forcing change term of dynamic relief | `cpp/src/engine/tectonics.cpp:1614-1617` | **not scaled** | `80*Δconv + 55*Δdiv - 30*Δtrans` is a per-transition difference |
| Fluvial routing partition fractions | `cpp/src/engine/earth_system.cpp:636-676` | **not scaled** | `fluvial_sediment_routing_model.routing_partition_fractions_timestep_invariant = true` (`process_serialization.cpp:1481`) |
| Climate, water budget, hydrology, sea level | `climate.cpp`, `hydrology.cpp`, `ocean.cpp` | **not scaled** | No call to `maturation_timestep_scale` exists in these translation units |
| Cryosphere and glacial transport | `cpp/src/engine/environment.cpp` | **not scaled** | Zero-duration endpoint operator; `simulation_clock.cryosphere_advances_nominal_time = false` (`process_serialization.cpp:2117`) |

The comment on the incision site states the intent verbatim:

```cpp
// cpp/src/engine/earth_system.cpp:988-992
// Preserve the exported erosion-rate signal as the 5 Ma reference
// response used by downstream diagnostics. Only the applied
// incision/source depth is integrated over the configured nominal
// transition. Otherwise merely refining dt changes soils,
// ecosystems, land use, and resource diagnostics by construction.
```

The document self-describes this split with `simulation_clock.cell_erosion_rate_semantics = "stream_power_response_per_reference_step_not_applied_transition_depth"` and `simulation_clock.stream_incision_update = "cell_erosion_rate_times_maturation_timestep_scale"` (`cpp/src/engine/process_serialization.cpp:2097-2100`). The plate kinematic model labels the whole arrangement `timestep_scaling_model = "reference_normalized_partial_process_scaling_v1"` (`process_serialization.cpp:2703-2704`) and its `model_limitation` explicitly contains `partial_reference_timestep_scaling_and_uncalibrated_physical_time` (`process_serialization.cpp:2939-2940`).

## The stage and iteration model

The loop produces one **feedback stage** per transition, bracketed by an initial snapshot and a terminal cryosphere coupling stage.

| Feedback stage `id` | `stage` string | `erosion_iteration` | Produced by | Nominal role |
| --- | --- | --- | --- | --- |
| `0` | `initial_climate_hydrology` | `-1` | `cpp/src/engine/pipeline.cpp:117-133` | `initial_state_snapshot` |
| `1 … erosion_iterations` | `erosion_iteration` | `1 … erosion_iterations` | `cpp/src/engine/earth_system.cpp:1131-1147` | `erosion_transition` |
| `erosion_iterations + 1` | `cryosphere_coupling` | `-1` | `cpp/src/engine/pipeline.cpp:168-184` | `final_cryosphere_coupling_snapshot` |

With the shipped default `erosion.iterations = 6` (`src/magic_geo/config.py:376`) that is 8 records in `earth_system_feedback_history`. With `erosion.iterations = 0` the loop body never executes and only the two bracketing records exist.

Nominal-time placement is computed by three helpers in `cpp/src/engine/process_serialization.cpp`:

| Helper | Lines | Behavior |
| --- | --- | --- |
| `nominal_elapsed_time_ma` | `:46`–`:54` | `maturation_timestep_ma * transition_count`; throws if `transition_count` is outside `[0, erosion_iterations]` |
| `nominal_erosion_interval` | `:56`–`:69` | `[elapsed(i-1), elapsed(i)]` for erosion iteration `i`; throws for `i <= 0` or `i > erosion_iterations` |
| `nominal_feedback_interval` | `:87`–`:115` | `{0,0}` for the initial snapshot, the erosion interval for `erosion_iteration` stages, `{T, T}` for the terminal cryosphere stage where `T = elapsed(erosion_iterations)`; throws otherwise |

Every record in the seven native mutation ledgers then carries a 12-field nominal-time block emitted by `add_nominal_time_fields` (`cpp/src/engine/process_serialization.cpp:135-160`), immediately after the record's id/stage/iteration prefix, at `max_digits10` precision:

| Field | Type | Value |
| --- | --- | --- |
| `nominal_time_model` | string | `configured_maturation_timestep_nominal_elapsed_time_v1` |
| `nominal_time_unit` | string | `Ma` |
| `nominal_time_basis` | string | `configured_maturation_timestep_ma_per_erosion_transition_v1` |
| `nominal_time_source_parameter` | string | `erosion.maturation_timestep_ma` |
| `nominal_time_role` | string | `initial_state_snapshot` / `erosion_transition` / `final_cryosphere_coupling_snapshot` (feedback history) |
| `nominal_interval_start_ma` | double | interval start |
| `nominal_interval_end_ma` | double | interval end |
| `nominal_interval_duration_ma` | double | `end - start` |
| `nominal_elapsed_time_ma` | double | equals `nominal_interval_end_ma` |
| `advances_nominal_time` | bool | `duration_ma > 0.0` |
| `nominal_time_calibrated` | bool | always `false` |
| `physical_time_resolved` | bool | always `false` |

The world-level `simulation_clock` object (`cpp/src/engine/process_serialization.cpp:2056-2137`) carries the coordinator contract:

| Key | Type | Value / source |
| --- | --- | --- |
| `clock_type` | string | `coupled_geodynamic_stage_clock_v12` |
| `time_unit` | string | `model_step` |
| `physical_time_resolved` | bool | `false` |
| `nominal_time_calibrated` | bool | `false` |
| `absolute_geological_age_resolved` | bool | `false` |
| `process_rate_calibration_resolved` | bool | `false` |
| `time_step_convergence_demonstrated` | bool | `false` |
| `clock_limitation` | string | `nominal_geological_intervals_without_calibrated_physical_time_or_timestep_convergence` |
| `nominal_time_model` / `_unit` / `_basis` / `_source_parameter` | string | mirrors the block above |
| `nominal_time_direction` | string | `forward_from_initial_generated_state` |
| `cell_erosion_rate_semantics` | string | `stream_power_response_per_reference_step_not_applied_transition_depth` |
| `stream_incision_update` | string | `cell_erosion_rate_times_maturation_timestep_scale` |
| `erosion_transition_coupling_semantics` | string | `hillslope_and_stream_use_prior_stabilized_surface_and_hydrology_with_updated_crust_state;tectonic_hillslope_stream_tendencies_are_combined_before_terrain_commit;fluvial_routing_uses_prior_flow_graph_and_provisional_terrain_accommodation` |
| `nominal_timestep_ma` | double | `erosion.maturation_timestep_ma` |
| `reference_timestep_ma` | double | `5.0` |
| `maturation_timestep_scale` | double | `nominal / 5.0` |
| `nominal_timed_transition_count` | int | `erosion_iterations` |
| `initial_nominal_elapsed_time_ma` | double | `0.0` |
| `current_nominal_elapsed_time_ma` / `final_nominal_elapsed_time_ma` | double | `maturation_timestep_ma * erosion_iterations` |
| `cryosphere_advances_nominal_time` | bool | `false` |
| `iteration_process_order` | string | the full ordering string quoted in the next section |
| `geological_age_ga` | double | `planet.geological_age_ga` |
| `configured_erosion_iteration_count` | int | `erosion_iterations` |
| `configured_cryosphere_coupling_stage_count` | int | literal `1` |
| `cryosphere_coupling_stage_count` | int | observed count of `cryosphere_applied` stages |
| `feedback_recompute_count` | int | stages where erosion-or-cryosphere applied **and** all four of sea level, climate, water budget, hydrology recomputed |
| `hydrologic_water_budget_recompute_count` | int | summed over stages |
| `stage_count`, `initial_stage_id`, `current_stage_id`, `final_stage_id`, `final_cryosphere_stage_id` | int | derived from `feedback_history` |

Mirrored counters also appear in `summary` (`cpp/src/engine/summary.cpp:1368-1377`): `simulation_clock_stage_count`, `simulation_clock_erosion_iteration_count`, `simulation_clock_cryosphere_coupling_stage_count`, `simulation_clock_sea_level_recompute_count`, `simulation_clock_climate_recompute_count`, `simulation_clock_hydrologic_water_budget_recompute_count`, `simulation_clock_hydrology_recompute_count`.

### What one maturation stage record contains

A **maturation stage record** is one element of `earth_system_feedback_history` (`cpp/src/engine/process_serialization.cpp:2139-2408`, built by `summarize_feedback_step` at `earth_system.cpp:20`). Field groups, in emission order:

| Group | Fields |
| --- | --- |
| Identity | `id`, `stage`, `erosion_iteration` |
| Nominal time | the 12-field block above |
| Applied-process flags | `sea_level_recomputed`, `climate_recomputed`, `hydrologic_water_budget_recomputed`, `hydrology_recomputed`, `erosion_applied`, `cryosphere_applied`, `plate_motion_applied`, `crust_transport_applied`, `crust_evolution_applied` |
| Stabilization counters | `sea_level_recompute_count`, `climate_recompute_count`, `hydrologic_water_budget_recompute_count`, `hydrology_recompute_count`, `numeric_depression_correction_pass_count`, `numeric_depression_correction_event_count`, `numeric_depression_breach_selected_event_count`, `numeric_depression_breach_excavation_cell_application_count`, `numeric_depression_breach_deposition_cell_application_count`, `numeric_depression_temporary_lake_event_count`, `numeric_depression_temporary_lake_cell_application_count`, `numeric_depression_temporary_lake_unique_cell_count` |
| Fluvial counters | `fluvial_sediment_active_cell_step_count`, `fluvial_sediment_routed_edge_count`, `fluvial_sediment_land_terminal_count`, `fluvial_sediment_marine_terminal_count`, `fluvial_sediment_terminal_allocation_count` |
| Hillslope counters | `hillslope_sediment_transport_edge_count`, `hillslope_sediment_source_cell_count`, `hillslope_sediment_target_cell_count`, `hillslope_sediment_land_to_land_edge_count`, `hillslope_sediment_land_to_marine_edge_count` |
| Glacial counters | `glacial_sediment_transfer_count`, `glacial_sediment_source_cell_count`, `glacial_sediment_target_cell_count`, `glacial_sediment_land_target_transfer_count`, `glacial_sediment_marine_target_transfer_count` |
| Linkage / geometry | `plate_motion_history_id`, `cell_count`, `land_cell_count`, `water_cell_count`, `river_cell_count`, `sea_level_adjustment_m` |
| Numeric-depression volumes | `numeric_depression_breach_excavation_volume_km3`, `numeric_depression_breach_deposition_volume_km3`, `numeric_depression_correction_mass_balance_residual_km3`, `numeric_depression_temporary_lake_candidate_area_km2`, `numeric_depression_temporary_lake_candidate_volume_km3`, `max_numeric_depression_temporary_lake_depth_m` |
| Fluvial volumes | `fluvial_sediment_local_source_volume_km3`, `fluvial_sediment_routed_throughput_volume_km3`, `fluvial_sediment_capacity_deposition_volume_km3`, `fluvial_sediment_depression_fill_deposition_volume_km3`, `fluvial_sediment_lake_trap_deposition_volume_km3`, `fluvial_sediment_terminal_land_deposition_volume_km3`, `fluvial_sediment_marine_deposition_volume_km3`, `fluvial_sediment_terminal_export_volume_km3`, `fluvial_sediment_mass_balance_residual_km3` |
| Hillslope volumes | `hillslope_sediment_production_volume_km3`, `hillslope_sediment_deposition_volume_km3`, `hillslope_sediment_mass_balance_residual_km3`, `max_hillslope_sediment_source_production_depth_m`, `max_hillslope_sediment_target_deposition_depth_m`, `mean_hillslope_effective_diffusivity` |
| Glacial volumes | `glacial_sediment_production_volume_km3`, `glacial_sediment_deposition_volume_km3`, `glacial_sediment_mass_balance_residual_km3`, `glacial_sediment_terrain_volume_change_residual_km3`, `max_glacial_sediment_source_production_depth_m`, `max_glacial_sediment_target_deposition_depth_m` |
| Sediment inventory | `sediment_alluvium_entrainment_volume_km3`, `sediment_bedrock_erosion_volume_km3`, `sediment_inventory_volume_km3`, `sediment_source_partition_residual_km3`, `sediment_inventory_mass_balance_residual_km3` |
| State aggregates | `surface_area_km2`, `ocean_area_km2`, `ocean_volume_km3`, `ocean_fraction`, `mean_elevation_m`, `mean_land_elevation_m`, `min_elevation_m`, `max_elevation_m`, `mean_temperature_c`, `mean_precipitation_mm_y`, `mean_runoff_mm_y` |
| Water budget | `hydrologic_land_precipitation_volume_km3_y`, `hydrologic_actual_evapotranspiration_volume_km3_y`, `hydrologic_infiltration_volume_km3_y`, `hydrologic_runoff_volume_km3_y`, `hydrologic_water_budget_residual_km3_y`, `max_abs_hydrologic_water_budget_cell_residual_mm_y` |
| Erosion / sediment means | `mean_stream_power_response_m_per_reference_step`, `mean_sediment_thickness_m`, `mean_cumulative_sediment_production_m`, `mean_cumulative_sediment_deposition_m`, `mean_cumulative_sediment_export_m`, `cumulative_sediment_production_volume_km3`, `cumulative_sediment_deposition_volume_km3`, `cumulative_sediment_export_volume_km3` |
| Stage-to-stage deltas | `mean_abs_elevation_change_m_from_previous_stage`, `mean_abs_temperature_change_c_from_previous_stage`, `mean_abs_precipitation_change_mm_y_from_previous_stage`, `mean_abs_runoff_change_mm_y_from_previous_stage` |

Flag values by stage kind (from the call sites):

| Stage | `erosion_applied` | `cryosphere_applied` | `plate_motion_applied` | `crust_transport_applied` | `crust_evolution_applied` | Source |
| --- | --- | --- | --- | --- | --- | --- |
| `initial_climate_hydrology` | `false` | `false` | `false` | `false` | `false` | `cpp/src/engine/pipeline.cpp:126-130` |
| `erosion_iteration` | `true` | `false` | `true` | `true` | `true` | `cpp/src/engine/earth_system.cpp:1140-1144` |
| `cryosphere_coupling` | `false` | `true` | `false` | `false` | `false` | `cpp/src/engine/pipeline.cpp:177-181` |

## Ordering inside one maturation transition

The exported ordering string (`simulation_clock.iteration_process_order`, `cpp/src/engine/process_serialization.cpp:2119`) is authoritative. It is emitted as a single unbroken line; the wrapping below is presentational only:

```text
{plate_motion->crust_transport->crust_evolution
 ->precommit_tendency_evaluation[tectonic_elevation+hillslope_sediment+stream_power_incision;prior_stabilized_surface_hydrology]
 ->provisional_terrain_composition
 ->fluvial_sediment_routing[prior_flow_graph+provisional_accommodation]
 ->finite_alluvium_bedrock_inventory_and_terrain_commit
 ->(sea_level->climate->causal_water_budget->hydrology->numeric_depression_correction)*until_stable}
*configured_erosion_iterations
->cryosphere_state->glacial_sediment_transport
->finite_alluvium_bedrock_inventory_and_terrain_commit
->(sea_level->climate->causal_water_budget->hydrology->numeric_depression_correction)*until_stable
->cryosphere_state_recompute
```

Step by step, with the code that implements each part:

| # | Step | Lines | What it reads | What it writes |
| --- | --- | --- | --- | --- |
| 1 | Capture `previous` feedback reference (elevation, temperature, precipitation, runoff per cell) | `earth_system.cpp:929`, `:5`–`:18` | prior stabilized state | local snapshot only |
| 2 | `advance_plate_motion_and_crust(params, iter + 1, …)` | `earth_system.cpp:930-938` | plates, cells | plate centers, plate assignment, boundary classes, crust transport plan, boundary segments, candidate-fate ledger, shadow/reservoir step, one `PlateMotionStep`; **returns** `tectonic_elevation_change` as a per-cell tendency |
| 3 | Compute `acc_scale` from land flow accumulation | `earth_system.cpp:939-946` | `cell.flow_accumulation`, `cell.is_water` from the **prior** hydrology | scalar |
| 4 | `transport_hillslope_sediment(...)` | `earth_system.cpp:949-958` | prior stabilized `elevation_m`, `lithology`, `area_km2`, `neighbors` | `HillslopeSedimentTransportStage`, `hillslope_production_depth_m`, `hillslope_deposition_depth_m`, per-cell `hillslope_sediment_*` counters |
| 5 | Stream-power loop (OpenMP `parallel for schedule(static)`) | `earth_system.cpp:966-996` | prior stabilized `hydrologic_flow_slope`, `flow_accumulation`, `flow_to`, `lithology` | `next[]` provisional surface, `sediment_source[]`, `cell.erosion_rate` |
| 6 | `route_fluvial_sediment(next, sediment_source, acc_scale, …)` | `earth_system.cpp:999-1009` | **prior** `flow_to` graph, `depression_component_id`, `spill_elevation_m`, `is_lake`, `water_body`, plus the provisional `next[]` as routing base elevation | `FluvialSedimentRoutingStage`, `sediment_delta[]`, `sediment_export[]`, per-cell `fluvial_sediment_*` fields |
| 7 | Combined per-cell terrain commit | `earth_system.cpp:1010-1097` | tectonic + hillslope + fluvial tendencies, opening `sediment_thickness_m` | one `apply_sediment_interface_material_change` call per cell; per-cell partition and budget fields |
| 8 | Interface closure and two source-partition audits | `earth_system.cpp:1098-1119` | committed cells | throws on violation |
| 9 | Push `sediment_routing` and `hillslope_transport` onto their histories | `earth_system.cpp:1120-1121` | — | ledger records |
| 10 | `stabilize_numeric_depressions(..., "erosion_iteration", iter + 1, ...)` | `earth_system.cpp:1122-1130` | committed terrain | sea level, marine labelling, climate, water budget, flow/rivers, numeric depression corrections; new `flow_to` graph for the *next* transition |
| 11 | `summarize_feedback_step(...)` | `earth_system.cpp:1131-1147` | stabilized state + `previous` | one `earth_system_feedback_history` record |

Three ordering facts matter and are stated as contracts in `cpp/src/engine/README.md:108-111`:

1. **Tectonic, hillslope and stream tendencies are all evaluated before the combined terrain commit, from the prior stabilized state.** `advance_plate_motion_and_crust` never assigns `cell.elevation_m` (the only assignment to that field in `tectonics.cpp` is the initial-topography line `:505`); it returns the change vector. `transport_hillslope_sediment` reads `elevation_m` but writes only `hillslope_sediment_*` counters. The stream-power loop writes `next[]`, a local array. The three erosion tendencies are therefore committed through exactly one `apply_sediment_interface_material_change` call per cell, at step 7. That is not the only terrain mutation inside a transition: the stabilization pass at step 10 can still move terrain through numeric-depression breach excavation and redeposition (`cpp/src/engine/hydrology.cpp:1014`, `:1083`) and through the volume-constrained sea-level datum shift (`cpp/src/engine/ocean.cpp:36`, `:245`).
2. **Routing retains the prior flow graph.** `route_fluvial_sediment` consumes `cell.flow_to`, `cell.depression_component_id`, `cell.depression_sink_cell_id`, `cell.spill_elevation_m`, `cell.flow_accumulation`, `cell.hydrologic_flow_slope`, `cell.is_lake`, `cell.lake_overflows` and `cell.water_body` (`earth_system.cpp:496-513`) — all of which were last written by the *previous* stabilization pass. Only the routing **base elevation** is the provisional `next[]` terrain. The model declares this: `fluvial_sediment_routing_model.routing_graph = "erosion_stage_acyclic_hydrologic_flow_to_v1"` (`process_serialization.cpp:1453-1454`).
3. **The terminal cryosphere state is recomputed after stabilization.** `pipeline.cpp` calls `derive_cryosphere_state` at `:151`, runs `transport_glacial_sediment` at `:152-156`, re-stabilizes at `:157-166`, and then calls `derive_cryosphere_state` a **second** time at `:167` before the final feedback record at `:168-184`. That second call is the "zero-duration endpoint operator" — `advances_nominal_time` is `false` for the `cryosphere_coupling` stage because `nominal_feedback_interval` returns `{T, T}` (`process_serialization.cpp:102-111`).

## Stream-power incision

The incision kernel, verbatim (`cpp/src/engine/earth_system.cpp:966-996`):

```cpp
#pragma omp parallel for schedule(static)
for (int i = 0; i < n; ++i) {
    Cell& cell = cells[i];
    next[i] =
        cell.elevation_m +
        tectonic_elevation_change[static_cast<std::size_t>(i)] -
        hillslope_production_depth_m[static_cast<std::size_t>(i)] +
        hillslope_deposition_depth_m[static_cast<std::size_t>(i)];
    if (cell.is_water) {
        cell.erosion_rate = 0.0;
        continue;
    }
    double slope = 0.0;
    if (cell.flow_to >= 0) {
        slope = std::max(0.0, cell.hydrologic_flow_slope);
    }
    const double acc_norm = clamp(cell.flow_accumulation / acc_scale, 0.0, 3.0);
    const double erodability = 1.0 / lithology_resistance(cell.lithology);
    const double stream = params.stream_power_coefficient * erodability *
        std::pow(acc_norm, params.drainage_exponent) *
        std::pow(std::max(0.0, slope * 900.0), params.slope_exponent);
    const double erosion_depth_m =
        stream * maturation_timestep_scale(params);
    cell.erosion_rate = stream;
    sediment_source[static_cast<std::size_t>(i)] = erosion_depth_m;
    next[i] -= erosion_depth_m;
}
```

Term by term:

| Term | Expression | Config property | Notes |
| --- | --- | --- | --- |
| Coefficient | `params.stream_power_coefficient` | `erosion.stream_power_coefficient` (`config.py:388`, default `7.5`) | Described in schema as the "Reference-step stream-power incision coefficient"; dimensionally a metres-per-reference-step scale |
| Erodability | `1.0 / lithology_resistance(cell.lithology)` | — | Table below |
| Drainage term | `pow(acc_norm, drainage_exponent)` | `erosion.drainage_exponent` (`config.py:394`, default `0.5`) | `acc_norm = clamp(flow_accumulation / acc_scale, 0.0, 3.0)` |
| Slope term | `pow(max(0.0, slope * 900.0), slope_exponent)` | `erosion.slope_exponent` (`config.py:400`, default `1.0`) | `slope = max(0.0, hydrologic_flow_slope)` when `flow_to >= 0`, else `0.0`; `900.0` is a hard-coded dimensionless slope gain |
| Applied depth | `stream * maturation_timestep_scale(params)` | `erosion.maturation_timestep_ma` | Written into `sediment_source[i]` and subtracted from `next[i]` |
| Exported response | `cell.erosion_rate = stream` | — | Serialized as the per-cell `erosion_rate` and averaged into `mean_stream_power_response_m_per_reference_step` |

`acc_scale` is the flow-accumulation normalizer (`cpp/src/engine/earth_system.cpp:939-946`): land cells with `flow_accumulation > 0.0` are collected, sorted ascending, and the value at index `(size_t)(0.95 * (accum.size() - 1))` is taken, floored at `1.0`; an empty set yields `1.0`. Because the index conversion truncates, this is a truncated-index 95th-percentile selection, not an interpolated quantile. The same `acc_scale` is passed into `route_fluvial_sediment` and serialized per stage as `fluvial_sediment_routing_history[].accumulation_scale`.

Water cells short-circuit: `erosion_rate` is zeroed and no incision is applied, but the tectonic and hillslope terms already written into `next[i]` remain.

Lithology resistance (`cpp/src/engine/tectonics.cpp:204-215`), with names from `LITHOLOGY_NAMES` (`cpp/src/engine/schema_names.hpp:11-13`):

| Lithology id | Name | `lithology_resistance` | Erodability `1/R` |
| --- | --- | --- | --- |
| 0 | `basalt` | `0.85` | `1.17647…` |
| 1 | `granite` | `1.25` | `0.80` |
| 2 | `limestone` | `0.75` | `1.33333…` |
| 3 | `sandstone` | `0.82` | `1.21951…` |
| 4 | `shale` | `0.62` | `1.61290…` |
| 5 | `volcanic` | `0.95` | `1.05263…` |
| 6 | `metamorphic` | `1.35` | `0.74074…` |
| other | — | `1.0` (default branch) | `1.0` |

The same resistance table is echoed into `hillslope_sediment_transport_model.source_lithology_resistance` (`cpp/src/engine/process_serialization.cpp:1129-1140, 1183-1184`).

### Worked stream-power evaluation

Defaults (`stream_power_coefficient = 7.5`, `drainage_exponent = 0.5`, `slope_exponent = 1.0`, `maturation_timestep_ma = 5.0`), a `shale` cell (`R = 0.62`) with `flow_accumulation / acc_scale = 2.25` and `hydrologic_flow_slope = 0.004`:

```text
erodability = 1 / 0.62                       = 1.612903...
acc_norm    = clamp(2.25, 0, 3)              = 2.25
drainage    = 2.25 ** 0.5                    = 1.5
slope_term  = max(0, 0.004 * 900) ** 1.0     = 3.6
stream      = 7.5 * 1.612903 * 1.5 * 3.6     = 65.322... m per reference step
scale       = 5.0 / 5.0                      = 1.0
erosion_depth_m = 65.322... m
```

At `maturation_timestep_ma = 1.0` the same cell reports the identical `erosion_rate` of `65.32…` but applies `13.06…` m in that transition. This is exactly the split the source comment describes; it is a modelling convention, not a demonstrated convergence property.

## Hillslope diffusion

`transport_hillslope_sediment` (`cpp/src/engine/earth_system.cpp:289-446`) walks every undirected mesh edge exactly once (`cell_b_id <= cell_a_id` is skipped at `:334`) and emits at most one directed transfer per edge.

| Step | Rule | Lines |
| --- | --- | --- |
| Input snapshot | For every cell record `cell_id`, `lithology`, `is_water`, `is_lake`, `elevation_m`, `sediment_thickness_m` **before** any mutation | `:312`–`:323` |
| Source selection | Higher-elevation endpoint is the source; ties keep `cell_a` as source | `:344`–`:349` |
| Eligibility | Skip when `source.is_water` or `elevation_drop_m <= 1.0e-12` | `:354`–`:356` |
| Effective diffusivity | `min(0.45, max(0, hillslope_diffusion) * maturation_timestep_scale / max(1e-12, lithology_resistance(source.lithology)))` | `:357`–`:363` |
| Zero guard | Skip when the effective diffusivity is `<= 0.0` | `:364`–`:366` |
| Source depth | `effective_diffusivity * elevation_drop_m / source_neighbor_count` | `:369`–`:371` |
| Volume transfer | `transfer_volume_km3 = source_depth_m * source.area_km2 / 1000.0` | `:372`–`:373` |
| Target depth | `target_depth_m = transfer_volume_km3 * 1000.0 / target.area_km2` | `:374`–`:375` |
| Per-cell accumulation | `hillslope_sediment_production_m`, `hillslope_sediment_deposition_m`, outgoing/incoming edge counts | `:379`–`:386` |
| Net | `hillslope_sediment_net_m = deposition - production` | `:422`–`:426` |
| Stage totals | `production_volume_km3`, `deposition_volume_km3`, `land_to_land_edge_count`, `land_to_marine_edge_count`, `mean_effective_diffusivity`, `mass_balance_residual_km3` | `:414`–`:443` |

The stability cap is `HILLSLOPE_MAX_EFFECTIVE_DIFFUSIVITY = 0.45` (`cpp/src/engine/constants.hpp:66`), exported as `hillslope_sediment_transport_model.maximum_effective_diffusivity`. With the default `hillslope_diffusion = 0.055` and scale `1.0`, the cap binds only if `lithology_resistance` were below `0.1222`, which no lithology reaches — so at defaults the cap is inactive and the diffusivity is `0.055 / R`, ranging from `0.04074…` (`metamorphic`) to `0.08871…` (`shale`).

Each edge is serialized as a `hillslope_sediment_transport_history[].edges[]` record (`cpp/src/engine/process_serialization.cpp:1348-1396`) carrying `id`, `mesh_edge_cell_a_id`, `mesh_edge_cell_b_id`, `source_cell_id`, `target_cell_id`, `source_lithology`, `source_neighbor_count`, `source_is_water`, `target_is_water`, `target_is_lake`, `source_area_km2`, `target_area_km2`, `source_elevation_m`, `target_elevation_m`, `elevation_drop_m`, `source_lithology_resistance`, `effective_diffusivity`, `source_production_depth_m`, `target_deposition_depth_m`, `transfer_volume_km3`, `mass_balance_residual_km3`. Note that `source_is_water` is emitted as a hard-coded literal `false` (`process_serialization.cpp:1367`) rather than read back from the edge record — it restates the eligibility rule (water sources are skipped at `earth_system.cpp:354-356`) and is not an independent per-edge observation; `HillslopeSedimentTransportEdge` has no such field (`cpp/src/engine/types/earth_system.hpp:224-245`).

Declared model metadata (`cpp/src/engine/process_serialization.cpp:1142-1194`):

| Key | Value |
| --- | --- |
| `model_type` | `pairwise_lithology_dependent_volume_conserving_hillslope_transport_v2` |
| `transport_graph` | `one_directed_transfer_per_eligible_undirected_mesh_edge_v1` |
| `source_selection` | `higher_non_marine_cell_to_lower_adjacent_cell` |
| `effective_diffusivity_model` | `min_stability_cap_configured_reference_diffusivity_times_maturation_timestep_scale_divided_by_source_lithology_resistance` |
| `source_depth_model` | `effective_diffusivity_times_elevation_drop_divided_by_source_neighbor_count` |
| `volume_transfer_model` | `source_depth_times_source_area_equals_target_depth_times_target_area` |
| `source_material_partition_model` | `available_alluvium_first_then_bedrock_erosion_v1` |
| `erosion_stage_source_partition_order` | `hillslope_before_fluvial` |
| `reference_step_response_timestep_scaled` | `true` |
| `time_step_convergence_demonstrated` | `false` |
| `mass_conserving` / `mass_conserving_semantics` | `true` / `bulk_reference_volume_only_not_dry_rock_mass` |
| `physical_time_resolved` | `false` |
| `shared_boundary_geometry_resolved` | `false` |
| `regolith_depth_resolved` | `true` |
| `model_limitation` | `procedural_bulk_transport_without_calibrated_time_shared_boundary_flux_or_grain_classes` |

Note the transfer is normalized by `source_neighbor_count`, not by shared boundary length; `shared_boundary_geometry_resolved` is explicitly `false`.

## Tectonic uplift scaling

`erosion.tectonic_uplift_scale` is a dimensionless multiplier that enters the tectonic **dynamic relief** tendency, not the isostatic or thermal equilibrium terms. It is applied at two places with identical shape:

```cpp
// cpp/src/engine/tectonics.cpp:1611-1613 (per maturation transition)
cell.uplift_rate = params.tectonic_uplift_scale * tectonic_activity *
    (1.5 * div + 8.5 * conv + (crust_type == 3 ? 2.5 : 0.0)) *
    timestep_scale;
```

and the initial-state equivalent at `cpp/src/engine/tectonics.cpp:502-504` (which uses `maturation_timestep_scale(params)` directly). The uplift index then contributes a fraction of the dynamic relief increment:

```cpp
// cpp/src/engine/tectonics.cpp:1614-1617 (boundary_change) and :1632-1646
const double boundary_change =
    80.0 * (conv - previous_convergent[index]) +
    55.0 * (div  - previous_divergent[index]) -
    30.0 * (trans - previous_transform[index]);
const double unbounded_dynamic_relief_change =
    cell.uplift_rate * TECTONIC_UPLIFT_RATE_RESPONSE_FRACTION + boundary_change;
const double bounded_dynamic_relief_change = clamp(
    unbounded_dynamic_relief_change,
    TECTONIC_DYNAMIC_RELIEF_MINIMUM_CHANGE_M,
    TECTONIC_DYNAMIC_RELIEF_MAXIMUM_CHANGE_M
);
const double delta = equilibrium_change + bounded_dynamic_relief_change;
tectonic_elevation_change[index] = delta;
```

| Constant | Value | Source |
| --- | --- | --- |
| `TECTONIC_UPLIFT_RATE_RESPONSE_FRACTION` | `0.42` | `cpp/src/engine/internal.hpp:37` |
| `TECTONIC_DYNAMIC_RELIEF_MINIMUM_CHANGE_M` | `-180.0` | `cpp/src/engine/internal.hpp:35` |
| `TECTONIC_DYNAMIC_RELIEF_MAXIMUM_CHANGE_M` | `220.0` | `cpp/src/engine/internal.hpp:36` |
| `TECTONIC_ISOSTATIC_TARGET_DIFFERENCE_GAIN` | `1.0` | `cpp/src/engine/internal.hpp:34` |
| `OCEANIC_AGE_DEPTH_TARGET_DIFFERENCE_GAIN` | `1.0` | `cpp/src/engine/internal.hpp:32` |

The serialized formula strings and clamp-authority flags match exactly (`cpp/src/engine/process_serialization.cpp:2902-2919`):

| Key | Value |
| --- | --- |
| `dynamic_relief_change_formula` | `tectonic_uplift_scale*tectonic_activity*(1.5*divergence+8.5*convergence+2.5_if_volcanic_arc)*maturation_timestep_scale*0.42+80*(convergence-previous_convergence)+55*(divergence-previous_divergence)-30*(transform-previous_transform)` |
| `bounded_dynamic_relief_formula` | `clamp(unbounded_dynamic_relief_change_m,-180,220)` |
| `tectonic_elevation_change_formula` | `isostatic_equilibrium_change_m+thermal_equilibrium_change_m+bounded_dynamic_relief_change_m` |
| `equilibrium_target_difference_clamped` | `false` |
| `combined_tectonic_equilibrium_and_dynamic_clamp_present` | `false` |
| `equilibrium_operator_physical_time_calibrated` | `false` |

`tectonic_activity` is `clamp(internal_heat * sqrt(4.5 / max(0.05, geological_age_ga)), 0.25, 2.25)` (`process_serialization.cpp:2878-2887`), so `planet.internal_heat` and `planet.geological_age_ga` also modulate the uplift term. The full tectonic tendency, including the crust-transport and equilibrium components, belongs to [Tectonics and Plates](tectonics-and-plates.md) and [Topography, Isostasy and Thermal Subsidence](topography-and-isostasy.md); this page only covers how the resulting `tectonic_elevation_change` vector enters the maturation commit.

## The shared material-update primitive

Every native terrain/material mutation goes through the checked helpers in `cpp/src/engine/sediment_partition.cpp`. The canonical state is two fields; the surface is derived:

| Field | Role | Constraint |
| --- | --- | --- |
| `bedrock_surface_elevation_m` | canonical | finite |
| `sediment_thickness_m` | canonical | finite and `>= 0.0` |
| `elevation_m` | **derived** | `= bedrock_surface_elevation_m + sediment_thickness_m` within a forward-error bound |

The material-update primitive `apply_sediment_interface_material_change(cell, vertical_displacement_m, bedrock_erosion_depth_m, alluvium_entrainment_depth_m, deposition_depth_m, context)` (`cpp/src/engine/sediment_partition.cpp:155-230`) implements exactly:

```text
bedrock_surface_elevation_m' = bedrock_surface_elevation_m
                             + vertical_displacement_m
                             - bedrock_erosion_depth_m
sediment_thickness_m'        = sediment_thickness_m
                             - alluvium_entrainment_depth_m
                             + deposition_depth_m
elevation_m'                 = bedrock_surface_elevation_m' + sediment_thickness_m'
```

This is the same string the document exports as `sediment_interface_model.material_update_equation` (`cpp/src/engine/process_serialization.cpp:1847-1848`).

Argument contract:

| Argument | Sign requirement | Meaning |
| --- | --- | --- |
| `vertical_displacement_m` | any finite value | tectonic elevation change for the transition |
| `bedrock_erosion_depth_m` | finite, `>= 0.0` | bedrock removed below the mobile layer |
| `alluvium_entrainment_depth_m` | finite, `>= 0.0` | mobile sediment taken from the opening inventory |
| `deposition_depth_m` | finite, `>= 0.0` | mobile sediment added |
| `context` | non-null, non-empty | prefix used in every thrown message |

Rejection rules, in evaluation order:

| # | Check | Lines | Thrown message (suffix after `context`) |
| --- | --- | --- | --- |
| 1 | Opening state validation (finite bedrock/thickness/elevation, `thickness >= 0`) | `:163`, `:42`–`:59` | ` sediment-interface state is nonfinite or negative` |
| 2 | Opening surface closure `|elevation - (bedrock + thickness)| <= forward_error_bound(...)` | `:60`–`:77` | ` sediment-interface surface closure failed` |
| 3 | Argument validity (all finite; the three depths `>= 0`) | `:164`–`:176` | ` sediment-interface material change is invalid` |
| 4 | **Entrainment rejection**: `alluvium_entrainment_depth_m > sediment_thickness_m + availability_bound` | `:178`–`:192` | ` sediment-interface entrainment exceeds mobile inventory` |
| 5 | Closing inventory: `opening - entrainment + deposition < -availability_bound` | `:194`–`:202` | ` sediment-interface closing mobile inventory is negative` |
| 6 | Overflow guards on bedrock, thickness and surface | `:204`–`:220`, `:30`–`:40` | `sediment-interface bedrock surface update overflowed` / `… mobile inventory update overflowed` / `… closing surface overflowed` |
| 7 | Closing state validation and surface closure (rules 1–2 again on the new triple) | `:221`–`:226` | same as 1–2 |

The tolerance used in rules 4 and 5 is

```cpp
// cpp/src/engine/sediment_partition.cpp:7-20
long double forward_error_bound(long double absolute_term_sum,
                                std::size_t arithmetic_term_count,
                                long double absolute_floor) {
    return std::max(
        absolute_floor,
        128.0L * std::numeric_limits<double>::epsilon() *
            std::max<std::size_t>(1, arithmetic_term_count) *
            (1.0L + std::abs(absolute_term_sum))
    );
}
```

with `absolute_term_sum = |opening_mobile_depth| + |alluvium_depth|`, `arithmetic_term_count = 2`, `absolute_floor = 1.0e-12`. After the bound check, a slightly negative closing inventory is snapped to `0.0` (`:203`) so `sediment_thickness_m` stays nonnegative by construction. All intermediate arithmetic is done in `long double` and narrowed once at the end.

Two sibling primitives complete the boundary:

| Primitive | Lines | Effect |
| --- | --- | --- |
| `initialize_sediment_interface` | `:91`–`:121` | `bedrock = elevation - thickness`; used once by `derive_crust_and_topography` (`tectonics.cpp:508-510`) |
| `shift_sediment_interface_datum` | `:123`–`:153` | moves bedrock and the derived surface together, leaving `sediment_thickness_m` untouched; used by the volume-constrained sea-level solve |
| `maximum_sediment_interface_closure_residual_m` | `:232`–`:260` | validates every cell and returns the maximum `|elevation - bedrock - thickness|`; throws on an empty cell set |

The maturation commit uses the material primitive; sea-level solving uses the datum shift; numeric-breach excavation/redeposition and terminal glacial transport use the material primitive as well (`cpp/src/engine/README.md:237-240`).

## The combined terrain commit and source partition

For each cell `i`, `erode` performs one alluvium-first partition and one commit (`cpp/src/engine/earth_system.cpp:1010-1097`):

```cpp
double available_alluvium_depth_m = cells[i].sediment_thickness_m;
const double hillslope_alluvium_entrainment_depth_m =
    std::min(available_alluvium_depth_m, hillslope_source_depth_m);
available_alluvium_depth_m -= hillslope_alluvium_entrainment_depth_m;
const double fluvial_alluvium_entrainment_depth_m =
    std::min(available_alluvium_depth_m, fluvial_source_depth_m);
const double hillslope_bedrock_erosion_depth_m =
    std::max(0.0, hillslope_source_depth_m - hillslope_alluvium_entrainment_depth_m);
const double fluvial_bedrock_erosion_depth_m =
    std::max(0.0, fluvial_source_depth_m - fluvial_alluvium_entrainment_depth_m);
```

| Property | Value | Evidence |
| --- | --- | --- |
| Partition order | hillslope demand first, then fluvial demand from what remains | `earth_system.cpp:1015-1026`; `erosion_stage_source_partition_order = "hillslope_then_fluvial"` (`process_serialization.cpp:1973-1974`) |
| Entrainment pool | the **opening** `sediment_thickness_m` of the transition | `earth_system.cpp:1015-1016` |
| Same-stage deposition reusable? | no | `sediment_inventory_model.same_stage_deposition_available_for_entrainment = false` (`process_serialization.cpp:1975-1976`) |
| Residual demand | becomes `bedrock_erosion_depth_m` | `earth_system.cpp:1027-1036` |
| Commit call | one per cell, combining tectonic displacement + both bedrock terms + both alluvium terms + `sediment_delta + hillslope_deposition` | `earth_system.cpp:1070-1080`, context string `"hillslope/fluvial sediment interface"` |

Per-cell fields updated alongside the commit:

| Field | Update | Lines |
| --- | --- | --- |
| `sediment_alluvium_entrainment_m` | `+= hillslope_alluvium + fluvial_alluvium` | `:1058`–`:1060` |
| `sediment_bedrock_erosion_m` | `+= hillslope_bedrock + fluvial_bedrock` | `:1061`–`:1063` |
| `sediment_deposition_m` | `+= sediment_delta[i] + hillslope_deposition_depth_m[i]` | `:1064`–`:1066` |
| `sediment_export_m` | `+= sediment_export[i]` | `:1067` |
| `sediment_net_budget_m` | `= sediment_deposition_m - sediment_gross_mobilization_m(cell)` | `:1094`–`:1096` |

with the canonical helpers in `cpp/src/engine/types/core.hpp:207-219`:

```cpp
inline double sediment_gross_mobilization_m(const Cell& cell) noexcept {
    return cell.sediment_alluvium_entrainment_m + cell.sediment_bedrock_erosion_m;
}
inline double sediment_process_source_witness_m(const Cell& cell) noexcept {
    return cell.hillslope_sediment_production_m +
        cell.fluvial_sediment_local_source_m +
        cell.glacial_sediment_production_m +
        cell.cumulative_numeric_depression_breach_excavation_m;
}
```

Immediately after the primitive call, `erode` re-derives the "compatibility surface" `next[i] + sediment_delta[i]` and requires the committed `elevation_m` to match it within `max(1.0e-9, |compatibility| * 1.0e-12)`, otherwise throwing `hillslope/fluvial sediment-interface update changed the compatibility surface` (`earth_system.cpp:1081-1093`). This is an algebraic identity check: the primitive's `elevation'` must equal the naive additive composition of the four tendencies.

Three audits then run before the histories are pushed (`earth_system.cpp:1098-1119`):

| Audit | Call | What it checks |
| --- | --- | --- |
| Interface closure | `maximum_sediment_interface_closure_residual_m(cells, "post hillslope/fluvial transport")` | every cell's `elevation = bedrock + thickness` within the forward-error bound |
| Hillslope partition | `validate_sediment_source_partition(..., "hillslope")` | per-cell `alluvium + bedrock == source_production_depth`, and the two `depth_m * area_km2 / 1000` volume reductions reconstruct the stage aggregates |
| Fluvial partition | `validate_sediment_source_partition(..., "fluvial")` | same, against the fluvial arrays |

`validate_sediment_source_partition` (`cpp/src/engine/sediment_partition.cpp:262-378`) additionally requires `cell.id == cell_index`, finite positive `area_km2`, nonnegative finite depths, and nonnegative finite aggregates; it throws `sediment source-partition audit linkage is malformed`, `… sediment source-partition aggregate is invalid`, `… sediment source-partition cell linkage is invalid`, `… sediment source-partition depth is invalid`, `… sediment source depth is not partitioned exactly`, or `… sediment source-partition volumes do not reconstruct`.

The world-level `sediment_inventory_model` (`cpp/src/engine/process_serialization.cpp:1874-2054`) aggregates the four contributing processes and publishes `process_source_partition` keyed `hillslope`, `fluvial`, `glacial`, `numeric_breach`, each with `gross_mobilization_volume_km3`, `alluvium_entrainment_volume_km3`, `bedrock_erosion_volume_km3` and `source_partition_residual_km3`. Its authority flags are all explicitly false: `dry_rock_mass_resolved`, `sediment_density_resolved`, `porosity_resolved`, `compaction_resolved`, `grain_provenance_resolved`, `chemical_weathering_resolved`, `physical_time_resolved`, `time_step_convergence_demonstrated`. `mass_conserving` is `true` but qualified by `mass_conserving_semantics = "bulk_reference_volume_only_not_dry_rock_mass"`.

## Fluvial routing inside the transition

Routing is covered in depth on [Sediment, Routing and Stratigraphy](sediment-and-stratigraphy.md); what matters for the maturation loop is the interface. `route_fluvial_sediment` (`cpp/src/engine/earth_system.cpp:448-912`) receives:

| Parameter | Value passed by `erode` | Meaning |
| --- | --- | --- |
| `routing_base_elevation_m` | `next` | the provisional post-tendency terrain, **before** deposition |
| `local_source_depth_m` | `sediment_source` | the timestep-scaled stream incision depths |
| `accumulation_scale` | `acc_scale` | the truncated-index 95th-percentile land accumulation, floored at `1.0` |
| `id` | `sediment_routing_history.size()` | zero-based stage index |
| `feedback_stage_id` | `feedback_history.size()` | equals `erosion_iteration` inside the loop |
| `erosion_iteration` | `iter + 1` | one-based |

It builds a Kahn topological order over the prior `flow_to` graph (`:515`–`:539`, throwing `fluvial sediment routing graph contains a cycle` if the order is short), then walks cells downstream. Fixed partition constants (`cpp/src/engine/constants.hpp:59-65`):

| Constant | Value | Role |
| --- | --- | --- |
| `FLUVIAL_SEDIMENT_MIN_TRANSPORT_CAPACITY_FRACTION` | `0.90` | lower clamp on the routed fraction |
| `FLUVIAL_SEDIMENT_MAX_TRANSPORT_CAPACITY_FRACTION` | `0.995` | upper clamp |
| `FLUVIAL_SEDIMENT_LAKE_TRAP_FRACTION` | `0.35` | overflowing lake trap target |
| `FLUVIAL_SEDIMENT_CLOSED_LAKE_TRAP_FRACTION` | `0.65` | closed lake trap target |
| `FLUVIAL_SEDIMENT_OPEN_OCEAN_DEPOSITION_FRACTION` | `0.12` | marine terminal, open ocean |
| `FLUVIAL_SEDIMENT_SHELF_DEPOSITION_FRACTION` | `0.55` | marine terminal, `water_body == 2` |
| `FLUVIAL_SEDIMENT_INLAND_SEA_DEPOSITION_FRACTION` | `0.30` | marine terminal, `water_body == 3` |

The transport-capacity fraction itself is `clamp(0.90 + 0.045*flow_index + 0.025*slope_index + 0.015*runoff_index + (is_river ? 0.015 : 0.0), 0.90, 0.995)` where `flow_index = clamp(sqrt(flow_accumulation / max(1, acc_scale)), 0, 1)`, `slope_index = clamp(hydrologic_flow_slope * 1200, 0, 1)` and `runoff_index = clamp(runoff_mm_y / 2000, 0, 1)` (`earth_system.cpp:618-644`). None of these fractions is timestep-scaled; `fluvial_sediment_routing_model.local_source_is_timestep_scaled_upstream = true` and `routing_partition_fractions_timestep_invariant = true` (`process_serialization.cpp:1480-1481`).

The stage record carries a complete cell-indexed input snapshot (`input_cells[]`, 15 fields per cell, `earth_system.cpp:496-513`) at round-trip precision, explicitly so that the Python replay can rebuild the routing branches independently (`process_serialization.cpp:1547-1556`).

## The coupled stage ledger and feedback summaries

`summarize_feedback_step` (`cpp/src/engine/earth_system.cpp:20-287`) is the single writer of `earth_system_feedback_history`. It merges one mandatory stabilization result with three nullable per-stage transport records:

| Source | Contribution | Lines |
| --- | --- | --- |
| `HydrologyStabilizationResult` | all recompute counters, numeric-depression counters/volumes, `sea_level_adjustment_m`, and the numeric-breach alluvium/bedrock volumes that **seed** `sediment_alluvium_entrainment_volume_km3` / `sediment_bedrock_erosion_volume_km3` | `:41`–`:89` |
| `FluvialSedimentRoutingStage*` (nullable) | fluvial counters and volumes; `+=` into the two sediment partition totals | `:90`–`:123` |
| `HillslopeSedimentTransportStage*` (nullable) | hillslope counters and volumes; `+=` into the two sediment partition totals | `:124`–`:151` |
| `GlacialSedimentTransportStage*` (nullable) | glacial counters and volumes; `+=` into the two sediment partition totals | `:152`–`:179` |

It then performs one pass over every cell (`:191`–`:257`) accumulating area, ocean volume (`max(0, -elevation) * area / 1000`, water cells only), elevation extrema, climate means, the reference stream-power response (`cell.erosion_rate`), sediment means and volumes, land-only hydrologic volumes (`mm/y * km2 * 1e-6`), and — when a `previous` reference is supplied — the four mean-absolute stage deltas.

Two residuals are computed as closure witnesses (`:272`–`:281`):

```text
sediment_source_partition_residual_km3 =
    | Σ sediment_process_source_witness_m·A/1000
      − Σ sediment_alluvium_entrainment_m·A/1000
      − Σ sediment_bedrock_erosion_m·A/1000 |

sediment_inventory_mass_balance_residual_km3 =
    | Σ sediment_bedrock_erosion_m·A/1000
      − sediment_inventory_volume_km3
      − cumulative_sediment_export_volume_km3 |
```

The first cross-checks the process-side witness against the material partition; the second checks that bedrock removal equals the standing mobile inventory plus everything exported. Both are diagnostics on bulk reference volume, not mass.

Summary-level roll-ups that pertain to maturation (`cpp/src/engine/summary.cpp:1500-1513`):

| Summary key | Definition |
| --- | --- |
| `mean_erosion_iteration_elevation_change_m` | mean of `mean_abs_elevation_change_m_from_previous_stage` over `erosion_iteration` stages only |
| `total_feedback_mean_abs_elevation_change_m` | sum of that delta over all feedback stages |
| `final_feedback_mean_abs_temperature_change_c` | the final stage's temperature delta |
| `final_feedback_mean_abs_precipitation_change_mm_y` | the final stage's precipitation delta |
| `final_feedback_mean_abs_runoff_change_mm_y` | the final stage's runoff delta |

Numeric precision for the feedback ledger: most scalars use `output.float_precision`; sediment and hydrologic volumes use `max(10, float_precision)`; `sea_level_adjustment_m` uses `max(10, …)`; water-budget residuals use `max(12, …)`; the max-depth fields use `max(8, …)`; the nominal-time block uses `max_digits10` (`cpp/src/engine/process_serialization.cpp:2238-2403`).

## The geo evolution provenance enricher

`src/magic_geo/geo_evolution_provenance.py` attaches a machine-readable temporal registry to geo-only worlds. It is invoked as the last enricher in `generate_geo_world` (`src/magic_geo/api.py:374`) and never runs on the full-world path.

Module constants:

| Constant | Value | Line |
| --- | --- | --- |
| `EVOLUTION_PROVENANCE_MODEL_TYPE` | `geo_evolution_provenance_registry_v2` | `:16` |
| `NOMINAL_TIME_MODEL` | `configured_maturation_timestep_nominal_elapsed_time_v1` | `:17` |
| `NOMINAL_TIME_BASIS` | `configured_maturation_timestep_ma_per_erosion_transition_v1` | `:18`–`:20` |
| `NOMINAL_TIME_SOURCE_PARAMETER` | `erosion.maturation_timestep_ma` | `:21` |
| `SOIL_LINKED_TIME_BASIS` | `posthoc_diagnostic_steps_linked_to_native_nominal_endpoints` | `:22` |

The registry partitions every exported "history" into two disjoint classes.

**Native state-mutation ledgers** (`NATIVE_STATE_HISTORY_FAMILIES`, `:25`–`:33`) — 7 families:

| Family | `temporal_role` | `state_mutation_evidence` | `time_basis` |
| --- | --- | --- | --- |
| `plate_motion_history` | `native_state_mutation_ledger` | `yes` | `NOMINAL_TIME_BASIS` |
| `earth_system_feedback_history` | `native_state_mutation_ledger` | `yes` | `NOMINAL_TIME_BASIS` |
| `hydrologic_water_budget_history` | `native_state_mutation_ledger` | `yes` | `NOMINAL_TIME_BASIS` |
| `numeric_depression_correction_history` | `native_mixed_mutation_and_counterfactual_event_ledger` | `mixed` | `NOMINAL_TIME_BASIS` |
| `hillslope_sediment_transport_history` | `native_state_mutation_ledger` | `yes` | `NOMINAL_TIME_BASIS` |
| `fluvial_sediment_routing_history` | `native_state_mutation_ledger` | `yes` | `NOMINAL_TIME_BASIS` |
| `glacial_sediment_transport_history` | `native_state_mutation_ledger` | `yes` | `NOMINAL_TIME_BASIS` |

All seven get `nominal_time_coordinate_available = true`, `physical_time_resolved = false`, `nominal_time_calibrated = false` (`:71`–`:90`).

**Post-hoc diagnostic trajectories** (`DIAGNOSTIC_TRAJECTORY_FAMILIES`, `:46`–`:60`) — 13 families, all with `temporal_role = "posthoc_diagnostic_trajectory"` and `state_mutation_evidence = "no"`:

| Family | `time_basis` | `nominal_time_coordinate_available` |
| --- | --- | --- |
| `climate_seasonal_histories` | `monthly_climatology` | `false` |
| `lake_overflow_histories` | `diagnostic_index_step` | `false` |
| `lake_overflow_channel_histories` | `diagnostic_index_step` | `false` |
| `river_reorganization_histories` | `diagnostic_index_step` | `false` |
| `sediment_routing_histories` | `diagnostic_index_step` | `false` |
| `sediment_transport_histories` | `diagnostic_index_step` | `false` |
| `sequence_stratigraphy_histories` | `diagnostic_index_step` | `false` |
| `ice_sheet_histories` | `diagnostic_index_step` | `false` |
| `ice_sheet_stability_histories` | `diagnostic_index_step` | `false` |
| `ice_flowline_histories` | `diagnostic_index_step` | `false` |
| `soil_profile_histories` | `SOIL_LINKED_TIME_BASIS` when `soil_pedogenesis_model.linked_nominal_time_coordinate_available is True`, else `diagnostic_index_step` | `true` only in the linked case |
| `vegetation_succession_histories` | `diagnostic_index_step` | `false` |
| `wildfire_spread_histories` | `diagnostic_index_step` | `false` |

`soil_profile_histories` is the one conditional case: when linked, it also carries `nominal_time_linkage = "contextual_native_stage_link_without_state_mutation"`; every other diagnostic family carries `nominal_time_linkage = "none"` (`:108`–`:123`).

Note the deliberate near-collision of names: the *native* ledgers `fluvial_sediment_routing_history` and `hillslope_sediment_transport_history` are singular-`history` keys and mutate world state; the *diagnostic* keys `sediment_routing_histories` and `sediment_transport_histories` are plural-`histories` and do not.

The attached `world["geo_evolution_provenance"]` object (`:127`–`:157`):

| Key | Type | Value |
| --- | --- | --- |
| `model_type` | string | `geo_evolution_provenance_registry_v2` |
| `generation_scope` | string | mirrors `world["generation_scope"]`, `"unknown"` if absent |
| `physical_time_resolved` | bool | `false` |
| `nominal_time_coordinate_available` | bool | `true` |
| `nominal_time_calibrated` | bool | `false` |
| `nominal_time_model` / `nominal_time_basis` / `nominal_time_source_parameter` | string | module constants above |
| `nominal_timestep_ma` | number | mirrored from `simulation_clock.nominal_timestep_ma` |
| `final_nominal_elapsed_time_ma` | number | mirrored from `simulation_clock.final_nominal_elapsed_time_ma` |
| `native_state_history_family_count` | int | `7` |
| `diagnostic_trajectory_family_count` | int | `13` |
| `family_count` | int | `20` |
| `native_state_history_families` | list | the 7 names |
| `diagnostic_trajectory_families` | list | the 13 names |
| `families` | list | one record per family, native families first |
| `limitations` | list of 5 strings | quoted below |

The exported `limitations` list is verbatim (`:150`–`:156`):

```text
native mutation histories use a nominal geological coordinate, not calibrated physical time
reference-step scaling has not demonstrated whole-coupling timestep convergence
diagnostic trajectories do not prove that intermediate states mutated the world
soil, vegetation, species, and wildfire diagnostics do not feed back into the native physical clock
the cryosphere mutates terrain once in a final bulk coupling stage
```

`validate_geo_evolution_provenance(world)` (`:161`–`:394`) returns one standardized check with `domain = "evolution_provenance"`, `name = "history_family_temporal_semantics"`, `severity = "error"`. It is appended to the geo validation report whenever `generation_scope == "geo_only"` or the key is present (`src/magic_geo/geo_validation.py:2718-2724`). Its checks:

| Check group | Requirement |
| --- | --- |
| Registry identity | `model_type`, `generation_scope == "geo_only"`, all three nominal-time strings |
| Falsity claims | `physical_time_resolved is False`, `nominal_time_calibrated is False`, `nominal_time_coordinate_available is True` |
| Clock mirror | `simulation_clock.physical_time_resolved is False`, matching `nominal_time_model` / `_basis` / `_source_parameter` / `nominal_time_calibrated`, and equal `nominal_timestep_ma` / `final_nominal_elapsed_time_ma` |
| Family registries | exact list equality with the two module tuples; coverage and uniqueness of the `families` records |
| Per-family | `record_count` equals `len(world[family])`, correct `state_mutation_evidence`, `temporal_role`, `time_basis`, `nominal_time_coordinate_available`, `nominal_time_linkage`, and both falsity flags |
| Per-record (native families only) | each ledger record must declare `nominal_time_model`, `nominal_time_basis`, `nominal_time_source_parameter`, `nominal_time_unit == "Ma"`, `nominal_time_calibrated is False`, `physical_time_resolved is False` |
| Interval consistency (native families only) | all four interval values finite, `start >= 0`, `end + tol >= start`, `duration ≈ end - start`, `elapsed ≈ end`, `advances_nominal_time is (duration > 0.0)`, with `tol = max(1e-12, |end| * 1e-12)` |
| Counts | `family_count == 20`, `native_state_history_family_count == 7`, `diagnostic_trajectory_family_count == 13` |

## Erosion configuration reference

All seven properties live under the `erosion:` section (`src/magic_geo/config.py:371-417`). Every model in the schema sets `extra="forbid"` and `allow_inf_nan=False`, so unknown keys and `nan`/`inf` are rejected.

| Property | Type | Default | Range (Pydantic) | Native field | Native bound | Where consumed | Tuning guidance |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `erosion.iterations` (`config.py:376`) | int | `6` | `ge=0`, `le=250` | `erosion_iterations` (`Params`, `native.hpp:55`; C ABI `CConfig`, `:114`) | `0 … 250` (`core.cpp:406-407`) | loop bound in `erode` (`earth_system.cpp:928`) | Sets both total nominal elapsed time and the number of full coupling passes. `0` skips maturation entirely and leaves only the initial and cryosphere feedback stages. Cost is roughly linear in this value and dominates runtime at large `mesh.cell_count`. The `smoke` profile uses `1`. |
| `erosion.maturation_timestep_ma` (`config.py:382`) | float | `5.0` | `gt=0.0`, `le=5.0` | `maturation_timestep_ma` (`Params`, `native.hpp:66`; C ABI tail `CConfigV3`, `:136-139`) | `>0` and `<=5` (`core.cpp:388-389`) | `maturation_timestep_scale` (`core.cpp:44`) | Refines the nominal interval below the 5 Ma reference. Halving it halves plate rotation, crust aging, uplift index, hillslope diffusivity and applied incision per transition, so you normally double `iterations` to reach the same nominal elapsed time — but the result is **not** guaranteed to converge; `time_step_convergence_demonstrated` is `false` everywhere. `cell.erosion_rate` and the routing partition fractions are deliberately invariant to this parameter. |
| `erosion.stream_power_coefficient` (`config.py:388`) | float | `7.5` | `ge=0.0`, `le=1000.0` | `stream_power_coefficient` (`native.hpp:56`) | `0 … 1000` (`core.cpp:410-413`) | `earth_system.cpp:984` | Linear gain on the reference-step incision response, in metres per reference step before erodability and the drainage/slope terms. Raising it deepens valleys and raises fluvial sediment supply proportionally; `0.0` disables fluvial incision without disabling hillslope transport. |
| `erosion.drainage_exponent` (`config.py:394`) | float | `0.5` | `ge=0.0`, `le=2.0` | `drainage_exponent` (`native.hpp:57`) | `0 … 2` (`core.cpp:415-416`) | `earth_system.cpp:985` | Exponent on `acc_norm ∈ [0, 3]`. `0.0` makes incision independent of drainage area; larger values concentrate incision into trunk streams. Because `acc_norm` is clamped at `3.0`, the term saturates at `3^m` regardless of how large the accumulation gets. |
| `erosion.slope_exponent` (`config.py:400`) | float | `1.0` | `ge=0.0`, `le=3.0` | `slope_exponent` (`native.hpp:58`) | `0 … 3` (`core.cpp:418-419`) | `earth_system.cpp:985` | Exponent on `slope * 900`. Because the base is scaled by 900, values around `1.0` keep the term near unity for gentle gradients; exponents near `3.0` make steep headwaters dominate and amplify sensitivity to `hydrologic_flow_slope`, which itself is a hydrology-stage output. |
| `erosion.hillslope_diffusion` (`config.py:406`) | float | `0.055` | `ge=0.0`, `le=1.0` | `hillslope_diffusion` (`native.hpp:59`) | `0 … 1` (`core.cpp:421-422`) | `earth_system.cpp:358-363` | Reference diffusivity before lithology division and the `0.45` stability cap. At defaults the cap never binds; raising this above roughly `0.28` starts clipping `shale` sources at scale `1.0`, which silently flattens lithologic contrast. `0.0` disables hillslope transport entirely. |
| `erosion.tectonic_uplift_scale` (`config.py:412`) | float | `0.85` | `ge=0.0`, `le=10.0` | `tectonic_uplift_scale` (`native.hpp:60`) | `0 … 10` (`core.cpp:424-425`) | `tectonics.cpp:502`, `:1611` | Multiplies the uplift index that contributes `0.42 ×` its value to the unbounded dynamic relief increment. Because the increment is clamped to `[-180, 220]` m per transition, large values saturate rather than growing relief without bound; the isostatic and thermal equilibrium terms are unaffected. `0.0` leaves only boundary-change dynamic relief plus the equilibrium terms. |

Profile deltas that touch maturation (`src/magic_geo/config.py`, `_PROFILE_OVERRIDES`):

| Profile | Erosion-relevant overrides |
| --- | --- |
| `default` | none |
| `earthlike` | none in `erosion`; `tectonics.plate_motion_scale_deg_per_step` `2.0 → 4.0` and `climate.precipitation_scale` `1.0 → 0.8` both feed the loop indirectly (`config.py:515-518`) |
| `smoke` | `erosion.iterations` `6 → 1`, plus `mesh.cell_count` `4096 → 128`, `tectonics.plate_count` `14 → 8`, `tectonics.plate_motion_scale_deg_per_step` `2.0 → 4.0`, `climate.precipitation_scale` `1.0 → 0.8`, `compute.backend` `auto → cpu`, `compute.threads` `0 → 1`, `run.name` `→ "smoke"` (`config.py:519-528`) |

Parameter marshalling: `config_to_native(config)` is `config.model_dump(mode="json")` (`src/magic_geo/config.py:840`), and `native._native_config` flattens the sections into `NativeConfigV3`. Only `erosion.iterations` is renamed (to `erosion_iterations`); the other six keep their leaf names. `maturation_timestep_ma` lives in the V3 struct tail, so v1 and v2 C callers receive the historical 5 Ma nominal reference step (`cpp/src/engine/README.md:341-345`).

## Worked examples

Materialize a config that refines the nominal timestep while holding total nominal elapsed time at 30 Ma. `init-config` accepts repeatable `--set section.field=YAML_VALUE` overrides (`src/magic_geo/cli/commands/config.py:16-50`):

```bash
magic-geo init-config \
  --profile earthlike \
  --set erosion.iterations=12 \
  --set erosion.maturation_timestep_ma=2.5 \
  --output magic-geo.yaml
```

The resulting `erosion:` block:

```yaml
erosion:
  iterations: 12
  maturation_timestep_ma: 2.5
  stream_power_coefficient: 7.5
  drainage_exponent: 0.5
  slope_exponent: 1.0
  hillslope_diffusion: 0.055
  tectonic_uplift_scale: 0.85
```

Generate a geo-only world (the only scope that receives the provenance registry):

```bash
magic-geo generate --config magic-geo.yaml --geo-only --output runs/world.json
```

Equivalent through the Python API, using the override parser rather than a file:

```python
from magic_geo.api import generate_geo_world
from magic_geo.config import create_config, parse_config_overrides

config = create_config(
    "earthlike",
    parse_config_overrides(
        [
            "erosion.iterations=12",
            "erosion.maturation_timestep_ma=2.5",
            "erosion.stream_power_coefficient=9.0",
        ]
    ),
)

world = generate_geo_world(config)

clock = world["simulation_clock"]
print(clock["nominal_timestep_ma"])            # 2.5
print(clock["maturation_timestep_scale"])      # 0.5
print(clock["final_nominal_elapsed_time_ma"])  # 30.0
print(clock["time_step_convergence_demonstrated"])  # False
```

Inspect the maturation stage ledger and the provenance registry:

```python
for step in world["earth_system_feedback_history"]:
    print(
        step["id"],
        step["stage"],
        step["erosion_iteration"],
        step["nominal_interval_start_ma"],
        step["nominal_interval_end_ma"],
        step["advances_nominal_time"],
        round(step["mean_abs_elevation_change_m_from_previous_stage"], 4),
    )

provenance = world["geo_evolution_provenance"]
print(provenance["model_type"])            # geo_evolution_provenance_registry_v2
print(provenance["family_count"])          # 20
print(provenance["physical_time_resolved"])  # False
for line in provenance["limitations"]:
    print("-", line)
```

Run the provenance check on its own:

```python
from magic_geo.geo_evolution_provenance import validate_geo_evolution_provenance

check = validate_geo_evolution_provenance(world)
print(check["status"], check["evidence"]["violations"])
```

Confirm that `cell.erosion_rate` is a reference-step response and not the applied depth:

```python
scale = world["simulation_clock"]["maturation_timestep_scale"]
cell = max(world["cells"], key=lambda c: c["erosion_rate"])
print(cell["erosion_rate"])            # metres per 5 Ma reference step
print(cell["erosion_rate"] * scale)    # metres applied in one transition
```

## Failure modes and native guards

Every guard below throws `std::runtime_error` from native code; the Python layer surfaces the message through the `{"error": ...}` envelope as a `RuntimeError`.

| Message | Raised by | Trigger |
| --- | --- | --- |
| `sediment transfer cell area is invalid` | `earth_system.cpp:961-965` | any cell with `area_km2 <= 0.0` before the stream-power loop |
| `hillslope sediment source geometry is invalid` | `earth_system.cpp:330-332` | source cell with non-positive area or no neighbors |
| `hillslope sediment neighbor is invalid` | `earth_system.cpp:337-339` | neighbor id outside `[0, n)` |
| `hillslope sediment target geometry is invalid` | `earth_system.cpp:341-343` | target cell with non-positive area or no neighbors |
| `fluvial sediment routing input size mismatch` | `earth_system.cpp:460-465` | `routing_base_elevation_m` or `local_source_depth_m` sized differently from `cells` |
| `fluvial sediment routing cell area is invalid` | `earth_system.cpp:487-489` | non-positive cell area |
| `fluvial sediment routing receiver is invalid` | `earth_system.cpp:491-493` | `flow_to` out of range or self-referential |
| `fluvial sediment routing graph contains a cycle` | `earth_system.cpp:537-539` | topological order shorter than the cell count |
| `hillslope/fluvial sediment interface sediment-interface entrainment exceeds mobile inventory` | `sediment_partition.cpp:187-192` | requested alluvium entrainment exceeds the opening mobile inventory beyond the forward-error bound |
| `hillslope/fluvial sediment interface sediment-interface material change is invalid` | `sediment_partition.cpp:164-176` | non-finite or negative depth argument |
| `hillslope/fluvial sediment-interface update changed the compatibility surface` | `earth_system.cpp:1081-1093` | committed `elevation_m` disagrees with `next[i] + sediment_delta[i]` |
| `post hillslope/fluvial transport sediment-interface surface closure failed` | `sediment_partition.cpp:67-77` via `:232` | derived-surface identity broken on any cell |
| `hillslope sediment source depth is not partitioned exactly` / `fluvial …` | `sediment_partition.cpp:330-340` | per-cell `alluvium + bedrock != source` beyond the bound |
| `hillslope sediment source-partition volumes do not reconstruct` / `fluvial …` | `sediment_partition.cpp:359-377` | cell-array volume reduction disagrees with the stage aggregate |
| `nominal maturation transition count is outside the configured clock` | `process_serialization.cpp:46-51` | serialization asked to place a transition index outside `[0, erosion_iterations]` |
| `erosion history record cannot be placed on the nominal maturation clock` | `process_serialization.cpp:60-64` | an erosion record with an out-of-range iteration |
| `earth-system feedback stage cannot be placed on the nominal maturation clock` | `process_serialization.cpp:112-114` | a feedback record whose `(id, stage)` pair does not match the three legal shapes |
| `maturation_timestep_ma must be greater than 0 and at most 5` | `core.cpp:388-389` | out-of-range nominal timestep at the native boundary |
| `erosion_iterations must be between 0 and 250` | `core.cpp:406-407` | out-of-range iteration count at the native boundary |

## Limitations and unresolved claims

These are stated plainly and are exported as machine-readable flags; do not present them as resolved.

| Claim | Exported value | Location |
| --- | --- | --- |
| Physical time | `physical_time_resolved = false` | `simulation_clock` (`process_serialization.cpp:2083`), every nominal-time block (`:159`), `plate_kinematic_model` (`:2686`), `hillslope_sediment_transport_model` (`:1188`), `fluvial_sediment_routing_model` (`:1488`), `sediment_inventory_model` (`:1988`), `geo_evolution_provenance` and all 20 family records |
| Nominal-time calibration | `nominal_time_calibrated = false` | `simulation_clock` (`:2084`), every nominal-time block (`:158`), `plate_kinematic_model` (`:2687`), `geo_evolution_provenance` |
| Process-rate calibration | `process_rate_calibration_resolved = false` | `simulation_clock` (`:2086`), `plate_kinematic_model` (`:2688`) |
| Whole-coupling timestep convergence | `time_step_convergence_demonstrated = false` | `simulation_clock` (`:2087`), `plate_kinematic_model` (`:2689`), `hillslope_sediment_transport_model` (`:1179`), `fluvial_sediment_routing_model` (`:1482`), `sediment_inventory_model` (`:1978`) |
| Absolute geological age | `absolute_geological_age_resolved = false` | `simulation_clock` (`:2085`) |

Additional caveats that follow from the implementation:

- **Refining `maturation_timestep_ma` is a resolution knob, not a convergence procedure.** The constants comment says so directly (`cpp/src/engine/constants.hpp:68-71`: "This is not physical calibration"), and the plate kinematic model labels the scheme `reference_normalized_partial_process_scaling_v1` with the limitation string `partial_reference_timestep_scaling_and_uncalibrated_physical_time`. Climate, hydrology, sea level, the fluvial partition fractions and the entire cryosphere path are *not* scaled, so the coupled system is not uniformly refined.
- **`cell.erosion_rate` is deliberately timestep-invariant.** It is the 5 Ma reference stream-power response, not the depth applied in the transition. Any downstream consumer treating it as a per-transition or per-year rate is misreading it; the document says so via `cell_erosion_rate_semantics`.
- **Bulk-volume conservation is not mass conservation.** All three transport models declare `mass_conserving = true` qualified by `mass_conserving_semantics = "bulk_reference_volume_only_not_dry_rock_mass"`. `dry_rock_mass_resolved`, `sediment_density_resolved`, `porosity_resolved`, `compaction_resolved`, `grain_provenance_resolved` and `chemical_weathering_resolved` are all `false` on both `sediment_interface_model` and `sediment_inventory_model`.
- **The per-cell alluvium/bedrock source-partition arrays are not mass or provenance claims.** Both `hillslope_sediment_transport_model` and `fluvial_sediment_routing_model` export `source_partition_audit_is_mass_claim = false` and `source_partition_audit_is_provenance_claim = false`.
- **Hillslope transport does not resolve shared boundary geometry.** The source depth is divided by the source's neighbor count, not by shared control-volume edge length; `shared_boundary_geometry_resolved = false`.
- **Fluvial capacity is a dimensionless proxy.** `model_limitation = "dimensionless_capacity_proxy_without_grain_size_calibrated_time_or_subcell_channels"`, with `grain_size_resolved = false` and `subcell_channel_geometry_resolved = false`.
- **The cryosphere mutates terrain exactly once, in a final bulk coupling stage**, and does not advance nominal time. This is the fifth entry in the enricher's own `limitations` list and matches `cryosphere_advances_nominal_time = false`.
- **Routing uses the previous transition's flow graph.** Within a transition, drainage is not re-derived after the tectonic/hillslope/incision tendencies are computed; only the routing base elevation is provisional. Whether this lag is acceptable at a given `maturation_timestep_ma` has not been demonstrated.
- **`acc_scale` is a truncated-index percentile over the current land accumulation field**, so it changes between transitions and between configurations. Absolute `erosion_rate` values are therefore not comparable across runs with different drainage structure.
- **Tectonic dynamic relief is clamped to `[-180, 220]` m per transition** and the clamp is *empirical*. Large `tectonic_uplift_scale` values saturate against it rather than producing proportional relief; only `unbounded_dynamic_relief_change_m` is clipped, and the equilibrium terms deliberately bypass it.
- **`geo_evolution_provenance` exists only on the geo-only path.** `generate_world` (full world) never attaches it, so full-world documents carry no history-family temporal registry and the corresponding validator does not run.
- **Diagnostic trajectory families do not prove intermediate world states existed.** The registry's own third limitation states this; the 13 `*_histories` families are reconstructed from final state.

## See also

- [Native Engine (C++ Core)](../08-native-engine.md)
- [Architecture](../04-architecture.md)
- [Configuration Reference](../05-configuration-reference.md)
- [World Document Schema](../10-world-schema.md)
- [Serialization and World Formats](../11-serialization.md)
- [Geo Validation Suite](../13-geo-validation-suite.md)
- [Validation](../12-validation.md)
- [Tectonics and Plates](tectonics-and-plates.md)
- [Topography, Isostasy and Thermal Subsidence](topography-and-isostasy.md)
- [Sediment, Routing and Stratigraphy](sediment-and-stratigraphy.md)
- [Hydrology, Rivers and Lakes](hydrology-and-rivers.md)
- [Cryosphere: Ice Sheets, Glaciers and Permafrost](cryosphere.md)
- [Crust Material Shadow and Dry-Rock Reservoirs](crust-material-and-reservoirs.md)
- [Soils and Weathering](soils.md)
- [Glossary](../21-glossary.md)
