#pragma once

#include "seasonal_energy_balance.hpp"

#include <vector>

namespace magic_geo::detail {

struct Cell;

// Physical, vertically integrated horizontal conductivity is in W/K. The
// caller chooses its planetary scaling; this builder supplies dimensionless
// mesh stiffness weights, with no radius or heat-capacity normalization.
//
// Fibonacci: orthogonal spherical Voronoi face-length/centre-distance flux.
// Geodesic: piecewise-linear primal-triangle cotangent stiffness with the
// existing barycentric control volumes used by the caller for heat storage.
// Every unordered cell pair appears once, first_cell < second_cell. Zero
// conductivity returns no edges; invalid geometry or coefficients throw.
std::vector<EnergyTransportEdge> build_climate_heat_transport_edges(
    int mesh_backend,
    const std::vector<Cell>& cells,
    double horizontal_conductivity_w_k
);

// Variable vertically integrated nodal conductivity, in W/K. Voronoi faces
// use equal half-distance harmonic resistance. Geodesic triangles use the
// arithmetic mean of their three nodal conductivities in the linear FEM
// stiffness. This is not harmonic rescaling of a homogeneous cotangent sum.
// Zero edge conductances are omitted; negative weighted stiffness is rejected.
std::vector<EnergyTransportEdge> build_climate_heat_transport_edges(
    int mesh_backend,
    const std::vector<Cell>& cells,
    const std::vector<double>& horizontal_conductivity_w_k
);

}  // namespace magic_geo::detail
