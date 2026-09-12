#pragma once

#include <vector>

namespace magic_geo::detail {

struct EnergyTransportEdge {
    int first_cell = 0;
    int second_cell = 0;
    double conductance_w_k = 0.0;
};

struct SurfaceEnergyColumn {
    double area_m2 = 0.0;
    double heat_capacity_j_m2_k = 0.0;
    double longwave_emissivity = 1.0;
};

struct SurfaceEnergyStepOptions {
    double duration_seconds = 0.0;
    double absolute_tolerance_w_m2 = 1.0e-7;
    double relative_tolerance = 1.0e-12;
    int maximum_newton_iterations = 64;
    int maximum_linear_iterations = 512;
    bool operator==(const SurfaceEnergyStepOptions&) const = default;
};

struct SurfaceEnergyStep {
    std::vector<double> temperature_k;
    std::vector<double> emitted_longwave_w_m2;
    std::vector<double> horizontal_heat_convergence_w_m2;
    std::vector<double> heat_storage_tendency_w_m2;
    std::vector<double> balance_residual_w_m2;
    // Explicit representational bounds, not heat corrections. High capacities
    // can make one temperature ulp exceed the requested flux tolerance.
    std::vector<double> temperature_roundoff_allowance_w_m2;
    std::vector<double> balance_tolerance_w_m2;
    double maximum_balance_residual_w_m2 = 0.0;
    double global_balance_residual_w = 0.0;
    int newton_iterations = 0;
    int linear_iterations = 0;
};

// Validates fixed geometry once and reuses it across a seasonal integration.
class SurfaceEnergySystem {
public:
    SurfaceEnergySystem(std::vector<SurfaceEnergyColumn> columns, std::vector<EnergyTransportEdge> edges);

    const std::vector<SurfaceEnergyColumn>& columns() const noexcept { return columns_; }
    const std::vector<EnergyTransportEdge>& edges() const noexcept { return edges_; }

    SurfaceEnergyStep advance(
        const std::vector<double>& previous_temperature_k,
        const std::vector<double>& absorbed_shortwave_w_m2,
        const SurfaceEnergyStepOptions& options
    ) const;

    // Algebraic implicit stage for a composed time integrator. The reference
    // and source may be signed intermediate quantities, while the initial
    // guess and returned stage temperature remain nonnegative. Its storage
    // and residual are relative to that reference, not a whole-step ledger.
    SurfaceEnergyStep implicit_stage(
        const std::vector<double>& reference_temperature_k,
        const std::vector<double>& source_w_m2,
        const std::vector<double>& initial_guess_temperature_k,
        const SurfaceEnergyStepOptions& options
    ) const;

    // Solve (local restoring + conservative graph Laplacian) response = flux.
    // Restoring coefficients must be strictly positive, in W/m²/K. This is
    // also the preconditioner for the periodic boundary-value iteration.
    std::vector<double> linear_response(
        const std::vector<double>& local_restoring_w_m2_k,
        const std::vector<double>& flux_w_m2,
        int maximum_linear_iterations = 512
    ) const;

private:
    std::vector<SurfaceEnergyColumn> columns_;
    std::vector<EnergyTransportEdge> edges_;
    std::vector<double> root_area_;
};

// One backward-Euler step of a column energy budget. Absorbed sunlight is the
// interval mean; symmetric edges exchange watts between cells. The caller owns
// the astronomical calendar, albedo/ice feedback and periodic spin-up. This
// numerical core never re-centres temperatures or inserts balancing heat.
SurfaceEnergyStep advance_surface_energy_balance(
    const std::vector<SurfaceEnergyColumn>& columns,
    const std::vector<EnergyTransportEdge>& edges,
    const std::vector<double>& previous_temperature_k,
    const std::vector<double>& absorbed_shortwave_w_m2,
    const SurfaceEnergyStepOptions& options
);

}  // namespace magic_geo::detail
