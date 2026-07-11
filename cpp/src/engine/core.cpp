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
            return "equal_area_fibonacci_quadrature_v1";
        case MESH_BACKEND_GEODESIC_ICOSAHEDRON:
            return "spherical_barycentric_dual_v1";
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
        value = 0.0;
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

void configure_threads(const Params& params) {
#ifdef _OPENMP
    if (params.threads > 0) {
        omp_set_num_threads(params.threads);
    }
#else
    (void)params;
#endif
}

void validate_params(const Params& params) {
    if (params.cell_count < 128) {
        throw std::runtime_error("cell_count must be at least 128");
    }
    if (params.mesh_backend != MESH_BACKEND_FIBONACCI &&
        params.mesh_backend != MESH_BACKEND_GEODESIC_ICOSAHEDRON) {
        throw std::runtime_error("unknown mesh backend");
    }
    if (params.plate_count < 2 || params.plate_count >= params.cell_count) {
        throw std::runtime_error("plate_count must be >= 2 and smaller than cell_count");
    }
    if (params.neighbor_count < 4) {
        throw std::runtime_error("neighbor_count must be at least 4");
    }
    if (params.gravity_g <= 0.0 || params.day_length_hours <= 0.0 || params.atmosphere_pressure_bar < 0.0) {
        throw std::runtime_error("planetary gravity/day length must be positive and atmosphere pressure must be non-negative");
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
    if (!std::isfinite(params.ocean_water_inventory_km3) || params.ocean_water_inventory_km3 < 0.0) {
        throw std::runtime_error("ocean_water_inventory_km3 must be finite and non-negative");
    }
    if (params.oceanic_crust_aging_ma_per_step < 0.0 || params.oceanic_crust_aging_ma_per_step > 50.0) {
        throw std::runtime_error("oceanic_crust_aging_ma_per_step must be between 0 and 50");
    }
    if (params.subtropical_drying_strength < 0.0 || params.subtropical_drying_strength > 0.9) {
        throw std::runtime_error("subtropical_drying_strength must be between 0 and 0.9");
    }
}

}  // namespace magic_geo::detail
