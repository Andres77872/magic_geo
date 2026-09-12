#pragma once

#include "layered_ice_material.hpp"
#include "layered_ice_remap.hpp"

namespace magic_geo::detail {

// The exact entire initial donor mass is selected; callers supply no substitute
// mass, energy or temperature. Old parcel layer IDs remain historical provenance.
struct LayeredIceWholeInventoryExport {
    std::string id;
    LayeredMaterialAddress donor;
    cryosphere_prototype::Phase phase = cryosphere_prototype::Phase::solid;
};
struct LayeredIceTopologyLimits : LayeredIceRemapLimits {
    std::size_t max_exports = 4096;
};
struct LayeredIceTopologyRequest {
    std::string id;
    LayeredIceInput source;
    double inherited_global_energy_error_j = 0;
    double maximum_final_energy_error_j = 0;
    std::vector<LayeredIceRemapTargetColumn> targets;
    std::vector<LayeredIceRemapDonor> donors;
    std::vector<LayeredIceWholeInventoryExport> exports;
    LayeredIceTopologyLimits limits;
};
struct LayeredIceTopologyWork {
    int source_builder_calls_started = 0, output_builder_calls_started = 0;
    std::size_t donors_completed = 0, allocations_completed = 0;
    std::size_t exports_completed = 0, targets_completed = 0;
    std::uint64_t arithmetic_groups_started = 0;
};
struct LayeredIceTopologyDomain {
    LayeredMaterialAddress address;
    double area_m2 = 0, water_mass_kg_m2 = 0, enthalpy_j_m2 = 0;
    double nonwater_capacity_j_m2_k = 0, global_energy_error_j = 0;
    EnthalpyMeshInterval enthalpy_ball_j_m2{}, physical_floor_j_m2{};
    bool constrained_empty_deep = false, proved = false;
};
struct LayeredIceTopologyExportCertificate {
    LayeredIceWholeInventoryExport selection;
    double source_area_m2 = 0, source_water_mass_kg_m2 = 0;
    double source_complete_enthalpy_j_m2 = 0, source_nonwater_capacity_j_m2_k = 0;
    double represented_full_mass_kg = 0;
    EnthalpyMeshInterval exact_full_mass_kg{}, source_complete_energy_ball_j{}, full_latent_energy_j{};
    bool exact_mass_representable = false, whole_phase_proved = false;
    // J is projected directly from A*qw, never from a rounded temperature.
    // The complete ideal donor energy is routed to qw and stationary qC;
    // deleted pure-water coordinates are identically zero in the ideal map.
    LayeredMaterialParcelCertificate parcel;
};
struct LayeredIceTopologyFinal {
    LayeredIceGraph graph;
    std::vector<LayeredMaterialParcelCertificate> parcels;
    double retained_energy_defect_upper_j = 0, outbox_energy_defect_upper_j = 0;
    double final_global_energy_error_j = 0;
};
struct LayeredIceTopologyReceipt {
    bool accepted = false;
    std::string failure_code, detail;
    std::optional<LayeredIceTopologyRequest> request;
    LayeredIceTopologyWork work;
    std::optional<LayeredIceGraph> source_graph;
    std::vector<LayeredIceTopologyDomain> source_domain, final_domain;
    std::vector<LayeredIceRemapDecomposition> decompositions;
    std::vector<LayeredIceRemapTransfer> transfers;
    std::vector<LayeredIceRemapProjection> projections;
    std::vector<LayeredIceTopologyExportCertificate> export_certificates;
    double retained_energy_defect_upper_j = 0, outbox_energy_defect_upper_j = 0;
    double final_global_energy_error_j = 0;
    EnthalpyMeshInterval retained_mass_change_kg{}, exported_mass_kg{}, mass_balance_residual_kg{};
    EnthalpyMeshInterval retained_energy_change_j{}, exported_energy_j{}, energy_balance_residual_j{};
    std::optional<LayeredIceTopologyFinal> final;
};

// One zero-time fixed homogeneous water map, with whole-donor phase-certified
// exports. Each positive initial active/deep donor occurs exactly once in
// donors OR exports. The full marginal E/A ball must have the declared export
// phase. A*W must be provably exactly representable for every exported mass.
// Top nonwater C and qC stay at the geographic top. Targets give the complete
// canonical layer order and prescribed density/conductivity. Existing builder
// rules still govern the final graph; no empty pure-water node is inverted.
// The inherited joint retained/old-outbox energy radius is charged once plus
// direct final retained/new-outbox projection defects. Old outboxes are identity
// coordinates managed by the owner. Canonical output W has separate mass
// projection intervals; original-mass/geometry/spatial accuracy is not certified.
LayeredIceTopologyReceipt apply_layered_ice_topology(const LayeredIceTopologyRequest&);
std::string layered_ice_topology_request_json(const LayeredIceTopologyRequest&);
std::string layered_ice_topology_receipt_json(const LayeredIceTopologyReceipt&);

} // namespace magic_geo::detail
