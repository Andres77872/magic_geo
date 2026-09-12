#pragma once

#include "enthalpy_mesh.hpp"
#include "terrestrial_water.hpp"
#include "terrestrial_coupled_error.hpp"

namespace magic_geo::detail {

struct EnthalpyMeshProperties {
    cryosphere_prototype::WaterProperties water{};
    double reference_water_density_kg_m3 = 0;
    double year_duration_seconds = 0;
    // Full surface coverage. C includes the combined sensible atmosphere;
    // W is the additional retained land-water reservoir, zero on wet cells.
    std::vector<SurfaceEnergyColumn> columns;
    std::vector<EnergyTransportEdge> edges;
};
struct EnthalpyMeshForcing {
    std::string id;
    double begin_seconds = 0, end_seconds = 0;
    std::vector<double> absorbed_shortwave_w_m2;
};
struct EnthalpyMeshRestart {
    std::uint64_t revision = 0;
    double elapsed_seconds = 0;
    std::vector<cryosphere_prototype::State> state;
    double canonical_energy_error_j = 0;
    std::vector<std::string> consumed_event_ids;
    std::vector<EnthalpyMeshForcing> forcing_history;
};
struct EnthalpyMeshOwnerLimits {
    std::size_t max_cells = 4096, max_edges = 32768;
    std::size_t max_prepare_attempts = 256, max_committed_intervals = 128;
    std::size_t max_events_per_interval = 8192, max_consumed_event_ids = 65536, max_identifier_bytes = 96;
    std::size_t max_thermal_attempts = 128, max_accepted_steps = 128;
    std::uint64_t max_scalar_evaluations_per_prepare = 4194304;
    std::uint64_t max_field_evaluations_per_prepare = 65536;
    std::uint64_t max_retained_cell_leaves = 2097152, max_retained_edge_leaves = 2097152;
    // Explicit opt-in admission may raise counts to 2048 commits / 4096
    // prepares, but all retained full-mesh forcing vectors share this cap.
    std::size_t max_stored_forcing_values = 524288;
};
struct EnthalpyMeshAutomaticOptions {
    double maximum_step_seconds = 21600, minimum_step_seconds = 0;
    std::size_t maximum_attempts = 64, maximum_accepted_steps = 64;
    double maximum_stage_error_j = .001;
    int maximum_sweeps = 128, maximum_coordinate_iterations = 64;
    std::uint64_t maximum_scalar_evaluations = 32768;
    int reconstruction_leaves = 32;
};
struct EnthalpyMeshIntervalRequest {
    std::uint64_t expected_revision = 0;
    double end_seconds = 0;
    EnthalpyMeshForcing forcing;
    std::vector<TerrestrialPrecipitationImport> imports;
    std::vector<TerrestrialLiquidWithdrawal> initial_liquid_withdrawals;
    EnthalpyMeshAutomaticOptions options;
    // Optional fixed allowance for this interval's actual rounded thermal E
    // increments. Sources and inherited E remain charged to the global budget.
    // A horizon scheduler can reserve duration-proportional shares once.
    std::optional<double> maximum_thermal_error_increment_j;
};
struct EnthalpyMeshOwnerWork {
    std::uint64_t prepare_attempts = 0, mass_calls_started = 0, mass_calls_returned = 0;
    std::uint64_t thermal_calls_started = 0, thermal_calls_returned = 0;
    std::uint64_t scalar_evaluations = 0, field_evaluations = 0, sweeps_started = 0;
    std::uint64_t coordinate_solves_started = 0, reconstruction_leaves_started = 0;
    std::uint64_t reserved_scalar_evaluations = 0, reserved_field_evaluations = 0;
    bool observed_counts_complete = true;
};
struct EnthalpyMeshReferenceDomain {
    bool attempted = false;
    bool proved = false;
    std::string failure_code, detail;
    double inherited_error_j = 0, duration_seconds = 0;
    std::vector<double> component_radius_j_m2;
    std::vector<EnthalpyMeshInterval> enthalpy_box_j_m2, physical_floor_j_m2;
    double reference_temperature_upper_k = 0;
};
struct EnthalpyMeshSourceJump {
    bool available = false;
    // Each old scalar certificate is explicitly airless, with Ctotal in Cb.
    // Its local inherited radius is a domain bound; local final errors are
    // never summed. The global inherited energy is charged exactly once.
    std::vector<int> cell_ids;
    std::vector<CoupledJumpCertificate> scalar_certificates;
    double inherited_error_j = 0, weighted_jump_defect_upper_j = 0, final_error_j = 0;
    EnthalpyMeshReferenceDomain after_domain;
};
struct EnthalpyMeshTrial {
    std::uint64_t begin_tick = 0, duration_ticks = 0, interval_ticks = 0;
    double start_seconds = 0, end_seconds = 0;
    double interval_initial_error_j = 0, headroom_lower_j = 0, offered_error_j = 0;
    double inherited_error_j = 0;
    EnthalpyMeshReferenceDomain before_domain, after_domain;
    bool call_started = false;
    std::optional<EnthalpyMeshReceipt> receipt;
    bool charged_increment_available = false;
    double proposed_final_error_j = 0;
    EnthalpyMeshInterval charged_increment_j{};
    bool accepted_for_private_carry = false;
    std::string refusal_code;
};
struct EnthalpyMeshDiscreteLedger {
    // Outward sums of represented states and individual recorded movements.
    // Radiation is the BE endpoint quadrature, not a true-flow integral.
    EnthalpyMeshInterval total_mass_change_kg{}, external_mass_kg{}, mass_projection_residual_kg{};
    EnthalpyMeshInterval total_storage_j{}, external_enthalpy_j{}, source_storage_j{}, source_projection_residual_j{};
    EnthalpyMeshInterval thermal_storage_j{}, absorbed_shortwave_j{}, backward_euler_emission_j{}, balance_residual_j{};
};
struct EnthalpyMeshOwnerReceipt {
    bool prepared = false;
    std::string failure_code, detail;
    std::uint64_t surface_revision = 0;
    EnthalpyMeshProperties properties;
    EnthalpyMeshOwnerLimits limits;
    double maximum_cumulative_error_j = 0;
    std::vector<Cell> surface_cells;
    EnthalpyMeshRestart initial, observed_accepted_after, private_prefix;
    bool private_prefix_error_available = false;
    std::optional<EnthalpyMeshIntervalRequest> request, observed_request_after;
    double clock_quantum_seconds = 0;
    bool mass_call_started = false;
    std::vector<int> kernel_column_cell_ids;
    std::vector<cryosphere_prototype::Column> kernel_columns;
    std::vector<cryosphere_prototype::State> kernel_initial;
    std::optional<cryosphere_prototype::MassEventInput> mass_request;
    std::optional<cryosphere_prototype::MassEventResult> mass_receipt;
    EnthalpyMeshSourceJump jump;
    std::optional<EnthalpyMeshRestart> thermal_initial;
    std::vector<EnthalpyMeshTrial> trials;
    std::vector<TerrestrialLiquidHandoff> private_liquid_outbox;
    std::optional<TerrestrialLiquidSupplyProjection> projection;
    std::optional<EnthalpyMeshDiscreteLedger> discrete_ledger;
    std::optional<EnthalpyMeshRestart> final;
    EnthalpyMeshOwnerWork work_before, work_after;
};
class EnthalpyMeshIntervalCandidate {
public:
    const EnthalpyMeshOwnerReceipt& receipt() const;
private:
    struct Data;
    std::shared_ptr<const Data> data_;
    explicit EnthalpyMeshIntervalCandidate(std::shared_ptr<const Data>);
    friend class EnthalpyMeshOwner;
};
struct EnthalpyMeshPreparation {
    std::shared_ptr<const EnthalpyMeshOwnerReceipt> diagnostic;
    std::optional<EnthalpyMeshIntervalCandidate> candidate;
};
class EnthalpyMeshOwner {
public:
    EnthalpyMeshOwner(TerrestrialSurfaceSnapshot, EnthalpyMeshProperties,
                     EnthalpyMeshRestart, double maximum_cumulative_error_j, EnthalpyMeshOwnerLimits = {});
    ~EnthalpyMeshOwner();
    EnthalpyMeshOwner(EnthalpyMeshOwner&&) noexcept;
    EnthalpyMeshOwner& operator=(EnthalpyMeshOwner&&) noexcept;
    EnthalpyMeshOwner(const EnthalpyMeshOwner&) = delete;
    EnthalpyMeshOwner& operator=(const EnthalpyMeshOwner&) = delete;
    const TerrestrialSurfaceSnapshot& surface() const;
    const EnthalpyMeshProperties& properties() const;
    const EnthalpyMeshRestart& restart() const;
    const EnthalpyMeshOwnerLimits& limits() const;
    double maximum_cumulative_error_j() const;
    const EnthalpyMeshOwnerWork& work_meter() const;
    const EnthalpyMeshOwnerReceipt* last_receipt() const;
    EnthalpyMeshPreparation prepare(const EnthalpyMeshIntervalRequest&);
    void commit(const EnthalpyMeshIntervalCandidate&);
private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

std::string enthalpy_mesh_properties_json(const EnthalpyMeshProperties&);
std::string enthalpy_mesh_restart_json(const EnthalpyMeshRestart&);
std::string enthalpy_mesh_interval_request_json(const EnthalpyMeshIntervalRequest&);
std::string enthalpy_mesh_owner_work_json(const EnthalpyMeshOwnerWork&);
std::string enthalpy_mesh_owner_receipt_json(const EnthalpyMeshOwnerReceipt&);
std::string enthalpy_mesh_owner_context_json(const EnthalpyMeshOwner&);

} // namespace magic_geo::detail
