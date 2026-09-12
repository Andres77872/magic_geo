#include "seasonal_climate.hpp"

#include "climate_transport.hpp"
#include "types/core.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <numbers>
#include <stdexcept>
#include <utility>

namespace magic_geo::detail {
namespace {

constexpr double STEFAN_BOLTZMANN_W_M2_K4 = 5.670374419e-8;

void require_positive_finite(double value, const char* message) {
    if (!std::isfinite(value) || value <= 0.0) {
        throw std::invalid_argument(message);
    }
}

}  // namespace

PrescribedSeasonalClimateOptions::PrescribedSeasonalClimateOptions() {
    integration.periodic.time_method = SurfaceEnergyTimeMethod::tr_bdf2;
}

PrescribedSeasonalClimate solve_prescribed_seasonal_climate(
    int mesh_backend,
    const std::vector<Cell>& cells,
    const PrescribedSeasonalClimateOptions& options,
    const std::vector<double>& initial_phase_temperature_k
) {
    require_positive_finite(options.radius_m, "seasonal climate radius must be positive and finite");
    require_positive_finite(options.year_duration_seconds, "seasonal climate year duration must be positive and finite");
    if (!std::isfinite(options.top_of_atmosphere_albedo) ||
        options.top_of_atmosphere_albedo < 0.0 || options.top_of_atmosphere_albedo > 1.0) {
        throw std::invalid_argument("seasonal climate TOA albedo must be finite and in [0,1]");
    }
    if (!initial_phase_temperature_k.empty() && initial_phase_temperature_k.size() != cells.size()) {
        throw std::invalid_argument("seasonal climate phase initial guess has the wrong cell count");
    }
    for (double temperature : initial_phase_temperature_k) {
        if (!std::isfinite(temperature) || temperature < 0.0) {
            throw std::invalid_argument("seasonal climate phase initial guess must be finite and nonnegative");
        }
    }

    PrescribedSeasonalClimate result;
    result.options = options;
    result.mesh_backend = mesh_backend;
    result.surfaces = prescribed_surface_columns_from_cells(cells, options.marine_mixed_layer_depth_m);
    result.physical_columns = build_prescribed_climate_columns(result.surfaces, options.atmosphere);
    const long double expected_area = 4.0L * std::numbers::pi_v<long double> *
        options.radius_m * options.radius_m;
    if (!std::isfinite(expected_area) ||
        std::abs(static_cast<long double>(result.physical_columns.total_area_m2) - expected_area) >
            2.0e-8L * expected_area) {
        throw std::invalid_argument("seasonal climate mesh area does not match the configured spherical radius");
    }
    result.transport_edges = build_climate_heat_transport_edges(
        mesh_backend, cells, result.physical_columns.horizontal_conductivity_w_k
    );
    result.atmospheric_scale_height_to_radius =
        result.physical_columns.atmospheric_scale_height_m / options.radius_m;
    for (std::size_t i = 0; i < cells.size(); ++i) {
        const Cell& cell = cells[i];
        const double geometric_latitude = std::atan2(cell.p.z, std::hypot(cell.p.x, cell.p.y));
        if (!std::isfinite(cell.lat) || std::abs(cell.lat) > std::numbers::pi / 2.0 ||
            std::abs(cell.lat - geometric_latitude) > 1.0e-9) {
            throw std::invalid_argument("seasonal climate latitude does not match the spherical cell position");
        }
        result.latitudes_rad.push_back(cell.lat);
        result.marine_surface.push_back(cell.is_water);
        result.water_depth_m.push_back(cell.water_depth_m);
        result.maximum_interface_elevation_to_radius = std::max(
            result.maximum_interface_elevation_to_radius,
            std::abs(result.surfaces[i].interface_elevation_m) / options.radius_m
        );
    }
    if (!std::isfinite(result.atmospheric_scale_height_to_radius) ||
        !std::isfinite(result.maximum_interface_elevation_to_radius)) {
        throw std::overflow_error("seasonal climate applicability ratio is not representable");
    }

    const SolarOrbitForcing solar(options.axial_tilt_deg, options.orbital_eccentricity,
        options.stellar_luminosity, options.forcing_refinement_level);
    result.forcing_intervals = solar.integration_intervals();
    if (result.forcing_intervals.size() > options.integration.maximum_accepted_steps_per_year / 2) {
        throw std::runtime_error("seasonal climate forcing already exceeds the adaptive step budget");
    }
    if (cells.size() > options.maximum_stored_forcing_values / result.forcing_intervals.size()) {
        throw std::runtime_error("seasonal climate dense forcing exceeds the configured value budget");
    }
    std::vector<SurfaceEnergyForcingInterval> intervals;
    intervals.reserve(result.forcing_intervals.size());
    std::vector<long double> annual_absorbed(cells.size(), 0.0L);
    for (std::size_t index = 0; index < result.forcing_intervals.size(); ++index) {
        const auto& orbital = result.forcing_intervals[index];
        SurfaceEnergyForcingInterval interval;
        interval.month_index = static_cast<int>(orbital.month_index);
        interval.duration_seconds = options.year_duration_seconds * orbital.duration_fraction_of_year;
        require_positive_finite(interval.duration_seconds, "seasonal climate forcing duration is not representable");
        interval.absorbed_shortwave_w_m2.reserve(cells.size());
        for (std::size_t i = 0; i < cells.size(); ++i) {
            const double incident = solar.interval_mean_insolation_w_m2(cells[i].lat, index);
            // Keep this one binary64 product identical to replay from shared
            // forcing nodes. Extended precision followed by a cast can double
            // round rare products and change their last bit. Positive-factor
            // checks below detect underflow without changing that arithmetic.
            const double absorbed = (1.0 - options.top_of_atmosphere_albedo) * incident;
            if (!std::isfinite(absorbed) || absorbed < 0.0 ||
                (incident > 0.0 && options.top_of_atmosphere_albedo < 1.0 && absorbed == 0.0)) {
                throw std::overflow_error("seasonal climate absorbed sunlight is not representable");
            }
            interval.absorbed_shortwave_w_m2.push_back(absorbed);
            annual_absorbed[i] += static_cast<long double>(absorbed) * orbital.duration_fraction_of_year;
        }
        intervals.push_back(std::move(interval));
    }
    std::vector<double> initial = initial_phase_temperature_k;
    if (initial.empty()) {
        initial.reserve(cells.size());
        for (std::size_t i = 0; i < cells.size(); ++i) {
            const long double fourth_power = annual_absorbed[i] /
                (static_cast<long double>(result.physical_columns.columns[i].longwave_emissivity) *
                    STEFAN_BOLTZMANN_W_M2_K4);
            const double temperature = static_cast<double>(std::sqrt(std::sqrt(fourth_power)));
            if (!std::isfinite(temperature)) {
                throw std::overflow_error("seasonal climate equilibrium initial guess is not representable");
            }
            initial.push_back(temperature);
        }
    }
    const SurfaceEnergySystem system(result.physical_columns.columns, result.transport_edges);
    result.solution = solve_adaptive_periodic_surface_energy_balance(system, intervals, initial, options.integration);
    return result;
}

}  // namespace magic_geo::detail
