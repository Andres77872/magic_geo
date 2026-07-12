#include "magic_geo/native.hpp"
#include "legacy_v1_layout.hpp"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cmath>
#include <cstdlib>
#include <future>
#include <iostream>
#include <limits>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>

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
static_assert(std::is_standard_layout_v<magic_geo::CConfigV3>);
#if INTPTR_MAX == INT64_MAX
static_assert(sizeof(magic_geo::CConfig) == 304);
static_assert(sizeof(magic_geo::CConfigV2) == 312);
static_assert(sizeof(magic_geo::CConfigV3) == 320);
static_assert(alignof(magic_geo::CConfig) == 8);
static_assert(offsetof(magic_geo::CConfigV2, base) == 0);
static_assert(offsetof(magic_geo::CConfigV2, compute_backend) == 304);
static_assert(offsetof(magic_geo::CConfigV2, opencl_prefer_gpu) == 308);
static_assert(offsetof(magic_geo::CConfigV3, base) == 0);
static_assert(offsetof(magic_geo::CConfigV3, maturation_timestep_ma) == 312);
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

magic_geo::CConfigV3 test_config_v3() {
    magic_geo::CConfigV3 cfg{};
    cfg.base = test_config_v2();
    cfg.maturation_timestep_ma = 2.5;
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
    CHECK(params.maturation_timestep_ma == 5.0);

    const magic_geo::CConfigV2 cfg_v2 = test_config_v2();
    const magic_geo::ComputeOptions compute_options =
        magic_geo::compute_options_from_c_config(cfg_v2);
    CHECK(compute_options.compute_backend == cfg_v2.compute_backend);
    CHECK(!compute_options.opencl_prefer_gpu);

    const magic_geo::CConfigV3 cfg_v3 = test_config_v3();
    const magic_geo::Params timestep_params =
        magic_geo::params_from_c_config(cfg_v3);
    CHECK(timestep_params.maturation_timestep_ma == 2.5);
    CHECK(timestep_params.seed == cfg_v3.base.base.seed);

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

int json_int(const std::string& json, const std::string& key);
bool json_bool(const std::string& json, const std::string& key);

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
    CHECK(generated.find("\"clock_type\":\"coupled_geodynamic_stage_clock_v12\"") !=
          std::string::npos);
    CHECK(generated.find("\"nominal_timestep_ma\":5") != std::string::npos);
    CHECK(generated.find("\"erosion_transition_coupling_semantics\":") !=
          std::string::npos);
    CHECK(generated.find("cryosphere_state_recompute") != std::string::npos);
    CHECK(generated.find(
        "\"mean_stream_power_response_m_per_reference_step\":"
    ) != std::string::npos);
    CHECK(generated.find("\"opencl_probe_performed\":false") != std::string::npos);
    CHECK(generated.find("\"cuda_probe_performed\":false") != std::string::npos);
    CHECK(generated.find(
        "\"plate_boundary_segment_model\":{"
    ) != std::string::npos);
    CHECK(generated.find(
        "\"model_type\":\"exact_directed_reciprocal_control_volume_boundary_segments_v2\""
    ) != std::string::npos);
    CHECK(generated.find("\"boundary_segments\":[{") != std::string::npos);
    CHECK(generated.find("\"mesh_segment_id\":") != std::string::npos);
    CHECK(generated.find("\"intrinsic_angular_speed\":") !=
        std::string::npos);
    CHECK(generated.find(
        "\"assignment_center_snapshot_semantics\":"
        "\"authoritative_root_operand_for_same_step_cell_plate_ids\""
    ) != std::string::npos);
    CHECK(
        json_int(generated, "assignment_center_serialized_significant_digits") ==
        std::numeric_limits<double>::max_digits10
    );
    CHECK(json_int(generated, "boundary_segment_count") > 0);
    CHECK(json_bool(generated, "authoritative_for_segment_geometry"));
    CHECK(json_bool(
        generated, "authoritative_for_direct_unsmoothed_kinematics"
    ));
    CHECK(json_bool(
        generated, "legacy_smoothed_cell_boundary_forcing_retained"
    ));
    CHECK(!json_bool(
        generated, "boundary_segments_drive_legacy_smoothed_forcing"
    ));
    CHECK(!json_bool(generated, "physical_subduction_polarity_resolved"));
    CHECK(!json_bool(generated, "slab_transfer_resolved"));
    CHECK(!json_bool(generated, "boundary_segments_drive_slab_transfers"));
    CHECK(generated.find(
        "\"crust_overlap_candidate_fate_model\":{"
    ) != std::string::npos);
    CHECK(generated.find(
        "\"model_type\":\"sparse_membership_class_to_uniform_boundary_plate_pair_candidate_v1\""
    ) != std::string::npos);
    CHECK(generated.find(
        "\"crust_overlap_candidate_fate_ledger\":{"
        "\"format\":\"sparse_membership_class_to_uniform_boundary_plate_pair_candidate_v1\""
    ) != std::string::npos);
    CHECK(generated.find(
        "\"candidate_partition_tolerance_model\":"
        "\"validated_binary64_fragment_to_class_rows_plus_portable_binary64_gamma_upper_envelope_v1\""
    ) != std::string::npos);
    CHECK(generated.find(
        "\"root_overlap_excess_serialization_model\":"
        "\"general_format_max_digits10_binary64_round_trip_v1_for_per_cell_and_global_operands\""
    ) != std::string::npos);
    CHECK(json_int(
        generated, "maximum_coverage_arrangement_fragments_per_cell"
    ) == 16384);
    CHECK(json_bool(generated, "deterministic_crosswalk_authoritative"));
    CHECK(!json_bool(generated, "candidate_allocation_authoritative"));
    CHECK(json_bool(generated, "pair_wide_consensus_only"));
    CHECK(json_bool(generated, "destination_endpoint_incidence_resolved"));
    CHECK(!json_bool(generated, "local_segment_link_resolved"));
    CHECK(!json_bool(generated, "connected_atom_topology_resolved"));
    CHECK(!json_bool(generated, "physical_material_fate_authoritative"));
    CHECK(!json_bool(generated, "slab_selection_authoritative"));
    CHECK(!json_bool(generated, "slab_transfer_authoritative"));
    CHECK(!json_bool(generated, "state_mutation_performed"));

    magic_geo::ComputeOptions cpu_options;
    cpu_options.compute_backend = 1;
    const std::string explicit_cpu_generated = magic_geo::generate_world_json(
        magic_geo::params_from_c_config(cfg), cpu_options
    );
    CHECK(explicit_cpu_generated == generated);

    const magic_geo::CConfigV2 geo_cfg = test_config_v2();
    const std::string geo_generated = magic_geo::generate_geo_world_json(
        magic_geo::params_from_c_config(geo_cfg.base),
        magic_geo::compute_options_from_c_config(geo_cfg)
    );
    CHECK(geo_generated.starts_with('{'));
    CHECK(geo_generated.find("\"settlements\":[]") != std::string::npos);
    CHECK(geo_generated.find("\"routes\":[]") != std::string::npos);
    CHECK(geo_generated.find("\"historical_events\":[]") != std::string::npos);
    CHECK(consume(magic_geo_generate_geo_json_v2(&geo_cfg)) == geo_generated);
    CHECK(
        consume(magic_geo_generate_geo_json_v2(nullptr)) ==
        "{\"error\":\"null config pointer\"}"
    );

    const magic_geo::CConfigV3 timestep_cfg = test_config_v3();
    const std::string timestep_generated = consume(
        magic_geo_generate_json_v3(&timestep_cfg)
    );
    CHECK(timestep_generated.starts_with('{'));
    CHECK(timestep_generated.find("\"nominal_timestep_ma\":2.5") !=
          std::string::npos);
    CHECK(timestep_generated.find("\"maturation_timestep_scale\":0.5") !=
          std::string::npos);
    CHECK(
        consume(magic_geo_generate_json_v3(nullptr)) ==
        "{\"error\":\"null config pointer\"}"
    );
    CHECK(
        consume(magic_geo_generate_geo_json_v3(nullptr)) ==
        "{\"error\":\"null config pointer\"}"
    );

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
    CHECK(invalid_backend_error.find("compute_backend must be auto, cpu, opencl, or cuda") !=
          std::string::npos);

    magic_geo::CConfigV3 invalid_v3 = test_config_v3();
    invalid_v3.maturation_timestep_ma = 5.1;
    const std::string invalid_timestep_error = consume(
        magic_geo_generate_json_v3(&invalid_v3)
    );
    CHECK(invalid_timestep_error.find(
        "maturation_timestep_ma must be greater than 0 and at most 5"
    ) != std::string::npos);

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

double json_double(const std::string& json, const std::string& key) {
    const std::string prefix = "\"" + key + "\":";
    const std::size_t start = json.find(prefix);
    if (start == std::string::npos) {
        return std::numeric_limits<double>::quiet_NaN();
    }
    return std::stod(json.substr(start + prefix.size()));
}

bool crust_overlap_shadow_errors_within_bounds(const std::string& json) {
    const std::pair<const char*, const char*> fields[] = {
        {
            "crust_overlap_continuous_shadow_maximum_crust_volume_error_km3",
            "crust_overlap_continuous_shadow_maximum_crust_volume_error_bound_km3",
        },
        {
            "crust_overlap_continuous_shadow_maximum_density_weighted_volume_error",
            "crust_overlap_continuous_shadow_maximum_density_weighted_volume_error_bound",
        },
        {
            "crust_overlap_continuous_shadow_maximum_age_volume_moment_error",
            "crust_overlap_continuous_shadow_maximum_age_volume_moment_error_bound",
        },
        {
            "crust_overlap_continuous_shadow_maximum_remapped_thickness_error_km",
            "crust_overlap_continuous_shadow_maximum_remapped_thickness_error_bound_km",
        },
        {
            "crust_overlap_continuous_shadow_maximum_remapped_density_error",
            "crust_overlap_continuous_shadow_maximum_remapped_density_error_bound",
        },
        {
            "crust_overlap_continuous_shadow_maximum_remapped_age_error_ma",
            "crust_overlap_continuous_shadow_maximum_remapped_age_error_bound_ma",
        },
    };
    for (const auto& [error_key, bound_key] : fields) {
        const double error = json_double(json, error_key);
        const double bound = json_double(json, bound_key);
        if (
            !std::isfinite(error) || !std::isfinite(bound) ||
            error < 0.0 || bound <= 0.0 || error > bound
        ) {
            return false;
        }
    }
    const double ratio = json_double(
        json, "crust_overlap_continuous_shadow_maximum_error_to_bound_ratio"
    );
    return std::isfinite(ratio) && ratio >= 0.0 && ratio <= 1.0;
}

bool json_bool(const std::string& json, const std::string& key) {
    const std::string prefix = "\"" + key + "\":";
    const std::size_t start = json.find(prefix);
    return start != std::string::npos &&
        json.compare(start + prefix.size(), 4, "true") == 0;
}

std::string json_object_at_occurrence(
    const std::string& json,
    const std::string& key,
    int occurrence
) {
    const std::string prefix = "\"" + key + "\":{";
    std::size_t object_start = 0;
    for (int index = 0; index <= occurrence; ++index) {
        const std::size_t key_position = json.find(prefix, object_start);
        if (key_position == std::string::npos) {
            return {};
        }
        object_start = key_position + prefix.size() - 1;
        if (index < occurrence) {
            object_start++;
        }
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
                return json.substr(object_start, position - object_start + 1);
            }
        }
    }
    return {};
}

std::vector<int> json_int_array(
    const std::string& json,
    const std::string& key
) {
    const std::string prefix = "\"" + key + "\":[";
    const std::size_t begin = json.find(prefix);
    if (begin == std::string::npos) {
        return {};
    }
    const std::size_t end = json.find(']', begin + prefix.size());
    if (end == std::string::npos) {
        return {};
    }
    std::vector<int> result;
    std::size_t cursor = begin + prefix.size();
    while (cursor < end) {
        std::size_t consumed = 0;
        result.push_back(std::stoi(json.substr(cursor, end - cursor), &consumed));
        cursor += consumed;
        if (cursor < end && json[cursor] == ',') {
            cursor++;
        }
    }
    return result;
}

std::vector<double> json_double_array(
    const std::string& json,
    const std::string& key
) {
    const std::string prefix = "\"" + key + "\":[";
    const std::size_t begin = json.find(prefix);
    if (begin == std::string::npos) {
        return {};
    }
    const std::size_t end = json.find(']', begin + prefix.size());
    if (end == std::string::npos) {
        return {};
    }
    std::vector<double> result;
    std::size_t cursor = begin + prefix.size();
    while (cursor < end) {
        std::size_t consumed = 0;
        result.push_back(std::stod(json.substr(cursor, end - cursor), &consumed));
        cursor += consumed;
        if (cursor < end && json[cursor] == ',') {
            cursor++;
        }
    }
    return result;
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
    CHECK(!json_bool(cpu_world, "cuda_probe_performed"));
    CHECK(cpu_world.find("\"opencl_capability_status\":\"not_probed\"") !=
          std::string::npos);
    CHECK(cpu_world.find("\"cuda_capability_status\":\"not_probed\"") !=
          std::string::npos);
    CHECK(json_int(cpu_world, "opencl_kernel_dispatch_count") == 0);
    CHECK(json_int(cpu_world, "cuda_kernel_dispatch_count") == 0);
    CHECK(
        cpu_world.find("\"crust_transport_execution_backend\":\"cpu\"") !=
        std::string::npos
    );
    CHECK(
        cpu_world.find(
            "\"crust_transport_execution_model\":"
            "\"forward_spherical_control_volume_overlap_v1\""
        ) != std::string::npos
    );
    CHECK(
        !json_bool(
            cpu_world,
            "accelerator_crust_source_remap_kernel_production_active"
        )
    );
    CHECK(
        cpu_world.find(
            "\"crust_overlap_continuous_shadow_model\":"
            "\"cpu_authoritative_overlap_csr_continuous_moment_shadow_v1\""
        ) != std::string::npos
    );
    CHECK(
        cpu_world.find(
            "\"crust_overlap_geometry_and_csr_authoritative_backend\":\"cpu\""
        ) != std::string::npos
    );
    CHECK(json_bool(cpu_world, "crust_overlap_continuous_shadow_only"));
    CHECK(!json_bool(
        cpu_world, "crust_overlap_continuous_shadow_authoritative"
    ));
    CHECK(!json_bool(
        cpu_world, "crust_overlap_continuous_shadow_result_used_for_state"
    ));
    CHECK(!json_bool(
        cpu_world, "crust_overlap_accelerator_complete_parity_demonstrated"
    ));
    CHECK(!json_bool(
        cpu_world, "crust_overlap_accelerator_state_authoritative"
    ));
    CHECK(json_int(
        cpu_world, "crust_overlap_continuous_shadow_device_dispatch_count"
    ) == 0);
    CHECK(json_int(
        cpu_world,
        "crust_overlap_continuous_shadow_validated_transition_count"
    ) == 0);
    CHECK(json_int(
        cpu_world, "opencl_crust_overlap_continuous_shadow_dispatch_count"
    ) == 0);
    CHECK(json_int(
        cpu_world, "cuda_crust_overlap_continuous_shadow_dispatch_count"
    ) == 0);

    magic_geo::CConfigV2 moving_cpu_cfg = cpu_cfg;
    moving_cpu_cfg.base.erosion_iterations = 1;
    const std::string moving_cpu_world = consume(
        magic_geo_generate_json_v2(&moving_cpu_cfg)
    );
    CHECK(moving_cpu_world.find("\"error\"") == std::string::npos);
    CHECK(json_int(
        moving_cpu_world, "cpu_conservative_crust_overlap_transition_count"
    ) == 1);
    CHECK(json_int(
        moving_cpu_world,
        "crust_overlap_continuous_shadow_device_dispatch_count"
    ) == 0);
    CHECK(json_int(
        moving_cpu_world,
        "crust_overlap_continuous_shadow_validated_transition_count"
    ) == 0);
    CHECK(json_int(
        moving_cpu_world,
        "opencl_crust_overlap_continuous_shadow_dispatch_count"
    ) == 0);
    CHECK(json_int(
        moving_cpu_world,
        "cuda_crust_overlap_continuous_shadow_dispatch_count"
    ) == 0);
    CHECK(
        moving_cpu_world.find(
            "\"crust_overlap_continuous_shadow_validation_status\":"
            "\"not_run_no_active_accelerator\""
        ) != std::string::npos
    );

    magic_geo::CConfigV2 auto_cfg = test_config_v2();
    auto_cfg.compute_backend = 0;
    const std::string auto_world = consume(magic_geo_generate_json_v2(&auto_cfg));
    CHECK(auto_world.find("\"error\"") == std::string::npos);
    CHECK(auto_world.find("\"requested_backend\":\"auto\"") != std::string::npos);
    CHECK(!json_bool(auto_world, "opencl_auto_offload_eligible"));
    CHECK(!json_bool(auto_world, "backend_fallback_used"));
    CHECK(!json_bool(auto_world, "opencl_probe_performed"));
    CHECK(!json_bool(auto_world, "cuda_probe_performed"));
    CHECK(auto_world.find("\"selected_backend\":\"cpu\"") != std::string::npos);
    CHECK(json_int(auto_world, "automatic_planning_cell_count") == 128);
    CHECK(json_int(auto_world, "opencl_kernel_dispatch_count") == 0);
    CHECK(json_int(auto_world, "cuda_kernel_dispatch_count") == 0);
    CHECK(json_int(
        auto_world, "crust_overlap_continuous_shadow_device_dispatch_count"
    ) == 0);
    CHECK(
        auto_world.find(
            "\"crust_overlap_continuous_shadow_validation_status\":"
            "\"not_run_no_conservative_transition\""
        ) != std::string::npos
    );

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
    CHECK(json_int(
        opencl_world, "crust_overlap_continuous_shadow_device_dispatch_count"
    ) == 0);
    CHECK(json_int(
        opencl_world, "cpu_conservative_crust_overlap_transition_count"
    ) == 0);
    CHECK(json_int(
        opencl_world,
        "crust_overlap_continuous_shadow_validated_transition_count"
    ) == 0);
    CHECK(
        opencl_world.find(
            "\"crust_overlap_continuous_shadow_validation_status\":"
            "\"not_run_no_conservative_transition\""
        ) != std::string::npos
    );
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
    CHECK(json_int(remap_opencl_world, "total_crust_mixed_destination_count") > 0);
    CHECK(
        json_int(remap_opencl_world, "opencl_crust_source_remap_dispatch_count") == 0
    );
    CHECK(
        json_int(
            remap_opencl_world,
            "cpu_conservative_crust_overlap_transition_count"
        ) == 2
    );
    CHECK(
        json_int(
            remap_opencl_world,
            "opencl_crust_overlap_continuous_shadow_dispatch_count"
        ) == 2
    );
    CHECK(
        json_int(
            remap_opencl_world,
            "crust_overlap_continuous_shadow_validated_transition_count"
        ) == 2
    );
    CHECK(json_int(
        remap_opencl_world, "crust_overlap_continuous_shadow_failure_count"
    ) == 0);
    CHECK(json_bool(
        remap_opencl_world,
        "crust_overlap_continuous_shadow_all_validated_transitions_passed"
    ));
    CHECK(!json_bool(
        remap_opencl_world,
        "crust_overlap_continuous_shadow_result_used_for_state"
    ));
    CHECK(crust_overlap_shadow_errors_within_bounds(remap_opencl_world));
    CHECK(
        remap_opencl_world.find(
            "\"crust_overlap_continuous_shadow_validation_status\":\"passed\""
        ) != std::string::npos
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

bool cuda_backend_failure_and_parity() {
    const std::string capability = magic_geo::backend_info_json();
    const bool cuda_compiled = json_bool(capability, "cuda_compiled");
    const bool cuda_available = json_bool(capability, "cuda_available");
    CHECK(capability.find("\"cuda_capability_status\":") != std::string::npos);
    CHECK(json_bool(capability, "cuda_probe_performed"));
    if (cuda_available) {
        CHECK(cuda_compiled);
        CHECK(json_bool(capability, "cuda_nvidia_device"));
        CHECK(json_bool(capability, "cuda_fp64_supported"));
        CHECK(json_int(capability, "cuda_compute_capability_major") >= 2);
    }

    magic_geo::CConfigV2 cpu_cfg = test_config_v2();
    cpu_cfg.compute_backend = 1;
    const std::string cpu_world = consume(magic_geo_generate_json_v2(&cpu_cfg));
    CHECK(cpu_world.find("\"error\"") == std::string::npos);

    magic_geo::CConfigV2 cuda_cfg = cpu_cfg;
    cuda_cfg.compute_backend = 3;
    const std::string cuda_world = consume(magic_geo_generate_json_v2(&cuda_cfg));
    if (!cuda_available) {
        CHECK(cuda_world.find("\"error\"") != std::string::npos);
        CHECK(cuda_world.find("explicit CUDA backend requested") != std::string::npos);
        return true;
    }

    CHECK(cuda_world.find("\"error\"") == std::string::npos);
    CHECK(cuda_world.find("\"requested_backend\":\"cuda\"") != std::string::npos);
    CHECK(cuda_world.find("\"selected_backend\":\"cuda\"") != std::string::npos);
    CHECK(cuda_world.find("\"active_backend\":\"cuda\"") != std::string::npos);
    CHECK(json_bool(cuda_world, "cuda_runtime_initialized"));
    CHECK(json_bool(cuda_world, "cuda_nvidia_device"));
    CHECK(json_bool(cuda_world, "cuda_fp64_supported"));
    CHECK(json_int(cuda_world, "cuda_plate_assignment_dispatch_count") > 0);
    CHECK(json_int(cuda_world, "cuda_smoothing_kernel_dispatch_count") > 0);
    CHECK(json_int(cuda_world, "cuda_batched_smoothing_operation_count") > 0);
    CHECK(json_int(cuda_world, "cuda_batched_smoothing_kernel_dispatch_count") > 0);
    CHECK(json_int(cuda_world, "cuda_last_threads_per_block") == 256);
    CHECK(json_int(
        cuda_world, "crust_overlap_continuous_shadow_device_dispatch_count"
    ) == 0);
    CHECK(json_int(
        cuda_world, "cpu_conservative_crust_overlap_transition_count"
    ) == 0);
    CHECK(json_int(
        cuda_world,
        "crust_overlap_continuous_shadow_validated_transition_count"
    ) == 0);
    CHECK(
        cuda_world.find(
            "\"crust_overlap_continuous_shadow_validation_status\":"
            "\"not_run_no_conservative_transition\""
        ) != std::string::npos
    );
    CHECK(normalize_backend_object(cpu_world) == normalize_backend_object(cuda_world));

    magic_geo::CConfigV2 remap_cpu_cfg = cpu_cfg;
    remap_cpu_cfg.base.cell_count = 129;
    remap_cpu_cfg.base.plate_count = 4;
    remap_cpu_cfg.base.erosion_iterations = 2;
    remap_cpu_cfg.base.include_cells = 1;
    remap_cpu_cfg.base.float_precision = 8;
    const std::string remap_cpu_world = consume(
        magic_geo_generate_json_v2(&remap_cpu_cfg)
    );
    magic_geo::CConfigV2 remap_cuda_cfg = remap_cpu_cfg;
    remap_cuda_cfg.compute_backend = 3;
    const std::string remap_cuda_world = consume(
        magic_geo_generate_json_v2(&remap_cuda_cfg)
    );
    CHECK(remap_cuda_world.find("\"error\"") == std::string::npos);
    CHECK(json_int(remap_cuda_world, "total_crust_mixed_destination_count") > 0);
    CHECK(
        json_int(remap_cuda_world, "cuda_crust_source_remap_dispatch_count") == 0
    );
    CHECK(
        json_int(
            remap_cuda_world,
            "cpu_conservative_crust_overlap_transition_count"
        ) == 2
    );
    CHECK(
        json_int(
            remap_cuda_world,
            "cuda_crust_overlap_continuous_shadow_dispatch_count"
        ) == 2
    );
    CHECK(
        json_int(
            remap_cuda_world,
            "crust_overlap_continuous_shadow_validated_transition_count"
        ) == 2
    );
    CHECK(json_int(
        remap_cuda_world, "crust_overlap_continuous_shadow_failure_count"
    ) == 0);
    CHECK(json_bool(
        remap_cuda_world,
        "crust_overlap_continuous_shadow_all_validated_transitions_passed"
    ));
    CHECK(!json_bool(
        remap_cuda_world,
        "crust_overlap_continuous_shadow_result_used_for_state"
    ));
    CHECK(crust_overlap_shadow_errors_within_bounds(remap_cuda_world));
    CHECK(
        remap_cuda_world.find(
            "\"crust_overlap_continuous_shadow_validation_status\":\"passed\""
        ) != std::string::npos
    );
    CHECK(
        json_int(
            remap_cuda_world,
            "cuda_batched_smoothing_kernel_dispatch_count"
        ) == 9
    );
    CHECK(
        normalize_backend_object(remap_cpu_world) ==
        normalize_backend_object(remap_cuda_world)
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
    CHECK(
        json_int(below_request_boundary, "reciprocal_mesh_segment_count") >
        3 * cfg.cell_count
    );
    return true;
}

bool reference_scale_membership_area_classes_close() {
    if (std::getenv("MAGIC_GEO_VALIDATE_FIBONACCI_KNN") == nullptr) {
        return true;
    }
    magic_geo::CConfig cfg = test_config();
    cfg.seed = 424242ULL;
    cfg.name = "reference_scale_membership_area_classes";
    cfg.radius_km = 6371.0;
    cfg.internal_heat = 1.0;
    cfg.geological_age_ga = 4.5;
    cfg.cell_count = 4096;
    cfg.mesh_backend = 0;
    cfg.neighbor_count = 7;
    cfg.plate_count = 14;
    cfg.continental_plate_fraction = 0.38;
    cfg.continental_crust_fraction_target = 0.34;
    cfg.min_angular_speed = 0.03;
    cfg.max_angular_speed = 0.95;
    cfg.boundary_smoothing_steps = 5;
    cfg.plate_motion_scale_deg_per_step = 2.0;
    cfg.oceanic_crust_aging_ma_per_step = 5.0;
    cfg.erosion_iterations = 1;
    cfg.threads = 2;
    cfg.include_cells = 0;
    cfg.float_precision = 4;
    const std::string world = consume(magic_geo_generate_json(&cfg));
    CHECK(world.find("\"error\"") == std::string::npos);
    const std::string motion_overlap = json_object_at_occurrence(
        world, "crust_overlap_ledger", 1
    );
    CHECK(!motion_overlap.empty());
    const int raw_fragment_count = json_int(
        motion_overlap, "total_coverage_arrangement_fragment_count"
    );
    const int membership_class_count = json_int(
        motion_overlap, "total_coverage_membership_area_class_count"
    );
    CHECK(raw_fragment_count > 100000);
    CHECK(membership_class_count > 4096);
    CHECK(membership_class_count < raw_fragment_count / 10);
    CHECK(
        json_int(
            motion_overlap,
            "maximum_coverage_membership_area_class_count"
        ) <= 32
    );
    const std::string class_ledger = json_object_at_occurrence(
        motion_overlap, "coverage_membership_area_class_ledger", 0
    );
    CHECK(!class_ledger.empty());
    CHECK(json_bool(class_ledger, "source_membership_resolved"));
    CHECK(!json_bool(class_ledger, "connected_fragment_topology_resolved"));
    return true;
}

bool concurrent_generation_sessions_are_isolated() {
    const std::string capability = magic_geo::backend_info_json();
    const bool cuda_available = json_bool(capability, "cuda_available");
    const bool opencl_available = json_bool(capability, "opencl_available");
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
    peer_cfg.compute_backend = cuda_available ? 3 : (opencl_available ? 2 : 1);

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
    if (cuda_available) {
        CHECK(peer_world.find("\"selected_backend\":\"cuda\"") != std::string::npos);
        CHECK(json_bool(peer_world, "cuda_nvidia_device"));
    } else if (opencl_available) {
        CHECK(peer_world.find("\"selected_backend\":\"opencl\"") != std::string::npos);
        CHECK(json_bool(peer_world, "opencl_device_fp64_denorm"));
    }
    CHECK(normalize_backend_object(cpu_world) == normalize_backend_object(peer_world));
    return true;
}

bool half_turn_crust_shadow_accepts_fully_uncovered_destinations() {
    magic_geo::CConfig cfg = test_config();
    cfg.internal_heat = 1.0;
    cfg.geological_age_ga = 4.5;
    cfg.min_angular_speed = 18.0;
    cfg.max_angular_speed = 18.0;
    cfg.plate_motion_scale_deg_per_step = 10.0;
    cfg.erosion_iterations = 1;
    cfg.include_cells = 1;
    cfg.threads = 1;
    const std::string world = consume(magic_geo_generate_json(&cfg));
    CHECK(world.find("\"error\"") == std::string::npos);
    cfg.threads = 2;
    const std::string threaded_world = consume(magic_geo_generate_json(&cfg));
    CHECK(threaded_world.find("\"error\"") == std::string::npos);
    CHECK(
        normalize_backend_object(world) ==
        normalize_backend_object(threaded_world)
    );
    CHECK(world.find("\"crust_material_shadow_history\"") !=
        std::string::npos);
    CHECK(world.find(
        "\"crust_transport_coverage_membership_area_class_model\":"
        "\"coalesced_destination_source_membership_area_classes_v1\""
    ) != std::string::npos);
    CHECK(!json_bool(
        world,
        "crust_transport_coverage_membership_area_class_connected_fragment_topology_resolved"
    ));
    CHECK(!json_bool(
        world,
        "crust_transport_coverage_membership_area_class_physical_fate_resolved"
    ));
    CHECK(!json_bool(
        world,
        "crust_transport_coverage_membership_area_class_slab_selection_resolved"
    ));
    CHECK(!json_bool(
        world,
        "crust_transport_coverage_membership_area_class_local_kinematics_resolved"
    ));

    const std::string identity_overlap = json_object_at_occurrence(
        world, "crust_overlap_ledger", 0
    );
    const std::string motion_overlap = json_object_at_occurrence(
        world, "crust_overlap_ledger", 1
    );
    CHECK(!identity_overlap.empty());
    CHECK(!motion_overlap.empty());
    const std::string identity_fragments = json_object_at_occurrence(
        identity_overlap, "coverage_membership_area_class_ledger", 0
    );
    const std::string motion_fragments = json_object_at_occurrence(
        motion_overlap, "coverage_membership_area_class_ledger", 0
    );
    CHECK(!identity_fragments.empty());
    CHECK(!motion_fragments.empty());
    CHECK(identity_fragments.find(
        "\"format\":\"destination_membership_area_class_csr_with_class_contributor_csr_v1\""
    ) != std::string::npos);
    CHECK(!json_bool(
        identity_fragments, "connected_fragment_topology_resolved"
    ));
    CHECK(!json_bool(identity_fragments, "physical_fate_resolved"));
    CHECK(!json_bool(identity_fragments, "slab_selection_resolved"));
    CHECK(!json_bool(identity_fragments, "local_kinematics_resolved"));

    const std::vector<int> identity_destination_offsets = json_int_array(
        identity_fragments, "destination_offsets"
    );
    const std::vector<int> identity_multiplicity = json_int_array(
        identity_fragments, "multiplicity"
    );
    const std::vector<int> identity_contributor_offsets = json_int_array(
        identity_fragments, "contributor_offsets"
    );
    const std::vector<int> identity_source_cells = json_int_array(
        identity_fragments, "source_cell_ids"
    );
    const std::vector<int> identity_source_plates = json_int_array(
        identity_fragments, "source_plate_ids"
    );
    CHECK(identity_destination_offsets.size() == 129);
    CHECK(identity_multiplicity.size() == 128);
    CHECK(identity_contributor_offsets.size() == 129);
    CHECK(identity_source_cells.size() == 128);
    CHECK(identity_source_plates.size() == 128);
    for (int index = 0; index <= 128; ++index) {
        CHECK(identity_destination_offsets[static_cast<std::size_t>(index)] == index);
        CHECK(identity_contributor_offsets[static_cast<std::size_t>(index)] == index);
        if (index < 128) {
            CHECK(identity_multiplicity[static_cast<std::size_t>(index)] == 1);
            CHECK(identity_source_cells[static_cast<std::size_t>(index)] == index);
            CHECK(identity_source_plates[static_cast<std::size_t>(index)] >= 0);
        }
    }

    const std::vector<int> destination_offsets = json_int_array(
        motion_fragments, "destination_offsets"
    );
    const std::vector<double> fragment_areas = json_double_array(
        motion_fragments, "area_km2"
    );
    const std::vector<int> multiplicity = json_int_array(
        motion_fragments, "multiplicity"
    );
    const std::vector<double> representative_x = json_double_array(
        motion_fragments, "representative_unit_x"
    );
    const std::vector<double> representative_y = json_double_array(
        motion_fragments, "representative_unit_y"
    );
    const std::vector<double> representative_z = json_double_array(
        motion_fragments, "representative_unit_z"
    );
    const std::vector<int> representative_available = json_int_array(
        motion_fragments, "representative_available"
    );
    const std::vector<int> contributor_offsets = json_int_array(
        motion_fragments, "contributor_offsets"
    );
    const std::vector<int> source_cells = json_int_array(
        motion_fragments, "source_cell_ids"
    );
    const std::vector<int> source_plates = json_int_array(
        motion_fragments, "source_plate_ids"
    );
    const std::vector<int> fragment_count_by_cell = json_int_array(
        motion_overlap, "coverage_arrangement_fragment_count_by_cell"
    );
    const std::vector<int> class_count_by_cell = json_int_array(
        motion_overlap, "coverage_membership_area_class_count_by_cell"
    );
    const std::vector<double> covered_union_area = json_double_array(
        motion_overlap, "covered_union_area_km2_by_cell"
    );
    const std::vector<double> uncovered_gap_area = json_double_array(
        motion_overlap, "uncovered_gap_area_km2_by_cell"
    );
    const std::vector<int> transport_destination_offsets = json_int_array(
        motion_overlap, "destination_offsets"
    );
    const std::vector<int> transport_source_cells = json_int_array(
        motion_overlap, "source_cell_ids"
    );
    const std::vector<double> overlap_areas = json_double_array(
        motion_overlap, "overlap_area_km2"
    );
    CHECK(destination_offsets.size() == 129);
    CHECK(fragment_count_by_cell.size() == 128);
    CHECK(class_count_by_cell.size() == 128);
    CHECK(covered_union_area.size() == 128);
    CHECK(uncovered_gap_area.size() == 128);
    CHECK(destination_offsets.front() == 0);
    CHECK(destination_offsets.back() == static_cast<int>(fragment_areas.size()));
    CHECK(multiplicity.size() == fragment_areas.size());
    CHECK(representative_x.size() == fragment_areas.size());
    CHECK(representative_y.size() == fragment_areas.size());
    CHECK(representative_z.size() == fragment_areas.size());
    CHECK(representative_available.size() == fragment_areas.size());
    CHECK(contributor_offsets.size() == fragment_areas.size() + 1);
    CHECK(source_cells.size() == source_plates.size());
    CHECK(contributor_offsets.back() == static_cast<int>(source_cells.size()));
    CHECK(transport_destination_offsets.size() == 129);
    CHECK(transport_source_cells.size() == overlap_areas.size());
    CHECK(
        transport_destination_offsets.back() ==
        static_cast<int>(transport_source_cells.size())
    );
    bool saw_gap_fragment = false;
    bool saw_overlap_fragment = false;
    int total_raw_fragment_count = 0;
    int total_class_count = 0;
    std::vector<double> reconstructed_overlap_areas(overlap_areas.size(), 0.0);
    for (int destination_id = 0; destination_id < 128; ++destination_id) {
        CHECK(
            destination_offsets[static_cast<std::size_t>(destination_id + 1)] -
                destination_offsets[static_cast<std::size_t>(destination_id)] ==
            class_count_by_cell[static_cast<std::size_t>(destination_id)]
        );
        CHECK(
            class_count_by_cell[static_cast<std::size_t>(destination_id)] <=
            fragment_count_by_cell[static_cast<std::size_t>(destination_id)]
        );
        total_raw_fragment_count +=
            fragment_count_by_cell[static_cast<std::size_t>(destination_id)];
        total_class_count +=
            class_count_by_cell[static_cast<std::size_t>(destination_id)];
        const int edge_begin = transport_destination_offsets[
            static_cast<std::size_t>(destination_id)
        ];
        const int edge_end = transport_destination_offsets[
            static_cast<std::size_t>(destination_id + 1)
        ];
        for (int fragment_id = destination_offsets[
                static_cast<std::size_t>(destination_id)
             ];
             fragment_id < destination_offsets[
                static_cast<std::size_t>(destination_id + 1)
             ];
             ++fragment_id) {
            for (int contributor_id = contributor_offsets[
                    static_cast<std::size_t>(fragment_id)
                 ];
                 contributor_id < contributor_offsets[
                    static_cast<std::size_t>(fragment_id + 1)
                 ];
                 ++contributor_id) {
                const int source_cell = source_cells[
                    static_cast<std::size_t>(contributor_id)
                ];
                const auto source_edge = std::lower_bound(
                    transport_source_cells.begin() + edge_begin,
                    transport_source_cells.begin() + edge_end,
                    source_cell
                );
                CHECK(source_edge != transport_source_cells.begin() + edge_end);
                CHECK(*source_edge == source_cell);
                reconstructed_overlap_areas[static_cast<std::size_t>(
                    std::distance(transport_source_cells.begin(), source_edge)
                )] += fragment_areas[static_cast<std::size_t>(fragment_id)];
            }
        }
    }
    for (std::size_t fragment_id = 0;
         fragment_id < fragment_areas.size();
         ++fragment_id) {
        CHECK(std::isfinite(fragment_areas[fragment_id]));
        CHECK(fragment_areas[fragment_id] > 0.0);
        const int contributor_begin = contributor_offsets[fragment_id];
        const int contributor_end = contributor_offsets[fragment_id + 1];
        CHECK(contributor_end - contributor_begin == multiplicity[fragment_id]);
        int previous_source = -1;
        for (int contributor_id = contributor_begin;
             contributor_id < contributor_end;
             ++contributor_id) {
            const int source = source_cells[static_cast<std::size_t>(contributor_id)];
            CHECK(source > previous_source);
            CHECK(source >= 0 && source < 128);
            CHECK(source_plates[static_cast<std::size_t>(contributor_id)] >= 0);
            previous_source = source;
        }
        if (representative_available[fragment_id] == 1) {
            const double squared_norm =
                representative_x[fragment_id] * representative_x[fragment_id] +
                representative_y[fragment_id] * representative_y[fragment_id] +
                representative_z[fragment_id] * representative_z[fragment_id];
            CHECK(std::abs(squared_norm - 1.0) < 5.0e-13);
        } else {
            CHECK(representative_available[fragment_id] == 0);
            CHECK(multiplicity[fragment_id] == 0);
            CHECK(representative_x[fragment_id] == 0.0);
            CHECK(representative_y[fragment_id] == 0.0);
            CHECK(representative_z[fragment_id] == 0.0);
        }
        saw_gap_fragment = saw_gap_fragment || multiplicity[fragment_id] == 0;
        saw_overlap_fragment = saw_overlap_fragment || multiplicity[fragment_id] >= 2;
    }
    for (std::size_t edge_id = 0; edge_id < overlap_areas.size(); ++edge_id) {
        const auto destination_offset = std::upper_bound(
            transport_destination_offsets.begin(),
            transport_destination_offsets.end(),
            static_cast<int>(edge_id)
        );
        CHECK(destination_offset != transport_destination_offsets.begin());
        const std::size_t destination_id = static_cast<std::size_t>(
            std::distance(
                transport_destination_offsets.begin(), destination_offset
            ) - 1
        );
        CHECK(destination_id < 128);
        const double destination_area =
            covered_union_area[destination_id] +
            uncovered_gap_area[destination_id];
        const double tolerance = std::max(1.0e-7, destination_area * 5.0e-10);
        CHECK(
            std::abs(
                reconstructed_overlap_areas[edge_id] - overlap_areas[edge_id]
            ) <= tolerance
        );
    }
    CHECK(total_class_count < total_raw_fragment_count);
    CHECK(saw_gap_fragment);
    CHECK(saw_overlap_fragment);

    const std::string key = "\"contributor_count_by_cell\":[";
    const std::size_t initial_begin = world.find(key);
    CHECK(initial_begin != std::string::npos);
    const std::size_t begin = world.find(
        key,
        initial_begin + key.size()
    );
    CHECK(begin != std::string::npos);
    const std::size_t end = world.find(']', begin + key.size());
    CHECK(end != std::string::npos);
    const std::string contributors = world.substr(
        begin + key.size(),
        end - (begin + key.size())
    );
    // This manufactured 180-degree plate step has fully uncovered
    // destinations. Their transported packet rows are empty, and the ordered
    // thickness-bound rule must create explicit unresolved-source material.
    CHECK(
        contributors.starts_with("0") ||
        contributors.find(",0") != std::string::npos
    );
    const std::string source_mass_key =
        "\"global_unresolved_source_mass_kg\":";
    const std::size_t initial_source = world.find(source_mass_key);
    CHECK(initial_source != std::string::npos);
    const std::size_t motion_source = world.find(
        source_mass_key,
        initial_source + source_mass_key.size()
    );
    CHECK(motion_source != std::string::npos);
    CHECK(world[motion_source + source_mass_key.size()] != '0');
    return true;
}

}  // namespace

int main() {
    if (!thread_configuration_is_generation_scoped() ||
        !conversion_preserves_every_field() || !public_api_is_usable() ||
        !geodesic_physics_uses_actual_mesh_size() ||
        !reference_scale_membership_area_classes_close() ||
        !half_turn_crust_shadow_accepts_fully_uncovered_destinations() ||
        !concurrent_generation_sessions_are_isolated() ||
        !backend_selection_fallback_and_opencl_parity() ||
        !cuda_backend_failure_and_parity()) {
        return 1;
    }
    return 0;
}
