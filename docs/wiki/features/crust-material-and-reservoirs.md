# Crust Material Shadow and Dry-Rock Reservoirs

[Wiki home](../README.md) > Features

magic-geo carries two mass-like bookkeeping structures alongside the authoritative scalar crust state: a **persistent sparse dry-rock mass shadow** (`cpp/src/engine/crust_material.cpp`) and a **finite three-reservoir dry-rock accounting counter-model** (`cpp/src/engine/crust_reservoir.cpp`). Both are explicitly, mechanically non-authoritative: their own serialized model metadata sets `authoritative_for_cell_state` to `false`, and every physical claim a reader might infer from them — physical source/sink, material provenance, solid volume, phase, mass-weighted age, a real upper mantle, a real subducted slab, global crust-cycle conservation — is emitted as an explicit `false` flag. They exist so that the ordered crust-rule chain's implied mass changes are *counted and made auditable*, not so that the engine can claim to conserve rock. This page documents both models exhaustively: packet layout, canonical keys, allocation arithmetic, forward-error bounds, transaction ordering, tie-breaks, operational caps, the serialized schema, and the independent Python replay validators.

## On this page

- [Non-authoritative by construction](#non-authoritative-by-construction)
- [Where the two models sit in the pipeline](#where-the-two-models-sit-in-the-pipeline)
- [The dry-rock mass definition and its unit factor](#the-dry-rock-mass-definition-and-its-unit-factor)
- [Shadow packet structure and canonical origin keys](#shadow-packet-structure-and-canonical-origin-keys)
- [Shadow step lifecycle: the four entry points](#shadow-step-lifecycle-the-four-entry-points)
- [Source-normalized allocation and the final-edge remainder](#source-normalized-allocation-and-the-final-edge-remainder)
- [Opening/closing linkage and the native forward-error bound](#openingclosing-linkage-and-the-native-forward-error-bound)
- [The serialized residual against raw density-weighted transport](#the-serialized-residual-against-raw-density-weighted-transport)
- [Rule execution order and the ordered adjustment rules](#rule-execution-order-and-the-ordered-adjustment-rules)
- [Valid intermediate empty and exhausted states](#valid-intermediate-empty-and-exhausted-states)
- [Serialized shadow schema](#serialized-shadow-schema)
- [The finite three-reservoir accounting model](#the-finite-three-reservoir-accounting-model)
- [The initial upper-mantle exchange counter-reserve](#the-initial-upper-mantle-exchange-counter-reserve)
- [Reason-major transactions, sink-before-source, and withdrawal order](#reason-major-transactions-sink-before-source-and-withdrawal-order)
- [Empty slab tables and physical_basis_resolved](#empty-slab-tables-and-physical_basis_resolved)
- [Operational caps as memory-safety limits](#operational-caps-as-memory-safety-limits)
- [Accounting closure invariants and fail-closed guards](#accounting-closure-invariants-and-fail-closed-guards)
- [Serialized accounting schema](#serialized-accounting-schema)
- [Independent replay validation](#independent-replay-validation)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

## Non-authoritative by construction

Neither model may be read as physics. The authority boundary is not a documentation convention — it is emitted into every world document as machine-checkable boolean flags, and the Python validators fail the world if any of them is flipped.

Shadow model flags (`cpp/src/engine/process_serialization.cpp:206-217`, mirrored literally in `src/magic_geo/crust_material_shadow_validation.py:138-148`):

| Serialized flag | Value | Meaning |
|---|---|---|
| `authoritative_for_cell_state` | `false` | The scalar `crust_thickness_km` / `crust_density` on the cell remain authoritative; the packet table only mirrors them |
| `physical_source_sink_resolved` | `false` | Positive and negative rule deltas are not physical creation or destruction of rock |
| `material_provenance_resolved` | `false` | Origin keys are bookkeeping labels, not a claim about where material came from |
| `solid_volume_resolved` | `false` | No solid-volume model exists |
| `phase_resolved` | `false` | No melt/solid/phase state is tracked |
| `mass_weighted_age_resolved` | `false` | Packet masses carry no age moment |
| `upper_mantle_exchange_reservoir_resolved` | `false` | The shadow does not model a mantle at all |
| `subducted_slab_reservoir_resolved` | `false` | The shadow does not model slabs |
| `global_crust_cycle_mass_conservation_resolved` | `false` | Global closure of the shadow is arithmetic, not geophysical |
| `transport_provenance_shadow_resolved` | `true` | The one positive claim: transport provenance *as a shadow* is resolved |
| `ordered_rule_mass_adjustments_exposed` | `true` | The second positive claim: every ordered rule adjustment is exposed |

Accounting model flags (`cpp/src/engine/crust_reservoir_serialization.cpp:175-192`, mirrored in `src/magic_geo/crust_dry_rock_accounting_validation.py:107-124`):

| Serialized flag | Value |
|---|---|
| `finite_three_reservoir_accounting_present` | `true` |
| `closed_three_reservoir_dry_rock_accounting` | `true` |
| `per_origin_accounting_closed` | `true` |
| `finite_exchange_inventory_enforced` | `true` |
| `proxy_compensations_exposed` | `true` |
| `plate_resolved_slab_accounting_state_present` | `true` |
| `authoritative_for_cell_state` | `false` |
| `physical_source_sink_resolved` | `false` |
| `material_provenance_resolved` | `false` |
| `upper_mantle_exchange_reservoir_resolved` | `false` |
| `subducted_slab_reservoir_resolved` | `false` |
| `global_crust_cycle_mass_conservation_resolved` | `false` |
| `solid_volume_resolved` | `false` |
| `phase_resolved` | `false` |
| `mass_weighted_age_resolved` | `false` |
| `sediment_coupled` | `false` |
| `coverage_membership_fate_resolved` | `false` |
| `subduction_polarity_resolved` | `false` |

Additional accounting semantics strings that carry the same warning in prose form:

| Key | Value |
|---|---|
| `mode` | `finite_accounting_shadow` |
| `capacity_geophysically_calibrated` | `false` |
| `capacity_semantics` | `finite_numerical_surface_state_envelope_not_an_estimate_of_upper_mantle_mass` |
| `operational_safety_limits_are_physical_flux_limits` | `false` |
| `operational_safety_limit_semantics` | `numerical_memory_safety_limits_not_physical_flux_or_reservoir_capacity_limits` |
| `subducted_slab_phase_2_state` | `plate_resolved_empty_reservoir_no_transfer_mechanism_enabled` |
| `instantaneous_global_mantle_mixing_assumed` | `true` |
| `mantle_origin_packets_homogenized` | `false` |
| `mantle_spatial_transport_resolved` | `false` |

The engine invariant list states this directly (`cpp/src/engine/README.md:318-320`): "Arithmetic closure across the three tables must never be described as physical provenance, solid-volume or phase closure, sediment/subduction coupling, or a resolved mantle/slab crust cycle."

## Where the two models sit in the pipeline

Both are driven from tectonics, one step per plate-motion step, and are always exactly as long as `plate_motion_history`.

| Order | Call | Source | When |
|---|---|---|---|
| 1 | `initialize_crust_material_shadow(cells, motion_id, erosion_iteration, stage, state)` | `cpp/src/engine/pipeline.cpp:90-96` | Once, after the identity-overlap step-0 checkpoint |
| 2 | `initialize_crust_dry_rock_accounting(cells, plate_count, motion_id, shadow_id, erosion_iteration, stage, state)` | `cpp/src/engine/pipeline.cpp:97-105` | Once, immediately after the shadow is initialized |
| 3 | `begin_crust_material_shadow_step(cells, transport_plan, motion_id, erosion_iteration, "plate_motion_iteration", state)` | `cpp/src/engine/tectonics.cpp:1158-1165` | Per maturation iteration, right after the forward-overlap transport plan is built |
| 4 | `apply_crust_material_shadow_transition(state, cell_id, current_plate_id, reason, area, before_thickness, before_density, after_thickness, after_density)` | `cpp/src/engine/tectonics.cpp:1306-1316` | Once per (cell, ordered rule) inside the per-cell rule chain |
| 5 | `finalize_crust_material_shadow_step(cells, transport_plan, state)` | `cpp/src/engine/tectonics.cpp:1772-1776` | After the rule chain and the canonical serial reduction |
| 6 | `advance_crust_dry_rock_accounting_step(cells, plates.size(), transport_plan, shadow.history.back(), state)` | `cpp/src/engine/tectonics.cpp:1777-1783` | Immediately after the shadow step closes; consumes the just-finalized shadow record |

Step 4 runs inside `#pragma omp parallel for schedule(static)` (`cpp/src/engine/tectonics.cpp:1247`). Each worker touches only its own cell's rows (`surface_packets_by_cell[cell_id]`, `unresolved_source_adjustments_by_cell[cell_id]`, `unresolved_sink_adjustments_by_cell[cell_id]`), so the mutation is row-local. Because OpenMP cannot propagate exceptions out of a parallel region, each worker records its own fail-closed error string into `crust_material_errors[index]`, and the serial pass at `cpp/src/engine/tectonics.cpp:1650-1660` rethrows the first non-empty one after all workers join.

The two translation units are compiled into `magic_geo_native` and serialized read-only by `cpp/src/engine/process_serialization.cpp` (shadow) and `cpp/src/engine/crust_reservoir_serialization.cpp` (accounting); the top-level key placement is in `cpp/src/engine/world_serialization.cpp:183-202`.

## The dry-rock mass definition and its unit factor

Both models use one definition, declared in the shadow model as `dry_rock_mass_definition = "cell_area_km2_times_crust_thickness_km_times_crust_density_g_cm3_times_1e12"` (`cpp/src/engine/process_serialization.cpp:171-172`):

```
dry_rock_mass_kg = area_km2 * crust_thickness_km * crust_density_g_cm3 * 1.0e12
```

`DRY_ROCK_MASS_KG_PER_DENSITY_WEIGHTED_KM3 = 1.0e12` is declared identically in both files (`cpp/src/engine/crust_material.cpp:11`, `cpp/src/engine/crust_reservoir.cpp:19`) and as `DENSITY_VOLUME_TO_MASS_KG` / `MASS_FACTOR_KG` in the two validators (`src/magic_geo/crust_material_shadow_validation.py:14`, `src/magic_geo/crust_dry_rock_accounting_validation.py:11`).

The conversion factor itself is a plain unit conversion (1 km³ · 1 g/cm³ = 10¹² kg). It is *not* a porosity, compaction, or grain-density model — `solid_volume_resolved` and `phase_resolved` are both `false`. The helper `checked_mass` fails closed on non-finite or negative operands and on a non-finite or negative product (`cpp/src/engine/crust_material.cpp:113-134`, `cpp/src/engine/crust_reservoir.cpp:111-129`); `area_km2` must be strictly positive, while thickness and density may be zero.

## Shadow packet structure and canonical origin keys

The shadow holds one sparse row per cell. Records are declared in `cpp/src/engine/types/earth_system.hpp:670-746`.

| Struct | Field | Type | Notes |
|---|---|---|---|
| `CrustMaterialShadowPacket` | `origin_kind_id` | `int` | `0..8` = crust type at origin, `9` = `unresolved_rule_source` |
| | `origin_plate_id` | `int` | `>= 0` natively; the validator additionally requires `< plate_count` |
| | `origin_reason_id` | `int` | `-1` for kinds `0..8`; `0..9` (a `CrustProcessReason`) for kind `9` |
| | `dry_rock_mass_kg` | `double` | Strictly positive in any canonical table |
| `CrustMaterialShadowAdjustment` | `process_reason_id` | `int` | The ordered rule that produced this adjustment |
| | `origin_kind_id`, `origin_plate_id`, `origin_reason_id` | `int` | The packet key affected |
| | `dry_rock_mass_kg` | `double` | Strictly positive magnitude (sign is carried by which table it lands in) |

Flattened CSR tables:

| Table type | Arrays | Indexed by |
|---|---|---|
| `CrustMaterialShadowPacketTable` | `cell_offsets` (length `cell_count + 1`), `origin_kind_ids`, `origin_plate_ids`, `origin_reason_ids`, `dry_rock_mass_kg` | cell id |
| `CrustMaterialShadowAdjustmentTable` | `cell_offsets`, `process_reason_ids`, `origin_kind_ids`, `origin_plate_ids`, `origin_reason_ids`, `dry_rock_mass_kg` | cell id |

Origin kind identifiers, in the exact order emitted as `origin_kind_order` (`cpp/src/engine/process_serialization.cpp:173-183`, from `CRUST_NAMES` in `cpp/src/engine/schema_names.hpp:7-10` plus one appended synthetic kind):

| `origin_kind_id` | Name | Source |
|---|---|---|
| 0 | `oceanic` | `CRUST_NAMES[0]` |
| 1 | `continental` | `CRUST_NAMES[1]` |
| 2 | `transitional` | `CRUST_NAMES[2]` |
| 3 | `volcanic_arc` | `CRUST_NAMES[3]` |
| 4 | `craton` | `CRUST_NAMES[4]` |
| 5 | `orogen` | `CRUST_NAMES[5]` |
| 6 | `rift_basin` | `CRUST_NAMES[6]` |
| 7 | `sedimentary_basin` | `CRUST_NAMES[7]` |
| 8 | `accreted_terrane` | `CRUST_NAMES[8]` |
| 9 | `unresolved_rule_source` | Appended literal; `UNRESOLVED_RULE_SOURCE_KIND_ID = 9` (`cpp/src/engine/crust_material.cpp:10`) |

Key validity rules, enforced by `validate_packet_key` (`cpp/src/engine/crust_material.cpp:49-74`) and by `_valid_packet_key` in the validator (`src/magic_geo/crust_material_shadow_validation.py:262-269`):

| Condition | Native error message |
|---|---|
| `origin_kind_id < 0` or `> 9` | `crust material shadow packet has an invalid origin kind` |
| `origin_plate_id < 0` | `crust material shadow packet has an invalid origin plate` |
| kind `== 9` and `origin_reason_id` outside `[0, CRUST_PROCESS_REASON_COUNT)` | `unresolved crust material packet has an invalid origin reason` |
| kind `!= 9` and `origin_reason_id != -1` | `initial crust material packet has a non-initial origin reason` |
| non-finite or `<= 0` mass | `crust material shadow packet mass is nonfinite or nonpositive` |

Canonicalization (`packet_sort_order = "origin_kind_id_then_origin_plate_id_then_origin_reason_id"`, `packet_coalescing_model = "sorted_equal_key_sum_v1"`):

- `normalize_packets` (`cpp/src/engine/crust_material.cpp:163-199`) drops exactly-zero masses, throws on negative or non-finite masses, sorts by the 3-tuple key, then sums adjacent equal keys, throwing `crust material shadow packet coalescing overflowed` on a non-finite sum.
- `normalize_adjustments` (`:201-240`) does the same over the 4-tuple `(process_reason_id, origin_kind_id, origin_plate_id, origin_reason_id)`.
- `validate_canonical_packets` (`:242-254`) re-asserts strict ascending uniqueness on every read, throwing `crust material shadow packets are not sorted and unique`.
- `flatten_packets` / `flatten_adjustments` throw if the flattened table would exceed `INT_MAX` offsets.

At initialization every cell gets exactly one packet keyed `(cell.crust_type, cell.plate_id, -1)` with mass `checked_mass(area_km2, crust_thickness_km, crust_density)` (`cpp/src/engine/crust_material.cpp:493-503`). Initialization fails closed if `crust_type` is outside `[0, 8]` or `plate_id < 0`.

## Shadow step lifecycle: the four entry points

| Function | Preconditions (all failures throw and mutate nothing observable) | Effect |
|---|---|---|
| `initialize_crust_material_shadow` (`cpp/src/engine/crust_material.cpp:461-534`) | `cells` non-empty; `!state.step_open`; `state.history` empty; `state.surface_packets_by_cell` empty; `plate_motion_history_id >= 0`; `stage` non-empty | Seeds one packet per cell, writes history record `id = 0` whose `opening_packets == transported_packets == closing_packets` and whose adjustment tables are empty (`cell_offsets` = `cell_count + 1` zeros) |
| `begin_crust_material_shadow_step` (`:536-805`) | non-empty cells; `!state.step_open`; history non-empty; row count matches cell count; `plate_motion_history_id == state.history.size()`; `stage` non-empty; the transport plan CSR is well formed | Verifies opening == prior closing bit-exactly, advects every packet, installs the transported rows as the new live state, clears both adjustment buffers, stores the pending step, sets `step_open = true` |
| `apply_crust_material_shadow_transition` (`:807-989`) | `state.step_open`; `0 <= cell_id < row count`; `current_plate_id >= 0`; `0 <= process_reason < CRUST_PROCESS_REASON_COUNT` | Computes `after_mass - before_mass`; returns immediately if the delta is exactly `0.0`; otherwise applies the positive or negative rule below |
| `finalize_crust_material_shadow_step` (`:991-1306`) | `state.step_open`; row and adjustment vector sizes all equal `cells.size()`; `pending_step.cell_count == cells.size()`; `pending_step.id == history.size()`; `pending_step.plate_motion_history_id == history.size()` | Flattens closing packets and both adjustment tables, runs every closure check, pushes the step, resets `pending_step`, clears `step_open` and both adjustment buffers |

## Source-normalized allocation and the final-edge remainder

Advection is declared as `transport_advection_model = "source_normalized_overlap_with_final_edge_remainder_v1"` with `transport_normalization_scope = "per_source_sum_of_raw_overlap_areas"` and `transport_remainder_rule = "final_destination_edge_receives_source_mass_roundoff_remainder"` (`cpp/src/engine/process_serialization.cpp:186-191`).

The algorithm (`cpp/src/engine/crust_material.cpp:584-716`):

1. Walk the destination-major CSR of the forward-overlap `CrustTransportPlan` and materialize one `TransportEdge{source_cell_id, destination_cell_id, original_edge_index, overlap_area_km2}` per row entry. Each edge is rejected unless `0 <= source_id < cell_count` and `overlap_area_km2` is finite and strictly positive.
2. Sort all edges by the tuple `(source_cell_id, destination_cell_id, original_edge_index)` — this converts a destination-major CSR into a deterministic source-major traversal.
3. For each source cell, sum the **raw** overlap areas of its outgoing edges into `source_overlap_sum` (plain left-to-right `double` accumulation). A source with no outgoing edge, or a non-finite/non-positive sum, throws `crust material shadow source has no valid outgoing overlap`.
4. For every packet on that source, allocate over the edges in sorted order:
   - non-final edge: `edge_mass = packet.mass * (edge.area / source_overlap_sum)`
   - **final** edge: `edge_mass = packet.mass - allocated_mass` (a subtraction, not a ratio)
5. Only strictly positive `edge_mass` values are pushed to the destination; each keeps the source packet's key unchanged.
6. After the packet is exhausted, assert `|allocated_mass - packet.mass| <= forward_error_bound(allocated_mass + packet.mass, edge_count + 1)`, else throw `crust material shadow source packet allocation exceeded its forward-error bound`.
7. After the traversal, `edge_cursor` must equal `edges.size()`, else `crust material shadow transport edge traversal did not close`.
8. Every destination row is then `normalize_packets`'d (drop zeros, sort, coalesce equal keys).

The final-edge rule is what makes the model *packet-exact*: each source packet is transported exactly once in floating point, so no source can silently gain or lose mass to normalization rounding. The docstring of the Python replay states the same contract (`src/magic_geo/crust_material_shadow_validation.py:517-525`).

### Worked example: one packet, three destinations

Source cell 7 holds one packet keyed `(1, 3, -1)` (continental, plate 3, initial) with mass `M = 6.0e18 kg`. Its outgoing overlap row is:

| Destination | `original_edge_index` | `overlap_area_km2` |
|---|---|---|
| 4 | 118 | 100.0 |
| 9 | 250 | 250.0 |
| 12 | 401 | 150.0 |

`source_overlap_sum = 500.0`. Sorted by `(source, destination, edge_index)` the order is 4, 9, 12, so cell 12 is the final edge:

| Destination | Formula | Allocated mass |
|---|---|---|
| 4 | `6.0e18 * (100.0 / 500.0)` | `1.2e18` |
| 9 | `6.0e18 * (250.0 / 500.0)` | `3.0e18` |
| 12 | `6.0e18 - (1.2e18 + 3.0e18)` | `1.8e18` (by subtraction) |

Had the final destination also used the ratio form, the three products would only sum to `M` up to rounding; the subtraction makes the source row close by construction, and the per-packet bound at step 6 is then a check on the accumulation, not on the partition.

Note that the overlap areas here are the **raw** per-edge areas from the transport plan, not areas renormalized to the source control-volume area. The shadow deliberately consumes the raw rows and exposes the resulting geometry mismatch as a separate diagnostic (see below). The Python replay independently reconstructs each source's row area from the same CSR and fails the world if `|reconstructed_source_area - cell.area_km2| > max(1.0e-6, source_area * 2.0e-10)` (`src/magic_geo/crust_material_shadow_validation.py:1000-1022`).

## Opening/closing linkage and the native forward-error bound

Every step's opening packet table must equal the previous step's closing packet table **bit-exactly** — `packet_tables_equal` compares `cell_offsets`, all three integer key columns, and the `dry_rock_mass_kg` doubles with `operator==` (`cpp/src/engine/crust_material.cpp:333-343`, checked at `:575-582`). Failure throws `crust material shadow opening packets do not equal prior closing packets`. Combined with `plate_motion_history_id == state.history.size()`, this makes the history a strict chain: record `i` is the transition from state after record `i-1` to state after record `i`, and record `0` is the identity checkpoint.

All conservation checks are expressed against one shared bound (`cpp/src/engine/crust_material.cpp:148-161`; the identical function exists at `cpp/src/engine/crust_reservoir.cpp:84-97`):

```
forward_error_bound(absolute_term_sum, arithmetic_term_count) =
    max( 1.0e-3L,
         128.0L * DBL_EPSILON * max(1, arithmetic_term_count)
                * (1.0L + |absolute_term_sum|) )
```

Everything is accumulated in `long double`; `checked_double` converts back and throws if the value is non-finite or exceeds `DBL_MAX` (`:136-146`).

Checks performed, with their operands:

| Check | Where | Residual | Bound |
|---|---|---|---|
| Per-source packet allocation | `:693-706` | `allocated - packet.mass` | `forward_error_bound(allocated + packet.mass, edges_for_source + 1)` |
| Global transport conservation (open) | `:719-734` | `transported_mass - opening_mass` | `forward_error_bound(opening + transported, opening_packets + transported_packets + edges)` |
| Shadow-vs-raw geometry closure | `:772-801` | `shadow_minus_raw_transport_mass_kg` | `prior_scalar_residual + 4 * max(0, plan.maximum_source_area_relative_closure_error) * (1 + max(|opening|, |raw|)) + forward_error_bound(|opening| + |raw|, edges + opening_packets)` |
| Per-cell scalar mirror | `:1101-1119` | `closing_cell_mass - area*thickness*density*1e12` | `prior_max_cell_residual * max(1, plan.contributor_count_by_cell[cell]) + 4 * geometry_relative_error * (1 + local_absolute_terms) + forward_error_bound(local_absolute_terms, local_packet_terms + 6)` |
| Per-cell adjustment reconciliation | `:1120-1147` | `closing_cell - transported_cell - source_cell + sink_cell` | `forward_error_bound(sum of the four absolute terms, per-cell packet/adjustment counts + 4)` |
| Global transport conservation (finalize) | `:1243-1253` | `transported_mass - opening_mass` | `forward_error_bound(|opening| + |transported|, arithmetic_terms)` |
| Global adjustment reconciliation | `:1254-1266` | `closing - transported - source + sink`, and the per-cell maximum | `forward_error_bound(|closing| + |transported| + |source| + |sink|, arithmetic_terms)` |
| Per-reason adjustment reconciliation | `:1268-1285` | `sum(per-reason source) - global source`, likewise for sinks | same `adjustment_bound` |
| Global scalar mirror | `:1287-1299` | `closing_mass - scalar_closing_mass`, and the per-cell maximum | `prior_max_cell_residual * cell_count + 4 * geometry_relative_error * (1 + scalar_absolute_terms) + forward_error_bound(scalar_absolute_terms, arithmetic_terms)` |

`arithmetic_terms` at finalization is `opening + transported + closing + source_adjustments + sink_adjustments + overlap_edges + cell_count` (`:1236-1242`). `geometry_relative_error` is `max(0, plan.maximum_source_area_relative_closure_error)`.

The two bound terms that are *not* pure rounding deserve attention: `prior_max_cell_residual * ...` lets the previous step's per-cell mirror error propagate (the shadow is persistent, so a residual carried into a step is not the step's fault), and `4 * geometry_relative_error * (1 + terms)` admits the exact-geometry closure error of the overlap arrangement itself. Both are *numerical* allowances, not physical flux terms.

## The serialized residual against raw density-weighted transport

The transport plan independently reports `transported_density_weighted_crust_volume` — the raw density-weighted crust volume moved by the overlap arrangement without any per-source normalization. The shadow converts it with the same `1e12` factor and stores both the scalar and the difference (`cpp/src/engine/crust_material.cpp:751-764`):

```
raw_transported_scalar_mass_kg        = plan.transported_density_weighted_crust_volume * 1.0e12
shadow_minus_raw_transport_residual_kg = transported_shadow_mass - raw_transported_scalar_mass_kg
```

Its declared meaning (`raw_transport_scalar_reference` and `shadow_minus_raw_transport_residual_semantics`, `cpp/src/engine/process_serialization.cpp:202-205`) is verbatim:

> `source_normalized_shadow_mass_minus_raw_overlap_scalar_mass_is_a_numerical_geometry_closure_diagnostic_not_a_physical_source_or_sink`

That is, the residual is non-zero precisely because source-normalized packet advection and raw-area moment transport are two different arithmetic paths over the same arrangement. It measures how far the exact spherical overlap partition is from perfectly tiling each source control volume. It is **not** a mass gain or loss, and it must never be reported as one. The world summary carries the running maximum as `maximum_absolute_crust_material_shadow_transport_raw_residual_kg` (`cpp/src/engine/summary.cpp:163-165`).

## Rule execution order and the ordered adjustment rules

The ordered crust rules live in the per-cell chain in `advance_plate_motion_and_crust` (`cpp/src/engine/tectonics.cpp:1326-1538`). Each is bracketed by a `CrustRuleState` snapshot and a `record_reason(...)` call, and `record_reason` always calls `apply_crust_material_shadow_transition` with the *before* and *after* thickness and density — including when the rule's `triggered` flag is false, in which case the mass delta is exactly zero and the transition returns immediately.

| id | `CRUST_PROCESS_REASON_NAMES` | Rule site | Changes thickness/density? |
|---|---|---|---|
| 0 | `quiet_oceanic_aging` | `tectonics.cpp:1326-1336` | No — age only |
| 1 | `oceanic_ridge_rejuvenation` | `:1344-1375` | No — age only |
| 2 | `oceanic_ridge_creation_relaxation` | `:1376-1391` | Yes — relaxes thickness toward 7 km and density toward 3.0 |
| 3 | `divergent_continental_rifting` | `:1396-1419` | Yes — thins (floored at 0), raises density |
| 4 | `oceanic_convergence_subduction_proxy` | `:1427-1440` | Yes — thickens; also rejuvenates age |
| 5 | `continental_collision_orogeny` | `:1446-1473` | Yes — thickens, lowers density |
| 6 | `plate_crossing_accretion_proxy` | `:1458-1482` | Yes — additional plate-crossing thickening |
| 7 | `age_bound_enforcement` | `:1501-1516` | No — age clamp only |
| 8 | `thickness_bound_enforcement` | `:1517-1530` | Yes — clamps to `[4.5, 18.0]` km oceanic / `[16.0, 76.0]` km continental |
| 9 | `density_bound_enforcement` | `:1531-1538` | Yes — clamps to `[2.58, 3.08]` |

The enum and name table are in `cpp/src/engine/constants.hpp:73-97`; the identical ordering is mirrored as `CRUST_PROCESS_REASON_ORDER` in `src/magic_geo/crust_process_validation.py:8-19`.

Reasons 0, 1, and 7 change only crust age, so their implied mass delta is structurally zero. The accounting model asserts this explicitly and throws `finite dry-rock accounting age-only reason changed mass` if any request appears under them (`cpp/src/engine/crust_reservoir.cpp:1307-1316`); the validator repeats the assertion for reasons `(0, 1, 7)` (`src/magic_geo/crust_dry_rock_accounting_validation.py:1074`).

### Positive delta: the unresolved rule source

Declared as `positive_adjustment_origin_kind = "unresolved_rule_source"` (`cpp/src/engine/process_serialization.cpp:198-199`). When `mass_delta > 0` (`cpp/src/engine/crust_material.cpp:851-869`):

1. Form the packet `{9, current_plate_id, static_cast<int>(process_reason), mass_delta}` — kind `9` = `unresolved_rule_source`, plate = the cell's *current* (post-reassignment) plate, reason = the rule that ran.
2. `merge_packet` binary-searches the key-sorted row (`std::lower_bound` with `packet_key_less`) and either adds to the existing equal-key packet or inserts in place, preserving canonical order. A non-finite sum throws `crust material shadow rule addition overflowed`.
3. Append one `CrustMaterialShadowAdjustment` with the same key and mass into `unresolved_source_adjustments_by_cell[cell]`.

Because the key encodes the reason, repeated positive deltas from different rules in the same step land in *different* packets; repeated deltas from the *same* rule on the same cell merge.

### Negative delta: proportional, provenance-preserving removal

Declared as `negative_adjustment_allocation = "proportional_across_transported_packets_with_remainder_to_largest_packet_lowest_key_tie_break"` (`cpp/src/engine/process_serialization.cpp:200-201`). When `mass_delta < 0` (`cpp/src/engine/crust_material.cpp:872-988`), with `requested_removal = -mass_delta`:

1. If the row is empty, throw `crust material shadow rule sink has no material packets`.
2. In one pass, compute `current_total` (plain `double` accumulation in key order) and `correction_index` — the index of the packet with the strictly greatest mass, scanned in key order with `>`. **The strict comparison is the tie-break**: on equal masses the first (lowest-key) packet wins.
3. Under-removal guard: if `requested_removal > current_total + forward_error_bound(current_total + requested_removal, packets.size() + 2)`, throw `crust material shadow rule sink exceeds available surface mass`.
4. If `requested_removal >= current_total`, this is **exact exhaustion**: emit one sink adjustment per packet at that packet's full mass, clear the row, and return.
5. Otherwise compute `removals[i] = requested_removal * packets[i].mass / current_total` for every packet, accumulate `provisional_removal`, then assign the arithmetic correction: `removals[correction_index] += requested_removal - provisional_removal`.
6. Every removal must be finite, `>= 0`, and `<= packets[i].mass`, else `crust material shadow proportional sink is invalid`. Each strictly positive removal is appended as a sink adjustment carrying the *original* packet key (this is what "provenance-preserving" means — a sink never re-labels the mass it removes).
7. Remainders `> 0` are retained; a packet reduced to exactly `0` is dropped. If the retained set is empty in this branch, throw `crust material shadow proportional sink exhausted all packets`.
8. Re-assert canonical ordering on the surviving row.

### Worked example: proportional removal with correction

A cell holds three packets (already key-sorted):

| Key | Mass (kg) |
|---|---|
| `(0, 2, -1)` oceanic / plate 2 / initial | `4.0e18` |
| `(1, 2, -1)` continental / plate 2 / initial | `6.0e18` |
| `(9, 2, 3)` unresolved / plate 2 / `divergent_continental_rifting` | `2.0e18` |

`current_total = 1.2e19`. `correction_index` is the second packet (`6.0e18`, the strict maximum). A `continental_collision_orogeny`-driven thinning of `-3.0e18 kg` produces:

| Key | `removal = 3.0e18 * mass / 1.2e19` | Retained |
|---|---|---|
| `(0, 2, -1)` | `1.0e18` | `3.0e18` |
| `(1, 2, -1)` | `1.5e18` + correction | `4.5e18` |
| `(9, 2, 3)` | `0.5e18` | `1.5e18` |

Three sink adjustments are recorded, all tagged `process_reason_id = 5`, each keyed by the packet it drew from. If the first two packets had both been `5.0e18`, the strict-`>` scan starting at index 0 would leave `correction_index` on `(0, 2, -1)` — the lowest key.

### Adjustment table flattening

At finalization, `flatten_adjustments` (`cpp/src/engine/crust_material.cpp:285-323`) normalizes each cell's adjustment vector (drop zeros, sort by the 4-tuple, coalesce equal 4-tuples) and re-asserts strict ascending uniqueness, throwing `crust material shadow adjustments are not sorted and unique`. Per-reason totals are then accumulated into `unresolved_source_mass_kg_by_reason` / `unresolved_sink_mass_kg_by_reason` (`:1199-1218`) and cross-checked against the global totals.

## Valid intermediate empty and exhausted states

The engine treats an emptied row as a legitimate intermediate state *within a step*, and says so in the source comment at `cpp/src/engine/crust_material.cpp:910-914`:

> Exact exhaustion is valid. A following ordered rule (normally a thickness/density bound) may explicitly reseed this empty surface row. A request materially larger than the available shadow mass was rejected by the under-removal check above.

Two structural facts make this safe:

1. `divergent_continental_rifting` floors crust thickness at `0.0` (`cpp/src/engine/tectonics.cpp:1409-1413`, with its own comment explaining that a fully uncovered overlap row can enter the rule at zero thickness), so a rifting sink can legitimately request the whole row.
2. `thickness_bound_enforcement` (reason 8) then clamps thickness to a strictly positive minimum (`4.5` km oceanic, `16.0` km continental), which produces a positive delta and reseeds the row with an `unresolved_rule_source` packet.

The corresponding fail-closed points are:

| Situation | Outcome |
|---|---|
| Exact exhaustion mid-step | Valid — every packet is recorded as a sink adjustment and the row is cleared |
| Removal materially larger than the row total | Throws `crust material shadow rule sink exceeds available surface mass` |
| Sink applied to an already-empty row | Throws `crust material shadow rule sink has no material packets` |
| Row still empty when the **next** step's transport reads it | Throws `crust material shadow source cell has no material packets` (`cpp/src/engine/crust_material.cpp:658-662`) |
| Closing row mass not mirroring the scalar `area*thickness*density` | Throws `crust material shadow cell scalar mirror residual is excessive` |

So exhaustion is an intra-step state only. The accounting model states the equivalent contract as a serialized string: `exact_exhaustion_semantics = "empty_reservoir_valid_and_reseed_requires_a_later_explicit_transfer"` (`cpp/src/engine/crust_reservoir_serialization.cpp:165-167`).

## Serialized shadow schema

Top-level keys: `crust_material_shadow_model` (declarative) and `crust_material_shadow_history` (one record per plate-motion step), placed at `cpp/src/engine/world_serialization.cpp:183-198`. Every mass is emitted at `std::numeric_limits<double>::max_digits10` (17) — declared in the shadow serializer as a function-local `constexpr int mass_precision` (`cpp/src/engine/process_serialization.cpp:227-228`, `:247-248`, `:271-272`); the accounting serializer uses the same value under a file-scope `MASS_PRECISION` (`cpp/src/engine/crust_reservoir_serialization.cpp:7`). `num()` applies that precision as `std::fixed`, so it means 17 **decimal places** — not 17 significant digits (`cpp/src/engine/core.cpp:168-177`).

`crust_material_shadow_model` — 27 keys, exhaustive (`cpp/src/engine/process_serialization.cpp:164-220`; the validator requires the key set to match exactly and every value to be literal-equal, `src/magic_geo/crust_material_shadow_validation.py:68-149`):

| Key | Value |
|---|---|
| `model_type` | `persistent_sparse_surface_crust_mass_shadow_v1` |
| `mode` | `shadow` |
| `mass_unit` | `kg` |
| `dry_rock_mass_definition` | `cell_area_km2_times_crust_thickness_km_times_crust_density_g_cm3_times_1e12` |
| `origin_kind_order` | the 10-element array above |
| `packet_key_fields` | `["origin_kind_id","origin_plate_id","origin_reason_id"]` |
| `transport_advection_model` | `source_normalized_overlap_with_final_edge_remainder_v1` |
| `transport_normalization_scope` | `per_source_sum_of_raw_overlap_areas` |
| `transport_remainder_rule` | `final_destination_edge_receives_source_mass_roundoff_remainder` |
| `packet_coalescing_model` | `sorted_equal_key_sum_v1` |
| `packet_sort_order` | `origin_kind_id_then_origin_plate_id_then_origin_reason_id` |
| `ordered_rule_adjustment_model` | `ordered_positive_unresolved_source_proportional_negative_sink_v1` |
| `positive_adjustment_origin_kind` | `unresolved_rule_source` |
| `negative_adjustment_allocation` | `proportional_across_transported_packets_with_remainder_to_largest_packet_lowest_key_tie_break` |
| `raw_transport_scalar_reference` | `raw_overlap_density_weighted_crust_volume_times_1e12` |
| `shadow_minus_raw_transport_residual_semantics` | the geometry-diagnostic string quoted above |
| the 11 authority flags | see [Non-authoritative by construction](#non-authoritative-by-construction) |

`crust_material_shadow_history[]` record — 28 keys (`cpp/src/engine/process_serialization.cpp:268-367`; key set pinned in `src/magic_geo/crust_material_shadow_validation.py:37-66`):

| Key | Type | Meaning |
|---|---|---|
| `id` | int | Step index; equals the array position |
| `plate_motion_history_id` | int | Links to `plate_motion_history[id]` |
| `stage` | string | Copied from the plate-motion step (`initial_plate_domains` or `plate_motion_iteration`) |
| `erosion_iteration` | int | Copied from the plate-motion step (`-1` at step 0) |
| `cell_count` | int | Mesh cell count |
| `opening_packets` | packet table | State at step entry; bit-equal to the prior `closing_packets` |
| `transported_packets` | packet table | After source-normalized advection, before any rule |
| `unresolved_source_adjustments` | adjustment table | Every positive rule delta |
| `unresolved_sink_adjustments` | adjustment table | Every proportional removal |
| `closing_packets` | packet table | State at step exit |
| `global_opening_mass_kg` | double | Sum over `opening_packets` |
| `global_transported_mass_kg` | double | Sum over `transported_packets` |
| `global_unresolved_source_mass_kg` | double | Sum over source adjustments |
| `global_unresolved_sink_mass_kg` | double | Sum over sink adjustments |
| `global_closing_mass_kg` | double | Sum over `closing_packets` |
| `raw_transported_scalar_mass_kg` | double | `plan.transported_density_weighted_crust_volume * 1e12` |
| `shadow_minus_raw_transport_residual_kg` | double | Geometry closure diagnostic |
| `source_to_transport_residual_kg` | double | `transported - opening` |
| `closing_scalar_mass_kg` | double | Sum of `area*thickness*density*1e12` over cells |
| `closing_scalar_mass_residual_kg` | double | Serialized from `post_scalar_mirror_residual_kg` |
| `maximum_absolute_cell_closing_scalar_mass_residual_kg` | double | Worst per-cell mirror residual in this step |
| `ordered_adjustment_reconciliation_residual_kg` | double | `closing - transported - source + sink` |
| `opening_packet_count` | int | |
| `transported_packet_count` | int | |
| `unresolved_source_adjustment_count` | int | |
| `unresolved_sink_adjustment_count` | int | |
| `closing_packet_count` | int | |
| `ordered_reason_adjustments` | array of 10 | `{process_reason_id, process_reason, source_mass_kg, sink_mass_kg}` per reason, in enum order |

Packet tables serialize as `{cell_offsets, origin_kind_ids, origin_plate_ids, origin_reason_ids, dry_rock_mass_kg}`; adjustment tables add `process_reason_ids` (`cpp/src/engine/process_serialization.cpp:224-264`).

`summary` extension — 18 keys appended by `summary_with_crust_material_shadow_json` (`cpp/src/engine/summary.cpp:17-175`):

| Key | Derivation |
|---|---|
| `crust_material_shadow_history_step_count` | `history.size()` |
| `total_crust_material_shadow_packet_count` | Σ(opening + transported + closing) |
| `maximum_crust_material_shadow_packet_count_per_table` | max over the three per-step maxima |
| `total_crust_material_shadow_opening_packet_count` | Σ opening |
| `total_crust_material_shadow_transported_packet_count` | Σ transported |
| `total_crust_material_shadow_closing_packet_count` | Σ closing |
| `maximum_crust_material_shadow_opening_packet_count_per_step` | max opening |
| `maximum_crust_material_shadow_transported_packet_count_per_step` | max transported |
| `maximum_crust_material_shadow_closing_packet_count_per_step` | max closing |
| `total_crust_material_shadow_adjustment_count` | Σ(source + sink) |
| `maximum_crust_material_shadow_adjustment_count_per_table` | max(max source, max sink) |
| `total_crust_material_shadow_unresolved_source_adjustment_count` | Σ source |
| `total_crust_material_shadow_unresolved_sink_adjustment_count` | Σ sink |
| `cumulative_crust_material_shadow_unresolved_source_mass_kg` | Σ `unresolved_source_mass_kg` |
| `cumulative_crust_material_shadow_unresolved_sink_mass_kg` | Σ `unresolved_sink_mass_kg` |
| `maximum_absolute_crust_material_shadow_transport_raw_residual_kg` | max `|shadow_minus_raw_transport_mass_kg|` |
| `maximum_crust_material_shadow_closing_scalar_relative_residual` | max `|post_scalar_mirror_residual| / max(1, |closing_scalar_mass|)` |
| `maximum_absolute_crust_material_shadow_adjustment_reconciliation_residual_kg` | max `|ordered_adjustment_reconciliation_residual_kg|` |

## The finite three-reservoir accounting model

Where the shadow answers "which provenance keys make up this cell's implied mass?", the accounting model answers "if the ordered rules' implied mass changes had to come from somewhere finite, what would the books look like?". Both questions are bookkeeping questions. The model's own `mode` is `finite_accounting_shadow`.

Three reservoirs, in the declared `reservoir_order`:

| id | Name | Owner space | Owner count | State |
|---|---|---|---|---|
| 0 | `surface_basement_crust` | cell id | `cell_count` | Live; seeded from scalar crust state at step 0 |
| 1 | `upper_mantle_exchange` | none (single global row) | 1 | Live; a numerical counter-reserve |
| 2 | `subducted_slab` | plate id | `plate_count` | Allocated, permanently empty (no transfer mechanism is enabled) |

Packet record (`cpp/src/engine/types/crust_reservoir.hpp:27-40`):

| Field | Type | Domain |
|---|---|---|
| `origin_domain_id` | `int` | `0` = `initial_surface_crust`, `1` = `initial_upper_mantle_exchange_reserve` |
| `origin_kind_id` | `int` | domain 0: `0..8` (the crust type at initialization); domain 1: exactly `-1` |
| `origin_plate_id` | `int` | domain 0: `0..plate_count-1`; domain 1: exactly `-1` |
| `dry_rock_mass_kg` | `double` | Strictly positive in any canonical table |

`validate_packet_key` (`cpp/src/engine/crust_reservoir.cpp:43-70`) rejects any other combination with `finite dry-rock accounting surface-origin key is invalid`, `... exchange-origin key is invalid`, or `... packet has an invalid origin domain`. Note there is **no** `unresolved_rule_source` kind here: the accounting model's origin keys are frozen at initialization. Mass that arrives on a cell after step 0 always carries the exchange-reserve key `(1, -1, -1)`, never a new surface key.

Tables are owner-offset CSR keyed by the origin triple (`cpp/src/engine/types/crust_reservoir.hpp:34-40`):

| Array | Length | Notes |
|---|---|---|
| `owner_offsets` | `owner_count + 1` | `cell_count + 1` for surface, `2` for the mantle, `plate_count + 1` for slabs |
| `origin_domain_ids`, `origin_kind_ids`, `origin_plate_ids` | packet count | The key triple |
| `dry_rock_mass_kg` | packet count | `max_digits10` |

Sort order is `origin_domain_id_then_origin_kind_id_then_origin_plate_id`; coalescing is `sorted_equal_key_sum_v1`. `validate_canonical_packets` (`cpp/src/engine/crust_reservoir.cpp:168-183`) throws `finite dry-rock accounting packets are not canonical` on any out-of-order or duplicate key.

Surface transport reuses the identical `source_normalized_overlap_with_final_edge_remainder_v1` algorithm (`cpp/src/engine/crust_reservoir.cpp:371-543`) with the same sorted `(source, destination, edge_index)` traversal and final-edge subtraction, but merges into destinations through `merge_packet` so the operational caps can be enforced incrementally. After transport, every cell's accounting mass is cross-checked against the shadow's transported mass for that cell within a forward-error bound; divergence throws `finite dry-rock accounting transport diverged from Phase-S` (`:1255-1276`).

## The initial upper-mantle exchange counter-reserve

At initialization (`cpp/src/engine/crust_reservoir.cpp:962-1116`):

1. Every cell contributes one surface packet `(0, crust_type, plate_id)` with mass `area*thickness*density*1e12`. Invalid `crust_type` (outside `[0,8]`) or `plate_id` (outside `[0, plate_count)`) throws `finite dry-rock accounting initial surface key is invalid`.
2. The **surface state envelope capacity** is computed from two hard-coded, explicitly uncalibrated constants (`cpp/src/engine/crust_reservoir.cpp:20-21`):

| Constant | Value | Serialized as |
|---|---|---|
| `SURFACE_ENVELOPE_MAXIMUM_THICKNESS_KM` | `76.0` | `capacity_maximum_surface_thickness_km` |
| `SURFACE_ENVELOPE_MAXIMUM_DENSITY_G_CM3` | `3.08` | `capacity_maximum_surface_density_g_cm3` |
| `DRY_ROCK_MASS_KG_PER_DENSITY_WEIGHTED_KM3` | `1.0e12` | implicit in `capacity_formula` |

```
surface_state_envelope_capacity_kg
    = Σ_cells area_km2 * 76.0 * 3.08 * 1.0e12
```

serialized as `capacity_formula = "sum_control_volume_area_km2_times_76_km_times_3.08_g_cm3_times_1e12"`.

The two numbers coincide exactly with the upper clamps the ordered rules enforce on the authoritative scalar state — `76.0` km is the continental thickness maximum at `cpp/src/engine/tectonics.cpp:1519` and `3.08` g/cm³ is the density maximum at `cpp/src/engine/tectonics.cpp:1532`. Reading that coincidence as "the envelope arithmetically bounds any surface mass the clamped rule chain can produce" is *this page's inference from the two clamp constants*, not a statement the source makes. What the source does state is `capacity_geophysically_calibrated = false` and `capacity_semantics = finite_numerical_surface_state_envelope_not_an_estimate_of_upper_mantle_mass`. Treat both constants as **uncalibrated numerical envelope constants**.

3. The counter-reserve is the slack: `mantle_mass = envelope_capacity - surface_mass`, pushed as a single packet `(1, -1, -1)` if strictly positive. If the envelope is non-finite, non-positive, or smaller than the initial surface mass, initialization throws `finite dry-rock accounting surface envelope cannot contain initial crust`.
4. `capacity_initialization_residual_kg = opening_global - envelope_capacity` is stored and asserted to be within `forward_error_bound(|surface| + |mantle| + |capacity|, cell_count + 4)`, else `finite dry-rock accounting initial capacity did not close`.
5. Step 0 records `opening == transported == closing` for all three reservoirs, `maximum_surface_packet_count_per_owner = 1`, and `maximum_live_reservoir_packet_count = cell_count + mantle packet count`.

Because the reserve is defined as capacity minus current surface mass, the global inventory `surface + mantle + slab` tracks the envelope at every step — that is the "finite" in "finite three-reservoir". It is not asserted bit-exactly: the closure guard tests `|opening_global - surface_state_envelope_capacity_kg| <= accounting_bound` (`cpp/src/engine/crust_reservoir.cpp:1802-1803`), so the invariant holds only within the forward-error bound. And the invariant is arithmetic, not physical.

The mantle pool has no spatial structure at all. Its declared topology is `single_global_packet_pool_shared_by_all_cells_without_spatial_coordinates_v1` with `instantaneous_global_mantle_mixing_assumed = true`, `mantle_origin_packets_homogenized = false` (origin keys stay distinct inside the pool), and `mantle_spatial_transport_resolved = false`.

## Reason-major transactions, sink-before-source, and withdrawal order

`advance_crust_dry_rock_accounting_step` (`cpp/src/engine/crust_reservoir.cpp:1118-1823`) reads the just-finalized shadow step and replays its unresolved adjustments as finite transfers. Declared as `phase_s_request_source = "crust_material_shadow_history_unresolved_adjustments_replayed_as_finite_proxy_compensations"`.

### Atomicity

The whole step runs on **copies** of `surface`, `mantle`, and `slab` (`cpp/src/engine/crust_reservoir.cpp:1142-1146`, with the comment "Work on copies so depletion or any failed invariant leaves the externally visible accounting state unchanged"). The copies are only moved back into the state at `:1819-1822`, after every invariant has passed. This implements the serialized contract `insufficient_exchange_semantics = "fail_closed_without_publishing_partial_accounting_state"`.

### Linkage

| Requirement | Source |
|---|---|
| `shadow_step.id == state.history.size()` | `:1132` |
| `shadow_step.plate_motion_history_id == shadow_step.id` | `:1133` |
| `shadow_step.cell_count == cells.size()`, `stage` non-empty | `:1134-1135` |
| Opening surface / mantle / slab tables bit-equal to the previous step's closing tables | `:1178-1196`, throwing `finite dry-rock accounting opening state does not link exactly` |

### Request construction

`adjustment_requests` (`:772-814`) collapses each shadow adjustment table into a `cell x reason` matrix of positive masses, validating the CSR shape and every record. Then, per reason (`:1289-1337`):

| Guard | Error |
|---|---|
| A cell has both a source and a sink request under the same reason | `finite dry-rock accounting cell/reason has both signs` |
| Reason 0, 1, or 7 has any non-zero request | `finite dry-rock accounting age-only reason changed mass` |
| Per-reason totals differ from `shadow_step.unresolved_*_mass_kg_by_reason` beyond `forward_error_bound(..., cell_count + 8)` | `finite dry-rock accounting requests do not match Phase-S reason totals` |

### Transaction order

Declared verbatim as `proxy_transaction_order = "process_reason_then_all_surface_sinks_by_ascending_cell_and_origin_key_then_all_surface_sources_by_ascending_cell_and_origin_key"` (`cpp/src/engine/crust_reservoir_serialization.cpp:152-153`). Implemented at `cpp/src/engine/crust_reservoir.cpp:1289-1486`:

```
for reason in 0 .. 9:                       # ascending CrustProcessReason
    for cell in 0 .. cell_count-1:          # ascending cell id
        commit this (cell, reason) SURFACE SINK  -> mantle
    assert requested_source[reason] <= mantle mass now available
    for cell in 0 .. cell_count-1:          # ascending cell id
        commit this (cell, reason) SURFACE SOURCE <- mantle
```

The **sink-before-source rule inside each reason** is what makes the exchange reserve able to fund that reason's sources: mass removed from the surface is already back in the pool before any withdrawal from it. The explicit pre-check at `:1411-1416` throws `finite dry-rock accounting upper-mantle exchange reserve exhausted` if the reason's total source demand still exceeds the pool.

### Surface sink: proportional withdrawal

`withdraw_packets` (`:550-647`), declared as `surface_sink_model = "proportional_packets_with_remainder_to_largest_packet_lowest_key_tie_break"`:

1. Request must be finite and `> 0`; available mass must be `> 0`.
2. If `requested > available`, bounded surface exhaustion is allowed (`allow_bounded_surface_exhaustion = true` for surface sinks): the excess must be within `forward_error_bound(available + requested, source.size() + 2)`, and `fulfilled` is clamped to `available`. Otherwise throw `finite dry-rock accounting surface sink exceeds available mass`.
3. If `fulfilled >= available`, take every packet whole and clear the row.
4. Otherwise: `correction_index` = the strictly-greatest-mass packet scanned in ascending key order (so ties keep the lowest key); `removals[i] = fulfilled * mass_i / available`; `removals[correction_index] += fulfilled - Σ removals`.
5. Each removal must be in `[0, mass_i]`, else `finite dry-rock accounting proportional withdrawal failed`; a negative remainder throws `... withdrawal produced negative mass`.
6. Both the residual row and the withdrawn set are re-normalized.

Each withdrawn packet is merged into the mantle pool by its own key and emits one transfer record.

### Mantle source: consumption order

`withdraw_exchange_packets` (`:649-732`), declared as `mantle_withdrawal_model = "initial_exchange_reserve_first_then_largest_packet_lowest_key_tie_break_v1"`:

1. `requested <= available` is required **strictly**, with no tolerance — otherwise `finite dry-rock accounting upper-mantle exchange reserve exhausted`.
2. Loop while mass remains:
   - If any packet in the pool has `origin_domain_id == 1` (the initial exchange reserve), restrict candidates to those packets.
   - Among candidates, select the strictly-greatest mass; because the pool is key-sorted and the comparison is `>`, ties resolve to the lowest key. The source comment at `:697-698` states this explicitly.
   - Withdraw `min(remaining, selected.mass)`; erase the packet if fully consumed, otherwise decrement it (a non-positive or non-finite remainder throws `finite dry-rock accounting exchange depletion failed`).
3. `fulfilled_mass_kg` is exactly the request — mantle sources are never partially fulfilled, and the closure check at `:1804` requires `requested_source_total == fulfilled_source_total` **exactly**.

Consequence worth stating plainly: because domain-1 packets are drained first, surface cells re-seeded by a bound-enforcement rule receive mass keyed `(1, -1, -1)` — the counter-reserve origin — and once the domain-1 packets are gone, they receive back whatever domain-0 keys other cells previously shed. Neither outcome is a provenance claim; `material_provenance_resolved` is `false`.

### Worked example: one reason's transaction

Suppose in step 4, reason `8` (`thickness_bound_enforcement`) has a sink of `2.0e17 kg` on cell 3 and a source of `5.0e17 kg` on cell 12.

1. Reasons 0-7 are processed first, in order.
2. Reason 8, sinks: cell 3's surface row is withdrawn proportionally for `2.0e17 kg`. If cell 3 held `(0, 0, 5) = 8.0e17` and `(1, -1, -1) = 2.0e17`, the removals are `1.6e17` and `0.4e17` (with the correction landing on the first, larger packet). Two transfer records are emitted, both with `source_reservoir_id = 0`, `source_owner_id = 3`, `destination_reservoir_id = 1`, `destination_owner_id = -1`, `process_reason_id = 8`.
3. `requested_source[8] = 5.0e17` is checked against the pool mass (now including the `2.0e17` just returned).
4. Reason 8, sources: cell 12 withdraws `5.0e17 kg`. If a `(1, -1, -1)` reserve packet is still present it supplies all of it; one transfer record is emitted with `source_reservoir_id = 1`, `source_owner_id = -1`, `destination_reservoir_id = 0`, `destination_owner_id = 12`.
5. Cell 12's closing row now contains a `(1, -1, -1)` packet. Its origin domain says "came from the numerical exchange reserve", which is a bookkeeping statement, not a petrological one.

### Transfer records

`append_transfer` (`cpp/src/engine/crust_reservoir.cpp:734-767`) writes one column-major row into `proxy_compensation_transfers`:

| Column | Value |
|---|---|
| `sequence_ids` | Monotone `0, 1, 2, ...` within the step |
| `mechanism_ids` | Always `0` (`RULE_PROXY_COMPENSATION_MECHANISM_ID`); declared `proxy_transfer_mechanism = "ordered_rule_mass_compensation_v1"` |
| `process_reason_ids` | The driving `CrustProcessReason` |
| `cell_ids` | The surface cell involved |
| `fragment_ids` | Always `-1` (`NO_FRAGMENT_ID`) — no overlap-fragment link exists |
| `source_reservoir_ids` / `source_owner_ids` | `(0, cell)` for a sink, `(1, -1)` for a source |
| `destination_reservoir_ids` / `destination_owner_ids` | `(1, -1)` for a sink, `(0, cell)` for a source |
| `origin_domain_ids`, `origin_kind_ids`, `origin_plate_ids` | The moved packet's key |
| `physical_basis_resolved` | Always `0`, serialized as `false` |
| `dry_rock_mass_kg` | Strictly positive |

`validate_transfer_table` (`:865-931`) re-checks all of the above and additionally rejects any transfer whose source or destination is reservoir `2`, throwing `finite dry-rock accounting transfer record is invalid`.

## Empty slab tables and physical_basis_resolved

The subducted-slab reservoir exists structurally and is deliberately inert:

| Property | Value | Source |
|---|---|---|
| Owner space | plate id, `plate_count` rows | `cpp/src/engine/crust_reservoir.cpp:1041-1043` |
| Owner semantics | `subducted_slab_owner_semantics = "subducting_source_plate_id"` | `crust_reservoir_serialization.cpp:169-170` |
| Current state | `subducted_slab_phase_2_state = "plate_resolved_empty_reservoir_no_transfer_mechanism_enabled"` | `crust_reservoir_serialization.cpp:171-172` |
| Transfers touching it | None — `validate_transfer_table` rejects reservoir `2` on either endpoint | `crust_reservoir.cpp:923-924` |
| Serialized flags | `plate_resolved_slab_accounting_state_present = true`, `subducted_slab_reservoir_resolved = false` | `crust_reservoir_serialization.cpp:180,185` |
| Validator assertion | `if any(opening_slab) or any(closing_slab): raise ValueError("phase-2 slab reservoirs must remain empty")` | `src/magic_geo/crust_dry_rock_accounting_validation.py:906-907` |

So `opening_subducted_slab_packets` and `closing_subducted_slab_packets` are always `owner_offsets = [0, 0, ..., 0]` with empty key and mass arrays, and `opening_subducted_slab_mass_kg` / `closing_subducted_slab_mass_kg` are always `0.0`. The presence of the tables is a schema commitment, not evidence that subduction moves mass. Note also that `subduction_polarity_resolved` is `false` in this same model — the plate-boundary ledger's physical polarity remains explicitly unknown, so there is nothing to key a slab transfer on even if a mechanism existed.

`physical_basis_resolved` is `false` on **every** transfer without exception. It is emitted as a per-record boolean array (`bool_array_json`, `cpp/src/engine/crust_reservoir_serialization.cpp:9-27`, which itself throws `finite dry-rock accounting boolean column is invalid` on anything other than `0` or `1`), and the per-reason transaction record carries the same flag as `physical_source_sink_resolved: false` (`:99`).

## Operational caps as memory-safety limits

Three constants, declared in `cpp/src/engine/types/crust_reservoir.hpp:12-20` with the comment "Operational memory-safety limits for the non-authoritative accounting shadow. They are deliberately far above the measured 4,096-cell reference peaks and are not physical material-flux or reservoir-capacity limits."

| Constant | Value | Enforced at | Error message |
|---|---|---|---|
| `CRUST_DRY_ROCK_MAX_SURFACE_PACKETS_PER_OWNER` | `1024` | `enforce_surface_owner_packet_limit` (`crust_reservoir.cpp:225-233`) and inside `merge_packet` before any insert (`:207-211`) | `finite dry-rock accounting surface-owner packet safety limit exceeded` |
| `CRUST_DRY_ROCK_MAX_LIVE_RESERVOIR_PACKETS` | `1000000` | `enforce_live_packet_limit` (`:262-268`) and inside `merge_packet` (`:212-219`) | `finite dry-rock accounting live reservoir packet safety limit exceeded` |
| `CRUST_DRY_ROCK_MAX_PROXY_TRANSFERS_PER_STEP` | `1000000` | `append_transfer` (`:744-749`) | `finite dry-rock accounting per-step transfer safety limit exceeded` |

They are serialized as `maximum_surface_packets_per_owner`, `maximum_live_reservoir_packets`, and `maximum_proxy_transfers_per_step`, alongside `operational_safety_limit_model = "incremental_fail_closed_packet_and_transfer_memory_caps_v1"`, `operational_safety_limits_enforced_incrementally = true`, and the two disclaimers `operational_safety_limits_are_physical_flux_limits = false` and `operational_safety_limit_semantics = "numerical_memory_safety_limits_not_physical_flux_or_reservoir_capacity_limits"` (`cpp/src/engine/crust_reservoir_serialization.cpp:138-151`).

"Incremental" is literal: the live count is maintained as packets are inserted and removed (`:1378-1379`, `:1390-1397`, `:1437-1438`, `:1454-1461`), and at the end of the step the incrementally tracked count is compared against a fresh full recount, throwing `finite dry-rock accounting incremental live packet count diverged` on a mismatch (`:1554-1562`). Observed peaks are exported per step as `maximum_surface_packet_count_per_owner` and `maximum_live_reservoir_packet_count`, and rolled up in the summary as `maximum_crust_dry_rock_surface_packet_count_per_owner` and `maximum_crust_dry_rock_live_reservoir_packet_count_per_step`.

The shadow model has no equivalent published cap; its only hard structural limit is that a flattened packet table must fit in `int` offsets (`cpp/src/engine/crust_material.cpp:270-277`).

## Accounting closure invariants and fail-closed guards

At the end of every accounting step (`cpp/src/engine/crust_reservoir.cpp:1554-1810`):

| Invariant | Residual field | Failure |
|---|---|---|
| Surface transport conserves mass | `source_to_transport_residual_kg` | `finite dry-rock accounting transport did not conserve surface mass` |
| Per-cell transported mass matches the shadow | (checked only) | `finite dry-rock accounting transport diverged from Phase-S` |
| Per-reason transfer totals match fulfilled source/sink | (checked only) | `finite dry-rock accounting transfer reasons do not reconcile` |
| Incremental vs recounted live packets | (checked only) | `finite dry-rock accounting incremental live packet count diverged` |
| Per-cell closing mass matches shadow closing and the scalar crust state | `maximum_absolute_cell_closing_scalar_mass_residual_kg` | `finite dry-rock accounting closing surface diverged from scalar state` |
| Per-origin-key totals unchanged across all three reservoirs | `maximum_absolute_origin_closure_residual_kg` | folded into the final closure check |
| Per-reservoir `closing - opening - incoming + outgoing` | `maximum_absolute_reservoir_transfer_residual_kg` | folded into the final closure check |
| Global inventory unchanged | `global_accounting_residual_kg` | folded into the final closure check |
| Global inventory still equals the envelope | `capacity_initialization_residual_kg` | folded into the final closure check |
| Source demand exactly fulfilled | `requested_minus_fulfilled_source_mass_kg` | `requested_source_total != fulfilled_source_total` → fail |
| Sink demand fulfilled up to the bound | `requested_minus_fulfilled_sink_mass_kg` | `requested_sink_total - fulfilled_sink_total > accounting_bound` → fail |

The combined final check throws `finite dry-rock accounting closure invariant failed` (`:1798-1810`). Its `accounting_bound` is `forward_error_bound(|opening_global| + |closing_global| + requested_source_total + requested_sink_total, arithmetic_terms)` where `arithmetic_terms` sums all five packet-table sizes, the transfer count, the overlap edge count, `cell_count`, and `16` (`:1785-1797`).

Note the asymmetry: source fulfillment is required to be *bit-exact* while sink fulfillment is allowed to fall short within the bound. That is the arithmetic consequence of `allow_bounded_surface_exhaustion` on surface sinks versus the strict availability test on mantle sources.

For the per-reservoir residual, the "opening" surface mass is the **transported** surface mass, not the step's opening mass, because transport happens before any transfer (`:1754-1758`).

## Serialized accounting schema

Top-level keys `crust_dry_rock_accounting_model` and `crust_dry_rock_accounting_history` (`cpp/src/engine/world_serialization.cpp:185-202`).

`crust_dry_rock_accounting_model` — 54 keys total (`cpp/src/engine/crust_reservoir_serialization.cpp:108-195`): the 18 authority flags and 9 semantics strings tabled earlier on this page, plus these 27 structural keys — `model_type`, `mass_unit`, `accounting_scope`, `reservoir_order`, `origin_domain_order`, `packet_key_fields`, `packet_sort_order`, `packet_coalescing_model`, `surface_transport_model`, `capacity_model`, `capacity_formula`, `capacity_maximum_surface_thickness_km`, `capacity_maximum_surface_density_g_cm3`, `operational_safety_limit_model`, `maximum_surface_packets_per_owner`, `maximum_live_reservoir_packets`, `maximum_proxy_transfers_per_step`, `operational_safety_limits_enforced_incrementally`, `proxy_transaction_order`, `proxy_transfer_mechanism`, `mantle_withdrawal_model`, `mantle_exchange_topology`, `surface_sink_model`, `exact_exhaustion_semantics`, `insufficient_exchange_semantics`, `subducted_slab_owner_semantics`, `phase_s_request_source`. `model_type` is `finite_three_reservoir_dry_rock_accounting_v1`; `accounting_scope` is `surface_basement_crust_upper_mantle_exchange_and_plate_resolved_subducted_slab`; `capacity_model` is `surface_state_envelope_v1`. The validator requires the emitted key set to equal `set(MODEL_LITERAL_VALUES)` exactly and every value to be literal-equal (`src/magic_geo/crust_dry_rock_accounting_validation.py:836-840`).

`crust_dry_rock_accounting_history[]` record — 47 keys (`cpp/src/engine/crust_reservoir_serialization.cpp:197-305`; key set pinned in `src/magic_geo/crust_dry_rock_accounting_validation.py:150-179`):

| Group | Keys |
|---|---|
| Identity and linkage | `id`, `plate_motion_history_id`, `crust_material_shadow_history_id`, `stage`, `erosion_iteration`, `cell_count`, `plate_count` |
| Packet tables (7) | `opening_surface_packets`, `transported_surface_packets`, `closing_surface_packets`, `opening_upper_mantle_packets`, `closing_upper_mantle_packets`, `opening_subducted_slab_packets`, `closing_subducted_slab_packets` |
| Transfers | `proxy_compensation_transfers` (14 parallel columns) |
| Per-reason | `ordered_reason_transactions` (10 records: `process_reason_id`, `process_reason`, `requested_surface_source_mass_kg`, `requested_surface_sink_mass_kg`, `fulfilled_surface_source_mass_kg`, `fulfilled_surface_sink_mass_kg`, `physical_source_sink_resolved`) |
| Capacity | `surface_state_envelope_capacity_kg`, `total_control_volume_area_km2` |
| Masses | `opening_surface_mass_kg`, `transported_surface_mass_kg`, `closing_surface_mass_kg`, `opening_upper_mantle_mass_kg`, `closing_upper_mantle_mass_kg`, `opening_subducted_slab_mass_kg`, `closing_subducted_slab_mass_kg`, `opening_global_mass_kg`, `closing_global_mass_kg` |
| Residuals | `source_to_transport_residual_kg`, `global_accounting_residual_kg`, `capacity_initialization_residual_kg`, `maximum_absolute_origin_closure_residual_kg`, `maximum_absolute_reservoir_transfer_residual_kg`, `closing_scalar_mass_kg`, `closing_scalar_mass_residual_kg`, `maximum_absolute_cell_closing_scalar_mass_residual_kg`, `requested_minus_fulfilled_source_mass_kg`, `requested_minus_fulfilled_sink_mass_kg` |
| Counters | `opening_surface_packet_count`, `transported_surface_packet_count`, `closing_surface_packet_count`, `opening_upper_mantle_packet_count`, `closing_upper_mantle_packet_count`, `opening_subducted_slab_packet_count`, `closing_subducted_slab_packet_count`, `proxy_compensation_transfer_count`, `maximum_surface_packet_count_per_owner`, `maximum_live_reservoir_packet_count` |

`summary` extension — 21 keys appended by `summary_with_crust_dry_rock_accounting_json` (`cpp/src/engine/crust_reservoir_serialization.cpp:307-491`):

| Key | Derivation |
|---|---|
| `crust_dry_rock_accounting_history_step_count` | `history.size()` |
| `total_crust_dry_rock_surface_packet_count` | Σ(opening + transported + closing surface counts) |
| `total_crust_dry_rock_upper_mantle_packet_count` | Σ(opening + closing mantle counts) |
| `total_crust_dry_rock_subducted_slab_packet_count` | Σ(opening + closing slab counts) — always `0` |
| `total_crust_dry_rock_proxy_transfer_count` | Σ transfer counts |
| `maximum_crust_dry_rock_closing_surface_packet_count_per_step` | max closing surface count |
| `maximum_crust_dry_rock_closing_upper_mantle_packet_count_per_step` | max closing mantle count |
| `maximum_crust_dry_rock_proxy_transfer_count_per_step` | max transfer count |
| `maximum_crust_dry_rock_closing_reservoir_packet_count_per_step` | max of the three closing counts summed |
| `maximum_crust_dry_rock_surface_packet_count_per_owner` | max per-step owner peak |
| `maximum_crust_dry_rock_live_reservoir_packet_count_per_step` | max per-step live peak |
| `cumulative_crust_dry_rock_requested_surface_source_mass_kg` | Σ over steps and reasons |
| `cumulative_crust_dry_rock_requested_surface_sink_mass_kg` | Σ over steps and reasons |
| `cumulative_crust_dry_rock_fulfilled_surface_source_mass_kg` | Σ over steps and reasons |
| `cumulative_crust_dry_rock_fulfilled_surface_sink_mass_kg` | Σ over steps and reasons |
| `minimum_crust_dry_rock_closing_upper_mantle_mass_kg` | min closing mantle mass (`0.0` when the history is empty) |
| `maximum_crust_dry_rock_closing_subducted_slab_mass_kg` | max closing slab mass — always `0.0` |
| `maximum_absolute_crust_dry_rock_global_accounting_residual_kg` | max `\|global_accounting_residual_kg\|` |
| `maximum_absolute_crust_dry_rock_origin_closure_residual_kg` | max `\|maximum_absolute_origin_closure_residual_kg\|` |
| `maximum_absolute_crust_dry_rock_reservoir_transfer_residual_kg` | max `\|maximum_absolute_reservoir_transfer_residual_kg\|` |
| `maximum_crust_dry_rock_closing_scalar_relative_residual` | max `\|closing_scalar_mass_residual\| / max(1, \|closing_scalar_mass\|)` |

`minimum_crust_dry_rock_closing_upper_mantle_mass_kg` is the field to watch: it is the low-water mark of the counter-reserve. If it approached zero, `withdraw_exchange_packets` would start throwing `finite dry-rock accounting upper-mantle exchange reserve exhausted` and generation would fail closed.

One retired field is explicitly forbidden in schema-2 worlds: `crust_dry_rock_accounting_model.legacy_proxy_compensations_exposed` (`src/magic_geo/serialization.py:107-110`). Its presence makes `retired_world_schema_fields` non-empty, which the native loader treats as a hard error.

## Independent replay validation

Both models are re-derived from scratch in Python and compared against the serialized ledgers. Neither validator accepts a native summary field as an operand — the summary is recomputed from the already-replayed history so a stale or edited headline cannot mask a damaged ledger (`src/magic_geo/crust_material_shadow_validation.py:1420-1422`).

| Validator module | Public entry point | Check name (domain) | Consumed by |
|---|---|---|---|
| `src/magic_geo/crust_material_shadow_validation.py` | `validate_crust_material_shadow(world)` | `persistent_crust_material_shadow_replay` (`tectonics`) | `src/magic_geo/geo_validation_physics.py:2685-2706` |
| `src/magic_geo/crust_dry_rock_accounting_validation.py` | `validate_crust_dry_rock_accounting(world)` | `finite_crust_dry_rock_accounting_replay` (`tectonics`) | `src/magic_geo/geo_validation_physics.py:2707-2729` |

Each check's `expected` map enumerates both what is replayed and what stays unresolved — the mechanism that keeps replay integrity separate from physical claims:

| Check | `expected` entries |
|---|---|
| `persistent_crust_material_shadow_replay` | `transported_packets_replay: True`, `ordered_rule_adjustments_replay: True`, `closing_packets_match_scalar_crust_mass: True`, `physical_source_sink_resolved: False`, `global_crust_cycle_mass_conservation_resolved: False` |
| `finite_crust_dry_rock_accounting_replay` | `finite_exchange_inventory_enforced: True`, `global_per_origin_and_reservoir_accounting_closed: True`, `subducted_slab_tables_empty: True`, `physical_source_sink_resolved: False`, `material_provenance_resolved: False`, `global_crust_cycle_mass_conservation_resolved: False` |

What the shadow validator actually replays, per step:

1. Model key set and every literal value (`:802-806`).
2. Record key set, `id == step_index`, and stage/iteration/cell-count agreement with `plate_motion_history[step_index]` (`:836-853`).
3. Step 0: the opening packets must equal `initial_crust_material_shadow_packets(...)` rebuilt from `cells[].area_km2`, the overlap ledger's `remapped_crust_thickness_km_by_cell` / `remapped_crust_density_by_cell`, and `crust_type_by_cell` / `cell_plate_ids` (`:925-947`).
4. Steps `> 0`: opening must match the previous closing (mass-close, not bit-exact).
5. `replay_crust_material_shadow_step(...)` re-derives `transported_packets` from the overlap CSR with zero rule deltas, and rejects any overlap row whose source ids are not `sorted(set(row))` (`:545-548`).
6. Source-row area closure is reconstructed from the CSR and gated at `max(1.0e-6, source_area * 2.0e-10)` km² (`:1011`).
7. Ordered adjustments are re-applied reason-major, cell-major, reconstructing the proportional allocation and the largest-packet/lowest-key correction (`:1039-1138`); a cell/reason may not carry both signs, and a source must be a single record keyed `(9, current_plate, reason)`.
8. Per-cell closing packet mass is compared to `area * (remapped_thickness + process_thickness) * (remapped_density + process_density) * 1e12` using the same composite tolerance shape as the native bound (`:1188-1201`).
9. All 12 step scalars, all 5 counts, and all 10 `ordered_reason_adjustments` records are recomputed; the reason net (`source - sink`) is additionally compared against the transport ledger's `process_inventory_attribution.reasons[i].net_delta.density_weighted_crust_volume * 1e12` (`:1299-1302`).
10. All 13 summary counts and 5 summary scalars are recomputed.

What the accounting validator replays, per step:

1. Model key set and literal values; aligned lengths of `crust_dry_rock_accounting_history`, `crust_material_shadow_history`, and `plate_motion_history`.
2. Triple linkage `record.id == plate_step.id == shadow.id == step_index`, matching `stage`, `erosion_iteration`, `cell_count`, and `plate_count == len(plate_step["plates"])`.
3. Packet tables parsed with per-owner cap enforcement; slab tables asserted empty; live-count table checks against the three caps.
4. Opening reservoir tables compared to the previous record's closing tables with **exact JSON equality** — "opening reservoir links are not bit-exact" (`:918-923`).
5. Requests rebuilt from the shadow's `unresolved_source_adjustments` / `unresolved_sink_adjustments`, with the same canonical-ordering and source-key rules.
6. Step 0: the surface must be `{(0, crust_type, plate): area*thickness*density*1e12}` per cell, the mantle must be `{(1,-1,-1): capacity - surface_mass}` (or empty), all three snapshots must be identical, and there must be zero transfers and zero requests (`:930-1017`).
7. Steps `> 0`: `replay_crust_dry_rock_accounting_step(...)` re-derives transported/closing surface, closing mantle, closing slab, and the full ordered transfer list including `sequence_id` order, and `_transfers_close` requires every non-mass field to be exactly equal.
8. All 10 `ordered_reason_transactions` records, including `physical_source_sink_resolved is False` and the zero-mass assertion for reasons 0, 1, 7.
9. All 21 step scalars and 10 step counters.
10. All 11 summary counts and 10 summary mass fields.

Tolerance models (deliberately different from the native bound, so the two implementations do not share a rounding assumption):

| Function | Formula |
|---|---|
| `_mass_tolerance` (shadow, `:202-209`) | `max(1e-3, 64*ulp(scale), 256*eps*(1 + Σ\|terms\|))` |
| `_operation_mass_tolerance` (shadow, `:225-259`) | `max(1e-3, 64*ulp(scale), epsilon_factor*eps*max(1,count)*(1 + Σ\|terms\|))`, `epsilon_factor` default `8.0` |
| `_bound` (accounting, `:239-246`) | `max(1e-3, 128*ulp(scale), 512*eps*max(1,count)*(1 + Σ\|terms\|))` |
| Native `forward_error_bound` | `max(1e-3, 128*DBL_EPSILON*max(1,count)*(1 + \|Σ terms\|))` in `long double` |

Both validators special-case the dimensionless `*_closing_scalar_relative_residual` summary mirror with an absolute floor of `5.1e-18`, because the native JSON writes it as 17 *fixed fractional digits* (`src/magic_geo/crust_material_shadow_validation.py:1573-1586`, `src/magic_geo/crust_dry_rock_accounting_validation.py:1296-1311`).

### Running the validators

```bash
# Full geo validation report; both replays appear as tectonics-domain checks.
magic-geo validate-geo --world worlds/earthlike.mgeo --output reports/geo-validation.json
```

```python
from magic_geo.crust_dry_rock_accounting_validation import (
    validate_crust_dry_rock_accounting,
)
from magic_geo.crust_material_shadow_validation import (
    validate_crust_material_shadow,
)
from magic_geo.serialization import read_world

world = read_world("worlds/earthlike.mgeo")

shadow = validate_crust_material_shadow(world)
print(shadow["passed"], shadow["metrics"])
for failure in shadow["failures"]:
    print("shadow:", failure)

accounting = validate_crust_dry_rock_accounting(world)
print(accounting["passed"], accounting["metrics"])
for failure in accounting["failures"]:
    print("accounting:", failure)
```

Returned `metrics` keys:

| Validator | `metrics` |
|---|---|
| Shadow | `history_step_count`, `maximum_absolute_cell_closing_scalar_mass_residual_kg`, `maximum_source_to_transport_residual_kg`, `cumulative_unresolved_source_mass_kg`, `cumulative_unresolved_sink_mass_kg` |
| Accounting | `history_step_count`, `capacity_kg`, `cumulative_requested_source_mass_kg`, `cumulative_requested_sink_mass_kg`, `maximum_absolute_transport_replay_residual_kg` |

`validate_crust_material_shadow` is also called directly from the full-world validator (`src/magic_geo/cli/commands/validate.py:6063-6068`), where its failures are prefixed `crust material shadow:`.

### Native unit tests

| CTest name | Executable | Cases (`int main`) |
|---|---|---|
| `magic_geo_crust_reservoir` | `magic_geo_crust_reservoir_test` (`cpp/tests/crust_reservoir_test.cpp:377-389`) | `exact_mantle_exhaustion_is_closed`, `empty_surface_can_be_explicitly_reseeded`, `mantle_depletion_does_not_fan_out_returned_origins`, `insufficient_mantle_rejects_without_publishing`, `age_only_reason_mass_is_rejected`, `surface_owner_cap_rejects_without_publishing` |
| `magic_geo_crust_reservoir_integration` | `magic_geo_crust_reservoir_integration_test` (`cpp/tests/crust_reservoir_integration_test.cpp:193-202`) | `schema_flags_and_empty_slab_are_truthful`, `accounting_history_is_thread_exact`, `capacity_scales_with_surface_area` |

Python-side unit tests live at `tests/test_crust_material_shadow_validation.py` and `tests/test_crust_dry_rock_accounting_validation.py`.

### Layer-contract participation

The `crust_lithology` layer contract (phase 3) requires all four keys to be present and well typed: `crust_material_shadow_model` (`dict`), `crust_material_shadow_history` (`nonempty_list`), `crust_dry_rock_accounting_model` (`dict`), `crust_dry_rock_accounting_history` (`nonempty_list`) (`src/magic_geo/geo_layer_contracts.py:88-91`, inside the `crust_lithology` contract that starts at `:78`). The layer's `evidence_class` is `initial_age_graph_witness_state_sparse_overlap_membership_shadow_and_finite_counter_accounting_replay`, and — like every layer — it hardcodes `empirical_realism_proven: False`.

## Limitations and unresolved claims

Everything below is a claim the codebase explicitly keeps **false**, or a structural limitation visible in the source. None of it is a to-do list this page is entitled to soften.

**Authority.**

- `authoritative_for_cell_state = false` in both models. The authoritative crust state is `Cell::crust_thickness_km` and `Cell::crust_density`; the packet tables only mirror them and are checked against them.
- Neither model feeds back into cell state, elevation, isostasy, sediment, or any downstream stage. They are pure observers.

**Physical mass claims.**

- `physical_source_sink_resolved = false`. A positive rule delta is not creation of rock; a negative delta is not destruction. The shadow's own key for a positive delta is literally named `unresolved_rule_source`.
- `material_provenance_resolved = false`. Origin keys are labels attached at initialization (or the reason that minted them), not a traced material history.
- `solid_volume_resolved = false` and `phase_resolved = false`. There is no porosity, compaction, melt fraction, or mineralogy anywhere in either model. The `1e12` factor is a unit conversion, nothing more.
- `mass_weighted_age_resolved = false`. Packets carry no age; crust age moments live only in the transport ledger's extensive-delta objects.
- `global_crust_cycle_mass_conservation_resolved = false` in both models. Arithmetic closure of the three reservoirs is not a geophysical crust cycle.
- `sediment_coupled = false` (accounting model). Sediment mass and crust dry-rock mass are entirely separate accounting systems; the sediment interface explicitly keeps dry mass, porosity, compaction, and grain provenance unresolved.

**The mantle and slab reservoirs.**

- `upper_mantle_exchange_reservoir_resolved = false`. The pool has no spatial coordinates, no temperature, no viscosity, no depth. `mantle_spatial_transport_resolved = false`.
- `instantaneous_global_mantle_mixing_assumed = true`. Any cell can withdraw from any packet in the pool in the same step, with no distance or time cost. That is an assumption, and it is declared as one.
- `mantle_origin_packets_homogenized = false` — origin keys inside the pool stay distinct, which is a bookkeeping choice, not a claim that the modelled mantle is heterogeneous.
- `subducted_slab_reservoir_resolved = false` and `subducted_slab_phase_2_state = plate_resolved_empty_reservoir_no_transfer_mechanism_enabled`. The slab tables are always empty; no transfer can target reservoir 2. `subduction_polarity_resolved = false`, so there is not even a resolved subducting side to key such a transfer on.
- `coverage_membership_fate_resolved = false`. The overlap membership classes upstream expose candidate fates only; the accounting model does not consume or resolve them.

**The capacity envelope.**

- `capacity_geophysically_calibrated = false`. `76.0` km and `3.08` g/cm³ are the rule chain's own upper clamps, chosen so the surface reservoir can never overflow the envelope. They are not measured crustal or mantle properties.
- `capacity_semantics = finite_numerical_surface_state_envelope_not_an_estimate_of_upper_mantle_mass`. The initial exchange reserve is capacity minus initial surface mass — a slack term, not an inventory. `minimum_crust_dry_rock_closing_upper_mantle_mass_kg` is a numerical headroom indicator, not a mantle depletion measurement.

**Residuals and diagnostics.**

- `shadow_minus_raw_transport_residual_kg` is declared to be "a numerical geometry closure diagnostic not a physical source or sink". Reporting it as gained or lost mass is a category error.
- The per-cell scalar-mirror bound admits `prior_max_cell_residual * contributor_count` and `4 * geometry_relative_error * (1 + terms)`. Residuals therefore may accumulate across steps within those allowances; the model does not claim step-to-step exactness, only bounded forward error.
- `closing_scalar_mass_residual_kg` and its per-cell maximum are serialized at `max_digits10` **decimal places** in fixed notation, not general-format round trip. The dimensionless relative residual in the summary is quantized at roughly `1e-17`, which is exactly why both validators floor its tolerance at `5.1e-18`.

**Operational caps.**

- `operational_safety_limits_are_physical_flux_limits = false`. `1024` packets per surface owner, `1000000` live packets, and `1000000` transfers per step are memory-safety limits. Hitting one is a fail-closed abort, not a physical saturation. The header comment states they are "deliberately far above the measured 4,096-cell reference peaks".

**Time and calibration.**

- Neither model carries the shared nominal-time block that the other process ledgers carry; step identity is by `plate_motion_history_id` only. Elsewhere in the document, `nominal_time_calibrated` and `physical_time_resolved` are both `false`, so a "per step" mass change is not a rate.
- No calibration target in `configs/geo_validation_earth_empirical_targets.json` scores either model. Nothing here is compared to Earth.

**Scope and coupling.**

- Rule execution order is a *native implementation order*, not a claim about the physical sequencing of aging, rifting, subduction, collision, and bound enforcement within a maturation interval. Reordering the rules would change the shadow adjustments, and the model says so by exporting `ordered_reason_adjustments` rather than a single net.
- `plate_crossing_accretion_proxy`, `oceanic_convergence_subduction_proxy`, and the exchange transfers are named "proxy" in the source for the same reason: they are stand-ins, not mechanisms.
- Accelerator parity is not claimed anywhere near these models. The FP64 continuous-overlap shadow in `cpp/src/crust_overlap_shadow.cpp` discards its output; CPU geometry remains authoritative and complete parity stays false.

## See also

- [Crust Transport and Forward Overlap](crust-transport-and-overlap.md) — the exact spherical overlap CSR, raw arrangement diagnostics, and the `transported_density_weighted_crust_volume` that the shadow's raw residual is measured against
- [Tectonics and Plates](tectonics-and-plates.md) — the ordered crust-rule chain, `CrustProcessReason`, and the process-inventory attribution ledger
- [Plate Boundary Segment Ledger](plate-boundary-ledger.md) — the explicitly unknown physical subduction polarity referenced by `subduction_polarity_resolved`
- [Sediment, Routing and Stratigraphy](sediment-and-stratigraphy.md) — the separate, uncoupled sediment inventory (`sediment_coupled: false`)
- [Native Engine (C++ Core)](../08-native-engine.md) — translation-unit responsibilities and the engine invariant list
- [World Document Schema](../10-world-schema.md) — the full top-level key order and the 412-key summary object
- [Serialization and World Formats](../11-serialization.md) — `max_digits10` fixed-notation emission and retired-field rejection
- [Validation](../12-validation.md) — the `validate-geo` report shape, domains, and severity model
- [Geo Validation Suite](../13-geo-validation-suite.md) — scenario matrix, determinism fingerprints, and paired relations
- [Testing and Quality Gates](../18-testing.md) — the CTest registrations for `magic_geo_crust_reservoir` and its integration test
- [Glossary](../21-glossary.md) — packet, origin key, counter-model, proxy compensation
