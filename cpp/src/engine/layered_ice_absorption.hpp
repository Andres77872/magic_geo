#pragma once

#include "layered_ice_material.hpp"

namespace magic_geo::detail {

struct LayeredIceOwnedParcel {
    std::string transaction_id;
    std::uint64_t source_revision = 0;
    LayeredMaterialParcelCertificate parcel;
    int geographic_cell_id = -1;
};
struct LayeredIceAbsorptionSelection {
    std::string transaction_id, event_id;
    LayeredMaterialAddress recipient;
};
struct LayeredIceAbsorptionRequest {
    // Trusted canonical initial witness. Owner callers bind these full parcel
    // records to their accepted snapshot; this pure component authenticates no
    // external owner, transport path or original physical source history.
    LayeredIceInput initial;
    std::vector<LayeredIceOwnedParcel> pending_outboxes;
    std::vector<LayeredIceAbsorptionSelection> selections;
    double inherited_joint_energy_error_j = 0;
    double maximum_final_energy_error_j = 0;
};
struct LayeredIceAbsorptionNode {
    LayeredMaterialAddress address;
    double area_m2 = 0, nonwater_capacity_j_m2_k = 0;
    double initial_W = 0, initial_H = 0, final_W = 0, final_H = 0;
    EnthalpyMeshInterval absorbed_mass_kg{}, absorbed_energy_j{};
    EnthalpyMeshInterval ideal_final_W{}, ideal_final_H{};
    EnthalpyMeshInterval mass_projection_kg_m2{}, energy_projection_j_m2{};
    EnthalpyMeshInterval before_H{}, before_floor{}, after_H{}, after_floor{};
};
struct LayeredIceAbsorptionWork {
    std::uint64_t source_builder_calls_started = 0, output_builder_calls_started = 0;
    std::uint64_t parcels_absorbed = 0, nodes_updated = 0;
};
struct LayeredIceAbsorptionResult {
    LayeredIceGraph graph;
    std::vector<LayeredIceOwnedParcel> pending_outboxes;
    double final_joint_energy_error_j = 0;
};
struct LayeredIceAbsorptionReceipt {
    bool accepted = false;
    std::string failure_code, detail;
    std::optional<LayeredIceAbsorptionRequest> request;
    std::optional<LayeredIceGraph> source_graph;
    std::optional<LayeredIceAbsorptionResult> final;
    std::vector<LayeredIceAbsorptionNode> nodes;
    LayeredIceAbsorptionWork work;
    double energy_projection_defect_upper_j = 0;
    EnthalpyMeshInterval absorbed_mass_kg{}, absorbed_energy_j{};
    EnthalpyMeshInterval retained_mass_change_kg{}, retained_energy_change_j{};
    EnthalpyMeshInterval mass_balance_residual_kg{}, energy_balance_residual_j{};
};

// Prescribed whole-parcel receiving only. Exact source operands are saved mass
// and carried joules; donor temperature and specific enthalpy are provenance.
// No calorimeter, extraction, thermal evolution or hydrologic routing runs.
LayeredIceAbsorptionReceipt absorb_layered_owned_parcels(const LayeredIceAbsorptionRequest&);
std::string layered_ice_owned_parcel_json(const LayeredIceOwnedParcel&);
std::string layered_ice_absorption_selection_json(const LayeredIceAbsorptionSelection&);
std::string layered_ice_absorption_request_json(const LayeredIceAbsorptionRequest&);
std::string layered_ice_absorption_receipt_json(const LayeredIceAbsorptionReceipt&);

} // namespace magic_geo::detail
