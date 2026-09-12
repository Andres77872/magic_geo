#pragma once

#include "time_integrated_energy.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace magic_geo::detail {

struct SurfaceEnergyForcingInterval {
    int month_index = 0;
    double duration_seconds = 0.0;
    std::vector<double> absorbed_shortwave_w_m2;
};

struct PeriodicSurfaceEnergyOptions {
    double phase_tolerance_k = 1.0e-5;
    double annual_flux_tolerance_w_m2 = 1.0e-5;
    double relative_tolerance = 1.0e-12;
    int maximum_periodic_iterations = 64;
    int maximum_backtracks = 24;
    SurfaceEnergyStepOptions step;
    SurfaceEnergyTimeMethod time_method = SurfaceEnergyTimeMethod::backward_euler;
    // Accepted physical steps per parent forcing interval, frozen throughout
    // this solve. Empty means one each; nonempty counts must be powers of two.
    std::vector<std::size_t> thermal_subdivisions;
    std::size_t maximum_integration_steps = std::numeric_limits<std::size_t>::max();
    bool operator==(const PeriodicSurfaceEnergyOptions&) const = default;
};

class PeriodicSurfaceEnergyStepError : public std::runtime_error {
public:
    PeriodicSurfaceEnergyStepError(std::size_t interval, std::size_t substep, const std::string& cause, std::size_t attempted = 0)
        : std::runtime_error("periodic thermal step failed at forcing interval " + std::to_string(interval) +
            ", substep " + std::to_string(substep) + ": " + cause),
          forcing_interval(interval), thermal_substep(substep), attempted_steps(attempted) {}
    std::size_t forcing_interval;
    std::size_t thermal_substep;
    std::size_t attempted_steps;
};

class PeriodicSurfaceEnergyWorkLimit : public std::runtime_error {
public:
    explicit PeriodicSurfaceEnergyWorkLimit(std::size_t attempted)
        : std::runtime_error("periodic surface energy integration work limit reached after " + std::to_string(attempted) + " steps"),
          attempted_steps(attempted) {}
    std::size_t attempted_steps;
};

struct SurfaceEnergyMonth {
    double duration_seconds = 0.0;
    std::vector<double> initial_temperature_k;
    std::vector<double> final_temperature_k;
    std::vector<double> mean_temperature_k;
    std::vector<double> mean_fourth_power_temperature_k4;
    std::vector<double> absorbed_shortwave_w_m2;
    std::vector<double> emitted_longwave_w_m2;
    std::vector<double> horizontal_heat_convergence_w_m2;
    std::vector<double> heat_storage_tendency_w_m2;
    std::vector<double> balance_residual_w_m2;
    std::vector<double> balance_tolerance_w_m2;
};

struct PeriodicSurfaceEnergyYear {
    double duration_seconds = 0.0;
    std::array<SurfaceEnergyMonth, 12> months;
    std::vector<double> initial_temperature_k;
    std::vector<double> final_temperature_k;
    std::vector<double> annual_net_heating_w_m2;
    std::vector<double> annual_flux_tolerance_w_m2;
    double maximum_phase_difference_k = 0.0;
    double maximum_annual_net_heating_w_m2 = 0.0;
    double global_annual_net_heating_w = 0.0;
    int periodic_iterations = 0;
    int year_evaluations = 0;
    std::size_t integration_step_count = 0;
    std::size_t total_integration_steps = 0;
    std::uint64_t year_newton_iterations = 0;
    std::uint64_t year_linear_iterations = 0;
    double maximum_step_balance_residual_w_m2 = 0.0;
};

// Solve a periodic boundary condition on a fixed physical column system and
// repeated prescribed forcing. Months are contiguous equal-time export bins;
// callers supply appropriately resolved physical integration intervals. The
// returned fluxes and temperatures are time means of the same implicit steps.
// The initial vector selects a starting iterate, never an imposed mean climate.
PeriodicSurfaceEnergyYear solve_periodic_surface_energy_balance(
    const SurfaceEnergySystem& system,
    const std::vector<SurfaceEnergyForcingInterval>& intervals,
    const std::vector<double>& initial_temperature_k,
    const PeriodicSurfaceEnergyOptions& options = {}
);

}  // namespace magic_geo::detail
