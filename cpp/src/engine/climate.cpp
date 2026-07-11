#include "internal.hpp"

namespace magic_geo::detail {

double wrap_angle(double radians) {
    while (radians > PI) {
        radians -= 2.0 * PI;
    }
    while (radians < -PI) {
        radians += 2.0 * PI;
    }
    return radians;
}

double local_relief(const std::vector<Cell>& cells, int i) {
    if (cells[i].neighbors.empty()) {
        return 0.0;
    }
    double avg = 0.0;
    for (int j : cells[i].neighbors) {
        avg += cells[j].elevation_m;
    }
    avg /= static_cast<double>(cells[i].neighbors.size());
    return std::max(0.0, cells[i].elevation_m - avg);
}

std::pair<double, double> prevailing_wind_components(double lat, double day_length_hours) {
    const double lat_abs_deg = std::abs(lat * DEG);
    const double rotation = clamp(24.0 / std::max(1.0, day_length_hours), 0.35, 2.6);
    double east = -1.0;
    double north = lat >= 0.0 ? -0.22 : 0.22;
    if (lat_abs_deg >= 30.0 && lat_abs_deg < 60.0) {
        east = 1.0;
        north = lat >= 0.0 ? 0.16 : -0.16;
    } else if (lat_abs_deg >= 60.0) {
        east = -0.75;
        north = lat >= 0.0 ? -0.18 : 0.18;
    }
    east *= rotation;
    const double len = std::max(1.0e-9, std::sqrt(east * east + north * north));
    return {east / len, north / len};
}

std::pair<int, double> upwind_neighbor_for_wind(const std::vector<Cell>& cells, int i, double wind_east, double wind_north) {
    const Cell& cell = cells[i];
    int upwind = -1;
    double best_alignment = -1.0;
    for (int neighbor : cell.neighbors) {
        const Cell& source = cells[neighbor];
        const double dx = wrap_angle(cell.lon - source.lon) * std::cos(cell.lat);
        const double dy = cell.lat - source.lat;
        const double len = std::sqrt(dx * dx + dy * dy);
        if (len < 1.0e-9) {
            continue;
        }
        const double alignment = (dx / len) * wind_east + (dy / len) * wind_north;
        if (alignment > best_alignment) {
            best_alignment = alignment;
            upwind = neighbor;
        }
    }
    return {upwind, best_alignment};
}

std::pair<double, double> orographic_and_shadow_factors(const std::vector<Cell>& cells, int i, double wind_east, double wind_north) {
    const Cell& cell = cells[i];
    const auto [upwind, best_alignment] = upwind_neighbor_for_wind(cells, i, wind_east, wind_north);
    if (upwind < 0 || best_alignment < 0.12) {
        return {1.0, 1.0};
    }
    const double upwind_elevation = cells[upwind].elevation_m;
    const double climb = std::max(0.0, cell.elevation_m - upwind_elevation);
    const double descent = std::max(0.0, upwind_elevation - cell.elevation_m);
    const double oro = 1.0 + 0.42 * clamp(climb / 1600.0, 0.0, 1.0) * best_alignment;
    const double shadow = 1.0 - 0.48 * clamp(descent / 1800.0, 0.0, 1.0) * best_alignment;
    return {clamp(oro, 0.70, 1.45), clamp(shadow, 0.48, 1.0)};
}

struct HumidityTransport {
    double index = 0.0;
    double upwind_ocean_fetch_km = 0.0;
    double factor = 1.0;
};

HumidityTransport humidity_transport_along_wind(
    const Params& params,
    const std::vector<Cell>& cells,
    int start,
    double wind_east,
    double wind_north
) {
    const int max_steps = clamp(params.cell_count / 256 + 10, 10, 34);
    int current = start;
    double parcel = cells[start].is_water ? 0.72 : 0.08;
    double fetch_km = cells[start].is_water ? 120.0 : 0.0;
    double rainout = 0.0;
    double decay = 1.0;
    std::set<int> visited;
    visited.insert(start);

    for (int step = 0; step < max_steps; ++step) {
        const auto [source_id, alignment] = upwind_neighbor_for_wind(cells, current, wind_east, wind_north);
        if (source_id < 0 || alignment < 0.10 || visited.count(source_id) > 0) {
            break;
        }
        const Cell& source = cells[source_id];
        const Cell& target = cells[current];
        const double distance_km = std::max(1.0, angular_distance(source.p, target.p) * params.radius_km);
        if (source.is_water) {
            const double source_strength = source.water_body == 1 ? 1.0 : (source.water_body == 2 ? 0.82 : 0.68);
            fetch_km += distance_km * source_strength * decay;
            parcel += decay * source_strength * clamp(distance_km / 620.0, 0.10, 0.46);
        } else if (source.is_lake || source.water_body == 4 || source.water_body == 5) {
            parcel += 0.12 * decay;
        } else {
            parcel *= 0.93;
        }

        const double climb = std::max(0.0, target.elevation_m - source.elevation_m);
        const double descent = std::max(0.0, source.elevation_m - target.elevation_m);
        rainout += decay * clamp(climb / 2600.0, 0.0, 1.2);
        parcel *= 1.0 - 0.18 * clamp(climb / 2600.0, 0.0, 1.0);
        parcel *= 1.0 - 0.04 * clamp(descent / 2200.0, 0.0, 1.0);

        current = source_id;
        visited.insert(source_id);
        decay *= 0.88;
    }

    HumidityTransport transport;
    transport.upwind_ocean_fetch_km = fetch_km;
    transport.index = clamp(parcel / (1.0 + 0.18 * rainout), 0.0, 1.35);
    transport.factor = clamp(0.82 + 0.28 * transport.index, 0.70, 1.20);
    return transport;
}

std::pair<double, double> ocean_current_components(double lat, double lon, double day_length_hours) {
    const double lat_abs_deg = std::abs(lat * DEG);
    const double rotation = clamp(24.0 / std::max(1.0, day_length_hours), 0.45, 2.4);
    double east = -0.85;
    double north = 0.0;
    if (lat_abs_deg < 12.0) {
        east = -1.0;
        north = 0.16 * std::sin(lon);
    } else if (lat_abs_deg < 35.0) {
        east = -0.72;
        north = (lat >= 0.0 ? 0.42 : -0.42) * std::sin(lon);
    } else if (lat_abs_deg < 62.0) {
        east = 0.86;
        north = (lat >= 0.0 ? -0.34 : 0.34) * std::cos(lon);
    } else {
        east = -0.42;
        north = lat >= 0.0 ? -0.22 : 0.22;
    }
    east *= std::sqrt(rotation);
    const double len = std::max(1.0e-9, std::sqrt(east * east + north * north));
    return {east / len, north / len};
}

void compute_climate(const Params& params, std::vector<Cell>& cells) {
    const std::vector<int> dist = ocean_distance(cells);
    const int n = static_cast<int>(cells.size());
    const double pressure = std::max(0.01, params.atmosphere_pressure_bar);
    const double pressure_temp_adj = 4.5 * std::log(pressure);
    const double pressure_precip_factor = clamp(std::pow(pressure, 0.35), 0.35, 1.85);
    const double gravity_precip_factor = clamp(1.08 - 0.10 * (params.gravity_g - 1.0), 0.65, 1.35);
    const double stellar_temperature_forcing_c =
        climate_stellar_temperature_forcing_c(params);
    const double greenhouse_temperature_forcing_c =
        climate_greenhouse_temperature_forcing_c(params);
    const double thermal_moisture_capacity_factor =
        climate_thermal_moisture_capacity_factor(params);
    const double rotation_band_shift = clamp((params.day_length_hours - 24.0) / 24.0 * 5.0, -7.0, 9.0);
    const double eccentricity_season_factor = 1.0 + 1.8 * clamp(params.orbital_eccentricity, 0.0, 0.8);
    double local_temperature_adjustment_area_sum = 0.0;
    double total_cell_area_km2 = 0.0;
    for (int i = 0; i < n; ++i) {
        const Cell& cell = cells[static_cast<std::size_t>(i)];
        const double oceanity = std::exp(-static_cast<double>(dist[static_cast<std::size_t>(i)]) / 7.5);
        const auto current = ocean_current_components(cell.lat, cell.lon, params.day_length_hours);
        const double poleward_current = cell.lat >= 0.0 ? current.second : -current.second;
        const double current_temp = oceanity * clamp(
            3.8 * poleward_current + 1.2 * std::cos(cell.lat) * std::sin(cell.lon),
            -4.5,
            4.5
        );
        const double lapse = std::max(0.0, cell.elevation_m) *
            params.lapse_rate_c_per_km / 1000.0;
        const double local_adjustment = -lapse +
            (cell.is_water ? CLIMATE_MARINE_ANNUAL_TEMPERATURE_OFFSET_C : 0.0) +
            current_temp;
        const double area_km2 = std::max(0.0, cell.area_km2);
        local_temperature_adjustment_area_sum += local_adjustment * area_km2;
        total_cell_area_km2 += area_km2;
    }
    const double local_temperature_adjustment_area_mean = total_cell_area_km2 > 0.0
        ? local_temperature_adjustment_area_sum / total_cell_area_km2
        : 0.0;
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        Cell& cell = cells[i];
        cell.temperature_monthly_c.assign(static_cast<std::size_t>(params.months), 0.0);
        cell.precipitation_monthly_mm.assign(static_cast<std::size_t>(params.months), 0.0);
        cell.wind_monthly_east.assign(static_cast<std::size_t>(params.months), 0.0);
        cell.wind_monthly_north.assign(static_cast<std::size_t>(params.months), 0.0);
        const auto wind = prevailing_wind_components(cell.lat, params.day_length_hours);
        cell.wind_east = wind.first;
        cell.wind_north = wind.second;
        const auto moisture_factors = orographic_and_shadow_factors(cells, i, cell.wind_east, cell.wind_north);
        cell.orographic_factor = moisture_factors.first;
        cell.rain_shadow_factor = moisture_factors.second;
        const HumidityTransport humidity = humidity_transport_along_wind(params, cells, i, cell.wind_east, cell.wind_north);
        cell.humidity_transport_index = humidity.index;
        cell.upwind_ocean_fetch_km = humidity.upwind_ocean_fetch_km;
        cell.advected_moisture_factor = humidity.factor;
        const double lat_abs_deg = std::abs(cell.lat * DEG);
        const double oceanity = std::exp(-static_cast<double>(dist[i]) / 7.5);
        const double continentality = 1.0 - oceanity;
        const double subtropical_center = 30.0 + rotation_band_shift;
        const double midlatitude_center = 55.0 + 0.5 * rotation_band_shift;
        const double tropical_ascent = std::exp(-(lat_abs_deg * lat_abs_deg) / (2.0 * 13.0 * 13.0));
        const double subtropical_high = std::exp(-std::pow(lat_abs_deg - subtropical_center, 2.0) / (2.0 * 9.5 * 9.5));
        const double subpolar_low = std::exp(-std::pow(lat_abs_deg - midlatitude_center, 2.0) / (2.0 * 11.0 * 11.0));
        const double polar_high = std::exp(-std::pow(lat_abs_deg - 82.0, 2.0) / (2.0 * 12.0 * 12.0));
        if (lat_abs_deg < 18.0) {
            cell.atmospheric_cell = 0;
        } else if (std::abs(lat_abs_deg - subtropical_center) < 14.0) {
            cell.atmospheric_cell = 1;
        } else if (lat_abs_deg < 66.0) {
            cell.atmospheric_cell = 2;
        } else {
            cell.atmospheric_cell = 3;
        }
        cell.vertical_velocity_index = clamp(
            0.58 * tropical_ascent + 0.36 * subpolar_low -
                0.46 * subtropical_high - 0.24 * polar_high +
                0.16 * std::max(0.0, cell.orographic_factor - 1.0),
            -1.0,
            1.0
        );
        cell.wind_divergence_index = clamp(
            0.54 * subtropical_high + 0.30 * polar_high -
                0.46 * tropical_ascent - 0.34 * subpolar_low,
            -1.0,
            1.0
        );
        cell.surface_pressure_anomaly_hpa = clamp(
            10.5 * cell.wind_divergence_index - 3.0 * cell.vertical_velocity_index,
            -22.0,
            22.0
        );
        const double circulation_precip_factor = clamp(
            1.0 + 0.22 * std::max(0.0, cell.vertical_velocity_index) -
                0.18 * std::max(0.0, cell.wind_divergence_index),
            0.66,
            1.26
        );
        const auto current = ocean_current_components(cell.lat, cell.lon, params.day_length_hours);
        cell.ocean_current_east = current.first * oceanity;
        cell.ocean_current_north = current.second * oceanity;
        const double poleward_current = cell.lat >= 0.0 ? current.second : -current.second;
        const double current_temp = oceanity * clamp(
            3.8 * poleward_current + 1.2 * std::cos(cell.lat) * std::sin(cell.lon),
            -4.5,
            4.5
        );
        cell.ocean_current_temperature_c = current_temp;
        cell.ocean_current_moisture_factor = clamp(
            1.0 + oceanity * (0.045 * std::max(0.0, current_temp) - 0.035 * std::max(0.0, -current_temp)),
            0.72,
            1.28
        );
        const double lum_adj = stellar_temperature_forcing_c;
        const double greenhouse_adj = greenhouse_temperature_forcing_c;
        const double latitude_temperature_area_mean_offset_c =
            CLIMATE_LATITUDE_TEMPERATURE_GRADIENT_C /
            (CLIMATE_LATITUDE_TEMPERATURE_EXPONENT + 1.0);
        const double latitude_temp = params.base_temperature_c +
            latitude_temperature_area_mean_offset_c -
            CLIMATE_LATITUDE_TEMPERATURE_GRADIENT_C * std::pow(
                std::sin(std::abs(cell.lat)), CLIMATE_LATITUDE_TEMPERATURE_EXPONENT
            );
        const double lapse = std::max(0.0, cell.elevation_m) * params.lapse_rate_c_per_km / 1000.0;
        double annual_temp = 0.0;
        double annual_precip = 0.0;
        double seasonal_wind_speed_sum = 0.0;
        double seasonal_wind_reversal_sum = 0.0;
        const double axial_wind_factor = clamp(params.axial_tilt_deg / 23.5, 0.12, 2.4) * eccentricity_season_factor;
        const double monsoon_band = std::exp(-(lat_abs_deg * lat_abs_deg) / (2.0 * 28.0 * 28.0));
        const double base_wind_len = std::max(
            1.0e-9,
            std::sqrt(cell.wind_east * cell.wind_east + cell.wind_north * cell.wind_north)
        );
        for (int month = 0; month < params.months; ++month) {
            const double season = std::cos(2.0 * PI * (static_cast<double>(month) - 6.0) / static_cast<double>(params.months));
            const double seasonal_amp = (9.0 + 16.0 * continentality) * (params.axial_tilt_deg / 23.5) *
                eccentricity_season_factor * std::sin(cell.lat);
            const double temp = latitude_temp + lum_adj + greenhouse_adj + pressure_temp_adj +
                seasonal_amp * season - lapse +
                (cell.is_water ? CLIMATE_MARINE_ANNUAL_TEMPERATURE_OFFSET_C : 0.0) + current_temp -
                local_temperature_adjustment_area_mean;
            annual_temp += temp;
            const double equator = std::exp(-(lat_abs_deg * lat_abs_deg) / (2.0 * 18.0 * 18.0));
            const double subtropic = std::exp(-std::pow(lat_abs_deg - (30.0 + rotation_band_shift), 2.0) / (2.0 * 10.0 * 10.0));
            const double mid = std::exp(-std::pow(lat_abs_deg - (55.0 + 0.5 * rotation_band_shift), 2.0) / (2.0 * 13.0 * 13.0));
            const double relief = clamp(local_relief(cells, i) / 2200.0, 0.0, 1.0);
            const double hemisphere_season = season * (cell.lat >= 0.0 ? 1.0 : -1.0);
            const double monsoon_surface_exposure = cell.is_water ? 0.30 : 0.70 + 0.30 * continentality;
            const double monsoon = CLIMATE_SEASONAL_MONSOON_PRECIPITATION_STRENGTH *
                hemisphere_season * monsoon_surface_exposure * monsoon_band;
            const double monsoon_precipitation_factor = clamp(
                1.0 + monsoon,
                CLIMATE_SEASONAL_MONSOON_PRECIPITATION_MIN_FACTOR,
                CLIMATE_SEASONAL_MONSOON_PRECIPITATION_MAX_FACTOR
            );
            const double monsoon_wind = clamp(season * axial_wind_factor * continentality * monsoon_band, -1.25, 1.25);
            double raw_wind_east = cell.wind_east - 1.12 * monsoon_wind * cell.wind_east +
                0.18 * oceanity * season * std::sin(cell.lon);
            double raw_wind_north = cell.wind_north +
                0.76 * monsoon_wind * (cell.lat >= 0.0 ? 1.0 : -1.0) +
                0.12 * oceanity * season * std::cos(cell.lon);
            const double raw_wind_len = std::max(1.0e-9, std::sqrt(raw_wind_east * raw_wind_east + raw_wind_north * raw_wind_north));
            const double monthly_wind_speed = clamp(
                0.72 + 0.20 * oceanity + 0.16 * std::abs(monsoon_wind) + 0.10 * std::abs(cell.wind_divergence_index),
                0.42,
                1.15
            );
            const double monthly_wind_east = clamp(raw_wind_east / raw_wind_len * monthly_wind_speed, -1.0, 1.0);
            const double monthly_wind_north = clamp(raw_wind_north / raw_wind_len * monthly_wind_speed, -1.0, 1.0);
            cell.wind_monthly_east[static_cast<std::size_t>(month)] = monthly_wind_east;
            cell.wind_monthly_north[static_cast<std::size_t>(month)] = monthly_wind_north;
            const double monthly_len = std::max(
                1.0e-9,
                std::sqrt(monthly_wind_east * monthly_wind_east + monthly_wind_north * monthly_wind_north)
            );
            seasonal_wind_speed_sum += monthly_len;
            const double wind_dot = (monthly_wind_east * cell.wind_east + monthly_wind_north * cell.wind_north) /
                (monthly_len * base_wind_len);
            seasonal_wind_reversal_sum += clamp((1.0 - wind_dot) * 0.5, 0.0, 1.0);
            double annual = 170.0 + 1450.0 * equator + 680.0 * mid - 610.0 * subtropic + 560.0 * oceanity + 320.0 * relief;
            const double cold_current_drying_index = clamp(-current_temp / 4.5, 0.0, 1.0);
            const double subtropical_drying_factor = clamp(
                1.0 - params.subtropical_drying_strength * subtropic *
                    (1.0 + 0.15 * cold_current_drying_index),
                CLIMATE_SUBTROPICAL_DRYING_MIN_FACTOR,
                1.0
            );
            annual *= cell.is_water ? 1.20 : 1.0;
            annual *= params.precipitation_scale * pressure_precip_factor * gravity_precip_factor *
                cell.orographic_factor * cell.rain_shadow_factor * cell.ocean_current_moisture_factor *
                cell.advected_moisture_factor * circulation_precip_factor *
                subtropical_drying_factor * monsoon_precipitation_factor;
            double monthly_precip = std::max(20.0, annual) / static_cast<double>(params.months);
            // Preserve the exact Earth-reference arithmetic path while applying the
            // configured moisture capacity to every monthly value, including the
            // diagnostic minimum-rainfall branch.
            if (thermal_moisture_capacity_factor != 1.0) {
                monthly_precip *= thermal_moisture_capacity_factor;
            }
            cell.temperature_monthly_c[static_cast<std::size_t>(month)] = temp;
            cell.precipitation_monthly_mm[static_cast<std::size_t>(month)] = monthly_precip;
            annual_precip += monthly_precip;
        }
        cell.temperature_c = annual_temp / static_cast<double>(params.months);
        cell.precipitation_mm_y = annual_precip;
        cell.mean_seasonal_wind_speed = seasonal_wind_speed_sum / static_cast<double>(params.months);
        cell.seasonal_wind_reversal_index = clamp(
            seasonal_wind_reversal_sum / static_cast<double>(params.months),
            0.0,
            1.0
        );
        const double pet = std::max(0.0, cell.temperature_c + 8.0) * 31.0;
        const double water_evaporation = (cell.water_body == 1 || cell.water_body == 2 || cell.water_body == 3) ?
            (760.0 + 28.0 * std::max(0.0, cell.temperature_c) + 90.0 * cell.ocean_current_moisture_factor) :
            0.0;
        const double land_evaporation = std::min(
            std::max(0.0, annual_precip) * clamp(0.38 + 0.22 * oceanity, 0.28, 0.72),
            pet * clamp(0.42 + 0.24 * cell.humidity_transport_index, 0.25, 0.86)
        );
        cell.vapor_evaporation_mm_y = clamp(cell.is_water ? water_evaporation : land_evaporation, 0.0, 2400.0);
        cell.precipitation_recycling_fraction = clamp(
            (cell.is_water ? 0.06 : 0.12) +
                0.34 * continentality +
                0.14 * clamp(cell.humidity_transport_index, 0.0, 1.0) +
                0.08 * clamp(cell.orographic_factor - 1.0, 0.0, 0.6),
            0.03,
            cell.is_water ? 0.22 : 0.68
        );
        const double recycled_source = std::min(
            annual_precip,
            cell.vapor_evaporation_mm_y * cell.precipitation_recycling_fraction
        );
        cell.moisture_convergence_mm_y = std::max(0.0, annual_precip - recycled_source);
        cell.orographic_rainout_mm_y = annual_precip * clamp(
            0.46 * std::max(0.0, cell.orographic_factor - 1.0) +
                0.18 * std::max(0.0, 1.0 - cell.rain_shadow_factor),
            0.0,
            0.55
        );
        cell.vapor_deficit_mm_y = std::max(0.0, pet - annual_precip);
        cell.vapor_budget_residual_mm_y = annual_precip - (recycled_source + cell.moisture_convergence_mm_y);
    }
}

}  // namespace magic_geo::detail
