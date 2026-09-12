#pragma once

#include "terrestrial_water.hpp"
#include "terrestrial_coupled_error.hpp"
#include "terrestrial_thermal/phase_segment.hpp"

#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace magic_geo::detail {

struct CoupledColumnState {
    double water_mass_kg_m2 = 0;
    double surface_enthalpy_j_m2 = 0;
    double atmospheric_energy_j_m2 = 0;
};
struct CoupledThermalParameters {
    double dry_heat_capacity_j_m2_k = 0;
    double atmospheric_heat_capacity_j_m2_k = 0;
    double atmospheric_longwave_absorptivity = 0;
    double sensible_exchange_w_m2_k = 0;
    double surface_shortwave_albedo = 0;
};
struct CoupledProperties {
    cryosphere_prototype::WaterProperties water;
    double reference_water_density_kg_m3;
    double year_duration_seconds;
    std::vector<CoupledThermalParameters> columns;
};
struct CoupledForcingSpan {
    std::string id;
    double begin_seconds;
    double end_seconds;
    std::vector<double> incident_shortwave_w_m2;
};
struct CoupledRestart {
    std::uint64_t revision = 0;
    double elapsed_seconds = 0;
    std::vector<CoupledColumnState> state;
    std::vector<double> canonical_energy_error_j_m2;
    std::vector<std::string> consumed_event_ids;
    std::vector<CoupledForcingSpan> forcing_history;
};
struct CoupledAcceptancePolicy {
    double max_joint_energy_error_j_m2;
};
struct CoupledLimits {
    std::size_t max_cells = 4096;
    std::size_t max_committed_intervals = 128;
    std::size_t max_prepare_attempts = 256;
    std::size_t max_events_per_interval = 8192;
    std::size_t max_consumed_event_ids = 65536;
    std::size_t max_identifier_bytes = 96;
    // Manual caller-supplied plans only; automatic mode has explicit separate
    // per-cell attempt and accepted-step caps in CoupledAutomaticOptions.
    std::size_t max_segments_per_cell = 8;
    std::size_t max_segment_calls = 512;
    std::size_t max_duration_trials = 4096;
    std::size_t max_stage_calls = 4096;
    std::size_t max_flux_evaluations = 262144;
    // Separately bounded certificate leaves; no stage/scalar-flux work hidden here.
    std::size_t max_reconstruction_leaves = 32768;
};
struct CoupledSegmentPlan {
    std::string id;
    phase_segment_prototype::Branch incoming_branch;
    phase_segment_prototype::Goal goal;
    double latest_end_seconds;
    phase_segment_prototype::StateBox tube;
    phase_segment_prototype::Budgets budgets;
    phase_segment_prototype::WorkLimits work;
    higher_order_thermal_prototype::Options stage_options;
    // Only a final within-branch entry whose cap is the common endpoint may
    // be skipped, and only when a preceding accepted segment ended there.
    bool skip_if_at_common_end = false;
    phase_segment_prototype::EndpointCertificate endpoint_certificate =
        phase_segment_prototype::EndpointCertificate::direct_tube;
    int reconstruction_leaves = 0;
};
struct CoupledCellPlan {
    int cell_id;
    std::vector<CoupledSegmentPlan> segments;
};
struct CoupledIntervalPlan {
    std::uint64_t expected_revision;
    double end_seconds;
    CoupledForcingSpan forcing;
    std::vector<TerrestrialPrecipitationImport> imports;
    std::vector<TerrestrialLiquidWithdrawal> initial_liquid_withdrawals;
    std::vector<CoupledCellPlan> columns;
};
// Fixed-W thermal continuation within one immutable forcing span. Tubes,
// branches and the accepted schedule are derived privately from the raw state.
struct CoupledAutomaticOptions {
    double maximum_step_seconds = 21600;
    // Zero means one tick of the common endpoint lattice.
    double minimum_step_seconds = 0;
    std::size_t maximum_attempts_per_cell = 64;
    std::size_t maximum_total_attempts = 256;
    std::size_t maximum_accepted_steps_per_cell = 64;
    std::size_t maximum_total_accepted_steps = 128;
    int maximum_tube_passes_per_attempt = 8;
    std::size_t maximum_total_tube_passes = 1024;
    double maximum_numerical_equation_defect_j_m2 = 1e-4;
    phase_segment_prototype::WorkLimits work{1,16,2,1024};
    higher_order_thermal_prototype::Options stage_options{1e-10,1e-12,30,12};
    int reconstruction_leaves = 64;
};
struct CoupledAutomaticRequest {
    std::uint64_t expected_revision = 0;
    double end_seconds = 0;
    CoupledForcingSpan forcing;
    CoupledAutomaticOptions options;
    // Applied once at the accepted initial clock, before any thermal trial.
    // Later source times require separate explicit interval boundaries.
    std::vector<TerrestrialPrecipitationImport> imports;
    std::vector<TerrestrialLiquidWithdrawal> initial_liquid_withdrawals;
};
// Spent computation is not physical state and is never rolled back on refusal.
struct CoupledWorkMeter {
    std::uint64_t prepare_attempts = 0;
    std::uint64_t mass_calls_started = 0;
    std::uint64_t mass_calls_returned = 0;
    std::uint64_t segment_calls_started = 0;
    std::uint64_t segment_calls_returned = 0;
    std::uint64_t duration_trials_started = 0;
    std::uint64_t stage_calls_started = 0;
    std::uint64_t scalar_flux_evaluations = 0;
    std::uint64_t reserved_duration_trials = 0;
    std::uint64_t reserved_stage_calls = 0;
    std::uint64_t reserved_flux_evaluations = 0;
    bool observed_work_counts_complete = true;
    std::uint64_t reserved_reconstruction_leaves = 0;
    std::uint64_t reconstruction_leaves_started = 0;
    std::uint64_t automatic_attempts_started = 0;
    std::uint64_t reserved_tube_passes = 0;
    std::uint64_t tube_passes_started = 0;
};
struct CoupledSegmentObservation {
    int cell_id;
    std::size_t plan_index;
    bool skipped_at_common_end = false;
    bool request_available = false;
    phase_segment_prototype::Input generated_input{};
    bool call_started = false;
    bool receipt_available = false;
    phase_segment_prototype::Receipt receipt;
    CoupledSegmentCertificate error;
    bool automatic_trial = false;
    std::uint64_t begin_tick = 0, duration_ticks = 0, interval_ticks = 0;
    double interval_initial_error_j_m2 = 0;
    double interval_headroom_lower_j_m2 = 0;
    double offered_error_j_m2 = 0;
    phase_segment_prototype::Input automatic_skeleton{};
    phase_segment_prototype::TubeProposalReceipt tube_proposal;
    bool charged_increment_available = false;
    phase_segment_prototype::Interval charged_increment_j_m2{};
    bool accepted_for_private_carry = false;
    std::string automatic_failure_code;
};
struct CoupledCellCoverage {
    int cell_id;
    bool applicable;
    double begin_seconds;
    double completed_end_seconds;
    std::size_t completed_segments = 0;
    bool complete = false;
};
struct CoupledEnergyLedger {
    // Ordered binary64 sums; component/aggregation residuals are retained.
    double canonical_external_enthalpy_j = 0;
    double surface_storage_j = 0;
    double air_storage_j = 0;
    double incident_shortwave_j = 0;
    double reflected_shortwave_j = 0;
    double outgoing_longwave_j = 0;
    double combined_residual_j = 0;
};
struct CoupledAttemptReceipt {
    bool prepared = false;
    std::string failure_code;
    std::string detail;
    std::uint64_t surface_revision = 0;
    CoupledProperties properties;
    CoupledAcceptancePolicy acceptance_policy{};
    CoupledLimits limits;
    std::vector<Cell> surface_cells;
    CoupledRestart initial;
    CoupledRestart observed_accepted_after;
    bool request_available = false;
    CoupledIntervalPlan request{};
    std::optional<CoupledIntervalPlan> observed_request_after;
    bool automatic_mode = false;
    std::optional<CoupledAutomaticRequest> automatic_request;
    std::optional<CoupledAutomaticRequest> observed_automatic_request_after;
    // Present only after a sourced automatic interval has certified its jump.
    // Diagnostic post-source anchor; never independent restart authority.
    std::optional<CoupledRestart> thermal_initial;
    double clock_quantum_seconds = 0;
    bool mass_request_available = false;
    cryosphere_prototype::MassEventInput mass_request;
    std::vector<int> kernel_column_cell_ids;
    std::vector<cryosphere_prototype::Column> kernel_columns;
    std::vector<cryosphere_prototype::State> kernel_initial;
    bool mass_call_started = false;
    bool mass_receipt_available = false;
    cryosphere_prototype::MassEventResult mass_receipt{};
    std::vector<CoupledJumpCertificate> mass_error;
    std::vector<CoupledSegmentObservation> segments;
    std::vector<CoupledCellCoverage> coverage;
    // A diagnostic prefix, never a committed/final state on refusal.
    CoupledRestart private_prefix;
    std::vector<TerrestrialLiquidHandoff> private_liquid_outbox;
    bool projection_available = false;
    TerrestrialLiquidSupplyProjection projection;
    bool energy_ledger_available = false;
    CoupledEnergyLedger energy_ledger;
    std::optional<CoupledRestart> final;
    CoupledWorkMeter work_before, work_after;
    bool original_source_accuracy_certified = false;
};
class CoupledIntervalCandidate {
  public:
    const CoupledAttemptReceipt& receipt() const;

  private:
    struct Data;
    std::shared_ptr<const Data> data_;
    explicit CoupledIntervalCandidate(std::shared_ptr<const Data>);
    friend class TerrestrialCoupledOwner;
};
struct CoupledPreparation {
    std::shared_ptr<const CoupledAttemptReceipt> diagnostic;
    std::optional<CoupledIntervalCandidate> candidate;
};
class TerrestrialCoupledOwner {
  public:
    TerrestrialCoupledOwner(TerrestrialSurfaceSnapshot, CoupledProperties, CoupledRestart,
                            CoupledAcceptancePolicy, CoupledLimits = {});
    ~TerrestrialCoupledOwner();
    TerrestrialCoupledOwner(TerrestrialCoupledOwner&&) noexcept;
    TerrestrialCoupledOwner& operator=(TerrestrialCoupledOwner&&) noexcept;
    TerrestrialCoupledOwner(const TerrestrialCoupledOwner&) = delete;
    TerrestrialCoupledOwner& operator=(const TerrestrialCoupledOwner&) = delete;
    const TerrestrialSurfaceSnapshot& surface() const;
    const CoupledProperties& properties() const;
    const CoupledAcceptancePolicy& acceptance_policy() const;
    const CoupledLimits& limits() const;
    const CoupledRestart& restart() const;
    const CoupledWorkMeter& work_meter() const;
    const CoupledAttemptReceipt* last_receipt() const;
    CoupledPreparation prepare(const CoupledIntervalPlan&);
    CoupledPreparation prepare(const CoupledAutomaticRequest&);
    void commit(const CoupledIntervalCandidate&);

  private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};
std::string coupled_restart_json(const CoupledRestart&);
std::string coupled_work_meter_json(const CoupledWorkMeter&);
std::string coupled_interval_plan_json(const CoupledIntervalPlan&);
std::string coupled_automatic_request_json(const CoupledAutomaticRequest&);
std::string coupled_attempt_receipt_json(const CoupledAttemptReceipt&);
std::string coupled_owner_context_json(const TerrestrialCoupledOwner&);

} // namespace magic_geo::detail
