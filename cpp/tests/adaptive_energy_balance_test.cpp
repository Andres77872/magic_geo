#include "engine/adaptive_energy_balance.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <iostream>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {
using namespace magic_geo::detail;
constexpr double sigma = 5.670374419e-8;
constexpr double pi = 3.1415926535897932384626433832795;
constexpr double year_seconds = 31557600.0;
constexpr double month_seconds = year_seconds / 12.0;

void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

void close(double actual, double expected, double tolerance, const char* message) {
    if (!std::isfinite(actual) || !std::isfinite(expected) || std::abs(actual - expected) > tolerance) {
        std::cerr << message << ": " << actual << " versus " << expected << '\n';
        throw std::runtime_error(message);
    }
}

template <typename Function>
void must_fail(Function function, const char* message) {
    bool failed = false;
    try { function(); }
    catch (const std::exception&) { failed = true; }
    require(failed, message);
}

SurfaceEnergySystem coupled_columns() {
    return SurfaceEnergySystem({{1.0e12, 4.0e6, 0.9}, {3.0e12, 2.1e8, 0.6}}, {{0, 1, 0.3e12}});
}

std::vector<SurfaceEnergyForcingInterval> constant_forcing(const std::vector<double>& flux) {
    std::vector<SurfaceEnergyForcingInterval> result;
    for (int month = 0; month < 12; ++month) result.push_back({month, month_seconds, flux});
    return result;
}

std::vector<SurfaceEnergyForcingInterval> pulse_forcing() {
    std::vector<SurfaceEnergyForcingInterval> result;
    for (int month = 0; month < 12; ++month) {
        if (month == 5) {
            // A sharp source change exactly at a month boundary, followed by
            // a short bright interval. Thermal refinement must preserve both
            // parent fluences, rather than interpolating or smoothing them.
            result.push_back({month, month_seconds / 256.0, {10000.0, 300.0}});
            result.push_back({month, month_seconds * (255.0 / 256.0), {50.0, 180.0}});
        } else {
            result.push_back({month, month_seconds, {80.0, 240.0}});
        }
    }
    return result;
}

std::vector<SurfaceEnergyForcingInterval> smooth_forcing() {
    std::vector<SurfaceEnergyForcingInterval> result;
    for (int month = 0; month < 12; ++month) {
        const double start = 2.0 * pi * month / 12.0;
        const double end = 2.0 * pi * (month + 1) / 12.0;
        const double mean_cosine = (std::sin(end) - std::sin(start)) / (end - start);
        result.push_back({month, month_seconds, {200.0 + 120.0 * mean_cosine, 240.0 - 80.0 * mean_cosine}});
    }
    return result;
}

AdaptivePeriodicSurfaceEnergyOptions options_for(SurfaceEnergyTimeMethod method, double tolerance = 0.002) {
    AdaptivePeriodicSurfaceEnergyOptions options;
    options.periodic.time_method = method;
    options.periodic.phase_tolerance_k = 1.0e-7;
    options.periodic.annual_flux_tolerance_w_m2 = 1.0e-7;
    options.periodic.step.absolute_tolerance_w_m2 = 1.0e-9;
    options.periodic.step.relative_tolerance = 1.0e-13;
    options.local_absolute_tolerance_k = tolerance;
    options.local_relative_tolerance = 0.0;
    options.required_monthly_refinement_confirmations = 0;
    return options;
}

std::size_t accepted_steps(const AdaptivePeriodicSurfaceEnergyYear& result) {
    return std::accumulate(result.thermal_subdivisions.begin(), result.thermal_subdivisions.end(), std::size_t{0});
}

void assert_same_physical_year(const PeriodicSurfaceEnergyYear& left, const PeriodicSurfaceEnergyYear& right) {
    require(left.duration_seconds == right.duration_seconds &&
        left.initial_temperature_k == right.initial_temperature_k && left.final_temperature_k == right.final_temperature_k,
        "replaying the accepted partition changed phase-boundary temperatures");
    require(left.annual_net_heating_w_m2 == right.annual_net_heating_w_m2 &&
        left.annual_flux_tolerance_w_m2 == right.annual_flux_tolerance_w_m2 &&
        left.global_annual_net_heating_w == right.global_annual_net_heating_w,
        "rejected trials leaked into the accepted annual ledger or tolerance");
    for (std::size_t index = 0; index < 12; ++index) {
        const auto& a = left.months[index];
        const auto& b = right.months[index];
        require(a.duration_seconds == b.duration_seconds && a.initial_temperature_k == b.initial_temperature_k &&
            a.final_temperature_k == b.final_temperature_k && a.mean_temperature_k == b.mean_temperature_k &&
            a.mean_fourth_power_temperature_k4 == b.mean_fourth_power_temperature_k4 &&
            a.absorbed_shortwave_w_m2 == b.absorbed_shortwave_w_m2 &&
            a.emitted_longwave_w_m2 == b.emitted_longwave_w_m2 &&
            a.horizontal_heat_convergence_w_m2 == b.horizontal_heat_convergence_w_m2 &&
            a.heat_storage_tendency_w_m2 == b.heat_storage_tendency_w_m2 &&
            a.balance_residual_w_m2 == b.balance_residual_w_m2 && a.balance_tolerance_w_m2 == b.balance_tolerance_w_m2,
            "rejected trials or an unfrozen method changed the accepted monthly ledger");
    }
}

void exact_equilibria_preserve_the_minimum_partition() {
    const SurfaceEnergySystem system({{1.0e12, 4.0e6, 0.96}}, {});
    const auto forcing = constant_forcing({0.96 * sigma * std::pow(300.0, 4)});
    for (const auto method : {SurfaceEnergyTimeMethod::backward_euler, SurfaceEnergyTimeMethod::tr_bdf2}) {
        const auto result = solve_adaptive_periodic_surface_energy_balance(system, forcing, {300.0}, options_for(method));
        require(result.thermal_subdivisions == std::vector<std::size_t>(12, 2), "equilibrium changed the minimum paired partition");
        require(result.partition_refinements == 0, "an exact equilibrium required thermal refinement");
        require(result.year.integration_step_count == 24, "physical steps were confused with estimator or implicit-stage work");
        require(result.year.total_integration_steps == 24 && result.total_step_attempts == 60 &&
            result.estimator_trials == 12 && result.total_periodic_year_evaluations == 1,
            "equilibrium work counters omit or double-count shooting and estimator steps");
        require(result.maximum_local_error_ratio <= 1.0 && result.maximum_numerical_error_ratio <= 0.1,
            "an accepted year exceeds its temporal or numerical error budget");
        for (const auto& month : result.year.months) close(month.mean_temperature_k[0], 300.0, 1.0e-11, "adaptive equilibrium acquired a thermal bias");
        const auto dark = solve_adaptive_periodic_surface_energy_balance(system, constant_forcing({0.0}), {300.0}, options_for(method));
        require(dark.year.initial_temperature_k[0] == 0.0 && dark.year.final_temperature_k[0] == 0.0,
            "adaptive uncertainty or positivity handling changed the exact dark periodic root");
    }
}

void tightened_solver_options_replay_the_accepted_year() {
    const SurfaceEnergySystem system({{1.0e12, 4.0e6, 0.96}}, {});
    const auto forcing = constant_forcing({0.96 * sigma * std::pow(300.0, 4)});
    for (const auto method : {SurfaceEnergyTimeMethod::backward_euler, SurfaceEnergyTimeMethod::tr_bdf2}) {
        auto options = options_for(method, 1.0e-4);
        // The initial residual fits the loose nonlinear flux tolerance, but
        // its independently measured endpoint uncertainty exceeds the temporal
        // budget. The wrapper must tighten the solve before publishing a year.
        options.periodic.step.absolute_tolerance_w_m2 = 0.01;
        const auto result = solve_adaptive_periodic_surface_energy_balance(system, forcing, {300.0001}, options);
        require(result.solver_tightenings > 0 &&
            result.accepted_periodic_options.step.absolute_tolerance_w_m2 < options.periodic.step.absolute_tolerance_w_m2,
            "endpoint uncertainty was hidden instead of tightening the nonlinear solve");
        const auto replay = solve_periodic_surface_energy_balance(system, forcing, result.year.initial_temperature_k,
            result.accepted_periodic_options);
        assert_same_physical_year(result.year, replay);
    }
}

void rejected_trials_preserve_fluence_and_replay() {
    const auto system = coupled_columns();
    const auto forcing = pulse_forcing();
    for (const auto method : {SurfaceEnergyTimeMethod::backward_euler, SurfaceEnergyTimeMethod::tr_bdf2}) {
        const auto options = options_for(method);
        const auto result = solve_adaptive_periodic_surface_energy_balance(system, forcing, {260.0, 290.0}, options);
        require(result.partition_refinements > 0 && result.failed_estimator_trials > 0,
            "sharp-pulse regression did not exercise rejected estimator trials");
        require(result.thermal_subdivisions.size() == forcing.size(), "thermal partition lost a parent forcing interval");
        for (const auto count : result.thermal_subdivisions) require(count >= 2 && (count & (count - 1)) == 0,
            "accepted physical subdivisions are not paired powers of two");
        require(result.year.integration_step_count == accepted_steps(result), "accepted step count includes discarded estimator work");
        require(result.estimator_trials >= accepted_steps(result) / 2,
            "the final accepted partition was not checked by paired step doubling");
        require(result.total_periodic_year_evaluations >= static_cast<std::size_t>(result.year.year_evaluations),
            "total shooting work omits the final periodic solve");
        require(result.maximum_local_error_ratio <= 1.0 &&
            result.maximum_numerical_error_ratio <= options.maximum_numerical_error_fraction,
            "adaptive acceptance exceeded a declared error budget");
        for (int index = 0; index < 12; ++index) {
            const auto& month = result.year.months[static_cast<std::size_t>(index)];
            close(month.duration_seconds, month_seconds, 1.0e-8, "thermal partition moved a month boundary");
            long double transport_w = 0.0L;
            for (std::size_t i = 0; i < system.columns().size(); ++i) {
                const auto& column = system.columns()[i];
                long double fluence = 0.0L;
                for (const auto& interval : forcing) if (interval.month_index == index) {
                    fluence += static_cast<long double>(interval.duration_seconds) * interval.absorbed_shortwave_w_m2[i];
                }
                close(month.absorbed_shortwave_w_m2[i], static_cast<double>(fluence / month_seconds), 1.0e-10,
                    "rejected or refined thermal steps changed prescribed monthly fluence");
                close(month.emitted_longwave_w_m2[i], column.longwave_emissivity * sigma * month.mean_fourth_power_temperature_k4[i],
                    1.0e-9, "adaptive radiation uses a different quadrature from the fourth temperature moment");
                require(month.mean_fourth_power_temperature_k4[i] >= std::pow(month.mean_temperature_k[i], 4) * (1.0 - 1.0e-12),
                    "accepted temperature moments violate positive-weight quadrature");
                const double net = month.absorbed_shortwave_w_m2[i] - month.emitted_longwave_w_m2[i] + month.horizontal_heat_convergence_w_m2[i];
                close(month.heat_storage_tendency_w_m2[i], column.heat_capacity_j_m2_k *
                    (month.final_temperature_k[i] - month.initial_temperature_k[i]) / month_seconds, 1.0e-8,
                    "accepted storage fails to telescope across refined steps");
                close(month.heat_storage_tendency_w_m2[i] - net, month.balance_residual_w_m2[i], 1.0e-9,
                    "accepted residual is not the physical monthly energy ledger");
                require(std::abs(month.balance_residual_w_m2[i]) <= month.balance_tolerance_w_m2[i],
                    "accepted monthly ledger exceeds its propagated solver tolerance");
                transport_w += column.area_m2 * static_cast<long double>(month.horizontal_heat_convergence_w_m2[i]);
            }
            close(static_cast<double>(transport_w), 0.0, 0.1, "adaptive coupled steps created globally integrated transport energy");
        }
        const auto replay_options = result.accepted_periodic_options;
        require(replay_options.thermal_subdivisions == result.thermal_subdivisions && replay_options.time_method == method,
            "exported replay options do not describe the accepted partition and method");
        const auto replay = solve_periodic_surface_energy_balance(system, forcing, result.year.initial_temperature_k, replay_options);
        require(replay.year_evaluations == 1, "accepted fine-map state is not periodic on the exported partition");
        assert_same_physical_year(result.year, replay);
    }
}

double monthly_temperature_distance(const PeriodicSurfaceEnergyYear& a, const PeriodicSurfaceEnergyYear& b) {
    double maximum = 0.0;
    for (std::size_t month = 0; month < 12; ++month) {
        for (std::size_t i = 0; i < a.months[month].mean_temperature_k.size(); ++i) {
            maximum = std::max(maximum, std::abs(a.months[month].mean_temperature_k[i] - b.months[month].mean_temperature_k[i]));
        }
    }
    return maximum;
}

void tighter_local_tolerance_improves_monthly_refinement() {
    const auto system = coupled_columns();
    const auto forcing = smooth_forcing();
    for (const auto method : {SurfaceEnergyTimeMethod::backward_euler, SurfaceEnergyTimeMethod::tr_bdf2}) {
        const auto loose = solve_adaptive_periodic_surface_energy_balance(system, forcing, {280.0, 290.0}, options_for(method, 0.02));
        const auto tight_options = options_for(method, 0.0002);
        const auto tight = solve_adaptive_periodic_surface_energy_balance(system, forcing, {280.0, 290.0}, tight_options);
        require(accepted_steps(tight) > accepted_steps(loose), "tighter temporal tolerance did not refine the seasonal solution");
        auto reference_options = tight.accepted_periodic_options;
        for (auto& count : reference_options.thermal_subdivisions) count *= 2;
        const auto reference = solve_periodic_surface_energy_balance(system, forcing, tight.year.initial_temperature_k, reference_options);
        require(monthly_temperature_distance(tight.year, reference) < 0.7 * monthly_temperature_distance(loose.year, reference),
            "smaller local error failed to improve independently refined monthly means");
        // Re-solving the identical final grid must recover its root from an
        // independent starting guess. Grid selection is not imposed climate.
        const auto fixed_options = tight.accepted_periodic_options;
        const auto other_initial = solve_periodic_surface_energy_balance(system, forcing, {310.0, 270.0}, fixed_options);
        require(monthly_temperature_distance(tight.year, other_initial) < 2.0e-6,
            "initial guess changes the converged climate on the accepted fixed partition");
    }
}

void work_and_refinement_exhaustion_are_explicit() {
    const auto system = coupled_columns();
    const auto forcing = pulse_forcing();
    auto options = options_for(SurfaceEnergyTimeMethod::backward_euler, 1.0e-8);
    options.maximum_accepted_steps_per_year = forcing.size() * 2;
    must_fail([&] { solve_adaptive_periodic_surface_energy_balance(system, forcing, {260.0, 290.0}, options); },
        "a thermal work budget silently returned an inaccurate coarse cycle");
    options.maximum_accepted_steps_per_year = 1'000'000;
    options.maximum_partition_refinements = 1;
    must_fail([&] { solve_adaptive_periodic_surface_energy_balance(system, forcing, {260.0, 290.0}, options); },
        "exhausted partition refinements silently returned an unchecked cycle");
    options = options_for(SurfaceEnergyTimeMethod::backward_euler);
    options.maximum_total_step_attempts = 1;
    must_fail([&] { solve_adaptive_periodic_surface_energy_balance(system, forcing, {260.0, 290.0}, options); },
        "total work exhaustion allowed uncounted shooting or estimator work");
    const SurfaceEnergySystem equilibrium({{1.0, 4.0e6, 0.96}}, {});
    const auto constant = constant_forcing({0.96 * sigma * std::pow(300.0, 4)});
    options.maximum_total_step_attempts = 60;
    const auto exact_budget = solve_adaptive_periodic_surface_energy_balance(equilibrium, constant, {300.0}, options);
    require(exact_budget.total_step_attempts == 60, "an exact work budget was rejected or miscounted");
    options.maximum_total_step_attempts = 59;
    must_fail([&] { solve_adaptive_periodic_surface_energy_balance(equilibrium, constant, {300.0}, options); },
        "estimator work continued past the last permitted physical step");
}

void monthly_accuracy_requires_reconverged_refinements() {
    const auto system = coupled_columns();
    const auto forcing = smooth_forcing();
    auto options = options_for(SurfaceEnergyTimeMethod::backward_euler, 0.01);
    options.required_monthly_refinement_confirmations = 2;
    options.monthly_relative_tolerance = 0.0;
    const auto result = solve_adaptive_periodic_surface_energy_balance(system, forcing, {280.0, 290.0}, options);
    require(result.monthly_refinement_confirmations >= 2, "monthly accuracy was accepted without successive confirmations");
    require(result.maximum_monthly_temperature_change_k <= options.monthly_temperature_tolerance_k &&
        result.maximum_monthly_flux_change_w_m2 <= options.monthly_flux_tolerance_w_m2,
        "accepted monthly accuracy metrics exceed their declared tolerances");
    auto coarse_options = result.accepted_periodic_options;
    for (auto& count : coarse_options.thermal_subdivisions) {
        require(count >= 4, "monthly refinement confirmation did not produce a finer accepted partition");
        count /= 2;
    }
    const auto coarse = solve_periodic_surface_energy_balance(system, forcing, result.year.initial_temperature_k, coarse_options);
    require(monthly_temperature_distance(result.year, coarse) <= options.monthly_temperature_tolerance_k,
        "independent re-convergence on the previous partition fails the monthly temperature gate");
    for (std::size_t month = 0; month < 12; ++month) {
        const auto& a = result.year.months[month];
        const auto& b = coarse.months[month];
        for (std::size_t i = 0; i < system.columns().size(); ++i) {
            close(std::sqrt(std::sqrt(a.mean_fourth_power_temperature_k4[i])),
                std::sqrt(std::sqrt(b.mean_fourth_power_temperature_k4[i])), options.monthly_temperature_tolerance_k,
                "independent fourth-moment refinement fails the monthly temperature gate");
            close(a.emitted_longwave_w_m2[i], b.emitted_longwave_w_m2[i], options.monthly_flux_tolerance_w_m2,
                "independent longwave refinement fails the monthly flux gate");
            close(a.horizontal_heat_convergence_w_m2[i], b.horizontal_heat_convergence_w_m2[i], options.monthly_flux_tolerance_w_m2,
                "independent transport refinement fails the monthly flux gate");
        }
    }
}

void unattainable_numerical_precision_is_explicit() {
    const SurfaceEnergySystem system({{1.0e12, 2.0475492046755865e11, 0.96}}, {});
    const auto forcing = constant_forcing({0.96 * sigma * std::pow(300.0, 4)});
    for (const auto method : {SurfaceEnergyTimeMethod::backward_euler, SurfaceEnergyTimeMethod::tr_bdf2}) {
        auto options = options_for(method, 1.0e-20);
        must_fail([&] { solve_adaptive_periodic_surface_energy_balance(system, forcing, {300.0}, options); },
            "sub-ulp temporal accuracy was reported despite endpoint numerical uncertainty");
    }
}

void malformed_adaptive_inputs_fail() {
    const SurfaceEnergySystem system({{1.0, 4.0e6, 0.96}}, {});
    const auto forcing = constant_forcing({240.0});
    const auto baseline = options_for(SurfaceEnergyTimeMethod::backward_euler);
    auto reject = [&](const AdaptivePeriodicSurfaceEnergyOptions& options) {
        must_fail([&] { solve_adaptive_periodic_surface_energy_balance(system, forcing, {280.0}, options); },
            "malformed adaptive options were accepted");
    };
    auto options = baseline; options.local_absolute_tolerance_k = 0.0; reject(options);
    options = baseline; options.local_absolute_tolerance_k = std::numeric_limits<double>::quiet_NaN(); reject(options);
    options = baseline; options.local_relative_tolerance = -1.0; reject(options);
    options = baseline; options.local_relative_tolerance = std::numeric_limits<double>::max(); reject(options);
    options = baseline; options.maximum_numerical_error_fraction = 0.0; reject(options);
    options = baseline; options.maximum_accepted_steps_per_year = 0; reject(options);
    options = baseline; options.maximum_total_step_attempts = 0; reject(options);
    options = baseline; options.maximum_partition_refinements = -1; reject(options);
    options = baseline; options.required_monthly_refinement_confirmations = -1; reject(options);
    options = baseline; options.monthly_temperature_tolerance_k = 0.0; reject(options);
    options = baseline; options.required_monthly_refinement_confirmations = 2;
    options.monthly_relative_tolerance = std::numeric_limits<double>::max(); reject(options);
    options = baseline; options.periodic.thermal_subdivisions.assign(12, 3); reject(options);
    options = baseline; options.periodic.thermal_subdivisions.assign(11, 2); reject(options);
}
}  // namespace

int main() {
    int failures = 0;
    const std::array<std::pair<const char*, void (*)()>, 8> tests{{
        {"exact equilibria", exact_equilibria_preserve_the_minimum_partition},
        {"rejected trials, fluence and replay", rejected_trials_preserve_fluence_and_replay},
        {"monthly refinement and initial guess", tighter_local_tolerance_improves_monthly_refinement},
        {"work and refinement exhaustion", work_and_refinement_exhaustion_are_explicit},
        {"reconverged monthly accuracy", monthly_accuracy_requires_reconverged_refinements},
        {"unattainable precision", unattainable_numerical_precision_is_explicit},
        {"tightened solver replay", tightened_solver_options_replay_the_accepted_year},
        {"invalid options", malformed_adaptive_inputs_fail},
    }};
    for (const auto& test : tests) {
        try { test.second(); }
        catch (const std::exception& error) { std::cerr << test.first << ": " << error.what() << '\n'; ++failures; }
    }
    return failures == 0 ? 0 : 1;
}
