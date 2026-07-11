#include "magic_geo/native.hpp"
#include "legacy_v1_layout.hpp"

#include <cstddef>
#include <cstdint>
#include <future>
#include <iostream>
#include <limits>
#include <string>
#include <type_traits>

#ifdef _OPENMP
#include <omp.h>
#endif

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
static_assert(std::is_standard_layout_v<magic_geo::CConfigV2>);
#if INTPTR_MAX == INT64_MAX
static_assert(sizeof(magic_geo::CConfig) == 304);
static_assert(sizeof(magic_geo::CConfigV2) == 312);
static_assert(alignof(magic_geo::CConfig) == 8);
static_assert(offsetof(magic_geo::CConfigV2, base) == 0);
static_assert(offsetof(magic_geo::CConfigV2, compute_backend) == 304);
static_assert(offsetof(magic_geo::CConfigV2, opencl_prefer_gpu) == 308);
#define MAGIC_GEO_ASSERT_CURRENT_V1_FIELD(type, name, expected_offset)          \
    static_assert(std::is_same_v<decltype(magic_geo::CConfig::name), type>);    \
    static_assert(offsetof(magic_geo::CConfig, name) == expected_offset);       \
    static_assert(                                                               \
        offsetof(magic_geo::CConfig, name) ==                                   \
        offsetof(magic_geo_legacy_v1::CConfig, name)                            \
    );
MAGIC_GEO_V1_CONFIG_FIELD_LIST(MAGIC_GEO_ASSERT_CURRENT_V1_FIELD)
#undef MAGIC_GEO_ASSERT_CURRENT_V1_FIELD
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

magic_geo::CConfigV2 test_config_v2() {
    magic_geo::CConfigV2 cfg{};
    cfg.base = test_config();
    cfg.compute_backend = 1;
    cfg.opencl_prefer_gpu = 0;
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

    const magic_geo::CConfigV2 cfg_v2 = test_config_v2();
    const magic_geo::ComputeOptions compute_options =
        magic_geo::compute_options_from_c_config(cfg_v2);
    CHECK(compute_options.compute_backend == cfg_v2.compute_backend);
    CHECK(!compute_options.opencl_prefer_gpu);

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
    CHECK(generated.find("\"requested_backend\":\"cpu\"") != std::string::npos);
    CHECK(generated.find("\"opencl_probe_performed\":false") != std::string::npos);

    magic_geo::ComputeOptions cpu_options;
    cpu_options.compute_backend = 1;
    const std::string explicit_cpu_generated = magic_geo::generate_world_json(
        magic_geo::params_from_c_config(cfg), cpu_options
    );
    CHECK(explicit_cpu_generated == generated);

    const std::string c_backend = consume(magic_geo_backend_info_json());
    CHECK(c_backend.starts_with('{'));
    CHECK(c_backend.find("\"active_backend\"") != std::string::npos);

    const std::string null_error = consume(magic_geo_generate_json(nullptr));
    CHECK(null_error == "{\"error\":\"null config pointer\"}");

    magic_geo::CConfig invalid = cfg;
    invalid.cell_count = 64;
    const std::string invalid_error = consume(magic_geo_generate_json(&invalid));
    CHECK(invalid_error.find("\"error\"") != std::string::npos);
    CHECK(invalid_error.find("cell_count must be between 128 and 200000") !=
          std::string::npos);

    magic_geo::CConfigV2 invalid_v2 = test_config_v2();
    invalid_v2.compute_backend = 99;
    const std::string invalid_backend_error = consume(magic_geo_generate_json_v2(&invalid_v2));
    CHECK(invalid_backend_error.find("compute_backend must be auto, cpu, or opencl") !=
          std::string::npos);

    invalid = cfg;
    invalid.radius_km = std::numeric_limits<double>::infinity();
    const std::string non_finite_error = consume(magic_geo_generate_json(&invalid));
    CHECK(non_finite_error.find("radius_km must be finite") != std::string::npos);

    invalid = cfg;
    invalid.radius_km = 1.0e155;
    CHECK(
        consume(magic_geo_generate_json(&invalid)).find("at most 100000") !=
        std::string::npos
    );
    invalid = cfg;
    invalid.day_length_hours = 10001.0;
    CHECK(
        consume(magic_geo_generate_json(&invalid)).find("at most 10000") !=
        std::string::npos
    );
    invalid = cfg;
    invalid.stellar_luminosity = 101.0;
    CHECK(
        consume(magic_geo_generate_json(&invalid)).find("at most 100") !=
        std::string::npos
    );
    invalid = cfg;
    invalid.atmosphere_pressure_bar = 1001.0;
    CHECK(
        consume(magic_geo_generate_json(&invalid)).find("between 0 and 1000") !=
        std::string::npos
    );
    invalid = cfg;
    invalid.greenhouse_factor = 101.0;
    CHECK(
        consume(magic_geo_generate_json(&invalid)).find("between 0 and 100") !=
        std::string::npos
    );
    invalid = cfg;
    invalid.internal_heat = 101.0;
    CHECK(
        consume(magic_geo_generate_json(&invalid)).find("between 0 and 100") !=
        std::string::npos
    );
    invalid = cfg;
    invalid.geological_age_ga = 101.0;
    CHECK(
        consume(magic_geo_generate_json(&invalid)).find("between 0.01 and 100") !=
        std::string::npos
    );
    invalid = cfg;
    invalid.max_angular_speed = 101.0;
    CHECK(
        consume(magic_geo_generate_json(&invalid)).find("between 0 and 100") !=
        std::string::npos
    );
    invalid = cfg;
    invalid.threads = 1025;
    CHECK(
        consume(magic_geo_generate_json(&invalid)).find("between 0 and 1024") !=
        std::string::npos
    );

    magic_geo::CConfig supported_extrema = cfg;
    supported_extrema.radius_km = 100000.0;
    supported_extrema.day_length_hours = 10000.0;
    supported_extrema.stellar_luminosity = 100.0;
    supported_extrema.atmosphere_pressure_bar = 1000.0;
    supported_extrema.greenhouse_factor = 100.0;
    supported_extrema.internal_heat = 100.0;
    supported_extrema.geological_age_ga = 100.0;
    supported_extrema.min_angular_speed = 100.0;
    supported_extrema.max_angular_speed = 100.0;
    supported_extrema.erosion_iterations = 1;
    const std::string extrema_world = consume(
        magic_geo_generate_json(&supported_extrema)
    );
    CHECK(extrema_world.find("\"error\"") == std::string::npos);

    magic_geo_free_string(nullptr);
    return true;
}

int json_int(const std::string& json, const std::string& key) {
    const std::string prefix = "\"" + key + "\":";
    const std::size_t start = json.find(prefix);
    if (start == std::string::npos) {
        return -1;
    }
    return std::stoi(json.substr(start + prefix.size()));
}

bool json_bool(const std::string& json, const std::string& key) {
    const std::string prefix = "\"" + key + "\":";
    const std::size_t start = json.find(prefix);
    return start != std::string::npos &&
        json.compare(start + prefix.size(), 4, "true") == 0;
}

std::string normalize_backend_object(std::string json) {
    const std::string key = "\"backend\":";
    const std::size_t key_position = json.find(key);
    if (key_position == std::string::npos) {
        return json;
    }
    const std::size_t object_start = json.find('{', key_position + key.size());
    if (object_start == std::string::npos) {
        return json;
    }
    int depth = 0;
    bool in_string = false;
    bool escaped = false;
    for (std::size_t position = object_start; position < json.size(); ++position) {
        const char ch = json[position];
        if (in_string) {
            if (escaped) {
                escaped = false;
            } else if (ch == '\\') {
                escaped = true;
            } else if (ch == '"') {
                in_string = false;
            }
            continue;
        }
        if (ch == '"') {
            in_string = true;
        } else if (ch == '{') {
            depth++;
        } else if (ch == '}') {
            depth--;
            if (depth == 0) {
                json.replace(object_start, position - object_start + 1, "{}");
                return json;
            }
        }
    }
    return json;
}

bool backend_selection_fallback_and_opencl_parity() {
    const std::string capability = magic_geo::backend_info_json();
    const bool opencl_available = json_bool(capability, "opencl_available");
    CHECK(json_bool(capability, "opencl_probe_performed"));
    CHECK(capability.find("\"opencl_capability_status\":") != std::string::npos);

    magic_geo::CConfigV2 cpu_cfg = test_config_v2();
    cpu_cfg.compute_backend = 1;
    const std::string cpu_world = consume(magic_geo_generate_json_v2(&cpu_cfg));
    CHECK(cpu_world.find("\"error\"") == std::string::npos);
    CHECK(cpu_world.find("\"requested_backend\":\"cpu\"") != std::string::npos);
    CHECK(cpu_world.find("\"selected_backend\":\"cpu\"") != std::string::npos);
    CHECK(!json_bool(cpu_world, "opencl_probe_performed"));
    CHECK(cpu_world.find("\"opencl_capability_status\":\"not_probed\"") !=
          std::string::npos);
    CHECK(json_int(cpu_world, "opencl_kernel_dispatch_count") == 0);

    magic_geo::CConfigV2 auto_cfg = test_config_v2();
    auto_cfg.compute_backend = 0;
    const std::string auto_world = consume(magic_geo_generate_json_v2(&auto_cfg));
    CHECK(auto_world.find("\"error\"") == std::string::npos);
    CHECK(auto_world.find("\"requested_backend\":\"auto\"") != std::string::npos);
    CHECK(!json_bool(auto_world, "opencl_auto_offload_eligible"));
    CHECK(!json_bool(auto_world, "backend_fallback_used"));
    CHECK(!json_bool(auto_world, "opencl_probe_performed"));
    CHECK(auto_world.find("\"selected_backend\":\"cpu\"") != std::string::npos);
    CHECK(json_int(auto_world, "opencl_kernel_dispatch_count") == 0);

    magic_geo::CConfigV2 opencl_cfg = test_config_v2();
    opencl_cfg.compute_backend = 2;
    const std::string opencl_world = consume(magic_geo_generate_json_v2(&opencl_cfg));
    if (!opencl_available) {
        CHECK(opencl_world.find("\"error\"") != std::string::npos);
        CHECK(opencl_world.find("explicit OpenCL backend requested") != std::string::npos);
        return true;
    }

    CHECK(opencl_world.find("\"error\"") == std::string::npos);
    CHECK(opencl_world.find("\"selected_backend\":\"opencl\"") != std::string::npos);
    CHECK(opencl_world.find("\"active_backend\":\"opencl\"") != std::string::npos);
    CHECK(json_bool(opencl_world, "opencl_program_built"));
    CHECK(json_bool(opencl_world, "opencl_program_active"));
    CHECK(json_bool(opencl_world, "opencl_device_fp64_denorm"));
    CHECK(json_bool(opencl_world, "opencl_device_fp64_round_to_nearest"));
    CHECK(json_bool(opencl_world, "opencl_device_fp64_inf_nan"));
    CHECK(json_bool(opencl_world, "opencl_device_endian_matches_host"));
    CHECK(json_bool(opencl_world, "opencl_device_opencl_c_1_2"));
    CHECK(json_int(opencl_world, "opencl_plate_assignment_dispatch_count") > 0);
    CHECK(json_int(opencl_world, "opencl_smoothing_kernel_dispatch_count") > 0);
    CHECK(json_int(opencl_world, "opencl_batched_smoothing_operation_count") > 0);
    CHECK(
        json_int(opencl_world, "opencl_batched_smoothing_kernel_dispatch_count") > 0
    );
    CHECK(normalize_backend_object(cpu_world) == normalize_backend_object(opencl_world));

    magic_geo::CConfigV2 remap_cpu_cfg = test_config_v2();
    remap_cpu_cfg.compute_backend = 1;
    remap_cpu_cfg.base.erosion_iterations = 2;
    const std::string remap_cpu_world = consume(
        magic_geo_generate_json_v2(&remap_cpu_cfg)
    );
    magic_geo::CConfigV2 remap_opencl_cfg = remap_cpu_cfg;
    remap_opencl_cfg.compute_backend = 2;
    const std::string remap_opencl_world = consume(
        magic_geo_generate_json_v2(&remap_opencl_cfg)
    );
    CHECK(remap_opencl_world.find("\"error\"") == std::string::npos);
    CHECK(
        json_int(remap_opencl_world, "opencl_crust_source_remap_dispatch_count") == 2
    );
    CHECK(
        json_int(
            remap_opencl_world,
            "opencl_batched_smoothing_kernel_dispatch_count"
        ) == 9
    );
    CHECK(
        normalize_backend_object(remap_cpu_world) ==
        normalize_backend_object(remap_opencl_world)
    );
    return true;
}

bool thread_configuration_is_generation_scoped() {
#ifdef _OPENMP
    const int initial_max_threads = omp_get_max_threads();
#else
    const int initial_max_threads = json_int(
        magic_geo::backend_info_json(), "openmp_max_threads"
    );
#endif
    CHECK(initial_max_threads >= 1);

    magic_geo::CConfig cfg = test_config();
    const int requested_threads = initial_max_threads == 1 ? 2 : 1;
    cfg.threads = requested_threads;
    const std::string explicit_world = magic_geo::generate_world_json(
        magic_geo::params_from_c_config(cfg)
    );
#ifdef _OPENMP
    CHECK(json_int(explicit_world, "openmp_max_threads") == requested_threads);
    CHECK(omp_get_max_threads() == initial_max_threads);
#else
    CHECK(json_int(explicit_world, "openmp_max_threads") == 1);
#endif
    CHECK(
        json_int(magic_geo::backend_info_json(), "openmp_max_threads") ==
        initial_max_threads
    );

    cfg.threads = 0;
    const std::string automatic_world = magic_geo::generate_world_json(
        magic_geo::params_from_c_config(cfg)
    );
    CHECK(json_int(automatic_world, "openmp_max_threads") == initial_max_threads);
#ifdef _OPENMP
    CHECK(omp_get_max_threads() == initial_max_threads);
#endif
    CHECK(
        json_int(magic_geo::backend_info_json(), "openmp_max_threads") ==
        initial_max_threads
    );
    return true;
}

bool geodesic_physics_uses_actual_mesh_size() {
    magic_geo::CConfig cfg = test_config();
    cfg.mesh_backend = 1;
    cfg.cell_count = 255;
    const std::string below_request_boundary = magic_geo::generate_world_json(
        magic_geo::params_from_c_config(cfg)
    );
    cfg.cell_count = 256;
    const std::string above_request_boundary = magic_geo::generate_world_json(
        magic_geo::params_from_c_config(cfg)
    );
    CHECK(below_request_boundary == above_request_boundary);
    return true;
}

bool concurrent_generation_sessions_are_isolated() {
    const bool opencl_available = json_bool(
        magic_geo::backend_info_json(), "opencl_available"
    );
    magic_geo::CConfigV2 cpu_cfg = test_config_v2();
    cpu_cfg.base.mesh_backend = 1;
    cpu_cfg.base.cell_count = 512;
    cpu_cfg.base.boundary_smoothing_steps = 4;
    cpu_cfg.base.erosion_iterations = 1;
    cpu_cfg.base.threads = 1;
    cpu_cfg.base.include_cells = 1;
    cpu_cfg.base.float_precision = 8;
    cpu_cfg.compute_backend = 1;

    magic_geo::CConfigV2 peer_cfg = cpu_cfg;
    peer_cfg.base.threads = 2;
    peer_cfg.compute_backend = opencl_available ? 2 : 1;

    auto cpu_future = std::async(std::launch::async, [cpu_cfg]() {
        return consume(magic_geo_generate_json_v2(&cpu_cfg));
    });
    auto peer_future = std::async(std::launch::async, [peer_cfg]() {
        return consume(magic_geo_generate_json_v2(&peer_cfg));
    });
    const std::string cpu_world = cpu_future.get();
    const std::string peer_world = peer_future.get();
    CHECK(cpu_world.find("\"error\"") == std::string::npos);
    CHECK(peer_world.find("\"error\"") == std::string::npos);
    if (opencl_available) {
        CHECK(peer_world.find("\"selected_backend\":\"opencl\"") != std::string::npos);
        CHECK(json_bool(peer_world, "opencl_device_fp64_denorm"));
    }
    CHECK(normalize_backend_object(cpu_world) == normalize_backend_object(peer_world));
    return true;
}

}  // namespace

int main() {
    if (!thread_configuration_is_generation_scoped() ||
        !conversion_preserves_every_field() || !public_api_is_usable() ||
        !geodesic_physics_uses_actual_mesh_size() ||
        !concurrent_generation_sessions_are_isolated() ||
        !backend_selection_fallback_and_opencl_parity()) {
        return 1;
    }
    return 0;
}
