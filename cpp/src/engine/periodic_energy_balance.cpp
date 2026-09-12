#include "periodic_energy_balance.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <utility>

namespace magic_geo::detail {
namespace {
constexpr double sigma = 5.670374419e-8;

struct MonthAccumulator {
    std::vector<long double> temperature, fourth_power, absorbed, emitted, transport, storage, residual, tolerance;

    explicit MonthAccumulator(std::size_t count) : temperature(count), fourth_power(count), absorbed(count), emitted(count),
        transport(count), storage(count), residual(count), tolerance(count) {}
};

struct Cycle {
    PeriodicSurfaceEnergyYear year;
    std::vector<double> mean_restoring;
    long double merit = 0.0L;
    bool converged = true;
};

std::vector<double> divide(const std::vector<long double>& integrated, double duration) {
    std::vector<double> mean;
    mean.reserve(integrated.size());
    for (const auto value : integrated) {
        const double result = static_cast<double>(value / duration);
        if (!std::isfinite(result)) {
            throw std::runtime_error("periodic energy integral is not representable");
        }
        mean.push_back(result);
    }
    return mean;
}

Cycle integrate_year(
    const SurfaceEnergySystem& system,
    const std::vector<SurfaceEnergyForcingInterval>& intervals,
    const std::array<double, 12>& month_durations,
    double year_duration,
    const std::vector<double>& initial,
    const PeriodicSurfaceEnergyOptions& options,
    std::size_t& total_step_attempts
) {
    const auto& columns = system.columns();
    const auto count = columns.size();
    Cycle cycle;
    auto& year = cycle.year;
    year.duration_seconds = year_duration;
    year.initial_temperature_k = initial;
    std::vector<MonthAccumulator> accumulators;
    for (std::size_t month = 0; month < 12; ++month) {
        accumulators.emplace_back(count);
        year.months[month].duration_seconds = month_durations[month];
    }
    std::vector<long double> restoring_integral(count, 0.0L);
    std::vector<double> temperature = initial;
    for (std::size_t interval_index = 0; interval_index < intervals.size(); ++interval_index) {
        const auto& interval = intervals[interval_index];
        auto& month = year.months[interval.month_index];
        auto& integral = accumulators[interval.month_index];
        if (month.initial_temperature_k.empty()) {
            month.initial_temperature_k = temperature;
        }
        auto step_options = options.step;
        const std::size_t subdivisions = options.thermal_subdivisions.empty() ? 1 : options.thermal_subdivisions[interval_index];
        step_options.duration_seconds = interval.duration_seconds / static_cast<double>(subdivisions);
        for (std::size_t substep = 0; substep < subdivisions; ++substep) {
            if (total_step_attempts >= options.maximum_integration_steps) {
                throw PeriodicSurfaceEnergyWorkLimit(total_step_attempts);
            }
            ++total_step_attempts;
            IntegratedSurfaceEnergyStep integrated;
            try {
                integrated = integrate_surface_energy_step(system, temperature, interval.absorbed_shortwave_w_m2, step_options, options.time_method);
            } catch (const std::runtime_error& error) {
                throw PeriodicSurfaceEnergyStepError(interval_index, substep, error.what(), total_step_attempts);
            }
            auto& step = integrated.budget;
            ++year.integration_step_count;
            year.year_newton_iterations += step.newton_iterations;
            year.year_linear_iterations += step.linear_iterations;
            year.maximum_step_balance_residual_w_m2 = std::max(
                year.maximum_step_balance_residual_w_m2, step.maximum_balance_residual_w_m2
            );
            const long double duration = step_options.duration_seconds;
            for (std::size_t i = 0; i < count; ++i) {
                integral.temperature[i] += duration * integrated.mean_temperature_k[i];
                integral.fourth_power[i] += duration * integrated.mean_fourth_power_temperature_k4[i];
                integral.absorbed[i] += duration * interval.absorbed_shortwave_w_m2[i];
                integral.emitted[i] += duration * step.emitted_longwave_w_m2[i];
                integral.transport[i] += duration * step.horizontal_heat_convergence_w_m2[i];
                integral.storage[i] += duration * step.heat_storage_tendency_w_m2[i];
                integral.residual[i] += duration * step.balance_residual_w_m2[i];
                integral.tolerance[i] += duration * step.balance_tolerance_w_m2[i];
                restoring_integral[i] += duration * 4.0L * columns[i].longwave_emissivity * sigma * integrated.mean_cubic_temperature_k3[i];
            }
            temperature = std::move(step.temperature_k);
            month.final_temperature_k = temperature;
        }
    }
    for (std::size_t month_index = 0; month_index < 12; ++month_index) {
        auto& month = year.months[month_index];
        const auto& integral = accumulators[month_index];
        const double duration = month.duration_seconds;
        month.mean_temperature_k = divide(integral.temperature, duration);
        month.mean_fourth_power_temperature_k4 = divide(integral.fourth_power, duration);
        month.absorbed_shortwave_w_m2 = divide(integral.absorbed, duration);
        month.emitted_longwave_w_m2 = divide(integral.emitted, duration);
        month.horizontal_heat_convergence_w_m2 = divide(integral.transport, duration);
        month.heat_storage_tendency_w_m2 = divide(integral.storage, duration);
        month.balance_residual_w_m2 = divide(integral.residual, duration);
        month.balance_tolerance_w_m2 = divide(integral.tolerance, duration);
    }
    year.final_temperature_k = temperature;
    year.annual_net_heating_w_m2.resize(count);
    year.annual_flux_tolerance_w_m2.resize(count);
    cycle.mean_restoring = divide(restoring_integral, year_duration);
    long double global_net_heating = 0.0L;
    for (std::size_t i = 0; i < count; ++i) {
        long double net = 0.0L, mean_absorbed = 0.0L, mean_emitted = 0.0L, transport = 0.0L, solve_tolerance = 0.0L;
        for (const auto& integral : accumulators) {
            // Accumulate the physical fluxes directly: endpoint temperature
            // subtraction alone can hide heating in a huge-capacity column.
            net += integral.absorbed[i] - integral.emitted[i] + integral.transport[i];
            mean_absorbed += integral.absorbed[i];
            mean_emitted += integral.emitted[i];
            transport += integral.transport[i];
            solve_tolerance += integral.tolerance[i];
        }
        net /= year_duration;
        const double scale = static_cast<double>(std::max({1.0L, mean_absorbed / year_duration,
            mean_emitted / year_duration, std::abs(transport) / year_duration}));
        const double flux_tolerance = options.annual_flux_tolerance_w_m2 + options.relative_tolerance * scale +
            static_cast<double>(solve_tolerance / year_duration);
        const double phase_difference = temperature[i] - initial[i];
        const double phase_tolerance = options.phase_tolerance_k + options.relative_tolerance * std::max(temperature[i], initial[i]);
        if (!std::isfinite(net) || !std::isfinite(flux_tolerance) || !std::isfinite(phase_tolerance)) {
            throw std::runtime_error("periodic energy convergence metric is not representable");
        }
        year.annual_net_heating_w_m2[i] = static_cast<double>(net);
        year.annual_flux_tolerance_w_m2[i] = flux_tolerance;
        year.maximum_phase_difference_k = std::max(year.maximum_phase_difference_k, std::abs(phase_difference));
        year.maximum_annual_net_heating_w_m2 = std::max(year.maximum_annual_net_heating_w_m2, static_cast<double>(std::abs(net)));
        cycle.converged = cycle.converged && std::abs(net) <= flux_tolerance && std::abs(phase_difference) <= phase_tolerance;
        // The period-map preconditioner is self-adjoint in the area*capacity
        // temperature norm. Its flux counterpart has area/capacity weights.
        // Per-cell tolerance normalization would lose this property and can
        // reject every positive step for a perfectly stable mixed-C system.
        const long double capacity = columns[i].heat_capacity_j_m2_k;
        const long double phase_flux = capacity * phase_difference / year_duration;
        cycle.merit += static_cast<long double>(columns[i].area_m2) / capacity *
            (net * net + phase_flux * phase_flux);
        global_net_heating += columns[i].area_m2 * net;
    }
    year.global_annual_net_heating_w = static_cast<double>(global_net_heating);
    if (!std::isfinite(year.global_annual_net_heating_w)) {
        throw std::runtime_error("periodic global energy residual is not representable");
    }
    return cycle;
}

}  // namespace

PeriodicSurfaceEnergyYear solve_periodic_surface_energy_balance(
    const SurfaceEnergySystem& system,
    const std::vector<SurfaceEnergyForcingInterval>& intervals,
    const std::vector<double>& initial_temperature_k,
    const PeriodicSurfaceEnergyOptions& options
) {
    const auto count = system.columns().size();
    if (intervals.empty() || initial_temperature_k.size() != count ||
        !std::isfinite(options.phase_tolerance_k) || options.phase_tolerance_k <= 0.0 ||
        !std::isfinite(options.annual_flux_tolerance_w_m2) || options.annual_flux_tolerance_w_m2 <= 0.0 ||
        !std::isfinite(options.relative_tolerance) || options.relative_tolerance < 0.0 ||
        options.maximum_periodic_iterations < 1 || options.maximum_backtracks < 1 || options.maximum_integration_steps == 0) {
        throw std::invalid_argument("invalid periodic energy inputs or tolerances");
    }
    if ((options.time_method != SurfaceEnergyTimeMethod::backward_euler && options.time_method != SurfaceEnergyTimeMethod::tr_bdf2) ||
        (!options.thermal_subdivisions.empty() && options.thermal_subdivisions.size() != intervals.size())) {
        throw std::invalid_argument("invalid periodic time method or thermal partition dimensions");
    }
    if (!options.thermal_subdivisions.empty()) {
        for (std::size_t i = 0; i < intervals.size(); ++i) {
            const auto count_steps = options.thermal_subdivisions[i];
            if (count_steps == 0 || (count_steps & (count_steps - 1)) != 0) {
                throw std::invalid_argument("periodic thermal subdivisions must be positive powers of two");
            }
            const double duration = intervals[i].duration_seconds / static_cast<double>(count_steps);
            if (!(duration > 0.0) || duration * static_cast<double>(count_steps) != intervals[i].duration_seconds) {
                throw std::invalid_argument("periodic thermal subdivision cannot preserve the parent duration");
            }
        }
    }
    for (std::size_t i = 0; i < count; ++i) {
        if (!std::isfinite(initial_temperature_k[i]) || initial_temperature_k[i] < 0.0 ||
            system.columns()[i].longwave_emissivity <= 0.0) {
            throw std::invalid_argument("periodic energy columns require nonnegative temperature and positive emissivity");
        }
    }
    std::array<double, 12> month_durations{};
    std::array<long double, 12> month_duration_sums{};
    int previous_month = 0;
    for (const auto& interval : intervals) {
        if (interval.month_index < previous_month || interval.month_index > previous_month + 1 || interval.month_index >= 12 ||
            !std::isfinite(interval.duration_seconds) || interval.duration_seconds <= 0.0 || interval.absorbed_shortwave_w_m2.size() != count) {
            throw std::invalid_argument("periodic forcing must contain ordered contiguous positive-duration months");
        }
        for (const double flux : interval.absorbed_shortwave_w_m2) {
            if (!std::isfinite(flux) || flux < 0.0) {
                throw std::invalid_argument("periodic absorbed shortwave must be finite and nonnegative");
            }
        }
        month_duration_sums[interval.month_index] += interval.duration_seconds;
        previous_month = interval.month_index;
    }
    long double year_sum = 0.0L;
    for (std::size_t month = 0; month < 12; ++month) {
        month_durations[month] = static_cast<double>(month_duration_sums[month]);
        year_sum += month_duration_sums[month];
    }
    const double year_duration = static_cast<double>(year_sum);
    if (!std::isfinite(year_duration) || year_duration <= 0.0) {
        throw std::invalid_argument("periodic year duration must be positive and finite");
    }
    for (const auto duration : month_durations) {
        if (std::abs(duration - year_duration / 12.0) > 1.0e-10 * year_duration / 12.0) {
            throw std::invalid_argument("periodic forcing must cover twelve equal-time months");
        }
    }
    std::vector<double> initial = initial_temperature_k;
    // A disconnected component with no absorbed energy has the exact unique
    // nonnegative periodic solution T=0: transport cancels globally and each
    // column emits positive radiation at T>0. Select that root analytically.
    // Otherwise radiative restoring tends to zero and an arbitrary warm guess
    // can appear phase-stationary before it has actually reached the dark root.
    std::vector<std::size_t> component(count);
    for (std::size_t i = 0; i < count; ++i) component[i] = i;
    auto find_component = [&](std::size_t index) {
        while (component[index] != index) {
            component[index] = component[component[index]];
            index = component[index];
        }
        return index;
    };
    for (const auto& edge : system.edges()) {
        component[find_component(edge.second_cell)] = find_component(edge.first_cell);
    }
    std::vector<bool> illuminated(count, false);
    for (const auto& interval : intervals) {
        for (std::size_t i = 0; i < count; ++i) {
            if (interval.absorbed_shortwave_w_m2[i] > 0.0) illuminated[find_component(i)] = true;
        }
    }
    for (std::size_t i = 0; i < count; ++i) {
        if (!illuminated[find_component(i)]) initial[i] = 0.0;
    }
    std::size_t total_step_attempts = 0;
    auto current = integrate_year(system, intervals, month_durations, year_duration, initial, options, total_step_attempts);
    int evaluations = 1;
    std::vector<double> previous_direction, previous_shift;
    for (int iteration = 0; iteration <= options.maximum_periodic_iterations; ++iteration) {
        if (current.converged) {
            current.year.periodic_iterations = iteration;
            current.year.year_evaluations = evaluations;
            current.year.total_integration_steps = total_step_attempts;
            return current.year;
        }
        if (iteration == options.maximum_periodic_iterations) {
            break;
        }
        auto restoring = current.mean_restoring;
        for (auto& value : restoring) {
            // A fully dark, exactly-zero column already has zero correction.
            // This only makes its preconditioner nonsingular; it adds no heat.
            if (value == 0.0) value = 1.0;
        }
        const auto correction = system.linear_response(restoring, current.year.annual_net_heating_w_m2, options.step.maximum_linear_iterations);
        std::vector<double> direction(count);
        for (std::size_t i = 0; i < count; ++i) {
            direction[i] = current.year.final_temperature_k[i] - initial[i] + correction[i];
        }
        double fraction = 1.0;
        if (!previous_direction.empty()) {
            // Scalar secant relaxation in the same area*capacity metric in
            // which the linear period correction is self-adjoint. Unlike a
            // fixed damping factor, it retains near-Newton updates for huge C.
            long double numerator = 0.0L, denominator = 0.0L;
            for (std::size_t i = 0; i < count; ++i) {
                const long double change = static_cast<long double>(direction[i]) - previous_direction[i];
                const long double mass = static_cast<long double>(system.columns()[i].area_m2) *
                    system.columns()[i].heat_capacity_j_m2_k;
                numerator -= mass * previous_shift[i] * change;
                denominator += mass * change * change;
            }
            if (denominator > 0.0L && std::isfinite(numerator) && std::isfinite(denominator)) {
                fraction = static_cast<double>(std::clamp(numerator / denominator, 0.5L, 1.0L));
            }
        }
        for (std::size_t i = 0; i < count; ++i) {
            if (direction[i] < 0.0) {
                fraction = std::min(fraction, -0.99 * initial[i] / direction[i]);
            }
        }
        bool accepted = false;
        for (int backtrack = 0; backtrack < options.maximum_backtracks; ++backtrack) {
            std::vector<double> trial(count);
            for (std::size_t i = 0; i < count; ++i) trial[i] = initial[i] + fraction * direction[i];
            ++evaluations;
            Cycle candidate;
            try {
                candidate = integrate_year(system, intervals, month_durations, year_duration, trial, options, total_step_attempts);
            } catch (const PeriodicSurfaceEnergyStepError&) {
                // A rejected shooting candidate must not alter the frozen
                // thermal partition or the last accepted secant history.
                fraction *= 0.5;
                continue;
            }
            if (candidate.converged || candidate.merit < current.merit * (1.0L - 1.0e-4L * fraction)) {
                previous_direction = direction;
                previous_shift.resize(count);
                for (std::size_t i = 0; i < count; ++i) previous_shift[i] = trial[i] - initial[i];
                initial = std::move(trial);
                current = std::move(candidate);
                accepted = true;
                break;
            }
            fraction *= 0.5;
        }
        if (!accepted) {
            throw std::runtime_error("periodic surface energy solve could not reduce its boundary residual");
        }
    }
    throw std::runtime_error("periodic surface energy solve did not converge");
}

}  // namespace magic_geo::detail
