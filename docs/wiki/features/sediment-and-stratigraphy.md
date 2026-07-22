# Sediment, Routing and Stratigraphy

[Wiki home](../README.md) > Features

magic-geo represents surface material with exactly two canonical per-cell fields — a bedrock surface elevation and a nonnegative mobile-sediment thickness — from which the terrain surface is *derived*, never independently written. Three native transport processes (hillslope, fluvial, glacial) plus the numeric-depression breach corrector mobilize and redeposit that material through a small set of checked mutation primitives in `cpp/src/engine/sediment_partition.cpp`, and every one of those mutations is replayed from the serialized world by Python validators. This page is the reference for the interface contract, the three transports, the fluvial routing snapshot and its replay, the alluvium-vs-bedrock source partition, the numeric-breach mass transfer, the diagnostic stratigraphy enrichers, and the decimal-quantization tolerance model that makes replay possible. Everything here is bulk geometric volume bookkeeping: dry-rock mass, density, porosity, compaction, grain provenance and chemical weathering are all explicitly marked unresolved in the serialized model, and this page never upgrades that.

## On this page

- [The sediment interface contract](#the-sediment-interface-contract)
- [Checked mutation primitives](#checked-mutation-primitives)
- [Where the interface is initialized and mutated](#where-the-interface-is-initialized-and-mutated)
- [The three transport processes](#the-three-transport-processes)
- [Hillslope transport](#hillslope-transport)
- [Fluvial routing: the stage input snapshot](#fluvial-routing-the-stage-input-snapshot)
- [Fluvial routing: the replay](#fluvial-routing-the-replay)
- [Terminal footprint and proportional allocation](#terminal-footprint-and-proportional-allocation)
- [Glacial transport](#glacial-transport)
- [Alluvium-versus-bedrock source partition](#alluvium-versus-bedrock-source-partition)
- [Numeric-breach excavation and redeposition](#numeric-breach-excavation-and-redeposition)
- [Sedimentary basins and stratigraphic columns](#sedimentary-basins-and-stratigraphic-columns)
- [Diagnostic enrichers: routing, transport history, sequence stratigraphy](#diagnostic-enrichers-routing-transport-history-sequence-stratigraphy)
- [Quantization and the forward-error tolerance model](#quantization-and-the-forward-error-tolerance-model)
- [Per-cell sediment fields](#per-cell-sediment-fields)
- [Validators](#validators)
- [Worked commands](#worked-commands)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

---

## The sediment interface contract

The authoritative geometry is declared by `sediment_interface_model_json` (`cpp/src/engine/process_serialization.cpp:1823`) and mirrored literal-for-literal by the Python replay in `src/magic_geo/sediment_interface_validation.py:11-55`. The model is `explicit_bedrock_surface_mobile_sediment_interface_v1`.

| `sediment_interface_model` field | Value | Meaning |
|---|---|---|
| `model_type` | `explicit_bedrock_surface_mobile_sediment_interface_v1` | Model identity |
| `elevation_unit` | `m` | All three interface fields are metres |
| `canonical_state_fields` | `["bedrock_surface_elevation_m","sediment_thickness_m"]` | The only two authoritative fields |
| `derived_surface_field` | `elevation_m` | Derived, never independently authored |
| `bedrock_surface_semantics` | `top_of_nonmobile_bedrock_below_mobile_sediment_not_moho_or_stratigraphic_basement` | See the note below |
| `interface_equation` | `elevation_m=bedrock_surface_elevation_m+sediment_thickness_m` | Closure identity |
| `initialization_equation` | `bedrock_surface_elevation_m=elevation_m-sediment_thickness_m` | One-time back-solve |
| `material_update_equation` | `bedrock_surface_elevation_m'=bedrock_surface_elevation_m+vertical_displacement_m-bedrock_erosion_depth_m;sediment_thickness_m'=sediment_thickness_m-alluvium_entrainment_depth_m+deposition_depth_m;elevation_m'=bedrock_surface_elevation_m'+sediment_thickness_m'` | The only material update |
| `sea_level_datum_update` | `bedrock_surface_elevation_m'=bedrock_surface_elevation_m-sea_level_adjustment_m;sediment_thickness_m'=sediment_thickness_m` | Datum shifts move bedrock only |
| `replay_tolerance_model` | `decimal_quantization_forward_error_by_serialized_operand_precision_v1` | See [quantization](#quantization-and-the-forward-error-tolerance-model) |
| `canonical_state_serialization_decimal_places` | `10` | Fixed floor for canonical/datum operands |
| `minimum_replay_operand_serialization_decimal_places` | `8` | Fixed floor for stage source/deposition depths |
| `authoritative_interface_geometry` | `true` | The geometry (not mass) is authoritative |
| `bedrock_surface_elevation_is_canonical` | `true` | — |
| `mobile_sediment_thickness_is_canonical` | `true` | — |
| `surface_elevation_is_derived` | `true` | — |
| `dry_rock_mass_resolved` | `false` | Explicitly unresolved |
| `sediment_density_resolved` | `false` | Explicitly unresolved |
| `porosity_resolved` | `false` | Explicitly unresolved |
| `compaction_resolved` | `false` | Explicitly unresolved |
| `grain_provenance_resolved` | `false` | Explicitly unresolved |
| `chemical_weathering_resolved` | `false` | Explicitly unresolved |
| `cell_count` | int | Dynamic; number of cells |
| `maximum_final_closure_residual_m` | double at `max(10, float_precision)` decimals | Native-computed max closure residual |
| `final_interface_closure_validated` | `true` | Native validated the whole cell set at serialization time |

**What the bedrock field does and does not mean.** `bedrock_surface_semantics` states it verbatim: the top of *nonmobile bedrock beneath the mobile sediment column*, **not** the Moho and **not** a stratigraphic basement. It is not the base of the crust, it is not the base of a stratigraphic package, and it carries no lithification, cementation or induration claim. It is simply the elevation at which the mobile-sediment inventory of the cell begins.

**Initialization.** Initial mobile sediment is declared zero everywhere: `sediment_inventory_model.initial_mobile_sediment_inventory == "zero_depth_all_cells_v1"` (`cpp/src/engine/process_serialization.cpp:1969-1970`), which the replay hard-requires (`src/magic_geo/sediment_interface_validation.py:278-284`). `derive_crust_and_topography` sets `cell.elevation_m = cell.initial_elevation_m` and then loops `initialize_sediment_interface(cell, "initial topography")` over every cell (`cpp/src/engine/tectonics.cpp:505-511`). Because thickness is zero at that point, the initial bedrock surface equals the initial elevation exactly.

**Derived-field rule.** The engine README's invariant #2 requires that mutation code update the two canonical fields *through the checked helpers* and derive `elevation_m`; it must not independently mutate all three. In the source tree the only place that writes `bedrock_surface_elevation_m` and `elevation_m` outside a helper is the sea-level strict-depth tie-break in `cpp/src/engine/ocean.cpp:251-269`, which nudges the bedrock operand to the next representable value below `-sediment_thickness_m` so a selected ocean cell cannot round back to signed zero — and it immediately calls `validate_sediment_interface(...)` on the result. Every other mutation path goes through a primitive.

---

## Checked mutation primitives

All six live in `cpp/src/engine/sediment_partition.cpp` and are declared in `cpp/src/engine/internal.hpp:275-302` (private; never exported from the shared library — no sediment-interface symbol appears in `cpp/include/`).

| Primitive | Signature (abridged) | Preconditions checked | Postconditions | Source |
|---|---|---|---|---|
| `validate_sediment_interface` | `(const Cell&, const char* context)` | finite bedrock/thickness/elevation; `thickness >= 0`; nonempty context | throws `"<context> sediment-interface state is nonfinite or negative"` or `"... surface closure failed"` | `sediment_partition.cpp:82` |
| `initialize_sediment_interface` | `(Cell&, const char* context)` | `elevation_m` finite; `sediment_thickness_m` finite and `>= 0` | sets `bedrock = elevation - thickness`, re-derives `elevation = bedrock + thickness`, revalidates | `sediment_partition.cpp:91` |
| `shift_sediment_interface_datum` | `(Cell&, double elevation_change_m, const char* context)` | opening state valid; `elevation_change_m` finite | `bedrock += change`; thickness untouched; `elevation` re-derived | `sediment_partition.cpp:123` |
| `apply_sediment_interface_material_change` | `(Cell&, double vertical_displacement_m, double bedrock_erosion_depth_m, double alluvium_entrainment_depth_m, double deposition_depth_m, const char* context)` | opening state valid; displacement finite; the three depths finite and `>= 0`; entrainment `<=` opening mobile depth within the forward-error bound | `bedrock += displacement - bedrock_erosion`; `thickness += deposition - entrainment` (clamped at 0 from below); `elevation` re-derived; revalidated | `sediment_partition.cpp:155` |
| `maximum_sediment_interface_closure_residual_m` | `(const std::vector<Cell>&, const char* context)` → `double` | cell set nonempty; every cell validates | returns `max |elevation - bedrock - thickness|` over all cells | `sediment_partition.cpp:232` |
| `validate_sediment_source_partition` | `(cells, source_depth_by_cell, alluvium_depth_by_cell, bedrock_depth_by_cell, alluvium_volume_km3, bedrock_volume_km3, context)` | array lengths equal `cells.size()`; `cell.id == index`; positive finite area; all three depths finite and `>= 0`; per-cell `alluvium + bedrock == source` within bound; both aggregate volumes reconstruct from `depth * area_km2 / 1000` | throws on any violation | `sediment_partition.cpp:262` |

The internal arithmetic is done in `long double`, and every stored value passes through `checked_interface_value` (`sediment_partition.cpp:30`), which rejects non-finite results and results whose magnitude exceeds `std::numeric_limits<double>::max()`.

The shared forward-error bound (`sediment_partition.cpp:7-20`) is:

```
bound(term_sum, n_terms, floor) =
    max(floor, 128 * DBL_EPSILON * max(1, n_terms) * (1 + |term_sum|))
```

with `floor = 1.0e-12` at every call site in this file. Closure uses `n_terms = 3`; entrainment availability uses `n_terms = 2`; the aggregate volume check uses `n_terms = 2 * cell_count + 4` (`sediment_partition.cpp:358`).

---

## Where the interface is initialized and mutated

| Call site | Primitive | Context string | Meaning |
|---|---|---|---|
| `cpp/src/engine/tectonics.cpp:509` | `initialize_sediment_interface` | `"initial topography"` | One-time back-solve after initial elevation is composed |
| `cpp/src/engine/ocean.cpp:36` | `shift_sediment_interface_datum` | `"zero-ocean sea-level datum"` | Degenerate zero-inventory sea-level branch |
| `cpp/src/engine/ocean.cpp:245` | `shift_sediment_interface_datum` | `"sea-level datum"` | Every volume-constrained sea-level solve |
| `cpp/src/engine/ocean.cpp:265` | `validate_sediment_interface` | `"sea-level selected-ocean strict-depth tie"` | Revalidation after the signed-zero tie-break |
| `cpp/src/engine/earth_system.cpp:1070` | `apply_sediment_interface_material_change` | `"hillslope/fluvial sediment interface"` | One combined tectonic + hillslope + fluvial change per cell per erosion iteration |
| `cpp/src/engine/environment.cpp:245` | `apply_sediment_interface_material_change` | `"glacial sediment interface"` | Terminal glacial transport |
| `cpp/src/engine/hydrology.cpp:1014` | `apply_sediment_interface_material_change` | `"numeric depression breach excavation"` | Breach path excavation |
| `cpp/src/engine/hydrology.cpp:1083` | `apply_sediment_interface_material_change` | `"numeric depression breach deposition"` | Breach redeposition |
| `cpp/src/engine/earth_system.cpp:1098` | `maximum_sediment_interface_closure_residual_m` | `"post hillslope/fluvial transport"` | Per-iteration audit |
| `cpp/src/engine/environment.cpp:276` | `maximum_sediment_interface_closure_residual_m` | `"post glacial transport"` | Post-glacial audit |
| `cpp/src/engine/hydrology.cpp:1107` | `maximum_sediment_interface_closure_residual_m` | `"post numeric depression breach correction"` | Post-breach audit |
| `cpp/src/engine/hydrology.cpp:1171` | `maximum_sediment_interface_closure_residual_m` | `"post hydrology stabilization"` | Convergence-exit audit |
| `cpp/src/engine/process_serialization.cpp:1828` | `maximum_sediment_interface_closure_residual_m` | `"sediment-interface serialization"` | Populates `maximum_final_closure_residual_m` |

Two of the material-change call sites additionally assert a *compatibility surface* — the surface elevation the old three-field arithmetic would have produced — and throw if the interface update moved it: `"hillslope/fluvial sediment-interface update changed the compatibility surface"` (`earth_system.cpp:1081-1093`, tolerance `max(1e-9, |surface| * 1e-12)`) and the glacial analogue (`environment.cpp:253-263`). The breach path asserts against its own precomputed `breach_target_elevation_m_by_cell` entry with a `1.0e-7` tolerance (`hydrology.cpp:1022-1031`).

---

## The three transport processes

| Process | Native function | Stage record | Stage count | Feedback stage link | Model key |
|---|---|---|---|---|---|
| Hillslope | `transport_hillslope_sediment` (`cpp/src/engine/earth_system.cpp:289`) | `HillslopeSedimentTransportStage` | `erosion.iterations` | `feedback_stage_id = stage_index + 1` | `hillslope_sediment_transport_model` |
| Fluvial | `route_fluvial_sediment` (`cpp/src/engine/earth_system.cpp:448`) | `FluvialSedimentRoutingStage` | `erosion.iterations` | `feedback_stage_id = stage_index + 1` | `fluvial_sediment_routing_model` |
| Glacial | `transport_glacial_sediment` (`cpp/src/engine/environment.cpp:102`) | `GlacialSedimentTransportStage` | exactly 1 | `feedback_stage_id = erosion_iterations + 1` | `glacial_sediment_transport_model` |

The stage-count and feedback-link expectations are enforced by `src/magic_geo/sediment_source_partition_validation.py:340-357` and `:544-553`, and independently by the CLI inventory replay (`src/magic_geo/cli/validators/sediment.py:2755-2763`).

Hillslope and fluvial run inside `erode` (`cpp/src/engine/earth_system.cpp:914`), once per erosion iteration, in that order. Glacial runs once, after the maturation loop and after the first `derive_cryosphere_state`, at pipeline stage 19 (`cpp/src/engine/pipeline.cpp:152-156`). Numeric-breach excavation runs inside `stabilize_numeric_depressions`, which itself is invoked at pipeline stage 14 (initial), once per erosion iteration, and at the cryosphere-coupling stage.

The four processes' aggregate source partitions are published together under `sediment_inventory_model.process_source_partition`, keyed `hillslope` / `fluvial` / `glacial` / `numeric_breach`, each carrying `gross_mobilization_volume_km3`, `alluvium_entrainment_volume_km3`, `bedrock_erosion_volume_km3` and `source_partition_residual_km3` (`cpp/src/engine/process_serialization.cpp:2021-2053`).

---

## Hillslope transport

Model type `pairwise_lithology_dependent_volume_conserving_hillslope_transport_v2` (`cpp/src/engine/process_serialization.cpp:1144`).

| Model field | Value |
|---|---|
| `transport_graph` | `one_directed_transfer_per_eligible_undirected_mesh_edge_v1` |
| `source_selection` | `higher_non_marine_cell_to_lower_adjacent_cell` |
| `effective_diffusivity_model` | `min_stability_cap_configured_reference_diffusivity_times_maturation_timestep_scale_divided_by_source_lithology_resistance` |
| `source_depth_model` | `effective_diffusivity_times_elevation_drop_divided_by_source_neighbor_count` |
| `volume_transfer_model` | `source_depth_times_source_area_equals_target_depth_times_target_area` |
| `source_material_partition_model` | `available_alluvium_first_then_bedrock_erosion_v1` |
| `erosion_stage_source_partition_order` | `hillslope_before_fluvial` |
| `configured_hillslope_diffusivity` | `erosion.hillslope_diffusion`, default `0.055` (`src/magic_geo/config.py:406-411`) |
| `reference_timestep_ma` | `5.0` (`MATURATION_REFERENCE_TIMESTEP_MA`) |
| `nominal_timestep_ma` | `erosion.maturation_timestep_ma`, default `5.0`, constrained `0 < x <= 5.0` (`src/magic_geo/config.py:382-387`) |
| `maturation_timestep_scale` | `nominal_timestep_ma / 5.0` (`cpp/src/engine/core.cpp:44-47`) |
| `reference_step_response_timestep_scaled` | `true` |
| `time_step_convergence_demonstrated` | **`false`** |
| `maximum_effective_diffusivity` | `0.45` (`HILLSLOPE_MAX_EFFECTIVE_DIFFUSIVITY`, `cpp/src/engine/constants.hpp:66`) |
| `source_lithology_resistance` | map over `LITHOLOGY_NAMES`, see below |
| `mass_conserving` | `true`, with `mass_conserving_semantics = bulk_reference_volume_only_not_dry_rock_mass` |
| `physical_time_resolved` | **`false`** |
| `shared_boundary_geometry_resolved` | **`false`** |
| `regolith_depth_resolved` | `true` |
| `model_limitation` | `procedural_bulk_transport_without_calibrated_time_shared_boundary_flux_or_grain_classes` |
| `stage_input_snapshot` | `complete_cell_elevation_water_lake_lithology_and_sediment_inventory_state_before_transport_v2` |

Lithology resistance (`cpp/src/engine/tectonics.cpp:204-215`, mirrored in `src/magic_geo/cli/_constants.py:50-58`):

| Lithology | Resistance |
|---|---|
| `basalt` | 0.85 |
| `granite` | 1.25 |
| `limestone` | 0.75 |
| `sandstone` | 0.82 |
| `shale` | 0.62 |
| `volcanic` | 0.95 |
| `metamorphic` | 1.35 |

Per undirected mesh edge `(a, b)` with `b > a` (`earth_system.cpp:328-354`): the higher-elevation cell is the source; the edge is skipped when the source `is_water` or `elevation_drop_m <= 1.0e-12`. Then

```
effective_diffusivity = min(0.45, max(0, hillslope_diffusion) * maturation_timestep_scale / max(1e-12, resistance(source_lithology)))
source_depth_m        = effective_diffusivity * elevation_drop_m / source_neighbor_count
transfer_volume_km3   = source_depth_m * source_area_km2 / 1000
target_depth_m        = transfer_volume_km3 * 1000 / target_area_km2
```

Each edge record (`edges[]`, 21 fields) carries `mesh_edge_cell_a_id`/`mesh_edge_cell_b_id` alongside `source_cell_id`/`target_cell_id`, so the undirected mesh edge and the directed transfer are both witnessed. `mass_balance_residual_km3` per edge is `|transfer_volume - target_depth * target_area / 1000|`.

**Stage history.** `hillslope_sediment_transport_history[]` carries `id`, `feedback_stage_id`, `erosion_iteration`, the nominal-time block, edge and cell counts, the four volume aggregates, the three cell-indexed depth arrays (`source_production_depth_m_by_cell`, `alluvium_entrainment_depth_m_by_cell`, `bedrock_erosion_depth_m_by_cell`), `mean_effective_diffusivity`, `input_cell_count`, the full `input_cells[]` snapshot (6 fields: `cell_id`, `lithology`, `is_water`, `is_lake`, `elevation_m`, `sediment_thickness_m`) and `edges[]`.

---

## Fluvial routing: the stage input snapshot

Model type `topological_capacity_limited_fluvial_sediment_routing_v1` (`cpp/src/engine/process_serialization.cpp:1450`).

| Model field | Value |
|---|---|
| `material_unit` | `km3` |
| `routing_graph` | `erosion_stage_acyclic_hydrologic_flow_to_v1` |
| `transport_capacity_model` | `bounded_dimensionless_flow_slope_runoff_river_capacity_fraction_v1` |
| `depression_deposition_model` | `explicit_spill_elevation_accommodation_then_capacity_and_lake_trap_v1` |
| `land_terminal_model` | `depression_footprint_proportional_accommodation_then_area_weighted_aggradation_v1` |
| `marine_terminal_model` | `water_body_class_deposition_then_unresolved_deep_marine_export_v1` |
| `cell_depth_conversion` | `volume_km3_times_1000_divided_by_cell_area_km2` |
| `source_material_partition_model` | `available_alluvium_after_hillslope_then_bedrock_erosion_v1` |
| `stage_input_snapshot` | `complete_cell_hydrology_topology_environment_and_provisional_surface_v1` |
| `stage_input_snapshot_cell_id_indexed` | `true` |
| `stage_input_snapshot_used_for_replay` | `true` |
| `source_material_partition_is_coupled_external_state` | `true` |
| `local_source_is_timestep_scaled_upstream` | `true` |
| `routing_partition_fractions_timestep_invariant` | `true` |
| `time_step_convergence_demonstrated` | **`false`** |
| `mass_conserving` | `true` (`bulk_reference_volume_only_not_dry_rock_mass`) |
| `depression_fill_deposition_is_cross_cut` | `true` |
| `grain_size_resolved` | **`false`** |
| `physical_time_resolved` | **`false`** |
| `subcell_channel_geometry_resolved` | **`false`** |
| `model_limitation` | `dimensionless_capacity_proxy_without_grain_size_calibrated_time_or_subcell_channels` |

Routing constants (`cpp/src/engine/constants.hpp:59-65`, mirrored in `src/magic_geo/cli/_constants.py:39-45` and `src/magic_geo/sediment_interface_validation.py:81-87`):

| Constant | Value | Model key |
|---|---|---|
| `FLUVIAL_SEDIMENT_MIN_TRANSPORT_CAPACITY_FRACTION` | `0.90` | `minimum_transport_capacity_fraction` |
| `FLUVIAL_SEDIMENT_MAX_TRANSPORT_CAPACITY_FRACTION` | `0.995` | `maximum_transport_capacity_fraction` |
| `FLUVIAL_SEDIMENT_LAKE_TRAP_FRACTION` | `0.35` | `overflowing_lake_trap_fraction` |
| `FLUVIAL_SEDIMENT_CLOSED_LAKE_TRAP_FRACTION` | `0.65` | `closed_lake_trap_fraction` |
| `FLUVIAL_SEDIMENT_OPEN_OCEAN_DEPOSITION_FRACTION` | `0.12` | `open_ocean_deposition_fraction` |
| `FLUVIAL_SEDIMENT_SHELF_DEPOSITION_FRACTION` | `0.55` | `continental_shelf_deposition_fraction` |
| `FLUVIAL_SEDIMENT_INLAND_SEA_DEPOSITION_FRACTION` | `0.30` | `inland_sea_deposition_fraction` |

**The snapshot itself.** Before any routing happens, `route_fluvial_sediment` walks all cells in id order and pushes one `FluvialSedimentRoutingInputCell` per cell (`cpp/src/engine/earth_system.cpp:496-513`). This is the complete cell-indexed routing-input state, and it is the *only* operand set the replay is permitted to use.

| `input_cells[i]` field | Source | Role in replay |
|---|---|---|
| `cell_id` | loop index | must equal `i` (`sediment_interface_validation.py:716-723`) |
| `flow_to_cell_id` | `cell.flow_to` | receiver; `-1 <= x < cell_count`, `!= cell_id` |
| `depression_component_id` | `cell.depression_component_id` | depression membership |
| `depression_sink_cell_id` | `cell.depression_sink_cell_id` | terminal-footprint key |
| `water_body_type` | `cell.water_body` | must be in `FLUVIAL_WATER_BODY_TYPES` (`land`, `ocean`, `continental_shelf`, `inland_sea`, `fresh_lake`, `saline_basin`) |
| `is_water`, `is_river`, `is_lake`, `lake_overflows` | cell flags | must be strict `bool`; `is_water`/`is_lake` must agree with the same-iteration hillslope snapshot |
| `cell_area_km2` | `cell.area_km2` | must match `cells[i].area_km2` at 10 decimals |
| `flow_accumulation` | `cell.flow_accumulation` | capacity term |
| `runoff_mm_y` | `cell.runoff_mm_y` | capacity term |
| `hydrologic_flow_slope` | `cell.hydrologic_flow_slope` | capacity term |
| `routing_base_elevation_m` | the provisional surface `next[i]` | accommodation datum |
| `spill_elevation_m` | `cell.spill_elevation_m` | accommodation ceiling |

`routing_base_elevation_m` is not the current cell elevation. It is the *provisional* surface computed in the same iteration (`cpp/src/engine/earth_system.cpp:969-995`):

```
next[i] = elevation_m
        + tectonic_elevation_change[i]
        - hillslope_production_depth_m[i]
        + hillslope_deposition_depth_m[i]
        - stream_power_erosion_depth_m[i]      // land cells only
```

**Round-trip precision.** `fluvial_sediment_routing_history_json` sets `evidence_precision = max(max_digits10, float_precision)` for *all* volumes and surface depths in the history (`cpp/src/engine/process_serialization.cpp:1547-1557`), with the in-source rationale that these are "replay operands, not presentation-only diagnostics" and must not accept a scale-relative tolerance "large enough to conceal a material-volume mutation".

**Stream-power source.** Fluvial local source depth is not produced by the router; it is the stream-power incision computed in `erode` (`earth_system.cpp:978-995`):

```
acc_norm     = clamp(flow_accumulation / acc_scale, 0, 3)
erodability  = 1 / lithology_resistance(lithology)
stream       = stream_power_coefficient * erodability * acc_norm^drainage_exponent * max(0, slope*900)^slope_exponent
erosion_depth_m = stream * maturation_timestep_scale
cell.erosion_rate = stream            // exported as the 5 Ma reference response, NOT the applied depth
```

`acc_scale` is `max(1.0, 95th-percentile land flow accumulation)` for the iteration (`earth_system.cpp:939-946`) and is serialized per stage as `accumulation_scale`. The engine deliberately exports the unscaled `stream` as `erosion_rate` so that merely refining `maturation_timestep_ma` does not change downstream soils/ecosystem/land-use diagnostics by construction (comment at `earth_system.cpp:988-992`).

---

## Fluvial routing: the replay

The replay lives in `src/magic_geo/sediment_interface_validation.py` inside `erosion_deposition_depths` (`:547-1571`). It never reads a live simulation; it reads only the serialized `input_cells[]` snapshot, `source_production_depth_m_by_cell`, and `accumulation_scale`.

**Deriving the acyclic active graph.** The replay builds `upstream_count` from `flow_to_cell_id`, seeds a min-heap with every zero-in-degree cell and runs Kahn's algorithm (`sediment_interface_validation.py:798-826`). If the resulting `flow_order` does not cover all cells it raises `"fluvial routing input graph contains a cycle"`. The native side does exactly the same with `std::priority_queue<int, std::vector<int>, std::greater<int>>` and throws `"fluvial sediment routing graph contains a cycle"` (`earth_system.cpp:515-539`). The replay then requires that emitted `cell_steps[]` appear in strictly increasing `flow_rank` order (`:887-897`).

**Active-cell threshold.** A cell only produces a `cell_steps[]` record when `local_source + incoming > 1.0e-15 km³` (`earth_system.cpp:554`, `:567-570`). The replay requires that every emitted step has `expected_available > 1.0e-15` (`:1021-1024`), and that every *omitted* cell has `source + incoming <= 1.0e-15` (`:1210-1220`). The source-partition validator applies the same `FLUVIAL_ACTIVE_VOLUME_THRESHOLD_KM3 = 1.0e-15` from the other direction (`src/magic_geo/sediment_source_partition_validation.py:9`, `:317-328`).

**The environmental branch.** Each active cell takes exactly one of three branches, decided purely from snapshot state:

| Branch | Condition | Outcome |
|---|---|---|
| Marine terminal | `is_water and flow_to < 0` | `marine_deposition = available * f(water_body_type)`; `terminal_export = available - marine_deposition` |
| Land terminal | `not is_water and flow_to < 0` | `terminal_land_storage = available`; recorded in `terminal_storage_by_sink[cell_id]` |
| Routed | `flow_to >= 0` | capacity / depression / lake-trap cascade below |

The replay additionally asserts `not (is_water and flow_to >= 0)` — a wet cell must be a terminal (`:926-931`).

Marine deposition fractions by `water_body_type` (`earth_system.cpp:594-600`, replay `:1039-1052`): `continental_shelf` → `0.55`, `inland_sea` → `0.30`, everything else (including `ocean`) → `0.12`. The remainder is `terminal_export_volume_km3` — declared by the model name as `unresolved_deep_marine_export`, i.e. it leaves the accounted domain.

**Routed-cell cascade** (`earth_system.cpp:617-699`, replay `:1059-1131`), evaluated strictly in this order:

```
flow_index    = min(1, sqrt(max(0, flow_accumulation) / max(1, accumulation_scale)))
slope_index   = min(1, max(0, hydrologic_flow_slope) * 1200)
runoff_index  = min(1, max(0, runoff_mm_y) / 2000)
capacity_fraction = clamp(0.90 + 0.045*flow_index + 0.025*slope_index + 0.015*runoff_index + (is_river ? 0.015 : 0),
                          0.90, 0.995)

remaining = available
if depression_component_id >= 0:
    depression_accommodation = max(0, spill_elevation_m - routing_base_elevation_m) * area_km2 / 1000
    depression_fill          = min(remaining, depression_accommodation);  remaining -= depression_fill
capacity_deposition = min(remaining, available * (1 - capacity_fraction)); remaining -= capacity_deposition
if is_lake:
    lake_fraction = lake_overflows ? 0.35 : 0.65
    lake_trap     = min(remaining, max(0, available*lake_fraction - depression_fill - capacity_deposition))
    remaining    -= lake_trap
routed_outgoing = max(0, remaining)
```

Note the sign of the capacity term: `capacity_fraction` is the fraction *transported onward*, so `1 - capacity_fraction` (at most 0.10, at least 0.005) is the fraction deposited in place. `routed_outgoing` is added to the receiver's incoming volume unconditionally; the `> 1.0e-15` test gates only the `routed_edge_count` increment (`earth_system.cpp:687-699`, replay `:1160-1168`).

Each step's `local_mass_balance_residual_km3` is the signed leftover after subtracting all seven sinks from `available` (`earth_system.cpp:701-709`), and the replay reproduces it exactly (`:1145-1159`).

**Stage aggregate checks.** The replay reconstructs and requires all of `local_source_volume_km3`, `routed_throughput_volume_km3`, `capacity_deposition_volume_km3`, `depression_fill_deposition_volume_km3`, `lake_trap_deposition_volume_km3`, `terminal_land_deposition_volume_km3`, `marine_deposition_volume_km3`, `terminal_export_volume_km3`, `alluvium_entrainment_volume_km3`, `bedrock_erosion_volume_km3`, `total_deposition_volume_km3` and `mass_balance_residual_km3` (`:1549-1570`). Two relations are worth calling out:

- `total_deposition_volume_km3 = local_source_volume_km3 - terminal_export_volume_km3` — declared, not measured (per-stage at `cpp/src/engine/process_serialization.cpp:1646-1648`, model-level at `:1533-1535`).
- The physical total subtracts `terminal_accommodation_volume` from `depression_fill_deposition_volume_km3` because terminal accommodation is double-counted into that bucket by design (`:1541-1548`); `depression_fill_deposition_is_cross_cut = true` is the model's declaration of exactly this.

---

## Terminal footprint and proportional allocation

Land-terminal storage is not deposited at the sink cell. It is redistributed across the sink's **depression footprint** (`earth_system.cpp:713-846`, replay `:1222-1500`).

**Footprint construction.** For every cell, if `not is_water and depression_component_id >= 0 and 0 <= depression_sink_cell_id < n`, the cell is appended to `terminal_targets_by_sink[depression_sink_cell_id]` in ascending cell id. If a sink has an empty target list, the fallback target list is `[sink_id]` (`earth_system.cpp:737-739`). The replay reconstructs the same ordered key list and requires `len(terminal_allocations) == len(expected_allocation_keys)` and that every emitted `(sink_cell_id, target_cell_id)` pair matches the expected list positionally and is strictly increasing (`:1234-1274`).

**Inactive targets are still emitted.** A `terminal_allocations[]` record is written for *every* footprint member, including members that end up with zero deposition. `terminal_allocation_count` counts only allocations whose `total_deposition_volume_km3 > 1.0e-15` (`earth_system.cpp:848-854`; the replay counts the same way at `:1477-1478`). So `len(terminal_allocations) >= terminal_allocation_count`, and the difference is exactly the inactive footprint.

**Two-phase allocation.**

Phase 1 — accommodation, proportional to remaining accommodation capacity:

```
prior_local_deposition = capacity_deposition + depression_fill + lake_trap        (at the target)
prior_local_depth      = prior_local_deposition * 1000 / target_area_km2
accommodation[t]       = depression_component_id(t) >= 0
                         ? max(0, spill_elevation(t) - routing_base(t) - prior_local_depth) * area(t) / 1000
                         : 0
accommodation_total    = min(terminal_load, sum(accommodation))
```

Each target then receives `min(remaining, accommodation_total * accommodation[t] / total_accommodation)`, except the **last target with positive accommodation** (`last_accommodation_target`), which absorbs the whole remainder so the phase closes exactly (`earth_system.cpp:779-818`, replay `:1414-1441`).

Phase 2 — excess aggradation, proportional to target area:

```
excess_total = terminal_load - accommodation_total
```

Each target receives `min(remaining_excess, excess_total * area(t) / max(1e-15, total_area))`, except the **last target in the list**, which absorbs the remainder (`earth_system.cpp:820-842`, replay `:1443-1457`).

The replay reproduces the native *ordered* accumulation of `total_capacity` and `total_area` term by term rather than using `math.fsum`, with an explicit comment that a different summation algorithm can flip a `min`/proportional branch at large magnitudes (`:1403-1411`).

Per-allocation fields (11), all replayed: `sink_cell_id`, `target_cell_id`, `depression_component_id`, `target_area_km2`, `routing_base_elevation_m`, `spill_elevation_m`, `prior_local_deposition_volume_km3`, `accommodation_before_allocation_km3`, `accommodation_deposition_volume_km3`, `excess_aggradation_volume_km3`, `total_deposition_volume_km3`.

**Dry-world fallback.** A land world can leave its global land sink outside every depression component. The replay accepts a single documented fallback shape — `target_id == sink_id`, target not water, `flow_to < 0`, `depression_component_id == -1`, `depression_sink_cell_id == -1`, allocation `depression_component_id == -1` — and rejects any other non-component target (`:1317-1336`).

---

## Glacial transport

Model type `downhill_area_conserving_glacial_sediment_transport_v2` (`cpp/src/engine/process_serialization.cpp:848-849`).

| Model field | Value |
|---|---|
| `routing_graph` | `single_steepest_downhill_mesh_neighbor_v1` |
| `source_state` | `post_erosion_pre_cryosphere_feedback_cell_state_v1` |
| `erosion_potential_model` | `ice_thickness_times_local_slope_proxy_bounded_85m_v1` |
| `mobile_sediment_fraction` | `0.28` (`GLACIAL_SEDIMENT_MOBILE_FRACTION`, `cpp/src/engine/constants.hpp:67`) |
| `source_depth_model` | `glacial_erosion_potential_times_mobile_sediment_fraction` |
| `source_material_partition_model` | `available_alluvium_first_then_bedrock_erosion_v1` |
| `stage_input_snapshot` | `complete_cell_cryosphere_terrain_and_sediment_inventory_before_transport_v2` |
| `volume_transfer_model` | `source_depth_times_source_area_equals_target_depth_times_target_area` |
| `mass_conserving` | `true` (`bulk_reference_volume_only_not_dry_rock_mass`) |
| `finite_sediment_inventory_resolved` | `true` |
| `terrain_elevation_coupled` | `true` |
| `earth_system_recomputed_after_transport` | `true` |
| `physical_time_resolved` | **`false`** |
| `multi_step_ice_dynamics_resolved` | **`false`** |
| `model_limitation` | `single_post_erosion_bulk_transfer_without_calibrated_time_multistep_ice_dynamics_or_grain_classes` |

The erosion potential itself comes from `derive_cryosphere_state`: `glacial_erosion_m = clamp((ice_thickness_m / 1000) * max(0, slope*900) * 12, 0, 85)` (`cpp/src/engine/environment.cpp:89`), which is where the `bounded_85m` in the model name comes from.

Transport is one transfer per source with `glacier_flow_to >= 0` and `glacial_erosion_m > 0` (`environment.cpp:136-141`); the target must be a listed neighbor of the source or the engine throws `"glacial sediment transfer target is invalid"` (`:142-153`). Source depth is `glacial_erosion_m * 0.28`; volume and target depth follow the same `depth * area / 1000` / `volume * 1000 / area` conversion as hillslope. Because at most one transfer exists per source, `source_cell_count == transfer_count` (`environment.cpp:280-281`), and the source-partition replay explicitly rejects a repeated glacial source (`src/magic_geo/sediment_source_partition_validation.py:271`).

The glacial stage is the only one that serializes `post_transport_elevation_m_by_cell` (`environment.cpp:274`), and it sets `terrain_volume_change_residual_km3 = mass_balance_residual_km3` (`environment.cpp:283-287`).

---

## Alluvium-versus-bedrock source partition

Every gram-free unit of material a process mobilizes must come from one of two places: the cell's existing mobile inventory (**alluvium entrainment**) or newly cut bedrock (**bedrock erosion**). The rule is `available_alluvium_first_then_bedrock_erosion_v1`, and within an erosion iteration the order across processes is `hillslope_then_fluvial` (`sediment_inventory_model`, `cpp/src/engine/process_serialization.cpp:1971-1974`).

The native combined commit loop (`cpp/src/engine/earth_system.cpp:1010-1097`) does exactly:

```
available = cells[i].sediment_thickness_m                     // opening inventory, before this iteration
hillslope_alluvium = min(available, hillslope_source_depth)
available         -= hillslope_alluvium
fluvial_alluvium   = min(available, fluvial_source_depth)
hillslope_bedrock  = max(0, hillslope_source_depth - hillslope_alluvium)
fluvial_bedrock    = max(0, fluvial_source_depth  - fluvial_alluvium)
```

and then issues **one** `apply_sediment_interface_material_change` per cell carrying the *combined* tectonic displacement, combined bedrock erosion, combined alluvium entrainment, and combined deposition (fluvial `sediment_delta` + hillslope deposition). `same_stage_deposition_available_for_entrainment` is declared **`false`** — this iteration's own deposition is not entrainable this iteration.

Glacial (`cpp/src/engine/environment.cpp:214-235`) and numeric breach (`cpp/src/engine/hydrology.cpp:1001-1009`) apply the same two-line `min` / `max(0, ...)` rule per cell against the inventory standing at their own moment.

**Depth arrays.** Every stage serializes three cell-indexed arrays that are the audit surface:

| Array | Semantics |
|---|---|
| `source_production_depth_m_by_cell` | The stage's per-cell demand (`source_partition_audit_demand_field`) |
| `alluvium_entrainment_depth_m_by_cell` | Portion satisfied from existing mobile inventory |
| `bedrock_erosion_depth_m_by_cell` | Portion cut from bedrock |

**These arrays are neither a mass claim nor a provenance claim.** Every one of the three transport models declares, verbatim — hillslope `process_serialization.cpp:1160-1166`, fluvial `:1473-1479`, glacial `:862-868` (the `mass_conserving_semantics` pair sits alongside at `:1185-1187`, `:1483-1485` and `:873-875`):

| Metadata key | Value |
|---|---|
| `per_cell_source_partition_audit_present` | `true` |
| `source_partition_audit_depth_unit` | `m` |
| `source_partition_audit_array_index` | `cell_id` |
| `source_partition_audit_demand_field` | `source_production_depth_m_by_cell` |
| `source_partition_audit_is_mass_claim` | **`false`** |
| `source_partition_audit_is_provenance_claim` | **`false`** |
| `mass_conserving_semantics` | `bulk_reference_volume_only_not_dry_rock_mass` |

`COMMON_AUDIT_METADATA` in `src/magic_geo/sediment_source_partition_validation.py:11-24` reproduces this set and requires every model to carry it exactly. The partition says *which reservoir a depth was drawn from*, in metres of column. It does not say how much dry rock that is, what it is made of, or where any individual grain came from.

**Native aggregation checks.** After every erosion iteration `erode` calls `validate_sediment_source_partition` twice, with contexts `"hillslope"` and `"fluvial"` (`earth_system.cpp:1102-1119`); `transport_glacial_sediment` calls it once with context `"glacial"` (`environment.cpp:289-297`). Each call re-derives `sum(depth * area_km2 / 1000)` for both partitions and compares against the stage's emitted `alluvium_entrainment_volume_km3` / `bedrock_erosion_volume_km3`, throwing `"<ctx> sediment source-partition volumes do not reconstruct"` on failure. Those three are the only `validate_sediment_source_partition` call sites in the engine — there is none for the numeric breach, whose aggregates are audited by the Python replay instead.

**Python replay.** `validate_sediment_source_partitions` (`src/magic_geo/sediment_source_partition_validation.py:504`) reconstructs, for each mechanism and stage: the three depth arrays with a per-cell partition identity check, the three bulk volumes via `math.fsum(area*depth/1000)`, the per-cell demand from the route records (`edges[]` for hillslope, `transfers[]` for glacial, the declared array for fluvial), and the model-level `total_*` mirrors. `_validate_alluvium_first_rules` (`:441`) then replays the exact `min`/`max` sequence per cell per erosion iteration from the hillslope `input_cells[]` opening inventory, plus the single glacial stage.

---

## Numeric-breach excavation and redeposition

The numeric-depression corrector is documented in full on the hydrology page; this section covers only its sediment mutation. Mechanism key `numeric_breach`. Selection is `apply_only_lower_volume_depth_bounded_capacity_sufficient_conflict_free_breaches_else_defer_without_material` (`src/magic_geo/cli/_constants.py:33-35`).

| Constant | Value | Source |
|---|---|---|
| `NUMERIC_DEPRESSION_CORRECTION_MAX_PASSES` | `16` | `cpp/src/engine/constants.hpp:55` |
| `NUMERIC_DEPRESSION_FILL_DEPTH_TOLERANCE_M` | `1.0e-9` | `cpp/src/engine/constants.hpp:56` |
| `NUMERIC_DEPRESSION_BREACH_GRADIENT_STEP_M` | `0.001` | `cpp/src/engine/constants.hpp:57` |
| `NUMERIC_DEPRESSION_SELECTED_BREACH_MAX_DEPTH_M` | `50.0` | `cpp/src/engine/constants.hpp:58` |
| Mobile-sediment ceiling for deposition capacity | `5000.0` m | literal at `cpp/src/engine/hydrology.cpp:921`, mirrored as `NUMERIC_DEPRESSION_MAX_MOBILE_SEDIMENT_M` in `src/magic_geo/sediment_interface_validation.py:97` |

A breach is selected only when all four gates pass (`hydrology.cpp:961-966`): `breach_has_lower_adjustment_volume` (excavation volume `+ 1e-9 <` the alternative fill volume), `breach_depth_bound_passed` (max excavation `<= 50 m + 1e-9`), `breach_deposition_capacity_sufficient` (capacity `+ 1e-9 >=` excavation volume) and `breach_same_pass_conflict_free`. Otherwise `temporary_numeric_lake_selected` is set, no material moves, and `correction_mass_balance_residual_km3` is 0.

**Excavation.** For each breach-path cell with `excavation_depth_m > 1e-9`, the corrector partitions alluvium-first and calls `apply_sediment_interface_material_change(cell, 0, bedrock, alluvium, 0, "numeric depression breach excavation")` (`hydrology.cpp:986-1020`), then asserts the resulting `elevation_m` matches the precomputed `breach_target_elevation_m_by_cell` within `1e-7`.

**Redeposition.** Deposition candidates are the depression component's cells *excluding* every cell that was excavated on this path (`hydrology.cpp:896-934`). Per candidate:

```
usable_depth   = min(fill_depth_m_by_cell[i], max(0, 5000 - sediment_thickness_before_correction[i]))
skip if usable_depth <= 1e-9
capacity_volume = usable_depth * area_km2 / 1000
```

Then, over candidates in order, the excavated volume is allocated proportionally to capacity, with the last candidate absorbing the remainder and every allocation additionally clipped by its own capacity:

```
proportional = applied_excavation * capacity_volume / breach_deposition_capacity
deposition   = min(capacity_volume, last ? remaining : min(remaining, proportional))
skip if deposition <= 1e-12
depth        = deposition * 1000 / area_km2
apply_sediment_interface_material_change(cell, 0, 0, 0, depth, "numeric depression breach deposition")
```

If `remaining > 1e-7` after the loop the engine throws `"numeric depression breach deposition capacity was not realized"` (`hydrology.cpp:1111-1115`). `correction_mass_balance_residual_km3` is `|applied_excavation - applied_deposition|`.

The Python replay reproduces all of this from the event record (`src/magic_geo/sediment_interface_validation.py:1869-2251`), including: the mobile-inventory snapshot check on `sediment_thickness_before_correction_m_by_cell`, the excavation geometry `max(0, elevation_before - target_elevation)`, the alluvium/bedrock split, the candidate filter, the proportional allocation, the emitted `breach_deposition_cell_ids` order, and the five event aggregates (`breach_deposition_capacity_km3`, `applied_breach_excavation_volume_km3`, `applied_alluvium_entrainment_volume_km3`, `applied_bedrock_erosion_volume_km3`, `applied_breach_deposition_volume_km3`) plus `correction_mass_balance_residual_km3`.

Two per-cell counters record the outcome: `cumulative_numeric_depression_breach_excavation_m` and `cumulative_numeric_depression_breach_deposition_m`, with `numeric_depression_breach_event_count` (`cpp/src/engine/entity_serialization.cpp:265-271`).

---

## Sedimentary basins and stratigraphic columns

Both are native (`cpp/src/engine/environment.cpp`), produced at pipeline stages 30 and 31, and both are read-only over the final cell state — they are classifications, not simulations.

**Basin cell eligibility** (`is_sedimentary_basin_cell`, `environment.cpp:672-679`): the cell must be land with a valid `basin_id`, and must satisfy any of `crust_type == 7`, `crust_type == 6`, `sediment_thickness_m > 0.55`, or `landform` in `{3, 4, 8, 11, 12, 14}`.

**Basin type** (`sedimentary_basin_type_for_cell`, `environment.cpp:653-670`), first match wins:

| Condition | Type id | `SEDIMENTARY_BASIN_TYPE_NAMES` |
|---|---|---|
| `landform == 4` or `water_body == 5` or `resource == 4` | 4 | `evaporite_basin` |
| `landform == 3` or `is_lake` or `is_closed_basin` | 3 | `lacustrine_basin` |
| `landform == 12` or (`is_river` and has an ocean neighbor) | 5 | `deltaic_basin` |
| `crust_type == 6` or `boundary_divergent > 0.32` | 0 | `rift_basin` |
| `boundary_convergent > 0.24` and `sediment_thickness_m > 0.30` | 1 | `foreland_basin` |
| otherwise | 2 | `passive_margin` |

Per-basin aggregation is area-weighted; the emitted record has 11 fields (`cpp/src/engine/entity_serialization.cpp:533-555`): `id`, `basin_id`, `type`, `dominant_resource`, `cell_count`, `is_active`, `area_km2`, `mean_sediment_thickness_m`, `max_sediment_thickness_m`, `mean_subsidence_index`, `depositional_age_ma`. Basins are sorted by descending area (ties by `basin_id`) and then reindexed `id = 0..n-1` (`environment.cpp:751-759`).

Derived quantities (`environment.cpp:697-728`):

```
subsidence(cell)      = clamp(0.20 + 0.42*boundary_divergent + 0.22*(crust_type==7) + 0.16*clamp(thickness/3.5,0,1), 0, 1)
depositional_age_ma   = clamp(1.5 + 0.045*mean_crust_age_ma + 10/(1 + mean_sediment_thickness_m), 0.1, 320)
is_active             = any member cell is a river, is a lake, has an ocean neighbor, or has thickness > 0.9
```

**Stratigraphic columns** (`generate_stratigraphic_columns`, `environment.cpp:847`). One column per basin with `cell_count > 0`. The representative cell is the basin's thickest-sediment cell. 13 column keys — 12 scalars plus a `layers[]` array (`entity_serialization.cpp:557-599`): `id`, `basin_id`, `representative_cell_id`, `dominant_facies`, `sequence_phase`, `is_active`, `layer_count`, `total_thickness_m`, `depositional_span_ma`, `mean_subsidence_index`, `sediment_flux_index`, `preservation_potential`, `layers`.

```
total_thickness_m     = max(0.05, 0.55*max_sediment_thickness_m + 0.45*mean_sediment_thickness_m)
depositional_span_ma  = clamp(depositional_age_ma * (0.45 + 0.45*mean_subsidence_index), 0.05, max(0.05, depositional_age_ma))
sediment_flux_index   = clamp(0.20 + 0.24*clamp(mean_runoff/1200,0,1.4) + 0.28*clamp(mean_thickness/4,0,1.3)
                              + 0.22*river_fraction + 0.16*mean_subsidence_index, 0, 1)
preservation_potential= clamp(0.22 + 0.44*mean_subsidence_index + 0.20*clamp(total_thickness/4,0,1)
                              + (is_active ? 0.08 : -0.04) - 0.10*clamp(local_relief/900,0,1), 0, 1)
layer_count           = clamp(2 + int(total_thickness_m / 1.15) + (is_active ? 1 : 0), 2, 5)
```

`sequence_phase_for_basin` (`environment.cpp:763-777`) maps to `SEQUENCE_PHASE_NAMES = {aggradation, progradation, retrogradation, starved, erosional}`: inactive and `mean_thickness < 0.35` → `erosional` (4); type `evaporite_basin` → `starved` (3); type `deltaic_basin` → `progradation` (1); active `passive_margin` → `retrogradation` (2); otherwise `aggradation` (0). The layer thickness weights are then driven by that phase (`environment.cpp:929-940`).

Facies come from `STRATIGRAPHIC_FACIES_NAMES` (9 values: `alluvial_fan`, `fluvial_channel`, `floodplain_mud`, `deltaic_sand`, `lacustrine_mud`, `evaporite`, `shallow_marine`, `deep_marine`, `glacial_till`) via `stratigraphic_facies_for_layer` (`environment.cpp:779-808`), which branches first on glacial state (`ice_thickness_m > 25` or `landform` in `{18, 19}` → `glacial_till` on top, `lacustrine_mud` below) and then on basin type and vertical position. Each of the 9 layer fields is a lookup or a clamp:

| Layer field | Derivation |
|---|---|
| `index` | 0-based, base to top |
| `facies` | `stratigraphic_facies_for_layer` |
| `thickness_m` | `total_thickness_m * weight[i] / sum(weights)` |
| `age_base_ma` / `age_top_ma` | linear split of `depositional_span_ma`; the topmost layer's `age_top_ma` is pinned to `top_age` |
| `grain_size_index` | `facies_grain_size(facies)` (`environment.cpp:810-823`) |
| `organic_potential` | `clamp(facies_organic_potential + (dominant_resource==3 ? 0.20 : 0) + 0.10*preservation_potential, 0, 1)` |
| `seal_quality` | `clamp(facies_seal_quality + (dominant_resource==4 ? 0.18 : 0), 0, 1)` |
| `reservoir_quality` | `clamp(0.18 + 0.68*grain_size_index + 0.14*sediment_flux_index - 0.34*seal_quality, 0, 1)` |

All basin and column numeric fields serialize at plain `output.float_precision` — these are diagnostics, not replay operands.

---

## Diagnostic enrichers: routing, transport history, sequence stratigraphy

Three Python enrichers add sediment products on top of the native world. They run in both `generate_world` and `generate_geo_world` (`src/magic_geo/api.py:215-219` and `:332-335`) but at slightly different positions: in the geo-only path `hydrology_realism` precedes `sediment_routing_history`, while in the full path it follows it.

| Enricher | Module | Signature | World keys added | Cell fields added |
|---|---|---|---|---|
| `enrich_world_with_sediment_routing_history` | `src/magic_geo/sediment_routing.py:82` | `(world, route_limit=12, max_path_length=72)` | `sediment_routing_histories` | `sediment_routing_load_m`, `sediment_routing_deposition_m`, `sediment_routing_export_m`, `sediment_routing_path_count` |
| `enrich_world_with_sediment_transport_history` | `src/magic_geo/sediment_dynamics.py:44` | `(world, step_count=6)` | `sediment_transport_histories` | — |
| `enrich_world_with_sequence_stratigraphy` | `src/magic_geo/sequence_stratigraphy.py:84` | `(world)` | `sequence_stratigraphy_histories`; annotates each `stratigraphic_columns[]` record | — |

**Sediment routing histories.** Selects up to `route_limit` source cells preferring `is_river` cells with `flow_to >= 0` and `fluvial_sediment_routed_outgoing_m > 0` (falling back to non-river cells with the same two conditions when no river candidate exists), ranked by `routed_outgoing_m * max(1, flow_accumulation)^0.25` and then by `flow_accumulation`, with a soft basin-diversity rule (`sediment_routing.py:22-55`). It walks each downstream `flow_to` chain up to `max_path_length` cells and runs a per-step load balance whose transport index is `clamp(0.28 + log1p(flow_accumulation)/28 + runoff_mm_y/8000 + (is_river ? 0.12 : 0), 0, 1)` (`:139-157`). All emitted values are `round(..., 6)`. This is a **post-hoc diagnostic trajectory**, not a native state mutation — it does not touch the sediment interface, and the classification is published as such by `geo_evolution_provenance`.

**Sediment transport histories.** One `step_count`-step trajectory per `sedimentary_basins[]` record, keyed to that basin's stratigraphic column (`sediment_dynamics.py:61-168`). Each step emits `sediment_input_m`, `deposited_m`, `exported_m`, `compaction_loss_m`, `accommodation_created_m`, `accommodation_fill_fraction`, `progradation_distance_km`, plus the three carried indices. Note that `compaction_loss_m = min(thickness + deposited, deposited * (0.035 + (1 - preservation)*0.055))` is a *diagnostic* trajectory term inside this enricher only; it does not feed back into the canonical mobile inventory, and `sediment_inventory_model.compaction_resolved` remains `false`.

**Sequence stratigraphy.** Reinterprets each basin's transport steps as systems tracts and surfaces (`sequence_stratigraphy.py:35-81`):

| Rule | Condition | Result |
|---|---|---|
| `_classify_systems_tract` | `ratio >= 1.25 and fill_delta <= 0.08` | `transgressive_systems_tract` |
| | `ratio <= 0.70 and fill_delta < -0.02` | `falling_stage_systems_tract` |
| | `fill >= 0.72 and progradation > 0` | `highstand_systems_tract` |
| | `ratio <= 0.90 and (progradation > 0 or exported > deposited*0.45)` | `lowstand_systems_tract` |
| | otherwise | `aggradational_systems_tract` |
| `_shoreline_trajectory` | `progradation > 0.05 and fill_delta >= -0.02` | `progradational` |
| | `fill_delta < -0.05` | `retrogradational` |
| | otherwise | `aggradational` |
| `_surface_for_step` | `index == 0` | `sequence_boundary` |
| | `index == max_flooding_index` | `maximum_flooding_surface` |
| | tract is transgressive | `transgressive_surface` |
| | progradational and `accommodation_ratio <= 1.05` | `regressive_surface` |
| | otherwise | `none` |

where `ratio = accommodation_created_m / max(0.001, deposited_m)` and `max_flooding_index` is the argmax of that ratio over steps 1..n-1 (step 0 is always the sequence boundary, `sequence_stratigraphy.py:114-120`). The enricher writes back onto each column: `dominant_systems_tract`, `dominant_shoreline_trajectory`, `sequence_boundary_count`, `maximum_flooding_surface_count`, `stratigraphic_sequence_event_count`, `mean_accommodation_to_deposition_ratio` (`:186-191`).

Summary keys added by these three enrichers include `sediment_routing_history_count`, `sediment_routing_step_count`, `sediment_routing_total_{local_supply,deposition,export,sink_loss}_m`, `sediment_routing_{total,mean}_path_length_km`, `sediment_routing_max_{final_load_m,delivery_ratio}`; `sediment_transport_history_count`, `sediment_transport_history_step_count`, `active_sediment_transport_history_count`, `sediment_transport_total_{input,deposition,export,compaction}_m`, `sediment_transport_mean_final_fill_fraction`, `sediment_transport_max_progradation_distance_km`; and `sequence_stratigraphy_{history_count,step_count,event_count}`, `sequence_boundary_count`, `transgressive_surface_count`, `maximum_flooding_surface_count`, `regressive_surface_count`, `mean_sequence_accommodation_to_deposition_ratio`, `mean_sequence_flooding_index`, `systems_tract_counts`, `shoreline_trajectory_counts`.

---

## Quantization and the forward-error tolerance model

The world document is serialized text. The replay must therefore tolerate exactly as much error as decimal quantization of the *serialized operands* can introduce — no more, so a real mutation cannot hide inside the tolerance.

**Two declared precisions.**

| Contract | Value | Applies to |
|---|---|---|
| `canonical_state_serialization_decimal_places` | `10` | `bedrock_surface_elevation_m`, `sediment_thickness_m`, initial-elevation components, sea-level datum shifts, `tectonic_elevation_change_m_by_cell`, routing-input surfaces, `maximum_final_closure_residual_m` |
| `minimum_replay_operand_serialization_decimal_places` | `8` | Stage source/entrainment/bedrock/deposition depth arrays, mobile-snapshot thicknesses, transport-capacity fractions |

These are *floors*, independent of the caller's `output.float_precision` (which is 0–8 with default 4). The serializer implements them as `surface_precision = max(10, precision)` for the canonical fields (`cpp/src/engine/entity_serialization.cpp:180`, `:277-285`) and `max(8, precision)`-class floors on the stage scalars; in practice the stage depth arrays themselves are emitted at full `max_digits10` (`process_serialization.cpp:1297-1311`), which clears the 8-decimal floor by a wide margin, and the whole fluvial history uses that round-trip precision. The Python side hard-caps the callable range: the replay refuses `output_float_precision` outside `[0, 8]` (`src/magic_geo/sediment_interface_validation.py:274-277`) and the tolerance helper refuses a precision outside `[0, 15]` (`:187`).

Two of the interface fields are exempt from fixed formatting entirely: `elevation_m` and `water_depth_m` serialize via `roundtrip_num` (17 significant digits, exact binary64 round-trip) because they jointly determine the discrete ocean mask, and fixed formatting can collapse a one-ULP-below-sea-level cell to signed zero and make the mask unreplayable (`cpp/src/engine/entity_serialization.cpp:182-186`).

**The forward-error model.** `_replay_tolerance` (`src/magic_geo/sediment_interface_validation.py:169-203`) is:

```
decimal_quantum   = 10^(-output_precision)
quantization_bound = 0.51 * decimal_quantum * max(2, operation_count + 2)
floating_bound     = 128 * DBL_EPSILON * max(2, operation_count + 2)
                         * (1 + |actual| + |expected| + operand_sum)
tolerance          = max(5.0e-8, quantization_bound, floating_bound)
```

The `0.51` is a half-ULP-plus-slack per rounded operand; `operation_count` is the accumulated number of serialized operands that have entered the running replay for that cell. The in-source comment is explicit about why this shape was chosen over a scale-relative tolerance: initial elevation, plate displacement, stage source depths and aggregate datum shifts are serialized *independently*, so their worst-case quantization accumulation must be bounded term by term "instead of using a scale-relative tolerance that could hide a large local mutation on an Earth-sized sum".

The replay tracks four independent accumulators per cell: `operand_sums` / `operation_counts` for the bedrock chain and `mobile_operand_sums` / `mobile_operation_counts` for the mobile chain (`:295-301`), each incremented at every applied stage.

The native primitive uses a structurally similar but distinct bound in `long double` (`cpp/src/engine/sediment_partition.cpp:7-20`), and the source-partition validator uses a third variant with an added `64 * math.ulp(scale)` term and a `1.0e-7` km³ floor (`src/magic_geo/sediment_source_partition_validation.py:89-99`).

**Final residuals.** After the full replay, four per-cell residuals are checked and their maxima reported as metrics (`sediment_interface_validation.py:2266-2363`):

| Metric | Compared quantity | Precision used |
|---|---|---|
| `maximum_bedrock_replay_residual_m` | replayed vs. serialized `bedrock_surface_elevation_m` | 8 |
| `maximum_mobile_sediment_replay_residual_m` | replayed vs. serialized `sediment_thickness_m` | 8 |
| `maximum_tectonic_cumulative_residual_m` | replayed vs. `cumulative_tectonic_elevation_change_m` | 10 |
| `maximum_surface_closure_residual_m` | `|elevation - bedrock - thickness|` | 10 |

The last of these is then cross-checked against the native `sediment_interface_model.maximum_final_closure_residual_m` with `operation_count = 4`, on the stated grounds that "a maximum selects one already-quantized cell residual; it does not accumulate one rounding error per cell" (`:2351-2363`).

---

## Per-cell sediment fields

All serialized by `cells_json` (`cpp/src/engine/entity_serialization.cpp:110`). `S` = `surface_precision` = `max(10, float_precision)`; `P` = plain `float_precision`; `RT` = `roundtrip_num`.

| Field | Precision | Meaning | Line |
|---|---|---|---|
| `bedrock_surface_elevation_m` | S | Canonical bedrock surface | `:180` |
| `sediment_thickness_m` | S | Canonical mobile inventory (nonnegative) | `:277` |
| `elevation_m` | RT | **Derived** surface = bedrock + thickness | `:184` |
| `water_depth_m` | RT | `-elevation_m` when wet, else 0 | `:186` |
| `cumulative_tectonic_elevation_change_m` | S | Sum of applied tectonic displacements | `:156` |
| `cumulative_numeric_depression_breach_excavation_m` | S | Breach excavation depth accumulated | `:265` |
| `cumulative_numeric_depression_breach_deposition_m` | S | Breach redeposition depth accumulated | `:269` |
| `numeric_depression_breach_event_count` | int | Excavation + deposition applications | `:272` |
| `erosion_rate` | P | Stream-power **5 Ma reference response**, not the applied depth | `:276` |
| `sediment_deposition_m` | P | Cumulative deposition, all processes | `:279` |
| `sediment_export_m` | P | Cumulative terminal export (leaves the domain) | `:280` |
| `sediment_net_budget_m` | P | `deposition - (alluvium_entrainment + bedrock_erosion)` | `:281` |
| `sediment_alluvium_entrainment_m` | S | Cumulative entrainment from mobile inventory | `:282` |
| `sediment_bedrock_erosion_m` | S | Cumulative bedrock cut | `:284` |
| `hillslope_sediment_production_m` | S | Cumulative hillslope source depth | `:286` |
| `hillslope_sediment_deposition_m` | S | Cumulative hillslope target depth | `:288` |
| `hillslope_sediment_net_m` | S | deposition − production | `:290` |
| `hillslope_sediment_outgoing_edge_count` | int | Directed edges sourced here | `:292` |
| `hillslope_sediment_incoming_edge_count` | int | Directed edges targeting here | `:294` |
| `fluvial_sediment_local_source_m` | S | Cumulative local (stream-power) source | `:296` |
| `fluvial_sediment_routed_incoming_m` | S | Cumulative routed inflow | `:298` |
| `fluvial_sediment_routed_outgoing_m` | S | Cumulative routed outflow | `:300` |
| `fluvial_sediment_local_deposition_m` | S | Capacity + depression + lake trap, minus terminal accommodation | `:302` |
| `fluvial_sediment_terminal_land_deposition_m` | S | Allocation deposits received | `:304` |
| `fluvial_sediment_marine_deposition_m` | S | Marine-terminal deposition | `:307` |
| `fluvial_sediment_depression_fill_m` | S | Depression fill including terminal accommodation (cross-cut) | `:309` |
| `fluvial_sediment_terminal_export_m` | S | Unresolved deep-marine export | `:311` |
| `fluvial_sediment_terminal_capture_volume_km3` | `max(10,P)` | Terminal load captured at this sink | `:314` |
| `fluvial_sediment_routing_event_count` | int | Stages where this cell sourced, received or was allocated | `:317` |
| `glacial_sediment_production_m` | S | Glacial source depth | `:326` |
| `glacial_sediment_deposition_m` | S | Glacial target depth | `:328` |
| `glacial_sediment_net_m` | S | deposition − production | `:330` |
| `glacial_sediment_outgoing_transfer_count` | int | Always 0 or 1 | `:332` |
| `glacial_sediment_incoming_transfer_count` | int | — | `:334` |

Two derived helpers exist in the native core (`cpp/src/engine/types/core.hpp:207-218`) and are the reason two independent closure witnesses can be compared:

```
sediment_gross_mobilization_m(cell)    = sediment_alluvium_entrainment_m + sediment_bedrock_erosion_m   // material side
sediment_process_source_witness_m(cell)= hillslope_sediment_production_m + fluvial_sediment_local_source_m
                                       + glacial_sediment_production_m
                                       + cumulative_numeric_depression_breach_excavation_m              // process side
```

`summary.sediment_source_partition_residual_km3` is `|process_witness_volume - alluvium_volume - bedrock_volume|` (`cpp/src/engine/summary.cpp:1972-1979`) — that is, the *process* side is compared against the *material* side, not against itself.

Selected `summary` keys (`cpp/src/engine/summary.cpp:1915-2000`):

| Summary key | Definition |
|---|---|
| `mean_sediment_thickness_m` | mean of `sediment_thickness_m` |
| `sediment_budget_production_m` / `_deposition_m` / `_export_m` / `_residual_m` | unweighted depth sums and `|prod - dep - exp|` |
| `sediment_budget_closure_model` | `cell_area_weighted_hillslope_glacial_and_routed_deposition_terminal_export_volume_v5` |
| `sediment_budget_production_km3` / `_deposition_km3` / `_export_km3` / `_residual_km3` | area-weighted volumes at `max(10, float_precision)` |
| `sediment_delivery_ratio` | `deposition_km3 / production_km3` (0 when production is 0); CLI gate requires `0 <= x <= 1.25` |
| `sediment_inventory_model` | `finite_alluvium_bedrock_sediment_inventory_v1` |
| `sediment_initial_mobile_inventory_model` | `zero_depth_all_cells_v1` |
| `sediment_source_partition_model` | `available_alluvium_first_then_bedrock_erosion_v1` |
| `sediment_erosion_stage_source_partition_order` | `hillslope_then_fluvial` |
| `sediment_gross_mobilization_volume_km3`, `sediment_alluvium_entrainment_volume_km3`, `sediment_bedrock_erosion_volume_km3`, `sediment_final_inventory_volume_km3` | area-weighted totals |
| `sediment_source_partition_residual_km3` | process-witness vs. material-partition residual |
| `sediment_inventory_mass_balance_residual_km3` | `\|bedrock_volume - final_inventory_volume - export_volume\|` |
| `{hillslope,fluvial,glacial}_sediment_{alluvium_entrainment,bedrock_erosion}_volume_km3` plus `numeric_depression_{alluvium_entrainment,bedrock_erosion}_volume_km3` (no `_sediment_` infix on the breach pair) | per-process splits; the fluvial pair is derived by subtraction and floored at 0 (`summary.cpp:1940-1954`) |

---

## Validators

| Validator | Entry point | Invoked from | What it asserts |
|---|---|---|---|
| Sediment interface replay | `validate_sediment_interfaces(world)` (`src/magic_geo/sediment_interface_validation.py:206`) | `geo_validation_physics.py:2752` as check `sediment.bedrock_mobile_sediment_interface_replay`; also `cli/commands/validate.py:9119` | Model literal set; zero initial inventory; initial-elevation component closure; per-stage bedrock chain (tectonic displacement, hillslope/fluvial/glacial/breach bedrock erosion, sea-level datum shifts); the full fluvial routing replay; mobile snapshots at every stage; final `surface = bedrock + mobile` closure; native `maximum_final_closure_residual_m` |
| Source-partition replay | `validate_sediment_source_partitions(world)` (`src/magic_geo/sediment_source_partition_validation.py:504`) | `geo_validation_physics.py:2730` as check `sediment.sediment_alluvium_bedrock_source_partition_replay` | Model metadata literals for all three mechanisms; per-cell `source == alluvium + bedrock`; per-stage bulk volumes from `area*depth/1000`; hillslope/glacial demand reconstruction from `edges[]`/`transfers[]`; fluvial `cell_steps[]` coverage vs. the 1e-15 threshold; model `total_*` mirrors; the alluvium-first rule per cell per iteration |
| Native in-loop audits | `validate_sediment_source_partition`, `maximum_sediment_interface_closure_residual_m` (`cpp/src/engine/sediment_partition.cpp`) | `erode`, `transport_glacial_sediment`, `stabilize_numeric_depressions`, serialization | Throw during generation, so a world that violates *these specific* checks (surface closure, nonnegative thickness, per-cell source partition, aggregate volume reconstruction) is never serialized. They are not a general validity proof |
| CLI fluvial replay | `_validate_fluvial_sediment_routing` (`src/magic_geo/cli/validators/sediment.py:28`) | `magic-geo validate` (`cli/commands/validate.py:9101`) | 42-key model schema; all 7 routing constants; 23-key stage schema, 30-key step schema, 11-key allocation schema; nominal-time record with role `erosion_interval_bulk_fluvial_routing`; per-cell aggregate mirrors into the cell fields |
| CLI hillslope replay | `_validate_hillslope_sediment_transport` (`src/magic_geo/cli/validators/sediment.py:1059`) | same | 36-key model schema; the 7-entry lithology-resistance map; `reference_timestep_ma == 5.0`; `maturation_timestep_scale == nominal/5.0`; mesh reciprocity and undirected-edge uniqueness; per-edge geometry |
| CLI glacial replay | `_validate_glacial_sediment_transport` (`src/magic_geo/cli/validators/sediment.py:1916`) | same | 30-key model schema; `mobile_sediment_fraction == 0.28`; exactly one stage; input/transfer schemas; `post_transport_elevation_m_by_cell` |
| CLI inventory replay | `_validate_sediment_inventory` (`src/magic_geo/cli/validators/sediment.py:2583`) | same | 31-key `sediment_inventory_model` schema and all seven `*_resolved` flags; stage coverage `hillslope`/`fluvial` on feedback ids `1..iterations` and `glacial` on `iterations+1`; numeric-event id ordering; the running per-cell inventory replayed in native stage order against every stage's `input_cells[]` snapshot |
| Sequence stratigraphy | `_validate_sequence_stratigraphy` (`src/magic_geo/geo_validation_subsystems.py:1649`) | `validate-geo`, domain `sequence_stratigraphy` | Every history links a column and a transport history for the same `basin_id`; step counts match the source; systems tract, surface and trajectory strings are in the closed sets; bounded/nonnegative field ranges; ages non-reversed; per-history and summary categorical aggregates |
| Layer contract | `erosion_sediment`, phase 8 (`src/magic_geo/geo_layer_contracts.py:176-201`) | `validate-geo` layer audit | Requires `hillslope_sediment_transport_model`, `hillslope_sediment_transport_history`, `fluvial_sediment_routing_model`, `fluvial_sediment_routing_history`, `glacial_sediment_transport_model`, `glacial_sediment_transport_history` (nonempty), `sediment_inventory_model`, `sediment_interface_model`, `sediment_transport_histories`, `sequence_stratigraphy_histories`, `river_reorganization_histories`; validator domains `sediment`, `simulation`, `river_evolution_channels`, `sequence_stratigraphy`; dependencies `hydrology` + `plate_tectonics` |

The `erosion_sediment` layer declares `evidence_class = canonical_bedrock_mobile_interface_and_bulk_volume_source_partition_replay_without_dry_rock_mass_or_physical_calibration` and — like every layer — hardcodes `empirical_realism_proven: False`.

The two `validate-geo` sediment checks carry `expected` maps that spell out both sides of the ledger. For the source partition: `source_demand_partitioned_per_cell: True`, `bulk_reference_volume_reconstructed: True`, `alluvium_first_rule_replayed: True`, `dry_rock_mass_claim: False`, `material_provenance_claim: False`. For the interface: `authoritative_interface_geometry: True`, `surface_elevation_derived_from_interfaces: True`, `all_native_sediment_mutation_paths_replayed: True`, `dry_rock_mass_resolved: False`, `porosity_resolved: False`, `grain_provenance_resolved: False`.

---

## Worked commands

Generate a world and run the full consistency gate (which includes every sediment replay above):

```bash
magic-geo generate --config configs/earthlike_seed.yaml --output runs/world.json
magic-geo validate --world runs/world.json
```

Run only the natural-system gate and write the machine-readable report:

```bash
magic-geo validate-geo --world runs/world.json --profile earthlike --output runs/geo_validation.json
```

Call the two sediment replays directly from Python:

```python
import json
from magic_geo.sediment_interface_validation import validate_sediment_interfaces
from magic_geo.sediment_source_partition_validation import validate_sediment_source_partitions

world = json.load(open("runs/world.json"))

interface = validate_sediment_interfaces(world)
print(interface["passed"])
print(interface["metrics"]["maximum_surface_closure_residual_m"])
print(interface["metrics"]["maximum_bedrock_replay_residual_m"])
print(interface["failures"])

partition = validate_sediment_source_partitions(world)
print(partition["passed"], partition["metrics"])
```

Read the declared contract straight out of the document rather than trusting any prose:

```python
import json
world = json.load(open("runs/world.json"))

model = world["sediment_interface_model"]
assert model["canonical_state_fields"] == ["bedrock_surface_elevation_m", "sediment_thickness_m"]
assert model["derived_surface_field"] == "elevation_m"
assert model["canonical_state_serialization_decimal_places"] == 10
assert model["minimum_replay_operand_serialization_decimal_places"] == 8
assert model["dry_rock_mass_resolved"] is False
assert model["porosity_resolved"] is False
assert model["compaction_resolved"] is False

inventory = world["sediment_inventory_model"]
assert inventory["initial_mobile_sediment_inventory"] == "zero_depth_all_cells_v1"
assert inventory["mass_conserving_semantics"] == "bulk_reference_volume_only_not_dry_rock_mass"
print(json.dumps(inventory["process_source_partition"], indent=2))
```

Verify the interface identity yourself over every cell:

```python
import json
world = json.load(open("runs/world.json"))
worst = 0.0
for cell in world["cells"]:
    residual = abs(cell["elevation_m"] - cell["bedrock_surface_elevation_m"] - cell["sediment_thickness_m"])
    worst = max(worst, residual)
    assert cell["sediment_thickness_m"] >= 0.0
print(worst, world["sediment_interface_model"]["maximum_final_closure_residual_m"])
```

Enrich an existing native world with the three diagnostic sediment layers (they are already run by `generate_world` / `generate_geo_world`; this is the direct API):

```python
from magic_geo.sediment_routing import enrich_world_with_sediment_routing_history
from magic_geo.sediment_dynamics import enrich_world_with_sediment_transport_history
from magic_geo.sequence_stratigraphy import enrich_world_with_sequence_stratigraphy

enrich_world_with_sediment_routing_history(world, route_limit=12, max_path_length=72)
enrich_world_with_sediment_transport_history(world, step_count=6)
enrich_world_with_sequence_stratigraphy(world)   # requires the transport histories above
```

Relevant configuration (see the [Configuration Reference](../05-configuration-reference.md) for the full schema; defaults from `src/magic_geo/config.py:371-417`):

```yaml
erosion:
  iterations: 6                  # 0..250; number of coupled maturation transitions
  maturation_timestep_ma: 5.0    # > 0 and <= 5.0; nominal Ma per transition
  stream_power_coefficient: 7.5  # 0..1000; reference-step incision coefficient
  drainage_exponent: 0.5         # 0..2
  slope_exponent: 1.0            # 0..3
  hillslope_diffusion: 0.055     # 0..1; reference diffusivity
  tectonic_uplift_scale: 0.85    # 0..10
```

---

## Limitations and unresolved claims

Every item below is a flag or string the engine itself emits; none of it is editorial hedging added here.

| Claim | Status | Where declared |
|---|---|---|
| Dry-rock mass | **`dry_rock_mass_resolved: false`** | `sediment_interface_model`, `sediment_inventory_model` |
| Sediment density | **`sediment_density_resolved: false`** | both models |
| Porosity | **`porosity_resolved: false`** | both models |
| Compaction | **`compaction_resolved: false`** | both models |
| Grain provenance | **`grain_provenance_resolved: false`** | both models |
| Chemical weathering | **`chemical_weathering_resolved: false`** | both models |
| Grain size | **`grain_size_resolved: false`** | `fluvial_sediment_routing_model` |
| Physical time | **`physical_time_resolved: false`** | fluvial, hillslope, glacial, inventory models |
| Timestep convergence | **`time_step_convergence_demonstrated: false`** | fluvial, hillslope, inventory models |
| Sub-cell channel geometry | **`subcell_channel_geometry_resolved: false`** | `fluvial_sediment_routing_model` |
| Shared-boundary flux geometry | **`shared_boundary_geometry_resolved: false`** | `hillslope_sediment_transport_model` |
| Multi-step ice dynamics | **`multi_step_ice_dynamics_resolved: false`** | `glacial_sediment_transport_model` |
| Source-partition arrays as mass | **`source_partition_audit_is_mass_claim: false`** | all three transport models |
| Source-partition arrays as provenance | **`source_partition_audit_is_provenance_claim: false`** | all three transport models |

Further, explicitly:

- **"Mass conserving" means bulk reference volume only.** Every `mass_conserving: true` in this subsystem is qualified by `mass_conserving_semantics = "bulk_reference_volume_only_not_dry_rock_mass"`. The system conserves `depth × area` bookkeeping, not matter.
- **The alluvium/bedrock arrays are a reservoir-of-origin ledger, not a provenance model.** They record which of two abstract reservoirs a metre of column was drawn from in a given stage. They do not track any material through space, do not identify grains, and do not survive as an attribute of the deposited column.
- **Terminal export leaves the accounted domain.** `marine_terminal_model` is `water_body_class_deposition_then_unresolved_deep_marine_export_v1`. The exported fraction has no sink in the model; the summary reports it as `sediment_budget_export_km3` and the closure is written to include it, but nothing downstream stores it.
- **`erosion_rate` is a reference-step response, not an applied depth.** It is `stream` before multiplication by `maturation_timestep_scale`; only the applied source depth is scaled (`cpp/src/engine/earth_system.cpp:986-995`). Consumers that treat `erosion_rate` as the material actually removed will be wrong by the timestep scale.
- **Timestep refinement is not demonstrated to converge.** `time_step_convergence_demonstrated: false` is set on the fluvial, hillslope and inventory models. The geo validation suite does exercise timestep-refinement scenarios (`maturation_timestep_coarse` / `_refined`) with two `eq` invariance relations, but a passing suite is not a convergence proof and the flag stays false.
- **`compaction_loss_m` in `sediment_transport_histories` is a diagnostic trajectory term.** It is produced by the Python enricher `src/magic_geo/sediment_dynamics.py:97` and never feeds back into `sediment_thickness_m`. `compaction_resolved` remains false in the native model.
- **`sediment_routing_histories` and `sediment_transport_histories` are post-hoc reconstructions.** They do not mutate native state; `geo_evolution_provenance` classifies history families as `native_state_mutation_ledger` vs. `posthoc_diagnostic_trajectory` precisely so consumers can tell them apart, and records `physical_time_resolved: False` / `nominal_time_calibrated: False` throughout.
- **Sequence stratigraphy is an interpretation of a diagnostic trajectory.** Systems tracts and surfaces are derived from the enricher's accommodation/deposition ratios, not from a eustatic curve, a subsidence solver, or any native state. There is no independent sea-level history behind `relative_sea_level_index`; it is `clamp(accommodation_fill_fraction / 2.5)`.
- **Basins and columns are classifications of the final state.** `generate_sedimentary_basins` and `generate_stratigraphic_columns` read the terminal cell array once. Layer ages are a linear subdivision of `depositional_span_ma`; they are not a deposition chronology and do not correspond to the maturation stages.
- **Nominal time is not physical time.** The nominal-time block on every sediment ledger carries `nominal_time_calibrated: false` and `physical_time_resolved: false`. `maturation_timestep_ma` names a nominal interval, not a calibrated one.
- **The depression-fill bucket is deliberately cross-cut.** `depression_fill_deposition_volume_km3` includes terminal accommodation, so it double-counts against the physical total; `depression_fill_deposition_is_cross_cut: true` is the declaration and the replay compensates by subtracting `terminal_accommodation_volume` (`src/magic_geo/sediment_interface_validation.py:1541-1548`). Naively summing the stage buckets will overcount.
- **The transport-capacity fraction is dimensionless.** `model_limitation` states it: `dimensionless_capacity_proxy_without_grain_size_calibrated_time_or_subcell_channels`. It is not a Bagnold, Engelund–Hansen, or any other calibrated transport relation.
- **`is_active` on basins and columns is a heuristic.** It is true when any member cell is a river, a lake, has an ocean neighbour, or exceeds 0.9 m of sediment (`cpp/src/engine/environment.cpp:709-711`) — not a subsidence or accommodation test.
- **The layer contract proves structure, not realism.** `erosion_sediment` sets `empirical_realism_proven: False`, like every layer in `geo_layer_contracts.py`. A passing contract means the outputs exist, the validator domains reported, dependencies passed, and nothing failed at error severity.

---

## See also

- [Erosion, Maturation and Landscape Evolution](erosion-and-maturation.md) — the maturation loop, stream-power incision, and the coupling order that produces the fluvial source depths
- [Hydrology, Rivers and Lakes](hydrology-and-rivers.md) — flow routing, depression components, spill elevations, and the numeric-depression corrector that owns the breach path
- [Topography, Isostasy and Thermal Subsidence](topography-and-isostasy.md) — the tectonic displacement operand consumed by the interface
- [Cryosphere: Ice Sheets, Glaciers and Permafrost](cryosphere.md) — `glacial_erosion_m` and the ice state that drives glacial transport
- [Oceans, Currents and Coasts](oceans-and-coasts.md) — the sea-level datum solve and the coastal features consumed by the transport-history enricher
- [Resources and Economic Geology](resources-and-economic-geology.md) — the sedimentary resource, petroleum-migration and commodity layers built on basins and columns
- [Crust Material Shadow and Dry-Rock Reservoirs](crust-material-and-reservoirs.md) — where dry-rock mass *is* modelled, non-authoritatively, and why it is separate from this subsystem
- [World Document Schema](../10-world-schema.md) — the full key inventory for the models, histories and cell fields referenced here
- [Serialization and World Formats](../11-serialization.md) — `roundtrip_num`, fixed-precision floors, and the MessagePack transcoding that preserves them
- [Validation](../12-validation.md) — how the sediment checks compose into `validate` and `validate-geo`
- [Geo Validation Suite](../13-geo-validation-suite.md) — the scenario matrix, including the maturation-timestep refinement relations
- [Native Engine (C++ Core)](../08-native-engine.md) — pipeline stage ordering and the engine invariants quoted above
- [Configuration Reference](../05-configuration-reference.md) — the `erosion` block
- [CLI Reference](../06-cli-reference.md) — `generate`, `validate`, `validate-geo`, `validate-geo-suite`
- [Glossary](../21-glossary.md)
