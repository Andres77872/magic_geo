#pragma once

#include <cstddef>
#include <cstdint>
#include <type_traits>

// Frozen independently from the public header. This list models the original
// 64-bit C ABI that existing ctypes and compiled clients pass to
// magic_geo_generate_json.
#define MAGIC_GEO_V1_CONFIG_FIELD_LIST(X)                                      \
    X(std::uint64_t, seed, 0)                                                   \
    X(const char*, name, 8)                                                     \
    X(double, radius_km, 16)                                                    \
    X(double, gravity_g, 24)                                                    \
    X(double, day_length_hours, 32)                                             \
    X(double, axial_tilt_deg, 40)                                               \
    X(double, orbital_eccentricity, 48)                                         \
    X(double, stellar_luminosity, 56)                                           \
    X(double, atmosphere_pressure_bar, 64)                                      \
    X(double, greenhouse_factor, 72)                                            \
    X(double, ocean_fraction_target, 80)                                        \
    X(double, ocean_water_inventory_km3, 88)                                    \
    X(double, internal_heat, 96)                                                \
    X(double, geological_age_ga, 104)                                           \
    X(int, cell_count, 112)                                                     \
    X(int, mesh_backend, 116)                                                   \
    X(int, neighbor_count, 120)                                                 \
    X(int, plate_count, 124)                                                    \
    X(double, continental_plate_fraction, 128)                                  \
    X(double, continental_crust_fraction_target, 136)                           \
    X(double, min_angular_speed, 144)                                           \
    X(double, max_angular_speed, 152)                                           \
    X(int, boundary_smoothing_steps, 160)                                       \
    X(double, plate_motion_scale_deg_per_step, 168)                             \
    X(double, oceanic_crust_aging_ma_per_step, 176)                             \
    X(int, months, 184)                                                         \
    X(double, lapse_rate_c_per_km, 192)                                         \
    X(double, base_temperature_c, 200)                                          \
    X(double, precipitation_scale, 208)                                         \
    X(double, subtropical_drying_strength, 216)                                 \
    X(int, preserve_geologic_depressions, 224)                                  \
    X(double, river_percentile, 232)                                            \
    X(int, erosion_iterations, 240)                                             \
    X(double, stream_power_coefficient, 248)                                    \
    X(double, drainage_exponent, 256)                                           \
    X(double, slope_exponent, 264)                                              \
    X(double, hillslope_diffusion, 272)                                         \
    X(double, tectonic_uplift_scale, 280)                                       \
    X(int, threads, 288)                                                        \
    X(int, include_cells, 292)                                                  \
    X(int, float_precision, 296)

namespace magic_geo_c_api_v1 {

struct CConfig {
#define MAGIC_GEO_DECLARE_V1_FIELD(type, name, offset) type name;
    MAGIC_GEO_V1_CONFIG_FIELD_LIST(MAGIC_GEO_DECLARE_V1_FIELD)
#undef MAGIC_GEO_DECLARE_V1_FIELD
};

static_assert(std::is_standard_layout_v<CConfig>);

#if INTPTR_MAX == INT64_MAX
static_assert(sizeof(CConfig) == 304);
static_assert(alignof(CConfig) == 8);
#define MAGIC_GEO_ASSERT_V1_FIELD(type, name, expected_offset)                  \
    static_assert(std::is_same_v<decltype(CConfig::name), type>);               \
    static_assert(offsetof(CConfig, name) == expected_offset);
MAGIC_GEO_V1_CONFIG_FIELD_LIST(MAGIC_GEO_ASSERT_V1_FIELD)
#undef MAGIC_GEO_ASSERT_V1_FIELD
#endif

}  // namespace magic_geo_c_api_v1
