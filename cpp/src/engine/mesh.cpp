#include "internal.hpp"

namespace magic_geo::detail {

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
#pragma omp parallel for schedule(dynamic)
    for (int i = 0; i < n; ++i) {
        std::vector<std::pair<double, int>> best;
        best.reserve(static_cast<std::size_t>(k));
        for (int j = 0; j < n; ++j) {
            if (i == j) {
                continue;
            }
            const double score = dot(cells[i].p, cells[j].p);
            if (static_cast<int>(best.size()) < k) {
                best.emplace_back(score, j);
                if (static_cast<int>(best.size()) == k) {
                    std::sort(best.begin(), best.end());
                }
            } else if (score > best.front().first) {
                best.front() = {score, j};
                std::sort(best.begin(), best.end());
            }
        }
        for (const auto& item : best) {
            cells[i].neighbors.push_back(item.second);
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
