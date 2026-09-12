#pragma once

#include "thermal_stage.hpp"
#include <string>
#include <vector>

namespace phase_segment_prototype {
using Energy = higher_order_thermal_prototype::Energy;
using Column = higher_order_thermal_prototype::Column;
using Water = higher_order_thermal_prototype::Water;
using Flux = higher_order_thermal_prototype::Flux;

struct Interval {
    double lower;
    double upper;
};
struct FluxBox {
    Interval surface_net_w_m2;
    Interval atmospheric_net_w_m2;
};
struct StateBox {
    Interval surface_enthalpy_j_m2;
    Interval atmospheric_energy_j_m2;
};
enum class Branch { dry, solid, mixed, liquid };
// fixed_duration uses the global phase law and certifies a same-time endpoint.
// Its stages may cross phase boundaries; it makes no first-hit/no-hit claim.
enum class Goal { within_branch, next_phase_boundary, fixed_duration };
enum class EndpointCertificate { direct_tube, hermite_residual };
struct WorkLimits {
    int maximum_duration_trials = 64;
    int maximum_air_iterations_per_trial = 96;
    int maximum_stage_calls = 64;
    int maximum_total_flux_evaluations = 32768;
};
struct Budgets {
    double maximum_numerical_equation_defect_j_m2;
    double maximum_locator_width_seconds;
    double maximum_physical_time_error_seconds;
    double maximum_physical_event_state_error_j_m2;
};
struct Input {
    std::string segment_id;
    std::string physical_boundary_id;
    bool is_water = false;
    bool is_lake = false;
    Water water;
    Column column;
    double water_mass_kg_m2;
    double incident_shortwave_w_m2;
    Energy initial;
    double start_seconds;
    double physical_boundary_seconds;
    double maximum_duration_seconds;
    Branch incoming_branch;
    Goal goal;
    StateBox proposed_tube;
    Budgets budgets;
    WorkLimits limits;
    higher_order_thermal_prototype::Options stage_options;
    // Zero preserves the local-horizon lattice; owners supply one shared
    // power-of-two quantum for every segment of a common interval.
    double clock_quantum_seconds = 0;
    // Opt-in same-time residual proof; direct requests retain their old format.
    EndpointCertificate endpoint_certificate = EndpointCertificate::direct_tube;
    int reconstruction_leaves = 0;
};
struct ResidualLeaf {
    int index = 0;
    bool polynomial = false;
    StateBox trace_range{};
    Interval surface_residual_integral_j_m2{};
    Interval air_residual_integral_j_m2{};
};
struct ResidualCertificate {
    bool started = false;
    bool available = false;
    int leaves_started = 0;
    std::vector<ResidualLeaf> leaves;
    Interval surface_residual_integral_j_m2{};
    Interval air_residual_integral_j_m2{};
    Interval endpoint_l1_error_j_m2{};
};
struct GuardReceipt {
    bool domain_proved = false;
    bool finite_horizon_tube_proved = false;
    bool transverse_monotonicity_proved = false;
    bool first_physical_hit_proved = false;
    bool no_physical_hit_proved = false;
    bool fixed_time_endpoint_proved = false;
    StateBox tube{};
    FluxBox field{};
    StateBox picard_image{};
    int direction = 0;
    Interval signed_surface_rate_w_m2{};
    Interval original_boundary_j_m2{};
    double represented_boundary_j_m2 = 0;
    // Original W*Lf = rounded product + exact retained product remainder
    // when that decomposition is certified; otherwise the interval remains
    // authoritative and ambiguous branch comparisons refuse.
    double boundary_product_remainder_j_m2 = 0;
    bool boundary_product_decomposition_exact = false;
    Interval boundary_representation_bridge_j_m2{};
    Interval physical_first_hit_seconds{}; // Relative to start, direct D/M..D/m.
    StateBox physical_event_state{};
};
struct TubeProposalPass {
    StateBox proposed_tube{};
    GuardReceipt guard;
    bool accepted = false;
    std::string failure_code;
};
struct TubeProposalReceipt {
    int maximum_passes = 0;
    bool accepted = false;
    std::string failure_code;
    std::string detail;
    bool input_available = false;
    Input generated_input{};
    int passes_started = 0;
    std::vector<TubeProposalPass> passes;
};
struct AirTrial {
    double energy_j_m2 = 0;
    bool evaluation_started = false;
    bool flux_available = false;
    bool equation_defect_available = false;
    std::string failure_code;
    double represented_equation_defect_j_m2 = 0;
    Flux flux{};
};
struct DurationTrial {
    double duration_seconds;
    bool first_stage_requested = false;
    bool first_stage_called = false;
    bool first_stage_in_incoming_branch = false;
    higher_order_thermal_prototype::StageInput first_stage_input{};
    higher_order_thermal_prototype::Receipt first_stage;
    bool second_stage_used = false;
    bool second_stage_called = false;
    higher_order_thermal_prototype::StageInput second_stage_input{};
    higher_order_thermal_prototype::Receipt second_stage;
    std::vector<AirTrial> air_trials;
    bool candidate_available = false;
    Energy endpoint{}; // H fixed before solving when fitting an event.
    Flux endpoint_flux{};
    bool represented_defects_available = false;
    double represented_surface_equation_defect_j_m2 = 0;
    double represented_air_equation_defect_j_m2 = 0;
    bool nominal_defects_available = false;
    StateBox nominal_first_stage_defect{};
    StateBox nominal_endpoint_quadrature_defect{};
    double nominal_equation_l1_upper_j_m2 = 0;
};
struct ComponentFluences {
    double incident_shortwave_j;
    double reflected_shortwave_j;
    double absorbed_shortwave_j;
    double surface_longwave_j;
    double atmospheric_absorbed_longwave_j;
    double atmospheric_upward_longwave_j;
    double atmospheric_downward_longwave_j;
    double sensible_surface_to_air_j;
    double outgoing_longwave_j;
    double surface_storage_j;
    double air_storage_j;
    double surface_component_residual_j;
    double air_component_residual_j;
    double combined_component_residual_j;
};
struct Receipt {
    bool accepted = false;
    std::string failure_code;
    std::string detail;
    Input request;
    GuardReceipt guard;
    std::vector<DurationTrial> trials;
    bool numerical_candidate_available = false;
    int selected_trial = -1;
    // A sampled numerical locator interval, not a certified exact SDIRK root
    // bracket or an earliest discrete root claim.
    bool sampled_locator_available = false;
    Interval sampled_duration_locator_seconds{};
    bool selected_in_locator = false;
    double clock_quantum_seconds = 0;
    double represented_gamma = 0;
    double represented_second_weight = 0;
    Interval nominal_gamma{};
    double selected_duration_seconds = 0;
    double selected_end_seconds = 0;
    double remaining_duration_seconds = 0;
    bool quadrature_available = false;
    ComponentFluences quadrature{};
    bool physical_error_bounds_available = false;
    Interval physical_time_error_seconds{};
    Interval physical_event_state_error_j_m2{};
    Interval direct_tube_state_error_j_m2{};
    bool direct_tube_error_available = false;
    // Separate from the original direct-tube box retained in guard.
    ResidualCertificate reconstruction;
    bool selected_first_stage_in_incoming_branch = false;
    bool numerical_budget_passed = false;
    bool physical_budget_passed = false;
    bool final_state_available = false;
    Energy final_state{};
    int stage_calls_started = 0;
    int duration_trials_started = 0;
    // Actual scalar evaluations in frozen stages and fitted-air trials only;
    // fixed-size outward guard/equation arithmetic is separately source-bounded.
    int total_flux_evaluations = 0;
};

// Pure, bounded construction. No A event, source consumption or owner commit.
// Refusal retains diagnostic trials but never supplies an accepted final state.
Receipt advance_phase_segment(const Input &);
// Fixed-duration proposal only: derives the initial branch and a physical
// Picard tube from the raw state. No solver call or energy/state projection.
TubeProposalReceipt propose_fixed_duration_tube(const Input &, int maximum_passes = 8);
std::string tube_proposal_receipt_json(const TubeProposalReceipt &);
std::string phase_segment_receipt_json(const Receipt &);
std::string phase_segment_input_json(const Input &);
std::string residual_certificate_json(const ResidualCertificate &);
} // namespace phase_segment_prototype
