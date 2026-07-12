#include "internal.hpp"

#include <cstdlib>

namespace magic_geo::detail {
namespace {

struct FibonacciKdNode {
    int cell_id = -1;
    int left = -1;
    int right = -1;
    std::array<double, 3> minimum{};
    std::array<double, 3> maximum{};
};

double coordinate(const Vec3& point, int axis) {
    if (axis == 0) {
        return point.x;
    }
    if (axis == 1) {
        return point.y;
    }
    return point.z;
}

void retain_neighbor_candidate(
    const std::vector<Cell>& cells,
    int query_id,
    int candidate_id,
    int count,
    std::vector<std::pair<double, int>>& best
) {
    if (candidate_id == query_id) {
        return;
    }
    const double score = dot(
        cells[static_cast<std::size_t>(query_id)].p,
        cells[static_cast<std::size_t>(candidate_id)].p
    );
    if (static_cast<int>(best.size()) < count) {
        best.emplace_back(score, candidate_id);
        if (static_cast<int>(best.size()) == count) {
            std::sort(best.begin(), best.end());
        }
    } else if (score > best.front().first) {
        best.front() = {score, candidate_id};
        std::sort(best.begin(), best.end());
    }
}

std::vector<int> select_neighbor_ids(
    const std::vector<Cell>& cells,
    int query_id,
    const std::vector<int>& candidates,
    int count
) {
    std::vector<std::pair<double, int>> best;
    best.reserve(static_cast<std::size_t>(count));
    for (int candidate_id : candidates) {
        retain_neighbor_candidate(cells, query_id, candidate_id, count, best);
    }
    const int expected_count = std::min(
        count, static_cast<int>(cells.size()) - 1
    );
    if (static_cast<int>(best.size()) != expected_count) {
        throw std::runtime_error("Fibonacci nearest-neighbor search returned too few candidates");
    }
    std::vector<int> result;
    result.reserve(best.size());
    for (const auto& item : best) {
        result.push_back(item.second);
    }
    return result;
}

std::vector<int> brute_force_neighbor_ids(
    const std::vector<Cell>& cells,
    int query_id,
    int count
) {
    std::vector<int> candidates(cells.size());
    std::iota(candidates.begin(), candidates.end(), 0);
    return select_neighbor_ids(cells, query_id, candidates, count);
}

class FibonacciKdTree {
public:
    explicit FibonacciKdTree(const std::vector<Cell>& cells) : cells_(cells) {
        order_.resize(cells.size());
        std::iota(order_.begin(), order_.end(), 0);
        nodes_.reserve(cells.size());
        root_ = build(0, static_cast<int>(order_.size()), 0);
    }

    std::vector<int> nearest_neighbor_ids(int query_id, int count) const {
        SearchState state;
        state.count = count;
        state.best.reserve(static_cast<std::size_t>(count));
        state.visited_ids.reserve(static_cast<std::size_t>(count * 4));
        search(root_, query_id, state);

        // Tree traversal is ordered for pruning efficiency, while the legacy
        // all-pairs implementation considered cell IDs in ascending order.
        // Replay the retained superset in that order to preserve its exact
        // boundary-tie behavior and score-ascending neighbor ordering.
        std::sort(state.visited_ids.begin(), state.visited_ids.end());
        return select_neighbor_ids(cells_, query_id, state.visited_ids, count);
    }

    int nearest_cell_id(Vec3 query) const {
        NearestState state;
        search_nearest(root_, normalize(query), state);
        if (state.cell_id < 0) {
            throw std::runtime_error("Fibonacci nearest-site search returned no cell");
        }
        return state.cell_id;
    }

private:
    struct SearchState {
        int count = 0;
        std::vector<std::pair<double, int>> best;
        std::vector<int> visited_ids;
    };

    struct NearestState {
        int cell_id = -1;
        double score = -std::numeric_limits<double>::infinity();
    };

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
            [&](int left_id, int right_id) {
                const double left_value = coordinate(
                    cells_[static_cast<std::size_t>(left_id)].p, axis
                );
                const double right_value = coordinate(
                    cells_[static_cast<std::size_t>(right_id)].p, axis
                );
                if (left_value < right_value) {
                    return true;
                }
                if (right_value < left_value) {
                    return false;
                }
                return left_id < right_id;
            }
        );

        const int node_id = static_cast<int>(nodes_.size());
        nodes_.emplace_back();
        nodes_[static_cast<std::size_t>(node_id)].cell_id =
            order_[static_cast<std::size_t>(middle)];
        const int left = build(begin, middle, depth + 1);
        const int right = build(middle + 1, end, depth + 1);

        FibonacciKdNode& node = nodes_[static_cast<std::size_t>(node_id)];
        node.left = left;
        node.right = right;
        const Vec3 point = cells_[static_cast<std::size_t>(node.cell_id)].p;
        node.minimum = {point.x, point.y, point.z};
        node.maximum = node.minimum;
        include_child_bounds(node, left);
        include_child_bounds(node, right);
        return node_id;
    }

    void include_child_bounds(FibonacciKdNode& node, int child_id) {
        if (child_id < 0) {
            return;
        }
        const FibonacciKdNode& child = nodes_[static_cast<std::size_t>(child_id)];
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

    long double maximum_dot_bound(const FibonacciKdNode& node, const Vec3& query) const {
        const std::array<double, 3> query_coordinates = {query.x, query.y, query.z};
        long double bound = 0.0L;
        long double magnitude = 0.0L;
        for (int axis = 0; axis < 3; ++axis) {
            const double query_coordinate = query_coordinates[static_cast<std::size_t>(axis)];
            const double endpoint = query_coordinate >= 0.0
                ? node.maximum[static_cast<std::size_t>(axis)]
                : node.minimum[static_cast<std::size_t>(axis)];
            const long double term = static_cast<long double>(query_coordinate) *
                static_cast<long double>(endpoint);
            bound += term;
            magnitude += std::abs(term);
        }

        // The AABB expression is a mathematical upper bound for every dot
        // product in the subtree. Inflate it far beyond the worst rounding
        // error of the three double products/additions so pruning remains
        // conservative if an optimized dot() differs by a few ulps.
        const long double rounding_margin =
            128.0L * static_cast<long double>(std::numeric_limits<double>::epsilon()) *
            (1.0L + magnitude);
        return bound + rounding_margin;
    }

    bool can_prune(int node_id, const Vec3& query, const SearchState& state) const {
        if (node_id < 0 || static_cast<int>(state.best.size()) < state.count) {
            return node_id < 0;
        }
        return maximum_dot_bound(nodes_[static_cast<std::size_t>(node_id)], query) <
            static_cast<long double>(state.best.front().first);
    }

    void search(int node_id, int query_id, SearchState& state) const {
        if (node_id < 0) {
            return;
        }
        const Vec3 query = cells_[static_cast<std::size_t>(query_id)].p;
        if (can_prune(node_id, query, state)) {
            return;
        }

        const FibonacciKdNode& node = nodes_[static_cast<std::size_t>(node_id)];
        if (node.cell_id != query_id) {
            state.visited_ids.push_back(node.cell_id);
            retain_neighbor_candidate(
                cells_, query_id, node.cell_id, state.count, state.best
            );
        }

        const long double left_bound = node.left < 0
            ? -std::numeric_limits<long double>::infinity()
            : maximum_dot_bound(nodes_[static_cast<std::size_t>(node.left)], query);
        const long double right_bound = node.right < 0
            ? -std::numeric_limits<long double>::infinity()
            : maximum_dot_bound(nodes_[static_cast<std::size_t>(node.right)], query);
        const int first = left_bound >= right_bound ? node.left : node.right;
        const int second = left_bound >= right_bound ? node.right : node.left;
        search(first, query_id, state);
        search(second, query_id, state);
    }

    void search_nearest(int node_id, const Vec3& query, NearestState& state) const {
        if (node_id < 0) {
            return;
        }
        const FibonacciKdNode& node = nodes_[static_cast<std::size_t>(node_id)];
        if (
            state.cell_id >= 0 &&
            maximum_dot_bound(node, query) < static_cast<long double>(state.score)
        ) {
            return;
        }

        const double score = dot(
            query, cells_[static_cast<std::size_t>(node.cell_id)].p
        );
        if (
            score > state.score ||
            (score == state.score && (state.cell_id < 0 || node.cell_id < state.cell_id))
        ) {
            state.score = score;
            state.cell_id = node.cell_id;
        }

        const long double left_bound = node.left < 0
            ? -std::numeric_limits<long double>::infinity()
            : maximum_dot_bound(nodes_[static_cast<std::size_t>(node.left)], query);
        const long double right_bound = node.right < 0
            ? -std::numeric_limits<long double>::infinity()
            : maximum_dot_bound(nodes_[static_cast<std::size_t>(node.right)], query);
        const int first = left_bound >= right_bound ? node.left : node.right;
        const int second = left_bound >= right_bound ? node.right : node.left;
        search_nearest(first, query, state);
        search_nearest(second, query, state);
    }

    const std::vector<Cell>& cells_;
    std::vector<int> order_;
    std::vector<FibonacciKdNode> nodes_;
    int root_ = -1;
};

bool validate_fibonacci_neighbors_with_brute_force() {
    const char* value = std::getenv("MAGIC_GEO_VALIDATE_FIBONACCI_KNN");
    return value != nullptr && std::string(value) == "1";
}

struct PlanarPoint {
    long double u = 0.0L;
    long double v = 0.0L;
};

struct TangentBasis {
    Vec3 first;
    Vec3 second;
};

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
        cross(reference, center), "control-volume tangent axis"
    );
    return {
        first,
        checked_normalize(cross(center, first), "control-volume tangent axis"),
    };
}

long double half_plane_value(
    const PlanarPoint& point,
    long double a,
    long double b,
    long double c
) {
    return a * point.u + b * point.v - c;
}

bool half_plane_inside(
    const PlanarPoint& point,
    long double a,
    long double b,
    long double c
) {
    const long double value = half_plane_value(point, a, b, c);
    const long double scale = 1.0L + std::abs(c) +
        std::abs(a * point.u) + std::abs(b * point.v);
    // Sites are binary64 inputs. Long-double arithmetic reduces cancellation,
    // but it cannot justify predicates tighter than the input precision.
    return value <= 256.0L *
        static_cast<long double>(std::numeric_limits<double>::epsilon()) * scale;
}

PlanarPoint half_plane_intersection(
    const PlanarPoint& start,
    const PlanarPoint& end,
    long double start_value,
    long double end_value
) {
    const long double denominator = start_value - end_value;
    if (std::abs(denominator) <= std::numeric_limits<long double>::min()) {
        return start;
    }
    const long double fraction = std::clamp(start_value / denominator, 0.0L, 1.0L);
    return {
        start.u + fraction * (end.u - start.u),
        start.v + fraction * (end.v - start.v),
    };
}

void remove_duplicate_planar_vertices(std::vector<PlanarPoint>& polygon) {
    if (polygon.size() < 2) {
        return;
    }
    std::vector<PlanarPoint> deduplicated;
    deduplicated.reserve(polygon.size());
    constexpr long double tolerance_squared = 1.0e-30L;
    for (const PlanarPoint& point : polygon) {
        if (!deduplicated.empty()) {
            const long double du = point.u - deduplicated.back().u;
            const long double dv = point.v - deduplicated.back().v;
            if (du * du + dv * dv <= tolerance_squared) {
                continue;
            }
        }
        deduplicated.push_back(point);
    }
    if (deduplicated.size() > 1) {
        const long double du = deduplicated.front().u - deduplicated.back().u;
        const long double dv = deduplicated.front().v - deduplicated.back().v;
        if (du * du + dv * dv <= tolerance_squared) {
            deduplicated.pop_back();
        }
    }
    polygon = std::move(deduplicated);
}

void clip_planar_polygon(
    std::vector<PlanarPoint>& polygon,
    long double a,
    long double b,
    long double c
) {
    if (polygon.empty()) {
        return;
    }
    std::vector<PlanarPoint> clipped;
    clipped.reserve(polygon.size() + 2);
    for (std::size_t index = 0; index < polygon.size(); ++index) {
        const PlanarPoint& start = polygon[index];
        const PlanarPoint& end = polygon[(index + 1) % polygon.size()];
        const long double start_value = half_plane_value(start, a, b, c);
        const long double end_value = half_plane_value(end, a, b, c);
        const bool start_inside = half_plane_inside(start, a, b, c);
        const bool end_inside = half_plane_inside(end, a, b, c);
        if (start_inside && end_inside) {
            clipped.push_back(end);
        } else if (start_inside && !end_inside) {
            clipped.push_back(half_plane_intersection(
                start, end, start_value, end_value
            ));
        } else if (!start_inside && end_inside) {
            clipped.push_back(half_plane_intersection(
                start, end, start_value, end_value
            ));
            clipped.push_back(end);
        }
    }
    remove_duplicate_planar_vertices(clipped);
    polygon = std::move(clipped);
}

Vec3 gnomonic_to_sphere(
    Vec3 center,
    const TangentBasis& basis,
    const PlanarPoint& point
) {
    return checked_normalize(add(
        center,
        add(
            mul(basis.first, static_cast<double>(point.u)),
            mul(basis.second, static_cast<double>(point.v))
        )
    ), "gnomonic control-volume vertex");
}

double control_volume_area_steradians(const Cell& cell) {
    long double area = 0.0L;
    long double compensation = 0.0L;
    for (std::size_t index = 0; index < cell.control_volume_vertices.size(); ++index) {
        const Vec3 first = cell.control_volume_vertices[index];
        const Vec3 second = cell.control_volume_vertices[
            (index + 1) % cell.control_volume_vertices.size()
        ];
        const long double determinant =
            static_cast<long double>(cell.p.x) *
                (static_cast<long double>(first.y) * second.z -
                 static_cast<long double>(first.z) * second.y) +
            static_cast<long double>(cell.p.y) *
                (static_cast<long double>(first.z) * second.x -
                 static_cast<long double>(first.x) * second.z) +
            static_cast<long double>(cell.p.z) *
                (static_cast<long double>(first.x) * second.y -
                 static_cast<long double>(first.y) * second.x);
        const long double denominator = 1.0L +
            precise_dot(cell.p, first) +
            precise_dot(first, second) +
            precise_dot(second, cell.p);
        const long double triangle_area = 2.0L * std::atan2(
            determinant, denominator
        );
        const long double adjusted = triangle_area - compensation;
        const long double updated = area + adjusted;
        compensation = (updated - area) - adjusted;
        area = updated;
    }
    if (!std::isfinite(area) || area <= 0.0L) {
        throw std::runtime_error(
            "control-volume polygon is not finite and counter-clockwise"
        );
    }
    return static_cast<double>(area);
}

Vec3 canonical_voronoi_vertex(
    const std::vector<Cell>& cells,
    int first_id,
    int second_id,
    int third_id,
    Vec3 approximate
) {
    std::array<int, 3> ids = {first_id, second_id, third_id};
    std::sort(ids.begin(), ids.end());
    if (ids[0] == ids[1] || ids[1] == ids[2]) {
        throw std::runtime_error("spherical Voronoi vertex has duplicate generating sites");
    }
    const Vec3 first = cells[static_cast<std::size_t>(ids[0])].p;
    const Vec3 second = cells[static_cast<std::size_t>(ids[1])].p;
    const Vec3 third = cells[static_cast<std::size_t>(ids[2])].p;
    Vec3 result = checked_normalize(
        cross(sub(first, second), sub(first, third)),
        "spherical Voronoi generating-site intersection"
    );
    const Vec3 site_sum = add(add(first, second), third);
    const double orientation = dot(result, site_sum);
    if (orientation < 0.0 || (orientation == 0.0 && dot(result, approximate) < 0.0)) {
        result = mul(result, -1.0);
    }
    return result;
}

void build_fibonacci_control_volume(
    const FibonacciKdTree& index,
    std::vector<Cell>& cells,
    int cell_id
) {
    Cell& cell = cells[static_cast<std::size_t>(cell_id)];
    const TangentBasis basis = tangent_basis(cell.p);
    const int seed_count = std::min(24, static_cast<int>(cells.size()) - 1);
    std::set<int> constraint_ids;
    for (int neighbor_id : index.nearest_neighbor_ids(cell_id, seed_count)) {
        constraint_ids.insert(neighbor_id);
    }

    std::vector<PlanarPoint> polygon;
    constexpr long double initial_bound = 16.0L;
    bool verified = false;
    for (int iteration = 0; iteration < 64; ++iteration) {
        polygon = {
            {-initial_bound, -initial_bound},
            {initial_bound, -initial_bound},
            {initial_bound, initial_bound},
            {-initial_bound, initial_bound},
        };
        for (int constraint_id : constraint_ids) {
            const Vec3 other = cells[static_cast<std::size_t>(constraint_id)].p;
            const long double a = precise_dot(basis.first, other);
            const long double b = precise_dot(basis.second, other);
            const long double c = 1.0L - precise_dot(cell.p, other);
            clip_planar_polygon(polygon, a, b, c);
            if (polygon.size() < 3) {
                throw std::runtime_error("spherical Voronoi clipping produced an empty cell");
            }
        }
        if (std::any_of(polygon.begin(), polygon.end(), [](const PlanarPoint& point) {
            return std::abs(point.u) >= initial_bound * 0.99L ||
                std::abs(point.v) >= initial_bound * 0.99L;
        })) {
            throw std::runtime_error("spherical Voronoi cell remained unbounded in tangent projection");
        }

        std::set<int> violating_ids;
        for (const PlanarPoint& point : polygon) {
            const Vec3 vertex = gnomonic_to_sphere(cell.p, basis, point);
            const int nearest_id = index.nearest_cell_id(vertex);
            if (
                nearest_id != cell_id &&
                dot(vertex, cells[static_cast<std::size_t>(nearest_id)].p) >
                    dot(vertex, cell.p) + 2.0e-13
            ) {
                violating_ids.insert(nearest_id);
            }
        }
        const std::size_t old_size = constraint_ids.size();
        constraint_ids.insert(violating_ids.begin(), violating_ids.end());
        if (violating_ids.empty()) {
            verified = true;
            break;
        }
        if (constraint_ids.size() == old_size) {
            break;
        }
    }
    if (!verified) {
        throw std::runtime_error("spherical Voronoi cell did not pass nearest-site verification");
    }

    cell.control_volume_vertices.clear();
    cell.control_volume_edge_neighbor_ids.clear();
    cell.control_volume_vertices.reserve(polygon.size());
    cell.control_volume_edge_neighbor_ids.reserve(polygon.size());
    for (const PlanarPoint& point : polygon) {
        cell.control_volume_vertices.push_back(
            gnomonic_to_sphere(cell.p, basis, point)
        );
    }

    for (std::size_t edge_index = 0; edge_index < polygon.size(); ++edge_index) {
        const PlanarPoint& start = polygon[edge_index];
        const PlanarPoint& end = polygon[(edge_index + 1) % polygon.size()];
        int best_id = -1;
        long double best_residual = std::numeric_limits<long double>::infinity();
        for (int constraint_id : constraint_ids) {
            const Vec3 other = cells[static_cast<std::size_t>(constraint_id)].p;
            const long double a = precise_dot(basis.first, other);
            const long double b = precise_dot(basis.second, other);
            const long double c = 1.0L - precise_dot(cell.p, other);
            const long double scale = 1.0L + std::abs(a) + std::abs(b) + std::abs(c);
            const long double residual = std::max(
                std::abs(half_plane_value(start, a, b, c)),
                std::abs(half_plane_value(end, a, b, c))
            ) / scale;
            if (residual < best_residual ||
                (residual == best_residual && constraint_id < best_id)) {
                best_residual = residual;
                best_id = constraint_id;
            }
        }
        if (best_id < 0 || best_residual > 1.0e-10L) {
            throw std::runtime_error("spherical Voronoi edge has no generating neighbor");
        }
        cell.control_volume_edge_neighbor_ids.push_back(best_id);
    }

    for (std::size_t vertex_index = 0;
         vertex_index < cell.control_volume_vertices.size();
         ++vertex_index) {
        const int previous_neighbor = cell.control_volume_edge_neighbor_ids[
            (vertex_index + cell.control_volume_edge_neighbor_ids.size() - 1) %
                cell.control_volume_edge_neighbor_ids.size()
        ];
        const int next_neighbor = cell.control_volume_edge_neighbor_ids[vertex_index];
        cell.control_volume_vertices[vertex_index] = canonical_voronoi_vertex(
            cells,
            cell_id,
            previous_neighbor,
            next_neighbor,
            cell.control_volume_vertices[vertex_index]
        );
    }

    // The nearest-site query at every planar polygon vertex is an exact
    // certificate for all omitted sites: each spherical Voronoi inequality
    // becomes a linear half-plane in this gnomonic chart, so if every vertex
    // satisfies every site constraint, the whole convex polygon does too.
    for (std::size_t edge_index = 0;
         edge_index < cell.control_volume_vertices.size();
         ++edge_index) {
        const Vec3 start = cell.control_volume_vertices[edge_index];
        const Vec3 end = cell.control_volume_vertices[
            (edge_index + 1) % cell.control_volume_vertices.size()
        ];
        if (norm(sub(start, end)) <= 1.0e-12) {
            throw std::runtime_error("spherical Voronoi polygon has a duplicate vertex");
        }
        if (precise_dot(cell.p, cross(start, end)) <= 0.0L) {
            throw std::runtime_error("spherical Voronoi polygon is not counter-clockwise");
        }
        for (Vec3 vertex : {start, end}) {
            const int nearest_id = index.nearest_cell_id(vertex);
            if (
                precise_dot(vertex, cells[static_cast<std::size_t>(nearest_id)].p) >
                    precise_dot(vertex, cell.p) + 2.0e-11L
            ) {
                throw std::runtime_error(
                    "canonical spherical Voronoi vertex failed nearest-site verification"
                );
            }
        }
        const Vec3 edge_neighbor = cells[static_cast<std::size_t>(
            cell.control_volume_edge_neighbor_ids[edge_index]
        )].p;
        const Vec3 bisector_normal = sub(cell.p, edge_neighbor);
        if (
            std::abs(precise_dot(start, bisector_normal)) > 2.0e-11L ||
            std::abs(precise_dot(end, bisector_normal)) > 2.0e-11L
        ) {
            throw std::runtime_error("canonical spherical Voronoi edge left its bisector");
        }
    }
}

void validate_control_volume_partition(
    const Params& params,
    const std::vector<Cell>& cells,
    const char* backend_name
) {
    const double expected_area = 4.0 * PI * params.radius_km * params.radius_km;
    double total_area = 0.0;
    for (const Cell& cell : cells) {
        if (
            cell.control_volume_vertices.size() < 3 ||
            cell.control_volume_vertices.size() !=
                cell.control_volume_edge_neighbor_ids.size() ||
            !std::isfinite(cell.area_km2) ||
            cell.area_km2 <= 0.0
        ) {
            throw std::runtime_error(
                std::string(backend_name) + " control-volume geometry is incomplete"
            );
        }
        for (int neighbor_id : cell.control_volume_edge_neighbor_ids) {
            if (
                neighbor_id < 0 ||
                neighbor_id >= static_cast<int>(cells.size()) ||
                neighbor_id == cell.id
            ) {
                throw std::runtime_error(
                    std::string(backend_name) + " control-volume edge neighbor is invalid"
                );
            }
        }
        for (std::size_t edge_index = 0;
             edge_index < cell.control_volume_edge_neighbor_ids.size();
             ++edge_index) {
            const int neighbor_id = cell.control_volume_edge_neighbor_ids[edge_index];
            const Cell& neighbor = cells[static_cast<std::size_t>(neighbor_id)];
            const int forward_segment_count = static_cast<int>(std::count(
                cell.control_volume_edge_neighbor_ids.begin(),
                cell.control_volume_edge_neighbor_ids.end(),
                neighbor_id
            ));
            const int reverse_segment_count = static_cast<int>(std::count(
                neighbor.control_volume_edge_neighbor_ids.begin(),
                neighbor.control_volume_edge_neighbor_ids.end(),
                cell.id
            ));
            if (forward_segment_count != reverse_segment_count) {
                throw std::runtime_error(
                    std::string(backend_name) +
                    " control-volume shared-edge multiplicity is not reciprocal"
                );
            }
            const Vec3 start = cell.control_volume_vertices[edge_index];
            const Vec3 end = cell.control_volume_vertices[
                (edge_index + 1) % cell.control_volume_vertices.size()
            ];
            bool reverse_match = false;
            for (std::size_t reverse_index = 0;
                 reverse_index < neighbor.control_volume_edge_neighbor_ids.size();
                 ++reverse_index) {
                if (neighbor.control_volume_edge_neighbor_ids[reverse_index] != cell.id) {
                    continue;
                }
                const Vec3 reverse_start = neighbor.control_volume_vertices[reverse_index];
                const Vec3 reverse_end = neighbor.control_volume_vertices[
                    (reverse_index + 1) % neighbor.control_volume_vertices.size()
                ];
                if (
                    norm(sub(start, reverse_end)) <= 1.0e-10 &&
                    norm(sub(end, reverse_start)) <= 1.0e-10
                ) {
                    reverse_match = true;
                    break;
                }
            }
            if (!reverse_match) {
                throw std::runtime_error(
                    std::string(backend_name) +
                    " control-volume shared-edge endpoints are not reciprocal"
                );
            }
        }
        total_area += cell.area_km2;
    }
    if (
        !std::isfinite(total_area) ||
        std::abs(total_area - expected_area) > expected_area * 2.0e-10
    ) {
        throw std::runtime_error(
            std::string(backend_name) + " control-volume areas do not close to the sphere"
        );
    }
}

}  // namespace

std::vector<Cell> build_fibonacci_mesh(const Params& params) {
    const int n = params.cell_count;
    std::vector<Cell> cells(n);
    const double golden_angle = PI * (3.0 - std::sqrt(5.0));
    for (int i = 0; i < n; ++i) {
        const double z = 1.0 - 2.0 * (static_cast<double>(i) + 0.5) / static_cast<double>(n);
        const double r = std::sqrt(std::max(0.0, 1.0 - z * z));
        const double theta = golden_angle * static_cast<double>(i);
        cells[i].id = i;
        cells[i].p = {std::cos(theta) * r, std::sin(theta) * r, z};
        cells[i].lat = std::asin(z);
        cells[i].lon = std::atan2(cells[i].p.y, cells[i].p.x);
    }

    const int k = params.neighbor_count;
    const FibonacciKdTree index(cells);
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        cells[static_cast<std::size_t>(i)].neighbors = index.nearest_neighbor_ids(i, k);
    }

    if (validate_fibonacci_neighbors_with_brute_force()) {
        for (int i = 0; i < n; ++i) {
            const std::vector<int> reference = brute_force_neighbor_ids(cells, i, k);
            if (cells[static_cast<std::size_t>(i)].neighbors != reference) {
                throw std::runtime_error(
                    "optimized Fibonacci nearest-neighbor search diverged from brute-force reference"
                );
            }
        }
    }
    for (int i = 0; i < n; ++i) {
        for (int j : cells[i].neighbors) {
            auto& back = cells[j].neighbors;
            if (std::find(back.begin(), back.end(), i) == back.end()) {
                back.push_back(i);
            }
        }
    }

    std::vector<std::string> control_volume_errors(static_cast<std::size_t>(n));
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        try {
            build_fibonacci_control_volume(index, cells, i);
            cells[static_cast<std::size_t>(i)].area_km2 =
                control_volume_area_steradians(cells[static_cast<std::size_t>(i)]) *
                params.radius_km * params.radius_km;
        } catch (const std::exception& error) {
            control_volume_errors[static_cast<std::size_t>(i)] = error.what();
        }
    }
    for (int i = 0; i < n; ++i) {
        if (!control_volume_errors[static_cast<std::size_t>(i)].empty()) {
            throw std::runtime_error(
                "Fibonacci control-volume cell " + std::to_string(i) + ": " +
                control_volume_errors[static_cast<std::size_t>(i)]
            );
        }
    }
    validate_control_volume_partition(params, cells, "Fibonacci Voronoi");
    return cells;
}

int geodesic_frequency_for_target(int cell_count) {
    const double target = static_cast<double>(std::max(12, cell_count));
    const double raw = std::sqrt(std::max(0.0, (target - 2.0) / 10.0));
    return std::max(1, static_cast<int>(std::ceil(raw - 1.0e-9)));
}

int add_geodesic_vertex(
    std::vector<Vec3>& points,
    std::vector<std::set<int>>& neighbor_sets,
    std::map<std::array<long long, 3>, int>& point_index,
    Vec3 point
) {
    point = normalize(point);
    const std::array<long long, 3> key = {
        static_cast<long long>(std::llround(point.x * 1000000000.0)),
        static_cast<long long>(std::llround(point.y * 1000000000.0)),
        static_cast<long long>(std::llround(point.z * 1000000000.0)),
    };
    const auto found = point_index.find(key);
    if (found != point_index.end()) {
        return found->second;
    }
    const int id = static_cast<int>(points.size());
    points.push_back(point);
    neighbor_sets.emplace_back();
    point_index[key] = id;
    return id;
}

void add_geodesic_edge(std::vector<std::set<int>>& neighbor_sets, int a, int b) {
    if (a == b || a < 0 || b < 0) {
        return;
    }
    neighbor_sets[static_cast<std::size_t>(a)].insert(b);
    neighbor_sets[static_cast<std::size_t>(b)].insert(a);
}

void add_geodesic_triangle(
    std::vector<std::set<int>>& neighbor_sets,
    std::vector<std::array<int, 3>>& triangles,
    int a,
    int b,
    int c
) {
    add_geodesic_edge(neighbor_sets, a, b);
    add_geodesic_edge(neighbor_sets, b, c);
    add_geodesic_edge(neighbor_sets, c, a);
    triangles.push_back({a, b, c});
}

std::vector<Cell> build_geodesic_icosahedron_mesh(const Params& params) {
    const double t = (1.0 + std::sqrt(5.0)) / 2.0;
    const std::array<Vec3, 12> base_vertices = {
        normalize({-1.0, t, 0.0}), normalize({1.0, t, 0.0}),
        normalize({-1.0, -t, 0.0}), normalize({1.0, -t, 0.0}),
        normalize({0.0, -1.0, t}), normalize({0.0, 1.0, t}),
        normalize({0.0, -1.0, -t}), normalize({0.0, 1.0, -t}),
        normalize({t, 0.0, -1.0}), normalize({t, 0.0, 1.0}),
        normalize({-t, 0.0, -1.0}), normalize({-t, 0.0, 1.0}),
    };
    const std::array<std::array<int, 3>, 20> faces = {{
        {{0, 11, 5}}, {{0, 5, 1}}, {{0, 1, 7}}, {{0, 7, 10}}, {{0, 10, 11}},
        {{1, 5, 9}}, {{5, 11, 4}}, {{11, 10, 2}}, {{10, 7, 6}}, {{7, 1, 8}},
        {{3, 9, 4}}, {{3, 4, 2}}, {{3, 2, 6}}, {{3, 6, 8}}, {{3, 8, 9}},
        {{4, 9, 5}}, {{2, 4, 11}}, {{6, 2, 10}}, {{8, 6, 7}}, {{9, 8, 1}},
    }};

    const int frequency = geodesic_frequency_for_target(params.cell_count);
    std::vector<Vec3> points;
    points.reserve(static_cast<std::size_t>(10 * frequency * frequency + 2));
    std::vector<std::set<int>> neighbor_sets;
    neighbor_sets.reserve(points.capacity());
    std::map<std::array<long long, 3>, int> point_index;
    std::vector<std::array<int, 3>> triangles;
    triangles.reserve(static_cast<std::size_t>(20 * frequency * frequency));

    for (const auto& face : faces) {
        const Vec3 a = base_vertices[static_cast<std::size_t>(face[0])];
        const Vec3 b = base_vertices[static_cast<std::size_t>(face[1])];
        const Vec3 c = base_vertices[static_cast<std::size_t>(face[2])];
        std::vector<std::vector<int>> grid(
            static_cast<std::size_t>(frequency + 1),
            std::vector<int>(static_cast<std::size_t>(frequency + 1), -1)
        );
        for (int i = 0; i <= frequency; ++i) {
            for (int j = 0; j <= frequency - i; ++j) {
                const int k = frequency - i - j;
                const Vec3 point = add(add(mul(a, static_cast<double>(k)), mul(b, static_cast<double>(i))),
                    mul(c, static_cast<double>(j)));
                grid[static_cast<std::size_t>(i)][static_cast<std::size_t>(j)] = add_geodesic_vertex(
                    points, neighbor_sets, point_index, point
                );
            }
        }
        for (int i = 0; i < frequency; ++i) {
            for (int j = 0; j < frequency - i; ++j) {
                const int v0 = grid[static_cast<std::size_t>(i)][static_cast<std::size_t>(j)];
                const int v1 = grid[static_cast<std::size_t>(i + 1)][static_cast<std::size_t>(j)];
                const int v2 = grid[static_cast<std::size_t>(i)][static_cast<std::size_t>(j + 1)];
                add_geodesic_triangle(neighbor_sets, triangles, v0, v1, v2);
                if (j < frequency - i - 1) {
                    const int v3 = grid[static_cast<std::size_t>(i + 1)][static_cast<std::size_t>(j + 1)];
                    add_geodesic_triangle(neighbor_sets, triangles, v1, v3, v2);
                }
            }
        }
    }

    std::vector<Cell> cells(points.size());
    for (int i = 0; i < static_cast<int>(points.size()); ++i) {
        const Vec3 point = points[static_cast<std::size_t>(i)];
        cells[static_cast<std::size_t>(i)].id = i;
        cells[static_cast<std::size_t>(i)].p = point;
        cells[static_cast<std::size_t>(i)].lat = std::asin(clamp(point.z, -1.0, 1.0));
        cells[static_cast<std::size_t>(i)].lon = std::atan2(point.y, point.x);
        cells[static_cast<std::size_t>(i)].neighbors.assign(
            neighbor_sets[static_cast<std::size_t>(i)].begin(),
            neighbor_sets[static_cast<std::size_t>(i)].end()
        );
    }

    struct TaggedControlPoint {
        Vec3 point;
        int midpoint_neighbor_id = -1;
        int face_id = -1;
    };
    std::vector<std::vector<TaggedControlPoint>> control_points(points.size());
    for (int cell_id = 0; cell_id < static_cast<int>(points.size()); ++cell_id) {
        for (int neighbor_id : neighbor_sets[static_cast<std::size_t>(cell_id)]) {
            control_points[static_cast<std::size_t>(cell_id)].push_back({
                checked_normalize(add(
                    points[static_cast<std::size_t>(cell_id)],
                    points[static_cast<std::size_t>(neighbor_id)]
                ), "geodesic primal-edge midpoint"),
                neighbor_id,
                -1,
            });
        }
    }
    for (int face_id = 0; face_id < static_cast<int>(triangles.size()); ++face_id) {
        const auto& triangle = triangles[static_cast<std::size_t>(face_id)];
        const Vec3 face_center = checked_normalize(add(
            add(
                points[static_cast<std::size_t>(triangle[0])],
                points[static_cast<std::size_t>(triangle[1])]
            ),
            points[static_cast<std::size_t>(triangle[2])]
        ), "geodesic primal-face center");
        for (int cell_id : triangle) {
            control_points[static_cast<std::size_t>(cell_id)].push_back({
                face_center,
                -1,
                face_id,
            });
        }
    }

    const double radius_squared_km2 = params.radius_km * params.radius_km;
    for (int cell_id = 0; cell_id < static_cast<int>(cells.size()); ++cell_id) {
        Cell& cell = cells[static_cast<std::size_t>(cell_id)];
        const TangentBasis basis = tangent_basis(cell.p);
        auto& tagged = control_points[static_cast<std::size_t>(cell_id)];
        std::sort(tagged.begin(), tagged.end(), [&](
            const TaggedControlPoint& left,
            const TaggedControlPoint& right
        ) {
            const double left_angle = std::atan2(
                dot(left.point, basis.second), dot(left.point, basis.first)
            );
            const double right_angle = std::atan2(
                dot(right.point, basis.second), dot(right.point, basis.first)
            );
            if (left_angle != right_angle) {
                return left_angle < right_angle;
            }
            if (left.midpoint_neighbor_id != right.midpoint_neighbor_id) {
                return left.midpoint_neighbor_id < right.midpoint_neighbor_id;
            }
            return left.face_id < right.face_id;
        });
        cell.control_volume_vertices.reserve(tagged.size());
        cell.control_volume_edge_neighbor_ids.reserve(tagged.size());
        for (const TaggedControlPoint& point : tagged) {
            cell.control_volume_vertices.push_back(point.point);
        }
        for (std::size_t edge_index = 0; edge_index < tagged.size(); ++edge_index) {
            const TaggedControlPoint& start = tagged[edge_index];
            const TaggedControlPoint& end = tagged[(edge_index + 1) % tagged.size()];
            const bool start_is_midpoint = start.midpoint_neighbor_id >= 0;
            const bool end_is_midpoint = end.midpoint_neighbor_id >= 0;
            if (start_is_midpoint == end_is_midpoint) {
                throw std::runtime_error(
                    "geodesic barycentric control-volume vertices do not alternate"
                );
            }
            cell.control_volume_edge_neighbor_ids.push_back(
                start_is_midpoint
                    ? start.midpoint_neighbor_id
                    : end.midpoint_neighbor_id
            );
        }
        cell.area_km2 = control_volume_area_steradians(cell) * radius_squared_km2;
    }
    validate_control_volume_partition(params, cells, "geodesic barycentric");
    return cells;
}

std::vector<Cell> build_mesh(const Params& params) {
    if (params.mesh_backend == MESH_BACKEND_GEODESIC_ICOSAHEDRON) {
        return build_geodesic_icosahedron_mesh(params);
    }
    return build_fibonacci_mesh(params);
}

}  // namespace magic_geo::detail
