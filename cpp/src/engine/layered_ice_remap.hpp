#pragma once

#include "layered_ice_column.hpp"

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace magic_geo::detail {

// Every allocation stays within one geographic column and applies to its
// water mass and water enthalpy together. The top's nonwater energy stays put.
struct LayeredIceRemapLocation {
    bool deep = false;
    int layer_id = -1; // Exactly -1 for deep; otherwise a canonical layer ID.
    bool operator==(const LayeredIceRemapLocation&) const = default;
};
struct LayeredIceRemapTargetLayer {
    int layer_id = -1;
    double density_kg_m3 = 0, conductivity_w_m_k = 0;
};
struct LayeredIceRemapTargetColumn {
    int cell_id = -1;
    std::vector<LayeredIceRemapTargetLayer> layers;
    std::optional<double> deep_density_kg_m3;
};
struct LayeredIceRemapAllocation {
    LayeredIceRemapLocation destination;
    std::uint64_t weight = 0;
};
struct LayeredIceRemapDonor {
    int cell_id = -1;
    LayeredIceRemapLocation source;
    std::vector<LayeredIceRemapAllocation> allocations;
};
struct LayeredIceRemapLimits {
    std::size_t max_columns = 4096, max_active_nodes = 16384;
    std::size_t max_donors = 20480, max_allocations = 131072;
    std::uint64_t max_arithmetic_groups = 1048576;
};
struct LayeredIceRemapRequest {
    std::string id;
    LayeredIceInput source;
    double inherited_global_energy_error_j = 0;
    double maximum_final_energy_error_j = 0;
    std::vector<LayeredIceRemapTargetColumn> targets;
    std::vector<LayeredIceRemapDonor> donors;
    LayeredIceRemapLimits limits;
};
struct LayeredIceRemapWork {
    int source_builder_calls_started = 0, output_builder_calls_started = 0;
    std::size_t donors_completed = 0, allocations_completed = 0, targets_completed = 0;
    std::uint64_t arithmetic_groups_started = 0;
};
struct LayeredIceRemapDecomposition {
    int cell_id = -1;
    LayeredIceRemapLocation source;
    double initial_water_mass_kg_m2 = 0, initial_complete_enthalpy_j_m2 = 0;
    double nonwater_capacity_j_m2_k = 0;
    double represented_water_enthalpy_j_m2 = 0, represented_stationary_nonwater_enthalpy_j_m2 = 0;
    EnthalpyMeshInterval ideal_water_enthalpy_j_m2{}, ideal_stationary_nonwater_enthalpy_j_m2{};
};
struct LayeredIceRemapTransfer {
    int cell_id = -1;
    LayeredIceRemapLocation source, destination;
    std::uint64_t weight = 0, total_weight = 0;
    double represented_fraction = 0;
    EnthalpyMeshInterval ideal_fraction{};
    double represented_water_mass_kg_m2 = 0, represented_water_enthalpy_j_m2 = 0;
    EnthalpyMeshInterval ideal_water_mass_kg_m2{}, ideal_water_enthalpy_j_m2{};
};
struct LayeredIceRemapProjection {
    int cell_id = -1;
    LayeredIceRemapLocation destination;
    double represented_water_mass_kg_m2 = 0, represented_complete_enthalpy_j_m2 = 0;
    EnthalpyMeshInterval ideal_water_mass_kg_m2{}, ideal_complete_enthalpy_j_m2{};
    EnthalpyMeshInterval mass_projection_difference_kg_m2{}, enthalpy_projection_difference_j_m2{};
    // Exact homogeneous identity maps bypass unnecessary decomposition rounding.
    bool exact_identity_used = false;
};
struct LayeredIceRemapFinal {
    LayeredIceGraph graph;
    double energy_projection_defect_upper_j = 0, final_global_energy_error_j = 0;
    EnthalpyMeshInterval represented_total_mass_change_kg{}, represented_total_enthalpy_change_j{};
    std::vector<LayeredIceRemapDecomposition> decompositions;
    std::vector<LayeredIceRemapTransfer> transfers;
    std::vector<LayeredIceRemapProjection> projections;
};
struct LayeredIceRemapReceipt {
    bool accepted = false;
    std::string failure_code, detail;
    std::optional<LayeredIceRemapRequest> request;
    LayeredIceRemapWork work;
    std::optional<LayeredIceGraph> source_graph;
    std::optional<LayeredIceRemapFinal> final;
};

// Fixed canonical input masses; all donor rows are complete and their exact
// normalized integer weights sum to one. Whole input/output global energy
// balls must be physical. The map is L1 nonexpansive for these fixed masses;
// inherited E is charged once plus the final energy projection bound. Output
// W is canonical represented W with separate mass projection intervals, not
// an original-mass trajectory certificate. A massless deep store is exactly
// constrained to zero energy and is not an independent error-ball coordinate.
LayeredIceRemapReceipt remap_layered_ice(const LayeredIceRemapRequest&);
std::string layered_ice_remap_request_json(const LayeredIceRemapRequest&);
std::string layered_ice_remap_receipt_json(const LayeredIceRemapReceipt&);

} // namespace magic_geo::detail
