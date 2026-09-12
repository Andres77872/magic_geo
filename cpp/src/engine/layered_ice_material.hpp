#pragma once
#include "layered_ice_column.hpp"

namespace magic_geo::detail {

// A layer index of -1 denotes the column's positive deep inventory.
// A cell index of -1 denotes the external boundary (layer must also be -1).
struct LayeredMaterialAddress { int cell_id = -1, layer_id = -1; };
struct LayeredMaterialMovement {
    std::string id;
    LayeredMaterialAddress donor, recipient;
    cryosphere_prototype::Phase phase = cryosphere_prototype::Phase::solid;
    double mass_kg = 0;
    // Used only for external imports. Internal/export temperature comes from
    // the initial donor. It must be zero for those movements.
    double import_temperature_k = 0;
};
struct LayeredMaterialRequest {
    LayeredIceInput initial;
    double inherited_energy_error_j = 0, maximum_final_energy_error_j = 0;
    std::vector<LayeredMaterialMovement> movements;
};
struct LayeredMaterialNodeCertificate {
    LayeredMaterialAddress address;
    double area_m2 = 0, nonwater_capacity_j_m2_k = 0;
    double initial_W = 0, initial_H = 0, final_W = 0, final_H = 0;
    EnthalpyMeshInterval before_H{}, before_floor{}, after_H{}, after_floor{};
    EnthalpyMeshInterval gross_solid_kg{}, gross_liquid_kg{};
    EnthalpyMeshInterval ideal_final_W{}, ideal_final_H{};
    EnthalpyMeshInterval mass_projection_kg_m2{}, energy_projection_j_m2{};
};
struct LayeredMaterialParcelCertificate {
    LayeredMaterialMovement movement;
    double donor_temperature_k = 0, specific_enthalpy_j_kg = 0, carried_enthalpy_j = 0;
    EnthalpyMeshInterval ideal_specific_enthalpy_j_kg{}, ideal_carried_enthalpy_j{}, energy_projection_j{};
    bool external_outbox = false;
};
struct LayeredMaterialReceipt {
    bool accepted = false;
    std::string failure_code, detail;
    int graph_builds_started = 0, mass_calls_started = 0;
    std::optional<LayeredMaterialRequest> request;
    std::optional<LayeredIceGraph> initial_graph, final_graph;
    std::vector<LayeredMaterialNodeCertificate> nodes;
    std::vector<LayeredMaterialParcelCertificate> parcels;
    double retained_energy_defect_upper_j = 0, outbox_energy_defect_upper_j = 0;
    double joint_final_energy_error_upper_j = 0;
    EnthalpyMeshInterval retained_mass_change_kg{}, external_net_mass_kg{}, mass_balance_residual_kg{};
    EnthalpyMeshInterval retained_energy_change_j{}, external_net_energy_j{}, energy_balance_residual_j{};
    bool gross_initial_phase_inventory_proved = false, joint_nonexpansion_proved = false;
};
// Simultaneous finite phase-selective movements, with no elapsed time or heat.
// Only same-column internal movement is allowed; geographic delivery belongs
// to the routing outbox. All gross withdrawals use the initial uncertainty
// domain. Imports cannot refeed withdrawals. Nonwater capacity never moves.
// Empty pure-water output nodes refuse; topology changes use a separate remap.
// Energy error covers retained nodes and NEW external outbox jointly, once.
// It is conditional on canonical projected W; mass projection is reported but
// does not certify an original-mass trajectory or its thermal sensitivity.
LayeredMaterialReceipt apply_layered_material_events(const LayeredMaterialRequest&);
std::string layered_material_request_json(const LayeredMaterialRequest&);
std::string layered_material_receipt_json(const LayeredMaterialReceipt&);

} // namespace magic_geo::detail
