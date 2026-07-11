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

private:
    struct SearchState {
        int count = 0;
        std::vector<std::pair<double, int>> best;
        std::vector<int> visited_ids;
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

    const std::vector<Cell>& cells_;
    std::vector<int> order_;
    std::vector<FibonacciKdNode> nodes_;
    int root_ = -1;
};

bool validate_fibonacci_neighbors_with_brute_force() {
    const char* value = std::getenv("MAGIC_GEO_VALIDATE_FIBONACCI_KNN");
    return value != nullptr && std::string(value) == "1";
}

}  // namespace

std::vector<Cell> build_fibonacci_mesh(const Params& params) {
    const int n = params.cell_count;
    std::vector<Cell> cells(n);
    const double golden_angle = PI * (3.0 - std::sqrt(5.0));
    const double area = 4.0 * PI * params.radius_km * params.radius_km / static_cast<double>(n);
    for (int i = 0; i < n; ++i) {
        const double z = 1.0 - 2.0 * (static_cast<double>(i) + 0.5) / static_cast<double>(n);
        const double r = std::sqrt(std::max(0.0, 1.0 - z * z));
        const double theta = golden_angle * static_cast<double>(i);
        cells[i].id = i;
        cells[i].p = {std::cos(theta) * r, std::sin(theta) * r, z};
        cells[i].lat = std::asin(z);
        cells[i].lon = std::atan2(cells[i].p.y, cells[i].p.x);
        cells[i].area_km2 = area;
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

    std::vector<double> cell_areas(points.size(), 0.0);
    const double radius_squared_km2 = params.radius_km * params.radius_km;
    for (const auto& triangle : triangles) {
        const double share_km2 = spherical_triangle_area_steradians(
            points[static_cast<std::size_t>(triangle[0])],
            points[static_cast<std::size_t>(triangle[1])],
            points[static_cast<std::size_t>(triangle[2])]
        ) * radius_squared_km2 / 3.0;
        for (int cell_id : triangle) {
            cell_areas[static_cast<std::size_t>(cell_id)] += share_km2;
        }
    }
    const double expected_area_km2 = 4.0 * PI * radius_squared_km2;
    const double computed_area_km2 = std::accumulate(cell_areas.begin(), cell_areas.end(), 0.0);
    if (
        computed_area_km2 <= 0.0 ||
        std::abs(computed_area_km2 - expected_area_km2) > expected_area_km2 * 1.0e-10
    ) {
        throw std::runtime_error("geodesic spherical cell areas do not close to planet surface area");
    }
    std::vector<Cell> cells(points.size());
    for (int i = 0; i < static_cast<int>(points.size()); ++i) {
        const Vec3 point = points[static_cast<std::size_t>(i)];
        cells[static_cast<std::size_t>(i)].id = i;
        cells[static_cast<std::size_t>(i)].p = point;
        cells[static_cast<std::size_t>(i)].lat = std::asin(clamp(point.z, -1.0, 1.0));
        cells[static_cast<std::size_t>(i)].lon = std::atan2(point.y, point.x);
        cells[static_cast<std::size_t>(i)].area_km2 = cell_areas[static_cast<std::size_t>(i)];
        cells[static_cast<std::size_t>(i)].neighbors.assign(
            neighbor_sets[static_cast<std::size_t>(i)].begin(),
            neighbor_sets[static_cast<std::size_t>(i)].end()
        );
    }
    return cells;
}

std::vector<Cell> build_mesh(const Params& params) {
    if (params.mesh_backend == MESH_BACKEND_GEODESIC_ICOSAHEDRON) {
        return build_geodesic_icosahedron_mesh(params);
    }
    return build_fibonacci_mesh(params);
}

}  // namespace magic_geo::detail
