from __future__ import annotations

import math
from typing import Any

from .crust_process_validation import (
    CRUST_PROCESS_REASON_ORDER,
    _final_crust_alias_binary64_bound,
    validate_crust_process_reason_ledger,
)


CRUST_OVERLAP_FORMAT = "destination_csr_spherical_forward_overlap_v1"
CRUST_COVERAGE_MODEL = (
    "destination_local_gnomonic_line_arrangement_multiplicity_v1"
)
CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_MODEL = (
    "coalesced_destination_source_membership_area_classes_v1"
)
CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_LEDGER_FORMAT = (
    "destination_membership_area_class_csr_with_class_contributor_csr_v1"
)
CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_ORDER = (
    "destination_id_then_multiplicity_then_source_cell_ids"
)
CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_COALESCING_KEY = (
    "sorted_contributing_source_cell_ids"
)
CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_REPRESENTATIVE_MODEL = (
    "largest_atomic_arrangement_piece_unprojected_vertex_mean_lowest_xyz_"
    "tie_v1"
)
CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_REPRESENTATIVE_AVAILABLE_SEMANTICS = (
    "one_for_every_v1_membership_area_class_zero_reserved_for_future_"
    "unavailable_representatives"
)
CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_SOURCE_PLATE_SEMANTICS = (
    "source_cell_plate_id_at_transport_source_snapshot"
)
CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_EDGE_TOLERANCE_BASIS = (
    "max_1e-7_km2_or_destination_control_volume_area_km2_times_5e-10"
)
CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_RAW_FRAGMENT_COUNT_LOCATION = (
    "sibling_coverage_arrangement_fragment_count_by_cell"
)
CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_LEDGER_KEYS = frozenset(
    {
        "format",
        "model",
        "class_order",
        "coalescing_key",
        "representative_model",
        "representative_available_semantics",
        "source_plate_id_semantics",
        "edge_area_reconstruction_tolerance_basis",
        "raw_arrangement_fragment_count_location",
        "area_unit",
        "destination_offsets",
        "area_km2",
        "multiplicity",
        "representative_unit_x",
        "representative_unit_y",
        "representative_unit_z",
        "representative_available",
        "contributor_offsets",
        "source_cell_ids",
        "source_plate_ids",
        "source_membership_resolved",
        "connected_fragment_topology_resolved",
        "physical_fate_resolved",
        "slab_selection_resolved",
        "local_kinematics_resolved",
    }
)
CRUST_EXTENSIVE_FIELDS = (
    "crust_volume_km3",
    "density_weighted_crust_volume",
    "crust_age_volume_moment_km3_ma",
)


def _close(first: float, second: float, *, relative: float = 2.0e-9) -> bool:
    return math.isclose(
        first,
        second,
        rel_tol=relative,
        abs_tol=max(1.0e-8, relative * max(abs(first), abs(second))),
    )


def _legacy_close(first: float, second: float) -> bool:
    return math.isclose(first, second, rel_tol=2.0e-8, abs_tol=2.0e-6)


def _ulp_close(first: float, second: float, *, ulps: float = 64.0) -> bool:
    scale = max(abs(first), abs(second))
    return abs(first - second) <= max(1.0e-8, ulps * math.ulp(scale))


def _two_operation_identity_bound(*operands: float) -> float:
    """Forward bound for one exported add/add-or-subtract identity.

    The native destination-partition diagnostic is the maximum of three
    residuals.  Only two of those residuals can be reconstructed from the
    serialized aggregate columns; the third uses an unexported ordered sum of
    raw arrangement atoms.  This bound is therefore used for the one-sided
    comparison that the native maximum must dominate, not to pretend that the
    two maxima are equal.
    """

    epsilon_product = 2.0 * math.ulp(1.0)
    gamma = epsilon_product / (1.0 - epsilon_product)
    absolute_sum = math.fsum(abs(value) for value in operands)
    scale = max((abs(value) for value in operands), default=0.0)
    return gamma * absolute_sum + 4.0 * math.ulp(scale)


def _atomic_partition_error_upper_bound(
    destination_area_km2: float,
    coalesced_class_areas_km2: list[float],
    fragment_count: int,
) -> float:
    """Bound the unexported sequential sum of raw arrangement fragments.

    Native code also coalesces those same positive binary64 fragment areas by
    membership class with a compensated accumulator whose precision is at
    least binary64, then exports each class sum.  Treating that compensated
    path conservatively as four rounded binary64 operations per fragment and
    the raw path as one rounded addition per fragment encloses the missing
    third closure term without accepting the much looser physical safety cap.
    """

    if not 1 <= fragment_count <= 16_384 or not coalesced_class_areas_km2:
        raise ValueError("atomic partition bound inputs are invalid")
    if any(
        not math.isfinite(area) or area <= 0.0
        for area in coalesced_class_areas_km2
    ):
        raise ValueError("coalesced partition areas are invalid")

    epsilon = math.ulp(1.0)

    def gamma(operation_count: int) -> float:
        product = operation_count * epsilon
        if product >= 1.0:
            raise ValueError("atomic partition operation bound overflowed")
        return product / (1.0 - product)

    class_total = math.fsum(coalesced_class_areas_km2)
    class_serialization_rounding = math.fsum(
        0.5 * math.ulp(area) for area in coalesced_class_areas_km2
    ) + 0.5 * math.ulp(class_total)
    class_delta = gamma(4 * fragment_count)
    raw_delta = gamma(max(0, fragment_count - 1))
    exact_atom_total_upper = (
        class_total + class_serialization_rounding
    ) / (1.0 - class_delta)
    return (
        abs(class_total - destination_area_km2)
        + (class_delta + raw_delta) * exact_atom_total_upper
        + class_serialization_rounding
        + 4.0 * math.ulp(max(class_total, destination_area_km2))
    )


def _exact_float(value: Any, expected: float) -> bool:
    try:
        return math.isclose(
            float(value), expected, rel_tol=0.0, abs_tol=0.0
        )
    except (TypeError, ValueError, OverflowError):
        return False


def _integer_array(container: dict[str, Any], field: str) -> list[int]:
    values = container[field]
    if not isinstance(values, list) or any(type(value) is not int for value in values):
        raise TypeError(f"{field} must be an integer array")
    return values


def _finite_numeric_array(container: dict[str, Any], field: str) -> list[float]:
    values = container[field]
    if not isinstance(values, list) or any(
        type(value) not in (int, float) for value in values
    ):
        raise TypeError(f"{field} must be a numeric array")
    converted = [float(value) for value in values]
    if any(not math.isfinite(value) for value in converted):
        raise ValueError(f"{field} must contain only finite values")
    return converted


def _membership_area_class_tolerance(
    actual: float,
    expected: float,
    term_count: int,
    *,
    absolute_floor: float = 1.0e-7,
) -> float:
    """Mirror native closure bounds while covering replay summation error."""

    scale = 1.0 + abs(actual) + abs(expected)
    return max(
        absolute_floor,
        max(abs(actual), abs(expected)) * 5.0e-10,
        8.0 * math.ulp(1.0) * max(1, term_count) * scale,
    )


def _coverage_membership_area_class_values(
    payload: Any,
) -> dict[str, Any]:
    if (
        not isinstance(payload, dict)
        or set(payload) != CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_LEDGER_KEYS
    ):
        raise TypeError(
            "coverage membership-area-class ledger has an invalid schema"
        )
    if (
        payload["format"]
        != CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_LEDGER_FORMAT
        or payload["model"] != CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_MODEL
        or payload["class_order"]
        != CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_ORDER
        or payload["coalescing_key"]
        != CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_COALESCING_KEY
        or payload["representative_model"]
        != CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_REPRESENTATIVE_MODEL
        or payload["representative_available_semantics"]
        != CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_REPRESENTATIVE_AVAILABLE_SEMANTICS
        or payload["source_plate_id_semantics"]
        != CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_SOURCE_PLATE_SEMANTICS
        or payload["edge_area_reconstruction_tolerance_basis"]
        != CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_EDGE_TOLERANCE_BASIS
        or payload["raw_arrangement_fragment_count_location"]
        != CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_RAW_FRAGMENT_COUNT_LOCATION
        or payload["area_unit"] != "km2"
        or payload["source_membership_resolved"] is not True
        or payload["connected_fragment_topology_resolved"] is not False
        or payload["physical_fate_resolved"] is not False
        or payload["slab_selection_resolved"] is not False
        or payload["local_kinematics_resolved"] is not False
    ):
        raise ValueError("coverage membership-area-class semantics are invalid")
    return {
        "destination_offsets": _integer_array(payload, "destination_offsets"),
        "areas": _finite_numeric_array(payload, "area_km2"),
        "multiplicities": _integer_array(payload, "multiplicity"),
        "representative_x": _finite_numeric_array(
            payload, "representative_unit_x"
        ),
        "representative_y": _finite_numeric_array(
            payload, "representative_unit_y"
        ),
        "representative_z": _finite_numeric_array(
            payload, "representative_unit_z"
        ),
        "representative_available": _integer_array(
            payload, "representative_available"
        ),
        "contributor_offsets": _integer_array(payload, "contributor_offsets"),
        "source_cell_ids": _integer_array(payload, "source_cell_ids"),
        "source_plate_ids": _integer_array(payload, "source_plate_ids"),
    }


def _validate_coverage_membership_area_classes(
    payload: Any,
    *,
    cell_areas: list[float],
    destination_offsets: list[int],
    destination_source_ids: list[int],
    overlap_areas: list[float],
    expected_source_plate_ids: list[int],
    membership_area_class_counts: list[int],
    coverage_sums: list[float],
    union_areas: list[float],
    gap_areas: list[float],
    excess_areas: list[float],
    maximum_multiplicities: list[int],
    coverage_histogram: list[float],
) -> dict[str, Any]:
    values = _coverage_membership_area_class_values(payload)
    cell_count = len(cell_areas)
    class_offsets = values["destination_offsets"]
    class_areas = values["areas"]
    multiplicities = values["multiplicities"]
    representative_x = values["representative_x"]
    representative_y = values["representative_y"]
    representative_z = values["representative_z"]
    representative_available = values["representative_available"]
    contributor_offsets = values["contributor_offsets"]
    class_source_ids = values["source_cell_ids"]
    class_source_plate_ids = values["source_plate_ids"]
    class_count = len(class_areas)
    contributor_count = len(class_source_ids)

    if (
        len(expected_source_plate_ids) != cell_count
        or len(destination_offsets) != cell_count + 1
        or len(destination_source_ids) != len(overlap_areas)
        or any(
            len(column) != cell_count
            for column in (
                membership_area_class_counts,
                coverage_sums,
                union_areas,
                gap_areas,
                excess_areas,
                maximum_multiplicities,
            )
        )
        or any(
            not math.isfinite(value) or value < 0.0
            for column in (
                cell_areas,
                overlap_areas,
                coverage_sums,
                union_areas,
                gap_areas,
                excess_areas,
                coverage_histogram,
            )
            for value in column
        )
        or len(class_offsets) != cell_count + 1
        or not class_offsets
        or class_offsets[0] != 0
        or class_offsets[-1] != class_count
        or any(
            left > right
            for left, right in zip(class_offsets, class_offsets[1:])
        )
        or any(offset < 0 for offset in class_offsets)
        or any(
            len(column) != class_count
            for column in (
                multiplicities,
                representative_x,
                representative_y,
                representative_z,
                representative_available,
            )
        )
        or len(contributor_offsets) != class_count + 1
        or not contributor_offsets
        or contributor_offsets[0] != 0
        or contributor_offsets[-1] != contributor_count
        or any(
            left > right
            for left, right in zip(contributor_offsets, contributor_offsets[1:])
        )
        or any(offset < 0 for offset in contributor_offsets)
        or len(class_source_plate_ids) != contributor_count
        or any(multiplicity < 0 for multiplicity in multiplicities)
        or any(value != 1 for value in representative_available)
    ):
        raise ValueError("coverage membership-area-class CSR shape is invalid")

    area_terms_by_multiplicity: list[list[float]] = []
    membership_area_by_destination: list[dict[tuple[int, ...], float]] = []
    maximum_destination_partition_error = 0.0
    maximum_destination_aggregate_error = 0.0
    maximum_edge_reconstruction_error = 0.0
    observed_maximum_multiplicity = 0
    for destination in range(cell_count):
        class_begin = class_offsets[destination]
        class_end = class_offsets[destination + 1]
        if (
            class_end - class_begin
            != membership_area_class_counts[destination]
            or class_begin == class_end
        ):
            raise ValueError(
                "coverage membership-area-class destination offsets are invalid"
            )
        edge_begin = destination_offsets[destination]
        edge_end = destination_offsets[destination + 1]
        row_source_ids = destination_source_ids[edge_begin:edge_end]
        row_source_index = {
            source_id: edge_begin + index
            for index, source_id in enumerate(row_source_ids)
        }
        reconstructed_edge_area_terms: list[list[float]] = [
            [] for _ in row_source_ids
        ]
        destination_partition_terms: list[float] = []
        gap_terms: list[float] = []
        union_terms: list[float] = []
        excess_terms: list[float] = []
        coverage_terms: list[float] = []
        membership_area_terms: dict[tuple[int, ...], list[float]] = {}
        previous_order_key: tuple[Any, ...] | None = None
        destination_maximum_multiplicity = 0
        for area_class in range(class_begin, class_end):
            area = class_areas[area_class]
            multiplicity = multiplicities[area_class]
            contributor_begin = contributor_offsets[area_class]
            contributor_end = contributor_offsets[area_class + 1]
            contributors = class_source_ids[contributor_begin:contributor_end]
            contributor_plates = class_source_plate_ids[
                contributor_begin:contributor_end
            ]
            representative = (
                representative_x[area_class],
                representative_y[area_class],
                representative_z[area_class],
            )
            invalid_membership_reasons: list[str] = []
            if area <= 0.0:
                invalid_membership_reasons.append(
                    f"nonpositive area {area:.17g}"
                )
            if contributor_end - contributor_begin != multiplicity:
                invalid_membership_reasons.append(
                    "contributor count "
                    f"{contributor_end - contributor_begin} != multiplicity "
                    f"{multiplicity}"
                )
            if contributors != sorted(set(contributors)):
                invalid_membership_reasons.append(
                    "contributors are not sorted and unique"
                )
            invalid_source_ids = [
                source_id
                for source_id in contributors
                if not 0 <= source_id < cell_count
            ]
            if invalid_source_ids:
                invalid_membership_reasons.append(
                    f"out-of-range source IDs {invalid_source_ids}"
                )
            missing_row_source_ids = [
                source_id
                for source_id in contributors
                if source_id not in row_source_index
            ]
            if missing_row_source_ids:
                invalid_membership_reasons.append(
                    "source IDs absent from overlap row "
                    f"{missing_row_source_ids}; row={row_source_ids}"
                )
            plate_mismatches = [
                (source_id, plate_id, expected_source_plate_ids[source_id])
                for source_id, plate_id in zip(
                    contributors, contributor_plates, strict=True
                )
                if 0 <= source_id < cell_count
                and plate_id != expected_source_plate_ids[source_id]
            ]
            if plate_mismatches:
                invalid_membership_reasons.append(
                    "(source, recorded plate, expected plate) mismatches "
                    f"{plate_mismatches}"
                )
            if invalid_membership_reasons:
                raise ValueError(
                    "coverage membership-area-class source membership is invalid "
                    f"at destination {destination}, class {area_class}: "
                    + "; ".join(invalid_membership_reasons)
                )
            order_key = (multiplicity, tuple(contributors))
            if previous_order_key is not None and order_key <= previous_order_key:
                raise ValueError(
                    "coverage membership-area classes are not canonical and unique"
                )
            previous_order_key = order_key

            representative_norm = math.sqrt(
                math.fsum(component * component for component in representative)
            )
            if not math.isclose(
                representative_norm, 1.0, rel_tol=0.0, abs_tol=2.0e-12
            ):
                raise ValueError(
                    "coverage membership-area-class representative is invalid"
                )

            for source_id in contributors:
                row_index = row_source_index[source_id] - edge_begin
                reconstructed_edge_area_terms[row_index].append(area)
            destination_partition_terms.append(area)
            if multiplicity == 0:
                gap_terms.append(area)
            else:
                union_terms.append(area)
            if multiplicity >= 2:
                excess_terms.append((multiplicity - 1) * area)
            coverage_terms.append(multiplicity * area)
            while len(area_terms_by_multiplicity) <= multiplicity:
                area_terms_by_multiplicity.append([])
            area_terms_by_multiplicity[multiplicity].append(area)
            membership_area_terms.setdefault(tuple(contributors), []).append(area)
            destination_maximum_multiplicity = max(
                destination_maximum_multiplicity, multiplicity
            )
            observed_maximum_multiplicity = max(
                observed_maximum_multiplicity, multiplicity
            )

        destination_partition_area = math.fsum(destination_partition_terms)
        destination_partition_error = abs(
            destination_partition_area - cell_areas[destination]
        )
        maximum_destination_partition_error = max(
            maximum_destination_partition_error, destination_partition_error
        )
        if destination_partition_error > _membership_area_class_tolerance(
            destination_partition_area,
            cell_areas[destination],
            len(destination_partition_terms),
        ):
            raise ValueError(
                "coverage membership-area-class destination area did not close"
            )
        if destination_maximum_multiplicity != maximum_multiplicities[destination]:
            raise ValueError(
                "coverage membership-area-class maximum multiplicity is invalid"
            )

        reconstructed_aggregates = (
            math.fsum(coverage_terms),
            math.fsum(union_terms),
            math.fsum(gap_terms),
            math.fsum(excess_terms),
        )
        recorded_aggregates = (
            coverage_sums[destination],
            union_areas[destination],
            gap_areas[destination],
            excess_areas[destination],
        )
        aggregate_term_counts = (
            len(coverage_terms),
            len(union_terms),
            len(gap_terms),
            len(excess_terms),
        )
        for reconstructed, recorded, term_count in zip(
            reconstructed_aggregates,
            recorded_aggregates,
            aggregate_term_counts,
            strict=True,
        ):
            error = abs(reconstructed - recorded)
            maximum_destination_aggregate_error = max(
                maximum_destination_aggregate_error, error
            )
            tolerance = max(
                _membership_area_class_tolerance(
                    reconstructed, recorded, term_count
                ),
                cell_areas[destination] * 5.0e-10,
            )
            if error > tolerance:
                raise ValueError(
                    "coverage membership-area-class destination aggregate is invalid"
                )

        for row_index, terms in enumerate(reconstructed_edge_area_terms):
            edge_index = edge_begin + row_index
            reconstructed = math.fsum(terms)
            recorded = overlap_areas[edge_index]
            error = abs(reconstructed - recorded)
            maximum_edge_reconstruction_error = max(
                maximum_edge_reconstruction_error, error
            )
            tolerance = max(
                _membership_area_class_tolerance(
                    reconstructed, recorded, len(terms)
                ),
                cell_areas[destination] * 5.0e-10,
            )
            if error > tolerance:
                raise ValueError(
                    "coverage membership-area-class source overlap did not close"
                )
        membership_area_by_destination.append(
            {
                membership: math.fsum(terms)
                for membership, terms in membership_area_terms.items()
            }
        )

    if observed_maximum_multiplicity != max(maximum_multiplicities, default=0):
        raise ValueError(
            "coverage membership-area-class global maximum multiplicity is invalid"
        )
    histogram_size = max(len(area_terms_by_multiplicity), len(coverage_histogram))
    for multiplicity in range(histogram_size):
        terms = (
            area_terms_by_multiplicity[multiplicity]
            if multiplicity < len(area_terms_by_multiplicity)
            else []
        )
        reconstructed = math.fsum(terms)
        recorded = (
            coverage_histogram[multiplicity]
            if multiplicity < len(coverage_histogram)
            else 0.0
        )
        if abs(reconstructed - recorded) > _membership_area_class_tolerance(
            reconstructed,
            recorded,
            len(terms),
            absolute_floor=1.0e-6,
        ):
            raise ValueError(
                "coverage membership-area-class multiplicity histogram is invalid"
            )

    return {
        "class_count": class_count,
        "contributor_count": contributor_count,
        "maximum_destination_partition_error_km2": (
            maximum_destination_partition_error
        ),
        "maximum_destination_aggregate_error_km2": (
            maximum_destination_aggregate_error
        ),
        "maximum_edge_reconstruction_error_km2": (
            maximum_edge_reconstruction_error
        ),
        "membership_area_by_destination": membership_area_by_destination,
        "values": values,
    }


def _dominant_crust_category_pair(
    category_pair_volumes: list[list[float]],
) -> tuple[int, int]:
    """Select the joint volume mode with the native deterministic tie-break."""

    dominant_type = 0
    dominant_lithology = 0
    dominant_volume = -1.0
    for crust_type, lithology_volumes in enumerate(category_pair_volumes):
        for lithology, volume in enumerate(lithology_volumes):
            if volume > dominant_volume:
                dominant_volume = volume
                dominant_type = crust_type
                dominant_lithology = lithology
    return dominant_type, dominant_lithology


def _inventory(
    areas: list[float],
    thicknesses: list[float],
    densities: list[float],
    ages: list[float],
) -> tuple[float, float, float]:
    volumes = [area * thickness for area, thickness in zip(areas, thicknesses)]
    return (
        math.fsum(volumes),
        math.fsum(volume * density for volume, density in zip(volumes, densities)),
        math.fsum(volume * age for volume, age in zip(volumes, ages)),
    )


def _extensive_values(record: Any) -> tuple[float, float, float]:
    if not isinstance(record, dict) or set(record) != set(CRUST_EXTENSIVE_FIELDS):
        raise TypeError("crust extensive record has an invalid schema")
    values = tuple(float(record[field]) for field in CRUST_EXTENSIVE_FIELDS)
    if any(not math.isfinite(value) for value in values):
        raise ValueError("crust extensive record must be finite")
    return values


def _process_attribution_values(
    attribution: Any,
    cell_count: int,
) -> dict[str, Any]:
    expected_keys = {
        "format",
        "semantics",
        "order_dependent",
        "reasons",
        "attributed_inventory_delta",
        "numerical_closure_residual",
        "reconciled_inventory_delta",
    }
    if not isinstance(attribution, dict) or set(attribution) != expected_keys:
        raise TypeError("crust process attribution has an invalid schema")
    if (
        attribution["format"] != "sequential_rule_extensive_state_delta_v1"
        or attribution["semantics"]
        != "ordered_rule_state_moment_changes_not_physical_material_provenance"
        or attribution["order_dependent"] is not True
    ):
        raise ValueError("crust process attribution semantics are invalid")
    reason_payload = attribution["reasons"]
    if not isinstance(reason_payload, list) or len(reason_payload) != len(
        CRUST_PROCESS_REASON_ORDER
    ):
        raise TypeError("crust process reason array has an invalid shape")

    reason_records: list[dict[str, Any]] = []
    for expected_reason, record in zip(
        CRUST_PROCESS_REASON_ORDER,
        reason_payload,
        strict=True,
    ):
        if not isinstance(record, dict) or set(record) != {
            "reason",
            "triggered_cell_count",
            "extensive_state_changed_cell_count",
            "positive_delta",
            "negative_delta_magnitude",
            "net_delta",
        }:
            raise TypeError("crust process reason record has an invalid schema")
        triggered = record["triggered_cell_count"]
        changed = record["extensive_state_changed_cell_count"]
        if (
            record["reason"] != expected_reason
            or type(triggered) is not int
            or type(changed) is not int
            or not 0 <= changed <= triggered <= cell_count
        ):
            raise ValueError("crust process reason identity or counts are invalid")
        positive = _extensive_values(record["positive_delta"])
        negative = _extensive_values(record["negative_delta_magnitude"])
        net = _extensive_values(record["net_delta"])
        if any(value < 0.0 for value in positive + negative):
            raise ValueError("crust process signed magnitudes must be nonnegative")
        for component in range(len(CRUST_EXTENSIVE_FIELDS)):
            if net[component] != positive[component] - negative[component]:
                raise ValueError("crust process positive/negative record does not reconcile")
        reason_records.append(
            {
                "reason": expected_reason,
                "triggered_cell_count": triggered,
                "extensive_state_changed_cell_count": changed,
                "positive": positive,
                "negative": negative,
                "net": net,
            }
        )

    attributed = _extensive_values(attribution["attributed_inventory_delta"])
    residual = _extensive_values(attribution["numerical_closure_residual"])
    reconciled = _extensive_values(attribution["reconciled_inventory_delta"])
    summed_net_values = [0.0] * len(CRUST_EXTENSIVE_FIELDS)
    for record in reason_records:
        for component in range(len(CRUST_EXTENSIVE_FIELDS)):
            summed_net_values[component] += record["net"][component]
    summed_net = tuple(summed_net_values)
    if any(
        not _ulp_close(actual, expected)
        for actual, expected in zip(attributed, summed_net, strict=True)
    ) or any(
        not _ulp_close(actual, net + closure)
        for actual, net, closure in zip(
            reconciled,
            attributed,
            residual,
            strict=True,
        )
    ):
        raise ValueError("crust process attributed totals do not reconcile")
    return {
        "reasons": reason_records,
        "attributed": attributed,
        "residual": residual,
        "reconciled": reconciled,
    }


def _rotate_vector(
    vector: tuple[float, float, float],
    axis: tuple[float, float, float],
    angle_deg: float,
) -> tuple[float, float, float]:
    angle = math.radians(angle_deg)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    dot_product = math.fsum(
        component * axis_component
        for component, axis_component in zip(vector, axis, strict=True)
    )
    cross_product = (
        axis[1] * vector[2] - axis[2] * vector[1],
        axis[2] * vector[0] - axis[0] * vector[2],
        axis[0] * vector[1] - axis[1] * vector[0],
    )
    return tuple(
        vector[index] * cosine
        + cross_product[index] * sine
        + axis[index] * dot_product * (1.0 - cosine)
        for index in range(3)
    )


def _surface_distance_km(
    first: tuple[float, float, float],
    second: tuple[float, float, float],
    radius_km: float,
) -> float:
    if first == second:
        return 0.0
    first_norm = math.sqrt(math.fsum(component * component for component in first))
    second_norm = math.sqrt(
        math.fsum(component * component for component in second)
    )
    cosine = max(
        -1.0,
        min(
            1.0,
            math.fsum(
                first_component * second_component
                for first_component, second_component in zip(
                    first, second, strict=True
                )
            )
            / (first_norm * second_norm),
        ),
    )
    return math.acos(cosine) * radius_km


def validate_crust_overlap_transport(world: dict[str, Any]) -> dict[str, Any]:
    """Replay every sparse overlap ledger and its transported extensive state."""

    failures: list[str] = []
    process_replay = validate_crust_process_reason_ledger(world)
    failures.extend(
        f"crust process replay: {failure}"
        for failure in process_replay["failures"]
    )
    model = world.get("plate_kinematic_model", {})
    backend = world.get("backend", {})
    history = world.get("plate_motion_history", [])
    cells = world.get("cells", [])
    if (
        not isinstance(model, dict)
        or not isinstance(history, list)
        or not history
        or not isinstance(cells, list)
        or not cells
    ):
        return {
            "passed": False,
            "failures": ["crust transport model, history, or cells are missing"],
            "metrics": {},
        }
    if (
        model.get("model_type") != "rotating_voronoi_plate_domains_v3"
        or model.get("crust_memory_model")
        != "plate_attached_conservative_extensive_mixture_v1"
        or model.get("crust_transport_model")
        != "forward_spherical_control_volume_overlap_v1"
        or model.get("crust_transport_ledger_format") != CRUST_OVERLAP_FORMAT
        or model.get("crust_transport_positive_area_serialization_model")
        != "general_format_max_digits10_binary64_round_trip_v1"
        or model.get("crust_transport_coverage_model") != CRUST_COVERAGE_MODEL
        or model.get("crust_transport_coverage_histogram_model")
        != "global_area_by_integer_source_multiplicity_v1"
        or model.get("crust_transport_coverage_membership_area_class_model")
        != CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_MODEL
        or model.get(
            "crust_transport_coverage_membership_area_class_ledger_format"
        )
        != CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_LEDGER_FORMAT
        or model.get("crust_transport_coverage_membership_area_class_order")
        != CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_ORDER
        or model.get(
            "crust_transport_coverage_membership_area_class_coalescing_key"
        )
        != CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_COALESCING_KEY
        or model.get(
            "crust_transport_coverage_membership_area_class_representative_model"
        )
        != CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_REPRESENTATIVE_MODEL
        or model.get(
            "crust_transport_coverage_membership_area_class_source_plate_id_semantics"
        )
        != CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_SOURCE_PLATE_SEMANTICS
        or model.get(
            "crust_transport_coverage_membership_area_class_edge_area_reconstruction_tolerance_basis"
        )
        != CRUST_COVERAGE_MEMBERSHIP_AREA_CLASS_EDGE_TOLERANCE_BASIS
        or model.get(
            "crust_transport_coverage_membership_area_class_source_membership_resolved"
        )
        is not True
        or model.get(
            "crust_transport_coverage_membership_area_class_connected_fragment_topology_resolved"
        )
        is not False
        or model.get(
            "crust_transport_coverage_membership_area_class_physical_fate_resolved"
        )
        is not False
        or model.get(
            "crust_transport_coverage_membership_area_class_slab_selection_resolved"
        )
        is not False
        or model.get(
            "crust_transport_coverage_membership_area_class_local_kinematics_resolved"
        )
        is not False
        or model.get("crust_categorical_remap_model")
        != "joint_crust_type_lithology_dominant_incoming_volume_v1"
        or model.get("crust_categorical_remap_tie_break")
        != "lowest_crust_type_then_lowest_lithology"
        or model.get("oceanic_state_classification_model")
        != "crust_type_with_transitional_lithology_provenance_and_arc_numeric_guard_v2"
        or model.get("transitional_oceanic_provenance_rule")
        != "crust_type_2_is_oceanic_iff_lithology_0_basalt"
        or model.get("volcanic_arc_oceanic_state_rule")
        != "crust_type_3_is_oceanic_iff_age_le_320_ma_thickness_le_18_km_density_ge_2_84"
        or model.get("crust_transport_coverage_arrangement_fragment_limit")
        != 16384
        or model.get("crust_density_unit") != "g_cm3"
        or model.get("density_weighted_crust_volume_unit") != "g_cm3_km3"
        or not _exact_float(
            model.get("density_weighted_crust_volume_to_mass_kg_factor"),
            1.0e12,
        )
        or model.get("crust_volume_conserving_transport") is not True
        or model.get("density_weighted_volume_conserving_transport") is not True
        or model.get("crust_age_volume_moment_conserving_transport") is not True
        or model.get("mass_conserving_crust_transport") is not True
        or model.get("mass_conservation_scope")
        != "transport_only_before_rule_based_tectonic_processes"
        or model.get("crust_advection_resolved") is not True
        or model.get("destination_overlap_areas_normalized") is not False
        or model.get("tectonic_process_inventory_changes_separately_ledgered")
        is not True
        or model.get("crust_transport_execution_backend") != "cpu"
        or model.get("accelerator_crust_source_remap_kernel_used") is not False
        or model.get("tectonic_process_inventory_ledger_granularity")
        != "transported_post_and_rule_reason_positive_negative_per_step_v2"
        or model.get("tectonic_process_reason_resolved_inventory_ledgered")
        is not True
        or model.get("tectonic_process_inventory_ledger_scope")
        != "transported_pre_process_to_post_process_with_sequential_rule_attribution"
        or model.get("tectonic_process_inventory_attribution_format")
        != "sequential_rule_extensive_state_delta_v1"
        or model.get("tectonic_process_rule_model")
        != "ordered_thresholded_crust_state_transition_v2"
        or tuple(model.get("tectonic_process_inventory_reason_order", ()))
        != CRUST_PROCESS_REASON_ORDER
        or model.get("tectonic_process_boundary_input_locations")
        != [
            "plate_motion_history[].boundary_convergent_by_cell",
            "plate_motion_history[].boundary_divergent_by_cell",
            "plate_motion_history[].boundary_transform_by_cell",
        ]
        or model.get("tectonic_process_rule_state_source_sink_accounting_resolved")
        is not True
        or model.get("tectonic_process_source_sink_attribution_resolved")
        is not False
        or model.get("tectonic_process_source_sink_attribution_semantics")
        != "componentwise_positive_negative_ordered_rule_state_delta_not_physical_material_flux"
        or model.get("tectonic_process_material_provenance_resolved") is not False
        or model.get("tectonic_process_attribution_order_dependent") is not True
        or model.get("tectonic_process_changed_cell_count_semantics")
        != "numeric_age_thickness_density_change_only_excludes_categorical_transitions"
        or model.get("oceanic_convergence_subduction_proxy_semantics")
        != "rule_adds_thickness_and_reduces_age_not_a_crust_removal_flux"
        or model.get("plate_crossing_accretion_proxy_semantics")
        != "extra_continental_convergence_thickening_not_external_reservoir_provenance"
        or model.get("legacy_crust_source_cell_id_semantics")
        != "dominant_incoming_crust_volume_contributor_compatibility_alias_v1"
        or model.get("legacy_crust_source_remap_event_semantics")
        != "dominant_contributor_id_differs_from_destination_cell_id"
        or model.get("legacy_crust_source_reuse_count_semantics")
        != "destination_count_minus_unique_dominant_contributor_count"
        or model.get("canonical_crust_mixture_provenance_location")
        != "plate_motion_history[].crust_overlap_ledger"
    ):
        failures.append("conservative crust transport model metadata is invalid")
    try:
        process_internal_heat = float(
            model["tectonic_process_internal_heat_input"]
        )
        process_geological_age_ga = float(
            model["tectonic_process_geological_age_ga_input"]
        )
        serialized_tectonic_activity = float(model["tectonic_activity_index"])
        expected_tectonic_activity = max(
            0.25,
            min(
                2.25,
                process_internal_heat
                * math.sqrt(4.5 / max(0.05, process_geological_age_ga)),
            ),
        )
        if (
            not math.isfinite(process_internal_heat)
            or not math.isfinite(process_geological_age_ga)
            or process_geological_age_ga <= 0.0
            or model.get("tectonic_activity_formula")
            != "clamp(internal_heat*sqrt(4.5/max(0.05,geological_age_ga)),0.25,2.25)"
            or not math.isclose(
                serialized_tectonic_activity,
                expected_tectonic_activity,
                rel_tol=2.0e-12,
                abs_tol=2.0e-12,
            )
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError, OverflowError):
        failures.append("tectonic process input metadata is invalid")
    if (
        not isinstance(backend, dict)
        or backend.get("backend_scope")
        != "accelerated_native_kernels_not_end_to_end_pipeline"
        or backend.get("crust_transport_execution_backend") != "cpu"
        or backend.get("crust_transport_execution_model")
        != "forward_spherical_control_volume_overlap_v1"
        or type(backend.get("crust_transport_accelerator_dispatch_count")) is not int
        or backend.get("crust_transport_accelerator_dispatch_count") != 0
        or type(
            backend.get("cpu_conservative_crust_overlap_transition_count")
        )
        is not int
        or backend.get("cpu_conservative_crust_overlap_transition_count")
        != len(history) - 1
        or backend.get(
            "accelerator_crust_source_remap_kernel_production_active"
        )
        is not False
        or backend.get("accelerator_crust_source_remap_kernel_role")
        != "legacy_nearest_donor_test_hook_not_used_by_v3_transport"
        or backend.get("legacy_nearest_source_remap_world_pipeline_enabled")
        is not False
        or backend.get("legacy_crust_source_remap_dispatch_counters_deprecated")
        is not True
        or type(backend.get("opencl_crust_source_remap_dispatch_count")) is not int
        or backend.get("opencl_crust_source_remap_dispatch_count") != 0
        or type(backend.get("cuda_crust_source_remap_dispatch_count")) is not int
        or backend.get("cuda_crust_source_remap_dispatch_count") != 0
    ):
        failures.append("conservative crust transport backend telemetry is invalid")

    cell_count = len(cells)
    try:
        areas = [float(cell["area_km2"]) for cell in cells]
        positions = [
            tuple(float(component) for component in cell["position_3d"])
            for cell in cells
        ]
        previous_ages = [float(cell["initial_crust_age_ma"]) for cell in cells]
        previous_thicknesses = [
            float(cell["initial_crust_thickness_km"]) for cell in cells
        ]
        previous_densities = [float(cell["initial_crust_density"]) for cell in cells]
        radius_km = math.sqrt(math.fsum(areas) / (4.0 * math.pi))
        plate_payload = world["plates"]
        if not isinstance(plate_payload, list) or not plate_payload:
            raise TypeError("plates must be a non-empty array")
        canonical_plate_axes: list[tuple[float, float, float]] = []
        for expected_plate_id, plate in enumerate(plate_payload):
            if (
                not isinstance(plate, dict)
                or type(plate.get("id")) is not int
                or plate["id"] != expected_plate_id
            ):
                raise TypeError("plate IDs must be canonical integers")
            axis = tuple(float(component) for component in plate["axis"])
            axis_norm = math.sqrt(math.fsum(component * component for component in axis))
            if (
                len(axis) != 3
                or not math.isfinite(axis_norm)
                or not math.isclose(axis_norm, 1.0, rel_tol=0.0, abs_tol=2.0e-12)
            ):
                raise ValueError("canonical plate rotation axis is invalid")
            canonical_plate_axes.append(axis)
    except (KeyError, TypeError, ValueError, OverflowError):
        return {
            "passed": False,
            "failures": failures + ["initial crust state is invalid"],
            "metrics": {},
        }
    if (
        any(len(position) != 3 for position in positions)
        or not math.isfinite(radius_km)
        or radius_km <= 0.0
        or any(
            not math.isfinite(component)
            for position in positions
            for component in position
        )
        or any(
            not math.isclose(
                math.sqrt(math.fsum(component * component for component in position)),
                1.0,
                rel_tol=0.0,
                abs_tol=2.0e-12,
            )
            for position in positions
        )
        or any(
            not math.isfinite(value) or value <= 0.0
            for value in areas + previous_thicknesses + previous_densities
        )
        or any(not math.isfinite(value) or value < 0.0 for value in previous_ages)
    ):
        return {
            "passed": False,
            "failures": failures
            + ["initial crust state is non-finite or out of range"],
            "metrics": {},
        }

    maximum_source_relative_error = 0.0
    maximum_source_absolute_error_km2 = 0.0
    maximum_inventory_relative_error = 0.0
    maximum_destination_identity_error_km2 = 0.0
    maximum_gap_overlap_balance_error_km2 = 0.0
    total_sparse_edge_count = 0
    total_mixed_destination_count = 0
    transition_sparse_edge_count = 0
    transition_mixed_destination_count = 0
    transition_maximum_coverage_multiplicity = 0
    transition_maximum_arrangement_line_count = 0
    transition_maximum_arrangement_fragment_count = 0
    transition_maximum_source_absolute_error_km2 = 0.0
    transition_maximum_source_relative_error = 0.0
    transition_maximum_destination_error_km2 = 0.0
    transition_total_gap_area_km2 = 0.0
    transition_total_excess_area_km2 = 0.0
    transition_maximum_inventory_relative_error = 0.0
    cumulative_absolute_process_volume_change_km3 = 0.0
    net_process_volume_change_km3 = 0.0
    cumulative_absolute_process_density_volume_change_g_cm3_km3 = 0.0
    net_process_density_volume_change_g_cm3_km3 = 0.0
    cumulative_absolute_process_age_moment_change_km3_ma = 0.0
    net_process_age_moment_change_km3_ma = 0.0
    maximum_process_attribution_relative_residual = 0.0
    total_process_reason_record_count = 0
    active_process_reason_record_count = 0
    total_coverage_membership_area_class_count = 0
    total_coverage_membership_area_class_contributor_count = 0
    maximum_membership_area_class_partition_error_km2 = 0.0
    maximum_membership_area_class_aggregate_error_km2 = 0.0
    maximum_membership_area_class_edge_reconstruction_error_km2 = 0.0

    previous_types: list[int] | None = None
    previous_lithologies: list[int] | None = None
    previous_plate_ids: list[int] | None = None
    for step_index, step in enumerate(history):
        if not isinstance(step, dict):
            failures.append(f"plate motion step {step_index} is invalid")
            break
        ledger = step.get("crust_overlap_ledger", {})
        try:
            offsets = _integer_array(ledger, "destination_offsets")
            source_ids = _integer_array(ledger, "source_cell_ids")
            overlap_areas = [float(value) for value in ledger["overlap_area_km2"]]
            residual_distances = [
                float(value) for value in ledger["remap_residual_distance_km"]
            ]
            kinematic_distances = [
                float(value) for value in ledger["source_kinematic_distance_km"]
            ]
            dominant_ids = _integer_array(ledger, "dominant_source_cell_ids")
            contributor_counts = _integer_array(
                ledger, "contributor_count_by_cell"
            )
            dominant_fractions = [
                float(value)
                for value in ledger["dominant_source_volume_fraction_by_cell"]
            ]
            coverage_sums = [
                float(value) for value in ledger["coverage_area_sum_km2_by_cell"]
            ]
            union_areas = [
                float(value) for value in ledger["covered_union_area_km2_by_cell"]
            ]
            gap_areas = [
                float(value) for value in ledger["uncovered_gap_area_km2_by_cell"]
            ]
            excess_areas = [
                float(value) for value in ledger["overlap_excess_area_km2_by_cell"]
            ]
            maximum_multiplicities = _integer_array(
                ledger, "maximum_coverage_multiplicity_by_cell"
            )
            arrangement_line_counts = ledger[
                "coverage_arrangement_line_count_by_cell"
            ]
            arrangement_fragment_counts = ledger[
                "coverage_arrangement_fragment_count_by_cell"
            ]
            if (
                not isinstance(arrangement_line_counts, list)
                or not isinstance(arrangement_fragment_counts, list)
                or any(type(value) is not int for value in arrangement_line_counts)
                or any(
                    type(value) is not int
                    for value in arrangement_fragment_counts
                )
            ):
                raise TypeError("arrangement counts must be integer arrays")
            total_arrangement_line_count = ledger[
                "total_coverage_arrangement_line_count"
            ]
            total_arrangement_fragment_count = ledger[
                "total_coverage_arrangement_fragment_count"
            ]
            if (
                type(total_arrangement_line_count) is not int
                or type(total_arrangement_fragment_count) is not int
            ):
                raise TypeError("arrangement totals must be integers")
            membership_area_class_counts = _integer_array(
                ledger, "coverage_membership_area_class_count_by_cell"
            )
            total_membership_area_class_count = ledger[
                "total_coverage_membership_area_class_count"
            ]
            maximum_membership_area_class_count = ledger[
                "maximum_coverage_membership_area_class_count"
            ]
            if (
                type(total_membership_area_class_count) is not int
                or type(maximum_membership_area_class_count) is not int
            ):
                raise TypeError(
                    "coverage membership-area-class totals must be integers"
                )
            coverage_histogram = [
                float(value)
                for value in ledger[
                    "global_coverage_area_km2_by_multiplicity"
                ]
            ]
            maximum_arrangement_line_count = ledger[
                "maximum_coverage_arrangement_line_count"
            ]
            maximum_arrangement_fragment_count = ledger[
                "maximum_coverage_arrangement_fragment_count"
            ]
            if (
                type(maximum_arrangement_line_count) is not int
                or type(maximum_arrangement_fragment_count) is not int
            ):
                raise TypeError("arrangement maxima must be integers")
            remapped_types = _integer_array(
                ledger, "remapped_crust_type_by_cell"
            )
            remapped_lithologies = _integer_array(
                ledger, "remapped_lithology_by_cell"
            )
            remapped_ages = [
                float(value) for value in ledger["remapped_crust_age_ma_by_cell"]
            ]
            remapped_thicknesses = [
                float(value)
                for value in ledger["remapped_crust_thickness_km_by_cell"]
            ]
            remapped_densities = [
                float(value) for value in ledger["remapped_crust_density_by_cell"]
            ]
            final_types = _integer_array(step, "crust_type_by_cell")
            final_lithologies = _integer_array(step, "lithology_by_cell")
            boundary_convergent = [
                float(value) for value in step["boundary_convergent_by_cell"]
            ]
            boundary_divergent = [
                float(value) for value in step["boundary_divergent_by_cell"]
            ]
            total_age_changes = [
                float(value) for value in step["crust_age_change_ma_by_cell"]
            ]
            total_thickness_changes = [
                float(value) for value in step["crust_thickness_change_km_by_cell"]
            ]
            total_density_changes = [
                float(value) for value in step["crust_density_change_by_cell"]
            ]
            transport_age_changes = [
                float(value)
                for value in step["crust_age_transport_change_ma_by_cell"]
            ]
            transport_thickness_changes = [
                float(value)
                for value in step["crust_thickness_transport_change_km_by_cell"]
            ]
            transport_density_changes = [
                float(value)
                for value in step["crust_density_transport_change_by_cell"]
            ]
            process_age_changes = [
                float(value) for value in step["crust_age_process_change_ma_by_cell"]
            ]
            process_thickness_changes = [
                float(value)
                for value in step["crust_thickness_process_change_km_by_cell"]
            ]
            process_density_changes = [
                float(value)
                for value in step["crust_density_process_change_by_cell"]
            ]
            legacy_dominant_ids = _integer_array(step, "crust_source_cell_ids")
            serialized_transport_distances = [
                float(value)
                for value in step["crust_transport_distance_km_by_cell"]
            ]
            cell_plate_ids = _integer_array(step, "cell_plate_ids")
            plate_snapshots = step["plates"]
            if not isinstance(plate_snapshots, list):
                raise TypeError("plate snapshots must be an array")
            rotation_axes: dict[int, tuple[float, float, float]] = {}
            step_rotations: dict[int, float] = {}
            for snapshot in plate_snapshots:
                if not isinstance(snapshot, dict) or type(snapshot.get("plate_id")) is not int:
                    raise TypeError("plate snapshot IDs must be integers")
                plate_id = snapshot["plate_id"]
                axis = tuple(
                    float(component) for component in snapshot["rotation_axis"]
                )
                if (
                    len(axis) != 3
                    or plate_id in rotation_axes
                    or any(not math.isfinite(component) for component in axis)
                    or not math.isclose(
                        math.sqrt(math.fsum(component * component for component in axis)),
                        1.0,
                        rel_tol=0.0,
                        abs_tol=2.0e-12,
                    )
                    or not 0 <= plate_id < len(canonical_plate_axes)
                    or any(
                        not math.isclose(
                            actual,
                            expected,
                            rel_tol=0.0,
                            abs_tol=2.0e-12,
                        )
                        for actual, expected in zip(
                            axis,
                            canonical_plate_axes[plate_id],
                            strict=True,
                        )
                    )
                ):
                    raise ValueError("plate rotation axis is invalid")
                rotation_axes[plate_id] = axis
                step_rotations[plate_id] = float(snapshot["step_rotation_deg"])
            step_scalar_metrics = {
                field: float(step[field])
                for field in (
                    "mean_plate_rotation_deg",
                    "max_plate_rotation_deg",
                    "mean_crust_transport_distance_km",
                    "max_crust_transport_distance_km",
                    "mean_abs_crust_age_change_ma",
                    "mean_abs_crust_thickness_change_km",
                    "mean_abs_crust_density_change",
                    "mean_abs_crust_age_transport_change_ma",
                    "mean_abs_crust_thickness_transport_change_km",
                    "mean_abs_crust_density_transport_change",
                    "mean_abs_crust_age_process_change_ma",
                    "mean_abs_crust_thickness_process_change_km",
                    "mean_abs_crust_density_process_change",
                )
            }
            step_count_metrics = {
                field: step[field]
                for field in (
                    "crust_source_remap_cell_count",
                    "unique_crust_source_cell_count",
                    "crust_source_reuse_count",
                )
            }
            if any(type(value) is not int for value in step_count_metrics.values()):
                raise TypeError("crust transport scalar counts must be integers")
        except (KeyError, TypeError, ValueError, OverflowError):
            failures.append(f"crust overlap ledger {step_index} has invalid fields")
            break

        per_cell_arrays = (
            dominant_ids,
            contributor_counts,
            dominant_fractions,
            coverage_sums,
            union_areas,
            gap_areas,
            excess_areas,
            maximum_multiplicities,
            arrangement_line_counts,
            arrangement_fragment_counts,
            membership_area_class_counts,
            remapped_types,
            remapped_lithologies,
            remapped_ages,
            remapped_thicknesses,
            remapped_densities,
            final_types,
            final_lithologies,
            boundary_convergent,
            boundary_divergent,
            total_age_changes,
            total_thickness_changes,
            total_density_changes,
            transport_age_changes,
            transport_thickness_changes,
            transport_density_changes,
            process_age_changes,
            process_thickness_changes,
            process_density_changes,
            legacy_dominant_ids,
            serialized_transport_distances,
            cell_plate_ids,
        )
        if (
            not isinstance(ledger, dict)
            or ledger.get("format") != CRUST_OVERLAP_FORMAT
            or ledger.get("coverage_model") != CRUST_COVERAGE_MODEL
            or ledger.get("crust_volume_unit") != "km3"
            or ledger.get("crust_density_unit") != "g_cm3"
            or ledger.get("density_weighted_crust_volume_unit") != "g_cm3_km3"
            or not _exact_float(
                ledger.get("density_weighted_crust_volume_to_mass_kg_factor"),
                1.0e12,
            )
            or ledger.get("crust_age_volume_moment_unit") != "km3_ma"
            or ledger.get("transport_conservation_scope")
            != "source_to_transported_pre_process"
            or ledger.get("post_process_inventory_semantics")
            != "state_snapshot_not_transport_conservation_target"
            or len(offsets) != cell_count + 1
            or offsets[0] != 0
            or offsets[-1] != len(source_ids)
            or any(left > right for left, right in zip(offsets, offsets[1:]))
            or len(overlap_areas) != len(source_ids)
            or len(residual_distances) != len(source_ids)
            or len(kinematic_distances) != cell_count
            or any(len(values) != cell_count for values in per_cell_arrays)
            or any(not 0 <= source_id < cell_count for source_id in source_ids)
            or any(not 0 <= source_id < cell_count for source_id in dominant_ids)
            or any(
                not 0 <= source_id < cell_count
                for source_id in legacy_dominant_ids
            )
            or any(value < 0 for value in contributor_counts)
            or any(value < 0 for value in maximum_multiplicities)
            or any(not 0 <= value < 9 for value in remapped_types + final_types)
            or any(
                not 0 <= value < 7
                for value in remapped_lithologies + final_lithologies
            )
            or any(not 0 <= plate_id < len(plate_snapshots) for plate_id in cell_plate_ids)
            or any(
                not math.isfinite(value) or not 0.0 <= value <= 1.0
                for value in boundary_convergent + boundary_divergent
            )
            or set(rotation_axes) != set(range(len(plate_snapshots)))
            or any(
                not math.isfinite(value)
                for value in step_rotations.values()
            )
            or any(not math.isfinite(value) or value <= 0.0 for value in overlap_areas)
            or any(not math.isfinite(value) or value < 0.0 for value in residual_distances)
            or any(not math.isfinite(value) or value < 0.0 for value in kinematic_distances)
            or len(coverage_histogram) < 2
            or len(coverage_histogram) != max(maximum_multiplicities) + 1
            or coverage_histogram[-1] <= 0.0
            or any(
                not math.isfinite(value) or value < 0.0
                for value in coverage_histogram
            )
            or maximum_arrangement_line_count < 0
            or not 1 <= maximum_arrangement_fragment_count <= 16384
            or maximum_arrangement_line_count != max(arrangement_line_counts)
            or maximum_arrangement_fragment_count
            != max(arrangement_fragment_counts)
            or total_arrangement_line_count != sum(arrangement_line_counts)
            or total_arrangement_fragment_count
            != sum(arrangement_fragment_counts)
            or maximum_membership_area_class_count
            != max(membership_area_class_counts)
            or total_membership_area_class_count
            != sum(membership_area_class_counts)
            or any(value < 0 for value in arrangement_line_counts)
            or any(
                not 1 <= value <= 16384
                for value in arrangement_fragment_counts
            )
            or any(
                not 1 <= class_count <= fragment_count
                for class_count, fragment_count in zip(
                    membership_area_class_counts,
                    arrangement_fragment_counts,
                    strict=True,
                )
            )
            or any(
                contributor_count > 1 and line_count <= 0
                for contributor_count, line_count in zip(
                    contributor_counts, arrangement_line_counts
                )
            )
        ):
            failures.append(f"crust overlap ledger {step_index} shape is invalid")
            break
        if any(
            source_ids[offsets[destination] : offsets[destination + 1]]
            != sorted(set(source_ids[offsets[destination] : offsets[destination + 1]]))
            for destination in range(cell_count)
        ):
            failures.append(f"crust overlap ledger {step_index} CSR is not canonical")
            break

        source_plate_ids = (
            cell_plate_ids if previous_plate_ids is None else previous_plate_ids
        )
        try:
            membership_area_class_replay = _validate_coverage_membership_area_classes(
                ledger["coverage_membership_area_class_ledger"],
                cell_areas=areas,
                destination_offsets=offsets,
                destination_source_ids=source_ids,
                overlap_areas=overlap_areas,
                expected_source_plate_ids=source_plate_ids,
                membership_area_class_counts=membership_area_class_counts,
                coverage_sums=coverage_sums,
                union_areas=union_areas,
                gap_areas=gap_areas,
                excess_areas=excess_areas,
                maximum_multiplicities=maximum_multiplicities,
                coverage_histogram=coverage_histogram,
            )
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            failures.append(
                "crust coverage membership-area-class ledger "
                f"{step_index} is invalid: {exc}"
            )
            break
        total_coverage_membership_area_class_count += (
            membership_area_class_replay["class_count"]
        )
        total_coverage_membership_area_class_contributor_count += (
            membership_area_class_replay["contributor_count"]
        )
        maximum_membership_area_class_partition_error_km2 = max(
            maximum_membership_area_class_partition_error_km2,
            membership_area_class_replay[
                "maximum_destination_partition_error_km2"
            ],
        )
        maximum_membership_area_class_aggregate_error_km2 = max(
            maximum_membership_area_class_aggregate_error_km2,
            membership_area_class_replay[
                "maximum_destination_aggregate_error_km2"
            ],
        )
        maximum_membership_area_class_edge_reconstruction_error_km2 = max(
            maximum_membership_area_class_edge_reconstruction_error_km2,
            membership_area_class_replay[
                "maximum_edge_reconstruction_error_km2"
            ],
        )

        if step_index == 0:
            class_values = membership_area_class_replay["values"]
            if (
                class_values["destination_offsets"]
                != list(range(cell_count + 1))
                or class_values["areas"] != areas
                or class_values["multiplicities"] != [1] * cell_count
                or class_values["representative_x"]
                != [position[0] for position in positions]
                or class_values["representative_y"]
                != [position[1] for position in positions]
                or class_values["representative_z"]
                != [position[2] for position in positions]
                or class_values["representative_available"]
                != [1] * cell_count
                or class_values["contributor_offsets"]
                != list(range(cell_count + 1))
                or class_values["source_cell_ids"] != list(range(cell_count))
                or class_values["source_plate_ids"] != cell_plate_ids
            ):
                failures.append(
                    "initial crust coverage membership-area-class ledger is not identity"
                )
                break

        if step_index == 0:
            # All initial numeric crust fields are round-trip compatibility
            # aliases for the identity overlap ledger.
            if (
                any(
                    alias != authoritative
                    for alias, authoritative in zip(
                        previous_ages, remapped_ages, strict=True
                    )
                )
                or any(
                    alias != authoritative
                    for alias, authoritative in zip(
                        previous_thicknesses,
                        remapped_thicknesses,
                        strict=True,
                    )
                )
                or any(
                    alias != authoritative
                    for alias, authoritative in zip(
                        previous_densities, remapped_densities, strict=True
                    )
                )
            ):
                failures.append("initial crust cell aliases do not match identity ledger")
                break
            previous_ages = remapped_ages.copy()
            previous_thicknesses = remapped_thicknesses.copy()
            previous_densities = remapped_densities.copy()
        rotated_source_positions: list[tuple[float, float, float]] = []
        for source, plate_id in enumerate(source_plate_ids):
            rotated_source_positions.append(
                _rotate_vector(
                    positions[source],
                    rotation_axes[plate_id],
                    step_rotations[plate_id],
                )
            )
        expected_source_kinematic_distances = [
            _surface_distance_km(
                positions[source],
                rotated_source_positions[source],
                radius_km,
            )
            for source in range(cell_count)
        ]
        if any(
            not math.isclose(actual, expected, rel_tol=2.0e-10, abs_tol=1.0e-7)
            for actual, expected in zip(
                kinematic_distances,
                expected_source_kinematic_distances,
                strict=True,
            )
        ):
            failures.append(
                f"crust overlap source kinematics failed at step {step_index}"
            )
            break
        if previous_types is None:
            previous_types = final_types.copy()
            previous_lithologies = final_lithologies.copy()
        assert previous_lithologies is not None
        source_area_sums = [0.0] * cell_count
        replayed_ages = [0.0] * cell_count
        replayed_thicknesses = [0.0] * cell_count
        replayed_densities = [0.0] * cell_count
        replayed_types = [0] * cell_count
        replayed_lithologies = [0] * cell_count
        replayed_dominant_ids = list(range(cell_count))
        replayed_dominant_fractions = [0.0] * cell_count
        replayed_transport_distances = [0.0] * cell_count
        transported_volume = 0.0
        transported_density_volume = 0.0
        transported_age_moment = 0.0
        step_destination_identity_error_km2 = 0.0
        step_destination_identity_forward_bound_km2 = 0.0
        step_destination_three_term_upper_bound_km2 = 0.0
        membership_areas_by_destination = membership_area_class_replay[
            "membership_area_by_destination"
        ]
        for destination in range(cell_count):
            begin, end = offsets[destination], offsets[destination + 1]
            category_pair_volumes = [[0.0] * 7 for _ in range(9)]
            destination_volume = 0.0
            destination_density_volume = 0.0
            destination_age_moment = 0.0
            dominant_volume = -1.0
            dominant_source = destination
            coverage_sum = 0.0
            distance_volume_sum = 0.0
            for edge_index in range(begin, end):
                source = source_ids[edge_index]
                overlap_area = overlap_areas[edge_index]
                expected_residual_distance = _surface_distance_km(
                    rotated_source_positions[source],
                    positions[destination],
                    radius_km,
                )
                if not math.isclose(
                    residual_distances[edge_index],
                    expected_residual_distance,
                    rel_tol=2.0e-10,
                    abs_tol=1.0e-7,
                ):
                    failures.append(
                        "crust overlap edge residual replay failed at "
                        f"step {step_index}, cell {destination}"
                    )
                    break
                source_area_sums[source] += overlap_area
                edge_volume = overlap_area * previous_thicknesses[source]
                destination_volume += edge_volume
                destination_density_volume += edge_volume * previous_densities[source]
                destination_age_moment += edge_volume * previous_ages[source]
                coverage_sum += overlap_area
                distance_volume_sum += edge_volume * kinematic_distances[source]
                category_pair_volumes[previous_types[source]][
                    previous_lithologies[source]
                ] += edge_volume
                if edge_volume > dominant_volume or (
                    edge_volume == dominant_volume and source < dominant_source
                ):
                    dominant_volume = edge_volume
                    dominant_source = source
            if destination_volume > 0.0:
                replayed_thicknesses[destination] = destination_volume / areas[destination]
                replayed_densities[destination] = (
                    destination_density_volume / destination_volume
                )
                replayed_ages[destination] = (
                    destination_age_moment / destination_volume
                )
                dominant_type, dominant_lithology = (
                    _dominant_crust_category_pair(category_pair_volumes)
                )
                replayed_types[destination] = dominant_type
                replayed_lithologies[destination] = dominant_lithology
                replayed_dominant_ids[destination] = dominant_source
                replayed_dominant_fractions[destination] = (
                    dominant_volume / destination_volume
                )
                replayed_transport_distances[destination] = (
                    distance_volume_sum / destination_volume
                )
            else:
                replayed_densities[destination] = previous_densities[destination]
                replayed_types[destination] = previous_types[destination]
                replayed_lithologies[destination] = previous_lithologies[destination]
            transported_volume += destination_volume
            transported_density_volume += destination_density_volume
            transported_age_moment += destination_age_moment
            destination_identity_error_km2 = max(
                abs(union_areas[destination] + gap_areas[destination] - areas[destination]),
                abs(union_areas[destination] + excess_areas[destination] - coverage_sum),
            )
            destination_identity_forward_bound_km2 = max(
                _two_operation_identity_bound(
                    union_areas[destination],
                    gap_areas[destination],
                    areas[destination],
                ),
                _two_operation_identity_bound(
                    union_areas[destination],
                    excess_areas[destination],
                    coverage_sum,
                ),
            )
            step_destination_identity_error_km2 = max(
                step_destination_identity_error_km2,
                destination_identity_error_km2,
            )
            step_destination_identity_forward_bound_km2 = max(
                step_destination_identity_forward_bound_km2,
                destination_identity_forward_bound_km2,
            )
            atomic_partition_upper_bound_km2 = (
                _atomic_partition_error_upper_bound(
                    areas[destination],
                    list(membership_areas_by_destination[destination].values()),
                    arrangement_fragment_counts[destination],
                )
            )
            step_destination_three_term_upper_bound_km2 = max(
                step_destination_three_term_upper_bound_km2,
                destination_identity_error_km2
                + destination_identity_forward_bound_km2,
                atomic_partition_upper_bound_km2,
            )
            maximum_destination_identity_error_km2 = max(
                maximum_destination_identity_error_km2,
                destination_identity_error_km2,
            )
            if (
                contributor_counts[destination] != end - begin
                or not _close(coverage_sums[destination], coverage_sum)
                or not 0.0 <= dominant_fractions[destination] <= 1.0 + 1.0e-12
                or maximum_multiplicities[destination] < 0
            ):
                failures.append(
                    f"crust overlap destination replay failed at step {step_index}, cell {destination}"
                )
                break
        if failures:
            break

        source_absolute_error_km2 = max(
            (
                abs(source_area_sums[source] - areas[source])
                for source in range(cell_count)
            ),
            default=0.0,
        )
        source_relative_error = max(
            (
                abs(source_area_sums[source] - areas[source]) / areas[source]
                for source in range(cell_count)
            ),
            default=0.0,
        )
        maximum_source_relative_error = max(
            maximum_source_relative_error, source_relative_error
        )
        maximum_source_absolute_error_km2 = max(
            maximum_source_absolute_error_km2,
            source_absolute_error_km2,
        )
        source_inventory = _inventory(
            areas, previous_thicknesses, previous_densities, previous_ages
        )
        transported_inventory = (
            transported_volume,
            transported_density_volume,
            transported_age_moment,
        )
        inventory_relative_error = 0.0
        for source_value, transported_value in zip(
            source_inventory, transported_inventory
        ):
            inventory_relative_error = max(
                inventory_relative_error,
                abs(transported_value - source_value)
                / max(1.0, abs(source_value)),
            )
            maximum_inventory_relative_error = max(
                maximum_inventory_relative_error,
                inventory_relative_error,
            )
        try:
            serialized_source_inventory = ledger["source_inventory"]
            serialized_transported_inventory = ledger["transported_inventory"]
            serialized_source_values = (
                float(serialized_source_inventory["crust_volume_km3"]),
                float(serialized_source_inventory["density_weighted_crust_volume"]),
                float(serialized_source_inventory["crust_age_volume_moment_km3_ma"]),
            )
            serialized_transported_values = (
                float(serialized_transported_inventory["crust_volume_km3"]),
                float(serialized_transported_inventory["density_weighted_crust_volume"]),
                float(serialized_transported_inventory["crust_age_volume_moment_km3_ma"]),
            )
            serialized_source_absolute_error_km2 = float(
                ledger["maximum_source_area_closure_error_km2"]
            )
            serialized_source_relative_error = float(
                ledger["maximum_source_area_relative_closure_error"]
            )
            serialized_destination_error_km2 = float(
                ledger["maximum_destination_partition_closure_error_km2"]
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            failures.append(f"crust overlap inventory {step_index} is invalid")
            break
        if (
            source_relative_error > 2.0e-10
            or inventory_relative_error > 5.0e-10
            or maximum_destination_identity_error_km2
            > max(0.01, max(areas) * 1.0e-9)
            or any(
                not _close(actual, expected)
                for actual, expected in zip(serialized_source_values, source_inventory)
            )
            or any(
                not _close(actual, expected)
                for actual, expected in zip(
                    serialized_transported_values, transported_inventory
                )
            )
            or not math.isclose(
                serialized_source_absolute_error_km2,
                source_absolute_error_km2,
                rel_tol=2.0e-8,
                abs_tol=1.0e-12,
            )
            or not math.isclose(
                serialized_source_relative_error,
                source_relative_error,
                rel_tol=2.0e-8,
                abs_tol=1.0e-15,
            )
            # The native scalar is a three-term maximum.  Its third term is an
            # unexported ordered sum of raw arrangement atoms, so equality with
            # this two-term aggregate replay is not expected.  The lower bound
            # comes from the replayable identities; the upper bound propagates
            # the exported coalesced class sums and raw fragment counts through
            # both native summation paths.
            or not math.isfinite(serialized_destination_error_km2)
            or serialized_destination_error_km2 < 0.0
            or serialized_destination_error_km2
            + step_destination_identity_forward_bound_km2
            < step_destination_identity_error_km2
            or serialized_destination_error_km2
            > step_destination_three_term_upper_bound_km2
            or any(
                not _close(actual, expected)
                for actual, expected in zip(remapped_ages, replayed_ages)
            )
            or any(
                not _close(actual, expected)
                for actual, expected in zip(remapped_thicknesses, replayed_thicknesses)
            )
            or any(
                not _close(actual, expected)
                for actual, expected in zip(remapped_densities, replayed_densities)
            )
            or remapped_types != replayed_types
            or remapped_lithologies != replayed_lithologies
            or dominant_ids != replayed_dominant_ids
            or legacy_dominant_ids != replayed_dominant_ids
            or any(
                not _close(actual, expected)
                for actual, expected in zip(
                    dominant_fractions, replayed_dominant_fractions
                )
            )
            or any(
                not _legacy_close(actual, expected)
                for actual, expected in zip(
                    serialized_transport_distances,
                    replayed_transport_distances,
                )
            )
        ):
            failures.append(f"crust overlap extensive replay failed at step {step_index}")
            break

        expected_scalar_metrics = {
            "mean_plate_rotation_deg": math.fsum(
                abs(value) for value in step_rotations.values()
            )
            / max(1, len(step_rotations)),
            "max_plate_rotation_deg": max(
                (abs(value) for value in step_rotations.values()), default=0.0
            ),
            "mean_crust_transport_distance_km": math.fsum(
                serialized_transport_distances
            )
            / cell_count,
            "max_crust_transport_distance_km": max(
                serialized_transport_distances, default=0.0
            ),
        }
        for prefix, columns in (
            (
                "",
                (total_age_changes, total_thickness_changes, total_density_changes),
            ),
            (
                "transport_",
                (
                    transport_age_changes,
                    transport_thickness_changes,
                    transport_density_changes,
                ),
            ),
            (
                "process_",
                (
                    process_age_changes,
                    process_thickness_changes,
                    process_density_changes,
                ),
            ),
        ):
            for quantity, unit, values in zip(
                ("age", "thickness", "density"),
                ("_ma", "_km", ""),
                columns,
                strict=True,
            ):
                expected_scalar_metrics[
                    f"mean_abs_crust_{quantity}_{prefix}change{unit}"
                ] = math.fsum(abs(value) for value in values) / cell_count
        if (
            any(
                not _legacy_close(step_scalar_metrics[field], expected)
                for field, expected in expected_scalar_metrics.items()
            )
            or step_count_metrics["crust_source_remap_cell_count"]
            != sum(
                source != destination
                for destination, source in enumerate(legacy_dominant_ids)
            )
            or step_count_metrics["unique_crust_source_cell_count"]
            != len(set(legacy_dominant_ids))
            or step_count_metrics["crust_source_reuse_count"]
            != cell_count - len(set(legacy_dominant_ids))
        ):
            failures.append(f"crust transport scalar mirrors failed at step {step_index}")
            break

        final_ages = [
            remapped + process
            for remapped, process in zip(remapped_ages, process_age_changes)
        ]
        final_thicknesses = [
            remapped + process
            for remapped, process in zip(
                remapped_thicknesses, process_thickness_changes
            )
        ]
        final_densities = [
            remapped + process
            for remapped, process in zip(
                remapped_densities, process_density_changes
            )
        ]
        if (
            any(
                not _legacy_close(transport, remapped - previous)
                for transport, remapped, previous in zip(
                    transport_age_changes, remapped_ages, previous_ages
                )
            )
            or any(
                not _legacy_close(transport, remapped - previous)
                for transport, remapped, previous in zip(
                    transport_thickness_changes,
                    remapped_thicknesses,
                    previous_thicknesses,
                )
            )
            or any(
                not _legacy_close(transport, remapped - previous)
                for transport, remapped, previous in zip(
                    transport_density_changes,
                    remapped_densities,
                    previous_densities,
                )
            )
            or any(
                not _legacy_close(total, final - previous)
                for total, final, previous in zip(
                    total_age_changes, final_ages, previous_ages
                )
            )
            or any(
                not _legacy_close(total, final - previous)
                for total, final, previous in zip(
                    total_thickness_changes, final_thicknesses, previous_thicknesses
                )
            )
            or any(
                not _legacy_close(total, final - previous)
                for total, final, previous in zip(
                    total_density_changes, final_densities, previous_densities
                )
            )
        ):
            failures.append(f"crust transport/process split failed at step {step_index}")
            break
        post_process_inventory = _inventory(
            areas, final_thicknesses, final_densities, final_ages
        )
        try:
            serialized_post = ledger["post_process_inventory"]
            serialized_post_values = (
                float(serialized_post["crust_volume_km3"]),
                float(serialized_post["density_weighted_crust_volume"]),
                float(serialized_post["crust_age_volume_moment_km3_ma"]),
            )
            serialized_process_delta = ledger["process_inventory_delta"]
            serialized_process_delta_values = (
                float(serialized_process_delta["crust_volume_km3"]),
                float(
                    serialized_process_delta["density_weighted_crust_volume"]
                ),
                float(
                    serialized_process_delta["crust_age_volume_moment_km3_ma"]
                ),
            )
            serialized_process_attribution = _process_attribution_values(
                ledger["process_inventory_attribution"],
                cell_count,
            )
            serialized_global_gap_area_km2 = float(
                ledger["global_uncovered_gap_area_km2"]
            )
            serialized_global_excess_area_km2 = float(
                ledger["global_overlap_excess_area_km2"]
            )
            serialized_global_balance_residual_km2 = float(
                ledger["global_gap_overlap_balance_residual_km2"]
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            failures.append(f"post-process crust inventory {step_index} is invalid")
            break
        if any(
            not _close(actual, expected, relative=5.0e-9)
            for actual, expected in zip(serialized_post_values, post_process_inventory)
        ) or any(
            not _ulp_close(actual, post - transported)
            for actual, post, transported in zip(
                serialized_process_delta_values,
                serialized_post_values,
                serialized_transported_values,
            )
        ):
            failures.append(f"post-process crust inventory {step_index} did not replay")
            break
        if any(
            not _ulp_close(actual, expected)
            for actual, expected in zip(
                serialized_process_attribution["reconciled"],
                serialized_process_delta_values,
                strict=True,
            )
        ):
            failures.append(
                f"crust process reason ledger {step_index} did not reconcile"
            )
            break
        expected_attribution_residual = tuple(
            process_delta - attributed
            for process_delta, attributed in zip(
                serialized_process_delta_values,
                serialized_process_attribution["attributed"],
                strict=True,
            )
        )
        if any(
            not _ulp_close(actual, expected)
            for actual, expected in zip(
                serialized_process_attribution["residual"],
                expected_attribution_residual,
                strict=True,
            )
        ):
            failures.append(
                f"crust process reason ledger {step_index} residual mirror is invalid"
            )
            break
        reason_records = serialized_process_attribution["reasons"]
        reduction_operation_count = (
            sum(
                int(record["extensive_state_changed_cell_count"]) + 3
                for record in reason_records
            )
            + len(reason_records)
            + 4
        )
        epsilon_product = reduction_operation_count * math.ulp(1.0)
        if epsilon_product >= 1.0:
            failures.append(
                f"crust process reason ledger {step_index} residual bound overflowed"
            )
            break
        gamma = epsilon_product / (1.0 - epsilon_product)
        for component, (residual, process_delta, attributed_delta) in enumerate(
            zip(
                serialized_process_attribution["residual"],
                serialized_process_delta_values,
                serialized_process_attribution["attributed"],
                strict=True,
            )
        ):
            absolute_term_sum = math.fsum(
                record["positive"][component] + record["negative"][component]
                for record in reason_records
            )
            scale = max(
                abs(residual),
                abs(process_delta),
                abs(attributed_delta),
                absolute_term_sum,
            )
            residual_tolerance = max(
                1.0e-6,
                gamma
                * (
                    abs(process_delta)
                    + abs(attributed_delta)
                    + absolute_term_sum
                )
                + 128.0 * math.ulp(scale),
            )
            if abs(residual) > residual_tolerance:
                failures.append(
                    f"crust process reason ledger {step_index} residual is excessive"
                )
                break
            maximum_process_attribution_relative_residual = max(
                maximum_process_attribution_relative_residual,
                abs(residual) / max(1.0, abs(process_delta)),
            )
        if failures:
            break
        if step_index == 0 and (
            any(
                record["triggered_cell_count"] != 0
                or record["extensive_state_changed_cell_count"] != 0
                or any(
                    value != 0.0
                    for values in (
                        record["positive"],
                        record["negative"],
                        record["net"],
                    )
                    for value in values
                )
                for record in serialized_process_attribution["reasons"]
            )
            or any(
                value != 0.0
                for field in ("attributed", "residual", "reconciled")
                for value in serialized_process_attribution[field]
            )
        ):
            failures.append("initial crust process reason ledger is not zero")
            break
        if step_index > 0:
            total_process_reason_record_count += len(
                serialized_process_attribution["reasons"]
            )
            active_process_reason_record_count += sum(
                record["triggered_cell_count"] > 0
                for record in serialized_process_attribution["reasons"]
            )

        total_gap = math.fsum(gap_areas)
        total_excess = math.fsum(excess_areas)
        histogram_surface_area = math.fsum(coverage_histogram)
        histogram_union_area = math.fsum(coverage_histogram[1:])
        histogram_coverage_area = math.fsum(
            multiplicity * area
            for multiplicity, area in enumerate(coverage_histogram)
        )
        histogram_excess_area = math.fsum(
            (multiplicity - 1) * coverage_histogram[multiplicity]
            for multiplicity in range(2, len(coverage_histogram))
        )
        histogram_maximum_multiplicity = max(
            (
                multiplicity
                for multiplicity, area in enumerate(coverage_histogram)
                if area > 0.0
            ),
            default=0,
        )
        gap_overlap_balance = abs(total_gap - total_excess)
        signed_gap_overlap_balance = total_excess - total_gap
        # The native mirror subtracts two sequentially accumulated global
        # areas, while this replay uses correctly rounded fsum totals.  Compare
        # the ill-conditioned residual with a forward-error bound for the two
        # O(N) sums, not with a fixed absolute epsilon on their cancellation.
        gap_overlap_residual_mirror_tolerance_km2 = max(
            1.0e-8,
            8.0
            * math.ulp(1.0)
            * cell_count
            * (1.0 + abs(total_gap) + abs(total_excess)),
        )
        maximum_gap_overlap_balance_error_km2 = max(
            maximum_gap_overlap_balance_error_km2, gap_overlap_balance
        )
        if (
            not _close(serialized_global_gap_area_km2, total_gap)
            or not _close(serialized_global_excess_area_km2, total_excess)
            or not _close(histogram_surface_area, math.fsum(areas))
            or not _close(coverage_histogram[0], total_gap)
            or not _close(histogram_union_area, math.fsum(union_areas))
            or not _close(histogram_coverage_area, math.fsum(coverage_sums))
            or not _close(histogram_excess_area, total_excess)
            or histogram_maximum_multiplicity != max(maximum_multiplicities)
            or abs(
                serialized_global_balance_residual_km2
                - signed_gap_overlap_balance
            )
            > gap_overlap_residual_mirror_tolerance_km2
            or gap_overlap_balance > max(0.01, math.fsum(areas) * 5.0e-10)
        ):
            failures.append(f"crust coverage balance failed at step {step_index}")
            break
        if step_index == 0 and (
            source_ids != list(range(cell_count))
            or offsets != list(range(cell_count + 1))
            or any(value != 0.0 for value in kinematic_distances + residual_distances)
            or any(not _close(value, 1.0) for value in dominant_fractions)
            or any(value != 0 for value in arrangement_line_counts)
            or any(value != 1 for value in arrangement_fragment_counts)
            or any(value != 1 for value in membership_area_class_counts)
        ):
            failures.append("initial crust overlap ledger is not identity")
            break

        if step_index > 0:
            transition_sparse_edge_count += len(source_ids)
            transition_mixed_destination_count += sum(
                count > 1 for count in contributor_counts
            )
            transition_maximum_coverage_multiplicity = max(
                transition_maximum_coverage_multiplicity,
                max(maximum_multiplicities, default=0),
            )
            transition_maximum_arrangement_line_count = max(
                transition_maximum_arrangement_line_count,
                maximum_arrangement_line_count,
            )
            transition_maximum_arrangement_fragment_count = max(
                transition_maximum_arrangement_fragment_count,
                maximum_arrangement_fragment_count,
            )
            transition_maximum_source_absolute_error_km2 = max(
                transition_maximum_source_absolute_error_km2,
                source_absolute_error_km2,
            )
            transition_maximum_source_relative_error = max(
                transition_maximum_source_relative_error,
                source_relative_error,
            )
            transition_maximum_destination_error_km2 = max(
                transition_maximum_destination_error_km2,
                step_destination_identity_error_km2,
            )
            transition_total_gap_area_km2 += total_gap
            transition_total_excess_area_km2 += total_excess
            transition_maximum_inventory_relative_error = max(
                transition_maximum_inventory_relative_error,
                inventory_relative_error,
            )
            process_volume_change_km3 = serialized_process_delta_values[0]
            process_density_volume_change_g_cm3_km3 = (
                serialized_process_delta_values[1]
            )
            process_age_moment_change_km3_ma = serialized_process_delta_values[2]
            cumulative_absolute_process_volume_change_km3 += abs(
                process_volume_change_km3
            )
            net_process_volume_change_km3 += process_volume_change_km3
            cumulative_absolute_process_density_volume_change_g_cm3_km3 += abs(
                process_density_volume_change_g_cm3_km3
            )
            net_process_density_volume_change_g_cm3_km3 += (
                process_density_volume_change_g_cm3_km3
            )
            cumulative_absolute_process_age_moment_change_km3_ma += abs(
                process_age_moment_change_km3_ma
            )
            net_process_age_moment_change_km3_ma += (
                process_age_moment_change_km3_ma
            )

        total_sparse_edge_count += len(source_ids)
        total_mixed_destination_count += sum(count > 1 for count in contributor_counts)
        previous_ages = final_ages
        previous_thicknesses = final_thicknesses
        previous_densities = final_densities
        previous_types = final_types
        previous_lithologies = final_lithologies
        previous_plate_ids = cell_plate_ids

    if not failures:
        try:
            final_numeric_fields = (
                (
                    "crust_age_ma",
                    previous_ages,
                    remapped_ages,
                    process_age_changes,
                ),
                (
                    "crust_thickness_km",
                    previous_thicknesses,
                    remapped_thicknesses,
                    process_thickness_changes,
                ),
                (
                    "crust_density",
                    previous_densities,
                    remapped_densities,
                    process_density_changes,
                ),
            )
            for field, reconstructed, remapped, process in final_numeric_fields:
                for index, cell in enumerate(cells):
                    observed = float(cell[field])
                    expected = reconstructed[index]
                    bound = _final_crust_alias_binary64_bound(
                        observed,
                        remapped[index],
                        process[index],
                        expected,
                    )
                    if (
                        not math.isfinite(observed)
                        or not math.isfinite(expected)
                        or abs(observed - expected) > bound
                    ):
                        failures.append(
                            f"final cell {index} {field} does not match "
                            "overlap history within its binary64 operation bound"
                        )
                        break
                if failures:
                    break
        except (KeyError, TypeError, ValueError, OverflowError):
            failures.append("final crust cell state is invalid")

    summary_mirrors = {
        "total_crust_overlap_sparse_edge_count": transition_sparse_edge_count,
        "total_crust_mixed_destination_count": transition_mixed_destination_count,
        "maximum_crust_coverage_multiplicity": (
            transition_maximum_coverage_multiplicity
        ),
        "maximum_crust_coverage_arrangement_line_count": (
            transition_maximum_arrangement_line_count
        ),
        "maximum_crust_coverage_arrangement_fragment_count": (
            transition_maximum_arrangement_fragment_count
        ),
        "maximum_crust_source_area_closure_error_km2": (
            transition_maximum_source_absolute_error_km2
        ),
        "maximum_crust_source_area_relative_closure_error": (
            transition_maximum_source_relative_error
        ),
        "maximum_crust_destination_partition_closure_error_km2": (
            transition_maximum_destination_error_km2
        ),
        "total_crust_uncovered_gap_area_km2": transition_total_gap_area_km2,
        "total_crust_overlap_excess_area_km2": transition_total_excess_area_km2,
        "maximum_crust_transport_inventory_relative_closure_error": (
            transition_maximum_inventory_relative_error
        ),
        "cumulative_absolute_tectonic_process_crust_volume_change_km3": (
            cumulative_absolute_process_volume_change_km3
        ),
        "net_tectonic_process_crust_volume_change_km3": (
            net_process_volume_change_km3
        ),
        "cumulative_absolute_tectonic_process_density_weighted_crust_volume_change_g_cm3_km3": (
            cumulative_absolute_process_density_volume_change_g_cm3_km3
        ),
        "net_tectonic_process_density_weighted_crust_volume_change_g_cm3_km3": (
            net_process_density_volume_change_g_cm3_km3
        ),
        "cumulative_absolute_tectonic_process_crust_age_volume_moment_change_km3_ma": (
            cumulative_absolute_process_age_moment_change_km3_ma
        ),
        "net_tectonic_process_crust_age_volume_moment_change_km3_ma": (
            net_process_age_moment_change_km3_ma
        ),
        "total_tectonic_process_reason_record_count": (
            total_process_reason_record_count
        ),
        "active_tectonic_process_reason_record_count": (
            active_process_reason_record_count
        ),
        "maximum_tectonic_process_attribution_relative_closure_residual": (
            maximum_process_attribution_relative_residual
        ),
    }
    if not failures:
        summary = world.get("summary", {})
        try:
            for field in (
                "total_crust_overlap_sparse_edge_count",
                "total_crust_mixed_destination_count",
                "maximum_crust_coverage_multiplicity",
                "maximum_crust_coverage_arrangement_line_count",
                "maximum_crust_coverage_arrangement_fragment_count",
                "total_tectonic_process_reason_record_count",
                "active_tectonic_process_reason_record_count",
            ):
                if (
                    type(summary[field]) is not int
                    or summary[field] != summary_mirrors[field]
                ):
                    failures.append(f"summary {field} does not match overlap ledgers")
            for field, expected in summary_mirrors.items():
                if field in {
                    "total_crust_overlap_sparse_edge_count",
                    "total_crust_mixed_destination_count",
                    "maximum_crust_coverage_multiplicity",
                    "maximum_crust_coverage_arrangement_line_count",
                    "maximum_crust_coverage_arrangement_fragment_count",
                    "total_tectonic_process_reason_record_count",
                    "active_tectonic_process_reason_record_count",
                }:
                    continue
                if not math.isclose(
                    float(summary[field]),
                    float(expected),
                    rel_tol=2.0e-9,
                    abs_tol=1.0e-8,
                ):
                    failures.append(
                        f"summary {field} does not match overlap ledgers"
                    )
        except (KeyError, TypeError, ValueError, OverflowError):
            failures.append("conservative crust transport summary mirrors are invalid")

    return {
        "passed": not failures,
        "failures": failures,
        "metrics": {
            "history_step_count": len(history),
            "sparse_edge_count": total_sparse_edge_count,
            "mixed_destination_count": total_mixed_destination_count,
            "maximum_source_absolute_closure_error_km2": maximum_source_absolute_error_km2,
            "maximum_source_relative_closure_error": maximum_source_relative_error,
            "maximum_inventory_relative_closure_error": maximum_inventory_relative_error,
            "maximum_destination_identity_error_km2": maximum_destination_identity_error_km2,
            "maximum_gap_overlap_balance_error_km2": maximum_gap_overlap_balance_error_km2,
            "maximum_process_attribution_relative_residual": (
                maximum_process_attribution_relative_residual
            ),
            "coverage_membership_area_class_count": (
                total_coverage_membership_area_class_count
            ),
            "coverage_membership_area_class_contributor_count": (
                total_coverage_membership_area_class_contributor_count
            ),
            "maximum_coverage_membership_area_class_partition_error_km2": (
                maximum_membership_area_class_partition_error_km2
            ),
            "maximum_coverage_membership_area_class_aggregate_error_km2": (
                maximum_membership_area_class_aggregate_error_km2
            ),
            "maximum_coverage_membership_area_class_edge_reconstruction_error_km2": (
                maximum_membership_area_class_edge_reconstruction_error_km2
            ),
            **summary_mirrors,
            **process_replay["metrics"],
        },
    }
