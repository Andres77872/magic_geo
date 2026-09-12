#include "seasonal_energy_balance.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <set>
#include <stdexcept>
#include <utility>

namespace magic_geo::detail {
namespace {

constexpr double sigma = 5.670374419e-8;

bool positive_finite(double value) {
    return std::isfinite(value) && value > 0.0;
}

double spacing(double value) {
    return std::nextafter(value, std::numeric_limits<double>::infinity()) - value;
}

long double inner_product(const std::vector<double>& a, const std::vector<double>& b) {
    long double sum = 0.0L;
    for (std::size_t i = 0; i < a.size(); ++i) {
        sum += static_cast<long double>(a[i]) * b[i];
    }
    return sum;
}

struct EnergyEvaluation {
    SurfaceEnergyStep step;
    long double merit = 0.0L;
    bool converged = true;
};

EnergyEvaluation evaluate(
    const std::vector<SurfaceEnergyColumn>& columns,
    const std::vector<EnergyTransportEdge>& edges,
    const std::vector<double>& previous,
    const std::vector<double>& absorbed,
    const std::vector<double>& temperature,
    const SurfaceEnergyStepOptions& options
) {
    EnergyEvaluation result;
    auto& step = result.step;
    const auto count = columns.size();
    step.temperature_k = temperature;
    step.emitted_longwave_w_m2.resize(count);
    step.horizontal_heat_convergence_w_m2.assign(count, 0.0);
    step.heat_storage_tendency_w_m2.resize(count);
    step.balance_residual_w_m2.resize(count);
    step.temperature_roundoff_allowance_w_m2.resize(count);
    step.balance_tolerance_w_m2.resize(count);
    std::vector<double> temperature_spacing(count);
    for (std::size_t i = 0; i < count; ++i) {
        temperature_spacing[i] = spacing(temperature[i]);
    }
    // Each physical exchange is computed once and enters with opposite signs.
    std::vector<long double> incoming_w(count, 0.0L);
    std::vector<long double> transport_roundoff_w(count, 0.0L);
    for (const auto& edge : edges) {
        const long double flow = static_cast<long double>(edge.conductance_w_k) *
            (temperature[edge.second_cell] - temperature[edge.first_cell]);
        incoming_w[edge.first_cell] += flow;
        incoming_w[edge.second_cell] -= flow;
        const long double bound = 2.0L * edge.conductance_w_k *
            (temperature_spacing[edge.first_cell] + temperature_spacing[edge.second_cell]);
        transport_roundoff_w[edge.first_cell] += bound;
        transport_roundoff_w[edge.second_cell] += bound;
    }
    long double global_residual = 0.0L;
    for (std::size_t i = 0; i < count; ++i) {
        const auto& column = columns[i];
        const double squared = temperature[i] * temperature[i];
        const double emitted = column.longwave_emissivity * sigma * squared * squared;
        const double transport = static_cast<double>(incoming_w[i] / column.area_m2);
        const double storage = column.heat_capacity_j_m2_k *
            (temperature[i] - previous[i]) / options.duration_seconds;
        const double residual = static_cast<double>(
            static_cast<long double>(storage) - absorbed[i] + emitted - transport
        );
        if (!std::isfinite(residual) || !std::isfinite(emitted)) {
            result.converged = false;
            result.merit = std::numeric_limits<long double>::infinity();
            return result;
        }
        step.emitted_longwave_w_m2[i] = emitted;
        step.horizontal_heat_convergence_w_m2[i] = transport;
        step.heat_storage_tendency_w_m2[i] = storage;
        step.balance_residual_w_m2[i] = residual;
        step.maximum_balance_residual_w_m2 = std::max(
            step.maximum_balance_residual_w_m2, std::abs(residual)
        );
        const double scale = std::max({1.0, std::abs(absorbed[i]), emitted, std::abs(transport), std::abs(storage)});
        const double roundoff = static_cast<double>(
            2.0L * temperature_spacing[i] * (column.heat_capacity_j_m2_k / options.duration_seconds +
                4.0L * column.longwave_emissivity * sigma * temperature[i] * squared) +
            transport_roundoff_w[i] / column.area_m2 + 8.0L * spacing(scale)
        );
        const double tolerance = options.absolute_tolerance_w_m2 + options.relative_tolerance * scale + roundoff;
        if (!std::isfinite(tolerance)) {
            result.converged = false;
            result.merit = std::numeric_limits<long double>::infinity();
            return result;
        }
        step.temperature_roundoff_allowance_w_m2[i] = roundoff;
        step.balance_tolerance_w_m2[i] = tolerance;
        result.converged = result.converged && std::abs(residual) <= tolerance;
        result.merit += static_cast<long double>(column.area_m2) * residual * residual;
        global_residual += static_cast<long double>(column.area_m2) * residual;
    }
    step.global_balance_residual_w = static_cast<double>(global_residual);
    return result;
}

std::vector<double> linear_response(
    const std::vector<SurfaceEnergyColumn>& columns,
    const std::vector<EnergyTransportEdge>& edges,
    const std::vector<double>& root_area,
    const std::vector<double>& base_diagonal,
    const std::vector<double>& flux,
    int maximum_iterations,
    int& iterations
) {
    const auto count = columns.size();
    std::vector<double> diagonal(count), rhs(count);
    for (std::size_t i = 0; i < count; ++i) {
        diagonal[i] = base_diagonal[i];
        rhs[i] = flux[i] * root_area[i];
    }
    for (const auto& edge : edges) {
        diagonal[edge.first_cell] += edge.conductance_w_k / columns[edge.first_cell].area_m2;
        diagonal[edge.second_cell] += edge.conductance_w_k / columns[edge.second_cell].area_m2;
    }
    // Scaling unknowns by sqrt(area) keeps the sparse Newton matrix symmetric
    // positive definite even when cell areas and surface capacities differ.
    auto multiply = [&](const std::vector<double>& vector, std::vector<double>& product) {
        for (std::size_t i = 0; i < count; ++i) {
            product[i] = base_diagonal[i] * vector[i];
        }
        for (const auto& edge : edges) {
            const auto a = edge.first_cell;
            const auto b = edge.second_cell;
            const double exchange = edge.conductance_w_k *
                (vector[a] / root_area[a] - vector[b] / root_area[b]);
            product[a] += exchange / root_area[a];
            product[b] -= exchange / root_area[b];
        }
    };
    std::vector<double> solution(count, 0.0), residual = rhs, preconditioned(count), direction(count);
    std::vector<double> product(count);
    for (std::size_t i = 0; i < count; ++i) {
        preconditioned[i] = residual[i] / diagonal[i];
    }
    direction = preconditioned;
    long double rz = inner_product(residual, preconditioned);
    const long double initial_norm = inner_product(rhs, rhs);
    if (initial_norm == 0.0L) {
        return solution;
    }
    bool converged = false;
    for (int iteration = 0; iteration < maximum_iterations; ++iteration) {
        ++iterations;
        multiply(direction, product);
        const long double denominator = inner_product(direction, product);
        if (!(denominator > 0.0L) || !std::isfinite(denominator)) {
            throw std::runtime_error("surface energy Newton matrix lost positive definiteness");
        }
        const double alpha = static_cast<double>(rz / denominator);
        for (std::size_t i = 0; i < count; ++i) {
            solution[i] += alpha * direction[i];
            residual[i] -= alpha * product[i];
        }
        if (inner_product(residual, residual) <= initial_norm * 1.0e-24L) {
            // Check the true residual rather than accepting only CG's recursive
            // residual, which can drift on strongly conditioned systems.
            multiply(solution, product);
            for (std::size_t i = 0; i < count; ++i) {
                residual[i] = rhs[i] - product[i];
            }
            if (inner_product(residual, residual) <= initial_norm * 4.0e-24L) {
                converged = true;
                break;
            }
            for (std::size_t i = 0; i < count; ++i) {
                preconditioned[i] = residual[i] / diagonal[i];
            }
            direction = preconditioned;
            rz = inner_product(residual, preconditioned);
            continue;
        }
        for (std::size_t i = 0; i < count; ++i) {
            preconditioned[i] = residual[i] / diagonal[i];
        }
        const long double next_rz = inner_product(residual, preconditioned);
        const double beta = static_cast<double>(next_rz / rz);
        for (std::size_t i = 0; i < count; ++i) {
            direction[i] = preconditioned[i] + beta * direction[i];
        }
        rz = next_rz;
    }
    if (!converged) {
        throw std::runtime_error("surface energy linear solve did not converge");
    }
    for (std::size_t i = 0; i < count; ++i) {
        solution[i] /= root_area[i];
    }
    return solution;
}

}  // namespace

SurfaceEnergySystem::SurfaceEnergySystem(
    std::vector<SurfaceEnergyColumn> columns, std::vector<EnergyTransportEdge> edges
) : columns_(std::move(columns)), edges_(std::move(edges)) {
    const auto count = columns_.size();
    if (count == 0) {
        throw std::invalid_argument("surface energy system requires columns");
    }
    for (std::size_t i = 0; i < count; ++i) {
        if (!positive_finite(columns_[i].area_m2) || !positive_finite(columns_[i].heat_capacity_j_m2_k) ||
            !std::isfinite(columns_[i].longwave_emissivity) || columns_[i].longwave_emissivity < 0.0 || columns_[i].longwave_emissivity > 1.0) {
            throw std::invalid_argument("invalid surface energy column");
        }
        root_area_.push_back(std::sqrt(columns_[i].area_m2));
    }
    std::set<std::pair<int, int>> seen_edges;
    for (const auto& edge : edges_) {
        if (edge.first_cell < 0 || edge.second_cell < 0 ||
            static_cast<std::size_t>(edge.first_cell) >= count || static_cast<std::size_t>(edge.second_cell) >= count ||
            edge.first_cell == edge.second_cell || !positive_finite(edge.conductance_w_k) ||
            !seen_edges.insert(std::minmax(edge.first_cell, edge.second_cell)).second) {
            throw std::invalid_argument("invalid or duplicate surface energy exchange edge");
        }
    }
}

std::vector<double> SurfaceEnergySystem::linear_response(
    const std::vector<double>& local_restoring_w_m2_k,
    const std::vector<double>& flux_w_m2,
    int maximum_linear_iterations
) const {
    if (local_restoring_w_m2_k.size() != columns_.size() || flux_w_m2.size() != columns_.size() || maximum_linear_iterations < 1) {
        throw std::invalid_argument("invalid surface energy linear response dimensions");
    }
    for (std::size_t i = 0; i < columns_.size(); ++i) {
        if (!positive_finite(local_restoring_w_m2_k[i]) || !std::isfinite(flux_w_m2[i])) {
            throw std::invalid_argument("invalid surface energy linear response coefficient or flux");
        }
    }
    int iterations = 0;
    return detail::linear_response(columns_, edges_, root_area_, local_restoring_w_m2_k, flux_w_m2, maximum_linear_iterations, iterations);
}

SurfaceEnergyStep SurfaceEnergySystem::implicit_stage(
    const std::vector<double>& previous_temperature_k,
    const std::vector<double>& absorbed_shortwave_w_m2,
    const std::vector<double>& initial_guess_temperature_k,
    const SurfaceEnergyStepOptions& options
) const {
    const auto& columns = columns_;
    const auto& edges = edges_;
    const auto count = columns.size();
    if (previous_temperature_k.size() != count || absorbed_shortwave_w_m2.size() != count || initial_guess_temperature_k.size() != count ||
        !positive_finite(options.duration_seconds) || !positive_finite(options.absolute_tolerance_w_m2) ||
        !std::isfinite(options.relative_tolerance) || options.relative_tolerance < 0.0 ||
        options.maximum_newton_iterations < 1 || options.maximum_linear_iterations < 1) {
        throw std::invalid_argument("invalid surface energy step dimensions or solver options");
    }
    for (std::size_t i = 0; i < count; ++i) {
        if (!std::isfinite(previous_temperature_k[i]) || !std::isfinite(absorbed_shortwave_w_m2[i]) ||
            !std::isfinite(initial_guess_temperature_k[i]) || initial_guess_temperature_k[i] < 0.0) {
            throw std::invalid_argument("invalid surface energy temperature or forcing");
        }
    }
    std::vector<double> temperature = initial_guess_temperature_k;
    auto current = evaluate(columns, edges, previous_temperature_k, absorbed_shortwave_w_m2, temperature, options);
    int linear_iterations = 0;
    for (int iteration = 0; iteration <= options.maximum_newton_iterations; ++iteration) {
        if (current.converged) {
            current.step.newton_iterations = iteration;
            current.step.linear_iterations = linear_iterations;
            return current.step;
        }
        if (iteration == options.maximum_newton_iterations || !std::isfinite(current.merit)) {
            break;
        }
        std::vector<double> restoring(count), flux(count);
        for (std::size_t i = 0; i < count; ++i) {
            const double value = temperature[i];
            restoring[i] = columns[i].heat_capacity_j_m2_k / options.duration_seconds +
                4.0 * columns[i].longwave_emissivity * sigma * value * value * value;
            flux[i] = -current.step.balance_residual_w_m2[i];
        }
        const auto direction = detail::linear_response(
            columns, edges, root_area_, restoring, flux, options.maximum_linear_iterations, linear_iterations
        );
        double step_length = 1.0;
        for (std::size_t i = 0; i < count; ++i) {
            if (direction[i] < 0.0) {
                step_length = std::min(step_length, -0.99 * temperature[i] / direction[i]);
            }
        }
        bool accepted = false;
        for (int backtrack = 0; backtrack < 64; ++backtrack) {
            std::vector<double> candidate(count);
            for (std::size_t i = 0; i < count; ++i) {
                candidate[i] = temperature[i] + step_length * direction[i];
            }
            auto next = evaluate(columns, edges, previous_temperature_k, absorbed_shortwave_w_m2, candidate, options);
            if (next.converged || next.merit < current.merit * (1.0L - 1.0e-4L * step_length)) {
                current = std::move(next);
                temperature = std::move(candidate);
                accepted = true;
                break;
            }
            step_length *= 0.5;
        }
        if (!accepted) {
            throw std::runtime_error("surface energy nonlinear solve could not reduce its residual");
        }
    }
    throw std::runtime_error("surface energy nonlinear solve did not converge");
}

SurfaceEnergyStep SurfaceEnergySystem::advance(
    const std::vector<double>& previous_temperature_k,
    const std::vector<double>& absorbed_shortwave_w_m2,
    const SurfaceEnergyStepOptions& options
) const {
    for (const double temperature : previous_temperature_k) {
        if (temperature < 0.0) throw std::invalid_argument("physical energy step requires nonnegative initial temperature");
    }
    for (const double source : absorbed_shortwave_w_m2) {
        if (source < 0.0) throw std::invalid_argument("physical energy step requires nonnegative absorbed shortwave");
    }
    return implicit_stage(previous_temperature_k, absorbed_shortwave_w_m2, previous_temperature_k, options);
}

SurfaceEnergyStep advance_surface_energy_balance(
    const std::vector<SurfaceEnergyColumn>& columns,
    const std::vector<EnergyTransportEdge>& edges,
    const std::vector<double>& previous_temperature_k,
    const std::vector<double>& absorbed_shortwave_w_m2,
    const SurfaceEnergyStepOptions& options
) {
    return SurfaceEnergySystem(columns, edges).advance(previous_temperature_k, absorbed_shortwave_w_m2, options);
}

}  // namespace magic_geo::detail
