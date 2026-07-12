#include "internal.hpp"

#ifdef _OPENMP
#include <omp.h>
#endif

namespace magic_geo::detail {

double climate_stellar_temperature_forcing_c(const Params& params) {
    return CLIMATE_STELLAR_TEMPERATURE_RESPONSE_C *
        (std::pow(params.stellar_luminosity, 0.25) - 1.0);
}

double climate_greenhouse_temperature_forcing_c(const Params& params) {
    return CLIMATE_GREENHOUSE_TEMPERATURE_RESPONSE_C *
        (params.greenhouse_factor - 1.0);
}

double climate_thermal_moisture_temperature_anomaly_c(const Params& params) {
    return params.base_temperature_c -
        CLIMATE_THERMAL_MOISTURE_REFERENCE_BASE_TEMPERATURE_C +
        climate_stellar_temperature_forcing_c(params) +
        climate_greenhouse_temperature_forcing_c(params);
}

double climate_thermal_moisture_capacity_factor(const Params& params) {
    const double bounded_exponent = clamp(
        CLIMATE_THERMAL_MOISTURE_RESPONSE_PER_C *
            climate_thermal_moisture_temperature_anomaly_c(params),
        std::log(CLIMATE_THERMAL_MOISTURE_MIN_FACTOR),
        std::log(CLIMATE_THERMAL_MOISTURE_MAX_FACTOR)
    );
    return clamp(
        std::exp(bounded_exponent),
        CLIMATE_THERMAL_MOISTURE_MIN_FACTOR,
        CLIMATE_THERMAL_MOISTURE_MAX_FACTOR
    );
}

double crust_age_ceiling_ma(const Params& params, double model_ceiling_ma) {
    return std::max(0.0, std::min(model_ceiling_ma, params.geological_age_ga * 1000.0));
}

double maturation_timestep_scale(const Params& params) {
    return params.maturation_timestep_ma /
        MATURATION_REFERENCE_TIMESTEP_MA;
}

double timestep_scaled_fraction(
    double reference_fraction,
    double timestep_scale
) {
    const double bounded_fraction = clamp(reference_fraction, 0.0, 1.0);
    const double bounded_scale = std::max(0.0, timestep_scale);
    if (bounded_fraction <= 0.0 || bounded_scale <= 0.0) {
        return 0.0;
    }
    if (bounded_scale == 1.0) {
        return bounded_fraction;
    }
    if (bounded_fraction >= 1.0) {
        return 1.0;
    }
    return -std::expm1(bounded_scale * std::log1p(-bounded_fraction));
}

Vec3 add(Vec3 a, Vec3 b) { return {a.x + b.x, a.y + b.y, a.z + b.z}; }
Vec3 sub(Vec3 a, Vec3 b) { return {a.x - b.x, a.y - b.y, a.z - b.z}; }
Vec3 mul(Vec3 a, double s) { return {a.x * s, a.y * s, a.z * s}; }
double dot(Vec3 a, Vec3 b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
Vec3 cross(Vec3 a, Vec3 b) {
    return {a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x};
}
double norm(Vec3 a) { return std::sqrt(dot(a, a)); }
Vec3 normalize(Vec3 a) {
    const double n = norm(a);
    if (n < 1.0e-12) {
        return {0.0, 0.0, 1.0};
    }
    return mul(a, 1.0 / n);
}
Vec3 rotate_about_axis(Vec3 value, Vec3 axis, double angle_rad) {
    if (angle_rad == 0.0) {
        return value;
    }
    const Vec3 unit_axis = normalize(axis);
    const double cosine = std::cos(angle_rad);
    const double sine = std::sin(angle_rad);
    return normalize(add(
        add(mul(value, cosine), mul(cross(unit_axis, value), sine)),
        mul(unit_axis, dot(unit_axis, value) * (1.0 - cosine))
    ));
}
double angular_distance(Vec3 a, Vec3 b) {
    return std::acos(clamp(dot(a, b), -1.0, 1.0));
}

double spherical_triangle_area_steradians(Vec3 a, Vec3 b, Vec3 c) {
    const double numerator = std::abs(dot(a, cross(b, c)));
    const double denominator = 1.0 + dot(a, b) + dot(b, c) + dot(c, a);
    return 2.0 * std::atan2(numerator, denominator);
}

const char* mesh_backend_name(int backend) {
    switch (backend) {
        case MESH_BACKEND_FIBONACCI:
            return "fibonacci_sphere";
        case MESH_BACKEND_GEODESIC_ICOSAHEDRON:
            return "geodesic_icosahedron";
        default:
            return "unknown";
    }
}

const char* cell_area_model_name(int backend) {
    switch (backend) {
        case MESH_BACKEND_FIBONACCI:
            return "spherical_voronoi_control_volume_v1";
        case MESH_BACKEND_GEODESIC_ICOSAHEDRON:
            return "spherical_barycentric_control_volume_v2";
        default:
            return "unknown";
    }
}

std::uint64_t splitmix64(std::uint64_t x) {
    x += 0x9e3779b97f4a7c15ULL;
    x = (x ^ (x >> 30U)) * 0xbf58476d1ce4e5b9ULL;
    x = (x ^ (x >> 27U)) * 0x94d049bb133111ebULL;
    return x ^ (x >> 31U);
}
double hash01(std::uint64_t seed, std::uint64_t a, std::uint64_t b) {
    const std::uint64_t x = splitmix64(seed ^ (a * 0x9e3779b97f4a7c15ULL) ^ (b * 0xbf58476d1ce4e5b9ULL));
    return static_cast<double>(x >> 11U) / 9007199254740992.0;
}
double signed_noise(std::uint64_t seed, std::uint64_t a, std::uint64_t b) {
    return hash01(seed, a, b) * 2.0 - 1.0;
}

std::string json_escape(const std::string& value) {
    std::string out;
    out.reserve(value.size() + 8);
    for (char ch : value) {
        switch (ch) {
            case '"': out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default: out += ch; break;
        }
    }
    return out;
}

std::string num(double value, int precision) {
    if (!std::isfinite(value)) {
        throw std::runtime_error(
            "attempted to serialize a non-finite simulation value"
        );
    }
    std::ostringstream out;
    out << std::fixed << std::setprecision(precision) << value;
    return out.str();
}

void comma(std::string& out, bool& first) {
    if (!first) {
        out += ",";
    }
    first = false;
}
void add_raw(std::string& out, bool& first, const char* key, const std::string& raw) {
    comma(out, first);
    out += "\"";
    out += key;
    out += "\":";
    out += raw;
}
void add_str(std::string& out, bool& first, const char* key, const std::string& value) {
    comma(out, first);
    out += "\"";
    out += key;
    out += "\":\"";
    out += json_escape(value);
    out += "\"";
}
void add_int(std::string& out, bool& first, const char* key, int value) {
    add_raw(out, first, key, std::to_string(value));
}
void add_u64(std::string& out, bool& first, const char* key, std::uint64_t value) {
    add_raw(out, first, key, std::to_string(value));
}
void add_double(std::string& out, bool& first, const char* key, double value, int precision) {
    add_raw(out, first, key, num(value, precision));
}
void add_bool(std::string& out, bool& first, const char* key, bool value) {
    add_raw(out, first, key, value ? "true" : "false");
}

ScopedThreadConfiguration::ScopedThreadConfiguration(int requested_threads) {
#ifdef _OPENMP
    if (requested_threads > 0) {
        previous_max_threads_ = omp_get_max_threads();
        omp_set_num_threads(requested_threads);
        restore_on_destruction_ = true;
    }
#else
    (void)requested_threads;
#endif
}

ScopedThreadConfiguration::~ScopedThreadConfiguration() {
#ifdef _OPENMP
    if (restore_on_destruction_) {
        omp_set_num_threads(previous_max_threads_);
    }
#endif
}

void validate_compute_options(const ComputeOptions& compute_options) {
    if (compute_options.compute_backend < 0 || compute_options.compute_backend > 3) {
        throw std::runtime_error("compute_backend must be auto, cpu, opencl, or cuda");
    }
}

void validate_params(const Params& params) {
    const auto require_finite = [](const char* name, double value) {
        if (!std::isfinite(value)) {
            throw std::runtime_error(std::string(name) + " must be finite");
        }
    };
    require_finite("radius_km", params.radius_km);
    require_finite("gravity_g", params.gravity_g);
    require_finite("day_length_hours", params.day_length_hours);
    require_finite("axial_tilt_deg", params.axial_tilt_deg);
    require_finite("orbital_eccentricity", params.orbital_eccentricity);
    require_finite("stellar_luminosity", params.stellar_luminosity);
    require_finite("atmosphere_pressure_bar", params.atmosphere_pressure_bar);
    require_finite("greenhouse_factor", params.greenhouse_factor);
    require_finite("ocean_fraction_target", params.ocean_fraction_target);
    require_finite("ocean_water_inventory_km3", params.ocean_water_inventory_km3);
    require_finite("internal_heat", params.internal_heat);
    require_finite("geological_age_ga", params.geological_age_ga);
    require_finite("continental_plate_fraction", params.continental_plate_fraction);
    require_finite(
        "continental_crust_fraction_target",
        params.continental_crust_fraction_target
    );
    require_finite("min_angular_speed", params.min_angular_speed);
    require_finite("max_angular_speed", params.max_angular_speed);
    require_finite(
        "plate_motion_scale_deg_per_step",
        params.plate_motion_scale_deg_per_step
    );
    require_finite(
        "oceanic_crust_aging_ma_per_step",
        params.oceanic_crust_aging_ma_per_step
    );
    require_finite("maturation_timestep_ma", params.maturation_timestep_ma);
    require_finite("lapse_rate_c_per_km", params.lapse_rate_c_per_km);
    require_finite("base_temperature_c", params.base_temperature_c);
    require_finite("precipitation_scale", params.precipitation_scale);
    require_finite(
        "subtropical_drying_strength",
        params.subtropical_drying_strength
    );
    require_finite("river_percentile", params.river_percentile);
    require_finite("stream_power_coefficient", params.stream_power_coefficient);
    require_finite("drainage_exponent", params.drainage_exponent);
    require_finite("slope_exponent", params.slope_exponent);
    require_finite("hillslope_diffusion", params.hillslope_diffusion);
    require_finite("tectonic_uplift_scale", params.tectonic_uplift_scale);

    if (params.cell_count < 128 || params.cell_count > 200000) {
        throw std::runtime_error("cell_count must be between 128 and 200000");
    }
    if (params.mesh_backend != MESH_BACKEND_FIBONACCI &&
        params.mesh_backend != MESH_BACKEND_GEODESIC_ICOSAHEDRON) {
        throw std::runtime_error("unknown mesh backend");
    }
    if (
        params.plate_count < 2 || params.plate_count > 256 ||
        params.plate_count >= params.cell_count
    ) {
        throw std::runtime_error(
            "plate_count must be between 2 and 256 and smaller than cell_count"
        );
    }
    if (params.neighbor_count < 4 || params.neighbor_count > 16) {
        throw std::runtime_error("neighbor_count must be between 4 and 16");
    }
    if (params.radius_km <= 100.0 || params.radius_km > 100000.0) {
        throw std::runtime_error(
            "radius_km must be greater than 100 and at most 100000"
        );
    }
    if (params.gravity_g <= 0.05 || params.gravity_g >= 5.0) {
        throw std::runtime_error("gravity_g must be greater than 0.05 and less than 5");
    }
    if (params.day_length_hours <= 1.0 || params.day_length_hours > 10000.0) {
        throw std::runtime_error(
            "day_length_hours must be greater than 1 and at most 10000"
        );
    }
    if (params.axial_tilt_deg < 0.0 || params.axial_tilt_deg > 90.0) {
        throw std::runtime_error("axial_tilt_deg must be between 0 and 90");
    }
    if (params.orbital_eccentricity < 0.0 || params.orbital_eccentricity >= 1.0) {
        throw std::runtime_error("orbital_eccentricity must be at least 0 and less than 1");
    }
    if (params.stellar_luminosity <= 0.01 || params.stellar_luminosity > 100.0) {
        throw std::runtime_error(
            "stellar_luminosity must be greater than 0.01 and at most 100"
        );
    }
    if (
        params.atmosphere_pressure_bar < 0.0 ||
        params.atmosphere_pressure_bar > 1000.0
    ) {
        throw std::runtime_error(
            "atmosphere_pressure_bar must be between 0 and 1000"
        );
    }
    if (params.greenhouse_factor < 0.0 || params.greenhouse_factor > 100.0) {
        throw std::runtime_error("greenhouse_factor must be between 0 and 100");
    }
    if (params.ocean_fraction_target < 0.0 || params.ocean_fraction_target > 0.95) {
        throw std::runtime_error("ocean_fraction_target must be between 0 and 0.95");
    }
    if (
        params.ocean_water_inventory_km3 < 0.0 ||
        params.ocean_water_inventory_km3 > 10000000000.0
    ) {
        throw std::runtime_error(
            "ocean_water_inventory_km3 must be between 0 and 10000000000"
        );
    }
    if (params.internal_heat < 0.0 || params.internal_heat > 100.0) {
        throw std::runtime_error("internal_heat must be between 0 and 100");
    }
    if (params.geological_age_ga < 0.01 || params.geological_age_ga > 100.0) {
        throw std::runtime_error("geological_age_ga must be between 0.01 and 100");
    }
    if (
        params.continental_plate_fraction < 0.0 ||
        params.continental_plate_fraction > 1.0
    ) {
        throw std::runtime_error("continental_plate_fraction must be between 0 and 1");
    }
    if (
        params.min_angular_speed < 0.0 || params.min_angular_speed > 100.0 ||
        params.max_angular_speed < params.min_angular_speed ||
        params.max_angular_speed > 100.0
    ) {
        throw std::runtime_error(
            "angular speeds must be between 0 and 100 and "
            "max_angular_speed must be >= min_angular_speed"
        );
    }
    if (params.boundary_smoothing_steps < 0 || params.boundary_smoothing_steps > 32) {
        throw std::runtime_error("boundary_smoothing_steps must be between 0 and 32");
    }
    if (params.months != 12) {
        throw std::runtime_error("months must be exactly 12");
    }
    if (params.plate_motion_scale_deg_per_step < 0.0 || params.plate_motion_scale_deg_per_step > 10.0) {
        throw std::runtime_error("plate_motion_scale_deg_per_step must be between 0 and 10");
    }
    if (params.continental_crust_fraction_target < 0.0 || params.continental_crust_fraction_target > 0.95) {
        throw std::runtime_error("continental_crust_fraction_target must be between 0 and 0.95");
    }
    if (params.oceanic_crust_aging_ma_per_step < 0.0 || params.oceanic_crust_aging_ma_per_step > 50.0) {
        throw std::runtime_error("oceanic_crust_aging_ma_per_step must be between 0 and 50");
    }
    if (params.maturation_timestep_ma <= 0.0 || params.maturation_timestep_ma > 5.0) {
        throw std::runtime_error("maturation_timestep_ma must be greater than 0 and at most 5");
    }
    if (params.subtropical_drying_strength < 0.0 || params.subtropical_drying_strength > 0.9) {
        throw std::runtime_error("subtropical_drying_strength must be between 0 and 0.9");
    }
    if (params.lapse_rate_c_per_km < 0.0 || params.lapse_rate_c_per_km > 15.0) {
        throw std::runtime_error("lapse_rate_c_per_km must be between 0 and 15");
    }
    if (params.base_temperature_c < -100.0 || params.base_temperature_c > 100.0) {
        throw std::runtime_error("base_temperature_c must be between -100 and 100");
    }
    if (params.precipitation_scale < 0.0 || params.precipitation_scale > 10.0) {
        throw std::runtime_error("precipitation_scale must be between 0 and 10");
    }
    if (params.river_percentile < 0.5 || params.river_percentile > 0.995) {
        throw std::runtime_error("river_percentile must be between 0.5 and 0.995");
    }
    if (params.erosion_iterations < 0 || params.erosion_iterations > 250) {
        throw std::runtime_error("erosion_iterations must be between 0 and 250");
    }
    if (
        params.stream_power_coefficient < 0.0 ||
        params.stream_power_coefficient > 1000.0
    ) {
        throw std::runtime_error("stream_power_coefficient must be between 0 and 1000");
    }
    if (params.drainage_exponent < 0.0 || params.drainage_exponent > 2.0) {
        throw std::runtime_error("drainage_exponent must be between 0 and 2");
    }
    if (params.slope_exponent < 0.0 || params.slope_exponent > 3.0) {
        throw std::runtime_error("slope_exponent must be between 0 and 3");
    }
    if (params.hillslope_diffusion < 0.0 || params.hillslope_diffusion > 1.0) {
        throw std::runtime_error("hillslope_diffusion must be between 0 and 1");
    }
    if (params.tectonic_uplift_scale < 0.0 || params.tectonic_uplift_scale > 10.0) {
        throw std::runtime_error("tectonic_uplift_scale must be between 0 and 10");
    }
    if (params.threads < 0 || params.threads > 1024) {
        throw std::runtime_error("threads must be between 0 and 1024");
    }
    if (params.float_precision < 0 || params.float_precision > 8) {
        throw std::runtime_error("float_precision must be between 0 and 8");
    }
}

}  // namespace magic_geo::detail
