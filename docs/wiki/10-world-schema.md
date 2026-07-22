# World Document Schema

[Wiki home](./README.md) > World Document Schema

This page is the field-level reference for a generated magic-geo world document. The native engine emits a hand-rolled JSON object with **57 top-level keys in a fixed emission order** (`cpp/src/engine/world_serialization.cpp:42`), containing a **412-key `summary` object**, a **155-field per-cell record**, twenty-odd nested entity families, and a set of declarative model/contract sections whose explicit `false` flags record exactly which physical claims the project does *not* make. Everything below was read out of the serializers; where a value is a diagnostic, a shadow, or an unresolved claim, that is stated as the source states it.

## On this page

- [Document identity and top-level key inventory](#document-identity-and-top-level-key-inventory)
- [Metadata and `planet_parameters`](#metadata-and-planet_parameters)
- [The `summary` object](#the-summary-object)
- [The per-cell record](#the-per-cell-record)
- [Natural entity record families](#natural-entity-record-families)
- [Society and history record families](#society-and-history-record-families)
- [Model and contract sections](#model-and-contract-sections)
- [Explicit `false` flags and what they mean](#explicit-false-flags-and-what-they-mean)
- [Process and history ledger families](#process-and-history-ledger-families)
- [The shared nominal-time block](#the-shared-nominal-time-block)
- [Enum name tables](#enum-name-tables)
- [Full-world vs geo-only documents](#full-world-vs-geo-only-documents)
- [Numerical precision contracts](#numerical-precision-contracts)
- [Decimal-quantization contracts declared in the document](#decimal-quantization-contracts-declared-in-the-document)
- [Stable navigation and versioning](#stable-navigation-and-versioning)
- [Worked examples](#worked-examples)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

---

## Document identity and top-level key inventory

The whole document is built by `magic_geo::detail::serialize_world` in `cpp/src/engine/world_serialization.cpp:42-294`. There is no JSON library involved: every key is appended by `add_int` / `add_str` / `add_double` / `add_bool` / `add_raw` / `add_u64` from `cpp/src/engine/core.cpp:185-211`. Key order is therefore **deterministic and stable** — it is literally the order of the calls in that function. Consumers should still key by name, not by position, but a textual diff of two documents shows real value changes rather than key-reordering noise. Bitwise run-to-run reproducibility is a property of the deterministic CPU reference path, not a schema guarantee; see [Compute Backends](./09-compute-backends.md).

`cells` is the last key and is emitted as `[]` when `params.include_cells == false` (`cpp/src/engine/world_serialization.cpp:289-291`). The key is always present.

| # | key | JSON type | one-line description | owning feature page |
|---|---|---|---|---|
| 1 | `schema_version` | int | Literal `2` (`world_serialization.cpp:49`). | this page |
| 2 | `name` | string | Configured run name. | [Configuration Reference](./05-configuration-reference.md) |
| 3 | `planet_parameters` | object | 12 planet inputs, all binary64 round-trip. | [Configuration Reference](./05-configuration-reference.md) |
| 4 | `mesh_backend` | string | `fibonacci_sphere` \| `geodesic_icosahedron` \| `unknown` (`core.cpp:104`). | [Mesh and Geometry](./features/mesh-and-geometry.md) |
| 5 | `cell_area_model` | string | `spherical_voronoi_control_volume_v1` \| `spherical_barycentric_control_volume_v2` \| `unknown` (`core.cpp:115`). | [Mesh and Geometry](./features/mesh-and-geometry.md) |
| 6 | `summary` | object | 412 aggregate/diagnostic keys. | this page |
| 7 | `backend` | object | Compute-backend telemetry and accelerator parity flags. | [Compute Backends](./09-compute-backends.md) |
| 8 | `climate_model` | object | Declarative equilibrium climate contract. | [Climate and Atmosphere](./features/climate-and-atmosphere.md) |
| 9 | `hydrologic_water_budget_model` | object | Land loss-partition water budget contract + final-stage totals. | [Hydrology, Rivers and Lakes](./features/hydrology-and-rivers.md) |
| 10 | `hydrologic_water_budget_history` | array | Per-stage water budget with 17 parallel by-cell arrays. | [Hydrology, Rivers and Lakes](./features/hydrology-and-rivers.md) |
| 11 | `simulation_clock` | object | Nominal stage clock contract. | [Architecture](./04-architecture.md) |
| 12 | `earth_system_feedback_history` | array | Per-stage coupled feedback ledger (118 fields/record). | [Erosion, Maturation and Landscape Evolution](./features/erosion-and-maturation.md) |
| 13 | `sediment_interface_model` | object | Bedrock/mobile-sediment interface contract. | [Sediment, Routing and Stratigraphy](./features/sediment-and-stratigraphy.md) |
| 14 | `sediment_inventory_model` | object | Finite alluvium/bedrock inventory + per-process partition. | [Sediment, Routing and Stratigraphy](./features/sediment-and-stratigraphy.md) |
| 15 | `numeric_depression_correction_history` | array | Per-event breach/fill/temporary-lake correction ledger. | [Hydrology, Rivers and Lakes](./features/hydrology-and-rivers.md) |
| 16 | `hillslope_sediment_transport_model` | object | Pairwise diffusive hillslope transport contract. | [Erosion, Maturation and Landscape Evolution](./features/erosion-and-maturation.md) |
| 17 | `hillslope_sediment_transport_history` | array | Per-stage hillslope transport with edge-level evidence. | [Erosion, Maturation and Landscape Evolution](./features/erosion-and-maturation.md) |
| 18 | `glacial_sediment_transport_model` | object | Downhill area-conserving glacial transport contract. | [Cryosphere](./features/cryosphere.md) |
| 19 | `glacial_sediment_transport_history` | array | Single cryosphere-stage glacial transfer ledger. | [Cryosphere](./features/cryosphere.md) |
| 20 | `fluvial_sediment_routing_model` | object | Capacity-limited fluvial routing contract. | [Sediment, Routing and Stratigraphy](./features/sediment-and-stratigraphy.md) |
| 21 | `fluvial_sediment_routing_history` | array | Per-stage routing with cell-step and terminal-allocation evidence. | [Sediment, Routing and Stratigraphy](./features/sediment-and-stratigraphy.md) |
| 22 | `plate_kinematic_model` | object | Rotating-Voronoi plate model contract (126 declared keys, `process_serialization.cpp:2613-2943`). | [Tectonics and Plates](./features/tectonics-and-plates.md) |
| 23 | `plate_boundary_segment_model` | object | Exact reciprocal control-volume segment contract. | [Plate Boundary Segment Ledger](./features/plate-boundary-ledger.md) |
| 24 | `initial_oceanic_crust_age_model` | object | Ridge-graph travel-time age initialization contract. | [Tectonics and Plates](./features/tectonics-and-plates.md) |
| 25 | `initial_oceanic_crust_age_ledger` | object (not array) | The procedurally authoritative initial oceanic age field + path witnesses (`authority_scope = "deterministic_procedural_initial_oceanic_like_age_field_only"`). | [Tectonics and Plates](./features/tectonics-and-plates.md) |
| 26 | `crust_overlap_candidate_fate_model` | object | Diagnostic overlap-candidate crosswalk contract. | [Crust Transport and Forward Overlap](./features/crust-transport-and-overlap.md) |
| 27 | `oceanic_age_depth_model` | object | Parsons–Sclater relative subsidence curve contract. | [Topography, Isostasy and Thermal Subsidence](./features/topography-and-isostasy.md) |
| 28 | `crust_material_shadow_model` | object | Sparse surface crust-mass shadow contract. | [Crust Material Shadow and Dry-Rock Reservoirs](./features/crust-material-and-reservoirs.md) |
| 29 | `crust_dry_rock_accounting_model` | object | Finite three-reservoir dry-rock accounting contract. | [Crust Material Shadow and Dry-Rock Reservoirs](./features/crust-material-and-reservoirs.md) |
| 30 | `sea_level_model` | object | Volume-constrained connectivity ocean flood contract. | [Oceans, Currents and Coasts](./features/oceans-and-coasts.md) |
| 31 | `plate_motion_history` | array | The largest family: per-step transport, coverage, boundary and plate ledgers. | [Crust Transport and Forward Overlap](./features/crust-transport-and-overlap.md) |
| 32 | `crust_material_shadow_history` | array | Per-step packet/adjustment mass tables. | [Crust Material Shadow and Dry-Rock Reservoirs](./features/crust-material-and-reservoirs.md) |
| 33 | `crust_dry_rock_accounting_history` | array | Per-step three-reservoir packet tables and residuals. | [Crust Material Shadow and Dry-Rock Reservoirs](./features/crust-material-and-reservoirs.md) |
| 34 | `plates` | array | Final plate records (19 fields). | [Tectonics and Plates](./features/tectonics-and-plates.md) |
| 35 | `watersheds` | array | Basin polygons and geometry quality (26 fields). | [Hydrology, Rivers and Lakes](./features/hydrology-and-rivers.md) |
| 36 | `lake_basins` | array | Depression/lake basins with overflow paths (28 fields). | [Hydrology, Rivers and Lakes](./features/hydrology-and-rivers.md) |
| 37 | `coastal_features` | array | Shoreline features and trends (12 fields). | [Oceans, Currents and Coasts](./features/oceans-and-coasts.md) |
| 38 | `sedimentary_basins` | array | Basin records (11 fields). | [Sediment, Routing and Stratigraphy](./features/sediment-and-stratigraphy.md) |
| 39 | `stratigraphic_columns` | array | Columns with nested `layers[]` (13 + 9 fields). | [Sediment, Routing and Stratigraphy](./features/sediment-and-stratigraphy.md) |
| 40 | `ice_sheets` | array | Ice sheet records (16 fields). | [Cryosphere](./features/cryosphere.md) |
| 41 | `political_regions` | array | Political regions (12 fields). | [Political, Cultural and Linguistic Geography](./features/political-and-cultural-geography.md) |
| 42 | `cultures` | array | Culture regions (20 fields). | [Political, Cultural and Linguistic Geography](./features/political-and-cultural-geography.md) |
| 43 | `language_regions` | array | Language regions (16 fields). | [Political, Cultural and Linguistic Geography](./features/political-and-cultural-geography.md) |
| 44 | `historical_eras` | array | Four-era partition records (10 fields). | [History, Demography, Economy and Markets](./features/history-demography-and-economy.md) |
| 45 | `historical_events` | array | Discrete history events (13 fields). | [History, Demography, Economy and Markets](./features/history-demography-and-economy.md) |
| 46 | `population_regions` | array | Population/capacity records (14 fields). | [History, Demography, Economy and Markets](./features/history-demography-and-economy.md) |
| 47 | `conflicts` | array | Conflict records (23 fields). | [History, Demography, Economy and Markets](./features/history-demography-and-economy.md) |
| 48 | `dynasties` | array | Dynasty lineage records (18 fields). | [History, Demography, Economy and Markets](./features/history-demography-and-economy.md) |
| 49 | `territorial_snapshots` | array | Era snapshots with nested `regions[]` (11 + 18 fields). | [Political, Cultural and Linguistic Geography](./features/political-and-cultural-geography.md) |
| 50 | `calibration_checks` | array | Reference-range checks (9 fields). | [Calibration Against Real-Earth Data](./14-calibration.md) |
| 51 | `sacred_areas` | array | Cultural sites (8 fields). | [Political, Cultural and Linguistic Geography](./features/political-and-cultural-geography.md) |
| 52 | `ruins` | array | Abandoned sites (10 fields). | [Political, Cultural and Linguistic Geography](./features/political-and-cultural-geography.md) |
| 53 | `borders` | array | Border segments (8 fields). | [Political, Cultural and Linguistic Geography](./features/political-and-cultural-geography.md) |
| 54 | `settlements` | array | Settlements (14 fields). | [Settlements, Routes and Corridors](./features/settlements-and-routes.md) |
| 55 | `routes` | array | Routes (6 fields). | [Settlements, Routes and Corridors](./features/settlements-and-routes.md) |
| 56 | `trade_flows` | array | Trade flows (11 fields). | [History, Demography, Economy and Markets](./features/history-demography-and-economy.md) |
| 57 | `cells` | array | The per-cell mesh state (155 fields), or `[]`. | this page |

Everything a Python enricher adds (`mesh_lod`, `cell_adjacency_edges`, `aquifer_systems`, `soil_profiles`, `river_channel_systems`, …) is **outside this native list**; those keys are documented on the corresponding feature pages and in [Python API](./07-python-api.md).

---

## Metadata and `planet_parameters`

`planet_parameters_json` (`cpp/src/engine/world_serialization.cpp:23-40`) emits exactly twelve fields, every one through `roundtrip_num` — i.e. `std::defaultfloat` at `std::numeric_limits<double>::max_digits10` significant digits, an exact binary64 round-trip.

| field | type | units | producer | meaning |
|---|---|---|---|---|
| `radius_km` | double (round-trip) | km | config → `Params` | Planet radius; validated `> 100` and `<= 100000` (`core.cpp:305`). |
| `gravity_g` | double (round-trip) | Earth g | config | Surface gravity; validated `> 0.05`, `< 5` (`core.cpp:310`). |
| `day_length_hours` | double (round-trip) | h | config | Rotation period; validated `> 1`, `<= 10000` (`core.cpp:313`). |
| `axial_tilt_deg` | double (round-trip) | ° | config | Obliquity; validated `0..90` (`core.cpp:318`). |
| `orbital_eccentricity` | double (round-trip) | — | config | Validated `>= 0`, `< 1` (`core.cpp:321`). |
| `stellar_luminosity` | double (round-trip) | Sun = 1 | config | Validated `> 0.01`, `<= 100` (`core.cpp:324`). |
| `atmosphere_pressure_bar` | double (round-trip) | bar | config | Validated `0..1000` (`core.cpp:329`). |
| `greenhouse_factor` | double (round-trip) | — | config | Validated `0..100` (`core.cpp:337`). |
| `ocean_fraction_target` | double (round-trip) | fraction | config | Validated `0..0.95` (`core.cpp:340`). |
| `ocean_water_inventory_km3` | double (round-trip) | km³ | config | Validated `0..1e10` (`core.cpp:343`). |
| `internal_heat` | double (round-trip) | — | config | Validated `0..100` (`core.cpp:351`). |
| `geological_age_ga` | double (round-trip) | Ga | config | Validated `0.01..100` (`core.cpp:354`); also caps the crust age ceiling via `crust_age_ceiling_ma` (`core.cpp:40`). |

The Python layer re-derives this object and refuses to proceed on a mismatch: `_require_configured_planet_snapshot` raises `RuntimeError("native planet_parameters do not match the configured planet snapshot")` (`src/magic_geo/api.py:185-192`), and `enrich_world_with_planet_realism` performs the same check a second time.

---

## The `summary` object

`summary` is composed by three functions, appended in this exact order:

```
summary_with_crust_dry_rock_accounting_json(
    summary_with_crust_material_shadow_json(
        summary_json(...)
    ), ...)
```
(`cpp/src/engine/world_serialization.cpp:54-84`)

| block | source | key count |
|---|---|---|
| base aggregate/diagnostic block | `summary_json`, `cpp/src/engine/summary.cpp:177` (emission starts at `summary.cpp:1319`) | 373 |
| crust-material-shadow extension | `summary_with_crust_material_shadow_json`, `cpp/src/engine/summary.cpp:121-172` | 18 |
| crust dry-rock accounting extension | `summary_with_crust_dry_rock_accounting_json`, `cpp/src/engine/crust_reservoir_serialization.cpp:430-488` | 21 |
| **total** | | **412** |

### 3a. Base block (`summary_json`, 373 keys, emission order)

Grouped by subject; the order below is emission order.

| group | keys |
|---|---|
| Run identity and formatting (5) | `seed`, `mesh_backend`, `cell_area_model`, `cell_count`, `output_float_precision` |
| Depression and hydrologic-surface model declarations (18) | `depression_routing_model`, `depression_geology_model`, `numeric_depression_correction_model`, `numeric_depression_correction_selection_model`, `numeric_depression_breach_diagnostic_model`, `numeric_depression_breach_gradient_step_m`, `numeric_depression_selected_breach_max_depth_m`, `numeric_depression_breach_mass_transfer_model`, `numeric_depression_correction_selection_reason`, `numeric_depression_correction_max_pass_count`, `numeric_depression_fill_depth_tolerance_m`, `hydrologic_surface_model`, `hydrologic_water_budget_model`, `hydrologic_water_budget_execution_order`, `hydrologic_flat_gradient_step_m`, `river_extraction_model`, `river_extraction_percentile`, `river_flow_accumulation_threshold` |
| Mesh geometry (6) | `surface_area_km2`, `mean_cell_area_km2`, `min_cell_area_km2`, `max_cell_area_km2`, `cell_area_coefficient_of_variation`, `plate_count` |
| Simulation clock counters (7) | `simulation_clock_stage_count`, `simulation_clock_erosion_iteration_count`, `simulation_clock_cryosphere_coupling_stage_count`, `simulation_clock_sea_level_recompute_count`, `simulation_clock_climate_recompute_count`, `simulation_clock_hydrologic_water_budget_recompute_count`, `simulation_clock_hydrology_recompute_count` |
| Fluvial sediment routing totals (18) | `fluvial_sediment_routing_stage_count`, `fluvial_sediment_active_cell_step_count`, `fluvial_sediment_routed_edge_count`, `fluvial_sediment_routed_cell_count`, `fluvial_sediment_land_terminal_count`, `fluvial_sediment_marine_terminal_count`, `fluvial_sediment_terminal_capture_cell_count`, `fluvial_sediment_terminal_allocation_count`, `fluvial_sediment_local_source_volume_km3`, `fluvial_sediment_routed_throughput_volume_km3`, `fluvial_sediment_capacity_deposition_volume_km3`, `fluvial_sediment_depression_fill_deposition_volume_km3`, `fluvial_sediment_lake_trap_deposition_volume_km3`, `fluvial_sediment_terminal_land_deposition_volume_km3`, `fluvial_sediment_marine_deposition_volume_km3`, `fluvial_sediment_terminal_export_volume_km3`, `fluvial_sediment_total_deposition_volume_km3`, `fluvial_sediment_mass_balance_residual_km3` |
| Hillslope sediment totals (14) | `hillslope_sediment_transport_stage_count`, `hillslope_sediment_transport_edge_count`, `hillslope_sediment_source_cell_stage_count`, `hillslope_sediment_target_cell_stage_count`, `hillslope_sediment_land_to_land_edge_count`, `hillslope_sediment_land_to_marine_edge_count`, `hillslope_sediment_unique_source_cell_count`, `hillslope_sediment_unique_target_cell_count`, `hillslope_sediment_production_volume_km3`, `hillslope_sediment_deposition_volume_km3`, `hillslope_sediment_mass_balance_residual_km3`, `max_hillslope_sediment_source_production_depth_m`, `max_hillslope_sediment_target_deposition_depth_m`, `mean_hillslope_sediment_effective_diffusivity` |
| Glacial sediment totals (12) | `glacial_sediment_transport_stage_count`, `glacial_sediment_transfer_count`, `glacial_sediment_source_cell_count`, `glacial_sediment_target_cell_count`, `glacial_sediment_land_target_transfer_count`, `glacial_sediment_marine_target_transfer_count`, `glacial_sediment_production_volume_km3`, `glacial_sediment_deposition_volume_km3`, `glacial_sediment_mass_balance_residual_km3`, `glacial_sediment_terrain_volume_change_residual_km3`, `max_glacial_sediment_source_production_depth_m`, `max_glacial_sediment_target_deposition_depth_m` |
| Feedback convergence (5) | `mean_erosion_iteration_elevation_change_m`, `total_feedback_mean_abs_elevation_change_m`, `final_feedback_mean_abs_temperature_change_c`, `final_feedback_mean_abs_precipitation_change_mm_y`, `final_feedback_mean_abs_runoff_change_mm_y` |
| Plate-motion counters (8) | `plate_motion_history_step_count`, `plate_motion_transition_count`, `total_plate_reassignment_event_count`, `plate_reassigned_cell_count`, `max_plate_assignment_change_count`, `total_aged_oceanic_event_count`, `total_rejuvenated_oceanic_event_count`, `total_subducted_oceanic_event_count` |
| Crust-transport closure diagnostics (5 counters + 13 `max_digits10` residuals + 2 reason-record counters) | `total_crust_overlap_sparse_edge_count`, `total_crust_mixed_destination_count`, `maximum_crust_coverage_multiplicity`, `maximum_crust_coverage_arrangement_line_count`, `maximum_crust_coverage_arrangement_fragment_count`, `maximum_crust_source_area_closure_error_km2`, `maximum_crust_source_area_relative_closure_error`, `maximum_crust_destination_partition_closure_error_km2`, `total_crust_uncovered_gap_area_km2`, `total_crust_overlap_excess_area_km2`, `maximum_crust_transport_inventory_relative_closure_error`, `cumulative_absolute_tectonic_process_crust_volume_change_km3`, `net_tectonic_process_crust_volume_change_km3`, `cumulative_absolute_tectonic_process_density_weighted_crust_volume_change_g_cm3_km3`, `net_tectonic_process_density_weighted_crust_volume_change_g_cm3_km3`, `cumulative_absolute_tectonic_process_crust_age_volume_moment_change_km3_ma`, `net_tectonic_process_crust_age_volume_moment_change_km3_ma`, `total_tectonic_process_reason_record_count`, `active_tectonic_process_reason_record_count`, `maximum_tectonic_process_attribution_relative_closure_residual` (`summary.cpp:1522-1586`) |
| Plate/crust motion aggregates (15) | `accreted_terrane_cell_count`, `mean_plate_cumulative_rotation_deg`, `max_plate_cumulative_rotation_deg`, `mean_crust_transport_distance_km_per_motion_step`, `max_crust_transport_distance_km`, `mean_abs_crust_age_change_ma_per_motion_step`, `mean_abs_crust_thickness_change_km_per_motion_step`, `mean_abs_crust_density_change_per_motion_step`, `mean_abs_crust_age_transport_change_ma_per_motion_step`, `mean_abs_crust_thickness_transport_change_km_per_motion_step`, `mean_abs_crust_density_transport_change_per_motion_step`, `mean_abs_crust_age_process_change_ma_per_motion_step`, `mean_abs_crust_thickness_process_change_km_per_motion_step`, `mean_abs_crust_density_process_change_per_motion_step`, `mean_abs_tectonic_elevation_change_m_per_motion_step` |
| Ocean and hypsometry (10) | `target_ocean_fraction`, `target_ocean_water_inventory_km3`, `ocean_area_km2`, `ocean_volume_km3`, `ocean_water_inventory_error_km3`, `ocean_fraction`, `ocean_cell_fraction`, `min_elevation_m`, `max_elevation_m`, `mean_land_elevation_m` |
| Flow-graph health (11) | `river_count`, `equal_filled_raw_downhill_reroute_count`, `hydrologic_surface_conditioned_cell_count`, `equal_filled_flow_edge_count`, `raw_uphill_flow_edge_count`, `non_downhill_hydrologic_flow_edge_count`, `max_hydrologic_surface_adjustment_m`, `max_raw_uphill_flow_step_m`, `terminal_land_sink_count`, `avoidable_equal_filled_raw_downhill_sink_count`, `flow_cycle_cell_count` |
| Lakes and depressions (10) | `lake_count`, `depression_component_count`, `depression_component_cell_count`, `lake_basin_count`, `overflowing_lake_basin_count`, `staged_overflow_lake_basin_count`, `high_avulsion_risk_lake_basin_count`, `preserved_geologic_depression_count`, `corrected_numeric_depression_count`, `temporary_numeric_lake_depression_count` |
| Numeric depression correction ledger (33) | `numeric_depression_correction_pass_count`, `numeric_depression_correction_event_count`, `numeric_depression_fill_candidate_event_count`, `numeric_depression_fill_candidate_cell_application_count`, `numeric_depression_fill_candidate_area_km2`, `numeric_depression_fill_candidate_volume_km3`, `numeric_depression_temporary_lake_event_count`, `numeric_depression_temporary_lake_cell_application_count`, `numeric_depression_temporary_lake_unique_cell_count`, `numeric_depression_temporary_lake_candidate_area_km2`, `numeric_depression_temporary_lake_candidate_volume_km3`, `max_numeric_depression_temporary_lake_depth_m`, `numeric_depression_breach_feasible_event_count`, `numeric_depression_breach_lower_volume_event_count`, `numeric_depression_breach_depth_bound_pass_event_count`, `numeric_depression_breach_capacity_pass_event_count`, `numeric_depression_breach_selected_event_count`, `numeric_depression_breach_excavation_cell_application_count`, `numeric_depression_breach_deposition_cell_application_count`, `numeric_depression_selected_breach_excavation_volume_km3`, `numeric_depression_selected_breach_deposition_volume_km3`, `numeric_depression_correction_mass_balance_residual_km3`, `numeric_depression_mass_conserving_event_count`, `numeric_depression_zero_material_deferral_event_count`, `numeric_depression_avoided_unsourced_fill_volume_km3`, `numeric_depression_feasible_breach_excavation_volume_km3`, `numeric_depression_lower_volume_hybrid_adjustment_volume_km3`, `numeric_depression_lower_volume_hybrid_saved_volume_km3`, `numeric_depression_lower_volume_hybrid_saved_fraction`, `mean_numeric_depression_breach_path_length_km`, `max_numeric_depression_breach_path_length_km`, `max_numeric_depression_breach_excavation_depth_m`, `max_lower_volume_breach_excavation_depth_m` (`summary.cpp:1668-1772`) |
| Lake/basin/watershed geometry (19) | `closed_depression_count`, `mean_lake_fill_fraction`, `lake_storage_capacity_km3`, `lake_annual_runoff_km3`, `mean_lake_overflow_path_length_km`, `mean_lake_avulsion_risk`, `basin_count`, `endorheic_basin_count`, `watershed_count`, `endorheic_watershed_count`, `largest_watershed_area_km2`, `watershed_geometry_count`, `largest_watershed_boundary_cell_count`, `watershed_polygon_count`, `largest_watershed_polygon_area_km2`, `mean_watershed_polygon_area_error_fraction`, `mean_watershed_compactness_index`, `mean_watershed_geometry_quality`, `mean_watershed_boundary_perimeter_km` |
| Coasts, basins, stratigraphy (17) | `coastal_feature_count`, `coastal_bar_feature_count`, `prograding_coastal_feature_count`, `eroding_coastal_feature_count`, `mean_coastal_migration_rate_m_y`, `sedimentary_basin_count`, `active_sedimentary_basin_count`, `largest_sedimentary_basin_area_km2`, `mean_sedimentary_basin_thickness_m`, `stratigraphic_column_count`, `stratigraphic_layer_count`, `active_stratigraphic_column_count`, `max_stratigraphic_layer_count`, `mean_stratigraphic_thickness_m`, `spill_corrected_cell_count`, `closed_basin_cell_count`, `max_depression_depth_m` |
| Society totals (58) | `settlement_count`, `route_count`, `trade_flow_count`, `trade_total_volume_index`, `interregional_trade_fraction`, `mean_trade_friction`, `political_region_count`, `culture_region_count`, `language_region_count`, `historical_era_count`, `historical_event_count`, `migration_event_count`, `dynastic_change_count`, `language_lineage_count`, `population_region_count`, `estimated_world_population`, `mean_population_pressure`, `conflict_count`, `high_intensity_conflict_count`, `mean_conflict_intensity`, `mean_war_duration_years`, `total_mobilized_population`, `mean_conflict_logistics_strain_index`, `mean_conflict_economic_disruption_index`, `high_economic_disruption_conflict_count`, `mean_conflict_casualty_rate`, `max_conflict_casualty_rate`, `dynasty_count`, `dynastic_lineage_count`, `dynasty_root_count`, `dynasty_successor_link_count`, `max_dynasty_lineage_depth`, `mean_dynastic_continuity_index`, `territorial_snapshot_count`, `snapshot_region_record_count`, `snapshot_polygon_region_count`, `mean_snapshot_fragmentation_index`, `mean_snapshot_polygon_area_error_fraction`, `mean_snapshot_compactness_index`, `mean_snapshot_geometry_quality`, `mean_snapshot_boundary_perimeter_km`, `mean_historical_instability`, `mean_cultural_continuity`, `mean_language_change_rate`, `mean_phonological_complexity`, `mean_sound_shift_index`, `mean_inherited_phonology_fraction`, `sacred_area_count`, `ruin_count`, `border_segment_count`, `border_total_length_km`, `natural_border_fraction`, `largest_region_area_km2`, `largest_culture_area_km2`, `politically_assigned_land_fraction`, `culturally_assigned_land_fraction`, `linguistically_assigned_land_fraction`, `top_settlement_score` |
| Sediment budget and inventory (29) | `mean_sediment_thickness_m`, `sediment_budget_production_m`, `sediment_budget_deposition_m`, `sediment_budget_export_m`, `sediment_budget_residual_m`, `sediment_budget_closure_model`, `sediment_budget_production_km3`, `sediment_budget_deposition_km3`, `sediment_budget_export_km3`, `sediment_budget_residual_km3`, `sediment_delivery_ratio`, `sediment_inventory_model`, `sediment_initial_mobile_inventory_model`, `sediment_source_partition_model`, `sediment_erosion_stage_source_partition_order`, `sediment_gross_mobilization_volume_km3`, `sediment_alluvium_entrainment_volume_km3`, `sediment_bedrock_erosion_volume_km3`, `sediment_final_inventory_volume_km3`, `sediment_source_partition_residual_km3`, `sediment_inventory_mass_balance_residual_km3`, `hillslope_sediment_alluvium_entrainment_volume_km3`, `hillslope_sediment_bedrock_erosion_volume_km3`, `fluvial_sediment_alluvium_entrainment_volume_km3`, `fluvial_sediment_bedrock_erosion_volume_km3`, `glacial_sediment_alluvium_entrainment_volume_km3`, `glacial_sediment_bedrock_erosion_volume_km3`, `numeric_depression_alluvium_entrainment_volume_km3`, `numeric_depression_bedrock_erosion_volume_km3` |
| Initial relief means (13) | `mean_initial_isostatic_elevation_m`, `mean_initial_thermal_subsidence_m`, `mean_initial_ridge_uplift_m`, `mean_initial_orogenic_uplift_m`, `mean_initial_volcanic_uplift_m`, `mean_initial_trench_subsidence_m`, `mean_initial_rift_subsidence_m`, `mean_initial_transform_fault_relief_m`, `mean_initial_secondary_roughness_m`, `mean_initial_elevation_m`, `mean_tectonic_uplift_rate_m_per_step`, `mean_volcanic_potential_index`, `high_volcanic_potential_cell_count` |
| Atmosphere and moisture means (22) | `mean_orographic_factor`, `mean_rain_shadow_factor`, `rain_shadowed_land_fraction`, `mean_humidity_transport_index`, `mean_upwind_ocean_fetch_km`, `mean_advected_moisture_factor`, `atmospheric_cell_counts`, `mean_surface_pressure_anomaly_hpa`, `mean_vertical_velocity_index`, `mean_wind_divergence_index`, `mean_seasonal_wind_speed`, `mean_seasonal_wind_reversal_index`, `ascending_air_fraction`, `mean_vapor_evaporation_mm_y`, `mean_moisture_convergence_mm_y`, `mean_orographic_rainout_mm_y`, `mean_precipitation_recycling_fraction`, `mean_vapor_deficit_mm_y`, `mean_abs_vapor_budget_residual_mm_y`, `mean_ocean_current_strength`, `mean_ocean_current_temperature_c`, `mean_ocean_current_moisture_factor` |
| Cryosphere means (11) | `mean_ice_thickness_m`, `mean_glacial_erosion_m`, `mean_ice_surface_mass_balance_m_y`, `mean_basal_sliding_index`, `mean_ice_velocity_m_y`, `glaciated_land_fraction`, `ice_sheet_count`, `mean_ice_sheet_retreat_rate_m_y`, `moraine_deposition_cell_count`, `mean_moraine_deposition_m`, `mean_deglaciation_age_ka` |
| Plausibility and calibration (6) | `river_downhill_fraction`, `mountain_convergent_alignment`, `calibration_check_count`, `calibration_pass_count`, `calibration_pass_fraction`, `mean_calibration_score` |
| Sparse categorical histograms (6, plus `atmospheric_cell_counts` above) | `boundary_counts`, `crust_counts`, `biome_counts`, `resource_counts`, `water_body_counts`, `landform_counts` |

The seven `*_counts` keys are sparse objects built by `counts_json` (`cpp/src/engine/summary.cpp:5-15`) from a `std::map<std::string,int>` — **only observed categories appear**, keys ordered lexicographically by `std::map`. Do not assume a fixed key set.

### 3b. Crust-material-shadow extension (18 keys)

`crust_material_shadow_history_step_count`, `total_crust_material_shadow_packet_count`, `maximum_crust_material_shadow_packet_count_per_table`, `total_crust_material_shadow_opening_packet_count`, `total_crust_material_shadow_transported_packet_count`, `total_crust_material_shadow_closing_packet_count`, `maximum_crust_material_shadow_opening_packet_count_per_step`, `maximum_crust_material_shadow_transported_packet_count_per_step`, `maximum_crust_material_shadow_closing_packet_count_per_step`, `total_crust_material_shadow_adjustment_count`, `maximum_crust_material_shadow_adjustment_count_per_table`, `total_crust_material_shadow_unresolved_source_adjustment_count`, `total_crust_material_shadow_unresolved_sink_adjustment_count`, `cumulative_crust_material_shadow_unresolved_source_mass_kg`, `cumulative_crust_material_shadow_unresolved_sink_mass_kg`, `maximum_absolute_crust_material_shadow_transport_raw_residual_kg`, `maximum_crust_material_shadow_closing_scalar_relative_residual`, `maximum_absolute_crust_material_shadow_adjustment_reconciliation_residual_kg` (`cpp/src/engine/summary.cpp:121-172`). Every mass value uses `mass_precision = max_digits10` (`summary.cpp:119`).

### 3c. Crust dry-rock accounting extension (21 keys)

`crust_dry_rock_accounting_history_step_count`, `total_crust_dry_rock_surface_packet_count`, `total_crust_dry_rock_upper_mantle_packet_count`, `total_crust_dry_rock_subducted_slab_packet_count`, `total_crust_dry_rock_proxy_transfer_count`, `maximum_crust_dry_rock_closing_surface_packet_count_per_step`, `maximum_crust_dry_rock_closing_upper_mantle_packet_count_per_step`, `maximum_crust_dry_rock_proxy_transfer_count_per_step`, `maximum_crust_dry_rock_closing_reservoir_packet_count_per_step`, `maximum_crust_dry_rock_surface_packet_count_per_owner`, `maximum_crust_dry_rock_live_reservoir_packet_count_per_step`, `cumulative_crust_dry_rock_requested_surface_source_mass_kg`, `cumulative_crust_dry_rock_requested_surface_sink_mass_kg`, `cumulative_crust_dry_rock_fulfilled_surface_source_mass_kg`, `cumulative_crust_dry_rock_fulfilled_surface_sink_mass_kg`, `minimum_crust_dry_rock_closing_upper_mantle_mass_kg`, `maximum_crust_dry_rock_closing_subducted_slab_mass_kg`, `maximum_absolute_crust_dry_rock_global_accounting_residual_kg`, `maximum_absolute_crust_dry_rock_origin_closure_residual_kg`, `maximum_absolute_crust_dry_rock_reservoir_transfer_residual_kg`, `maximum_crust_dry_rock_closing_scalar_relative_residual` (`cpp/src/engine/crust_reservoir_serialization.cpp:430-488`). All masses at `MASS_PRECISION = max_digits10` (`crust_reservoir_serialization.cpp:7`).

> `conflict_intensity_scale` is **not** a document key. It is a C++ local at `cpp/src/engine/summary.cpp:712`, computed as `pow(10, clamp(float_precision, 0, 8))` and used to round conflict intensity **before** the `>= 0.65` test for `high_intensity_conflict_count`. This is a genuine value dependence of a counter on the display-precision setting, not just formatting.

---

## The per-cell record

Emitted by `cells_json` (`cpp/src/engine/entity_serialization.cpp:110-355`). **155 fields**, always in this order. Precision legend used in the table:

| symbol | definition | source |
|---|---|---|
| `G` | `geometry_precision = max(max_digits10, float_precision)` | `entity_serialization.cpp:113` |
| `S` | `surface_precision = max(10, float_precision)` | `entity_serialization.cpp:117` |
| `P` | `float_precision` (configured, default 4) | `src/magic_geo/config.py:450` |
| `RT` | `roundtrip_num` — general format, `max_digits10` significant digits, exact binary64 round-trip | `cpp/src/engine/numeric_serialization.cpp:5` |

Producer column names the native stage file under `cpp/src/engine/`. No Python enricher writes into any of these 155 keys; enrichers add *new* keys alongside them.

| # | field | type / precision | units | producer stage | meaning |
|---|---|---|---|---|---|
| 1 | `id` | int | — | `mesh.cpp` | Canonical cell id; equals array index. |
| 2 | `position_3d` | double[3] `G` | unit sphere | `mesh.cpp` | Cell site on the unit sphere. |
| 3 | `normal_3d` | double[3] `G` | unit sphere | `mesh.cpp` | Serialized from the same `cell.p` as `position_3d` (`entity_serialization.cpp:123-124`) — an exact alias, not an independent normal. |
| 4 | `lat_deg` | double `G` | ° | `mesh.cpp` | Latitude (`cell.lat * DEG`). |
| 5 | `lon_deg` | double `G` | ° | `mesh.cpp` | Longitude (`cell.lon * DEG`). |
| 6 | `area_km2` | double `G` | km² | `mesh.cpp` | Control-volume area under `cell_area_model`. |
| 7 | `control_volume_vertices_3d` | double[3][] `G` | unit sphere | `mesh.cpp` | Ordered control-volume polygon vertices. |
| 8 | `control_volume_edge_neighbor_ids` | int[] | — | `mesh.cpp` | Neighbor id per control-volume edge; basis for reciprocal boundary segments. |
| 9 | `neighbors` | int[] | — | `mesh.cpp` | Mesh adjacency list. |
| 10 | `political_region_id` | int | — | `civilization.cpp` | Owning political region, or negative when unassigned. Stripped in geo-only. |
| 11 | `culture_region_id` | int | — | `civilization.cpp`, `history.cpp` | Owning culture region. Stripped in geo-only. |
| 12 | `language_region_id` | int | — | `history.cpp`, `civilization.cpp` | Owning language region. Stripped in geo-only. |
| 13 | `plate_id` | int | — | `tectonics.cpp` | Final plate assignment. |
| 14 | `initial_plate_id` | int | — | `tectonics.cpp` | Plate assignment at step 0. |
| 15 | `plate_assignment_change_count` | int | — | `tectonics.cpp` | Number of plate reassignments over the run. |
| 16 | `last_plate_assignment_change_iteration` | int | — | `tectonics.cpp` | Erosion iteration of the most recent reassignment. |
| 17 | `oceanic_crust_aging_event_count` | int | — | `tectonics.cpp` | Times the quiet-aging rule fired here. |
| 18 | `oceanic_crust_rejuvenation_event_count` | int | — | `tectonics.cpp` | Times the ridge-rejuvenation rule fired. |
| 19 | `oceanic_crust_subduction_event_count` | int | — | `tectonics.cpp` | Times the convergence subduction **proxy** rule fired (see caveats). |
| 20 | `cumulative_crust_transport_distance_km` | double `P` | km | `tectonics.cpp` | Summed forward-overlap transport distance. |
| 21 | `crust_type` | enum string | — | `tectonics.cpp` | `CRUST_NAMES`. |
| 22 | `lithology` | enum string | — | `tectonics.cpp`, `environment.cpp` | `LITHOLOGY_NAMES`. |
| 23 | `boundary_type` | enum string | — | `tectonics.cpp` | `BOUNDARY_NAMES` (smoothed cell-level class). |
| 24 | `boundary_convergent` | double `P` | index 0..1 | `tectonics.cpp` | Smoothed convergent forcing strength. |
| 25 | `boundary_divergent` | double `P` | index 0..1 | `tectonics.cpp` | Smoothed divergent forcing strength. |
| 26 | `boundary_transform` | double `P` | index 0..1 | `tectonics.cpp` | Smoothed transform forcing strength. |
| 27 | `crust_age_ma` | **`RT`** | Ma | `tectonics.cpp` | Crust age; round-trip because history replay depends on it. |
| 28 | `crust_thickness_km` | **`RT`** | km | `tectonics.cpp` | Crust thickness. |
| 29 | `crust_density` | **`RT`** | g/cm³ | `tectonics.cpp` | Crust density. |
| 30 | `cumulative_tectonic_elevation_change_m` | double `S` | m | `tectonics.cpp` | Summed tectonic elevation change. |
| 31 | `initial_isostatic_elevation_m` | double `S` | m | `tectonics.cpp` | Initial isostatic equilibrium component. |
| 32 | `thermal_subsidence_target_m` | **`RT`** | m | `tectonics.cpp` | Parsons–Sclater relative subsidence target; negative for oceanic-like cells. |
| 33 | `initial_ridge_uplift_m` | double `S` | m | `tectonics.cpp` | Initial ridge relief component. |
| 34 | `initial_orogenic_uplift_m` | double `S` | m | `tectonics.cpp` | Initial orogenic relief component. |
| 35 | `initial_volcanic_uplift_m` | double `S` | m | `tectonics.cpp` | Initial volcanic-arc relief component. |
| 36 | `initial_trench_subsidence_m` | double `S` | m | `tectonics.cpp` | Initial trench relief component. |
| 37 | `initial_rift_subsidence_m` | double `S` | m | `tectonics.cpp` | Initial rift relief component. |
| 38 | `initial_transform_fault_relief_m` | double `S` | m | `tectonics.cpp` | Initial transform relief component. |
| 39 | `initial_secondary_roughness_m` | double `S` | m | `tectonics.cpp` | Graph-smoothed signed-noise relief component. |
| 40 | `initial_elevation_m` | double `S` | m | `tectonics.cpp` | Sum of the initial relief components. |
| 41 | `tectonic_uplift_rate_m_per_step` | double `P` | m / model step | `tectonics.cpp` | Serialized from `cell.uplift_rate`. |
| 42 | `volcanic_potential_index` | double `P` | index | `tectonics.cpp` | Volcanic potential proxy. |
| 43 | `bedrock_surface_elevation_m` | double `S` | m | `sediment_partition.cpp`, `ocean.cpp` | Canonical top of non-mobile bedrock (see `sediment_interface_model`). |
| 44 | `elevation_m` | **`RT`** | m | `sediment_partition.cpp`, `earth_system.cpp`, `ocean.cpp` | Derived surface `= bedrock_surface_elevation_m + sediment_thickness_m`. Round-trip because it is an ocean-mask determinant. |
| 45 | `water_depth_m` | **`RT`** | m | `ocean.cpp`, `hydrology.cpp` | Water column depth. Round-trip for the same reason. |
| 46 | `is_water` | bool | — | `ocean.cpp`, `environment.cpp` | Discrete ocean/water mask. |
| 47 | `water_body_type` | enum string | — | `ocean.cpp`, `hydrology.cpp`, `water_features.cpp` | `WATER_BODY_NAMES`. |
| 48 | `temperature_c` | double `P` | °C | `climate.cpp` | Annual mean surface temperature. |
| 49 | `temperature_monthly_c` | double[12] `P` | °C | `climate.cpp` | Monthly climatology (`months` is validated to be exactly 12, `core.cpp:376`). |
| 50 | `precipitation_mm_y` | double `P` | mm/y | `climate.cpp` | Annual precipitation. |
| 51 | `precipitation_monthly_mm` | double[12] `P` | mm | `climate.cpp` | Monthly precipitation. |
| 52 | `wind_east` | double `P` | index | `climate.cpp` | Eastward wind component. |
| 53 | `wind_north` | double `P` | index | `climate.cpp` | Northward wind component. |
| 54 | `wind_monthly_east` | double[12] `P` | index | `climate.cpp` | Monthly eastward wind. |
| 55 | `wind_monthly_north` | double[12] `P` | index | `climate.cpp` | Monthly northward wind. |
| 56 | `mean_seasonal_wind_speed` | double `P` | index | `climate.cpp` | Mean magnitude across months. |
| 57 | `seasonal_wind_reversal_index` | double `P` | index | `climate.cpp` | Monsoonal reversal proxy. |
| 58 | `atmospheric_cell` | enum string | — | `climate.cpp` | `ATMOSPHERIC_CELL_NAMES`. |
| 59 | `surface_pressure_anomaly_hpa` | double `P` | hPa | `climate.cpp` | Diagnostic pressure anomaly. |
| 60 | `vertical_velocity_index` | double `P` | index | `climate.cpp` | Ascent/descent proxy. |
| 61 | `wind_divergence_index` | double `P` | index | `climate.cpp` | Horizontal divergence proxy. |
| 62 | `ocean_current_east` | double `P` | index | `climate.cpp` | Eastward surface current. |
| 63 | `ocean_current_north` | double `P` | index | `climate.cpp` | Northward surface current. |
| 64 | `ocean_current_temperature_c` | double `P` | °C | `climate.cpp` | Advected current temperature. |
| 65 | `ocean_current_moisture_factor` | double `P` | factor | `climate.cpp` | Current-driven moisture multiplier. |
| 66 | `humidity_transport_index` | double `P` | index | `climate.cpp` | Moisture transport proxy. |
| 67 | `upwind_ocean_fetch_km` | double `P` | km | `climate.cpp` | Upwind over-water fetch. |
| 68 | `advected_moisture_factor` | double `P` | factor | `climate.cpp` | Advected moisture multiplier. |
| 69 | `orographic_factor` | double `P` | factor | `climate.cpp` | Windward enhancement. |
| 70 | `rain_shadow_factor` | double `P` | factor | `climate.cpp` | Leeward suppression. |
| 71 | `vapor_evaporation_mm_y` | double `P` | mm/y | `climate.cpp` | Vapor budget evaporation term. |
| 72 | `moisture_convergence_mm_y` | double `P` | mm/y | `climate.cpp` | Vapor budget convergence term. |
| 73 | `orographic_rainout_mm_y` | double `P` | mm/y | `climate.cpp` | Vapor budget rainout term. |
| 74 | `precipitation_recycling_fraction` | double `P` | fraction | `climate.cpp` | Locally recycled precipitation share. |
| 75 | `vapor_deficit_mm_y` | double `P` | mm/y | `climate.cpp` | Unmet vapor demand. |
| 76 | `vapor_budget_residual_mm_y` | double `P` | mm/y | `climate.cpp` | Vapor budget closure residual (diagnostic). |
| 77 | `hydrologic_potential_evapotranspiration_mm_y` | double `P` | mm/y | `hydrology.cpp` | PET from the land water-budget model. |
| 78 | `actual_evapotranspiration_mm_y` | double `P` | mm/y | `hydrology.cpp` | AET = climate loss − infiltration. |
| 79 | `infiltration_capacity_index` | double `P` | index | `hydrology.cpp` | Lithology/sediment/relief/frozen capacity. |
| 80 | `infiltration_mm_y` | double `P` | mm/y | `hydrology.cpp` | Infiltrated depth. |
| 81 | `hydrologic_water_balance_mm_y` | double `P` | mm/y | `hydrology.cpp` | `P − AET − infiltration`. |
| 82 | `water_budget_runoff_mm_y` | double `P` | mm/y | `hydrology.cpp` | `max(0, water balance)`. |
| 83 | `runoff_budget_residual_mm_y` | double `S` | mm/y | `hydrology.cpp` | Cell-level budget closure residual. |
| 84 | `runoff_budget_consistency_index` | double `P` | index | `hydrology.cpp` | Consistency diagnostic. |
| 85 | `hydrologic_deficit_mm_y` | double `P` | mm/y | `hydrology.cpp` | Water deficit. |
| 86 | `runoff_generation_fraction` | double `P` | fraction | `hydrology.cpp` | Runoff share of precipitation. |
| 87 | `runoff_mm_y` | double `P` | mm/y | `hydrology.cpp`, `earth_system.cpp` | Runoff used by routing. |
| 88 | `flow_to` | int | — | `hydrology.cpp` | Downstream cell id, or negative at a terminal. |
| 89 | `equal_filled_raw_downhill_rerouted` | bool | — | `hydrology.cpp` | Flow was rerouted on an equal-filled surface. |
| 90 | `spill_to` | int | — | `hydrology.cpp` | Spill target cell id. |
| 91 | `depression_component_id` | int | — | `hydrology.cpp`, `water_features.cpp` | Connected depression component. |
| 92 | `depression_sink_cell_id` | int | — | `hydrology.cpp` | Sink cell of that component. |
| 93 | `lake_basin_id` | int | — | `water_features.cpp`, `hydrology.cpp` | Index into `lake_basins`. |
| 94 | `depression_policy` | enum string | — | `hydrology.cpp`, `water_features.cpp` | `DEPRESSION_POLICY_NAMES`. |
| 95 | `flow_accumulation` | double `P` | accumulated units | `hydrology.cpp`, `earth_system.cpp` | Upstream accumulation. |
| 96 | `filled_elevation_m` | double `P` | m | `hydrology.cpp` | Priority-flood filled surface. |
| 97 | `hydrologic_surface_elevation_m` | double `S` | m | `hydrology.cpp` | Conditioned routing surface. |
| 98 | `hydrologic_flow_drop_m` | double `S` | m | `hydrology.cpp` | Drop along the chosen flow edge. |
| 99 | `hydrologic_flow_slope` | double `max(12, S)` | dimensionless | `hydrology.cpp` | Drop / distance; highest per-cell decimal floor in the record. |
| 100 | `hydrologic_surface_conditioned` | bool | — | `hydrology.cpp` | Surface was adjusted for routing. |
| 101 | `depression_depth_m` | double `P` | m | `hydrology.cpp` | Depth below the spill point. |
| 102 | `spill_elevation_m` | double `P` | m | `hydrology.cpp` | Spill sill elevation. |
| 103 | `lake_fill_fraction` | double `P` | fraction | `hydrology.cpp` | Fill state of the containing basin. |
| 104 | `basin_id` | int | — | `hydrology.cpp`, `water_features.cpp` | Drainage basin id. |
| 105 | `is_river` | bool | — | `hydrology.cpp` | Above the river extraction threshold. |
| 106 | `is_lake` | bool | — | `hydrology.cpp`, `ocean.cpp` | Lake surface cell. |
| 107 | `is_closed_basin` | bool | — | `hydrology.cpp` | Endorheic. |
| 108 | `lake_overflows` | bool | — | `hydrology.cpp`, `earth_system.cpp` | Basin overflows its sill. |
| 109 | `cumulative_numeric_depression_breach_excavation_m` | double `S` | m | `hydrology.cpp` | Summed breach excavation depth. |
| 110 | `cumulative_numeric_depression_breach_deposition_m` | double `S` | m | `hydrology.cpp` | Summed breach deposition depth. |
| 111 | `numeric_depression_breach_event_count` | int | — | `hydrology.cpp` | Breach events touching this cell. |
| 112 | `numeric_depression_temporary_lake_event_count` | int | — | `hydrology.cpp` | Temporary-lake deferrals touching this cell. |
| 113 | `erosion_rate` | double `P` | m / reference step | `earth_system.cpp` | Stream-power **response per reference step**, not applied depth (`simulation_clock.cell_erosion_rate_semantics`). |
| 114 | `sediment_thickness_m` | double `S` | m | `sediment_partition.cpp`, `earth_system.cpp` | Canonical mobile sediment thickness. |
| 115 | `sediment_deposition_m` | double `P` | m | `earth_system.cpp`, `hydrology.cpp` | Cumulative deposition depth. |
| 116 | `sediment_export_m` | double `P` | m | `earth_system.cpp` | Cumulative export depth. |
| 117 | `sediment_net_budget_m` | double `P` | m | `earth_system.cpp` | Net budget depth. |
| 118 | `sediment_alluvium_entrainment_m` | double `S` | m | `sediment_partition.cpp` | Depth sourced from existing alluvium. |
| 119 | `sediment_bedrock_erosion_m` | double `S` | m | `sediment_partition.cpp` | Depth sourced from bedrock. |
| 120 | `hillslope_sediment_production_m` | double `S` | m | `earth_system.cpp` | Hillslope source depth. |
| 121 | `hillslope_sediment_deposition_m` | double `S` | m | `earth_system.cpp` | Hillslope target depth. |
| 122 | `hillslope_sediment_net_m` | double `S` | m | `earth_system.cpp` | Hillslope net depth. |
| 123 | `hillslope_sediment_outgoing_edge_count` | int | — | `earth_system.cpp` | Outgoing hillslope edges. |
| 124 | `hillslope_sediment_incoming_edge_count` | int | — | `earth_system.cpp` | Incoming hillslope edges. |
| 125 | `fluvial_sediment_local_source_m` | double `S` | m | `earth_system.cpp` | Locally mobilized fluvial depth. |
| 126 | `fluvial_sediment_routed_incoming_m` | double `S` | m | `earth_system.cpp` | Routed inflow depth. |
| 127 | `fluvial_sediment_routed_outgoing_m` | double `S` | m | `earth_system.cpp` | Routed outflow depth. |
| 128 | `fluvial_sediment_local_deposition_m` | double `S` | m | `earth_system.cpp` | Capacity-limited local deposition. |
| 129 | `fluvial_sediment_terminal_land_deposition_m` | double `S` | m | `earth_system.cpp` | Land terminal deposition. |
| 130 | `fluvial_sediment_marine_deposition_m` | double `S` | m | `earth_system.cpp` | Marine deposition. |
| 131 | `fluvial_sediment_depression_fill_m` | double `S` | m | `earth_system.cpp` | Depression accommodation fill. |
| 132 | `fluvial_sediment_terminal_export_m` | double `S` | m | `earth_system.cpp` | Exported out of the domain. |
| 133 | `fluvial_sediment_terminal_capture_volume_km3` | double `max(10, P)` | km³ | `earth_system.cpp` | Volume captured at this terminal. |
| 134 | `fluvial_sediment_routing_event_count` | int | — | `earth_system.cpp` | Routing events touching this cell. |
| 135 | `ice_thickness_m` | double `P` | m | `environment.cpp` | Ice thickness. |
| 136 | `ice_sheet_id` | int | — | `environment.cpp` | Index into `ice_sheets`. |
| 137 | `glacier_flow_to` | int | — | `environment.cpp` | Steepest-downhill glacier target. |
| 138 | `ice_surface_mass_balance_m_y` | double `P` | m/y | `environment.cpp` | Surface mass balance. |
| 139 | `basal_sliding_index` | double `P` | index | `environment.cpp` | Basal sliding proxy. |
| 140 | `ice_velocity_m_y` | double `P` | m/y | `environment.cpp` | Ice velocity proxy. |
| 141 | `glacial_erosion_m` | double `P` | m | `environment.cpp` | Glacial erosion potential depth. |
| 142 | `glacial_sediment_production_m` | double `S` | m | `environment.cpp` | Glacial source depth. |
| 143 | `glacial_sediment_deposition_m` | double `S` | m | `environment.cpp` | Glacial target depth. |
| 144 | `glacial_sediment_net_m` | double `S` | m | `environment.cpp` | Glacial net depth. |
| 145 | `glacial_sediment_outgoing_transfer_count` | int | — | `environment.cpp` | Outgoing glacial transfers. |
| 146 | `glacial_sediment_incoming_transfer_count` | int | — | `environment.cpp` | Incoming glacial transfers. |
| 147 | `moraine_deposition_m` | double `P` | m | `environment.cpp` | Moraine depth. |
| 148 | `deglaciation_age_ka` | double `P` | ka | `environment.cpp` | Nominal deglaciation age (see time caveats). |
| 149 | `landform` | enum string | — | `environment.cpp`, `civilization.cpp` | `LANDFORM_NAMES`. |
| 150 | `soil_type` | enum string | — | `environment.cpp` | `SOIL_NAMES`. |
| 151 | `soil_depth_m` | double `P` | m | `environment.cpp` | Soil depth. |
| 152 | `fertility` | double `max(8, P)` | index | `environment.cpp` | Agricultural fertility index. |
| 153 | `biome` | enum string | — | `environment.cpp` | `BIOME_NAMES`. |
| 154 | `resource` | enum string | — | `environment.cpp`, `civilization.cpp` | `RESOURCE_NAMES`. |
| 155 | `settlement_score` | double `max(8, P)` | index | `settlements.cpp`, `environment.cpp` | Native settlement suitability. Stripped in geo-only. |

The comment at `cpp/src/engine/entity_serialization.cpp:182-184` explains the round-trip choice for fields 44–45 verbatim:

> These two fields jointly determine the discrete ocean mask. Fixed fractional formatting can collapse a one-ULP-below-sea-level water cell to signed zero and make the serialized mask unreplayable.

`Cell::numeric_depression_temporary_lake_deferred` exists in the engine types but is **not** serialized; do not expect it in the document.

---

## Natural entity record families

All natural entity arrays are serialized at plain `float_precision` unless noted.

### `plates[]` — 19 fields (`entity_serialization.cpp:5-45`)

| field | type | units | producer | meaning |
|---|---|---|---|---|
| `id` | int | — | `tectonics.cpp` | Plate id. |
| `kind` | string | — | `tectonics.cpp` | `oceanic` (0) / `continental` (1) / `mixed` (otherwise). |
| `axis` | double[3] `G` | unit sphere | `tectonics.cpp` | Euler rotation axis. |
| `initial_center` | double[3] `G` | unit sphere | `tectonics.cpp` | Step-0 plate center. |
| `center` | double[3] `G` | unit sphere | `tectonics.cpp` | Final plate center. |
| `angular_speed` | double `G` | intrinsic | `tectonics.cpp` | Intrinsic angular speed. |
| `cumulative_rotation_deg` | double `P` | ° | `tectonics.cpp` | Total rotation. |
| `crust_density` | double `P` | g/cm³ | `tectonics.cpp` | Plate crust density parameter. |
| `crust_thickness_km` | double `P` | km | `tectonics.cpp` | Plate crust thickness parameter. |
| `cell_count` | int | — | `tectonics.cpp` | Cells assigned. |
| `area_km2` | double `P` | km² | `tectonics.cpp` | Plate area. |
| `mean_crust_age_ma` | double `P` | Ma | `tectonics.cpp` | Area/cell mean age. |
| `mean_crust_density` | double `P` | g/cm³ | `tectonics.cpp` | Mean density. |
| `mean_crust_thickness_km` | double `P` | km | `tectonics.cpp` | Mean thickness. |
| `dominant_crust_type` | enum string | — | `tectonics.cpp` | `CRUST_NAMES`. |
| `dominant_lithology` | enum string | — | `tectonics.cpp` | `LITHOLOGY_NAMES`. |
| `mean_boundary_activity` | double `P` | index | `tectonics.cpp` | Mean boundary forcing. |
| `mean_heat_flow_mw_m2` | double `P` | mW/m² | `tectonics.cpp` | Mean heat-flow proxy. |
| `thermal_state` | string | — | serializer | `hot_active` if `>= 95`, `warm_active` if `>= 65`, else `cool_stable` (`entity_serialization.cpp:39-40`). |

### `watersheds[]` — 26 fields (`entity_serialization.cpp:428-465`)

`id`, `basin_id`, `outlet_cell_id`, `outlet_type` (`WATERSHED_OUTLET_NAMES`), `is_endorheic`, `cell_count`, `river_cell_count`, `area_km2`, `mean_runoff_mm_y`, `mean_elevation_m`, `max_flow_accumulation`, `centroid_lat_deg`, `centroid_lon_deg`, `min_lat_deg`, `max_lat_deg`, `min_lon_deg`, `max_lon_deg`, `lon_span_deg`, `crosses_antimeridian`, `boundary_perimeter_km`, `dissolved_polygon_area_km2`, `polygon_area_error_fraction`, `compactness_index`, `geometry_quality`, `boundary_cell_ids` (int[]), `boundary_ring` (`[[lat_deg, lon_deg], …]` at `float_precision`).

### `lake_basins[]` — 28 fields (`entity_serialization.cpp:467-506`)

`id`, `depression_component_id`, `outlet_cell_id`, `spill_to_cell_id`, `depression_policy`, `water_body_type`, `is_geologic`, `overflows`, `depression_cell_count`, `cell_count`, `lake_cell_count`, `depression_area_km2`, `geologic_area_fraction`, `area_km2`, `lake_area_km2`, `mean_runoff_mm_y`, `outlet_elevation_m`, `spill_elevation_m`, `max_depression_depth_m`, `mean_water_depth_m`, `fill_fraction`, `storage_capacity_km3`, `annual_runoff_km3`, `overflow_index`, `overflow_stage_count`, `overflow_path_length_km`, `avulsion_risk`, `overflow_path_cell_ids` (int[]).

### `coastal_features[]` — 12 fields (`entity_serialization.cpp:508-531`)

`id`, `cell_id`, `type` (`COASTAL_FEATURE_TYPE_NAMES`), `shoreline_trend` (`SHORELINE_TREND_NAMES`), `lat_deg`, `lon_deg`, `length_km`, `sediment_supply_index`, `wave_energy_index`, `progradation_index`, `migration_rate_m_y`, `longshore_transport_index`.

### `sedimentary_basins[]` — 11 fields (`entity_serialization.cpp:533-555`)

`id`, `basin_id`, `type` (`SEDIMENTARY_BASIN_TYPE_NAMES`), `dominant_resource` (`RESOURCE_NAMES`), `cell_count`, `is_active`, `area_km2`, `mean_sediment_thickness_m`, `max_sediment_thickness_m`, `mean_subsidence_index`, `depositional_age_ma`.

### `stratigraphic_columns[]` — 13 fields + nested `layers[]` (`entity_serialization.cpp:557-599`)

Column: `id`, `basin_id`, `representative_cell_id`, `dominant_facies` (`STRATIGRAPHIC_FACIES_NAMES`), `sequence_phase` (`SEQUENCE_PHASE_NAMES`), `is_active`, `layer_count`, `total_thickness_m`, `depositional_span_ma`, `mean_subsidence_index`, `sediment_flux_index`, `preservation_potential`, `layers`.

`layers[]` — 9 fields: `index`, `facies`, `thickness_m`, `age_top_ma`, `age_base_ma`, `grain_size_index`, `organic_potential`, `reservoir_quality`, `seal_quality`.

### `ice_sheets[]` — 16 fields (`entity_serialization.cpp:601-628`)

`id`, `retreat_stage` (`ICE_RETREAT_STAGE_NAMES`), `cell_count`, `moraine_cell_count`, `area_km2`, `mean_ice_thickness_m`, `max_ice_thickness_m`, `mean_glacial_erosion_m`, `mean_surface_mass_balance_m_y`, `mean_basal_sliding_index`, `mean_ice_velocity_m_y`, `accumulation_area_fraction`, `equilibrium_line_altitude_m`, `retreat_rate_m_y`, `mean_deglaciation_age_ka`, `mean_moraine_deposition_m`.

### `calibration_checks[]` — 9 fields (`process_serialization.cpp:4417-4437`)

`id`, `dataset` (`CALIBRATION_DATASET_NAMES`), `layer` (`CALIBRATION_LAYER_NAMES`), `metric` (`CALIBRATION_METRIC_NAMES`), `passed` (bool), `value`, `target_min`, `target_max`, `score`. Retained in geo-only documents.

---

## Society and history record families

These fifteen arrays are the ones removed entirely by the geo-only path.

| key | record | fields | nested |
|---|---|---|---|
| `settlements` | Settlement (`entity_serialization.cpp:357-383`) | 14: `id`, `cell_id`, `region_id`, `culture_region_id`, `language_region_id`, `type`, `score`, `lat_deg`, `lon_deg`, `biome`, `resource`, `water_body_type`, `fertility`, `is_river` | — |
| `routes` | Route (`:385-402`) | 6: `id`, `from`, `to`, `type`, `distance_km`, `cost` | — |
| `trade_flows` | TradeFlow (`:404-426`) | 11: `id`, `route_id`, `from`, `to`, `region_from`, `region_to`, `primary_good`, `interregional`, `distance_km`, `friction`, `volume_index` | — |
| `political_regions` | PoliticalRegion (`:630-653`) | 12: `id`, `capital_settlement_id`, `type`, `dominant_biome`, `dominant_resource`, `settlement_count`, `route_count`, `settlement_ids`, `area_km2`, `mean_settlement_score`, `mean_elevation_m`, `barrier_pressure` | `settlement_ids` |
| `cultures` | CultureRegion (`:655-686`) | 20: `id`, `language_region_id`, `homeland_region_id`, `type`, `dominant_biome`, `dominant_resource`, `settlement_count`, `sacred_area_count`, `ruin_count`, `settlement_ids`, `area_km2`, `agricultural_area_km2`, `mining_area_km2`, `mean_fertility`, `mean_elevation_m`, `barrier_isolation`, `trade_contact_index`, `migration_pressure`, `continuity_index`, `estimated_age_years` | `settlement_ids` |
| `language_regions` | LanguageRegion (`:688-715`) | 16: `id`, `parent_language_region_id`, `family`, `lineage_depth`, `culture_count`, `settlement_count`, `culture_ids`, `area_km2`, `barrier_isolation`, `trade_contact_index`, `divergence_age_years`, `change_rate`, `phoneme_inventory_size`, `phonological_complexity`, `sound_shift_index`, `inherited_phonology_fraction` | `culture_ids` |
| `sacred_areas` | SacredArea (`:717-736`) | 8: `id`, `cell_id`, `culture_region_id`, `language_region_id`, `type`, `significance`, `lat_deg`, `lon_deg` | — |
| `ruins` | Ruin (`:738-759`) | 10: `id`, `cell_id`, `culture_region_id`, `language_region_id`, `type`, `abandonment_reason`, `significance`, `preservation_score`, `lat_deg`, `lon_deg` | — |
| `historical_eras` | HistoricalEra (`:761-782`) | 10: `id`, `dominant_process`, `event_count`, `state_event_count`, `migration_event_count`, `language_event_count`, `start_year_bp`, `end_year_bp`, `mean_instability`, `mean_connectivity` | — |
| `historical_events` | HistoricalEvent (`:784-808`) | 13: `id`, `era_id`, `type`, `region_id`, `related_region_id`, `culture_region_id`, `related_culture_region_id`, `language_region_id`, `related_language_region_id`, `cell_id`, `year_bp`, `pressure_index`, `continuity_index` | — |
| `population_regions` | PopulationRegion (`:810-835`) | 14: `id`, `region_id`, `culture_region_id`, `language_region_id`, `settlement_count`, `carrying_capacity`, `estimated_population`, `agricultural_capacity_index`, `water_security_index`, `urbanization_fraction`, `growth_rate_per_year`, `population_pressure`, `migration_balance`, `hazard_mortality_index` | — |
| `conflicts` | ConflictRecord (`:837-871`) | 23: `id`, `era_id`, `region_a`, `region_b`, `culture_a`, `culture_b`, `cause`, `outcome`, `contested_cell_id`, `start_year_bp`, `end_year_bp`, `war_duration_years`, `intensity`, `resource_pressure`, `water_stress`, `trade_chokepoint_index`, `region_a_force_estimate`, `region_b_force_estimate`, `mobilized_population`, `casualty_rate`, `logistics_strain_index`, `economic_disruption_index`, `estimated_casualties` | — |
| `dynasties` | DynastyRecord (`:873-902`) | 18: `id`, `region_id`, `culture_region_id`, `language_region_id`, `parent_dynasty_id`, `founder_dynasty_id`, `successor_dynasty_id`, `founding_event_id`, `collapse_reason`, `lineage_depth`, `child_dynasty_count`, `child_dynasty_ids`, `start_year_bp`, `end_year_bp`, `duration_years`, `legitimacy_index`, `succession_pressure`, `dynastic_continuity_index` | `child_dynasty_ids` |
| `territorial_snapshots` | TerritorialSnapshot (`:935-957`) | 11: `id`, `era_id`, `dominant_process`, `region_count`, `largest_region_id`, `regions`, `year_bp`, `assigned_land_fraction`, `estimated_population`, `largest_region_area_km2`, `fragmentation_index` | `regions[]` |
| `borders` | BorderSegment (`process_serialization.cpp:4439-4459`) | 8: `id`, `region_a`, `region_b`, `cell_a`, `cell_b`, `type`, `length_km`, `barrier_score` | — |

`territorial_snapshots[].regions[]` — SnapshotRegion, 18 fields (`entity_serialization.cpp:904-933`): `region_id`, `capital_settlement_id`, `culture_region_id`, `language_region_id`, `cell_count`, `crosses_antimeridian`, `boundary_cell_ids`, `boundary_ring`, `area_km2`, `boundary_perimeter_km`, `dissolved_polygon_area_km2`, `polygon_area_error_fraction`, `compactness_index`, `geometry_quality`, `estimated_population`, `stability_index`, `centroid_lat_deg`, `centroid_lon_deg`.

---

## Model and contract sections

Sixteen top-level objects are purely declarative: they publish the model type, its parameters, and its stated limitations, plus (in most cases) run-level totals. They contain no per-step data.

| section | `model_type` / `clock_type` / `model` string | declared limitation string | source |
|---|---|---|---|
| `climate_model` | `equilibrium_latitude_circulation_climate_v5` | `equilibrium_diagnostic_climate_without_mass_conserving_three_dimensional_atmosphere` | `process_serialization.cpp:369-449` |
| `hydrologic_water_budget_model` | `causal_land_climate_loss_partition_v1` | `empirical_annual_loss_partition_without_transient_soil_moisture_groundwater_return_flow_or_calibrated_time` | `:451-548` |
| `simulation_clock` | `coupled_geodynamic_stage_clock_v12` | `nominal_geological_intervals_without_calibrated_physical_time_or_timestep_convergence` | `:2056-2137` |
| `sediment_interface_model` | `explicit_bedrock_surface_mobile_sediment_interface_v1` | (no `model_limitation`; declares canonical/derived fields and a replay tolerance model) | `:1823-1872` |
| `sediment_inventory_model` | `finite_alluvium_bedrock_sediment_inventory_v1` | `bulk_inventory_without_grain_classes_calibrated_time_shared_boundary_flux_or_subcell_channels` | `:1874-2054` |
| `hillslope_sediment_transport_model` | `pairwise_lithology_dependent_volume_conserving_hillslope_transport_v2` | `procedural_bulk_transport_without_calibrated_time_shared_boundary_flux_or_grain_classes` | `:1087-1229` |
| `glacial_sediment_transport_model` | `downhill_area_conserving_glacial_sediment_transport_v2` | `single_post_erosion_bulk_transfer_without_calibrated_time_multistep_ice_dynamics_or_grain_classes` | `:800-910` |
| `fluvial_sediment_routing_model` | `topological_capacity_limited_fluvial_sediment_routing_v1` | `dimensionless_capacity_proxy_without_grain_size_calibrated_time_or_subcell_channels` | `:1406-1541` |
| `plate_kinematic_model` | `rotating_voronoi_plate_domains_v3` | `kinematic_domains_with_conservative_first_order_crust_transport_rule_based_boundary_processes_partial_reference_timestep_scaling_and_uncalibrated_physical_time` | `:2613-2944` |
| `plate_boundary_segment_model` | `exact_directed_reciprocal_control_volume_boundary_segments_v2` | `kinematic_candidate_evidence_only_without_physical_polarity_slab_geometry_material_fate_or_feedback_into_smoothed_cell_boundary_forcing` | `:2945-3151` |
| `initial_oceanic_crust_age_model` | `multi_source_nominal_ridge_graph_travel_time_v1` | `procedural_graph_distance_age_initialization_using_one_global_nominal_half_spreading_rate_without_physical_plate_reconstruction_flowlines_or_crust_creation_and_destruction_history` | `:2410-2510` |
| `crust_overlap_candidate_fate_model` | `sparse_membership_class_to_uniform_boundary_plate_pair_candidate_v1` | `diagnostic_candidate_crosswalk_only_without_connected_fragment_localization_physical_fate_slab_geometry_swept_area_or_state_transfer` | `:3152-3257` |
| `oceanic_age_depth_model` | `continuity_adjusted_parsons_sclater_relative_basement_subsidence_v1` (key is `model`, not `model_type`) | (no `model_limitation`; uses a bank of explicit `*_represented` / `*_calibrated` flags) | `:3259-3346` |
| `sea_level_model` | `volume_constrained_connectivity_ocean_flood_v3` | `cell_column_volume_without_subcell_bathymetry_straits_or_exact_coast_polygons` | `:3348-3465` |
| `crust_material_shadow_model` | `persistent_sparse_surface_crust_mass_shadow_v1`, `mode = "shadow"` | (declares residual semantics as a numerical closure diagnostic, not a physical source/sink) | `:164-220` |
| `crust_dry_rock_accounting_model` | `finite_three_reservoir_dry_rock_accounting_v1`, `mode = "finite_accounting_shadow"` | (declares safety limits as memory limits, not physical flux limits) | `crust_reservoir_serialization.cpp:108-195` |

Two of these deserve a closer look because downstream code depends on their declared invariants.

**`sediment_interface_model`** (`process_serialization.cpp:1835-1869`) publishes the canonical/derived split explicitly:

| key | value |
|---|---|
| `canonical_state_fields` | `["bedrock_surface_elevation_m","sediment_thickness_m"]` |
| `derived_surface_field` | `elevation_m` |
| `interface_equation` | `elevation_m=bedrock_surface_elevation_m+sediment_thickness_m` |
| `bedrock_surface_semantics` | `top_of_nonmobile_bedrock_below_mobile_sediment_not_moho_or_stratigraphic_basement` |
| `sea_level_datum_update` | bedrock shifts by `-sea_level_adjustment_m`; sediment thickness is unchanged |
| `replay_tolerance_model` | `decimal_quantization_forward_error_by_serialized_operand_precision_v1` |
| `canonical_state_serialization_decimal_places` | `10` |
| `minimum_replay_operand_serialization_decimal_places` | `8` |
| `maximum_final_closure_residual_m` | measured, at `surface_precision = max(10, float_precision)` |

**`sediment_inventory_model`** additionally carries a nested `process_source_partition` object keyed `hillslope` / `fluvial` / `glacial` / `numeric_breach`, each with `gross_mobilization_volume_km3`, `alluvium_entrainment_volume_km3`, `bedrock_erosion_volume_km3`, `source_partition_residual_km3` (`process_serialization.cpp:2021-2051`).

---

## Explicit `false` flags and what they mean

The document is deliberately built so that **every unresolved physical claim is a serialized `false`, not an omission**. A consumer that treats these sections as physics without reading the flags will over-claim. The complete inventory of literal `false` booleans (all verified by line):

| section | flag | line |
|---|---|---|
| shared nominal-time block (7 ledgers) | `nominal_time_calibrated`, `physical_time_resolved` | `process_serialization.cpp:158-159` |
| `crust_material_shadow_model` | `authoritative_for_cell_state`, `physical_source_sink_resolved`, `material_provenance_resolved`, `solid_volume_resolved`, `phase_resolved`, `mass_weighted_age_resolved`, `upper_mantle_exchange_reservoir_resolved`, `subducted_slab_reservoir_resolved`, `global_crust_cycle_mass_conservation_resolved` | `:206-215` |
| `climate_model` | `mass_conserving_atmosphere`, `transient_climate_resolved` | `:443-444` |
| `hydrologic_water_budget_model` | `physical_time_resolved` | `:511` |
| `glacial_sediment_transport_model` | `source_partition_audit_is_mass_claim`, `source_partition_audit_is_provenance_claim`, `physical_time_resolved`, `multi_step_ice_dynamics_resolved` | `:867-880` |
| `hillslope_sediment_transport_model` | `source_partition_audit_is_mass_claim`, `source_partition_audit_is_provenance_claim`, `time_step_convergence_demonstrated`, `physical_time_resolved`, `shared_boundary_geometry_resolved` | `:1165-1189` |
| `fluvial_sediment_routing_model` | `source_partition_audit_is_mass_claim`, `source_partition_audit_is_provenance_claim`, `time_step_convergence_demonstrated`, `grain_size_resolved`, `physical_time_resolved`, `subcell_channel_geometry_resolved` | `:1478-1489` |
| `sediment_interface_model` | `dry_rock_mass_resolved`, `sediment_density_resolved`, `porosity_resolved`, `compaction_resolved`, `grain_provenance_resolved`, `chemical_weathering_resolved` | `:1860-1865` |
| `sediment_inventory_model` | `same_stage_deposition_available_for_entrainment`, `time_step_convergence_demonstrated`, `dry_rock_mass_resolved`, `sediment_density_resolved`, `porosity_resolved`, `compaction_resolved`, `grain_provenance_resolved`, `chemical_weathering_resolved`, `physical_time_resolved` | `:1975-1988` |
| `simulation_clock` | `physical_time_resolved`, `nominal_time_calibrated`, `absolute_geological_age_resolved`, `process_rate_calibration_resolved`, `time_step_convergence_demonstrated`, `cryosphere_advances_nominal_time` | `:2083-2117` |
| `initial_oceanic_crust_age_model` | `independent_replay_inputs_unconditionally_exposed`, `physical_seafloor_creation_resolved`, `spreading_rate_calibrated`, `local_spreading_rates_resolved`, `ridge_flowlines_resolved`, `subduction_sink_history_resolved`, `convergence_history_resolved`, `seton_2020_age_grid_used_as_generation_input` | `:2495-2503` |
| `plate_kinematic_model` | `physical_time_resolved`, `nominal_time_calibrated`, `process_rate_calibration_resolved`, `time_step_convergence_demonstrated`, `destination_overlap_areas_normalized`, `equilibrium_target_difference_clamped`, `equilibrium_operator_physical_time_calibrated`, `tectonic_process_material_provenance_resolved` | `:2686-2929` |
| `plate_boundary_segment_model` | `nominal_time_calibrated`, `physical_time_resolved`, `physical_plate_velocity_calibrated`, `polarity_candidate_is_physical_decision`, `physical_subduction_polarity_resolved`, `physical_slab_geometry_resolved`, `slab_selection_resolved`, `slab_transfer_resolved`, `physical_material_fate_resolved`, `boundary_segments_drive_slab_transfers` | `:3135-3145` |
| `crust_overlap_candidate_fate_model` | `candidate_allocation_authoritative`, `pair_evidence_standalone_physical_provenance_complete`, `physical_polarity_authoritative`, `physical_polarity_resolved`, `physical_material_fate_authoritative`, `physical_material_fate_resolved`, `slab_selection_authoritative`, `slab_selection_resolved`, `slab_transfer_authoritative`, `slab_transfer_resolved`, `state_mutation_performed`, `crust_material_shadow_mutation_performed`, `crust_reservoir_mutation_performed`, `swept_area_calculated`, `local_segment_link_resolved`, `connected_atom_topology_resolved`, `local_fragment_topology_resolved` | `:3230-3252` |
| `oceanic_age_depth_model` | `derivative_continuity_at_transition_resolved`, `authoritative_for_realized_thermal_relief_component`, `realized_thermal_relief_state_tracked`, `thermal_relaxation_timescale_calibrated`, `unapplied_thermal_tendency_residual_carried_forward`, `absolute_basement_depth_calibrated`, `physical_crust_creation_age_provenance`, `ridge_age_distance_consistency`, `thermal_structure_represented`, `heat_flow_represented`, `dynamic_topography_represented`, `flexure_represented`, `physical_dynamics_represented` | `:3320-3343` |
| `crust_dry_rock_accounting_model` | `capacity_geophysically_calibrated`, `mantle_origin_packets_homogenized`, `mantle_spatial_transport_resolved`, `operational_safety_limits_are_physical_flux_limits`, `authoritative_for_cell_state`, `physical_source_sink_resolved`, `material_provenance_resolved`, `upper_mantle_exchange_reservoir_resolved`, `subducted_slab_reservoir_resolved`, `global_crust_cycle_mass_conservation_resolved`, `solid_volume_resolved`, `phase_resolved`, `mass_weighted_age_resolved`, `sediment_coupled`, `coverage_membership_fate_resolved`, `subduction_polarity_resolved` | `crust_reservoir_serialization.cpp:135-192` |
| `crust_dry_rock_accounting_history[].ordered_reason_transactions[]` | `physical_source_sink_resolved` (per reason record) | `crust_reservoir_serialization.cpp:99` |
| `backend` | `crust_overlap_continuous_shadow_authoritative`, `crust_overlap_continuous_shadow_result_used_for_state`, `crust_overlap_accelerator_geometry_parity_demonstrated`, `crust_overlap_accelerator_coverage_membership_parity_demonstrated`, `crust_overlap_accelerator_categorical_parity_demonstrated`, `crust_overlap_accelerator_complete_parity_demonstrated`, `crust_overlap_accelerator_state_authoritative` | `cpp/src/opencl_compute.cpp:2136-2174` |

The small set of flags that are deliberately `true` is equally load-bearing, because it marks what *is* claimed: `transport_provenance_shadow_resolved` and `ordered_rule_mass_adjustments_exposed` (`:216-217`), `cell_mass_balance_closed` and `runoff_computed_before_flow_routing` (`:509-510`), `authoritative_interface_geometry` / `bedrock_surface_elevation_is_canonical` / `mobile_sediment_thickness_is_canonical` / `surface_elevation_is_derived` / `final_interface_closure_validated` (`:1856-1869`), `mass_conserving` with `mass_conserving_semantics = "bulk_reference_volume_only_not_dry_rock_mass"` (`:1979-1981`), `crust_advection_resolved` (`:2837`), `reciprocal_segment_identity_resolved` (`:3130`), `deterministic_crosswalk_authoritative` scoped to `serialized_pair_consensus_and_membership_class_diagnostic_mapping_only` (`:3227-3229`), `destination_endpoint_incidence_resolved` (`:3232`), `continuity_at_transition_resolved` (`:3319`), `procedural_authority` and `path_decision_witness_exposed` (`:2492-2493`), and the dry-rock block's `closed_three_reservoir_dry_rock_accounting` / `per_origin_accounting_closed` / `finite_exchange_inventory_enforced` / `proxy_compensations_exposed` (`crust_reservoir_serialization.cpp:176-179`).

---

## Process and history ledger families

Nine array ledgers plus one single-object ledger. Every record family below is described by its actual emitted field order.

### `hydrologic_water_budget_history[]` — 43 fields (`process_serialization.cpp:550-648`)

Prefix: `id`, `feedback_stage_id`, `stage`, `erosion_iteration`, `stabilization_recomputation_index`. Then the 12-field nominal-time block with role `stage_end_stabilization_recomputation_snapshot`. Then `cell_count`, `land_cell_count`, `marine_cell_count`, `land_precipitation_volume_km3_y`, `actual_evapotranspiration_volume_km3_y`, `infiltration_volume_km3_y`, `runoff_volume_km3_y`, `mass_balance_residual_km3_y`, `max_abs_cell_residual_mm_y`. Then **17 parallel by-cell arrays** all of length `cell_count`, indexed positionally against `cell_ids`: `cell_ids`, `is_marine_by_cell`, `lithology_by_cell`, `cell_area_km2_by_cell`, `elevation_m_by_cell`, `temperature_c_by_cell`, `precipitation_mm_y_by_cell`, `local_relief_m_by_cell`, `sediment_thickness_m_by_cell`, `ice_thickness_m_by_cell`, `potential_evapotranspiration_mm_y_by_cell`, `infiltration_capacity_index_by_cell`, `actual_evapotranspiration_mm_y_by_cell`, `infiltration_mm_y_by_cell`, `water_balance_mm_y_by_cell`, `runoff_mm_y_by_cell`, `residual_mm_y_by_cell`.

Precision: volume fields at `max(12, float_precision)`; all other doubles and every array at `max(10, float_precision)` (`process_serialization.cpp:555-556`).

### `earth_system_feedback_history[]` — 118 fields (`process_serialization.cpp:2139-2409`)

`id`, `stage`, `erosion_iteration`, then the nominal-time block whose role is `initial_state_snapshot` (stage `initial_climate_hydrology`), `erosion_transition` (stage `erosion_iteration`), or `final_cryosphere_coupling_snapshot` (`:2154-2160`). Then:

- 9 boolean stage flags: `sea_level_recomputed`, `climate_recomputed`, `hydrologic_water_budget_recomputed`, `hydrology_recomputed`, `erosion_applied`, `cryosphere_applied`, `plate_motion_applied`, `crust_transport_applied`, `crust_evolution_applied`.
- 32 counters: the four `*_recompute_count`, the eight numeric-depression correction/breach/temporary-lake counters, the five fluvial, five hillslope and five glacial edge/cell counters, `plate_motion_history_id`, `cell_count`, `land_cell_count`, `water_cell_count`, `river_cell_count`.
- `sea_level_adjustment_m` — the datum shift applied at this stage.
- Volume and residual blocks for numeric depression, fluvial, hillslope, glacial, and the sediment inventory (`sediment_alluvium_entrainment_volume_km3`, `sediment_bedrock_erosion_volume_km3`, `sediment_inventory_volume_km3`, `sediment_source_partition_residual_km3`, `sediment_inventory_mass_balance_residual_km3`).
- State aggregates: `surface_area_km2`, `ocean_area_km2`, `ocean_volume_km3`, `ocean_fraction`, `mean_elevation_m`, `mean_land_elevation_m`, `min_elevation_m`, `max_elevation_m`, `mean_temperature_c`, `mean_precipitation_mm_y`, `mean_runoff_mm_y`, `hydrologic_land_precipitation_volume_km3_y`, `hydrologic_actual_evapotranspiration_volume_km3_y`, `hydrologic_infiltration_volume_km3_y`, `hydrologic_runoff_volume_km3_y`, `hydrologic_water_budget_residual_km3_y`, `max_abs_hydrologic_water_budget_cell_residual_mm_y`, `mean_stream_power_response_m_per_reference_step`, `mean_sediment_thickness_m`, `mean_cumulative_sediment_{production,deposition,export}_m`, `cumulative_sediment_{production,deposition,export}_volume_km3`.
- Four convergence deltas: `mean_abs_elevation_change_m_from_previous_stage`, `mean_abs_temperature_change_c_from_previous_stage`, `mean_abs_precipitation_change_mm_y_from_previous_stage`, `mean_abs_runoff_change_mm_y_from_previous_stage`.

### `numeric_depression_correction_history[]` — 56 fields plus the 12-field nominal block, 68 in total (`process_serialization.cpp:650-799`)

`id`, `feedback_stage_id`, `stage`, `erosion_iteration`, `stabilization_pass`, nominal block (role `stage_end_stabilization_event`), then: `correction_method` (`bounded_mass_conserving_breach_with_local_deposition_v1` or `zero_material_temporary_numeric_lake_deferral_v1`), `fill_candidate_model` (`priority_flood_full_depression_fill_candidate_v1`), `source_depression_policy`, `source_depression_component_id`, `sink_cell_id`, `sink_crust_type`, `sink_is_geologic`, `sink_boundary_divergent`, `sink_boundary_convergent`, `cell_count`, `cell_ids`, `elevation_before_fill_m_by_cell`, `sediment_thickness_before_correction_m_by_cell`, `fill_depth_m_by_cell`, `elevation_after_fill_m_by_cell`, `area_km2`, `fill_volume_km3`, `max_fill_depth_m`, `fill_candidate_applied`, `temporary_numeric_lake_selected`, `breach_diagnostic_model` (`weighted_graph_excavation_proxy_monotone_lower_outlet_v1`), `breach_gradient_step_m`, `breach_feasible`, `breach_outlet_cell_id`, `breach_path_cell_ids`, `breach_elevation_before_m_by_cell`, `breach_target_elevation_m_by_cell`, `breach_excavation_depth_m_by_cell`, `breach_sediment_thickness_before_excavation_m_by_cell`, `breach_alluvium_entrainment_depth_m_by_cell`, `breach_bedrock_erosion_depth_m_by_cell`, `breach_path_length_km`, `breach_excavation_area_km2`, `breach_excavation_volume_km3`, `max_breach_excavation_depth_m`, `breach_to_fill_volume_ratio`, `breach_has_lower_adjustment_volume`, `breach_depth_bound_passed`, `breach_deposition_capacity_sufficient`, `breach_same_pass_conflict_free`, `breach_deposition_capacity_km3`, `breach_deposition_cell_count`, `breach_deposition_cell_ids`, `breach_deposition_depth_m_by_cell`, `applied_breach_excavation_volume_km3`, `applied_breach_deposition_volume_km3`, `applied_alluvium_entrainment_volume_km3`, `applied_bedrock_erosion_volume_km3`, `correction_mass_balance_residual_km3`, `lower_adjustment_volume_method` (`breach` / `fill`), `selected_correction_method` (`mass_conserving_breach` / `temporary_numeric_lake`). Surface fields at `max(12, float_precision)` (`:655`).

### `hillslope_sediment_transport_history[]` (`process_serialization.cpp:1230-1405`)

Step scalars: `id`, `feedback_stage_id`, `erosion_iteration`, nominal block (role `erosion_interval_bulk_hillslope_transport`), `transport_edge_count`, `cell_count`, `source_cell_count`, `target_cell_count`, `land_to_land_edge_count`, `land_to_marine_edge_count`, `production_volume_km3`, `deposition_volume_km3`, `alluvium_entrainment_volume_km3`, `bedrock_erosion_volume_km3`, `source_production_depth_m_by_cell`, `alluvium_entrainment_depth_m_by_cell`, `bedrock_erosion_depth_m_by_cell`, `mass_balance_residual_km3`, `max_source_production_depth_m`, `max_target_deposition_depth_m`, `mean_effective_diffusivity`, `input_cell_count`, `input_cells`, `edges`.

- `input_cells[]` — 6: `cell_id`, `lithology`, `is_water`, `is_lake`, `elevation_m`, `sediment_thickness_m`.
- `edges[]` — 21: `id`, `mesh_edge_cell_a_id`, `mesh_edge_cell_b_id`, `source_cell_id`, `target_cell_id`, `source_lithology`, `source_neighbor_count`, `source_is_water`, `target_is_water`, `target_is_lake`, `source_area_km2`, `target_area_km2`, `source_elevation_m`, `target_elevation_m`, `elevation_drop_m`, `source_lithology_resistance`, `effective_diffusivity`, `source_production_depth_m`, `target_deposition_depth_m`, `transfer_volume_km3`, `mass_balance_residual_km3`.

Precision: volumes at `max(10, float_precision)`, surface depths at `max(8, float_precision)` (`:1235-1236`).

### `glacial_sediment_transport_history[]` (`process_serialization.cpp:911-1086`)

There is exactly one stage; the serializer throws if `feedback_stage_id != erosion_iterations + 1` (`:925-929`). Fields: `id`, `feedback_stage_id`, nominal block (role `final_cryosphere_coupling_bulk_transport`), `transfer_count`, `cell_count`, `source_cell_count`, `target_cell_count`, `land_target_transfer_count`, `marine_target_transfer_count`, `production_volume_km3`, `deposition_volume_km3`, `alluvium_entrainment_volume_km3`, `bedrock_erosion_volume_km3`, `source_production_depth_m_by_cell`, `alluvium_entrainment_depth_m_by_cell`, `bedrock_erosion_depth_m_by_cell`, `mass_balance_residual_km3`, `terrain_volume_change_residual_km3`, `max_source_production_depth_m`, `max_target_deposition_depth_m`, `input_cell_count`, `input_cells`, `transfers`, `post_transport_elevation_m_by_cell`.

- `input_cells[]` — 7: `cell_id`, `glacier_flow_to_cell_id`, `is_water`, `elevation_m`, `ice_thickness_m`, `glacial_erosion_m`, `sediment_thickness_m`.
- `transfers[]` — 15: `id`, `source_cell_id`, `target_cell_id`, `target_is_water`, `source_area_km2`, `target_area_km2`, `source_elevation_m`, `target_elevation_m`, `elevation_drop_m`, `source_ice_thickness_m`, `source_glacial_erosion_m`, `source_production_depth_m`, `target_deposition_depth_m`, `transfer_volume_km3`, `mass_balance_residual_km3`.

### `fluvial_sediment_routing_history[]` (`process_serialization.cpp:1542-1822`)

Step scalars: `id`, `feedback_stage_id`, `erosion_iteration`, nominal block (role `erosion_interval_bulk_fluvial_routing`), `active_cell_step_count`, `cell_count`, `routed_edge_count`, `land_terminal_count`, `marine_terminal_count`, `terminal_allocation_count`, `accumulation_scale`, `local_source_volume_km3`, `routed_throughput_volume_km3`, `capacity_deposition_volume_km3`, `depression_fill_deposition_volume_km3`, `lake_trap_deposition_volume_km3`, `terminal_land_deposition_volume_km3`, `marine_deposition_volume_km3`, `terminal_export_volume_km3`, `alluvium_entrainment_volume_km3`, `bedrock_erosion_volume_km3`, `source_production_depth_m_by_cell`, `alluvium_entrainment_depth_m_by_cell`, `bedrock_erosion_depth_m_by_cell`, `total_deposition_volume_km3`, `mass_balance_residual_km3`, `input_cell_count`, `input_cells`, `cell_steps`, `terminal_allocations`.

- `input_cells[]` — 15: `cell_id`, `flow_to_cell_id`, `depression_component_id`, `depression_sink_cell_id`, `water_body_type`, `is_water`, `is_river`, `is_lake`, `lake_overflows`, `cell_area_km2`, `flow_accumulation`, `runoff_mm_y`, `hydrologic_flow_slope`, `routing_base_elevation_m`, `spill_elevation_m`.
- `cell_steps[]` — 30: `cell_id`, `flow_to_cell_id`, `depression_component_id`, `depression_sink_cell_id`, `water_body_type`, `is_water`, `is_river`, `is_lake`, `lake_overflows`, `is_land_terminal`, `is_marine_terminal`, `cell_area_km2`, `flow_accumulation`, `runoff_mm_y`, `hydrologic_flow_slope`, `routing_base_elevation_m`, `spill_elevation_m`, `local_source_volume_km3`, `incoming_volume_km3`, `available_volume_km3`, `transport_capacity_fraction`, `depression_accommodation_volume_km3`, `capacity_deposition_volume_km3`, `depression_fill_deposition_volume_km3`, `lake_trap_deposition_volume_km3`, `marine_deposition_volume_km3`, `routed_outgoing_volume_km3`, `terminal_land_storage_volume_km3`, `terminal_export_volume_km3`, `local_mass_balance_residual_km3`.
- `terminal_allocations[]` — 11: `sink_cell_id`, `target_cell_id`, `depression_component_id`, `target_area_km2`, `routing_base_elevation_m`, `spill_elevation_m`, `prior_local_deposition_volume_km3`, `accommodation_before_allocation_km3`, `accommodation_deposition_volume_km3`, `excess_aggradation_volume_km3`, `total_deposition_volume_km3`.

This family is the one exception to the "history is presentation-only" rule. The serializer comment at `process_serialization.cpp:1547-1551` states it plainly:

> These history values are replay operands, not presentation-only diagnostics. Preserve a round-trip representation so downstream validators can independently recompute routing branches and terminal allocations without accepting a scale-relative tolerance large enough to conceal a material-volume mutation.

Consequently `evidence_precision = max(max_digits10, float_precision)` is applied to **all** volumes and surface depths in the family (`:1552-1558`).

### `initial_oceanic_crust_age_ledger` — single object, 28 fields (`process_serialization.cpp:2512-2611`)

`source_plate_motion_history_id` (always `0`), `cell_count`, `oceanic_like_cell_count`, `non_oceanic_like_cell_count`, `eligible_ridge_segment_count`, `ridge_seed_cell_count`, `reachable_oceanic_like_cell_count`, `unreachable_oceanic_like_cell_count`, `reachable_ceiling_clamped_cell_count`, `ceiling_assigned_cell_count`, `eligible_ridge_total_length_km`, `opening_rate_length_sum_km2_per_ma`, `representative_full_spreading_rate_km_per_ma`, `representative_half_spreading_rate_km_per_ma`, `maximum_age_ma`, `oceanic_like_area_km2`, `area_weighted_mean_age_ma`, `minimum_oceanic_like_age_ma`, `maximum_oceanic_like_age_ma`, `eligible_ridge_segment_ids`, `ridge_seed_cell_ids`, `age_ma_by_cell`, `unclamped_graph_age_ma_by_cell`, `status_id_by_cell`, `predecessor_cell_id_by_cell`, `origin_ridge_seed_cell_id_by_cell`, `cdf_thresholds_ma`, `area_weighted_cdf_le_threshold`.

Every double scalar and every double array goes through `roundtrip_num` / `roundtrip_double_array_json`; the integer counters and the integer arrays (`eligible_ridge_segment_ids`, `ridge_seed_cell_ids`, `status_id_by_cell`, `predecessor_cell_id_by_cell`, `origin_ridge_seed_cell_id_by_cell`) are emitted as exact integers. The serializer throws `"initial oceanic crust age ledger is internally inconsistent"` if array lengths or the reachable/unreachable partition do not close (`:2515-2543`). `status_id_by_cell` indexes `status_id_order = ["not_oceanic_like","ridge_seed","ridge_reachable","ridge_reachable_ceiling_clamped","unresolved_no_active_ridge_path_ceiling"]`, and `unclamped_graph_age_unavailable_sentinel` documents `-1` for non-oceanic-like or unreachable cells (`:2476-2479`).

### `plate_motion_history[]` — the largest family (`process_serialization.cpp:3467-4415`)

Step scalars: `id`, `stage`, `erosion_iteration`, nominal block (role `initial_plate_state_snapshot` for stage `initial_plate_domains`, else `plate_motion_transition`), `cell_count`, `plate_count`, `reassigned_cell_count`, `reassigned_cell_fraction`, `plate_boundary_cell_count`, `plate_boundary_edge_count`, `reciprocal_mesh_segment_count`, `boundary_segment_count`, `control_volume_boundary_incident_cell_count`, `accreted_terrane_cell_count`, `aged_oceanic_cell_count`, `rejuvenated_oceanic_cell_count`, `subducted_oceanic_cell_count`, `mean_plate_rotation_deg`, `max_plate_rotation_deg`, `mean_crust_transport_distance_km`, `max_crust_transport_distance_km`, nine `mean_abs_crust_*_change*` aggregates, `mean_tectonic_elevation_change_m`, `mean_abs_tectonic_elevation_change_m`, `max_abs_tectonic_elevation_change_m`, `cell_plate_ids`.

Precision split: step aggregates use `history_precision = max(6, float_precision)` (`:3472`), **except** the three tectonic-elevation-change scalars, which are at `max_digits10` (`:3519-3527`).

Then five nested structures:

1. **`crust_overlap_ledger`** (object, `transport_precision = max_digits10` throughout, `:3530`). Declares `format = "destination_csr_spherical_forward_overlap_v1"`, `coverage_model = "destination_local_gnomonic_line_arrangement_multiplicity_v1"`, units, `density_weighted_crust_volume_to_mass_kg_factor` (`1.0e12`), `transport_conservation_scope = "source_to_transported_pre_process"`, `post_process_inventory_semantics = "state_snapshot_not_transport_conservation_target"`. CSR arrays: `destination_offsets`, `source_cell_ids`, `overlap_area_km2`, `remap_residual_distance_km`, `source_kinematic_distance_km`. Per-cell arrays: `dominant_source_cell_ids`, `contributor_count_by_cell`, `dominant_source_volume_fraction_by_cell`, `coverage_area_sum_km2_by_cell`, `covered_union_area_km2_by_cell`, `uncovered_gap_area_km2_by_cell`, `overlap_excess_area_km2_by_cell`, `maximum_coverage_multiplicity_by_cell`, `coverage_arrangement_line_count_by_cell`, `coverage_arrangement_fragment_count_by_cell`, `coverage_membership_area_class_count_by_cell`, plus totals. Sub-ledger **`coverage_membership_area_class_ledger`** carries its own `format`/`model`/`class_order`/`coalescing_key`/`representative_model`/`representative_available_semantics`/`source_plate_id_semantics`/`edge_area_reconstruction_tolerance_basis`/`raw_arrangement_fragment_count_location`/`area_unit`, CSR arrays `destination_offsets`, `area_km2`, `multiplicity`, `representative_unit_x/_y/_z`, `representative_available`, `contributor_offsets`, `source_cell_ids`, `source_plate_ids`, and five resolution flags of which only `source_membership_resolved` is `true` — `connected_fragment_topology_resolved`, `physical_fate_resolved`, `slab_selection_resolved` and `local_kinematics_resolved` are all `false` (`process_serialization.cpp:3717-3726`). The ledger closes with `global_coverage_area_km2_by_multiplicity`, the five `remapped_*_by_cell` arrays, the closure errors, and four extensive-delta objects `source_inventory` / `transported_inventory` / `post_process_inventory` / `process_inventory_delta` (each `{crust_volume_km3, density_weighted_crust_volume, crust_age_volume_moment_km3_ma}` — `crust_extensive_delta_json`, `:19-44`), plus **`process_inventory_attribution`** (`format = "sequential_rule_extensive_state_delta_v1"`, `semantics = "ordered_rule_state_moment_changes_not_physical_material_provenance"`, `order_dependent`, `reasons[]`, `attributed_inventory_delta`, `numerical_closure_residual`, `reconciled_inventory_delta`). Each `reasons[]` record: `reason`, `triggered_cell_count`, `extensive_state_changed_cell_count`, `positive_delta`, `negative_delta_magnitude`, `net_delta`.
2. **`crust_overlap_candidate_fate_ledger`** (object): `format`, `source_plate_assignment_step_id`, `boundary_plate_assignment_step_id`, `boundary_pair_evidence[]` (`pair_id`, `plate_low_id`, `plate_high_id`, `segment_ids`, `physical_consensus_status`, `physical_subducting_plate_id`, `physical_overriding_plate_id`, `heuristic_consensus_status`, `heuristic_subducting_plate_id`, `heuristic_overriding_plate_id`), `overlap_class_candidates[]` (`membership_area_class_id`, `destination_cell_id`, `multiplicity`, `boundary_pair_evidence_id`, `assignment_status`, `candidate_subducting_contributor_id`, `candidate_overriding_contributor_id`), then `physical_polarity_backed_candidate_excess_area_km2`, `oceanic_heuristic_candidate_excess_area_km2`, `unresolved_candidate_excess_area_km2`, `accounted_overlap_excess_area_km2`, `candidate_partition_residual_km2`.
3. **`boundary_segments[]`** — 67 fields per segment: `segment_id`, `mesh_segment_id`, `left_cell_id`, `right_cell_id`, `left_edge_index`, `right_edge_index`, `left_plate_id`, `right_plate_id`, the nine geometry unit components (`start_unit_x/_y/_z`, `midpoint_unit_x/_y/_z`, `end_unit_x/_y/_z`), `tangent_unit_x/_y/_z`, `left_to_right_normal_unit_x/_y/_z`, `angular_length_rad`, `length_km`, the six Euler-velocity components, the three `relative_velocity_*_km_per_ma`, `signed_opening_rate_km_per_ma`, `signed_convergence_rate_km_per_ma`, `signed_slip_rate_km_per_ma`, `signed_opening_index`, `signed_convergence_index`, `signed_slip_index`, `direct_convergent_strength`, `direct_divergent_strength`, `direct_transform_strength`, `direct_boundary_class`, `convergence_active`, the fourteen `left_opening_*` / `right_opening_*` crust-state fields (`crust_type`, `lithology`, `crust_age_ma`, `crust_thickness_km`, `crust_density_g_cm3`, `crust_state_available`, `oceanic_like` on each side), `polarity_candidate_status`, `candidate_subducting_side`, `candidate_overriding_side`, `physical_polarity_status`, `physical_polarity_source`, `physical_subducting_side`, `physical_overriding_side`, `physical_polarity_confidence`.
4. **Per-cell arrays**: `crust_type_by_cell`, `lithology_by_cell`, `boundary_convergent_by_cell`, `boundary_divergent_by_cell`, `boundary_transform_by_cell`, `crust_transport_distance_km_by_cell`, the nine `crust_*_change*_by_cell` arrays, `tectonic_elevation_change_m_by_cell`, `previous_local_isostatic_equilibrium_m`, `post_process_local_isostatic_equilibrium_m`, `isostatic_equilibrium_change_m`, `previous_local_thermal_subsidence_target_m`, `post_process_local_thermal_subsidence_target_m`, `thermal_equilibrium_change_m`, `unbounded_dynamic_relief_change_m`, `bounded_dynamic_relief_change_m`, `aged_oceanic_cell_ids`, `rejuvenated_oceanic_cell_ids`, `subducted_oceanic_cell_ids`.
5. **`plates[]`** (per-step plate snapshots) — 8: `plate_id`, `center`, `rotation_axis`, `intrinsic_angular_speed`, `step_rotation_deg`, `cumulative_rotation_deg`, `cell_count`, `area_km2`.

### `crust_material_shadow_history[]` (`process_serialization.cpp:268-367`)

`id`, `plate_motion_history_id`, `stage`, `erosion_iteration`, `cell_count`, then five tables: `opening_packets`, `transported_packets`, `unresolved_source_adjustments`, `unresolved_sink_adjustments`, `closing_packets`. Then `global_opening_mass_kg`, `global_transported_mass_kg`, `global_unresolved_source_mass_kg`, `global_unresolved_sink_mass_kg`, `global_closing_mass_kg`, `raw_transported_scalar_mass_kg`, `shadow_minus_raw_transport_residual_kg`, `source_to_transport_residual_kg`, `closing_scalar_mass_kg`, `closing_scalar_mass_residual_kg`, `maximum_absolute_cell_closing_scalar_mass_residual_kg`, `ordered_adjustment_reconciliation_residual_kg`, the five packet/adjustment counters, and `ordered_reason_adjustments[]`.

| table kind | shape | fields |
|---|---|---|
| packet table (`opening_packets`, `transported_packets`, `closing_packets`) | 5 parallel CSR arrays | `cell_offsets`, `origin_kind_ids`, `origin_plate_ids`, `origin_reason_ids`, `dry_rock_mass_kg` |
| adjustment table (`unresolved_source_adjustments`, `unresolved_sink_adjustments`) | 6 parallel CSR arrays | the five above plus `process_reason_ids` |
| `ordered_reason_adjustments[]` | one record per `CRUST_PROCESS_REASON_COUNT` | `process_reason_id`, `process_reason`, `source_mass_kg`, `sink_mass_kg` |

The model declares `shadow_minus_raw_transport_residual_semantics = "source_normalized_shadow_mass_minus_raw_overlap_scalar_mass_is_a_numerical_geometry_closure_diagnostic_not_a_physical_source_or_sink"` (`:204-205`). Read that literally: the residual is a geometry-closure number, not evidence of mass creation or destruction.

### `crust_dry_rock_accounting_history[]` — 47 fields (`crust_reservoir_serialization.cpp:197-305`)

`id`, `plate_motion_history_id`, `crust_material_shadow_history_id`, `stage`, `erosion_iteration`, `cell_count`, `plate_count`, seven packet tables (`opening_surface_packets`, `transported_surface_packets`, `closing_surface_packets`, `opening_upper_mantle_packets`, `closing_upper_mantle_packets`, `opening_subducted_slab_packets`, `closing_subducted_slab_packets`), `proxy_compensation_transfers`, `ordered_reason_transactions`, then `surface_state_envelope_capacity_kg`, `total_control_volume_area_km2`, the opening/transported/closing masses for each reservoir, `opening_global_mass_kg`, `closing_global_mass_kg`, `source_to_transport_residual_kg`, `global_accounting_residual_kg`, `capacity_initialization_residual_kg`, `maximum_absolute_origin_closure_residual_kg`, `maximum_absolute_reservoir_transfer_residual_kg`, `closing_scalar_mass_kg`, `closing_scalar_mass_residual_kg`, `maximum_absolute_cell_closing_scalar_mass_residual_kg`, `requested_minus_fulfilled_source_mass_kg`, `requested_minus_fulfilled_sink_mass_kg`, and ten packet/transfer counters.

| table | fields |
|---|---|
| packet table (all seven) | `owner_offsets`, `origin_domain_ids`, `origin_kind_ids`, `origin_plate_ids`, `dry_rock_mass_kg` |
| `proxy_compensation_transfers` | `sequence_ids`, `mechanism_ids`, `process_reason_ids`, `cell_ids`, `fragment_ids`, `source_reservoir_ids`, `source_owner_ids`, `destination_reservoir_ids`, `destination_owner_ids`, `origin_domain_ids`, `origin_kind_ids`, `origin_plate_ids`, `physical_basis_resolved` (bool array), `dry_rock_mass_kg` |
| `ordered_reason_transactions[]` | `process_reason_id`, `process_reason`, `requested_surface_source_mass_kg`, `requested_surface_sink_mass_kg`, `fulfilled_surface_source_mass_kg`, `fulfilled_surface_sink_mass_kg`, `physical_source_sink_resolved` (always `false`) |

---

## The shared nominal-time block

`add_nominal_time_fields` (`cpp/src/engine/process_serialization.cpp:135-160`) injects the same twelve fields into **seven** ledger record families, always immediately after the record's id/stage/iteration prefix: `hydrologic_water_budget_history`, `earth_system_feedback_history`, `numeric_depression_correction_history`, `hillslope_sediment_transport_history`, `glacial_sediment_transport_history`, `fluvial_sediment_routing_history`, `plate_motion_history`.

| field | type | value / meaning |
|---|---|---|
| `nominal_time_model` | string | `configured_maturation_timestep_nominal_elapsed_time_v1` (`:7-8`) |
| `nominal_time_unit` | string | `"Ma"` |
| `nominal_time_basis` | string | `configured_maturation_timestep_ma_per_erosion_transition_v1` (`:9-10`) |
| `nominal_time_source_parameter` | string | `erosion.maturation_timestep_ma` (`:11-12`) |
| `nominal_time_role` | string | Per-family role name (listed with each ledger above). |
| `nominal_interval_start_ma` | double, `max_digits10` | Interval start on the nominal clock. |
| `nominal_interval_end_ma` | double, `max_digits10` | Interval end. |
| `nominal_interval_duration_ma` | double, `max_digits10` | `end − start`. |
| `nominal_elapsed_time_ma` | double, `max_digits10` | Equals `nominal_interval_end_ma`. |
| `advances_nominal_time` | bool | `duration_ma > 0.0`. |
| `nominal_time_calibrated` | bool | **always `false`** |
| `physical_time_resolved` | bool | **always `false`** |

Elapsed time is `maturation_timestep_ma * transition_count` (`:46-54`). Placement is strict: `nominal_erosion_interval` and `nominal_feedback_interval` throw (`"…cannot be placed on the nominal maturation clock"`) rather than emitting a guessed time, so an inconsistent clock fails generation instead of shipping a wrong number.

---

## Enum name tables

All enum-valued string fields draw from fixed tables in `cpp/src/engine/schema_names.hpp`. The serializers index these arrays directly, so an out-of-range enum is a native bug, not a document variant.

| table | size | values |
|---|---|---|
| `CRUST_NAMES` | 9 | `oceanic`, `continental`, `transitional`, `volcanic_arc`, `craton`, `orogen`, `rift_basin`, `sedimentary_basin`, `accreted_terrane` |
| `LITHOLOGY_NAMES` | 7 | `basalt`, `granite`, `limestone`, `sandstone`, `shale`, `volcanic`, `metamorphic` |
| `BOUNDARY_NAMES` | 5 | `interior`, `convergent`, `divergent`, `transform`, `mixed` |
| `SOIL_NAMES` | 11 | `none`, `thin_mountain`, `volcanic`, `alluvial`, `arid`, `tropical`, `temperate`, `boreal`, `tundra`, `wetland`, `saline` |
| `BIOME_NAMES` | 16 | `ocean`, `continental_shelf`, `lake`, `ice_cap`, `tundra`, `boreal_forest`, `temperate_forest`, `temperate_grassland`, `mediterranean_scrub`, `cold_desert`, `hot_desert`, `savanna`, `tropical_seasonal_forest`, `tropical_rainforest`, `alpine`, `wetland` |
| `RESOURCE_NAMES` | 9 | `none`, `volcanic_arc_metals`, `craton_iron_gold`, `sedimentary_fuels`, `evaporites`, `placer_metals`, `geothermal`, `fertile_alluvium`, `coastal_fisheries` |
| `ATMOSPHERIC_CELL_NAMES` | 4 | `tropical_ascent`, `subtropical_high`, `midlatitude_westerly`, `polar_cell` |
| `WATER_BODY_NAMES` | 6 | `land`, `ocean`, `continental_shelf`, `inland_sea`, `fresh_lake`, `saline_basin` |
| `LANDFORM_NAMES` | 20 | `open_ocean`, `continental_shelf`, `inland_sea`, `lacustrine_basin`, `salt_flat`, `ice_field`, `mountain_belt`, `volcanic_arc`, `rift_valley`, `trench`, `river_valley`, `floodplain`, `delta`, `alluvial_fan`, `coastal_plain`, `stable_lowland`, `fjord`, `glacial_valley`, `moraine`, `glacial_lake` |
| `SETTLEMENT_TYPE_NAMES` | 6 | `river_city`, `port`, `mining_town`, `agricultural_town`, `oasis`, `frontier_town` |
| `ROUTE_TYPE_NAMES` | 4 | `overland`, `river_corridor`, `coastal_sea`, `mountain_pass` |
| `WATERSHED_OUTLET_NAMES` | 5 | `ocean`, `lake`, `saline_basin`, `inland_sea`, `closed_land` |
| `DEPRESSION_POLICY_NAMES` | 6 | `none`, `corrected_numeric`, `preserved_geologic`, `overflow_spill`, `dry_closed`, `temporary_numeric_lake` |
| `POLITICAL_REGION_TYPE_NAMES` | 6 | `river_realm`, `maritime_league`, `mountain_march`, `mining_domain`, `agrarian_state`, `frontier_territory` |
| `BORDER_TYPE_NAMES` | 6 | `open_lowland`, `river`, `mountain`, `desert`, `ice`, `coastal` |
| `CULTURE_TYPE_NAMES` | 8 | `river_valley`, `maritime`, `highland`, `desert_oasis`, `agrarian_lowland`, `mining_frontier`, `boreal_frontier`, `forest_realm` |
| `LANGUAGE_FAMILY_NAMES` | 6 | `riverine`, `coastal`, `highland`, `arid`, `lowland`, `frontier` |
| `SACRED_AREA_TYPE_NAMES` | 6 | `mountain_shrine`, `spring_oracle`, `sacred_grove`, `volcanic_sanctuary`, `ancestral_coast`, `desert_sanctuary` |
| `RUIN_TYPE_NAMES` | 6 | `ruined_city`, `abandoned_mine`, `desert_outpost`, `mountain_fortress`, `old_harbor`, `glacial_relic` |
| `ABANDONMENT_REASON_NAMES` | 6 | `aridity`, `tectonic_hazard`, `glaciation`, `salinization`, `trade_decline`, `frontier_isolation` |
| `HISTORY_EVENT_TYPE_NAMES` | 7 | `state_foundation`, `dynastic_change`, `migration`, `language_split`, `trade_boom`, `sacred_founding`, `ruin_abandonment` |
| `HISTORICAL_PROCESS_NAMES` | 4 | `founding`, `expansion`, `fragmentation`, `integration` |
| `CONFLICT_CAUSE_NAMES` | 6 | `water_rights`, `fertile_plain`, `mining_claim`, `trade_chokepoint`, `border_fragmentation`, `sacred_site` |
| `CONFLICT_OUTCOME_NAMES` | 5 | `stalemate`, `region_a_victory`, `region_b_victory`, `border_shift`, `exhaustion` |
| `DYNASTY_COLLAPSE_REASON_NAMES` | 6 | `continuity`, `succession_crisis`, `resource_shock`, `trade_decline`, `migration_pressure`, `conflict_defeat` |
| `CALIBRATION_DATASET_NAMES` | 4 | `ETOPO_reference_range`, `WorldClim_reference_range`, `HydroSHEDS_reference_range`, `NaturalEarth_reference_range` |
| `CALIBRATION_LAYER_NAMES` | 5 | `relief_bathymetry`, `climate`, `hydrology`, `biomes`, `cartography` |
| `CALIBRATION_METRIC_NAMES` | 12 | `ocean_fraction`, `mean_land_elevation_m`, `hypsometric_span_m`, `global_mean_temperature_c`, `mean_land_precipitation_mm_y`, `mean_monthly_temperature_range_c`, `river_cell_fraction`, `endorheic_watershed_fraction`, `desert_land_fraction`, `ice_land_fraction`, `forest_land_fraction`, `coastal_land_fraction` |
| `COASTAL_FEATURE_TYPE_NAMES` | 6 | `beach`, `barrier_bar`, `barrier_island`, `delta_lobe`, `tidal_marsh`, `coastal_cliff` |
| `SHORELINE_TREND_NAMES` | 5 | `stable`, `prograding`, `eroding`, `landward_migration`, `delta_switching` |
| `SEDIMENTARY_BASIN_TYPE_NAMES` | 6 | `rift_basin`, `foreland_basin`, `passive_margin`, `lacustrine_basin`, `evaporite_basin`, `deltaic_basin` |
| `STRATIGRAPHIC_FACIES_NAMES` | 9 | `alluvial_fan`, `fluvial_channel`, `floodplain_mud`, `deltaic_sand`, `lacustrine_mud`, `evaporite`, `shallow_marine`, `deep_marine`, `glacial_till` |
| `SEQUENCE_PHASE_NAMES` | 5 | `aggradation`, `progradation`, `retrogradation`, `starved`, `erosional` |
| `ICE_RETREAT_STAGE_NAMES` | 5 | `advancing`, `stable`, `retreating`, `stagnant`, `relict` |

`CRUST_PROCESS_REASON_NAMES` lives in `cpp/src/engine/constants.hpp` (10 entries) and drives `ordered_reason_adjustments[].process_reason`, `ordered_reason_transactions[].process_reason`, and `process_inventory_attribution.reasons[].reason`: `quiet_oceanic_aging`, `oceanic_ridge_rejuvenation`, `oceanic_ridge_creation_relaxation`, `divergent_continental_rifting`, `oceanic_convergence_subduction_proxy`, `continental_collision_orogeny`, `plate_crossing_accretion_proxy`, `age_bound_enforcement`, `thickness_bound_enforcement`, `density_bound_enforcement`.

---

## Full-world vs geo-only documents

**At the C++ layer there is no shape difference.** The native geo entry point `generate_geo_world_json` (`cpp/src/engine.cpp:27-35`) calls `simulate_geo_world`, which is `simulate_world_impl(params, include_society = false)` (`cpp/src/engine/pipeline.cpp:272-274`; the single society branch is at `pipeline.cpp:199`), and then the *same* `serialize_world`. All 57 top-level keys, all 155 cell fields, and all 412 summary keys are emitted; the society arrays are simply `[]` and the derived counters are `0`.

**The divergence is created in Python** by `_strip_native_civilization_outputs` (`src/magic_geo/api.py:269-284`), which runs immediately after the planet-snapshot check and *before* any enricher. The module comment explains why: the native serializer keeps stable empty/default civilization fields, and they must be removed so mixed natural models take their documented no-human default branches instead of reading empty lists as real data (`src/magic_geo/api.py:83-85`, `287-292`).

| aspect | full-world | geo-only |
|---|---|---|
| entry point | `magic_geo.api.generate_world` | `magic_geo.api.generate_geo_world` |
| `generation_scope` key | **absent** | `"geo_only"` (`api.py:305`) |
| native top-level keys | 57 | 42 (15 removed) |
| per-cell native fields | 155 | 151 (4 removed) |
| native summary keys | 412 | 354 (58 removed) |
| `output.include_cells` | optional | **required**; otherwise `ValueError` (`api.py:296-300`) |
| enricher count | 66 | 48 |

### Removed top-level keys (15) — `NATIVE_CIVILIZATION_TOP_LEVEL_FIELDS`, `api.py:86-104`

`borders`, `conflicts`, `cultures`, `dynasties`, `historical_eras`, `historical_events`, `language_regions`, `political_regions`, `population_regions`, `routes`, `ruins`, `sacred_areas`, `settlements`, `territorial_snapshots`, `trade_flows`.

Retained: `calibration_checks`, `plates`, `watersheds`, `lake_basins`, `coastal_features`, `sedimentary_basins`, `stratigraphic_columns`, `ice_sheets`, and every model/history/ledger section.

### Removed per-cell fields (4) — `NATIVE_CIVILIZATION_CELL_FIELDS`, `api.py:106-113`

`culture_region_id`, `language_region_id`, `political_region_id`, `settlement_score`.

`settlement_score` is the load-bearing removal: several mixed natural/human enrichers read it with a `0.0` default, so deleting the key forces them onto their no-human baseline branch rather than treating a defaulted score as data.

### Removed summary keys (58) — `NATIVE_CIVILIZATION_SUMMARY_FIELDS`, `api.py:115-176`

`border_segment_count`, `border_total_length_km`, `conflict_count`, `culturally_assigned_land_fraction`, `culture_region_count`, `dynastic_change_count`, `dynastic_lineage_count`, `dynasty_count`, `dynasty_root_count`, `dynasty_successor_link_count`, `estimated_world_population`, `high_economic_disruption_conflict_count`, `high_intensity_conflict_count`, `historical_era_count`, `historical_event_count`, `interregional_trade_fraction`, `language_lineage_count`, `language_region_count`, `largest_culture_area_km2`, `largest_region_area_km2`, `linguistically_assigned_land_fraction`, `max_conflict_casualty_rate`, `max_dynasty_lineage_depth`, `mean_conflict_casualty_rate`, `mean_conflict_economic_disruption_index`, `mean_conflict_intensity`, `mean_conflict_logistics_strain_index`, `mean_cultural_continuity`, `mean_dynastic_continuity_index`, `mean_historical_instability`, `mean_inherited_phonology_fraction`, `mean_language_change_rate`, `mean_phonological_complexity`, `mean_population_pressure`, `mean_snapshot_boundary_perimeter_km`, `mean_snapshot_compactness_index`, `mean_snapshot_fragmentation_index`, `mean_snapshot_geometry_quality`, `mean_snapshot_polygon_area_error_fraction`, `mean_sound_shift_index`, `mean_trade_friction`, `mean_war_duration_years`, `migration_event_count`, `natural_border_fraction`, `politically_assigned_land_fraction`, `political_region_count`, `population_region_count`, `route_count`, `ruin_count`, `sacred_area_count`, `settlement_count`, `snapshot_polygon_region_count`, `snapshot_region_record_count`, `territorial_snapshot_count`, `top_settlement_score`, `total_mobilized_population`, `trade_flow_count`, `trade_total_volume_index`.

### Enricher-key divergence

Full-world runs 21 enrichers that geo-only does not (settlement/route models, political/cultural/historical/civilization/territorial models, navigability, port sites, route corridors, land-use zones, natural frontiers, worldbuilding realism, population/economy/dynasty/logistics histories, demographic agents, market clearing, phonology history, and the civilization variants of graph/boundary diagnostics). Geo-only substitutes `enrich_world_with_physical_graph_diagnostics`, `enrich_world_with_physical_boundary_geometry`, and the geo-only-exclusive `enrich_world_with_geo_evolution_provenance` (`api.py:372-374`). Ordering also differs — geology/tectonics/faults run *before* sea level and ocean circulation in geo-only, `hydrology_realism` runs before `sediment_routing_history`, and `karst_diagnostics` moves into the water-systems block. See [Python API](./07-python-api.md).

Independent of scope, `params.include_cells == false` yields `"cells": []` with the key still present (`cpp/src/engine/world_serialization.cpp:289-291`).

---

## Numerical precision contracts

### Two serialization primitives

| primitive | formatting | used by | source |
|---|---|---|---|
| `num(value, precision)` | `std::fixed` with `precision` **decimal places** | `add_double`, `double_array_json`, `vec3_json`, `latlon_ring_json` | `cpp/src/engine/core.cpp:168-177` |
| `roundtrip_num(value)` | `std::defaultfloat` with `max_digits10` **significant digits** — exact binary64 round-trip | `add_raw(..., roundtrip_num(...))`, `roundtrip_double_array_json` | `cpp/src/engine/numeric_serialization.cpp:5-16` |

Both throw `std::runtime_error("attempted to serialize a non-finite simulation value")` on non-finite input, so **no `NaN` or `Infinity` can appear in a world document**. The configured display precision is `output.float_precision`, default **4**, validated `0 <= p <= 8` in Python (`src/magic_geo/config.py:450-454`) and again natively (`cpp/src/engine/core.cpp:430-432`).

> Consumer caution: the five digit-count keys in `plate_boundary_segment_model` — `intrinsic_angular_speed_serialized_significant_digits`, `rotation_axis_serialized_significant_digits`, `assignment_center_serialized_significant_digits`, `top_level_plate_center_serialized_significant_digits` and `serialized_float_decimal_significant_digits` — are plain integers emitted through `add_int` and all hold `max_digits10` (`process_serialization.cpp:2949`, `:3041-3064`, `:3126-3127`). Despite the `significant_digits` naming, the double fields they describe are written with `num()`, i.e. `std::fixed` with that many **decimal places**. Read them as declarations about other fields, not as self-descriptions, and not as a significant-digit contract.

### Fields on exact binary64 round-trip

| location | fields |
|---|---|
| `planet_parameters` | all 12 |
| `cells[]` | `crust_age_ma`, `crust_thickness_km`, `crust_density`, `thermal_subsidence_target_m`, `elevation_m`, `water_depth_m` (`entity_serialization.cpp:151-186`) |
| `initial_oceanic_crust_age_model` | `provisional_age_for_oceanic_predicate_ma`, `representative_half_spreading_rate_factor`, `configured_maximum_model_age_ma`, `effective_maximum_age_ma` |
| `initial_oceanic_crust_age_ledger` | every scalar and every double array, including `age_ma_by_cell`, `unclamped_graph_age_ma_by_cell`, `cdf_thresholds_ma`, `area_weighted_cdf_le_threshold` |
| `oceanic_age_depth_model` | `young_age_cutoff_ma`, `young_age_coefficient_m_per_sqrt_ma`, `old_age_exponential_scale_m`, `old_age_efolding_time_ma`, `thermal_target_difference_gain` |

### Fixed decimal floors above the display precision

| floor | where | source |
|---|---|---|
| `geometry_precision = max(max_digits10, float_precision)` | `cells[]` positions/normals/lat/lon/area/control-volume vertices; `plates[]` `axis`, `initial_center`, `center`, `angular_speed` | `entity_serialization.cpp:8-11`, `:113-116` |
| `surface_precision = max(10, float_precision)` | the 33 elevation/sediment-depth cell fields (`cumulative_tectonic_elevation_change_m` through `glacial_sediment_net_m`); `sediment_interface_model.maximum_final_closure_residual_m` | `entity_serialization.cpp:117`, `process_serialization.cpp:1832` |
| `max(12, surface_precision)` | `cells[].hydrologic_flow_slope` | `entity_serialization.cpp:253` |
| `max(10, float_precision)` | `cells[].fluvial_sediment_terminal_capture_volume_km3`; the whole `hydrologic_water_budget_model`; glacial/hillslope/fluvial model volume totals; `sediment_inventory_model` volumes; numeric-depression and sediment-budget summary volume keys | `entity_serialization.cpp:316`, `process_serialization.cpp:455`, `:1963`, `summary.cpp:1394` |
| `max(12, float_precision)` | `hydrologic_water_budget_history[]` volume fields; `numeric_depression_correction_history[]` surface fields | `process_serialization.cpp:556`, `:655` |
| `max(8, float_precision)` | `cells[].fertility`, `cells[].settlement_score`, `settlements[].score`, `settlements[].fertility`; hillslope/glacial history surface depths; hillslope/glacial max-depth summary keys | `entity_serialization.cpp:341`, `:349`, `:371`, `:377`, `process_serialization.cpp:917`, `:1236`, `summary.cpp:1456` |
| `max(6, float_precision)` | all of `climate_model`; `plate_motion_history[]` step aggregates; several summary area/fraction keys | `process_serialization.cpp:370`, `:3472`, `summary.cpp:1360-1364` |
| `max_digits10` (fixed format) | the 13 crust-transport / tectonic-attribution closure keys in `summary` (`crust_transport_diagnostic_precision`); every mass key in the shadow and dry-rock blocks; every double in `sea_level_model` **except** `below_sea_level_land_area_km2`, which is emitted at plain `float_precision` (`process_serialization.cpp:3456-3457`); all of `plate_boundary_segment_model`; the entire `crust_overlap_ledger`, `crust_overlap_candidate_fate_ledger`, `boundary_segments[]`, per-cell arrays and plate snapshots inside `plate_motion_history[]`; the three tectonic-elevation-change step scalars; `simulation_clock` times; the nominal-time block | `summary.cpp:1532-1533`, `summary.cpp:119`, `crust_reservoir_serialization.cpp:7`, `process_serialization.cpp:3410-3453`, `:3530`, `:2078`, `:141` |
| `max(max_digits10, float_precision)` | the entire `fluvial_sediment_routing_history[]` volume/surface set (`evidence_precision`) | `process_serialization.cpp:1552-1558` |
| plain `float_precision` | all natural and society entity arrays (`watersheds`, `lake_basins`, `coastal_features`, `sedimentary_basins`, `stratigraphic_columns` + `layers[]`, `ice_sheets`, `plates` non-geometry fields, `political_regions`, `cultures`, `language_regions`, `sacred_areas`, `ruins`, `historical_eras`, `historical_events`, `population_regions`, `conflicts`, `dynasties`, `territorial_snapshots` + `regions[]`, `borders`, `settlements` lat/lon, `routes`, `trade_flows`, `calibration_checks`); `boundary_ring` lat/lon rings; the bulk of the `cells[]` climate/hydrology/ice/soil fields; most `summary` means and fractions | throughout |

---

## Decimal-quantization contracts declared in the document

The document describes its own quantization so that a validator can bound replay error without guessing.

| key path | value | consequence |
|---|---|---|
| `sediment_interface_model.replay_tolerance_model` | `decimal_quantization_forward_error_by_serialized_operand_precision_v1` | Replay tolerance is derived from serialized operand precision, not a fixed epsilon. |
| `sediment_interface_model.canonical_state_serialization_decimal_places` | `10` | Matches the `surface_precision` floor for `bedrock_surface_elevation_m` and `sediment_thickness_m`. |
| `sediment_interface_model.minimum_replay_operand_serialization_decimal_places` | `8` | Floor for any operand entering a replay. |
| `initial_oceanic_crust_age_model.array_serialization_model` | `decimal_max_digits10_binary64_round_trip` | Age arrays are exact. |
| `initial_oceanic_crust_age_model.unclamped_graph_age_unavailable_sentinel` | `negative_one_for_non_oceanic_like_or_unreachable_cells` | `-1` is a sentinel, not an age. |
| `plate_kinematic_model.crust_transport_positive_area_serialization_model` | `general_format_max_digits10_binary64_round_trip_v1` | Positive overlap areas round-trip. |
| `crust_overlap_candidate_fate_model.candidate_area_serialization_model` | `general_format_max_digits10_binary64_round_trip_v1` | Candidate excess areas round-trip. |
| `crust_overlap_candidate_fate_model.root_overlap_excess_serialization_model` | `general_format_max_digits10_binary64_round_trip_v1_for_per_cell_and_global_operands` | Per-cell and global excess operands round-trip. |
| `oceanic_age_depth_model.array_serialization_model` | `general_format_max_digits10_binary64_round_trip_v1` | Thermal target/equilibrium arrays round-trip. |
| `oceanic_age_depth_model.final_cell_crust_numeric_root_semantics` | `binary64_round_trip_aliases_cross_checked_against_authoritative_history_roots` | The final `cells[]` crust numbers are aliases of history roots, cross-checked. |
| `crust_material_shadow_model.dry_rock_mass_definition` | `cell_area_km2_times_crust_thickness_km_times_crust_density_g_cm3_times_1e12` | Exact mass formula for reproducing packets. |
| `crust_dry_rock_accounting_model.capacity_formula` | `sum_control_volume_area_km2_times_76_km_times_3.08_g_cm3_times_1e12` | With `capacity_geophysically_calibrated = false`. |
| `summary.output_float_precision` | echoes configured `float_precision` | Lets a consumer reconstruct the quantization grid of every plain-precision field. |

---

## Stable navigation and versioning

**`schema_version` is a hard gate, not a hint.** The native emitter writes literal `2` (`cpp/src/engine/world_serialization.cpp:49`); Python defines `CURRENT_WORLD_SCHEMA_VERSION = 2` (`src/magic_geo/serialization.py:27`) and `_require_current_world_schema` raises if the native library returns anything else, telling the user to rebuild `magic_geo_native` (`src/magic_geo/native.py:234-241`). The `.mgeo` binary container carries the same version in its header and refuses a mismatch (`src/magic_geo/serialization.py:445-450`).

**Retired fields are rejected, not ignored.** `retired_world_schema_fields` (`src/magic_geo/serialization.py:68-233`) enumerates every key that existed in an earlier shape and must not appear in a schema-2 world; a hit fails the load with `"native library returned retired fields in a schema-2 world: …"`. Grouped by container:

| container | retired keys |
|---|---|
| `simulation_clock` | `legacy_mean_erosion_rate_field_semantics` |
| `plate_kinematic_model` | `accelerator_crust_source_remap_kernel_used`, `legacy_crust_source_cell_id_semantics`, `legacy_crust_source_remap_event_semantics`, `legacy_crust_source_reuse_count_semantics` |
| `plate_boundary_segment_model` | `unavailable_opening_crust_fallback_semantics`, `legacy_smoothed_cell_boundary_forcing_retained`, `boundary_segments_drive_legacy_smoothed_forcing` |
| `crust_dry_rock_accounting_model` | `legacy_proxy_compensations_exposed` |
| `backend` | `accelerator_crust_source_remap_kernel_production_active`, `accelerator_crust_source_remap_kernel_role`, `legacy_nearest_source_remap_world_pipeline_enabled`, `legacy_crust_source_remap_dispatch_counters_deprecated`, `opencl_crust_source_remap_dispatch_count`, `cuda_crust_source_remap_dispatch_count` |
| `climate_model` | `positive_precipitation_pre_thermal_annual_floor_mm`, `positive_precipitation_effective_annual_floor_mm`, `positive_precipitation_floor_application` |
| `oceanic_age_depth_model` | `thermal_target_difference_tendency_formula`, `thermal_target_difference_tendency_application`, `thermal_target_difference_tendency_compatibility_alias`, `thermal_target_difference_tendency_application_replayed` |
| `initial_oceanic_crust_age_model` | `compatibility_cell_alias_location`, `compatibility_history_alias_location`, `compatibility_alias_scope` |
| `summary` | `total_crust_source_remap_event_count`, `total_crust_source_reuse_count`, and thirteen retired numeric-depression fill keys (`numeric_depression_fill_max_pass_count`, `numeric_depression_fill_pass_count`, `numeric_depression_fill_event_count`, `numeric_depression_fill_cell_application_count`, `numeric_depression_filled_unique_cell_count`, `numeric_depression_fill_geologic_source_event_count`, `numeric_depression_fill_area_km2`, `numeric_depression_fill_volume_km3`, `mean_numeric_depression_fill_depth_m`, `max_numeric_depression_fill_depth_m`, `cumulative_numeric_depression_fill_sum_m`, `max_cumulative_numeric_depression_fill_m`, `numeric_depression_unbalanced_fill_event_count`) |
| root | `numeric_depression_fill_history` |
| `cells[]` | `last_crust_source_cell_id`, `crust_source_remap_event_count`, `initial_crust_age_ma`, `initial_crust_thickness_km`, `initial_crust_density`, `initial_thermal_subsidence_m`, `sediment_production_m`, `cumulative_numeric_depression_fill_m`, `numeric_depression_fill_event_count` |
| `earth_system_feedback_history[]` | `mean_erosion_rate_m_per_step`, and seven `numeric_depression_fill_*` keys |
| `numeric_depression_correction_history[]` | `applied_fill_volume_km3` |
| `plate_motion_history[]` | `crust_source_remap_cell_count`, `unique_crust_source_cell_count`, `crust_source_reuse_count`, `crust_source_cell_ids`, `thermal_target_difference_tendency_m` |

### Practical navigation rules

| rule | why |
|---|---|
| Key by name, never by index into the object. | Emission order is stable but is an implementation detail of `serialize_world`; the retired-field list shows keys do get removed across versions. |
| Treat `*_counts` histograms as sparse. | `counts_json` only emits observed categories (`summary.cpp:5-15`). |
| Treat every `*_by_cell` array as positionally indexed by the ledger's own `cell_ids` (or by canonical cell id where the model says `array_index = "canonical_cell_id"`). | Mixing the two indexings silently corrupts replays. |
| Check the model section's `*_resolved` / `*_authoritative` flags before treating a ledger as physics. | Several ledgers are explicitly diagnostic-only. |
| Read `summary.output_float_precision` before comparing floats. | It defines the quantization grid for every plain-precision field. |
| Do not assume `generation_scope` exists. | It is only set on geo-only documents (`api.py:305`); full-world documents have no such key, and consumers test `root.get("generation_scope") == "geo_only"` (`src/magic_geo/geo_layer_contracts.py:337`). |
| Do not assume `cells` is non-empty. | It is `[]` when `output.include_cells` is false. |

---

## Worked examples

Generate both document shapes:

```bash
# Full world (all 57 native top-level keys + civilization enrichers)
magic-geo generate --config magic-geo.yaml --output runs/world.json

# Geo-only (civilization keys stripped, generation_scope == "geo_only")
magic-geo generate --config magic-geo.yaml --output runs/geo.json --geo-only

# Fast binary container with the same document shape
magic-geo generate --config magic-geo.yaml --output runs/world.mgeo --format mgeo
```

Read a document back and inspect the contracts that matter before trusting a number:

```python
from magic_geo.io import read_world

world = read_world("runs/world.json")

assert world["schema_version"] == 2
print("scope:", world.get("generation_scope", "full_world"))
print("cells:", len(world["cells"]), "of", world["summary"]["cell_count"])
print("float_precision:", world["summary"]["output_float_precision"])

# Time is nominal, never calibrated.
clock = world["simulation_clock"]
print(clock["clock_type"], clock["nominal_timestep_ma"], "Ma per transition")
print("physical_time_resolved:", clock["physical_time_resolved"])          # False
print("nominal_time_calibrated:", clock["nominal_time_calibrated"])        # False
print("limitation:", clock["clock_limitation"])
```

Verify the sediment interface identity on every cell, using the document's own declared quantization:

```python
model = world["sediment_interface_model"]
places = model["canonical_state_serialization_decimal_places"]   # 10
tol = 3 * 10 ** -places

for cell in world["cells"]:
    derived = cell["bedrock_surface_elevation_m"] + cell["sediment_thickness_m"]
    assert abs(derived - cell["elevation_m"]) <= tol, cell["id"]
```

Walk the crust-mass shadow packet CSR for one step (packets are grouped per cell by `cell_offsets`):

```python
step = world["crust_material_shadow_history"][-1]
table = step["closing_packets"]
offsets = table["cell_offsets"]

for cell_id in range(step["cell_count"]):
    start, end = offsets[cell_id], offsets[cell_id + 1]
    for i in range(start, end):
        origin_kind = table["origin_kind_ids"][i]
        mass_kg = table["dry_rock_mass_kg"][i]
        ...  # provenance here is a shadow, not a physical claim
```

Before drawing any conclusion from that walk, check the model flags:

```python
shadow = world["crust_material_shadow_model"]
assert shadow["mode"] == "shadow"
assert shadow["authoritative_for_cell_state"] is False
assert shadow["material_provenance_resolved"] is False
assert shadow["global_crust_cycle_mass_conservation_resolved"] is False
print(shadow["shadow_minus_raw_transport_residual_semantics"])
```

Enumerate every self-declared unresolved claim in a document:

```python
def unresolved_flags(world):
    for key, value in world.items():
        if not isinstance(value, dict):
            continue
        for name, flag in value.items():
            if flag is False and (
                name.endswith(("_resolved", "_calibrated", "_authoritative",
                               "_demonstrated", "_represented"))
            ):
                yield f"{key}.{name}"

for path in unresolved_flags(world):
    print(path)
```

---

## Limitations and unresolved claims

These are the document's own statements, carried forward without softening.

- **Physical time is not resolved anywhere.** `simulation_clock.physical_time_resolved`, `nominal_time_calibrated`, `absolute_geological_age_resolved`, `process_rate_calibration_resolved` and `time_step_convergence_demonstrated` are all `false` (`process_serialization.cpp:2083-2087`). Every `*_ma`, `*_ka`, `*_y` and `*_per_step` value in the document is on a **nominal** clock defined only by `erosion.maturation_timestep_ma`. `deglaciation_age_ka`, `crust_age_ma`, `year_bp`, `duration_years` and the era boundaries inherit this.
- **Subduction polarity is unresolved.** `plate_boundary_segment_model` sets `physical_subduction_polarity_resolved`, `physical_slab_geometry_resolved`, `slab_selection_resolved`, `slab_transfer_resolved`, `physical_material_fate_resolved` and `boundary_segments_drive_slab_transfers` to `false`, and states that `polarity_candidate_is_physical_decision` is `false` (`:3139-3145`). The `candidate_subducting_side` / `candidate_overriding_side` fields are an **oceanic-side heuristic**, explicitly documented as "not physical polarity". `physical_polarity_source_rule` is `none_until_supplied_constraint_or_physical_solver_is_implemented`.
- **Overlap candidate fate is a crosswalk, not an allocation.** `crust_overlap_candidate_fate_model` sets `candidate_allocation_authoritative`, `state_mutation_performed`, `crust_material_shadow_mutation_performed`, `crust_reservoir_mutation_performed`, `swept_area_calculated`, `local_segment_link_resolved`, `connected_atom_topology_resolved` and `local_fragment_topology_resolved` to `false` (`:3230-3252`), and declares `candidate_area_semantics = "diagnostic_partition_of_overlap_excess_not_allocated_material_fate_or_transfer"`.
- **Mass provenance is a shadow.** Both `crust_material_shadow_model` and `crust_dry_rock_accounting_model` set `authoritative_for_cell_state`, `material_provenance_resolved`, `physical_source_sink_resolved`, `solid_volume_resolved`, `phase_resolved`, `mass_weighted_age_resolved`, `upper_mantle_exchange_reservoir_resolved`, `subducted_slab_reservoir_resolved` and `global_crust_cycle_mass_conservation_resolved` to `false`. The dry-rock capacity is a numerical envelope: `capacity_geophysically_calibrated = false`, `capacity_semantics = "finite_numerical_surface_state_envelope_not_an_estimate_of_upper_mantle_mass"`. The subducted-slab reservoir is `plate_resolved_empty_reservoir_no_transfer_mechanism_enabled`. `instantaneous_global_mantle_mixing_assumed` is `true` while `mantle_spatial_transport_resolved` is `false`.
- **Sediment mass conservation is bulk-volume only.** `sediment_inventory_model.mass_conserving` is `true` but `mass_conserving_semantics = "bulk_reference_volume_only_not_dry_rock_mass"`, with `dry_rock_mass_resolved`, `sediment_density_resolved`, `porosity_resolved`, `compaction_resolved`, `grain_provenance_resolved` and `chemical_weathering_resolved` all `false` (`:1979-1987`). The per-process source partition is explicitly *not* a mass or provenance claim (`source_partition_audit_is_mass_claim = false`, `source_partition_audit_is_provenance_claim = false` in all three transport models).
- **Climate is an equilibrium diagnostic.** `climate_model.mass_conserving_atmosphere = false`, `transient_climate_resolved = false`; the thermal-moisture capacity factor is declared `diagnostic_global_scaling_without_explicit_atmospheric_water_mass_or_energy_balance` (`:436-446`).
- **Initial oceanic age is procedural.** `physical_seafloor_creation_resolved`, `spreading_rate_calibrated`, `local_spreading_rates_resolved`, `ridge_flowlines_resolved`, `subduction_sink_history_resolved`, `convergence_history_resolved` are all `false`, and `seton_2020_age_grid_used_as_generation_input = false` — the CDF thresholds exist for *external validation output*, not as generation input (`:2485-2503`).
- **Thermal subsidence is a relative curve.** `oceanic_age_depth_model` claims authority only for `relative_oceanic_thermal_subsidence_target_curve_only`; `absolute_basement_depth_calibrated`, `thermal_structure_represented`, `heat_flow_represented`, `dynamic_topography_represented`, `flexure_represented` and `physical_dynamics_represented` are `false`, and the 70 Ma branch switch has value continuity but explicitly **not** slope continuity (`derivative_continuity_at_transition_resolved = false`).
- **Accelerator parity is not demonstrated.** In `backend`, `crust_overlap_continuous_shadow_only = true` while `crust_overlap_continuous_shadow_authoritative`, `crust_overlap_continuous_shadow_result_used_for_state`, all four `crust_overlap_accelerator_*_parity_demonstrated` flags and `crust_overlap_accelerator_state_authoritative` are `false` (`cpp/src/opencl_compute.cpp:2130-2174`). The authoritative crust-overlap geometry, CSR and remap backend is `cpu`; `backend_scope` is `accelerated_native_kernels_not_end_to_end_pipeline`.
- **Sea level is cell-column volume.** `sea_level_model.model_limitation = "cell_column_volume_without_subcell_bathymetry_straits_or_exact_coast_polygons"`.
- **`normal_3d` is not an independent quantity.** It is byte-identical to `position_3d`, both serialized from `cell.p`.
- **`high_intensity_conflict_count` depends on `output.float_precision`.** Intensity is rounded to `10^clamp(float_precision,0,8)` before the `>= 0.65` test (`summary.cpp:712-722`), so changing a *formatting* setting can change this *counter*. No other summary counter was observed to have this dependence.
- **Not verified in source on this page:** the exact key count and per-key semantics of the `backend` object (185 emission sites inside `ComputeSession::Impl::json()`, `cpp/src/opencl_compute.cpp:2033`, several of which are inside device-enumeration loops so the emitted key count varies with hardware). Treat `backend` as variable-shaped and see [Compute Backends](./09-compute-backends.md).

---

## See also

- [Serialization and World Formats](./11-serialization.md) — JSON vs `.mgeo`, the value model, retired-field enforcement
- [Validation](./12-validation.md) — how the contracts on this page are checked
- [Geo Validation Suite](./13-geo-validation-suite.md) — geo-only layer contracts and empirical bundles
- [Configuration Reference](./05-configuration-reference.md) — `output.float_precision`, `output.include_cells`, planet inputs
- [Python API](./07-python-api.md) — `generate_world`, `generate_geo_world`, enricher-added keys
- [CLI Reference](./06-cli-reference.md) — `magic-geo generate --geo-only --format`
- [Native Engine (C++ Core)](./08-native-engine.md) — where each `cells[]` field is produced
- [Compute Backends (CPU, OpenCL, CUDA)](./09-compute-backends.md) — the `backend` object and accelerator parity flags
- [Architecture](./04-architecture.md) — stage order behind `simulation_clock`
- [Crust Transport and Forward Overlap](./features/crust-transport-and-overlap.md) — `plate_motion_history[].crust_overlap_ledger`
- [Crust Material Shadow and Dry-Rock Reservoirs](./features/crust-material-and-reservoirs.md) — the two mass-shadow families
- [Plate Boundary Segment Ledger](./features/plate-boundary-ledger.md) — `boundary_segments[]`
- [Sediment, Routing and Stratigraphy](./features/sediment-and-stratigraphy.md) — inventory, interface and fluvial routing evidence
- [Hydrology, Rivers and Lakes](./features/hydrology-and-rivers.md) — water budget and depression correction ledgers
- [Glossary](./21-glossary.md) — shadow, ledger, nominal time, membership area class
