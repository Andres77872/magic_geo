from __future__ import annotations

import math
import sys
from collections.abc import Mapping, Sequence
from typing import Any, NamedTuple

from .crust_process_validation import CRUST_PROCESS_REASON_ORDER


SHADOW_MODEL_TYPE = "persistent_sparse_surface_crust_mass_shadow_v1"
SHADOW_HISTORY_FORMAT = "persistent_sparse_surface_crust_mass_shadow_v1"
UNRESOLVED_ORIGIN_KIND_ID = 9
DENSITY_VOLUME_TO_MASS_KG = 1.0e12

ORIGIN_KIND_ORDER = (
    "oceanic",
    "continental",
    "transitional",
    "volcanic_arc",
    "craton",
    "orogen",
    "rift_basin",
    "sedimentary_basin",
    "accreted_terrane",
    "unresolved_rule_source",
)

PACKET_TABLE_KEYS = {
    "cell_offsets",
    "origin_kind_ids",
    "origin_plate_ids",
    "origin_reason_ids",
    "dry_rock_mass_kg",
}
ADJUSTMENT_TABLE_KEYS = PACKET_TABLE_KEYS | {"process_reason_ids"}
HISTORY_RECORD_KEYS = {
    "id",
    "plate_motion_history_id",
    "stage",
    "erosion_iteration",
    "cell_count",
    "opening_packets",
    "transported_packets",
    "unresolved_source_adjustments",
    "unresolved_sink_adjustments",
    "closing_packets",
    "global_opening_mass_kg",
    "global_transported_mass_kg",
    "global_unresolved_source_mass_kg",
    "global_unresolved_sink_mass_kg",
    "global_closing_mass_kg",
    "raw_transported_scalar_mass_kg",
    "shadow_minus_raw_transport_residual_kg",
    "source_to_transport_residual_kg",
    "closing_scalar_mass_kg",
    "closing_scalar_mass_residual_kg",
    "maximum_absolute_cell_closing_scalar_mass_residual_kg",
    "ordered_adjustment_reconciliation_residual_kg",
    "opening_packet_count",
    "transported_packet_count",
    "unresolved_source_adjustment_count",
    "unresolved_sink_adjustment_count",
    "closing_packet_count",
    "ordered_reason_adjustments",
}

MODEL_KEYS = {
    "model_type",
    "mode",
    "mass_unit",
    "dry_rock_mass_definition",
    "origin_kind_order",
    "packet_key_fields",
    "transport_advection_model",
    "transport_normalization_scope",
    "transport_remainder_rule",
    "packet_coalescing_model",
    "packet_sort_order",
    "ordered_rule_adjustment_model",
    "positive_adjustment_origin_kind",
    "negative_adjustment_allocation",
    "raw_transport_scalar_reference",
    "shadow_minus_raw_transport_residual_semantics",
    "authoritative_for_cell_state",
    "physical_source_sink_resolved",
    "material_provenance_resolved",
    "solid_volume_resolved",
    "phase_resolved",
    "mass_weighted_age_resolved",
    "upper_mantle_exchange_reservoir_resolved",
    "subducted_slab_reservoir_resolved",
    "global_crust_cycle_mass_conservation_resolved",
    "transport_provenance_shadow_resolved",
    "ordered_rule_mass_adjustments_exposed",
}

MODEL_LITERAL_VALUES: dict[str, Any] = {
    "model_type": SHADOW_MODEL_TYPE,
    "mode": "shadow",
    "mass_unit": "kg",
    "dry_rock_mass_definition": (
        "cell_area_km2_times_crust_thickness_km_times_"
        "crust_density_g_cm3_times_1e12"
    ),
    "origin_kind_order": list(ORIGIN_KIND_ORDER),
    "packet_key_fields": [
        "origin_kind_id",
        "origin_plate_id",
        "origin_reason_id",
    ],
    "transport_advection_model": (
        "source_normalized_overlap_with_final_edge_remainder_v1"
    ),
    "transport_normalization_scope": "per_source_sum_of_raw_overlap_areas",
    "transport_remainder_rule": (
        "final_destination_edge_receives_source_mass_roundoff_remainder"
    ),
    "packet_coalescing_model": "sorted_equal_key_sum_v1",
    "packet_sort_order": (
        "origin_kind_id_then_origin_plate_id_then_origin_reason_id"
    ),
    "ordered_rule_adjustment_model": (
        "ordered_positive_unresolved_source_proportional_negative_sink_v1"
    ),
    "positive_adjustment_origin_kind": "unresolved_rule_source",
    "negative_adjustment_allocation": (
        "proportional_across_transported_packets_with_remainder_to_largest_"
        "packet_lowest_key_tie_break"
    ),
    "raw_transport_scalar_reference": (
        "raw_overlap_density_weighted_crust_volume_times_1e12"
    ),
    "shadow_minus_raw_transport_residual_semantics": (
        "source_normalized_shadow_mass_minus_raw_overlap_scalar_mass_is_a_"
        "numerical_geometry_closure_diagnostic_not_a_physical_source_or_sink"
    ),
    "authoritative_for_cell_state": False,
    "physical_source_sink_resolved": False,
    "material_provenance_resolved": False,
    "solid_volume_resolved": False,
    "phase_resolved": False,
    "mass_weighted_age_resolved": False,
    "upper_mantle_exchange_reservoir_resolved": False,
    "subducted_slab_reservoir_resolved": False,
    "global_crust_cycle_mass_conservation_resolved": False,
    "transport_provenance_shadow_resolved": True,
    "ordered_rule_mass_adjustments_exposed": True,
}

SUMMARY_COUNT_FIELDS = {
    "crust_material_shadow_history_step_count",
    "total_crust_material_shadow_packet_count",
    "maximum_crust_material_shadow_packet_count_per_table",
    "total_crust_material_shadow_opening_packet_count",
    "total_crust_material_shadow_transported_packet_count",
    "total_crust_material_shadow_closing_packet_count",
    "maximum_crust_material_shadow_opening_packet_count_per_step",
    "maximum_crust_material_shadow_transported_packet_count_per_step",
    "maximum_crust_material_shadow_closing_packet_count_per_step",
    "total_crust_material_shadow_adjustment_count",
    "maximum_crust_material_shadow_adjustment_count_per_table",
    "total_crust_material_shadow_unresolved_source_adjustment_count",
    "total_crust_material_shadow_unresolved_sink_adjustment_count",
}
SUMMARY_SCALAR_FIELDS = {
    "cumulative_crust_material_shadow_unresolved_source_mass_kg",
    "cumulative_crust_material_shadow_unresolved_sink_mass_kg",
    "maximum_absolute_crust_material_shadow_transport_raw_residual_kg",
    "maximum_crust_material_shadow_closing_scalar_relative_residual",
    "maximum_absolute_crust_material_shadow_adjustment_reconciliation_residual_kg",
}


class PacketKey(NamedTuple):
    origin_kind_id: int
    origin_plate_id: int
    origin_reason_id: int


class Adjustment(NamedTuple):
    process_reason_id: int
    key: PacketKey
    dry_rock_mass_kg: float


def _finite_float(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{field} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def _integer(value: Any, field: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field} must be an integer")
    return value


def _mass_tolerance(*values: float, terms: Sequence[float] = ()) -> float:
    scale = max(1.0, *(abs(value) for value in values))
    operand_sum = math.fsum(abs(value) for value in terms)
    return max(
        1.0e-3,
        64.0 * math.ulp(scale),
        256.0 * sys.float_info.epsilon * (1.0 + operand_sum),
    )


def _mass_close(
    actual: float,
    expected: float,
    *,
    terms: Sequence[float] = (),
) -> bool:
    return abs(actual - expected) <= _mass_tolerance(
        actual,
        expected,
        terms=terms,
    )


def _operation_mass_tolerance(
    actual: float,
    expected: float,
    *,
    absolute_term_sum: float,
    operation_count: int,
    epsilon_factor: float = 8.0,
) -> float:
    """Bound a cross-language reduction from its operands and operation count."""

    if (
        not math.isfinite(actual)
        or not math.isfinite(expected)
        or not math.isfinite(absolute_term_sum)
        or absolute_term_sum < 0.0
        or operation_count < 0
        or not math.isfinite(epsilon_factor)
        or epsilon_factor <= 0.0
    ):
        raise ValueError("mass tolerance operands must be finite and nonnegative")
    scale = max(1.0, abs(actual), abs(expected), absolute_term_sum)
    try:
        tolerance = max(
            1.0e-3,
            64.0 * math.ulp(scale),
            epsilon_factor
            * sys.float_info.epsilon
            * max(1, operation_count)
            * (1.0 + absolute_term_sum),
        )
    except OverflowError as exc:
        raise ValueError("mass tolerance overflowed") from exc
    if not math.isfinite(tolerance):
        raise ValueError("mass tolerance overflowed")
    return tolerance


def _valid_packet_key(key: PacketKey, plate_count: int) -> bool:
    if not 0 <= key.origin_kind_id < len(ORIGIN_KIND_ORDER):
        return False
    if not 0 <= key.origin_plate_id < plate_count:
        return False
    if key.origin_kind_id == UNRESOLVED_ORIGIN_KIND_ID:
        return 0 <= key.origin_reason_id < len(CRUST_PROCESS_REASON_ORDER)
    return key.origin_reason_id == -1


def _canonical_snapshot(
    packets_by_cell: Sequence[Mapping[PacketKey, float]],
) -> dict[str, list[int] | list[float]]:
    offsets = [0]
    kinds: list[int] = []
    plates: list[int] = []
    reasons: list[int] = []
    masses: list[float] = []
    for packets in packets_by_cell:
        for key in sorted(packets):
            mass = float(packets[key])
            if not math.isfinite(mass) or mass <= 0.0:
                raise ValueError("packet masses must be finite and positive")
            kinds.append(key.origin_kind_id)
            plates.append(key.origin_plate_id)
            reasons.append(key.origin_reason_id)
            masses.append(mass)
        offsets.append(len(masses))
    return {
        "cell_offsets": offsets,
        "origin_kind_ids": kinds,
        "origin_plate_ids": plates,
        "origin_reason_ids": reasons,
        "dry_rock_mass_kg": masses,
    }


def _canonical_adjustments(
    adjustments_by_cell: Sequence[Sequence[Adjustment]],
) -> dict[str, list[int] | list[float]]:
    offsets = [0]
    kinds: list[int] = []
    plates: list[int] = []
    origin_reasons: list[int] = []
    process_reasons: list[int] = []
    masses: list[float] = []
    for records in adjustments_by_cell:
        ordered = sorted(records, key=lambda item: (item.process_reason_id, item.key))
        for record in ordered:
            if not math.isfinite(record.dry_rock_mass_kg) or record.dry_rock_mass_kg <= 0.0:
                raise ValueError("adjustment masses must be finite and positive")
            kinds.append(record.key.origin_kind_id)
            plates.append(record.key.origin_plate_id)
            origin_reasons.append(record.key.origin_reason_id)
            process_reasons.append(record.process_reason_id)
            masses.append(record.dry_rock_mass_kg)
        offsets.append(len(masses))
    return {
        "cell_offsets": offsets,
        "origin_kind_ids": kinds,
        "origin_plate_ids": plates,
        "origin_reason_ids": origin_reasons,
        "process_reason_ids": process_reasons,
        "dry_rock_mass_kg": masses,
    }


def _snapshot_cells(
    payload: Any,
    *,
    cell_count: int,
    plate_count: int,
    field: str,
) -> list[dict[PacketKey, float]]:
    if not isinstance(payload, dict) or set(payload) != PACKET_TABLE_KEYS:
        raise TypeError(f"{field} has an invalid schema")
    offsets = payload["cell_offsets"]
    kinds = payload["origin_kind_ids"]
    plates = payload["origin_plate_ids"]
    reasons = payload["origin_reason_ids"]
    masses = payload["dry_rock_mass_kg"]
    if not all(isinstance(values, list) for values in (offsets, kinds, plates, reasons, masses)):
        raise TypeError(f"{field} arrays must be lists")
    offsets = [_integer(value, f"{field}.cell_offsets") for value in offsets]
    kinds = [_integer(value, f"{field}.origin_kind_ids") for value in kinds]
    plates = [_integer(value, f"{field}.origin_plate_ids") for value in plates]
    reasons = [_integer(value, f"{field}.origin_reason_ids") for value in reasons]
    masses = [_finite_float(value, f"{field}.dry_rock_mass_kg") for value in masses]
    if (
        len(offsets) != cell_count + 1
        or offsets[0] != 0
        or any(left > right for left, right in zip(offsets, offsets[1:]))
        or offsets[-1] != len(masses)
        or not (len(kinds) == len(plates) == len(reasons) == len(masses))
    ):
        raise ValueError(f"{field} has an invalid sparse shape")
    result: list[dict[PacketKey, float]] = []
    for cell in range(cell_count):
        packets: dict[PacketKey, float] = {}
        previous_key: PacketKey | None = None
        for index in range(offsets[cell], offsets[cell + 1]):
            key = PacketKey(kinds[index], plates[index], reasons[index])
            if (
                not _valid_packet_key(key, plate_count)
                or masses[index] <= 0.0
                or (previous_key is not None and key <= previous_key)
            ):
                raise ValueError(f"{field} packet keys or masses are not canonical")
            packets[key] = masses[index]
            previous_key = key
        result.append(packets)
    return result


def _adjustment_cells(
    payload: Any,
    *,
    cell_count: int,
    plate_count: int,
    field: str,
    source: bool,
) -> list[list[Adjustment]]:
    if not isinstance(payload, dict) or set(payload) != ADJUSTMENT_TABLE_KEYS:
        raise TypeError(f"{field} has an invalid schema")
    packet_payload = {key: payload[key] for key in PACKET_TABLE_KEYS}
    # Parse the common columns without imposing unique packet keys: the same
    # provenance key may legitimately be adjusted by multiple ordered rules.
    offsets = packet_payload["cell_offsets"]
    kinds = packet_payload["origin_kind_ids"]
    plates = packet_payload["origin_plate_ids"]
    origin_reasons = packet_payload["origin_reason_ids"]
    process_reasons = payload["process_reason_ids"]
    masses = packet_payload["dry_rock_mass_kg"]
    if not all(
        isinstance(values, list)
        for values in (offsets, kinds, plates, origin_reasons, process_reasons, masses)
    ):
        raise TypeError(f"{field} arrays must be lists")
    offsets = [_integer(value, f"{field}.cell_offsets") for value in offsets]
    kinds = [_integer(value, f"{field}.origin_kind_ids") for value in kinds]
    plates = [_integer(value, f"{field}.origin_plate_ids") for value in plates]
    origin_reasons = [
        _integer(value, f"{field}.origin_reason_ids") for value in origin_reasons
    ]
    process_reasons = [
        _integer(value, f"{field}.process_reason_ids") for value in process_reasons
    ]
    masses = [_finite_float(value, f"{field}.dry_rock_mass_kg") for value in masses]
    if (
        len(offsets) != cell_count + 1
        or offsets[0] != 0
        or any(left > right for left, right in zip(offsets, offsets[1:]))
        or offsets[-1] != len(masses)
        or not (
            len(kinds)
            == len(plates)
            == len(origin_reasons)
            == len(process_reasons)
            == len(masses)
        )
    ):
        raise ValueError(f"{field} has an invalid sparse shape")
    result: list[list[Adjustment]] = []
    for cell in range(cell_count):
        records: list[Adjustment] = []
        previous_order: tuple[int, PacketKey] | None = None
        for index in range(offsets[cell], offsets[cell + 1]):
            reason = process_reasons[index]
            key = PacketKey(kinds[index], plates[index], origin_reasons[index])
            order = (reason, key)
            if (
                not 0 <= reason < len(CRUST_PROCESS_REASON_ORDER)
                or not _valid_packet_key(key, plate_count)
                or masses[index] <= 0.0
                or (source and (
                    key.origin_kind_id != UNRESOLVED_ORIGIN_KIND_ID
                    or key.origin_reason_id != reason
                ))
                or (previous_order is not None and order <= previous_order)
            ):
                raise ValueError(f"{field} adjustment keys or masses are not canonical")
            records.append(Adjustment(reason, key, masses[index]))
            previous_order = order
        result.append(records)
    return result


def _copy_packets(
    packets_by_cell: Sequence[Mapping[PacketKey, float]],
) -> list[dict[PacketKey, float]]:
    return [dict(packets) for packets in packets_by_cell]


def initial_crust_material_shadow_packets(
    *,
    areas_km2: Sequence[float],
    crust_thickness_km: Sequence[float],
    crust_density_g_cm3: Sequence[float],
    crust_type_ids: Sequence[int],
    plate_ids: Sequence[int],
) -> list[dict[PacketKey, float]]:
    lengths = {
        len(areas_km2),
        len(crust_thickness_km),
        len(crust_density_g_cm3),
        len(crust_type_ids),
        len(plate_ids),
    }
    if len(lengths) != 1 or not areas_km2:
        raise ValueError("initial shadow packet input lengths differ or are empty")
    result: list[dict[PacketKey, float]] = []
    for index, (area, thickness, density, crust_type, plate_id) in enumerate(
        zip(
            areas_km2,
            crust_thickness_km,
            crust_density_g_cm3,
            crust_type_ids,
            plate_ids,
            strict=True,
        )
    ):
        area_value = _finite_float(area, f"areas_km2[{index}]")
        thickness_value = _finite_float(thickness, f"crust_thickness_km[{index}]")
        density_value = _finite_float(density, f"crust_density_g_cm3[{index}]")
        crust_type_value = _integer(crust_type, f"crust_type_ids[{index}]")
        plate_value = _integer(plate_id, f"plate_ids[{index}]")
        if (
            area_value <= 0.0
            or thickness_value <= 0.0
            or density_value <= 0.0
            or not 0 <= crust_type_value < UNRESOLVED_ORIGIN_KIND_ID
            or plate_value < 0
        ):
            raise ValueError("initial shadow packet state is invalid")
        mass = (
            area_value
            * thickness_value
            * density_value
            * DENSITY_VOLUME_TO_MASS_KG
        )
        result.append(
            {PacketKey(crust_type_value, plate_value, -1): mass}
        )
    return result


def replay_crust_material_shadow_step(
    *,
    opening_packets: Sequence[Mapping[PacketKey, float]],
    destination_offsets: Sequence[int],
    source_cell_ids: Sequence[int],
    overlap_area_km2: Sequence[float],
    current_plate_ids: Sequence[int],
    ordered_reason_mass_delta_kg_by_cell: Sequence[Sequence[float]],
) -> dict[str, Any]:
    """Independently replay one normalized shadow-packet transition.

    Raw overlap areas determine relative destination weights for each source.
    The final destination edge receives the subtraction remainder, so every
    source packet is transported exactly once in floating-point arithmetic.
    Ordered rule deltas then add explicit unresolved-origin packets or remove
    existing packets proportionally.  None of these adjustments is a physical
    source, sink, phase transformation, mantle exchange, or slab transfer.
    """

    cell_count = len(opening_packets)
    if cell_count == 0 or len(current_plate_ids) != cell_count:
        raise ValueError("shadow replay requires equal nonempty cell arrays")
    offsets = [_integer(value, "destination_offsets") for value in destination_offsets]
    sources = [_integer(value, "source_cell_ids") for value in source_cell_ids]
    overlaps = [_finite_float(value, "overlap_area_km2") for value in overlap_area_km2]
    plates = [_integer(value, "current_plate_ids") for value in current_plate_ids]
    if (
        len(offsets) != cell_count + 1
        or offsets[0] != 0
        or offsets[-1] != len(sources)
        or any(left > right for left, right in zip(offsets, offsets[1:]))
        or len(sources) != len(overlaps)
        or any(not 0 <= source < cell_count for source in sources)
        or any(area <= 0.0 for area in overlaps)
        or any(plate < 0 for plate in plates)
    ):
        raise ValueError("shadow replay overlap CSR is invalid")
    for destination in range(cell_count):
        row = sources[offsets[destination] : offsets[destination + 1]]
        if row != sorted(set(row)):
            raise ValueError("shadow replay overlap CSR is not canonical")
    if len(ordered_reason_mass_delta_kg_by_cell) != len(CRUST_PROCESS_REASON_ORDER):
        raise ValueError("shadow replay requires one mass-delta row per reason")
    reason_deltas = [
        [_finite_float(value, "ordered_reason_mass_delta_kg_by_cell") for value in row]
        for row in ordered_reason_mass_delta_kg_by_cell
    ]
    if any(len(row) != cell_count for row in reason_deltas):
        raise ValueError("shadow replay reason-delta rows have invalid length")

    opening = _copy_packets(opening_packets)
    for packets in opening:
        for key, mass in packets.items():
            if not isinstance(key, PacketKey) or mass <= 0.0 or not math.isfinite(mass):
                raise ValueError("opening shadow packets are invalid")

    source_edges: list[list[tuple[int, float]]] = [[] for _ in range(cell_count)]
    for destination in range(cell_count):
        for edge_index in range(offsets[destination], offsets[destination + 1]):
            source_edges[sources[edge_index]].append(
                (destination, overlaps[edge_index])
            )
    if any(not edges for edges in source_edges):
        raise ValueError("every shadow source must have a transport edge")

    destination_terms: list[dict[PacketKey, list[float]]] = [
        {} for _ in range(cell_count)
    ]
    for source in range(cell_count):
        edges = source_edges[source]
        denominator = 0.0
        for _, area in edges:
            denominator += area
        if not math.isfinite(denominator) or denominator <= 0.0:
            raise ValueError("shadow source overlap area is invalid")
        for key in sorted(opening[source]):
            mass = opening[source][key]
            allocated_mass = 0.0
            for destination, area in edges[:-1]:
                contribution = mass * (area / denominator)
                if not math.isfinite(contribution) or contribution <= 0.0:
                    raise ValueError("shadow packet transport underflowed or overflowed")
                allocated_mass += contribution
                destination_terms[destination].setdefault(key, []).append(
                    contribution
                )
            final_destination = edges[-1][0]
            remainder = mass - allocated_mass
            if not math.isfinite(remainder) or remainder <= 0.0:
                raise ValueError("shadow packet final-edge remainder is invalid")
            destination_terms[final_destination].setdefault(key, []).append(
                remainder
            )
    transported: list[dict[PacketKey, float]] = []
    for terms_by_key in destination_terms:
        cell_packets: dict[PacketKey, float] = {}
        for key, terms in sorted(terms_by_key.items()):
            total = 0.0
            for term in terms:
                total += term
            cell_packets[key] = total
        transported.append(cell_packets)

    closing = _copy_packets(transported)
    source_adjustments: list[list[Adjustment]] = [
        [] for _ in range(cell_count)
    ]
    sink_adjustments: list[list[Adjustment]] = [
        [] for _ in range(cell_count)
    ]
    source_by_reason = [0.0] * len(CRUST_PROCESS_REASON_ORDER)
    sink_by_reason = [0.0] * len(CRUST_PROCESS_REASON_ORDER)
    for reason_id, deltas in enumerate(reason_deltas):
        for cell, delta in enumerate(deltas):
            if delta > 0.0:
                key = PacketKey(
                    UNRESOLVED_ORIGIN_KIND_ID,
                    plates[cell],
                    reason_id,
                )
                closing[cell][key] = closing[cell].get(key, 0.0) + delta
                source_adjustments[cell].append(
                    Adjustment(reason_id, key, delta)
                )
                source_by_reason[reason_id] += delta
            elif delta < 0.0:
                sink_mass = -delta
                if not closing[cell]:
                    raise ValueError("shadow sink cannot draw from an empty cell")
                keys = sorted(closing[cell])
                total = math.fsum(closing[cell][key] for key in keys)
                if sink_mass > total + _mass_tolerance(sink_mass, total):
                    raise ValueError("shadow sink exceeds available packet mass")
                sink_mass = min(sink_mass, total)
                correction_key = min(
                    keys,
                    key=lambda key: (-closing[cell][key], key),
                )
                allocated: dict[PacketKey, float] = {}
                provisional_total = 0.0
                for key in keys:
                    removal = sink_mass * closing[cell][key] / total
                    if removal < 0.0 or removal > closing[cell][key]:
                        raise ValueError("shadow proportional sink is invalid")
                    if removal > 0.0:
                        allocated[key] = removal
                    provisional_total += removal
                allocated[correction_key] = (
                    allocated.get(correction_key, 0.0)
                    + sink_mass
                    - provisional_total
                )
                correction = allocated[correction_key]
                if correction < 0.0 or correction > closing[cell][correction_key]:
                    raise ValueError("shadow sink remainder is invalid")
                for key in keys:
                    removal = allocated.get(key, 0.0)
                    if removal > 0.0:
                        remaining = closing[cell][key] - removal
                        sink_adjustments[cell].append(
                            Adjustment(reason_id, key, removal)
                        )
                        if remaining > 0.0:
                            closing[cell][key] = remaining
                        else:
                            del closing[cell][key]
                sink_by_reason[reason_id] += sink_mass

    opening_total = math.fsum(
        mass for packets in opening for mass in packets.values()
    )
    transported_total = math.fsum(
        mass for packets in transported for mass in packets.values()
    )
    source_total = math.fsum(source_by_reason)
    sink_total = math.fsum(sink_by_reason)
    closing_total = math.fsum(
        mass for packets in closing for mass in packets.values()
    )
    return {
        "opening_packets": _canonical_snapshot(opening),
        "transported_packets": _canonical_snapshot(transported),
        "unresolved_source_adjustments": _canonical_adjustments(
            source_adjustments
        ),
        "unresolved_sink_adjustments": _canonical_adjustments(sink_adjustments),
        "closing_packets": _canonical_snapshot(closing),
        "global_opening_mass_kg": opening_total,
        "global_transported_mass_kg": transported_total,
        "global_unresolved_source_mass_kg": source_total,
        "global_unresolved_sink_mass_kg": sink_total,
        "global_closing_mass_kg": closing_total,
        "source_to_transport_residual_kg": transported_total - opening_total,
        "ordered_adjustment_reconciliation_residual_kg": (
            closing_total - transported_total - source_total + sink_total
        ),
        "opening_packet_count": len(
            _canonical_snapshot(opening)["dry_rock_mass_kg"]
        ),
        "transported_packet_count": len(
            _canonical_snapshot(transported)["dry_rock_mass_kg"]
        ),
        "unresolved_source_adjustment_count": len(
            _canonical_adjustments(source_adjustments)["dry_rock_mass_kg"]
        ),
        "unresolved_sink_adjustment_count": len(
            _canonical_adjustments(sink_adjustments)["dry_rock_mass_kg"]
        ),
        "closing_packet_count": len(
            _canonical_snapshot(closing)["dry_rock_mass_kg"]
        ),
        "ordered_reason_adjustments": [
            {
                "process_reason_id": reason_id,
                "process_reason": CRUST_PROCESS_REASON_ORDER[reason_id],
                "source_mass_kg": source_by_reason[reason_id],
                "sink_mass_kg": sink_by_reason[reason_id],
            }
            for reason_id in range(len(CRUST_PROCESS_REASON_ORDER))
        ],
    }


def _packet_maps_close(
    actual: Sequence[Mapping[PacketKey, float]],
    expected: Sequence[Mapping[PacketKey, float]],
) -> bool:
    if len(actual) != len(expected):
        return False
    for actual_cell, expected_cell in zip(actual, expected, strict=True):
        if set(actual_cell) != set(expected_cell):
            return False
        if any(
            not _mass_close(
                actual_cell[key],
                expected_cell[key],
                terms=(actual_cell[key], expected_cell[key]),
            )
            for key in actual_cell
        ):
            return False
    return True


def _adjustments_close(
    actual: Sequence[Sequence[Adjustment]],
    expected: Sequence[Sequence[Adjustment]],
) -> bool:
    if len(actual) != len(expected):
        return False
    for actual_cell, expected_cell in zip(actual, expected, strict=True):
        if len(actual_cell) != len(expected_cell):
            return False
        for actual_record, expected_record in zip(
            actual_cell, expected_cell, strict=True
        ):
            if (
                actual_record.process_reason_id != expected_record.process_reason_id
                or actual_record.key != expected_record.key
                or not _mass_close(
                    actual_record.dry_rock_mass_kg,
                    expected_record.dry_rock_mass_kg,
                    terms=(
                        actual_record.dry_rock_mass_kg,
                        expected_record.dry_rock_mass_kg,
                    ),
                )
            ):
                return False
    return True


def validate_crust_material_shadow(world: dict[str, Any]) -> dict[str, Any]:
    """Strictly replay the serialized Phase-S surface-crust shadow ledger."""

    failures: list[str] = []
    model = world.get("crust_material_shadow_model")
    history = world.get("crust_material_shadow_history")
    plate_history = world.get("plate_motion_history")
    cells = world.get("cells")
    if (
        not isinstance(model, dict)
        or not isinstance(history, list)
        or not isinstance(plate_history, list)
        or not isinstance(cells, list)
        or not history
        or len(history) != len(plate_history)
        or not cells
    ):
        return {
            "passed": False,
            "failures": ["crust material shadow model or aligned histories are missing"],
            "metrics": {},
        }
    if set(model) != MODEL_KEYS or any(
        model.get(field) != expected
        for field, expected in MODEL_LITERAL_VALUES.items()
    ):
        failures.append("crust material shadow model metadata is invalid")

    cell_count = len(cells)
    try:
        areas = [_finite_float(cell["area_km2"], "cells.area_km2") for cell in cells]
        if any(area <= 0.0 for area in areas):
            raise ValueError
        plate_count = max(
            len(step.get("plates", []))
            for step in plate_history
            if isinstance(step, dict)
        )
        if plate_count <= 0:
            raise ValueError
    except (KeyError, TypeError, ValueError, OverflowError):
        return {
            "passed": False,
            "failures": failures + ["crust material shadow geometry is invalid"],
            "metrics": {},
        }

    previous_closing: list[dict[PacketKey, float]] | None = None
    maximum_cell_scalar_residual = 0.0
    maximum_transport_replay_residual = 0.0
    total_source_mass = 0.0
    total_sink_mass = 0.0
    previous_step_maximum_cell_scalar_residual = 0.0
    for step_index, (record, plate_step) in enumerate(
        zip(history, plate_history, strict=True)
    ):
        if (
            not isinstance(record, dict)
            or set(record) != HISTORY_RECORD_KEYS
            or not isinstance(plate_step, dict)
        ):
            failures.append(f"crust material shadow history {step_index} schema is invalid")
            break
        try:
            if (
                _integer(record["id"], "history.id") != step_index
                or _integer(record["plate_motion_history_id"], "history.plate_motion_history_id")
                != _integer(plate_step["id"], "plate step id")
                or record["stage"] != plate_step["stage"]
                or _integer(record["erosion_iteration"], "history.erosion_iteration")
                != _integer(plate_step["erosion_iteration"], "plate erosion iteration")
                or _integer(record["cell_count"], "history.cell_count") != cell_count
            ):
                raise ValueError
            opening = _snapshot_cells(
                record["opening_packets"],
                cell_count=cell_count,
                plate_count=plate_count,
                field="opening_packets",
            )
            transported = _snapshot_cells(
                record["transported_packets"],
                cell_count=cell_count,
                plate_count=plate_count,
                field="transported_packets",
            )
            sources = _adjustment_cells(
                record["unresolved_source_adjustments"],
                cell_count=cell_count,
                plate_count=plate_count,
                field="unresolved_source_adjustments",
                source=True,
            )
            sinks = _adjustment_cells(
                record["unresolved_sink_adjustments"],
                cell_count=cell_count,
                plate_count=plate_count,
                field="unresolved_sink_adjustments",
                source=False,
            )
            closing = _snapshot_cells(
                record["closing_packets"],
                cell_count=cell_count,
                plate_count=plate_count,
                field="closing_packets",
            )
            overlap = plate_step["crust_overlap_ledger"]
            offsets = overlap["destination_offsets"]
            source_ids = overlap["source_cell_ids"]
            overlap_areas = overlap["overlap_area_km2"]
            contributor_counts = [
                _integer(value, "contributor_count_by_cell")
                for value in overlap["contributor_count_by_cell"]
            ]
            current_plate_ids = plate_step["cell_plate_ids"]
            reason_records = overlap["process_inventory_attribution"]["reasons"]
            remapped_thickness = overlap["remapped_crust_thickness_km_by_cell"]
            remapped_density = overlap["remapped_crust_density_by_cell"]
            process_thickness = plate_step["crust_thickness_process_change_km_by_cell"]
            process_density = plate_step["crust_density_process_change_by_cell"]
            if any(
                len(values) != cell_count
                for values in (
                    current_plate_ids,
                    remapped_thickness,
                    remapped_density,
                    process_thickness,
                    process_density,
                    contributor_counts,
                )
            ) or any(
                not 0 <= count <= cell_count for count in contributor_counts
            ):
                raise ValueError
            serialized_reason_adjustments = record["ordered_reason_adjustments"]
            if (
                not isinstance(serialized_reason_adjustments, list)
                or len(serialized_reason_adjustments)
                != len(CRUST_PROCESS_REASON_ORDER)
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError, OverflowError):
            failures.append(f"crust material shadow history {step_index} fields are invalid")
            break

        if step_index == 0:
            try:
                initial_types = [
                    _integer(value, "initial crust type")
                    for value in plate_step["crust_type_by_cell"]
                ]
                initial_plates = [
                    _integer(value, "initial plate")
                    for value in plate_step["cell_plate_ids"]
                ]
                expected_initial = initial_crust_material_shadow_packets(
                    areas_km2=areas,
                    crust_thickness_km=remapped_thickness,
                    crust_density_g_cm3=remapped_density,
                    crust_type_ids=initial_types,
                    plate_ids=initial_plates,
                )
            except (KeyError, TypeError, ValueError, OverflowError):
                failures.append("initial crust material shadow state is invalid")
                break
            if not _packet_maps_close(opening, expected_initial):
                failures.append("initial crust material shadow packets do not replay")
                break
        elif previous_closing is None or not _packet_maps_close(opening, previous_closing):
            failures.append(f"crust material shadow opening link failed at step {step_index}")
            break

        zero_deltas = [
            [0.0] * cell_count for _ in CRUST_PROCESS_REASON_ORDER
        ]
        try:
            transport_replay = replay_crust_material_shadow_step(
                opening_packets=opening,
                destination_offsets=offsets,
                source_cell_ids=source_ids,
                overlap_area_km2=overlap_areas,
                current_plate_ids=current_plate_ids,
                ordered_reason_mass_delta_kg_by_cell=zero_deltas,
            )
            expected_transported = _snapshot_cells(
                transport_replay["transported_packets"],
                cell_count=cell_count,
                plate_count=plate_count,
                field="replayed transported packets",
            )
        except (TypeError, ValueError, OverflowError):
            failures.append(f"crust material shadow transport replay failed at step {step_index}")
            break
        if not _packet_maps_close(transported, expected_transported):
            failures.append(f"crust material shadow transported packets differ at step {step_index}")
            break

        # Reconstruct the raw source-row closure instead of trusting the
        # serialized maximum.  It is both a shadow-advection prerequisite and
        # an operand in the native scalar-mirror forward-error bound.
        source_overlap_area_terms: list[list[float]] = [
            [] for _ in range(cell_count)
        ]
        try:
            replay_source_ids = [
                _integer(value, "source_cell_ids") for value in source_ids
            ]
            replay_overlap_areas = [
                _finite_float(value, "overlap_area_km2")
                for value in overlap_areas
            ]
            for source_id, overlap_area in zip(
                replay_source_ids, replay_overlap_areas, strict=True
            ):
                source_overlap_area_terms[source_id].append(overlap_area)
        except (IndexError, TypeError, ValueError, OverflowError):
            failures.append(
                f"crust material shadow source-area operands failed at step {step_index}"
            )
            break
        source_geometry_relative_error = 0.0
        source_geometry_valid = True
        for source_id, (terms, source_area) in enumerate(
            zip(source_overlap_area_terms, areas, strict=True)
        ):
            reconstructed_source_area = math.fsum(terms)
            closure_error = abs(reconstructed_source_area - source_area)
            source_geometry_relative_error = max(
                source_geometry_relative_error,
                closure_error / source_area,
            )
            if closure_error > max(1.0e-6, source_area * 2.0e-10):
                failures.append(
                    "crust material shadow source-area closure failed at "
                    f"step {step_index}, source {source_id}: "
                    f"replayed_area_km2={reconstructed_source_area:.17g}, "
                    f"source_area_km2={source_area:.17g}, "
                    f"residual_km2={closure_error:.17g}"
                )
                source_geometry_valid = False
                break
        if not source_geometry_valid:
            break

        # Reconstruct the ordered rule application from its explicit source and
        # sink records.  Existing process validation independently proves the
        # native rule chain; this validator proves its packet consequences.
        current = _copy_packets(transported)
        expected_sources: list[list[Adjustment]] = [[] for _ in range(cell_count)]
        expected_sinks: list[list[Adjustment]] = [[] for _ in range(cell_count)]
        source_by_reason = [0.0] * len(CRUST_PROCESS_REASON_ORDER)
        sink_by_reason = [0.0] * len(CRUST_PROCESS_REASON_ORDER)
        adjustment_absolute_mass_operands_by_reason = [
            0.0
        ] * len(CRUST_PROCESS_REASON_ORDER)
        adjustment_operation_counts_by_reason = [
            0
        ] * len(CRUST_PROCESS_REASON_ORDER)
        valid_adjustments = True
        for reason_id in range(len(CRUST_PROCESS_REASON_ORDER)):
            for cell in range(cell_count):
                source_records = [
                    item for item in sources[cell] if item.process_reason_id == reason_id
                ]
                sink_records = [
                    item for item in sinks[cell] if item.process_reason_id == reason_id
                ]
                if source_records and sink_records:
                    valid_adjustments = False
                    break
                if source_records:
                    if len(source_records) != 1:
                        valid_adjustments = False
                        break
                    item = source_records[0]
                    expected_key = PacketKey(
                        UNRESOLVED_ORIGIN_KIND_ID,
                        _integer(current_plate_ids[cell], "current plate"),
                        reason_id,
                    )
                    if item.key != expected_key:
                        valid_adjustments = False
                        break
                    before_cell_mass = math.fsum(current[cell].values())
                    after_cell_mass = before_cell_mass + item.dry_rock_mass_kg
                    adjustment_absolute_mass_operands_by_reason[reason_id] += (
                        abs(before_cell_mass)
                        + abs(after_cell_mass)
                        + abs(item.dry_rock_mass_kg)
                    )
                    # Two three-factor scalar products plus the mass
                    # conversion/subtraction and packet addition are the
                    # independent rounded path behind this adjustment.
                    adjustment_operation_counts_by_reason[reason_id] += 8
                    current[cell][item.key] = current[cell].get(item.key, 0.0) + item.dry_rock_mass_kg
                    expected_sources[cell].append(item)
                    source_by_reason[reason_id] += item.dry_rock_mass_kg
                elif sink_records:
                    if not current[cell]:
                        valid_adjustments = False
                        break
                    total = math.fsum(current[cell].values())
                    sink_total = math.fsum(item.dry_rock_mass_kg for item in sink_records)
                    if sink_total > total + _mass_tolerance(sink_total, total):
                        valid_adjustments = False
                        break
                    adjustment_absolute_mass_operands_by_reason[reason_id] += (
                        abs(total)
                        + abs(total - sink_total)
                        + abs(sink_total)
                    )
                    adjustment_operation_counts_by_reason[reason_id] += (
                        8 + len(sink_records)
                    )
                    keys = sorted(current[cell])
                    correction_key = min(keys, key=lambda key: (-current[cell][key], key))
                    expected_allocations: dict[PacketKey, float] = {}
                    provisional_total = 0.0
                    for key in keys:
                        removal = sink_total * current[cell][key] / total
                        if removal > 0.0:
                            expected_allocations[key] = removal
                        provisional_total += removal
                    expected_allocations[correction_key] = (
                        expected_allocations.get(correction_key, 0.0)
                        + sink_total
                        - provisional_total
                    )
                    actual_allocations = {
                        item.key: item.dry_rock_mass_kg for item in sink_records
                    }
                    if set(actual_allocations) != set(expected_allocations) or any(
                        not _mass_close(
                            actual_allocations[key],
                            expected_allocations[key],
                            terms=(sink_total, current[cell][key], total),
                        )
                        for key in actual_allocations
                    ):
                        valid_adjustments = False
                        break
                    for key, removal in actual_allocations.items():
                        remaining = current[cell][key] - removal
                        if remaining > 0.0:
                            current[cell][key] = remaining
                        else:
                            del current[cell][key]
                    expected_sinks[cell].extend(sink_records)
                    sink_by_reason[reason_id] += sink_total
            if not valid_adjustments:
                break
        if (
            not valid_adjustments
            or not _adjustments_close(sources, expected_sources)
            or not _adjustments_close(sinks, expected_sinks)
            or not _packet_maps_close(closing, current)
        ):
            failures.append(f"crust material shadow ordered adjustments failed at step {step_index}")
            break

        cell_scalar_masses: list[float] = []
        cell_residuals: list[float] = []
        for cell in range(cell_count):
            final_thickness = _finite_float(remapped_thickness[cell], "remapped thickness") + _finite_float(
                process_thickness[cell], "process thickness"
            )
            final_density = _finite_float(remapped_density[cell], "remapped density") + _finite_float(
                process_density[cell], "process density"
            )
            scalar_mass = (
                areas[cell]
                * final_thickness
                * final_density
                * DENSITY_VOLUME_TO_MASS_KG
            )
            packet_mass = math.fsum(closing[cell].values())
            if not math.isfinite(scalar_mass) or not math.isfinite(packet_mass):
                failures.append(
                    "crust material shadow final scalar is nonfinite at "
                    f"step {step_index}, cell {cell}"
                )
                break
            cell_scalar_masses.append(scalar_mass)
            cell_residuals.append(packet_mass - scalar_mass)
            transported_cell_mass = math.fsum(transported[cell].values())
            source_cell_mass = math.fsum(
                item.dry_rock_mass_kg for item in sources[cell]
            )
            sink_cell_mass = math.fsum(
                item.dry_rock_mass_kg for item in sinks[cell]
            )
            local_absolute_mass_terms = math.fsum(
                abs(value)
                for value in (
                    packet_mass,
                    scalar_mass,
                    transported_cell_mass,
                    source_cell_mass,
                    sink_cell_mass,
                )
            )
            local_operation_count = (
                len(closing[cell])
                + len(transported[cell])
                + len(sources[cell])
                + len(sinks[cell])
                + 6
            )
            try:
                tolerance = (
                    previous_step_maximum_cell_scalar_residual
                    * max(1, contributor_counts[cell])
                    + 4.0
                    * source_geometry_relative_error
                    * (1.0 + local_absolute_mass_terms)
                    + _operation_mass_tolerance(
                        packet_mass,
                        scalar_mass,
                        absolute_term_sum=local_absolute_mass_terms,
                        operation_count=local_operation_count,
                    )
                )
                if not math.isfinite(tolerance):
                    raise ValueError("composite mass tolerance overflowed")
            except (ValueError, OverflowError):
                failures.append(
                    "crust material shadow final scalar tolerance is invalid at "
                    f"step {step_index}, cell {cell}"
                )
                break
            if abs(packet_mass - scalar_mass) > tolerance:
                failures.append(
                    "crust material shadow final scalar failed at "
                    f"step {step_index}, cell {cell}: "
                    f"packet_mass_kg={packet_mass:.17g}, "
                    f"scalar_mass_kg={scalar_mass:.17g}, "
                    f"residual_kg={packet_mass - scalar_mass:.17g}, "
                    f"tolerance_kg={tolerance:.17g}, "
                    f"area_km2={areas[cell]:.17g}, "
                    f"final_thickness_km={final_thickness:.17g}, "
                    f"final_density_g_cm3={final_density:.17g}, "
                    f"prior_maximum_cell_residual_kg="
                    f"{previous_step_maximum_cell_scalar_residual:.17g}, "
                    f"contributor_count={contributor_counts[cell]}, "
                    f"source_geometry_relative_error="
                    f"{source_geometry_relative_error:.17g}, "
                    f"local_operation_count={local_operation_count}"
                )
                break
        if failures:
            break

        opening_total = math.fsum(mass for packets in opening for mass in packets.values())
        transported_total = math.fsum(mass for packets in transported for mass in packets.values())
        source_total = math.fsum(source_by_reason)
        sink_total = math.fsum(sink_by_reason)
        closing_total = math.fsum(mass for packets in closing for mass in packets.values())
        closing_scalar_total = math.fsum(cell_scalar_masses)
        raw_transport_mass = _finite_float(
            overlap["transported_inventory"]["density_weighted_crust_volume"],
            "raw transported density volume",
        ) * DENSITY_VOLUME_TO_MASS_KG
        expected_scalars = {
            "global_opening_mass_kg": opening_total,
            "global_transported_mass_kg": transported_total,
            "global_unresolved_source_mass_kg": source_total,
            "global_unresolved_sink_mass_kg": sink_total,
            "global_closing_mass_kg": closing_total,
            "raw_transported_scalar_mass_kg": raw_transport_mass,
            "shadow_minus_raw_transport_residual_kg": transported_total - raw_transport_mass,
            "source_to_transport_residual_kg": transported_total - opening_total,
            "closing_scalar_mass_kg": closing_scalar_total,
            "closing_scalar_mass_residual_kg": closing_total - closing_scalar_total,
            "maximum_absolute_cell_closing_scalar_mass_residual_kg": max(
                (abs(value) for value in cell_residuals), default=0.0
            ),
            "ordered_adjustment_reconciliation_residual_kg": (
                closing_total - transported_total - source_total + sink_total
            ),
        }
        for field, expected in expected_scalars.items():
            try:
                actual = _finite_float(record[field], field)
            except (TypeError, ValueError, OverflowError):
                failures.append(f"crust material shadow scalar {field} is invalid")
                break
            if not _mass_close(actual, expected, terms=tuple(expected_scalars.values())):
                failures.append(f"crust material shadow scalar {field} does not replay")
                break
        if failures:
            break
        expected_counts = {
            "opening_packet_count": sum(len(packets) for packets in opening),
            "transported_packet_count": sum(len(packets) for packets in transported),
            "unresolved_source_adjustment_count": sum(len(items) for items in sources),
            "unresolved_sink_adjustment_count": sum(len(items) for items in sinks),
            "closing_packet_count": sum(len(packets) for packets in closing),
        }
        if any(
            type(record[field]) is not int or record[field] != expected
            for field, expected in expected_counts.items()
        ):
            failures.append(f"crust material shadow packet counts failed at step {step_index}")
            break

        for reason_id, (serialized, process_record) in enumerate(
            zip(serialized_reason_adjustments, reason_records, strict=True)
        ):
            if not isinstance(serialized, dict) or set(serialized) != {
                "process_reason_id",
                "process_reason",
                "source_mass_kg",
                "sink_mass_kg",
            }:
                failures.append(f"crust material shadow reason record {reason_id} is invalid")
                break
            try:
                serialized_source = _finite_float(serialized["source_mass_kg"], "reason source")
                serialized_sink = _finite_float(serialized["sink_mass_kg"], "reason sink")
                process_mass_delta = _finite_float(
                    process_record["net_delta"]["density_weighted_crust_volume"],
                    "reason density-volume delta",
                ) * DENSITY_VOLUME_TO_MASS_KG
                if not math.isfinite(process_mass_delta):
                    raise ValueError
                changed_cell_count = _integer(
                    process_record.get(
                        "extensive_state_changed_cell_count",
                        max(
                            1,
                            adjustment_operation_counts_by_reason[reason_id]
                            // 8,
                        ),
                    ),
                    "reason extensive-state changed cell count",
                )
                if not 0 <= changed_cell_count <= cell_count:
                    raise ValueError
            except (KeyError, TypeError, ValueError, OverflowError):
                failures.append(f"crust material shadow reason record {reason_id} is invalid")
                break
            source_tolerance = _mass_tolerance(
                serialized_source,
                source_by_reason[reason_id],
                terms=(serialized_source, source_by_reason[reason_id]),
            )
            sink_tolerance = _mass_tolerance(
                serialized_sink,
                sink_by_reason[reason_id],
                terms=(serialized_sink, sink_by_reason[reason_id]),
            )
            delta_absolute_term_sum = math.fsum(
                (
                    abs(serialized_source),
                    abs(serialized_sink),
                    abs(process_mass_delta),
                    adjustment_absolute_mass_operands_by_reason[reason_id],
                )
            )
            try:
                delta_tolerance = (
                    previous_step_maximum_cell_scalar_residual
                    * max(1, changed_cell_count)
                    + _operation_mass_tolerance(
                        serialized_source - serialized_sink,
                        process_mass_delta,
                        absolute_term_sum=delta_absolute_term_sum,
                        operation_count=(
                            adjustment_operation_counts_by_reason[reason_id]
                            + changed_cell_count
                            + 3
                        ),
                        # The two evidence paths each form scalar products,
                        # round at different unit-conversion boundaries, and
                        # reduce in double versus long double. Eight epsilons
                        # per explicit operation is a modest cross-language
                        # safety factor over the standard operand-count model.
                        epsilon_factor=8.0,
                    )
                )
                if not math.isfinite(delta_tolerance):
                    raise ValueError("composite reason tolerance overflowed")
            except (ValueError, OverflowError):
                failures.append(
                    "crust material shadow reason tolerance is invalid at "
                    f"step {step_index}, reason {reason_id}"
                )
                break
            reason_failure = (
                type(serialized["process_reason_id"]) is not int
                or serialized["process_reason_id"] != reason_id
                or serialized["process_reason"] != CRUST_PROCESS_REASON_ORDER[reason_id]
                or serialized_source < 0.0
                or serialized_sink < 0.0
                or abs(serialized_source - source_by_reason[reason_id])
                > source_tolerance
                or abs(serialized_sink - sink_by_reason[reason_id])
                > sink_tolerance
                or abs(
                    (serialized_source - serialized_sink) - process_mass_delta
                )
                > delta_tolerance
            )
            if reason_failure:
                failures.append(
                    "crust material shadow reason totals failed at "
                    f"step {step_index}, reason {reason_id}: "
                    f"serialized_source_kg={serialized_source:.17g}, "
                    f"replayed_source_kg={source_by_reason[reason_id]:.17g}, "
                    f"source_tolerance_kg={source_tolerance:.17g}, "
                    f"serialized_sink_kg={serialized_sink:.17g}, "
                    f"replayed_sink_kg={sink_by_reason[reason_id]:.17g}, "
                    f"sink_tolerance_kg={sink_tolerance:.17g}, "
                    f"serialized_net_kg={serialized_source - serialized_sink:.17g}, "
                    f"process_net_kg={process_mass_delta:.17g}, "
                    f"net_tolerance_kg={delta_tolerance:.17g}, "
                    f"net_absolute_operand_sum_kg="
                    f"{delta_absolute_term_sum:.17g}, "
                    f"changed_cell_count={changed_cell_count}"
                )
                break
        if failures:
            break

        maximum_cell_scalar_residual = max(
            maximum_cell_scalar_residual,
            max((abs(value) for value in cell_residuals), default=0.0),
        )
        maximum_transport_replay_residual = max(
            maximum_transport_replay_residual,
            abs(transported_total - opening_total),
        )
        total_source_mass += source_total
        total_sink_mass += sink_total
        previous_closing = closing
        previous_step_maximum_cell_scalar_residual = max(
            (abs(value) for value in cell_residuals),
            default=0.0,
        )

    # The native summary is an observability mirror, not a second source of
    # truth.  Recompute every shadow field from the already replayed history so
    # a stale or collusively edited headline cannot mask a damaged ledger.
    if not failures:
        summary = world.get("summary")
        try:
            if not isinstance(summary, dict):
                raise TypeError
            opening_counts = [
                _integer(record["opening_packet_count"], "opening packet count")
                for record in history
            ]
            transported_counts = [
                _integer(
                    record["transported_packet_count"],
                    "transported packet count",
                )
                for record in history
            ]
            closing_counts = [
                _integer(record["closing_packet_count"], "closing packet count")
                for record in history
            ]
            source_counts = [
                _integer(
                    record["unresolved_source_adjustment_count"],
                    "source adjustment count",
                )
                for record in history
            ]
            sink_counts = [
                _integer(
                    record["unresolved_sink_adjustment_count"],
                    "sink adjustment count",
                )
                for record in history
            ]
            expected_summary_counts = {
                "crust_material_shadow_history_step_count": len(history),
                "total_crust_material_shadow_packet_count": (
                    sum(opening_counts)
                    + sum(transported_counts)
                    + sum(closing_counts)
                ),
                "maximum_crust_material_shadow_packet_count_per_table": max(
                    max(opening_counts, default=0),
                    max(transported_counts, default=0),
                    max(closing_counts, default=0),
                ),
                "total_crust_material_shadow_opening_packet_count": sum(
                    opening_counts
                ),
                "total_crust_material_shadow_transported_packet_count": sum(
                    transported_counts
                ),
                "total_crust_material_shadow_closing_packet_count": sum(
                    closing_counts
                ),
                "maximum_crust_material_shadow_opening_packet_count_per_step": max(
                    opening_counts,
                    default=0,
                ),
                "maximum_crust_material_shadow_transported_packet_count_per_step": max(
                    transported_counts,
                    default=0,
                ),
                "maximum_crust_material_shadow_closing_packet_count_per_step": max(
                    closing_counts,
                    default=0,
                ),
                "total_crust_material_shadow_adjustment_count": (
                    sum(source_counts) + sum(sink_counts)
                ),
                "maximum_crust_material_shadow_adjustment_count_per_table": max(
                    max(source_counts, default=0),
                    max(sink_counts, default=0),
                ),
                "total_crust_material_shadow_unresolved_source_adjustment_count": sum(
                    source_counts
                ),
                "total_crust_material_shadow_unresolved_sink_adjustment_count": sum(
                    sink_counts
                ),
            }
            if set(expected_summary_counts) != SUMMARY_COUNT_FIELDS or any(
                type(summary.get(field)) is not int
                or summary[field] != expected
                for field, expected in expected_summary_counts.items()
            ):
                raise ValueError

            cumulative_source = 0.0
            cumulative_sink = 0.0
            maximum_raw_residual = 0.0
            maximum_scalar_relative_residual = 0.0
            maximum_adjustment_residual = 0.0
            for record in history:
                cumulative_source += _finite_float(
                    record["global_unresolved_source_mass_kg"],
                    "history source mass",
                )
                cumulative_sink += _finite_float(
                    record["global_unresolved_sink_mass_kg"],
                    "history sink mass",
                )
                maximum_raw_residual = max(
                    maximum_raw_residual,
                    abs(
                        _finite_float(
                            record["shadow_minus_raw_transport_residual_kg"],
                            "history raw transport residual",
                        )
                    ),
                )
                closing_scalar_mass = _finite_float(
                    record["closing_scalar_mass_kg"],
                    "history closing scalar mass",
                )
                maximum_scalar_relative_residual = max(
                    maximum_scalar_relative_residual,
                    abs(
                        _finite_float(
                            record["closing_scalar_mass_residual_kg"],
                            "history closing scalar residual",
                        )
                    )
                    / max(1.0, abs(closing_scalar_mass)),
                )
                maximum_adjustment_residual = max(
                    maximum_adjustment_residual,
                    abs(
                        _finite_float(
                            record[
                                "ordered_adjustment_reconciliation_residual_kg"
                            ],
                            "history adjustment residual",
                        )
                    ),
                )
            expected_summary_scalars = {
                "cumulative_crust_material_shadow_unresolved_source_mass_kg": cumulative_source,
                "cumulative_crust_material_shadow_unresolved_sink_mass_kg": cumulative_sink,
                "maximum_absolute_crust_material_shadow_transport_raw_residual_kg": maximum_raw_residual,
                "maximum_crust_material_shadow_closing_scalar_relative_residual": maximum_scalar_relative_residual,
                "maximum_absolute_crust_material_shadow_adjustment_reconciliation_residual_kg": maximum_adjustment_residual,
            }
            scalar_mirrors_match = True
            for field, expected in expected_summary_scalars.items():
                actual = _finite_float(summary.get(field), f"summary.{field}")
                if field == (
                    "maximum_crust_material_shadow_closing_scalar_"
                    "relative_residual"
                ):
                    tolerance = max(
                        # Native numeric JSON uses 17 fixed fractional digits,
                        # so this dimensionless headline is quantized at
                        # 1e-17 even though the underlying history masses are
                        # serialized without a meaningful loss at their scale.
                        5.1e-18,
                        64.0 * math.ulp(max(sys.float_info.min, abs(expected))),
                    )
                    matches = math.isclose(
                        actual,
                        expected,
                        rel_tol=64.0 * sys.float_info.epsilon,
                        abs_tol=tolerance,
                    )
                else:
                    matches = _mass_close(
                        actual,
                        expected,
                        terms=tuple(expected_summary_scalars.values()),
                    )
                scalar_mirrors_match = scalar_mirrors_match and matches
            if (
                set(expected_summary_scalars) != SUMMARY_SCALAR_FIELDS
                or not scalar_mirrors_match
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError, OverflowError):
            failures.append("crust material shadow summary mirrors do not replay")

    return {
        "passed": not failures,
        "failures": failures,
        "metrics": {
            "history_step_count": len(history),
            "maximum_absolute_cell_closing_scalar_mass_residual_kg": (
                maximum_cell_scalar_residual
            ),
            "maximum_source_to_transport_residual_kg": (
                maximum_transport_replay_residual
            ),
            "cumulative_unresolved_source_mass_kg": total_source_mass,
            "cumulative_unresolved_sink_mass_kg": total_sink_mass,
        },
    }
