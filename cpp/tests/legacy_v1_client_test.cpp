#include "legacy_v1_layout.hpp"

#include <iostream>
#include <string>

extern "C" {
const char* magic_geo_generate_json(const magic_geo_legacy_v1::CConfig* cfg);
void magic_geo_free_string(const char* ptr);
}

int main() {
    magic_geo_legacy_v1::CConfig cfg{};
    cfg.seed = 987654321ULL;
    cfg.name = "legacy_v1_client";
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

    const char* raw = magic_geo_generate_json(&cfg);
    const std::string json = raw == nullptr ? std::string{} : std::string(raw);
    magic_geo_free_string(raw);
    const bool valid = !json.empty() && json.find("\"error\"") == std::string::npos &&
        json.find("\"name\":\"legacy_v1_client\"") != std::string::npos &&
        json.find("\"requested_backend\":\"cpu\"") != std::string::npos &&
        json.find("\"opencl_probe_performed\":false") != std::string::npos;
    if (!valid) {
        std::cerr << "legacy v1 client received an invalid response\n";
        return 1;
    }
    return 0;
}
