#pragma once
#include "terrestrial_thermal/phase_segment.hpp"
#include <string>
#include <vector>

namespace magic_geo::detail {
// Conditional on the explicit canonical W projection and prescribed import J.
// This is not an original-source mass/energy trajectory certificate.
inline constexpr const char *coupled_error_scope =
    "canonical_projected_W_prescribed_import_J_reference_v1";
struct CanonicalMovement {
    double mass_kg;
    double carried_enthalpy_j;
};
struct CoupledDomainCertificate {
    bool accepted = false;
    std::string failure_code, detail;
    phase_segment_prototype::StateBox uncertainty_box{};
    phase_segment_prototype::Interval surface_floor_j_m2{}, air_floor_j_m2{};
};
struct CoupledJumpCertificate {
    bool accepted = false;
    std::string failure_code, detail;
    CoupledDomainCertificate before_domain, after_domain;
    phase_segment_prototype::Interval withdrawal_density_kg_m2{}, import_energy_j_m2{};
    phase_segment_prototype::Interval canonical_mass_projection_kg_m2{};
    phase_segment_prototype::Interval ideal_jump_j_m2{}, state_projection_j_m2{},
        export_bridge_j_m2{};
    bool liquid_feasibility_proved = false;
    double inherited_error_j_m2 = 0, jump_defect_upper_j_m2 = 0,
        final_error_j_m2 = 0, outbox_error_upper_j = 0;
    std::vector<double> per_withdrawal_error_upper_j;
};
struct CoupledSegmentCertificate {
    bool accepted = false;
    std::string failure_code, detail;
    CoupledDomainCertificate before_domain, after_domain;
    double inherited_error_j_m2 = 0, time_transport_upper_j_m2 = 0,
        local_same_time_error_upper_j_m2 = 0, final_error_j_m2 = 0;
};
CoupledDomainCertificate certify_coupled_domain(
    const phase_segment_prototype::Water &, const phase_segment_prototype::Column &,
    double water_mass_kg_m2, phase_segment_prototype::Energy, double joint_error_j_m2);
CoupledJumpCertificate certify_canonical_jump(
    const phase_segment_prototype::Water &, const phase_segment_prototype::Column &,
    double initial_W, phase_segment_prototype::Energy initial,
    double final_W, phase_segment_prototype::Energy final,
    double inherited_error_j_m2, const std::vector<CanonicalMovement> &imports,
    const std::vector<CanonicalMovement> &liquid_withdrawals,
    double maximum_joint_error_j_m2);
// Accept only a native accepted receipt. The owner calls this directly with its
// actual returned receipt; this helper does not authenticate caller-made data.
CoupledSegmentCertificate certify_coupled_segment(
    const phase_segment_prototype::Receipt &, double inherited_error_j_m2,
    double maximum_joint_error_j_m2);
} // namespace magic_geo::detail
