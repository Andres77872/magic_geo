#include "engine/seasonal_energy_balance.hpp"

#include <algorithm>
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <vector>

namespace {
using namespace magic_geo::detail;
constexpr double sigma = 5.670374419e-8;

void require(bool condition, const char* message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

void close(double actual, double expected, double tolerance, const char* message) {
    if (!std::isfinite(actual) || std::abs(actual - expected) > tolerance) {
        std::cerr << message << ": " << actual << " versus " << expected << '\n';
        throw std::runtime_error(message);
    }
}

void equilibrium_and_zero_temperature() {
    const std::vector<SurfaceEnergyColumn> columns{{2.0, 4.0e6, 0.96}, {3.0, 2.1e8, 0.96}};
    const double flux = 0.96 * sigma * std::pow(300.0, 4);
    SurfaceEnergyStepOptions options;
    options.duration_seconds = 1.0e6;
    const auto equilibrium = advance_surface_energy_balance(columns, {{0, 1, 10.0}}, {300.0, 300.0}, {flux, flux}, options);
    require(equilibrium.temperature_k == std::vector<double>({300.0, 300.0}), "uniform radiative equilibrium moved");
    require(equilibrium.newton_iterations == 0, "equilibrium required a spurious correction");
    options.duration_seconds = 3.0;
    const auto heating = advance_surface_energy_balance({{2.0, 4.0, 0.0}}, {}, {0.0}, {100.0}, options);
    close(heating.temperature_k[0], 75.0, 1.0e-10, "absolute-zero heating changed the budget");
    const auto cold = advance_surface_energy_balance({{2.0, 4.0, 0.0}}, {}, {0.0}, {0.0}, options);
    require(cold.temperature_k[0] == 0.0 && cold.newton_iterations == 0, "zero equilibrium was not preserved exactly");
    options.duration_seconds = 1.0e15;
    const auto long_cold = advance_surface_energy_balance({{1.0e12, 4.0e6, 0.0}}, {}, {0.0}, {0.0}, options);
    require(long_cold.temperature_k[0] == 0.0, "Newton initial guess became a physical temperature floor");
    const auto sub_kelvin = advance_surface_energy_balance(
        {{1.0e12, 4.0e6, 0.0}, {2.0e12, 2.0e8, 0.0}}, {{0, 1, 1.0e12}}, {0.5, 0.5}, {0.0, 0.0}, options);
    require(sub_kelvin.temperature_k == std::vector<double>({0.5, 0.5}) && sub_kelvin.newton_iterations == 0,
        "balanced sub-kelvin columns entered an unnecessary solve");
}

void storage_tolerance_accounts_for_representable_temperature() {
    // A supported high-pressure/low-gravity column. For an hourly step, one
    // double-precision temperature ulp represents several micro-watts/m².
    const double capacity = 1004.0 * 1.0e8 / (9.80665 * 0.050001);
    SurfaceEnergyStepOptions options;
    options.duration_seconds = 3600.0;
    for (const double flux : {0.0, 100.0, 240.0, 400.0, 1000.0}) {
        const auto step = advance_surface_energy_balance({{1.0e12, capacity, 0.96}}, {}, {300.0}, {flux}, options);
        long double low = 299.0L, high = 301.0L;
        for (int iteration = 0; iteration < 100; ++iteration) {
            const long double middle = (low + high) / 2.0L;
            const long double residual = static_cast<long double>(capacity) * (middle - 300.0L) / 3600.0L +
                static_cast<long double>(0.96) * sigma * middle * middle * middle * middle - flux;
            if (residual > 0.0L) high = middle; else low = middle;
        }
        const double reference = static_cast<double>((low + high) / 2.0L);
        const double ulp = std::nextafter(reference, std::numeric_limits<double>::infinity()) - reference;
        close(step.temperature_k[0], reference, 2.0 * ulp, "storage-limited temperature disagrees with independent root");
        require(step.temperature_roundoff_allowance_w_m2[0] > options.absolute_tolerance_w_m2,
            "representational storage uncertainty was hidden");
        require(std::abs(step.balance_residual_w_m2[0]) <= step.balance_tolerance_w_m2[0],
            "representational tolerance did not cover the measured residual");
        const double direct = capacity * (step.temperature_k[0] - 300.0) / 3600.0 +
            step.emitted_longwave_w_m2[0] - flux;
        close(step.balance_residual_w_m2[0], direct, 1.0e-12, "reported energy residual was replaced with a balancing correction");
    }
}

void unequal_columns_exchange_heat_conservatively() {
    const std::vector<SurfaceEnergyColumn> columns{{2.0, 4.0, 0.0}, {3.0, 5.0, 0.0}};
    SurfaceEnergyStepOptions options;
    options.duration_seconds = 2.0;
    const auto step = advance_surface_energy_balance(columns, {{0, 1, 7.0}}, {200.0, 300.0}, {0.0, 0.0}, options);
    const double difference = 100.0 / (1.0 + 14.0 * (1.0 / 8.0 + 1.0 / 15.0));
    const double mean = (8.0 * 200.0 + 15.0 * 300.0) / 23.0;
    close(step.temperature_k[0], mean - 15.0 / 23.0 * difference, 1.0e-9, "two-column implicit solution differs");
    close(step.temperature_k[1], mean + 8.0 / 23.0 * difference, 1.0e-9, "two-column implicit solution differs");
    close(8.0 * step.temperature_k[0] + 15.0 * step.temperature_k[1], 6100.0, 1.0e-8, "transport created heat");
    close(2.0 * step.horizontal_heat_convergence_w_m2[0] + 3.0 * step.horizontal_heat_convergence_w_m2[1], 0.0, 1.0e-10, "edge exchange is not antisymmetric");
    require(step.temperature_k[0] >= 200.0 && step.temperature_k[1] <= 300.0, "diffusion introduced an extremum");
    const auto permuted = advance_surface_energy_balance({columns[1], columns[0]}, {{1, 0, 7.0}}, {300.0, 200.0}, {0.0, 0.0}, options);
    close(step.temperature_k[0], permuted.temperature_k[1], 1.0e-10, "cell permutation changed physical solution");
    close(step.temperature_k[1], permuted.temperature_k[0], 1.0e-10, "edge orientation changed physical solution");
}

void nonlinear_cooling_matches_independent_scalar_root() {
    SurfaceEnergyStepOptions options;
    options.duration_seconds = 1.0e7;
    const auto step = advance_surface_energy_balance({{1.0e12, 1.0e7, 0.8}}, {}, {300.0}, {0.0}, options);
    double lower = 0.0, upper = 300.0;
    for (int i = 0; i < 120; ++i) {
        const double middle = (lower + upper) / 2.0;
        const double residual = middle - 300.0 + 0.8 * sigma * std::pow(middle, 4);
        if (residual > 0.0) upper = middle; else lower = middle;
    }
    close(step.temperature_k[0], (lower + upper) / 2.0, 1.0e-8, "graybody cooling disagrees with bisection");
    require(step.temperature_k[0] > 0.0 && step.temperature_k[0] < 300.0, "implicit cooling lost positivity");
    close(step.heat_storage_tendency_w_m2[0] + step.emitted_longwave_w_m2[0], 0.0, 1.0e-7, "cooling ledger does not close");
}

void stiff_heating_remains_finite_and_balanced() {
    SurfaceEnergyStepOptions options;
    options.duration_seconds = 2.6e6;
    const auto step = advance_surface_energy_balance({{3.0e12, 4.0e6, 0.96}}, {}, {0.0}, {2.1e12}, options);
    require(std::isfinite(step.temperature_k[0]) && step.temperature_k[0] > 0.0, "extreme irradiation lost finite positive temperature");
    close(step.emitted_longwave_w_m2[0] + step.heat_storage_tendency_w_m2[0], 2.1e12, 3.0, "extreme irradiation energy budget failed");
}

double diffuse_for_duration(int steps) {
    std::vector<double> temperature{200.0, 300.0};
    const std::vector<SurfaceEnergyColumn> columns{{1.0, 10.0, 0.0}, {1.0, 10.0, 0.0}};
    SurfaceEnergyStepOptions options;
    options.duration_seconds = 2.0 / steps;
    for (int i = 0; i < steps; ++i) {
        temperature = advance_surface_energy_balance(columns, {{0, 1, 3.0}}, temperature, {0.0, 0.0}, options).temperature_k;
    }
    return temperature[1] - temperature[0];
}

void temporal_refinement_matches_exact_heat_equation() {
    const double exact = 100.0 * std::exp(-0.6 * 2.0);
    const double coarse = std::abs(diffuse_for_duration(16) - exact);
    const double medium = std::abs(diffuse_for_duration(32) - exact);
    const double fine = std::abs(diffuse_for_duration(64) - exact);
    require(coarse / medium > 1.9 && medium / fine > 1.9, "backward Euler fails first-order temporal refinement");
    require(fine < medium && medium < coarse, "temporal refinement did not approach the analytic solution");
}

void malformed_or_unconverged_steps_fail_explicitly() {
    SurfaceEnergyStepOptions options;
    options.duration_seconds = 1.0;
    const std::vector<SurfaceEnergyColumn> columns{{1.0, 4.0e6, 0.96}, {1.0, 4.0e6, 0.96}};
    bool rejected = false;
    try {
        advance_surface_energy_balance(columns, {{0, 1, 1.0}, {1, 0, 1.0}}, {300.0, 300.0}, {1.0, 1.0}, options);
    } catch (const std::invalid_argument&) { rejected = true; }
    require(rejected, "duplicate heat exchange was silently doubled");
    rejected = false;
    options.maximum_newton_iterations = 1;
    options.duration_seconds = 1.0e7;
    try {
        advance_surface_energy_balance({columns[0]}, {}, {300.0}, {0.0}, options);
    } catch (const std::runtime_error&) { rejected = true; }
    require(rejected, "unconverged climate step was published as a solution");
}

void algebraic_stages_keep_physical_steps_strict() {
    SurfaceEnergyStepOptions options;
    options.duration_seconds = 1.0;
    const SurfaceEnergySystem system({{2.0, 1.0, 0.0}}, {});
    const auto stage = system.implicit_stage({-100.0}, {200.0}, {300.0}, options);
    close(stage.temperature_k[0], 100.0, 1.0e-8, "signed stage reference was treated as a physical initial state");
    const auto signed_source = system.implicit_stage({100.0}, {-10.0}, {100.0}, options);
    close(signed_source.temperature_k[0], 90.0, 1.0e-8, "signed stage source changed its algebraic equation");
    bool rejected = false;
    try { system.advance({100.0}, {-10.0}, options); }
    catch (const std::invalid_argument&) { rejected = true; }
    require(rejected, "algebraic stages weakened the physical forcing contract");
    rejected = false;
    try { system.implicit_stage({-100.0}, {0.0}, {300.0}, options); }
    catch (const std::runtime_error&) { rejected = true; }
    require(rejected, "a stage without a nonnegative solution was accepted");
}

}  // namespace

int main() {
    try {
        equilibrium_and_zero_temperature();
        storage_tolerance_accounts_for_representable_temperature();
        unequal_columns_exchange_heat_conservatively();
        nonlinear_cooling_matches_independent_scalar_root();
        stiff_heating_remains_finite_and_balanced();
        temporal_refinement_matches_exact_heat_equation();
        malformed_or_unconverged_steps_fail_explicitly();
        algebraic_stages_keep_physical_steps_strict();
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
    return 0;
}
