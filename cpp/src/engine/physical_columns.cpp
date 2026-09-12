#include "physical_columns.hpp"

#include "types/core.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <string>

namespace magic_geo::detail {
namespace {

void require_nonnegative(double value, const char* name) {
    if (!std::isfinite(value) || value < 0.0) {
        throw std::runtime_error(std::string(name) + " must be finite and nonnegative");
    }
}

void require_positive(double value, const char* name) {
    if (!std::isfinite(value) || value <= 0.0) {
        throw std::runtime_error(std::string(name) + " must be finite and positive");
    }
}

double finite_result(long double value, const char* name) {
    if (!std::isfinite(value) ||
        std::abs(value) > static_cast<long double>(std::numeric_limits<double>::max())) {
        throw std::runtime_error(std::string(name) + " exceeds the finite double range");
    }
    return static_cast<double>(value);
}

double positive_result(long double value, const char* name) {
    const double result = finite_result(value, name);
    if (!(result > 0.0)) {
        throw std::runtime_error(std::string(name) + " is not representable as a positive double");
    }
    return result;
}

}  // namespace

PrescribedClimateColumns build_prescribed_climate_columns(
    const std::vector<PrescribedSurfaceColumn>& surfaces,
    const PrescribedAtmosphereOptions& options
) {
    if (surfaces.empty()) {
        throw std::runtime_error("prescribed climate columns require at least one surface");
    }
    require_nonnegative(options.mean_surface_pressure_pa, "mean surface pressure");
    require_positive(options.gravity_m_s2, "gravity");
    require_positive(options.profile_temperature_k, "hydrostatic profile temperature");
    require_nonnegative(options.reference_infrared_optical_depth, "reference infrared optical depth");
    require_nonnegative(options.greenhouse_factor, "greenhouse factor");
    require_nonnegative(options.atmospheric_diffusivity_m2_s, "atmospheric diffusivity");

    long double total_area = 0.0L;
    double minimum_elevation = surfaces.front().interface_elevation_m;
    double maximum_elevation = minimum_elevation;
    for (const auto& surface : surfaces) {
        require_positive(surface.area_m2, "surface area");
        require_positive(surface.surface_heat_capacity_j_m2_k, "surface heat capacity");
        if (!std::isfinite(surface.interface_elevation_m)) {
            throw std::runtime_error("surface interface elevation must be finite");
        }
        total_area += surface.area_m2;
        minimum_elevation = std::min(minimum_elevation, surface.interface_elevation_m);
        maximum_elevation = std::max(maximum_elevation, surface.interface_elevation_m);
    }

    PrescribedClimateColumns result;
    result.total_area_m2 = positive_result(total_area, "total surface area");
    const long double scale_height =
        static_cast<long double>(CLIMATE_DRY_AIR_GAS_CONSTANT_J_KG_K) *
        options.profile_temperature_k / options.gravity_m_s2;
    result.atmospheric_scale_height_m = positive_result(scale_height, "atmospheric scale height");
    const std::size_t count = surfaces.size();
    result.columns.reserve(count);
    result.surface_pressure_pa.resize(count, 0.0);
    result.atmospheric_heat_capacity_j_m2_k.resize(count, 0.0);
    result.infrared_optical_depth.resize(count, 0.0);
    result.horizontal_conductivity_w_k.resize(count, 0.0);

    if (options.mean_surface_pressure_pa > 0.0) {
        if (minimum_elevation == maximum_elevation) {
            // Also preserves the exact uniform reference and avoids needless
            // logarithmic roundoff in the flat-column analytic limit.
            std::fill(result.surface_pressure_pa.begin(), result.surface_pressure_pa.end(),
                      options.mean_surface_pressure_pa);
        } else {
            std::vector<long double> exponents(count);
            std::vector<long double> weighted_exponents(count);
            long double largest_weighted_exponent = -std::numeric_limits<long double>::infinity();
            for (std::size_t i = 0; i < count; ++i) {
                // Subtract the datum before dividing: a large common height
                // cannot overflow an otherwise representable pressure ratio.
                exponents[i] = -(static_cast<long double>(surfaces[i].interface_elevation_m) -
                                 minimum_elevation) / scale_height;
                weighted_exponents[i] = std::log(static_cast<long double>(surfaces[i].area_m2)) +
                    exponents[i];
                if (!std::isfinite(weighted_exponents[i])) {
                    throw std::runtime_error("hydrostatic pressure exponent exceeds numerical range");
                }
                largest_weighted_exponent = std::max(largest_weighted_exponent, weighted_exponents[i]);
            }
            long double scaled_area_weight = 0.0L;
            for (long double weighted_exponent : weighted_exponents) {
                scaled_area_weight += std::exp(weighted_exponent - largest_weighted_exponent);
            }
            const long double log_normalizer = largest_weighted_exponent + std::log(scaled_area_weight);
            const long double log_pressure_area =
                std::log(static_cast<long double>(options.mean_surface_pressure_pa)) + std::log(total_area);
            for (std::size_t i = 0; i < count; ++i) {
                result.surface_pressure_pa[i] = positive_result(
                    std::exp(log_pressure_area + exponents[i] - log_normalizer), "local surface pressure"
                );
            }
        }
    }

    long double pressure_area_sum = 0.0L;
    for (std::size_t i = 0; i < count; ++i) {
        const auto& surface = surfaces[i];
        const double pressure = result.surface_pressure_pa[i];
        double emissivity = 1.0;
        if (pressure > 0.0) {
            result.atmospheric_heat_capacity_j_m2_k[i] = positive_result(
                static_cast<long double>(CLIMATE_DRY_AIR_HEAT_CAPACITY_J_KG_K) * pressure /
                    options.gravity_m_s2, "atmospheric heat capacity"
            );
            if (options.reference_infrared_optical_depth > 0.0 && options.greenhouse_factor > 0.0) {
                result.infrared_optical_depth[i] = positive_result(
                    static_cast<long double>(options.reference_infrared_optical_depth) *
                        options.greenhouse_factor * pressure / CLIMATE_REFERENCE_PRESSURE_PA *
                        CLIMATE_REFERENCE_GRAVITY_M_S2 / options.gravity_m_s2,
                    "local infrared optical depth"
                );
                emissivity = positive_result(
                    1.0L / (1.0L + 0.75L * result.infrared_optical_depth[i]),
                    "effective longwave emissivity"
                );
            }
            if (options.atmospheric_diffusivity_m2_s > 0.0) {
                result.horizontal_conductivity_w_k[i] = positive_result(
                    static_cast<long double>(options.atmospheric_diffusivity_m2_s) *
                        result.atmospheric_heat_capacity_j_m2_k[i],
                    "integrated atmospheric conductivity"
                );
            }
        }
        const double total_capacity = positive_result(
            static_cast<long double>(surface.surface_heat_capacity_j_m2_k) +
                result.atmospheric_heat_capacity_j_m2_k[i], "total column heat capacity"
        );
        result.columns.push_back({surface.area_m2, total_capacity, emissivity});
        pressure_area_sum += static_cast<long double>(surface.area_m2) * pressure;
    }
    const long double actual_mean_pressure = pressure_area_sum / total_area;
    result.area_weighted_mean_surface_pressure_pa = finite_result(actual_mean_pressure, "mean surface pressure");
    result.mean_surface_pressure_residual_pa = finite_result(
        actual_mean_pressure - options.mean_surface_pressure_pa, "mean pressure residual"
    );
    result.total_atmospheric_mass_kg = options.mean_surface_pressure_pa > 0.0
        ? positive_result(pressure_area_sum / options.gravity_m_s2, "total atmospheric mass")
        : 0.0;
    result.atmospheric_mass_residual_kg = finite_result(
        (pressure_area_sum - static_cast<long double>(options.mean_surface_pressure_pa) * total_area) /
            options.gravity_m_s2, "atmospheric mass residual"
    );
    return result;
}

std::vector<PrescribedSurfaceColumn> prescribed_surface_columns_from_cells(
    const std::vector<Cell>& cells,
    double marine_mixed_layer_depth_m
) {
    require_positive(marine_mixed_layer_depth_m, "marine mixed-layer depth");
    if (cells.empty() || cells.size() > static_cast<std::size_t>(std::numeric_limits<int>::max())) {
        throw std::runtime_error("prescribed surface cell count is outside the nonempty index range");
    }
    std::vector<PrescribedSurfaceColumn> result;
    result.reserve(cells.size());
    for (std::size_t i = 0; i < cells.size(); ++i) {
        const Cell& cell = cells[i];
        if (cell.id != static_cast<int>(i)) {
            throw std::runtime_error("prescribed surface cells must be in canonical id order");
        }
        require_positive(cell.area_km2, "cell area");
        if (!std::isfinite(cell.elevation_m)) {
            throw std::runtime_error("cell surface elevation must be finite");
        }
        require_nonnegative(cell.water_depth_m, "cell water depth");
        if (cell.is_lake) {
            throw std::runtime_error("prescribed surface adapter requires fresh marine state without lakes");
        }
        if ((cell.is_water && (cell.water_body < 1 || cell.water_body > 3)) ||
            (!cell.is_water && cell.water_body != 0)) {
            throw std::runtime_error("prescribed surface water-body classification must match fresh marine state");
        }
        const double area_m2 = positive_result(
            static_cast<long double>(cell.area_km2) * 1.0e6L, "cell area in square metres"
        );
        double elevation_m = cell.elevation_m;
        double capacity = CLIMATE_LAND_SLAB_HEAT_CAPACITY_J_M2_K;
        if (cell.is_water) {
            if (!(cell.elevation_m < 0.0) || !(cell.water_depth_m > 0.0) ||
                cell.water_depth_m != -cell.elevation_m) {
                // apply_sea_level assigns depth from this exact unary negation.
                // No tolerance may silently authorize a different water surface.
                throw std::runtime_error("marine depth must equal the positive depth below the sea-level datum");
            }
            elevation_m = 0.0;
            capacity = positive_result(
                static_cast<long double>(CLIMATE_WATER_VOLUMETRIC_HEAT_CAPACITY_J_M3_K) *
                    std::min(cell.water_depth_m, marine_mixed_layer_depth_m),
                "marine slab heat capacity"
            );
        } else if (cell.water_depth_m != 0.0) {
            throw std::runtime_error("exposed land must have zero fresh-marine water depth");
        }
        result.push_back({area_m2, elevation_m, capacity});
    }
    return result;
}

}  // namespace magic_geo::detail
