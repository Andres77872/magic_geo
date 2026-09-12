#include "adaptive_energy_balance.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <optional>
#include <sstream>
#include <utility>

namespace magic_geo::detail {
namespace {

bool positive_finite(double value) { return std::isfinite(value) && value > 0.0; }

double fourth_root(double value) { return std::sqrt(std::sqrt(value)); }

double spacing(double value) {
    return std::nextafter(value, std::numeric_limits<double>::infinity()) - value;
}

double upward_bound(long double value) {
    if (value == 0.0L) return 0.0;
    const double rounded = std::nextafter(static_cast<double>(value), std::numeric_limits<double>::infinity());
    if (!std::isfinite(rounded) || rounded < 0.0) {
        throw std::runtime_error("adaptive numerical uncertainty bound is not representable");
    }
    return rounded;
}

std::runtime_error failure(const char* reason, const AdaptivePeriodicSurfaceEnergyYear& state) {
    std::ostringstream message;
    message << reason << "; local error ratio=" << state.maximum_local_error_ratio
            << ", numerical error ratio=" << state.maximum_numerical_error_ratio
            << ", monthly temperature change K=" << state.maximum_monthly_temperature_change_k
            << ", monthly flux change W/m2=" << state.maximum_monthly_flux_change_w_m2
            << ", attempted thermal steps=" << state.total_step_attempts;
    return std::runtime_error(message.str());
}

void check_partition_budget(
    const std::vector<std::size_t>& partition, const AdaptivePeriodicSurfaceEnergyOptions& options,
    const AdaptivePeriodicSurfaceEnergyYear& state
) {
    std::size_t total = 0;
    for (const auto count : partition) {
        if (count > options.maximum_accepted_steps_per_year - total) {
            throw failure("adaptive energy accepted-step budget exhausted", state);
        }
        total += count;
    }
}

bool compare_months(
    const PeriodicSurfaceEnergyYear& coarse, const PeriodicSurfaceEnergyYear& fine,
    const AdaptivePeriodicSurfaceEnergyOptions& options, AdaptivePeriodicSurfaceEnergyYear& result
) {
    result.maximum_monthly_temperature_change_k = 0.0;
    result.maximum_monthly_flux_change_w_m2 = 0.0;
    bool passed = true;
    for (std::size_t month = 0; month < 12; ++month) {
        const auto& a = coarse.months[month];
        const auto& b = fine.months[month];
        for (std::size_t i = 0; i < a.mean_temperature_k.size(); ++i) {
            const double temperature_change = std::max(std::abs(a.mean_temperature_k[i] - b.mean_temperature_k[i]),
                std::abs(fourth_root(a.mean_fourth_power_temperature_k4[i]) - fourth_root(b.mean_fourth_power_temperature_k4[i])));
            const double temperature_scale = std::max({a.mean_temperature_k[i], b.mean_temperature_k[i],
                fourth_root(a.mean_fourth_power_temperature_k4[i]), fourth_root(b.mean_fourth_power_temperature_k4[i])});
            const double temperature_tolerance = options.monthly_temperature_tolerance_k + options.monthly_relative_tolerance * temperature_scale;
            if (!positive_finite(temperature_tolerance)) {
                throw failure("adaptive monthly temperature tolerance is not representable", result);
            }
            result.maximum_monthly_temperature_change_k = std::max(result.maximum_monthly_temperature_change_k, temperature_change);
            passed = passed && temperature_change <= temperature_tolerance;
            for (const auto field : {&SurfaceEnergyMonth::emitted_longwave_w_m2, &SurfaceEnergyMonth::horizontal_heat_convergence_w_m2}) {
                const double first = (a.*field)[i], second = (b.*field)[i];
                const double change = std::abs(first - second);
                const double flux_tolerance = options.monthly_flux_tolerance_w_m2 +
                    options.monthly_relative_tolerance * std::max(std::abs(first), std::abs(second));
                if (!positive_finite(flux_tolerance)) {
                    throw failure("adaptive monthly flux tolerance is not representable", result);
                }
                result.maximum_monthly_flux_change_w_m2 = std::max(result.maximum_monthly_flux_change_w_m2, change);
                passed = passed && change <= flux_tolerance;
            }
        }
    }
    return passed;
}

}  // namespace

AdaptivePeriodicSurfaceEnergyYear solve_adaptive_periodic_surface_energy_balance(
    const SurfaceEnergySystem& system,
    const std::vector<SurfaceEnergyForcingInterval>& intervals,
    const std::vector<double>& initial_temperature_k,
    const AdaptivePeriodicSurfaceEnergyOptions& options
) {
    if (intervals.empty() || !positive_finite(options.local_absolute_tolerance_k) ||
        !std::isfinite(options.local_relative_tolerance) || options.local_relative_tolerance < 0.0 ||
        !positive_finite(options.maximum_numerical_error_fraction) || options.maximum_numerical_error_fraction > 1.0 ||
        !positive_finite(options.monthly_temperature_tolerance_k) || !positive_finite(options.monthly_flux_tolerance_w_m2) ||
        !std::isfinite(options.monthly_relative_tolerance) || options.monthly_relative_tolerance < 0.0 ||
        options.required_monthly_refinement_confirmations < 0 || options.maximum_partition_refinements < 0 ||
        options.maximum_solver_tightenings < 0 || options.maximum_accepted_steps_per_year == 0 || options.maximum_total_step_attempts == 0) {
        throw std::invalid_argument("invalid adaptive energy tolerances or work limits");
    }
    auto periodic = options.periodic;
    if (!periodic.thermal_subdivisions.empty() && periodic.thermal_subdivisions.size() != intervals.size()) {
        throw std::invalid_argument("adaptive thermal partition dimensions differ from forcing");
    }
    std::vector<std::size_t> partition = periodic.thermal_subdivisions;
    if (partition.empty()) partition.assign(intervals.size(), 2);
    for (auto& count : partition) {
        if (count == 0 || (count & (count - 1)) != 0) {
            throw std::invalid_argument("adaptive thermal partition requires positive powers of two");
        }
        count = std::max<std::size_t>(2, count);
    }
    AdaptivePeriodicSurfaceEnergyYear result;
    std::vector<double> initial = initial_temperature_k;
    std::optional<PeriodicSurfaceEnergyYear> monthly_reference;
    const bool second_order = periodic.time_method == SurfaceEnergyTimeMethod::tr_bdf2;
    const double estimator_divisor = second_order ? 3.0 : 1.0;
    // For equal TR-BDF2 halves under the same Q, stage elimination gives
    // U_fine <= (4*b/a-1)*U_first + U_second. A factor of one is unsafe even
    // when all stages are positive; BE alone is infinity-nonexpansive here.
    const long double first_half_amplification = second_order ? 1.0L + 2.0L * std::sqrt(2.0L) : 1.0L;
    for (;;) {
        check_partition_budget(partition, options, result);
        if (result.total_step_attempts >= options.maximum_total_step_attempts) {
            throw failure("adaptive energy total work budget exhausted", result);
        }
        periodic.thermal_subdivisions = partition;
        periodic.maximum_integration_steps = std::min(options.periodic.maximum_integration_steps,
            options.maximum_total_step_attempts - result.total_step_attempts);
        std::vector<bool> refine(intervals.size(), false);
        PeriodicSurfaceEnergyYear year;
        bool initial_step_failed = false;
        try {
            year = solve_periodic_surface_energy_balance(system, intervals, initial, periodic);
            result.total_step_attempts += year.total_integration_steps;
            result.total_periodic_year_evaluations += year.year_evaluations;
        } catch (const PeriodicSurfaceEnergyStepError& error) {
            result.total_step_attempts += error.attempted_steps;
            ++result.total_periodic_year_evaluations;
            refine.at(error.forcing_interval) = true;
            initial_step_failed = true;
        } catch (const PeriodicSurfaceEnergyWorkLimit& error) {
            result.total_step_attempts += error.attempted_steps;
            throw failure("adaptive energy total or periodic work budget exhausted", result);
        }
        bool precision_limited = false;
        bool local_passed = !initial_step_failed;
        if (!initial_step_failed) {
            result.maximum_local_error_ratio = 0.0;
            result.maximum_numerical_error_ratio = 0.0;
            result.maximum_endpoint_numerical_uncertainty_k = 0.0;
            std::vector<double> temperature = year.initial_temperature_k;
            auto trial_step = [&](const std::vector<double>& start, const SurfaceEnergyForcingInterval& interval, double duration) {
                if (result.total_step_attempts >= options.maximum_total_step_attempts) {
                    throw PeriodicSurfaceEnergyWorkLimit(result.total_step_attempts);
                }
                ++result.total_step_attempts;
                auto step_options = periodic.step;
                step_options.duration_seconds = duration;
                return integrate_surface_energy_step(system, start, interval.absorbed_shortwave_w_m2, step_options, periodic.time_method);
            };
            for (std::size_t index = 0; index < intervals.size(); ++index) {
                const auto& interval = intervals[index];
                const std::size_t pairs = partition[index] / 2;
                const double duration = interval.duration_seconds / static_cast<double>(pairs);
                for (std::size_t pair = 0; pair < pairs; ++pair) {
                    ++result.estimator_trials;
                    // These are exactly the accepted shooting map's two steps.
                    // Their trajectory continues even if the diagnostic full
                    // step fails or its error is too large.
                    const auto first = trial_step(temperature, interval, duration / 2.0);
                    const auto second = trial_step(first.budget.temperature_k, interval, duration / 2.0);
                    IntegratedSurfaceEnergyStep coarse;
                    bool coarse_valid = true;
                    try {
                        coarse = trial_step(temperature, interval, duration);
                    } catch (const PeriodicSurfaceEnergyWorkLimit&) { throw; }
                    catch (const std::runtime_error&) { coarse_valid = false; }
                    if (!coarse_valid) {
                        refine[index] = true;
                        local_passed = false;
                        ++result.failed_estimator_trials;
                        temperature = second.budget.temperature_k;
                        continue;
                    }
                    const double propagated_first_uncertainty = upward_bound(first_half_amplification * first.endpoint_numerical_uncertainty_k);
                    const double fine_uncertainty = upward_bound(static_cast<long double>(propagated_first_uncertainty) +
                        second.endpoint_numerical_uncertainty_k);
                    result.maximum_endpoint_numerical_uncertainty_k = std::max(result.maximum_endpoint_numerical_uncertainty_k, fine_uncertainty);
                    bool trial_passed = true;
                    if (second.minimum_stage_positivity_margin_k < propagated_first_uncertainty) {
                        // An uncertain exact intermediate stage needs a finer
                        // globally coupled step; positivity of a rounded stage
                        // alone is insufficient for the error comparison.
                        refine[index] = true;
                        trial_passed = false;
                    }
                    for (std::size_t i = 0; i < temperature.size(); ++i) {
                        const double fine_mean = 0.5 * first.mean_temperature_k[i] + 0.5 * second.mean_temperature_k[i];
                        const double fine_fourth_root = fourth_root(0.5 * first.mean_fourth_power_temperature_k4[i] +
                            0.5 * second.mean_fourth_power_temperature_k4[i]);
                        const double coarse_fourth_root = fourth_root(coarse.mean_fourth_power_temperature_k4[i]);
                        const double scale = std::max({1.0, temperature[i], second.budget.temperature_k[i], fine_mean, fine_fourth_root,
                            coarse.budget.temperature_k[i], coarse.mean_temperature_k[i], coarse_fourth_root});
                        const double tolerance = options.local_absolute_tolerance_k + options.local_relative_tolerance * scale;
                        if (!positive_finite(tolerance)) {
                            throw failure("adaptive local temperature tolerance is not representable", result);
                        }
                        // Moments are quadrature states: compare their local
                        // increments, normalized to the fixed export month.
                        // Comparing unweighted leaf means would turn BE's
                        // O(h²) local error test into an O(h) restriction.
                        const long double month_weight = static_cast<long double>(duration) / year.months[interval.month_index].duration_seconds;
                        const long double fine_fourth = 0.5L * first.mean_fourth_power_temperature_k4[i] +
                            0.5L * second.mean_fourth_power_temperature_k4[i];
                        const double mean_increment_error = static_cast<double>(month_weight * std::abs(fine_mean - coarse.mean_temperature_k[i]));
                        const double fourth_increment_error = static_cast<double>(month_weight *
                            std::abs(fine_fourth - coarse.mean_fourth_power_temperature_k4[i]) /
                            (4.0L * scale * scale * scale));
                        const double difference = std::max({std::abs(second.budget.temperature_k[i] - coarse.budget.temperature_k[i]),
                            mean_increment_error, fourth_increment_error}) / estimator_divisor;
                        const double numerical = upward_bound(static_cast<long double>(fine_uncertainty) +
                            (static_cast<long double>(fine_uncertainty) + coarse.endpoint_numerical_uncertainty_k + 16.0L * spacing(scale)) / estimator_divisor);
                        const double error_ratio = upward_bound((static_cast<long double>(difference) + numerical) / tolerance);
                        const double numerical_ratio = upward_bound(static_cast<long double>(numerical) / tolerance);
                        result.maximum_local_error_ratio = std::max(result.maximum_local_error_ratio, error_ratio);
                        result.maximum_numerical_error_ratio = std::max(result.maximum_numerical_error_ratio, numerical_ratio);
                        if (!std::isfinite(error_ratio) || !std::isfinite(numerical_ratio)) {
                            throw failure("adaptive temporal error is not representable", result);
                        }
                        if (numerical_ratio > options.maximum_numerical_error_fraction) {
                            precision_limited = true;
                            trial_passed = false;
                        }
                        if (error_ratio > 1.0) {
                            refine[index] = true;
                            trial_passed = false;
                        }
                    }
                    if (!trial_passed) {
                        local_passed = false;
                        ++result.failed_estimator_trials;
                    }
                    temperature = second.budget.temperature_k;
                }
            }
            if (temperature != year.final_temperature_k) {
                throw std::runtime_error("adaptive error check changed the frozen periodic map");
            }
            initial = year.initial_temperature_k;
        }
        if (precision_limited) {
            if (result.solver_tightenings >= options.maximum_solver_tightenings) {
                throw failure("adaptive energy precision limit exceeds requested temporal tolerance", result);
            }
            periodic.step.absolute_tolerance_w_m2 *= 0.01;
            periodic.step.relative_tolerance *= 0.01;
            if (!positive_finite(periodic.step.absolute_tolerance_w_m2)) {
                throw failure("adaptive energy solver tolerance is not representable", result);
            }
            ++result.solver_tightenings;
            monthly_reference.reset();
            result.monthly_refinement_confirmations = 0;
            continue;
        }
        if (local_passed) {
            if (monthly_reference) {
                if (compare_months(*monthly_reference, year, options, result)) ++result.monthly_refinement_confirmations;
                else result.monthly_refinement_confirmations = 0;
            }
            if (result.monthly_refinement_confirmations >= options.required_monthly_refinement_confirmations) {
                result.year = std::move(year);
                result.accepted_periodic_options = periodic;
                result.thermal_subdivisions = std::move(partition);
                return result;
            }
            monthly_reference = std::move(year);
            std::fill(refine.begin(), refine.end(), true);
        } else {
            monthly_reference.reset();
            result.monthly_refinement_confirmations = 0;
        }
        if (result.partition_refinements >= options.maximum_partition_refinements) {
            throw failure("adaptive energy thermal refinement budget exhausted", result);
        }
        for (std::size_t i = 0; i < partition.size(); ++i) {
            if (!refine[i]) continue;
            if (partition[i] > options.maximum_accepted_steps_per_year / 2) {
                throw failure("adaptive energy accepted-step budget exhausted", result);
            }
            partition[i] *= 2;
            const double child = intervals[i].duration_seconds / static_cast<double>(partition[i]);
            if (!(child > 0.0) || child * static_cast<double>(partition[i]) != intervals[i].duration_seconds) {
                throw failure("adaptive energy subdivision cannot preserve positive duration and fluence", result);
            }
        }
        ++result.partition_refinements;
    }
}

}  // namespace magic_geo::detail
