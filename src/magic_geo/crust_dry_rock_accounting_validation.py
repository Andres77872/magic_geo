from __future__ import annotations

import math
import sys
from collections.abc import Mapping, Sequence
from typing import Any, NamedTuple

from .crust_process_validation import CRUST_PROCESS_REASON_ORDER


MASS_FACTOR_KG = 1.0e12
CAPACITY_THICKNESS_KM = 76.0
CAPACITY_DENSITY_G_CM3 = 3.08
SURFACE_RESERVOIR_ID = 0
UPPER_MANTLE_RESERVOIR_ID = 1
SUBDUCTED_SLAB_RESERVOIR_ID = 2
MAX_SURFACE_PACKETS_PER_OWNER = 1024
MAX_LIVE_RESERVOIR_PACKETS = 1_000_000
MAX_PROXY_TRANSFERS_PER_STEP = 1_000_000

MODEL_LITERAL_VALUES: dict[str, Any] = {
    "model_type": "finite_three_reservoir_dry_rock_accounting_v1",
    "mode": "finite_accounting_shadow",
    "mass_unit": "kg",
    "accounting_scope": (
        "surface_basement_crust_upper_mantle_exchange_and_plate_resolved_"
        "subducted_slab"
    ),
    "reservoir_order": [
        "surface_basement_crust",
        "upper_mantle_exchange",
        "subducted_slab",
    ],
    "origin_domain_order": [
        "initial_surface_crust",
        "initial_upper_mantle_exchange_reserve",
    ],
    "packet_key_fields": [
        "origin_domain_id",
        "origin_kind_id",
        "origin_plate_id",
    ],
    "packet_sort_order": (
        "origin_domain_id_then_origin_kind_id_then_origin_plate_id"
    ),
    "packet_coalescing_model": "sorted_equal_key_sum_v1",
    "surface_transport_model": (
        "source_normalized_overlap_with_final_edge_remainder_v1"
    ),
    "capacity_model": "surface_state_envelope_v1",
    "capacity_formula": (
        "sum_control_volume_area_km2_times_76_km_times_3.08_g_cm3_times_1e12"
    ),
    "capacity_maximum_surface_thickness_km": 76.0,
    "capacity_maximum_surface_density_g_cm3": 3.08,
    "capacity_geophysically_calibrated": False,
    "capacity_semantics": (
        "finite_numerical_surface_state_envelope_not_an_estimate_of_upper_"
        "mantle_mass"
    ),
    "operational_safety_limit_model": (
        "incremental_fail_closed_packet_and_transfer_memory_caps_v1"
    ),
    "maximum_surface_packets_per_owner": MAX_SURFACE_PACKETS_PER_OWNER,
    "maximum_live_reservoir_packets": MAX_LIVE_RESERVOIR_PACKETS,
    "maximum_proxy_transfers_per_step": MAX_PROXY_TRANSFERS_PER_STEP,
    "operational_safety_limits_enforced_incrementally": True,
    "operational_safety_limits_are_physical_flux_limits": False,
    "operational_safety_limit_semantics": (
        "numerical_memory_safety_limits_not_physical_flux_or_reservoir_"
        "capacity_limits"
    ),
    "proxy_transaction_order": (
        "process_reason_then_all_surface_sinks_by_ascending_cell_and_origin_"
        "key_then_all_surface_sources_by_ascending_cell_and_origin_key"
    ),
    "proxy_transfer_mechanism": "legacy_rule_mass_compensation_v1",
    "mantle_withdrawal_model": (
        "initial_exchange_reserve_first_then_largest_packet_lowest_key_tie_"
        "break_v1"
    ),
    "mantle_exchange_topology": (
        "single_global_packet_pool_shared_by_all_cells_without_spatial_"
        "coordinates_v1"
    ),
    "instantaneous_global_mantle_mixing_assumed": True,
    "mantle_origin_packets_homogenized": False,
    "mantle_spatial_transport_resolved": False,
    "surface_sink_model": (
        "proportional_packets_with_remainder_to_largest_packet_lowest_key_"
        "tie_break"
    ),
    "exact_exhaustion_semantics": (
        "empty_reservoir_valid_and_reseed_requires_a_later_explicit_transfer"
    ),
    "insufficient_exchange_semantics": (
        "fail_closed_without_publishing_partial_accounting_state"
    ),
    "subducted_slab_owner_semantics": "subducting_source_plate_id",
    "subducted_slab_phase_2_state": (
        "plate_resolved_empty_reservoir_no_transfer_mechanism_enabled"
    ),
    "phase_s_request_source": (
        "crust_material_shadow_history_unresolved_adjustments_replayed_as_"
        "finite_proxy_compensations"
    ),
    "finite_three_reservoir_accounting_present": True,
    "closed_three_reservoir_dry_rock_accounting": True,
    "per_origin_accounting_closed": True,
    "finite_exchange_inventory_enforced": True,
    "legacy_proxy_compensations_exposed": True,
    "plate_resolved_slab_accounting_state_present": True,
    "authoritative_for_cell_state": False,
    "physical_source_sink_resolved": False,
    "material_provenance_resolved": False,
    "upper_mantle_exchange_reservoir_resolved": False,
    "subducted_slab_reservoir_resolved": False,
    "global_crust_cycle_mass_conservation_resolved": False,
    "solid_volume_resolved": False,
    "phase_resolved": False,
    "mass_weighted_age_resolved": False,
    "sediment_coupled": False,
    "coverage_membership_fate_resolved": False,
    "subduction_polarity_resolved": False,
}

PACKET_TABLE_KEYS = {
    "owner_offsets",
    "origin_domain_ids",
    "origin_kind_ids",
    "origin_plate_ids",
    "dry_rock_mass_kg",
}
TRANSFER_TABLE_KEYS = {
    "sequence_ids",
    "mechanism_ids",
    "process_reason_ids",
    "cell_ids",
    "fragment_ids",
    "source_reservoir_ids",
    "source_owner_ids",
    "destination_reservoir_ids",
    "destination_owner_ids",
    "origin_domain_ids",
    "origin_kind_ids",
    "origin_plate_ids",
    "physical_basis_resolved",
    "dry_rock_mass_kg",
}
HISTORY_RECORD_KEYS = {
    "id", "plate_motion_history_id", "crust_material_shadow_history_id",
    "stage", "erosion_iteration", "cell_count", "plate_count",
    "opening_surface_packets", "transported_surface_packets",
    "closing_surface_packets", "opening_upper_mantle_packets",
    "closing_upper_mantle_packets", "opening_subducted_slab_packets",
    "closing_subducted_slab_packets", "proxy_compensation_transfers",
    "ordered_reason_transactions", "surface_state_envelope_capacity_kg",
    "total_control_volume_area_km2", "opening_surface_mass_kg",
    "transported_surface_mass_kg", "closing_surface_mass_kg",
    "opening_upper_mantle_mass_kg", "closing_upper_mantle_mass_kg",
    "opening_subducted_slab_mass_kg", "closing_subducted_slab_mass_kg",
    "opening_global_mass_kg", "closing_global_mass_kg",
    "source_to_transport_residual_kg", "global_accounting_residual_kg",
    "capacity_initialization_residual_kg",
    "maximum_absolute_origin_closure_residual_kg",
    "maximum_absolute_reservoir_transfer_residual_kg",
    "closing_scalar_mass_kg", "closing_scalar_mass_residual_kg",
    "maximum_absolute_cell_closing_scalar_mass_residual_kg",
    "requested_minus_fulfilled_source_mass_kg",
    "requested_minus_fulfilled_sink_mass_kg",
    "opening_surface_packet_count", "transported_surface_packet_count",
    "closing_surface_packet_count", "opening_upper_mantle_packet_count",
    "closing_upper_mantle_packet_count",
    "opening_subducted_slab_packet_count",
    "closing_subducted_slab_packet_count",
    "proxy_compensation_transfer_count",
    "maximum_surface_packet_count_per_owner",
    "maximum_live_reservoir_packet_count",
}
SUMMARY_COUNT_FIELDS = {
    "crust_dry_rock_accounting_history_step_count",
    "total_crust_dry_rock_surface_packet_count",
    "total_crust_dry_rock_upper_mantle_packet_count",
    "total_crust_dry_rock_subducted_slab_packet_count",
    "total_crust_dry_rock_proxy_transfer_count",
    "maximum_crust_dry_rock_closing_surface_packet_count_per_step",
    "maximum_crust_dry_rock_closing_upper_mantle_packet_count_per_step",
    "maximum_crust_dry_rock_proxy_transfer_count_per_step",
    "maximum_crust_dry_rock_closing_reservoir_packet_count_per_step",
    "maximum_crust_dry_rock_surface_packet_count_per_owner",
    "maximum_crust_dry_rock_live_reservoir_packet_count_per_step",
}
SUMMARY_MASS_FIELDS = {
    "cumulative_crust_dry_rock_requested_surface_source_mass_kg",
    "cumulative_crust_dry_rock_requested_surface_sink_mass_kg",
    "cumulative_crust_dry_rock_fulfilled_surface_source_mass_kg",
    "cumulative_crust_dry_rock_fulfilled_surface_sink_mass_kg",
    "minimum_crust_dry_rock_closing_upper_mantle_mass_kg",
    "maximum_crust_dry_rock_closing_subducted_slab_mass_kg",
    "maximum_absolute_crust_dry_rock_global_accounting_residual_kg",
    "maximum_absolute_crust_dry_rock_origin_closure_residual_kg",
    "maximum_absolute_crust_dry_rock_reservoir_transfer_residual_kg",
    "maximum_crust_dry_rock_closing_scalar_relative_residual",
}


class PacketKey(NamedTuple):
    origin_domain_id: int
    origin_kind_id: int
    origin_plate_id: int


class Transfer(NamedTuple):
    process_reason_id: int
    cell_id: int
    source_reservoir_id: int
    source_owner_id: int
    destination_reservoir_id: int
    destination_owner_id: int
    key: PacketKey
    dry_rock_mass_kg: float


def _integer(value: Any, field: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{field} must be an integer")
    return value


def _finite(value: Any, field: str) -> float:
    if type(value) not in (int, float):
        raise TypeError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def _bound(*values: float, terms: Sequence[float] = (), count: int = 1) -> float:
    scale = max(1.0, *(abs(value) for value in values))
    operand_sum = math.fsum(abs(value) for value in terms)
    return max(
        1.0e-3,
        128.0 * math.ulp(scale),
        512.0 * sys.float_info.epsilon * max(1, count) * (1.0 + operand_sum),
    )


def _close(actual: float, expected: float, *, terms: Sequence[float] = ()) -> bool:
    return abs(actual - expected) <= _bound(actual, expected, terms=terms)


def _valid_key(key: PacketKey, plate_count: int) -> bool:
    if key.origin_domain_id == 0:
        return 0 <= key.origin_kind_id <= 8 and 0 <= key.origin_plate_id < plate_count
    if key.origin_domain_id == 1:
        return key.origin_kind_id == -1 and key.origin_plate_id == -1
    return False


def _parse_packets(
    payload: Any,
    *,
    owner_count: int,
    plate_count: int,
    field: str,
    maximum_packets_per_owner: int | None = None,
) -> list[dict[PacketKey, float]]:
    if not isinstance(payload, dict) or set(payload) != PACKET_TABLE_KEYS:
        raise TypeError(f"{field} has an invalid schema")
    columns = [payload[key] for key in PACKET_TABLE_KEYS]
    if not all(isinstance(column, list) for column in columns):
        raise TypeError(f"{field} columns must be lists")
    offsets = [_integer(value, f"{field}.owner_offsets") for value in payload["owner_offsets"]]
    domains = [_integer(value, f"{field}.origin_domain_ids") for value in payload["origin_domain_ids"]]
    kinds = [_integer(value, f"{field}.origin_kind_ids") for value in payload["origin_kind_ids"]]
    plates = [_integer(value, f"{field}.origin_plate_ids") for value in payload["origin_plate_ids"]]
    masses = [_finite(value, f"{field}.dry_rock_mass_kg") for value in payload["dry_rock_mass_kg"]]
    if (
        len(offsets) != owner_count + 1 or not offsets or offsets[0] != 0
        or any(left > right for left, right in zip(offsets, offsets[1:]))
        or offsets[-1] != len(masses)
        or not len(domains) == len(kinds) == len(plates) == len(masses)
    ):
        raise ValueError(f"{field} has invalid sparse dimensions")
    result: list[dict[PacketKey, float]] = []
    for owner in range(owner_count):
        if (
            maximum_packets_per_owner is not None
            and offsets[owner + 1] - offsets[owner]
            > maximum_packets_per_owner
        ):
            raise ValueError(f"{field} exceeds its per-owner safety limit")
        packets: dict[PacketKey, float] = {}
        previous: PacketKey | None = None
        for index in range(offsets[owner], offsets[owner + 1]):
            key = PacketKey(domains[index], kinds[index], plates[index])
            if (
                not _valid_key(key, plate_count) or masses[index] <= 0.0
                or (previous is not None and key <= previous)
            ):
                raise ValueError(f"{field} packets are not canonical")
            packets[key] = masses[index]
            previous = key
        result.append(packets)
    return result


def _canonical_packets(packets: Sequence[Mapping[PacketKey, float]]) -> dict[str, list[Any]]:
    offsets = [0]
    domains: list[int] = []
    kinds: list[int] = []
    plates: list[int] = []
    masses: list[float] = []
    for owner in packets:
        for key in sorted(owner):
            mass = float(owner[key])
            if mass <= 0.0 or not math.isfinite(mass):
                raise ValueError("packet mass is invalid")
            domains.append(key.origin_domain_id)
            kinds.append(key.origin_kind_id)
            plates.append(key.origin_plate_id)
            masses.append(mass)
        offsets.append(len(masses))
    return {
        "owner_offsets": offsets,
        "origin_domain_ids": domains,
        "origin_kind_ids": kinds,
        "origin_plate_ids": plates,
        "dry_rock_mass_kg": masses,
    }


def _maps_close(
    actual: Sequence[Mapping[PacketKey, float]],
    expected: Sequence[Mapping[PacketKey, float]],
) -> bool:
    return len(actual) == len(expected) and all(
        set(left) == set(right) and all(
            _close(left[key], right[key], terms=(left[key], right[key]))
            for key in left
        )
        for left, right in zip(actual, expected, strict=True)
    )


def _normalize(packets: Mapping[PacketKey, float]) -> dict[PacketKey, float]:
    return {
        key: mass for key, mass in sorted(packets.items())
        if math.isfinite(mass) and mass > 0.0
    }


def _transport_surface(
    opening: Sequence[Mapping[PacketKey, float]],
    destination_offsets: Sequence[Any],
    source_cell_ids: Sequence[Any],
    overlap_area_km2: Sequence[Any],
    non_surface_packet_count: int,
) -> tuple[list[dict[PacketKey, float]], int, int]:
    cell_count = len(opening)
    offsets = [_integer(value, "destination_offsets") for value in destination_offsets]
    sources = [_integer(value, "source_cell_ids") for value in source_cell_ids]
    areas = [_finite(value, "overlap_area_km2") for value in overlap_area_km2]
    if (
        len(offsets) != cell_count + 1 or offsets[0] != 0
        or offsets[-1] != len(sources) or len(sources) != len(areas)
        or any(left > right for left, right in zip(offsets, offsets[1:]))
        or any(not 0 <= source < cell_count for source in sources)
        or any(area <= 0.0 for area in areas)
    ):
        raise ValueError("transport CSR is invalid")
    edges: list[tuple[int, int, int, float]] = []
    for destination in range(cell_count):
        row = sources[offsets[destination]:offsets[destination + 1]]
        if row != sorted(set(row)):
            raise ValueError("transport CSR rows are not canonical")
        for edge in range(offsets[destination], offsets[destination + 1]):
            edges.append((sources[edge], destination, edge, areas[edge]))
    edges.sort()
    by_source: list[list[tuple[int, int, float]]] = [[] for _ in range(cell_count)]
    for source, destination, edge, area in edges:
        by_source[source].append((destination, edge, area))
    if any(not row for row in by_source):
        raise ValueError("a source cell has no outgoing overlap")
    if any(len(owner) > MAX_SURFACE_PACKETS_PER_OWNER for owner in opening):
        raise ValueError("an opening surface owner exceeds its packet safety limit")
    transported: list[dict[PacketKey, float]] = [
        {} for _ in range(cell_count)
    ]
    transported_packet_count = 0
    maximum_owner_packet_count = max((len(owner) for owner in opening), default=0)
    for source, row in enumerate(by_source):
        denominator = 0.0
        for _, _, area in row:
            denominator += area
        for key in sorted(opening[source]):
            mass = opening[source][key]
            allocated = 0.0
            for position, (destination, _, area) in enumerate(row):
                contribution = (
                    mass - allocated if position + 1 == len(row)
                    else mass * (area / denominator)
                )
                if contribution < 0.0 or not math.isfinite(contribution):
                    raise ValueError("transport allocation is invalid")
                if contribution > 0.0:
                    owner = transported[destination]
                    if key in owner:
                        owner[key] += contribution
                        if not math.isfinite(owner[key]):
                            raise ValueError("transport packet accumulation overflowed")
                    else:
                        if len(owner) >= MAX_SURFACE_PACKETS_PER_OWNER:
                            raise ValueError(
                                "surface-owner packet safety limit exceeded"
                            )
                        if (
                            non_surface_packet_count + transported_packet_count
                            >= MAX_LIVE_RESERVOIR_PACKETS
                        ):
                            raise ValueError(
                                "live reservoir packet safety limit exceeded"
                            )
                        owner[key] = contribution
                        transported_packet_count += 1
                        maximum_owner_packet_count = max(
                            maximum_owner_packet_count,
                            len(owner),
                        )
                allocated += contribution
    return (
        [_normalize(owner) for owner in transported],
        maximum_owner_packet_count,
        transported_packet_count,
    )


def _withdraw_surface(
    packets: dict[PacketKey, float], requested: float
) -> tuple[list[tuple[PacketKey, float]], float]:
    keys = sorted(packets)
    available = math.fsum(packets.values())
    if requested <= 0.0 or available <= 0.0:
        raise ValueError("invalid or unavailable surface withdrawal")
    fulfilled = requested
    if requested > available:
        if requested - available > _bound(requested, available, terms=(requested, available), count=len(keys) + 2):
            raise ValueError("surface withdrawal exceeds available mass")
        fulfilled = available
    if fulfilled >= available:
        withdrawn = [(key, packets[key]) for key in keys]
        packets.clear()
        return withdrawn, available
    correction = min(keys, key=lambda key: (-packets[key], key))
    removals: dict[PacketKey, float] = {}
    provisional = 0.0
    for key in keys:
        removals[key] = fulfilled * packets[key] / available
        provisional += removals[key]
    removals[correction] += fulfilled - provisional
    withdrawn: list[tuple[PacketKey, float]] = []
    for key in keys:
        removal = removals[key]
        if removal < 0.0 or removal > packets[key]:
            raise ValueError("proportional withdrawal failed")
        if removal > 0.0:
            withdrawn.append((key, removal))
        remainder = packets[key] - removal
        if remainder > 0.0:
            packets[key] = remainder
        else:
            del packets[key]
    return withdrawn, fulfilled


def _withdraw_mantle(
    packets: dict[PacketKey, float], requested: float
) -> list[tuple[PacketKey, float]]:
    if requested <= 0.0 or requested > math.fsum(packets.values()):
        raise ValueError("upper-mantle exchange reserve exhausted")
    remaining = requested
    withdrawn: dict[PacketKey, float] = {}
    while remaining > 0.0:
        keys = sorted(packets)
        exchange = [key for key in keys if key.origin_domain_id == 1]
        candidates = exchange or keys
        if not candidates:
            raise ValueError("upper-mantle exchange reserve exhausted")
        selected = min(candidates, key=lambda key: (-packets[key], key))
        removal = min(remaining, packets[selected])
        withdrawn[selected] = withdrawn.get(selected, 0.0) + removal
        remaining -= removal
        if removal == packets[selected]:
            del packets[selected]
        else:
            packets[selected] -= removal
    return sorted(withdrawn.items())


def _merge(packets: dict[PacketKey, float], key: PacketKey, mass: float) -> None:
    packets[key] = packets.get(key, 0.0) + mass


def replay_crust_dry_rock_accounting_step(
    *,
    opening_surface_packets: Sequence[Mapping[PacketKey, float]],
    opening_upper_mantle_packets: Mapping[PacketKey, float],
    opening_subducted_slab_packets: Sequence[Mapping[PacketKey, float]],
    destination_offsets: Sequence[Any],
    source_cell_ids: Sequence[Any],
    overlap_area_km2: Sequence[Any],
    source_requests_kg_by_reason_cell: Sequence[Sequence[Any]],
    sink_requests_kg_by_reason_cell: Sequence[Sequence[Any]],
) -> dict[str, Any]:
    """Independently replay one finite proxy-accounting transaction."""

    cell_count = len(opening_surface_packets)
    reason_count = len(CRUST_PROCESS_REASON_ORDER)
    if len(source_requests_kg_by_reason_cell) != reason_count or len(sink_requests_kg_by_reason_cell) != reason_count:
        raise ValueError("one request row is required for every process reason")
    sources = [[_finite(value, "source request") for value in row] for row in source_requests_kg_by_reason_cell]
    sinks = [[_finite(value, "sink request") for value in row] for row in sink_requests_kg_by_reason_cell]
    if any(len(row) != cell_count for row in sources + sinks) or any(value < 0.0 for row in sources + sinks for value in row):
        raise ValueError("request matrix is invalid")
    surface = [dict(owner) for owner in opening_surface_packets]
    mantle = dict(opening_upper_mantle_packets)
    slab = [dict(owner) for owner in opening_subducted_slab_packets]
    if any(len(owner) > MAX_SURFACE_PACKETS_PER_OWNER for owner in surface):
        raise ValueError("an opening surface owner exceeds its packet safety limit")
    opening_live_packet_count = (
        sum(len(owner) for owner in surface)
        + len(mantle)
        + sum(len(owner) for owner in slab)
    )
    if opening_live_packet_count > MAX_LIVE_RESERVOIR_PACKETS:
        raise ValueError("live reservoir packet safety limit exceeded")
    maximum_owner_packet_count = max(
        (len(owner) for owner in surface),
        default=0,
    )
    transported, transport_maximum_owner, transported_packet_count = (
        _transport_surface(
            surface,
            destination_offsets,
            source_cell_ids,
            overlap_area_km2,
            len(mantle) + sum(len(owner) for owner in slab),
        )
    )
    maximum_owner_packet_count = max(
        maximum_owner_packet_count,
        transport_maximum_owner,
    )
    surface = [dict(owner) for owner in transported]
    live_packet_count = (
        transported_packet_count
        + len(mantle)
        + sum(len(owner) for owner in slab)
    )
    if live_packet_count > MAX_LIVE_RESERVOIR_PACKETS:
        raise ValueError("live reservoir packet safety limit exceeded")
    maximum_live_packet_count = max(
        opening_live_packet_count,
        live_packet_count,
    )
    transfers: list[Transfer] = []
    fulfilled_sources = [0.0] * reason_count
    fulfilled_sinks = [0.0] * reason_count
    for reason in range(reason_count):
        for cell in range(cell_count):
            if sources[reason][cell] > 0.0 and sinks[reason][cell] > 0.0:
                raise ValueError("a cell/reason cannot request both signs")
            request = sinks[reason][cell]
            if request == 0.0:
                continue
            surface_count_before = len(surface[cell])
            withdrawn, fulfilled = _withdraw_surface(surface[cell], request)
            live_packet_count -= surface_count_before - len(surface[cell])
            fulfilled_sinks[reason] += fulfilled
            for key, mass in withdrawn:
                mantle_count_before = len(mantle)
                if (
                    key not in mantle
                    and live_packet_count >= MAX_LIVE_RESERVOIR_PACKETS
                ):
                    raise ValueError("live reservoir packet safety limit exceeded")
                _merge(mantle, key, mass)
                live_packet_count += len(mantle) - mantle_count_before
                if live_packet_count > MAX_LIVE_RESERVOIR_PACKETS:
                    raise ValueError("live reservoir packet safety limit exceeded")
                maximum_live_packet_count = max(
                    maximum_live_packet_count,
                    live_packet_count,
                )
                if len(transfers) >= MAX_PROXY_TRANSFERS_PER_STEP:
                    raise ValueError("per-step transfer safety limit exceeded")
                transfers.append(Transfer(reason, cell, 0, cell, 1, -1, key, mass))
        if math.fsum(sources[reason]) > math.fsum(mantle.values()):
            raise ValueError("upper-mantle exchange reserve exhausted")
        for cell in range(cell_count):
            request = sources[reason][cell]
            if request == 0.0:
                continue
            mantle_count_before = len(mantle)
            withdrawn = _withdraw_mantle(mantle, request)
            live_packet_count -= mantle_count_before - len(mantle)
            fulfilled_sources[reason] += request
            for key, mass in withdrawn:
                surface_count_before = len(surface[cell])
                if key not in surface[cell]:
                    if len(surface[cell]) >= MAX_SURFACE_PACKETS_PER_OWNER:
                        raise ValueError("surface-owner packet safety limit exceeded")
                    if live_packet_count >= MAX_LIVE_RESERVOIR_PACKETS:
                        raise ValueError("live reservoir packet safety limit exceeded")
                _merge(surface[cell], key, mass)
                if len(surface[cell]) > MAX_SURFACE_PACKETS_PER_OWNER:
                    raise ValueError("surface-owner packet safety limit exceeded")
                maximum_owner_packet_count = max(
                    maximum_owner_packet_count,
                    len(surface[cell]),
                )
                live_packet_count += len(surface[cell]) - surface_count_before
                if live_packet_count > MAX_LIVE_RESERVOIR_PACKETS:
                    raise ValueError("live reservoir packet safety limit exceeded")
                maximum_live_packet_count = max(
                    maximum_live_packet_count,
                    live_packet_count,
                )
                if len(transfers) >= MAX_PROXY_TRANSFERS_PER_STEP:
                    raise ValueError("per-step transfer safety limit exceeded")
                transfers.append(Transfer(reason, cell, 1, -1, 0, cell, key, mass))
    return {
        "transported_surface_packets": transported,
        "closing_surface_packets": [_normalize(owner) for owner in surface],
        "closing_upper_mantle_packets": _normalize(mantle),
        "closing_subducted_slab_packets": [_normalize(owner) for owner in slab],
        "transfers": transfers,
        "requested_sources": [math.fsum(row) for row in sources],
        "requested_sinks": [math.fsum(row) for row in sinks],
        "fulfilled_sources": fulfilled_sources,
        "fulfilled_sinks": fulfilled_sinks,
        "maximum_surface_packet_count_per_owner": maximum_owner_packet_count,
        "maximum_live_reservoir_packet_count": maximum_live_packet_count,
    }


def _shadow_packet_origins(
    payload: Any, *, cell_count: int, plate_count: int
) -> list[dict[tuple[int, int, int], float]]:
    keys = {
        "cell_offsets", "origin_kind_ids", "origin_plate_ids",
        "origin_reason_ids", "dry_rock_mass_kg",
    }
    if not isinstance(payload, dict) or set(payload) != keys:
        raise TypeError("shadow opening packet table schema is invalid")
    offsets = [_integer(value, "shadow.cell_offsets") for value in payload["cell_offsets"]]
    kinds = [_integer(value, "shadow.origin_kind_ids") for value in payload["origin_kind_ids"]]
    plates = [_integer(value, "shadow.origin_plate_ids") for value in payload["origin_plate_ids"]]
    reasons = [_integer(value, "shadow.origin_reason_ids") for value in payload["origin_reason_ids"]]
    masses = [_finite(value, "shadow.dry_rock_mass_kg") for value in payload["dry_rock_mass_kg"]]
    if (
        len(offsets) != cell_count + 1 or offsets[0] != 0
        or offsets[-1] != len(masses)
        or any(left > right for left, right in zip(offsets, offsets[1:]))
        or not len(kinds) == len(plates) == len(reasons) == len(masses)
    ):
        raise ValueError("shadow packet table shape is invalid")
    result: list[dict[tuple[int, int, int], float]] = []
    for cell in range(cell_count):
        owner: dict[tuple[int, int, int], float] = {}
        previous: tuple[int, int, int] | None = None
        for index in range(offsets[cell], offsets[cell + 1]):
            key = (kinds[index], plates[index], reasons[index])
            valid = (
                0 <= key[0] <= 9 and 0 <= key[1] < plate_count
                and ((key[0] == 9 and 0 <= key[2] < len(CRUST_PROCESS_REASON_ORDER))
                     or (key[0] != 9 and key[2] == -1))
            )
            if not valid or masses[index] <= 0.0 or (previous is not None and key <= previous):
                raise ValueError("shadow packet key is invalid")
            owner[key] = masses[index]
            previous = key
        result.append(owner)
    return result


def _shadow_requests(
    payload: Any,
    *,
    cell_count: int,
    plate_count: int,
    source: bool,
) -> list[list[float]]:
    keys = {
        "cell_offsets", "process_reason_ids", "origin_kind_ids",
        "origin_plate_ids", "origin_reason_ids", "dry_rock_mass_kg",
    }
    if not isinstance(payload, dict) or set(payload) != keys:
        raise TypeError("shadow adjustment table schema is invalid")
    for value in payload.values():
        if not isinstance(value, list):
            raise TypeError("shadow adjustment columns must be lists")
    offsets = [_integer(value, "shadow adjustment offsets") for value in payload["cell_offsets"]]
    process = [_integer(value, "shadow process reason") for value in payload["process_reason_ids"]]
    kinds = [_integer(value, "shadow origin kind") for value in payload["origin_kind_ids"]]
    plates = [_integer(value, "shadow origin plate") for value in payload["origin_plate_ids"]]
    origins = [_integer(value, "shadow origin reason") for value in payload["origin_reason_ids"]]
    masses = [_finite(value, "shadow adjustment mass") for value in payload["dry_rock_mass_kg"]]
    if (
        len(offsets) != cell_count + 1 or offsets[0] != 0
        or offsets[-1] != len(masses)
        or any(left > right for left, right in zip(offsets, offsets[1:]))
        or not len(process) == len(kinds) == len(plates) == len(origins) == len(masses)
    ):
        raise ValueError("shadow adjustment table shape is invalid")
    requests = [[0.0] * cell_count for _ in CRUST_PROCESS_REASON_ORDER]
    for cell in range(cell_count):
        previous: tuple[int, int, int, int] | None = None
        for index in range(offsets[cell], offsets[cell + 1]):
            order = (process[index], kinds[index], plates[index], origins[index])
            valid_origin = (
                0 <= kinds[index] <= 9 and 0 <= plates[index] < plate_count
                and ((kinds[index] == 9 and 0 <= origins[index] < len(CRUST_PROCESS_REASON_ORDER))
                     or (kinds[index] != 9 and origins[index] == -1))
            )
            if (
                not 0 <= process[index] < len(CRUST_PROCESS_REASON_ORDER)
                or not valid_origin or masses[index] <= 0.0
                or (source and (kinds[index] != 9 or origins[index] != process[index]))
                or (previous is not None and order <= previous)
            ):
                raise ValueError("shadow adjustment record is invalid")
            requests[process[index]][cell] += masses[index]
            if not math.isfinite(requests[process[index]][cell]):
                raise ValueError("shadow adjustment accumulation overflowed")
            previous = order
    return requests


def _parse_transfers(
    payload: Any, *, cell_count: int, plate_count: int
) -> list[Transfer]:
    if not isinstance(payload, dict) or set(payload) != TRANSFER_TABLE_KEYS:
        raise TypeError("proxy transfer table schema is invalid")
    if not all(isinstance(value, list) for value in payload.values()):
        raise TypeError("proxy transfer columns must be lists")
    count = len(payload["dry_rock_mass_kg"])
    if any(len(payload[field]) != count for field in TRANSFER_TABLE_KEYS):
        raise ValueError("proxy transfer columns differ in length")
    integer_fields = TRANSFER_TABLE_KEYS - {"physical_basis_resolved", "dry_rock_mass_kg"}
    columns = {
        field: [_integer(value, f"transfer.{field}") for value in payload[field]]
        for field in integer_fields
    }
    physical = payload["physical_basis_resolved"]
    masses = [_finite(value, "transfer mass") for value in payload["dry_rock_mass_kg"]]
    result: list[Transfer] = []
    for index in range(count):
        key = PacketKey(
            columns["origin_domain_ids"][index],
            columns["origin_kind_ids"][index],
            columns["origin_plate_ids"][index],
        )
        cell = columns["cell_ids"][index]
        source_reservoir = columns["source_reservoir_ids"][index]
        source_owner = columns["source_owner_ids"][index]
        destination_reservoir = columns["destination_reservoir_ids"][index]
        destination_owner = columns["destination_owner_ids"][index]
        surface_to_mantle = (
            source_reservoir == 0 and destination_reservoir == 1
            and source_owner == cell and destination_owner == -1
        )
        mantle_to_surface = (
            source_reservoir == 1 and destination_reservoir == 0
            and source_owner == -1 and destination_owner == cell
        )
        if (
            columns["sequence_ids"][index] != index
            or columns["mechanism_ids"][index] != 0
            or not 0 <= columns["process_reason_ids"][index] < len(CRUST_PROCESS_REASON_ORDER)
            or not 0 <= cell < cell_count
            or columns["fragment_ids"][index] != -1
            or type(physical[index]) is not bool or physical[index] is not False
            or not _valid_key(key, plate_count) or masses[index] <= 0.0
            or not (surface_to_mantle or mantle_to_surface)
        ):
            raise ValueError("proxy transfer record is invalid")
        result.append(Transfer(
            columns["process_reason_ids"][index], cell,
            source_reservoir, source_owner,
            destination_reservoir, destination_owner,
            key, masses[index],
        ))
    return result


def _transfers_close(actual: Sequence[Transfer], expected: Sequence[Transfer]) -> bool:
    return len(actual) == len(expected) and all(
        left[:-1] == right[:-1]
        and _close(left.dry_rock_mass_kg, right.dry_rock_mass_kg,
                   terms=(left.dry_rock_mass_kg, right.dry_rock_mass_kg))
        for left, right in zip(actual, expected, strict=True)
    )


def _packet_mass(packets: Sequence[Mapping[PacketKey, float]]) -> float:
    return math.fsum(mass for owner in packets for mass in owner.values())


def _origin_totals(
    surface: Sequence[Mapping[PacketKey, float]],
    mantle: Mapping[PacketKey, float],
    slab: Sequence[Mapping[PacketKey, float]],
) -> dict[PacketKey, float]:
    terms: dict[PacketKey, list[float]] = {}
    for owner in [*surface, mantle, *slab]:
        for key, mass in owner.items():
            terms.setdefault(key, []).append(mass)
    return {key: math.fsum(values) for key, values in terms.items()}


def _record_scalar(record: Mapping[str, Any], field: str) -> float:
    return _finite(record[field], field)


def validate_crust_dry_rock_accounting(world: dict[str, Any]) -> dict[str, Any]:
    """Strictly replay the finite three-reservoir dry-rock accounting ledger."""

    failures: list[str] = []
    model = world.get("crust_dry_rock_accounting_model")
    history = world.get("crust_dry_rock_accounting_history")
    shadow_history = world.get("crust_material_shadow_history")
    plate_history = world.get("plate_motion_history")
    cells = world.get("cells")
    if (
        not isinstance(model, dict) or set(model) != set(MODEL_LITERAL_VALUES)
        or any(model.get(key) != value for key, value in MODEL_LITERAL_VALUES.items())
    ):
        failures.append("crust dry-rock accounting model metadata is invalid")
    if (
        not isinstance(history, list) or not history
        or not isinstance(shadow_history, list)
        or not isinstance(plate_history, list)
        or len(history) != len(shadow_history) or len(history) != len(plate_history)
        or not isinstance(cells, list) or not cells
    ):
        return {"passed": False, "failures": failures + ["aligned accounting histories are missing"], "metrics": {}}
    try:
        if any(not isinstance(cell, dict) or _integer(cell.get("id"), "cell.id") != index for index, cell in enumerate(cells)):
            raise ValueError
        areas = [_finite(cell["area_km2"], "cell.area_km2") for cell in cells]
        if any(area <= 0.0 for area in areas):
            raise ValueError
        cell_count = len(cells)
        first = history[0]
        if not isinstance(first, dict) or set(first) != HISTORY_RECORD_KEYS:
            raise ValueError
        plate_count = _integer(first["plate_count"], "plate_count")
        if plate_count <= 0:
            raise ValueError
        total_area = math.fsum(areas)
        capacity = total_area * CAPACITY_THICKNESS_KM * CAPACITY_DENSITY_G_CM3 * MASS_FACTOR_KG
    except (KeyError, TypeError, ValueError, OverflowError):
        return {"passed": False, "failures": failures + ["accounting geometry or initial schema is invalid"], "metrics": {}}

    previous_record: dict[str, Any] | None = None
    cumulative_requested_source = 0.0
    cumulative_requested_sink = 0.0
    cumulative_fulfilled_source = 0.0
    cumulative_fulfilled_sink = 0.0
    maximum_transport_residual = 0.0
    for step_index, (record, shadow, plate_step) in enumerate(zip(history, shadow_history, plate_history, strict=True)):
        if not isinstance(record, dict) or set(record) != HISTORY_RECORD_KEYS or not isinstance(shadow, dict) or not isinstance(plate_step, dict):
            failures.append(f"crust dry-rock accounting history {step_index} schema is invalid")
            break
        try:
            if (
                _integer(record["id"], "history.id") != step_index
                or _integer(record["plate_motion_history_id"], "plate link") != step_index
                or _integer(plate_step["id"], "plate.id") != step_index
                or _integer(record["crust_material_shadow_history_id"], "shadow link") != step_index
                or _integer(shadow["id"], "shadow.id") != step_index
                or record["stage"] != plate_step["stage"] or record["stage"] != shadow["stage"]
                or not isinstance(record["stage"], str) or not record["stage"]
                or _integer(record["erosion_iteration"], "erosion iteration") != _integer(plate_step["erosion_iteration"], "plate erosion iteration")
                or record["erosion_iteration"] != _integer(shadow["erosion_iteration"], "shadow erosion iteration")
                or _integer(record["cell_count"], "cell count") != cell_count
                or _integer(plate_step["cell_count"], "plate cell count") != cell_count
                or _integer(shadow["cell_count"], "shadow cell count") != cell_count
                or _integer(record["plate_count"], "plate count") != plate_count
                or _integer(plate_step["plate_count"], "plate step count") != plate_count
                or len(plate_step["plates"]) != plate_count
            ):
                raise ValueError
            opening_surface = _parse_packets(record["opening_surface_packets"], owner_count=cell_count, plate_count=plate_count, field="opening_surface_packets", maximum_packets_per_owner=MAX_SURFACE_PACKETS_PER_OWNER)
            transported_surface = _parse_packets(record["transported_surface_packets"], owner_count=cell_count, plate_count=plate_count, field="transported_surface_packets", maximum_packets_per_owner=MAX_SURFACE_PACKETS_PER_OWNER)
            closing_surface = _parse_packets(record["closing_surface_packets"], owner_count=cell_count, plate_count=plate_count, field="closing_surface_packets", maximum_packets_per_owner=MAX_SURFACE_PACKETS_PER_OWNER)
            opening_mantle_rows = _parse_packets(record["opening_upper_mantle_packets"], owner_count=1, plate_count=plate_count, field="opening_upper_mantle_packets")
            closing_mantle_rows = _parse_packets(record["closing_upper_mantle_packets"], owner_count=1, plate_count=plate_count, field="closing_upper_mantle_packets")
            opening_slab = _parse_packets(record["opening_subducted_slab_packets"], owner_count=plate_count, plate_count=plate_count, field="opening_subducted_slab_packets")
            closing_slab = _parse_packets(record["closing_subducted_slab_packets"], owner_count=plate_count, plate_count=plate_count, field="closing_subducted_slab_packets")
            transfers = _parse_transfers(record["proxy_compensation_transfers"], cell_count=cell_count, plate_count=plate_count)
            opening_mantle = opening_mantle_rows[0]
            closing_mantle = closing_mantle_rows[0]
            if any(opening_slab) or any(closing_slab):
                raise ValueError("phase-2 slab reservoirs must remain empty")
            table_live_counts = (
                sum(map(len, opening_surface)) + len(opening_mantle) + sum(map(len, opening_slab)),
                sum(map(len, transported_surface)) + len(opening_mantle) + sum(map(len, opening_slab)),
                sum(map(len, closing_surface)) + len(closing_mantle) + sum(map(len, closing_slab)),
            )
            if (
                any(count > MAX_LIVE_RESERVOIR_PACKETS for count in table_live_counts)
                or len(transfers) > MAX_PROXY_TRANSFERS_PER_STEP
            ):
                raise ValueError("accounting history exceeds an operational safety limit")
            if previous_record is not None and (
                record["opening_surface_packets"] != previous_record["closing_surface_packets"]
                or record["opening_upper_mantle_packets"] != previous_record["closing_upper_mantle_packets"]
                or record["opening_subducted_slab_packets"] != previous_record["closing_subducted_slab_packets"]
            ):
                raise ValueError("opening reservoir links are not bit-exact")
            source_requests = _shadow_requests(shadow["unresolved_source_adjustments"], cell_count=cell_count, plate_count=plate_count, source=True)
            sink_requests = _shadow_requests(shadow["unresolved_sink_adjustments"], cell_count=cell_count, plate_count=plate_count, source=False)
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            failures.append(f"crust dry-rock accounting history {step_index} fields are invalid: {error}")
            break

        if step_index == 0:
            try:
                shadow_opening = _shadow_packet_origins(shadow["opening_packets"], cell_count=cell_count, plate_count=plate_count)
                if any(len(owner) != 1 for owner in shadow_opening):
                    raise ValueError
                overlap = plate_step["crust_overlap_ledger"]
                initial_thickness = overlap["remapped_crust_thickness_km_by_cell"]
                initial_density = overlap["remapped_crust_density_by_cell"]
                initial_kinds = plate_step["crust_type_by_cell"]
                initial_plates = plate_step["cell_plate_ids"]
                if any(
                    len(values) != cell_count
                    for values in (
                        initial_thickness,
                        initial_density,
                        initial_kinds,
                        initial_plates,
                    )
                ):
                    raise ValueError
                expected_surface: list[dict[PacketKey, float]] = []
                for cell, owner in enumerate(shadow_opening):
                    (shadow_key, mass), = owner.items()
                    kind = _integer(initial_kinds[cell], "initial crust kind")
                    plate = _integer(initial_plates[cell], "initial plate")
                    thickness = _finite(initial_thickness[cell], "initial thickness")
                    density = _finite(initial_density[cell], "initial density")
                    if (
                        not 0 <= kind <= 8
                        or not 0 <= plate < plate_count
                        or thickness < 0.0
                        or density < 0.0
                    ):
                        raise ValueError
                    expected_mass = areas[cell] * thickness * density * MASS_FACTOR_KG
                    if (
                        shadow_key != (kind, plate, -1)
                        or not _close(
                            mass,
                            expected_mass,
                            terms=(areas[cell], thickness, density, expected_mass),
                        )
                    ):
                        raise ValueError
                    expected_surface.append({PacketKey(0, kind, plate): expected_mass})
                surface_mass = _packet_mass(expected_surface)
                reserve = capacity - surface_mass
                if reserve < -_bound(
                    capacity,
                    surface_mass,
                    terms=(capacity, surface_mass),
                    count=cell_count + 4,
                ):
                    raise ValueError
                expected_mantle = {} if reserve <= 0.0 else {PacketKey(1, -1, -1): reserve}
            except (KeyError, TypeError, ValueError, OverflowError):
                failures.append("initial accounting origin state is invalid")
                break
            if (
                not _maps_close(opening_surface, expected_surface)
                or not _maps_close([opening_mantle], [expected_mantle])
                or not _maps_close(transported_surface, opening_surface)
                or not _maps_close(closing_surface, opening_surface)
                or not _maps_close([closing_mantle], [opening_mantle])
                or transfers or any(any(row) for row in source_requests + sink_requests)
            ):
                failures.append("initial accounting reservoirs do not replay")
                break
            replay = {
                "transported_surface_packets": opening_surface,
                "closing_surface_packets": opening_surface,
                "closing_upper_mantle_packets": opening_mantle,
                "closing_subducted_slab_packets": opening_slab,
                "transfers": [],
                "requested_sources": [0.0] * len(CRUST_PROCESS_REASON_ORDER),
                "requested_sinks": [0.0] * len(CRUST_PROCESS_REASON_ORDER),
                "fulfilled_sources": [0.0] * len(CRUST_PROCESS_REASON_ORDER),
                "fulfilled_sinks": [0.0] * len(CRUST_PROCESS_REASON_ORDER),
                "maximum_surface_packet_count_per_owner": max(
                    (len(owner) for owner in opening_surface),
                    default=0,
                ),
                "maximum_live_reservoir_packet_count": (
                    sum(map(len, opening_surface))
                    + len(opening_mantle)
                    + sum(map(len, opening_slab))
                ),
            }
        else:
            try:
                overlap = plate_step["crust_overlap_ledger"]
                replay = replay_crust_dry_rock_accounting_step(
                    opening_surface_packets=opening_surface,
                    opening_upper_mantle_packets=opening_mantle,
                    opening_subducted_slab_packets=opening_slab,
                    destination_offsets=overlap["destination_offsets"],
                    source_cell_ids=overlap["source_cell_ids"],
                    overlap_area_km2=overlap["overlap_area_km2"],
                    source_requests_kg_by_reason_cell=source_requests,
                    sink_requests_kg_by_reason_cell=sink_requests,
                )
            except (KeyError, TypeError, ValueError, OverflowError) as error:
                failures.append(f"accounting transaction replay failed at step {step_index}: {error}")
                break
            if (
                not _maps_close(transported_surface, replay["transported_surface_packets"])
                or not _maps_close(closing_surface, replay["closing_surface_packets"])
                or not _maps_close([closing_mantle], [replay["closing_upper_mantle_packets"]])
                or not _maps_close(closing_slab, replay["closing_subducted_slab_packets"])
                or not _transfers_close(transfers, replay["transfers"])
            ):
                failures.append(f"accounting packets or ordered transfers differ at step {step_index}")
                break

        reason_records = record["ordered_reason_transactions"]
        if not isinstance(reason_records, list) or len(reason_records) != len(CRUST_PROCESS_REASON_ORDER):
            failures.append(f"accounting reason records are invalid at step {step_index}")
            break
        valid_reasons = True
        for reason, reason_record in enumerate(reason_records):
            expected_reason = {
                "process_reason_id", "process_reason",
                "requested_surface_source_mass_kg", "requested_surface_sink_mass_kg",
                "fulfilled_surface_source_mass_kg", "fulfilled_surface_sink_mass_kg",
                "physical_source_sink_resolved",
            }
            try:
                if not isinstance(reason_record, dict) or set(reason_record) != expected_reason:
                    raise ValueError
                values = [
                    replay["requested_sources"][reason], replay["requested_sinks"][reason],
                    replay["fulfilled_sources"][reason], replay["fulfilled_sinks"][reason],
                ]
                actual = [
                    _finite(reason_record["requested_surface_source_mass_kg"], "requested source"),
                    _finite(reason_record["requested_surface_sink_mass_kg"], "requested sink"),
                    _finite(reason_record["fulfilled_surface_source_mass_kg"], "fulfilled source"),
                    _finite(reason_record["fulfilled_surface_sink_mass_kg"], "fulfilled sink"),
                ]
                if (
                    _integer(reason_record["process_reason_id"], "process reason") != reason
                    or reason_record["process_reason"] != CRUST_PROCESS_REASON_ORDER[reason]
                    or reason_record["physical_source_sink_resolved"] is not False
                    or any(not _close(left, right, terms=tuple(values)) for left, right in zip(actual, values, strict=True))
                    or (reason in (0, 1, 7) and any(value != 0.0 for value in values))
                ):
                    raise ValueError
            except (KeyError, TypeError, ValueError, OverflowError):
                valid_reasons = False
                break
        if not valid_reasons:
            failures.append(f"accounting reason transactions differ at step {step_index}")
            break

        opening_surface_mass = _packet_mass(opening_surface)
        transported_surface_mass = _packet_mass(transported_surface)
        closing_surface_mass = _packet_mass(closing_surface)
        opening_mantle_mass = math.fsum(opening_mantle.values())
        closing_mantle_mass = math.fsum(closing_mantle.values())
        opening_slab_mass = _packet_mass(opening_slab)
        closing_slab_mass = _packet_mass(closing_slab)
        opening_global = opening_surface_mass + opening_mantle_mass + opening_slab_mass
        closing_global = closing_surface_mass + closing_mantle_mass + closing_slab_mass
        opening_origins = _origin_totals(opening_surface, opening_mantle, opening_slab)
        closing_origins = _origin_totals(closing_surface, closing_mantle, closing_slab)
        origin_residual = max((abs(closing_origins.get(key, 0.0) - opening_origins.get(key, 0.0)) for key in set(opening_origins) | set(closing_origins)), default=0.0)
        incoming = [0.0, 0.0, 0.0]
        outgoing = [0.0, 0.0, 0.0]
        for transfer in transfers:
            outgoing[transfer.source_reservoir_id] += transfer.dry_rock_mass_kg
            incoming[transfer.destination_reservoir_id] += transfer.dry_rock_mass_kg
        reservoir_opening = [transported_surface_mass, opening_mantle_mass, opening_slab_mass]
        reservoir_closing = [closing_surface_mass, closing_mantle_mass, closing_slab_mass]
        reservoir_residual = max(abs(reservoir_closing[index] - reservoir_opening[index] - incoming[index] + outgoing[index]) for index in range(3))
        try:
            overlap = plate_step["crust_overlap_ledger"]
            remapped_thickness = overlap["remapped_crust_thickness_km_by_cell"]
            remapped_density = overlap["remapped_crust_density_by_cell"]
            thickness_change = plate_step["crust_thickness_process_change_km_by_cell"]
            density_change = plate_step["crust_density_process_change_by_cell"]
            if any(len(values) != cell_count for values in (remapped_thickness, remapped_density, thickness_change, density_change)):
                raise ValueError
            scalar_cells = [
                areas[cell]
                * (_finite(remapped_thickness[cell], "remapped thickness") + _finite(thickness_change[cell], "thickness change"))
                * (_finite(remapped_density[cell], "remapped density") + _finite(density_change[cell], "density change"))
                * MASS_FACTOR_KG
                for cell in range(cell_count)
            ]
        except (KeyError, TypeError, ValueError, OverflowError):
            failures.append(f"accounting scalar replay inputs are invalid at step {step_index}")
            break
        scalar_mass = math.fsum(scalar_cells)
        cell_scalar_residual = max((abs(math.fsum(closing_surface[cell].values()) - scalar_cells[cell]) for cell in range(cell_count)), default=0.0)
        requested_source = math.fsum(replay["requested_sources"])
        requested_sink = math.fsum(replay["requested_sinks"])
        fulfilled_source = math.fsum(replay["fulfilled_sources"])
        fulfilled_sink = math.fsum(replay["fulfilled_sinks"])
        expected_scalars = {
            "surface_state_envelope_capacity_kg": capacity,
            "total_control_volume_area_km2": total_area,
            "opening_surface_mass_kg": opening_surface_mass,
            "transported_surface_mass_kg": transported_surface_mass,
            "closing_surface_mass_kg": closing_surface_mass,
            "opening_upper_mantle_mass_kg": opening_mantle_mass,
            "closing_upper_mantle_mass_kg": closing_mantle_mass,
            "opening_subducted_slab_mass_kg": opening_slab_mass,
            "closing_subducted_slab_mass_kg": closing_slab_mass,
            "opening_global_mass_kg": opening_global,
            "closing_global_mass_kg": closing_global,
            "source_to_transport_residual_kg": transported_surface_mass - opening_surface_mass,
            "global_accounting_residual_kg": closing_global - opening_global,
            "capacity_initialization_residual_kg": opening_global - capacity,
            "maximum_absolute_origin_closure_residual_kg": origin_residual,
            "maximum_absolute_reservoir_transfer_residual_kg": reservoir_residual,
            "closing_scalar_mass_kg": scalar_mass,
            "closing_scalar_mass_residual_kg": closing_surface_mass - scalar_mass,
            "maximum_absolute_cell_closing_scalar_mass_residual_kg": cell_scalar_residual,
            "requested_minus_fulfilled_source_mass_kg": requested_source - fulfilled_source,
            "requested_minus_fulfilled_sink_mass_kg": requested_sink - fulfilled_sink,
        }
        scalar_terms: dict[str, tuple[float, ...]] = {
            "surface_state_envelope_capacity_kg": (total_area, capacity),
            "total_control_volume_area_km2": tuple(areas),
            "opening_surface_mass_kg": (opening_surface_mass,),
            "transported_surface_mass_kg": (transported_surface_mass,),
            "closing_surface_mass_kg": (closing_surface_mass,),
            "opening_upper_mantle_mass_kg": (opening_mantle_mass,),
            "closing_upper_mantle_mass_kg": (closing_mantle_mass,),
            "opening_subducted_slab_mass_kg": (opening_slab_mass,),
            "closing_subducted_slab_mass_kg": (closing_slab_mass,),
            "opening_global_mass_kg": (
                opening_surface_mass, opening_mantle_mass, opening_slab_mass,
            ),
            "closing_global_mass_kg": (
                closing_surface_mass, closing_mantle_mass, closing_slab_mass,
            ),
            "source_to_transport_residual_kg": (
                transported_surface_mass, opening_surface_mass,
            ),
            "global_accounting_residual_kg": (closing_global, opening_global),
            "capacity_initialization_residual_kg": (opening_global, capacity),
            "maximum_absolute_origin_closure_residual_kg": tuple(
                [*opening_origins.values(), *closing_origins.values()]
            ),
            "maximum_absolute_reservoir_transfer_residual_kg": tuple(
                [*reservoir_opening, *reservoir_closing, *incoming, *outgoing]
            ),
            "closing_scalar_mass_kg": tuple(scalar_cells),
            "closing_scalar_mass_residual_kg": (
                closing_surface_mass, scalar_mass,
            ),
            "maximum_absolute_cell_closing_scalar_mass_residual_kg": tuple(
                [
                    *(math.fsum(owner.values()) for owner in closing_surface),
                    *scalar_cells,
                ]
            ),
            "requested_minus_fulfilled_source_mass_kg": (
                requested_source, fulfilled_source,
            ),
            "requested_minus_fulfilled_sink_mass_kg": (
                requested_sink, fulfilled_sink,
            ),
        }
        try:
            scalar_mirrors_close = True
            for field, expected in expected_scalars.items():
                actual = _record_scalar(record, field)
                if field == (
                    "maximum_absolute_cell_closing_scalar_mass_residual_kg"
                ):
                    per_cell_bound = max(
                        (
                            _bound(
                                actual,
                                expected,
                                terms=(
                                    math.fsum(owner.values()),
                                    scalar_cell_mass,
                                ),
                                count=len(owner) + 6,
                            )
                            for owner, scalar_cell_mass in zip(
                                closing_surface,
                                scalar_cells,
                                strict=True,
                            )
                        ),
                        default=1.0e-3,
                    )
                    if abs(actual - expected) > per_cell_bound:
                        scalar_mirrors_close = False
                        break
                elif not _close(
                    actual,
                    expected,
                    terms=scalar_terms[field],
                ):
                    scalar_mirrors_close = False
                    break
        except (KeyError, TypeError, ValueError, OverflowError):
            scalar_mirrors_close = False
        if not scalar_mirrors_close:
            failures.append(f"accounting scalar mirrors differ at step {step_index}")
            break
        expected_counts = {
            "opening_surface_packet_count": sum(map(len, opening_surface)),
            "transported_surface_packet_count": sum(map(len, transported_surface)),
            "closing_surface_packet_count": sum(map(len, closing_surface)),
            "opening_upper_mantle_packet_count": len(opening_mantle),
            "closing_upper_mantle_packet_count": len(closing_mantle),
            "opening_subducted_slab_packet_count": sum(map(len, opening_slab)),
            "closing_subducted_slab_packet_count": sum(map(len, closing_slab)),
            "proxy_compensation_transfer_count": len(transfers),
            "maximum_surface_packet_count_per_owner": replay[
                "maximum_surface_packet_count_per_owner"
            ],
            "maximum_live_reservoir_packet_count": replay[
                "maximum_live_reservoir_packet_count"
            ],
        }
        if any(type(record[field]) is not int or record[field] != expected for field, expected in expected_counts.items()):
            failures.append(f"accounting packet or transfer counts differ at step {step_index}")
            break
        cumulative_requested_source += requested_source
        cumulative_requested_sink += requested_sink
        cumulative_fulfilled_source += fulfilled_source
        cumulative_fulfilled_sink += fulfilled_sink
        maximum_transport_residual = max(maximum_transport_residual, abs(transported_surface_mass - opening_surface_mass))
        previous_record = record

    if not failures:
        summary = world.get("summary")
        try:
            if not isinstance(summary, dict):
                raise ValueError
            counts = {
                "crust_dry_rock_accounting_history_step_count": len(history),
                "total_crust_dry_rock_surface_packet_count": sum(record["opening_surface_packet_count"] + record["transported_surface_packet_count"] + record["closing_surface_packet_count"] for record in history),
                "total_crust_dry_rock_upper_mantle_packet_count": sum(record["opening_upper_mantle_packet_count"] + record["closing_upper_mantle_packet_count"] for record in history),
                "total_crust_dry_rock_subducted_slab_packet_count": sum(record["opening_subducted_slab_packet_count"] + record["closing_subducted_slab_packet_count"] for record in history),
                "total_crust_dry_rock_proxy_transfer_count": sum(record["proxy_compensation_transfer_count"] for record in history),
                "maximum_crust_dry_rock_closing_surface_packet_count_per_step": max(record["closing_surface_packet_count"] for record in history),
                "maximum_crust_dry_rock_closing_upper_mantle_packet_count_per_step": max(record["closing_upper_mantle_packet_count"] for record in history),
                "maximum_crust_dry_rock_proxy_transfer_count_per_step": max(record["proxy_compensation_transfer_count"] for record in history),
                "maximum_crust_dry_rock_closing_reservoir_packet_count_per_step": max(record["closing_surface_packet_count"] + record["closing_upper_mantle_packet_count"] + record["closing_subducted_slab_packet_count"] for record in history),
                "maximum_crust_dry_rock_surface_packet_count_per_owner": max(record["maximum_surface_packet_count_per_owner"] for record in history),
                "maximum_crust_dry_rock_live_reservoir_packet_count_per_step": max(record["maximum_live_reservoir_packet_count"] for record in history),
            }
            if set(counts) != SUMMARY_COUNT_FIELDS or any(type(summary.get(field)) is not int or summary[field] != value for field, value in counts.items()):
                raise ValueError
            mass_values = {
                "cumulative_crust_dry_rock_requested_surface_source_mass_kg": cumulative_requested_source,
                "cumulative_crust_dry_rock_requested_surface_sink_mass_kg": cumulative_requested_sink,
                "cumulative_crust_dry_rock_fulfilled_surface_source_mass_kg": cumulative_fulfilled_source,
                "cumulative_crust_dry_rock_fulfilled_surface_sink_mass_kg": cumulative_fulfilled_sink,
                "minimum_crust_dry_rock_closing_upper_mantle_mass_kg": min(record["closing_upper_mantle_mass_kg"] for record in history),
                "maximum_crust_dry_rock_closing_subducted_slab_mass_kg": max(record["closing_subducted_slab_mass_kg"] for record in history),
                "maximum_absolute_crust_dry_rock_global_accounting_residual_kg": max(abs(record["global_accounting_residual_kg"]) for record in history),
                "maximum_absolute_crust_dry_rock_origin_closure_residual_kg": max(abs(record["maximum_absolute_origin_closure_residual_kg"]) for record in history),
                "maximum_absolute_crust_dry_rock_reservoir_transfer_residual_kg": max(abs(record["maximum_absolute_reservoir_transfer_residual_kg"]) for record in history),
                "maximum_crust_dry_rock_closing_scalar_relative_residual": max(abs(record["closing_scalar_mass_residual_kg"]) / max(1.0, abs(record["closing_scalar_mass_kg"])) for record in history),
            }
            if set(mass_values) != SUMMARY_MASS_FIELDS:
                raise ValueError
            relative_field = (
                "maximum_crust_dry_rock_closing_scalar_relative_residual"
            )
            for field, expected in mass_values.items():
                actual = _finite(summary.get(field), field)
                if field == relative_field:
                    # This mirror is dimensionless.  It must never inherit the
                    # kilogram-scale forward-error bound used by the other
                    # summary fields.  The native value is emitted with
                    # max_digits10; a small absolute allowance covers the
                    # independently reordered binary64 quotient only.
                    if abs(actual - expected) > max(
                        5.1e-18,
                        128.0 * math.ulp(max(abs(actual), abs(expected))),
                    ):
                        raise ValueError
                elif not _close(actual, expected, terms=(expected,)):
                    raise ValueError
        except (KeyError, TypeError, ValueError, OverflowError):
            failures.append("crust dry-rock accounting summary mirrors are invalid")

    return {
        "passed": not failures,
        "failures": failures,
        "metrics": {
            "history_step_count": len(history),
            "capacity_kg": capacity,
            "cumulative_requested_source_mass_kg": cumulative_requested_source,
            "cumulative_requested_sink_mass_kg": cumulative_requested_sink,
            "maximum_absolute_transport_replay_residual_kg": maximum_transport_residual,
        },
    }


__all__ = [
    "CAPACITY_DENSITY_G_CM3",
    "CAPACITY_THICKNESS_KM",
    "MASS_FACTOR_KG",
    "MAX_LIVE_RESERVOIR_PACKETS",
    "MAX_PROXY_TRANSFERS_PER_STEP",
    "MAX_SURFACE_PACKETS_PER_OWNER",
    "MODEL_LITERAL_VALUES",
    "PacketKey",
    "replay_crust_dry_rock_accounting_step",
    "validate_crust_dry_rock_accounting",
]
