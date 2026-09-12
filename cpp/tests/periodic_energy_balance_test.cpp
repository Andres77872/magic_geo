#include "engine/periodic_energy_balance.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <utility>
#include <vector>

namespace {
using namespace magic_geo::detail;
constexpr double sigma = 5.670374419e-8;
constexpr double pi = 3.1415926535897932384626433832795;
constexpr double year_seconds = 31557600.0;

void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

void close(double actual, double expected, double tolerance, const char* message) {
    if (!std::isfinite(actual) || !std::isfinite(expected) || std::abs(actual - expected) > tolerance) {
        std::cerr << message << ": " << actual << " versus " << expected << '\n';
        throw std::runtime_error(message);
    }
}

std::vector<SurfaceEnergyForcingInterval> constant_forcing(const std::vector<double>& flux) {
    std::vector<SurfaceEnergyForcingInterval> result;
    for (int month = 0; month < 12; ++month) result.push_back({month, year_seconds / 12.0, flux});
    return result;
}

SurfaceEnergySystem mixed_system() {
    const double thick_atmosphere = 1004.0 * 1.0e8 / (9.80665 * 0.050001);
    return SurfaceEnergySystem(
        {{1.0e12, 4.0e6, 0.96}, {3.0e12, 2.1e8, 0.6}, {0.2e12, thick_atmosphere, 0.1}},
        {{0, 1, 0.5e12}, {1, 2, 0.3e12}}
    );
}

std::vector<SurfaceEnergyForcingInterval> seasonal_forcing() {
    // Unequal subinterval durations exercise time weighting within every month.
    const std::array<double, 3> fractions{1.0 / 6.0, 1.0 / 3.0, 0.5};
    const std::array<double, 3> mean{40.0, 200.0, 500.0};
    const std::array<double, 3> phase{0.0, pi, 0.4};
    std::vector<SurfaceEnergyForcingInterval> result;
    double elapsed = 0.0;
    for (int month = 0; month < 12; ++month) {
        for (double fraction : fractions) {
            const double duration = year_seconds / 12.0 * fraction;
            const double start = 2.0 * pi * elapsed / year_seconds;
            const double end = 2.0 * pi * (elapsed + duration) / year_seconds;
            std::vector<double> flux;
            for (std::size_t i = 0; i < mean.size(); ++i) {
                const double mean_cosine = (std::sin(end + phase[i]) - std::sin(start + phase[i])) / (end - start);
                flux.push_back(mean[i] * (1.0 + 0.95 * mean_cosine));
            }
            result.push_back({month, duration, flux});
            elapsed += duration;
        }
    }
    return result;
}

void equilibrium_and_extreme_capacity() {
    const auto system = mixed_system();
    std::vector<double> flux;
    for (const auto& column : system.columns()) flux.push_back(column.longwave_emissivity * sigma * std::pow(300.0, 4));
    const auto forcing = constant_forcing(flux);
    const auto exact = solve_periodic_surface_energy_balance(system, forcing, {300.0, 300.0, 300.0});
    require(exact.periodic_iterations == 0 && exact.year_evaluations == 1, "exact equilibrium was iterated");
    require(exact.initial_temperature_k == exact.final_temperature_k, "constant equilibrium moved");
    for (const auto& month : exact.months) {
        for (double temperature : month.mean_temperature_k) close(temperature, 300.0, 1.0e-12, "constant mean temperature changed");
    }
    const auto corrected = solve_periodic_surface_energy_balance(system, forcing, {150.0, 450.0, 250.0});
    require(corrected.periodic_iterations < 32, "large capacity required slow year-by-year spinup");
    for (double temperature : corrected.initial_temperature_k) close(temperature, 300.0, 5.0e-5, "constant forcing did not recover graybody equilibrium");
    const SurfaceEnergySystem dark({{1.0e12, 4.0e6, 0.96}}, {});
    const auto zero = solve_periodic_surface_energy_balance(dark, constant_forcing({0.0}), {0.0});
    require(zero.initial_temperature_k[0] == 0.0 && zero.final_temperature_k[0] == 0.0, "dark equilibrium acquired heat");
    const auto initially_warm = solve_periodic_surface_energy_balance(dark, constant_forcing({0.0}), {300.0});
    require(initially_warm.initial_temperature_k[0] == 0.0 && initially_warm.final_temperature_k[0] == 0.0,
        "vanishing radiative restoring hid the exact dark periodic root");
    const SurfaceEnergySystem disconnected({{1.0, 4.0e6, 0.96}, {2.0, 2.1e8, 0.96}, {1.0, 4.0e6, 0.96}}, {{0, 1, 1.0}});
    const auto partly_dark = solve_periodic_surface_energy_balance(disconnected, constant_forcing({0.0, 0.0, 240.0}), {100.0, 300.0, 280.0});
    require(partly_dark.initial_temperature_k[0] == 0.0 && partly_dark.initial_temperature_k[1] == 0.0 &&
        partly_dark.initial_temperature_k[2] > 0.0, "dark component root affected an illuminated component");
}

void monthly_and_annual_ledgers_are_conservative() {
    const auto system = mixed_system();
    const auto forcing = seasonal_forcing();
    const auto solved = solve_periodic_surface_energy_balance(system, forcing, {290.0, 350.0, 500.0});
    std::array<long double, 3> annual_net{}, annual_absorbed{};
    bool positive_storage = false, negative_storage = false;
    for (int index = 0; index < 12; ++index) {
        const auto& month = solved.months[static_cast<std::size_t>(index)];
        close(month.duration_seconds, year_seconds / 12.0, 1.0e-8, "monthly export duration changed");
        const auto& prior = index == 0 ? solved.initial_temperature_k : solved.months[static_cast<std::size_t>(index - 1)].final_temperature_k;
        require(month.initial_temperature_k == prior, "month boundary temperature is discontinuous");
        long double transport_w = 0.0L;
        for (std::size_t i = 0; i < system.columns().size(); ++i) {
            const auto& column = system.columns()[i];
            long double incoming_energy = 0.0L;
            for (const auto& interval : forcing) {
                if (interval.month_index == index) incoming_energy += static_cast<long double>(interval.duration_seconds) * interval.absorbed_shortwave_w_m2[i];
            }
            close(month.absorbed_shortwave_w_m2[i], static_cast<double>(incoming_energy / month.duration_seconds), 1.0e-10, "monthly forcing is not time weighted");
            close(month.emitted_longwave_w_m2[i], column.longwave_emissivity * sigma * month.mean_fourth_power_temperature_k4[i], 1.0e-9, "longwave is not the mean fourth-power flux");
            require(month.mean_fourth_power_temperature_k4[i] + 1.0e-12 * month.mean_fourth_power_temperature_k4[i] >= std::pow(month.mean_temperature_k[i], 4), "temperature moments violate convexity");
            const double endpoint_storage = column.heat_capacity_j_m2_k *
                (month.final_temperature_k[i] - month.initial_temperature_k[i]) / month.duration_seconds;
            close(month.heat_storage_tendency_w_m2[i], endpoint_storage, 1.0e-8, "monthly storage does not telescope from endpoints");
            const double net = month.absorbed_shortwave_w_m2[i] - month.emitted_longwave_w_m2[i] + month.horizontal_heat_convergence_w_m2[i];
            close(month.heat_storage_tendency_w_m2[i] - net, month.balance_residual_w_m2[i], 1.0e-9, "reported monthly residual differs from physical ledger");
            require(std::abs(month.balance_residual_w_m2[i]) <= month.balance_tolerance_w_m2[i], "monthly ledger exceeds recorded numerical tolerance");
            annual_net[i] += static_cast<long double>(month.duration_seconds) * net;
            annual_absorbed[i] += incoming_energy;
            transport_w += static_cast<long double>(column.area_m2) * month.horizontal_heat_convergence_w_m2[i];
        }
        close(static_cast<double>(transport_w), 0.0, 0.1, "unequal-area heat transport created global energy");
        positive_storage = positive_storage || month.heat_storage_tendency_w_m2[0] > 1.0;
        negative_storage = negative_storage || month.heat_storage_tendency_w_m2[0] < -1.0;
    }
    require(positive_storage && negative_storage, "periodic temperature was flattened instead of storing seasonal heat");
    require(solved.final_temperature_k == solved.months.back().final_temperature_k, "annual final state differs from final month");
    long double global_net = 0.0L, global_tolerance = 0.0L;
    for (std::size_t i = 0; i < system.columns().size(); ++i) {
        close(static_cast<double>(annual_net[i] / year_seconds), solved.annual_net_heating_w_m2[i], 1.0e-9, "annual physical net flux does not match monthly ledger");
        close(static_cast<double>(annual_absorbed[i] / year_seconds), std::array<double, 3>{40.0, 200.0, 500.0}[i], 1.0e-9, "seasonal forcing changed annual input");
        require(std::abs(solved.annual_net_heating_w_m2[i]) <= solved.annual_flux_tolerance_w_m2[i], "periodic solution retained unresolved annual heating");
        global_net += system.columns()[i].area_m2 * annual_net[i] / year_seconds;
        global_tolerance += system.columns()[i].area_m2 * solved.annual_flux_tolerance_w_m2[i];
    }
    require(std::abs(global_net) <= global_tolerance, "periodic cycle creates global energy");
    close(static_cast<double>(global_net), solved.global_annual_net_heating_w, 2.0, "global annual residual differs from physical areas");
}

void initial_guess_does_not_select_an_imposed_climate() {
    const auto system = mixed_system();
    const auto forcing = seasonal_forcing();
    PeriodicSurfaceEnergyOptions options;
    options.phase_tolerance_k = 1.0e-6;
    options.annual_flux_tolerance_w_m2 = 1.0e-6;
    const auto cold = solve_periodic_surface_energy_balance(system, forcing, {100.0, 180.0, 240.0}, options);
    const auto hot = solve_periodic_surface_energy_balance(system, forcing, {600.0, 700.0, 900.0}, options);
    for (std::size_t month = 0; month < 12; ++month) {
        for (std::size_t i = 0; i < system.columns().size(); ++i) {
            close(cold.months[month].mean_temperature_k[i], hot.months[month].mean_temperature_k[i], 1.0e-5, "initial guess changed the periodic cycle");
        }
    }
}

void mixed_capacity_residual_norm_counterexample_converges() {
    // Linearization about 500 K has a stable period correction whose unweighted
    // maximum flux residual initially grows by a factor of approximately 2.4.
    // A max-norm line search cannot follow that correction; A/C weighting can.
    const std::array<double, 3> area{1.45892041e12, 0.34329445e12, 7.23684699e12};
    const std::array<double, 3> capacity_per_year{0.79561583, 128.70943361, 0.51578288};
    const std::array<double, 3> restoring{12.09266251, 0.05796342, 0.69129601};
    std::vector<SurfaceEnergyColumn> columns;
    std::vector<double> flux;
    for (std::size_t i = 0; i < 3; ++i) {
        const double emissivity = restoring[i] / (4.0 * sigma * std::pow(500.0, 3));
        columns.push_back({area[i], capacity_per_year[i] * year_seconds, emissivity});
        flux.push_back(emissivity * sigma * std::pow(500.0, 4));
    }
    const SurfaceEnergySystem system(columns, {{0, 1, 0.05056948 * area[0]}, {1, 2, 17.16095286 * area[1]}});
    PeriodicSurfaceEnergyOptions options;
    options.phase_tolerance_k = 1.0e-7;
    options.annual_flux_tolerance_w_m2 = 1.0e-7;
    const auto solved = solve_periodic_surface_energy_balance(system, constant_forcing(flux),
        {500.0 - 0.0012632306014290816, 500.0 - 0.0015103100051212185, 500.0 - 0.002912606373357892}, options);
    require(solved.periodic_iterations < 24, "mixed-capacity correction was stalled by the wrong residual norm");
    for (double temperature : solved.initial_temperature_k) close(temperature, 500.0, 2.0e-6, "mixed-capacity equilibrium differs from analytic solution");
}

struct HarmonicResponse { double cosine = 0.0; double sine = 0.0; };

HarmonicResponse harmonic_response(int substeps) {
    constexpr double equilibrium = 280.0;
    constexpr double emissivity = 0.96;
    constexpr double forcing_amplitude = 0.01;
    const double restoring = 4.0 * emissivity * sigma * std::pow(equilibrium, 3);
    const double capacity = restoring * year_seconds / (2.0 * pi);
    const double mean_flux = emissivity * sigma * std::pow(equilibrium, 4);
    const SurfaceEnergySystem system({{1.0e12, capacity, emissivity}}, {});
    std::vector<SurfaceEnergyForcingInterval> forcing;
    for (int month = 0; month < 12; ++month) {
        for (int substep = 0; substep < substeps; ++substep) {
            const int index = month * substeps + substep;
            const double start = 2.0 * pi * index / (12 * substeps);
            const double end = 2.0 * pi * (index + 1) / (12 * substeps);
            const double flux = mean_flux + forcing_amplitude * (std::sin(end) - std::sin(start)) / (end - start);
            forcing.push_back({month, year_seconds / (12 * substeps), {flux}});
        }
    }
    PeriodicSurfaceEnergyOptions options;
    options.phase_tolerance_k = 1.0e-10;
    options.annual_flux_tolerance_w_m2 = 1.0e-9;
    options.relative_tolerance = 1.0e-13;
    options.step.absolute_tolerance_w_m2 = 1.0e-10;
    options.step.relative_tolerance = 1.0e-14;
    const auto solved = solve_periodic_surface_energy_balance(system, forcing, {equilibrium}, options);
    HarmonicResponse response;
    for (int month = 0; month < 12; ++month) {
        const double phase = 2.0 * pi * (month + 0.5) / 12;
        const double anomaly = solved.months[static_cast<std::size_t>(month)].mean_temperature_k[0] - equilibrium;
        response.cosine += anomaly * std::cos(phase) / 6.0;
        response.sine += anomaly * std::sin(phase) / 6.0;
    }
    return response;
}

void temporal_refinement_recovers_analytic_seasonal_phase_and_amplitude() {
    const double restoring = 4.0 * 0.96 * sigma * std::pow(280.0, 3);
    // C*omega = restoring: the infinitesimal graybody response has a 45-degree
    // lag. Equal-duration monthly averaging multiplies both coefficients by sinc.
    const double monthly_sinc = std::sin(pi / 12.0) / (pi / 12.0);
    const double expected_coefficient = 0.01 / (2.0 * restoring) * monthly_sinc;
    const auto coarse = harmonic_response(2);
    const auto medium = harmonic_response(4);
    const auto fine = harmonic_response(8);
    auto error = [&](const HarmonicResponse& value) {
        return std::hypot(value.cosine - expected_coefficient, value.sine - expected_coefficient);
    };
    require(error(coarse) / error(medium) > 1.8 && error(medium) / error(fine) > 1.8, "periodic seasonal response fails first-order refinement");
    close(std::atan2(fine.sine, fine.cosine), pi / 4.0, 0.025, "seasonal phase lag differs from analytic thermal storage");
    close(std::hypot(fine.cosine, fine.sine), std::sqrt(2.0) * expected_coefficient, 0.03 * std::sqrt(2.0) * expected_coefficient, "seasonal amplitude differs from analytic thermal storage");
}

void incomplete_or_unconverged_years_fail_explicitly() {
    const SurfaceEnergySystem system({{1.0e12, 4.0e6, 0.96}}, {});
    const auto forcing = constant_forcing({0.96 * sigma * std::pow(300.0, 4)});
    auto incomplete = forcing;
    incomplete.pop_back();
    bool rejected = false;
    try { solve_periodic_surface_energy_balance(system, incomplete, {300.0}); }
    catch (const std::invalid_argument&) { rejected = true; }
    require(rejected, "missing monthly forcing was silently accepted");
    PeriodicSurfaceEnergyOptions options;
    options.maximum_periodic_iterations = 1;
    rejected = false;
    try { solve_periodic_surface_energy_balance(system, forcing, {100.0}, options); }
    catch (const std::runtime_error&) { rejected = true; }
    require(rejected, "unconverged periodic year was published as a solution");
}

}  // namespace

int main() {
    int failures = 0;
    const std::array<std::pair<const char*, void (*)()>, 6> tests{{
        {"equilibrium/extreme capacity", equilibrium_and_extreme_capacity},
        {"monthly/annual conservation", monthly_and_annual_ledgers_are_conservative},
        {"initial guess independence", initial_guess_does_not_select_an_imposed_climate},
        {"mixed-capacity residual norm", mixed_capacity_residual_norm_counterexample_converges},
        {"seasonal phase/amplitude refinement", temporal_refinement_recovers_analytic_seasonal_phase_and_amplitude},
        {"invalid/unconverged inputs", incomplete_or_unconverged_years_fail_explicitly},
    }};
    for (const auto& test : tests) {
        try { test.second(); }
        catch (const std::exception& error) {
            std::cerr << test.first << ": " << error.what() << '\n';
            ++failures;
        }
    }
    return failures == 0 ? 0 : 1;
}
