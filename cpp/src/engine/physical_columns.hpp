#pragma once

#include "seasonal_energy_balance.hpp"

#include <vector>

namespace magic_geo::detail {

struct Cell;

// Declared dry-air/reference constants for this prescribed, isothermal
// hydrostatic column model. These are not solved surface temperatures.
inline constexpr double CLIMATE_DRY_AIR_GAS_CONSTANT_J_KG_K = 287.05;
inline constexpr double CLIMATE_DRY_AIR_HEAT_CAPACITY_J_KG_K = 1004.0;
inline constexpr double CLIMATE_REFERENCE_GRAVITY_M_S2 = 9.80665;
inline constexpr double CLIMATE_REFERENCE_PRESSURE_PA = 100000.0;
inline constexpr double CLIMATE_LAND_SLAB_HEAT_CAPACITY_J_M2_K = 4.0e6;
inline constexpr double CLIMATE_WATER_VOLUMETRIC_HEAT_CAPACITY_J_M3_K = 4.1813e6;

struct PrescribedAtmosphereOptions {
    double mean_surface_pressure_pa = CLIMATE_REFERENCE_PRESSURE_PA;
    double gravity_m_s2 = CLIMATE_REFERENCE_GRAVITY_M_S2;
    double profile_temperature_k = 288.15;
    double reference_infrared_optical_depth = 1.0;
    double greenhouse_factor = 1.0;
    double atmospheric_diffusivity_m2_s = 2.2e6;
    bool operator==(const PrescribedAtmosphereOptions&) const = default;
};

struct PrescribedSurfaceColumn {
    double area_m2 = 0.0;
    double interface_elevation_m = 0.0;
    double surface_heat_capacity_j_m2_k = 0.0;
};

struct PrescribedClimateColumns {
    std::vector<SurfaceEnergyColumn> columns;
    std::vector<double> surface_pressure_pa;
    std::vector<double> atmospheric_heat_capacity_j_m2_k;
    std::vector<double> infrared_optical_depth;
    // Vertically integrated conductivity K_i = diffusivity * C_atmosphere.
    std::vector<double> horizontal_conductivity_w_k;
    double total_area_m2 = 0.0;
    double atmospheric_scale_height_m = 0.0;
    double area_weighted_mean_surface_pressure_pa = 0.0;
    double mean_surface_pressure_residual_pa = 0.0;
    double total_atmospheric_mass_kg = 0.0;
    double atmospheric_mass_residual_kg = 0.0;
};

// Pure coefficient assembly: arbitrary finite interface elevations are allowed,
// including a common datum shift. Preserves the area-weighted mean pressure;
// diagnostics report floating-point residuals without correcting any column.
// p_i = p_mean exp(-z_i/H) / area_mean(exp(-z/H)), H=R_d*T_profile/g.
// C_atm=cp*p_i/g; tau=tau_ref*greenhouse*(p_i/p_ref)*(g_ref/g);
// emissivity=1/(1+3*tau/4); C_total=C_surface+C_atm.
// Mean pressure zero gives exact atmospheric zeros and emissivity one. A
// positive mathematical pressure/coefficient outside double range is rejected.
// Model assumptions: docs/seasonal_climate_vertical_model_research.md.
// Coefficients do not depend on albedo, solved temperature or lake/ice feedback.
PrescribedClimateColumns build_prescribed_climate_columns(
    const std::vector<PrescribedSurfaceColumn>& surfaces,
    const PrescribedAtmosphereOptions& options = {}
);

// Fresh post-sea-level state only. Marine pressure is evaluated at z=0, and
// marine storage uses the smaller of actual depth and the prescribed maximum.
// Exposed land uses elevation_m and a positive mineral slab. Marine water-body
// codes must be 1..3, exposed land code 0. Lakes, inconsistent wet flags/depths,
// noncanonical ids, and unrepresentable storage are rejected.
// Grounded ice and all other later diagnostic fields are deliberately unused.
std::vector<PrescribedSurfaceColumn> prescribed_surface_columns_from_cells(
    const std::vector<Cell>& cells,
    double marine_mixed_layer_depth_m = 50.0
);

}  // namespace magic_geo::detail
