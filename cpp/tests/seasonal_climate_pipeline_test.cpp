#include "magic_geo/native.hpp"

#include <algorithm>
#include <charconv>
#include <chrono>
#include <cmath>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace {

void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

// Bounded readers for the compact generated schema. Nested objects/arrays and
// escaped strings are skipped structurally; numeric parsing ignores locale.
std::size_t value_end(std::string_view text, std::size_t begin) {
    require(begin < text.size(), "truncated JSON value");
    if (text[begin] == '{' || text[begin] == '[') {
        int depth = 0;
        bool quoted = false, escaped = false;
        for (std::size_t i = begin; i < text.size(); ++i) {
            const char c = text[i];
            if (quoted) {
                if (escaped) escaped = false;
                else if (c == '\\') escaped = true;
                else if (c == '"') quoted = false;
            } else if (c == '"') quoted = true;
            else if (c == '{' || c == '[') ++depth;
            else if ((c == '}' || c == ']') && --depth == 0) return i + 1;
        }
    } else if (text[begin] == '"') {
        bool escaped = false;
        for (std::size_t i = begin + 1; i < text.size(); ++i) {
            if (escaped) escaped = false;
            else if (text[i] == '\\') escaped = true;
            else if (text[i] == '"') return i + 1;
        }
    } else {
        const auto end = text.find_first_of(",}]", begin);
        return end == std::string_view::npos ? text.size() : end;
    }
    throw std::runtime_error("unterminated JSON value");
}

std::string_view field(std::string_view object, std::string_view key) {
    require(!object.empty() && object.front() == '{', "expected JSON object");
    std::size_t pos = 1;
    while (pos < object.size() && object[pos] != '}') {
        const auto end = value_end(object, pos);
        require(object[pos] == '"' && end < object.size() && object[end] == ':', "invalid object key");
        const auto begin_value = end + 1;
        const auto end_value = value_end(object, begin_value);
        if (object.substr(pos + 1, end - pos - 2) == key) return object.substr(begin_value, end_value - begin_value);
        pos = end_value;
        if (pos < object.size() && object[pos] == ',') ++pos;
    }
    throw std::runtime_error("missing JSON key: " + std::string(key));
}

std::vector<std::string_view> elements(std::string_view array) {
    require(array.size() >= 2 && array.front() == '[' && array.back() == ']', "expected JSON array");
    std::vector<std::string_view> result;
    std::size_t pos = 1;
    while (pos < array.size() - 1) {
        const auto end = value_end(array, pos);
        result.push_back(array.substr(pos, end - pos));
        pos = end;
        if (pos < array.size() - 1) {
            require(array[pos] == ',', "invalid JSON array separator");
            ++pos;
        }
    }
    return result;
}

double number(std::string_view value) {
    double result = 0;
    const auto parsed = std::from_chars(value.data(), value.data() + value.size(), result);
    require(parsed.ec == std::errc{} && parsed.ptr == value.data() + value.size() && std::isfinite(result),
            "invalid finite JSON number");
    return result;
}

double number(std::string_view object, std::string_view key) { return number(field(object, key)); }

std::vector<double> numbers(std::string_view object, std::string_view key) {
    std::vector<double> result;
    for (auto item : elements(field(object, key))) result.push_back(number(item));
    return result;
}

void near(double actual, double expected, double tolerance, const char* message) {
    require(std::isfinite(actual) && std::isfinite(expected) && std::abs(actual - expected) <= tolerance, message);
}

magic_geo::Params parameters() {
    magic_geo::Params params;
    params.name = "seasonal_climate_pipeline";
    params.cell_count = 128;
    params.plate_count = 8;
    params.erosion_iterations = 0;
    params.threads = 1;
    params.float_precision = 8;
    // Leave temperature_model untouched: the public default must retain the
    // native seasonal witness and drive all downstream temperature consumers.
    return params;
}

std::string generate(const magic_geo::Params& params) {
    magic_geo::ComputeOptions compute;
    compute.compute_backend = 1;
    return magic_geo::generate_geo_world_json(params, compute);
}

void validation_and_frozen_c_adapters() {
    using Model = magic_geo::ClimateTemperatureModel;
    require(magic_geo::Params{}.temperature_model == Model::prescribed_seasonal,
            "new C++ generation does not default to the seasonal producer");
    magic_geo::CConfig c{};
    require(magic_geo::params_from_c_config(c).temperature_model == Model::legacy_empirical,
            "frozen v1 C adapter selected seasonal temperatures");
    magic_geo::CConfigV2 v2{};
    require(magic_geo::params_from_c_config(v2.base).temperature_model == Model::legacy_empirical,
            "frozen v2 C adapter selected seasonal temperatures");
    magic_geo::CConfigV3 v3{};
    require(magic_geo::params_from_c_config(v3).temperature_model == Model::legacy_empirical,
            "frozen v3 C adapter selected seasonal temperatures");
    const auto rejects = [](magic_geo::Params params, std::string_view expected) {
        try { generate(params); }
        catch (const std::exception& error) {
            require(std::string_view(error.what()).find(expected) != std::string_view::npos,
                    "validation failed for an unexpected reason");
            return;
        }
        throw std::runtime_error("invalid public climate configuration was accepted");
    };
    auto params = parameters();
    params.temperature_model = static_cast<Model>(99);
    rejects(params, "temperature_model");
    params = parameters(); params.reference_infrared_optical_depth = -1;
    rejects(params, "reference_infrared_optical_depth");
    params.reference_infrared_optical_depth = std::numeric_limits<double>::quiet_NaN();
    rejects(params, "reference_infrared_optical_depth");
    // A finite optical depth has no invented upper limit in configuration
    // validation. The later deliberately invalid cell count avoids a solve.
    params.reference_infrared_optical_depth = std::numeric_limits<double>::max();
    params.cell_count = 0;
    rejects(params, "cell_count");
    params = parameters(); params.temperature_model = Model::legacy_empirical;
    params.base_temperature_c = std::numeric_limits<double>::quiet_NaN();
    rejects(params, "base_temperature_c");
    params.base_temperature_c = 15; params.lapse_rate_c_per_km = std::numeric_limits<double>::infinity();
    rejects(params, "lapse_rate_c_per_km");
}

void retained_temperatures_and_downstream_history(const std::string& world) {
    const auto model = field(world, "climate_model");
    require(field(model, "model_type") == "\"prescribed_seasonal_surface_energy_v1\"", "seasonal world advertises legacy climate");
    require(field(model, "post_solve_temperature_adjustments") == "false", "temperature offsets were advertised");
    require(field(model, "lake_ice_cloud_biome_feedback_resolved") == "false", "prescribed feedback limitation missing");
    require(model.find("\"base_temperature_c\"") == std::string_view::npos, "obsolete mean leaked into seasonal metadata");
    const auto energy = field(world, "climate_energy_model");
    require(field(energy, "ownership") == "\"native_temperature_producer\"", "retained energy is diagnostic-only");
    require(number(energy, "mean_surface_pressure_pa") == 100000 && number(energy, "gravity_m_s2") == 9.80665,
            "planet pressure/gravity mapping changed units");
    require(number(energy, "radius_m") == 6371000 && number(energy, "reference_infrared_optical_depth") == 1,
            "planet radius/reference opacity mapping is wrong");
    const auto achieved = field(energy, "achieved");
    require(number(achieved, "monthly_refinement_confirmations") == 2, "producer skipped independent monthly grid checks");
    require(number(achieved, "maximum_local_error_ratio") <= 1 && number(achieved, "maximum_numerical_error_ratio") <= 1,
            "producer accepted failed local accuracy checks");
    require(number(achieved, "completed_physical_solves") >= 1, "no retained producer solve");
    require(number(achieved, "total_step_attempts") >= number(achieved, "accepted_steps_per_year"),
            "work accounting omits accepted cycle");

    const auto records = elements(field(world, "climate_energy_balance_records"));
    const auto cells = elements(field(world, "cells"));
    require(records.size() == 128 && cells.size() == records.size(), "retained columns do not cover generated cells");
    const auto durations = numbers(energy, "monthly_duration_seconds");
    require(durations.size() == 12, "wrong retained calendar");
    const double year = number(energy, "year_duration_seconds");
    const auto stages = elements(field(world, "hydrologic_water_budget_history"));
    require(stages.size() >= 2, "initial/final hydrology stages were skipped");
    require(field(stages.front(), "stage") == "\"initial_climate_hydrology\"" &&
            field(stages.back(), "stage") == "\"cryosphere_coupling\"", "cache propagation missed final stabilization");
    const auto final_hydrology_temperature = numbers(stages.back(), "temperature_c_by_cell");
    require(final_hydrology_temperature.size() == cells.size(), "final hydrology temperature snapshot is incomplete");
    long double area_sum = 0, temperature_integral = 0;
    for (std::size_t i = 0; i < cells.size(); ++i) {
        require(number(records[i], "cell_id") == static_cast<double>(i), "retained cell order changed");
        const auto kelvin = numbers(records[i], "monthly_mean_temperature_k");
        const auto celsius = numbers(cells[i], "temperature_monthly_c");
        require(kelvin.size() == 12 && celsius.size() == 12, "incomplete generated monthly temperatures");
        long double local_integral = 0;
        const long double area = number(records[i], "area_m2");
        area_sum += area;
        for (std::size_t m = 0; m < 12; ++m) {
            near(celsius[m], kelvin[m] - 273.15, 5.1e-9, "downstream monthly temperature differs from retained energy mean");
            local_integral += static_cast<long double>(durations[m]) * kelvin[m];
            temperature_integral += area * durations[m] * kelvin[m];
        }
        const double annual = static_cast<double>(local_integral / year - 273.15L);
        near(number(cells[i], "temperature_c"), annual, 5.1e-9, "annual temperature lost accepted time weighting");
        near(final_hydrology_temperature[i], annual, 5.1e-9, "hydrology read stale legacy temperature");
        const double rain = number(cells[i], "precipitation_mm_y");
        near(number(cells[i], "vapor_deficit_mm_y"), std::max(0.0, std::max(0.0, annual + 8) * 31 - rain),
             2e-8, "vapor diagnostic used a different temperature source");
        near(number(records[i], "annual_net_heating_w_m2"), 0,
             number(records[i], "annual_flux_tolerance_w_m2"), "producer annual energy budget did not close");
    }
    const double global_mean = static_cast<double>(temperature_integral / (area_sum * year) - 273.15L);
    near(number(model, "solved_area_time_mean_temperature_c"), global_mean, 1e-12, "rain source mean is not area/time weighted");
    const double factor = std::clamp(std::exp(0.04 * (global_mean - 15)), 0.35, 2.25);
    near(number(model, "thermal_moisture_capacity_factor"), factor, 1e-14, "rain metadata derives capacity from obsolete parameters");
}

void compare_initial_empirical_rain(const std::string& seasonal, const std::string& legacy) {
    const auto seasonal_stage = elements(field(seasonal, "hydrologic_water_budget_history")).front();
    const auto legacy_stage = elements(field(legacy, "hydrologic_water_budget_history")).front();
    const auto area = numbers(seasonal_stage, "cell_area_km2_by_cell");
    const auto temperature = numbers(seasonal_stage, "temperature_c_by_cell");
    const auto rain = numbers(seasonal_stage, "precipitation_mm_y_by_cell");
    const auto baseline_rain = numbers(legacy_stage, "precipitation_mm_y_by_cell");
    require(area.size() == 128 && temperature.size() == area.size() && rain.size() == area.size() &&
            baseline_rain.size() == area.size(), "incomplete initial climate snapshots");
    require(field(seasonal_stage, "elevation_m_by_cell") == field(legacy_stage, "elevation_m_by_cell"),
            "rain comparison does not use identical initial terrain");
    long double total = 0, weighted = 0;
    for (std::size_t i = 0; i < area.size(); ++i) { total += area[i]; weighted += static_cast<long double>(area[i]) * temperature[i]; }
    const double factor = std::clamp(std::exp(0.04 * (static_cast<double>(weighted / total) - 15)), 0.35, 2.25);
    bool positive = false;
    for (std::size_t i = 0; i < rain.size(); ++i) {
        // At the declared reference L=G=1, legacy configured base=15 gives
        // multiplier one; all other first-stage empirical rain inputs match.
        near(rain[i], baseline_rain[i] * factor, 1e-5, "actual rainfall did not use the solved temperature factor");
        positive = positive || rain[i] > 0;
    }
    require(positive, "rain-source regression has no precipitation witness");
}

void airless_rain(const std::string& world) {
    const auto energy = field(world, "climate_energy_model");
    require(number(energy, "mean_surface_pressure_pa") == 0, "airless atmosphere retained pressure");
    require(number(energy, "radius_m") == 6200000 && number(energy, "gravity_m_s2") == 0.93 * 9.80665 &&
            number(energy, "reference_infrared_optical_depth") == 3 && number(energy, "greenhouse_factor") == 2 &&
            number(energy, "stellar_luminosity") == 0.97, "nondefault planet inputs were not retained by the producer");
    require(field(world, "climate_energy_transport_edges") == "[]", "airless planet has atmospheric heat transport");
    for (const auto cell : elements(field(world, "cells"))) {
        require(number(cell, "precipitation_mm_y") == 0, "airless annual rainfall is nonzero");
        for (double rain : numbers(cell, "precipitation_monthly_mm")) require(rain == 0, "airless monthly rainfall is nonzero");
    }
    for (const auto record : elements(field(world, "climate_energy_balance_records"))) {
        require(number(record, "surface_pressure_pa") == 0 && number(record, "atmospheric_heat_capacity_j_m2_k") == 0 &&
                number(record, "infrared_optical_depth") == 0 && number(record, "effective_longwave_emissivity") == 1,
                "airless retained column has atmospheric mass or opacity");
    }
}

}  // namespace

int main(int argc, char** argv) {
    try {
        require(argc <= 2, "usage: seasonal_climate_pipeline_test [generated-seasonal-world.json]");
        validation_and_frozen_c_adapters();
        auto params = parameters();
        const auto start = std::chrono::steady_clock::now();
        const std::string seasonal = generate(params);
        retained_temperatures_and_downstream_history(seasonal);
        std::cout << "default C++ seasonal reference verified in " << std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count() << " s\n";
        params.base_temperature_c = std::numeric_limits<double>::quiet_NaN();
        params.lapse_rate_c_per_km = std::numeric_limits<double>::infinity();
        require(generate(params) == seasonal, "obsolete Celsius controls changed seasonal generation or downstream outputs");
        params = parameters();
        params.temperature_model = magic_geo::ClimateTemperatureModel::legacy_empirical;
        params.reference_infrared_optical_depth = std::numeric_limits<double>::quiet_NaN();
        const std::string legacy = generate(params);
        require(field(field(legacy, "climate_model"), "model_type") == "\"equilibrium_latitude_circulation_climate_v5\"",
                "legacy C++ model metadata changed");
        require(legacy.find("\"climate_energy_model\"") == std::string::npos, "legacy generation retained seasonal energy");
        compare_initial_empirical_rain(seasonal, legacy);
        params = parameters();
        params.atmosphere_pressure_bar = 0; params.axial_tilt_deg = 0; params.orbital_eccentricity = 0;
        params.radius_km = 6200; params.gravity_g = 0.93; params.stellar_luminosity = 0.97;
        params.reference_infrared_optical_depth = 3; params.greenhouse_factor = 2;
        airless_rain(generate(params));
        if (argc == 2) {
            std::ofstream out(argv[1], std::ios::binary | std::ios::trunc);
            if (!out || !(out << seasonal << '\n')) throw std::runtime_error("could not write generated seasonal test artifact");
        }
        std::cout << "seasonal climate public pipeline tests passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
