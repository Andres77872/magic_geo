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
#include <utility>
#include <vector>

namespace {

using namespace magic_geo::detail;

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            std::cerr << "check failed at line " << __LINE__ << ": "           \
                      << #condition << '\n';                                    \
            return false;                                                       \
        }                                                                       \
    } while (false)

bool close(double a, double b, double tolerance = 1.0e-12) {
    return std::abs(a - b) <= tolerance * std::max({1.0, std::abs(a), std::abs(b)});
}

template <typename Callable>
bool rejects(Callable&& callable) {
    try {
        callable();
    } catch (const std::runtime_error&) {
        return true;
    }
    return false;
}

std::vector<Cell> generated_mesh(int backend, int count, double radius_km = 1.0) {
    magic_geo::Params params;
    params.mesh_backend = backend;
    params.cell_count = count;
    params.radius_km = radius_km;
    return build_mesh(params);
}

std::map<std::pair<int, int>, double> edge_map(const std::vector<EnergyTransportEdge>& edges) {
    std::map<std::pair<int, int>, double> result;
    for (const auto& edge : edges) {
        result[{edge.first_cell, edge.second_cell}] = edge.conductance_w_k;
    }
    return result;
}

std::vector<double> fluxes(const std::vector<EnergyTransportEdge>& edges, const std::vector<double>& temperatures) {
    std::vector<double> result(temperatures.size(), 0.0);
    for (const auto& edge : edges) {
        const double flux = edge.conductance_w_k * (
            temperatures[static_cast<std::size_t>(edge.second_cell)] -
            temperatures[static_cast<std::size_t>(edge.first_cell)]
        );
        result[static_cast<std::size_t>(edge.first_cell)] += flux;
        result[static_cast<std::size_t>(edge.second_cell)] -= flux;
    }
    return result;
}

std::vector<Cell> octahedral_voronoi() {
    const std::array<Vec3, 6> sites{{
        {1.0, 0.0, 0.0}, {-1.0, 0.0, 0.0},
        {0.0, 1.0, 0.0}, {0.0, -1.0, 0.0},
        {0.0, 0.0, 1.0}, {0.0, 0.0, -1.0},
    }};
    std::vector<Cell> cells(sites.size());
    for (std::size_t i = 0; i < sites.size(); ++i) {
        Cell& cell = cells[i];
        cell.id = static_cast<int>(i);
        cell.p = sites[i];
        cell.area_km2 = 4.0 * PI / static_cast<double>(sites.size());
        for (double x : {-1.0, 1.0}) {
            for (double y : {-1.0, 1.0}) {
                for (double z : {-1.0, 1.0}) {
                    const Vec3 vertex = normalize({x, y, z});
                    if (dot(vertex, cell.p) > 0.0) {
                        cell.control_volume_vertices.push_back(vertex);
                    }
                }
            }
        }
        const Vec3 reference = std::abs(cell.p.z) > 0.5
            ? Vec3{1.0, 0.0, 0.0} : Vec3{0.0, 0.0, 1.0};
        const Vec3 u = normalize(cross(reference, cell.p));
        const Vec3 v = cross(cell.p, u);
        std::sort(cell.control_volume_vertices.begin(), cell.control_volume_vertices.end(), [&](Vec3 a, Vec3 b) {
            return std::atan2(dot(a, v), dot(a, u)) < std::atan2(dot(b, v), dot(b, u));
        });
        for (std::size_t edge = 0; edge < cell.control_volume_vertices.size(); ++edge) {
            const Vec3 midpoint = normalize(add(
                cell.control_volume_vertices[edge],
                cell.control_volume_vertices[(edge + 1) % cell.control_volume_vertices.size()]
            ));
            int neighbor = -1;
            double best = -2.0;
            for (std::size_t j = 0; j < sites.size(); ++j) {
                if (j != i && dot(midpoint, sites[j]) > best) {
                    best = dot(midpoint, sites[j]);
                    neighbor = static_cast<int>(j);
                }
            }
            cell.control_volume_edge_neighbor_ids.push_back(neighbor);
            cell.neighbors.push_back(neighbor);
        }
    }
    return cells;
}

bool analytic_stiffness_and_face_aggregation() {
    const double conductivity = 7.0;
    const auto voronoi = octahedral_voronoi();
    const auto edges = build_climate_heat_transport_edges(MESH_BACKEND_FIBONACCI, voronoi, conductivity);
    CHECK(edges.size() == 12);
    const double expected = conductivity * std::acos(1.0 / 3.0) / (PI / 2.0);
    for (const auto& edge : edges) {
        CHECK(close(edge.conductance_w_k, expected));
    }
    std::vector<double> impulse(voronoi.size(), 0.0);
    impulse[0] = 10.0;
    const auto flux = fluxes(edges, impulse);
    CHECK(close(flux[0], -40.0 * expected));
    CHECK(flux[1] == 0.0);
    for (std::size_t i = 2; i < flux.size(); ++i) {
        CHECK(close(flux[i], 10.0 * expected));
    }

    // A regular icosahedron has two equilateral triangles per primal edge:
    // 0.5*(cot(pi/3)+cot(pi/3)) = 1/sqrt(3). Its barycentric dual has two
    // boundary segments per pair, which must not produce duplicate heat edges.
    const auto geodesic = generated_mesh(MESH_BACKEND_GEODESIC_ICOSAHEDRON, 12);
    const auto triangle_edges = build_climate_heat_transport_edges(MESH_BACKEND_GEODESIC_ICOSAHEDRON, geodesic, conductivity);
    CHECK(geodesic.size() == 12);
    CHECK(triangle_edges.size() == 30);
    std::size_t directed_segments = 0;
    for (const Cell& cell : geodesic) {
        directed_segments += cell.control_volume_vertices.size();
    }
    CHECK(directed_segments == 4 * triangle_edges.size());
    for (const auto& edge : triangle_edges) {
        CHECK(close(edge.conductance_w_k, conductivity / std::sqrt(3.0)));
    }
    return true;
}

bool conservation_constant_mode_and_dissipation() {
    for (int backend : {MESH_BACKEND_FIBONACCI, MESH_BACKEND_GEODESIC_ICOSAHEDRON}) {
        const auto cells = generated_mesh(backend, 128);
        const auto edges = build_climate_heat_transport_edges(backend, cells, 2.0);
        CHECK(edge_map(edges).size() == edges.size());
        CHECK(edges.size() == 3 * cells.size() - 6);
        const auto constant = fluxes(edges, std::vector<double>(cells.size(), 271.25));
        CHECK(std::all_of(constant.begin(), constant.end(), [](double flux) { return flux == 0.0; }));
        std::vector<double> temperatures(cells.size());
        std::vector<double> capacity(cells.size());
        std::vector<double> outgoing(cells.size(), 0.0);
        for (std::size_t i = 0; i < cells.size(); ++i) {
            temperatures[i] = 10.0 + std::sin(static_cast<double>(i) * 0.37) + static_cast<double>(i) / 200.0;
            capacity[i] = cells[i].area_km2 * (1.0 + static_cast<double>(i % 11));
        }
        for (const auto& edge : edges) {
            CHECK(edge.first_cell < edge.second_cell);
            CHECK(std::isfinite(edge.conductance_w_k) && edge.conductance_w_k > 0.0);
            outgoing[static_cast<std::size_t>(edge.first_cell)] += edge.conductance_w_k;
            outgoing[static_cast<std::size_t>(edge.second_cell)] += edge.conductance_w_k;
        }
        const auto flux = fluxes(edges, temperatures);
        double timestep = std::numeric_limits<double>::infinity();
        double net_flux = 0.0;
        double absolute_flux = 0.0;
        double old_energy = 0.0;
        double old_quadratic = 0.0;
        for (std::size_t i = 0; i < cells.size(); ++i) {
            timestep = std::min(timestep, 0.1 * capacity[i] / outgoing[i]);
            net_flux += flux[i];
            absolute_flux += std::abs(flux[i]);
            old_energy += capacity[i] * temperatures[i];
            old_quadratic += capacity[i] * temperatures[i] * temperatures[i];
        }
        CHECK(std::abs(net_flux) < 1.0e-13 * absolute_flux);
        double new_energy = 0.0;
        double new_quadratic = 0.0;
        for (std::size_t i = 0; i < cells.size(); ++i) {
            const double updated = temperatures[i] + timestep * flux[i] / capacity[i];
            new_energy += capacity[i] * updated;
            new_quadratic += capacity[i] * updated * updated;
        }
        CHECK(close(new_energy, old_energy, 2.0e-14));
        CHECK(new_quadratic < old_quadratic);
    }
    return true;
}

bool permutations_and_physical_scaling() {
    for (int backend : {MESH_BACKEND_FIBONACCI, MESH_BACKEND_GEODESIC_ICOSAHEDRON}) {
        const auto original = generated_mesh(backend, 128);
        const auto original_edges = build_climate_heat_transport_edges(backend, original, 1.0);
        const auto original_map = edge_map(original_edges);
        auto permuted = original;
        const int count = static_cast<int>(original.size());
        for (int old_id = 0; old_id < count; ++old_id) {
            const int new_id = count - 1 - old_id;
            Cell cell = original[static_cast<std::size_t>(old_id)];
            cell.id = new_id;
            for (int& neighbor : cell.neighbors) {
                neighbor = count - 1 - neighbor;
            }
            std::reverse(cell.neighbors.begin(), cell.neighbors.end());
            for (int& neighbor : cell.control_volume_edge_neighbor_ids) {
                neighbor = count - 1 - neighbor;
            }
            const auto shift = static_cast<std::ptrdiff_t>(old_id % cell.control_volume_vertices.size());
            std::rotate(cell.control_volume_vertices.begin(), cell.control_volume_vertices.begin() + shift, cell.control_volume_vertices.end());
            std::rotate(cell.control_volume_edge_neighbor_ids.begin(), cell.control_volume_edge_neighbor_ids.begin() + shift, cell.control_volume_edge_neighbor_ids.end());
            permuted[static_cast<std::size_t>(new_id)] = cell;
        }
        const auto renamed = build_climate_heat_transport_edges(backend, permuted, 1.0);
        CHECK(renamed.size() == original_edges.size());
        for (const auto& edge : renamed) {
            const std::pair<int, int> old_pair = std::minmax(
                count - 1 - edge.first_cell, count - 1 - edge.second_cell
            );
            CHECK(close(edge.conductance_w_k, original_map.at(old_pair)));
        }
        auto larger = original;
        for (Cell& cell : larger) {
            cell.area_km2 *= 9.0;
        }
        const auto scaled = build_climate_heat_transport_edges(backend, larger, 3.0);
        CHECK(scaled.size() == original_edges.size());
        for (std::size_t i = 0; i < scaled.size(); ++i) {
            CHECK(close(scaled[i].conductance_w_k, 3.0 * original_edges[i].conductance_w_k));
        }
        CHECK(build_climate_heat_transport_edges(backend, original, 0.0).empty());
    }
    return true;
}

double degree_one_error(const std::vector<Cell>& cells, const std::vector<EnergyTransportEdge>& edges) {
    double residual_squared = 0.0;
    double exact_squared = 0.0;
    for (int axis = 0; axis < 3; ++axis) {
        std::vector<double> field;
        for (const Cell& cell : cells) {
            field.push_back(axis == 0 ? cell.p.x : (axis == 1 ? cell.p.y : cell.p.z));
        }
        const auto flux = fluxes(edges, field);
        for (std::size_t i = 0; i < cells.size(); ++i) {
            // Mesh radius is one kilometre, so area_km2 equals solid angle.
            const double area = cells[i].area_km2;
            const double exact = -2.0 * field[i];
            const double residual = flux[i] / area - exact;
            residual_squared += area * residual * residual;
            exact_squared += area * exact * exact;
        }
    }
    return std::sqrt(residual_squared / exact_squared);
}

bool spherical_harmonics_refine_on_both_meshes() {
    for (int backend : {MESH_BACKEND_FIBONACCI, MESH_BACKEND_GEODESIC_ICOSAHEDRON}) {
        const auto coarse = generated_mesh(backend, 128);
        const auto fine = generated_mesh(backend, 2048);
        const double coarse_error = degree_one_error(coarse, build_climate_heat_transport_edges(backend, coarse, 1.0));
        const double fine_error = degree_one_error(fine, build_climate_heat_transport_edges(backend, fine, 1.0));
        std::cout << "degree-one relative L2 error backend=" << backend
                  << " cells=" << coarse.size() << '/' << fine.size()
                  << " error=" << coarse_error << '/' << fine_error << '\n';
        CHECK(coarse_error < 0.10);
        CHECK(fine_error < 0.02);
        CHECK(fine_error < 0.6 * coarse_error);
    }
    return true;
}

bool invalid_geometry_and_coefficients_are_rejected() {
    for (int backend : {MESH_BACKEND_FIBONACCI, MESH_BACKEND_GEODESIC_ICOSAHEDRON}) {
        const auto original = generated_mesh(backend, 128);
        for (double bad : {-1.0, std::numeric_limits<double>::infinity(), std::numeric_limits<double>::quiet_NaN()}) {
            CHECK(rejects([&] { build_climate_heat_transport_edges(backend, original, bad); }));
        }
        auto bad = original;
        bad[0].area_km2 = 0.0;
        CHECK(rejects([&] { build_climate_heat_transport_edges(backend, bad, 1.0); }));
        bad = original;
        bad[0].area_km2 *= 1.01;
        CHECK(rejects([&] { build_climate_heat_transport_edges(backend, bad, 1.0); }));
        bad = original;
        bad[0].control_volume_edge_neighbor_ids.pop_back();
        CHECK(rejects([&] { build_climate_heat_transport_edges(backend, bad, 1.0); }));
        bad = original;
        bad[0].control_volume_edge_neighbor_ids[0] = 0;
        CHECK(rejects([&] { build_climate_heat_transport_edges(backend, bad, 1.0); }));
        bad = original;
        bad[0].control_volume_vertices[0] = normalize(add(bad[0].control_volume_vertices[0], mul(bad[0].p, 0.001)));
        CHECK(rejects([&] { build_climate_heat_transport_edges(backend, bad, 1.0); }));
        bad = original;
        bad[0].p = {std::numeric_limits<double>::quiet_NaN(), 0.0, 1.0};
        CHECK(rejects([&] { build_climate_heat_transport_edges(backend, bad, 1.0); }));
        bad = original;
        bad[0].id = 1;
        CHECK(rejects([&] { build_climate_heat_transport_edges(backend, bad, 1.0); }));
    }
    const auto geodesic = generated_mesh(MESH_BACKEND_GEODESIC_ICOSAHEDRON, 128);
    CHECK(rejects([&] { build_climate_heat_transport_edges(MESH_BACKEND_FIBONACCI, geodesic, 1.0); }));
    CHECK(rejects([&] { build_climate_heat_transport_edges(77, geodesic, 1.0); }));
    return true;
}

}  // namespace

int main() {
    if (
        !analytic_stiffness_and_face_aggregation() ||
        !conservation_constant_mode_and_dissipation() ||
        !permutations_and_physical_scaling() ||
        !spherical_harmonics_refine_on_both_meshes() ||
        !invalid_geometry_and_coefficients_are_rejected()
    ) {
        return 1;
    }
    return 0;
}
