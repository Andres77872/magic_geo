#pragma once

#include <cstdint>
#include <string>

#if defined(_WIN32)
#if defined(magic_geo_native_EXPORTS)
#define MAGIC_GEO_API __declspec(dllexport)
#else
#define MAGIC_GEO_API __declspec(dllimport)
#endif
#elif defined(__GNUC__) || defined(__clang__)
#define MAGIC_GEO_API __attribute__((visibility("default")))
#else
#define MAGIC_GEO_API
#endif

namespace magic_geo {

struct Params {
    std::uint64_t seed = 424242;
    std::string name = "earthlike_mvp";
    double radius_km = 6371.0;
    double gravity_g = 1.0;
    double day_length_hours = 24.0;
    double axial_tilt_deg = 23.5;
    double orbital_eccentricity = 0.016;
    double stellar_luminosity = 1.0;
    double atmosphere_pressure_bar = 1.0;
    double greenhouse_factor = 1.0;
    double ocean_fraction_target = 0.70;
    double ocean_water_inventory_km3 = 1338000000.0;
    double internal_heat = 1.0;
    double geological_age_ga = 4.5;
    int cell_count = 4096;
    int mesh_backend = 0;
    int neighbor_count = 7;
    int plate_count = 14;
    double continental_plate_fraction = 0.38;
    double continental_crust_fraction_target = 0.34;
    double min_angular_speed = 0.03;
    double max_angular_speed = 0.95;
    int boundary_smoothing_steps = 5;
    double plate_motion_scale_deg_per_step = 2.0;
    double oceanic_crust_aging_ma_per_step = 5.0;
    int months = 12;
    double lapse_rate_c_per_km = 6.5;
    double base_temperature_c = 15.0;
    double precipitation_scale = 1.0;
    double subtropical_drying_strength = 0.65;
    bool preserve_geologic_depressions = true;
    double river_percentile = 0.92;
    int erosion_iterations = 6;
    double stream_power_coefficient = 7.5;
    double drainage_exponent = 0.5;
    double slope_exponent = 1.0;
    double hillslope_diffusion = 0.055;
    double tectonic_uplift_scale = 0.85;
    int threads = 0;
    bool include_cells = true;
    int float_precision = 4;
};

// Compute policy is intentionally separate from Params so the original public
// C++ parameter layout remains ABI-compatible. The legacy one-argument
// generate_world_json overload always uses the CPU; callers must opt into
// automatic or OpenCL execution through the two-argument overload.
struct ComputeOptions {
    int compute_backend = 0;
    bool opencl_prefer_gpu = true;
};

struct CConfig {
    std::uint64_t seed;
    const char* name;
    double radius_km;
    double gravity_g;
    double day_length_hours;
    double axial_tilt_deg;
    double orbital_eccentricity;
    double stellar_luminosity;
    double atmosphere_pressure_bar;
    double greenhouse_factor;
    double ocean_fraction_target;
    double ocean_water_inventory_km3;
    double internal_heat;
    double geological_age_ga;
    int cell_count;
    int mesh_backend;
    int neighbor_count;
    int plate_count;
    double continental_plate_fraction;
    double continental_crust_fraction_target;
    double min_angular_speed;
    double max_angular_speed;
    int boundary_smoothing_steps;
    double plate_motion_scale_deg_per_step;
    double oceanic_crust_aging_ma_per_step;
    int months;
    double lapse_rate_c_per_km;
    double base_temperature_c;
    double precipitation_scale;
    double subtropical_drying_strength;
    int preserve_geologic_depressions;
    double river_percentile;
    int erosion_iterations;
    double stream_power_coefficient;
    double drainage_exponent;
    double slope_exponent;
    double hillslope_diffusion;
    double tectonic_uplift_scale;
    int threads;
    int include_cells;
    int float_precision;
};

// Versioned extension of the stable v1 C ABI. Keep CConfig byte-for-byte
// unchanged so callers compiled against the original 304-byte structure stay
// safe when loaded with a newer shared library.
struct CConfigV2 {
    CConfig base;
    int compute_backend;
    int opencl_prefer_gpu;
};

MAGIC_GEO_API std::string backend_info_json();
MAGIC_GEO_API std::string generate_world_json(const Params& params);
MAGIC_GEO_API std::string generate_world_json(
    const Params& params,
    const ComputeOptions& compute_options
);
MAGIC_GEO_API Params params_from_c_config(const CConfig& cfg);
MAGIC_GEO_API ComputeOptions compute_options_from_c_config(const CConfigV2& cfg);

}  // namespace magic_geo

extern "C" {
MAGIC_GEO_API const char* magic_geo_backend_info_json();
MAGIC_GEO_API const char* magic_geo_generate_json(const magic_geo::CConfig* cfg);
MAGIC_GEO_API const char* magic_geo_generate_json_v2(const magic_geo::CConfigV2* cfg);
MAGIC_GEO_API void magic_geo_free_string(const char* ptr);
}

#undef MAGIC_GEO_API
