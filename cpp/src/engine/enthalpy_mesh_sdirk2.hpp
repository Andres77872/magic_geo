#pragma once

#include "enthalpy_mesh.hpp"

namespace magic_geo::detail {

// Bernstein coefficients on one leaf's unit interval. All coefficients are
// outward enclosures; degree is coefficients.size()-1, bounded by eight.
using EnthalpyMeshPolynomial = std::vector<EnthalpyMeshInterval>;
struct EnthalpyMeshQuadraticLeaf {
    int index = 0;
    bool complete = false;
    std::vector<EnthalpyMeshPolynomial> enthalpy, temperature, residual;
    std::vector<std::string> temperature_branch;
    std::vector<double> absolute_residual_integral_upper_j_m2;
    double weighted_residual_upper_j = 0;
};
struct EnthalpyMeshSdirk2Receipt {
    bool accepted = false;
    std::string failure_code, detail;
    std::optional<EnthalpyMeshRequest> request;
    double gamma = 0, diagonal_duration_seconds = 0, off_diagonal_duration_seconds = 0;
    bool tableau_bridges_available = false;
    EnthalpyMeshInterval duration_sum_defect_seconds{}, second_order_coefficient_defect{};
    std::vector<double> initial_heating_w_m2, first_stage_heating_w_m2, second_stage_base_j_m2;
    std::vector<EnthalpyMeshInterval> second_stage_base_defect_j_m2;
    // Each existing BE primitive retains its own physical-domain and algebraic
    // proof, and one deliberately untightened linear reconstruction leaf.
    // These internal endpoint errors are NOT added to the final curve error.
    std::optional<EnthalpyMeshReceipt> first_stage, second_stage;
    bool physical_curve_proved = false, endpoint_error_available = false;
    std::vector<EnthalpyMeshQuadraticLeaf> leaves;
    double local_endpoint_error_upper_j = 0;
    std::optional<std::vector<double>> final_enthalpy_j_m2;
    std::uint64_t scalar_evaluations = 0, field_evaluations = 0;
    int stage_calls_started = 0, sweeps_started = 0, coordinate_solves_started = 0;
    int backward_euler_leaves_started = 0, certificate_leaves_started = 0;
};

// Represented SDIRK2 proposal, with physical stage-base admission and an
// independent exact quadratic-curve residual proof. Refuses a nonphysical
// stage base or reconstruction; never repairs it by clipping. The request's
// sweep/scalar caps are shared by both stages. Fixed W, nonnegative S, positive
// effective sensible capacities and symmetric positive transport have the same
// meaning as the BE core. Pure-water mode must be explicitly enabled in options.
// The certified norm is sum_i A_i |delta H_i| from the canonical point start.
// No owner dispatch, annual accuracy, source uncertainty, or glacier-depth
// model is implied. Rounded tableau/base defects are included by the curve.
EnthalpyMeshSdirk2Receipt advance_enthalpy_mesh_sdirk2(const EnthalpyMeshRequest&);
std::string enthalpy_mesh_sdirk2_receipt_json(const EnthalpyMeshSdirk2Receipt&);

} // namespace magic_geo::detail
