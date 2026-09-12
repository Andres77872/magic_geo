#include "magic_geo/native.hpp"

#include "engine/messagepack.hpp"

#include <cstdlib>
#include <cstring>
#include <exception>
#include <stdexcept>
#include <string>
#include <string_view>

namespace magic_geo {

Params params_from_c_config(const CConfig& cfg) {
    Params params;
    // Frozen C ABIs have no seasonal model selector and retain their contract.
    params.temperature_model = ClimateTemperatureModel::legacy_empirical;
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

namespace {
bool v4_flag(std::int32_t value, const char* name) {
    if (value != 0 && value != 1) {
        throw std::invalid_argument(std::string(name) + " must be exactly 0 or 1 in CConfigV4");
    }
    return value == 1;
}
}  // namespace

Params params_from_c_config(const CConfigV4& cfg) {
    Params params;
    params.temperature_model = ClimateTemperatureModel::prescribed_seasonal;
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
    params.reference_infrared_optical_depth = cfg.reference_infrared_optical_depth;
    params.precipitation_scale = cfg.precipitation_scale;
    params.subtropical_drying_strength = cfg.subtropical_drying_strength;
    params.preserve_geologic_depressions = v4_flag(cfg.preserve_geologic_depressions, "preserve_geologic_depressions");
    params.river_percentile = cfg.river_percentile;
    params.erosion_iterations = cfg.erosion_iterations;
    params.stream_power_coefficient = cfg.stream_power_coefficient;
    params.drainage_exponent = cfg.drainage_exponent;
    params.slope_exponent = cfg.slope_exponent;
    params.hillslope_diffusion = cfg.hillslope_diffusion;
    params.tectonic_uplift_scale = cfg.tectonic_uplift_scale;
    params.threads = cfg.threads;
    params.include_cells = v4_flag(cfg.include_cells, "include_cells");
    params.float_precision = cfg.float_precision;
    params.maturation_timestep_ma = cfg.maturation_timestep_ma;
    return params;
}

ComputeOptions compute_options_from_c_config(const CConfigV4& cfg) {
    ComputeOptions options;
    options.compute_backend = cfg.compute_backend;
    options.opencl_prefer_gpu = v4_flag(cfg.opencl_prefer_gpu, "opencl_prefer_gpu");
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

std::uint8_t* copy_buffer(
    const std::vector<std::uint8_t>& value,
    std::size_t* size
) {
    if (size == nullptr) {
        return nullptr;
    }
    *size = 0;
    void* allocation = std::malloc(value.empty() ? 1 : value.size());
    if (allocation == nullptr) {
        return nullptr;
    }
    if (!value.empty()) {
        std::memcpy(allocation, value.data(), value.size());
    }
    *size = value.size();
    return static_cast<std::uint8_t*>(allocation);
}

std::string error_json(std::string_view message) {
    std::string escaped;
    constexpr char hex[] = "0123456789abcdef";
    const std::string sanitized = magic_geo::detail::sanitize_utf8(message);
    escaped.reserve(sanitized.size() + 8);
    for (char raw_ch : sanitized) {
        const auto ch = static_cast<unsigned char>(raw_ch);
        switch (ch) {
            case '"': escaped += "\\\""; break;
            case '\\': escaped += "\\\\"; break;
            case '\b': escaped += "\\b"; break;
            case '\f': escaped += "\\f"; break;
            case '\n': escaped += "\\n"; break;
            case '\r': escaped += "\\r"; break;
            case '\t': escaped += "\\t"; break;
            default:
                if (ch < 0x20) {
                    escaped += "\\u00";
                    escaped += hex[ch >> 4U];
                    escaped += hex[ch & 0x0fU];
                } else {
                    escaped += static_cast<char>(ch);
                }
                break;
        }
    }
    return "{\"error\":\"" + escaped + "\"}";
}

std::vector<std::uint8_t> error_msgpack(std::string_view message) {
    return magic_geo::detail::json_to_messagepack(error_json(message));
}

const char* copy_error_json_noexcept(std::string_view message) noexcept {
    try {
        return copy_string(error_json(message));
    } catch (...) {
        return nullptr;
    }
}

const std::uint8_t* copy_error_msgpack_noexcept(
    std::string_view message,
    std::size_t* size
) noexcept {
    try {
        return copy_buffer(error_msgpack(message), size);
    } catch (...) {
        if (size != nullptr) {
            *size = 0;
        }
        return nullptr;
    }
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

extern "C" const std::uint8_t* magic_geo_generate_msgpack_v3(
    const magic_geo::CConfigV3* cfg,
    std::size_t* size
) {
    if (size == nullptr) {
        return nullptr;
    }
    *size = 0;
    try {
        if (cfg == nullptr) {
            return copy_error_msgpack_noexcept("null config pointer", size);
        }
        return copy_buffer(magic_geo::generate_world_msgpack(
            magic_geo::params_from_c_config(*cfg),
            magic_geo::compute_options_from_c_config(cfg->base)
        ), size);
    } catch (const std::exception& exc) {
        return copy_error_msgpack_noexcept(exc.what(), size);
    } catch (...) {
        return copy_error_msgpack_noexcept("unknown generation failure", size);
    }
}

extern "C" const std::uint8_t* magic_geo_generate_geo_msgpack_v3(
    const magic_geo::CConfigV3* cfg,
    std::size_t* size
) {
    if (size == nullptr) {
        return nullptr;
    }
    *size = 0;
    try {
        if (cfg == nullptr) {
            return copy_error_msgpack_noexcept("null config pointer", size);
        }
        return copy_buffer(magic_geo::generate_geo_world_msgpack(
            magic_geo::params_from_c_config(*cfg),
            magic_geo::compute_options_from_c_config(cfg->base)
        ), size);
    } catch (const std::exception& exc) {
        return copy_error_msgpack_noexcept(exc.what(), size);
    } catch (...) {
        return copy_error_msgpack_noexcept(
            "unknown geo generation failure",
            size
        );
    }
}

extern "C" const char* magic_geo_generate_json_v4(
    const magic_geo::CConfigV4* cfg
) noexcept {
    try {
        if (cfg == nullptr) return copy_error_json_noexcept("null config pointer");
        return copy_string(magic_geo::generate_world_json(
            magic_geo::params_from_c_config(*cfg),
            magic_geo::compute_options_from_c_config(*cfg)
        ));
    } catch (const std::exception& exc) {
        return copy_error_json_noexcept(exc.what());
    } catch (...) {
        return copy_error_json_noexcept("unknown generation failure");
    }
}

extern "C" const char* magic_geo_generate_geo_json_v4(
    const magic_geo::CConfigV4* cfg
) noexcept {
    try {
        if (cfg == nullptr) return copy_error_json_noexcept("null config pointer");
        return copy_string(magic_geo::generate_geo_world_json(
            magic_geo::params_from_c_config(*cfg),
            magic_geo::compute_options_from_c_config(*cfg)
        ));
    } catch (const std::exception& exc) {
        return copy_error_json_noexcept(exc.what());
    } catch (...) {
        return copy_error_json_noexcept("unknown geo generation failure");
    }
}

extern "C" const std::uint8_t* magic_geo_generate_msgpack_v4(
    const magic_geo::CConfigV4* cfg,
    std::size_t* size
) noexcept {
    if (size == nullptr) return nullptr;
    *size = 0;
    try {
        if (cfg == nullptr) return copy_error_msgpack_noexcept("null config pointer", size);
        return copy_buffer(magic_geo::generate_world_msgpack(
            magic_geo::params_from_c_config(*cfg),
            magic_geo::compute_options_from_c_config(*cfg)
        ), size);
    } catch (const std::exception& exc) {
        return copy_error_msgpack_noexcept(exc.what(), size);
    } catch (...) {
        return copy_error_msgpack_noexcept("unknown generation failure", size);
    }
}

extern "C" const std::uint8_t* magic_geo_generate_geo_msgpack_v4(
    const magic_geo::CConfigV4* cfg,
    std::size_t* size
) noexcept {
    if (size == nullptr) return nullptr;
    *size = 0;
    try {
        if (cfg == nullptr) return copy_error_msgpack_noexcept("null config pointer", size);
        return copy_buffer(magic_geo::generate_geo_world_msgpack(
            magic_geo::params_from_c_config(*cfg),
            magic_geo::compute_options_from_c_config(*cfg)
        ), size);
    } catch (const std::exception& exc) {
        return copy_error_msgpack_noexcept(exc.what(), size);
    } catch (...) {
        return copy_error_msgpack_noexcept("unknown geo generation failure", size);
    }
}

extern "C" void magic_geo_free_string(const char* ptr) {
    std::free(const_cast<char*>(ptr));
}

extern "C" void magic_geo_free_buffer(const std::uint8_t* ptr) {
    std::free(const_cast<std::uint8_t*>(ptr));
}
