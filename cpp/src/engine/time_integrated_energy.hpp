#pragma once

#include "seasonal_energy_balance.hpp"

#include <vector>

namespace magic_geo::detail {

enum class SurfaceEnergyTimeMethod {
    backward_euler,
    tr_bdf2,
};

struct IntegratedSurfaceEnergyStep {
    // Final temperature; all fluxes, storage and residuals describe the whole
    // physical interval, using the accepted method's quadrature weights.
    SurfaceEnergyStep budget;
    std::vector<double> mean_temperature_k;
    std::vector<double> mean_fourth_power_temperature_k4;
    std::vector<double> mean_cubic_temperature_k3;
    // Bound on endpoint error from stage solves and arithmetic, independent
    // of the accepted method's local temporal-discretization error.
    double endpoint_numerical_uncertainty_k = 0.0;
    // TR-BDF2's minimum stage margin after stage/endpoint uncertainty bounds.
    // Entire analytically unforced zero components are excluded. max(double)
    // denotes either an all-zero system or BE's analytic positivity guarantee.
    double minimum_stage_positivity_margin_k = 0.0;
};

// Integrate a nonnegative interval-constant physical shortwave source on a
// fixed column system. TR-BDF2 uses its positive (b,b,a) quadrature at the
// initial and two implicit stage temperatures. A failed/uncertified TR stage
// throws for the adaptive caller to reject; no extrapolated state, temperature
// clipping, or balancing flux is substituted.
IntegratedSurfaceEnergyStep integrate_surface_energy_step(
    const SurfaceEnergySystem& system,
    const std::vector<double>& initial_temperature_k,
    const std::vector<double>& absorbed_shortwave_w_m2,
    const SurfaceEnergyStepOptions& options,
    SurfaceEnergyTimeMethod method
);

}  // namespace magic_geo::detail
