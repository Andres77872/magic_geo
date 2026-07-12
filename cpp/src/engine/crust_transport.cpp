#include "internal.hpp"

namespace magic_geo::detail {
namespace {

struct PlanarPoint {
    long double x = 0.0L;
    long double y = 0.0L;
};

struct TangentBasis {
    Vec3 first;
    Vec3 second;
};

struct NormalizedLine {
    long double a = 0.0L;
    long double b = 0.0L;
    long double c = 0.0L;
};

struct OverlapEdge {
    int source_cell_id = -1;
    int destination_cell_id = -1;
    double area_km2 = 0.0;
    double remap_residual_distance_km = 0.0;
    std::vector<std::vector<PlanarPoint>> destination_chart_polygons;
};

struct CoverageDiagnostics {
    double union_area_km2 = 0.0;
    double gap_area_km2 = 0.0;
    double overlap_excess_area_km2 = 0.0;
    double partition_closure_error_km2 = 0.0;
    int maximum_multiplicity = 0;
    int arrangement_line_count = 0;
    int arrangement_fragment_count = 0;
    std::vector<double> area_km2_by_multiplicity;
    struct MembershipAreaClass {
        double area_km2 = 0.0;
        int multiplicity = 0;
        Vec3 representative_unit;
        bool representative_available = false;
        std::vector<int> source_cell_ids;
        std::vector<int> source_plate_ids;
    };
    std::vector<MembershipAreaClass> membership_area_classes;
};

constexpr int COVERAGE_ARRANGEMENT_LOCAL_FRAGMENT_LIMIT = 16384;

long double precise_dot(Vec3 first, Vec3 second) {
    return static_cast<long double>(first.x) * second.x +
        static_cast<long double>(first.y) * second.y +
        static_cast<long double>(first.z) * second.z;
}

Vec3 checked_normalize(Vec3 value, const char* context) {
    const long double squared_norm = precise_dot(value, value);
    if (!std::isfinite(squared_norm) || squared_norm <= 1.0e-28L) {
        throw std::runtime_error(std::string(context) + " is geometrically degenerate");
    }
    return mul(value, 1.0 / std::sqrt(static_cast<double>(squared_norm)));
}

TangentBasis tangent_basis(Vec3 center) {
    const Vec3 reference = std::abs(center.z) < 0.8
        ? Vec3{0.0, 0.0, 1.0}
        : Vec3{1.0, 0.0, 0.0};
    const Vec3 first = checked_normalize(
        cross(reference, center), "crust-remap tangent axis"
    );
    return {
        first,
        checked_normalize(cross(center, first), "crust-remap tangent axis"),
    };
}

PlanarPoint project_gnomonic(
    Vec3 point,
    Vec3 center,
    const TangentBasis& basis
) {
    const long double denominator = precise_dot(center, point);
    if (denominator <= 1.0e-10L) {
        throw std::runtime_error(
            "crust-remap overlap candidate left the destination gnomonic hemisphere"
        );
    }
    return {
        precise_dot(basis.first, point) / denominator,
        precise_dot(basis.second, point) / denominator,
    };
}

Vec3 unproject_gnomonic(
    const PlanarPoint& point,
    Vec3 center,
    const TangentBasis& basis
) {
    return checked_normalize(
        add(
            center,
            add(
                mul(basis.first, static_cast<double>(point.x)),
                mul(basis.second, static_cast<double>(point.y))
            )
        ),
        "crust-remap overlap vertex"
    );
}

long double cross_2d(PlanarPoint first, PlanarPoint second) {
    return first.x * second.y - first.y * second.x;
}

PlanarPoint subtract_2d(PlanarPoint first, PlanarPoint second) {
    return {first.x - second.x, first.y - second.y};
}

long double line_value(
    PlanarPoint line_start,
    PlanarPoint line_end,
    PlanarPoint point
) {
    return cross_2d(
        subtract_2d(line_end, line_start),
        subtract_2d(point, line_start)
    );
}

long double planar_scale(PlanarPoint first, PlanarPoint second) {
    return 1.0L + std::abs(first.x) + std::abs(first.y) +
        std::abs(second.x) + std::abs(second.y);
}

bool line_inside(
    PlanarPoint line_start,
    PlanarPoint line_end,
    PlanarPoint point,
    bool keep_left
) {
    long double value = line_value(line_start, line_end, point);
    if (!keep_left) {
        value = -value;
    }
    const long double tolerance = 512.0L *
        static_cast<long double>(std::numeric_limits<double>::epsilon()) *
        planar_scale(line_start, line_end) *
        (1.0L + std::abs(point.x) + std::abs(point.y));
    return value >= -tolerance;
}

PlanarPoint line_intersection(
    PlanarPoint segment_start,
    PlanarPoint segment_end,
    PlanarPoint line_start,
    PlanarPoint line_end
) {
    const long double start_value = line_value(
        line_start, line_end, segment_start
    );
    const long double end_value = line_value(
        line_start, line_end, segment_end
    );
    const long double denominator = start_value - end_value;
    if (std::abs(denominator) <= 1.0e-30L) {
        return segment_start;
    }
    const long double fraction = std::clamp(
        start_value / denominator, 0.0L, 1.0L
    );
    return {
        segment_start.x + fraction * (segment_end.x - segment_start.x),
        segment_start.y + fraction * (segment_end.y - segment_start.y),
    };
}

void remove_duplicate_vertices(std::vector<PlanarPoint>& polygon) {
    std::vector<PlanarPoint> result;
    result.reserve(polygon.size());
    constexpr long double tolerance_squared = 1.0e-28L;
    for (PlanarPoint point : polygon) {
        if (!result.empty()) {
            const long double dx = point.x - result.back().x;
            const long double dy = point.y - result.back().y;
            if (dx * dx + dy * dy <= tolerance_squared) {
                continue;
            }
        }
        result.push_back(point);
    }
    if (result.size() > 1) {
        const long double dx = result.front().x - result.back().x;
        const long double dy = result.front().y - result.back().y;
        if (dx * dx + dy * dy <= tolerance_squared) {
            result.pop_back();
        }
    }
    polygon = std::move(result);
}

std::vector<PlanarPoint> clip_by_line(
    const std::vector<PlanarPoint>& subject,
    PlanarPoint line_start,
    PlanarPoint line_end,
    bool keep_left
) {
    if (subject.empty()) {
        return {};
    }
    std::vector<PlanarPoint> result;
    result.reserve(subject.size() + 2);
    for (std::size_t index = 0; index < subject.size(); ++index) {
        const PlanarPoint start = subject[index];
        const PlanarPoint end = subject[(index + 1) % subject.size()];
        const bool start_inside = line_inside(
            line_start, line_end, start, keep_left
        );
        const bool end_inside = line_inside(
            line_start, line_end, end, keep_left
        );
        if (start_inside && end_inside) {
            result.push_back(end);
        } else if (start_inside && !end_inside) {
            result.push_back(line_intersection(
                start, end, line_start, line_end
            ));
        } else if (!start_inside && end_inside) {
            result.push_back(line_intersection(
                start, end, line_start, line_end
            ));
            result.push_back(end);
        }
    }
    remove_duplicate_vertices(result);
    if (result.size() < 3) {
        result.clear();
    }
    return result;
}

NormalizedLine normalized_line(PlanarPoint start, PlanarPoint end) {
    const long double dx = end.x - start.x;
    const long double dy = end.y - start.y;
    const long double length = std::sqrt(dx * dx + dy * dy);
    if (!std::isfinite(length) || length <= 1.0e-16L) {
        throw std::runtime_error("crust-remap coverage arrangement has a degenerate line");
    }
    return {
        -dy / length,
        dx / length,
        (dy * start.x - dx * start.y) / length,
    };
}

long double normalized_line_value(const NormalizedLine& line, PlanarPoint point) {
    return line.a * point.x + line.b * point.y + line.c;
}

std::vector<PlanarPoint> split_clip_by_line(
    const std::vector<PlanarPoint>& subject,
    const NormalizedLine& line,
    bool keep_positive
) {
    if (subject.empty()) {
        return {};
    }
    std::vector<PlanarPoint> result;
    result.reserve(subject.size() + 2);
    for (std::size_t index = 0; index < subject.size(); ++index) {
        const PlanarPoint start = subject[index];
        const PlanarPoint end = subject[(index + 1) % subject.size()];
        long double start_value = normalized_line_value(line, start);
        long double end_value = normalized_line_value(line, end);
        if (!keep_positive) {
            start_value = -start_value;
            end_value = -end_value;
        }
        const bool start_inside = start_value >= 0.0L;
        const bool end_inside = end_value >= 0.0L;
        if (start_inside && end_inside) {
            result.push_back(end);
        } else if (start_inside != end_inside) {
            const long double denominator = start_value - end_value;
            if (std::abs(denominator) > 1.0e-30L) {
                const long double fraction = std::clamp(
                    start_value / denominator, 0.0L, 1.0L
                );
                PlanarPoint intersection = {
                    start.x + fraction * (end.x - start.x),
                    start.y + fraction * (end.y - start.y),
                };
                const long double residual = normalized_line_value(
                    line, intersection
                );
                intersection.x -= residual * line.a;
                intersection.y -= residual * line.b;
                result.push_back(intersection);
            }
            if (!start_inside && end_inside) {
                result.push_back(end);
            }
        }
    }
    remove_duplicate_vertices(result);
    if (result.size() < 3) {
        result.clear();
    }
    return result;
}

bool coincident_lines(const NormalizedLine& first, const NormalizedLine& second) {
    constexpr long double tolerance = 2.0e-12L;
    const bool same =
        std::abs(first.a - second.a) <= tolerance &&
        std::abs(first.b - second.b) <= tolerance &&
        std::abs(first.c - second.c) <= tolerance;
    const bool opposite =
        std::abs(first.a + second.a) <= tolerance &&
        std::abs(first.b + second.b) <= tolerance &&
        std::abs(first.c + second.c) <= tolerance;
    return same || opposite;
}

std::vector<PlanarPoint> project_polygon(
    const std::vector<Vec3>& vertices,
    Vec3 center,
    const TangentBasis& basis
) {
    std::vector<PlanarPoint> result;
    result.reserve(vertices.size());
    for (Vec3 vertex : vertices) {
        result.push_back(project_gnomonic(vertex, center, basis));
    }
    return result;
}

std::vector<PlanarPoint> intersect_convex_polygons(
    std::vector<PlanarPoint> subject,
    const std::vector<PlanarPoint>& clip_polygon
) {
    for (std::size_t edge_index = 0;
         edge_index < clip_polygon.size() && !subject.empty();
         ++edge_index) {
        subject = clip_by_line(
            subject,
            clip_polygon[edge_index],
            clip_polygon[(edge_index + 1) % clip_polygon.size()],
            true
        );
    }
    return subject;
}

double spherical_polygon_area_km2(
    const std::vector<PlanarPoint>& polygon,
    Vec3 chart_center,
    const TangentBasis& basis,
    double radius_km
) {
    if (polygon.size() < 3) {
        return 0.0;
    }
    std::vector<Vec3> vertices;
    vertices.reserve(polygon.size());
    Vec3 centroid_sum{};
    for (PlanarPoint point : polygon) {
        const Vec3 vertex = unproject_gnomonic(point, chart_center, basis);
        vertices.push_back(vertex);
        centroid_sum = add(centroid_sum, vertex);
    }
    const Vec3 reference = checked_normalize(
        centroid_sum, "crust-remap intersection centroid"
    );
    long double area = 0.0L;
    long double compensation = 0.0L;
    for (std::size_t index = 0; index < vertices.size(); ++index) {
        const Vec3 first = vertices[index];
        const Vec3 second = vertices[(index + 1) % vertices.size()];
        const long double determinant = precise_dot(
            reference, cross(first, second)
        );
        const long double denominator = 1.0L +
            precise_dot(reference, first) +
            precise_dot(first, second) +
            precise_dot(second, reference);
        const long double triangle_area = 2.0L * std::atan2(
            determinant, denominator
        );
        const long double adjusted = triangle_area - compensation;
        const long double updated = area + adjusted;
        compensation = (updated - area) - adjusted;
        area = updated;
    }
    if (!std::isfinite(area) || area < -5.0e-15L) {
        throw std::runtime_error(
            "crust-remap intersection polygon is reversed: signed_area_sr=" +
            num(static_cast<double>(area), 17) +
            ", vertex_count=" + std::to_string(polygon.size())
        );
    }
    if (area < 0.0L) {
        area = -area;
    }
    return static_cast<double>(area) * radius_km * radius_km;
}

bool point_in_convex_polygon(
    PlanarPoint point,
    const std::vector<PlanarPoint>& polygon
) {
    for (std::size_t edge_index = 0; edge_index < polygon.size(); ++edge_index) {
        if (!line_inside(
                polygon[edge_index],
                polygon[(edge_index + 1) % polygon.size()],
                point,
                true
            )) {
            return false;
        }
    }
    return true;
}

struct CoverageArrangement {
    TangentBasis basis;
    std::vector<std::vector<PlanarPoint>> fragments;
    int line_count = 0;
};

CoverageArrangement build_coverage_arrangement(
    const Cell& destination,
    const std::vector<std::vector<std::vector<PlanarPoint>>>& coverage_by_source
) {
    CoverageArrangement result;
    const TangentBasis basis = tangent_basis(destination.p);
    result.basis = basis;
    result.fragments.reserve(destination.control_volume_vertices.size());
    for (std::size_t vertex_index = 0;
         vertex_index < destination.control_volume_vertices.size();
         ++vertex_index) {
        result.fragments.push_back(project_polygon(
            {
                destination.p,
                destination.control_volume_vertices[vertex_index],
                destination.control_volume_vertices[
                    (vertex_index + 1) %
                        destination.control_volume_vertices.size()
                ],
            },
            destination.p,
            basis
        ));
    }
    std::vector<NormalizedLine> lines;
    for (const auto& source_pieces : coverage_by_source) {
        for (const auto& polygon : source_pieces) {
            for (std::size_t edge_index = 0; edge_index < polygon.size(); ++edge_index) {
                const PlanarPoint start = polygon[edge_index];
                const PlanarPoint end = polygon[(edge_index + 1) % polygon.size()];
                const long double dx = end.x - start.x;
                const long double dy = end.y - start.y;
                if (dx * dx + dy * dy <= 1.0e-28L) {
                    continue;
                }
                const NormalizedLine candidate = normalized_line(start, end);
                if (std::none_of(lines.begin(), lines.end(), [&](const NormalizedLine& line) {
                    return coincident_lines(line, candidate);
                })) {
                    lines.push_back(candidate);
                }
            }
        }
    }
    for (const NormalizedLine& line : lines) {
        std::vector<std::vector<PlanarPoint>> split_fragments;
        split_fragments.reserve(result.fragments.size() * 2);
        for (const auto& fragment : result.fragments) {
            long double minimum_value = std::numeric_limits<long double>::infinity();
            long double maximum_value = -std::numeric_limits<long double>::infinity();
            long double coordinate_scale = 1.0L;
            for (PlanarPoint point : fragment) {
                const long double value = normalized_line_value(line, point);
                minimum_value = std::min(minimum_value, value);
                maximum_value = std::max(maximum_value, value);
                coordinate_scale = std::max(
                    coordinate_scale,
                    1.0L + std::abs(point.x) + std::abs(point.y)
                );
            }
            const long double predicate_tolerance = 128.0L *
                static_cast<long double>(std::numeric_limits<double>::epsilon()) *
                coordinate_scale;
            if (
                minimum_value >= -predicate_tolerance ||
                maximum_value <= predicate_tolerance
            ) {
                split_fragments.push_back(fragment);
                continue;
            }
            std::vector<PlanarPoint> left = split_clip_by_line(
                fragment, line, true
            );
            std::vector<PlanarPoint> right = split_clip_by_line(
                fragment, line, false
            );
            if (!left.empty()) {
                split_fragments.push_back(std::move(left));
            }
            if (!right.empty()) {
                split_fragments.push_back(std::move(right));
            }
        }
        result.fragments = std::move(split_fragments);
        if (result.fragments.size() >
            static_cast<std::size_t>(COVERAGE_ARRANGEMENT_LOCAL_FRAGMENT_LIMIT)) {
            throw std::runtime_error(
                "crust-remap coverage arrangement exceeded its local complexity bound"
            );
        }
    }
    result.line_count = static_cast<int>(lines.size());
    return result;
}

PlanarPoint planar_fragment_representative(
    const std::vector<PlanarPoint>& fragment
) {
    if (fragment.empty()) {
        throw std::runtime_error(
            "crust-remap coverage fragment has no representative"
        );
    }
    PlanarPoint representative{};
    for (PlanarPoint point : fragment) {
        representative.x += point.x;
        representative.y += point.y;
    }
    representative.x /= static_cast<long double>(fragment.size());
    representative.y /= static_cast<long double>(fragment.size());
    return representative;
}

CoverageDiagnostics coverage_diagnostics(
    const Cell& destination,
    const std::vector<std::vector<std::vector<PlanarPoint>>>& coverage_by_source,
    const std::vector<int>& coverage_source_cell_ids,
    const std::vector<int>& coverage_source_plate_ids,
    double coverage_area_sum_km2,
    double radius_km
) {
    if (
        coverage_source_cell_ids.size() != coverage_by_source.size() ||
        coverage_source_plate_ids.size() != coverage_by_source.size()
    ) {
        throw std::runtime_error(
            "crust-remap coverage membership inputs have inconsistent shapes"
        );
    }
    for (std::size_t source_index = 0;
         source_index < coverage_source_cell_ids.size();
         ++source_index) {
        if (
            coverage_source_cell_ids[source_index] < 0 ||
            coverage_source_plate_ids[source_index] < 0 ||
            (source_index > 0 &&
                coverage_source_cell_ids[source_index - 1] >=
                    coverage_source_cell_ids[source_index])
        ) {
            throw std::runtime_error(
                "crust-remap coverage sources are not canonical"
            );
        }
    }

    CoverageDiagnostics result;
    if (coverage_by_source.empty()) {
        result.gap_area_km2 = destination.area_km2;
        result.arrangement_fragment_count = 1;
        result.area_km2_by_multiplicity = {destination.area_km2};
        result.membership_area_classes.push_back({
            destination.area_km2,
            0,
            destination.p,
            true,
            {},
            {},
        });
        return result;
    }

    const CoverageArrangement arrangement = build_coverage_arrangement(
        destination, coverage_by_source
    );
    result.arrangement_line_count = arrangement.line_count;
    result.arrangement_fragment_count = static_cast<int>(
        arrangement.fragments.size()
    );

    struct MembershipAreaClassAccumulator {
        CoverageDiagnostics::MembershipAreaClass area_class;
        long double area_sum_km2 = 0.0L;
        long double area_sum_compensation_km2 = 0.0L;
        double representative_atomic_area_km2 = -1.0;
    };
    std::map<std::vector<int>, MembershipAreaClassAccumulator>
        class_by_source_membership;
    double partition_area_km2 = 0.0;
    for (const auto& fragment : arrangement.fragments) {
        const PlanarPoint representative =
            planar_fragment_representative(fragment);
        CoverageDiagnostics::MembershipAreaClass retained;
        retained.representative_unit = unproject_gnomonic(
            representative, destination.p, arrangement.basis
        );
        retained.representative_available = true;
        for (std::size_t source_index = 0;
             source_index < coverage_by_source.size();
             ++source_index) {
            const bool contributes = std::any_of(
                coverage_by_source[source_index].begin(),
                coverage_by_source[source_index].end(),
                [&](const std::vector<PlanarPoint>& polygon) {
                    return point_in_convex_polygon(representative, polygon);
                }
            );
            if (contributes) {
                retained.source_cell_ids.push_back(
                    coverage_source_cell_ids[source_index]
                );
                retained.source_plate_ids.push_back(
                    coverage_source_plate_ids[source_index]
                );
            }
        }
        const double area_km2 = spherical_polygon_area_km2(
            fragment, destination.p, arrangement.basis, radius_km
        );
        retained.area_km2 = area_km2;
        retained.multiplicity = static_cast<int>(
            retained.source_cell_ids.size()
        );
        const int multiplicity = retained.multiplicity;
        MembershipAreaClassAccumulator& accumulator =
            class_by_source_membership[retained.source_cell_ids];
        if (accumulator.representative_atomic_area_km2 < 0.0) {
            accumulator.area_class = retained;
        } else if (
            accumulator.area_class.source_plate_ids !=
                retained.source_plate_ids
        ) {
            throw std::runtime_error(
                "crust-remap coverage membership-area-class plate IDs are inconsistent"
            );
        }
        const bool lower_representative =
            retained.representative_unit.x <
                accumulator.area_class.representative_unit.x ||
            (retained.representative_unit.x ==
                accumulator.area_class.representative_unit.x &&
             (retained.representative_unit.y <
                accumulator.area_class.representative_unit.y ||
              (retained.representative_unit.y ==
                    accumulator.area_class.representative_unit.y &&
               retained.representative_unit.z <
                    accumulator.area_class.representative_unit.z)));
        if (
            area_km2 > accumulator.representative_atomic_area_km2 ||
            (area_km2 == accumulator.representative_atomic_area_km2 &&
                lower_representative)
        ) {
            accumulator.area_class.representative_unit =
                retained.representative_unit;
            accumulator.area_class.representative_available =
                retained.representative_available;
            accumulator.representative_atomic_area_km2 = area_km2;
        }
        const long double adjusted_area = static_cast<long double>(area_km2) -
            accumulator.area_sum_compensation_km2;
        const long double updated_area =
            accumulator.area_sum_km2 + adjusted_area;
        accumulator.area_sum_compensation_km2 =
            (updated_area - accumulator.area_sum_km2) - adjusted_area;
        accumulator.area_sum_km2 = updated_area;
        partition_area_km2 += area_km2;
        result.maximum_multiplicity = std::max(
            result.maximum_multiplicity, multiplicity
        );
        if (result.area_km2_by_multiplicity.size() <=
            static_cast<std::size_t>(multiplicity)) {
            result.area_km2_by_multiplicity.resize(
                static_cast<std::size_t>(multiplicity + 1), 0.0
            );
        }
        result.area_km2_by_multiplicity[
            static_cast<std::size_t>(multiplicity)
        ] += area_km2;
        if (multiplicity == 0) {
            result.gap_area_km2 += area_km2;
        } else {
            result.union_area_km2 += area_km2;
            result.overlap_excess_area_km2 +=
                static_cast<double>(multiplicity - 1) * area_km2;
        }
    }
    result.partition_closure_error_km2 = std::max({
        std::abs(partition_area_km2 - destination.area_km2),
        std::abs(
            result.union_area_km2 + result.gap_area_km2 - destination.area_km2
        ),
        std::abs(
            result.union_area_km2 + result.overlap_excess_area_km2 -
            coverage_area_sum_km2
        ),
    });
    const double tolerance = std::max(1.0e-7, destination.area_km2 * 5.0e-10);
    if (result.partition_closure_error_km2 > tolerance) {
        throw std::runtime_error(
            "crust-remap coverage multiplicity arrangement did not close"
        );
    }
    result.membership_area_classes.reserve(class_by_source_membership.size());
    for (auto& [source_membership, accumulator] :
         class_by_source_membership) {
        if (
            source_membership != accumulator.area_class.source_cell_ids ||
            accumulator.representative_atomic_area_km2 < 0.0
        ) {
            throw std::runtime_error(
                "crust-remap coverage membership-area-class coalescing failed"
            );
        }
        accumulator.area_class.area_km2 = static_cast<double>(
            accumulator.area_sum_km2
        );
        result.membership_area_classes.push_back(
            std::move(accumulator.area_class)
        );
    }
    std::sort(
        result.membership_area_classes.begin(),
        result.membership_area_classes.end(),
        [](const CoverageDiagnostics::MembershipAreaClass& left,
           const CoverageDiagnostics::MembershipAreaClass& right) {
            if (left.multiplicity != right.multiplicity) {
                return left.multiplicity < right.multiplicity;
            }
            if (left.source_cell_ids != right.source_cell_ids) {
                return left.source_cell_ids < right.source_cell_ids;
            }
            if (left.representative_unit.x != right.representative_unit.x) {
                return left.representative_unit.x < right.representative_unit.x;
            }
            if (left.representative_unit.y != right.representative_unit.y) {
                return left.representative_unit.y < right.representative_unit.y;
            }
            if (left.representative_unit.z != right.representative_unit.z) {
                return left.representative_unit.z < right.representative_unit.z;
            }
            return left.area_km2 < right.area_km2;
        }
    );
    return result;
}

struct KdNode {
    int point_id = -1;
    int left = -1;
    int right = -1;
    std::array<double, 3> minimum{};
    std::array<double, 3> maximum{};
};

double coordinate(Vec3 point, int axis) {
    return axis == 0 ? point.x : (axis == 1 ? point.y : point.z);
}

class SphericalPointIndex {
public:
    explicit SphericalPointIndex(const std::vector<Cell>& cells) : cells_(cells) {
        order_.resize(cells.size());
        std::iota(order_.begin(), order_.end(), 0);
        nodes_.reserve(cells.size());
        root_ = build(0, static_cast<int>(order_.size()), 0);
    }

    std::vector<int> within_angle(Vec3 query, double angle_rad) const {
        std::vector<int> result;
        const double threshold = angle_rad >= PI
            ? -1.0
            : std::cos(std::max(0.0, angle_rad));
        query_radius(root_, normalize(query), threshold, result);
        std::sort(result.begin(), result.end());
        return result;
    }

private:
    int build(int begin, int end, int depth) {
        if (begin >= end) {
            return -1;
        }
        const int axis = depth % 3;
        const int middle = begin + (end - begin) / 2;
        std::nth_element(
            order_.begin() + begin,
            order_.begin() + middle,
            order_.begin() + end,
            [&](int left, int right) {
                const double left_value = coordinate(
                    cells_[static_cast<std::size_t>(left)].p, axis
                );
                const double right_value = coordinate(
                    cells_[static_cast<std::size_t>(right)].p, axis
                );
                return left_value != right_value
                    ? left_value < right_value
                    : left < right;
            }
        );
        const int node_id = static_cast<int>(nodes_.size());
        nodes_.emplace_back();
        KdNode& node = nodes_.back();
        node.point_id = order_[static_cast<std::size_t>(middle)];
        const Vec3 point = cells_[static_cast<std::size_t>(node.point_id)].p;
        node.minimum = {point.x, point.y, point.z};
        node.maximum = node.minimum;
        node.left = build(begin, middle, depth + 1);
        node.right = build(middle + 1, end, depth + 1);
        include_child(node_id, node.left);
        include_child(node_id, node.right);
        return node_id;
    }

    void include_child(int node_id, int child_id) {
        if (child_id < 0) {
            return;
        }
        KdNode& node = nodes_[static_cast<std::size_t>(node_id)];
        const KdNode& child = nodes_[static_cast<std::size_t>(child_id)];
        for (int axis = 0; axis < 3; ++axis) {
            node.minimum[static_cast<std::size_t>(axis)] = std::min(
                node.minimum[static_cast<std::size_t>(axis)],
                child.minimum[static_cast<std::size_t>(axis)]
            );
            node.maximum[static_cast<std::size_t>(axis)] = std::max(
                node.maximum[static_cast<std::size_t>(axis)],
                child.maximum[static_cast<std::size_t>(axis)]
            );
        }
    }

    long double maximum_dot_bound(const KdNode& node, Vec3 query) const {
        const std::array<double, 3> values = {query.x, query.y, query.z};
        long double bound = 0.0L;
        long double magnitude = 0.0L;
        for (int axis = 0; axis < 3; ++axis) {
            const double endpoint = values[static_cast<std::size_t>(axis)] >= 0.0
                ? node.maximum[static_cast<std::size_t>(axis)]
                : node.minimum[static_cast<std::size_t>(axis)];
            const long double term =
                static_cast<long double>(values[static_cast<std::size_t>(axis)]) *
                endpoint;
            bound += term;
            magnitude += std::abs(term);
        }
        return bound + 128.0L *
            static_cast<long double>(std::numeric_limits<double>::epsilon()) *
            (1.0L + magnitude);
    }

    void query_radius(
        int node_id,
        Vec3 query,
        double threshold,
        std::vector<int>& result
    ) const {
        if (node_id < 0) {
            return;
        }
        const KdNode& node = nodes_[static_cast<std::size_t>(node_id)];
        if (maximum_dot_bound(node, query) < static_cast<long double>(threshold)) {
            return;
        }
        if (dot(query, cells_[static_cast<std::size_t>(node.point_id)].p) >= threshold) {
            result.push_back(node.point_id);
        }
        query_radius(node.left, query, threshold, result);
        query_radius(node.right, query, threshold, result);
    }

    const std::vector<Cell>& cells_;
    std::vector<int> order_;
    std::vector<KdNode> nodes_;
    int root_ = -1;
};

double cell_cap_radius(const Cell& cell) {
    double radius = 0.0;
    for (Vec3 vertex : cell.control_volume_vertices) {
        radius = std::max(radius, angular_distance(cell.p, vertex));
    }
    return radius;
}

void initialize_plan_arrays(CrustTransportPlan& plan, std::size_t cell_count) {
    plan.destination_offsets.assign(cell_count + 1, 0);
    plan.coverage_membership_area_class_count_by_cell.assign(cell_count, 0);
    plan.coverage_membership_area_class_destination_offsets.assign(
        cell_count + 1, 0
    );
    plan.coverage_membership_area_class_contributor_offsets.assign(1, 0);
    plan.source_kinematic_distance_km.assign(cell_count, 0.0);
    plan.dominant_source_cell_ids.assign(cell_count, -1);
    plan.contributor_count_by_cell.assign(cell_count, 0);
    plan.dominant_source_volume_fraction_by_cell.assign(cell_count, 0.0);
    plan.coverage_area_sum_km2_by_cell.assign(cell_count, 0.0);
    plan.covered_union_area_km2_by_cell.assign(cell_count, 0.0);
    plan.uncovered_gap_area_km2_by_cell.assign(cell_count, 0.0);
    plan.overlap_excess_area_km2_by_cell.assign(cell_count, 0.0);
    plan.maximum_coverage_multiplicity_by_cell.assign(cell_count, 0);
    plan.coverage_arrangement_line_count_by_cell.assign(cell_count, 0);
    plan.coverage_arrangement_fragment_count_by_cell.assign(cell_count, 0);
    plan.remapped_crust_type_by_cell.assign(cell_count, 0);
    plan.remapped_lithology_by_cell.assign(cell_count, 0);
    plan.remapped_crust_age_ma_by_cell.assign(cell_count, 0.0);
    plan.remapped_crust_thickness_km_by_cell.assign(cell_count, 0.0);
    plan.remapped_crust_density_by_cell.assign(cell_count, 0.0);
}

void append_coverage_membership_area_classes(
    CrustTransportPlan& plan,
    std::size_t destination_id,
    const CoverageDiagnostics& coverage
) {
    if (
        destination_id >=
            plan.coverage_membership_area_class_destination_offsets.size() - 1 ||
        plan.coverage_membership_area_class_destination_offsets[
            destination_id
        ] != static_cast<int>(
            plan.coverage_membership_area_class_area_km2.size()
        )
    ) {
        throw std::runtime_error(
            "crust-remap coverage membership-area-class append is not canonical"
        );
    }
    for (const CoverageDiagnostics::MembershipAreaClass& area_class :
         coverage.membership_area_classes) {
        if (
            area_class.source_cell_ids.size() !=
                area_class.source_plate_ids.size() ||
            area_class.multiplicity !=
                static_cast<int>(area_class.source_cell_ids.size())
        ) {
            throw std::runtime_error(
                "crust-remap coverage fragment membership shape is invalid"
            );
        }
        plan.coverage_membership_area_class_area_km2.push_back(
            area_class.area_km2
        );
        plan.coverage_membership_area_class_multiplicity.push_back(
            area_class.multiplicity
        );
        plan.coverage_membership_area_class_representative_unit_x.push_back(
            area_class.representative_unit.x
        );
        plan.coverage_membership_area_class_representative_unit_y.push_back(
            area_class.representative_unit.y
        );
        plan.coverage_membership_area_class_representative_unit_z.push_back(
            area_class.representative_unit.z
        );
        plan.coverage_membership_area_class_representative_available.push_back(
            area_class.representative_available ? 1 : 0
        );
        plan.coverage_membership_area_class_source_cell_ids.insert(
            plan.coverage_membership_area_class_source_cell_ids.end(),
            area_class.source_cell_ids.begin(),
            area_class.source_cell_ids.end()
        );
        plan.coverage_membership_area_class_source_plate_ids.insert(
            plan.coverage_membership_area_class_source_plate_ids.end(),
            area_class.source_plate_ids.begin(),
            area_class.source_plate_ids.end()
        );
        plan.coverage_membership_area_class_contributor_offsets.push_back(
            static_cast<int>(
                plan.coverage_membership_area_class_source_cell_ids.size()
            )
        );
    }
    const int class_count = static_cast<int>(
        coverage.membership_area_classes.size()
    );
    plan.coverage_membership_area_class_count_by_cell[destination_id] =
        class_count;
    plan.maximum_coverage_membership_area_class_count = std::max(
        plan.maximum_coverage_membership_area_class_count, class_count
    );
    plan.coverage_membership_area_class_destination_offsets[
        destination_id + 1
    ] = static_cast<int>(
        plan.coverage_membership_area_class_area_km2.size()
    );
}

void validate_coverage_membership_area_class_ledger(
    const CrustTransportPlan& plan,
    const std::vector<Cell>& cells,
    const std::vector<int>& source_plate_ids
) {
    const std::size_t cell_count = cells.size();
    const std::size_t class_count =
        plan.coverage_membership_area_class_area_km2.size();
    if (
        source_plate_ids.size() != cell_count ||
        plan.destination_offsets.size() != cell_count + 1 ||
        plan.destination_offsets.front() != 0 ||
        plan.destination_offsets.back() !=
            static_cast<int>(plan.source_cell_ids.size()) ||
        plan.overlap_area_km2.size() != plan.source_cell_ids.size() ||
        plan.coverage_arrangement_fragment_count_by_cell.size() != cell_count ||
        plan.coverage_membership_area_class_count_by_cell.size() != cell_count ||
        plan.coverage_membership_area_class_destination_offsets.size() !=
            cell_count + 1 ||
        plan.coverage_membership_area_class_destination_offsets.front() != 0 ||
        plan.coverage_membership_area_class_destination_offsets.back() !=
            static_cast<int>(class_count) ||
        plan.coverage_membership_area_class_multiplicity.size() != class_count ||
        plan.coverage_membership_area_class_representative_unit_x.size() !=
            class_count ||
        plan.coverage_membership_area_class_representative_unit_y.size() !=
            class_count ||
        plan.coverage_membership_area_class_representative_unit_z.size() !=
            class_count ||
        plan.coverage_membership_area_class_representative_available.size() !=
            class_count ||
        plan.coverage_membership_area_class_contributor_offsets.size() !=
            class_count + 1 ||
        plan.coverage_membership_area_class_contributor_offsets.front() != 0 ||
        plan.coverage_membership_area_class_contributor_offsets.back() !=
            static_cast<int>(
                plan.coverage_membership_area_class_source_cell_ids.size()
            ) ||
        plan.coverage_membership_area_class_source_cell_ids.size() !=
            plan.coverage_membership_area_class_source_plate_ids.size()
    ) {
        throw std::runtime_error(
            "crust-remap coverage membership-area-class ledger shape is invalid"
        );
    }

    std::vector<double> area_by_multiplicity;
    int observed_maximum_multiplicity = 0;
    int observed_maximum_class_count = 0;
    const auto class_less = [&](int left_id, int right_id) {
        const std::size_t left = static_cast<std::size_t>(left_id);
        const std::size_t right = static_cast<std::size_t>(right_id);
        if (plan.coverage_membership_area_class_multiplicity[left] !=
            plan.coverage_membership_area_class_multiplicity[right]) {
            return plan.coverage_membership_area_class_multiplicity[left] <
                plan.coverage_membership_area_class_multiplicity[right];
        }
        const int left_begin =
            plan.coverage_membership_area_class_contributor_offsets[left];
        const int left_end =
            plan.coverage_membership_area_class_contributor_offsets[left + 1];
        const int right_begin =
            plan.coverage_membership_area_class_contributor_offsets[right];
        const int right_end =
            plan.coverage_membership_area_class_contributor_offsets[right + 1];
        if (!std::equal(
                plan.coverage_membership_area_class_source_cell_ids.begin() +
                    left_begin,
                plan.coverage_membership_area_class_source_cell_ids.begin() +
                    left_end,
                plan.coverage_membership_area_class_source_cell_ids.begin() +
                    right_begin,
                plan.coverage_membership_area_class_source_cell_ids.begin() +
                    right_end
            )) {
            return std::lexicographical_compare(
                plan.coverage_membership_area_class_source_cell_ids.begin() +
                    left_begin,
                plan.coverage_membership_area_class_source_cell_ids.begin() +
                    left_end,
                plan.coverage_membership_area_class_source_cell_ids.begin() +
                    right_begin,
                plan.coverage_membership_area_class_source_cell_ids.begin() +
                    right_end
            );
        }
        if (plan.coverage_membership_area_class_representative_unit_x[left] !=
            plan.coverage_membership_area_class_representative_unit_x[right]) {
            return plan.coverage_membership_area_class_representative_unit_x[
                left
            ] < plan.coverage_membership_area_class_representative_unit_x[right];
        }
        if (plan.coverage_membership_area_class_representative_unit_y[left] !=
            plan.coverage_membership_area_class_representative_unit_y[right]) {
            return plan.coverage_membership_area_class_representative_unit_y[
                left
            ] < plan.coverage_membership_area_class_representative_unit_y[right];
        }
        if (plan.coverage_membership_area_class_representative_unit_z[left] !=
            plan.coverage_membership_area_class_representative_unit_z[right]) {
            return plan.coverage_membership_area_class_representative_unit_z[
                left
            ] < plan.coverage_membership_area_class_representative_unit_z[right];
        }
        return plan.coverage_membership_area_class_area_km2[left] <
            plan.coverage_membership_area_class_area_km2[right];
    };
    for (std::size_t destination_id = 0;
         destination_id < cell_count;
         ++destination_id) {
        const int class_begin =
            plan.coverage_membership_area_class_destination_offsets[
                destination_id
            ];
        const int class_end =
            plan.coverage_membership_area_class_destination_offsets[
                destination_id + 1
            ];
        if (
            class_begin < 0 ||
            class_end < class_begin ||
            class_end > static_cast<int>(class_count) ||
            class_end - class_begin !=
                plan.coverage_membership_area_class_count_by_cell[
                    destination_id
                ] ||
            class_end == class_begin ||
            class_end - class_begin >
                plan.coverage_arrangement_fragment_count_by_cell[
                    destination_id
                ]
        ) {
            throw std::runtime_error(
                "crust-remap coverage membership-area-class destination offsets are invalid"
            );
        }
        observed_maximum_class_count = std::max(
            observed_maximum_class_count, class_end - class_begin
        );
        const int edge_begin = plan.destination_offsets[destination_id];
        const int edge_end = plan.destination_offsets[destination_id + 1];
        if (
            edge_begin < 0 || edge_end < edge_begin ||
            edge_end > static_cast<int>(plan.source_cell_ids.size()) ||
            !std::is_sorted(
                plan.source_cell_ids.begin() + edge_begin,
                plan.source_cell_ids.begin() + edge_end
            ) ||
            std::adjacent_find(
                plan.source_cell_ids.begin() + edge_begin,
                plan.source_cell_ids.begin() + edge_end
            ) != plan.source_cell_ids.begin() + edge_end
        ) {
            throw std::runtime_error(
                "crust-remap coverage membership-area-class source column is invalid"
            );
        }

        double destination_class_area_km2 = 0.0;
        int destination_maximum_multiplicity = 0;
        std::vector<double> reconstructed_edge_area_km2(
            static_cast<std::size_t>(edge_end - edge_begin), 0.0
        );
        for (int class_id = class_begin;
             class_id < class_end;
             ++class_id) {
            const std::size_t class_index =
                static_cast<std::size_t>(class_id);
            const double area_km2 =
                plan.coverage_membership_area_class_area_km2[class_index];
            const int multiplicity =
                plan.coverage_membership_area_class_multiplicity[class_index];
            const int contributor_begin =
                plan.coverage_membership_area_class_contributor_offsets[
                    class_index
                ];
            const int contributor_end =
                plan.coverage_membership_area_class_contributor_offsets[
                    class_index + 1
                ];
            if (
                !std::isfinite(area_km2) || area_km2 <= 0.0 ||
                multiplicity < 0 ||
                contributor_begin < 0 ||
                contributor_end < contributor_begin ||
                contributor_end > static_cast<int>(
                    plan.coverage_membership_area_class_source_cell_ids.size()
                ) ||
                contributor_end - contributor_begin != multiplicity
            ) {
                throw std::runtime_error(
                    "crust-remap coverage membership-area-class area or multiplicity is invalid"
                );
            }
            if (
                class_id > class_begin &&
                class_less(class_id, class_id - 1)
            ) {
                throw std::runtime_error(
                    "crust-remap coverage membership-area classes are not canonically ordered"
                );
            }
            if (class_id > class_begin) {
                const std::size_t previous_index =
                    static_cast<std::size_t>(class_id - 1);
                const int previous_begin =
                    plan.coverage_membership_area_class_contributor_offsets[
                        previous_index
                    ];
                const int previous_end =
                    plan.coverage_membership_area_class_contributor_offsets[
                        previous_index + 1
                    ];
                if (std::equal(
                        plan.coverage_membership_area_class_source_cell_ids.begin() +
                            previous_begin,
                        plan.coverage_membership_area_class_source_cell_ids.begin() +
                            previous_end,
                        plan.coverage_membership_area_class_source_cell_ids.begin() +
                            contributor_begin,
                        plan.coverage_membership_area_class_source_cell_ids.begin() +
                            contributor_end
                    )) {
                    throw std::runtime_error(
                        "crust-remap coverage membership-area classes were not coalesced"
                    );
                }
            }
            int previous_source_cell_id = -1;
            for (int contributor_id = contributor_begin;
                 contributor_id < contributor_end;
                 ++contributor_id) {
                const int source_cell_id =
                    plan.coverage_membership_area_class_source_cell_ids[
                        static_cast<std::size_t>(contributor_id)
                    ];
                const int source_plate_id =
                    plan.coverage_membership_area_class_source_plate_ids[
                        static_cast<std::size_t>(contributor_id)
                    ];
                const auto edge_source = std::lower_bound(
                    plan.source_cell_ids.begin() + edge_begin,
                    plan.source_cell_ids.begin() + edge_end,
                    source_cell_id
                );
                if (
                    source_cell_id <= previous_source_cell_id ||
                    source_cell_id >= static_cast<int>(cell_count) ||
                    source_plate_id != source_plate_ids[
                        static_cast<std::size_t>(source_cell_id)
                    ] ||
                    edge_source == plan.source_cell_ids.begin() + edge_end ||
                    *edge_source != source_cell_id
                ) {
                    throw std::runtime_error(
                        "crust-remap coverage membership-area-class membership is invalid"
                    );
                }
                reconstructed_edge_area_km2[static_cast<std::size_t>(
                    std::distance(
                        plan.source_cell_ids.begin() + edge_begin,
                        edge_source
                    )
                )] += area_km2;
                previous_source_cell_id = source_cell_id;
            }

            const int representative_available =
                plan.coverage_membership_area_class_representative_available[
                    class_index
                ];
            const Vec3 representative = {
                plan.coverage_membership_area_class_representative_unit_x[
                    class_index
                ],
                plan.coverage_membership_area_class_representative_unit_y[
                    class_index
                ],
                plan.coverage_membership_area_class_representative_unit_z[
                    class_index
                ],
            };
            const double representative_norm = norm(representative);
            if (
                (representative_available != 0 && representative_available != 1) ||
                (representative_available == 1 &&
                    (!std::isfinite(representative_norm) ||
                     std::abs(representative_norm - 1.0) > 2.0e-12)) ||
                (representative_available == 0 &&
                    (multiplicity != 0 || representative_norm != 0.0))
            ) {
                throw std::runtime_error(
                    "crust-remap coverage membership-area-class representative is invalid"
                );
            }
            destination_class_area_km2 += area_km2;
            observed_maximum_multiplicity = std::max(
                observed_maximum_multiplicity, multiplicity
            );
            destination_maximum_multiplicity = std::max(
                destination_maximum_multiplicity, multiplicity
            );
            if (
                area_by_multiplicity.size() <=
                    static_cast<std::size_t>(multiplicity)
            ) {
                area_by_multiplicity.resize(
                    static_cast<std::size_t>(multiplicity + 1), 0.0
                );
            }
            area_by_multiplicity[static_cast<std::size_t>(multiplicity)] +=
                area_km2;
        }
        const double area_tolerance = std::max(
            1.0e-7, cells[destination_id].area_km2 * 5.0e-10
        );
        if (
            std::abs(
                destination_class_area_km2 - cells[destination_id].area_km2
            ) > area_tolerance ||
            destination_maximum_multiplicity !=
                plan.maximum_coverage_multiplicity_by_cell[destination_id]
        ) {
            throw std::runtime_error(
                "crust-remap coverage membership-area-class destination area did not close"
            );
        }
        for (int edge_id = edge_begin; edge_id < edge_end; ++edge_id) {
            const double recorded_area_km2 = plan.overlap_area_km2[
                static_cast<std::size_t>(edge_id)
            ];
            const double reconstructed_area_km2 = reconstructed_edge_area_km2[
                static_cast<std::size_t>(edge_id - edge_begin)
            ];
            // Both values are independent spherical decompositions of area
            // within this destination control volume. Use the already
            // enforced destination partition forward-error bound rather than
            // an edge-relative bound that becomes artificially strict for a
            // small contributor.
            const double edge_area_tolerance = area_tolerance;
            if (
                !std::isfinite(recorded_area_km2) ||
                recorded_area_km2 <= 0.0 ||
                std::abs(reconstructed_area_km2 - recorded_area_km2) >
                    edge_area_tolerance
            ) {
                throw std::runtime_error(
                    "crust-remap coverage membership-area-class source overlap area did not close: "
                    "destination_cell_id=" + std::to_string(destination_id) +
                    ", source_cell_id=" + std::to_string(
                        plan.source_cell_ids[static_cast<std::size_t>(edge_id)]
                    ) +
                    ", recorded_area_km2=" + num(recorded_area_km2, 17) +
                    ", reconstructed_area_km2=" +
                        num(reconstructed_area_km2, 17) +
                    ", absolute_error_km2=" + num(
                        std::abs(reconstructed_area_km2 - recorded_area_km2), 17
                    ) +
                    ", tolerance_km2=" + num(edge_area_tolerance, 17) +
                    ", destination_class_count=" +
                        std::to_string(class_end - class_begin) +
                    ", destination_raw_arrangement_fragment_count=" +
                        std::to_string(
                            plan.coverage_arrangement_fragment_count_by_cell[
                                destination_id
                            ]
                        )
                );
            }
        }
    }

    const std::size_t histogram_size = std::max(
        area_by_multiplicity.size(),
        plan.global_coverage_area_km2_by_multiplicity.size()
    );
    for (std::size_t multiplicity = 0;
         multiplicity < histogram_size;
         ++multiplicity) {
        const double fragment_area = multiplicity < area_by_multiplicity.size()
            ? area_by_multiplicity[multiplicity]
            : 0.0;
        const double histogram_area =
            multiplicity < plan.global_coverage_area_km2_by_multiplicity.size()
                ? plan.global_coverage_area_km2_by_multiplicity[multiplicity]
                : 0.0;
        const double tolerance = std::max(
            1.0e-6,
            std::max(std::abs(fragment_area), std::abs(histogram_area)) *
                5.0e-10
        );
        if (std::abs(fragment_area - histogram_area) > tolerance) {
            throw std::runtime_error(
                "crust-remap coverage membership-area-class multiplicity area did not close"
            );
        }
    }
    const int recorded_maximum_multiplicity =
        plan.maximum_coverage_multiplicity_by_cell.empty()
            ? 0
            : *std::max_element(
                plan.maximum_coverage_multiplicity_by_cell.begin(),
                plan.maximum_coverage_multiplicity_by_cell.end()
            );
    if (observed_maximum_multiplicity != recorded_maximum_multiplicity) {
        throw std::runtime_error(
            "crust-remap coverage fragment maximum multiplicity is inconsistent"
        );
    }
    if (
        observed_maximum_class_count !=
            plan.maximum_coverage_membership_area_class_count
    ) {
        throw std::runtime_error(
            "crust-remap coverage membership-area-class maximum is inconsistent"
        );
    }
}

}  // namespace

CrustTransportPlan build_identity_crust_transport_plan(
    const std::vector<Cell>& cells
) {
    CrustTransportPlan plan;
    initialize_plan_arrays(plan, cells.size());
    plan.source_cell_ids.reserve(cells.size());
    plan.overlap_area_km2.reserve(cells.size());
    plan.remap_residual_distance_km.reserve(cells.size());
    plan.global_coverage_area_km2_by_multiplicity.assign(2, 0.0);
    plan.maximum_coverage_arrangement_fragment_count = cells.empty() ? 0 : 1;
    std::vector<int> source_plate_ids(cells.size(), 0);
    for (std::size_t index = 0; index < cells.size(); ++index) {
        const Cell& cell = cells[index];
        source_plate_ids[index] = cell.plate_id;
        plan.destination_offsets[index] = static_cast<int>(index);
        plan.source_cell_ids.push_back(static_cast<int>(index));
        plan.overlap_area_km2.push_back(cell.area_km2);
        plan.remap_residual_distance_km.push_back(0.0);
        plan.dominant_source_cell_ids[index] = static_cast<int>(index);
        plan.contributor_count_by_cell[index] = 1;
        plan.dominant_source_volume_fraction_by_cell[index] = 1.0;
        plan.coverage_area_sum_km2_by_cell[index] = cell.area_km2;
        plan.covered_union_area_km2_by_cell[index] = cell.area_km2;
        plan.maximum_coverage_multiplicity_by_cell[index] = 1;
        plan.coverage_arrangement_fragment_count_by_cell[index] = 1;
        plan.global_coverage_area_km2_by_multiplicity[1] += cell.area_km2;
        CoverageDiagnostics identity_coverage;
        identity_coverage.arrangement_fragment_count = 1;
        identity_coverage.membership_area_classes.push_back({
            cell.area_km2,
            1,
            cell.p,
            true,
            {static_cast<int>(index)},
            {cell.plate_id},
        });
        append_coverage_membership_area_classes(
            plan, index, identity_coverage
        );
        plan.remapped_crust_type_by_cell[index] = cell.crust_type;
        plan.remapped_lithology_by_cell[index] = cell.lithology;
        plan.remapped_crust_age_ma_by_cell[index] = cell.crust_age_ma;
        plan.remapped_crust_thickness_km_by_cell[index] = cell.crust_thickness_km;
        plan.remapped_crust_density_by_cell[index] = cell.crust_density;
        const double volume = cell.area_km2 * cell.crust_thickness_km;
        plan.initial_crust_volume_km3 += volume;
        plan.transported_crust_volume_km3 += volume;
        plan.initial_density_weighted_crust_volume += volume * cell.crust_density;
        plan.transported_density_weighted_crust_volume += volume * cell.crust_density;
        plan.initial_crust_age_volume_moment += volume * cell.crust_age_ma;
        plan.transported_crust_age_volume_moment += volume * cell.crust_age_ma;
    }
    plan.destination_offsets[cells.size()] = static_cast<int>(cells.size());
    validate_coverage_membership_area_class_ledger(
        plan, cells, source_plate_ids
    );
    return plan;
}

CrustTransportPlan build_forward_overlap_crust_transport_plan(
    const Params& params,
    const std::vector<Plate>& plates,
    const std::vector<Cell>& cells,
    const std::vector<int>& previous_plate_ids,
    const std::vector<int>& previous_crust_types,
    const std::vector<int>& previous_lithologies,
    const std::vector<double>& previous_crust_age_ma,
    const std::vector<double>& previous_crust_thickness_km,
    const std::vector<double>& previous_crust_density,
    const std::vector<double>& step_rotation_deg
) {
    const std::size_t cell_count = cells.size();
    if (
        previous_plate_ids.size() != cell_count ||
        previous_crust_types.size() != cell_count ||
        previous_lithologies.size() != cell_count ||
        previous_crust_age_ma.size() != cell_count ||
        previous_crust_thickness_km.size() != cell_count ||
        previous_crust_density.size() != cell_count
    ) {
        throw std::runtime_error("crust-remap source state does not match the mesh");
    }
    if (std::all_of(step_rotation_deg.begin(), step_rotation_deg.end(), [](double value) {
        return value == 0.0;
    })) {
        return build_identity_crust_transport_plan(cells);
    }

    CrustTransportPlan plan;
    initialize_plan_arrays(plan, cell_count);
    std::vector<double> cap_radii(cell_count, 0.0);
    double maximum_cap_radius = 0.0;
    for (std::size_t index = 0; index < cell_count; ++index) {
        cap_radii[index] = cell_cap_radius(cells[index]);
        maximum_cap_radius = std::max(maximum_cap_radius, cap_radii[index]);
    }

    const SphericalPointIndex destination_index(cells);
    std::vector<OverlapEdge> edges;
    edges.reserve(cell_count * 2);
    std::vector<double> source_overlap_area_sum(cell_count, 0.0);
    for (std::size_t source_id = 0; source_id < cell_count; ++source_id) {
        const int plate_id = previous_plate_ids[source_id];
        if (plate_id < 0 || plate_id >= static_cast<int>(plates.size())) {
            throw std::runtime_error("crust-remap source plate ID is invalid");
        }
        const double rotation_rad =
            step_rotation_deg[static_cast<std::size_t>(plate_id)] / DEG;
        const Vec3 rotated_center = rotate_about_axis(
            cells[source_id].p,
            plates[static_cast<std::size_t>(plate_id)].axis,
            rotation_rad
        );
        plan.source_kinematic_distance_km[source_id] = angular_distance(
            cells[source_id].p, rotated_center
        ) * params.radius_km;
        std::vector<Vec3> rotated_vertices;
        rotated_vertices.reserve(cells[source_id].control_volume_vertices.size());
        for (Vec3 vertex : cells[source_id].control_volume_vertices) {
            rotated_vertices.push_back(rotate_about_axis(
                vertex,
                plates[static_cast<std::size_t>(plate_id)].axis,
                rotation_rad
            ));
        }
        const std::vector<int> candidates = destination_index.within_angle(
            rotated_center,
            cap_radii[source_id] + maximum_cap_radius + 1.0e-10
        );
        for (int destination_id : candidates) {
            const Cell& destination = cells[static_cast<std::size_t>(destination_id)];
            if (
                angular_distance(rotated_center, destination.p) >
                cap_radii[source_id] +
                    cap_radii[static_cast<std::size_t>(destination_id)] + 1.0e-10
            ) {
                continue;
            }
            const TangentBasis basis = tangent_basis(destination.p);
            std::vector<std::vector<PlanarPoint>> overlap_pieces;
            double area_km2 = 0.0;
            for (std::size_t source_vertex_index = 0;
                 source_vertex_index < rotated_vertices.size();
                 ++source_vertex_index) {
                const std::vector<Vec3> source_triangle = {
                    rotated_center,
                    rotated_vertices[source_vertex_index],
                    rotated_vertices[
                        (source_vertex_index + 1) % rotated_vertices.size()
                    ],
                };
                const std::vector<PlanarPoint> source_polygon = project_polygon(
                    source_triangle, destination.p, basis
                );
                for (std::size_t destination_vertex_index = 0;
                     destination_vertex_index <
                        destination.control_volume_vertices.size();
                     ++destination_vertex_index) {
                    const std::vector<Vec3> destination_triangle = {
                        destination.p,
                        destination.control_volume_vertices[
                            destination_vertex_index
                        ],
                        destination.control_volume_vertices[
                            (destination_vertex_index + 1) %
                                destination.control_volume_vertices.size()
                        ],
                    };
                    const std::vector<PlanarPoint> destination_polygon =
                        project_polygon(
                            destination_triangle, destination.p, basis
                        );
                    std::vector<PlanarPoint> overlap = intersect_convex_polygons(
                        source_polygon, destination_polygon
                    );
                    if (overlap.empty()) {
                        continue;
                    }
                    const double piece_area_km2 = spherical_polygon_area_km2(
                        overlap, destination.p, basis, params.radius_km
                    );
                    if (piece_area_km2 <= 1.0e-12) {
                        continue;
                    }
                    area_km2 += piece_area_km2;
                    overlap_pieces.push_back(std::move(overlap));
                }
            }
            const double minimum_area_km2 = std::max(
                1.0e-10,
                cells[source_id].area_km2 * 1.0e-13
            );
            if (area_km2 <= minimum_area_km2) {
                continue;
            }
            source_overlap_area_sum[source_id] += area_km2;
            edges.push_back({
                static_cast<int>(source_id),
                destination_id,
                area_km2,
                angular_distance(rotated_center, destination.p) * params.radius_km,
                std::move(overlap_pieces),
            });
        }
        const double source_area = cells[source_id].area_km2;
        const double closure_error = std::abs(
            source_overlap_area_sum[source_id] - source_area
        );
        plan.maximum_source_area_closure_error_km2 = std::max(
            plan.maximum_source_area_closure_error_km2, closure_error
        );
        plan.maximum_source_area_relative_closure_error = std::max(
            plan.maximum_source_area_relative_closure_error,
            closure_error / source_area
        );
        if (closure_error > std::max(1.0e-6, source_area * 2.0e-10)) {
            throw std::runtime_error(
                "forward spherical crust-remap source overlaps do not close"
            );
        }
    }

    std::sort(edges.begin(), edges.end(), [](const OverlapEdge& left, const OverlapEdge& right) {
        if (left.destination_cell_id != right.destination_cell_id) {
            return left.destination_cell_id < right.destination_cell_id;
        }
        return left.source_cell_id < right.source_cell_id;
    });
    plan.source_cell_ids.reserve(edges.size());
    plan.overlap_area_km2.reserve(edges.size());
    plan.remap_residual_distance_km.reserve(edges.size());

    std::size_t edge_cursor = 0;
    for (std::size_t destination_id = 0;
         destination_id < cell_count;
         ++destination_id) {
        plan.destination_offsets[destination_id] = static_cast<int>(edge_cursor);
        std::array<std::array<double, 7>, 9> category_pair_volumes{};
        std::vector<std::vector<std::vector<PlanarPoint>>> coverage_by_source;
        std::vector<int> coverage_source_cell_ids;
        std::vector<int> coverage_source_plate_ids;
        double volume = 0.0;
        double density_weighted_volume = 0.0;
        double age_volume_moment = 0.0;
        double dominant_volume = -1.0;
        int dominant_source = -1;
        while (
            edge_cursor < edges.size() &&
            edges[edge_cursor].destination_cell_id ==
                static_cast<int>(destination_id)
        ) {
            const OverlapEdge& edge = edges[edge_cursor];
            const std::size_t source_id = static_cast<std::size_t>(edge.source_cell_id);
            const double edge_volume =
                edge.area_km2 * previous_crust_thickness_km[source_id];
            volume += edge_volume;
            density_weighted_volume +=
                edge_volume * previous_crust_density[source_id];
            age_volume_moment += edge_volume * previous_crust_age_ma[source_id];
            const int crust_type = previous_crust_types[source_id];
            const int lithology = previous_lithologies[source_id];
            if (
                crust_type >= 0 &&
                crust_type < static_cast<int>(category_pair_volumes.size()) &&
                lithology >= 0 &&
                lithology < static_cast<int>(
                    category_pair_volumes[static_cast<std::size_t>(crust_type)].size()
                )
            ) {
                category_pair_volumes[static_cast<std::size_t>(crust_type)][
                    static_cast<std::size_t>(lithology)
                ] += edge_volume;
            }
            if (
                edge_volume > dominant_volume ||
                (edge_volume == dominant_volume && edge.source_cell_id < dominant_source)
            ) {
                dominant_volume = edge_volume;
                dominant_source = edge.source_cell_id;
            }
            plan.coverage_area_sum_km2_by_cell[destination_id] += edge.area_km2;
            coverage_by_source.push_back(edge.destination_chart_polygons);
            coverage_source_cell_ids.push_back(edge.source_cell_id);
            coverage_source_plate_ids.push_back(
                previous_plate_ids[source_id]
            );
            plan.source_cell_ids.push_back(edge.source_cell_id);
            plan.overlap_area_km2.push_back(edge.area_km2);
            plan.remap_residual_distance_km.push_back(
                edge.remap_residual_distance_km
            );
            edge_cursor++;
        }
        plan.contributor_count_by_cell[destination_id] =
            plan.destination_offsets[destination_id] < static_cast<int>(edge_cursor)
                ? static_cast<int>(edge_cursor) -
                    plan.destination_offsets[destination_id]
                : 0;
        plan.dominant_source_cell_ids[destination_id] = dominant_source >= 0
            ? dominant_source
            : static_cast<int>(destination_id);
        plan.dominant_source_volume_fraction_by_cell[destination_id] = volume > 0.0
            ? dominant_volume / volume
            : 0.0;
        const Cell& destination = cells[destination_id];
        if (volume > 0.0) {
            plan.remapped_crust_thickness_km_by_cell[destination_id] =
                volume / destination.area_km2;
            plan.remapped_crust_density_by_cell[destination_id] =
                density_weighted_volume / volume;
            plan.remapped_crust_age_ma_by_cell[destination_id] =
                age_volume_moment / volume;
            double dominant_category_volume = -1.0;
            int dominant_crust_type = 0;
            int dominant_lithology = 0;
            for (int crust_type = 0;
                 crust_type < static_cast<int>(category_pair_volumes.size());
                 ++crust_type) {
                for (int lithology = 0;
                     lithology < static_cast<int>(
                        category_pair_volumes[static_cast<std::size_t>(crust_type)].size()
                     );
                     ++lithology) {
                    const double category_volume =
                        category_pair_volumes[static_cast<std::size_t>(crust_type)][
                            static_cast<std::size_t>(lithology)
                        ];
                    if (category_volume > dominant_category_volume) {
                        dominant_category_volume = category_volume;
                        dominant_crust_type = crust_type;
                        dominant_lithology = lithology;
                    }
                }
            }
            plan.remapped_crust_type_by_cell[destination_id] =
                dominant_crust_type;
            plan.remapped_lithology_by_cell[destination_id] =
                dominant_lithology;
        } else {
            plan.remapped_crust_type_by_cell[destination_id] =
                previous_crust_types[destination_id];
            plan.remapped_lithology_by_cell[destination_id] =
                previous_lithologies[destination_id];
            plan.remapped_crust_age_ma_by_cell[destination_id] = 0.0;
            plan.remapped_crust_density_by_cell[destination_id] =
                previous_crust_density[destination_id];
        }
        const CoverageDiagnostics coverage = coverage_diagnostics(
            destination,
            coverage_by_source,
            coverage_source_cell_ids,
            coverage_source_plate_ids,
            plan.coverage_area_sum_km2_by_cell[destination_id],
            params.radius_km
        );
        append_coverage_membership_area_classes(
            plan, destination_id, coverage
        );
        plan.covered_union_area_km2_by_cell[destination_id] =
            coverage.union_area_km2;
        plan.uncovered_gap_area_km2_by_cell[destination_id] =
            coverage.gap_area_km2;
        plan.overlap_excess_area_km2_by_cell[destination_id] =
            coverage.overlap_excess_area_km2;
        plan.maximum_coverage_multiplicity_by_cell[destination_id] =
            coverage.maximum_multiplicity;
        plan.coverage_arrangement_line_count_by_cell[destination_id] =
            coverage.arrangement_line_count;
        plan.coverage_arrangement_fragment_count_by_cell[destination_id] =
            coverage.arrangement_fragment_count;
        if (plan.global_coverage_area_km2_by_multiplicity.size() <
            coverage.area_km2_by_multiplicity.size()) {
            plan.global_coverage_area_km2_by_multiplicity.resize(
                coverage.area_km2_by_multiplicity.size(), 0.0
            );
        }
        for (std::size_t multiplicity = 0;
             multiplicity < coverage.area_km2_by_multiplicity.size();
             ++multiplicity) {
            plan.global_coverage_area_km2_by_multiplicity[multiplicity] +=
                coverage.area_km2_by_multiplicity[multiplicity];
        }
        plan.maximum_destination_partition_closure_error_km2 = std::max(
            plan.maximum_destination_partition_closure_error_km2,
            coverage.partition_closure_error_km2
        );
        plan.maximum_coverage_arrangement_line_count = std::max(
            plan.maximum_coverage_arrangement_line_count,
            coverage.arrangement_line_count
        );
        plan.maximum_coverage_arrangement_fragment_count = std::max(
            plan.maximum_coverage_arrangement_fragment_count,
            coverage.arrangement_fragment_count
        );
        plan.global_uncovered_gap_area_km2 += coverage.gap_area_km2;
        plan.global_overlap_excess_area_km2 += coverage.overlap_excess_area_km2;
        plan.transported_crust_volume_km3 += volume;
        plan.transported_density_weighted_crust_volume += density_weighted_volume;
        plan.transported_crust_age_volume_moment += age_volume_moment;
    }
    plan.destination_offsets[cell_count] = static_cast<int>(edges.size());
    for (std::size_t source_id = 0; source_id < cell_count; ++source_id) {
        const double volume =
            cells[source_id].area_km2 * previous_crust_thickness_km[source_id];
        plan.initial_crust_volume_km3 += volume;
        plan.initial_density_weighted_crust_volume +=
            volume * previous_crust_density[source_id];
        plan.initial_crust_age_volume_moment +=
            volume * previous_crust_age_ma[source_id];
    }
    const double volume_tolerance = std::max(
        1.0e-7,
        plan.initial_crust_volume_km3 * 5.0e-10
    );
    if (
        std::abs(
            plan.transported_crust_volume_km3 - plan.initial_crust_volume_km3
        ) > volume_tolerance
    ) {
        throw std::runtime_error("forward spherical crust-remap volume did not close");
    }
    const double density_weighted_volume_tolerance = std::max(
        1.0e-7,
        std::abs(plan.initial_density_weighted_crust_volume) * 5.0e-10
    );
    if (
        std::abs(
            plan.transported_density_weighted_crust_volume -
            plan.initial_density_weighted_crust_volume
        ) > density_weighted_volume_tolerance
    ) {
        throw std::runtime_error(
            "forward spherical crust-remap density-weighted volume did not close"
        );
    }
    const double crust_age_volume_moment_tolerance = std::max(
        1.0e-7,
        std::abs(plan.initial_crust_age_volume_moment) * 5.0e-10
    );
    if (
        std::abs(
            plan.transported_crust_age_volume_moment -
            plan.initial_crust_age_volume_moment
        ) > crust_age_volume_moment_tolerance
    ) {
        throw std::runtime_error(
            "forward spherical crust-remap age-volume moment did not close"
        );
    }
    const double coverage_balance_tolerance = std::max(
        1.0e-6,
        4.0 * PI * params.radius_km * params.radius_km * 5.0e-10
    );
    if (
        std::abs(
            plan.global_uncovered_gap_area_km2 -
            plan.global_overlap_excess_area_km2
        ) > coverage_balance_tolerance
    ) {
        throw std::runtime_error(
            "forward spherical crust-remap global gap/overlap areas do not balance"
        );
    }
    const double histogram_area_km2 = std::accumulate(
        plan.global_coverage_area_km2_by_multiplicity.begin(),
        plan.global_coverage_area_km2_by_multiplicity.end(),
        0.0
    );
    const double histogram_gap_km2 =
        plan.global_coverage_area_km2_by_multiplicity.empty()
            ? 0.0
            : plan.global_coverage_area_km2_by_multiplicity.front();
    double histogram_excess_km2 = 0.0;
    for (std::size_t multiplicity = 2;
         multiplicity < plan.global_coverage_area_km2_by_multiplicity.size();
         ++multiplicity) {
        histogram_excess_km2 += static_cast<double>(multiplicity - 1) *
            plan.global_coverage_area_km2_by_multiplicity[multiplicity];
    }
    const double surface_area_km2 = 4.0 * PI * params.radius_km * params.radius_km;
    if (
        std::abs(histogram_area_km2 - surface_area_km2) >
            coverage_balance_tolerance ||
        std::abs(histogram_gap_km2 - plan.global_uncovered_gap_area_km2) >
            coverage_balance_tolerance ||
        std::abs(histogram_excess_km2 - plan.global_overlap_excess_area_km2) >
            coverage_balance_tolerance
    ) {
        throw std::runtime_error(
            "forward spherical crust-remap multiplicity histogram did not close"
        );
    }
    validate_coverage_membership_area_class_ledger(
        plan, cells, previous_plate_ids
    );
    return plan;
}

}  // namespace magic_geo::detail
