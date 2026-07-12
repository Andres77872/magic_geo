#pragma once

namespace magic_geo::detail {

constexpr double PI = 3.141592653589793238462643383279502884;
constexpr double DEG = 180.0 / PI;
constexpr double CLIMATE_LATITUDE_TEMPERATURE_GRADIENT_C = 47.0;
constexpr double CLIMATE_LATITUDE_TEMPERATURE_EXPONENT = 3.0;
constexpr double CLIMATE_SUBTROPICAL_DRYING_MIN_FACTOR = 0.25;
constexpr double CLIMATE_MARINE_ANNUAL_TEMPERATURE_OFFSET_C = 0.0;
constexpr double CLIMATE_SEASONAL_MONSOON_PRECIPITATION_STRENGTH = 1.60;
constexpr double CLIMATE_SEASONAL_MONSOON_PRECIPITATION_MIN_FACTOR = 0.08;
constexpr double CLIMATE_SEASONAL_MONSOON_PRECIPITATION_MAX_FACTOR = 1.92;
constexpr double CLIMATE_STELLAR_TEMPERATURE_RESPONSE_C = 38.0;
constexpr double CLIMATE_GREENHOUSE_TEMPERATURE_RESPONSE_C = 11.0;
constexpr double CLIMATE_THERMAL_MOISTURE_REFERENCE_BASE_TEMPERATURE_C = 15.0;
// A 4%/C diagnostic response is deliberately weaker than saturation-vapor-pressure
// scaling because global precipitation is also energy and circulation limited.
// Bounds keep extreme configured worlds finite without erasing cold/hot ordering.
constexpr double CLIMATE_THERMAL_MOISTURE_RESPONSE_PER_C = 0.04;
constexpr double CLIMATE_THERMAL_MOISTURE_MIN_FACTOR = 0.35;
constexpr double CLIMATE_THERMAL_MOISTURE_MAX_FACTOR = 2.25;
constexpr int INITIAL_CRUST_COHERENCE_SMOOTHING_STEPS = 1;
constexpr double INITIAL_CRUST_COHERENCE_SELF_WEIGHT = 0.77;
constexpr int SECONDARY_RELIEF_SMOOTHING_STEPS = 4;
constexpr double SECONDARY_RELIEF_SELF_WEIGHT = 0.58;
constexpr double CONTINENTAL_ISOSTATIC_FREEBOARD_M = 500.0;
constexpr double CONTINENTAL_REFERENCE_CRUST_THICKNESS_KM = 30.0;
constexpr double CONTINENTAL_CRUST_THICKNESS_FREEBOARD_M_PER_KM = 12.0;
constexpr double CONTINENTAL_REFERENCE_CRUST_DENSITY_G_CM3 = 2.72;
constexpr double CONTINENTAL_CRUST_DENSITY_FREEBOARD_M_PER_G_CM3 = 1800.0;
// Parsons and Sclater (1977) give 2500 m as the zero-age intercept of
// ocean-floor depth.  Thermal subsidence is added separately by the
// age-depth target, so using a deeper baseline would count part of that
// depth twice.
constexpr double OCEANIC_RIDGE_REFERENCE_DEPTH_M = 2500.0;
// A 200 Ma procedural ceiling covers the dominant present-day seafloor-age
// distribution but is not a physical maximum: the pinned Seton et al. (2020)
// grid contains a rare older tail to about 339 Ma. Younger planets retain the
// stricter planet-age ceiling, and capped/unreachable cells remain explicit in
// the initialization ledger.
constexpr double INITIAL_OCEANIC_CRUST_MAX_AGE_MA = 200.0;
constexpr double CONTINENTAL_OROGEN_UPLIFT_SCALE_M = 20000.0;
constexpr double OCEANIC_TRENCH_SUBSIDENCE_SCALE_M = 17000.0;
constexpr double VOLCANIC_ARC_TRENCH_SUBSIDENCE_SCALE_M = 1400.0;
constexpr double VOLCANIC_ARC_UPLIFT_SCALE_M = 15000.0;
constexpr double HYDROLOGIC_FLAT_GRADIENT_STEP_M = 0.001;
constexpr double HYDROLOGIC_PET_TEMPERATURE_OFFSET_C = 8.0;
constexpr double HYDROLOGIC_PET_SCALE_MM_Y_PER_C = 31.0;
constexpr double HYDROLOGIC_CLIMATE_LOSS_FRACTION = 0.68;
constexpr double HYDROLOGIC_INFILTRATION_BASE_SHARE = 0.10;
constexpr double HYDROLOGIC_INFILTRATION_CAPACITY_SHARE = 0.50;
constexpr double HYDROLOGIC_MIN_INFILTRATION_CAPACITY = 0.02;
constexpr double HYDROLOGIC_MAX_INFILTRATION_CAPACITY = 0.90;
constexpr int NUMERIC_DEPRESSION_FILL_MAX_PASSES = 16;
constexpr double NUMERIC_DEPRESSION_FILL_DEPTH_TOLERANCE_M = 1.0e-9;
constexpr double NUMERIC_DEPRESSION_BREACH_GRADIENT_STEP_M = 0.001;
constexpr double NUMERIC_DEPRESSION_SELECTED_BREACH_MAX_DEPTH_M = 50.0;
constexpr double FLUVIAL_SEDIMENT_MIN_TRANSPORT_CAPACITY_FRACTION = 0.90;
constexpr double FLUVIAL_SEDIMENT_MAX_TRANSPORT_CAPACITY_FRACTION = 0.995;
constexpr double FLUVIAL_SEDIMENT_LAKE_TRAP_FRACTION = 0.35;
constexpr double FLUVIAL_SEDIMENT_CLOSED_LAKE_TRAP_FRACTION = 0.65;
constexpr double FLUVIAL_SEDIMENT_OPEN_OCEAN_DEPOSITION_FRACTION = 0.12;
constexpr double FLUVIAL_SEDIMENT_SHELF_DEPOSITION_FRACTION = 0.55;
constexpr double FLUVIAL_SEDIMENT_INLAND_SEA_DEPOSITION_FRACTION = 0.30;
constexpr double HILLSLOPE_MAX_EFFECTIVE_DIFFUSIVITY = 0.45;
constexpr double GLACIAL_SEDIMENT_MOBILE_FRACTION = 0.28;
// Existing per-step coefficients are reference-normalized to the shipped 5 Ma
// crust-aging setting. Other nominal timesteps scale continuous mutations
// against this reference so temporal refinement changes resolution rather than
// only the number of process applications. This is not physical calibration.
constexpr double MATURATION_REFERENCE_TIMESTEP_MA = 5.0;
enum CrustProcessReason : int {
    CRUST_PROCESS_QUIET_OCEANIC_AGING = 0,
    CRUST_PROCESS_OCEANIC_RIDGE_REJUVENATION = 1,
    CRUST_PROCESS_OCEANIC_RIDGE_CREATION_RELAXATION = 2,
    CRUST_PROCESS_DIVERGENT_CONTINENTAL_RIFTING = 3,
    CRUST_PROCESS_OCEANIC_CONVERGENCE_SUBDUCTION_PROXY = 4,
    CRUST_PROCESS_CONTINENTAL_COLLISION_OROGENY = 5,
    CRUST_PROCESS_PLATE_CROSSING_ACCRETION_PROXY = 6,
    CRUST_PROCESS_AGE_BOUND_ENFORCEMENT = 7,
    CRUST_PROCESS_THICKNESS_BOUND_ENFORCEMENT = 8,
    CRUST_PROCESS_DENSITY_BOUND_ENFORCEMENT = 9,
};
constexpr int CRUST_PROCESS_REASON_COUNT = 10;
constexpr const char* CRUST_PROCESS_REASON_NAMES[CRUST_PROCESS_REASON_COUNT] = {
    "quiet_oceanic_aging",
    "oceanic_ridge_rejuvenation",
    "oceanic_ridge_creation_relaxation",
    "divergent_continental_rifting",
    "oceanic_convergence_subduction_proxy",
    "continental_collision_orogeny",
    "plate_crossing_accretion_proxy",
    "age_bound_enforcement",
    "thickness_bound_enforcement",
    "density_bound_enforcement",
};
constexpr int MESH_BACKEND_FIBONACCI = 0;
constexpr int MESH_BACKEND_GEODESIC_ICOSAHEDRON = 1;

}  // namespace magic_geo::detail
