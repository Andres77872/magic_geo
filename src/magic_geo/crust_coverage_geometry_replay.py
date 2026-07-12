"""Independent small-mesh replay of native crust-coverage geometry.

The replay deliberately does not read the serialized overlap CSR while it
discovers source/destination pairs or computes overlap polygons.  It rotates
the native spherical control volumes, rejects disjoint caps, clips every
surviving source/destination triangle pair in a destination gnomonic chart,
and rebuilds the destination-local line arrangement used for integer coverage
multiplicity.

Pair discovery is an O(N**2) brute-force cap search.  That makes the
implementation straightforwardly independent of the native k-d tree and is
appropriate for routine validation fixtures (128/162 cells, and typically a
few hundred cells).  ``max_cell_count`` defaults to 1,024 to prevent this
diagnostic implementation from being used accidentally as a production
remapper.  A caller may raise the explicit bound, but large meshes should use
an independently implemented spatial index first.
"""

from __future__ import annotations

import math
import sys
from collections.abc import Sequence
from typing import Any, TypeAlias


Vec3: TypeAlias = tuple[float, float, float]
Point2: TypeAlias = tuple[float, float]
Line2: TypeAlias = tuple[float, float, float]
Polygon2: TypeAlias = list[Point2]

ARRANGEMENT_FRAGMENT_LIMIT = 16_384
DEFAULT_MAX_CELL_COUNT = 1_024

_EPSILON = sys.float_info.epsilon
_CAP_ANGLE_PADDING_RAD = 1.0e-10
_PIECE_AREA_MIN_KM2 = 1.0e-12
_EDGE_AREA_ABSOLUTE_MIN_KM2 = 1.0e-10
_EDGE_AREA_RELATIVE_MIN = 1.0e-13
_GNOMONIC_DENOMINATOR_MIN = 1.0e-10
_DUPLICATE_VERTEX_DISTANCE_SQUARED = 1.0e-28
_COINCIDENT_LINE_TOLERANCE = 2.0e-12

# The independent replay evaluates the clipping and spherical-area path in
# binary64, while the native implementation keeps its planar predicates and
# spherical excess accumulation in long double.  Reserve this many dependent
# roundings for one projected/clip/unproject/area path before accounting for
# the actual destination and fragment reductions below.  The resulting
# comparison bound is a standard gamma_n forward-error bound, not a relative
# acceptance band proportional to an individual serialized area.
_GEOMETRY_FORWARD_ERROR_OPERATION_BUDGET = 256
_GEOMETRY_FORWARD_ERROR_AREA_FLOOR_KM2 = 32.0 * _PIECE_AREA_MIN_KM2


def _dot(first: Vec3, second: Vec3) -> float:
    return (
        first[0] * second[0]
        + first[1] * second[1]
        + first[2] * second[2]
    )


def _add(first: Vec3, second: Vec3) -> Vec3:
    return (
        first[0] + second[0],
        first[1] + second[1],
        first[2] + second[2],
    )


def _scale(value: Vec3, factor: float) -> Vec3:
    return value[0] * factor, value[1] * factor, value[2] * factor


def _cross(first: Vec3, second: Vec3) -> Vec3:
    return (
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    )


def _normalize(value: Vec3, *, context: str) -> Vec3:
    squared_norm = _dot(value, value)
    if not math.isfinite(squared_norm) or squared_norm <= 1.0e-28:
        raise ValueError(f"{context} is geometrically degenerate")
    return _scale(value, 1.0 / math.sqrt(squared_norm))


def _native_normalize(value: Vec3) -> Vec3:
    """Match the non-throwing normalizer used by native axis rotation."""

    norm = math.sqrt(_dot(value, value))
    if norm < 1.0e-12:
        return 0.0, 0.0, 1.0
    return _scale(value, 1.0 / norm)


def _rotate(value: Vec3, axis: Vec3, angle_deg: float) -> Vec3:
    if angle_deg == 0.0:
        return value
    unit_axis = _native_normalize(axis)
    angle_rad = math.radians(angle_deg)
    cosine = math.cos(angle_rad)
    sine = math.sin(angle_rad)
    return _native_normalize(
        _add(
            _add(
                _scale(value, cosine),
                _scale(_cross(unit_axis, value), sine),
            ),
            _scale(unit_axis, _dot(unit_axis, value) * (1.0 - cosine)),
        )
    )


def _angular_distance(first: Vec3, second: Vec3) -> float:
    return math.acos(max(-1.0, min(1.0, _dot(first, second))))


def _tangent_basis(center: Vec3) -> tuple[Vec3, Vec3]:
    reference: Vec3 = (
        (0.0, 0.0, 1.0) if abs(center[2]) < 0.8 else (1.0, 0.0, 0.0)
    )
    first = _normalize(_cross(reference, center), context="replay tangent axis")
    second = _normalize(_cross(center, first), context="replay tangent axis")
    return first, second


def _project(point: Vec3, center: Vec3, basis: tuple[Vec3, Vec3]) -> Point2:
    denominator = _dot(center, point)
    if denominator <= _GNOMONIC_DENOMINATOR_MIN:
        raise ValueError("replay candidate left the destination gnomonic hemisphere")
    return _dot(basis[0], point) / denominator, _dot(basis[1], point) / denominator


def _unproject(point: Point2, center: Vec3, basis: tuple[Vec3, Vec3]) -> Vec3:
    return _normalize(
        _add(center, _add(_scale(basis[0], point[0]), _scale(basis[1], point[1]))),
        context="replay overlap vertex",
    )


def _cross_2d(first: Point2, second: Point2) -> float:
    return first[0] * second[1] - first[1] * second[0]


def _subtract_2d(first: Point2, second: Point2) -> Point2:
    return first[0] - second[0], first[1] - second[1]


def _line_value(start: Point2, end: Point2, point: Point2) -> float:
    return _cross_2d(_subtract_2d(end, start), _subtract_2d(point, start))


def _line_inside(
    start: Point2,
    end: Point2,
    point: Point2,
    *,
    keep_left: bool,
) -> bool:
    value = _line_value(start, end, point)
    if not keep_left:
        value = -value
    planar_scale = (
        1.0 + abs(start[0]) + abs(start[1]) + abs(end[0]) + abs(end[1])
    )
    tolerance = (
        512.0
        * _EPSILON
        * planar_scale
        * (1.0 + abs(point[0]) + abs(point[1]))
    )
    return value >= -tolerance


def _line_intersection(
    segment_start: Point2,
    segment_end: Point2,
    line_start: Point2,
    line_end: Point2,
) -> Point2:
    start_value = _line_value(line_start, line_end, segment_start)
    end_value = _line_value(line_start, line_end, segment_end)
    denominator = start_value - end_value
    if abs(denominator) <= 1.0e-30:
        return segment_start
    fraction = max(0.0, min(1.0, start_value / denominator))
    return (
        segment_start[0] + fraction * (segment_end[0] - segment_start[0]),
        segment_start[1] + fraction * (segment_end[1] - segment_start[1]),
    )


def _remove_duplicate_vertices(polygon: Polygon2) -> Polygon2:
    result: Polygon2 = []
    for point in polygon:
        if result:
            dx = point[0] - result[-1][0]
            dy = point[1] - result[-1][1]
            if dx * dx + dy * dy <= _DUPLICATE_VERTEX_DISTANCE_SQUARED:
                continue
        result.append(point)
    if len(result) > 1:
        dx = result[0][0] - result[-1][0]
        dy = result[0][1] - result[-1][1]
        if dx * dx + dy * dy <= _DUPLICATE_VERTEX_DISTANCE_SQUARED:
            result.pop()
    return result


def _clip_by_line(
    subject: Sequence[Point2],
    line_start: Point2,
    line_end: Point2,
    *,
    keep_left: bool,
) -> Polygon2:
    if not subject:
        return []
    result: Polygon2 = []
    for index, start in enumerate(subject):
        end = subject[(index + 1) % len(subject)]
        start_inside = _line_inside(
            line_start, line_end, start, keep_left=keep_left
        )
        end_inside = _line_inside(line_start, line_end, end, keep_left=keep_left)
        if start_inside and end_inside:
            result.append(end)
        elif start_inside and not end_inside:
            result.append(
                _line_intersection(start, end, line_start, line_end)
            )
        elif not start_inside and end_inside:
            result.append(
                _line_intersection(start, end, line_start, line_end)
            )
            result.append(end)
    result = _remove_duplicate_vertices(result)
    return result if len(result) >= 3 else []


def _intersect_convex_polygons(
    subject: Polygon2, clip_polygon: Sequence[Point2]
) -> Polygon2:
    result = subject
    for index, line_start in enumerate(clip_polygon):
        if not result:
            break
        result = _clip_by_line(
            result,
            line_start,
            clip_polygon[(index + 1) % len(clip_polygon)],
            keep_left=True,
        )
    return result


def _normalized_line(start: Point2, end: Point2) -> Line2:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.sqrt(dx * dx + dy * dy)
    if not math.isfinite(length) or length <= 1.0e-16:
        raise ValueError("replay coverage arrangement has a degenerate line")
    return -dy / length, dx / length, (dy * start[0] - dx * start[1]) / length


def _normalized_line_value(line: Line2, point: Point2) -> float:
    return line[0] * point[0] + line[1] * point[1] + line[2]


def _coincident_lines(first: Line2, second: Line2) -> bool:
    same = all(
        abs(left - right) <= _COINCIDENT_LINE_TOLERANCE
        for left, right in zip(first, second, strict=True)
    )
    opposite = all(
        abs(left + right) <= _COINCIDENT_LINE_TOLERANCE
        for left, right in zip(first, second, strict=True)
    )
    return same or opposite


def _split_clip_by_line(
    subject: Sequence[Point2], line: Line2, *, keep_positive: bool
) -> Polygon2:
    if not subject:
        return []
    result: Polygon2 = []
    for index, start in enumerate(subject):
        end = subject[(index + 1) % len(subject)]
        start_value = _normalized_line_value(line, start)
        end_value = _normalized_line_value(line, end)
        if not keep_positive:
            start_value = -start_value
            end_value = -end_value
        start_inside = start_value >= 0.0
        end_inside = end_value >= 0.0
        if start_inside and end_inside:
            result.append(end)
        elif start_inside != end_inside:
            denominator = start_value - end_value
            if abs(denominator) > 1.0e-30:
                fraction = max(0.0, min(1.0, start_value / denominator))
                intersection = (
                    start[0] + fraction * (end[0] - start[0]),
                    start[1] + fraction * (end[1] - start[1]),
                )
                residual = _normalized_line_value(line, intersection)
                intersection = (
                    intersection[0] - residual * line[0],
                    intersection[1] - residual * line[1],
                )
                result.append(intersection)
            if not start_inside and end_inside:
                result.append(end)
    result = _remove_duplicate_vertices(result)
    return result if len(result) >= 3 else []


def _project_polygon(
    vertices: Sequence[Vec3], center: Vec3, basis: tuple[Vec3, Vec3]
) -> Polygon2:
    return [_project(vertex, center, basis) for vertex in vertices]


def _spherical_polygon_area_km2(
    polygon: Sequence[Point2],
    chart_center: Vec3,
    basis: tuple[Vec3, Vec3],
    radius_km: float,
) -> float:
    if len(polygon) < 3:
        return 0.0
    vertices = [_unproject(point, chart_center, basis) for point in polygon]
    # The native implementation accumulates this Vec3 in vertex order.
    # Preserve that order instead of using a compensated reduction.
    centroid_sum: Vec3 = (0.0, 0.0, 0.0)
    for vertex in vertices:
        centroid_sum = _add(centroid_sum, vertex)
    reference = _normalize(
        centroid_sum,
        context="replay intersection centroid",
    )
    area = 0.0
    compensation = 0.0
    for index, first in enumerate(vertices):
        second = vertices[(index + 1) % len(vertices)]
        determinant = _dot(reference, _cross(first, second))
        denominator = (
            1.0
            + _dot(reference, first)
            + _dot(first, second)
            + _dot(second, reference)
        )
        triangle_area = 2.0 * math.atan2(determinant, denominator)
        adjusted = triangle_area - compensation
        updated = area + adjusted
        compensation = (updated - area) - adjusted
        area = updated
    if not math.isfinite(area) or area < -5.0e-15:
        raise ValueError("replay intersection polygon is reversed")
    if area < 0.0:
        area = -area
    return area * radius_km * radius_km


def _point_in_convex_polygon(point: Point2, polygon: Sequence[Point2]) -> bool:
    return all(
        _line_inside(
            polygon[index],
            polygon[(index + 1) % len(polygon)],
            point,
            keep_left=True,
        )
        for index in range(len(polygon))
    )


def _coverage_diagnostics(
    destination_center: Vec3,
    destination_vertices: Sequence[Vec3],
    destination_area_km2: float,
    coverage_by_source: Sequence[Sequence[Polygon2]],
    coverage_source_cell_ids: Sequence[int],
    coverage_area_sum_km2: float,
    radius_km: float,
) -> dict[str, Any]:
    if len(coverage_by_source) != len(coverage_source_cell_ids):
        raise ValueError("replay coverage membership inputs have inconsistent shapes")
    if not coverage_by_source:
        return {
            "union_area_km2": 0.0,
            "gap_area_km2": destination_area_km2,
            "overlap_excess_area_km2": 0.0,
            "partition_closure_error_km2": 0.0,
            "maximum_multiplicity": 0,
            "arrangement_line_count": 0,
            "arrangement_fragment_count": 1,
            "area_km2_by_multiplicity": [destination_area_km2],
            "area_km2_by_source_membership": {(): destination_area_km2},
        }
    if len(coverage_by_source) == 1:
        union_area = coverage_area_sum_km2
        gap_area = max(0.0, destination_area_km2 - union_area)
        return {
            "union_area_km2": union_area,
            "gap_area_km2": gap_area,
            "overlap_excess_area_km2": 0.0,
            "partition_closure_error_km2": abs(
                destination_area_km2 - union_area - gap_area
            ),
            "maximum_multiplicity": 1,
            "arrangement_line_count": 0,
            "arrangement_fragment_count": (
                2 if gap_area > 0.0 and union_area > 0.0 else 1
            ),
            "area_km2_by_multiplicity": [gap_area, union_area],
            "area_km2_by_source_membership": {
                **({(): gap_area} if gap_area > 0.0 else {}),
                (coverage_source_cell_ids[0],): union_area,
            },
        }

    basis = _tangent_basis(destination_center)
    fragments = [
        _project_polygon(
            (
                destination_center,
                destination_vertices[index],
                destination_vertices[(index + 1) % len(destination_vertices)],
            ),
            destination_center,
            basis,
        )
        for index in range(len(destination_vertices))
    ]
    lines: list[Line2] = []
    for source_pieces in coverage_by_source:
        for polygon in source_pieces:
            for index, start in enumerate(polygon):
                end = polygon[(index + 1) % len(polygon)]
                dx = end[0] - start[0]
                dy = end[1] - start[1]
                if dx * dx + dy * dy <= _DUPLICATE_VERTEX_DISTANCE_SQUARED:
                    continue
                candidate = _normalized_line(start, end)
                if not any(_coincident_lines(line, candidate) for line in lines):
                    lines.append(candidate)

    for line in lines:
        split_fragments: list[Polygon2] = []
        for fragment in fragments:
            values = [_normalized_line_value(line, point) for point in fragment]
            coordinate_scale = max(
                1.0,
                *(1.0 + abs(point[0]) + abs(point[1]) for point in fragment),
            )
            predicate_tolerance = 128.0 * _EPSILON * coordinate_scale
            if min(values) >= -predicate_tolerance or max(values) <= predicate_tolerance:
                split_fragments.append(fragment)
                continue
            positive = _split_clip_by_line(fragment, line, keep_positive=True)
            negative = _split_clip_by_line(fragment, line, keep_positive=False)
            if positive:
                split_fragments.append(positive)
            if negative:
                split_fragments.append(negative)
        fragments = split_fragments
        if len(fragments) > ARRANGEMENT_FRAGMENT_LIMIT:
            raise ValueError("replay coverage arrangement exceeded its complexity bound")

    partition_area = 0.0
    union_area = 0.0
    gap_area = 0.0
    excess_area = 0.0
    maximum_multiplicity = 0
    histogram: list[float] = []
    membership_area_terms: dict[tuple[int, ...], list[float]] = {}
    for fragment in fragments:
        representative = (
            sum(point[0] for point in fragment) / len(fragment),
            sum(point[1] for point in fragment) / len(fragment),
        )
        contributors = tuple(
            source_id
            for source_id, source_pieces in zip(
                coverage_source_cell_ids, coverage_by_source, strict=True
            )
            if any(
                _point_in_convex_polygon(representative, polygon)
                for polygon in source_pieces
            )
        )
        multiplicity = len(contributors)
        area_km2 = _spherical_polygon_area_km2(
            fragment, destination_center, basis, radius_km
        )
        partition_area += area_km2
        maximum_multiplicity = max(maximum_multiplicity, multiplicity)
        if len(histogram) <= multiplicity:
            histogram.extend([0.0] * (multiplicity + 1 - len(histogram)))
        histogram[multiplicity] += area_km2
        membership_area_terms.setdefault(contributors, []).append(area_km2)
        if multiplicity == 0:
            gap_area += area_km2
        else:
            union_area += area_km2
            excess_area += (multiplicity - 1) * area_km2

    partition_error = max(
        abs(partition_area - destination_area_km2),
        abs(union_area + gap_area - destination_area_km2),
        abs(union_area + excess_area - coverage_area_sum_km2),
    )
    return {
        "union_area_km2": union_area,
        "gap_area_km2": gap_area,
        "overlap_excess_area_km2": excess_area,
        "partition_closure_error_km2": partition_error,
        "maximum_multiplicity": maximum_multiplicity,
        "arrangement_line_count": len(lines),
        "arrangement_fragment_count": len(fragments),
        "area_km2_by_multiplicity": histogram,
        "area_km2_by_source_membership": {
            membership: math.fsum(terms)
            for membership, terms in membership_area_terms.items()
        },
    }


def _vec3(payload: Any, *, context: str) -> Vec3:
    if not isinstance(payload, list) or len(payload) != 3:
        raise TypeError(f"{context} must be a three-component array")
    result = tuple(float(component) for component in payload)
    if any(not math.isfinite(component) for component in result):
        raise ValueError(f"{context} must be finite")
    return result  # type: ignore[return-value]


def _binary64_long_double_forward_error_bounds(
    replay: dict[str, Any],
) -> tuple[float, float]:
    """Return absolute-area and dimensionless replay comparison bounds.

    ``gamma_n = n*u/(1-n*u)`` bounds a chain of binary64 roundings relative
    to exact (and, conservatively here, native long-double) arithmetic.  The
    operation count includes the geometry-path allowance above, one reduction
    per destination, and the largest independently observed arrangement
    fragment count.  Scaling by the complete sphere area bounds every local or
    global area output without allowing a large serialized value to inflate
    its own tolerance.
    """

    cell_count = int(replay["cell_count"])
    fragment_counts = replay["coverage_arrangement_fragment_count_by_cell"]
    maximum_fragment_count = max(fragment_counts, default=1)
    operation_count = (
        _GEOMETRY_FORWARD_ERROR_OPERATION_BUDGET
        + cell_count
        + maximum_fragment_count
    )
    accumulated_roundoff = operation_count * _EPSILON
    if accumulated_roundoff >= 1.0:
        raise ValueError("geometry replay forward-error budget is ill-conditioned")
    relative_bound = accumulated_roundoff / (1.0 - accumulated_roundoff)
    surface_area_km2 = (
        4.0 * math.pi * float(replay["radius_km"]) * float(replay["radius_km"])
    )
    area_bound_km2 = max(
        _GEOMETRY_FORWARD_ERROR_AREA_FLOOR_KM2,
        relative_bound * surface_area_km2,
    )
    return area_bound_km2, relative_bound


def _serialized_membership_area_by_cell(
    ledger: dict[str, Any],
    cell_count: int,
) -> list[dict[tuple[int, ...], float]]:
    """Decode the native coalesced contributor-set area classes."""

    payload = ledger.get("coverage_membership_area_class_ledger")
    if not isinstance(payload, dict):
        raise TypeError("native membership-area-class ledger is missing")
    offsets = payload.get("destination_offsets")
    areas = payload.get("area_km2")
    contributor_offsets = payload.get("contributor_offsets")
    source_ids = payload.get("source_cell_ids")
    if (
        not isinstance(offsets, list)
        or any(type(value) is not int for value in offsets)
        or not isinstance(areas, list)
        or any(type(value) not in (int, float) for value in areas)
        or not isinstance(contributor_offsets, list)
        or any(type(value) is not int for value in contributor_offsets)
        or not isinstance(source_ids, list)
        or any(type(value) is not int for value in source_ids)
    ):
        raise TypeError("native membership-area-class CSR has invalid types")
    class_count = len(areas)
    if (
        len(offsets) != cell_count + 1
        or offsets[0] != 0
        or offsets[-1] != class_count
        or any(left > right for left, right in zip(offsets, offsets[1:]))
        or len(contributor_offsets) != class_count + 1
        or contributor_offsets[0] != 0
        or contributor_offsets[-1] != len(source_ids)
        or any(
            left > right
            for left, right in zip(
                contributor_offsets, contributor_offsets[1:]
            )
        )
    ):
        raise ValueError("native membership-area-class CSR has invalid offsets")

    result: list[dict[tuple[int, ...], float]] = []
    for destination in range(cell_count):
        area_by_membership: dict[tuple[int, ...], float] = {}
        for area_class in range(offsets[destination], offsets[destination + 1]):
            area = float(areas[area_class])
            begin = contributor_offsets[area_class]
            end = contributor_offsets[area_class + 1]
            membership = tuple(source_ids[begin:end])
            if (
                not math.isfinite(area)
                or area <= 0.0
                or membership != tuple(sorted(set(membership)))
                or membership in area_by_membership
            ):
                raise ValueError(
                    "native membership-area classes are not canonical and unique"
                )
            area_by_membership[membership] = area
        result.append(area_by_membership)
    return result


def _load_geometry(
    world: dict[str, Any], *, max_cell_count: int
) -> tuple[list[Vec3], list[list[Vec3]], list[float], float]:
    cells = world.get("cells")
    if not isinstance(cells, list) or not cells:
        raise TypeError("world cells must be a non-empty array")
    if len(cells) > max_cell_count:
        raise ValueError(
            f"geometry replay is bounded to {max_cell_count} cells; got {len(cells)}"
        )
    centers: list[Vec3] = []
    rings: list[list[Vec3]] = []
    areas: list[float] = []
    for expected_id, cell in enumerate(cells):
        if not isinstance(cell, dict) or cell.get("id") != expected_id:
            raise ValueError("world cells must have canonical integer IDs")
        centers.append(_vec3(cell.get("position_3d"), context="cell center"))
        ring_payload = cell.get("control_volume_vertices_3d")
        if not isinstance(ring_payload, list) or len(ring_payload) < 3:
            raise TypeError("cell control-volume ring is missing")
        rings.append(
            [_vec3(vertex, context="control-volume vertex") for vertex in ring_payload]
        )
        area = float(cell.get("area_km2"))
        if not math.isfinite(area) or area <= 0.0:
            raise ValueError("cell area must be positive and finite")
        areas.append(area)
    radius_km = math.sqrt(math.fsum(areas) / (4.0 * math.pi))
    return centers, rings, areas, radius_km


def _step_kinematics(
    history: Sequence[Any], step_index: int, cell_count: int
) -> tuple[list[int], dict[int, Vec3], dict[int, float]]:
    step = history[step_index]
    if not isinstance(step, dict):
        raise TypeError("plate-motion step must be an object")
    if step_index == 0:
        source_plate_payload = step.get("cell_plate_ids")
    else:
        previous_step = history[step_index - 1]
        if not isinstance(previous_step, dict):
            raise TypeError("previous plate-motion step must be an object")
        source_plate_payload = previous_step.get("cell_plate_ids")
    if (
        not isinstance(source_plate_payload, list)
        or len(source_plate_payload) != cell_count
        or any(type(value) is not int for value in source_plate_payload)
    ):
        raise TypeError("source plate assignments must be an integer cell array")
    axes: dict[int, Vec3] = {}
    rotations: dict[int, float] = {}
    snapshots = step.get("plates")
    if not isinstance(snapshots, list) or not snapshots:
        raise TypeError("plate snapshots must be a non-empty array")
    for snapshot in snapshots:
        if not isinstance(snapshot, dict) or type(snapshot.get("plate_id")) is not int:
            raise TypeError("plate snapshot ID must be an integer")
        plate_id = snapshot["plate_id"]
        if plate_id in axes:
            raise ValueError("plate snapshot IDs must be unique")
        axes[plate_id] = _vec3(snapshot.get("rotation_axis"), context="plate axis")
        rotation = float(snapshot.get("step_rotation_deg"))
        if not math.isfinite(rotation):
            raise ValueError("plate step rotation must be finite")
        rotations[plate_id] = rotation
    if any(plate_id not in axes for plate_id in source_plate_payload):
        raise ValueError("source plate assignment has no kinematic snapshot")
    return list(source_plate_payload), axes, rotations


def replay_crust_coverage_geometry(
    world: dict[str, Any],
    step_index: int,
    *,
    max_cell_count: int = DEFAULT_MAX_CELL_COUNT,
) -> dict[str, Any]:
    """Recompute a crust-overlap coverage step without reading its native CSR.

    Returned edge arrays are canonical destination-major/source-minor arrays,
    matching the native ledger's ordering solely to make cross-language
    comparisons unambiguous.
    """

    if type(max_cell_count) is not int or max_cell_count <= 0:
        raise ValueError("max_cell_count must be a positive integer")
    history = world.get("plate_motion_history")
    if not isinstance(history, list) or not history:
        raise TypeError("plate motion history must be a non-empty array")
    if type(step_index) is not int or not 0 <= step_index < len(history):
        raise IndexError("plate-motion step index is out of range")
    centers, rings, areas, radius_km = _load_geometry(
        world, max_cell_count=max_cell_count
    )
    cell_count = len(centers)
    source_plate_ids, axes, rotations = _step_kinematics(
        history, step_index, cell_count
    )

    if all(rotation == 0.0 for rotation in rotations.values()):
        surface_area = math.fsum(areas)
        return {
            "algorithm": "independent_brute_force_cap_gnomonic_arrangement_v1",
            "pair_search": "identity_shortcut_matching_native_zero_rotation_semantics",
            "performance_scope": "O(N**2) moving-step cap discovery; small meshes only",
            "cell_count": cell_count,
            "radius_km": radius_km,
            "candidate_pair_count": cell_count,
            "destination_offsets": list(range(cell_count + 1)),
            "source_cell_ids": list(range(cell_count)),
            "overlap_area_km2": areas.copy(),
            "source_area_sum_km2": areas.copy(),
            "coverage_area_sum_km2_by_cell": areas.copy(),
            "covered_union_area_km2_by_cell": areas.copy(),
            "uncovered_gap_area_km2_by_cell": [0.0] * cell_count,
            "overlap_excess_area_km2_by_cell": [0.0] * cell_count,
            "maximum_coverage_multiplicity_by_cell": [1] * cell_count,
            "coverage_arrangement_line_count_by_cell": [0] * cell_count,
            "coverage_arrangement_fragment_count_by_cell": [1] * cell_count,
            "coverage_area_km2_by_source_membership_by_cell": [
                {(cell_id,): area}
                for cell_id, area in enumerate(areas)
            ],
            "global_coverage_area_km2_by_multiplicity": [0.0, surface_area],
            "global_uncovered_gap_area_km2": 0.0,
            "global_overlap_excess_area_km2": 0.0,
            "global_gap_overlap_balance_residual_km2": 0.0,
            "maximum_source_area_closure_error_km2": 0.0,
            "maximum_source_area_relative_closure_error": 0.0,
            "maximum_destination_partition_closure_error_km2": 0.0,
        }

    cap_radii = [
        max(_angular_distance(center, vertex) for vertex in ring)
        for center, ring in zip(centers, rings, strict=True)
    ]
    destination_bases = [_tangent_basis(center) for center in centers]
    destination_triangles: list[list[Polygon2]] = []
    for center, ring, basis in zip(
        centers, rings, destination_bases, strict=True
    ):
        destination_triangles.append(
            [
                _project_polygon(
                    (center, ring[index], ring[(index + 1) % len(ring)]),
                    center,
                    basis,
                )
                for index in range(len(ring))
            ]
        )

    # Each edge is source, destination, area, and the independently produced
    # overlap pieces expressed in the destination chart.
    edges: list[tuple[int, int, float, list[Polygon2]]] = []
    source_area_sums = [0.0] * cell_count
    candidate_pair_count = 0
    for source_id in range(cell_count):
        plate_id = source_plate_ids[source_id]
        axis = axes[plate_id]
        rotation = rotations[plate_id]
        rotated_center = _rotate(centers[source_id], axis, rotation)
        rotated_vertices = [
            _rotate(vertex, axis, rotation) for vertex in rings[source_id]
        ]
        for destination_id in range(cell_count):
            if (
                _angular_distance(rotated_center, centers[destination_id])
                > cap_radii[source_id]
                + cap_radii[destination_id]
                + _CAP_ANGLE_PADDING_RAD
            ):
                continue
            candidate_pair_count += 1
            basis = destination_bases[destination_id]
            overlap_pieces: list[Polygon2] = []
            area_km2 = 0.0
            for source_vertex_index in range(len(rotated_vertices)):
                source_triangle = _project_polygon(
                    (
                        rotated_center,
                        rotated_vertices[source_vertex_index],
                        rotated_vertices[
                            (source_vertex_index + 1) % len(rotated_vertices)
                        ],
                    ),
                    centers[destination_id],
                    basis,
                )
                for destination_triangle in destination_triangles[destination_id]:
                    overlap = _intersect_convex_polygons(
                        source_triangle.copy(), destination_triangle
                    )
                    if not overlap:
                        continue
                    piece_area = _spherical_polygon_area_km2(
                        overlap,
                        centers[destination_id],
                        basis,
                        radius_km,
                    )
                    if piece_area <= _PIECE_AREA_MIN_KM2:
                        continue
                    area_km2 += piece_area
                    overlap_pieces.append(overlap)
            minimum_area = max(
                _EDGE_AREA_ABSOLUTE_MIN_KM2,
                areas[source_id] * _EDGE_AREA_RELATIVE_MIN,
            )
            if area_km2 <= minimum_area:
                continue
            source_area_sums[source_id] += area_km2
            edges.append(
                (source_id, destination_id, area_km2, overlap_pieces)
            )

    edges.sort(key=lambda edge: (edge[1], edge[0]))
    destination_offsets = [0] * (cell_count + 1)
    source_ids: list[int] = []
    overlap_areas: list[float] = []
    coverage_sums = [0.0] * cell_count
    union_areas = [0.0] * cell_count
    gap_areas = [0.0] * cell_count
    excess_areas = [0.0] * cell_count
    maximum_multiplicities = [0] * cell_count
    line_counts = [0] * cell_count
    fragment_counts = [0] * cell_count
    membership_areas: list[dict[tuple[int, ...], float]] = [
        {} for _ in range(cell_count)
    ]
    global_histogram: list[float] = [0.0, 0.0]
    maximum_destination_error = 0.0
    edge_cursor = 0
    for destination_id in range(cell_count):
        destination_offsets[destination_id] = edge_cursor
        coverage_by_source: list[list[Polygon2]] = []
        coverage_source_cell_ids: list[int] = []
        while edge_cursor < len(edges) and edges[edge_cursor][1] == destination_id:
            source_id, _, area_km2, pieces = edges[edge_cursor]
            source_ids.append(source_id)
            overlap_areas.append(area_km2)
            coverage_sums[destination_id] += area_km2
            coverage_by_source.append(pieces)
            coverage_source_cell_ids.append(source_id)
            edge_cursor += 1
        coverage = _coverage_diagnostics(
            centers[destination_id],
            rings[destination_id],
            areas[destination_id],
            coverage_by_source,
            coverage_source_cell_ids,
            coverage_sums[destination_id],
            radius_km,
        )
        union_areas[destination_id] = coverage["union_area_km2"]
        gap_areas[destination_id] = coverage["gap_area_km2"]
        excess_areas[destination_id] = coverage["overlap_excess_area_km2"]
        maximum_multiplicities[destination_id] = coverage["maximum_multiplicity"]
        line_counts[destination_id] = coverage["arrangement_line_count"]
        fragment_counts[destination_id] = coverage["arrangement_fragment_count"]
        membership_areas[destination_id] = coverage[
            "area_km2_by_source_membership"
        ]
        maximum_destination_error = max(
            maximum_destination_error,
            coverage["partition_closure_error_km2"],
        )
        local_histogram = coverage["area_km2_by_multiplicity"]
        if len(global_histogram) < len(local_histogram):
            global_histogram.extend([0.0] * (len(local_histogram) - len(global_histogram)))
        for multiplicity, area_km2 in enumerate(local_histogram):
            global_histogram[multiplicity] += area_km2
    destination_offsets[cell_count] = len(edges)

    source_errors = [
        abs(actual - expected)
        for actual, expected in zip(source_area_sums, areas, strict=True)
    ]
    global_gap_area_km2 = sum(gap_areas)
    global_overlap_excess_area_km2 = sum(excess_areas)
    return {
        "algorithm": "independent_brute_force_cap_gnomonic_arrangement_v1",
        "pair_search": "brute_force_spherical_cap_v1",
        "performance_scope": "O(N**2) moving-step cap discovery; small meshes only",
        "cell_count": cell_count,
        "radius_km": radius_km,
        "candidate_pair_count": candidate_pair_count,
        "destination_offsets": destination_offsets,
        "source_cell_ids": source_ids,
        "overlap_area_km2": overlap_areas,
        "source_area_sum_km2": source_area_sums,
        "coverage_area_sum_km2_by_cell": coverage_sums,
        "covered_union_area_km2_by_cell": union_areas,
        "uncovered_gap_area_km2_by_cell": gap_areas,
        "overlap_excess_area_km2_by_cell": excess_areas,
        "maximum_coverage_multiplicity_by_cell": maximum_multiplicities,
        "coverage_arrangement_line_count_by_cell": line_counts,
        "coverage_arrangement_fragment_count_by_cell": fragment_counts,
        "coverage_area_km2_by_source_membership_by_cell": membership_areas,
        "global_coverage_area_km2_by_multiplicity": global_histogram,
        "global_uncovered_gap_area_km2": global_gap_area_km2,
        "global_overlap_excess_area_km2": global_overlap_excess_area_km2,
        "global_gap_overlap_balance_residual_km2": (
            global_overlap_excess_area_km2 - global_gap_area_km2
        ),
        "maximum_source_area_closure_error_km2": max(source_errors, default=0.0),
        "maximum_source_area_relative_closure_error": max(
            (
                error / area
                for error, area in zip(source_errors, areas, strict=True)
            ),
            default=0.0,
        ),
        "maximum_destination_partition_closure_error_km2": maximum_destination_error,
    }


def compare_crust_coverage_geometry(
    world: dict[str, Any],
    step_index: int,
    *,
    max_cell_count: int = DEFAULT_MAX_CELL_COUNT,
) -> dict[str, Any]:
    """Compare the independent replay with one serialized native ledger."""

    replay = replay_crust_coverage_geometry(
        world, step_index, max_cell_count=max_cell_count
    )
    history = world["plate_motion_history"]
    ledger = history[step_index]["crust_overlap_ledger"]
    failures: list[str] = []
    (
        area_forward_error_bound_km2,
        relative_forward_error_bound,
    ) = _binary64_long_double_forward_error_bounds(replay)
    for field in ("destination_offsets", "source_cell_ids"):
        if replay[field] != ledger.get(field):
            failures.append(f"independently discovered {field} differs from native ledger")

    area_fields = (
        "overlap_area_km2",
        "coverage_area_sum_km2_by_cell",
        "covered_union_area_km2_by_cell",
        "uncovered_gap_area_km2_by_cell",
        "overlap_excess_area_km2_by_cell",
        "global_coverage_area_km2_by_multiplicity",
    )
    maximum_area_difference = 0.0
    for field in area_fields:
        expected = ledger.get(field)
        actual = replay[field]
        if not isinstance(expected, list) or len(actual) != len(expected):
            failures.append(f"independent {field} shape differs from native ledger")
            continue
        for replayed, native in zip(actual, expected, strict=True):
            difference = abs(float(replayed) - float(native))
            maximum_area_difference = max(maximum_area_difference, difference)
            if difference > area_forward_error_bound_km2:
                failures.append(f"independent {field} differs from native ledger")
                break

    maximum_membership_area_difference = 0.0
    try:
        native_membership_areas = _serialized_membership_area_by_cell(
            ledger, replay["cell_count"]
        )
    except (TypeError, ValueError, OverflowError):
        failures.append(
            "native coverage membership-area-class ledger shape is invalid"
        )
    else:
        replayed_membership_areas = replay[
            "coverage_area_km2_by_source_membership_by_cell"
        ]
        membership_mismatch = False
        for replayed_by_membership, native_by_membership in zip(
            replayed_membership_areas,
            native_membership_areas,
            strict=True,
        ):
            for membership in (
                replayed_by_membership.keys() | native_by_membership.keys()
            ):
                difference = abs(
                    replayed_by_membership.get(membership, 0.0)
                    - native_by_membership.get(membership, 0.0)
                )
                maximum_membership_area_difference = max(
                    maximum_membership_area_difference, difference
                )
                maximum_area_difference = max(
                    maximum_area_difference, difference
                )
                if difference > area_forward_error_bound_km2:
                    membership_mismatch = True
        if membership_mismatch:
            failures.append(
                "independent contributor-set membership area differs from native ledger"
            )

    # Multiplicity is a physical/output result and must agree exactly.  Raw
    # line and fragment counts describe one particular arrangement execution;
    # they can differ when Python binary64 and native long-double predicates
    # take different but area-equivalent paths at a coincident boundary.
    multiplicity_field = "maximum_coverage_multiplicity_by_cell"
    if replay[multiplicity_field] != ledger.get(multiplicity_field):
        failures.append(
            f"independent {multiplicity_field} differs from native ledger"
        )
    native_line_counts = ledger.get("coverage_arrangement_line_count_by_cell")
    native_fragment_counts = ledger.get(
        "coverage_arrangement_fragment_count_by_cell"
    )
    line_count_mismatch_count = (
        sum(
            replayed != native
            for replayed, native in zip(
                replay["coverage_arrangement_line_count_by_cell"],
                native_line_counts,
                strict=True,
            )
        )
        if isinstance(native_line_counts, list)
        and len(native_line_counts) == replay["cell_count"]
        else replay["cell_count"]
    )
    fragment_count_mismatch_count = (
        sum(
            replayed != native
            for replayed, native in zip(
                replay["coverage_arrangement_fragment_count_by_cell"],
                native_fragment_counts,
                strict=True,
            )
        )
        if isinstance(native_fragment_counts, list)
        and len(native_fragment_counts) == replay["cell_count"]
        else replay["cell_count"]
    )

    # Compare every serialized geometric closure witness directly.  In
    # particular, do not infer the native source/destination maxima or its
    # signed gap/overlap residual merely from the already compared arrays: a
    # stale or independently corrupted telemetry scalar must fail on its own.
    scalar_area_fields = (
        "global_uncovered_gap_area_km2",
        "global_overlap_excess_area_km2",
        "maximum_source_area_closure_error_km2",
        "maximum_destination_partition_closure_error_km2",
        "global_gap_overlap_balance_residual_km2",
    )
    maximum_closure_telemetry_difference_km2 = 0.0
    for field in scalar_area_fields:
        replayed = float(replay[field])
        native = float(ledger.get(field, math.nan))
        difference = abs(replayed - native)
        maximum_area_difference = max(maximum_area_difference, difference)
        if field not in (
            "global_uncovered_gap_area_km2",
            "global_overlap_excess_area_km2",
        ):
            maximum_closure_telemetry_difference_km2 = max(
                maximum_closure_telemetry_difference_km2,
                difference,
            )
        if not math.isfinite(native) or difference > area_forward_error_bound_km2:
            failures.append(f"independent {field} differs from native ledger")

    relative_closure_field = "maximum_source_area_relative_closure_error"
    replayed_relative_closure = float(replay[relative_closure_field])
    native_relative_closure = float(
        ledger.get(relative_closure_field, math.nan)
    )
    relative_closure_difference = abs(
        replayed_relative_closure - native_relative_closure
    )
    if (
        not math.isfinite(native_relative_closure)
        or relative_closure_difference > relative_forward_error_bound
    ):
        failures.append(
            f"independent {relative_closure_field} differs from native ledger"
        )

    return {
        "passed": not failures,
        "failures": failures,
        "metrics": {
            "cell_count": replay["cell_count"],
            "candidate_pair_count": replay["candidate_pair_count"],
            "independently_discovered_edge_count": len(replay["source_cell_ids"]),
            "maximum_native_area_difference_km2": maximum_area_difference,
            "maximum_native_membership_area_difference_km2": (
                maximum_membership_area_difference
            ),
            "binary64_long_double_area_forward_error_bound_km2": (
                area_forward_error_bound_km2
            ),
            "binary64_long_double_relative_forward_error_bound": (
                relative_forward_error_bound
            ),
            "maximum_closure_telemetry_difference_km2": (
                maximum_closure_telemetry_difference_km2
            ),
            "source_relative_closure_difference": relative_closure_difference,
            "maximum_source_area_relative_closure_error": replay[
                "maximum_source_area_relative_closure_error"
            ],
            "maximum_destination_partition_closure_error_km2": replay[
                "maximum_destination_partition_closure_error_km2"
            ],
            "arrangement_line_count_mismatch_count": line_count_mismatch_count,
            "arrangement_fragment_count_mismatch_count": (
                fragment_count_mismatch_count
            ),
        },
        "replay": replay,
    }
