#include "engine/climate_transport.hpp"
#include "engine/internal.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <iostream>
#include <limits>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {

using namespace magic_geo::detail;
using Pair = std::pair<int, int>;

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            std::cerr << "check failed at line " << __LINE__ << ": "           \
                      << #condition << '\n';                                    \
            return false;                                                       \
        }                                                                       \
    } while (false)

bool close(long double a, long double b, long double relative = 2.0e-13L) {
    return std::abs(a - b) <= relative * std::max(std::abs(a), std::abs(b));
}

template <typename Callable>
bool rejects(Callable&& callable, const std::string& message_fragment = "") {
    try {
        callable();
    } catch (const std::runtime_error& error) {
        return std::string(error.what()).find(message_fragment) != std::string::npos;
    }
    return false;
}

std::vector<Cell> mesh(int backend, int count) {
    magic_geo::Params params;
    params.mesh_backend = backend;
    params.cell_count = count;
    params.radius_km = 1.0;
    return build_mesh(params);
}

std::map<Pair, double> by_pair(const std::vector<EnergyTransportEdge>& edges) {
    std::map<Pair, double> result;
    for (const auto& edge : edges) result[{edge.first_cell, edge.second_cell}] = edge.conductance_w_k;
    return result;
}

std::vector<long double> heat(const std::vector<EnergyTransportEdge>& edges, const std::vector<double>& temperature) {
    std::vector<long double> result(temperature.size(), 0.0L);
    for (const auto& edge : edges) {
        const long double exchange = static_cast<long double>(edge.conductance_w_k) *
            (temperature[static_cast<std::size_t>(edge.second_cell)] -
             temperature[static_cast<std::size_t>(edge.first_cell)]);
        result[static_cast<std::size_t>(edge.first_cell)] += exchange;
        result[static_cast<std::size_t>(edge.second_cell)] -= exchange;
    }
    return result;
}

std::vector<std::set<int>> adjacency(const std::vector<Cell>& cells) {
    std::vector<std::set<int>> result(cells.size());
    for (std::size_t i = 0; i < cells.size(); ++i) {
        result[i].insert(cells[i].control_volume_edge_neighbor_ids.begin(),
                         cells[i].control_volume_edge_neighbor_ids.end());
    }
    return result;
}

bool harmonic_interfaces_and_contrast() {
    const auto cells = mesh(MESH_BACKEND_FIBONACCI, 128);
    const auto unit = build_climate_heat_transport_edges(MESH_BACKEND_FIBONACCI, cells, 1.0);
    std::vector<double> conductivity(cells.size());
    for (std::size_t i = 0; i < cells.size(); ++i) conductivity[i] = i % 2 == 0 ? 2.0 : 18.0;
    const auto result = build_climate_heat_transport_edges(MESH_BACKEND_FIBONACCI, cells, conductivity);
    CHECK(result.size() == unit.size());
    for (std::size_t k = 0; k < result.size(); ++k) {
        const auto& edge = result[k];
        const long double ki = conductivity[static_cast<std::size_t>(edge.first_cell)];
        const long double kj = conductivity[static_cast<std::size_t>(edge.second_cell)];
        CHECK(edge.first_cell == unit[k].first_cell && edge.second_cell == unit[k].second_cell);
        CHECK(close(edge.conductance_w_k, unit[k].conductance_w_k / (0.5L / ki + 0.5L / kj)));
    }
    conductivity[0] = 0.0;
    const auto insulated = build_climate_heat_transport_edges(MESH_BACKEND_FIBONACCI, cells, conductivity);
    CHECK(insulated.size() == result.size() - adjacency(cells)[0].size());
    for (const auto& edge : insulated) CHECK(edge.first_cell != 0 && edge.second_cell != 0);
    for (std::size_t i = 0; i < cells.size(); ++i) conductivity[i] = i % 2 == 0 ? 1.0e-200 : 1.0e200;
    const auto contrast = build_climate_heat_transport_edges(MESH_BACKEND_FIBONACCI, cells, conductivity);
    CHECK(contrast.size() == unit.size());
    for (std::size_t k = 0; k < contrast.size(); ++k) {
        const auto& edge = contrast[k];
        const long double ki = conductivity[static_cast<std::size_t>(edge.first_cell)];
        const long double kj = conductivity[static_cast<std::size_t>(edge.second_cell)];
        CHECK(close(edge.conductance_w_k, unit[k].conductance_w_k / (0.5L / ki + 0.5L / kj)));
    }
    return true;
}

bool triangle_integrated_coefficient() {
    const auto cells = mesh(MESH_BACKEND_GEODESIC_ICOSAHEDRON, 12);
    const auto adjacent = adjacency(cells);
    std::vector<double> conductivity(cells.size());
    for (std::size_t i = 0; i < cells.size(); ++i) conductivity[i] = static_cast<double>(i + 1);
    const auto edges = build_climate_heat_transport_edges(MESH_BACKEND_GEODESIC_ICOSAHEDRON, cells, conductivity);
    CHECK(edges.size() == 30);
    for (const auto& edge : edges) {
        const auto i = static_cast<std::size_t>(edge.first_cell);
        const auto j = static_cast<std::size_t>(edge.second_cell);
        long double opposite_sum = 0.0L;
        int opposite_count = 0;
        for (int k : adjacent[i]) {
            if (adjacent[j].contains(k)) {
                opposite_sum += conductivity[static_cast<std::size_t>(k)];
                ++opposite_count;
            }
        }
        CHECK(opposite_count == 2);
        // Equilateral primal faces give cot(theta)=1/sqrt(3). Integrating
        // the linear nodal coefficient over each face gives its three-node
        // arithmetic mean, including the node opposite this transport edge.
        const long double expected = (2.0L * conductivity[i] + 2.0L * conductivity[j] + opposite_sum) /
            (6.0L * std::sqrt(3.0L));
        CHECK(close(edge.conductance_w_k, expected));
    }
    // A zero nodal value is not an insulating face in linear FEM: the
    // positive coefficient elsewhere in either adjoining face still conducts.
    conductivity.assign(cells.size(), 1.0);
    conductivity[0] = 0.0;
    CHECK(build_climate_heat_transport_edges(MESH_BACKEND_GEODESIC_ICOSAHEDRON, cells, conductivity).size() == 30);
    return true;
}

bool conservation_dissipation_and_uniform_compatibility() {
    for (int backend : {MESH_BACKEND_FIBONACCI, MESH_BACKEND_GEODESIC_ICOSAHEDRON}) {
        const auto cells = mesh(backend, 128);
        for (double value : {0.0, 3.25}) {
            const auto scalar = build_climate_heat_transport_edges(backend, cells, value);
            const auto uniform = build_climate_heat_transport_edges(backend, cells, std::vector<double>(cells.size(), value));
            CHECK(scalar.size() == uniform.size());
            for (std::size_t k = 0; k < scalar.size(); ++k) {
                CHECK(scalar[k].first_cell == uniform[k].first_cell);
                CHECK(scalar[k].second_cell == uniform[k].second_cell);
                CHECK(scalar[k].conductance_w_k == uniform[k].conductance_w_k);
            }
        }
        std::vector<double> conductivity(cells.size()), temperature(cells.size());
        for (std::size_t i = 0; i < cells.size(); ++i) {
            conductivity[i] = 2.0 + 0.5 * cells[i].p.z;
            temperature[i] = 270.0 + 5.0 * cells[i].p.x + 2.0 * cells[i].p.z;
        }
        const auto edges = build_climate_heat_transport_edges(backend, cells, conductivity);
        CHECK(by_pair(edges).size() == edges.size());
        CHECK(edges.size() == 3 * cells.size() - 6);
        const auto constant = heat(edges, std::vector<double>(cells.size(), 273.15));
        for (long double q : constant) CHECK(q == 0.0L);
        const auto q = heat(edges, temperature);
        long double total = 0.0L, absolute = 0.0L, quadratic_rate = 0.0L, expected_rate = 0.0L;
        for (std::size_t i = 0; i < cells.size(); ++i) {
            total += q[i];
            absolute += std::abs(q[i]);
            quadratic_rate += 2.0L * temperature[i] * q[i];
        }
        for (const auto& edge : edges) {
            CHECK(edge.first_cell < edge.second_cell);
            CHECK(std::isfinite(edge.conductance_w_k) && edge.conductance_w_k > 0.0);
            const long double difference = temperature[static_cast<std::size_t>(edge.second_cell)] -
                temperature[static_cast<std::size_t>(edge.first_cell)];
            expected_rate -= 2.0L * edge.conductance_w_k * difference * difference;
        }
        CHECK(std::abs(total) <= 1.0e-17L * absolute);
        CHECK(quadratic_rate < 0.0L);
        CHECK(close(quadratic_rate, expected_rate, 1.0e-15L));
        // Area is storage geometry, not an extra hidden factor in W/K.
        auto enlarged = cells;
        for (auto& cell : enlarged) cell.area_km2 *= 16.0;
        const auto scaled = build_climate_heat_transport_edges(backend, enlarged, conductivity);
        CHECK(scaled.size() == edges.size());
        for (std::size_t k = 0; k < edges.size(); ++k) CHECK(scaled[k].conductance_w_k == edges[k].conductance_w_k);
    }
    return true;
}

double variable_manufactured_error(int backend, int count) {
    const auto cells = mesh(backend, count);
    std::vector<double> conductivity(cells.size());
    for (std::size_t i = 0; i < cells.size(); ++i) conductivity[i] = 2.0 + 0.5 * cells[i].p.z;
    const auto edges = build_climate_heat_transport_edges(backend, cells, conductivity);
    long double residual_squared = 0.0L, exact_squared = 0.0L;
    for (int axis = 0; axis < 3; ++axis) {
        std::vector<double> field(cells.size());
        for (std::size_t i = 0; i < cells.size(); ++i) {
            const auto p = cells[i].p;
            field[i] = axis == 0 ? p.x : (axis == 1 ? p.y : p.z);
        }
        const auto q = heat(edges, field);
        for (std::size_t i = 0; i < cells.size(); ++i) {
            // On the unit sphere, Laplacian(x_a)=-2*x_a and
            // grad(z).grad(x_a)=delta(a,z)-z*x_a. Thus div(K grad(x_a))
            // for K=2+z/2 is -4*x_a-1.5*z*x_a+0.5*delta(a,z).
            const long double exact = -4.0L * field[i] - 1.5L * cells[i].p.z * field[i] + (axis == 2 ? 0.5L : 0.0L);
            const long double area = cells[i].area_km2;
            const long double residual = q[i] / area - exact;
            residual_squared += area * residual * residual;
            exact_squared += area * exact * exact;
        }
    }
    return static_cast<double>(std::sqrt(residual_squared / exact_squared));
}

bool smooth_variable_coefficient_refines() {
    for (int backend : {MESH_BACKEND_FIBONACCI, MESH_BACKEND_GEODESIC_ICOSAHEDRON}) {
        const double coarse = variable_manufactured_error(backend, 128);
        const double fine = variable_manufactured_error(backend, 2048);
        std::cout << "variable-coefficient relative L2 backend=" << backend << " error=" << coarse << '/' << fine << '\n';
        CHECK(coarse < 0.10);
        CHECK(fine < 0.025);
        CHECK(fine < 0.6 * coarse);
    }
    return true;
}

using Triangle = std::array<int, 3>;

std::vector<Triangle> triangles(const std::vector<Cell>& cells) {
    const auto adjacent = adjacency(cells);
    std::vector<Triangle> result;
    for (std::size_t i = 0; i < cells.size(); ++i) {
        for (int j : adjacent[i]) {
            if (j <= static_cast<int>(i)) continue;
            for (int k : adjacent[i]) {
                if (k > j && adjacent[static_cast<std::size_t>(j)].contains(k)) result.push_back({static_cast<int>(i), j, k});
            }
        }
    }
    return result;
}

void rebuild_barycentric_dual(std::vector<Cell>& cells, const std::vector<Triangle>& faces) {
    struct TaggedPoint { Vec3 point; int neighbor; };
    for (std::size_t i = 0; i < cells.size(); ++i) {
        auto& cell = cells[i];
        std::vector<TaggedPoint> points;
        std::set<int> midpoint_neighbors;
        for (const auto& face : faces) {
            if (std::find(face.begin(), face.end(), static_cast<int>(i)) == face.end()) continue;
            points.push_back({normalize(add(add(cells[static_cast<std::size_t>(face[0])].p,
                                                 cells[static_cast<std::size_t>(face[1])].p),
                                             cells[static_cast<std::size_t>(face[2])].p)), -1});
            for (int j : face) {
                if (j != static_cast<int>(i) && midpoint_neighbors.insert(j).second) {
                    points.push_back({normalize(add(cell.p, cells[static_cast<std::size_t>(j)].p)), j});
                }
            }
        }
        const Vec3 reference = std::abs(cell.p.z) < 0.8 ? Vec3{0.0, 0.0, 1.0} : Vec3{1.0, 0.0, 0.0};
        const Vec3 u = normalize(cross(reference, cell.p));
        const Vec3 v = cross(cell.p, u);
        std::sort(points.begin(), points.end(), [&](const auto& a, const auto& b) {
            return std::atan2(dot(a.point, v), dot(a.point, u)) < std::atan2(dot(b.point, v), dot(b.point, u));
        });
        cell.control_volume_vertices.clear();
        cell.control_volume_edge_neighbor_ids.clear();
        cell.area_km2 = 0.0;
        for (std::size_t k = 0; k < points.size(); ++k) {
            const auto& a = points[k];
            const auto& b = points[(k + 1) % points.size()];
            cell.control_volume_vertices.push_back(a.point);
            cell.control_volume_edge_neighbor_ids.push_back(a.neighbor >= 0 ? a.neighbor : b.neighbor);
            cell.area_km2 += 2.0 * std::atan2(dot(cell.p, cross(a.point, b.point)),
                1.0 + dot(cell.p, a.point) + dot(a.point, b.point) + dot(b.point, cell.p));
        }
    }
}

double cotangent(Vec3 a, Vec3 b, Vec3 opposite) {
    a = add(a, mul(opposite, -1.0));
    b = add(b, mul(opposite, -1.0));
    const auto product = cross(a, b);
    return dot(a, b) / std::sqrt(dot(product, product));
}

bool negative_heterogeneous_stiffness_is_rejected() {
    const auto original = mesh(MESH_BACKEND_GEODESIC_ICOSAHEDRON, 12);
    const auto faces = triangles(original);
    CHECK(faces.size() == 20);
    const auto adjacent = adjacency(original);
    const int destination = *adjacent[0].begin();
    // Rebuild the real dual after moving a primal vertex. Leaving the old
    // control polygons in place would test malformed geometry instead.
    for (double fraction : {0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65}) {
        auto cells = original;
        cells[0].p = normalize(add(mul(original[0].p, 1.0 - fraction),
                                   mul(original[static_cast<std::size_t>(destination)].p, fraction)));
        rebuild_barycentric_dual(cells, faces);
        std::vector<EnergyTransportEdge> unit;
        try {
            unit = build_climate_heat_transport_edges(MESH_BACKEND_GEODESIC_ICOSAHEDRON, cells, 1.0);
        } catch (const std::runtime_error&) {
            continue;
        }
        for (const auto& edge : unit) {
            for (int opposite : adjacent[static_cast<std::size_t>(edge.first_cell)]) {
                if (!adjacent[static_cast<std::size_t>(edge.second_cell)].contains(opposite)) continue;
                if (cotangent(cells[static_cast<std::size_t>(edge.first_cell)].p,
                              cells[static_cast<std::size_t>(edge.second_cell)].p,
                              cells[static_cast<std::size_t>(opposite)].p) >= -0.01) continue;
                std::vector<double> conductivity(cells.size(), 1.0);
                conductivity[static_cast<std::size_t>(opposite)] = 1.0e6;
                CHECK(rejects([&] {
                    build_climate_heat_transport_edges(MESH_BACKEND_GEODESIC_ICOSAHEDRON, cells, conductivity);
                }, "finite nonnegative range"));
                std::cout << "negative weighted FEM fixture distortion=" << fraction << '\n';
                return true;
            }
        }
    }
    CHECK(false);  // The positive homogeneous operator must have an obtuse face.
}

bool invalid_coefficients_and_geometry_are_rejected() {
    for (int backend : {MESH_BACKEND_FIBONACCI, MESH_BACKEND_GEODESIC_ICOSAHEDRON}) {
        const auto cells = mesh(backend, 128);
        CHECK(rejects([&] { build_climate_heat_transport_edges(backend, cells, std::vector<double>(cells.size() - 1, 1.0)); }));
        for (double bad : {-1.0, std::numeric_limits<double>::infinity(), std::numeric_limits<double>::quiet_NaN()}) {
            std::vector<double> conductivity(cells.size(), 1.0);
            conductivity[0] = bad;
            CHECK(rejects([&] { build_climate_heat_transport_edges(backend, cells, conductivity); }));
        }
        auto malformed = cells;
        malformed[0].area_km2 *= 1.01;
        CHECK(rejects([&] { build_climate_heat_transport_edges(backend, malformed, std::vector<double>(cells.size(), 0.0)); }));
        std::vector<double> variable(cells.size(), 1.0);
        variable[0] = 2.0;
        CHECK(rejects([&] { build_climate_heat_transport_edges(backend, malformed, variable); }));
    }
    return true;
}

}  // namespace

int main() {
    if (!harmonic_interfaces_and_contrast() ||
        !triangle_integrated_coefficient() ||
        !conservation_dissipation_and_uniform_compatibility() ||
        !smooth_variable_coefficient_refines() ||
        !negative_heterogeneous_stiffness_is_rejected() ||
        !invalid_coefficients_and_geometry_are_rejected()) {
        return 1;
    }
    return 0;
}
