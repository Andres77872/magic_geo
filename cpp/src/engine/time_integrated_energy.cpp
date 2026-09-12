#include "time_integrated_energy.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <numbers>
#include <numeric>
#include <stdexcept>
#include <utility>

namespace magic_geo::detail {
namespace {

constexpr double sigma = 5.670374419e-8;
constexpr double inverse_sqrt_two = 1.0 / std::numbers::sqrt2;
constexpr double a = 1.0 - inverse_sqrt_two;
constexpr double b = 0.5 * inverse_sqrt_two;
constexpr double stage_ratio = b / a;
constexpr long double arithmetic_epsilon = std::numeric_limits<long double>::epsilon();

double representable(long double value, const char* context) {
    const double result = static_cast<double>(value);
    if (!std::isfinite(result)) throw std::runtime_error(context);
    return result;
}

double upper_bound(long double value, const char* context) {
    double result = representable(value, context);
    if (value < 0.0L) throw std::runtime_error(context);
    if (static_cast<long double>(result) < value) {
        result = std::nextafter(result, std::numeric_limits<double>::infinity());
        if (!std::isfinite(result)) throw std::runtime_error(context);
    }
    return result;
}

double lower_bound(long double value, const char* context) {
    double result = representable(value, context);
    if (static_cast<long double>(result) > value) {
        result = std::nextafter(result, -std::numeric_limits<double>::infinity());
        if (!std::isfinite(result)) throw std::runtime_error(context);
    }
    return result;
}

double spacing(double value) {
    return std::nextafter(value, std::numeric_limits<double>::infinity()) - value;
}

struct InstantaneousFlux {
    std::vector<double> emitted, transport, roundoff;
};

InstantaneousFlux initial_flux(
    const SurfaceEnergySystem& system,
    const std::vector<double>& temperature,
    const std::vector<double>& source
) {
    const auto& columns = system.columns();
    const auto count = columns.size();
    InstantaneousFlux flux;
    flux.emitted.resize(count);
    flux.transport.resize(count);
    flux.roundoff.resize(count);
    std::vector<double> temperature_spacing(count);
    for (std::size_t i = 0; i < count; ++i) temperature_spacing[i] = spacing(temperature[i]);
    std::vector<long double> incoming(count, 0.0L), transport_roundoff(count, 0.0L);
    // One physical exchange per pair, with opposite signs at its endpoints.
    for (const auto& edge : system.edges()) {
        const auto i = edge.first_cell;
        const auto j = edge.second_cell;
        const long double exchange = static_cast<long double>(edge.conductance_w_k) *
            (temperature[j] - temperature[i]);
        incoming[i] += exchange;
        incoming[j] -= exchange;
        const long double bound = 2.0L * edge.conductance_w_k *
            (temperature_spacing[i] + static_cast<long double>(temperature_spacing[j]));
        transport_roundoff[i] += bound;
        transport_roundoff[j] += bound;
    }
    for (std::size_t i = 0; i < count; ++i) {
        const auto& column = columns[i];
        const double squared = temperature[i] * temperature[i];
        flux.emitted[i] = column.longwave_emissivity * sigma * squared * squared;
        flux.transport[i] = representable(incoming[i] / column.area_m2,
            "initial energy transport is not representable");
        if (!std::isfinite(flux.emitted[i])) {
            throw std::runtime_error("initial outgoing radiation is not representable");
        }
        const double scale = std::max({1.0, source[i], flux.emitted[i], std::abs(flux.transport[i])});
        flux.roundoff[i] = upper_bound(
            8.0L * spacing(scale) + transport_roundoff[i] / column.area_m2 +
            8.0L * temperature_spacing[i] * column.longwave_emissivity * sigma *
                temperature[i] * squared,
            "initial energy roundoff is not representable"
        );
    }
    return flux;
}

void validate_physical_inputs(
    const SurfaceEnergySystem& system,
    const std::vector<double>& initial,
    const std::vector<double>& source,
    const SurfaceEnergyStepOptions& options
) {
    if (initial.size() != system.columns().size() || source.size() != initial.size() ||
        !std::isfinite(options.duration_seconds) || options.duration_seconds <= 0.0 ||
        !std::isfinite(options.absolute_tolerance_w_m2) || options.absolute_tolerance_w_m2 <= 0.0 ||
        !std::isfinite(options.relative_tolerance) || options.relative_tolerance < 0.0 ||
        options.maximum_newton_iterations < 1 || options.maximum_linear_iterations < 1) {
        throw std::invalid_argument("invalid time-integrated energy inputs or options");
    }
    for (std::size_t i = 0; i < initial.size(); ++i) {
        if (!std::isfinite(initial[i]) || initial[i] < 0.0 || !std::isfinite(source[i]) || source[i] < 0.0) {
            throw std::invalid_argument("time-integrated physical temperature/source must be finite and nonnegative");
        }
    }
}

void moments(
    IntegratedSurfaceEnergyStep& result,
    const std::vector<double>& initial,
    const std::vector<double>& stage,
    bool tr_bdf2
) {
    const auto count = initial.size();
    result.mean_temperature_k.resize(count);
    result.mean_fourth_power_temperature_k4.resize(count);
    result.mean_cubic_temperature_k3.resize(count);
    for (std::size_t i = 0; i < count; ++i) {
        const long double t0 = initial[i], t1 = stage[i], t2 = result.budget.temperature_k[i];
        const long double w0 = tr_bdf2 ? b : 0.0L;
        const long double w1 = tr_bdf2 ? b : 0.0L;
        const long double w2 = tr_bdf2 ? a : 1.0L;
        result.mean_temperature_k[i] = representable(w0 * t0 + w1 * t1 + w2 * t2,
            "mean energy temperature is not representable");
        result.mean_cubic_temperature_k3[i] = representable(
            w0 * t0 * t0 * t0 + w1 * t1 * t1 * t1 + w2 * t2 * t2 * t2,
            "mean cubic energy temperature is not representable");
        result.mean_fourth_power_temperature_k4[i] = representable(
            w0 * t0 * t0 * t0 * t0 + w1 * t1 * t1 * t1 * t1 + w2 * t2 * t2 * t2 * t2,
            "mean fourth-power energy temperature is not representable");
    }
}

int sum_iterations(int first, int second) {
    if (first > std::numeric_limits<int>::max() - second) {
        throw std::runtime_error("time-integrated iteration count is not representable");
    }
    return first + second;
}

std::vector<bool> exact_zero_components(
    const SurfaceEnergySystem& system,
    const std::vector<double>& initial,
    const std::vector<double>& source
) {
    if (std::find(initial.begin(), initial.end(), 0.0) == initial.end()) {
        return std::vector<bool>(initial.size(), false);
    }
    std::vector<std::size_t> parent(initial.size());
    std::iota(parent.begin(), parent.end(), 0);
    const auto root = [&](std::size_t index) {
        while (parent[index] != index) {
            parent[index] = parent[parent[index]];
            index = parent[index];
        }
        return index;
    };
    for (const auto& edge : system.edges()) parent[root(edge.first_cell)] = root(edge.second_cell);
    std::vector<bool> zero(initial.size(), true);
    for (std::size_t i = 0; i < initial.size(); ++i) {
        if (initial[i] != 0.0 || source[i] != 0.0) zero[root(i)] = false;
    }
    std::vector<bool> result(initial.size());
    for (std::size_t i = 0; i < initial.size(); ++i) result[i] = zero[root(i)];
    return result;
}

void verify_zero_component(const SurfaceEnergyStep& step, std::size_t i) {
    if (step.temperature_k[i] != 0.0 || step.emitted_longwave_w_m2[i] != 0.0 ||
        step.horizontal_heat_convergence_w_m2[i] != 0.0 || step.heat_storage_tendency_w_m2[i] != 0.0 ||
        step.balance_residual_w_m2[i] != 0.0) {
        throw std::runtime_error("analytically unforced zero component acquired energy");
    }
}

}  // namespace

IntegratedSurfaceEnergyStep integrate_surface_energy_step(
    const SurfaceEnergySystem& system,
    const std::vector<double>& initial,
    const std::vector<double>& source,
    const SurfaceEnergyStepOptions& options,
    SurfaceEnergyTimeMethod method
) {
    validate_physical_inputs(system, initial, source, options);
    IntegratedSurfaceEnergyStep result;
    const auto& columns = system.columns();
    const auto count = columns.size();
    const long double duration = options.duration_seconds;
    const auto exact_zero = exact_zero_components(system, initial, source);
    if (method == SurfaceEnergyTimeMethod::backward_euler) {
        result.budget = system.advance(initial, source, options);
        moments(result, initial, initial, false);
        long double uncertainty = 0.0L;
        for (std::size_t i = 0; i < count; ++i) {
            if (exact_zero[i]) {
                verify_zero_component(result.budget, i);
                continue;
            }
            const long double residual_bound = std::abs(result.budget.balance_residual_w_m2[i]) +
                static_cast<long double>(result.budget.temperature_roundoff_allowance_w_m2[i]);
            uncertainty = std::max(uncertainty, duration * residual_bound / columns[i].heat_capacity_j_m2_k +
                2.0L * spacing(result.budget.temperature_k[i]));
        }
        result.endpoint_numerical_uncertainty_k = upper_bound(uncertainty,
            "backward-Euler endpoint uncertainty is not representable");
        // Physical BE has a nonnegative exact solution for every nonnegative
        // initial state/source: the gray radiation and graph diffusion form a
        // monotone implicit map. A numerical error enclosure crossing zero
        // therefore does not invalidate its separate analytic certificate.
        result.minimum_stage_positivity_margin_k = std::numeric_limits<double>::max();
        return result;
    }
    if (method != SurfaceEnergyTimeMethod::tr_bdf2) {
        throw std::invalid_argument("unsupported surface energy time method");
    }

    auto stage_options = options;
    stage_options.duration_seconds = a * options.duration_seconds;
    if (!std::isfinite(stage_options.duration_seconds) || stage_options.duration_seconds <= 0.0) {
        throw std::runtime_error("TR-BDF2 stage duration is not representable");
    }
    const long double stage_duration = stage_options.duration_seconds;
    const long double duration_error = std::abs(stage_duration - static_cast<long double>(a) * duration);
    const auto flux0 = initial_flux(system, initial, source);
    std::vector<double> reference1(count), reference2(count);
    std::vector<long double> net0(count), reference_error1(count), reference_error2(count);
    for (std::size_t i = 0; i < count; ++i) {
        net0[i] = static_cast<long double>(source[i]) - flux0.emitted[i] + flux0.transport[i];
        const long double increment = stage_duration * net0[i] / columns[i].heat_capacity_j_m2_k;
        const long double exact_reference = initial[i] + increment;
        reference1[i] = representable(exact_reference, "first TR-BDF2 reference is not representable");
        reference_error1[i] = std::abs(static_cast<long double>(reference1[i]) - exact_reference) +
            8.0L * arithmetic_epsilon * (std::abs(initial[i]) + std::abs(increment));
    }
    const auto first = system.implicit_stage(reference1, source, initial, stage_options);
    // Eliminating F(T0)+F(Y) from the trapezoidal first stage gives this BDF
    // reference. It propagates the first stage's actual defect rather than
    // silently recomputing a different explicit right-hand side.
    const long double ratio_error = std::abs(static_cast<long double>(stage_ratio) -
        static_cast<long double>(b) / a);
    for (std::size_t i = 0; i < count; ++i) {
        const long double difference = static_cast<long double>(first.temperature_k[i]) - initial[i];
        const long double increment = stage_ratio * difference;
        const long double exact_reference = initial[i] + increment;
        reference2[i] = representable(exact_reference, "second TR-BDF2 reference is not representable");
        reference_error2[i] = std::abs(static_cast<long double>(reference2[i]) - exact_reference) +
            8.0L * arithmetic_epsilon * (std::abs(initial[i]) + std::abs(increment));
    }
    const auto second = system.implicit_stage(reference2, source, first.temperature_k, stage_options);
    auto& budget = result.budget;
    budget.temperature_k = second.temperature_k;
    budget.emitted_longwave_w_m2.resize(count);
    budget.horizontal_heat_convergence_w_m2.resize(count);
    budget.heat_storage_tendency_w_m2.resize(count);
    budget.balance_residual_w_m2.resize(count);
    budget.temperature_roundoff_allowance_w_m2.resize(count);
    budget.balance_tolerance_w_m2.resize(count);
    budget.newton_iterations = sum_iterations(first.newton_iterations, second.newton_iterations);
    budget.linear_iterations = sum_iterations(first.linear_iterations, second.linear_iterations);
    const long double second_residual_weight = stage_duration / duration;
    const long double first_residual_weight = stage_ratio * second_residual_weight;
    long double global_residual = 0.0L, first_uncertainty = 0.0L, second_uncertainty = 0.0L;
    for (std::size_t i = 0; i < count; ++i) {
        const long double capacity = columns[i].heat_capacity_j_m2_k;
        const long double net1 = static_cast<long double>(source[i]) -
            first.emitted_longwave_w_m2[i] + first.horizontal_heat_convergence_w_m2[i];
        const long double net2 = static_cast<long double>(source[i]) -
            second.emitted_longwave_w_m2[i] + second.horizontal_heat_convergence_w_m2[i];
        budget.emitted_longwave_w_m2[i] = representable(
            static_cast<long double>(b) * (flux0.emitted[i] + static_cast<long double>(first.emitted_longwave_w_m2[i])) +
                static_cast<long double>(a) * second.emitted_longwave_w_m2[i],
            "TR-BDF2 mean outgoing radiation is not representable");
        budget.horizontal_heat_convergence_w_m2[i] = representable(
            static_cast<long double>(b) * (flux0.transport[i] + static_cast<long double>(first.horizontal_heat_convergence_w_m2[i])) +
                static_cast<long double>(a) * second.horizontal_heat_convergence_w_m2[i],
            "TR-BDF2 mean heat transport is not representable");
        budget.heat_storage_tendency_w_m2[i] = representable(capacity *
            (static_cast<long double>(second.temperature_k[i]) - initial[i]) / duration,
            "TR-BDF2 storage tendency is not representable");
        const long double residual = static_cast<long double>(budget.heat_storage_tendency_w_m2[i]) - source[i] +
            budget.emitted_longwave_w_m2[i] - budget.horizontal_heat_convergence_w_m2[i];
        budget.balance_residual_w_m2[i] = representable(residual, "TR-BDF2 energy residual is not representable");

        // Exact eliminated-stage identity, plus bounds on the represented
        // references and duration/weight arithmetic. These are uncertainties;
        // the physical residual above is never replaced with their negative.
        const long double construction_flux_error = capacity / duration *
            (stage_ratio * reference_error1[i] + reference_error2[i]) +
            std::abs(first_residual_weight - b) * (std::abs(net0[i]) + std::abs(net1)) +
            std::abs(second_residual_weight - a) * std::abs(net2);
        const double scale = std::max({1.0, source[i], budget.emitted_longwave_w_m2[i],
            std::abs(budget.horizontal_heat_convergence_w_m2[i]), std::abs(budget.heat_storage_tendency_w_m2[i])});
        const long double output_roundoff = 8.0L * spacing(scale) +
            2.0L * capacity / duration * (spacing(initial[i]) + static_cast<long double>(spacing(second.temperature_k[i])));
        const long double extra_roundoff = construction_flux_error + output_roundoff +
            static_cast<long double>(b) * flux0.roundoff[i];
        budget.temperature_roundoff_allowance_w_m2[i] = upper_bound(extra_roundoff +
            first_residual_weight * first.temperature_roundoff_allowance_w_m2[i] +
            second_residual_weight * second.temperature_roundoff_allowance_w_m2[i],
            "TR-BDF2 energy roundoff is not representable");
        budget.balance_tolerance_w_m2[i] = upper_bound(extra_roundoff +
            first_residual_weight * first.balance_tolerance_w_m2[i] +
            second_residual_weight * second.balance_tolerance_w_m2[i],
            "TR-BDF2 energy tolerance is not representable");
        if (std::abs(budget.balance_residual_w_m2[i]) > budget.balance_tolerance_w_m2[i]) {
            throw std::runtime_error("TR-BDF2 weighted physical energy ledger did not close");
        }
        budget.maximum_balance_residual_w_m2 = std::max(budget.maximum_balance_residual_w_m2,
            std::abs(budget.balance_residual_w_m2[i]));
        global_residual += columns[i].area_m2 * residual;

        if (exact_zero[i]) {
            verify_zero_component(first, i);
            verify_zero_component(second, i);
            verify_zero_component(budget, i);
            continue;
        }
        const long double rho1 = std::abs(first.balance_residual_w_m2[i]) +
            static_cast<long double>(first.temperature_roundoff_allowance_w_m2[i]);
        const long double rho2 = std::abs(second.balance_residual_w_m2[i]) +
            static_cast<long double>(second.temperature_roundoff_allowance_w_m2[i]);
        first_uncertainty = std::max(first_uncertainty, reference_error1[i] +
            stage_duration * (flux0.roundoff[i] + rho1) / capacity +
            duration_error * (std::abs(net0[i]) + std::abs(net1)) / capacity);
        second_uncertainty = std::max(second_uncertainty, reference_error2[i] +
            ratio_error * std::abs(static_cast<long double>(first.temperature_k[i]) - initial[i]) +
            stage_duration * rho2 / capacity + duration_error * std::abs(net2) / capacity +
            2.0L * spacing(second.temperature_k[i]));
    }
    budget.global_balance_residual_w = representable(global_residual, "TR-BDF2 global residual is not representable");
    // A nonnegative gray-radiation/diffusion implicit resolvent is a
    // contraction in the maximum temperature norm. The eliminated second
    // reference amplifies the first stage's error by b/a, not a Jacobian norm.
    result.endpoint_numerical_uncertainty_k = upper_bound(
        (stage_ratio + ratio_error) * first_uncertainty + second_uncertainty,
        "TR-BDF2 endpoint uncertainty is not representable");
    result.minimum_stage_positivity_margin_k = std::numeric_limits<double>::max();
    for (std::size_t i = 0; i < count; ++i) {
        if (!exact_zero[i]) result.minimum_stage_positivity_margin_k = std::min({
            result.minimum_stage_positivity_margin_k,
            lower_bound(static_cast<long double>(first.temperature_k[i]) - first_uncertainty,
                "TR-BDF2 first-stage positivity margin is not representable"),
            lower_bound(static_cast<long double>(second.temperature_k[i]) - result.endpoint_numerical_uncertainty_k,
                "TR-BDF2 endpoint positivity margin is not representable"),
        });
    }
    if (result.minimum_stage_positivity_margin_k < 0.0) {
        throw std::runtime_error("TR-BDF2 stage positivity is not numerically certified");
    }
    moments(result, initial, first.temperature_k, true);
    return result;
}

}  // namespace magic_geo::detail
