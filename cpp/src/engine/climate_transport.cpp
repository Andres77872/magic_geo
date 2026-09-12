#include "climate_transport.hpp"

#include "constants.hpp"
#include "types/core.hpp"

#include <algorithm>
#include <cmath>
#include <iterator>
#include <limits>
#include <map>
#include <set>
#include <stdexcept>
#include <utility>
#include <vector>

namespace magic_geo::detail {
namespace {

constexpr double UNIT_TOLERANCE = 1.0e-9;
constexpr double RECIPROCAL_TOLERANCE = 1.0e-10;
constexpr double VORONOI_BISECTOR_TOLERANCE = 2.0e-9;
constexpr double AREA_RELATIVE_TOLERANCE = 2.0e-8;

Vec3 difference(Vec3 a, Vec3 b) {
    return {a.x - b.x, a.y - b.y, a.z - b.z};
}

double inner(Vec3 a, Vec3 b) {
    return a.x * b.x + a.y * b.y + a.z * b.z;
}

Vec3 vector_product(Vec3 a, Vec3 b) {
    return {
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x,
    };
}

double magnitude(Vec3 value) {
    return std::hypot(value.x, value.y, value.z);
}

void require_unit(Vec3 value) {
    if (
        !std::isfinite(value.x) || !std::isfinite(value.y) ||
        !std::isfinite(value.z) ||
        std::abs(magnitude(value) - 1.0) > UNIT_TOLERANCE
    ) {
        throw std::runtime_error("climate transport requires unit-sphere geometry");
    }
}

double minor_arc(Vec3 a, Vec3 b) {
    const double angle = std::atan2(magnitude(vector_product(a, b)), inner(a, b));
    if (!std::isfinite(angle) || angle <= 0.0 || angle >= PI) {
        throw std::runtime_error("climate transport has a degenerate spherical arc");
    }
    return angle;
}

struct SharedBoundary {
    // Reciprocal segment lengths are averaged before accumulation so choosing
    // the lower cell id as owner cannot change the physical conductance.
    std::vector<double> angular_segment_lengths;
};

using Pair = std::pair<int, int>;

std::map<Pair, SharedBoundary> shared_boundaries(const std::vector<Cell>& cells) {
    std::vector<std::vector<bool>> reverse_used;
    reverse_used.reserve(cells.size());
    for (std::size_t i = 0; i < cells.size(); ++i) {
        const Cell& cell = cells[i];
        if (cell.id != static_cast<int>(i)) {
            throw std::runtime_error("climate transport cells must be in canonical id order");
        }
        require_unit(cell.p);
        if (!std::isfinite(cell.area_km2) || cell.area_km2 <= 0.0) {
            throw std::runtime_error("climate transport cell area must be positive and finite");
        }
        const std::size_t count = cell.control_volume_vertices.size();
        if (count < 3 || cell.control_volume_edge_neighbor_ids.size() != count) {
            throw std::runtime_error("climate transport control-volume geometry is incomplete");
        }
        reverse_used.emplace_back(count, false);
        for (std::size_t edge = 0; edge < count; ++edge) {
            const int neighbor = cell.control_volume_edge_neighbor_ids[edge];
            if (neighbor < 0 || neighbor >= static_cast<int>(cells.size()) || neighbor == cell.id) {
                throw std::runtime_error("climate transport control-volume neighbor is invalid");
            }
            const Vec3 start = cell.control_volume_vertices[edge];
            const Vec3 end = cell.control_volume_vertices[(edge + 1) % count];
            require_unit(start);
            require_unit(end);
            minor_arc(start, end);
            if (inner(vector_product(start, end), cell.p) <= 0.0) {
                throw std::runtime_error("climate transport cell boundary must be counter-clockwise");
            }
        }
    }

    std::map<Pair, SharedBoundary> boundaries;
    for (std::size_t i = 0; i < cells.size(); ++i) {
        const Cell& first = cells[i];
        for (std::size_t edge = 0; edge < first.control_volume_vertices.size(); ++edge) {
            const int j = first.control_volume_edge_neighbor_ids[edge];
            if (j < static_cast<int>(i)) {
                continue;
            }
            const Cell& second = cells[static_cast<std::size_t>(j)];
            const Vec3 start = first.control_volume_vertices[edge];
            const Vec3 end = first.control_volume_vertices[
                (edge + 1) % first.control_volume_vertices.size()
            ];
            int reverse_edge = -1;
            for (std::size_t candidate = 0; candidate < second.control_volume_vertices.size(); ++candidate) {
                if (second.control_volume_edge_neighbor_ids[candidate] != static_cast<int>(i)) {
                    continue;
                }
                const Vec3 reverse_start = second.control_volume_vertices[candidate];
                const Vec3 reverse_end = second.control_volume_vertices[
                    (candidate + 1) % second.control_volume_vertices.size()
                ];
                if (
                    magnitude(difference(start, reverse_end)) <= RECIPROCAL_TOLERANCE &&
                    magnitude(difference(end, reverse_start)) <= RECIPROCAL_TOLERANCE
                ) {
                    if (reverse_edge >= 0 || reverse_used[static_cast<std::size_t>(j)][candidate]) {
                        throw std::runtime_error("climate transport segment has ambiguous reciprocity");
                    }
                    reverse_edge = static_cast<int>(candidate);
                }
            }
            if (reverse_edge < 0) {
                throw std::runtime_error("climate transport segment has no reciprocal boundary");
            }
            reverse_used[i][edge] = true;
            reverse_used[static_cast<std::size_t>(j)][static_cast<std::size_t>(reverse_edge)] = true;
            const Vec3 reverse_start = second.control_volume_vertices[static_cast<std::size_t>(reverse_edge)];
            const Vec3 reverse_end = second.control_volume_vertices[
                (static_cast<std::size_t>(reverse_edge) + 1) % second.control_volume_vertices.size()
            ];
            boundaries[{static_cast<int>(i), j}].angular_segment_lengths.push_back(
                0.5 * (minor_arc(start, end) + minor_arc(reverse_start, reverse_end))
            );
        }
    }
    for (const auto& used : reverse_used) {
        if (std::find(used.begin(), used.end(), false) != used.end()) {
            throw std::runtime_error("climate transport boundary segment is not paired");
        }
    }
    return boundaries;
}

void require_voronoi_bisectors(const std::vector<Cell>& cells) {
    for (const Cell& cell : cells) {
        for (std::size_t edge = 0; edge < cell.control_volume_vertices.size(); ++edge) {
            const int j = cell.control_volume_edge_neighbor_ids[edge];
            const Vec3 bisector = difference(cell.p, cells[static_cast<std::size_t>(j)].p);
            const double separation = magnitude(bisector);
            if (!(separation > 0.0)) {
                throw std::runtime_error("climate transport has coincident cell centres");
            }
            const Vec3 start = cell.control_volume_vertices[edge];
            const Vec3 end = cell.control_volume_vertices[(edge + 1) % cell.control_volume_vertices.size()];
            if (
                std::abs(inner(start, bisector)) > VORONOI_BISECTOR_TOLERANCE * separation ||
                std::abs(inner(end, bisector)) > VORONOI_BISECTOR_TOLERANCE * separation
            ) {
                throw std::runtime_error("climate transport Voronoi boundary is not a centre bisector");
            }
        }
    }
}

void require_consistent_spherical_areas(const std::vector<Cell>& cells) {
    if (cells.empty()) {
        return;
    }
    std::vector<double> solid_angles;
    solid_angles.reserve(cells.size());
    long double total_solid_angle = 0.0L;
    long double total_area_km2 = 0.0L;
    for (const Cell& cell : cells) {
        double solid_angle = 0.0;
        for (std::size_t edge = 0; edge < cell.control_volume_vertices.size(); ++edge) {
            const Vec3 first = cell.control_volume_vertices[edge];
            const Vec3 second = cell.control_volume_vertices[(edge + 1) % cell.control_volume_vertices.size()];
            solid_angle += 2.0 * std::atan2(
                inner(cell.p, vector_product(first, second)),
                1.0 + inner(cell.p, first) + inner(first, second) + inner(second, cell.p)
            );
        }
        if (!std::isfinite(solid_angle) || solid_angle <= 0.0) {
            throw std::runtime_error("climate transport polygon has invalid spherical area");
        }
        solid_angles.push_back(solid_angle);
        total_solid_angle += solid_angle;
        total_area_km2 += cell.area_km2;
    }
    if (std::abs(total_solid_angle - 4.0L * PI) > AREA_RELATIVE_TOLERANCE * 4.0L * PI) {
        throw std::runtime_error("climate transport control volumes do not partition the sphere");
    }
    const long double radius_squared_km2 = total_area_km2 / total_solid_angle;
    for (std::size_t i = 0; i < cells.size(); ++i) {
        const long double expected = radius_squared_km2 * solid_angles[i];
        if (std::abs(cells[i].area_km2 - expected) > AREA_RELATIVE_TOLERANCE * expected) {
            throw std::runtime_error("climate transport cell area disagrees with its spherical polygon");
        }
    }
}

double opposite_cotangent(Vec3 first, Vec3 second, Vec3 opposite) {
    const Vec3 a = difference(first, opposite);
    const Vec3 b = difference(second, opposite);
    const double twice_area = magnitude(vector_product(a, b));
    if (!std::isfinite(twice_area) || twice_area <= 0.0) {
        throw std::runtime_error("climate transport primal triangle is degenerate");
    }
    return inner(a, b) / twice_area;
}

}  // namespace

std::vector<EnergyTransportEdge> build_climate_heat_transport_edges(
    int mesh_backend,
    const std::vector<Cell>& cells,
    double horizontal_conductivity_w_k
) {
    if (mesh_backend != MESH_BACKEND_FIBONACCI && mesh_backend != MESH_BACKEND_GEODESIC_ICOSAHEDRON) {
        throw std::runtime_error("climate transport mesh backend is unsupported");
    }
    if (!std::isfinite(horizontal_conductivity_w_k) || horizontal_conductivity_w_k < 0.0) {
        throw std::runtime_error("climate transport conductivity must be nonnegative and finite");
    }
    if (cells.size() > static_cast<std::size_t>(std::numeric_limits<int>::max())) {
        throw std::runtime_error("climate transport cell count exceeds index range");
    }
    const auto boundaries = shared_boundaries(cells);
    require_consistent_spherical_areas(cells);
    if (mesh_backend == MESH_BACKEND_FIBONACCI) {
        require_voronoi_bisectors(cells);
    }
    std::vector<std::set<int>> adjacent(cells.size());
    for (const auto& [pair, boundary] : boundaries) {
        (void)boundary;
        adjacent[static_cast<std::size_t>(pair.first)].insert(pair.second);
        adjacent[static_cast<std::size_t>(pair.second)].insert(pair.first);
    }

    std::vector<EnergyTransportEdge> result;
    result.reserve(boundaries.size());
    for (const auto& [pair, boundary] : boundaries) {
        const Cell& first = cells[static_cast<std::size_t>(pair.first)];
        const Cell& second = cells[static_cast<std::size_t>(pair.second)];
        const double centre_angle = minor_arc(first.p, second.p);
        double weight = 0.0;
        if (mesh_backend == MESH_BACKEND_FIBONACCI) {
            // Radius cancels between shared boundary length and separation.
            // Sorting makes split-face accumulation independent of polygon start.
            auto lengths = boundary.angular_segment_lengths;
            std::sort(lengths.begin(), lengths.end());
            for (double length : lengths) {
                weight += length / centre_angle;
            }
        } else {
            // A geodesic dual boundary bends at the primal-edge midpoint.
            // Two-point L/d is not consistent on this nonorthogonal geometry.
            // Assemble the symmetric piecewise-linear triangle stiffness once
            // per primal edge; each adjacent triangle supplies cot(angle)/2.
            // The cotangent/Delaunay positivity relationship is discussed in
            // Bobenko & Springborn, doi:10.1007/s00454-007-9006-1. We verify
            // positivity on the supplied mesh instead of assuming it.
            std::vector<int> opposite_vertices;
            const auto& first_neighbors = adjacent[static_cast<std::size_t>(pair.first)];
            const auto& second_neighbors = adjacent[static_cast<std::size_t>(pair.second)];
            std::set_intersection(
                first_neighbors.begin(), first_neighbors.end(),
                second_neighbors.begin(), second_neighbors.end(),
                std::back_inserter(opposite_vertices)
            );
            if (opposite_vertices.size() != 2 || boundary.angular_segment_lengths.size() != 2) {
                throw std::runtime_error("climate transport geodesic edge must bound two primal triangles");
            }
            for (int opposite : opposite_vertices) {
                weight += 0.5 * opposite_cotangent(
                    first.p, second.p, cells[static_cast<std::size_t>(opposite)].p
                );
            }
        }
        if (!std::isfinite(weight) || weight <= 0.0) {
            // Never clip a negative cotangent sum: that silently changes the
            // operator and hides a non-Delaunay or malformed triangulation.
            throw std::runtime_error("climate transport stiffness must be positive and finite");
        }
        if (horizontal_conductivity_w_k == 0.0) {
            continue;
        }
        const double conductance = horizontal_conductivity_w_k * weight;
        if (!std::isfinite(conductance) || conductance <= 0.0) {
            throw std::runtime_error("climate transport conductance is outside finite positive range");
        }
        result.push_back({pair.first, pair.second, conductance});
    }
    return result;
}

std::vector<EnergyTransportEdge> build_climate_heat_transport_edges(
    int mesh_backend,
    const std::vector<Cell>& cells,
    const std::vector<double>& horizontal_conductivity_w_k
) {
    if (horizontal_conductivity_w_k.size() != cells.size()) {
        throw std::runtime_error("climate transport nodal conductivity count must match cells");
    }
    for (double conductivity : horizontal_conductivity_w_k) {
        if (!std::isfinite(conductivity) || conductivity < 0.0) {
            throw std::runtime_error("climate transport nodal conductivity must be nonnegative and finite");
        }
    }
    if (horizontal_conductivity_w_k.empty()) {
        return build_climate_heat_transport_edges(mesh_backend, cells, 0.0);
    }
    const double first_conductivity = horizontal_conductivity_w_k.front();
    if (std::all_of(horizontal_conductivity_w_k.begin(), horizontal_conductivity_w_k.end(),
                    [first_conductivity](double value) { return value == first_conductivity; })) {
        // Preserve the existing homogeneous operator, including its arithmetic
        // and geometry validation, exactly for uniform input coefficients.
        return build_climate_heat_transport_edges(mesh_backend, cells, first_conductivity);
    }

    // Reuse all existing mesh, area, reciprocity, and primal-triangle checks.
    // A unit conductivity supplies the dimensionless geometric stiffness and
    // the authoritative unordered adjacency (not the generic kNN neighbors).
    const auto geometry = build_climate_heat_transport_edges(mesh_backend, cells, 1.0);
    std::vector<std::set<int>> adjacent;
    if (mesh_backend == MESH_BACKEND_GEODESIC_ICOSAHEDRON) {
        adjacent.resize(cells.size());
        for (const auto& edge : geometry) {
            adjacent[static_cast<std::size_t>(edge.first_cell)].insert(edge.second_cell);
            adjacent[static_cast<std::size_t>(edge.second_cell)].insert(edge.first_cell);
        }
    }
    std::vector<EnergyTransportEdge> result;
    result.reserve(geometry.size());
    for (const auto& edge : geometry) {
        const std::size_t i = static_cast<std::size_t>(edge.first_cell);
        const std::size_t j = static_cast<std::size_t>(edge.second_cell);
        long double conductance = 0.0L;
        bool strictly_positive_expected = false;
        if (mesh_backend == MESH_BACKEND_FIBONACCI) {
            const double lower = std::min(horizontal_conductivity_w_k[i], horizontal_conductivity_w_k[j]);
            const double upper = std::max(horizontal_conductivity_w_k[i], horizontal_conductivity_w_k[j]);
            if (lower > 0.0) {
                // Resistances of equal Voronoi half distances add in series.
                // This form avoids overflow in 2*K_i*K_j and in K_i+K_j.
                const long double harmonic = static_cast<long double>(lower) *
                    (2.0L / (1.0L + static_cast<long double>(lower) / upper));
                conductance = harmonic * edge.conductance_w_k;
                strictly_positive_expected = true;
            }
        } else {
            std::vector<int> opposite_vertices;
            std::set_intersection(adjacent[i].begin(), adjacent[i].end(),
                                  adjacent[j].begin(), adjacent[j].end(),
                                  std::back_inserter(opposite_vertices));
            if (opposite_vertices.size() != 2) {
                throw std::runtime_error("variable climate transport edge must bound two primal triangles");
            }
            for (int opposite : opposite_vertices) {
                // For P1 temperature basis functions on a flat chord triangle,
                // gradients are constant. Integrating a P1 nodal conductivity
                // therefore gives exactly its arithmetic three-node mean.
                const long double triangle_conductivity =
                    (static_cast<long double>(horizontal_conductivity_w_k[i]) +
                     horizontal_conductivity_w_k[j] +
                     horizontal_conductivity_w_k[static_cast<std::size_t>(opposite)]) / 3.0L;
                conductance += 0.5L * triangle_conductivity * opposite_cotangent(
                    cells[i].p, cells[j].p, cells[static_cast<std::size_t>(opposite)].p
                );
            }
            // Nonnegative nodal coefficients do not by themselves guarantee
            // a monotone weighted stiffness on triangles with obtuse angles.
            // Audit the assembled edge; never clip its negative contribution.
            strictly_positive_expected = conductance > 0.0L;
        }
        if (!std::isfinite(conductance) || conductance < 0.0L ||
            conductance > static_cast<long double>(std::numeric_limits<double>::max())) {
            throw std::runtime_error("variable climate transport stiffness is outside the finite nonnegative range");
        }
        const double represented_conductance = static_cast<double>(conductance);
        if (strictly_positive_expected && !(represented_conductance > 0.0)) {
            throw std::runtime_error("variable climate transport positive conductance is unrepresentable");
        }
        if (represented_conductance > 0.0) {
            result.push_back({edge.first_cell, edge.second_cell, represented_conductance});
        }
    }
    return result;
}

}  // namespace magic_geo::detail
