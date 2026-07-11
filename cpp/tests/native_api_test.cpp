#include "magic_geo/native.hpp"

#include <cstddef>
#include <cstdint>
#include <iostream>
#include <string>
#include <type_traits>

namespace {

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            std::cerr << "check failed at line " << __LINE__ << ": "          \
                      << #condition << '\n';                                    \
            return false;                                                       \
        }                                                                       \
    } while (false)

static_assert(std::is_standard_layout_v<magic_geo::CConfig>);
#if INTPTR_MAX == INT64_MAX
static_assert(sizeof(magic_geo::CConfig) == 304);
static_assert(alignof(magic_geo::CConfig) == 8);
#endif

magic_geo::CConfig test_config() {
    magic_geo::CConfig cfg{};
    cfg.seed = 987654321ULL;
    cfg.name = "native_api_test";
    cfg.radius_km = 6200.0;
    cfg.gravity_g = 0.93;
    cfg.day_length_hours = 26.0;
    cfg.axial_tilt_deg = 18.0;
    cfg.orbital_eccentricity = 0.02;
    cfg.stellar_luminosity = 0.97;
    cfg.atmosphere_pressure_bar = 0.88;
    cfg.greenhouse_factor = 1.04;
    cfg.ocean_fraction_target = 0.63;
    cfg.ocean_water_inventory_km3 = 850000000.0;
    cfg.internal_heat = 1.12;
    cfg.geological_age_ga = 3.8;
    cfg.cell_count = 128;
    cfg.mesh_backend = 0;
    cfg.neighbor_count = 6;
    cfg.plate_count = 4;
    cfg.continental_plate_fraction = 0.42;
    cfg.continental_crust_fraction_target = 0.36;
    cfg.min_angular_speed = 0.05;
    cfg.max_angular_speed = 0.75;
    cfg.boundary_smoothing_steps = 3;
    cfg.plate_motion_scale_deg_per_step = 1.5;
    cfg.oceanic_crust_aging_ma_per_step = 4.0;
    cfg.months = 12;
    cfg.lapse_rate_c_per_km = 6.2;
    cfg.base_temperature_c = 14.0;
    cfg.precipitation_scale = 0.9;
    cfg.subtropical_drying_strength = 0.55;
    cfg.preserve_geologic_depressions = 1;
    cfg.river_percentile = 0.90;
    cfg.erosion_iterations = 0;
    cfg.stream_power_coefficient = 6.5;
    cfg.drainage_exponent = 0.45;
    cfg.slope_exponent = 1.1;
    cfg.hillslope_diffusion = 0.04;
    cfg.tectonic_uplift_scale = 0.8;
    cfg.threads = 1;
    cfg.include_cells = 0;
    cfg.float_precision = 5;
    return cfg;
}

bool conversion_preserves_every_field() {
    const magic_geo::CConfig cfg = test_config();
    const magic_geo::Params params = magic_geo::params_from_c_config(cfg);
    CHECK(params.seed == cfg.seed);
    CHECK(params.name == cfg.name);
    CHECK(params.radius_km == cfg.radius_km);
    CHECK(params.gravity_g == cfg.gravity_g);
    CHECK(params.day_length_hours == cfg.day_length_hours);
    CHECK(params.axial_tilt_deg == cfg.axial_tilt_deg);
    CHECK(params.orbital_eccentricity == cfg.orbital_eccentricity);
    CHECK(params.stellar_luminosity == cfg.stellar_luminosity);
    CHECK(params.atmosphere_pressure_bar == cfg.atmosphere_pressure_bar);
    CHECK(params.greenhouse_factor == cfg.greenhouse_factor);
    CHECK(params.ocean_fraction_target == cfg.ocean_fraction_target);
    CHECK(params.ocean_water_inventory_km3 == cfg.ocean_water_inventory_km3);
    CHECK(params.internal_heat == cfg.internal_heat);
    CHECK(params.geological_age_ga == cfg.geological_age_ga);
    CHECK(params.cell_count == cfg.cell_count);
    CHECK(params.mesh_backend == cfg.mesh_backend);
    CHECK(params.neighbor_count == cfg.neighbor_count);
    CHECK(params.plate_count == cfg.plate_count);
    CHECK(params.continental_plate_fraction == cfg.continental_plate_fraction);
    CHECK(params.continental_crust_fraction_target ==
          cfg.continental_crust_fraction_target);
    CHECK(params.min_angular_speed == cfg.min_angular_speed);
    CHECK(params.max_angular_speed == cfg.max_angular_speed);
    CHECK(params.boundary_smoothing_steps == cfg.boundary_smoothing_steps);
    CHECK(params.plate_motion_scale_deg_per_step ==
          cfg.plate_motion_scale_deg_per_step);
    CHECK(params.oceanic_crust_aging_ma_per_step ==
          cfg.oceanic_crust_aging_ma_per_step);
    CHECK(params.months == cfg.months);
    CHECK(params.lapse_rate_c_per_km == cfg.lapse_rate_c_per_km);
    CHECK(params.base_temperature_c == cfg.base_temperature_c);
    CHECK(params.precipitation_scale == cfg.precipitation_scale);
    CHECK(params.subtropical_drying_strength == cfg.subtropical_drying_strength);
    CHECK(params.preserve_geologic_depressions);
    CHECK(params.river_percentile == cfg.river_percentile);
    CHECK(params.erosion_iterations == cfg.erosion_iterations);
    CHECK(params.stream_power_coefficient == cfg.stream_power_coefficient);
    CHECK(params.drainage_exponent == cfg.drainage_exponent);
    CHECK(params.slope_exponent == cfg.slope_exponent);
    CHECK(params.hillslope_diffusion == cfg.hillslope_diffusion);
    CHECK(params.tectonic_uplift_scale == cfg.tectonic_uplift_scale);
    CHECK(params.threads == cfg.threads);
    CHECK(!params.include_cells);
    CHECK(params.float_precision == cfg.float_precision);

    magic_geo::CConfig null_name = cfg;
    null_name.name = nullptr;
    CHECK(magic_geo::params_from_c_config(null_name).name == "world");
    return true;
}

std::string consume(const char* raw) {
    const std::string value = raw == nullptr ? std::string{} : std::string(raw);
    magic_geo_free_string(raw);
    return value;
}

bool public_api_is_usable() {
    const std::string backend = magic_geo::backend_info_json();
    CHECK(backend.starts_with('{'));
    CHECK(backend.find("\"active_backend\"") != std::string::npos);

    const magic_geo::CConfig cfg = test_config();
    const std::string generated = magic_geo::generate_world_json(
        magic_geo::params_from_c_config(cfg)
    );
    CHECK(generated.starts_with('{'));
    CHECK(generated.find("\"schema_version\":1") != std::string::npos);
    CHECK(generated.find("\"name\":\"native_api_test\"") != std::string::npos);
    CHECK(generated.find("\"cells\":[]") != std::string::npos);

    const std::string c_backend = consume(magic_geo_backend_info_json());
    CHECK(c_backend.starts_with('{'));
    CHECK(c_backend.find("\"active_backend\"") != std::string::npos);

    const std::string null_error = consume(magic_geo_generate_json(nullptr));
    CHECK(null_error == "{\"error\":\"null config pointer\"}");

    magic_geo::CConfig invalid = cfg;
    invalid.cell_count = 64;
    const std::string invalid_error = consume(magic_geo_generate_json(&invalid));
    CHECK(invalid_error.find("\"error\"") != std::string::npos);
    CHECK(invalid_error.find("cell_count must be at least 128") !=
          std::string::npos);

    magic_geo_free_string(nullptr);
    return true;
}

}  // namespace

int main() {
    if (!conversion_preserves_every_field() || !public_api_is_usable()) {
        return 1;
    }
    return 0;
}
