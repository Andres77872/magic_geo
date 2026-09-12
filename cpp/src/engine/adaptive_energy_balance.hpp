#pragma once

#include "periodic_energy_balance.hpp"

namespace magic_geo::detail {

struct AdaptivePeriodicSurfaceEnergyOptions {
    PeriodicSurfaceEnergyOptions periodic;
    // Local endpoint error and month-normalized quadrature increments, with
    // fourth moments expressed as equivalent kelvin at the temperature scale.
    double local_absolute_tolerance_k = 1.0e-4;
    double local_relative_tolerance = 1.0e-8;
    double maximum_numerical_error_fraction = 0.1;
    // Observed differences between separately reconverged grids, not certified
    // absolute errors relative to the continuous equations or exact climate.
    double monthly_temperature_tolerance_k = 0.01;
    double monthly_flux_tolerance_w_m2 = 0.05;
    double monthly_relative_tolerance = 1.0e-8;
    // Zero disables the separate global refinement check, useful for isolated
    // controller experiments. A production accuracy claim requires this gate.
    int required_monthly_refinement_confirmations = 2;
    std::size_t maximum_accepted_steps_per_year = 1'000'000;
    std::size_t maximum_total_step_attempts = 5'000'000;
    int maximum_partition_refinements = 16;
    int maximum_solver_tightenings = 4;
    bool operator==(const AdaptivePeriodicSurfaceEnergyOptions&) const = default;
};

struct AdaptivePeriodicSurfaceEnergyYear {
    PeriodicSurfaceEnergyYear year;
    PeriodicSurfaceEnergyOptions accepted_periodic_options;
    // Accepted physical substeps, always pairs for a doubling comparison.
    std::vector<std::size_t> thermal_subdivisions;
    double maximum_local_error_ratio = 0.0;
    double maximum_numerical_error_ratio = 0.0;
    double maximum_endpoint_numerical_uncertainty_k = 0.0;
    double maximum_monthly_temperature_change_k = 0.0;
    double maximum_monthly_flux_change_w_m2 = 0.0;
    int monthly_refinement_confirmations = 0;
    int partition_refinements = 0;
    int solver_tightenings = 0;
    std::size_t estimator_trials = 0;
    std::size_t failed_estimator_trials = 0;
    std::size_t total_periodic_year_evaluations = 0;
    std::size_t total_step_attempts = 0;
};

// The partition and method remain fixed throughout each periodic solve. Check
// the accepted fine map against coarser steps, refine failing parent intervals,
// then restart the periodic solve without its old secant history. Children
// retain their parent's prescribed mean sunlight. By default, separately
// reconverged uniform refinements also verify monthly temperatures and fluxes.
// Astronomical forcing error still requires independent verification.
AdaptivePeriodicSurfaceEnergyYear solve_adaptive_periodic_surface_energy_balance(
    const SurfaceEnergySystem& system,
    const std::vector<SurfaceEnergyForcingInterval>& intervals,
    const std::vector<double>& initial_temperature_k,
    const AdaptivePeriodicSurfaceEnergyOptions& options = {}
);

}  // namespace magic_geo::detail
