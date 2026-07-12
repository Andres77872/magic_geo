#include "magic_geo/native.hpp"

#include <cstdlib>
#include <cstring>
#include <exception>
#include <string>

namespace magic_geo {

Params params_from_c_config(const CConfig& cfg) {
    Params params;
    params.seed = cfg.seed;
    params.name = cfg.name == nullptr ? "world" : cfg.name;
    params.radius_km = cfg.radius_km;
    params.gravity_g = cfg.gravity_g;
    params.day_length_hours = cfg.day_length_hours;
    params.axial_tilt_deg = cfg.axial_tilt_deg;
    params.orbital_eccentricity = cfg.orbital_eccentricity;
    params.stellar_luminosity = cfg.stellar_luminosity;
    params.atmosphere_pressure_bar = cfg.atmosphere_pressure_bar;
    params.greenhouse_factor = cfg.greenhouse_factor;
    params.ocean_fraction_target = cfg.ocean_fraction_target;
    params.ocean_water_inventory_km3 = cfg.ocean_water_inventory_km3;
    params.internal_heat = cfg.internal_heat;
    params.geological_age_ga = cfg.geological_age_ga;
    params.cell_count = cfg.cell_count;
    params.mesh_backend = cfg.mesh_backend;
    params.neighbor_count = cfg.neighbor_count;
    params.plate_count = cfg.plate_count;
    params.continental_plate_fraction = cfg.continental_plate_fraction;
    params.continental_crust_fraction_target = cfg.continental_crust_fraction_target;
    params.min_angular_speed = cfg.min_angular_speed;
    params.max_angular_speed = cfg.max_angular_speed;
    params.boundary_smoothing_steps = cfg.boundary_smoothing_steps;
    params.plate_motion_scale_deg_per_step = cfg.plate_motion_scale_deg_per_step;
    params.oceanic_crust_aging_ma_per_step = cfg.oceanic_crust_aging_ma_per_step;
    params.months = cfg.months;
    params.lapse_rate_c_per_km = cfg.lapse_rate_c_per_km;
    params.base_temperature_c = cfg.base_temperature_c;
    params.precipitation_scale = cfg.precipitation_scale;
    params.subtropical_drying_strength = cfg.subtropical_drying_strength;
    params.preserve_geologic_depressions = cfg.preserve_geologic_depressions != 0;
    params.river_percentile = cfg.river_percentile;
    params.erosion_iterations = cfg.erosion_iterations;
    params.stream_power_coefficient = cfg.stream_power_coefficient;
    params.drainage_exponent = cfg.drainage_exponent;
    params.slope_exponent = cfg.slope_exponent;
    params.hillslope_diffusion = cfg.hillslope_diffusion;
    params.tectonic_uplift_scale = cfg.tectonic_uplift_scale;
    params.threads = cfg.threads;
    params.include_cells = cfg.include_cells != 0;
    params.float_precision = cfg.float_precision;
    return params;
}

Params params_from_c_config(const CConfigV3& cfg) {
    Params params = params_from_c_config(cfg.base.base);
    params.maturation_timestep_ma = cfg.maturation_timestep_ma;
    return params;
}

ComputeOptions compute_options_from_c_config(const CConfigV2& cfg) {
    ComputeOptions options;
    options.compute_backend = cfg.compute_backend;
    options.opencl_prefer_gpu = cfg.opencl_prefer_gpu != 0;
    return options;
}

}  // namespace magic_geo

namespace {

char* copy_string(const std::string& value) {
    char* out = static_cast<char*>(std::malloc(value.size() + 1));
    if (out == nullptr) {
        return nullptr;
    }
    std::memcpy(out, value.c_str(), value.size() + 1);
    return out;
}

std::string error_json(const std::string& message) {
    std::string escaped;
    for (char ch : message) {
        if (ch == '"' || ch == '\\') {
            escaped += '\\';
        }
        escaped += ch;
    }
    return "{\"error\":\"" + escaped + "\"}";
}

}  // namespace

extern "C" const char* magic_geo_backend_info_json() {
    try {
        return copy_string(magic_geo::backend_info_json());
    } catch (const std::exception& exc) {
        return copy_string(error_json(exc.what()));
    } catch (...) {
        return copy_string(error_json("unknown backend_info failure"));
    }
}

extern "C" const char* magic_geo_generate_json(const magic_geo::CConfig* cfg) {
    try {
        if (cfg == nullptr) {
            return copy_string(error_json("null config pointer"));
        }
        return copy_string(magic_geo::generate_world_json(magic_geo::params_from_c_config(*cfg)));
    } catch (const std::exception& exc) {
        return copy_string(error_json(exc.what()));
    } catch (...) {
        return copy_string(error_json("unknown generation failure"));
    }
}

extern "C" const char* magic_geo_generate_json_v2(const magic_geo::CConfigV2* cfg) {
    try {
        if (cfg == nullptr) {
            return copy_string(error_json("null config pointer"));
        }
        return copy_string(magic_geo::generate_world_json(
            magic_geo::params_from_c_config(cfg->base),
            magic_geo::compute_options_from_c_config(*cfg)
        ));
    } catch (const std::exception& exc) {
        return copy_string(error_json(exc.what()));
    } catch (...) {
        return copy_string(error_json("unknown generation failure"));
    }
}

extern "C" const char* magic_geo_generate_json_v3(const magic_geo::CConfigV3* cfg) {
    try {
        if (cfg == nullptr) {
            return copy_string(error_json("null config pointer"));
        }
        return copy_string(magic_geo::generate_world_json(
            magic_geo::params_from_c_config(*cfg),
            magic_geo::compute_options_from_c_config(cfg->base)
        ));
    } catch (const std::exception& exc) {
        return copy_string(error_json(exc.what()));
    } catch (...) {
        return copy_string(error_json("unknown generation failure"));
    }
}

extern "C" const char* magic_geo_generate_geo_json_v2(
    const magic_geo::CConfigV2* cfg
) {
    try {
        if (cfg == nullptr) {
            return copy_string(error_json("null config pointer"));
        }
        return copy_string(magic_geo::generate_geo_world_json(
            magic_geo::params_from_c_config(cfg->base),
            magic_geo::compute_options_from_c_config(*cfg)
        ));
    } catch (const std::exception& exc) {
        return copy_string(error_json(exc.what()));
    } catch (...) {
        return copy_string(error_json("unknown geo generation failure"));
    }
}

extern "C" const char* magic_geo_generate_geo_json_v3(
    const magic_geo::CConfigV3* cfg
) {
    try {
        if (cfg == nullptr) {
            return copy_string(error_json("null config pointer"));
        }
        return copy_string(magic_geo::generate_geo_world_json(
            magic_geo::params_from_c_config(*cfg),
            magic_geo::compute_options_from_c_config(cfg->base)
        ));
    } catch (const std::exception& exc) {
        return copy_string(error_json(exc.what()));
    } catch (...) {
        return copy_string(error_json("unknown geo generation failure"));
    }
}

extern "C" void magic_geo_free_string(const char* ptr) {
    std::free(const_cast<char*>(ptr));
}
