#include "engine/time_integrated_energy.hpp"

#include <algorithm>
#include <cmath>
#include <iostream>
#include <limits>
#include <numbers>
#include <stdexcept>
#include <vector>

namespace {
using namespace magic_geo::detail;
constexpr double sigma = 5.670374419e-8;
constexpr double a = 1.0 - 1.0 / std::numbers::sqrt2;
constexpr double b = 0.5 / std::numbers::sqrt2;

void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

void close(double actual, double expected, double tolerance, const char* message) {
    if (!std::isfinite(actual) || std::abs(actual - expected) > tolerance) {
        std::cerr << message << ": " << actual << " versus " << expected << '\n';
        throw std::runtime_error(message);
    }
}

template <class Callable> void rejects(Callable&& callable, const char* message) {
    bool rejected = false;
    try { callable(); } catch (const std::exception&) { rejected = true; }
    require(rejected, message);
}

void equilibrium_and_disconnected_exact_zero() {
    const SurfaceEnergySystem system({{2.0, 4.0e6, 0.8}, {3.0, 2.0e8, 0.8},
        {1.0, 10.0, 1.0}, {2.0, 30.0, 0.0}}, {{0, 1, 10.0}, {2, 3, 7.0}});
    const double outgoing = 0.8 * sigma * (300.0 * 300.0) * (300.0 * 300.0);
    SurfaceEnergyStepOptions options;
    options.duration_seconds = 1.0e6;
    for (const auto method : {SurfaceEnergyTimeMethod::backward_euler, SurfaceEnergyTimeMethod::tr_bdf2}) {
        const auto result = integrate_surface_energy_step(system, {300.0, 300.0, 0.0, 0.0},
            {outgoing, outgoing, 0.0, 0.0}, options, method);
        require(result.budget.temperature_k == std::vector<double>({300.0, 300.0, 0.0, 0.0}),
            "uniform equilibrium or disconnected dark component moved");
        require(result.budget.newton_iterations == 0, "equilibrium required an artificial correction");
        require(result.minimum_stage_positivity_margin_k > 299.0,
            "exact disconnected zero component poisoned the positivity margin");
        close(result.mean_temperature_k[0], 300.0, 0.0, "equilibrium mean changed");
        const auto zero = integrate_surface_energy_step(SurfaceEnergySystem({{1.0, 4.0, 0.8}}, {}),
            {0.0}, {0.0}, options, method);
        require(zero.endpoint_numerical_uncertainty_k == 0.0 &&
            zero.minimum_stage_positivity_margin_k == std::numeric_limits<double>::max(),
            "exact zero system was assigned artificial numerical uncertainty");
    }
}

void constant_heating_has_method_consistent_moments() {
    const SurfaceEnergySystem system({{2.0, 3.0, 0.0}}, {});
    SurfaceEnergyStepOptions options;
    options.duration_seconds = 4.0;
    options.absolute_tolerance_w_m2 = 1.0e-11;
    const auto tr = integrate_surface_energy_step(system, {100.0}, {75.0}, options, SurfaceEnergyTimeMethod::tr_bdf2);
    const double middle = 100.0 + 2.0 * a * 4.0 * 25.0;
    close(tr.budget.temperature_k[0], 200.0, 1.0e-11, "constant heating endpoint changed");
    close(tr.mean_temperature_k[0], 150.0, 1.0e-11, "TR-BDF2 did not integrate a linear temperature exactly");
    close(tr.mean_cubic_temperature_k3[0], b * std::pow(100.0, 3) + b * std::pow(middle, 3) + a * std::pow(200.0, 3),
        1.0e-7, "TR-BDF2 cubic moment uses inconsistent stage weights");
    close(tr.mean_fourth_power_temperature_k4[0], b * std::pow(100.0, 4) + b * std::pow(middle, 4) + a * std::pow(200.0, 4),
        1.0e-4, "TR-BDF2 quartic moment uses inconsistent stage weights");
    require(tr.mean_fourth_power_temperature_k4[0] > std::pow(tr.mean_temperature_k[0], 4),
        "mean fourth power was replaced by fourth power of mean temperature");
    close(tr.budget.heat_storage_tendency_w_m2[0], 75.0, 1.0e-11, "TR-BDF2 constant-source fluence was changed");
    const auto be = integrate_surface_energy_step(system, {100.0}, {75.0}, options, SurfaceEnergyTimeMethod::backward_euler);
    close(be.mean_temperature_k[0], 200.0, 1.0e-11, "BE mean lost its endpoint convention");
    close(be.mean_fourth_power_temperature_k4[0], std::pow(be.budget.temperature_k[0], 4), 1.0e-5,
        "BE quartic moment does not describe its accepted endpoint");
}

void weighted_flux_ledger_is_independently_replayable() {
    const SurfaceEnergySystem system({{2.0, 4.0e6, 0.8}, {3.0, 1.0e7, 0.9}, {5.0, 2.0e8, 0.6}},
        {{0, 1, 7.0}, {1, 2, 11.0}});
    const std::vector<double> initial{280.0, 310.0, 260.0}, source{250.0, 400.0, 180.0};
    SurfaceEnergyStepOptions options;
    options.duration_seconds = 1.0e6;
    const auto result = integrate_surface_energy_step(system, initial, source, options, SurfaceEnergyTimeMethod::tr_bdf2);
    std::vector<long double> heat(3, 0.0L);
    for (const auto& edge : system.edges()) {
        const long double exchange = edge.conductance_w_k *
            (static_cast<long double>(result.mean_temperature_k[edge.second_cell]) - result.mean_temperature_k[edge.first_cell]);
        heat[edge.first_cell] += exchange;
        heat[edge.second_cell] -= exchange;
    }
    long double global_transport = 0.0L, global_residual = 0.0L;
    for (std::size_t i = 0; i < initial.size(); ++i) {
        const auto& column = system.columns()[i];
        const double emitted = column.longwave_emissivity * sigma * result.mean_fourth_power_temperature_k4[i];
        const double transport = static_cast<double>(heat[i] / column.area_m2);
        const double storage = column.heat_capacity_j_m2_k *
            (result.budget.temperature_k[i] - initial[i]) / options.duration_seconds;
        close(result.budget.emitted_longwave_w_m2[i], emitted, 1.0e-10, "weighted OLR disagrees with the quartic moment");
        close(result.budget.horizontal_heat_convergence_w_m2[i], transport, 1.0e-10,
            "weighted transport disagrees with the mean-temperature graph");
        close(result.budget.balance_residual_w_m2[i], storage - source[i] + emitted - transport, 1.0e-9,
            "physical residual was replaced with a closure correction");
        require(std::abs(result.budget.balance_residual_w_m2[i]) <= result.budget.balance_tolerance_w_m2[i],
            "accepted weighted ledger exceeds propagated tolerance");
        global_transport += column.area_m2 * result.budget.horizontal_heat_convergence_w_m2[i];
        global_residual += column.area_m2 * result.budget.balance_residual_w_m2[i];
    }
    close(static_cast<double>(global_transport), 0.0, 1.0e-10, "weighted transport created global energy");
    close(result.budget.global_balance_residual_w, static_cast<double>(global_residual), 1.0e-10,
        "global physical residual was not area weighted");
}

double cooling_endpoint(int steps, SurfaceEnergyTimeMethod method) {
    const SurfaceEnergySystem system({{1.0, 4.0e6, 0.8}}, {});
    SurfaceEnergyStepOptions options;
    options.duration_seconds = 2.0e6 / steps;
    options.absolute_tolerance_w_m2 = 1.0e-9;
    std::vector<double> temperature{300.0};
    for (int step = 0; step < steps; ++step) {
        temperature = integrate_surface_energy_step(system, temperature, {0.0}, options, method).budget.temperature_k;
    }
    return temperature[0];
}

void analytic_radiative_cooling_is_second_order() {
    const double exact = std::pow(std::pow(300.0, -3) + 3.0 * 0.8 * sigma / 4.0e6 * 2.0e6, -1.0 / 3.0);
    const double coarse = std::abs(cooling_endpoint(16, SurfaceEnergyTimeMethod::tr_bdf2) - exact);
    const double medium = std::abs(cooling_endpoint(32, SurfaceEnergyTimeMethod::tr_bdf2) - exact);
    const double fine = std::abs(cooling_endpoint(64, SurfaceEnergyTimeMethod::tr_bdf2) - exact);
    require(coarse / medium > 3.7 && coarse / medium < 4.3 && medium / fine > 3.8 && medium / fine < 4.2,
        "TR-BDF2 radiative cooling is not second order");
    const double be_coarse = std::abs(cooling_endpoint(32, SurfaceEnergyTimeMethod::backward_euler) - exact);
    const double be_fine = std::abs(cooling_endpoint(64, SurfaceEnergyTimeMethod::backward_euler) - exact);
    require(be_coarse / be_fine > 1.8 && be_coarse / be_fine < 2.1, "BE adapter lost first-order accuracy");
    require(fine < be_fine * 0.02, "TR-BDF2 did not improve smooth cooling accuracy");
}

double diffusion_difference(int steps) {
    const SurfaceEnergySystem system({{2.0, 4.0, 0.0}, {3.0, 5.0, 0.0}}, {{0, 1, 0.7}});
    SurfaceEnergyStepOptions options;
    options.duration_seconds = 4.0 / steps;
    options.absolute_tolerance_w_m2 = 1.0e-10;
    std::vector<double> temperature{200.0, 300.0};
    for (int step = 0; step < steps; ++step) {
        temperature = integrate_surface_energy_step(system, temperature, {0.0, 0.0}, options,
            SurfaceEnergyTimeMethod::tr_bdf2).budget.temperature_k;
        close(8.0 * temperature[0] + 15.0 * temperature[1], 6100.0, 1.0e-8,
            "TR-BDF2 unequal-area/capacity diffusion created heat");
    }
    return temperature[1] - temperature[0];
}

void analytic_diffusion_is_second_order() {
    const double exact = 100.0 * std::exp(-0.7 * (1.0 / 8.0 + 1.0 / 15.0) * 4.0);
    const double coarse = std::abs(diffusion_difference(8) - exact);
    const double medium = std::abs(diffusion_difference(16) - exact);
    const double fine = std::abs(diffusion_difference(32) - exact);
    require(coarse / medium > 3.8 && coarse / medium < 4.2 && medium / fine > 3.8 && medium / fine < 4.2,
        "TR-BDF2 conservative diffusion is not second order");
}

long double scalar_implicit_root(long double reference, long double diagonal_time, long double capacity,
    long double emissivity, long double source) {
    const auto residual = [&](long double value) {
        return capacity * (value - reference) / diagonal_time + emissivity * sigma * value * value * value * value - source;
    };
    require(residual(0.0L) <= 0.0L, "independent positive scalar root does not exist");
    long double lower = 0.0L, upper = 1000.0L;
    while (residual(upper) < 0.0L) upper *= 2.0L;
    for (int iteration = 0; iteration < 180; ++iteration) {
        const long double middle = (lower + upper) / 2.0L;
        if (residual(middle) > 0.0L) upper = middle; else lower = middle;
    }
    return (lower + upper) / 2.0L;
}

long double scalar_tr_reference(double initial, double capacity, double emissivity, double source, double duration) {
    const long double time = a * duration;
    const long double value = initial;
    const long double reference1 = value + time / capacity *
        (source - emissivity * sigma * value * value * value * value);
    const long double middle = scalar_implicit_root(reference1, time, capacity, emissivity, source);
    const long double reference2 = value + static_cast<long double>(b) / a * (middle - value);
    return scalar_implicit_root(reference2, time, capacity, emissivity, source);
}

void endpoint_error_bound_and_noncontractive_positive_step() {
    const SurfaceEnergySystem system({{1.0, 4.0e6, 0.8}}, {});
    SurfaceEnergyStepOptions options;
    options.duration_seconds = 1.0e6;
    options.absolute_tolerance_w_m2 = 5.0;
    const auto loose = integrate_surface_energy_step(system, {300.0}, {0.0}, options, SurfaceEnergyTimeMethod::tr_bdf2);
    const double exact = static_cast<double>(scalar_tr_reference(300.0, 4.0e6, 0.8, 0.0, options.duration_seconds));
    require(loose.endpoint_numerical_uncertainty_k > 1.0e-6,
        "loose implicit stages were assigned a negligible endpoint uncertainty");
    require(std::abs(loose.budget.temperature_k[0] - exact) <= loose.endpoint_numerical_uncertainty_k,
        "stage-defect bound does not enclose independently solved endpoint");

    // Normalize T'= -T^4 by a 300 K reference without tiny absolute fluxes.
    // Both stages stay positive, but the step map is not a contraction in T0.
    const double capacity = sigma * 300.0 * 300.0 * 300.0;
    const SurfaceEnergySystem stiff({{1.0, capacity, 1.0}}, {});
    options.duration_seconds = 0.8 / a;
    options.absolute_tolerance_w_m2 = 1.0e-10;
    const double increment = 0.003;
    const auto low = integrate_surface_energy_step(stiff, {300.0 - increment}, {0.0}, options, SurfaceEnergyTimeMethod::tr_bdf2);
    const auto high = integrate_surface_energy_step(stiff, {300.0 + increment}, {0.0}, options, SurfaceEnergyTimeMethod::tr_bdf2);
    const double derivative = (high.budget.temperature_k[0] - low.budget.temperature_k[0]) / (2.0 * increment);
    const double exact_derivative = static_cast<double>((
        scalar_tr_reference(300.0 + increment, capacity, 1.0, 0.0, options.duration_seconds) -
        scalar_tr_reference(300.0 - increment, capacity, 1.0, 0.0, options.duration_seconds)) / (2.0L * increment));
    close(derivative, exact_derivative, 1.0e-7, "positive stiff-step sensitivity disagrees with independent scalar roots");
    require(derivative < -2.7 && derivative > -2.9,
        "stiff positive-stage counterexample no longer detects noncontractive TR composition");
    require(low.minimum_stage_positivity_margin_k > 0.0 && high.minimum_stage_positivity_margin_k > 0.0,
        "positive-stage sensitivity example was not certified");
}

void invalid_or_nonpositive_stages_fail_explicitly() {
    const SurfaceEnergySystem system({{1.0, 4.0e6, 1.0}}, {});
    SurfaceEnergyStepOptions options;
    options.duration_seconds = 1.0e8;
    rejects([&] { integrate_surface_energy_step(system, {300.0}, {0.0}, options, SurfaceEnergyTimeMethod::tr_bdf2); },
        "nonpositive TR-BDF2 stage was silently clipped or accepted");
    const auto be = integrate_surface_energy_step(system, {300.0}, {0.0}, options, SurfaceEnergyTimeMethod::backward_euler);
    require(be.budget.temperature_k[0] > 0.0, "physical backward Euler could not handle stiff cooling");
    options.duration_seconds = 1.0;
    const auto unresolved_heating = integrate_surface_energy_step(SurfaceEnergySystem({{1.0, 1.0, 1.0}}, {}),
        {0.0}, {1.0e-9}, options, SurfaceEnergyTimeMethod::backward_euler);
    require(unresolved_heating.budget.temperature_k[0] == 0.0 &&
        unresolved_heating.endpoint_numerical_uncertainty_k >= 1.0e-9 &&
        unresolved_heating.minimum_stage_positivity_margin_k == std::numeric_limits<double>::max(),
        "BE lost analytic positivity when its numerical enclosure crossed zero");
    rejects([&] { integrate_surface_energy_step(system, {-1.0}, {0.0}, options, SurfaceEnergyTimeMethod::tr_bdf2); },
        "signed physical initial temperature was accepted");
    rejects([&] { integrate_surface_energy_step(system, {300.0}, {-1.0}, options, SurfaceEnergyTimeMethod::tr_bdf2); },
        "signed physical shortwave was accepted");
    rejects([&] { integrate_surface_energy_step(system, {300.0}, {0.0}, options, static_cast<SurfaceEnergyTimeMethod>(99)); },
        "unknown time method was accepted");
    options.duration_seconds = std::numeric_limits<double>::denorm_min();
    rejects([&] { integrate_surface_energy_step(system, {300.0}, {0.0}, options, SurfaceEnergyTimeMethod::tr_bdf2); },
        "unrepresentable stage duration was silently floored");
    options.duration_seconds = 1.0e6;
    options.maximum_newton_iterations = 1;
    rejects([&] { integrate_surface_energy_step(system, {300.0}, {0.0}, options, SurfaceEnergyTimeMethod::tr_bdf2); },
        "unconverged implicit stage was published");
}

}  // namespace

int main() {
    try {
        equilibrium_and_disconnected_exact_zero();
        constant_heating_has_method_consistent_moments();
        weighted_flux_ledger_is_independently_replayable();
        analytic_radiative_cooling_is_second_order();
        analytic_diffusion_is_second_order();
        endpoint_error_bound_and_noncontractive_positive_step();
        invalid_or_nonpositive_stages_fail_explicitly();
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
    return 0;
}
