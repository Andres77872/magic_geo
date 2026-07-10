#include "magic_geo/native.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <limits>
#include <map>
#include <numeric>
#include <queue>
#include <random>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <utility>
#include <vector>

#ifdef _OPENMP
#include <omp.h>
#endif

namespace magic_geo {
namespace {

constexpr double PI = 3.141592653589793238462643383279502884;
constexpr double DEG = 180.0 / PI;
constexpr double CLIMATE_LATITUDE_TEMPERATURE_GRADIENT_C = 47.0;
constexpr double CLIMATE_LATITUDE_TEMPERATURE_EXPONENT = 3.0;
constexpr double CLIMATE_SUBTROPICAL_DRYING_MIN_FACTOR = 0.25;
constexpr double CLIMATE_MARINE_ANNUAL_TEMPERATURE_OFFSET_C = 0.0;
constexpr double CLIMATE_SEASONAL_MONSOON_PRECIPITATION_STRENGTH = 1.60;
constexpr double CLIMATE_SEASONAL_MONSOON_PRECIPITATION_MIN_FACTOR = 0.08;
constexpr double CLIMATE_SEASONAL_MONSOON_PRECIPITATION_MAX_FACTOR = 1.92;
constexpr int INITIAL_CRUST_COHERENCE_SMOOTHING_STEPS = 1;
constexpr double INITIAL_CRUST_COHERENCE_SELF_WEIGHT = 0.77;
constexpr int SECONDARY_RELIEF_SMOOTHING_STEPS = 4;
constexpr double SECONDARY_RELIEF_SELF_WEIGHT = 0.58;
constexpr double CONTINENTAL_ISOSTATIC_FREEBOARD_M = 500.0;
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
constexpr int MESH_BACKEND_FIBONACCI = 0;
constexpr int MESH_BACKEND_GEODESIC_ICOSAHEDRON = 1;

struct Vec3 {
    double x = 0.0;
    double y = 0.0;
    double z = 0.0;
};

struct Plate {
    int id = 0;
    Vec3 axis;
    Vec3 initial_center;
    Vec3 center;
    double angular_speed = 0.0;
    double cumulative_rotation_deg = 0.0;
    int kind = 0;
    double crust_density = 0.0;
    double crust_thickness_km = 0.0;
    int cell_count = 0;
    double area_km2 = 0.0;
    double mean_crust_age_ma = 0.0;
    double mean_crust_density = 0.0;
    double mean_crust_thickness_km = 0.0;
    int dominant_crust_type = 0;
    int dominant_lithology = 0;
    double mean_boundary_activity = 0.0;
    double mean_heat_flow_mw_m2 = 0.0;
};

struct Cell {
    int id = 0;
    Vec3 p;
    double lat = 0.0;
    double lon = 0.0;
    double area_km2 = 0.0;
    std::vector<int> neighbors;
    int plate_id = 0;
    int initial_plate_id = 0;
    int plate_assignment_change_count = 0;
    int last_plate_assignment_change_iteration = -1;
    int last_crust_source_cell_id = -1;
    int crust_source_remap_event_count = 0;
    int oceanic_crust_aging_event_count = 0;
    int oceanic_crust_rejuvenation_event_count = 0;
    int oceanic_crust_subduction_event_count = 0;
    double cumulative_crust_transport_distance_km = 0.0;
    int crust_type = 0;
    int lithology = 0;
    int boundary_type = 0;
    int soil_type = 0;
    int biome = 0;
    int resource = 0;
    int landform = 0;
    int water_body = 0;
    int political_region_id = -1;
    int culture_region_id = -1;
    int language_region_id = -1;
    int basin_id = -1;
    double crust_age_ma = 0.0;
    double crust_thickness_km = 0.0;
    double crust_density = 0.0;
    double initial_crust_age_ma = 0.0;
    double initial_crust_thickness_km = 0.0;
    double initial_crust_density = 0.0;
    double cumulative_tectonic_elevation_change_m = 0.0;
    double boundary_convergent = 0.0;
    double boundary_divergent = 0.0;
    double boundary_transform = 0.0;
    double initial_isostatic_elevation_m = 0.0;
    double initial_thermal_subsidence_m = 0.0;
    double initial_ridge_uplift_m = 0.0;
    double initial_orogenic_uplift_m = 0.0;
    double initial_volcanic_uplift_m = 0.0;
    double initial_trench_subsidence_m = 0.0;
    double initial_rift_subsidence_m = 0.0;
    double initial_transform_fault_relief_m = 0.0;
    double initial_secondary_roughness_m = 0.0;
    double initial_elevation_m = 0.0;
    double volcanic_potential_index = 0.0;
    double uplift_rate = 0.0;
    double elevation_m = 0.0;
    double water_depth_m = 0.0;
    bool is_water = false;
    bool is_river = false;
    bool is_lake = false;
    double temperature_c = 0.0;
    double precipitation_mm_y = 0.0;
    std::vector<double> temperature_monthly_c;
    std::vector<double> precipitation_monthly_mm;
    double wind_east = 0.0;
    double wind_north = 0.0;
    std::vector<double> wind_monthly_east;
    std::vector<double> wind_monthly_north;
    double mean_seasonal_wind_speed = 0.0;
    double seasonal_wind_reversal_index = 0.0;
    int atmospheric_cell = 0;
    double surface_pressure_anomaly_hpa = 0.0;
    double vertical_velocity_index = 0.0;
    double wind_divergence_index = 0.0;
    double ocean_current_east = 0.0;
    double ocean_current_north = 0.0;
    double ocean_current_temperature_c = 0.0;
    double ocean_current_moisture_factor = 1.0;
    double humidity_transport_index = 0.0;
    double upwind_ocean_fetch_km = 0.0;
    double advected_moisture_factor = 1.0;
    double orographic_factor = 1.0;
    double rain_shadow_factor = 1.0;
    double vapor_evaporation_mm_y = 0.0;
    double moisture_convergence_mm_y = 0.0;
    double orographic_rainout_mm_y = 0.0;
    double precipitation_recycling_fraction = 0.0;
    double vapor_deficit_mm_y = 0.0;
    double vapor_budget_residual_mm_y = 0.0;
    double hydrologic_potential_evapotranspiration_mm_y = 0.0;
    double actual_evapotranspiration_mm_y = 0.0;
    double infiltration_capacity_index = 0.0;
    double infiltration_mm_y = 0.0;
    double hydrologic_water_balance_mm_y = 0.0;
    double water_budget_runoff_mm_y = 0.0;
    double runoff_budget_residual_mm_y = 0.0;
    double runoff_budget_consistency_index = 1.0;
    double hydrologic_deficit_mm_y = 0.0;
    double runoff_generation_fraction = 0.0;
    double runoff_mm_y = 0.0;
    int flow_to = -1;
    bool equal_filled_raw_downhill_rerouted = false;
    int spill_to = -1;
    int depression_component_id = -1;
    int depression_sink_cell_id = -1;
    int lake_basin_id = -1;
    int depression_policy = 0;
    double flow_accumulation = 0.0;
    double filled_elevation_m = 0.0;
    double hydrologic_surface_elevation_m = 0.0;
    double hydrologic_flow_drop_m = 0.0;
    double hydrologic_flow_slope = 0.0;
    bool hydrologic_surface_conditioned = false;
    double depression_depth_m = 0.0;
    double spill_elevation_m = 0.0;
    double lake_fill_fraction = 0.0;
    bool is_closed_basin = false;
    bool lake_overflows = false;
    double cumulative_numeric_depression_fill_m = 0.0;
    int numeric_depression_fill_event_count = 0;
    double cumulative_numeric_depression_breach_excavation_m = 0.0;
    double cumulative_numeric_depression_breach_deposition_m = 0.0;
    int numeric_depression_breach_event_count = 0;
    bool numeric_depression_temporary_lake_deferred = false;
    int numeric_depression_temporary_lake_event_count = 0;
    double erosion_rate = 0.0;
    double sediment_thickness_m = 0.0;
    double sediment_production_m = 0.0;
    double sediment_deposition_m = 0.0;
    double sediment_export_m = 0.0;
    double sediment_net_budget_m = 0.0;
    double sediment_alluvium_entrainment_m = 0.0;
    double sediment_bedrock_erosion_m = 0.0;
    double fluvial_sediment_local_source_m = 0.0;
    double fluvial_sediment_routed_incoming_m = 0.0;
    double fluvial_sediment_routed_outgoing_m = 0.0;
    double fluvial_sediment_local_deposition_m = 0.0;
    double fluvial_sediment_terminal_land_deposition_m = 0.0;
    double fluvial_sediment_marine_deposition_m = 0.0;
    double fluvial_sediment_depression_fill_m = 0.0;
    double fluvial_sediment_terminal_export_m = 0.0;
    double fluvial_sediment_terminal_capture_volume_km3 = 0.0;
    int fluvial_sediment_routing_event_count = 0;
    double hillslope_sediment_production_m = 0.0;
    double hillslope_sediment_deposition_m = 0.0;
    double hillslope_sediment_net_m = 0.0;
    int hillslope_sediment_outgoing_edge_count = 0;
    int hillslope_sediment_incoming_edge_count = 0;
    double ice_thickness_m = 0.0;
    int ice_sheet_id = -1;
    int glacier_flow_to = -1;
    double ice_surface_mass_balance_m_y = 0.0;
    double basal_sliding_index = 0.0;
    double ice_velocity_m_y = 0.0;
    double glacial_erosion_m = 0.0;
    double glacial_sediment_production_m = 0.0;
    double glacial_sediment_deposition_m = 0.0;
    double glacial_sediment_net_m = 0.0;
    int glacial_sediment_outgoing_transfer_count = 0;
    int glacial_sediment_incoming_transfer_count = 0;
    double moraine_deposition_m = 0.0;
    double deglaciation_age_ka = 0.0;
    double soil_depth_m = 0.0;
    double fertility = 0.0;
    double settlement_score = 0.0;
};

struct FeedbackReference {
    std::vector<double> elevation_m;
    std::vector<double> temperature_c;
    std::vector<double> precipitation_mm_y;
    std::vector<double> runoff_mm_y;
};

struct NumericDepressionFillEvent {
    int id = 0;
    int feedback_stage_id = 0;
    std::string stage;
    int erosion_iteration = -1;
    int stabilization_pass = 0;
    int source_depression_component_id = -1;
    int sink_cell_id = -1;
    int sink_crust_type = 0;
    bool sink_is_geologic = false;
    double sink_boundary_divergent = 0.0;
    double sink_boundary_convergent = 0.0;
    std::vector<int> cell_ids;
    std::vector<double> elevation_before_fill_m_by_cell;
    std::vector<double> sediment_thickness_before_correction_m_by_cell;
    std::vector<double> fill_depth_m_by_cell;
    std::vector<double> elevation_after_fill_m_by_cell;
    double area_km2 = 0.0;
    double fill_volume_km3 = 0.0;
    double max_fill_depth_m = 0.0;
    bool breach_feasible = false;
    int breach_outlet_cell_id = -1;
    std::vector<int> breach_path_cell_ids;
    std::vector<double> breach_elevation_before_m_by_cell;
    std::vector<double> breach_target_elevation_m_by_cell;
    std::vector<double> breach_excavation_depth_m_by_cell;
    std::vector<double> breach_sediment_thickness_before_excavation_m_by_cell;
    std::vector<double> breach_alluvium_entrainment_depth_m_by_cell;
    std::vector<double> breach_bedrock_erosion_depth_m_by_cell;
    double breach_path_length_km = 0.0;
    double breach_excavation_area_km2 = 0.0;
    double breach_excavation_volume_km3 = 0.0;
    double max_breach_excavation_depth_m = 0.0;
    double breach_to_fill_volume_ratio = 0.0;
    bool breach_has_lower_adjustment_volume = false;
    bool breach_depth_bound_passed = false;
    bool breach_deposition_capacity_sufficient = false;
    bool breach_same_pass_conflict_free = false;
    bool breach_selected = false;
    bool temporary_numeric_lake_selected = false;
    double breach_deposition_capacity_km3 = 0.0;
    std::vector<int> breach_deposition_cell_ids;
    std::vector<double> breach_deposition_depth_m_by_cell;
    double applied_fill_volume_km3 = 0.0;
    double applied_breach_excavation_volume_km3 = 0.0;
    double applied_breach_deposition_volume_km3 = 0.0;
    double applied_alluvium_entrainment_volume_km3 = 0.0;
    double applied_bedrock_erosion_volume_km3 = 0.0;
    double correction_mass_balance_residual_km3 = 0.0;
};

struct HydrologyStabilizationResult {
    int sea_level_recompute_count = 0;
    int climate_recompute_count = 0;
    int hydrologic_water_budget_recompute_count = 0;
    int hydrology_recompute_count = 0;
    int numeric_depression_fill_pass_count = 0;
    int numeric_depression_fill_event_count = 0;
    int numeric_depression_fill_cell_application_count = 0;
    int numeric_depression_filled_unique_cell_count = 0;
    int numeric_depression_correction_event_count = 0;
    int numeric_depression_breach_selected_event_count = 0;
    int numeric_depression_breach_excavation_cell_application_count = 0;
    int numeric_depression_breach_deposition_cell_application_count = 0;
    int numeric_depression_temporary_lake_event_count = 0;
    int numeric_depression_temporary_lake_cell_application_count = 0;
    int numeric_depression_temporary_lake_unique_cell_count = 0;
    double sea_level_adjustment_m = 0.0;
    double numeric_depression_fill_area_km2 = 0.0;
    double numeric_depression_fill_volume_km3 = 0.0;
    double max_numeric_depression_fill_depth_m = 0.0;
    double numeric_depression_breach_excavation_volume_km3 = 0.0;
    double numeric_depression_breach_deposition_volume_km3 = 0.0;
    double numeric_depression_alluvium_entrainment_volume_km3 = 0.0;
    double numeric_depression_bedrock_erosion_volume_km3 = 0.0;
    double numeric_depression_correction_mass_balance_residual_km3 = 0.0;
    double numeric_depression_temporary_lake_candidate_area_km2 = 0.0;
    double numeric_depression_temporary_lake_candidate_volume_km3 = 0.0;
    double max_numeric_depression_temporary_lake_depth_m = 0.0;
};

struct HydrologicWaterBudgetStage {
    int id = 0;
    int feedback_stage_id = 0;
    int erosion_iteration = -1;
    int stabilization_recomputation_index = 0;
    std::string stage;
    int cell_count = 0;
    int land_cell_count = 0;
    int marine_cell_count = 0;
    double land_precipitation_volume_km3_y = 0.0;
    double actual_evapotranspiration_volume_km3_y = 0.0;
    double infiltration_volume_km3_y = 0.0;
    double runoff_volume_km3_y = 0.0;
    double mass_balance_residual_km3_y = 0.0;
    double max_abs_cell_residual_mm_y = 0.0;
    std::vector<int> cell_ids;
    std::vector<int> is_marine_by_cell;
    std::vector<int> lithology_by_cell;
    std::vector<double> cell_area_km2_by_cell;
    std::vector<double> elevation_m_by_cell;
    std::vector<double> temperature_c_by_cell;
    std::vector<double> precipitation_mm_y_by_cell;
    std::vector<double> local_relief_m_by_cell;
    std::vector<double> sediment_thickness_m_by_cell;
    std::vector<double> ice_thickness_m_by_cell;
    std::vector<double> potential_evapotranspiration_mm_y_by_cell;
    std::vector<double> infiltration_capacity_index_by_cell;
    std::vector<double> actual_evapotranspiration_mm_y_by_cell;
    std::vector<double> infiltration_mm_y_by_cell;
    std::vector<double> water_balance_mm_y_by_cell;
    std::vector<double> runoff_mm_y_by_cell;
    std::vector<double> residual_mm_y_by_cell;
};

struct FluvialSedimentRoutingCellStep {
    int cell_id = -1;
    int flow_to_cell_id = -1;
    int depression_component_id = -1;
    int depression_sink_cell_id = -1;
    int water_body = 0;
    bool is_water = false;
    bool is_river = false;
    bool is_lake = false;
    bool lake_overflows = false;
    bool is_land_terminal = false;
    bool is_marine_terminal = false;
    double cell_area_km2 = 0.0;
    double flow_accumulation = 0.0;
    double runoff_mm_y = 0.0;
    double hydrologic_flow_slope = 0.0;
    double routing_base_elevation_m = 0.0;
    double spill_elevation_m = 0.0;
    double local_source_volume_km3 = 0.0;
    double incoming_volume_km3 = 0.0;
    double available_volume_km3 = 0.0;
    double transport_capacity_fraction = 0.0;
    double depression_accommodation_volume_km3 = 0.0;
    double capacity_deposition_volume_km3 = 0.0;
    double depression_fill_deposition_volume_km3 = 0.0;
    double lake_trap_deposition_volume_km3 = 0.0;
    double marine_deposition_volume_km3 = 0.0;
    double routed_outgoing_volume_km3 = 0.0;
    double terminal_land_storage_volume_km3 = 0.0;
    double terminal_export_volume_km3 = 0.0;
    double local_mass_balance_residual_km3 = 0.0;
};

struct FluvialSedimentTerminalAllocation {
    int sink_cell_id = -1;
    int target_cell_id = -1;
    int depression_component_id = -1;
    double target_area_km2 = 0.0;
    double routing_base_elevation_m = 0.0;
    double spill_elevation_m = 0.0;
    double prior_local_deposition_volume_km3 = 0.0;
    double accommodation_before_allocation_km3 = 0.0;
    double accommodation_deposition_volume_km3 = 0.0;
    double excess_aggradation_volume_km3 = 0.0;
    double total_deposition_volume_km3 = 0.0;
};

struct FluvialSedimentRoutingStage {
    int id = 0;
    int feedback_stage_id = 0;
    int erosion_iteration = 0;
    int active_cell_step_count = 0;
    int routed_edge_count = 0;
    int land_terminal_count = 0;
    int marine_terminal_count = 0;
    int terminal_allocation_count = 0;
    double accumulation_scale = 1.0;
    double local_source_volume_km3 = 0.0;
    double routed_throughput_volume_km3 = 0.0;
    double capacity_deposition_volume_km3 = 0.0;
    double depression_fill_deposition_volume_km3 = 0.0;
    double lake_trap_deposition_volume_km3 = 0.0;
    double terminal_land_deposition_volume_km3 = 0.0;
    double marine_deposition_volume_km3 = 0.0;
    double terminal_export_volume_km3 = 0.0;
    double mass_balance_residual_km3 = 0.0;
    double alluvium_entrainment_volume_km3 = 0.0;
    double bedrock_erosion_volume_km3 = 0.0;
    std::vector<FluvialSedimentRoutingCellStep> cell_steps;
    std::vector<FluvialSedimentTerminalAllocation> terminal_allocations;
};

struct HillslopeSedimentTransportEdge {
    int id = 0;
    int mesh_edge_cell_a_id = -1;
    int mesh_edge_cell_b_id = -1;
    int source_cell_id = -1;
    int target_cell_id = -1;
    int source_lithology = 0;
    int source_neighbor_count = 0;
    bool target_is_water = false;
    bool target_is_lake = false;
    double source_area_km2 = 0.0;
    double target_area_km2 = 0.0;
    double source_elevation_m = 0.0;
    double target_elevation_m = 0.0;
    double elevation_drop_m = 0.0;
    double source_lithology_resistance = 1.0;
    double effective_diffusivity = 0.0;
    double source_production_depth_m = 0.0;
    double target_deposition_depth_m = 0.0;
    double transfer_volume_km3 = 0.0;
    double mass_balance_residual_km3 = 0.0;
};

struct HillslopeSedimentTransportInputCell {
    int cell_id = -1;
    int lithology = 0;
    bool is_water = false;
    bool is_lake = false;
    double elevation_m = 0.0;
    double sediment_thickness_m = 0.0;
};

struct HillslopeSedimentTransportStage {
    int id = 0;
    int feedback_stage_id = 0;
    int erosion_iteration = 0;
    int transport_edge_count = 0;
    int source_cell_count = 0;
    int target_cell_count = 0;
    int land_to_land_edge_count = 0;
    int land_to_marine_edge_count = 0;
    double production_volume_km3 = 0.0;
    double deposition_volume_km3 = 0.0;
    double mass_balance_residual_km3 = 0.0;
    double alluvium_entrainment_volume_km3 = 0.0;
    double bedrock_erosion_volume_km3 = 0.0;
    double max_source_production_depth_m = 0.0;
    double max_target_deposition_depth_m = 0.0;
    double mean_effective_diffusivity = 0.0;
    std::vector<HillslopeSedimentTransportInputCell> input_cells;
    std::vector<HillslopeSedimentTransportEdge> edges;
};

struct GlacialSedimentTransportInputCell {
    int cell_id = -1;
    int glacier_flow_to_cell_id = -1;
    bool is_water = false;
    double elevation_m = 0.0;
    double ice_thickness_m = 0.0;
    double glacial_erosion_m = 0.0;
    double sediment_thickness_m = 0.0;
};

struct GlacialSedimentTransfer {
    int id = 0;
    int source_cell_id = -1;
    int target_cell_id = -1;
    bool target_is_water = false;
    double source_area_km2 = 0.0;
    double target_area_km2 = 0.0;
    double source_elevation_m = 0.0;
    double target_elevation_m = 0.0;
    double elevation_drop_m = 0.0;
    double source_ice_thickness_m = 0.0;
    double source_glacial_erosion_m = 0.0;
    double source_production_depth_m = 0.0;
    double target_deposition_depth_m = 0.0;
    double transfer_volume_km3 = 0.0;
    double mass_balance_residual_km3 = 0.0;
};

struct GlacialSedimentTransportStage {
    int id = 0;
    int feedback_stage_id = 0;
    int transfer_count = 0;
    int source_cell_count = 0;
    int target_cell_count = 0;
    int land_target_transfer_count = 0;
    int marine_target_transfer_count = 0;
    double production_volume_km3 = 0.0;
    double deposition_volume_km3 = 0.0;
    double mass_balance_residual_km3 = 0.0;
    double terrain_volume_change_residual_km3 = 0.0;
    double alluvium_entrainment_volume_km3 = 0.0;
    double bedrock_erosion_volume_km3 = 0.0;
    double max_source_production_depth_m = 0.0;
    double max_target_deposition_depth_m = 0.0;
    std::vector<GlacialSedimentTransportInputCell> input_cells;
    std::vector<GlacialSedimentTransfer> transfers;
    std::vector<double> post_transport_elevation_m_by_cell;
};

struct EarthSystemFeedbackStep {
    int id = 0;
    int erosion_iteration = -1;
    std::string stage;
    bool sea_level_recomputed = false;
    bool climate_recomputed = false;
    bool hydrologic_water_budget_recomputed = false;
    bool hydrology_recomputed = false;
    bool erosion_applied = false;
    bool cryosphere_applied = false;
    bool plate_motion_applied = false;
    bool crust_transport_applied = false;
    bool crust_evolution_applied = false;
    int sea_level_recompute_count = 0;
    int climate_recompute_count = 0;
    int hydrologic_water_budget_recompute_count = 0;
    int hydrology_recompute_count = 0;
    int numeric_depression_fill_pass_count = 0;
    int numeric_depression_fill_event_count = 0;
    int numeric_depression_fill_cell_application_count = 0;
    int numeric_depression_filled_unique_cell_count = 0;
    int numeric_depression_correction_event_count = 0;
    int numeric_depression_breach_selected_event_count = 0;
    int numeric_depression_breach_excavation_cell_application_count = 0;
    int numeric_depression_breach_deposition_cell_application_count = 0;
    int numeric_depression_temporary_lake_event_count = 0;
    int numeric_depression_temporary_lake_cell_application_count = 0;
    int numeric_depression_temporary_lake_unique_cell_count = 0;
    int fluvial_sediment_active_cell_step_count = 0;
    int fluvial_sediment_routed_edge_count = 0;
    int fluvial_sediment_land_terminal_count = 0;
    int fluvial_sediment_marine_terminal_count = 0;
    int fluvial_sediment_terminal_allocation_count = 0;
    int hillslope_sediment_transport_edge_count = 0;
    int hillslope_sediment_source_cell_count = 0;
    int hillslope_sediment_target_cell_count = 0;
    int hillslope_sediment_land_to_land_edge_count = 0;
    int hillslope_sediment_land_to_marine_edge_count = 0;
    int glacial_sediment_transfer_count = 0;
    int glacial_sediment_source_cell_count = 0;
    int glacial_sediment_target_cell_count = 0;
    int glacial_sediment_land_target_transfer_count = 0;
    int glacial_sediment_marine_target_transfer_count = 0;
    int plate_motion_history_id = 0;
    int cell_count = 0;
    int land_cell_count = 0;
    int water_cell_count = 0;
    int river_cell_count = 0;
    double sea_level_adjustment_m = 0.0;
    double numeric_depression_fill_area_km2 = 0.0;
    double numeric_depression_fill_volume_km3 = 0.0;
    double max_numeric_depression_fill_depth_m = 0.0;
    double numeric_depression_breach_excavation_volume_km3 = 0.0;
    double numeric_depression_breach_deposition_volume_km3 = 0.0;
    double numeric_depression_correction_mass_balance_residual_km3 = 0.0;
    double numeric_depression_temporary_lake_candidate_area_km2 = 0.0;
    double numeric_depression_temporary_lake_candidate_volume_km3 = 0.0;
    double max_numeric_depression_temporary_lake_depth_m = 0.0;
    double fluvial_sediment_local_source_volume_km3 = 0.0;
    double fluvial_sediment_routed_throughput_volume_km3 = 0.0;
    double fluvial_sediment_capacity_deposition_volume_km3 = 0.0;
    double fluvial_sediment_depression_fill_deposition_volume_km3 = 0.0;
    double fluvial_sediment_lake_trap_deposition_volume_km3 = 0.0;
    double fluvial_sediment_terminal_land_deposition_volume_km3 = 0.0;
    double fluvial_sediment_marine_deposition_volume_km3 = 0.0;
    double fluvial_sediment_terminal_export_volume_km3 = 0.0;
    double fluvial_sediment_mass_balance_residual_km3 = 0.0;
    double hillslope_sediment_production_volume_km3 = 0.0;
    double hillslope_sediment_deposition_volume_km3 = 0.0;
    double hillslope_sediment_mass_balance_residual_km3 = 0.0;
    double max_hillslope_sediment_source_production_depth_m = 0.0;
    double max_hillslope_sediment_target_deposition_depth_m = 0.0;
    double mean_hillslope_effective_diffusivity = 0.0;
    double glacial_sediment_production_volume_km3 = 0.0;
    double glacial_sediment_deposition_volume_km3 = 0.0;
    double glacial_sediment_mass_balance_residual_km3 = 0.0;
    double glacial_sediment_terrain_volume_change_residual_km3 = 0.0;
    double max_glacial_sediment_source_production_depth_m = 0.0;
    double max_glacial_sediment_target_deposition_depth_m = 0.0;
    double sediment_alluvium_entrainment_volume_km3 = 0.0;
    double sediment_bedrock_erosion_volume_km3 = 0.0;
    double sediment_inventory_volume_km3 = 0.0;
    double sediment_source_partition_residual_km3 = 0.0;
    double sediment_inventory_mass_balance_residual_km3 = 0.0;
    double surface_area_km2 = 0.0;
    double ocean_area_km2 = 0.0;
    double ocean_volume_km3 = 0.0;
    double ocean_fraction = 0.0;
    double mean_elevation_m = 0.0;
    double mean_land_elevation_m = 0.0;
    double min_elevation_m = 0.0;
    double max_elevation_m = 0.0;
    double mean_temperature_c = 0.0;
    double mean_precipitation_mm_y = 0.0;
    double mean_runoff_mm_y = 0.0;
    double hydrologic_land_precipitation_volume_km3_y = 0.0;
    double hydrologic_actual_evapotranspiration_volume_km3_y = 0.0;
    double hydrologic_infiltration_volume_km3_y = 0.0;
    double hydrologic_runoff_volume_km3_y = 0.0;
    double hydrologic_water_budget_residual_km3_y = 0.0;
    double max_abs_hydrologic_water_budget_cell_residual_mm_y = 0.0;
    double mean_erosion_rate_m_per_step = 0.0;
    double mean_sediment_thickness_m = 0.0;
    double mean_cumulative_sediment_production_m = 0.0;
    double mean_cumulative_sediment_deposition_m = 0.0;
    double mean_cumulative_sediment_export_m = 0.0;
    double cumulative_sediment_production_volume_km3 = 0.0;
    double cumulative_sediment_deposition_volume_km3 = 0.0;
    double cumulative_sediment_export_volume_km3 = 0.0;
    double mean_abs_elevation_change_m_from_previous_stage = 0.0;
    double mean_abs_temperature_change_c_from_previous_stage = 0.0;
    double mean_abs_precipitation_change_mm_y_from_previous_stage = 0.0;
    double mean_abs_runoff_change_mm_y_from_previous_stage = 0.0;
};

struct PlateKinematicSnapshot {
    int plate_id = 0;
    Vec3 center;
    double step_rotation_deg = 0.0;
    double cumulative_rotation_deg = 0.0;
    int cell_count = 0;
    double area_km2 = 0.0;
};

struct CrustMotionDiagnostics {
    std::vector<int> source_cell_ids;
    std::vector<double> transport_distance_km_by_cell;
    std::vector<double> age_transport_change_ma_by_cell;
    std::vector<double> thickness_transport_change_km_by_cell;
    std::vector<double> density_transport_change_by_cell;
    std::vector<double> age_process_change_ma_by_cell;
    std::vector<double> thickness_process_change_km_by_cell;
    std::vector<double> density_process_change_by_cell;
    std::vector<int> aged_oceanic_cell_ids;
    std::vector<int> rejuvenated_oceanic_cell_ids;
    std::vector<int> subducted_oceanic_cell_ids;
};

struct PlateMotionStep {
    int id = 0;
    int erosion_iteration = -1;
    std::string stage;
    int cell_count = 0;
    int plate_count = 0;
    int reassigned_cell_count = 0;
    int plate_boundary_cell_count = 0;
    int plate_boundary_edge_count = 0;
    int accreted_terrane_cell_count = 0;
    int crust_source_remap_cell_count = 0;
    int unique_crust_source_cell_count = 0;
    int crust_source_reuse_count = 0;
    int aged_oceanic_cell_count = 0;
    int rejuvenated_oceanic_cell_count = 0;
    int subducted_oceanic_cell_count = 0;
    double reassigned_cell_fraction = 0.0;
    double mean_plate_rotation_deg = 0.0;
    double max_plate_rotation_deg = 0.0;
    double mean_crust_transport_distance_km = 0.0;
    double max_crust_transport_distance_km = 0.0;
    double mean_abs_crust_age_change_ma = 0.0;
    double mean_abs_crust_thickness_change_km = 0.0;
    double mean_abs_crust_density_change = 0.0;
    double mean_abs_crust_age_transport_change_ma = 0.0;
    double mean_abs_crust_thickness_transport_change_km = 0.0;
    double mean_abs_crust_density_transport_change = 0.0;
    double mean_abs_crust_age_process_change_ma = 0.0;
    double mean_abs_crust_thickness_process_change_km = 0.0;
    double mean_abs_crust_density_process_change = 0.0;
    double mean_tectonic_elevation_change_m = 0.0;
    double mean_abs_tectonic_elevation_change_m = 0.0;
    double max_abs_tectonic_elevation_change_m = 0.0;
    std::vector<int> cell_plate_ids;
    std::vector<int> crust_source_cell_ids;
    std::vector<int> crust_type_by_cell;
    std::vector<int> lithology_by_cell;
    std::vector<double> crust_transport_distance_km_by_cell;
    std::vector<double> crust_age_change_ma_by_cell;
    std::vector<double> crust_thickness_change_km_by_cell;
    std::vector<double> crust_density_change_by_cell;
    std::vector<double> crust_age_transport_change_ma_by_cell;
    std::vector<double> crust_thickness_transport_change_km_by_cell;
    std::vector<double> crust_density_transport_change_by_cell;
    std::vector<double> crust_age_process_change_ma_by_cell;
    std::vector<double> crust_thickness_process_change_km_by_cell;
    std::vector<double> crust_density_process_change_by_cell;
    std::vector<double> tectonic_elevation_change_m_by_cell;
    std::vector<int> aged_oceanic_cell_ids;
    std::vector<int> rejuvenated_oceanic_cell_ids;
    std::vector<int> subducted_oceanic_cell_ids;
    std::vector<PlateKinematicSnapshot> plates;
};

struct Settlement {
    int id = 0;
    int cell_id = 0;
    int type = 0;
    int region_id = -1;
    int culture_region_id = -1;
    int language_region_id = -1;
    double score = 0.0;
};

struct Route {
    int id = 0;
    int from = 0;
    int to = 0;
    int type = 0;
    double distance_km = 0.0;
    double cost = 0.0;
};

struct TradeFlow {
    int id = 0;
    int route_id = 0;
    int from = 0;
    int to = 0;
    int region_from = -1;
    int region_to = -1;
    int primary_good = 0;
    bool interregional = false;
    double distance_km = 0.0;
    double friction = 1.0;
    double volume_index = 0.0;
};

struct CultureRegion {
    int id = 0;
    int language_region_id = -1;
    int homeland_region_id = -1;
    int type = 0;
    int dominant_biome = 0;
    int dominant_resource = 0;
    int settlement_count = 0;
    int sacred_area_count = 0;
    int ruin_count = 0;
    double area_km2 = 0.0;
    double agricultural_area_km2 = 0.0;
    double mining_area_km2 = 0.0;
    double mean_fertility = 0.0;
    double mean_elevation_m = 0.0;
    double barrier_isolation = 0.0;
    double trade_contact_index = 0.0;
    double migration_pressure = 0.0;
    double continuity_index = 0.0;
    double estimated_age_years = 0.0;
    std::vector<int> settlement_ids;
};

struct LanguageRegion {
    int id = 0;
    int parent_language_region_id = -1;
    int family = 0;
    int lineage_depth = 0;
    int culture_count = 0;
    int settlement_count = 0;
    double area_km2 = 0.0;
    double barrier_isolation = 0.0;
    double trade_contact_index = 0.0;
    double divergence_age_years = 0.0;
    double change_rate = 0.0;
    int phoneme_inventory_size = 0;
    double phonological_complexity = 0.0;
    double sound_shift_index = 0.0;
    double inherited_phonology_fraction = 1.0;
    std::vector<int> culture_ids;
};

struct SacredArea {
    int id = 0;
    int cell_id = 0;
    int culture_region_id = -1;
    int language_region_id = -1;
    int type = 0;
    double significance = 0.0;
    double lat_deg = 0.0;
    double lon_deg = 0.0;
};

struct Ruin {
    int id = 0;
    int cell_id = 0;
    int culture_region_id = -1;
    int language_region_id = -1;
    int type = 0;
    int abandonment_reason = 0;
    double significance = 0.0;
    double preservation_score = 0.0;
    double lat_deg = 0.0;
    double lon_deg = 0.0;
};

struct CulturalLayers {
    std::vector<CultureRegion> cultures;
    std::vector<LanguageRegion> language_regions;
    std::vector<SacredArea> sacred_areas;
    std::vector<Ruin> ruins;
};

struct HistoricalEra {
    int id = 0;
    int dominant_process = 0;
    int event_count = 0;
    int state_event_count = 0;
    int migration_event_count = 0;
    int language_event_count = 0;
    double start_year_bp = 0.0;
    double end_year_bp = 0.0;
    double mean_instability = 0.0;
    double mean_connectivity = 0.0;
};

struct HistoricalEvent {
    int id = 0;
    int era_id = 0;
    int type = 0;
    int region_id = -1;
    int related_region_id = -1;
    int culture_region_id = -1;
    int related_culture_region_id = -1;
    int language_region_id = -1;
    int related_language_region_id = -1;
    int cell_id = -1;
    double year_bp = 0.0;
    double pressure_index = 0.0;
    double continuity_index = 0.0;
};

struct HistoricalLayers {
    std::vector<HistoricalEra> eras;
    std::vector<HistoricalEvent> events;
};

struct PopulationRegion {
    int id = 0;
    int region_id = -1;
    int culture_region_id = -1;
    int language_region_id = -1;
    int settlement_count = 0;
    double carrying_capacity = 0.0;
    double estimated_population = 0.0;
    double agricultural_capacity_index = 0.0;
    double water_security_index = 0.0;
    double urbanization_fraction = 0.0;
    double growth_rate_per_year = 0.0;
    double population_pressure = 0.0;
    double migration_balance = 0.0;
    double hazard_mortality_index = 0.0;
};

struct ConflictRecord {
    int id = 0;
    int era_id = 0;
    int region_a = -1;
    int region_b = -1;
    int culture_a = -1;
    int culture_b = -1;
    int cause = 0;
    int contested_cell_id = -1;
    double start_year_bp = 0.0;
    double end_year_bp = 0.0;
    double intensity = 0.0;
    double resource_pressure = 0.0;
    double water_stress = 0.0;
    double trade_chokepoint_index = 0.0;
    double war_duration_years = 0.0;
    double region_a_force_estimate = 0.0;
    double region_b_force_estimate = 0.0;
    double mobilized_population = 0.0;
    double casualty_rate = 0.0;
    double logistics_strain_index = 0.0;
    double economic_disruption_index = 0.0;
    double estimated_casualties = 0.0;
    int outcome = 0;
};

struct DynastyRecord {
    int id = 0;
    int region_id = -1;
    int culture_region_id = -1;
    int language_region_id = -1;
    int parent_dynasty_id = -1;
    int founder_dynasty_id = -1;
    int successor_dynasty_id = -1;
    int founding_event_id = -1;
    int collapse_reason = 0;
    int lineage_depth = 0;
    int child_dynasty_count = 0;
    std::vector<int> child_dynasty_ids;
    double start_year_bp = 0.0;
    double end_year_bp = 0.0;
    double duration_years = 0.0;
    double legitimacy_index = 0.0;
    double succession_pressure = 0.0;
    double dynastic_continuity_index = 0.0;
};

struct LatLon {
    double lat_deg = 0.0;
    double lon_deg = 0.0;
};

struct SnapshotRegion {
    int region_id = -1;
    int capital_settlement_id = -1;
    int culture_region_id = -1;
    int language_region_id = -1;
    int cell_count = 0;
    double area_km2 = 0.0;
    double estimated_population = 0.0;
    double stability_index = 0.0;
    double centroid_lat_deg = 0.0;
    double centroid_lon_deg = 0.0;
    bool crosses_antimeridian = false;
    double boundary_perimeter_km = 0.0;
    double dissolved_polygon_area_km2 = 0.0;
    double polygon_area_error_fraction = 0.0;
    double compactness_index = 0.0;
    double geometry_quality = 0.0;
    std::vector<int> boundary_cell_ids;
    std::vector<LatLon> boundary_ring;
};

struct TerritorialSnapshot {
    int id = 0;
    int era_id = 0;
    int dominant_process = 0;
    int region_count = 0;
    int largest_region_id = -1;
    double year_bp = 0.0;
    double assigned_land_fraction = 0.0;
    double estimated_population = 0.0;
    double largest_region_area_km2 = 0.0;
    double fragmentation_index = 0.0;
    std::vector<SnapshotRegion> regions;
};

struct CalibrationCheck {
    int id = 0;
    int dataset = 0;
    int layer = 0;
    int metric = 0;
    bool passed = false;
    double value = 0.0;
    double target_min = 0.0;
    double target_max = 0.0;
    double score = 0.0;
};

struct Watershed {
    int id = 0;
    int basin_id = -1;
    int outlet_cell_id = -1;
    int cell_count = 0;
    int river_cell_count = 0;
    int outlet_type = 0;
    bool is_endorheic = false;
    double area_km2 = 0.0;
    double mean_runoff_mm_y = 0.0;
    double mean_elevation_m = 0.0;
    double max_flow_accumulation = 0.0;
    double centroid_lat_deg = 0.0;
    double centroid_lon_deg = 0.0;
    double min_lat_deg = 0.0;
    double max_lat_deg = 0.0;
    double min_lon_deg = 0.0;
    double max_lon_deg = 0.0;
    double lon_span_deg = 0.0;
    double boundary_perimeter_km = 0.0;
    double dissolved_polygon_area_km2 = 0.0;
    double polygon_area_error_fraction = 0.0;
    double compactness_index = 0.0;
    double geometry_quality = 0.0;
    bool crosses_antimeridian = false;
    std::vector<int> boundary_cell_ids;
    std::vector<LatLon> boundary_ring;
};

struct LakeBasin {
    int id = 0;
    int depression_component_id = -1;
    int outlet_cell_id = -1;
    int spill_to_cell_id = -1;
    int depression_policy = 0;
    int water_body = 0;
    bool is_geologic = false;
    bool overflows = false;
    int depression_cell_count = 0;
    int cell_count = 0;
    int lake_cell_count = 0;
    double depression_area_km2 = 0.0;
    double geologic_area_fraction = 0.0;
    double area_km2 = 0.0;
    double lake_area_km2 = 0.0;
    double mean_runoff_mm_y = 0.0;
    double outlet_elevation_m = 0.0;
    double spill_elevation_m = 0.0;
    double max_depression_depth_m = 0.0;
    double mean_water_depth_m = 0.0;
    double fill_fraction = 0.0;
    double storage_capacity_km3 = 0.0;
    double annual_runoff_km3 = 0.0;
    double overflow_index = 0.0;
    int overflow_stage_count = 0;
    double overflow_path_length_km = 0.0;
    double avulsion_risk = 0.0;
    std::vector<int> overflow_path_cell_ids;
};

struct CoastalFeature {
    int id = 0;
    int cell_id = -1;
    int type = 0;
    int shoreline_trend = 0;
    double lat_deg = 0.0;
    double lon_deg = 0.0;
    double length_km = 0.0;
    double sediment_supply_index = 0.0;
    double wave_energy_index = 0.0;
    double progradation_index = 0.0;
    double migration_rate_m_y = 0.0;
    double longshore_transport_index = 0.0;
};

struct SedimentaryBasin {
    int id = 0;
    int basin_id = -1;
    int type = 0;
    int dominant_resource = 0;
    int cell_count = 0;
    bool is_active = false;
    double area_km2 = 0.0;
    double mean_sediment_thickness_m = 0.0;
    double max_sediment_thickness_m = 0.0;
    double mean_subsidence_index = 0.0;
    double depositional_age_ma = 0.0;
};

struct StratigraphicLayer {
    int index = 0;
    int facies = 0;
    double thickness_m = 0.0;
    double age_top_ma = 0.0;
    double age_base_ma = 0.0;
    double grain_size_index = 0.0;
    double organic_potential = 0.0;
    double reservoir_quality = 0.0;
    double seal_quality = 0.0;
};

struct StratigraphicColumn {
    int id = 0;
    int basin_id = -1;
    int representative_cell_id = -1;
    int dominant_facies = 0;
    int sequence_phase = 0;
    bool is_active = false;
    double total_thickness_m = 0.0;
    double depositional_span_ma = 0.0;
    double mean_subsidence_index = 0.0;
    double sediment_flux_index = 0.0;
    double preservation_potential = 0.0;
    std::vector<StratigraphicLayer> layers;
};

struct IceSheet {
    int id = 0;
    int retreat_stage = 0;
    int cell_count = 0;
    int moraine_cell_count = 0;
    double area_km2 = 0.0;
    double mean_ice_thickness_m = 0.0;
    double max_ice_thickness_m = 0.0;
    double mean_glacial_erosion_m = 0.0;
    double mean_surface_mass_balance_m_y = 0.0;
    double mean_basal_sliding_index = 0.0;
    double mean_ice_velocity_m_y = 0.0;
    double accumulation_area_fraction = 0.0;
    double equilibrium_line_altitude_m = 0.0;
    double retreat_rate_m_y = 0.0;
    double mean_deglaciation_age_ka = 0.0;
    double mean_moraine_deposition_m = 0.0;
};

struct PoliticalRegion {
    int id = 0;
    int capital_settlement_id = -1;
    int type = 0;
    int dominant_biome = 0;
    int dominant_resource = 0;
    int settlement_count = 0;
    int route_count = 0;
    double area_km2 = 0.0;
    double mean_settlement_score = 0.0;
    double mean_elevation_m = 0.0;
    double barrier_pressure = 0.0;
    std::vector<int> settlement_ids;
};

struct BorderSegment {
    int id = 0;
    int region_a = -1;
    int region_b = -1;
    int cell_a = -1;
    int cell_b = -1;
    int type = 0;
    double length_km = 0.0;
    double barrier_score = 0.0;
};

const std::array<const char*, 9> CRUST_NAMES = {
    "oceanic", "continental", "transitional", "volcanic_arc",
    "craton", "orogen", "rift_basin", "sedimentary_basin", "accreted_terrane",
};
const std::array<const char*, 7> LITHOLOGY_NAMES = {
    "basalt", "granite", "limestone", "sandstone", "shale", "volcanic", "metamorphic",
};
const std::array<const char*, 5> BOUNDARY_NAMES = {
    "interior", "convergent", "divergent", "transform", "mixed",
};
const std::array<const char*, 11> SOIL_NAMES = {
    "none", "thin_mountain", "volcanic", "alluvial", "arid", "tropical",
    "temperate", "boreal", "tundra", "wetland", "saline",
};
const std::array<const char*, 16> BIOME_NAMES = {
    "ocean", "continental_shelf", "lake", "ice_cap", "tundra", "boreal_forest",
    "temperate_forest", "temperate_grassland", "mediterranean_scrub", "cold_desert",
    "hot_desert", "savanna", "tropical_seasonal_forest", "tropical_rainforest",
    "alpine", "wetland",
};
const std::array<const char*, 9> RESOURCE_NAMES = {
    "none", "volcanic_arc_metals", "craton_iron_gold", "sedimentary_fuels",
    "evaporites", "placer_metals", "geothermal", "fertile_alluvium", "coastal_fisheries",
};
const std::array<const char*, 4> ATMOSPHERIC_CELL_NAMES = {
    "tropical_ascent", "subtropical_high", "midlatitude_westerly", "polar_cell",
};
const std::array<const char*, 6> WATER_BODY_NAMES = {
    "land", "ocean", "continental_shelf", "inland_sea", "fresh_lake", "saline_basin",
};
const std::array<const char*, 20> LANDFORM_NAMES = {
    "open_ocean", "continental_shelf", "inland_sea", "lacustrine_basin",
    "salt_flat", "ice_field", "mountain_belt", "volcanic_arc",
    "rift_valley", "trench", "river_valley", "floodplain",
    "delta", "alluvial_fan", "coastal_plain", "stable_lowland",
    "fjord", "glacial_valley", "moraine", "glacial_lake",
};
const std::array<const char*, 6> SETTLEMENT_TYPE_NAMES = {
    "river_city", "port", "mining_town", "agricultural_town", "oasis", "frontier_town",
};
const std::array<const char*, 4> ROUTE_TYPE_NAMES = {
    "overland", "river_corridor", "coastal_sea", "mountain_pass",
};
const std::array<const char*, 5> WATERSHED_OUTLET_NAMES = {
    "ocean", "lake", "saline_basin", "inland_sea", "closed_land",
};
const std::array<const char*, 6> DEPRESSION_POLICY_NAMES = {
    "none", "corrected_numeric", "preserved_geologic", "overflow_spill", "dry_closed",
    "temporary_numeric_lake",
};
const std::array<const char*, 6> POLITICAL_REGION_TYPE_NAMES = {
    "river_realm", "maritime_league", "mountain_march",
    "mining_domain", "agrarian_state", "frontier_territory",
};
const std::array<const char*, 6> BORDER_TYPE_NAMES = {
    "open_lowland", "river", "mountain", "desert", "ice", "coastal",
};
const std::array<const char*, 8> CULTURE_TYPE_NAMES = {
    "river_valley", "maritime", "highland", "desert_oasis",
    "agrarian_lowland", "mining_frontier", "boreal_frontier", "forest_realm",
};
const std::array<const char*, 6> LANGUAGE_FAMILY_NAMES = {
    "riverine", "coastal", "highland", "arid", "lowland", "frontier",
};
const std::array<const char*, 6> SACRED_AREA_TYPE_NAMES = {
    "mountain_shrine", "spring_oracle", "sacred_grove",
    "volcanic_sanctuary", "ancestral_coast", "desert_sanctuary",
};
const std::array<const char*, 6> RUIN_TYPE_NAMES = {
    "ruined_city", "abandoned_mine", "desert_outpost",
    "mountain_fortress", "old_harbor", "glacial_relic",
};
const std::array<const char*, 6> ABANDONMENT_REASON_NAMES = {
    "aridity", "tectonic_hazard", "glaciation",
    "salinization", "trade_decline", "frontier_isolation",
};
const std::array<const char*, 7> HISTORY_EVENT_TYPE_NAMES = {
    "state_foundation", "dynastic_change", "migration",
    "language_split", "trade_boom", "sacred_founding", "ruin_abandonment",
};
const std::array<const char*, 4> HISTORICAL_PROCESS_NAMES = {
    "founding", "expansion", "fragmentation", "integration",
};
const std::array<const char*, 6> CONFLICT_CAUSE_NAMES = {
    "water_rights", "fertile_plain", "mining_claim",
    "trade_chokepoint", "border_fragmentation", "sacred_site",
};
const std::array<const char*, 5> CONFLICT_OUTCOME_NAMES = {
    "stalemate", "region_a_victory", "region_b_victory",
    "border_shift", "exhaustion",
};
const std::array<const char*, 6> DYNASTY_COLLAPSE_REASON_NAMES = {
    "continuity", "succession_crisis", "resource_shock",
    "trade_decline", "migration_pressure", "conflict_defeat",
};
const std::array<const char*, 4> CALIBRATION_DATASET_NAMES = {
    "ETOPO_reference_range", "WorldClim_reference_range",
    "HydroSHEDS_reference_range", "NaturalEarth_reference_range",
};
const std::array<const char*, 5> CALIBRATION_LAYER_NAMES = {
    "relief_bathymetry", "climate", "hydrology", "biomes", "cartography",
};
const std::array<const char*, 12> CALIBRATION_METRIC_NAMES = {
    "ocean_fraction", "mean_land_elevation_m", "hypsometric_span_m",
    "global_mean_temperature_c", "mean_land_precipitation_mm_y",
    "mean_monthly_temperature_range_c", "river_cell_fraction",
    "endorheic_watershed_fraction", "desert_land_fraction",
    "ice_land_fraction", "forest_land_fraction", "coastal_land_fraction",
};
const std::array<const char*, 6> COASTAL_FEATURE_TYPE_NAMES = {
    "beach", "barrier_bar", "barrier_island", "delta_lobe", "tidal_marsh", "coastal_cliff",
};
const std::array<const char*, 5> SHORELINE_TREND_NAMES = {
    "stable", "prograding", "eroding", "landward_migration", "delta_switching",
};
const std::array<const char*, 6> SEDIMENTARY_BASIN_TYPE_NAMES = {
    "rift_basin", "foreland_basin", "passive_margin", "lacustrine_basin", "evaporite_basin", "deltaic_basin",
};
const std::array<const char*, 9> STRATIGRAPHIC_FACIES_NAMES = {
    "alluvial_fan", "fluvial_channel", "floodplain_mud", "deltaic_sand",
    "lacustrine_mud", "evaporite", "shallow_marine", "deep_marine", "glacial_till",
};
const std::array<const char*, 5> SEQUENCE_PHASE_NAMES = {
    "aggradation", "progradation", "retrogradation", "starved", "erosional",
};
const std::array<const char*, 5> ICE_RETREAT_STAGE_NAMES = {
    "advancing", "stable", "retreating", "stagnant", "relict",
};

template <typename T>
T clamp(T value, T low, T high) {
    return std::max(low, std::min(high, value));
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
double hash01(std::uint64_t seed, std::uint64_t a, std::uint64_t b = 0) {
    const std::uint64_t x = splitmix64(seed ^ (a * 0x9e3779b97f4a7c15ULL) ^ (b * 0xbf58476d1ce4e5b9ULL));
    return static_cast<double>(x >> 11U) / 9007199254740992.0;
}
double signed_noise(std::uint64_t seed, std::uint64_t a, std::uint64_t b = 0) {
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

std::vector<Cell> build_fibonacci_mesh(const Params& params) {
    const int n = params.cell_count;
    std::vector<Cell> cells(n);
    const double golden_angle = PI * (3.0 - std::sqrt(5.0));
    const double area = 4.0 * PI * params.radius_km * params.radius_km / static_cast<double>(n);
    for (int i = 0; i < n; ++i) {
        const double z = 1.0 - 2.0 * (static_cast<double>(i) + 0.5) / static_cast<double>(n);
        const double r = std::sqrt(std::max(0.0, 1.0 - z * z));
        const double theta = golden_angle * static_cast<double>(i);
        cells[i].id = i;
        cells[i].p = {std::cos(theta) * r, std::sin(theta) * r, z};
        cells[i].lat = std::asin(z);
        cells[i].lon = std::atan2(cells[i].p.y, cells[i].p.x);
        cells[i].area_km2 = area;
    }

    const int k = params.neighbor_count;
#pragma omp parallel for schedule(dynamic)
    for (int i = 0; i < n; ++i) {
        std::vector<std::pair<double, int>> best;
        best.reserve(static_cast<std::size_t>(k));
        for (int j = 0; j < n; ++j) {
            if (i == j) {
                continue;
            }
            const double score = dot(cells[i].p, cells[j].p);
            if (static_cast<int>(best.size()) < k) {
                best.emplace_back(score, j);
                if (static_cast<int>(best.size()) == k) {
                    std::sort(best.begin(), best.end());
                }
            } else if (score > best.front().first) {
                best.front() = {score, j};
                std::sort(best.begin(), best.end());
            }
        }
        for (const auto& item : best) {
            cells[i].neighbors.push_back(item.second);
        }
    }
    for (int i = 0; i < n; ++i) {
        for (int j : cells[i].neighbors) {
            auto& back = cells[j].neighbors;
            if (std::find(back.begin(), back.end(), i) == back.end()) {
                back.push_back(i);
            }
        }
    }
    return cells;
}

int geodesic_frequency_for_target(int cell_count) {
    const double target = static_cast<double>(std::max(12, cell_count));
    const double raw = std::sqrt(std::max(0.0, (target - 2.0) / 10.0));
    return std::max(1, static_cast<int>(std::ceil(raw - 1.0e-9)));
}

int add_geodesic_vertex(
    std::vector<Vec3>& points,
    std::vector<std::set<int>>& neighbor_sets,
    std::map<std::array<long long, 3>, int>& point_index,
    Vec3 point
) {
    point = normalize(point);
    const std::array<long long, 3> key = {
        static_cast<long long>(std::llround(point.x * 1000000000.0)),
        static_cast<long long>(std::llround(point.y * 1000000000.0)),
        static_cast<long long>(std::llround(point.z * 1000000000.0)),
    };
    const auto found = point_index.find(key);
    if (found != point_index.end()) {
        return found->second;
    }
    const int id = static_cast<int>(points.size());
    points.push_back(point);
    neighbor_sets.emplace_back();
    point_index[key] = id;
    return id;
}

void add_geodesic_edge(std::vector<std::set<int>>& neighbor_sets, int a, int b) {
    if (a == b || a < 0 || b < 0) {
        return;
    }
    neighbor_sets[static_cast<std::size_t>(a)].insert(b);
    neighbor_sets[static_cast<std::size_t>(b)].insert(a);
}

void add_geodesic_triangle(
    std::vector<std::set<int>>& neighbor_sets,
    std::vector<std::array<int, 3>>& triangles,
    int a,
    int b,
    int c
) {
    add_geodesic_edge(neighbor_sets, a, b);
    add_geodesic_edge(neighbor_sets, b, c);
    add_geodesic_edge(neighbor_sets, c, a);
    triangles.push_back({a, b, c});
}

std::vector<Cell> build_geodesic_icosahedron_mesh(const Params& params) {
    const double t = (1.0 + std::sqrt(5.0)) / 2.0;
    const std::array<Vec3, 12> base_vertices = {
        normalize({-1.0, t, 0.0}), normalize({1.0, t, 0.0}),
        normalize({-1.0, -t, 0.0}), normalize({1.0, -t, 0.0}),
        normalize({0.0, -1.0, t}), normalize({0.0, 1.0, t}),
        normalize({0.0, -1.0, -t}), normalize({0.0, 1.0, -t}),
        normalize({t, 0.0, -1.0}), normalize({t, 0.0, 1.0}),
        normalize({-t, 0.0, -1.0}), normalize({-t, 0.0, 1.0}),
    };
    const std::array<std::array<int, 3>, 20> faces = {{
        {{0, 11, 5}}, {{0, 5, 1}}, {{0, 1, 7}}, {{0, 7, 10}}, {{0, 10, 11}},
        {{1, 5, 9}}, {{5, 11, 4}}, {{11, 10, 2}}, {{10, 7, 6}}, {{7, 1, 8}},
        {{3, 9, 4}}, {{3, 4, 2}}, {{3, 2, 6}}, {{3, 6, 8}}, {{3, 8, 9}},
        {{4, 9, 5}}, {{2, 4, 11}}, {{6, 2, 10}}, {{8, 6, 7}}, {{9, 8, 1}},
    }};

    const int frequency = geodesic_frequency_for_target(params.cell_count);
    std::vector<Vec3> points;
    points.reserve(static_cast<std::size_t>(10 * frequency * frequency + 2));
    std::vector<std::set<int>> neighbor_sets;
    neighbor_sets.reserve(points.capacity());
    std::map<std::array<long long, 3>, int> point_index;
    std::vector<std::array<int, 3>> triangles;
    triangles.reserve(static_cast<std::size_t>(20 * frequency * frequency));

    for (const auto& face : faces) {
        const Vec3 a = base_vertices[static_cast<std::size_t>(face[0])];
        const Vec3 b = base_vertices[static_cast<std::size_t>(face[1])];
        const Vec3 c = base_vertices[static_cast<std::size_t>(face[2])];
        std::vector<std::vector<int>> grid(
            static_cast<std::size_t>(frequency + 1),
            std::vector<int>(static_cast<std::size_t>(frequency + 1), -1)
        );
        for (int i = 0; i <= frequency; ++i) {
            for (int j = 0; j <= frequency - i; ++j) {
                const int k = frequency - i - j;
                const Vec3 point = add(add(mul(a, static_cast<double>(k)), mul(b, static_cast<double>(i))),
                    mul(c, static_cast<double>(j)));
                grid[static_cast<std::size_t>(i)][static_cast<std::size_t>(j)] = add_geodesic_vertex(
                    points, neighbor_sets, point_index, point
                );
            }
        }
        for (int i = 0; i < frequency; ++i) {
            for (int j = 0; j < frequency - i; ++j) {
                const int v0 = grid[static_cast<std::size_t>(i)][static_cast<std::size_t>(j)];
                const int v1 = grid[static_cast<std::size_t>(i + 1)][static_cast<std::size_t>(j)];
                const int v2 = grid[static_cast<std::size_t>(i)][static_cast<std::size_t>(j + 1)];
                add_geodesic_triangle(neighbor_sets, triangles, v0, v1, v2);
                if (j < frequency - i - 1) {
                    const int v3 = grid[static_cast<std::size_t>(i + 1)][static_cast<std::size_t>(j + 1)];
                    add_geodesic_triangle(neighbor_sets, triangles, v1, v3, v2);
                }
            }
        }
    }

    std::vector<double> cell_areas(points.size(), 0.0);
    const double radius_squared_km2 = params.radius_km * params.radius_km;
    for (const auto& triangle : triangles) {
        const double share_km2 = spherical_triangle_area_steradians(
            points[static_cast<std::size_t>(triangle[0])],
            points[static_cast<std::size_t>(triangle[1])],
            points[static_cast<std::size_t>(triangle[2])]
        ) * radius_squared_km2 / 3.0;
        for (int cell_id : triangle) {
            cell_areas[static_cast<std::size_t>(cell_id)] += share_km2;
        }
    }
    const double expected_area_km2 = 4.0 * PI * radius_squared_km2;
    const double computed_area_km2 = std::accumulate(cell_areas.begin(), cell_areas.end(), 0.0);
    if (
        computed_area_km2 <= 0.0 ||
        std::abs(computed_area_km2 - expected_area_km2) > expected_area_km2 * 1.0e-10
    ) {
        throw std::runtime_error("geodesic spherical cell areas do not close to planet surface area");
    }
    std::vector<Cell> cells(points.size());
    for (int i = 0; i < static_cast<int>(points.size()); ++i) {
        const Vec3 point = points[static_cast<std::size_t>(i)];
        cells[static_cast<std::size_t>(i)].id = i;
        cells[static_cast<std::size_t>(i)].p = point;
        cells[static_cast<std::size_t>(i)].lat = std::asin(clamp(point.z, -1.0, 1.0));
        cells[static_cast<std::size_t>(i)].lon = std::atan2(point.y, point.x);
        cells[static_cast<std::size_t>(i)].area_km2 = cell_areas[static_cast<std::size_t>(i)];
        cells[static_cast<std::size_t>(i)].neighbors.assign(
            neighbor_sets[static_cast<std::size_t>(i)].begin(),
            neighbor_sets[static_cast<std::size_t>(i)].end()
        );
    }
    return cells;
}

std::vector<Cell> build_mesh(const Params& params) {
    if (params.mesh_backend == MESH_BACKEND_GEODESIC_ICOSAHEDRON) {
        return build_geodesic_icosahedron_mesh(params);
    }
    return build_fibonacci_mesh(params);
}

Vec3 random_unit_vector(std::mt19937_64& rng) {
    std::uniform_real_distribution<double> uni(0.0, 1.0);
    const double z = 2.0 * uni(rng) - 1.0;
    const double a = 2.0 * PI * uni(rng);
    const double r = std::sqrt(std::max(0.0, 1.0 - z * z));
    return {std::cos(a) * r, std::sin(a) * r, z};
}

std::vector<Plate> generate_plates(const Params& params) {
    std::mt19937_64 rng(params.seed ^ 0xC0FFEEULL);
    std::uniform_real_distribution<double> uni(0.0, 1.0);
    std::vector<Plate> plates;
    plates.reserve(static_cast<std::size_t>(params.plate_count));
    const double tectonic_activity = clamp(params.internal_heat * std::sqrt(4.5 / std::max(0.05, params.geological_age_ga)), 0.25, 2.25);
    for (int i = 0; i < params.plate_count; ++i) {
        const double draw = uni(rng);
        int kind = 0;
        if (draw < params.continental_plate_fraction) {
            kind = 1;
        } else if (draw < params.continental_plate_fraction + 0.22) {
            kind = 2;
        }
        Plate plate;
        plate.id = i;
        plate.axis = random_unit_vector(rng);
        plate.angular_speed = (params.min_angular_speed +
            (params.max_angular_speed - params.min_angular_speed) * uni(rng)) * tectonic_activity;
        plate.kind = kind;
        plate.crust_density = kind == 0 ? 3.0 : (kind == 1 ? 2.72 : 2.84);
        plate.crust_thickness_km = kind == 0 ? 7.0 : (kind == 1 ? 34.0 : 22.0);
        plates.push_back(plate);
    }
    return plates;
}

std::vector<int> choose_plate_seeds(const Params& params, int cell_count) {
    std::mt19937_64 rng(params.seed ^ 0xBAD5EEDULL);
    std::uniform_int_distribution<int> pick(0, cell_count - 1);
    std::unordered_set<int> used;
    std::vector<int> seeds;
    while (static_cast<int>(seeds.size()) < params.plate_count) {
        const int candidate = pick(rng);
        if (used.insert(candidate).second) {
            seeds.push_back(candidate);
        }
    }
    return seeds;
}

void assign_plates(const std::vector<Vec3>& centers, std::vector<Cell>& cells) {
    const int n = static_cast<int>(cells.size());
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        double best = -2.0;
        int best_plate = 0;
        for (int p = 0; p < static_cast<int>(centers.size()); ++p) {
            const double score = dot(cells[i].p, centers[static_cast<std::size_t>(p)]);
            if (score > best) {
                best = score;
                best_plate = p;
            }
        }
        cells[i].plate_id = best_plate;
    }
    std::vector<int> assigned_counts(centers.size(), 0);
    for (const Cell& cell : cells) {
        assigned_counts[static_cast<std::size_t>(cell.plate_id)]++;
    }
    for (std::size_t plate_id = 0; plate_id < assigned_counts.size(); ++plate_id) {
        if (assigned_counts[plate_id] == 0) {
            throw std::runtime_error(
                "nearest-center plate domain became empty; increase mesh.cell_count or reduce "
                "tectonics.plate_count/plate motion"
            );
        }
    }
}

Vec3 plate_velocity(const Plate& plate, Vec3 pos) {
    return cross(mul(plate.axis, plate.angular_speed), pos);
}

std::vector<double> smooth_field(const std::vector<Cell>& cells, const std::vector<double>& input, int steps, double self_weight) {
    std::vector<double> current = input;
    std::vector<double> next(input.size(), 0.0);
    for (int step = 0; step < steps; ++step) {
#pragma omp parallel for schedule(static)
        for (int i = 0; i < static_cast<int>(cells.size()); ++i) {
            double sum = 0.0;
            for (int j : cells[i].neighbors) {
                sum += current[j];
            }
            const double avg = cells[i].neighbors.empty() ? current[i] : sum / static_cast<double>(cells[i].neighbors.size());
            next[i] = self_weight * current[i] + (1.0 - self_weight) * avg;
        }
        current.swap(next);
    }
    return current;
}

void classify_boundaries(const Params& params, const std::vector<Plate>& plates, std::vector<Cell>& cells) {
    const int n = static_cast<int>(cells.size());
    std::vector<double> conv(n, 0.0), div(n, 0.0), trans(n, 0.0);
    for (int i = 0; i < n; ++i) {
        for (int j : cells[i].neighbors) {
            if (j <= i || cells[i].plate_id == cells[j].plate_id) {
                continue;
            }
            const Plate& a = plates[cells[i].plate_id];
            const Plate& b = plates[cells[j].plate_id];
            const Vec3 mid = normalize(add(cells[i].p, cells[j].p));
            const Vec3 delta = sub(cells[j].p, cells[i].p);
            const Vec3 across = normalize(sub(delta, mul(mid, dot(delta, mid))));
            const Vec3 tangent = normalize(cross(mid, across));
            const Vec3 vrel = sub(plate_velocity(b, mid), plate_velocity(a, mid));
            const double separation = dot(vrel, across);
            const double shear = std::abs(dot(vrel, tangent));
            const double c = clamp(-separation * 1.25, 0.0, 1.0);
            const double d = clamp(separation * 1.25, 0.0, 1.0);
            const double t = clamp((shear - std::abs(separation) * 0.35) * 1.05, 0.0, 1.0);
            conv[i] += c;
            conv[j] += c;
            div[i] += d;
            div[j] += d;
            trans[i] += t;
            trans[j] += t;
        }
    }
    for (int i = 0; i < n; ++i) {
        const double degree = std::max(1.0, static_cast<double>(cells[i].neighbors.size()));
        conv[i] = clamp(conv[i] / degree * 3.2, 0.0, 1.0);
        div[i] = clamp(div[i] / degree * 3.2, 0.0, 1.0);
        trans[i] = clamp(trans[i] / degree * 3.2, 0.0, 1.0);
    }
    conv = smooth_field(cells, conv, params.boundary_smoothing_steps, 0.58);
    div = smooth_field(cells, div, params.boundary_smoothing_steps, 0.58);
    trans = smooth_field(cells, trans, params.boundary_smoothing_steps, 0.62);
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        cells[i].boundary_convergent = clamp(conv[i], 0.0, 1.0);
        cells[i].boundary_divergent = clamp(div[i], 0.0, 1.0);
        cells[i].boundary_transform = clamp(trans[i], 0.0, 1.0);
        const double m = std::max(cells[i].boundary_convergent, std::max(cells[i].boundary_divergent, cells[i].boundary_transform));
        if (m < 0.08) {
            cells[i].boundary_type = 0;
        } else if (cells[i].boundary_convergent == m && cells[i].boundary_divergent > 0.45 * m) {
            cells[i].boundary_type = 4;
        } else if (cells[i].boundary_convergent == m) {
            cells[i].boundary_type = 1;
        } else if (cells[i].boundary_divergent == m) {
            cells[i].boundary_type = 2;
        } else {
            cells[i].boundary_type = 3;
        }
    }
}

double lithology_resistance(int lithology) {
    switch (lithology) {
        case 0: return 0.85;
        case 1: return 1.25;
        case 2: return 0.75;
        case 3: return 0.82;
        case 4: return 0.62;
        case 5: return 0.95;
        case 6: return 1.35;
        default: return 1.0;
    }
}

void derive_crust_and_topography(const Params& params, const std::vector<Plate>& plates, std::vector<Cell>& cells) {
    const int n = static_cast<int>(cells.size());
    const double relief_scale = clamp(1.0 / std::sqrt(std::max(0.08, params.gravity_g)), 0.55, 1.60);
    const double tectonic_activity = clamp(params.internal_heat * std::sqrt(4.5 / std::max(0.05, params.geological_age_ga)), 0.25, 2.25);
    std::vector<double> continental_noise(static_cast<std::size_t>(n), 0.0);
    std::vector<double> relief_noise(static_cast<std::size_t>(n), 0.0);
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        continental_noise[static_cast<std::size_t>(i)] = signed_noise(
            params.seed, static_cast<std::uint64_t>(i), 17
        );
        relief_noise[static_cast<std::size_t>(i)] = signed_noise(
            params.seed, static_cast<std::uint64_t>(i), 31
        );
    }
    continental_noise = smooth_field(
        cells,
        continental_noise,
        INITIAL_CRUST_COHERENCE_SMOOTHING_STEPS,
        INITIAL_CRUST_COHERENCE_SELF_WEIGHT
    );
    relief_noise = smooth_field(
        cells,
        relief_noise,
        SECONDARY_RELIEF_SMOOTHING_STEPS,
        SECONDARY_RELIEF_SELF_WEIGHT
    );
    std::vector<double> continental_score(static_cast<std::size_t>(n), 0.0);
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        const Cell& cell = cells[static_cast<std::size_t>(i)];
        const Plate& plate = plates[static_cast<std::size_t>(cell.plate_id)];
        const double wave = 0.12 * std::sin(3.0 * cell.lon + 1.7 * std::sin(cell.lat * 2.0));
        const double plate_bias = plate.kind == 1 ? 0.72 : (plate.kind == 2 ? 0.48 : 0.17);
        continental_score[static_cast<std::size_t>(i)] = plate_bias +
            0.20 * continental_noise[static_cast<std::size_t>(i)] + wave +
            0.14 * cell.boundary_convergent;
    }
    std::vector<int> continental_rank(static_cast<std::size_t>(n), 0);
    std::iota(continental_rank.begin(), continental_rank.end(), 0);
    std::stable_sort(
        continental_rank.begin(),
        continental_rank.end(),
        [&continental_score](int a, int b) {
            const double score_a = continental_score[static_cast<std::size_t>(a)];
            const double score_b = continental_score[static_cast<std::size_t>(b)];
            return score_a == score_b ? a < b : score_a > score_b;
        }
    );
    const int continental_target_count = std::clamp(
        static_cast<int>(std::llround(params.continental_crust_fraction_target * static_cast<double>(n))),
        0,
        n
    );
    std::vector<int> continental_mask(static_cast<std::size_t>(n), 0);
    for (int rank = 0; rank < continental_target_count; ++rank) {
        const int cell_id = continental_rank[static_cast<std::size_t>(rank)];
        continental_mask[static_cast<std::size_t>(cell_id)] = 1;
    }
    std::vector<int> continental_margin(static_cast<std::size_t>(n), 0);
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        if (continental_mask[static_cast<std::size_t>(i)] != 0) {
            continue;
        }
        for (int neighbor_id : cells[static_cast<std::size_t>(i)].neighbors) {
            if (continental_mask[static_cast<std::size_t>(neighbor_id)] != 0) {
                continental_margin[static_cast<std::size_t>(i)] = 1;
                break;
            }
        }
    }
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        Cell& cell = cells[i];
        const Plate& plate = plates[cell.plate_id];
        const double n0 = continental_noise[static_cast<std::size_t>(i)];
        const double n1 = signed_noise(params.seed, static_cast<std::uint64_t>(i), 23);
        const double n2 = signed_noise(params.seed, static_cast<std::uint64_t>(i), 31);
        const double coherent_n2 = relief_noise[static_cast<std::size_t>(i)];
        const bool continental = continental_mask[static_cast<std::size_t>(i)] != 0;
        const double conv = cell.boundary_convergent;
        const double div = cell.boundary_divergent;
        const double trans = cell.boundary_transform;
        if (continental) {
            if (conv > 0.40) {
                cell.crust_type = 5;
                cell.lithology = 6;
            } else if (div > 0.36) {
                cell.crust_type = 6;
                cell.lithology = 3;
            } else if (n1 > 0.55 && conv < 0.16 && div < 0.14) {
                cell.crust_type = 4;
                cell.lithology = 1;
            } else if (n1 < -0.45) {
                cell.crust_type = 7;
                cell.lithology = n2 > 0.0 ? 2 : 4;
            } else {
                cell.crust_type = 1;
                cell.lithology = n2 > 0.35 ? 1 : 3;
            }
        } else {
            if (conv > 0.35 && plate.kind != 0) {
                cell.crust_type = 3;
                cell.lithology = 5;
            } else if (continental_margin[static_cast<std::size_t>(i)] != 0) {
                cell.crust_type = 2;
                cell.lithology = 0;
            } else {
                cell.crust_type = 0;
                cell.lithology = 0;
            }
        }
        const bool oceanic = cell.crust_type == 0 || cell.crust_type == 2 || cell.crust_type == 3;
        cell.crust_age_ma = oceanic
            ? clamp(8.0 + 190.0 * (1.0 - div) + 25.0 * n1, 0.0, 260.0)
            : clamp(450.0 + 900.0 * params.geological_age_ga * hash01(params.seed, i, 41), 120.0, 4200.0);
        cell.crust_thickness_km = oceanic
            ? clamp(6.5 + 3.0 * conv + 1.5 * n2, 4.5, 14.0)
            : clamp(29.0 + 17.0 * conv - 8.0 * div + 5.0 * n2, 18.0, 72.0);
        cell.crust_density = oceanic ? 3.00 : 2.70 + 0.08 * hash01(params.seed, i, 43);
        const double isostatic = oceanic
            ? -3000.0
            : CONTINENTAL_ISOSTATIC_FREEBOARD_M +
                12.0 * (cell.crust_thickness_km - 30.0) -
                1800.0 * (cell.crust_density - 2.72);
        const double thermal = oceanic ? -1050.0 * std::sqrt(std::max(0.0, cell.crust_age_ma) / 190.0) : 0.0;
        const double ridge = div * (oceanic ? 2600.0 : 880.0) * relief_scale;
        const double rift = div * (oceanic ? 0.0 : -820.0) * relief_scale;
        const double convergence_squared = conv * conv;
        const double orogen = (
            continental
                ? convergence_squared * CONTINENTAL_OROGEN_UPLIFT_SCALE_M
                : conv * 1350.0
        ) * relief_scale;
        const double oceanic_trench_scale = cell.crust_type == 3
            ? VOLCANIC_ARC_TRENCH_SUBSIDENCE_SCALE_M
            : OCEANIC_TRENCH_SUBSIDENCE_SCALE_M;
        const double trench = (
            oceanic
                ? -convergence_squared * oceanic_trench_scale
                : -conv * 350.0
        ) * relief_scale;
        const double volcanic = (
            (cell.crust_type == 3 ? VOLCANIC_ARC_UPLIFT_SCALE_M * convergence_squared : 0.0) +
            380.0 * div
        ) * relief_scale;
        const double fault = -320.0 * trans;
        const double rough = (continental ? 520.0 : 180.0) * coherent_n2 +
            (oceanic ? 260.0 : 620.0) * n0 +
            180.0 * std::sin(9.0 * cell.lon + 4.0 * cell.lat);
        cell.initial_isostatic_elevation_m = isostatic;
        cell.initial_thermal_subsidence_m = thermal;
        cell.initial_ridge_uplift_m = ridge;
        cell.initial_orogenic_uplift_m = orogen;
        cell.initial_volcanic_uplift_m = volcanic;
        cell.initial_trench_subsidence_m = trench;
        cell.initial_rift_subsidence_m = rift;
        cell.initial_transform_fault_relief_m = fault;
        cell.initial_secondary_roughness_m = rough;
        cell.initial_elevation_m = isostatic + thermal + ridge + rift + orogen + trench + volcanic + fault + rough;
        cell.volcanic_potential_index = clamp(
            0.42 * div + 0.38 * conv * (cell.crust_type == 3 ? 1.0 : 0.35) +
            0.16 * (cell.lithology == 5 ? 1.0 : 0.0) + 0.04 * tectonic_activity,
            0.0,
            1.0
        );
        cell.uplift_rate = params.tectonic_uplift_scale * tectonic_activity *
            (1.5 * div + 8.5 * conv + (cell.crust_type == 3 ? 2.5 : 0.0));
        cell.elevation_m = cell.initial_elevation_m;
        cell.initial_plate_id = cell.plate_id;
        cell.last_crust_source_cell_id = cell.id;
        cell.initial_crust_age_ma = cell.crust_age_ma;
        cell.initial_crust_thickness_km = cell.crust_thickness_km;
        cell.initial_crust_density = cell.crust_density;
    }
}

bool is_oceanic_crust_state(int crust_type, double age_ma, double thickness_km, double density) {
    if (crust_type == 0) {
        return true;
    }
    if (crust_type != 2 && crust_type != 3) {
        return false;
    }
    return age_ma <= 320.0 && thickness_km <= 18.0 && density >= 2.84;
}

double crust_equilibrium_elevation_m(double thickness_km, double density, bool oceanic) {
    if (oceanic) {
        return -3000.0;
    }
    return CONTINENTAL_ISOSTATIC_FREEBOARD_M +
        12.0 * (thickness_km - 30.0) -
        1800.0 * (density - 2.72);
}

double oceanic_thermal_subsidence_m(double crust_age_ma, bool oceanic) {
    return oceanic ? -1050.0 * std::sqrt(std::max(0.0, crust_age_ma) / 190.0) : 0.0;
}

PlateMotionStep summarize_plate_motion_step(
    const std::vector<Cell>& cells,
    const std::vector<Plate>& plates,
    int id,
    int erosion_iteration,
    const std::string& stage,
    const std::vector<int>& previous_plate_ids,
    const std::vector<double>& step_rotation_deg,
    const CrustMotionDiagnostics& crust_motion,
    const std::vector<double>& crust_age_change_ma,
    const std::vector<double>& crust_thickness_change_km,
    const std::vector<double>& crust_density_change,
    const std::vector<double>& tectonic_elevation_change_m
) {
    PlateMotionStep step;
    step.id = id;
    step.erosion_iteration = erosion_iteration;
    step.stage = stage;
    step.cell_count = static_cast<int>(cells.size());
    step.plate_count = static_cast<int>(plates.size());
    step.cell_plate_ids.reserve(cells.size());
    step.crust_type_by_cell.reserve(cells.size());
    step.lithology_by_cell.reserve(cells.size());
    step.crust_source_cell_ids = crust_motion.source_cell_ids;
    if (step.crust_source_cell_ids.size() != cells.size()) {
        step.crust_source_cell_ids.resize(cells.size());
        std::iota(step.crust_source_cell_ids.begin(), step.crust_source_cell_ids.end(), 0);
    }
    step.crust_transport_distance_km_by_cell = crust_motion.transport_distance_km_by_cell;
    step.crust_age_transport_change_ma_by_cell = crust_motion.age_transport_change_ma_by_cell;
    step.crust_thickness_transport_change_km_by_cell = crust_motion.thickness_transport_change_km_by_cell;
    step.crust_density_transport_change_by_cell = crust_motion.density_transport_change_by_cell;
    step.crust_age_process_change_ma_by_cell = crust_motion.age_process_change_ma_by_cell;
    step.crust_thickness_process_change_km_by_cell = crust_motion.thickness_process_change_km_by_cell;
    step.crust_density_process_change_by_cell = crust_motion.density_process_change_by_cell;
    for (std::vector<double>* values : {
        &step.crust_transport_distance_km_by_cell,
        &step.crust_age_transport_change_ma_by_cell,
        &step.crust_thickness_transport_change_km_by_cell,
        &step.crust_density_transport_change_by_cell,
        &step.crust_age_process_change_ma_by_cell,
        &step.crust_thickness_process_change_km_by_cell,
        &step.crust_density_process_change_by_cell,
    }) {
        if (values->size() != cells.size()) {
            values->assign(cells.size(), 0.0);
        }
    }
    step.aged_oceanic_cell_ids = crust_motion.aged_oceanic_cell_ids;
    step.rejuvenated_oceanic_cell_ids = crust_motion.rejuvenated_oceanic_cell_ids;
    step.subducted_oceanic_cell_ids = crust_motion.subducted_oceanic_cell_ids;
    step.aged_oceanic_cell_count = static_cast<int>(step.aged_oceanic_cell_ids.size());
    step.rejuvenated_oceanic_cell_count = static_cast<int>(step.rejuvenated_oceanic_cell_ids.size());
    step.subducted_oceanic_cell_count = static_cast<int>(step.subducted_oceanic_cell_ids.size());
    step.crust_age_change_ma_by_cell = crust_age_change_ma;
    step.crust_thickness_change_km_by_cell = crust_thickness_change_km;
    step.crust_density_change_by_cell = crust_density_change;
    step.tectonic_elevation_change_m_by_cell = tectonic_elevation_change_m;

    std::vector<int> plate_cell_counts(plates.size(), 0);
    std::vector<double> plate_areas(plates.size(), 0.0);
    std::unordered_set<int> unique_crust_sources;
    for (std::size_t index = 0; index < cells.size(); ++index) {
        const Cell& cell = cells[index];
        step.cell_plate_ids.push_back(cell.plate_id);
        step.crust_type_by_cell.push_back(cell.crust_type);
        step.lithology_by_cell.push_back(cell.lithology);
        const int source_cell_id = step.crust_source_cell_ids[index];
        if (source_cell_id != static_cast<int>(index)) {
            step.crust_source_remap_cell_count++;
        }
        unique_crust_sources.insert(source_cell_id);
        const double transport_distance_km = step.crust_transport_distance_km_by_cell[index];
        step.mean_crust_transport_distance_km += transport_distance_km;
        step.max_crust_transport_distance_km = std::max(
            step.max_crust_transport_distance_km, transport_distance_km
        );
        if (cell.plate_id >= 0 && cell.plate_id < static_cast<int>(plates.size())) {
            plate_cell_counts[static_cast<std::size_t>(cell.plate_id)]++;
            plate_areas[static_cast<std::size_t>(cell.plate_id)] += cell.area_km2;
        }
        if (cell.boundary_type != 0) {
            step.plate_boundary_cell_count++;
        }
        if (cell.crust_type == 8) {
            step.accreted_terrane_cell_count++;
        }
        if (index < previous_plate_ids.size() && cell.plate_id != previous_plate_ids[index]) {
            step.reassigned_cell_count++;
        }
        if (index < crust_age_change_ma.size()) {
            step.mean_abs_crust_age_change_ma += std::abs(crust_age_change_ma[index]);
        }
        if (index < crust_thickness_change_km.size()) {
            step.mean_abs_crust_thickness_change_km += std::abs(crust_thickness_change_km[index]);
        }
        if (index < crust_density_change.size()) {
            step.mean_abs_crust_density_change += std::abs(crust_density_change[index]);
        }
        step.mean_abs_crust_age_transport_change_ma += std::abs(
            step.crust_age_transport_change_ma_by_cell[index]
        );
        step.mean_abs_crust_thickness_transport_change_km += std::abs(
            step.crust_thickness_transport_change_km_by_cell[index]
        );
        step.mean_abs_crust_density_transport_change += std::abs(
            step.crust_density_transport_change_by_cell[index]
        );
        step.mean_abs_crust_age_process_change_ma += std::abs(
            step.crust_age_process_change_ma_by_cell[index]
        );
        step.mean_abs_crust_thickness_process_change_km += std::abs(
            step.crust_thickness_process_change_km_by_cell[index]
        );
        step.mean_abs_crust_density_process_change += std::abs(
            step.crust_density_process_change_by_cell[index]
        );
        if (index < tectonic_elevation_change_m.size()) {
            const double delta = tectonic_elevation_change_m[index];
            step.mean_tectonic_elevation_change_m += delta;
            step.mean_abs_tectonic_elevation_change_m += std::abs(delta);
            step.max_abs_tectonic_elevation_change_m = std::max(
                step.max_abs_tectonic_elevation_change_m,
                std::abs(delta)
            );
        }
        for (int neighbor : cell.neighbors) {
            if (neighbor > static_cast<int>(index) && cell.plate_id != cells[static_cast<std::size_t>(neighbor)].plate_id) {
                step.plate_boundary_edge_count++;
            }
        }
    }

    const double cell_divisor = cells.empty() ? 1.0 : static_cast<double>(cells.size());
    step.unique_crust_source_cell_count = static_cast<int>(unique_crust_sources.size());
    step.crust_source_reuse_count = static_cast<int>(cells.size()) - step.unique_crust_source_cell_count;
    step.reassigned_cell_fraction = static_cast<double>(step.reassigned_cell_count) / cell_divisor;
    step.mean_crust_transport_distance_km /= cell_divisor;
    step.mean_abs_crust_age_change_ma /= cell_divisor;
    step.mean_abs_crust_thickness_change_km /= cell_divisor;
    step.mean_abs_crust_density_change /= cell_divisor;
    step.mean_abs_crust_age_transport_change_ma /= cell_divisor;
    step.mean_abs_crust_thickness_transport_change_km /= cell_divisor;
    step.mean_abs_crust_density_transport_change /= cell_divisor;
    step.mean_abs_crust_age_process_change_ma /= cell_divisor;
    step.mean_abs_crust_thickness_process_change_km /= cell_divisor;
    step.mean_abs_crust_density_process_change /= cell_divisor;
    step.mean_tectonic_elevation_change_m /= cell_divisor;
    step.mean_abs_tectonic_elevation_change_m /= cell_divisor;

    for (std::size_t plate_index = 0; plate_index < plates.size(); ++plate_index) {
        const Plate& plate = plates[plate_index];
        PlateKinematicSnapshot snapshot;
        snapshot.plate_id = plate.id;
        snapshot.center = plate.center;
        snapshot.step_rotation_deg = plate_index < step_rotation_deg.size() ? step_rotation_deg[plate_index] : 0.0;
        snapshot.cumulative_rotation_deg = plate.cumulative_rotation_deg;
        snapshot.cell_count = plate_cell_counts[plate_index];
        snapshot.area_km2 = plate_areas[plate_index];
        step.mean_plate_rotation_deg += std::abs(snapshot.step_rotation_deg);
        step.max_plate_rotation_deg = std::max(step.max_plate_rotation_deg, std::abs(snapshot.step_rotation_deg));
        step.plates.push_back(snapshot);
    }
    if (!plates.empty()) {
        step.mean_plate_rotation_deg /= static_cast<double>(plates.size());
    }
    return step;
}

std::vector<double> advance_plate_motion_and_crust(
    const Params& params,
    int erosion_iteration,
    std::vector<Plate>& plates,
    std::vector<Cell>& cells,
    std::vector<PlateMotionStep>& plate_motion_history
) {
    const int n = static_cast<int>(cells.size());
    std::vector<int> previous_plate_ids(static_cast<std::size_t>(n));
    std::vector<int> previous_crust_types(static_cast<std::size_t>(n));
    std::vector<int> previous_lithologies(static_cast<std::size_t>(n));
    std::vector<double> previous_crust_age(static_cast<std::size_t>(n));
    std::vector<double> previous_crust_thickness(static_cast<std::size_t>(n));
    std::vector<double> previous_crust_density(static_cast<std::size_t>(n));
    std::vector<double> previous_convergent(static_cast<std::size_t>(n));
    std::vector<double> previous_divergent(static_cast<std::size_t>(n));
    std::vector<double> previous_transform(static_cast<std::size_t>(n));
    for (int i = 0; i < n; ++i) {
        const Cell& cell = cells[static_cast<std::size_t>(i)];
        previous_plate_ids[static_cast<std::size_t>(i)] = cell.plate_id;
        previous_crust_types[static_cast<std::size_t>(i)] = cell.crust_type;
        previous_lithologies[static_cast<std::size_t>(i)] = cell.lithology;
        previous_crust_age[static_cast<std::size_t>(i)] = cell.crust_age_ma;
        previous_crust_thickness[static_cast<std::size_t>(i)] = cell.crust_thickness_km;
        previous_crust_density[static_cast<std::size_t>(i)] = cell.crust_density;
        previous_convergent[static_cast<std::size_t>(i)] = cell.boundary_convergent;
        previous_divergent[static_cast<std::size_t>(i)] = cell.boundary_divergent;
        previous_transform[static_cast<std::size_t>(i)] = cell.boundary_transform;
    }

    std::vector<double> step_rotation_deg(plates.size(), 0.0);
    std::vector<Vec3> centers;
    centers.reserve(plates.size());
    for (std::size_t index = 0; index < plates.size(); ++index) {
        Plate& plate = plates[index];
        const double rotation_deg = plate.angular_speed * params.plate_motion_scale_deg_per_step;
        const double rotation_rad = rotation_deg / DEG;
        plate.center = rotate_about_axis(plate.center, plate.axis, rotation_rad);
        plate.cumulative_rotation_deg += rotation_deg;
        step_rotation_deg[index] = rotation_deg;
        centers.push_back(plate.center);
    }
    assign_plates(centers, cells);
    classify_boundaries(params, plates, cells);

    std::vector<std::vector<int>> previous_cells_by_plate(plates.size());
    for (int i = 0; i < n; ++i) {
        const int plate_id = previous_plate_ids[static_cast<std::size_t>(i)];
        if (plate_id >= 0 && plate_id < static_cast<int>(plates.size())) {
            previous_cells_by_plate[static_cast<std::size_t>(plate_id)].push_back(i);
        }
    }
    CrustMotionDiagnostics crust_motion;
    crust_motion.source_cell_ids.assign(static_cast<std::size_t>(n), -1);
    crust_motion.transport_distance_km_by_cell.assign(static_cast<std::size_t>(n), 0.0);
    crust_motion.age_transport_change_ma_by_cell.assign(static_cast<std::size_t>(n), 0.0);
    crust_motion.thickness_transport_change_km_by_cell.assign(static_cast<std::size_t>(n), 0.0);
    crust_motion.density_transport_change_by_cell.assign(static_cast<std::size_t>(n), 0.0);
    crust_motion.age_process_change_ma_by_cell.assign(static_cast<std::size_t>(n), 0.0);
    crust_motion.thickness_process_change_km_by_cell.assign(static_cast<std::size_t>(n), 0.0);
    crust_motion.density_process_change_by_cell.assign(static_cast<std::size_t>(n), 0.0);
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        const std::size_t index = static_cast<std::size_t>(i);
        const int plate_id = cells[index].plate_id;
        const Plate& plate = plates[static_cast<std::size_t>(plate_id)];
        const double rotation_rad = step_rotation_deg[static_cast<std::size_t>(plate_id)] / DEG;
        const Vec3 backtraced_position = rotate_about_axis(cells[index].p, plate.axis, -rotation_rad);
        int best_source = i;
        double best_score = -2.0;
        const std::vector<int>& candidates = previous_cells_by_plate[static_cast<std::size_t>(plate_id)];
        for (int candidate : candidates) {
            const double score = dot(backtraced_position, cells[static_cast<std::size_t>(candidate)].p);
            if (score > best_score) {
                best_score = score;
                best_source = candidate;
            }
        }
        const std::size_t source_index = static_cast<std::size_t>(best_source);
        crust_motion.source_cell_ids[index] = best_source;
        crust_motion.transport_distance_km_by_cell[index] =
            angular_distance(backtraced_position, cells[index].p) * params.radius_km;
        crust_motion.age_transport_change_ma_by_cell[index] =
            previous_crust_age[source_index] - previous_crust_age[index];
        crust_motion.thickness_transport_change_km_by_cell[index] =
            previous_crust_thickness[source_index] - previous_crust_thickness[index];
        crust_motion.density_transport_change_by_cell[index] =
            previous_crust_density[source_index] - previous_crust_density[index];
    }

    const double tectonic_activity = clamp(
        params.internal_heat * std::sqrt(4.5 / std::max(0.05, params.geological_age_ga)),
        0.25,
        2.25
    );
    std::vector<double> crust_age_change(static_cast<std::size_t>(n), 0.0);
    std::vector<double> crust_thickness_change(static_cast<std::size_t>(n), 0.0);
    std::vector<double> crust_density_change(static_cast<std::size_t>(n), 0.0);
    std::vector<double> tectonic_elevation_change(static_cast<std::size_t>(n), 0.0);
    std::vector<int> aged_oceanic_flags(static_cast<std::size_t>(n), 0);
    std::vector<int> rejuvenated_oceanic_flags(static_cast<std::size_t>(n), 0);
    std::vector<int> subducted_oceanic_flags(static_cast<std::size_t>(n), 0);
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        Cell& cell = cells[static_cast<std::size_t>(i)];
        const std::size_t index = static_cast<std::size_t>(i);
        const std::size_t source_index = static_cast<std::size_t>(crust_motion.source_cell_ids[index]);
        const int old_plate_id = previous_plate_ids[index];
        const bool plate_changed = cell.plate_id != old_plate_id;
        const bool local_old_oceanic = is_oceanic_crust_state(
            previous_crust_types[index],
            previous_crust_age[index],
            previous_crust_thickness[index],
            previous_crust_density[index]
        );
        const bool old_oceanic = is_oceanic_crust_state(
            previous_crust_types[source_index],
            previous_crust_age[source_index],
            previous_crust_thickness[source_index],
            previous_crust_density[source_index]
        );
        const Plate& plate = plates[static_cast<std::size_t>(cell.plate_id)];
        const double conv = cell.boundary_convergent;
        const double div = cell.boundary_divergent;
        const double trans = cell.boundary_transform;

        int crust_type = previous_crust_types[source_index];
        int lithology = previous_lithologies[source_index];
        double crust_age = previous_crust_age[source_index];
        double crust_thickness = previous_crust_thickness[source_index];
        double crust_density = previous_crust_density[source_index];

        if (old_oceanic && div < 0.10 && conv < 0.10) {
            const double quiet_fraction = clamp(1.0 - std::max(div, conv) / 0.10, 0.0, 1.0);
            crust_age += params.oceanic_crust_aging_ma_per_step * quiet_fraction;
        }

        if (plate_changed && std::max(conv, div) < 0.18) {
            crust_type = 2;
            lithology = old_oceanic ? 0 : 3;
        }
        if (div >= 0.10) {
            if (old_oceanic) {
                const double rejuvenation = clamp(div * (plate_changed ? 0.72 : 0.55), 0.0, 0.85);
                crust_age *= 1.0 - rejuvenation;
                crust_thickness += (7.0 - crust_thickness) * 0.34 * div;
                crust_density += (3.0 - crust_density) * 0.24 * div;
                if (div >= 0.28) {
                    crust_type = 0;
                    lithology = 0;
                }
            } else {
                crust_thickness -= tectonic_activity * (0.45 + (plate_changed ? 0.20 : 0.0)) * div;
                crust_density += 0.004 * div;
                if (div >= 0.24) {
                    crust_type = 6;
                    lithology = 3;
                }
            }
        }
        if (conv >= 0.10) {
            if (old_oceanic) {
                crust_thickness += tectonic_activity * 0.34 * conv;
                crust_age *= 1.0 - 0.12 * conv;
                if (conv >= 0.26) {
                    crust_type = 3;
                    lithology = 5;
                }
            } else {
                crust_thickness += tectonic_activity * (0.72 + (plate_changed ? 0.38 : 0.0)) * conv;
                crust_density -= 0.006 * conv;
                if (plate_changed && conv >= 0.18) {
                    crust_type = 8;
                    lithology = 6;
                } else if (conv >= 0.28) {
                    crust_type = 5;
                    lithology = 6;
                }
            }
        }

        const bool new_oceanic = is_oceanic_crust_state(
            crust_type, crust_age, crust_thickness, crust_density
        );
        crust_age = clamp(crust_age, 0.0, new_oceanic ? 320.0 : 4200.0);
        crust_thickness = clamp(crust_thickness, new_oceanic ? 4.5 : 16.0, new_oceanic ? 18.0 : 76.0);
        crust_density = clamp(crust_density, 2.58, 3.08);

        crust_motion.age_process_change_ma_by_cell[index] = crust_age - previous_crust_age[source_index];
        crust_motion.thickness_process_change_km_by_cell[index] =
            crust_thickness - previous_crust_thickness[source_index];
        crust_motion.density_process_change_by_cell[index] =
            crust_density - previous_crust_density[source_index];
        crust_age_change[index] = crust_age - previous_crust_age[index];
        crust_thickness_change[index] = crust_thickness - previous_crust_thickness[index];
        crust_density_change[index] = crust_density - previous_crust_density[index];
        cell.crust_type = crust_type;
        cell.lithology = lithology;
        cell.crust_age_ma = crust_age;
        cell.crust_thickness_km = crust_thickness;
        cell.crust_density = crust_density;
        cell.last_crust_source_cell_id = static_cast<int>(source_index);
        cell.cumulative_crust_transport_distance_km += crust_motion.transport_distance_km_by_cell[index];
        if (source_index != index) {
            cell.crust_source_remap_event_count++;
        }
        if (crust_motion.age_process_change_ma_by_cell[index] > 1.0e-6 && old_oceanic) {
            aged_oceanic_flags[index] = 1;
            cell.oceanic_crust_aging_event_count++;
        }
        if (div >= 0.10 && crust_motion.age_process_change_ma_by_cell[index] < -1.0e-6 && old_oceanic) {
            rejuvenated_oceanic_flags[index] = 1;
            cell.oceanic_crust_rejuvenation_event_count++;
        }
        if (
            conv >= 0.18 &&
            ((plate_changed && local_old_oceanic) || (old_oceanic && conv >= 0.26))
        ) {
            subducted_oceanic_flags[index] = 1;
            cell.oceanic_crust_subduction_event_count++;
        }
        if (plate_changed) {
            cell.plate_assignment_change_count++;
            cell.last_plate_assignment_change_iteration = erosion_iteration;
        }

        const double old_equilibrium = crust_equilibrium_elevation_m(
            previous_crust_thickness[index], previous_crust_density[index], local_old_oceanic
        ) + oceanic_thermal_subsidence_m(previous_crust_age[index], local_old_oceanic);
        const double new_equilibrium = crust_equilibrium_elevation_m(
            crust_thickness, crust_density, new_oceanic
        ) + oceanic_thermal_subsidence_m(crust_age, new_oceanic);
        cell.volcanic_potential_index = clamp(
            0.42 * div + 0.38 * conv * (crust_type == 3 ? 1.0 : 0.35) +
            0.16 * (lithology == 5 ? 1.0 : 0.0) + 0.04 * tectonic_activity,
            0.0,
            1.0
        );
        cell.uplift_rate = params.tectonic_uplift_scale * tectonic_activity *
            (1.5 * div + 8.5 * conv + (crust_type == 3 ? 2.5 : 0.0));
        const double boundary_change =
            80.0 * (conv - previous_convergent[index]) +
            55.0 * (div - previous_divergent[index]) -
            30.0 * (trans - previous_transform[index]);
        const double equilibrium_change = 0.18 * (new_equilibrium - old_equilibrium);
        const double delta = clamp(
            cell.uplift_rate * 0.42 + equilibrium_change + boundary_change,
            -180.0,
            220.0
        );
        tectonic_elevation_change[index] = delta;
        cell.cumulative_tectonic_elevation_change_m += delta;
    }

    for (int i = 0; i < n; ++i) {
        if (aged_oceanic_flags[static_cast<std::size_t>(i)] != 0) {
            crust_motion.aged_oceanic_cell_ids.push_back(i);
        }
        if (rejuvenated_oceanic_flags[static_cast<std::size_t>(i)] != 0) {
            crust_motion.rejuvenated_oceanic_cell_ids.push_back(i);
        }
        if (subducted_oceanic_flags[static_cast<std::size_t>(i)] != 0) {
            crust_motion.subducted_oceanic_cell_ids.push_back(i);
        }
    }

    plate_motion_history.push_back(summarize_plate_motion_step(
        cells,
        plates,
        static_cast<int>(plate_motion_history.size()),
        erosion_iteration,
        "plate_motion_iteration",
        previous_plate_ids,
        step_rotation_deg,
        crust_motion,
        crust_age_change,
        crust_thickness_change,
        crust_density_change,
        tectonic_elevation_change
    ));
    return tectonic_elevation_change;
}

double approximate_heat_flow_mw_m2(const Params& params, const Cell& cell) {
    const bool oceanic = is_oceanic_crust_state(
        cell.crust_type, cell.crust_age_ma, cell.crust_thickness_km, cell.crust_density
    );
    const double age = std::max(0.0, cell.crust_age_ma);
    const double age_heat = oceanic
        ? 45.0 + 95.0 * std::exp(-age / 60.0)
        : 38.0 + 34.0 * std::exp(-age / 1400.0);
    const double boundary_heat =
        55.0 * cell.boundary_divergent +
        30.0 * cell.boundary_convergent +
        18.0 * cell.boundary_transform +
        (cell.crust_type == 3 ? 24.0 : 0.0);
    return clamp(params.internal_heat * (age_heat + boundary_heat), 18.0, 240.0);
}

void summarize_plates(const Params& params, const std::vector<Cell>& cells, std::vector<Plate>& plates) {
    std::vector<std::array<double, 9>> crust_area(plates.size());
    std::vector<std::array<double, 7>> lithology_area(plates.size());
    for (auto& counts : crust_area) {
        counts.fill(0.0);
    }
    for (auto& counts : lithology_area) {
        counts.fill(0.0);
    }
    for (Plate& plate : plates) {
        plate.cell_count = 0;
        plate.area_km2 = 0.0;
        plate.mean_crust_age_ma = 0.0;
        plate.mean_crust_density = 0.0;
        plate.mean_crust_thickness_km = 0.0;
        plate.mean_boundary_activity = 0.0;
        plate.mean_heat_flow_mw_m2 = 0.0;
        plate.dominant_crust_type = plate.kind == 0 ? 0 : (plate.kind == 1 ? 1 : 2);
        plate.dominant_lithology = plate.kind == 0 ? 0 : 1;
    }
    for (const Cell& cell : cells) {
        if (cell.plate_id < 0 || cell.plate_id >= static_cast<int>(plates.size())) {
            continue;
        }
        Plate& plate = plates[static_cast<std::size_t>(cell.plate_id)];
        const double area = std::max(0.0, cell.area_km2);
        plate.cell_count += 1;
        plate.area_km2 += area;
        plate.mean_crust_age_ma += cell.crust_age_ma * area;
        plate.mean_crust_density += cell.crust_density * area;
        plate.mean_crust_thickness_km += cell.crust_thickness_km * area;
        plate.mean_boundary_activity += std::max(cell.boundary_convergent, std::max(cell.boundary_divergent, cell.boundary_transform)) * area;
        plate.mean_heat_flow_mw_m2 += approximate_heat_flow_mw_m2(params, cell) * area;
        if (cell.crust_type >= 0 && cell.crust_type < static_cast<int>(CRUST_NAMES.size())) {
            crust_area[static_cast<std::size_t>(cell.plate_id)][static_cast<std::size_t>(cell.crust_type)] += area;
        }
        if (cell.lithology >= 0 && cell.lithology < static_cast<int>(LITHOLOGY_NAMES.size())) {
            lithology_area[static_cast<std::size_t>(cell.plate_id)][static_cast<std::size_t>(cell.lithology)] += area;
        }
    }
    for (Plate& plate : plates) {
        const double divisor = plate.area_km2 > 0.0 ? plate.area_km2 : 1.0;
        plate.mean_crust_age_ma /= divisor;
        plate.mean_crust_density /= divisor;
        plate.mean_crust_thickness_km /= divisor;
        plate.mean_boundary_activity /= divisor;
        plate.mean_heat_flow_mw_m2 /= divisor;
        const std::size_t plate_index = static_cast<std::size_t>(plate.id);
        if (plate_index < crust_area.size()) {
            plate.dominant_crust_type = static_cast<int>(
                std::distance(crust_area[plate_index].begin(), std::max_element(crust_area[plate_index].begin(), crust_area[plate_index].end()))
            );
            plate.dominant_lithology = static_cast<int>(
                std::distance(lithology_area[plate_index].begin(), std::max_element(lithology_area[plate_index].begin(), lithology_area[plate_index].end()))
            );
        }
        if (plate.area_km2 <= 0.0) {
            plate.mean_crust_density = plate.crust_density;
            plate.mean_crust_thickness_km = plate.crust_thickness_km;
            plate.mean_crust_age_ma = plate.kind == 0 ? 120.0 : 1600.0;
            plate.mean_heat_flow_mw_m2 = plate.kind == 0 ? 62.0 : 54.0;
        }
    }
}

double apply_sea_level(const Params& params, std::vector<Cell>& cells) {
    const int n = static_cast<int>(cells.size());
    if (n == 0) {
        return 0.0;
    }

    std::vector<int> order(static_cast<std::size_t>(n));
    std::iota(order.begin(), order.end(), 0);
    std::sort(order.begin(), order.end(), [&](int a, int b) {
        if (cells[a].elevation_m == cells[b].elevation_m) {
            return a < b;
        }
        return cells[a].elevation_m < cells[b].elevation_m;
    });

    const double total_area_km2 = std::accumulate(
        cells.begin(),
        cells.end(),
        0.0,
        [](double total, const Cell& cell) { return total + std::max(0.0, cell.area_km2); }
    );
    if (total_area_km2 <= 0.0) {
        throw std::runtime_error("sea-level selection requires positive cell areas");
    }
    const double target_volume_km3 = params.ocean_water_inventory_km3;
    if (target_volume_km3 <= 0.0) {
        const double sea_level = std::nextafter(
            cells[order.front()].elevation_m,
            -std::numeric_limits<double>::infinity()
        );
        for (Cell& cell : cells) {
            cell.elevation_m -= sea_level;
            cell.is_water = false;
            cell.water_depth_m = 0.0;
            cell.water_body = 0;
            cell.is_lake = false;
        }
        return sea_level;
    }

    std::vector<int> parent(static_cast<std::size_t>(n));
    std::vector<int> component_size(static_cast<std::size_t>(n), 1);
    std::vector<double> component_area_km2(static_cast<std::size_t>(n), 0.0);
    std::vector<double> component_elevation_area_m_km2(static_cast<std::size_t>(n), 0.0);
    std::vector<int> component_min_id(static_cast<std::size_t>(n), 0);
    std::vector<bool> active(static_cast<std::size_t>(n), false);
    std::iota(parent.begin(), parent.end(), 0);
    for (int i = 0; i < n; ++i) {
        component_area_km2[static_cast<std::size_t>(i)] = std::max(0.0, cells[i].area_km2);
        component_elevation_area_m_km2[static_cast<std::size_t>(i)] =
            component_area_km2[static_cast<std::size_t>(i)] * cells[i].elevation_m;
        component_min_id[static_cast<std::size_t>(i)] = i;
    }
    const auto find_root = [&](int start) {
        int root = start;
        while (parent[root] != root) {
            root = parent[root];
        }
        int current = start;
        while (parent[current] != current) {
            const int next = parent[current];
            parent[current] = root;
            current = next;
        }
        return root;
    };
    const auto merge = [&](int a, int b) {
        int root_a = find_root(a);
        int root_b = find_root(b);
        if (root_a == root_b) {
            return root_a;
        }
        if (component_size[root_a] < component_size[root_b] ||
            (component_size[root_a] == component_size[root_b] && root_b < root_a)) {
            std::swap(root_a, root_b);
        }
        parent[root_b] = root_a;
        component_size[root_a] += component_size[root_b];
        component_area_km2[root_a] += component_area_km2[root_b];
        component_elevation_area_m_km2[root_a] += component_elevation_area_m_km2[root_b];
        component_min_id[root_a] = std::min(component_min_id[root_a], component_min_id[root_b]);
        return root_a;
    };

    double best_error_km3 = std::numeric_limits<double>::infinity();
    double best_connected_area_km2 = 0.0;
    double best_flood_elevation = cells[order.front()].elevation_m;
    double best_sea_level = std::nextafter(
        best_flood_elevation,
        std::numeric_limits<double>::infinity()
    );
    int largest_component_root = -1;
    bool exact_solution_found = false;
    const auto consider_candidate = [&](double sea_level, int component_root, double flood_elevation) {
        if (!std::isfinite(sea_level) || component_root < 0) {
            return;
        }
        component_root = find_root(component_root);
        const double area_km2 = component_area_km2[component_root];
        if (area_km2 <= 0.0) {
            return;
        }
        const double volume_km3 = std::max(
            0.0,
            (area_km2 * sea_level - component_elevation_area_m_km2[component_root]) / 1000.0
        );
        const double error_km3 = std::abs(volume_km3 - target_volume_km3);
        if (
            error_km3 < best_error_km3 ||
            (error_km3 == best_error_km3 && sea_level < best_sea_level)
        ) {
            best_error_km3 = error_km3;
            best_connected_area_km2 = area_km2;
            best_flood_elevation = flood_elevation;
            best_sea_level = sea_level;
        }
    };
    std::size_t position = 0;
    while (position < order.size()) {
        const double elevation = cells[order[position]].elevation_m;
        std::size_t end = position;
        while (end < order.size() && cells[order[end]].elevation_m == elevation) {
            active[static_cast<std::size_t>(order[end])] = true;
            ++end;
        }
        for (std::size_t index = position; index < end; ++index) {
            const int cell_id = order[index];
            for (int neighbor_id : cells[cell_id].neighbors) {
                if (neighbor_id >= 0 && neighbor_id < n && active[static_cast<std::size_t>(neighbor_id)]) {
                    merge(cell_id, neighbor_id);
                }
            }
        }
        if (largest_component_root >= 0) {
            largest_component_root = find_root(largest_component_root);
        }
        for (std::size_t index = position; index < end; ++index) {
            const int root = find_root(order[index]);
            if (
                largest_component_root < 0 ||
                component_area_km2[root] > component_area_km2[largest_component_root] ||
                (component_area_km2[root] == component_area_km2[largest_component_root] &&
                    component_min_id[root] < component_min_id[largest_component_root])
            ) {
                largest_component_root = root;
            }
        }
        largest_component_root = find_root(largest_component_root);
        const double component_area = component_area_km2[largest_component_root];
        const double component_elevation_area =
            component_elevation_area_m_km2[largest_component_root];
        const double solved_sea_level =
            (target_volume_km3 * 1000.0 + component_elevation_area) / component_area;
        const double next_elevation = end < order.size()
            ? cells[order[end]].elevation_m
            : std::numeric_limits<double>::infinity();
        const double interval_lower = std::nextafter(
            elevation,
            std::numeric_limits<double>::infinity()
        );
        consider_candidate(interval_lower, largest_component_root, elevation);
        if (solved_sea_level >= interval_lower && solved_sea_level < next_elevation) {
            consider_candidate(solved_sea_level, largest_component_root, elevation);
            exact_solution_found = true;
        } else if (std::isfinite(next_elevation)) {
            const double interval_upper = std::nextafter(next_elevation, elevation);
            if (interval_upper >= interval_lower) {
                consider_candidate(interval_upper, largest_component_root, elevation);
            }
        } else if (solved_sea_level >= interval_lower) {
            consider_candidate(solved_sea_level, largest_component_root, elevation);
            exact_solution_found = true;
        }
        position = end;
        if (exact_solution_found) {
            break;
        }
    }

    std::vector<bool> below_level(static_cast<std::size_t>(n), false);
    for (int i = 0; i < n; ++i) {
        below_level[static_cast<std::size_t>(i)] = cells[i].elevation_m <= best_flood_elevation;
    }
    std::vector<bool> visited(static_cast<std::size_t>(n), false);
    std::vector<int> ocean_component;
    double ocean_component_area_km2 = 0.0;
    int ocean_component_min_id = std::numeric_limits<int>::max();
    for (int start_id : order) {
        if (!below_level[static_cast<std::size_t>(start_id)] || visited[static_cast<std::size_t>(start_id)]) {
            continue;
        }
        std::vector<int> component;
        double component_area = 0.0;
        int component_min_id = start_id;
        std::queue<int> queue;
        queue.push(start_id);
        visited[static_cast<std::size_t>(start_id)] = true;
        while (!queue.empty()) {
            const int current = queue.front();
            queue.pop();
            component.push_back(current);
            component_area += std::max(0.0, cells[current].area_km2);
            component_min_id = std::min(component_min_id, current);
            for (int neighbor_id : cells[current].neighbors) {
                if (
                    neighbor_id >= 0 && neighbor_id < n &&
                    below_level[static_cast<std::size_t>(neighbor_id)] &&
                    !visited[static_cast<std::size_t>(neighbor_id)]
                ) {
                    visited[static_cast<std::size_t>(neighbor_id)] = true;
                    queue.push(neighbor_id);
                }
            }
        }
        if (
            component_area > ocean_component_area_km2 ||
            (component_area == ocean_component_area_km2 && component_min_id < ocean_component_min_id)
        ) {
            ocean_component = std::move(component);
            ocean_component_area_km2 = component_area;
            ocean_component_min_id = component_min_id;
        }
    }
    if (
        std::abs(ocean_component_area_km2 - best_connected_area_km2) >
        std::max(1.0e-6, best_connected_area_km2 * 1.0e-12)
    ) {
        throw std::runtime_error("connectivity-constrained sea-level reconstruction mismatch");
    }

    const double sea_level = best_sea_level;
    std::vector<bool> is_ocean(static_cast<std::size_t>(n), false);
    for (int cell_id : ocean_component) {
        is_ocean[static_cast<std::size_t>(cell_id)] = true;
    }
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        cells[i].elevation_m -= sea_level;
        cells[i].is_water = is_ocean[static_cast<std::size_t>(i)];
        cells[i].water_depth_m = cells[i].is_water ? -cells[i].elevation_m : 0.0;
        cells[i].water_body = cells[i].is_water ? 1 : 0;
        cells[i].is_lake = false;
    }
    return sea_level;
}

void label_marine_water_bodies(std::vector<Cell>& cells) {
    const int n = static_cast<int>(cells.size());
    std::vector<int> component(n, -1);
    std::vector<int> sizes;
    int component_id = 0;
    for (int i = 0; i < n; ++i) {
        if (!cells[i].is_water || component[i] >= 0) {
            continue;
        }
        int size = 0;
        std::queue<int> queue;
        queue.push(i);
        component[i] = component_id;
        while (!queue.empty()) {
            const int current = queue.front();
            queue.pop();
            ++size;
            for (int neighbor : cells[current].neighbors) {
                if (cells[neighbor].is_water && component[neighbor] < 0) {
                    component[neighbor] = component_id;
                    queue.push(neighbor);
                }
            }
        }
        sizes.push_back(size);
        ++component_id;
    }
    int largest_component = -1;
    int largest_size = -1;
    for (int id = 0; id < static_cast<int>(sizes.size()); ++id) {
        if (sizes[id] > largest_size) {
            largest_size = sizes[id];
            largest_component = id;
        }
    }
    for (int i = 0; i < n; ++i) {
        if (!cells[i].is_water) {
            cells[i].water_body = 0;
        } else if (component[i] == largest_component) {
            cells[i].water_body = cells[i].water_depth_m < 220.0 ? 2 : 1;
        } else {
            cells[i].water_body = 3;
        }
    }
}

std::vector<int> ocean_distance(const std::vector<Cell>& cells) {
    const int n = static_cast<int>(cells.size());
    std::vector<int> distance(n, std::numeric_limits<int>::max());
    std::queue<int> queue;
    for (int i = 0; i < n; ++i) {
        if (cells[i].is_water) {
            distance[i] = 0;
            queue.push(i);
        }
    }
    while (!queue.empty()) {
        const int i = queue.front();
        queue.pop();
        for (int j : cells[i].neighbors) {
            if (distance[j] == std::numeric_limits<int>::max()) {
                distance[j] = distance[i] + 1;
                queue.push(j);
            }
        }
    }
    for (int& d : distance) {
        if (d == std::numeric_limits<int>::max()) {
            d = n;
        }
    }
    return distance;
}

double wrap_angle(double radians) {
    while (radians > PI) {
        radians -= 2.0 * PI;
    }
    while (radians < -PI) {
        radians += 2.0 * PI;
    }
    return radians;
}

double local_relief(const std::vector<Cell>& cells, int i) {
    if (cells[i].neighbors.empty()) {
        return 0.0;
    }
    double avg = 0.0;
    for (int j : cells[i].neighbors) {
        avg += cells[j].elevation_m;
    }
    avg /= static_cast<double>(cells[i].neighbors.size());
    return std::max(0.0, cells[i].elevation_m - avg);
}

std::pair<double, double> prevailing_wind_components(double lat, double day_length_hours) {
    const double lat_abs_deg = std::abs(lat * DEG);
    const double rotation = clamp(24.0 / std::max(1.0, day_length_hours), 0.35, 2.6);
    double east = -1.0;
    double north = lat >= 0.0 ? -0.22 : 0.22;
    if (lat_abs_deg >= 30.0 && lat_abs_deg < 60.0) {
        east = 1.0;
        north = lat >= 0.0 ? 0.16 : -0.16;
    } else if (lat_abs_deg >= 60.0) {
        east = -0.75;
        north = lat >= 0.0 ? -0.18 : 0.18;
    }
    east *= rotation;
    const double len = std::max(1.0e-9, std::sqrt(east * east + north * north));
    return {east / len, north / len};
}

std::pair<int, double> upwind_neighbor_for_wind(const std::vector<Cell>& cells, int i, double wind_east, double wind_north) {
    const Cell& cell = cells[i];
    int upwind = -1;
    double best_alignment = -1.0;
    for (int neighbor : cell.neighbors) {
        const Cell& source = cells[neighbor];
        const double dx = wrap_angle(cell.lon - source.lon) * std::cos(cell.lat);
        const double dy = cell.lat - source.lat;
        const double len = std::sqrt(dx * dx + dy * dy);
        if (len < 1.0e-9) {
            continue;
        }
        const double alignment = (dx / len) * wind_east + (dy / len) * wind_north;
        if (alignment > best_alignment) {
            best_alignment = alignment;
            upwind = neighbor;
        }
    }
    return {upwind, best_alignment};
}

std::pair<double, double> orographic_and_shadow_factors(const std::vector<Cell>& cells, int i, double wind_east, double wind_north) {
    const Cell& cell = cells[i];
    const auto [upwind, best_alignment] = upwind_neighbor_for_wind(cells, i, wind_east, wind_north);
    if (upwind < 0 || best_alignment < 0.12) {
        return {1.0, 1.0};
    }
    const double upwind_elevation = cells[upwind].elevation_m;
    const double climb = std::max(0.0, cell.elevation_m - upwind_elevation);
    const double descent = std::max(0.0, upwind_elevation - cell.elevation_m);
    const double oro = 1.0 + 0.42 * clamp(climb / 1600.0, 0.0, 1.0) * best_alignment;
    const double shadow = 1.0 - 0.48 * clamp(descent / 1800.0, 0.0, 1.0) * best_alignment;
    return {clamp(oro, 0.70, 1.45), clamp(shadow, 0.48, 1.0)};
}

struct HumidityTransport {
    double index = 0.0;
    double upwind_ocean_fetch_km = 0.0;
    double factor = 1.0;
};

HumidityTransport humidity_transport_along_wind(
    const Params& params,
    const std::vector<Cell>& cells,
    int start,
    double wind_east,
    double wind_north
) {
    const int max_steps = clamp(params.cell_count / 256 + 10, 10, 34);
    int current = start;
    double parcel = cells[start].is_water ? 0.72 : 0.08;
    double fetch_km = cells[start].is_water ? 120.0 : 0.0;
    double rainout = 0.0;
    double decay = 1.0;
    std::set<int> visited;
    visited.insert(start);

    for (int step = 0; step < max_steps; ++step) {
        const auto [source_id, alignment] = upwind_neighbor_for_wind(cells, current, wind_east, wind_north);
        if (source_id < 0 || alignment < 0.10 || visited.count(source_id) > 0) {
            break;
        }
        const Cell& source = cells[source_id];
        const Cell& target = cells[current];
        const double distance_km = std::max(1.0, angular_distance(source.p, target.p) * params.radius_km);
        if (source.is_water) {
            const double source_strength = source.water_body == 1 ? 1.0 : (source.water_body == 2 ? 0.82 : 0.68);
            fetch_km += distance_km * source_strength * decay;
            parcel += decay * source_strength * clamp(distance_km / 620.0, 0.10, 0.46);
        } else if (source.is_lake || source.water_body == 4 || source.water_body == 5) {
            parcel += 0.12 * decay;
        } else {
            parcel *= 0.93;
        }

        const double climb = std::max(0.0, target.elevation_m - source.elevation_m);
        const double descent = std::max(0.0, source.elevation_m - target.elevation_m);
        rainout += decay * clamp(climb / 2600.0, 0.0, 1.2);
        parcel *= 1.0 - 0.18 * clamp(climb / 2600.0, 0.0, 1.0);
        parcel *= 1.0 - 0.04 * clamp(descent / 2200.0, 0.0, 1.0);

        current = source_id;
        visited.insert(source_id);
        decay *= 0.88;
    }

    HumidityTransport transport;
    transport.upwind_ocean_fetch_km = fetch_km;
    transport.index = clamp(parcel / (1.0 + 0.18 * rainout), 0.0, 1.35);
    transport.factor = clamp(0.82 + 0.28 * transport.index, 0.70, 1.20);
    return transport;
}

std::pair<double, double> ocean_current_components(double lat, double lon, double day_length_hours) {
    const double lat_abs_deg = std::abs(lat * DEG);
    const double rotation = clamp(24.0 / std::max(1.0, day_length_hours), 0.45, 2.4);
    double east = -0.85;
    double north = 0.0;
    if (lat_abs_deg < 12.0) {
        east = -1.0;
        north = 0.16 * std::sin(lon);
    } else if (lat_abs_deg < 35.0) {
        east = -0.72;
        north = (lat >= 0.0 ? 0.42 : -0.42) * std::sin(lon);
    } else if (lat_abs_deg < 62.0) {
        east = 0.86;
        north = (lat >= 0.0 ? -0.34 : 0.34) * std::cos(lon);
    } else {
        east = -0.42;
        north = lat >= 0.0 ? -0.22 : 0.22;
    }
    east *= std::sqrt(rotation);
    const double len = std::max(1.0e-9, std::sqrt(east * east + north * north));
    return {east / len, north / len};
}

void compute_climate(const Params& params, std::vector<Cell>& cells) {
    const std::vector<int> dist = ocean_distance(cells);
    const int n = static_cast<int>(cells.size());
    const double pressure = std::max(0.01, params.atmosphere_pressure_bar);
    const double pressure_temp_adj = 4.5 * std::log(pressure);
    const double pressure_precip_factor = clamp(std::pow(pressure, 0.35), 0.35, 1.85);
    const double gravity_precip_factor = clamp(1.08 - 0.10 * (params.gravity_g - 1.0), 0.65, 1.35);
    const double rotation_band_shift = clamp((params.day_length_hours - 24.0) / 24.0 * 5.0, -7.0, 9.0);
    const double eccentricity_season_factor = 1.0 + 1.8 * clamp(params.orbital_eccentricity, 0.0, 0.8);
    double local_temperature_adjustment_area_sum = 0.0;
    double total_cell_area_km2 = 0.0;
    for (int i = 0; i < n; ++i) {
        const Cell& cell = cells[static_cast<std::size_t>(i)];
        const double oceanity = std::exp(-static_cast<double>(dist[static_cast<std::size_t>(i)]) / 7.5);
        const auto current = ocean_current_components(cell.lat, cell.lon, params.day_length_hours);
        const double poleward_current = cell.lat >= 0.0 ? current.second : -current.second;
        const double current_temp = oceanity * clamp(
            3.8 * poleward_current + 1.2 * std::cos(cell.lat) * std::sin(cell.lon),
            -4.5,
            4.5
        );
        const double lapse = std::max(0.0, cell.elevation_m) *
            params.lapse_rate_c_per_km / 1000.0;
        const double local_adjustment = -lapse +
            (cell.is_water ? CLIMATE_MARINE_ANNUAL_TEMPERATURE_OFFSET_C : 0.0) +
            current_temp;
        const double area_km2 = std::max(0.0, cell.area_km2);
        local_temperature_adjustment_area_sum += local_adjustment * area_km2;
        total_cell_area_km2 += area_km2;
    }
    const double local_temperature_adjustment_area_mean = total_cell_area_km2 > 0.0
        ? local_temperature_adjustment_area_sum / total_cell_area_km2
        : 0.0;
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        Cell& cell = cells[i];
        cell.temperature_monthly_c.assign(static_cast<std::size_t>(params.months), 0.0);
        cell.precipitation_monthly_mm.assign(static_cast<std::size_t>(params.months), 0.0);
        cell.wind_monthly_east.assign(static_cast<std::size_t>(params.months), 0.0);
        cell.wind_monthly_north.assign(static_cast<std::size_t>(params.months), 0.0);
        const auto wind = prevailing_wind_components(cell.lat, params.day_length_hours);
        cell.wind_east = wind.first;
        cell.wind_north = wind.second;
        const auto moisture_factors = orographic_and_shadow_factors(cells, i, cell.wind_east, cell.wind_north);
        cell.orographic_factor = moisture_factors.first;
        cell.rain_shadow_factor = moisture_factors.second;
        const HumidityTransport humidity = humidity_transport_along_wind(params, cells, i, cell.wind_east, cell.wind_north);
        cell.humidity_transport_index = humidity.index;
        cell.upwind_ocean_fetch_km = humidity.upwind_ocean_fetch_km;
        cell.advected_moisture_factor = humidity.factor;
        const double lat_abs_deg = std::abs(cell.lat * DEG);
        const double oceanity = std::exp(-static_cast<double>(dist[i]) / 7.5);
        const double continentality = 1.0 - oceanity;
        const double subtropical_center = 30.0 + rotation_band_shift;
        const double midlatitude_center = 55.0 + 0.5 * rotation_band_shift;
        const double tropical_ascent = std::exp(-(lat_abs_deg * lat_abs_deg) / (2.0 * 13.0 * 13.0));
        const double subtropical_high = std::exp(-std::pow(lat_abs_deg - subtropical_center, 2.0) / (2.0 * 9.5 * 9.5));
        const double subpolar_low = std::exp(-std::pow(lat_abs_deg - midlatitude_center, 2.0) / (2.0 * 11.0 * 11.0));
        const double polar_high = std::exp(-std::pow(lat_abs_deg - 82.0, 2.0) / (2.0 * 12.0 * 12.0));
        if (lat_abs_deg < 18.0) {
            cell.atmospheric_cell = 0;
        } else if (std::abs(lat_abs_deg - subtropical_center) < 14.0) {
            cell.atmospheric_cell = 1;
        } else if (lat_abs_deg < 66.0) {
            cell.atmospheric_cell = 2;
        } else {
            cell.atmospheric_cell = 3;
        }
        cell.vertical_velocity_index = clamp(
            0.58 * tropical_ascent + 0.36 * subpolar_low -
                0.46 * subtropical_high - 0.24 * polar_high +
                0.16 * std::max(0.0, cell.orographic_factor - 1.0),
            -1.0,
            1.0
        );
        cell.wind_divergence_index = clamp(
            0.54 * subtropical_high + 0.30 * polar_high -
                0.46 * tropical_ascent - 0.34 * subpolar_low,
            -1.0,
            1.0
        );
        cell.surface_pressure_anomaly_hpa = clamp(
            10.5 * cell.wind_divergence_index - 3.0 * cell.vertical_velocity_index,
            -22.0,
            22.0
        );
        const double circulation_precip_factor = clamp(
            1.0 + 0.22 * std::max(0.0, cell.vertical_velocity_index) -
                0.18 * std::max(0.0, cell.wind_divergence_index),
            0.66,
            1.26
        );
        const auto current = ocean_current_components(cell.lat, cell.lon, params.day_length_hours);
        cell.ocean_current_east = current.first * oceanity;
        cell.ocean_current_north = current.second * oceanity;
        const double poleward_current = cell.lat >= 0.0 ? current.second : -current.second;
        const double current_temp = oceanity * clamp(
            3.8 * poleward_current + 1.2 * std::cos(cell.lat) * std::sin(cell.lon),
            -4.5,
            4.5
        );
        cell.ocean_current_temperature_c = current_temp;
        cell.ocean_current_moisture_factor = clamp(
            1.0 + oceanity * (0.045 * std::max(0.0, current_temp) - 0.035 * std::max(0.0, -current_temp)),
            0.72,
            1.28
        );
        const double lum_adj = 38.0 * (std::pow(params.stellar_luminosity, 0.25) - 1.0);
        const double greenhouse_adj = 11.0 * (params.greenhouse_factor - 1.0);
        const double latitude_temperature_area_mean_offset_c =
            CLIMATE_LATITUDE_TEMPERATURE_GRADIENT_C /
            (CLIMATE_LATITUDE_TEMPERATURE_EXPONENT + 1.0);
        const double latitude_temp = params.base_temperature_c +
            latitude_temperature_area_mean_offset_c -
            CLIMATE_LATITUDE_TEMPERATURE_GRADIENT_C * std::pow(
                std::sin(std::abs(cell.lat)), CLIMATE_LATITUDE_TEMPERATURE_EXPONENT
            );
        const double lapse = std::max(0.0, cell.elevation_m) * params.lapse_rate_c_per_km / 1000.0;
        double annual_temp = 0.0;
        double annual_precip = 0.0;
        double seasonal_wind_speed_sum = 0.0;
        double seasonal_wind_reversal_sum = 0.0;
        const double axial_wind_factor = clamp(params.axial_tilt_deg / 23.5, 0.12, 2.4) * eccentricity_season_factor;
        const double monsoon_band = std::exp(-(lat_abs_deg * lat_abs_deg) / (2.0 * 28.0 * 28.0));
        const double base_wind_len = std::max(
            1.0e-9,
            std::sqrt(cell.wind_east * cell.wind_east + cell.wind_north * cell.wind_north)
        );
        for (int month = 0; month < params.months; ++month) {
            const double season = std::cos(2.0 * PI * (static_cast<double>(month) - 6.0) / static_cast<double>(params.months));
            const double seasonal_amp = (9.0 + 16.0 * continentality) * (params.axial_tilt_deg / 23.5) *
                eccentricity_season_factor * std::sin(cell.lat);
            const double temp = latitude_temp + lum_adj + greenhouse_adj + pressure_temp_adj +
                seasonal_amp * season - lapse +
                (cell.is_water ? CLIMATE_MARINE_ANNUAL_TEMPERATURE_OFFSET_C : 0.0) + current_temp -
                local_temperature_adjustment_area_mean;
            annual_temp += temp;
            const double equator = std::exp(-(lat_abs_deg * lat_abs_deg) / (2.0 * 18.0 * 18.0));
            const double subtropic = std::exp(-std::pow(lat_abs_deg - (30.0 + rotation_band_shift), 2.0) / (2.0 * 10.0 * 10.0));
            const double mid = std::exp(-std::pow(lat_abs_deg - (55.0 + 0.5 * rotation_band_shift), 2.0) / (2.0 * 13.0 * 13.0));
            const double relief = clamp(local_relief(cells, i) / 2200.0, 0.0, 1.0);
            const double hemisphere_season = season * (cell.lat >= 0.0 ? 1.0 : -1.0);
            const double monsoon_surface_exposure = cell.is_water ? 0.30 : 0.70 + 0.30 * continentality;
            const double monsoon = CLIMATE_SEASONAL_MONSOON_PRECIPITATION_STRENGTH *
                hemisphere_season * monsoon_surface_exposure * monsoon_band;
            const double monsoon_precipitation_factor = clamp(
                1.0 + monsoon,
                CLIMATE_SEASONAL_MONSOON_PRECIPITATION_MIN_FACTOR,
                CLIMATE_SEASONAL_MONSOON_PRECIPITATION_MAX_FACTOR
            );
            const double monsoon_wind = clamp(season * axial_wind_factor * continentality * monsoon_band, -1.25, 1.25);
            double raw_wind_east = cell.wind_east - 1.12 * monsoon_wind * cell.wind_east +
                0.18 * oceanity * season * std::sin(cell.lon);
            double raw_wind_north = cell.wind_north +
                0.76 * monsoon_wind * (cell.lat >= 0.0 ? 1.0 : -1.0) +
                0.12 * oceanity * season * std::cos(cell.lon);
            const double raw_wind_len = std::max(1.0e-9, std::sqrt(raw_wind_east * raw_wind_east + raw_wind_north * raw_wind_north));
            const double monthly_wind_speed = clamp(
                0.72 + 0.20 * oceanity + 0.16 * std::abs(monsoon_wind) + 0.10 * std::abs(cell.wind_divergence_index),
                0.42,
                1.15
            );
            const double monthly_wind_east = clamp(raw_wind_east / raw_wind_len * monthly_wind_speed, -1.0, 1.0);
            const double monthly_wind_north = clamp(raw_wind_north / raw_wind_len * monthly_wind_speed, -1.0, 1.0);
            cell.wind_monthly_east[static_cast<std::size_t>(month)] = monthly_wind_east;
            cell.wind_monthly_north[static_cast<std::size_t>(month)] = monthly_wind_north;
            const double monthly_len = std::max(
                1.0e-9,
                std::sqrt(monthly_wind_east * monthly_wind_east + monthly_wind_north * monthly_wind_north)
            );
            seasonal_wind_speed_sum += monthly_len;
            const double wind_dot = (monthly_wind_east * cell.wind_east + monthly_wind_north * cell.wind_north) /
                (monthly_len * base_wind_len);
            seasonal_wind_reversal_sum += clamp((1.0 - wind_dot) * 0.5, 0.0, 1.0);
            double annual = 170.0 + 1450.0 * equator + 680.0 * mid - 610.0 * subtropic + 560.0 * oceanity + 320.0 * relief;
            const double cold_current_drying_index = clamp(-current_temp / 4.5, 0.0, 1.0);
            const double subtropical_drying_factor = clamp(
                1.0 - params.subtropical_drying_strength * subtropic *
                    (1.0 + 0.15 * cold_current_drying_index),
                CLIMATE_SUBTROPICAL_DRYING_MIN_FACTOR,
                1.0
            );
            annual *= cell.is_water ? 1.20 : 1.0;
            annual *= params.precipitation_scale * pressure_precip_factor * gravity_precip_factor *
                cell.orographic_factor * cell.rain_shadow_factor * cell.ocean_current_moisture_factor *
                cell.advected_moisture_factor * circulation_precip_factor *
                subtropical_drying_factor * monsoon_precipitation_factor;
            const double monthly_precip = std::max(20.0, annual) / static_cast<double>(params.months);
            cell.temperature_monthly_c[static_cast<std::size_t>(month)] = temp;
            cell.precipitation_monthly_mm[static_cast<std::size_t>(month)] = monthly_precip;
            annual_precip += monthly_precip;
        }
        cell.temperature_c = annual_temp / static_cast<double>(params.months);
        cell.precipitation_mm_y = annual_precip;
        cell.mean_seasonal_wind_speed = seasonal_wind_speed_sum / static_cast<double>(params.months);
        cell.seasonal_wind_reversal_index = clamp(
            seasonal_wind_reversal_sum / static_cast<double>(params.months),
            0.0,
            1.0
        );
        const double pet = std::max(0.0, cell.temperature_c + 8.0) * 31.0;
        const double water_evaporation = (cell.water_body == 1 || cell.water_body == 2 || cell.water_body == 3) ?
            (760.0 + 28.0 * std::max(0.0, cell.temperature_c) + 90.0 * cell.ocean_current_moisture_factor) :
            0.0;
        const double land_evaporation = std::min(
            std::max(0.0, annual_precip) * clamp(0.38 + 0.22 * oceanity, 0.28, 0.72),
            pet * clamp(0.42 + 0.24 * cell.humidity_transport_index, 0.25, 0.86)
        );
        cell.vapor_evaporation_mm_y = clamp(cell.is_water ? water_evaporation : land_evaporation, 0.0, 2400.0);
        cell.precipitation_recycling_fraction = clamp(
            (cell.is_water ? 0.06 : 0.12) +
                0.34 * continentality +
                0.14 * clamp(cell.humidity_transport_index, 0.0, 1.0) +
                0.08 * clamp(cell.orographic_factor - 1.0, 0.0, 0.6),
            0.03,
            cell.is_water ? 0.22 : 0.68
        );
        const double recycled_source = std::min(
            annual_precip,
            cell.vapor_evaporation_mm_y * cell.precipitation_recycling_fraction
        );
        cell.moisture_convergence_mm_y = std::max(0.0, annual_precip - recycled_source);
        cell.orographic_rainout_mm_y = annual_precip * clamp(
            0.46 * std::max(0.0, cell.orographic_factor - 1.0) +
                0.18 * std::max(0.0, 1.0 - cell.rain_shadow_factor),
            0.0,
            0.55
        );
        cell.vapor_deficit_mm_y = std::max(0.0, pet - annual_precip);
        cell.vapor_budget_residual_mm_y = annual_precip - (recycled_source + cell.moisture_convergence_mm_y);
    }
}

double hydrologic_lithology_permeability(int lithology) {
    switch (lithology) {
        case 0: return 0.46;
        case 1: return 0.31;
        case 2: return 0.82;
        case 3: return 0.76;
        case 4: return 0.18;
        case 5: return 0.48;
        case 6: return 0.30;
        default: return 0.34;
    }
}

HydrologicWaterBudgetStage compute_hydrologic_water_budget(
    std::vector<Cell>& cells,
    int id,
    int feedback_stage_id,
    const std::string& stage_name,
    int erosion_iteration,
    int stabilization_recomputation_index
) {
    HydrologicWaterBudgetStage stage;
    stage.id = id;
    stage.feedback_stage_id = feedback_stage_id;
    stage.stage = stage_name;
    stage.erosion_iteration = erosion_iteration;
    stage.stabilization_recomputation_index =
        stabilization_recomputation_index;
    stage.cell_count = static_cast<int>(cells.size());

    const std::size_t cell_count = cells.size();
    stage.cell_ids.reserve(cell_count);
    stage.is_marine_by_cell.reserve(cell_count);
    stage.lithology_by_cell.reserve(cell_count);
    stage.cell_area_km2_by_cell.reserve(cell_count);
    stage.elevation_m_by_cell.reserve(cell_count);
    stage.temperature_c_by_cell.reserve(cell_count);
    stage.precipitation_mm_y_by_cell.reserve(cell_count);
    stage.local_relief_m_by_cell.reserve(cell_count);
    stage.sediment_thickness_m_by_cell.reserve(cell_count);
    stage.ice_thickness_m_by_cell.reserve(cell_count);
    stage.potential_evapotranspiration_mm_y_by_cell.reserve(cell_count);
    stage.infiltration_capacity_index_by_cell.reserve(cell_count);
    stage.actual_evapotranspiration_mm_y_by_cell.reserve(cell_count);
    stage.infiltration_mm_y_by_cell.reserve(cell_count);
    stage.water_balance_mm_y_by_cell.reserve(cell_count);
    stage.runoff_mm_y_by_cell.reserve(cell_count);
    stage.residual_mm_y_by_cell.reserve(cell_count);

    for (std::size_t index = 0; index < cell_count; ++index) {
        Cell& cell = cells[index];
        const bool is_marine = cell.is_water;
        const double area_km2 = std::max(0.0, cell.area_km2);
        const double precipitation_mm_y = std::max(
            0.0,
            cell.precipitation_mm_y
        );
        const double relief_m = local_relief(cells, static_cast<int>(index));

        double potential_evapotranspiration_mm_y = 0.0;
        double infiltration_capacity_index = 0.0;
        double actual_evapotranspiration_mm_y = 0.0;
        double infiltration_mm_y = 0.0;
        double water_balance_mm_y = 0.0;
        double runoff_mm_y = 0.0;
        double residual_mm_y = 0.0;

        if (!is_marine) {
            potential_evapotranspiration_mm_y = std::max(
                0.0,
                cell.temperature_c +
                    HYDROLOGIC_PET_TEMPERATURE_OFFSET_C
            ) * HYDROLOGIC_PET_SCALE_MM_Y_PER_C;
            const double permeability =
                hydrologic_lithology_permeability(cell.lithology);
            const double terrain_retention = 1.0 - clamp(
                relief_m / 2500.0,
                0.0,
                1.0
            );
            const double sediment_index = clamp(
                cell.sediment_thickness_m / 3.0,
                0.0,
                1.0
            );
            const double frozen_index = clamp(
                (-cell.temperature_c - 2.0) / 18.0,
                0.0,
                1.0
            );
            infiltration_capacity_index = clamp(
                0.62 * permeability +
                    0.16 * sediment_index +
                    0.12 * terrain_retention -
                    0.10 * frozen_index,
                HYDROLOGIC_MIN_INFILTRATION_CAPACITY,
                HYDROLOGIC_MAX_INFILTRATION_CAPACITY
            );
            const double climate_loss_mm_y = std::min(
                precipitation_mm_y,
                HYDROLOGIC_CLIMATE_LOSS_FRACTION *
                    potential_evapotranspiration_mm_y
            );
            const double infiltration_share = clamp(
                HYDROLOGIC_INFILTRATION_BASE_SHARE +
                    HYDROLOGIC_INFILTRATION_CAPACITY_SHARE *
                        infiltration_capacity_index,
                HYDROLOGIC_INFILTRATION_BASE_SHARE,
                HYDROLOGIC_INFILTRATION_BASE_SHARE +
                    HYDROLOGIC_INFILTRATION_CAPACITY_SHARE *
                        HYDROLOGIC_MAX_INFILTRATION_CAPACITY
            );
            infiltration_mm_y = climate_loss_mm_y * infiltration_share;
            actual_evapotranspiration_mm_y =
                climate_loss_mm_y - infiltration_mm_y;

            // Keep the calibrated loss envelope grouped so routing receives
            // the same residual while the causal source partition is explicit.
            water_balance_mm_y =
                precipitation_mm_y - climate_loss_mm_y;
            runoff_mm_y = std::max(0.0, water_balance_mm_y);
            residual_mm_y =
                precipitation_mm_y -
                actual_evapotranspiration_mm_y -
                infiltration_mm_y -
                runoff_mm_y;
        }

        cell.hydrologic_potential_evapotranspiration_mm_y =
            potential_evapotranspiration_mm_y;
        cell.actual_evapotranspiration_mm_y =
            actual_evapotranspiration_mm_y;
        cell.infiltration_capacity_index = infiltration_capacity_index;
        cell.infiltration_mm_y = infiltration_mm_y;
        cell.hydrologic_water_balance_mm_y = water_balance_mm_y;
        cell.water_budget_runoff_mm_y = runoff_mm_y;
        cell.runoff_mm_y = runoff_mm_y;
        cell.runoff_budget_residual_mm_y = residual_mm_y;
        cell.runoff_budget_consistency_index = clamp(
            1.0 - std::abs(residual_mm_y) /
                std::max(1.0, precipitation_mm_y),
            0.0,
            1.0
        );
        cell.hydrologic_deficit_mm_y = std::max(
            0.0,
            potential_evapotranspiration_mm_y -
                actual_evapotranspiration_mm_y
        );
        cell.runoff_generation_fraction = clamp(
            runoff_mm_y / std::max(1.0, precipitation_mm_y),
            0.0,
            1.0
        );

        stage.cell_ids.push_back(cell.id);
        stage.is_marine_by_cell.push_back(is_marine ? 1 : 0);
        stage.lithology_by_cell.push_back(cell.lithology);
        stage.cell_area_km2_by_cell.push_back(area_km2);
        stage.elevation_m_by_cell.push_back(cell.elevation_m);
        stage.temperature_c_by_cell.push_back(cell.temperature_c);
        stage.precipitation_mm_y_by_cell.push_back(precipitation_mm_y);
        stage.local_relief_m_by_cell.push_back(relief_m);
        stage.sediment_thickness_m_by_cell.push_back(
            cell.sediment_thickness_m
        );
        stage.ice_thickness_m_by_cell.push_back(cell.ice_thickness_m);
        stage.potential_evapotranspiration_mm_y_by_cell.push_back(
            potential_evapotranspiration_mm_y
        );
        stage.infiltration_capacity_index_by_cell.push_back(
            infiltration_capacity_index
        );
        stage.actual_evapotranspiration_mm_y_by_cell.push_back(
            actual_evapotranspiration_mm_y
        );
        stage.infiltration_mm_y_by_cell.push_back(infiltration_mm_y);
        stage.water_balance_mm_y_by_cell.push_back(water_balance_mm_y);
        stage.runoff_mm_y_by_cell.push_back(runoff_mm_y);
        stage.residual_mm_y_by_cell.push_back(residual_mm_y);

        if (is_marine) {
            stage.marine_cell_count++;
        } else {
            stage.land_cell_count++;
            stage.land_precipitation_volume_km3_y +=
                precipitation_mm_y * area_km2 * 1.0e-6;
            stage.actual_evapotranspiration_volume_km3_y +=
                actual_evapotranspiration_mm_y * area_km2 * 1.0e-6;
            stage.infiltration_volume_km3_y +=
                infiltration_mm_y * area_km2 * 1.0e-6;
            stage.runoff_volume_km3_y +=
                runoff_mm_y * area_km2 * 1.0e-6;
            stage.mass_balance_residual_km3_y +=
                residual_mm_y * area_km2 * 1.0e-6;
            stage.max_abs_cell_residual_mm_y = std::max(
                stage.max_abs_cell_residual_mm_y,
                std::abs(residual_mm_y)
            );
        }
    }
    return stage;
}

double neighbor_distance_m(const Params& params, const Cell& a, const Cell& b) {
    return std::max(1.0, angular_distance(a.p, b.p) * params.radius_km * 1000.0);
}

bool is_geologic_depression(const Cell& cell) {
    return cell.crust_type == 6 || cell.crust_type == 7 || cell.boundary_divergent > 0.28 || cell.boundary_convergent > 0.42;
}

struct FloodItem {
    double elevation = 0.0;
    int cell = -1;
};

struct FloodItemGreater {
    bool operator()(const FloodItem& a, const FloodItem& b) const {
        if (a.elevation == b.elevation) {
            return a.cell > b.cell;
        }
        return a.elevation > b.elevation;
    }
};

void compute_priority_flood_spill(std::vector<Cell>& cells) {
    const int n = static_cast<int>(cells.size());
    std::priority_queue<FloodItem, std::vector<FloodItem>, FloodItemGreater> queue;
    for (int i = 0; i < n; ++i) {
        cells[i].filled_elevation_m = std::numeric_limits<double>::infinity();
        cells[i].depression_depth_m = 0.0;
        cells[i].spill_to = -1;
        cells[i].is_closed_basin = false;
        if (cells[i].is_water) {
            cells[i].filled_elevation_m = 0.0;
            queue.push({0.0, i});
        }
    }

    if (queue.empty() && !cells.empty()) {
        int lowest = 0;
        for (int i = 1; i < n; ++i) {
            if (cells[i].elevation_m < cells[lowest].elevation_m) {
                lowest = i;
            }
        }
        cells[lowest].filled_elevation_m = cells[lowest].elevation_m;
        queue.push({cells[lowest].filled_elevation_m, lowest});
    }

    while (!queue.empty()) {
        const FloodItem item = queue.top();
        queue.pop();
        if (item.elevation > cells[item.cell].filled_elevation_m + 1.0e-9) {
            continue;
        }
        for (int neighbor : cells[item.cell].neighbors) {
            if (cells[neighbor].filled_elevation_m != std::numeric_limits<double>::infinity()) {
                continue;
            }
            const double filled = std::max(cells[neighbor].elevation_m, item.elevation);
            cells[neighbor].filled_elevation_m = filled;
            cells[neighbor].depression_depth_m = std::max(0.0, filled - cells[neighbor].elevation_m);
            cells[neighbor].spill_to = item.cell;
            queue.push({filled, neighbor});
        }
    }

    for (Cell& cell : cells) {
        if (!std::isfinite(cell.filled_elevation_m)) {
            cell.filled_elevation_m = cell.elevation_m;
            cell.depression_depth_m = 0.0;
            cell.spill_to = -1;
        }
    }
}

void assign_basin_ids(std::vector<Cell>& cells) {
    const int n = static_cast<int>(cells.size());
    for (Cell& cell : cells) {
        cell.basin_id = -1;
    }
    for (int i = 0; i < n; ++i) {
        if (cells[i].is_water) {
            cells[i].basin_id = i;
        }
    }
    for (int i = 0; i < n; ++i) {
        if (cells[i].basin_id >= 0) {
            continue;
        }
        std::vector<int> path;
        std::set<int> seen;
        int current = i;
        int basin = i;
        while (current >= 0 && current < n) {
            if (cells[current].basin_id >= 0) {
                basin = cells[current].basin_id;
                break;
            }
            if (!seen.insert(current).second) {
                basin = current;
                break;
            }
            path.push_back(current);
            if (cells[current].is_water ||
                (cells[current].is_lake && (cells[current].is_closed_basin || cells[current].flow_to < 0)) ||
                cells[current].flow_to < 0) {
                basin = current;
                break;
            }
            current = cells[current].flow_to;
        }
        for (int cell_id : path) {
            cells[cell_id].basin_id = basin;
        }
    }
}

void condition_hydrologic_surface(
    const Params& params,
    std::vector<Cell>& cells,
    const std::vector<int>& flow_order
) {
    for (Cell& cell : cells) {
        cell.hydrologic_surface_elevation_m = cell.filled_elevation_m;
        cell.hydrologic_flow_drop_m = 0.0;
        cell.hydrologic_flow_slope = 0.0;
        cell.hydrologic_surface_conditioned = false;
    }

    for (auto it = flow_order.rbegin(); it != flow_order.rend(); ++it) {
        Cell& cell = cells[static_cast<std::size_t>(*it)];
        if (cell.flow_to < 0) {
            continue;
        }
        Cell& receiver = cells[static_cast<std::size_t>(cell.flow_to)];
        if (cell.filled_elevation_m + 1.0e-9 < receiver.filled_elevation_m) {
            throw std::runtime_error("Priority-Flood routing surface rises downstream");
        }
        cell.hydrologic_surface_elevation_m = std::max(
            cell.filled_elevation_m,
            receiver.hydrologic_surface_elevation_m + HYDROLOGIC_FLAT_GRADIENT_STEP_M
        );
    }

    for (Cell& cell : cells) {
        cell.hydrologic_surface_conditioned =
            cell.hydrologic_surface_elevation_m > cell.filled_elevation_m + 1.0e-12;
        if (cell.flow_to < 0) {
            continue;
        }
        const Cell& receiver = cells[static_cast<std::size_t>(cell.flow_to)];
        cell.hydrologic_flow_drop_m =
            cell.hydrologic_surface_elevation_m - receiver.hydrologic_surface_elevation_m;
        if (cell.hydrologic_flow_drop_m <= 0.0) {
            throw std::runtime_error("conditioned hydrologic surface is not downhill");
        }
        cell.hydrologic_flow_slope = cell.hydrologic_flow_drop_m /
            neighbor_distance_m(params, cell, receiver);
    }
}

void compute_flow_and_rivers(const Params& params, std::vector<Cell>& cells) {
    const int n = static_cast<int>(cells.size());
    compute_priority_flood_spill(cells);
    std::vector<int> raw_flow_to(static_cast<std::size_t>(n), -1);
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        Cell& cell = cells[i];
        cell.is_river = false;
        cell.is_lake = false;
        cell.flow_to = -1;
        cell.equal_filled_raw_downhill_rerouted = false;
        cell.flow_accumulation = 0.0;
        cell.basin_id = -1;
        cell.depression_component_id = -1;
        cell.depression_sink_cell_id = -1;
        cell.lake_basin_id = -1;
        cell.depression_policy = 0;
        cell.spill_elevation_m = std::isfinite(cell.filled_elevation_m) ? cell.filled_elevation_m : cell.elevation_m;
        cell.lake_fill_fraction = 0.0;
        cell.is_closed_basin = false;
        cell.lake_overflows = false;
        if (cell.is_water) {
            continue;
        }
        cell.water_body = 0;
        cell.flow_accumulation = cell.runoff_mm_y * cell.area_km2;
        double best_raw_drop = 0.0;
        int raw_best = -1;
        for (int j : cell.neighbors) {
            const double raw_drop = cell.elevation_m - cells[j].elevation_m;
            if (
                raw_drop > 1.0e-9 &&
                (raw_drop > best_raw_drop + 1.0e-9 ||
                    (std::abs(raw_drop - best_raw_drop) <= 1.0e-9 && (raw_best < 0 || j < raw_best)))
            ) {
                best_raw_drop = raw_drop;
                raw_best = j;
            }
        }
        raw_flow_to[static_cast<std::size_t>(i)] = raw_best;

        const double current_surface = std::isfinite(cell.filled_elevation_m) ?
            cell.filled_elevation_m : cell.elevation_m;
        double best_drop = 0.0;
        best_raw_drop = -std::numeric_limits<double>::infinity();
        int best = -1;
        for (int j : cell.neighbors) {
            const double neighbor_surface = std::isfinite(cells[j].filled_elevation_m) ?
                cells[j].filled_elevation_m : cells[j].elevation_m;
            const double drop = current_surface - neighbor_surface;
            const double raw_drop = cell.elevation_m - cells[j].elevation_m;
            if (
                drop > 1.0e-9 &&
                (drop > best_drop + 1.0e-9 ||
                    (std::abs(drop - best_drop) <= 1.0e-9 &&
                        (raw_drop > best_raw_drop + 1.0e-9 ||
                            (std::abs(raw_drop - best_raw_drop) <= 1.0e-9 && (best < 0 || j < best)))))
            ) {
                best_drop = drop;
                best_raw_drop = raw_drop;
                best = j;
            }
        }
        if (best < 0 && cell.spill_to >= 0 && cell.spill_to != i) {
            best = cell.spill_to;
            const Cell& receiver = cells[static_cast<std::size_t>(best)];
            cell.equal_filled_raw_downhill_rerouted =
                std::abs(cell.filled_elevation_m - receiver.filled_elevation_m) <= 1.0e-9 &&
                cell.elevation_m - receiver.elevation_m > 1.0e-9;
        }
        cell.flow_to = best;
        cell.water_depth_m = 0.0;
    }

    // Label each raw-downhill drainage tree by its terminal cell. A terminal
    // with Priority-Flood depth is one model depression unit, even when it
    // shares a final fill elevation with neighboring sinks.
    std::vector<int> raw_sink_by_cell(static_cast<std::size_t>(n), -2);
    for (int i = 0; i < n; ++i) {
        if (cells[static_cast<std::size_t>(i)].is_water) {
            raw_sink_by_cell[static_cast<std::size_t>(i)] = -1;
        }
    }
    for (int i = 0; i < n; ++i) {
        if (raw_sink_by_cell[static_cast<std::size_t>(i)] != -2) {
            continue;
        }
        std::vector<int> path;
        int current = i;
        int sink = -3;
        for (int step = 0; step <= n; ++step) {
            if (current < 0) {
                sink = path.empty() ? i : path.back();
                break;
            }
            if (current >= n) {
                throw std::runtime_error("raw hydrology receiver is invalid");
            }
            const int known_sink = raw_sink_by_cell[static_cast<std::size_t>(current)];
            if (known_sink != -2) {
                sink = known_sink;
                break;
            }
            path.push_back(current);
            const int next = raw_flow_to[static_cast<std::size_t>(current)];
            if (next < 0) {
                sink = current;
                break;
            }
            current = next;
        }
        if (sink == -3) {
            throw std::runtime_error("raw hydrology drainage labeling did not terminate");
        }
        for (int cell_id : path) {
            raw_sink_by_cell[static_cast<std::size_t>(cell_id)] = sink;
        }
    }

    std::map<int, std::vector<int>> depression_cells_by_sink;
    for (int i = 0; i < n; ++i) {
        const Cell& cell = cells[static_cast<std::size_t>(i)];
        const int sink = raw_sink_by_cell[static_cast<std::size_t>(i)];
        if (!cell.is_water && cell.depression_depth_m > 1.0e-9 && sink >= 0) {
            depression_cells_by_sink[sink].push_back(i);
        }
    }

    int depression_component_id = 0;
    for (const auto& [sink_id, depression_cell_ids] : depression_cells_by_sink) {
        if (sink_id < 0 || sink_id >= n || depression_cell_ids.empty()) {
            throw std::runtime_error("hydrology depression unit is invalid");
        }
        Cell& sink_cell = cells[static_cast<std::size_t>(sink_id)];
        double area_km2 = 0.0;
        double runoff_area_sum = 0.0;
        double precipitation_area_sum = 0.0;
        double pet_area_sum = 0.0;
        double max_depression_depth_m = 0.0;
        for (int cell_id : depression_cell_ids) {
            Cell& cell = cells[static_cast<std::size_t>(cell_id)];
            cell.depression_component_id = depression_component_id;
            cell.depression_sink_cell_id = sink_id;
            area_km2 += cell.area_km2;
            runoff_area_sum += cell.runoff_mm_y * cell.area_km2;
            precipitation_area_sum += cell.precipitation_mm_y * cell.area_km2;
            pet_area_sum +=
                cell.hydrologic_potential_evapotranspiration_mm_y *
                cell.area_km2;
            max_depression_depth_m = std::max(max_depression_depth_m, cell.depression_depth_m);
        }
        if (area_km2 <= 0.0) {
            throw std::runtime_error("hydrology depression unit has no area");
        }
        const double mean_runoff_mm_y = runoff_area_sum / area_km2;
        const double mean_precipitation_mm_y = precipitation_area_sum / area_km2;
        const double mean_pet_mm_y = pet_area_sum / area_km2;
        const double aridity = mean_precipitation_mm_y / std::max(1.0, mean_pet_mm_y);
        const double fill_fraction = clamp(
            (mean_runoff_mm_y / 220.0) * clamp(aridity, 0.08, 2.5) /
                (1.0 + max_depression_depth_m / 120.0),
            0.0,
            1.5
        );

        std::vector<int> spill_path;
        int spill_destination = -1;
        int current = sink_id;
        for (int step = 0; step <= n; ++step) {
            if (current < 0 || current >= n ||
                raw_sink_by_cell[static_cast<std::size_t>(current)] != sink_id) {
                break;
            }
            spill_path.push_back(current);
            const int next = cells[static_cast<std::size_t>(current)].spill_to;
            if (next < 0 || next >= n) {
                break;
            }
            if (cells[static_cast<std::size_t>(next)].is_water ||
                raw_sink_by_cell[static_cast<std::size_t>(next)] != sink_id) {
                spill_destination = next;
                break;
            }
            current = next;
        }

        const bool geologic_depression =
            params.preserve_geologic_depressions && is_geologic_depression(sink_cell);
        const bool wet_geologic_depression = geologic_depression && mean_runoff_mm_y > 25.0;
        const bool temporary_numeric_depression =
            !geologic_depression &&
            std::any_of(
                depression_cell_ids.begin(),
                depression_cell_ids.end(),
                [&cells](int cell_id) {
                    return cells[static_cast<std::size_t>(cell_id)]
                        .numeric_depression_temporary_lake_deferred;
                }
            );
        const bool wet_temporary_numeric_depression =
            temporary_numeric_depression && mean_runoff_mm_y > 25.0;
        const bool geologic_overflows =
            wet_geologic_depression && spill_destination >= 0 && fill_fraction >= 1.0;
        const bool temporary_numeric_lake_overflows =
            wet_temporary_numeric_depression &&
            spill_destination >= 0 && fill_fraction >= 1.0;
        const bool overflows =
            geologic_overflows || temporary_numeric_lake_overflows;
        int policy = 0;
        if (geologic_overflows) {
            policy = 3;
        } else if (wet_geologic_depression) {
            policy = 2;
        } else if (geologic_depression) {
            policy = 4;
        } else if (temporary_numeric_depression) {
            policy = 5;
        } else if (spill_destination >= 0) {
            policy = 1;
        } else {
            policy = 4;
        }

        for (int cell_id : depression_cell_ids) {
            Cell& cell = cells[static_cast<std::size_t>(cell_id)];
            cell.depression_policy = policy;
            cell.lake_fill_fraction = fill_fraction;
            cell.is_closed_basin = false;
            cell.lake_overflows = false;
            cell.is_lake = false;
            cell.water_body = 0;
            cell.water_depth_m = 0.0;
        }

        if (policy == 1 || policy == 3 ||
            (policy == 5 && temporary_numeric_lake_overflows)) {
            if (spill_destination < 0 || spill_path.empty()) {
                throw std::runtime_error("open depression unit has no spill corridor");
            }
            for (int path_cell_id : spill_path) {
                Cell& path_cell = cells[static_cast<std::size_t>(path_cell_id)];
                if (path_cell.spill_to < 0 || path_cell.spill_to >= n) {
                    throw std::runtime_error("depression spill corridor is invalid");
                }
                path_cell.flow_to = path_cell.spill_to;
            }
        } else {
            for (int cell_id : depression_cell_ids) {
                Cell& cell = cells[static_cast<std::size_t>(cell_id)];
                const int raw_receiver = raw_flow_to[static_cast<std::size_t>(cell_id)];
                if (cell_id != sink_id &&
                    (raw_receiver < 0 || raw_receiver >= n ||
                        raw_sink_by_cell[static_cast<std::size_t>(raw_receiver)] != sink_id ||
                        cells[static_cast<std::size_t>(raw_receiver)].depression_depth_m <= 1.0e-9)) {
                    throw std::runtime_error("closed depression raw routing leaves its footprint");
                }
                cell.flow_to = raw_receiver;
                cell.equal_filled_raw_downhill_rerouted = false;
            }
            sink_cell.flow_to = -1;
            sink_cell.is_closed_basin = true;
        }

        if (wet_geologic_depression || wet_temporary_numeric_depression) {
            const int water_body = aridity < 0.5 ? 5 : 4;
            const double water_surface_m = sink_cell.elevation_m +
                std::min(1.0, fill_fraction) *
                    std::max(0.0, sink_cell.spill_elevation_m - sink_cell.elevation_m);
            for (int cell_id : depression_cell_ids) {
                Cell& cell = cells[static_cast<std::size_t>(cell_id)];
                const double depth_m = std::max(0.0, water_surface_m - cell.elevation_m);
                if (depth_m > 1.0e-9) {
                    cell.is_lake = true;
                    cell.water_body = overflows ? 4 : water_body;
                    cell.water_depth_m = clamp(depth_m, 0.2, 240.0);
                }
            }
            sink_cell.is_lake = true;
            sink_cell.water_body = overflows ? 4 : water_body;
            sink_cell.water_depth_m = clamp(
                std::max(0.2, water_surface_m - sink_cell.elevation_m),
                0.2,
                240.0
            );
            sink_cell.lake_overflows = overflows;
        } else if (geologic_depression && aridity < 0.55) {
            sink_cell.water_body = 5;
        }
        depression_component_id++;
    }

    std::vector<int> upstream_count(static_cast<std::size_t>(n), 0);
    for (int i = 0; i < n; ++i) {
        const int to = cells[static_cast<std::size_t>(i)].flow_to;
        if (to >= 0) {
            if (to >= n || to == i) {
                throw std::runtime_error("hydrology flow receiver is invalid");
            }
            upstream_count[static_cast<std::size_t>(to)]++;
        }
    }
    std::priority_queue<int, std::vector<int>, std::greater<int>> ready;
    for (int i = 0; i < n; ++i) {
        if (upstream_count[static_cast<std::size_t>(i)] == 0) {
            ready.push(i);
        }
    }
    int processed_flow_cells = 0;
    std::vector<int> flow_order;
    flow_order.reserve(static_cast<std::size_t>(n));
    while (!ready.empty()) {
        const int current = ready.top();
        ready.pop();
        processed_flow_cells++;
        flow_order.push_back(current);
        const int to = cells[static_cast<std::size_t>(current)].flow_to;
        if (to < 0) {
            continue;
        }
        if (!cells[static_cast<std::size_t>(current)].is_water) {
            cells[static_cast<std::size_t>(to)].flow_accumulation +=
                cells[static_cast<std::size_t>(current)].flow_accumulation;
        }
        int& remaining = upstream_count[static_cast<std::size_t>(to)];
        remaining--;
        if (remaining == 0) {
            ready.push(to);
        }
    }
    if (processed_flow_cells != n) {
        throw std::runtime_error("hydrology flow graph contains a cycle");
    }
    condition_hydrologic_surface(params, cells, flow_order);
    std::vector<double> accum;
    for (const Cell& cell : cells) {
        if (!cell.is_water && cell.flow_accumulation > 0.0) {
            accum.push_back(cell.flow_accumulation);
        }
    }
    if (accum.empty()) {
        return;
    }
    std::sort(accum.begin(), accum.end());
    const auto idx = static_cast<std::size_t>(clamp(params.river_percentile, 0.5, 0.999) * static_cast<double>(accum.size() - 1));
    const double threshold = std::max(1.0, accum[idx]);
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        if (cells[i].is_water || cells[i].flow_to < 0) {
            continue;
        }
        cells[i].is_river = cells[i].flow_accumulation >= threshold &&
            cells[i].hydrologic_flow_slope > 0.0 && cells[i].runoff_mm_y > 10.0;
    }
    assign_basin_ids(cells);
}

void derive_numeric_depression_breach_alternative(
    const Params& params,
    const std::vector<Cell>& cells,
    const std::vector<double>& elevation_before_correction_m,
    const std::vector<int>& source_component_cell_ids,
    NumericDepressionFillEvent& event
) {
    if (event.sink_cell_id < 0 ||
        event.sink_cell_id >= static_cast<int>(cells.size()) ||
        elevation_before_correction_m.size() != cells.size()) {
        throw std::runtime_error("numeric depression breach diagnostic input is invalid");
    }

    const int n = static_cast<int>(cells.size());
    const std::set<int> source_cells(
        source_component_cell_ids.begin(),
        source_component_cell_ids.end()
    );
    const double sink_elevation_m = elevation_before_correction_m[
        static_cast<std::size_t>(event.sink_cell_id)
    ];
    std::vector<double> best_cost_km3(
        static_cast<std::size_t>(n),
        std::numeric_limits<double>::infinity()
    );
    std::vector<int> parent(static_cast<std::size_t>(n), -1);
    std::vector<int> hop_count(static_cast<std::size_t>(n), 0);
    std::priority_queue<
        std::pair<double, int>,
        std::vector<std::pair<double, int>>,
        std::greater<std::pair<double, int>>
    > queue;
    best_cost_km3[static_cast<std::size_t>(event.sink_cell_id)] = 0.0;
    queue.push({0.0, event.sink_cell_id});

    int outlet_cell_id = -1;
    while (!queue.empty()) {
        const auto [cost_km3, current] = queue.top();
        queue.pop();
        if (cost_km3 > best_cost_km3[static_cast<std::size_t>(current)] + 1.0e-12) {
            continue;
        }
        const int current_hops = hop_count[static_cast<std::size_t>(current)];
        const double current_elevation_m =
            elevation_before_correction_m[static_cast<std::size_t>(current)];
        if (current != event.sink_cell_id &&
            source_cells.count(current) == 0 &&
            current_elevation_m <= sink_elevation_m -
                NUMERIC_DEPRESSION_BREACH_GRADIENT_STEP_M * current_hops) {
            outlet_cell_id = current;
            break;
        }

        for (int next : cells[static_cast<std::size_t>(current)].neighbors) {
            if (next < 0 || next >= n || next == current) {
                throw std::runtime_error("numeric depression breach graph is invalid");
            }
            const int next_hops = current_hops + 1;
            const double required_upper_m = sink_elevation_m -
                NUMERIC_DEPRESSION_BREACH_GRADIENT_STEP_M * next_hops;
            const double next_elevation_m =
                elevation_before_correction_m[static_cast<std::size_t>(next)];
            const bool outside_source = source_cells.count(next) == 0;
            const bool naturally_lower_outlet =
                outside_source && next_elevation_m <= required_upper_m;
            const bool enters_other_depression =
                outside_source &&
                cells[static_cast<std::size_t>(next)].depression_component_id >= 0 &&
                cells[static_cast<std::size_t>(next)].depression_component_id !=
                    event.source_depression_component_id;
            if (!naturally_lower_outlet &&
                (cells[static_cast<std::size_t>(next)].is_water ||
                    enters_other_depression)) {
                continue;
            }

            const double excavation_depth_m = naturally_lower_outlet ?
                0.0 : std::max(0.0, next_elevation_m - required_upper_m);
            const double candidate_cost_km3 = cost_km3 +
                excavation_depth_m *
                    cells[static_cast<std::size_t>(next)].area_km2 / 1000.0;
            double& best_next_cost_km3 =
                best_cost_km3[static_cast<std::size_t>(next)];
            const int previous_parent = parent[static_cast<std::size_t>(next)];
            if (candidate_cost_km3 < best_next_cost_km3 - 1.0e-9 ||
                (std::abs(candidate_cost_km3 - best_next_cost_km3) <= 1.0e-9 &&
                    (previous_parent < 0 || current < previous_parent))) {
                best_next_cost_km3 = candidate_cost_km3;
                parent[static_cast<std::size_t>(next)] = current;
                hop_count[static_cast<std::size_t>(next)] = next_hops;
                queue.push({candidate_cost_km3, next});
            }
        }
    }

    if (outlet_cell_id >= 0) {
        std::vector<int> reverse_path;
        int current = outlet_cell_id;
        for (int step = 0; step <= n; ++step) {
            reverse_path.push_back(current);
            if (current == event.sink_cell_id) {
                break;
            }
            current = parent[static_cast<std::size_t>(current)];
            if (current < 0 || current >= n) {
                reverse_path.clear();
                break;
            }
        }
        if (!reverse_path.empty() &&
            reverse_path.back() == event.sink_cell_id) {
            event.breach_path_cell_ids.assign(
                reverse_path.rbegin(),
                reverse_path.rend()
            );
            event.breach_feasible = true;
            event.breach_outlet_cell_id = outlet_cell_id;
        }
    }

    double current_target_m = sink_elevation_m;
    for (std::size_t index = 0; index < event.breach_path_cell_ids.size(); ++index) {
        const int cell_id = event.breach_path_cell_ids[index];
        const double before_m =
            elevation_before_correction_m[static_cast<std::size_t>(cell_id)];
        double target_m = before_m;
        if (index == 0) {
            target_m = sink_elevation_m;
        } else if (cell_id != outlet_cell_id) {
            target_m = std::min(
                before_m,
                current_target_m - NUMERIC_DEPRESSION_BREACH_GRADIENT_STEP_M
            );
        }
        const double excavation_depth_m = std::max(0.0, before_m - target_m);
        event.breach_elevation_before_m_by_cell.push_back(before_m);
        event.breach_target_elevation_m_by_cell.push_back(target_m);
        event.breach_excavation_depth_m_by_cell.push_back(excavation_depth_m);
        event.breach_sediment_thickness_before_excavation_m_by_cell.push_back(
            cells[static_cast<std::size_t>(cell_id)].sediment_thickness_m
        );
        event.breach_alluvium_entrainment_depth_m_by_cell.push_back(0.0);
        event.breach_bedrock_erosion_depth_m_by_cell.push_back(0.0);
        if (index > 0) {
            event.breach_path_length_km += neighbor_distance_m(
                params,
                cells[static_cast<std::size_t>(event.breach_path_cell_ids[index - 1])],
                cells[static_cast<std::size_t>(cell_id)]
            ) / 1000.0;
        }
        if (excavation_depth_m > NUMERIC_DEPRESSION_FILL_DEPTH_TOLERANCE_M) {
            const Cell& path_cell = cells[static_cast<std::size_t>(cell_id)];
            event.breach_excavation_area_km2 += path_cell.area_km2;
            event.breach_excavation_volume_km3 +=
                excavation_depth_m * path_cell.area_km2 / 1000.0;
            event.max_breach_excavation_depth_m = std::max(
                event.max_breach_excavation_depth_m,
                excavation_depth_m
            );
        }
        current_target_m = target_m;
    }

    event.breach_to_fill_volume_ratio = event.fill_volume_km3 > 0.0 ?
        event.breach_excavation_volume_km3 / event.fill_volume_km3 :
        std::numeric_limits<double>::infinity();
    event.breach_has_lower_adjustment_volume =
        event.breach_feasible &&
        event.breach_excavation_volume_km3 + 1.0e-9 < event.fill_volume_km3;
}

void apply_numeric_depression_correction(
    std::vector<Cell>& cells,
    NumericDepressionFillEvent& event,
    std::set<int>& mutated_cell_ids_this_pass
) {
    std::set<int> excavated_path_cell_ids;
    for (std::size_t index = 0;
         index < event.breach_path_cell_ids.size();
         ++index) {
        if (event.breach_excavation_depth_m_by_cell[index] >
            NUMERIC_DEPRESSION_FILL_DEPTH_TOLERANCE_M) {
            excavated_path_cell_ids.insert(event.breach_path_cell_ids[index]);
        }
    }

    std::vector<std::size_t> deposition_candidate_indices;
    for (std::size_t index = 0; index < event.cell_ids.size(); ++index) {
        const int cell_id = event.cell_ids[index];
        if (excavated_path_cell_ids.count(cell_id) != 0) {
            continue;
        }
        const double capacity_depth_m = event.fill_depth_m_by_cell[index];
        const Cell& cell = cells[static_cast<std::size_t>(cell_id)];
        const double sediment_capacity_depth_m = std::max(
            0.0,
            5000.0 -
                event.sediment_thickness_before_correction_m_by_cell[index]
        );
        const double usable_depth_m = std::min(
            capacity_depth_m,
            sediment_capacity_depth_m
        );
        if (usable_depth_m <= NUMERIC_DEPRESSION_FILL_DEPTH_TOLERANCE_M) {
            continue;
        }
        deposition_candidate_indices.push_back(index);
        event.breach_deposition_capacity_km3 +=
            usable_depth_m * cell.area_km2 / 1000.0;
    }

    event.breach_depth_bound_passed =
        event.breach_feasible &&
        event.max_breach_excavation_depth_m <=
            NUMERIC_DEPRESSION_SELECTED_BREACH_MAX_DEPTH_M +
                NUMERIC_DEPRESSION_FILL_DEPTH_TOLERANCE_M;
    event.breach_deposition_capacity_sufficient =
        event.breach_feasible &&
        event.breach_deposition_capacity_km3 + 1.0e-9 >=
            event.breach_excavation_volume_km3;
    event.breach_same_pass_conflict_free = event.breach_feasible;
    for (int cell_id : excavated_path_cell_ids) {
        if (mutated_cell_ids_this_pass.count(cell_id) != 0) {
            event.breach_same_pass_conflict_free = false;
            break;
        }
    }
    if (event.breach_same_pass_conflict_free) {
        for (std::size_t index : deposition_candidate_indices) {
            if (mutated_cell_ids_this_pass.count(event.cell_ids[index]) != 0) {
                event.breach_same_pass_conflict_free = false;
                break;
            }
        }
    }

    event.breach_selected =
        event.breach_has_lower_adjustment_volume &&
        event.breach_depth_bound_passed &&
        event.breach_deposition_capacity_sufficient &&
        event.breach_same_pass_conflict_free;
    event.temporary_numeric_lake_selected = !event.breach_selected;

    if (!event.breach_selected) {
        for (std::size_t index = 0; index < event.cell_ids.size(); ++index) {
            const int cell_id = event.cell_ids[index];
            Cell& cell = cells[static_cast<std::size_t>(cell_id)];
            const double before_fill_m = event.elevation_before_fill_m_by_cell[index];
            if (std::abs(cell.elevation_m - before_fill_m) > 1.0e-7) {
                throw std::runtime_error(
                    "numeric depression deferral conflicts with an earlier correction"
                );
            }
            cell.numeric_depression_temporary_lake_deferred = true;
            cell.numeric_depression_temporary_lake_event_count++;
        }
        event.applied_fill_volume_km3 = 0.0;
        event.correction_mass_balance_residual_km3 = 0.0;
        return;
    }

    for (std::size_t index = 0;
         index < event.breach_path_cell_ids.size();
         ++index) {
        const double excavation_depth_m =
            event.breach_excavation_depth_m_by_cell[index];
        if (excavation_depth_m <= NUMERIC_DEPRESSION_FILL_DEPTH_TOLERANCE_M) {
            continue;
        }
        const int cell_id = event.breach_path_cell_ids[index];
        Cell& cell = cells[static_cast<std::size_t>(cell_id)];
        const double before_m = event.breach_elevation_before_m_by_cell[index];
        if (std::abs(cell.elevation_m - before_m) > 1.0e-7) {
            throw std::runtime_error(
                "numeric depression breach conflicts with an earlier correction"
            );
        }
        cell.elevation_m = event.breach_target_elevation_m_by_cell[index];
        const double sediment_thickness_before_m = cell.sediment_thickness_m;
        const double alluvium_entrainment_depth_m = std::min(
            sediment_thickness_before_m,
            excavation_depth_m
        );
        const double bedrock_erosion_depth_m = std::max(
            0.0,
            excavation_depth_m - alluvium_entrainment_depth_m
        );
        event.breach_alluvium_entrainment_depth_m_by_cell[index] =
            alluvium_entrainment_depth_m;
        event.breach_bedrock_erosion_depth_m_by_cell[index] =
            bedrock_erosion_depth_m;
        cell.sediment_thickness_m =
            sediment_thickness_before_m - alluvium_entrainment_depth_m;
        cell.sediment_production_m += excavation_depth_m;
        cell.sediment_alluvium_entrainment_m +=
            alluvium_entrainment_depth_m;
        cell.sediment_bedrock_erosion_m += bedrock_erosion_depth_m;
        cell.sediment_net_budget_m =
            cell.sediment_deposition_m - cell.sediment_production_m;
        cell.cumulative_numeric_depression_breach_excavation_m +=
            excavation_depth_m;
        cell.numeric_depression_breach_event_count++;
        event.applied_breach_excavation_volume_km3 +=
            excavation_depth_m * cell.area_km2 / 1000.0;
        event.applied_alluvium_entrainment_volume_km3 +=
            alluvium_entrainment_depth_m * cell.area_km2 / 1000.0;
        event.applied_bedrock_erosion_volume_km3 +=
            bedrock_erosion_depth_m * cell.area_km2 / 1000.0;
        mutated_cell_ids_this_pass.insert(cell_id);
    }

    double remaining_deposition_volume_km3 =
        event.applied_breach_excavation_volume_km3;
    for (std::size_t candidate_position = 0;
         candidate_position < deposition_candidate_indices.size();
         ++candidate_position) {
        const std::size_t event_index =
            deposition_candidate_indices[candidate_position];
        const int cell_id = event.cell_ids[event_index];
        Cell& cell = cells[static_cast<std::size_t>(cell_id)];
        const double capacity_depth_m = std::min(
            event.fill_depth_m_by_cell[event_index],
            std::max(0.0, 5000.0 - cell.sediment_thickness_m)
        );
        const double capacity_volume_km3 =
            capacity_depth_m * cell.area_km2 / 1000.0;
        const double proportional_volume_km3 =
            event.breach_deposition_capacity_km3 > 0.0 ?
                event.applied_breach_excavation_volume_km3 *
                    capacity_volume_km3 /
                    event.breach_deposition_capacity_km3 :
                0.0;
        const bool last_candidate =
            candidate_position + 1 == deposition_candidate_indices.size();
        const double deposition_volume_km3 = std::min(
            capacity_volume_km3,
            last_candidate ? remaining_deposition_volume_km3 :
                std::min(remaining_deposition_volume_km3, proportional_volume_km3)
        );
        if (deposition_volume_km3 <= 1.0e-12) {
            continue;
        }
        const double deposition_depth_m =
            deposition_volume_km3 * 1000.0 / cell.area_km2;
        cell.elevation_m += deposition_depth_m;
        cell.sediment_thickness_m += deposition_depth_m;
        cell.sediment_deposition_m += deposition_depth_m;
        cell.sediment_net_budget_m =
            cell.sediment_deposition_m - cell.sediment_production_m;
        cell.cumulative_numeric_depression_breach_deposition_m +=
            deposition_depth_m;
        cell.numeric_depression_breach_event_count++;
        event.breach_deposition_cell_ids.push_back(cell_id);
        event.breach_deposition_depth_m_by_cell.push_back(deposition_depth_m);
        event.applied_breach_deposition_volume_km3 += deposition_volume_km3;
        remaining_deposition_volume_km3 = std::max(
            0.0,
            remaining_deposition_volume_km3 - deposition_volume_km3
        );
        mutated_cell_ids_this_pass.insert(cell_id);
    }
    if (remaining_deposition_volume_km3 > 1.0e-7) {
        throw std::runtime_error(
            "numeric depression breach deposition capacity was not realized"
        );
    }
    event.correction_mass_balance_residual_km3 = std::abs(
        event.applied_breach_excavation_volume_km3 -
            event.applied_breach_deposition_volume_km3
    );
}

HydrologyStabilizationResult stabilize_numeric_depressions(
    const Params& params,
    std::vector<Cell>& cells,
    int feedback_stage_id,
    const std::string& stage,
    int erosion_iteration,
    std::vector<NumericDepressionFillEvent>& fill_history,
    std::vector<HydrologicWaterBudgetStage>& water_budget_history
) {
    HydrologyStabilizationResult result;
    std::set<int> filled_unique_cell_ids;
    std::set<int> temporary_lake_unique_cell_ids;
    for (Cell& cell : cells) {
        cell.numeric_depression_temporary_lake_deferred = false;
    }

    for (int recomputation_index = 0;
         recomputation_index <= NUMERIC_DEPRESSION_FILL_MAX_PASSES;
         ++recomputation_index) {
        result.sea_level_adjustment_m += apply_sea_level(params, cells);
        result.sea_level_recompute_count++;
        label_marine_water_bodies(cells);
        compute_climate(params, cells);
        result.climate_recompute_count++;
        water_budget_history.push_back(compute_hydrologic_water_budget(
            cells,
            static_cast<int>(water_budget_history.size()),
            feedback_stage_id,
            stage,
            erosion_iteration,
            recomputation_index
        ));
        result.hydrologic_water_budget_recompute_count++;
        compute_flow_and_rivers(params, cells);
        result.hydrology_recompute_count++;

        std::map<int, std::vector<int>> cells_by_component;
        for (const Cell& cell : cells) {
            if (!cell.is_water && cell.depression_policy == 1) {
                if (cell.depression_component_id < 0 ||
                    cell.depression_sink_cell_id < 0 ||
                    cell.depression_depth_m <= NUMERIC_DEPRESSION_FILL_DEPTH_TOLERANCE_M) {
                    throw std::runtime_error("numeric depression correction candidate is invalid");
                }
                cells_by_component[cell.depression_component_id].push_back(cell.id);
            }
        }
        if (cells_by_component.empty()) {
            result.numeric_depression_filled_unique_cell_count =
                static_cast<int>(filled_unique_cell_ids.size());
            result.numeric_depression_temporary_lake_unique_cell_count =
                static_cast<int>(temporary_lake_unique_cell_ids.size());
            return result;
        }
        if (recomputation_index == NUMERIC_DEPRESSION_FILL_MAX_PASSES) {
            throw std::runtime_error("numeric depression fill did not converge within the bounded pass count");
        }

        result.numeric_depression_fill_pass_count++;
        const int stabilization_pass = result.numeric_depression_fill_pass_count;
        std::vector<double> elevation_before_correction_m;
        elevation_before_correction_m.reserve(cells.size());
        for (const Cell& cell : cells) {
            elevation_before_correction_m.push_back(cell.elevation_m);
        }
        std::set<int> mutated_cell_ids_this_pass;
        for (const auto& [component_id, cell_ids] : cells_by_component) {
            if (cell_ids.empty()) {
                throw std::runtime_error("numeric depression correction component is empty");
            }
            const Cell& first_cell = cells[static_cast<std::size_t>(cell_ids.front())];
            const int sink_cell_id = first_cell.depression_sink_cell_id;
            if (sink_cell_id < 0 || sink_cell_id >= static_cast<int>(cells.size())) {
                throw std::runtime_error("numeric depression correction sink is invalid");
            }
            const Cell& sink = cells[static_cast<std::size_t>(sink_cell_id)];

            NumericDepressionFillEvent event;
            event.id = static_cast<int>(fill_history.size());
            event.feedback_stage_id = feedback_stage_id;
            event.stage = stage;
            event.erosion_iteration = erosion_iteration;
            event.stabilization_pass = stabilization_pass;
            event.source_depression_component_id = component_id;
            event.sink_cell_id = sink_cell_id;
            event.sink_crust_type = sink.crust_type;
            event.sink_is_geologic = is_geologic_depression(sink);
            event.sink_boundary_divergent = sink.boundary_divergent;
            event.sink_boundary_convergent = sink.boundary_convergent;
            event.cell_ids.reserve(cell_ids.size());
            event.elevation_before_fill_m_by_cell.reserve(cell_ids.size());
            event.sediment_thickness_before_correction_m_by_cell.reserve(
                cell_ids.size()
            );
            event.fill_depth_m_by_cell.reserve(cell_ids.size());
            event.elevation_after_fill_m_by_cell.reserve(cell_ids.size());

            for (int cell_id : cell_ids) {
                const Cell& cell = cells[static_cast<std::size_t>(cell_id)];
                if (cell.depression_component_id != component_id ||
                    cell.depression_sink_cell_id != sink_cell_id ||
                    cell.depression_policy != 1 ||
                    !std::isfinite(cell.elevation_m) ||
                    !std::isfinite(cell.filled_elevation_m)) {
                    throw std::runtime_error("numeric depression correction metadata is inconsistent");
                }
                const double before_fill_m = cell.elevation_m;
                const double fill_depth_m = cell.filled_elevation_m - before_fill_m;
                if (fill_depth_m <= NUMERIC_DEPRESSION_FILL_DEPTH_TOLERANCE_M ||
                    std::abs(fill_depth_m - cell.depression_depth_m) > 1.0e-7) {
                    throw std::runtime_error("numeric depression correction depth is invalid");
                }
                const double after_fill_m = before_fill_m + fill_depth_m;
                event.cell_ids.push_back(cell_id);
                event.elevation_before_fill_m_by_cell.push_back(before_fill_m);
                event.sediment_thickness_before_correction_m_by_cell.push_back(
                    cell.sediment_thickness_m
                );
                event.fill_depth_m_by_cell.push_back(fill_depth_m);
                event.elevation_after_fill_m_by_cell.push_back(after_fill_m);
                event.area_km2 += cell.area_km2;
                event.fill_volume_km3 += fill_depth_m * cell.area_km2 / 1000.0;
                event.max_fill_depth_m = std::max(event.max_fill_depth_m, fill_depth_m);
            }

            derive_numeric_depression_breach_alternative(
                params,
                cells,
                elevation_before_correction_m,
                cell_ids,
                event
            );
            apply_numeric_depression_correction(
                cells,
                event,
                mutated_cell_ids_this_pass
            );

            result.numeric_depression_correction_event_count++;
            result.numeric_depression_correction_mass_balance_residual_km3 +=
                event.correction_mass_balance_residual_km3;
            if (event.breach_selected) {
                result.numeric_depression_breach_selected_event_count++;
                result.numeric_depression_breach_excavation_cell_application_count +=
                    static_cast<int>(std::count_if(
                        event.breach_excavation_depth_m_by_cell.begin(),
                        event.breach_excavation_depth_m_by_cell.end(),
                        [](double depth_m) {
                            return depth_m >
                                NUMERIC_DEPRESSION_FILL_DEPTH_TOLERANCE_M;
                        }
                    ));
                result.numeric_depression_breach_deposition_cell_application_count +=
                    static_cast<int>(event.breach_deposition_cell_ids.size());
                result.numeric_depression_breach_excavation_volume_km3 +=
                    event.applied_breach_excavation_volume_km3;
                result.numeric_depression_breach_deposition_volume_km3 +=
                    event.applied_breach_deposition_volume_km3;
                result.numeric_depression_alluvium_entrainment_volume_km3 +=
                    event.applied_alluvium_entrainment_volume_km3;
                result.numeric_depression_bedrock_erosion_volume_km3 +=
                    event.applied_bedrock_erosion_volume_km3;
            } else {
                result.numeric_depression_temporary_lake_event_count++;
                result.numeric_depression_temporary_lake_cell_application_count +=
                    static_cast<int>(event.cell_ids.size());
                result.numeric_depression_temporary_lake_candidate_area_km2 +=
                    event.area_km2;
                result.numeric_depression_temporary_lake_candidate_volume_km3 +=
                    event.fill_volume_km3;
                result.max_numeric_depression_temporary_lake_depth_m = std::max(
                    result.max_numeric_depression_temporary_lake_depth_m,
                    event.max_fill_depth_m
                );
                for (int cell_id : event.cell_ids) {
                    temporary_lake_unique_cell_ids.insert(cell_id);
                }
            }
            fill_history.push_back(std::move(event));
        }
    }

    throw std::runtime_error("numeric depression fill stabilization terminated unexpectedly");
}

FeedbackReference capture_feedback_reference(const std::vector<Cell>& cells) {
    FeedbackReference reference;
    reference.elevation_m.reserve(cells.size());
    reference.temperature_c.reserve(cells.size());
    reference.precipitation_mm_y.reserve(cells.size());
    reference.runoff_mm_y.reserve(cells.size());
    for (const Cell& cell : cells) {
        reference.elevation_m.push_back(cell.elevation_m);
        reference.temperature_c.push_back(cell.temperature_c);
        reference.precipitation_mm_y.push_back(cell.precipitation_mm_y);
        reference.runoff_mm_y.push_back(cell.runoff_mm_y);
    }
    return reference;
}

EarthSystemFeedbackStep summarize_feedback_step(
    const std::vector<Cell>& cells,
    int id,
    const std::string& stage,
    int erosion_iteration,
    const HydrologyStabilizationResult& stabilization,
    const FluvialSedimentRoutingStage* sediment_routing,
    const HillslopeSedimentTransportStage* hillslope_transport,
    const GlacialSedimentTransportStage* glacial_transport,
    bool erosion_applied,
    bool cryosphere_applied,
    bool plate_motion_applied,
    bool crust_transport_applied,
    bool crust_evolution_applied,
    int plate_motion_history_id,
    const FeedbackReference* previous
) {
    EarthSystemFeedbackStep step;
    step.id = id;
    step.stage = stage;
    step.erosion_iteration = erosion_iteration;
    step.sea_level_recomputed = stabilization.sea_level_recompute_count > 0;
    step.climate_recomputed = stabilization.climate_recompute_count > 0;
    step.hydrologic_water_budget_recomputed =
        stabilization.hydrologic_water_budget_recompute_count > 0;
    step.hydrology_recomputed = stabilization.hydrology_recompute_count > 0;
    step.erosion_applied = erosion_applied;
    step.cryosphere_applied = cryosphere_applied;
    step.plate_motion_applied = plate_motion_applied;
    step.crust_transport_applied = crust_transport_applied;
    step.crust_evolution_applied = crust_evolution_applied;
    step.sea_level_recompute_count = stabilization.sea_level_recompute_count;
    step.climate_recompute_count = stabilization.climate_recompute_count;
    step.hydrologic_water_budget_recompute_count =
        stabilization.hydrologic_water_budget_recompute_count;
    step.hydrology_recompute_count = stabilization.hydrology_recompute_count;
    step.numeric_depression_fill_pass_count =
        stabilization.numeric_depression_fill_pass_count;
    step.numeric_depression_fill_event_count =
        stabilization.numeric_depression_fill_event_count;
    step.numeric_depression_fill_cell_application_count =
        stabilization.numeric_depression_fill_cell_application_count;
    step.numeric_depression_filled_unique_cell_count =
        stabilization.numeric_depression_filled_unique_cell_count;
    step.numeric_depression_correction_event_count =
        stabilization.numeric_depression_correction_event_count;
    step.numeric_depression_breach_selected_event_count =
        stabilization.numeric_depression_breach_selected_event_count;
    step.numeric_depression_breach_excavation_cell_application_count =
        stabilization.numeric_depression_breach_excavation_cell_application_count;
    step.numeric_depression_breach_deposition_cell_application_count =
        stabilization.numeric_depression_breach_deposition_cell_application_count;
    step.numeric_depression_temporary_lake_event_count =
        stabilization.numeric_depression_temporary_lake_event_count;
    step.numeric_depression_temporary_lake_cell_application_count =
        stabilization.numeric_depression_temporary_lake_cell_application_count;
    step.numeric_depression_temporary_lake_unique_cell_count =
        stabilization.numeric_depression_temporary_lake_unique_cell_count;
    step.plate_motion_history_id = plate_motion_history_id;
    step.sea_level_adjustment_m = stabilization.sea_level_adjustment_m;
    step.numeric_depression_fill_area_km2 =
        stabilization.numeric_depression_fill_area_km2;
    step.numeric_depression_fill_volume_km3 =
        stabilization.numeric_depression_fill_volume_km3;
    step.max_numeric_depression_fill_depth_m =
        stabilization.max_numeric_depression_fill_depth_m;
    step.numeric_depression_breach_excavation_volume_km3 =
        stabilization.numeric_depression_breach_excavation_volume_km3;
    step.numeric_depression_breach_deposition_volume_km3 =
        stabilization.numeric_depression_breach_deposition_volume_km3;
    step.numeric_depression_correction_mass_balance_residual_km3 =
        stabilization.numeric_depression_correction_mass_balance_residual_km3;
    step.numeric_depression_temporary_lake_candidate_area_km2 =
        stabilization.numeric_depression_temporary_lake_candidate_area_km2;
    step.numeric_depression_temporary_lake_candidate_volume_km3 =
        stabilization.numeric_depression_temporary_lake_candidate_volume_km3;
    step.max_numeric_depression_temporary_lake_depth_m =
        stabilization.max_numeric_depression_temporary_lake_depth_m;
    step.sediment_alluvium_entrainment_volume_km3 =
        stabilization.numeric_depression_alluvium_entrainment_volume_km3;
    step.sediment_bedrock_erosion_volume_km3 =
        stabilization.numeric_depression_bedrock_erosion_volume_km3;
    if (sediment_routing != nullptr) {
        step.fluvial_sediment_active_cell_step_count =
            sediment_routing->active_cell_step_count;
        step.fluvial_sediment_routed_edge_count =
            sediment_routing->routed_edge_count;
        step.fluvial_sediment_land_terminal_count =
            sediment_routing->land_terminal_count;
        step.fluvial_sediment_marine_terminal_count =
            sediment_routing->marine_terminal_count;
        step.fluvial_sediment_terminal_allocation_count =
            sediment_routing->terminal_allocation_count;
        step.fluvial_sediment_local_source_volume_km3 =
            sediment_routing->local_source_volume_km3;
        step.fluvial_sediment_routed_throughput_volume_km3 =
            sediment_routing->routed_throughput_volume_km3;
        step.fluvial_sediment_capacity_deposition_volume_km3 =
            sediment_routing->capacity_deposition_volume_km3;
        step.fluvial_sediment_depression_fill_deposition_volume_km3 =
            sediment_routing->depression_fill_deposition_volume_km3;
        step.fluvial_sediment_lake_trap_deposition_volume_km3 =
            sediment_routing->lake_trap_deposition_volume_km3;
        step.fluvial_sediment_terminal_land_deposition_volume_km3 =
            sediment_routing->terminal_land_deposition_volume_km3;
        step.fluvial_sediment_marine_deposition_volume_km3 =
            sediment_routing->marine_deposition_volume_km3;
        step.fluvial_sediment_terminal_export_volume_km3 =
            sediment_routing->terminal_export_volume_km3;
        step.fluvial_sediment_mass_balance_residual_km3 =
            sediment_routing->mass_balance_residual_km3;
        step.sediment_alluvium_entrainment_volume_km3 +=
            sediment_routing->alluvium_entrainment_volume_km3;
        step.sediment_bedrock_erosion_volume_km3 +=
            sediment_routing->bedrock_erosion_volume_km3;
    }
    if (hillslope_transport != nullptr) {
        step.hillslope_sediment_transport_edge_count =
            hillslope_transport->transport_edge_count;
        step.hillslope_sediment_source_cell_count =
            hillslope_transport->source_cell_count;
        step.hillslope_sediment_target_cell_count =
            hillslope_transport->target_cell_count;
        step.hillslope_sediment_land_to_land_edge_count =
            hillslope_transport->land_to_land_edge_count;
        step.hillslope_sediment_land_to_marine_edge_count =
            hillslope_transport->land_to_marine_edge_count;
        step.hillslope_sediment_production_volume_km3 =
            hillslope_transport->production_volume_km3;
        step.hillslope_sediment_deposition_volume_km3 =
            hillslope_transport->deposition_volume_km3;
        step.hillslope_sediment_mass_balance_residual_km3 =
            hillslope_transport->mass_balance_residual_km3;
        step.max_hillslope_sediment_source_production_depth_m =
            hillslope_transport->max_source_production_depth_m;
        step.max_hillslope_sediment_target_deposition_depth_m =
            hillslope_transport->max_target_deposition_depth_m;
        step.mean_hillslope_effective_diffusivity =
            hillslope_transport->mean_effective_diffusivity;
        step.sediment_alluvium_entrainment_volume_km3 +=
            hillslope_transport->alluvium_entrainment_volume_km3;
        step.sediment_bedrock_erosion_volume_km3 +=
            hillslope_transport->bedrock_erosion_volume_km3;
    }
    if (glacial_transport != nullptr) {
        step.glacial_sediment_transfer_count =
            glacial_transport->transfer_count;
        step.glacial_sediment_source_cell_count =
            glacial_transport->source_cell_count;
        step.glacial_sediment_target_cell_count =
            glacial_transport->target_cell_count;
        step.glacial_sediment_land_target_transfer_count =
            glacial_transport->land_target_transfer_count;
        step.glacial_sediment_marine_target_transfer_count =
            glacial_transport->marine_target_transfer_count;
        step.glacial_sediment_production_volume_km3 =
            glacial_transport->production_volume_km3;
        step.glacial_sediment_deposition_volume_km3 =
            glacial_transport->deposition_volume_km3;
        step.glacial_sediment_mass_balance_residual_km3 =
            glacial_transport->mass_balance_residual_km3;
        step.glacial_sediment_terrain_volume_change_residual_km3 =
            glacial_transport->terrain_volume_change_residual_km3;
        step.max_glacial_sediment_source_production_depth_m =
            glacial_transport->max_source_production_depth_m;
        step.max_glacial_sediment_target_deposition_depth_m =
            glacial_transport->max_target_deposition_depth_m;
        step.sediment_alluvium_entrainment_volume_km3 +=
            glacial_transport->alluvium_entrainment_volume_km3;
        step.sediment_bedrock_erosion_volume_km3 +=
            glacial_transport->bedrock_erosion_volume_km3;
    }
    step.cell_count = static_cast<int>(cells.size());
    if (cells.empty()) {
        return step;
    }

    step.min_elevation_m = std::numeric_limits<double>::infinity();
    step.max_elevation_m = -std::numeric_limits<double>::infinity();
    double land_elevation_sum = 0.0;
    double cumulative_alluvium_entrainment_volume_km3 = 0.0;
    double cumulative_bedrock_erosion_volume_km3 = 0.0;
    for (std::size_t index = 0; index < cells.size(); ++index) {
        const Cell& cell = cells[index];
        const double area_km2 = std::max(0.0, cell.area_km2);
        step.water_cell_count += cell.is_water ? 1 : 0;
        step.land_cell_count += cell.is_water ? 0 : 1;
        step.river_cell_count += cell.is_river ? 1 : 0;
        step.surface_area_km2 += area_km2;
        step.ocean_area_km2 += cell.is_water ? area_km2 : 0.0;
        step.ocean_volume_km3 += cell.is_water ?
            std::max(0.0, -cell.elevation_m) * area_km2 / 1000.0 : 0.0;
        step.mean_elevation_m += cell.elevation_m;
        step.min_elevation_m = std::min(step.min_elevation_m, cell.elevation_m);
        step.max_elevation_m = std::max(step.max_elevation_m, cell.elevation_m);
        step.mean_temperature_c += cell.temperature_c;
        step.mean_precipitation_mm_y += cell.precipitation_mm_y;
        step.mean_runoff_mm_y += cell.runoff_mm_y;
        step.mean_erosion_rate_m_per_step += cell.erosion_rate;
        step.mean_sediment_thickness_m += cell.sediment_thickness_m;
        step.mean_cumulative_sediment_production_m += cell.sediment_production_m;
        step.mean_cumulative_sediment_deposition_m += cell.sediment_deposition_m;
        step.mean_cumulative_sediment_export_m += cell.sediment_export_m;
        step.cumulative_sediment_production_volume_km3 +=
            cell.sediment_production_m * area_km2 / 1000.0;
        step.cumulative_sediment_deposition_volume_km3 +=
            cell.sediment_deposition_m * area_km2 / 1000.0;
        step.cumulative_sediment_export_volume_km3 +=
            cell.sediment_export_m * area_km2 / 1000.0;
        step.sediment_inventory_volume_km3 +=
            cell.sediment_thickness_m * area_km2 / 1000.0;
        cumulative_alluvium_entrainment_volume_km3 +=
            cell.sediment_alluvium_entrainment_m * area_km2 / 1000.0;
        cumulative_bedrock_erosion_volume_km3 +=
            cell.sediment_bedrock_erosion_m * area_km2 / 1000.0;
        if (!cell.is_water) {
            land_elevation_sum += cell.elevation_m;
            step.hydrologic_land_precipitation_volume_km3_y +=
                cell.precipitation_mm_y * area_km2 * 1.0e-6;
            step.hydrologic_actual_evapotranspiration_volume_km3_y +=
                cell.actual_evapotranspiration_mm_y * area_km2 * 1.0e-6;
            step.hydrologic_infiltration_volume_km3_y +=
                cell.infiltration_mm_y * area_km2 * 1.0e-6;
            step.hydrologic_runoff_volume_km3_y +=
                cell.runoff_mm_y * area_km2 * 1.0e-6;
            step.hydrologic_water_budget_residual_km3_y +=
                cell.runoff_budget_residual_mm_y * area_km2 * 1.0e-6;
            step.max_abs_hydrologic_water_budget_cell_residual_mm_y =
                std::max(
                    step.max_abs_hydrologic_water_budget_cell_residual_mm_y,
                    std::abs(cell.runoff_budget_residual_mm_y)
                );
        }
        if (previous != nullptr && previous->elevation_m.size() == cells.size()) {
            step.mean_abs_elevation_change_m_from_previous_stage +=
                std::abs(cell.elevation_m - previous->elevation_m[index]);
            step.mean_abs_temperature_change_c_from_previous_stage +=
                std::abs(cell.temperature_c - previous->temperature_c[index]);
            step.mean_abs_precipitation_change_mm_y_from_previous_stage +=
                std::abs(cell.precipitation_mm_y - previous->precipitation_mm_y[index]);
            step.mean_abs_runoff_change_mm_y_from_previous_stage +=
                std::abs(cell.runoff_mm_y - previous->runoff_mm_y[index]);
        }
    }

    const double divisor = static_cast<double>(cells.size());
    step.ocean_fraction = step.surface_area_km2 > 0.0 ?
        step.ocean_area_km2 / step.surface_area_km2 : 0.0;
    step.mean_elevation_m /= divisor;
    step.mean_land_elevation_m = step.land_cell_count > 0 ? land_elevation_sum / static_cast<double>(step.land_cell_count) : 0.0;
    step.mean_temperature_c /= divisor;
    step.mean_precipitation_mm_y /= divisor;
    step.mean_runoff_mm_y /= divisor;
    step.mean_erosion_rate_m_per_step /= divisor;
    step.mean_sediment_thickness_m /= divisor;
    step.mean_cumulative_sediment_production_m /= divisor;
    step.mean_cumulative_sediment_deposition_m /= divisor;
    step.mean_cumulative_sediment_export_m /= divisor;
    step.sediment_source_partition_residual_km3 = std::abs(
        step.cumulative_sediment_production_volume_km3 -
        cumulative_alluvium_entrainment_volume_km3 -
        cumulative_bedrock_erosion_volume_km3
    );
    step.sediment_inventory_mass_balance_residual_km3 = std::abs(
        cumulative_bedrock_erosion_volume_km3 -
        step.sediment_inventory_volume_km3 -
        step.cumulative_sediment_export_volume_km3
    );
    step.mean_abs_elevation_change_m_from_previous_stage /= divisor;
    step.mean_abs_temperature_change_c_from_previous_stage /= divisor;
    step.mean_abs_precipitation_change_mm_y_from_previous_stage /= divisor;
    step.mean_abs_runoff_change_mm_y_from_previous_stage /= divisor;
    return step;
}

HillslopeSedimentTransportStage transport_hillslope_sediment(
    const Params& params,
    int id,
    int feedback_stage_id,
    int erosion_iteration,
    std::vector<Cell>& cells,
    std::vector<double>& production_depth_m,
    std::vector<double>& deposition_depth_m
) {
    const int n = static_cast<int>(cells.size());
    HillslopeSedimentTransportStage stage;
    stage.id = id;
    stage.feedback_stage_id = feedback_stage_id;
    stage.erosion_iteration = erosion_iteration;
    production_depth_m.assign(static_cast<std::size_t>(n), 0.0);
    deposition_depth_m.assign(static_cast<std::size_t>(n), 0.0);
    stage.input_cells.reserve(static_cast<std::size_t>(n));
    for (int cell_id = 0; cell_id < n; ++cell_id) {
        const Cell& cell = cells[static_cast<std::size_t>(cell_id)];
        HillslopeSedimentTransportInputCell input_cell;
        input_cell.cell_id = cell_id;
        input_cell.lithology = cell.lithology;
        input_cell.is_water = cell.is_water;
        input_cell.is_lake = cell.is_lake;
        input_cell.elevation_m = cell.elevation_m;
        input_cell.sediment_thickness_m = cell.sediment_thickness_m;
        stage.input_cells.push_back(input_cell);
    }
    std::set<int> source_cell_ids;
    std::set<int> target_cell_ids;
    double effective_diffusivity_sum = 0.0;

    for (int cell_a_id = 0; cell_a_id < n; ++cell_a_id) {
        const Cell& cell_a = cells[static_cast<std::size_t>(cell_a_id)];
        if (cell_a.area_km2 <= 0.0 || cell_a.neighbors.empty()) {
            throw std::runtime_error("hillslope sediment source geometry is invalid");
        }
        for (int cell_b_id : cell_a.neighbors) {
            if (cell_b_id <= cell_a_id) {
                continue;
            }
            if (cell_b_id < 0 || cell_b_id >= n) {
                throw std::runtime_error("hillslope sediment neighbor is invalid");
            }
            const Cell& cell_b = cells[static_cast<std::size_t>(cell_b_id)];
            if (cell_b.area_km2 <= 0.0 || cell_b.neighbors.empty()) {
                throw std::runtime_error("hillslope sediment target geometry is invalid");
            }
            int source_cell_id = cell_a_id;
            int target_cell_id = cell_b_id;
            if (cell_b.elevation_m > cell_a.elevation_m) {
                source_cell_id = cell_b_id;
                target_cell_id = cell_a_id;
            }
            Cell& source = cells[static_cast<std::size_t>(source_cell_id)];
            Cell& target = cells[static_cast<std::size_t>(target_cell_id)];
            const double elevation_drop_m =
                source.elevation_m - target.elevation_m;
            if (source.is_water || elevation_drop_m <= 1.0e-12) {
                continue;
            }
            const double resistance = lithology_resistance(source.lithology);
            const double effective_diffusivity = std::min(
                HILLSLOPE_MAX_EFFECTIVE_DIFFUSIVITY,
                std::max(0.0, params.hillslope_diffusion) /
                    std::max(1.0e-12, resistance)
            );
            if (effective_diffusivity <= 0.0) {
                continue;
            }
            const int source_neighbor_count =
                static_cast<int>(source.neighbors.size());
            const double source_depth_m =
                effective_diffusivity * elevation_drop_m /
                static_cast<double>(source_neighbor_count);
            const double transfer_volume_km3 =
                source_depth_m * source.area_km2 / 1000.0;
            const double target_depth_m =
                transfer_volume_km3 * 1000.0 / target.area_km2;
            const double deposited_volume_km3 =
                target_depth_m * target.area_km2 / 1000.0;

            production_depth_m[static_cast<std::size_t>(source_cell_id)] +=
                source_depth_m;
            deposition_depth_m[static_cast<std::size_t>(target_cell_id)] +=
                target_depth_m;
            source.hillslope_sediment_production_m += source_depth_m;
            source.hillslope_sediment_outgoing_edge_count++;
            target.hillslope_sediment_deposition_m += target_depth_m;
            target.hillslope_sediment_incoming_edge_count++;
            source_cell_ids.insert(source_cell_id);
            target_cell_ids.insert(target_cell_id);

            HillslopeSedimentTransportEdge edge;
            edge.id = static_cast<int>(stage.edges.size());
            edge.mesh_edge_cell_a_id = cell_a_id;
            edge.mesh_edge_cell_b_id = cell_b_id;
            edge.source_cell_id = source_cell_id;
            edge.target_cell_id = target_cell_id;
            edge.source_lithology = source.lithology;
            edge.source_neighbor_count = source_neighbor_count;
            edge.target_is_water = target.is_water;
            edge.target_is_lake = target.is_lake;
            edge.source_area_km2 = source.area_km2;
            edge.target_area_km2 = target.area_km2;
            edge.source_elevation_m = source.elevation_m;
            edge.target_elevation_m = target.elevation_m;
            edge.elevation_drop_m = elevation_drop_m;
            edge.source_lithology_resistance = resistance;
            edge.effective_diffusivity = effective_diffusivity;
            edge.source_production_depth_m = source_depth_m;
            edge.target_deposition_depth_m = target_depth_m;
            edge.transfer_volume_km3 = transfer_volume_km3;
            edge.mass_balance_residual_km3 = std::abs(
                transfer_volume_km3 - deposited_volume_km3
            );
            stage.edges.push_back(edge);
            stage.production_volume_km3 += transfer_volume_km3;
            stage.deposition_volume_km3 += deposited_volume_km3;
            stage.land_to_marine_edge_count += target.is_water ? 1 : 0;
            stage.land_to_land_edge_count += target.is_water ? 0 : 1;
            effective_diffusivity_sum += effective_diffusivity;
        }
    }

    for (int cell_id = 0; cell_id < n; ++cell_id) {
        Cell& cell = cells[static_cast<std::size_t>(cell_id)];
        cell.hillslope_sediment_net_m =
            cell.hillslope_sediment_deposition_m -
            cell.hillslope_sediment_production_m;
        stage.max_source_production_depth_m = std::max(
            stage.max_source_production_depth_m,
            production_depth_m[static_cast<std::size_t>(cell_id)]
        );
        stage.max_target_deposition_depth_m = std::max(
            stage.max_target_deposition_depth_m,
            deposition_depth_m[static_cast<std::size_t>(cell_id)]
        );
    }
    stage.transport_edge_count = static_cast<int>(stage.edges.size());
    stage.source_cell_count = static_cast<int>(source_cell_ids.size());
    stage.target_cell_count = static_cast<int>(target_cell_ids.size());
    stage.mean_effective_diffusivity = stage.edges.empty() ? 0.0 :
        effective_diffusivity_sum / static_cast<double>(stage.edges.size());
    stage.mass_balance_residual_km3 = std::abs(
        stage.production_volume_km3 - stage.deposition_volume_km3
    );
    return stage;
}

FluvialSedimentRoutingStage route_fluvial_sediment(
    const std::vector<double>& routing_base_elevation_m,
    const std::vector<double>& local_source_depth_m,
    double accumulation_scale,
    int id,
    int feedback_stage_id,
    int erosion_iteration,
    std::vector<Cell>& cells,
    std::vector<double>& deposition_depth_m,
    std::vector<double>& terminal_export_depth_m
) {
    const int n = static_cast<int>(cells.size());
    if (
        routing_base_elevation_m.size() != cells.size() ||
        local_source_depth_m.size() != cells.size()
    ) {
        throw std::runtime_error("fluvial sediment routing input size mismatch");
    }

    FluvialSedimentRoutingStage stage;
    stage.id = id;
    stage.feedback_stage_id = feedback_stage_id;
    stage.erosion_iteration = erosion_iteration;
    stage.accumulation_scale = std::max(1.0, accumulation_scale);
    deposition_depth_m.assign(static_cast<std::size_t>(n), 0.0);
    terminal_export_depth_m.assign(static_cast<std::size_t>(n), 0.0);

    std::vector<int> upstream_count(static_cast<std::size_t>(n), 0);
    for (int i = 0; i < n; ++i) {
        const Cell& cell = cells[static_cast<std::size_t>(i)];
        if (cell.area_km2 <= 0.0) {
            throw std::runtime_error("fluvial sediment routing cell area is invalid");
        }
        if (cell.flow_to >= 0) {
            if (cell.flow_to >= n || cell.flow_to == i) {
                throw std::runtime_error("fluvial sediment routing receiver is invalid");
            }
            upstream_count[static_cast<std::size_t>(cell.flow_to)]++;
        }
    }
    std::priority_queue<int, std::vector<int>, std::greater<int>> ready;
    for (int i = 0; i < n; ++i) {
        if (upstream_count[static_cast<std::size_t>(i)] == 0) {
            ready.push(i);
        }
    }
    std::vector<int> flow_order;
    flow_order.reserve(static_cast<std::size_t>(n));
    while (!ready.empty()) {
        const int current = ready.top();
        ready.pop();
        flow_order.push_back(current);
        const int receiver = cells[static_cast<std::size_t>(current)].flow_to;
        if (receiver < 0) {
            continue;
        }
        int& remaining = upstream_count[static_cast<std::size_t>(receiver)];
        remaining--;
        if (remaining == 0) {
            ready.push(receiver);
        }
    }
    if (flow_order.size() != cells.size()) {
        throw std::runtime_error("fluvial sediment routing graph contains a cycle");
    }

    std::vector<double> source_volume_km3(static_cast<std::size_t>(n), 0.0);
    std::vector<double> incoming_volume_km3(static_cast<std::size_t>(n), 0.0);
    std::vector<double> capacity_deposition_volume_km3(static_cast<std::size_t>(n), 0.0);
    std::vector<double> depression_fill_volume_km3(static_cast<std::size_t>(n), 0.0);
    std::vector<double> lake_trap_volume_km3(static_cast<std::size_t>(n), 0.0);
    std::vector<double> marine_deposition_volume_km3(static_cast<std::size_t>(n), 0.0);
    std::vector<double> routed_outgoing_volume_km3(static_cast<std::size_t>(n), 0.0);
    std::vector<double> terminal_land_deposition_volume_km3(static_cast<std::size_t>(n), 0.0);
    std::vector<double> terminal_accommodation_deposition_volume_km3(
        static_cast<std::size_t>(n), 0.0
    );
    std::vector<double> terminal_export_volume_km3(static_cast<std::size_t>(n), 0.0);
    std::vector<double> terminal_load_by_sink_km3(static_cast<std::size_t>(n), 0.0);
    constexpr double volume_epsilon_km3 = 1.0e-15;

    for (int i = 0; i < n; ++i) {
        source_volume_km3[static_cast<std::size_t>(i)] =
            std::max(0.0, local_source_depth_m[static_cast<std::size_t>(i)]) *
            cells[static_cast<std::size_t>(i)].area_km2 / 1000.0;
        stage.local_source_volume_km3 += source_volume_km3[static_cast<std::size_t>(i)];
    }

    for (int cell_id : flow_order) {
        const Cell& cell = cells[static_cast<std::size_t>(cell_id)];
        const double local_source = source_volume_km3[static_cast<std::size_t>(cell_id)];
        const double incoming = incoming_volume_km3[static_cast<std::size_t>(cell_id)];
        const double available = local_source + incoming;
        if (available <= volume_epsilon_km3) {
            continue;
        }

        FluvialSedimentRoutingCellStep step;
        step.cell_id = cell_id;
        step.flow_to_cell_id = cell.flow_to;
        step.depression_component_id = cell.depression_component_id;
        step.depression_sink_cell_id = cell.depression_sink_cell_id;
        step.water_body = cell.water_body;
        step.is_water = cell.is_water;
        step.is_river = cell.is_river;
        step.is_lake = cell.is_lake;
        step.lake_overflows = cell.lake_overflows;
        step.is_land_terminal = !cell.is_water && cell.flow_to < 0;
        step.is_marine_terminal = cell.is_water && cell.flow_to < 0;
        step.cell_area_km2 = cell.area_km2;
        step.flow_accumulation = cell.flow_accumulation;
        step.runoff_mm_y = cell.runoff_mm_y;
        step.hydrologic_flow_slope = cell.hydrologic_flow_slope;
        step.routing_base_elevation_m = routing_base_elevation_m[static_cast<std::size_t>(cell_id)];
        step.spill_elevation_m = cell.spill_elevation_m;
        step.local_source_volume_km3 = local_source;
        step.incoming_volume_km3 = incoming;
        step.available_volume_km3 = available;

        if (step.is_marine_terminal) {
            double deposition_fraction = FLUVIAL_SEDIMENT_OPEN_OCEAN_DEPOSITION_FRACTION;
            if (cell.water_body == 2) {
                deposition_fraction = FLUVIAL_SEDIMENT_SHELF_DEPOSITION_FRACTION;
            } else if (cell.water_body == 3) {
                deposition_fraction = FLUVIAL_SEDIMENT_INLAND_SEA_DEPOSITION_FRACTION;
            }
            step.marine_deposition_volume_km3 = available * deposition_fraction;
            step.terminal_export_volume_km3 =
                available - step.marine_deposition_volume_km3;
            marine_deposition_volume_km3[static_cast<std::size_t>(cell_id)] =
                step.marine_deposition_volume_km3;
            terminal_export_volume_km3[static_cast<std::size_t>(cell_id)] =
                step.terminal_export_volume_km3;
            stage.marine_terminal_count++;
            stage.marine_deposition_volume_km3 +=
                step.marine_deposition_volume_km3;
            stage.terminal_export_volume_km3 +=
                step.terminal_export_volume_km3;
        } else if (step.is_land_terminal) {
            step.terminal_land_storage_volume_km3 = available;
            terminal_load_by_sink_km3[static_cast<std::size_t>(cell_id)] = available;
            stage.land_terminal_count++;
        } else {
            const double flow_index = clamp(
                std::sqrt(
                    std::max(0.0, cell.flow_accumulation) /
                    std::max(1.0, accumulation_scale)
                ),
                0.0,
                1.0
            );
            const double slope_index = clamp(
                std::max(0.0, cell.hydrologic_flow_slope) * 1200.0,
                0.0,
                1.0
            );
            const double runoff_index = clamp(
                std::max(0.0, cell.runoff_mm_y) / 2000.0,
                0.0,
                1.0
            );
            step.transport_capacity_fraction = clamp(
                FLUVIAL_SEDIMENT_MIN_TRANSPORT_CAPACITY_FRACTION +
                    0.045 * flow_index +
                    0.025 * slope_index +
                    0.015 * runoff_index +
                    (cell.is_river ? 0.015 : 0.0),
                FLUVIAL_SEDIMENT_MIN_TRANSPORT_CAPACITY_FRACTION,
                FLUVIAL_SEDIMENT_MAX_TRANSPORT_CAPACITY_FRACTION
            );
            const double raw_capacity_deposition =
                available * (1.0 - step.transport_capacity_fraction);
            double remaining = available;
            if (cell.depression_component_id >= 0) {
                step.depression_accommodation_volume_km3 =
                    std::max(
                        0.0,
                        cell.spill_elevation_m - step.routing_base_elevation_m
                    ) * cell.area_km2 / 1000.0;
                step.depression_fill_deposition_volume_km3 = std::min(
                    remaining,
                    step.depression_accommodation_volume_km3
                );
                remaining -= step.depression_fill_deposition_volume_km3;
            }
            step.capacity_deposition_volume_km3 = std::min(
                remaining,
                raw_capacity_deposition
            );
            remaining -= step.capacity_deposition_volume_km3;
            if (cell.is_lake) {
                const double lake_trap_fraction = cell.lake_overflows ?
                    FLUVIAL_SEDIMENT_LAKE_TRAP_FRACTION :
                    FLUVIAL_SEDIMENT_CLOSED_LAKE_TRAP_FRACTION;
                const double existing_deposition =
                    step.depression_fill_deposition_volume_km3 +
                    step.capacity_deposition_volume_km3;
                step.lake_trap_deposition_volume_km3 = std::min(
                    remaining,
                    std::max(0.0, available * lake_trap_fraction - existing_deposition)
                );
                remaining -= step.lake_trap_deposition_volume_km3;
            }
            step.routed_outgoing_volume_km3 = std::max(0.0, remaining);
            capacity_deposition_volume_km3[static_cast<std::size_t>(cell_id)] =
                step.capacity_deposition_volume_km3;
            depression_fill_volume_km3[static_cast<std::size_t>(cell_id)] =
                step.depression_fill_deposition_volume_km3;
            lake_trap_volume_km3[static_cast<std::size_t>(cell_id)] =
                step.lake_trap_deposition_volume_km3;
            routed_outgoing_volume_km3[static_cast<std::size_t>(cell_id)] =
                step.routed_outgoing_volume_km3;
            incoming_volume_km3[static_cast<std::size_t>(cell.flow_to)] +=
                step.routed_outgoing_volume_km3;
            stage.routed_throughput_volume_km3 +=
                step.routed_outgoing_volume_km3;
            stage.capacity_deposition_volume_km3 +=
                step.capacity_deposition_volume_km3;
            stage.depression_fill_deposition_volume_km3 +=
                step.depression_fill_deposition_volume_km3;
            stage.lake_trap_deposition_volume_km3 +=
                step.lake_trap_deposition_volume_km3;
            if (step.routed_outgoing_volume_km3 > volume_epsilon_km3) {
                stage.routed_edge_count++;
            }
        }
        step.local_mass_balance_residual_km3 =
            step.available_volume_km3 -
            step.capacity_deposition_volume_km3 -
            step.depression_fill_deposition_volume_km3 -
            step.lake_trap_deposition_volume_km3 -
            step.marine_deposition_volume_km3 -
            step.routed_outgoing_volume_km3 -
            step.terminal_land_storage_volume_km3 -
            step.terminal_export_volume_km3;
        stage.cell_steps.push_back(step);
    }

    std::vector<std::vector<int>> terminal_targets_by_sink(
        static_cast<std::size_t>(n)
    );
    for (int cell_id = 0; cell_id < n; ++cell_id) {
        const Cell& cell = cells[static_cast<std::size_t>(cell_id)];
        if (
            !cell.is_water &&
            cell.depression_component_id >= 0 &&
            cell.depression_sink_cell_id >= 0 &&
            cell.depression_sink_cell_id < n
        ) {
            terminal_targets_by_sink[
                static_cast<std::size_t>(cell.depression_sink_cell_id)
            ].push_back(cell_id);
        }
    }
    for (int sink_id = 0; sink_id < n; ++sink_id) {
        const double terminal_load = terminal_load_by_sink_km3[static_cast<std::size_t>(sink_id)];
        if (terminal_load <= volume_epsilon_km3) {
            continue;
        }
        std::vector<int> targets = terminal_targets_by_sink[
            static_cast<std::size_t>(sink_id)
        ];
        if (targets.empty()) {
            targets.push_back(sink_id);
        }

        std::vector<double> accommodation_by_target_km3;
        accommodation_by_target_km3.reserve(targets.size());
        double total_accommodation_km3 = 0.0;
        double total_target_area_km2 = 0.0;
        for (int target_id : targets) {
            const Cell& target = cells[static_cast<std::size_t>(target_id)];
            const double prior_local_deposition_volume_km3 =
                capacity_deposition_volume_km3[static_cast<std::size_t>(target_id)] +
                depression_fill_volume_km3[static_cast<std::size_t>(target_id)] +
                lake_trap_volume_km3[static_cast<std::size_t>(target_id)];
            const double prior_local_deposition_depth_m =
                prior_local_deposition_volume_km3 * 1000.0 / target.area_km2;
            const double accommodation_km3 = target.depression_component_id >= 0 ?
                std::max(
                    0.0,
                    target.spill_elevation_m -
                        routing_base_elevation_m[static_cast<std::size_t>(target_id)] -
                        prior_local_deposition_depth_m
                ) * target.area_km2 / 1000.0 : 0.0;
            accommodation_by_target_km3.push_back(accommodation_km3);
            total_accommodation_km3 += accommodation_km3;
            total_target_area_km2 += target.area_km2;
            FluvialSedimentTerminalAllocation allocation;
            allocation.sink_cell_id = sink_id;
            allocation.target_cell_id = target_id;
            allocation.depression_component_id = target.depression_component_id;
            allocation.target_area_km2 = target.area_km2;
            allocation.routing_base_elevation_m =
                routing_base_elevation_m[static_cast<std::size_t>(target_id)];
            allocation.spill_elevation_m = target.spill_elevation_m;
            allocation.prior_local_deposition_volume_km3 =
                prior_local_deposition_volume_km3;
            allocation.accommodation_before_allocation_km3 = accommodation_km3;
            stage.terminal_allocations.push_back(allocation);
        }

        const std::size_t allocation_start =
            stage.terminal_allocations.size() - targets.size();
        double remaining_accommodation_deposition = std::min(
            terminal_load,
            total_accommodation_km3
        );
        int last_accommodation_target = -1;
        for (std::size_t index = 0; index < targets.size(); ++index) {
            if (accommodation_by_target_km3[index] > volume_epsilon_km3) {
                last_accommodation_target = static_cast<int>(index);
            }
        }
        for (std::size_t index = 0; index < targets.size(); ++index) {
            double allocation_volume = 0.0;
            if (
                remaining_accommodation_deposition > 0.0 &&
                total_accommodation_km3 > 0.0 &&
                accommodation_by_target_km3[index] > 0.0
            ) {
                allocation_volume = static_cast<int>(index) == last_accommodation_target ?
                    remaining_accommodation_deposition :
                    std::min(
                        remaining_accommodation_deposition,
                        std::min(terminal_load, total_accommodation_km3) *
                            accommodation_by_target_km3[index] /
                            total_accommodation_km3
                    );
            }
            remaining_accommodation_deposition -= allocation_volume;
            FluvialSedimentTerminalAllocation& allocation =
                stage.terminal_allocations[allocation_start + index];
            allocation.accommodation_deposition_volume_km3 = allocation_volume;
            allocation.total_deposition_volume_km3 += allocation_volume;
            terminal_land_deposition_volume_km3[static_cast<std::size_t>(targets[index])] +=
                allocation_volume;
            terminal_accommodation_deposition_volume_km3[
                static_cast<std::size_t>(targets[index])
            ] += allocation_volume;
            depression_fill_volume_km3[static_cast<std::size_t>(targets[index])] +=
                allocation_volume;
            stage.depression_fill_deposition_volume_km3 += allocation_volume;
        }

        const double accommodation_deposition = std::min(
            terminal_load,
            total_accommodation_km3
        );
        double remaining_excess = terminal_load - accommodation_deposition;
        const double initial_excess = remaining_excess;
        for (std::size_t index = 0; index < targets.size(); ++index) {
            const Cell& target = cells[static_cast<std::size_t>(targets[index])];
            const double allocation_volume = index + 1 == targets.size() ?
                remaining_excess :
                std::min(
                    remaining_excess,
                    initial_excess * target.area_km2 /
                        std::max(volume_epsilon_km3, total_target_area_km2)
                );
            remaining_excess -= allocation_volume;
            FluvialSedimentTerminalAllocation& allocation =
                stage.terminal_allocations[allocation_start + index];
            allocation.excess_aggradation_volume_km3 = allocation_volume;
            allocation.total_deposition_volume_km3 += allocation_volume;
            terminal_land_deposition_volume_km3[static_cast<std::size_t>(targets[index])] +=
                allocation_volume;
        }
        cells[static_cast<std::size_t>(sink_id)]
            .fluvial_sediment_terminal_capture_volume_km3 += terminal_load;
        stage.terminal_land_deposition_volume_km3 += terminal_load;
    }

    stage.terminal_allocation_count = static_cast<int>(std::count_if(
        stage.terminal_allocations.begin(),
        stage.terminal_allocations.end(),
        [volume_epsilon_km3](const FluvialSedimentTerminalAllocation& allocation) {
            return allocation.total_deposition_volume_km3 > volume_epsilon_km3;
        }
    ));
    stage.active_cell_step_count = static_cast<int>(stage.cell_steps.size());

    double total_deposition_volume_km3 = 0.0;
    for (int i = 0; i < n; ++i) {
        Cell& cell = cells[static_cast<std::size_t>(i)];
        const double area_km2 = cell.area_km2;
        const double land_local_deposition_volume_km3 =
            capacity_deposition_volume_km3[static_cast<std::size_t>(i)] +
            depression_fill_volume_km3[static_cast<std::size_t>(i)] +
            lake_trap_volume_km3[static_cast<std::size_t>(i)] -
            terminal_accommodation_deposition_volume_km3[
                static_cast<std::size_t>(i)
            ];
        const double total_cell_deposition_volume_km3 =
            land_local_deposition_volume_km3 +
            terminal_land_deposition_volume_km3[static_cast<std::size_t>(i)] +
            marine_deposition_volume_km3[static_cast<std::size_t>(i)];
        deposition_depth_m[static_cast<std::size_t>(i)] =
            total_cell_deposition_volume_km3 * 1000.0 / area_km2;
        terminal_export_depth_m[static_cast<std::size_t>(i)] =
            terminal_export_volume_km3[static_cast<std::size_t>(i)] * 1000.0 /
            area_km2;
        cell.fluvial_sediment_local_source_m +=
            source_volume_km3[static_cast<std::size_t>(i)] * 1000.0 / area_km2;
        cell.fluvial_sediment_routed_incoming_m +=
            incoming_volume_km3[static_cast<std::size_t>(i)] * 1000.0 / area_km2;
        cell.fluvial_sediment_routed_outgoing_m +=
            routed_outgoing_volume_km3[static_cast<std::size_t>(i)] * 1000.0 /
            area_km2;
        cell.fluvial_sediment_local_deposition_m +=
            land_local_deposition_volume_km3 * 1000.0 / area_km2;
        cell.fluvial_sediment_terminal_land_deposition_m +=
            terminal_land_deposition_volume_km3[static_cast<std::size_t>(i)] *
            1000.0 / area_km2;
        cell.fluvial_sediment_marine_deposition_m +=
            marine_deposition_volume_km3[static_cast<std::size_t>(i)] * 1000.0 /
            area_km2;
        cell.fluvial_sediment_depression_fill_m +=
            depression_fill_volume_km3[static_cast<std::size_t>(i)] * 1000.0 /
            area_km2;
        cell.fluvial_sediment_terminal_export_m +=
            terminal_export_depth_m[static_cast<std::size_t>(i)];
        if (
            source_volume_km3[static_cast<std::size_t>(i)] > volume_epsilon_km3 ||
            incoming_volume_km3[static_cast<std::size_t>(i)] > volume_epsilon_km3 ||
            terminal_land_deposition_volume_km3[static_cast<std::size_t>(i)] > volume_epsilon_km3
        ) {
            cell.fluvial_sediment_routing_event_count++;
        }
        total_deposition_volume_km3 += total_cell_deposition_volume_km3;
    }
    stage.mass_balance_residual_km3 = std::abs(
        stage.local_source_volume_km3 -
        total_deposition_volume_km3 -
        stage.terminal_export_volume_km3
    );
    return stage;
}

void erode(
    const Params& params,
    std::vector<Plate>& plates,
    std::vector<Cell>& cells,
    std::vector<EarthSystemFeedbackStep>& feedback_history,
    std::vector<PlateMotionStep>& plate_motion_history,
    std::vector<NumericDepressionFillEvent>& numeric_depression_fill_history,
    std::vector<HydrologicWaterBudgetStage>& hydrologic_water_budget_history,
    std::vector<FluvialSedimentRoutingStage>& sediment_routing_history,
    std::vector<HillslopeSedimentTransportStage>& hillslope_transport_history
) {
    const int n = static_cast<int>(cells.size());
    for (int iter = 0; iter < params.erosion_iterations; ++iter) {
        const FeedbackReference previous = capture_feedback_reference(cells);
        const std::vector<double> tectonic_elevation_change = advance_plate_motion_and_crust(
            params,
            iter + 1,
            plates,
            cells,
            plate_motion_history
        );
        std::vector<double> accum;
        for (const Cell& cell : cells) {
            if (!cell.is_water && cell.flow_accumulation > 0.0) {
                accum.push_back(cell.flow_accumulation);
            }
        }
        std::sort(accum.begin(), accum.end());
        const double acc_scale = accum.empty() ? 1.0 : std::max(1.0, accum[static_cast<std::size_t>(0.95 * (accum.size() - 1))]);
        std::vector<double> hillslope_production_depth_m;
        std::vector<double> hillslope_deposition_depth_m;
        HillslopeSedimentTransportStage hillslope_transport =
            transport_hillslope_sediment(
                params,
                static_cast<int>(hillslope_transport_history.size()),
                static_cast<int>(feedback_history.size()),
                iter + 1,
                cells,
                hillslope_production_depth_m,
                hillslope_deposition_depth_m
            );
        std::vector<double> next(n);
        std::vector<double> sediment_source(n, 0.0);
        if (std::any_of(cells.begin(), cells.end(), [](const Cell& cell) {
                return cell.area_km2 <= 0.0;
            })) {
            throw std::runtime_error("sediment transfer cell area is invalid");
        }
#pragma omp parallel for schedule(static)
        for (int i = 0; i < n; ++i) {
            Cell& cell = cells[i];
            next[i] =
                cell.elevation_m +
                tectonic_elevation_change[static_cast<std::size_t>(i)] -
                hillslope_production_depth_m[static_cast<std::size_t>(i)] +
                hillslope_deposition_depth_m[static_cast<std::size_t>(i)];
            if (cell.is_water) {
                cell.erosion_rate = 0.0;
                continue;
            }
            double slope = 0.0;
            if (cell.flow_to >= 0) {
                slope = std::max(0.0, cell.hydrologic_flow_slope);
            }
            const double acc_norm = clamp(cell.flow_accumulation / acc_scale, 0.0, 3.0);
            const double erodability = 1.0 / lithology_resistance(cell.lithology);
            const double stream = params.stream_power_coefficient * erodability *
                std::pow(acc_norm, params.drainage_exponent) * std::pow(std::max(0.0, slope * 900.0), params.slope_exponent);
            cell.erosion_rate = stream;
            sediment_source[static_cast<std::size_t>(i)] = stream;
            next[i] -= stream;
        }
        std::vector<double> sediment_delta;
        std::vector<double> sediment_export;
        FluvialSedimentRoutingStage sediment_routing = route_fluvial_sediment(
            next,
            sediment_source,
            acc_scale,
            static_cast<int>(sediment_routing_history.size()),
            static_cast<int>(feedback_history.size()),
            iter + 1,
            cells,
            sediment_delta,
            sediment_export
        );
        for (int i = 0; i < n; ++i) {
            const double hillslope_source_depth_m =
                hillslope_production_depth_m[static_cast<std::size_t>(i)];
            const double fluvial_source_depth_m =
                sediment_source[static_cast<std::size_t>(i)];
            double available_alluvium_depth_m =
                cells[i].sediment_thickness_m;
            const double hillslope_alluvium_entrainment_depth_m = std::min(
                available_alluvium_depth_m,
                hillslope_source_depth_m
            );
            available_alluvium_depth_m -=
                hillslope_alluvium_entrainment_depth_m;
            const double fluvial_alluvium_entrainment_depth_m = std::min(
                available_alluvium_depth_m,
                fluvial_source_depth_m
            );
            available_alluvium_depth_m -=
                fluvial_alluvium_entrainment_depth_m;
            const double hillslope_bedrock_erosion_depth_m = std::max(
                0.0,
                hillslope_source_depth_m -
                    hillslope_alluvium_entrainment_depth_m
            );
            const double fluvial_bedrock_erosion_depth_m = std::max(
                0.0,
                fluvial_source_depth_m -
                    fluvial_alluvium_entrainment_depth_m
            );
            const double area_km2 = cells[i].area_km2;
            hillslope_transport.alluvium_entrainment_volume_km3 +=
                hillslope_alluvium_entrainment_depth_m * area_km2 / 1000.0;
            hillslope_transport.bedrock_erosion_volume_km3 +=
                hillslope_bedrock_erosion_depth_m * area_km2 / 1000.0;
            sediment_routing.alluvium_entrainment_volume_km3 +=
                fluvial_alluvium_entrainment_depth_m * area_km2 / 1000.0;
            sediment_routing.bedrock_erosion_volume_km3 +=
                fluvial_bedrock_erosion_depth_m * area_km2 / 1000.0;
            cells[i].sediment_alluvium_entrainment_m +=
                hillslope_alluvium_entrainment_depth_m +
                fluvial_alluvium_entrainment_depth_m;
            cells[i].sediment_bedrock_erosion_m +=
                hillslope_bedrock_erosion_depth_m +
                fluvial_bedrock_erosion_depth_m;
            cells[i].sediment_production_m +=
                fluvial_source_depth_m + hillslope_source_depth_m;
            cells[i].sediment_deposition_m +=
                sediment_delta[static_cast<std::size_t>(i)] +
                hillslope_deposition_depth_m[static_cast<std::size_t>(i)];
            cells[i].sediment_export_m += sediment_export[static_cast<std::size_t>(i)];
            cells[i].sediment_thickness_m = std::max(
                0.0,
                available_alluvium_depth_m +
                    sediment_delta[static_cast<std::size_t>(i)] +
                    hillslope_deposition_depth_m[static_cast<std::size_t>(i)]
            );
            cells[i].elevation_m = next[i] + sediment_delta[i];
            cells[i].sediment_net_budget_m = cells[i].sediment_deposition_m - cells[i].sediment_production_m;
        }
        sediment_routing_history.push_back(std::move(sediment_routing));
        hillslope_transport_history.push_back(std::move(hillslope_transport));
        const HydrologyStabilizationResult stabilization = stabilize_numeric_depressions(
            params,
            cells,
            static_cast<int>(feedback_history.size()),
            "erosion_iteration",
            iter + 1,
            numeric_depression_fill_history,
            hydrologic_water_budget_history
        );
        feedback_history.push_back(summarize_feedback_step(
            cells,
            static_cast<int>(feedback_history.size()),
            "erosion_iteration",
            iter + 1,
            stabilization,
            &sediment_routing_history.back(),
            &hillslope_transport_history.back(),
            nullptr,
            true,
            false,
            true,
            true,
            true,
            plate_motion_history.back().id,
            &previous
        ));
    }
}

bool has_ocean_neighbor(const std::vector<Cell>& cells, int i) {
    for (int j : cells[i].neighbors) {
        if (cells[j].is_water) {
            return true;
        }
    }
    return false;
}

bool has_glacier_neighbor(const std::vector<Cell>& cells, int i, double threshold_m = 80.0) {
    for (int j : cells[i].neighbors) {
        if (cells[j].ice_thickness_m >= threshold_m) {
            return true;
        }
    }
    return false;
}

void derive_cryosphere_state(const Params& params, std::vector<Cell>& cells) {
    const int n = static_cast<int>(cells.size());
    for (int i = 0; i < n; ++i) {
        Cell& cell = cells[i];
        cell.ice_thickness_m = 0.0;
        cell.glacier_flow_to = -1;
        cell.ice_surface_mass_balance_m_y = 0.0;
        cell.basal_sliding_index = 0.0;
        cell.ice_velocity_m_y = 0.0;
        cell.glacial_erosion_m = 0.0;
        if (cell.is_water) {
            continue;
        }

        const double lat_factor = clamp((std::abs(cell.lat) * DEG - 50.0) / 32.0, 0.0, 1.25);
        const double elevation_factor = clamp((cell.elevation_m - 1250.0) / 2500.0, 0.0, 1.25);
        const double cold_index = clamp((-cell.temperature_c - 3.0) / 22.0, 0.0, 1.25);
        const double moisture = clamp((cell.precipitation_mm_y - 140.0) / 1500.0, 0.05, 1.15);
        const double persistence = cold_index * moisture * (0.42 + std::max(lat_factor, elevation_factor));
        if (persistence > 0.16) {
            cell.ice_thickness_m = clamp((persistence - 0.16) * 1350.0, 0.0, 3200.0);
            if (cell.temperature_c > -2.0 && cell.elevation_m < 1900.0) {
                cell.ice_thickness_m *= 0.35;
            }
            if (cell.ice_thickness_m < 25.0) {
                cell.ice_thickness_m = 0.0;
            }
        }

        if (cell.ice_thickness_m <= 0.0) {
            continue;
        }
        const double accumulation_m_y = clamp(
            (cell.precipitation_mm_y / 1000.0) * clamp((-cell.temperature_c + 1.0) / 18.0, 0.0, 1.4),
            0.0,
            3.2
        );
        const double ablation_m_y = clamp(std::max(0.0, cell.temperature_c + 1.5) * 0.075, 0.0, 4.0);
        cell.ice_surface_mass_balance_m_y = clamp(accumulation_m_y - ablation_m_y, -4.0, 3.2);
        double best_drop = 0.0;
        int best = -1;
        for (int j : cell.neighbors) {
            const double drop = cell.elevation_m - cells[j].elevation_m;
            if (drop > best_drop) {
                best_drop = drop;
                best = j;
            }
        }
        cell.glacier_flow_to = best;
        if (best >= 0) {
            const double distance = neighbor_distance_m(params, cell, cells[best]);
            const double slope = best_drop / distance;
            cell.basal_sliding_index = clamp(
                0.18 + 0.32 * clamp(cell.ice_thickness_m / 1800.0, 0.0, 1.0) +
                    0.22 * clamp((cell.temperature_c + 8.0) / 10.0, 0.0, 1.0) +
                    0.14 * clamp(cell.precipitation_mm_y / 1600.0, 0.0, 1.0) +
                    0.24 * clamp(slope * 900.0, 0.0, 1.0),
                0.0,
                1.0
            );
            cell.ice_velocity_m_y = clamp(
                4.0 + 110.0 * cell.basal_sliding_index +
                    85.0 * clamp(cell.ice_thickness_m / 2200.0, 0.0, 1.0) * clamp(slope * 1200.0, 0.0, 1.4),
                0.0,
                420.0
            );
            cell.glacial_erosion_m = clamp((cell.ice_thickness_m / 1000.0) * std::max(0.0, slope * 900.0) * 12.0, 0.0, 85.0);
        } else {
            cell.basal_sliding_index = clamp(
                0.12 + 0.30 * clamp(cell.ice_thickness_m / 1800.0, 0.0, 1.0) +
                    0.18 * clamp((cell.temperature_c + 8.0) / 10.0, 0.0, 1.0),
                0.0,
                1.0
            );
            cell.ice_velocity_m_y = clamp(2.0 + 52.0 * cell.basal_sliding_index, 0.0, 120.0);
        }
    }
}

GlacialSedimentTransportStage transport_glacial_sediment(
    int id,
    int feedback_stage_id,
    std::vector<Cell>& cells
) {
    const int n = static_cast<int>(cells.size());
    GlacialSedimentTransportStage stage;
    stage.id = id;
    stage.feedback_stage_id = feedback_stage_id;
    stage.input_cells.reserve(static_cast<std::size_t>(n));
    std::vector<double> production_depth_m(static_cast<std::size_t>(n), 0.0);
    std::vector<double> deposition_depth_m(static_cast<std::size_t>(n), 0.0);
    std::set<int> target_cell_ids;

    for (int cell_id = 0; cell_id < n; ++cell_id) {
        const Cell& cell = cells[static_cast<std::size_t>(cell_id)];
        GlacialSedimentTransportInputCell input;
        input.cell_id = cell_id;
        input.glacier_flow_to_cell_id = cell.glacier_flow_to;
        input.is_water = cell.is_water;
        input.elevation_m = cell.elevation_m;
        input.ice_thickness_m = cell.ice_thickness_m;
        input.glacial_erosion_m = cell.glacial_erosion_m;
        input.sediment_thickness_m = cell.sediment_thickness_m;
        stage.input_cells.push_back(input);
    }

    for (int source_cell_id = 0; source_cell_id < n; ++source_cell_id) {
        Cell& source = cells[static_cast<std::size_t>(source_cell_id)];
        const int target_cell_id = source.glacier_flow_to;
        if (target_cell_id < 0 || source.glacial_erosion_m <= 0.0) {
            continue;
        }
        if (
            target_cell_id >= n ||
            std::find(
                source.neighbors.begin(),
                source.neighbors.end(),
                target_cell_id
            ) == source.neighbors.end()
        ) {
            throw std::runtime_error(
                "glacial sediment transfer target is invalid"
            );
        }
        Cell& target = cells[static_cast<std::size_t>(target_cell_id)];
        const double elevation_drop_m =
            source.elevation_m - target.elevation_m;
        if (
            source.is_water || source.ice_thickness_m <= 0.0 ||
            elevation_drop_m <= 0.0 || source.area_km2 <= 0.0 ||
            target.area_km2 <= 0.0
        ) {
            throw std::runtime_error(
                "glacial sediment transfer source state is invalid"
            );
        }
        const double source_depth_m =
            source.glacial_erosion_m * GLACIAL_SEDIMENT_MOBILE_FRACTION;
        const double transfer_volume_km3 =
            source_depth_m * source.area_km2 / 1000.0;
        const double target_depth_m =
            transfer_volume_km3 * 1000.0 / target.area_km2;
        const double deposited_volume_km3 =
            target_depth_m * target.area_km2 / 1000.0;

        production_depth_m[static_cast<std::size_t>(source_cell_id)] +=
            source_depth_m;
        deposition_depth_m[static_cast<std::size_t>(target_cell_id)] +=
            target_depth_m;
        source.glacial_sediment_production_m += source_depth_m;
        source.glacial_sediment_outgoing_transfer_count++;
        target.glacial_sediment_deposition_m += target_depth_m;
        target.glacial_sediment_incoming_transfer_count++;
        target_cell_ids.insert(target_cell_id);

        GlacialSedimentTransfer transfer;
        transfer.id = static_cast<int>(stage.transfers.size());
        transfer.source_cell_id = source_cell_id;
        transfer.target_cell_id = target_cell_id;
        transfer.target_is_water = target.is_water;
        transfer.source_area_km2 = source.area_km2;
        transfer.target_area_km2 = target.area_km2;
        transfer.source_elevation_m = source.elevation_m;
        transfer.target_elevation_m = target.elevation_m;
        transfer.elevation_drop_m = elevation_drop_m;
        transfer.source_ice_thickness_m = source.ice_thickness_m;
        transfer.source_glacial_erosion_m = source.glacial_erosion_m;
        transfer.source_production_depth_m = source_depth_m;
        transfer.target_deposition_depth_m = target_depth_m;
        transfer.transfer_volume_km3 = transfer_volume_km3;
        transfer.mass_balance_residual_km3 = std::abs(
            transfer_volume_km3 - deposited_volume_km3
        );
        stage.transfers.push_back(transfer);
        stage.production_volume_km3 += transfer_volume_km3;
        stage.deposition_volume_km3 += deposited_volume_km3;
        stage.land_target_transfer_count += target.is_water ? 0 : 1;
        stage.marine_target_transfer_count += target.is_water ? 1 : 0;
        stage.max_source_production_depth_m = std::max(
            stage.max_source_production_depth_m,
            source_depth_m
        );
    }

    for (int i = 0; i < n; ++i) {
        Cell& cell = cells[static_cast<std::size_t>(i)];
        const double source_depth_m =
            production_depth_m[static_cast<std::size_t>(i)];
        const double alluvium_entrainment_depth_m = std::min(
            cell.sediment_thickness_m,
            source_depth_m
        );
        const double bedrock_erosion_depth_m = std::max(
            0.0,
            source_depth_m - alluvium_entrainment_depth_m
        );
        stage.alluvium_entrainment_volume_km3 +=
            alluvium_entrainment_depth_m * cell.area_km2 / 1000.0;
        stage.bedrock_erosion_volume_km3 +=
            bedrock_erosion_depth_m * cell.area_km2 / 1000.0;
        cell.sediment_alluvium_entrainment_m +=
            alluvium_entrainment_depth_m;
        cell.sediment_bedrock_erosion_m += bedrock_erosion_depth_m;
        cell.elevation_m +=
            deposition_depth_m[static_cast<std::size_t>(i)] -
            source_depth_m;
        cell.sediment_production_m +=
            source_depth_m;
        cell.sediment_deposition_m +=
            deposition_depth_m[static_cast<std::size_t>(i)];
        cell.sediment_thickness_m = std::max(
            0.0,
            cell.sediment_thickness_m - alluvium_entrainment_depth_m +
                deposition_depth_m[static_cast<std::size_t>(i)]
        );
        cell.glacial_sediment_net_m =
            cell.glacial_sediment_deposition_m -
            cell.glacial_sediment_production_m;
        cell.sediment_net_budget_m =
            cell.sediment_deposition_m - cell.sediment_production_m;
        stage.max_target_deposition_depth_m = std::max(
            stage.max_target_deposition_depth_m,
            deposition_depth_m[static_cast<std::size_t>(i)]
        );
        stage.post_transport_elevation_m_by_cell.push_back(cell.elevation_m);
    }
    stage.transfer_count = static_cast<int>(stage.transfers.size());
    stage.source_cell_count = stage.transfer_count;
    stage.target_cell_count = static_cast<int>(target_cell_ids.size());
    stage.mass_balance_residual_km3 = std::abs(
        stage.production_volume_km3 - stage.deposition_volume_km3
    );
    stage.terrain_volume_change_residual_km3 =
        stage.mass_balance_residual_km3;
    return stage;
}

void derive_soils_biomes_resources(const Params& params, std::vector<Cell>& cells) {
    const int n = static_cast<int>(cells.size());
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        Cell& cell = cells[i];
        const double relief = local_relief(cells, i);
        const double slope_penalty = clamp(relief / 1800.0, 0.0, 1.0);
        const double pet = std::max(1.0, (cell.temperature_c + 8.0) * 31.0);
        const double aridity = cell.precipitation_mm_y / pet;
        const double latitude_pet_factor = 0.66 + 0.34 *
            (1.0 - std::min(1.0, std::abs(cell.lat) * DEG / 90.0));
        int dry_season_months = 0;
        int wet_season_months = 0;
        const std::size_t climate_month_count = std::min(
            cell.temperature_monthly_c.size(), cell.precipitation_monthly_mm.size()
        );
        for (std::size_t month = 0; month < climate_month_count; ++month) {
            const double monthly_pet = std::max(0.0, cell.temperature_monthly_c[month] + 5.0) *
                3.1 * latitude_pet_factor;
            dry_season_months += cell.precipitation_monthly_mm[month] < monthly_pet * 0.35 ? 1 : 0;
            wet_season_months += cell.precipitation_monthly_mm[month] >= monthly_pet * 0.75 ? 1 : 0;
        }
        const bool warm_seasonal_climate =
            dry_season_months >= 2 && wet_season_months >= 3;
        const bool coast = has_ocean_neighbor(cells, i);
        if (cell.is_water) {
            cell.soil_type = 0;
            cell.soil_depth_m = 0.0;
            cell.fertility = 0.0;
            cell.biome = cell.water_body == 2 ? 1 : (cell.water_body == 3 ? 2 : 0);
            cell.resource = (coast || cell.water_body == 2) ? 8 : 0;
            cell.settlement_score = 0.0;
            continue;
        }
        const double litho_base = cell.lithology == 5 ? 0.78 : (cell.lithology == 1 ? 0.50 : (cell.lithology == 4 ? 0.44 : 0.58));
        const double climate_soil = clamp(cell.precipitation_mm_y / 1300.0, 0.0, 1.2) * clamp((cell.temperature_c + 8.0) / 30.0, 0.0, 1.1);
        cell.soil_depth_m = clamp(0.12 + 1.8 * climate_soil + (cell.is_river ? 0.85 : 0.0) - 1.5 * slope_penalty, 0.02, 5.0);
        cell.fertility = clamp(litho_base + 0.20 * climate_soil + (cell.is_river ? 0.24 : 0.0) -
            0.35 * slope_penalty - (aridity < 0.45 ? 0.28 : 0.0), 0.0, 1.0);
        if (cell.is_lake) {
            cell.water_body = aridity < 0.5 ? 5 : 4;
            cell.soil_type = aridity < 0.5 ? 10 : 9;
            cell.biome = aridity < 0.5 ? 10 : 2;
        } else if (cell.ice_thickness_m > 180.0 ||
            (cell.temperature_c < -8.0 && (std::abs(cell.lat) * DEG > 55.0 || cell.elevation_m > 1600.0))) {
            cell.soil_type = 8;
            cell.biome = 3;
        } else if (cell.elevation_m > 2800.0 && cell.temperature_c < 6.0) {
            cell.soil_type = 1;
            cell.biome = 14;
        } else if (cell.temperature_c < -2.0) {
            cell.soil_type = 8;
            cell.biome = 4;
        } else if (aridity < 0.32) {
            cell.soil_type = 4;
            cell.biome = cell.temperature_c < 11.0 ? 9 : 10;
        } else if (cell.temperature_c > 23.0 && cell.precipitation_mm_y > 2100.0) {
            cell.soil_type = 5;
            cell.biome = 13;
        } else if (cell.temperature_c > 21.0 && cell.precipitation_mm_y > 950.0) {
            cell.soil_type = 5;
            cell.biome = 12;
        } else if (cell.temperature_c > 18.0 && aridity < 0.82 && warm_seasonal_climate) {
            cell.soil_type = 4;
            cell.biome = 11;
        } else if (cell.temperature_c > 8.0 && cell.precipitation_mm_y > 760.0) {
            cell.soil_type = 6;
            cell.biome = 6;
        } else if (cell.temperature_c > 5.0 && aridity > 0.45) {
            cell.soil_type = 6;
            cell.biome = aridity > 1.1 ? 6 : 7;
        } else if (cell.temperature_c > -1.0 && cell.precipitation_mm_y > 420.0) {
            cell.soil_type = 7;
            cell.biome = 5;
        } else {
            cell.soil_type = 4;
            cell.biome = (cell.temperature_c < 2.0 && cell.precipitation_mm_y > 320.0 && aridity > 0.55) ?
                4 :
                (cell.temperature_c < 8.0 ? 9 : 10);
        }
        if (cell.is_river && relief < 450.0 && cell.precipitation_mm_y > 500.0) {
            cell.soil_type = 3;
            if (cell.biome != 13 && cell.biome != 3) {
                cell.biome = 15;
            }
        } else if (cell.lithology == 5 && cell.soil_type != 8) {
            cell.soil_type = 2;
        }
        if (cell.boundary_convergent > 0.38 && (cell.crust_type == 3 || cell.lithology == 5)) {
            cell.resource = 1;
        } else if (cell.crust_type == 4 && cell.crust_age_ma > 1800.0) {
            cell.resource = 2;
        } else if (cell.crust_type == 7 || cell.lithology == 4 || cell.lithology == 2 || cell.sediment_thickness_m > 1.4) {
            cell.resource = aridity < 0.45 ? 4 : 3;
        } else if (cell.is_river && cell.boundary_convergent > 0.16) {
            cell.resource = 5;
        } else if (cell.boundary_divergent > 0.42 || (cell.lithology == 5 && cell.temperature_c > 0.0)) {
            cell.resource = 6;
        } else if (cell.soil_type == 3 && cell.fertility > 0.62) {
            cell.resource = 7;
        } else {
            cell.resource = 0;
        }
        const double water_access = cell.is_river ? 1.0 : (cell.is_lake ? 0.85 : (coast ? 0.78 : clamp(cell.runoff_mm_y / 550.0, 0.0, 0.55)));
        const double climate_score = clamp(1.0 - std::abs(cell.temperature_c - 17.0) / 31.0, 0.0, 1.0);
        const double resource_score = cell.resource == 0 ? 0.0 : 0.18;
        const double hazard = clamp(cell.boundary_convergent * 0.28 + cell.boundary_transform * 0.18 +
            slope_penalty * 0.24 + clamp(cell.ice_thickness_m / 2200.0, 0.0, 1.0) * 0.22, 0.0, 0.65);
        cell.settlement_score = clamp(0.38 * water_access + 0.30 * cell.fertility + 0.18 * climate_score + resource_score - hazard, 0.0, 1.0);
        if (cell.biome == 3 || cell.biome == 4 || cell.biome == 14 || cell.biome == 0) {
            cell.settlement_score *= 0.18;
        }
    }
}

void derive_landforms(std::vector<Cell>& cells) {
    const int n = static_cast<int>(cells.size());
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        Cell& cell = cells[i];
        const double relief = local_relief(cells, i);
        const double pet = std::max(1.0, (cell.temperature_c + 8.0) * 31.0);
        const double aridity = cell.precipitation_mm_y / pet;
        const bool coast = has_ocean_neighbor(cells, i);
        const bool flows_to_water = cell.flow_to >= 0 && cells[cell.flow_to].is_water;
        const bool flows_to_lake = cell.flow_to >= 0 && cells[cell.flow_to].is_lake;
        const bool glacier_neighbor = has_glacier_neighbor(cells, i);

        if (cell.is_water) {
            if (glacier_neighbor && cell.water_depth_m < 1200.0 && (cell.water_body == 2 || cell.water_body == 3)) {
                cell.landform = 16;
            } else if (cell.boundary_convergent > 0.38 && cell.water_depth_m > 700.0) {
                cell.landform = 9;
            } else if (cell.water_body == 2) {
                cell.landform = 1;
            } else if (cell.water_body == 3) {
                cell.landform = 2;
            } else {
                cell.landform = 0;
            }
            continue;
        }

        if (cell.is_lake) {
            cell.landform = glacier_neighbor ? 19 : (cell.water_body == 5 ? 4 : 3);
        } else if (cell.is_closed_basin || cell.water_body == 5) {
            cell.landform = cell.water_body == 5 ? 4 : 3;
        } else if (cell.ice_thickness_m > 180.0 || cell.biome == 3) {
            cell.landform = 5;
        } else if (cell.glacial_erosion_m > 8.0 && relief > 320.0) {
            cell.landform = 17;
        } else if (glacier_neighbor && cell.sediment_thickness_m > 0.35 && cell.elevation_m > 120.0) {
            cell.landform = 18;
        } else if (cell.is_river && cell.elevation_m < 180.0 && (coast || flows_to_water || flows_to_lake) &&
            cell.sediment_thickness_m > 0.6) {
            cell.landform = 12;
        } else if (cell.is_river && aridity < 0.78 && relief > 420.0 && cell.sediment_thickness_m > 0.35) {
            cell.landform = 13;
        } else if (cell.is_river && relief < 360.0 && cell.sediment_thickness_m > 0.45) {
            cell.landform = 11;
        } else if (cell.is_river) {
            cell.landform = 10;
        } else if (cell.crust_type == 5 || (cell.elevation_m > 1600.0 && relief > 430.0)) {
            cell.landform = 6;
        } else if (cell.crust_type == 3 || (cell.lithology == 5 && cell.boundary_convergent > 0.22)) {
            cell.landform = 7;
        } else if (cell.crust_type == 6 || (cell.boundary_divergent > 0.36 && cell.elevation_m < 900.0)) {
            cell.landform = 8;
        } else if (coast && cell.elevation_m < 240.0 && relief < 300.0) {
            cell.landform = 14;
        } else {
            cell.landform = 15;
        }

        if (cell.landform == 12 || cell.landform == 11) {
            cell.soil_type = 3;
            cell.fertility = clamp(cell.fertility + (cell.landform == 12 ? 0.16 : 0.10), 0.0, 1.0);
            if (cell.precipitation_mm_y > 500.0 && cell.biome != 3) {
                cell.biome = 15;
            }
            if (cell.fertility > 0.64) {
                cell.resource = 7;
            }
            cell.settlement_score = clamp(cell.settlement_score + 0.08, 0.0, 1.0);
        } else if (cell.landform == 13) {
            cell.soil_type = cell.soil_type == 8 ? cell.soil_type : 4;
            if (cell.resource == 0 && cell.boundary_convergent > 0.10) {
                cell.resource = 5;
            }
            cell.settlement_score = clamp(cell.settlement_score + 0.03, 0.0, 1.0);
        } else if (cell.landform == 4) {
            cell.soil_type = 10;
            cell.resource = 4;
            cell.settlement_score *= 0.55;
        } else if (cell.landform == 17 || cell.landform == 18 || cell.landform == 19) {
            if (cell.landform != 19) {
                cell.soil_type = 8;
            }
            cell.settlement_score *= cell.landform == 19 ? 0.72 : 0.42;
        } else if (cell.landform == 14 && cell.settlement_score > 0.0) {
            cell.settlement_score = clamp(cell.settlement_score + 0.04, 0.0, 1.0);
        }
    }
}

double coastal_edge_length_km(const Params& params, const std::vector<Cell>& cells, int i) {
    double length_km = 0.0;
    for (int neighbor_id : cells[i].neighbors) {
        if (cells[neighbor_id].is_water) {
            length_km += neighbor_distance_m(params, cells[i], cells[neighbor_id]) / 1000.0;
        }
    }
    return length_km;
}

double coastal_sediment_supply(const std::vector<Cell>& cells, int i) {
    const Cell& cell = cells[i];
    double supply = 0.20 * clamp(cell.sediment_thickness_m / 3.0, 0.0, 1.0);
    if (cell.is_river) {
        supply += 0.34;
    }
    if (cell.landform == 12 || cell.landform == 11 || cell.landform == 14) {
        supply += 0.20;
    }
    for (int neighbor_id : cell.neighbors) {
        const Cell& neighbor = cells[neighbor_id];
        if (neighbor.is_river) {
            supply += 0.08;
        }
        if (neighbor.landform == 12 || neighbor.landform == 11) {
            supply += 0.07;
        }
        supply += 0.03 * clamp(neighbor.sediment_thickness_m / 3.0, 0.0, 1.0);
    }
    return clamp(supply, 0.0, 1.0);
}

double coastal_wave_energy(const std::vector<Cell>& cells, int i) {
    const Cell& cell = cells[i];
    const double current_strength = std::sqrt(
        cell.ocean_current_east * cell.ocean_current_east +
        cell.ocean_current_north * cell.ocean_current_north
    );
    double exposure = 0.0;
    for (int neighbor_id : cell.neighbors) {
        if (cells[neighbor_id].is_water) {
            exposure += 1.0;
        }
    }
    exposure /= std::max(1.0, static_cast<double>(cell.neighbors.size()));
    const double tectonic = clamp(cell.boundary_convergent + 0.5 * cell.boundary_transform, 0.0, 1.0);
    return clamp(0.22 + 0.40 * exposure + 0.24 * current_strength + 0.14 * tectonic, 0.0, 1.0);
}

int coastal_feature_type_for_cell(const std::vector<Cell>& cells, int i, double sediment_supply, double wave_energy) {
    const Cell& cell = cells[i];
    const double relief = local_relief(cells, i);
    if (cell.landform == 12 || (cell.is_river && sediment_supply > 0.58 && cell.elevation_m < 120.0)) {
        return 3;
    }
    if ((cell.landform == 11 || cell.biome == 15) && sediment_supply > 0.42 && wave_energy < 0.55) {
        return 4;
    }
    if (sediment_supply > 0.56 && wave_energy > 0.48 && cell.elevation_m < 90.0) {
        return 2;
    }
    if (sediment_supply > 0.30 && wave_energy > 0.34 && cell.elevation_m < 260.0) {
        return 1;
    }
    if (relief > 650.0 || (cell.elevation_m > 180.0 && wave_energy > 0.62 && sediment_supply < 0.45)) {
        return 5;
    }
    return 0;
}

double coastal_longshore_transport_index(const Cell& cell, double sediment_supply, double wave_energy) {
    const double current_strength = std::sqrt(
        cell.ocean_current_east * cell.ocean_current_east +
        cell.ocean_current_north * cell.ocean_current_north
    );
    return clamp(0.18 + 0.46 * wave_energy + 0.24 * current_strength + 0.12 * sediment_supply, 0.0, 1.0);
}

double coastal_migration_rate_m_y(int feature_type, double sediment_supply, double wave_energy, double longshore_transport) {
    double rate = 1.55 * sediment_supply - 1.05 * wave_energy + 0.28 * longshore_transport;
    if (feature_type == 3) {
        rate += 0.62;
    } else if (feature_type == 1 || feature_type == 2) {
        rate += 0.18 * sediment_supply - 0.24 * wave_energy;
    } else if (feature_type == 5) {
        rate -= 0.55;
    }
    return clamp(rate, -2.5, 4.0);
}

int shoreline_trend_for_feature(int feature_type, double sediment_supply, double wave_energy, double migration_rate) {
    if (feature_type == 3 && sediment_supply > 0.55 && migration_rate > 0.45) {
        return 4;
    }
    if ((feature_type == 1 || feature_type == 2) && wave_energy > 0.56 && migration_rate < 0.25) {
        return 3;
    }
    if (migration_rate > 0.34) {
        return 1;
    }
    if (migration_rate < -0.28 || (feature_type == 5 && wave_energy > 0.58)) {
        return 2;
    }
    return 0;
}

std::vector<CoastalFeature> generate_coastal_features(const Params& params, const std::vector<Cell>& cells) {
    std::vector<CoastalFeature> features;
    for (const Cell& cell : cells) {
        if (cell.is_water || !has_ocean_neighbor(cells, cell.id)) {
            continue;
        }
        const double length_km = coastal_edge_length_km(params, cells, cell.id);
        if (length_km <= 0.0) {
            continue;
        }
        const double sediment_supply = coastal_sediment_supply(cells, cell.id);
        const double wave_energy = coastal_wave_energy(cells, cell.id);
        CoastalFeature feature;
        feature.id = static_cast<int>(features.size());
        feature.cell_id = cell.id;
        feature.type = coastal_feature_type_for_cell(cells, cell.id, sediment_supply, wave_energy);
        feature.lat_deg = cell.lat * DEG;
        feature.lon_deg = cell.lon * DEG;
        feature.length_km = length_km;
        feature.sediment_supply_index = sediment_supply;
        feature.wave_energy_index = wave_energy;
        feature.progradation_index = clamp((sediment_supply + (feature.type == 3 ? 0.22 : 0.0)) / (0.55 + wave_energy), 0.0, 1.0);
        feature.longshore_transport_index = coastal_longshore_transport_index(cell, sediment_supply, wave_energy);
        feature.migration_rate_m_y = coastal_migration_rate_m_y(
            feature.type,
            sediment_supply,
            wave_energy,
            feature.longshore_transport_index
        );
        feature.shoreline_trend = shoreline_trend_for_feature(
            feature.type,
            sediment_supply,
            wave_energy,
            feature.migration_rate_m_y
        );
        features.push_back(feature);
    }
    return features;
}

int sedimentary_basin_type_for_cell(const std::vector<Cell>& cells, const Cell& cell) {
    if (cell.landform == 4 || cell.water_body == 5 || cell.resource == 4) {
        return 4;
    }
    if (cell.landform == 3 || cell.is_lake || cell.is_closed_basin) {
        return 3;
    }
    if (cell.landform == 12 || (cell.is_river && has_ocean_neighbor(cells, cell.id))) {
        return 5;
    }
    if (cell.crust_type == 6 || cell.boundary_divergent > 0.32) {
        return 0;
    }
    if (cell.boundary_convergent > 0.24 && cell.sediment_thickness_m > 0.30) {
        return 1;
    }
    return 2;
}

bool is_sedimentary_basin_cell(const std::vector<Cell>& cells, const Cell& cell) {
    if (cell.is_water || cell.basin_id < 0 || cell.basin_id >= static_cast<int>(cells.size())) {
        return false;
    }
    return cell.crust_type == 7 || cell.crust_type == 6 || cell.sediment_thickness_m > 0.55 ||
        cell.landform == 3 || cell.landform == 4 || cell.landform == 8 ||
        cell.landform == 11 || cell.landform == 12 || cell.landform == 14;
}

std::vector<SedimentaryBasin> generate_sedimentary_basins(const std::vector<Cell>& cells) {
    std::map<int, SedimentaryBasin> by_basin;
    std::map<int, std::map<int, int>> type_counts;
    std::map<int, std::map<int, int>> resource_counts;
    std::map<int, double> weighted_crust_age;
    std::map<int, int> active_cells;
    for (const Cell& cell : cells) {
        if (!is_sedimentary_basin_cell(cells, cell)) {
            continue;
        }
        SedimentaryBasin& basin = by_basin[cell.basin_id];
        basin.basin_id = cell.basin_id;
        basin.cell_count += 1;
        basin.area_km2 += cell.area_km2;
        basin.mean_sediment_thickness_m += cell.sediment_thickness_m * cell.area_km2;
        basin.max_sediment_thickness_m = std::max(basin.max_sediment_thickness_m, cell.sediment_thickness_m);
        const double subsidence = clamp(
            0.20 + 0.42 * cell.boundary_divergent + 0.22 * (cell.crust_type == 7 ? 1.0 : 0.0) +
                0.16 * clamp(cell.sediment_thickness_m / 3.5, 0.0, 1.0),
            0.0,
            1.0
        );
        basin.mean_subsidence_index += subsidence * cell.area_km2;
        weighted_crust_age[cell.basin_id] += cell.crust_age_ma * cell.area_km2;
        type_counts[cell.basin_id][sedimentary_basin_type_for_cell(cells, cell)]++;
        if (cell.resource != 0) {
            resource_counts[cell.basin_id][cell.resource]++;
        }
        if (cell.is_river || cell.is_lake || has_ocean_neighbor(cells, cell.id) || cell.sediment_thickness_m > 0.9) {
            active_cells[cell.basin_id] += 1;
        }
    }

    std::vector<SedimentaryBasin> basins;
    basins.reserve(by_basin.size());
    for (auto& [basin_id, basin] : by_basin) {
        if (basin.cell_count <= 0 || basin.area_km2 <= 0.0) {
            continue;
        }
        basin.mean_sediment_thickness_m /= basin.area_km2;
        basin.mean_subsidence_index /= basin.area_km2;
        const double mean_crust_age = weighted_crust_age[basin_id] / basin.area_km2;
        basin.depositional_age_ma = clamp(
            1.5 + 0.045 * mean_crust_age + 10.0 / (1.0 + basin.mean_sediment_thickness_m),
            0.1,
            320.0
        );
        basin.is_active = active_cells[basin_id] > 0;

        int best_type = 2;
        int best_type_count = -1;
        for (const auto& [type, count] : type_counts[basin_id]) {
            if (count > best_type_count) {
                best_type = type;
                best_type_count = count;
            }
        }
        basin.type = best_type;

        int best_resource = 0;
        int best_resource_count = -1;
        for (const auto& [resource, count] : resource_counts[basin_id]) {
            if (count > best_resource_count) {
                best_resource = resource;
                best_resource_count = count;
            }
        }
        basin.dominant_resource = best_resource_count < 0 ? 0 : best_resource;
        basins.push_back(basin);
    }
    std::sort(basins.begin(), basins.end(), [](const SedimentaryBasin& a, const SedimentaryBasin& b) {
        if (a.area_km2 == b.area_km2) {
            return a.basin_id < b.basin_id;
        }
        return a.area_km2 > b.area_km2;
    });
    for (int i = 0; i < static_cast<int>(basins.size()); ++i) {
        basins[static_cast<std::size_t>(i)].id = i;
    }
    return basins;
}

int sequence_phase_for_basin(const SedimentaryBasin& basin) {
    if (!basin.is_active && basin.mean_sediment_thickness_m < 0.35) {
        return 4;
    }
    if (basin.type == 4) {
        return 3;
    }
    if (basin.type == 5) {
        return 1;
    }
    if (basin.type == 2 && basin.is_active) {
        return 2;
    }
    return 0;
}

int stratigraphic_facies_for_layer(
    const SedimentaryBasin& basin,
    const Cell& representative,
    int layer_index,
    int layer_count
) {
    const double position = layer_count <= 1 ? 1.0 : static_cast<double>(layer_index) / static_cast<double>(layer_count - 1);
    if (representative.ice_thickness_m > 25.0 || representative.landform == 18 || representative.landform == 19) {
        return layer_index == layer_count - 1 ? 8 : 4;
    }
    if (basin.type == 0) {
        return position < 0.34 ? 0 : (position < 0.70 ? 4 : 1);
    }
    if (basin.type == 1) {
        return position < 0.42 ? 0 : (position < 0.76 ? 2 : 1);
    }
    if (basin.type == 2) {
        return position < 0.34 ? 7 : (position < 0.72 ? 6 : 3);
    }
    if (basin.type == 3) {
        return position < 0.72 ? 4 : 2;
    }
    if (basin.type == 4) {
        return position < 0.45 ? 4 : 5;
    }
    if (basin.type == 5) {
        return position < 0.35 ? 1 : (position < 0.76 ? 3 : 6);
    }
    return 2;
}

double facies_grain_size(int facies) {
    switch (facies) {
        case 0: return 0.78;
        case 1: return 0.58;
        case 2: return 0.22;
        case 3: return 0.48;
        case 4: return 0.18;
        case 5: return 0.06;
        case 6: return 0.34;
        case 7: return 0.16;
        case 8: return 0.66;
        default: return 0.35;
    }
}

double facies_organic_potential(int facies) {
    switch (facies) {
        case 3: return 0.58;
        case 4: return 0.64;
        case 7: return 0.50;
        case 2: return 0.32;
        case 6: return 0.24;
        default: return 0.12;
    }
}

double facies_seal_quality(int facies) {
    switch (facies) {
        case 5: return 0.92;
        case 4: return 0.76;
        case 7: return 0.70;
        case 2: return 0.64;
        case 6: return 0.42;
        default: return 0.22;
    }
}

std::vector<StratigraphicColumn> generate_stratigraphic_columns(
    const std::vector<Cell>& cells,
    const std::vector<SedimentaryBasin>& basins
) {
    std::map<int, int> representative_cell;
    std::map<int, double> representative_sediment;
    std::map<int, double> runoff_sum;
    std::map<int, double> area_sum;
    std::map<int, int> river_cell_count;
    for (const Cell& cell : cells) {
        if (cell.basin_id < 0) {
            continue;
        }
        const double previous = representative_sediment.count(cell.basin_id) > 0 ?
            representative_sediment[cell.basin_id] :
            -1.0;
        if (cell.sediment_thickness_m > previous) {
            representative_sediment[cell.basin_id] = cell.sediment_thickness_m;
            representative_cell[cell.basin_id] = cell.id;
        }
        runoff_sum[cell.basin_id] += cell.runoff_mm_y * cell.area_km2;
        area_sum[cell.basin_id] += cell.area_km2;
        if (cell.is_river) {
            river_cell_count[cell.basin_id] += 1;
        }
    }

    std::vector<StratigraphicColumn> columns;
    for (const SedimentaryBasin& basin : basins) {
        if (basin.cell_count <= 0) {
            continue;
        }
        StratigraphicColumn column;
        column.id = static_cast<int>(columns.size());
        column.basin_id = basin.basin_id;
        column.representative_cell_id = representative_cell.count(basin.basin_id) > 0 ?
            representative_cell[basin.basin_id] :
            basin.basin_id;
        if (column.representative_cell_id < 0 || column.representative_cell_id >= static_cast<int>(cells.size())) {
            column.representative_cell_id = basin.basin_id >= 0 && basin.basin_id < static_cast<int>(cells.size()) ?
                basin.basin_id :
                0;
        }
        const Cell& representative = cells[column.representative_cell_id];
        const double area = std::max(1.0, area_sum[basin.basin_id]);
        const double mean_runoff = runoff_sum[basin.basin_id] / area;
        const double river_fraction = static_cast<double>(river_cell_count[basin.basin_id]) /
            std::max(1.0, static_cast<double>(basin.cell_count));
        column.is_active = basin.is_active;
        column.sequence_phase = sequence_phase_for_basin(basin);
        column.total_thickness_m = std::max(
            0.05,
            0.55 * basin.max_sediment_thickness_m + 0.45 * basin.mean_sediment_thickness_m
        );
        column.depositional_span_ma = clamp(
            basin.depositional_age_ma * (0.45 + 0.45 * basin.mean_subsidence_index),
            0.05,
            std::max(0.05, basin.depositional_age_ma)
        );
        column.mean_subsidence_index = basin.mean_subsidence_index;
        column.sediment_flux_index = clamp(
            0.20 + 0.24 * clamp(mean_runoff / 1200.0, 0.0, 1.4) +
                0.28 * clamp(basin.mean_sediment_thickness_m / 4.0, 0.0, 1.3) +
                0.22 * river_fraction + 0.16 * basin.mean_subsidence_index,
            0.0,
            1.0
        );
        column.preservation_potential = clamp(
            0.22 + 0.44 * basin.mean_subsidence_index +
                0.20 * clamp(column.total_thickness_m / 4.0, 0.0, 1.0) +
                (basin.is_active ? 0.08 : -0.04) -
                0.10 * clamp(local_relief(cells, representative.id) / 900.0, 0.0, 1.0),
            0.0,
            1.0
        );

        const int layer_count = clamp(
            2 + static_cast<int>(column.total_thickness_m / 1.15) + (basin.is_active ? 1 : 0),
            2,
            5
        );
        const double top_age = basin.is_active ? 0.0 : clamp(basin.depositional_age_ma - column.depositional_span_ma, 0.0, basin.depositional_age_ma);
        double weight_sum = 0.0;
        std::vector<double> weights(static_cast<std::size_t>(layer_count), 1.0);
        for (int i = 0; i < layer_count; ++i) {
            const double upward = static_cast<double>(i + 1) / static_cast<double>(layer_count);
            weights[static_cast<std::size_t>(i)] = 0.70 + upward * (column.sequence_phase == 1 ? 0.70 : 0.30);
            if (column.sequence_phase == 2) {
                weights[static_cast<std::size_t>(i)] = 1.35 - 0.45 * upward;
            } else if (column.sequence_phase == 3) {
                weights[static_cast<std::size_t>(i)] = 0.95 - 0.18 * upward;
            }
            weight_sum += weights[static_cast<std::size_t>(i)];
        }

        std::map<int, double> facies_thickness;
        for (int i = 0; i < layer_count; ++i) {
            StratigraphicLayer layer;
            layer.index = i;
            layer.facies = stratigraphic_facies_for_layer(basin, representative, i, layer_count);
            layer.thickness_m = column.total_thickness_m * weights[static_cast<std::size_t>(i)] / std::max(0.001, weight_sum);
            const double base_fraction = static_cast<double>(i) / static_cast<double>(layer_count);
            const double top_fraction = static_cast<double>(i + 1) / static_cast<double>(layer_count);
            layer.age_base_ma = basin.depositional_age_ma - column.depositional_span_ma * base_fraction;
            layer.age_top_ma = basin.depositional_age_ma - column.depositional_span_ma * top_fraction;
            if (i == layer_count - 1) {
                layer.age_top_ma = top_age;
            }
            layer.grain_size_index = facies_grain_size(layer.facies);
            layer.organic_potential = clamp(
                facies_organic_potential(layer.facies) +
                    (basin.dominant_resource == 3 ? 0.20 : 0.0) +
                    0.10 * column.preservation_potential,
                0.0,
                1.0
            );
            layer.seal_quality = clamp(
                facies_seal_quality(layer.facies) +
                    (basin.dominant_resource == 4 ? 0.18 : 0.0),
                0.0,
                1.0
            );
            layer.reservoir_quality = clamp(
                0.18 + 0.68 * layer.grain_size_index + 0.14 * column.sediment_flux_index - 0.34 * layer.seal_quality,
                0.0,
                1.0
            );
            facies_thickness[layer.facies] += layer.thickness_m;
            column.layers.push_back(layer);
        }

        int dominant_facies = column.layers.empty() ? 2 : column.layers.front().facies;
        double dominant_thickness = -1.0;
        for (const auto& [facies, thickness] : facies_thickness) {
            if (thickness > dominant_thickness) {
                dominant_facies = facies;
                dominant_thickness = thickness;
            }
        }
        column.dominant_facies = dominant_facies;
        columns.push_back(column);
    }
    return columns;
}

int nearest_neighbor_ice_sheet(const std::vector<Cell>& cells, const Cell& cell) {
    int best_sheet = -1;
    double best_score = -1.0;
    for (int neighbor_id : cell.neighbors) {
        const Cell& neighbor = cells[neighbor_id];
        if (neighbor.ice_sheet_id >= 0) {
            const double score = neighbor.ice_thickness_m + 0.8 * neighbor.glacial_erosion_m;
            if (score > best_score) {
                best_score = score;
                best_sheet = neighbor.ice_sheet_id;
            }
        }
    }
    return best_sheet;
}

int retreat_stage_for_ice_sheet(const IceSheet& sheet) {
    if (sheet.cell_count <= 0) {
        return 4;
    }
    if (sheet.max_ice_thickness_m < 80.0) {
        return 4;
    }
    if (sheet.accumulation_area_fraction < 0.28) {
        return 2;
    }
    if (sheet.moraine_cell_count > sheet.cell_count / 4 && sheet.accumulation_area_fraction < 0.52) {
        return 3;
    }
    if (sheet.accumulation_area_fraction > 0.66 && sheet.mean_ice_thickness_m > 420.0) {
        return 0;
    }
    return 1;
}

std::vector<IceSheet> generate_ice_sheets(std::vector<Cell>& cells) {
    for (Cell& cell : cells) {
        cell.ice_sheet_id = -1;
        cell.moraine_deposition_m = 0.0;
        cell.deglaciation_age_ka = 0.0;
    }

    std::vector<IceSheet> sheets;
    const int n = static_cast<int>(cells.size());
    std::vector<char> visited(static_cast<std::size_t>(n), 0);
    for (int i = 0; i < n; ++i) {
        if (visited[static_cast<std::size_t>(i)] || cells[i].ice_thickness_m <= 25.0 || cells[i].is_water) {
            continue;
        }
        IceSheet sheet;
        sheet.id = static_cast<int>(sheets.size());
        std::queue<int> queue;
        queue.push(i);
        visited[static_cast<std::size_t>(i)] = 1;
        std::vector<double> elevations;
        while (!queue.empty()) {
            const int current = queue.front();
            queue.pop();
            Cell& cell = cells[current];
            cell.ice_sheet_id = sheet.id;
            sheet.cell_count += 1;
            sheet.area_km2 += cell.area_km2;
            sheet.mean_ice_thickness_m += cell.ice_thickness_m * cell.area_km2;
            sheet.max_ice_thickness_m = std::max(sheet.max_ice_thickness_m, cell.ice_thickness_m);
            sheet.mean_glacial_erosion_m += cell.glacial_erosion_m * cell.area_km2;
            sheet.mean_surface_mass_balance_m_y += cell.ice_surface_mass_balance_m_y * cell.area_km2;
            sheet.mean_basal_sliding_index += cell.basal_sliding_index * cell.area_km2;
            sheet.mean_ice_velocity_m_y += cell.ice_velocity_m_y * cell.area_km2;
            if (cell.precipitation_mm_y > 260.0 && cell.temperature_c < -1.0) {
                sheet.accumulation_area_fraction += cell.area_km2;
            }
            elevations.push_back(cell.elevation_m);
            for (int neighbor_id : cell.neighbors) {
                if (!visited[static_cast<std::size_t>(neighbor_id)] &&
                    !cells[neighbor_id].is_water &&
                    cells[neighbor_id].ice_thickness_m > 25.0) {
                    visited[static_cast<std::size_t>(neighbor_id)] = 1;
                    queue.push(neighbor_id);
                }
            }
        }
        if (sheet.area_km2 > 0.0) {
            sheet.mean_ice_thickness_m /= sheet.area_km2;
            sheet.mean_glacial_erosion_m /= sheet.area_km2;
            sheet.mean_surface_mass_balance_m_y /= sheet.area_km2;
            sheet.mean_basal_sliding_index /= sheet.area_km2;
            sheet.mean_ice_velocity_m_y /= sheet.area_km2;
            sheet.accumulation_area_fraction /= sheet.area_km2;
        }
        if (!elevations.empty()) {
            std::sort(elevations.begin(), elevations.end());
            sheet.equilibrium_line_altitude_m = elevations[static_cast<std::size_t>(0.42 * (elevations.size() - 1))];
        }
        sheets.push_back(sheet);
    }

    for (Cell& cell : cells) {
        if (cell.ice_sheet_id < 0 && (cell.landform == 18 || cell.landform == 17 || cell.landform == 19 ||
            (cell.ice_thickness_m <= 25.0 && has_glacier_neighbor(cells, cell.id, 25.0)))) {
            cell.ice_sheet_id = nearest_neighbor_ice_sheet(cells, cell);
        }
        if (cell.ice_sheet_id >= 0 && cell.ice_thickness_m <= 25.0) {
            const double cold_memory = clamp((-cell.temperature_c + 4.0) / 18.0, 0.0, 1.0);
            const double erosion_memory = clamp(cell.glacial_erosion_m / 18.0, 0.0, 1.0);
            const double sediment_memory = clamp(cell.sediment_thickness_m / 2.5, 0.0, 1.0);
            cell.deglaciation_age_ka = clamp(2.0 + 80.0 * cold_memory + 22.0 * erosion_memory, 0.0, 120.0);
            if (cell.landform == 18 || has_glacier_neighbor(cells, cell.id, 25.0)) {
                cell.moraine_deposition_m = clamp(0.18 + 1.4 * sediment_memory + 0.18 * local_relief(cells, cell.id) / 700.0, 0.0, 4.0);
            }
        }
    }

    std::vector<double> sheet_deglaciation_sum(sheets.size(), 0.0);
    std::vector<double> sheet_moraine_sum(sheets.size(), 0.0);
    std::vector<int> sheet_deglaciation_count(sheets.size(), 0);
    for (const Cell& cell : cells) {
        if (cell.ice_sheet_id < 0 || cell.ice_sheet_id >= static_cast<int>(sheets.size())) {
            continue;
        }
        IceSheet& sheet = sheets[static_cast<std::size_t>(cell.ice_sheet_id)];
        if (cell.moraine_deposition_m > 0.0 || cell.landform == 18) {
            sheet.moraine_cell_count += 1;
            sheet_moraine_sum[static_cast<std::size_t>(cell.ice_sheet_id)] += cell.moraine_deposition_m;
        }
        if (cell.deglaciation_age_ka > 0.0) {
            sheet_deglaciation_sum[static_cast<std::size_t>(cell.ice_sheet_id)] += cell.deglaciation_age_ka;
            sheet_deglaciation_count[static_cast<std::size_t>(cell.ice_sheet_id)] += 1;
        }
    }
    for (IceSheet& sheet : sheets) {
        if (sheet.moraine_cell_count > 0) {
            sheet.mean_moraine_deposition_m = sheet_moraine_sum[static_cast<std::size_t>(sheet.id)] /
                static_cast<double>(sheet.moraine_cell_count);
        }
        if (sheet_deglaciation_count[static_cast<std::size_t>(sheet.id)] > 0) {
            sheet.mean_deglaciation_age_ka = sheet_deglaciation_sum[static_cast<std::size_t>(sheet.id)] /
                static_cast<double>(sheet_deglaciation_count[static_cast<std::size_t>(sheet.id)]);
        }
        sheet.retreat_rate_m_y = clamp(
            4.0 + 42.0 * std::max(0.0, 0.45 - sheet.accumulation_area_fraction) +
                16.0 * sheet.mean_basal_sliding_index -
                22.0 * sheet.mean_surface_mass_balance_m_y,
            0.0,
            120.0
        );
        sheet.retreat_stage = retreat_stage_for_ice_sheet(sheet);
    }
    std::sort(sheets.begin(), sheets.end(), [](const IceSheet& a, const IceSheet& b) {
        if (a.area_km2 == b.area_km2) {
            return a.id < b.id;
        }
        return a.area_km2 > b.area_km2;
    });
    std::vector<int> remap(sheets.size(), -1);
    for (int new_id = 0; new_id < static_cast<int>(sheets.size()); ++new_id) {
        remap[static_cast<std::size_t>(sheets[static_cast<std::size_t>(new_id)].id)] = new_id;
        sheets[static_cast<std::size_t>(new_id)].id = new_id;
    }
    for (Cell& cell : cells) {
        if (cell.ice_sheet_id >= 0 && cell.ice_sheet_id < static_cast<int>(remap.size())) {
            cell.ice_sheet_id = remap[static_cast<std::size_t>(cell.ice_sheet_id)];
        }
    }
    return sheets;
}

int settlement_type_for_cell(const std::vector<Cell>& cells, const Cell& cell) {
    const bool coast = has_ocean_neighbor(cells, cell.id);
    if (coast) {
        return 1;
    }
    if (cell.is_river) {
        return 0;
    }
    if (cell.resource == 1 || cell.resource == 2 || cell.resource == 5 || cell.resource == 6) {
        return 2;
    }
    if (cell.fertility > 0.66 || cell.resource == 7) {
        return 3;
    }
    if ((cell.biome == 9 || cell.biome == 10) && (cell.runoff_mm_y > 120.0 || cell.is_lake)) {
        return 4;
    }
    return 5;
}

std::vector<Settlement> generate_settlements(const Params& params, const std::vector<Cell>& cells) {
    std::vector<int> candidates;
    candidates.reserve(cells.size() / 8);
    for (const Cell& cell : cells) {
        if (cell.is_water || cell.settlement_score < 0.48) {
            continue;
        }
        bool local_max = true;
        for (int neighbor : cell.neighbors) {
            if (!cells[neighbor].is_water && cells[neighbor].settlement_score > cell.settlement_score) {
                local_max = false;
                break;
            }
        }
        if (local_max) {
            candidates.push_back(cell.id);
        }
    }
    std::sort(candidates.begin(), candidates.end(), [&](int a, int b) {
        if (cells[a].settlement_score == cells[b].settlement_score) {
            return a < b;
        }
        return cells[a].settlement_score > cells[b].settlement_score;
    });

    const int target = clamp(static_cast<int>(cells.size()) / 180, 8, 64);
    const double min_sep = 2.4 * std::sqrt(4.0 * PI / static_cast<double>(std::max(1, params.cell_count)));
    std::vector<Settlement> settlements;
    for (int cell_id : candidates) {
        bool too_close = false;
        for (const Settlement& settlement : settlements) {
            if (angular_distance(cells[cell_id].p, cells[settlement.cell_id].p) < min_sep) {
                too_close = true;
                break;
            }
        }
        if (too_close) {
            continue;
        }
        Settlement settlement;
        settlement.id = static_cast<int>(settlements.size());
        settlement.cell_id = cell_id;
        settlement.type = settlement_type_for_cell(cells, cells[cell_id]);
        settlement.score = cells[cell_id].settlement_score;
        settlements.push_back(settlement);
        if (static_cast<int>(settlements.size()) >= target) {
            break;
        }
    }
    return settlements;
}

double route_barrier_cost(const Cell& a, const Cell& b) {
    const double mountain = clamp((std::max(a.elevation_m, b.elevation_m) - 1200.0) / 2600.0, 0.0, 1.0);
    const double tectonic_hazard = 0.5 * (a.boundary_convergent + b.boundary_convergent) +
        0.25 * (a.boundary_transform + b.boundary_transform);
    const double arid = (a.biome == 9 || a.biome == 10 || b.biome == 9 || b.biome == 10) ? 0.18 : 0.0;
    return 1.0 + 0.95 * mountain + 0.45 * clamp(tectonic_hazard, 0.0, 1.0) + arid;
}

int route_type_for_pair(const std::vector<Cell>& cells, const Settlement& a, const Settlement& b) {
    const Cell& ca = cells[a.cell_id];
    const Cell& cb = cells[b.cell_id];
    if (a.type == 1 && b.type == 1) {
        return 2;
    }
    if (ca.is_river && cb.is_river && ca.basin_id == cb.basin_id) {
        return 1;
    }
    if (ca.elevation_m > 1300.0 || cb.elevation_m > 1300.0 || ca.boundary_convergent > 0.24 || cb.boundary_convergent > 0.24) {
        return 3;
    }
    return 0;
}

std::vector<Route> generate_routes(const Params& params, const std::vector<Cell>& cells, const std::vector<Settlement>& settlements) {
    std::vector<Route> routes;
    std::set<std::pair<int, int>> used;
    for (const Settlement& settlement : settlements) {
        std::vector<std::pair<double, int>> ranked;
        for (const Settlement& other : settlements) {
            if (settlement.id == other.id) {
                continue;
            }
            const Cell& a = cells[settlement.cell_id];
            const Cell& b = cells[other.cell_id];
            const double distance_km = angular_distance(a.p, b.p) * params.radius_km;
            double cost = distance_km * route_barrier_cost(a, b);
            if (settlement.type == 1 && other.type == 1) {
                cost *= 0.68;
            } else if (a.basin_id == b.basin_id && (a.is_river || b.is_river)) {
                cost *= 0.78;
            }
            ranked.emplace_back(cost, other.id);
        }
        std::sort(ranked.begin(), ranked.end());
        const int links = std::min(2, static_cast<int>(ranked.size()));
        for (int i = 0; i < links; ++i) {
            const int a_id = std::min(settlement.id, ranked[i].second);
            const int b_id = std::max(settlement.id, ranked[i].second);
            if (!used.insert({a_id, b_id}).second) {
                continue;
            }
            const Settlement& from = settlements[static_cast<std::size_t>(a_id)];
            const Settlement& to = settlements[static_cast<std::size_t>(b_id)];
            const double distance_km = angular_distance(cells[from.cell_id].p, cells[to.cell_id].p) * params.radius_km;
            Route route;
            route.id = static_cast<int>(routes.size());
            route.from = a_id;
            route.to = b_id;
            route.type = route_type_for_pair(cells, from, to);
            route.distance_km = distance_km;
            route.cost = distance_km * route_barrier_cost(cells[from.cell_id], cells[to.cell_id]);
            if (route.type == 2) {
                route.cost *= 0.68;
            } else if (route.type == 1) {
                route.cost *= 0.78;
            }
            routes.push_back(route);
        }
    }
    return routes;
}

void derive_lake_overflow_stages(const Params& params, const std::vector<Cell>& cells, LakeBasin& basin) {
    basin.overflow_path_cell_ids.clear();
    basin.overflow_stage_count = 0;
    basin.overflow_path_length_km = 0.0;
    basin.avulsion_risk = 0.0;
    if (!basin.overflows || basin.spill_to_cell_id < 0 ||
        basin.spill_to_cell_id >= static_cast<int>(cells.size())) {
        return;
    }

    std::set<int> seen;
    int current = basin.outlet_cell_id;
    int next = basin.spill_to_cell_id;
    basin.overflow_path_cell_ids.push_back(current);
    for (int step = 0; step < 16; ++step) {
        if (current < 0 || current >= static_cast<int>(cells.size()) ||
            next < 0 || next >= static_cast<int>(cells.size())) {
            break;
        }
        if (!seen.insert(current).second) {
            break;
        }
        basin.overflow_path_length_km += neighbor_distance_m(params, cells[static_cast<std::size_t>(current)],
            cells[static_cast<std::size_t>(next)]) / 1000.0;
        if (basin.overflow_path_cell_ids.empty() || basin.overflow_path_cell_ids.back() != next) {
            basin.overflow_path_cell_ids.push_back(next);
        }
        const Cell& next_cell = cells[static_cast<std::size_t>(next)];
        const bool enters_other_depression = next_cell.depression_component_id >= 0 &&
            next_cell.depression_component_id != basin.depression_component_id;
        if (next_cell.is_water || enters_other_depression ||
            (next_cell.is_lake && next_cell.depression_component_id != basin.depression_component_id)) {
            break;
        }
        current = next;
        next = cells[static_cast<std::size_t>(current)].flow_to;
    }

    basin.overflow_stage_count = std::max(0, static_cast<int>(basin.overflow_path_cell_ids.size()) - 1);
    const double relief = basin.outlet_cell_id >= 0 && basin.outlet_cell_id < static_cast<int>(cells.size()) ?
        local_relief(cells, basin.outlet_cell_id) : 0.0;
    const double pressure = clamp(basin.overflow_index / 4.0, 0.0, 1.0);
    const double short_path = 1.0 / (1.0 + basin.overflow_path_length_km / 180.0);
    const double incision = clamp(basin.max_depression_depth_m / 180.0, 0.0, 1.0);
    const double relief_factor = clamp(relief / 1400.0, 0.0, 1.0);
    basin.avulsion_risk = clamp(0.42 * pressure + 0.24 * short_path + 0.20 * incision + 0.14 * relief_factor, 0.0, 1.0);
}

std::vector<LakeBasin> generate_lake_basins(const Params& params, std::vector<Cell>& cells) {
    for (Cell& cell : cells) {
        cell.lake_basin_id = -1;
    }

    std::map<int, std::vector<int>> depression_cells_by_component;
    for (const Cell& cell : cells) {
        if (!cell.is_water && cell.depression_component_id >= 0) {
            depression_cells_by_component[cell.depression_component_id].push_back(cell.id);
        }
    }

    std::vector<LakeBasin> basins;
    std::map<int, int> basin_by_component;
    for (const auto& [component_id, depression_cell_ids] : depression_cells_by_component) {
        if (depression_cell_ids.empty()) {
            throw std::runtime_error("empty depression component");
        }
        const int sink_id = cells[static_cast<std::size_t>(depression_cell_ids.front())].depression_sink_cell_id;
        if (sink_id < 0 || sink_id >= static_cast<int>(cells.size())) {
            throw std::runtime_error("depression component sink is invalid");
        }
        const Cell& sink = cells[static_cast<std::size_t>(sink_id)];
        LakeBasin basin;
        basin.id = static_cast<int>(basins.size());
        basin.depression_component_id = component_id;
        basin.outlet_cell_id = sink_id;
        basin.spill_to_cell_id = sink.spill_to;
        basin.depression_policy = sink.depression_policy;
        basin.water_body = sink.water_body;
        basin.is_geologic = is_geologic_depression(sink);
        basin.overflows = sink.lake_overflows;
        basin.outlet_elevation_m = sink.elevation_m;
        basin.spill_elevation_m = sink.spill_elevation_m;
        basin.fill_fraction = sink.lake_fill_fraction;
        double geologic_area_km2 = 0.0;
        for (int cell_id : depression_cell_ids) {
            const Cell& cell = cells[static_cast<std::size_t>(cell_id)];
            if (cell.depression_component_id != component_id ||
                cell.depression_sink_cell_id != sink_id ||
                cell.depression_policy != basin.depression_policy) {
                throw std::runtime_error("depression component metadata is inconsistent");
            }
            basin.depression_cell_count++;
            basin.depression_area_km2 += cell.area_km2;
            basin.max_depression_depth_m = std::max(basin.max_depression_depth_m, cell.depression_depth_m);
            basin.storage_capacity_km3 += cell.depression_depth_m * cell.area_km2 / 1000.0;
            if (is_geologic_depression(cell)) {
                geologic_area_km2 += cell.area_km2;
            }
            if (basin.water_body == 0 && cell.water_body != 0) {
                basin.water_body = cell.water_body;
            }
        }
        if (basin.depression_area_km2 > 0.0) {
            basin.geologic_area_fraction = geologic_area_km2 / basin.depression_area_km2;
        }
        basin_by_component[component_id] = basin.id;
        basins.push_back(basin);
    }

    std::vector<double> water_depth_sum(basins.size(), 0.0);
    for (Cell& cell : cells) {
        if (cell.is_water) {
            continue;
        }
        int current = cell.id;
        std::set<int> seen;
        while (current >= 0 && current < static_cast<int>(cells.size())) {
            const int component_id = cells[static_cast<std::size_t>(current)].depression_component_id;
            const auto found = basin_by_component.find(component_id);
            if (found != basin_by_component.end()) {
                LakeBasin& basin = basins[static_cast<std::size_t>(found->second)];
                cell.lake_basin_id = basin.id;
                basin.cell_count += 1;
                basin.area_km2 += cell.area_km2;
                basin.mean_runoff_mm_y += cell.runoff_mm_y * cell.area_km2;
                basin.annual_runoff_km3 += cell.runoff_mm_y * cell.area_km2 * 1.0e-6;
                if (cell.is_lake) {
                    basin.lake_cell_count += 1;
                    basin.lake_area_km2 += cell.area_km2;
                    water_depth_sum[static_cast<std::size_t>(basin.id)] += cell.water_depth_m * cell.area_km2;
                }
                break;
            }
            if (!seen.insert(current).second) {
                break;
            }
            const int next = cells[static_cast<std::size_t>(current)].flow_to;
            if (next < 0 || next >= static_cast<int>(cells.size()) || cells[static_cast<std::size_t>(next)].is_water) {
                break;
            }
            current = next;
        }
    }

    for (LakeBasin& basin : basins) {
        if (basin.area_km2 > 0.0) {
            basin.mean_runoff_mm_y /= basin.area_km2;
        }
        if (basin.lake_area_km2 > 0.0) {
            basin.mean_water_depth_m = water_depth_sum[static_cast<std::size_t>(basin.id)] / basin.lake_area_km2;
        }
        if (basin.overflows) {
            basin.overflow_index = clamp(basin.annual_runoff_km3 / std::max(0.001, basin.storage_capacity_km3), 0.0, 50.0);
        }
        derive_lake_overflow_stages(params, cells, basin);
    }
    return basins;
}

int watershed_outlet_type(const std::vector<Cell>& cells, int basin_id) {
    if (basin_id < 0 || basin_id >= static_cast<int>(cells.size())) {
        return 4;
    }
    const Cell& outlet = cells[basin_id];
    if (outlet.is_lake) {
        return outlet.water_body == 5 ? 2 : 1;
    }
    if (outlet.is_water) {
        if (outlet.water_body == 3) {
            return 3;
        }
        return 0;
    }
    if (outlet.water_body == 5) {
        return 2;
    }
    if (outlet.water_body == 4) {
        return 1;
    }
    return 4;
}

std::vector<LatLon> watershed_boundary_ring(
    const std::vector<Cell>& cells,
    const std::vector<int>& boundary_cell_ids,
    Vec3 weighted_center,
    int max_points
) {
    if (boundary_cell_ids.empty()) {
        return {};
    }
    const Vec3 center = normalize(weighted_center);
    const Vec3 ref = std::abs(center.z) < 0.92 ? Vec3{0.0, 0.0, 1.0} : Vec3{0.0, 1.0, 0.0};
    const Vec3 axis_x = normalize(cross(ref, center));
    const Vec3 axis_y = normalize(cross(center, axis_x));
    std::vector<std::pair<double, int>> ordered;
    ordered.reserve(boundary_cell_ids.size());
    for (int cell_id : boundary_cell_ids) {
        const Cell& cell = cells[cell_id];
        const double angle = std::atan2(dot(cell.p, axis_y), dot(cell.p, axis_x));
        ordered.emplace_back(angle, cell_id);
    }
    std::sort(ordered.begin(), ordered.end());

    const int target = std::min(max_points, static_cast<int>(ordered.size()));
    std::vector<LatLon> ring;
    ring.reserve(static_cast<std::size_t>(target + 1));
    if (target <= 0) {
        return ring;
    }
    for (int k = 0; k < target; ++k) {
        const int index = static_cast<int>(
            std::floor(static_cast<double>(k) * static_cast<double>(ordered.size()) / static_cast<double>(target))
        );
        const Cell& cell = cells[ordered[static_cast<std::size_t>(index)].second];
        ring.push_back({cell.lat * DEG, cell.lon * DEG});
    }
    if (ring.size() > 2) {
        ring.push_back(ring.front());
    }
    return ring;
}

Vec3 latlon_to_vec(const LatLon& point) {
    const double lat = point.lat_deg / DEG;
    const double lon = point.lon_deg / DEG;
    const double c = std::cos(lat);
    return {c * std::cos(lon), c * std::sin(lon), std::sin(lat)};
}

double ring_perimeter_km(const Params& params, const std::vector<LatLon>& ring) {
    if (ring.size() < 2) {
        return 0.0;
    }
    double perimeter = 0.0;
    for (std::size_t i = 1; i < ring.size(); ++i) {
        perimeter += angular_distance(latlon_to_vec(ring[i - 1]), latlon_to_vec(ring[i])) * params.radius_km;
    }
    return perimeter;
}

double ring_projected_area_km2(const Params& params, const std::vector<LatLon>& ring, Vec3 weighted_center) {
    if (ring.size() < 4) {
        return 0.0;
    }
    const Vec3 center = normalize(weighted_center);
    const Vec3 ref = std::abs(center.z) < 0.92 ? Vec3{0.0, 0.0, 1.0} : Vec3{0.0, 1.0, 0.0};
    const Vec3 axis_x = normalize(cross(ref, center));
    const Vec3 axis_y = normalize(cross(center, axis_x));
    std::vector<std::pair<double, double>> points;
    points.reserve(ring.size());
    for (const LatLon& point : ring) {
        const Vec3 p = latlon_to_vec(point);
        const double x = params.radius_km * dot(p, axis_x);
        const double y = params.radius_km * dot(p, axis_y);
        points.push_back({x, y});
    }
    double area = 0.0;
    for (std::size_t i = 1; i < points.size(); ++i) {
        area += points[i - 1].first * points[i].second - points[i].first * points[i - 1].second;
    }
    return std::abs(0.5 * area);
}

std::vector<Watershed> generate_watersheds(const Params& params, const std::vector<Cell>& cells) {
    std::map<int, Watershed> by_basin;
    std::map<int, Vec3> centroid_sum;
    std::map<int, std::vector<int>> watershed_cells;
    std::map<int, std::vector<int>> boundary_cells;
    for (const Cell& cell : cells) {
        if (cell.is_water || cell.basin_id < 0 || cell.basin_id >= static_cast<int>(cells.size())) {
            continue;
        }
        Watershed& watershed = by_basin[cell.basin_id];
        watershed.basin_id = cell.basin_id;
        watershed.outlet_cell_id = cell.basin_id;
        watershed.cell_count += 1;
        watershed.area_km2 += cell.area_km2;
        watershed.mean_runoff_mm_y += cell.runoff_mm_y;
        watershed.mean_elevation_m += cell.elevation_m;
        watershed.max_flow_accumulation = std::max(watershed.max_flow_accumulation, cell.flow_accumulation);
        centroid_sum[cell.basin_id] = add(centroid_sum[cell.basin_id], mul(cell.p, cell.area_km2));
        watershed_cells[cell.basin_id].push_back(cell.id);
        const double lat_deg = cell.lat * DEG;
        if (watershed.cell_count == 1) {
            watershed.min_lat_deg = lat_deg;
            watershed.max_lat_deg = lat_deg;
        } else {
            watershed.min_lat_deg = std::min(watershed.min_lat_deg, lat_deg);
            watershed.max_lat_deg = std::max(watershed.max_lat_deg, lat_deg);
        }
        bool boundary = false;
        for (int neighbor_id : cell.neighbors) {
            const Cell& neighbor = cells[neighbor_id];
            if (neighbor.is_water || neighbor.basin_id != cell.basin_id) {
                boundary = true;
                break;
            }
        }
        if (boundary) {
            boundary_cells[cell.basin_id].push_back(cell.id);
        }
        if (cell.is_river) {
            watershed.river_cell_count += 1;
        }
    }

    std::vector<Watershed> watersheds;
    watersheds.reserve(by_basin.size());
    for (auto& [basin_id, watershed] : by_basin) {
        if (watershed.cell_count <= 0) {
            continue;
        }
        watershed.mean_runoff_mm_y /= static_cast<double>(watershed.cell_count);
        watershed.mean_elevation_m /= static_cast<double>(watershed.cell_count);
        watershed.outlet_type = watershed_outlet_type(cells, basin_id);
        watershed.is_endorheic = watershed.outlet_type != 0;
        const Vec3 center = normalize(centroid_sum[basin_id]);
        watershed.centroid_lat_deg = std::asin(clamp(center.z, -1.0, 1.0)) * DEG;
        watershed.centroid_lon_deg = std::atan2(center.y, center.x) * DEG;
        double min_unwrapped_lon = std::numeric_limits<double>::infinity();
        double max_unwrapped_lon = -std::numeric_limits<double>::infinity();
        const double centroid_lon_rad = watershed.centroid_lon_deg / DEG;
        for (int cell_id : watershed_cells[basin_id]) {
            const double unwrapped = watershed.centroid_lon_deg + wrap_angle(cells[cell_id].lon - centroid_lon_rad) * DEG;
            min_unwrapped_lon = std::min(min_unwrapped_lon, unwrapped);
            max_unwrapped_lon = std::max(max_unwrapped_lon, unwrapped);
        }
        watershed.lon_span_deg = std::max(0.0, max_unwrapped_lon - min_unwrapped_lon);
        watershed.crosses_antimeridian = min_unwrapped_lon < -180.0 || max_unwrapped_lon > 180.0;
        watershed.min_lon_deg = wrap_angle(min_unwrapped_lon / DEG) * DEG;
        watershed.max_lon_deg = wrap_angle(max_unwrapped_lon / DEG) * DEG;
        std::vector<int>& boundary = boundary_cells[basin_id];
        std::sort(boundary.begin(), boundary.end());
        boundary.erase(std::unique(boundary.begin(), boundary.end()), boundary.end());
        watershed.boundary_cell_ids = boundary;
        watershed.boundary_ring = watershed_boundary_ring(cells, watershed.boundary_cell_ids, centroid_sum[basin_id], 64);
        watershed.boundary_perimeter_km = ring_perimeter_km(params, watershed.boundary_ring);
        watershed.dissolved_polygon_area_km2 = ring_projected_area_km2(params, watershed.boundary_ring, centroid_sum[basin_id]);
        if (watershed.area_km2 > 0.0 && watershed.dissolved_polygon_area_km2 > 0.0) {
            watershed.polygon_area_error_fraction = std::abs(watershed.dissolved_polygon_area_km2 - watershed.area_km2) /
                std::max(1.0, watershed.area_km2);
        }
        if (watershed.boundary_perimeter_km > 0.0 && watershed.dissolved_polygon_area_km2 > 0.0) {
            watershed.compactness_index = clamp(
                4.0 * PI * watershed.dissolved_polygon_area_km2 /
                    std::max(1.0, watershed.boundary_perimeter_km * watershed.boundary_perimeter_km),
                0.0,
                1.0
            );
        }
        const double ring_quality = clamp(static_cast<double>(watershed.boundary_ring.size()) / 24.0, 0.0, 1.0);
        const double area_quality = clamp(1.0 - watershed.polygon_area_error_fraction, 0.0, 1.0);
        watershed.geometry_quality = clamp(0.62 * area_quality + 0.38 * ring_quality, 0.0, 1.0);
        watersheds.push_back(watershed);
    }
    std::sort(watersheds.begin(), watersheds.end(), [](const Watershed& a, const Watershed& b) {
        if (a.area_km2 == b.area_km2) {
            return a.basin_id < b.basin_id;
        }
        return a.area_km2 > b.area_km2;
    });
    for (int i = 0; i < static_cast<int>(watersheds.size()); ++i) {
        watersheds[static_cast<std::size_t>(i)].id = i;
    }
    return watersheds;
}

int political_region_type_for_capital(const std::vector<Cell>& cells, const Settlement& capital) {
    const Cell& cell = cells[capital.cell_id];
    if (capital.type == 1) {
        return 1;
    }
    if (capital.type == 0 || cell.is_river) {
        return 0;
    }
    if (capital.type == 2 || cell.resource == 1 || cell.resource == 2 || cell.resource == 5 || cell.resource == 6) {
        return 3;
    }
    if (cell.elevation_m > 1200.0 || cell.landform == 6 || cell.landform == 17) {
        return 2;
    }
    if (capital.type == 3 || cell.fertility > 0.68 || cell.resource == 7) {
        return 4;
    }
    return 5;
}

double settlement_region_cost(
    const Params& params,
    const std::vector<Cell>& cells,
    const Settlement& settlement,
    const Settlement& capital,
    const std::vector<Route>& routes
) {
    const Cell& a = cells[settlement.cell_id];
    const Cell& b = cells[capital.cell_id];
    double cost = angular_distance(a.p, b.p) * params.radius_km * route_barrier_cost(a, b);
    if (a.basin_id == b.basin_id && (a.is_river || b.is_river)) {
        cost *= 0.76;
    }
    if (has_ocean_neighbor(cells, a.id) && has_ocean_neighbor(cells, b.id)) {
        cost *= 0.72;
    }
    for (const Route& route : routes) {
        const bool linked = (route.from == settlement.id && route.to == capital.id) ||
            (route.to == settlement.id && route.from == capital.id);
        if (linked) {
            cost *= route.type == 2 ? 0.45 : 0.58;
            break;
        }
    }
    return cost;
}

void assign_cell_regions(const Params& params, std::vector<Cell>& cells, const std::vector<Settlement>& capitals) {
    if (capitals.empty()) {
        for (Cell& cell : cells) {
            cell.political_region_id = -1;
        }
        return;
    }
#pragma omp parallel for schedule(static)
    for (int i = 0; i < static_cast<int>(cells.size()); ++i) {
        if (cells[i].is_water) {
            cells[i].political_region_id = -1;
            continue;
        }
        double best_cost = std::numeric_limits<double>::infinity();
        int best_region = -1;
        for (const Settlement& capital : capitals) {
            const Cell& capital_cell = cells[capital.cell_id];
            double cost = angular_distance(cells[i].p, capital_cell.p) * params.radius_km * route_barrier_cost(cells[i], capital_cell);
            if (cells[i].basin_id == capital_cell.basin_id && (cells[i].is_river || capital_cell.is_river)) {
                cost *= 0.80;
            }
            if (has_ocean_neighbor(cells, i) && has_ocean_neighbor(cells, capital.cell_id)) {
                cost *= 0.76;
            }
            if (cost < best_cost) {
                best_cost = cost;
                best_region = capital.region_id;
            }
        }
        cells[i].political_region_id = best_region;
    }
}

std::vector<PoliticalRegion> generate_political_regions(
    const Params& params,
    std::vector<Cell>& cells,
    std::vector<Settlement>& settlements,
    const std::vector<Route>& routes
) {
    for (Settlement& settlement : settlements) {
        settlement.region_id = -1;
    }
    for (Cell& cell : cells) {
        cell.political_region_id = -1;
    }
    if (settlements.empty()) {
        return {};
    }

    const int target_regions = clamp(static_cast<int>(settlements.size()) / 5 + 1, 1, std::min(10, static_cast<int>(settlements.size())));
    std::vector<int> capital_indices;
    for (const Settlement& settlement : settlements) {
        bool too_close = false;
        for (int capital_index : capital_indices) {
            const double distance = angular_distance(cells[settlement.cell_id].p, cells[settlements[capital_index].cell_id].p);
            if (distance < 0.18) {
                too_close = true;
                break;
            }
        }
        if (!too_close) {
            capital_indices.push_back(settlement.id);
        }
        if (static_cast<int>(capital_indices.size()) >= target_regions) {
            break;
        }
    }
    if (capital_indices.empty()) {
        capital_indices.push_back(settlements.front().id);
    }

    std::vector<PoliticalRegion> regions;
    regions.reserve(capital_indices.size());
    for (int i = 0; i < static_cast<int>(capital_indices.size()); ++i) {
        Settlement& capital = settlements[capital_indices[static_cast<std::size_t>(i)]];
        capital.region_id = i;
        PoliticalRegion region;
        region.id = i;
        region.capital_settlement_id = capital.id;
        region.type = political_region_type_for_capital(cells, capital);
        regions.push_back(region);
    }

    for (Settlement& settlement : settlements) {
        if (settlement.region_id >= 0) {
            continue;
        }
        double best_cost = std::numeric_limits<double>::infinity();
        int best_region = 0;
        for (const PoliticalRegion& region : regions) {
            const Settlement& capital = settlements[region.capital_settlement_id];
            const double cost = settlement_region_cost(params, cells, settlement, capital, routes);
            if (cost < best_cost) {
                best_cost = cost;
                best_region = region.id;
            }
        }
        settlement.region_id = best_region;
    }

    std::vector<Settlement> capitals;
    for (const PoliticalRegion& region : regions) {
        capitals.push_back(settlements[region.capital_settlement_id]);
    }
    assign_cell_regions(params, cells, capitals);

    std::vector<std::map<int, int>> biome_counts(regions.size());
    std::vector<std::map<int, int>> resource_counts(regions.size());
    for (const Settlement& settlement : settlements) {
        if (settlement.region_id < 0 || settlement.region_id >= static_cast<int>(regions.size())) {
            continue;
        }
        PoliticalRegion& region = regions[settlement.region_id];
        region.settlement_ids.push_back(settlement.id);
        region.settlement_count += 1;
        region.mean_settlement_score += settlement.score;
    }
    for (const Route& route : routes) {
        if (route.from < 0 || route.from >= static_cast<int>(settlements.size()) ||
            route.to < 0 || route.to >= static_cast<int>(settlements.size())) {
            continue;
        }
        const int a = settlements[route.from].region_id;
        const int b = settlements[route.to].region_id;
        if (a >= 0 && a == b && a < static_cast<int>(regions.size())) {
            regions[a].route_count += 1;
        }
    }
    for (const Cell& cell : cells) {
        const int region_id = cell.political_region_id;
        if (region_id < 0 || region_id >= static_cast<int>(regions.size())) {
            continue;
        }
        PoliticalRegion& region = regions[region_id];
        region.area_km2 += cell.area_km2;
        region.mean_elevation_m += cell.elevation_m * cell.area_km2;
        region.barrier_pressure += clamp(local_relief(cells, cell.id) / 1800.0, 0.0, 1.0) * cell.area_km2;
        biome_counts[region_id][cell.biome]++;
        resource_counts[region_id][cell.resource]++;
    }
    for (PoliticalRegion& region : regions) {
        if (region.settlement_count > 0) {
            region.mean_settlement_score /= static_cast<double>(region.settlement_count);
        }
        if (region.area_km2 > 0.0) {
            region.mean_elevation_m /= region.area_km2;
            region.barrier_pressure /= region.area_km2;
        }
        int best_biome = 0;
        int best_biome_count = -1;
        for (const auto& [biome, count] : biome_counts[region.id]) {
            if (count > best_biome_count) {
                best_biome = biome;
                best_biome_count = count;
            }
        }
        region.dominant_biome = best_biome;
        int best_resource = 0;
        int best_resource_count = -1;
        for (const auto& [resource, count] : resource_counts[region.id]) {
            if (resource != 0 && count > best_resource_count) {
                best_resource = resource;
                best_resource_count = count;
            }
        }
        region.dominant_resource = best_resource_count < 0 ? 0 : best_resource;
    }
    return regions;
}

int border_type_for_cells(const Cell& a, const Cell& b) {
    if (a.is_river || b.is_river) {
        return 1;
    }
    if (a.landform == 6 || b.landform == 6 || a.landform == 17 || b.landform == 17 ||
        a.elevation_m > 1400.0 || b.elevation_m > 1400.0) {
        return 2;
    }
    if (a.biome == 9 || a.biome == 10 || b.biome == 9 || b.biome == 10) {
        return 3;
    }
    if (a.landform == 5 || b.landform == 5 || a.biome == 3 || b.biome == 3) {
        return 4;
    }
    if (a.landform == 14 || b.landform == 14) {
        return 5;
    }
    return 0;
}

std::vector<BorderSegment> generate_border_segments(const Params& params, const std::vector<Cell>& cells) {
    std::vector<BorderSegment> borders;
    for (const Cell& cell : cells) {
        if (cell.is_water || cell.political_region_id < 0) {
            continue;
        }
        for (int neighbor_id : cell.neighbors) {
            if (neighbor_id <= cell.id) {
                continue;
            }
            const Cell& neighbor = cells[neighbor_id];
            if (neighbor.is_water || neighbor.political_region_id < 0 || neighbor.political_region_id == cell.political_region_id) {
                continue;
            }
            BorderSegment border;
            border.id = static_cast<int>(borders.size());
            border.region_a = std::min(cell.political_region_id, neighbor.political_region_id);
            border.region_b = std::max(cell.political_region_id, neighbor.political_region_id);
            border.cell_a = cell.id;
            border.cell_b = neighbor.id;
            border.length_km = neighbor_distance_m(params, cell, neighbor) / 1000.0;
            border.type = border_type_for_cells(cell, neighbor);
            const double relief = std::abs(cell.elevation_m - neighbor.elevation_m);
            const double hazard = 0.5 * (cell.boundary_convergent + neighbor.boundary_convergent) +
                0.25 * (cell.boundary_transform + neighbor.boundary_transform);
            border.barrier_score = clamp(
                0.18 + relief / 2500.0 + hazard * 0.45 +
                    ((border.type == 2 || border.type == 3 || border.type == 4) ? 0.34 : 0.0),
                0.0,
                1.0
            );
            borders.push_back(border);
        }
    }
    return borders;
}

int trade_good_priority(int resource) {
    switch (resource) {
        case 1:
        case 2:
        case 5:
            return 6;
        case 3:
        case 4:
            return 5;
        case 6:
            return 4;
        case 7:
            return 3;
        case 8:
            return 2;
        default:
            return 0;
    }
}

int primary_trade_good(const std::vector<Cell>& cells, const Settlement& a, const Settlement& b) {
    const Cell& ca = cells[a.cell_id];
    const Cell& cb = cells[b.cell_id];
    int good = 0;
    int best_priority = 0;
    for (int resource : {ca.resource, cb.resource}) {
        const int priority = trade_good_priority(resource);
        if (resource != 0 && priority > best_priority) {
            good = resource;
            best_priority = priority;
        }
    }
    if (good != 0) {
        return good;
    }
    if (a.type == 1 || b.type == 1 || has_ocean_neighbor(cells, ca.id) || has_ocean_neighbor(cells, cb.id)) {
        return 8;
    }
    if (ca.fertility > 0.62 || cb.fertility > 0.62) {
        return 7;
    }
    return 0;
}

std::vector<TradeFlow> generate_trade_flows(
    const std::vector<Cell>& cells,
    const std::vector<Settlement>& settlements,
    const std::vector<Route>& routes
) {
    std::vector<TradeFlow> flows;
    flows.reserve(routes.size());
    for (const Route& route : routes) {
        if (route.from < 0 || route.to < 0 ||
            route.from >= static_cast<int>(settlements.size()) ||
            route.to >= static_cast<int>(settlements.size())) {
            continue;
        }
        const Settlement& from = settlements[route.from];
        const Settlement& to = settlements[route.to];
        const Cell& a = cells[from.cell_id];
        const Cell& b = cells[to.cell_id];
        const double friction = route.cost / std::max(1.0, route.distance_km);
        const int primary_good = primary_trade_good(cells, from, to);
        const double resource_bonus = primary_good == 0 ? 0.0 :
            (primary_good == 7 || primary_good == 8 ? 0.16 : 0.30);
        const double fertility_complement = std::abs(a.fertility - b.fertility);
        const double climate_complement = clamp(std::abs(a.temperature_c - b.temperature_c) / 45.0, 0.0, 0.55);
        const bool interregional = from.region_id >= 0 && to.region_id >= 0 && from.region_id != to.region_id;
        const double region_bonus = interregional ? 0.22 : 0.0;
        const double route_bonus = route.type == 2 ? 0.25 : (route.type == 1 ? 0.18 : (route.type == 3 ? -0.10 : 0.0));
        const double endpoint_strength = 0.5 * (from.score + to.score);
        const double volume = 80.0 * endpoint_strength *
            (1.0 + resource_bonus + 0.35 * fertility_complement + 0.25 * climate_complement + region_bonus + route_bonus) /
            (0.55 + friction);

        TradeFlow flow;
        flow.id = static_cast<int>(flows.size());
        flow.route_id = route.id;
        flow.from = route.from;
        flow.to = route.to;
        flow.region_from = from.region_id;
        flow.region_to = to.region_id;
        flow.primary_good = primary_good;
        flow.interregional = interregional;
        flow.distance_km = route.distance_km;
        flow.friction = friction;
        flow.volume_index = clamp(volume, 0.0, 100.0);
        flows.push_back(flow);
    }
    return flows;
}

int culture_type_for_region(const PoliticalRegion& region) {
    if (region.type == 1) {
        return 1;
    }
    if (region.type == 0) {
        return 0;
    }
    if (region.type == 2 || region.mean_elevation_m > 1100.0) {
        return 2;
    }
    if (region.dominant_biome == 9 || region.dominant_biome == 10) {
        return 3;
    }
    if (region.type == 3 || region.dominant_resource == 1 || region.dominant_resource == 2 ||
        region.dominant_resource == 5 || region.dominant_resource == 6) {
        return 5;
    }
    if (region.dominant_biome == 4 || region.dominant_biome == 5) {
        return 6;
    }
    if (region.dominant_biome == 11 || region.dominant_biome == 12 || region.dominant_biome == 13) {
        return 7;
    }
    return 4;
}

int language_family_for_culture(const CultureRegion& culture) {
    switch (culture.type) {
        case 0:
            return 0;
        case 1:
            return 1;
        case 2:
            return 2;
        case 3:
            return 3;
        case 4:
            return 4;
        default:
            return 5;
    }
}

int base_phoneme_inventory_for_family(int family) {
    switch (family) {
        case 0:
            return 27;
        case 1:
            return 31;
        case 2:
            return 34;
        case 3:
            return 24;
        case 4:
            return 29;
        default:
            return 30;
    }
}

void derive_language_phonology(std::vector<LanguageRegion>& languages) {
    for (LanguageRegion& language : languages) {
        const int base_inventory = base_phoneme_inventory_for_family(language.family);
        language.sound_shift_index = language.parent_language_region_id < 0 ?
            clamp(0.04 + 0.16 * language.change_rate, 0.0, 0.28) :
            clamp(
                0.10 + 0.42 * language.change_rate +
                    0.28 * clamp(language.divergence_age_years / 3200.0, 0.0, 1.0) +
                    0.18 * language.barrier_isolation -
                    0.14 * language.trade_contact_index,
                0.0,
                1.0
            );
        language.inherited_phonology_fraction = language.parent_language_region_id < 0 ?
            1.0 :
            clamp(1.0 - 0.78 * language.sound_shift_index, 0.0, 1.0);
        const int parent_inventory =
            language.parent_language_region_id >= 0 &&
                language.parent_language_region_id < static_cast<int>(languages.size()) &&
                languages[static_cast<std::size_t>(language.parent_language_region_id)].phoneme_inventory_size > 0 ?
            languages[static_cast<std::size_t>(language.parent_language_region_id)].phoneme_inventory_size :
            base_inventory;
        const double innovation = 8.0 * language.sound_shift_index +
            4.0 * language.barrier_isolation -
            3.0 * language.trade_contact_index +
            1.6 * static_cast<double>(language.lineage_depth);
        language.phoneme_inventory_size = clamp(
            static_cast<int>(std::lround(parent_inventory * (0.72 + 0.28 * language.inherited_phonology_fraction) + innovation)),
            16,
            58
        );
        language.phonological_complexity = clamp(
            0.20 +
                0.44 * (static_cast<double>(language.phoneme_inventory_size) / 58.0) +
                0.20 * language.barrier_isolation +
                0.10 * language.sound_shift_index -
                0.10 * language.trade_contact_index +
                0.04 * static_cast<double>(language.lineage_depth),
            0.0,
            1.0
        );
    }
}

int find_root(std::vector<int>& parent, int value) {
    int root = value;
    while (parent[root] != root) {
        root = parent[root];
    }
    while (parent[value] != value) {
        const int next = parent[value];
        parent[value] = root;
        value = next;
    }
    return root;
}

void union_roots(std::vector<int>& parent, int a, int b) {
    const int root_a = find_root(parent, a);
    const int root_b = find_root(parent, b);
    if (root_a != root_b) {
        parent[std::max(root_a, root_b)] = std::min(root_a, root_b);
    }
}

double sacred_significance_for_cell(const std::vector<Cell>& cells, const Cell& cell) {
    double score = 0.0;
    if (cell.elevation_m > 1700.0 || cell.landform == 6 || cell.landform == 17) {
        score += 0.34;
    }
    if (cell.is_river || cell.is_lake || cell.water_body == 4 || cell.water_body == 5) {
        score += 0.18;
    }
    if (cell.resource == 6 || cell.landform == 7) {
        score += 0.26;
    }
    if (cell.landform == 4 || cell.is_closed_basin) {
        score += 0.22;
    }
    if (cell.fertility > 0.74 && cell.precipitation_mm_y > 650.0) {
        score += 0.16;
    }
    if (has_ocean_neighbor(cells, cell.id)) {
        score += 0.12;
    }
    score += 0.12 * clamp(local_relief(cells, cell.id) / 1700.0, 0.0, 1.0);
    return clamp(score, 0.0, 1.0);
}

int sacred_area_type_for_cell(const std::vector<Cell>& cells, const Cell& cell) {
    if (cell.resource == 6 || cell.landform == 7) {
        return 3;
    }
    if (cell.elevation_m > 1700.0 || cell.landform == 6 || cell.landform == 17) {
        return 0;
    }
    if (cell.is_river || cell.is_lake || cell.water_body == 4 || cell.water_body == 5) {
        return 1;
    }
    if (cell.biome == 5 || cell.biome == 6 || cell.biome == 13 || cell.biome == 15) {
        return 2;
    }
    if (cell.biome == 9 || cell.biome == 10 || cell.landform == 4) {
        return 5;
    }
    if (has_ocean_neighbor(cells, cell.id)) {
        return 4;
    }
    return 2;
}

double ruin_significance_for_cell(const std::vector<Cell>& cells, const Cell& cell) {
    const bool coast = has_ocean_neighbor(cells, cell.id);
    double historical_potential = 0.18 + 0.38 * cell.settlement_score + 0.24 * cell.fertility;
    if (cell.is_river || cell.is_lake || coast) {
        historical_potential += 0.14;
    }
    if (cell.resource == 1 || cell.resource == 2 || cell.resource == 3 ||
        cell.resource == 4 || cell.resource == 5 || cell.resource == 6 || cell.resource == 7) {
        historical_potential += 0.16;
    }
    double abandonment_pressure = 0.0;
    if (cell.biome == 9 || cell.biome == 10 || cell.precipitation_mm_y < 220.0) {
        abandonment_pressure += 0.24;
    }
    if (cell.ice_thickness_m > 20.0 || cell.biome == 3) {
        abandonment_pressure += 0.22;
    }
    if (cell.water_body == 5 || cell.landform == 4 || cell.is_closed_basin) {
        abandonment_pressure += 0.18;
    }
    abandonment_pressure += 0.18 * clamp(cell.boundary_convergent + cell.boundary_transform, 0.0, 1.0);
    abandonment_pressure += 0.12 * clamp(local_relief(cells, cell.id) / 1800.0, 0.0, 1.0);
    if (cell.settlement_score < 0.52) {
        abandonment_pressure += 0.10;
    }
    return clamp(historical_potential * (0.55 + abandonment_pressure), 0.0, 1.0);
}

int ruin_type_for_cell(const std::vector<Cell>& cells, const Cell& cell) {
    if (cell.resource == 1 || cell.resource == 2 || cell.resource == 5 || cell.resource == 6) {
        return 1;
    }
    if (cell.biome == 9 || cell.biome == 10 || cell.landform == 4) {
        return 2;
    }
    if (cell.elevation_m > 1300.0 || cell.landform == 6 || cell.landform == 17) {
        return 3;
    }
    if (has_ocean_neighbor(cells, cell.id)) {
        return 4;
    }
    if (cell.ice_thickness_m > 20.0 || cell.biome == 3) {
        return 5;
    }
    return 0;
}

int abandonment_reason_for_cell(const Cell& cell) {
    if (cell.biome == 9 || cell.biome == 10 || cell.precipitation_mm_y < 220.0) {
        return 0;
    }
    if (cell.boundary_convergent + cell.boundary_transform > 0.45) {
        return 1;
    }
    if (cell.ice_thickness_m > 20.0 || cell.biome == 3) {
        return 2;
    }
    if (cell.water_body == 5 || cell.landform == 4 || cell.is_closed_basin) {
        return 3;
    }
    if (cell.settlement_score < 0.48) {
        return 4;
    }
    return 5;
}

CulturalLayers generate_cultural_layers(
    const Params& params,
    std::vector<Cell>& cells,
    std::vector<Settlement>& settlements,
    const std::vector<PoliticalRegion>& political_regions,
    const std::vector<BorderSegment>& borders,
    const std::vector<TradeFlow>& trade_flows
) {
    for (Cell& cell : cells) {
        cell.culture_region_id = -1;
        cell.language_region_id = -1;
    }
    for (Settlement& settlement : settlements) {
        settlement.culture_region_id = -1;
        settlement.language_region_id = -1;
    }
    CulturalLayers layers;
    if (political_regions.empty()) {
        return layers;
    }

    int max_region_id = -1;
    for (const PoliticalRegion& region : political_regions) {
        max_region_id = std::max(max_region_id, region.id);
    }
    std::vector<int> region_to_culture(static_cast<std::size_t>(max_region_id + 1), -1);
    layers.cultures.reserve(political_regions.size());
    for (const PoliticalRegion& region : political_regions) {
        CultureRegion culture;
        culture.id = static_cast<int>(layers.cultures.size());
        culture.homeland_region_id = region.id;
        culture.type = culture_type_for_region(region);
        culture.dominant_biome = region.dominant_biome;
        culture.dominant_resource = region.dominant_resource;
        culture.settlement_count = region.settlement_count;
        culture.settlement_ids = region.settlement_ids;
        if (region.id >= 0 && region.id < static_cast<int>(region_to_culture.size())) {
            region_to_culture[region.id] = culture.id;
        }
        layers.cultures.push_back(culture);
    }

    for (Cell& cell : cells) {
        if (cell.is_water || cell.political_region_id < 0 ||
            cell.political_region_id >= static_cast<int>(region_to_culture.size())) {
            continue;
        }
        cell.culture_region_id = region_to_culture[cell.political_region_id];
    }

    std::vector<double> barrier_sum(layers.cultures.size(), 0.0);
    std::vector<double> border_length(layers.cultures.size(), 0.0);
    std::vector<double> trade_volume(layers.cultures.size(), 0.0);
    std::vector<std::map<int, int>> biome_counts(layers.cultures.size());
    std::vector<std::map<int, int>> resource_counts(layers.cultures.size());

    for (const Cell& cell : cells) {
        if (cell.culture_region_id < 0) {
            continue;
        }
        CultureRegion& culture = layers.cultures[cell.culture_region_id];
        culture.area_km2 += cell.area_km2;
        culture.mean_fertility += cell.fertility * cell.area_km2;
        culture.mean_elevation_m += cell.elevation_m * cell.area_km2;
        if (cell.fertility > 0.62 || cell.resource == 7 || cell.landform == 11 || cell.landform == 12) {
            culture.agricultural_area_km2 += cell.area_km2;
        }
        if (cell.resource == 1 || cell.resource == 2 || cell.resource == 5 || cell.resource == 6) {
            culture.mining_area_km2 += cell.area_km2;
        }
        biome_counts[cell.culture_region_id][cell.biome]++;
        resource_counts[cell.culture_region_id][cell.resource]++;
    }

    for (const BorderSegment& border : borders) {
        if (border.region_a < 0 || border.region_b < 0 ||
            border.region_a >= static_cast<int>(region_to_culture.size()) ||
            border.region_b >= static_cast<int>(region_to_culture.size())) {
            continue;
        }
        const int a = region_to_culture[border.region_a];
        const int b = region_to_culture[border.region_b];
        if (a < 0 || b < 0 || a == b) {
            continue;
        }
        barrier_sum[a] += border.barrier_score * border.length_km;
        barrier_sum[b] += border.barrier_score * border.length_km;
        border_length[a] += border.length_km;
        border_length[b] += border.length_km;
    }

    std::vector<int> parent(layers.cultures.size());
    std::iota(parent.begin(), parent.end(), 0);
    for (const TradeFlow& flow : trade_flows) {
        if (flow.region_from < 0 || flow.region_to < 0 ||
            flow.region_from >= static_cast<int>(region_to_culture.size()) ||
            flow.region_to >= static_cast<int>(region_to_culture.size())) {
            continue;
        }
        const int a = region_to_culture[flow.region_from];
        const int b = region_to_culture[flow.region_to];
        if (a < 0 || b < 0) {
            continue;
        }
        trade_volume[a] += flow.volume_index;
        trade_volume[b] += flow.volume_index;
        if (a != b && flow.volume_index >= 70.0 && flow.friction <= 0.92) {
            union_roots(parent, a, b);
        }
    }

    std::map<int, int> root_to_language;
    for (CultureRegion& culture : layers.cultures) {
        const int root = find_root(parent, culture.id);
        auto [it, inserted] = root_to_language.emplace(root, static_cast<int>(root_to_language.size()));
        (void)inserted;
        culture.language_region_id = it->second;
    }

    layers.language_regions.resize(root_to_language.size());
    std::vector<std::map<int, double>> language_family_area(layers.language_regions.size());
    for (int i = 0; i < static_cast<int>(layers.language_regions.size()); ++i) {
        layers.language_regions[i].id = i;
    }

    for (CultureRegion& culture : layers.cultures) {
        if (culture.area_km2 > 0.0) {
            culture.mean_fertility /= culture.area_km2;
            culture.mean_elevation_m /= culture.area_km2;
        }
        culture.barrier_isolation = border_length[culture.id] > 0.0 ? barrier_sum[culture.id] / border_length[culture.id] : 0.0;
        culture.trade_contact_index = clamp(trade_volume[culture.id] / (100.0 * std::max(1, culture.settlement_count)), 0.0, 1.0);
        int best_biome = culture.dominant_biome;
        int best_biome_count = -1;
        for (const auto& [biome, count] : biome_counts[culture.id]) {
            if (count > best_biome_count) {
                best_biome = biome;
                best_biome_count = count;
            }
        }
        culture.dominant_biome = best_biome;
        int best_resource = 0;
        int best_resource_count = -1;
        for (const auto& [resource, count] : resource_counts[culture.id]) {
            if (resource != 0 && count > best_resource_count) {
                best_resource = resource;
                best_resource_count = count;
            }
        }
        culture.dominant_resource = best_resource_count < 0 ? 0 : best_resource;
        culture.migration_pressure = clamp(
            0.18 + 0.28 * (1.0 - culture.barrier_isolation) +
                0.22 * culture.trade_contact_index +
                0.16 * (1.0 - culture.mean_fertility) +
                0.12 * clamp(culture.mean_elevation_m / 1800.0, 0.0, 1.0),
            0.0,
            1.0
        );
        culture.continuity_index = clamp(
            0.30 + 0.22 * culture.barrier_isolation +
                0.18 * culture.mean_fertility +
                0.10 * std::min(1.0, static_cast<double>(culture.settlement_count) / 6.0) +
                0.10 * std::min(1.0, static_cast<double>(culture.sacred_area_count) / 3.0) -
                0.16 * std::min(1.0, static_cast<double>(culture.ruin_count) / 4.0),
            0.0,
            1.0
        );
        culture.estimated_age_years = clamp(
            420.0 + 1900.0 * culture.continuity_index +
                520.0 * culture.barrier_isolation +
                260.0 * std::min(1.0, static_cast<double>(culture.settlement_count) / 8.0),
            120.0,
            4200.0
        );

        LanguageRegion& language = layers.language_regions[culture.language_region_id];
        language.culture_count += 1;
        language.settlement_count += culture.settlement_count;
        language.area_km2 += culture.area_km2;
        language.barrier_isolation += culture.barrier_isolation * culture.area_km2;
        language.trade_contact_index += culture.trade_contact_index * culture.area_km2;
        language.culture_ids.push_back(culture.id);
        language_family_area[culture.language_region_id][language_family_for_culture(culture)] += culture.area_km2;
    }

    for (LanguageRegion& language : layers.language_regions) {
        if (language.area_km2 > 0.0) {
            language.barrier_isolation /= language.area_km2;
            language.trade_contact_index /= language.area_km2;
        }
        int best_family = 0;
        double best_area = -1.0;
        for (const auto& [family, area] : language_family_area[language.id]) {
            if (area > best_area) {
                best_family = family;
                best_area = area;
            }
        }
        language.family = best_family;
    }
    std::map<int, std::vector<std::pair<double, int>>> languages_by_family;
    for (const LanguageRegion& language : layers.language_regions) {
        languages_by_family[language.family].push_back({language.area_km2, language.id});
    }
    for (auto& [family, members] : languages_by_family) {
        (void)family;
        std::sort(members.begin(), members.end(), [](const auto& a, const auto& b) {
            if (a.first == b.first) {
                return a.second < b.second;
            }
            return a.first > b.first;
        });
        const int parent_language = members.empty() ? -1 : members.front().second;
        for (std::size_t i = 0; i < members.size(); ++i) {
            LanguageRegion& language = layers.language_regions[static_cast<std::size_t>(members[i].second)];
            language.parent_language_region_id = i == 0 ? -1 : parent_language;
            language.lineage_depth = i == 0 ? 0 : 1;
            language.change_rate = clamp(
                0.16 + 0.48 * language.barrier_isolation -
                    0.26 * language.trade_contact_index +
                    0.08 * std::min(1.0, static_cast<double>(language.culture_count) / 4.0),
                0.0,
                1.0
            );
            language.divergence_age_years = language.parent_language_region_id < 0 ?
                clamp(900.0 + 2100.0 * (1.0 - language.change_rate) + 380.0 * language.barrier_isolation, 250.0, 4200.0) :
                clamp(220.0 + 1700.0 * language.barrier_isolation + 820.0 * (1.0 - language.trade_contact_index), 120.0, 3200.0);
        }
    }
    bool has_lineage = false;
    for (const LanguageRegion& language : layers.language_regions) {
        if (language.parent_language_region_id >= 0) {
            has_lineage = true;
            break;
        }
    }
    if (!has_lineage && layers.language_regions.size() > 1) {
        int parent_language = 0;
        for (int i = 1; i < static_cast<int>(layers.language_regions.size()); ++i) {
            if (layers.language_regions[static_cast<std::size_t>(i)].area_km2 >
                layers.language_regions[static_cast<std::size_t>(parent_language)].area_km2) {
                parent_language = i;
            }
        }
        for (LanguageRegion& language : layers.language_regions) {
            if (language.id == parent_language) {
                continue;
            }
            language.parent_language_region_id = parent_language;
            language.lineage_depth = 1;
            language.divergence_age_years = clamp(
                280.0 + 1500.0 * language.barrier_isolation + 680.0 * (1.0 - language.trade_contact_index),
                120.0,
                3000.0
            );
            language.change_rate = clamp(language.change_rate + 0.08, 0.0, 1.0);
        }
    }

    derive_language_phonology(layers.language_regions);

    for (Cell& cell : cells) {
        if (cell.culture_region_id >= 0) {
            cell.language_region_id = layers.cultures[cell.culture_region_id].language_region_id;
        }
    }
    for (Settlement& settlement : settlements) {
        const Cell& cell = cells[settlement.cell_id];
        settlement.culture_region_id = cell.culture_region_id;
        settlement.language_region_id = cell.language_region_id;
    }

    std::vector<std::pair<double, int>> sacred_candidates;
    for (const Cell& cell : cells) {
        if (cell.is_water || cell.culture_region_id < 0) {
            continue;
        }
        const double significance = sacred_significance_for_cell(cells, cell);
        if (significance >= 0.30) {
            sacred_candidates.emplace_back(significance, cell.id);
        }
    }
    std::sort(sacred_candidates.begin(), sacred_candidates.end(), [](const auto& a, const auto& b) {
        if (a.first == b.first) {
            return a.second < b.second;
        }
        return a.first > b.first;
    });
    const int sacred_target = clamp(static_cast<int>(layers.cultures.size()) * 2, 2, 24);
    const double site_min_sep = 1.4 * std::sqrt(4.0 * PI / static_cast<double>(std::max(1, params.cell_count)));
    for (const auto& [significance, cell_id] : sacred_candidates) {
        bool too_close = false;
        for (const SacredArea& site : layers.sacred_areas) {
            if (angular_distance(cells[cell_id].p, cells[site.cell_id].p) < site_min_sep) {
                too_close = true;
                break;
            }
        }
        if (too_close) {
            continue;
        }
        const Cell& cell = cells[cell_id];
        SacredArea site;
        site.id = static_cast<int>(layers.sacred_areas.size());
        site.cell_id = cell_id;
        site.culture_region_id = cell.culture_region_id;
        site.language_region_id = cell.language_region_id;
        site.type = sacred_area_type_for_cell(cells, cell);
        site.significance = significance;
        site.lat_deg = cell.lat * DEG;
        site.lon_deg = cell.lon * DEG;
        layers.sacred_areas.push_back(site);
        layers.cultures[site.culture_region_id].sacred_area_count += 1;
        if (static_cast<int>(layers.sacred_areas.size()) >= sacred_target) {
            break;
        }
    }

    std::vector<char> active_settlement_cell(cells.size(), 0);
    for (const Settlement& settlement : settlements) {
        if (settlement.cell_id >= 0 && settlement.cell_id < static_cast<int>(active_settlement_cell.size())) {
            active_settlement_cell[settlement.cell_id] = 1;
        }
    }
    std::vector<std::pair<double, int>> ruin_candidates;
    for (const Cell& cell : cells) {
        if (cell.is_water || cell.culture_region_id < 0 || active_settlement_cell[cell.id]) {
            continue;
        }
        const double significance = ruin_significance_for_cell(cells, cell);
        if (significance >= 0.32) {
            ruin_candidates.emplace_back(significance, cell.id);
        }
    }
    std::sort(ruin_candidates.begin(), ruin_candidates.end(), [](const auto& a, const auto& b) {
        if (a.first == b.first) {
            return a.second < b.second;
        }
        return a.first > b.first;
    });
    const int ruin_target = clamp(static_cast<int>(layers.cultures.size()) + static_cast<int>(settlements.size()) / 4, 2, 32);
    for (const auto& [significance, cell_id] : ruin_candidates) {
        bool too_close = false;
        for (const Ruin& ruin : layers.ruins) {
            if (angular_distance(cells[cell_id].p, cells[ruin.cell_id].p) < site_min_sep) {
                too_close = true;
                break;
            }
        }
        if (too_close) {
            continue;
        }
        const Cell& cell = cells[cell_id];
        Ruin ruin;
        ruin.id = static_cast<int>(layers.ruins.size());
        ruin.cell_id = cell_id;
        ruin.culture_region_id = cell.culture_region_id;
        ruin.language_region_id = cell.language_region_id;
        ruin.type = ruin_type_for_cell(cells, cell);
        ruin.abandonment_reason = abandonment_reason_for_cell(cell);
        ruin.significance = significance;
        ruin.preservation_score = clamp(
            0.35 + 0.20 * ((cell.biome == 9 || cell.biome == 10) ? 1.0 : 0.0) +
                0.20 * (cell.ice_thickness_m > 20.0 ? 1.0 : 0.0) -
                0.18 * (cell.precipitation_mm_y > 1200.0 ? 1.0 : 0.0),
            0.0,
            1.0
        );
        ruin.lat_deg = cell.lat * DEG;
        ruin.lon_deg = cell.lon * DEG;
        layers.ruins.push_back(ruin);
        layers.cultures[ruin.culture_region_id].ruin_count += 1;
        if (static_cast<int>(layers.ruins.size()) >= ruin_target) {
            break;
        }
    }

    for (CultureRegion& culture : layers.cultures) {
        culture.continuity_index = clamp(
            0.30 + 0.22 * culture.barrier_isolation +
                0.18 * culture.mean_fertility +
                0.10 * std::min(1.0, static_cast<double>(culture.settlement_count) / 6.0) +
                0.10 * std::min(1.0, static_cast<double>(culture.sacred_area_count) / 3.0) -
                0.16 * std::min(1.0, static_cast<double>(culture.ruin_count) / 4.0),
            0.0,
            1.0
        );
        culture.estimated_age_years = clamp(
            420.0 + 1900.0 * culture.continuity_index +
                520.0 * culture.barrier_isolation +
                260.0 * std::min(1.0, static_cast<double>(culture.settlement_count) / 8.0),
            120.0,
            4200.0
        );
    }

    return layers;
}

int historical_era_for_year_bp(double year_bp) {
    if (year_bp > 2400.0) {
        return 0;
    }
    if (year_bp > 1300.0) {
        return 1;
    }
    if (year_bp > 450.0) {
        return 2;
    }
    return 3;
}

std::vector<HistoricalEra> default_historical_eras() {
    std::vector<HistoricalEra> eras(4);
    eras[0].id = 0;
    eras[0].dominant_process = 0;
    eras[0].start_year_bp = 4200.0;
    eras[0].end_year_bp = 2400.0;
    eras[1].id = 1;
    eras[1].dominant_process = 1;
    eras[1].start_year_bp = 2400.0;
    eras[1].end_year_bp = 1300.0;
    eras[2].id = 2;
    eras[2].dominant_process = 2;
    eras[2].start_year_bp = 1300.0;
    eras[2].end_year_bp = 450.0;
    eras[3].id = 3;
    eras[3].dominant_process = 3;
    eras[3].start_year_bp = 450.0;
    eras[3].end_year_bp = 0.0;
    return eras;
}

void add_historical_event(
    std::vector<HistoricalEvent>& events,
    int type,
    double year_bp,
    int region_id,
    int related_region_id,
    int culture_region_id,
    int related_culture_region_id,
    int language_region_id,
    int related_language_region_id,
    int cell_id,
    double pressure_index,
    double continuity_index
) {
    HistoricalEvent event;
    event.id = static_cast<int>(events.size());
    event.type = type;
    event.era_id = historical_era_for_year_bp(year_bp);
    event.year_bp = year_bp;
    event.region_id = region_id;
    event.related_region_id = related_region_id;
    event.culture_region_id = culture_region_id;
    event.related_culture_region_id = related_culture_region_id;
    event.language_region_id = language_region_id;
    event.related_language_region_id = related_language_region_id;
    event.cell_id = cell_id;
    event.pressure_index = clamp(pressure_index, 0.0, 1.0);
    event.continuity_index = clamp(continuity_index, 0.0, 1.0);
    events.push_back(event);
}

HistoricalLayers generate_historical_layers(
    const std::vector<Cell>& cells,
    const std::vector<Settlement>& settlements,
    const std::vector<PoliticalRegion>& political_regions,
    const std::vector<BorderSegment>& borders,
    const std::vector<TradeFlow>& trade_flows,
    const CulturalLayers& cultural_layers
) {
    HistoricalLayers history;
    history.eras = default_historical_eras();
    if (political_regions.empty() || cultural_layers.cultures.empty()) {
        return history;
    }

    std::map<int, int> region_to_culture;
    for (const CultureRegion& culture : cultural_layers.cultures) {
        region_to_culture[culture.homeland_region_id] = culture.id;
    }
    std::map<int, double> region_border_pressure;
    std::map<int, double> region_border_length;
    for (const BorderSegment& border : borders) {
        region_border_pressure[border.region_a] += border.barrier_score * border.length_km;
        region_border_pressure[border.region_b] += border.barrier_score * border.length_km;
        region_border_length[border.region_a] += border.length_km;
        region_border_length[border.region_b] += border.length_km;
    }
    std::map<int, double> region_trade_volume;
    for (const TradeFlow& flow : trade_flows) {
        if (flow.region_from >= 0) {
            region_trade_volume[flow.region_from] += flow.volume_index;
        }
        if (flow.region_to >= 0) {
            region_trade_volume[flow.region_to] += flow.volume_index;
        }
    }

    for (const PoliticalRegion& region : political_regions) {
        const int culture_id = region_to_culture.count(region.id) > 0 ? region_to_culture[region.id] : -1;
        const CultureRegion* culture = culture_id >= 0 ? &cultural_layers.cultures[static_cast<std::size_t>(culture_id)] : nullptr;
        const int language_id = culture != nullptr ? culture->language_region_id : -1;
        const int cell_id = region.capital_settlement_id >= 0 &&
                region.capital_settlement_id < static_cast<int>(settlements.size()) ?
            settlements[static_cast<std::size_t>(region.capital_settlement_id)].cell_id :
            -1;
        const double continuity = culture != nullptr ? culture->continuity_index : 0.5;
        const double pressure = clamp(
            0.18 + region.barrier_pressure * 0.32 +
                (region_border_length[region.id] > 0.0 ? region_border_pressure[region.id] / region_border_length[region.id] : 0.0) * 0.28 +
                (region.settlement_count <= 2 ? 0.18 : 0.0),
            0.0,
            1.0
        );
        const double foundation_year = clamp(380.0 + 0.72 * (culture != nullptr ? culture->estimated_age_years : 1800.0), 260.0, 3800.0);
        add_historical_event(
            history.events,
            0,
            foundation_year,
            region.id,
            -1,
            culture_id,
            -1,
            language_id,
            -1,
            cell_id,
            pressure,
            continuity
        );
        const double trade_contact = region_trade_volume[region.id] / (100.0 * std::max(1, region.settlement_count));
        if (pressure > 0.34 || trade_contact > 0.55 || region.route_count == 0) {
            add_historical_event(
                history.events,
                1,
                clamp(foundation_year * 0.48 + 180.0 * (region.id + 1), 180.0, 2100.0),
                region.id,
                -1,
                culture_id,
                -1,
                language_id,
                -1,
                cell_id,
                clamp(pressure + 0.18 * trade_contact, 0.0, 1.0),
                continuity
            );
        }
    }

    for (const CultureRegion& culture : cultural_layers.cultures) {
        if (culture.migration_pressure < 0.42 && culture.trade_contact_index < 0.28) {
            continue;
        }
        int cell_id = -1;
        if (!culture.settlement_ids.empty()) {
            const int settlement_id = culture.settlement_ids.front();
            if (settlement_id >= 0 && settlement_id < static_cast<int>(settlements.size())) {
                cell_id = settlements[static_cast<std::size_t>(settlement_id)].cell_id;
            }
        }
        int related_culture = -1;
        double best_contact = -1.0;
        for (const CultureRegion& other : cultural_layers.cultures) {
            if (other.id == culture.id || other.language_region_id != culture.language_region_id) {
                continue;
            }
            const double contact = 1.0 - std::abs(other.trade_contact_index - culture.trade_contact_index);
            if (contact > best_contact) {
                best_contact = contact;
                related_culture = other.id;
            }
        }
        add_historical_event(
            history.events,
            2,
            clamp(260.0 + 2100.0 * culture.migration_pressure + 220.0 * culture.id, 120.0, 2600.0),
            culture.homeland_region_id,
            -1,
            culture.id,
            related_culture,
            culture.language_region_id,
            -1,
            cell_id,
            culture.migration_pressure,
            culture.continuity_index
        );
    }

    for (const LanguageRegion& language : cultural_layers.language_regions) {
        if (language.parent_language_region_id < 0) {
            continue;
        }
        const int culture_id = language.culture_ids.empty() ? -1 : language.culture_ids.front();
        int cell_id = -1;
        int region_id = -1;
        if (culture_id >= 0) {
            const CultureRegion& culture = cultural_layers.cultures[static_cast<std::size_t>(culture_id)];
            region_id = culture.homeland_region_id;
            if (!culture.settlement_ids.empty()) {
                const int settlement_id = culture.settlement_ids.front();
                if (settlement_id >= 0 && settlement_id < static_cast<int>(settlements.size())) {
                    cell_id = settlements[static_cast<std::size_t>(settlement_id)].cell_id;
                }
            }
        }
        add_historical_event(
            history.events,
            3,
            clamp(language.divergence_age_years, 80.0, 3400.0),
            region_id,
            -1,
            culture_id,
            -1,
            language.id,
            language.parent_language_region_id,
            cell_id,
            language.change_rate,
            clamp(1.0 - language.change_rate, 0.0, 1.0)
        );
    }

    std::vector<TradeFlow> ranked_flows = trade_flows;
    std::sort(ranked_flows.begin(), ranked_flows.end(), [](const TradeFlow& a, const TradeFlow& b) {
        if (a.volume_index == b.volume_index) {
            return a.id < b.id;
        }
        return a.volume_index > b.volume_index;
    });
    const int trade_event_target = std::min(12, static_cast<int>(ranked_flows.size()));
    for (int i = 0; i < trade_event_target; ++i) {
        const TradeFlow& flow = ranked_flows[static_cast<std::size_t>(i)];
        int culture_id = region_to_culture.count(flow.region_from) > 0 ? region_to_culture[flow.region_from] : -1;
        int related_culture = region_to_culture.count(flow.region_to) > 0 ? region_to_culture[flow.region_to] : -1;
        int language_id = culture_id >= 0 ? cultural_layers.cultures[static_cast<std::size_t>(culture_id)].language_region_id : -1;
        int cell_id = flow.from >= 0 && flow.from < static_cast<int>(settlements.size()) ?
            settlements[static_cast<std::size_t>(flow.from)].cell_id :
            -1;
        add_historical_event(
            history.events,
            4,
            clamp(140.0 + 820.0 * (1.0 - clamp(flow.friction / 2.0, 0.0, 1.0)) + 42.0 * i, 70.0, 1300.0),
            flow.region_from,
            flow.region_to,
            culture_id,
            related_culture,
            language_id,
            -1,
            cell_id,
            clamp(flow.volume_index / 100.0, 0.0, 1.0),
            clamp(1.0 - flow.friction / 2.0, 0.0, 1.0)
        );
    }

    const int sacred_event_target = std::min(12, static_cast<int>(cultural_layers.sacred_areas.size()));
    for (int i = 0; i < sacred_event_target; ++i) {
        const SacredArea& site = cultural_layers.sacred_areas[static_cast<std::size_t>(i)];
        const CultureRegion* culture = site.culture_region_id >= 0 ?
            &cultural_layers.cultures[static_cast<std::size_t>(site.culture_region_id)] :
            nullptr;
        add_historical_event(
            history.events,
            5,
            clamp(220.0 + 1800.0 * site.significance + 35.0 * i, 120.0, 2400.0),
            culture != nullptr ? culture->homeland_region_id : -1,
            -1,
            site.culture_region_id,
            -1,
            site.language_region_id,
            -1,
            site.cell_id,
            site.significance,
            culture != nullptr ? culture->continuity_index : 0.5
        );
    }

    const int ruin_event_target = std::min(16, static_cast<int>(cultural_layers.ruins.size()));
    for (int i = 0; i < ruin_event_target; ++i) {
        const Ruin& ruin = cultural_layers.ruins[static_cast<std::size_t>(i)];
        const CultureRegion* culture = ruin.culture_region_id >= 0 ?
            &cultural_layers.cultures[static_cast<std::size_t>(ruin.culture_region_id)] :
            nullptr;
        add_historical_event(
            history.events,
            6,
            clamp(90.0 + 1500.0 * ruin.significance + 28.0 * i, 80.0, 1900.0),
            culture != nullptr ? culture->homeland_region_id : -1,
            -1,
            ruin.culture_region_id,
            -1,
            ruin.language_region_id,
            -1,
            ruin.cell_id,
            ruin.significance,
            ruin.preservation_score
        );
    }

    std::sort(history.events.begin(), history.events.end(), [](const HistoricalEvent& a, const HistoricalEvent& b) {
        if (a.year_bp == b.year_bp) {
            return a.type < b.type;
        }
        return a.year_bp > b.year_bp;
    });
    for (int i = 0; i < static_cast<int>(history.events.size()); ++i) {
        history.events[static_cast<std::size_t>(i)].id = i;
        history.events[static_cast<std::size_t>(i)].era_id = historical_era_for_year_bp(history.events[static_cast<std::size_t>(i)].year_bp);
    }
    for (const HistoricalEvent& event : history.events) {
        if (event.era_id < 0 || event.era_id >= static_cast<int>(history.eras.size())) {
            continue;
        }
        HistoricalEra& era = history.eras[static_cast<std::size_t>(event.era_id)];
        era.event_count += 1;
        era.mean_instability += event.pressure_index;
        era.mean_connectivity += event.continuity_index;
        if (event.type == 0 || event.type == 1) {
            era.state_event_count += 1;
        } else if (event.type == 2) {
            era.migration_event_count += 1;
        } else if (event.type == 3) {
            era.language_event_count += 1;
        }
    }
    for (HistoricalEra& era : history.eras) {
        if (era.event_count > 0) {
            era.mean_instability /= static_cast<double>(era.event_count);
            era.mean_connectivity /= static_cast<double>(era.event_count);
        }
    }
    return history;
}

std::map<int, int> region_to_culture_map(const CulturalLayers& cultural_layers) {
    std::map<int, int> region_to_culture;
    for (const CultureRegion& culture : cultural_layers.cultures) {
        if (culture.homeland_region_id >= 0) {
            region_to_culture[culture.homeland_region_id] = culture.id;
        }
    }
    return region_to_culture;
}

double population_water_security(const std::vector<Cell>& cells, const Cell& cell) {
    double water = clamp(cell.runoff_mm_y / 1300.0, 0.0, 0.70);
    if (cell.is_river) {
        water += 0.24;
    }
    if (cell.is_lake || cell.water_body == 4) {
        water += 0.18;
    }
    if (has_ocean_neighbor(cells, cell.id)) {
        water += 0.08;
    }
    if (cell.water_body == 5 || cell.soil_type == 10) {
        water -= 0.18;
    }
    return clamp(water, 0.0, 1.0);
}

std::vector<PopulationRegion> generate_population_regions(
    const std::vector<Cell>& cells,
    const std::vector<PoliticalRegion>& political_regions,
    const CulturalLayers& cultural_layers
) {
    const std::map<int, int> region_to_culture = region_to_culture_map(cultural_layers);
    std::vector<PopulationRegion> populations;
    populations.reserve(political_regions.size());
    for (const PoliticalRegion& region : political_regions) {
        PopulationRegion pop;
        pop.id = static_cast<int>(populations.size());
        pop.region_id = region.id;
        pop.settlement_count = region.settlement_count;
        if (region_to_culture.count(region.id) > 0) {
            pop.culture_region_id = region_to_culture.at(region.id);
            const CultureRegion& culture = cultural_layers.cultures[static_cast<std::size_t>(pop.culture_region_id)];
            pop.language_region_id = culture.language_region_id;
            pop.migration_balance = clamp(0.5 - culture.migration_pressure, -1.0, 1.0);
        }

        double area = 0.0;
        double fertility_sum = 0.0;
        double water_sum = 0.0;
        double climate_sum = 0.0;
        double hazard_sum = 0.0;
        double urban_site_sum = 0.0;
        int cell_count = 0;
        for (const Cell& cell : cells) {
            if (cell.is_water || cell.political_region_id != region.id) {
                continue;
            }
            const double water = population_water_security(cells, cell);
            const double climate = clamp(
                1.0 - std::abs(cell.temperature_c - 17.0) / 42.0 -
                    std::max(0.0, 360.0 - cell.precipitation_mm_y) / 1400.0 -
                    cell.ice_thickness_m / 2800.0,
                0.0,
                1.0
            );
            const double hazard = clamp(
                0.35 * cell.boundary_convergent + 0.25 * cell.boundary_transform +
                    local_relief(cells, cell.id) / 4200.0 + cell.ice_thickness_m / 3200.0,
                0.0,
                1.0
            );
            area += cell.area_km2;
            fertility_sum += cell.fertility * cell.area_km2;
            water_sum += water * cell.area_km2;
            climate_sum += climate * cell.area_km2;
            hazard_sum += hazard * cell.area_km2;
            urban_site_sum += cell.settlement_score * cell.area_km2;
            cell_count++;
        }
        if (area <= 0.0 || cell_count == 0) {
            populations.push_back(pop);
            continue;
        }
        const double fertility = fertility_sum / area;
        const double water = water_sum / area;
        const double climate = climate_sum / area;
        const double hazard = hazard_sum / area;
        const double site_strength = urban_site_sum / area;
        const double route_factor = clamp(static_cast<double>(region.route_count) / std::max(1.0, static_cast<double>(region.settlement_count)), 0.0, 1.0);
        const double density_capacity = clamp(1.5 + 64.0 * fertility * water * climate + 12.0 * site_strength, 0.2, 90.0);
        pop.agricultural_capacity_index = clamp(fertility * climate * (0.55 + 0.45 * water), 0.0, 1.0);
        pop.water_security_index = water;
        pop.hazard_mortality_index = hazard;
        pop.urbanization_fraction = clamp(0.04 + 0.025 * region.settlement_count + 0.16 * route_factor + 0.12 * site_strength, 0.02, 0.62);
        pop.carrying_capacity = area * density_capacity;
        const double continuity = pop.culture_region_id >= 0 ?
            cultural_layers.cultures[static_cast<std::size_t>(pop.culture_region_id)].continuity_index :
            0.5;
        const double occupancy = clamp(0.22 + 0.30 * continuity + 0.26 * pop.urbanization_fraction + 0.18 * route_factor - 0.18 * hazard, 0.05, 0.93);
        pop.estimated_population = pop.carrying_capacity * occupancy;
        pop.population_pressure = pop.carrying_capacity > 0.0 ? clamp(pop.estimated_population / pop.carrying_capacity, 0.0, 1.4) : 0.0;
        pop.growth_rate_per_year = clamp(
            0.0015 + 0.0065 * pop.agricultural_capacity_index + 0.0025 * pop.water_security_index -
                0.0030 * pop.population_pressure - 0.0045 * hazard,
            -0.012,
            0.018
        );
        populations.push_back(pop);
    }
    return populations;
}

std::vector<ConflictRecord> generate_conflicts(
    const std::vector<Cell>& cells,
    const std::vector<PoliticalRegion>& political_regions,
    const std::vector<BorderSegment>& borders,
    const std::vector<TradeFlow>& trade_flows,
    const CulturalLayers& cultural_layers,
    const std::vector<PopulationRegion>& population_regions
) {
    const std::map<int, int> region_to_culture = region_to_culture_map(cultural_layers);
    std::map<int, const PopulationRegion*> population_by_region;
    for (const PopulationRegion& population : population_regions) {
        population_by_region[population.region_id] = &population;
    }
    std::map<int, const PoliticalRegion*> region_by_id;
    for (const PoliticalRegion& region : political_regions) {
        region_by_id[region.id] = &region;
    }
    std::map<std::pair<int, int>, double> trade_chokepoint_by_pair;
    for (const TradeFlow& flow : trade_flows) {
        if (!flow.interregional || flow.region_from < 0 || flow.region_to < 0) {
            continue;
        }
        const std::pair<int, int> key = std::minmax(flow.region_from, flow.region_to);
        trade_chokepoint_by_pair[key] += flow.volume_index * flow.friction / 100.0;
    }

    struct Candidate {
        ConflictRecord record;
        double score = 0.0;
    };
    std::map<std::pair<int, int>, Candidate> best_by_pair;
    for (const BorderSegment& border : borders) {
        if (border.region_a < 0 || border.region_b < 0 || border.cell_a < 0 || border.cell_b < 0) {
            continue;
        }
        const Cell& a = cells[static_cast<std::size_t>(border.cell_a)];
        const Cell& b = cells[static_cast<std::size_t>(border.cell_b)];
        const std::pair<int, int> pair = std::minmax(border.region_a, border.region_b);
        const PopulationRegion* pop_a = population_by_region.count(pair.first) > 0 ? population_by_region[pair.first] : nullptr;
        const PopulationRegion* pop_b = population_by_region.count(pair.second) > 0 ? population_by_region[pair.second] : nullptr;
        const PoliticalRegion* region_a = region_by_id.count(pair.first) > 0 ? region_by_id[pair.first] : nullptr;
        const PoliticalRegion* region_b = region_by_id.count(pair.second) > 0 ? region_by_id[pair.second] : nullptr;
        const double pressure = 0.5 * (
            (pop_a != nullptr ? pop_a->population_pressure : 0.35) +
            (pop_b != nullptr ? pop_b->population_pressure : 0.35)
        );
        const double resource_pressure = (a.resource != 0 || b.resource != 0) ? 0.72 : 0.0;
        const double water_a = population_water_security(cells, a);
        const double water_b = population_water_security(cells, b);
        const double water_stress = clamp(1.0 - 0.5 * (water_a + water_b), 0.0, 1.0);
        const double fertility_pressure = clamp(0.5 * (a.fertility + b.fertility), 0.0, 1.0);
        const double trade_chokepoint = clamp(
            trade_chokepoint_by_pair[pair] * 0.24 +
                (border.type == 1 || border.type == 2 || border.type == 5 ? 0.34 : 0.0),
            0.0,
            1.0
        );
        double cause_score = water_stress;
        int cause = 0;
        if (fertility_pressure > cause_score) {
            cause_score = fertility_pressure;
            cause = 1;
        }
        if (resource_pressure > cause_score) {
            cause_score = resource_pressure;
            cause = 2;
        }
        if (trade_chokepoint > cause_score) {
            cause_score = trade_chokepoint;
            cause = 3;
        }
        if (border.barrier_score > cause_score && border.type != 0) {
            cause = 4;
        }
        const double intensity = clamp(
            0.12 + 0.28 * pressure + 0.22 * border.barrier_score +
                0.18 * resource_pressure + 0.16 * water_stress + 0.18 * trade_chokepoint,
            0.0,
            1.0
        );
        const double score = intensity + 0.08 * fertility_pressure;
        if (score < 0.24) {
            continue;
        }
        Candidate candidate;
        candidate.score = score;
        candidate.record.region_a = pair.first;
        candidate.record.region_b = pair.second;
        candidate.record.culture_a = region_to_culture.count(pair.first) > 0 ? region_to_culture.at(pair.first) : -1;
        candidate.record.culture_b = region_to_culture.count(pair.second) > 0 ? region_to_culture.at(pair.second) : -1;
        candidate.record.cause = cause;
        candidate.record.contested_cell_id = intensity >= 0.5 ? border.cell_a : border.cell_b;
        candidate.record.intensity = intensity;
        candidate.record.resource_pressure = resource_pressure;
        candidate.record.water_stress = water_stress;
        candidate.record.trade_chokepoint_index = trade_chokepoint;
        const double start_year = clamp(160.0 + 1850.0 * intensity + 17.0 * static_cast<double>(best_by_pair.size() + 1), 90.0, 2600.0);
        const double duration = clamp(12.0 + 90.0 * intensity + 18.0 * trade_chokepoint, 8.0, 160.0);
        candidate.record.start_year_bp = start_year;
        candidate.record.end_year_bp = std::max(0.0, start_year - duration);
        candidate.record.war_duration_years = candidate.record.start_year_bp - candidate.record.end_year_bp;
        candidate.record.era_id = historical_era_for_year_bp(start_year);
        const double population_a = pop_a != nullptr ? pop_a->estimated_population : 0.0;
        const double population_b = pop_b != nullptr ? pop_b->estimated_population : 0.0;
        const double average_population = 0.5 * (
            population_a +
            population_b
        );
        const double total_population = population_a + population_b;
        const double route_factor_a = region_a != nullptr ?
            clamp(static_cast<double>(region_a->route_count) / std::max(1.0, static_cast<double>(region_a->settlement_count)), 0.0, 1.0) :
            0.0;
        const double route_factor_b = region_b != nullptr ?
            clamp(static_cast<double>(region_b->route_count) / std::max(1.0, static_cast<double>(region_b->settlement_count)), 0.0, 1.0) :
            0.0;
        const double urban_a = pop_a != nullptr ? pop_a->urbanization_fraction : 0.05;
        const double urban_b = pop_b != nullptr ? pop_b->urbanization_fraction : 0.05;
        candidate.record.logistics_strain_index = clamp(
            0.24 * border.barrier_score + 0.22 * water_stress + 0.20 * trade_chokepoint +
                0.18 * intensity + (border.type == 1 || border.type == 2 ? 0.10 : 0.0),
            0.0,
            1.0
        );
        const double mobilization_rate = clamp(
            0.012 + 0.070 * intensity + 0.022 * trade_chokepoint + 0.015 * pressure -
                0.018 * candidate.record.logistics_strain_index,
            0.004,
            0.16
        );
        candidate.record.region_a_force_estimate = std::max(0.0, population_a * mobilization_rate *
            (0.72 + 0.28 * urban_a + 0.14 * route_factor_a - 0.22 * candidate.record.logistics_strain_index));
        candidate.record.region_b_force_estimate = std::max(0.0, population_b * mobilization_rate *
            (0.72 + 0.28 * urban_b + 0.14 * route_factor_b - 0.22 * candidate.record.logistics_strain_index));
        candidate.record.mobilized_population =
            candidate.record.region_a_force_estimate + candidate.record.region_b_force_estimate;
        candidate.record.estimated_casualties = average_population * intensity * (0.006 + 0.025 * intensity);
        candidate.record.casualty_rate = total_population > 0.0 ?
            clamp(candidate.record.estimated_casualties / total_population, 0.0, 1.0) :
            0.0;
        candidate.record.economic_disruption_index = clamp(
            0.18 * intensity + 0.18 * candidate.record.logistics_strain_index +
                0.18 * trade_chokepoint + 0.16 * resource_pressure +
                0.14 * water_stress + 0.16 * (candidate.record.war_duration_years / 160.0),
            0.0,
            1.0
        );
        const double effectiveness_a = candidate.record.region_a_force_estimate *
            (1.0 + 0.26 * route_factor_a + 0.18 * urban_a - 0.38 * candidate.record.logistics_strain_index);
        const double effectiveness_b = candidate.record.region_b_force_estimate *
            (1.0 + 0.26 * route_factor_b + 0.18 * urban_b - 0.38 * candidate.record.logistics_strain_index);
        const double force_scale = std::max(1.0, candidate.record.mobilized_population);
        const double advantage = (effectiveness_a - effectiveness_b) / force_scale;
        if (candidate.record.logistics_strain_index > 0.72 && intensity > 0.58) {
            candidate.record.outcome = 4;
        } else if (std::abs(advantage) < 0.08) {
            candidate.record.outcome = 0;
        } else if (std::abs(advantage) < 0.20 && trade_chokepoint > 0.38) {
            candidate.record.outcome = 3;
        } else {
            candidate.record.outcome = advantage > 0.0 ? 1 : 2;
        }
        if (best_by_pair.count(pair) == 0 || score > best_by_pair[pair].score) {
            best_by_pair[pair] = candidate;
        }
    }

    std::vector<Candidate> candidates;
    candidates.reserve(best_by_pair.size());
    for (const auto& [_, candidate] : best_by_pair) {
        candidates.push_back(candidate);
    }
    std::sort(candidates.begin(), candidates.end(), [](const Candidate& a, const Candidate& b) {
        if (a.score == b.score) {
            return std::make_pair(a.record.region_a, a.record.region_b) < std::make_pair(b.record.region_a, b.record.region_b);
        }
        return a.score > b.score;
    });
    const int target = std::min(static_cast<int>(candidates.size()), std::max(0, static_cast<int>(political_regions.size()) * 2));
    std::vector<ConflictRecord> conflicts;
    conflicts.reserve(target);
    for (int i = 0; i < target; ++i) {
        ConflictRecord conflict = candidates[static_cast<std::size_t>(i)].record;
        conflict.id = static_cast<int>(conflicts.size());
        conflicts.push_back(conflict);
    }
    return conflicts;
}

std::vector<DynastyRecord> generate_dynasties(
    const std::vector<PoliticalRegion>& political_regions,
    const CulturalLayers& cultural_layers,
    const HistoricalLayers& historical_layers,
    const std::vector<PopulationRegion>& population_regions,
    const std::vector<ConflictRecord>& conflicts
) {
    const std::map<int, int> region_to_culture = region_to_culture_map(cultural_layers);
    std::map<int, const PopulationRegion*> population_by_region;
    for (const PopulationRegion& population : population_regions) {
        population_by_region[population.region_id] = &population;
    }
    std::map<int, double> conflict_pressure_by_region;
    for (const ConflictRecord& conflict : conflicts) {
        conflict_pressure_by_region[conflict.region_a] += conflict.intensity;
        conflict_pressure_by_region[conflict.region_b] += conflict.intensity;
    }
    std::map<int, int> founding_event_by_region;
    std::map<int, double> founding_year_by_region;
    for (const HistoricalEvent& event : historical_layers.events) {
        if (event.type != 0 || event.region_id < 0) {
            continue;
        }
        if (founding_event_by_region.count(event.region_id) == 0 || event.year_bp > founding_year_by_region[event.region_id]) {
            founding_event_by_region[event.region_id] = event.id;
            founding_year_by_region[event.region_id] = event.year_bp;
        }
    }

    std::vector<DynastyRecord> dynasties;
    for (const PoliticalRegion& region : political_regions) {
        const int culture_id = region_to_culture.count(region.id) > 0 ? region_to_culture.at(region.id) : -1;
        const int language_id = culture_id >= 0 ?
            cultural_layers.cultures[static_cast<std::size_t>(culture_id)].language_region_id :
            -1;
        const double continuity = culture_id >= 0 ?
            cultural_layers.cultures[static_cast<std::size_t>(culture_id)].continuity_index :
            0.5;
        const PopulationRegion* population = population_by_region.count(region.id) > 0 ? population_by_region[region.id] : nullptr;
        const double population_pressure = population != nullptr ? population->population_pressure : 0.4;
        const double conflict_pressure = clamp(conflict_pressure_by_region[region.id] / 3.0, 0.0, 1.0);
        const double base_succession_pressure = clamp(
            0.18 + 0.34 * population_pressure + 0.36 * conflict_pressure +
                (region.route_count == 0 ? 0.10 : 0.0) - 0.24 * continuity,
            0.0,
            1.0
        );
        const int dynasty_count = 1 + (base_succession_pressure > 0.36 ? 1 : 0) + (base_succession_pressure > 0.66 ? 1 : 0);
        const double founding_year = founding_year_by_region.count(region.id) > 0 ?
            founding_year_by_region[region.id] :
            clamp(620.0 + 240.0 * static_cast<double>(region.id + 1), 260.0, 3200.0);
        const int founding_event_id = founding_event_by_region.count(region.id) > 0 ? founding_event_by_region[region.id] : -1;
        int parent_id = -1;
        int founder_id = -1;
        for (int i = 0; i < dynasty_count; ++i) {
            DynastyRecord dynasty;
            dynasty.id = static_cast<int>(dynasties.size());
            if (i == 0) {
                founder_id = dynasty.id;
            }
            dynasty.region_id = region.id;
            dynasty.culture_region_id = culture_id;
            dynasty.language_region_id = language_id;
            dynasty.parent_dynasty_id = parent_id;
            dynasty.founder_dynasty_id = founder_id;
            dynasty.founding_event_id = i == 0 ? founding_event_id : -1;
            dynasty.lineage_depth = i;
            dynasty.start_year_bp = founding_year * (1.0 - static_cast<double>(i) / static_cast<double>(dynasty_count));
            dynasty.end_year_bp = i == dynasty_count - 1 ?
                0.0 :
                founding_year * (1.0 - static_cast<double>(i + 1) / static_cast<double>(dynasty_count));
            dynasty.duration_years = std::max(0.0, dynasty.start_year_bp - dynasty.end_year_bp);
            dynasty.succession_pressure = clamp(base_succession_pressure + 0.10 * static_cast<double>(i), 0.0, 1.0);
            dynasty.legitimacy_index = clamp(
                0.34 + 0.42 * continuity + 0.18 * region.mean_settlement_score -
                    0.22 * dynasty.succession_pressure - 0.10 * conflict_pressure,
                0.0,
                1.0
            );
            dynasty.dynastic_continuity_index = clamp(
                0.26 + 0.34 * dynasty.legitimacy_index +
                    0.22 * (dynasty.duration_years / std::max(1.0, founding_year)) +
                    0.18 * (1.0 - dynasty.succession_pressure),
                0.0,
                1.0
            );
            if (i == dynasty_count - 1) {
                dynasty.collapse_reason = 0;
            } else if (conflict_pressure > 0.45) {
                dynasty.collapse_reason = 5;
            } else if (population_pressure > 0.68) {
                dynasty.collapse_reason = 4;
            } else if (region.dominant_resource != 0 && region.type == 3) {
                dynasty.collapse_reason = 2;
            } else if (region.route_count == 0) {
                dynasty.collapse_reason = 3;
            } else {
                dynasty.collapse_reason = 1;
            }
            dynasties.push_back(dynasty);
            parent_id = dynasty.id;
        }
    }
    for (DynastyRecord& dynasty : dynasties) {
        if (dynasty.parent_dynasty_id < 0 ||
            dynasty.parent_dynasty_id >= static_cast<int>(dynasties.size())) {
            continue;
        }
        DynastyRecord& parent = dynasties[static_cast<std::size_t>(dynasty.parent_dynasty_id)];
        parent.child_dynasty_ids.push_back(dynasty.id);
        parent.child_dynasty_count = static_cast<int>(parent.child_dynasty_ids.size());
        if (parent.successor_dynasty_id < 0 ||
            dynasty.start_year_bp > dynasties[static_cast<std::size_t>(parent.successor_dynasty_id)].start_year_bp) {
            parent.successor_dynasty_id = dynasty.id;
        }
    }
    return dynasties;
}

std::vector<int> sampled_ids(const std::vector<int>& values, int limit) {
    if (static_cast<int>(values.size()) <= limit) {
        return values;
    }
    std::vector<int> sampled;
    sampled.reserve(static_cast<std::size_t>(limit));
    const double stride = static_cast<double>(values.size()) / static_cast<double>(limit);
    for (int i = 0; i < limit; ++i) {
        sampled.push_back(values[static_cast<std::size_t>(std::floor(stride * static_cast<double>(i)))]);
    }
    return sampled;
}

std::vector<TerritorialSnapshot> generate_territorial_snapshots(
    const Params& params,
    const std::vector<Cell>& cells,
    const std::vector<PoliticalRegion>& political_regions,
    const std::vector<Settlement>& settlements,
    const CulturalLayers& cultural_layers,
    const HistoricalLayers& historical_layers,
    const std::vector<PopulationRegion>& population_regions,
    const std::vector<ConflictRecord>& conflicts
) {
    const std::map<int, int> region_to_culture = region_to_culture_map(cultural_layers);
    std::map<int, const PopulationRegion*> population_by_region;
    for (const PopulationRegion& population : population_regions) {
        population_by_region[population.region_id] = &population;
    }
    std::map<std::pair<int, int>, double> conflict_by_region_era;
    for (const ConflictRecord& conflict : conflicts) {
        conflict_by_region_era[{conflict.region_a, conflict.era_id}] += conflict.intensity;
        conflict_by_region_era[{conflict.region_b, conflict.era_id}] += conflict.intensity;
    }

    std::vector<SnapshotRegion> base_regions(political_regions.size());
    std::vector<Vec3> center_weight(political_regions.size(), Vec3{0.0, 0.0, 0.0});
    std::vector<double> lat_weight(political_regions.size(), 0.0);
    std::vector<double> lon_weight(political_regions.size(), 0.0);
    std::vector<double> area_weight(political_regions.size(), 0.0);
    double land_area = 0.0;
    for (const PoliticalRegion& region : political_regions) {
        SnapshotRegion& snapshot_region = base_regions[static_cast<std::size_t>(region.id)];
        snapshot_region.region_id = region.id;
        snapshot_region.capital_settlement_id = region.capital_settlement_id;
        if (region_to_culture.count(region.id) > 0) {
            snapshot_region.culture_region_id = region_to_culture.at(region.id);
            const CultureRegion& culture = cultural_layers.cultures[static_cast<std::size_t>(snapshot_region.culture_region_id)];
            snapshot_region.language_region_id = culture.language_region_id;
        }
    }
    for (const Cell& cell : cells) {
        if (cell.is_water) {
            continue;
        }
        land_area += cell.area_km2;
        const int region_id = cell.political_region_id;
        if (region_id < 0 || region_id >= static_cast<int>(base_regions.size())) {
            continue;
        }
        SnapshotRegion& snapshot_region = base_regions[static_cast<std::size_t>(region_id)];
        snapshot_region.cell_count += 1;
        snapshot_region.area_km2 += cell.area_km2;
        center_weight[static_cast<std::size_t>(region_id)] = add(
            center_weight[static_cast<std::size_t>(region_id)],
            mul(cell.p, cell.area_km2)
        );
        lat_weight[static_cast<std::size_t>(region_id)] += cell.lat * DEG * cell.area_km2;
        lon_weight[static_cast<std::size_t>(region_id)] += cell.lon * DEG * cell.area_km2;
        area_weight[static_cast<std::size_t>(region_id)] += cell.area_km2;
        bool boundary = false;
        for (int neighbor_id : cell.neighbors) {
            const Cell& neighbor = cells[static_cast<std::size_t>(neighbor_id)];
            if (neighbor.is_water || neighbor.political_region_id != region_id) {
                boundary = true;
                break;
            }
        }
        if (boundary) {
            snapshot_region.boundary_cell_ids.push_back(cell.id);
        }
    }
    for (SnapshotRegion& snapshot_region : base_regions) {
        const int region_id = snapshot_region.region_id;
        if (region_id >= 0 && region_id < static_cast<int>(area_weight.size()) && area_weight[static_cast<std::size_t>(region_id)] > 0.0) {
            snapshot_region.centroid_lat_deg = lat_weight[static_cast<std::size_t>(region_id)] / area_weight[static_cast<std::size_t>(region_id)];
            snapshot_region.centroid_lon_deg = lon_weight[static_cast<std::size_t>(region_id)] / area_weight[static_cast<std::size_t>(region_id)];
        } else if (region_id >= 0 && region_id < static_cast<int>(political_regions.size())) {
            const PoliticalRegion& region = political_regions[static_cast<std::size_t>(region_id)];
            if (region.capital_settlement_id >= 0 && region.capital_settlement_id < static_cast<int>(settlements.size())) {
                const Cell& capital_cell = cells[static_cast<std::size_t>(settlements[static_cast<std::size_t>(region.capital_settlement_id)].cell_id)];
                snapshot_region.centroid_lat_deg = capital_cell.lat * DEG;
                snapshot_region.centroid_lon_deg = capital_cell.lon * DEG;
            }
        }
        if (region_id >= 0 && region_id < static_cast<int>(center_weight.size())) {
            const Vec3 weighted_center = center_weight[static_cast<std::size_t>(region_id)];
            snapshot_region.boundary_ring = watershed_boundary_ring(cells, snapshot_region.boundary_cell_ids, weighted_center, 64);
            snapshot_region.boundary_perimeter_km = ring_perimeter_km(params, snapshot_region.boundary_ring);
            snapshot_region.dissolved_polygon_area_km2 = ring_projected_area_km2(params, snapshot_region.boundary_ring, weighted_center);
            if (snapshot_region.area_km2 > 0.0 && snapshot_region.dissolved_polygon_area_km2 > 0.0) {
                snapshot_region.polygon_area_error_fraction = std::abs(snapshot_region.dissolved_polygon_area_km2 - snapshot_region.area_km2) /
                    snapshot_region.area_km2;
            }
            if (snapshot_region.boundary_perimeter_km > 0.0 && snapshot_region.dissolved_polygon_area_km2 > 0.0) {
                snapshot_region.compactness_index = clamp(
                    4.0 * PI * snapshot_region.dissolved_polygon_area_km2 /
                        std::max(1.0, snapshot_region.boundary_perimeter_km * snapshot_region.boundary_perimeter_km),
                    0.0,
                    1.0
                );
            }
            if (!snapshot_region.boundary_ring.empty()) {
                double min_lon = std::numeric_limits<double>::infinity();
                double max_lon = -std::numeric_limits<double>::infinity();
                for (const LatLon& point : snapshot_region.boundary_ring) {
                    min_lon = std::min(min_lon, point.lon_deg);
                    max_lon = std::max(max_lon, point.lon_deg);
                }
                snapshot_region.crosses_antimeridian = max_lon - min_lon > 180.0;
            }
            const double ring_quality = clamp(static_cast<double>(snapshot_region.boundary_ring.size()) / 24.0, 0.0, 1.0);
            const double area_quality = clamp(1.0 - snapshot_region.polygon_area_error_fraction, 0.0, 1.0);
            snapshot_region.geometry_quality = clamp(0.62 * area_quality + 0.38 * ring_quality, 0.0, 1.0);
        }
        snapshot_region.boundary_cell_ids = sampled_ids(snapshot_region.boundary_cell_ids, 64);
    }

    const std::array<double, 4> area_factors = {0.48, 0.78, 0.64, 1.0};
    const std::array<double, 4> population_factors = {0.34, 0.58, 0.74, 1.0};
    std::vector<TerritorialSnapshot> snapshots;
    snapshots.reserve(historical_layers.eras.size());
    for (const HistoricalEra& era : historical_layers.eras) {
        TerritorialSnapshot snapshot;
        snapshot.id = static_cast<int>(snapshots.size());
        snapshot.era_id = era.id;
        snapshot.dominant_process = era.dominant_process;
        snapshot.year_bp = 0.5 * (era.start_year_bp + era.end_year_bp);
        const double era_area_factor = area_factors[static_cast<std::size_t>(clamp(era.id, 0, 3))];
        const double era_population_factor = population_factors[static_cast<std::size_t>(clamp(era.id, 0, 3))];
        double conflict_sum = 0.0;
        for (SnapshotRegion base_region : base_regions) {
            if (base_region.region_id < 0 || base_region.cell_count == 0) {
                continue;
            }
            const PopulationRegion* population = population_by_region.count(base_region.region_id) > 0 ?
                population_by_region[base_region.region_id] :
                nullptr;
            const double region_conflict = clamp(conflict_by_region_era[{base_region.region_id, era.id}] / 2.0, 0.0, 1.0);
            const double continuity = base_region.culture_region_id >= 0 ?
                cultural_layers.cultures[static_cast<std::size_t>(base_region.culture_region_id)].continuity_index :
                0.5;
            const double stability = clamp(0.42 + 0.42 * continuity - 0.30 * region_conflict + 0.10 * era.mean_connectivity, 0.0, 1.0);
            const double region_area_factor = era_area_factor * (0.82 + 0.18 * stability);
            base_region.area_km2 *= region_area_factor;
            base_region.dissolved_polygon_area_km2 *= region_area_factor;
            base_region.boundary_perimeter_km *= std::sqrt(region_area_factor);
            if (base_region.area_km2 > 0.0 && base_region.dissolved_polygon_area_km2 > 0.0) {
                base_region.polygon_area_error_fraction = std::abs(base_region.dissolved_polygon_area_km2 - base_region.area_km2) /
                    base_region.area_km2;
            }
            if (base_region.boundary_perimeter_km > 0.0 && base_region.dissolved_polygon_area_km2 > 0.0) {
                base_region.compactness_index = clamp(
                    4.0 * PI * base_region.dissolved_polygon_area_km2 /
                        std::max(1.0, base_region.boundary_perimeter_km * base_region.boundary_perimeter_km),
                    0.0,
                    1.0
                );
            }
            const double ring_quality = clamp(static_cast<double>(base_region.boundary_ring.size()) / 24.0, 0.0, 1.0);
            const double area_quality = clamp(1.0 - base_region.polygon_area_error_fraction, 0.0, 1.0);
            base_region.geometry_quality = clamp(0.62 * area_quality + 0.38 * ring_quality, 0.0, 1.0);
            base_region.estimated_population = (population != nullptr ? population->estimated_population : 0.0) *
                era_population_factor * (0.82 + 0.22 * stability);
            base_region.stability_index = stability;
            snapshot.estimated_population += base_region.estimated_population;
            snapshot.assigned_land_fraction += base_region.area_km2;
            if (base_region.area_km2 > snapshot.largest_region_area_km2) {
                snapshot.largest_region_area_km2 = base_region.area_km2;
                snapshot.largest_region_id = base_region.region_id;
            }
            conflict_sum += region_conflict;
            snapshot.regions.push_back(base_region);
        }
        snapshot.region_count = static_cast<int>(snapshot.regions.size());
        snapshot.assigned_land_fraction = land_area > 0.0 ? clamp(snapshot.assigned_land_fraction / land_area, 0.0, 1.0) : 0.0;
        const double largest_share = snapshot.assigned_land_fraction > 0.0 && land_area > 0.0 ?
            snapshot.largest_region_area_km2 / (snapshot.assigned_land_fraction * land_area) :
            0.0;
        snapshot.fragmentation_index = clamp(
            (snapshot.region_count > 1 ? 1.0 - largest_share : 0.0) * 0.72 +
                (snapshot.region_count > 0 ? conflict_sum / static_cast<double>(snapshot.region_count) : 0.0) * 0.28,
            0.0,
            1.0
        );
        snapshots.push_back(snapshot);
    }
    return snapshots;
}

double calibration_score_for_range(double value, double target_min, double target_max) {
    if (value >= target_min && value <= target_max) {
        return 1.0;
    }
    const double width = std::max(1.0e-9, target_max - target_min);
    const double distance = value < target_min ? target_min - value : value - target_max;
    return clamp(1.0 - distance / width, 0.0, 1.0);
}

void add_calibration_check(
    std::vector<CalibrationCheck>& checks,
    int dataset,
    int layer,
    int metric,
    double value,
    double target_min,
    double target_max
) {
    CalibrationCheck check;
    check.id = static_cast<int>(checks.size());
    check.dataset = dataset;
    check.layer = layer;
    check.metric = metric;
    check.value = value;
    check.target_min = target_min;
    check.target_max = target_max;
    check.score = calibration_score_for_range(value, target_min, target_max);
    check.passed = value >= target_min && value <= target_max;
    checks.push_back(check);
}

std::vector<CalibrationCheck> generate_calibration_checks(
    const std::vector<Cell>& cells,
    const std::vector<Watershed>& watersheds
) {
    std::vector<CalibrationCheck> checks;
    if (cells.empty()) {
        return checks;
    }

    double water_count = 0.0;
    double water_area_km2 = 0.0;
    double total_area_km2 = 0.0;
    double land_count = 0.0;
    double land_elev_sum = 0.0;
    double min_elevation = std::numeric_limits<double>::infinity();
    double max_elevation = -std::numeric_limits<double>::infinity();
    double temp_sum = 0.0;
    double land_precip_sum = 0.0;
    double monthly_range_sum = 0.0;
    double river_land_count = 0.0;
    double desert_land_count = 0.0;
    double ice_land_count = 0.0;
    double forest_land_count = 0.0;
    double coastal_land_count = 0.0;

    for (const Cell& cell : cells) {
        const double area_km2 = std::max(0.0, cell.area_km2);
        water_count += cell.is_water ? 1.0 : 0.0;
        water_area_km2 += cell.is_water ? area_km2 : 0.0;
        total_area_km2 += area_km2;
        min_elevation = std::min(min_elevation, cell.elevation_m);
        max_elevation = std::max(max_elevation, cell.elevation_m);
        temp_sum += cell.temperature_c;
        if (!cell.temperature_monthly_c.empty()) {
            const auto [min_temp, max_temp] = std::minmax_element(cell.temperature_monthly_c.begin(), cell.temperature_monthly_c.end());
            monthly_range_sum += *max_temp - *min_temp;
        }
        if (cell.is_water) {
            continue;
        }
        land_count += 1.0;
        land_elev_sum += cell.elevation_m;
        land_precip_sum += cell.precipitation_mm_y;
        if (cell.is_river) {
            river_land_count += 1.0;
        }
        if (cell.biome == 9 || cell.biome == 10) {
            desert_land_count += 1.0;
        }
        if (cell.biome == 3 || cell.ice_thickness_m > 25.0) {
            ice_land_count += 1.0;
        }
        if (cell.biome == 5 || cell.biome == 6 || cell.biome == 12 || cell.biome == 13) {
            forest_land_count += 1.0;
        }
        for (int neighbor_id : cell.neighbors) {
            if (neighbor_id >= 0 && neighbor_id < static_cast<int>(cells.size()) && cells[static_cast<std::size_t>(neighbor_id)].is_water) {
                coastal_land_count += 1.0;
                break;
            }
        }
    }

    double endorheic_watersheds = 0.0;
    for (const Watershed& watershed : watersheds) {
        endorheic_watersheds += watershed.is_endorheic ? 1.0 : 0.0;
    }

    const double cell_count = static_cast<double>(cells.size());
    add_calibration_check(
        checks,
        0,
        0,
        0,
        total_area_km2 > 0.0 ? water_area_km2 / total_area_km2 : water_count / cell_count,
        0.55,
        0.78
    );
    add_calibration_check(checks, 0, 0, 1, land_count > 0.0 ? land_elev_sum / land_count : 0.0, 120.0, 1800.0);
    add_calibration_check(checks, 0, 0, 2, max_elevation - min_elevation, 3500.0, 17000.0);
    add_calibration_check(checks, 1, 1, 3, temp_sum / cell_count, -5.0, 28.0);
    add_calibration_check(checks, 1, 1, 4, land_count > 0.0 ? land_precip_sum / land_count : 0.0, 250.0, 2300.0);
    add_calibration_check(checks, 1, 1, 5, monthly_range_sum / cell_count, 2.0, 38.0);
    add_calibration_check(checks, 2, 2, 6, land_count > 0.0 ? river_land_count / land_count : 0.0, 0.005, 0.14);
    add_calibration_check(
        checks,
        2,
        2,
        7,
        watersheds.empty() ? 0.0 : endorheic_watersheds / static_cast<double>(watersheds.size()),
        0.0,
        0.55
    );
    add_calibration_check(checks, 1, 3, 8, land_count > 0.0 ? desert_land_count / land_count : 0.0, 0.04, 0.48);
    add_calibration_check(checks, 1, 3, 9, land_count > 0.0 ? ice_land_count / land_count : 0.0, 0.0, 0.38);
    add_calibration_check(checks, 1, 3, 10, land_count > 0.0 ? forest_land_count / land_count : 0.0, 0.08, 0.58);
    add_calibration_check(checks, 3, 4, 11, land_count > 0.0 ? coastal_land_count / land_count : 0.0, 0.03, 0.48);
    return checks;
}

template <std::size_t N>
std::string counts_json(const std::map<std::string, int>& counts) {
    (void)N;
    std::string out = "{";
    bool first = true;
    for (const auto& [key, value] : counts) {
        add_int(out, first, key.c_str(), value);
    }
    out += "}";
    return out;
}

std::string summary_json(
    const Params& params,
    const std::vector<Cell>& cells,
    const std::vector<Watershed>& watersheds,
    const std::vector<LakeBasin>& lake_basins,
    const std::vector<CoastalFeature>& coastal_features,
    const std::vector<SedimentaryBasin>& sedimentary_basins,
    const std::vector<StratigraphicColumn>& stratigraphic_columns,
    const std::vector<IceSheet>& ice_sheets,
    const std::vector<PoliticalRegion>& political_regions,
    const std::vector<BorderSegment>& borders,
    const std::vector<TradeFlow>& trade_flows,
    const CulturalLayers& cultural_layers,
    const HistoricalLayers& historical_layers,
    const std::vector<PopulationRegion>& population_regions,
    const std::vector<ConflictRecord>& conflicts,
    const std::vector<DynastyRecord>& dynasties,
    const std::vector<TerritorialSnapshot>& territorial_snapshots,
    const std::vector<CalibrationCheck>& calibration_checks,
    const std::vector<Settlement>& settlements,
    const std::vector<Route>& routes,
    const std::vector<EarthSystemFeedbackStep>& feedback_history,
    const std::vector<PlateMotionStep>& plate_motion_history,
    const std::vector<NumericDepressionFillEvent>& numeric_depression_fill_history,
    const std::vector<HillslopeSedimentTransportStage>& hillslope_transport_history,
    const std::vector<GlacialSedimentTransportStage>& glacial_transport_history
) {
    double ocean = 0.0, min_elev = std::numeric_limits<double>::infinity(), max_elev = -std::numeric_limits<double>::infinity();
    double surface_area_km2 = 0.0, ocean_area_km2 = 0.0, ocean_volume_km3 = 0.0;
    double cell_area_squared_sum = 0.0;
    double min_cell_area_km2 = std::numeric_limits<double>::infinity(), max_cell_area_km2 = 0.0;
    double land_sum = 0.0, land_count = 0.0;
    double sediment_sum = 0.0;
    double sediment_production_sum = 0.0;
    double sediment_deposition_sum = 0.0;
    double sediment_export_sum = 0.0;
    double sediment_production_volume_km3 = 0.0;
    double sediment_deposition_volume_km3 = 0.0;
    double sediment_export_volume_km3 = 0.0;
    double sediment_inventory_volume_km3 = 0.0;
    double sediment_alluvium_entrainment_volume_km3 = 0.0;
    double sediment_bedrock_erosion_volume_km3 = 0.0;
    double initial_isostatic_sum = 0.0, initial_thermal_sum = 0.0, initial_ridge_sum = 0.0;
    double initial_orogenic_sum = 0.0, initial_volcanic_sum = 0.0, initial_trench_sum = 0.0;
    double initial_rift_sum = 0.0, initial_transform_sum = 0.0, initial_roughness_sum = 0.0;
    double initial_elevation_sum = 0.0, volcanic_potential_sum = 0.0, uplift_rate_sum = 0.0;
    double orographic_sum = 0.0, rain_shadow_sum = 0.0;
    double humidity_transport_sum = 0.0, upwind_fetch_sum = 0.0, advected_moisture_sum = 0.0;
    double surface_pressure_anomaly_sum = 0.0, vertical_velocity_sum = 0.0, wind_divergence_sum = 0.0;
    double seasonal_wind_speed_sum = 0.0, seasonal_wind_reversal_sum = 0.0;
    double ocean_current_strength_sum = 0.0, ocean_current_temp_sum = 0.0, ocean_current_moisture_sum = 0.0;
    double vapor_evaporation_sum = 0.0, moisture_convergence_sum = 0.0, orographic_rainout_sum = 0.0;
    double precipitation_recycling_sum = 0.0, vapor_deficit_sum = 0.0, vapor_budget_residual_abs_sum = 0.0;
    double ice_sum = 0.0, glacial_erosion_sum = 0.0;
    double ice_surface_mass_balance_sum = 0.0, basal_sliding_sum = 0.0, ice_velocity_sum = 0.0;
    double ice_sheet_retreat_rate_sum = 0.0;
    double moraine_deposition_sum = 0.0, deglaciation_age_sum = 0.0;
    int river_count = 0, lake_count = 0, river_edges = 0, downhill_edges = 0;
    int high_volcanic_potential_cells = 0;
    int rain_shadowed_cells = 0;
    int ascending_air_cells = 0;
    int glacier_cells = 0;
    int moraine_deposition_cells = 0, deglaciated_cells = 0;
    int spill_corrected_cells = 0, closed_basin_cells = 0;
    int equal_filled_raw_downhill_reroute_count = 0;
    int hydrologic_surface_conditioned_cell_count = 0;
    int equal_filled_flow_edge_count = 0;
    int raw_uphill_flow_edge_count = 0;
    int non_downhill_hydrologic_flow_edge_count = 0;
    int terminal_land_sink_count = 0;
    int avoidable_equal_filled_raw_downhill_sink_count = 0;
    int flow_cycle_cell_count = 0;
    int endorheic_watersheds = 0;
    int watershed_geometry_count = 0;
    int watershed_polygon_count = 0;
    int largest_watershed_boundary_cell_count = 0;
    int overflowing_lake_basins = 0;
    int staged_overflow_lake_basins = 0;
    int high_avulsion_risk_lake_basins = 0;
    int preserved_geologic_depressions = 0;
    int corrected_numeric_depressions = 0;
    int temporary_numeric_lake_depressions = 0;
    int closed_depressions = 0;
    int depression_component_cell_count = 0;
    int numeric_depression_filled_unique_cell_count = 0;
    int numeric_depression_fill_cell_event_count = 0;
    int numeric_depression_breach_cell_event_count = 0;
    int numeric_depression_temporary_lake_cell_event_count = 0;
    int numeric_depression_temporary_lake_unique_cell_count = 0;
    int fluvial_sediment_routed_cell_count = 0;
    int fluvial_sediment_terminal_capture_cell_count = 0;
    int hillslope_sediment_unique_source_cell_count = 0;
    int hillslope_sediment_unique_target_cell_count = 0;
    int politically_assigned_land_cells = 0;
    int culturally_assigned_land_cells = 0;
    int linguistically_assigned_land_cells = 0;
    int migration_events = 0;
    int dynastic_change_events = 0;
    int language_lineages = 0;
    int high_intensity_conflicts = 0;
    int high_economic_disruption_conflicts = 0;
    int dynastic_lineages = 0;
    int dynasty_roots = 0;
    int dynasty_successor_links = 0;
    int max_dynasty_lineage_depth = 0;
    int snapshot_region_records = 0;
    int snapshot_polygon_region_count = 0;
    int calibration_pass_count = 0;
    double max_depression_depth = 0.0;
    double cumulative_numeric_depression_fill_sum_m = 0.0;
    double max_cumulative_numeric_depression_fill_m = 0.0;
    double cumulative_numeric_depression_breach_excavation_sum_m = 0.0;
    double cumulative_numeric_depression_breach_deposition_sum_m = 0.0;
    double max_hydrologic_surface_adjustment_m = 0.0;
    double max_raw_uphill_flow_step_m = 0.0;
    double largest_watershed_area = 0.0;
    double largest_watershed_polygon_area = 0.0;
    double watershed_polygon_area_error_sum = 0.0;
    double watershed_compactness_sum = 0.0;
    double watershed_geometry_quality_sum = 0.0;
    double watershed_boundary_perimeter_sum = 0.0;
    double lake_fill_fraction_sum = 0.0;
    double lake_storage_capacity_sum = 0.0;
    double lake_annual_runoff_sum = 0.0;
    double lake_overflow_path_length_sum = 0.0;
    double lake_avulsion_risk_sum = 0.0;
    double largest_sedimentary_basin_area = 0.0;
    double sedimentary_basin_thickness_sum = 0.0;
    double stratigraphic_thickness_sum = 0.0;
    int stratigraphic_layer_count = 0;
    int active_stratigraphic_columns = 0;
    int max_stratigraphic_layer_count = 0;
    double coastal_migration_sum = 0.0;
    double largest_region_area = 0.0;
    double largest_culture_area = 0.0;
    double historical_instability_sum = 0.0;
    double cultural_continuity_sum = 0.0;
    double dynastic_continuity_sum = 0.0;
    double conflict_duration_sum = 0.0;
    double conflict_mobilized_sum = 0.0;
    double conflict_logistics_strain_sum = 0.0;
    double conflict_economic_disruption_sum = 0.0;
    double conflict_casualty_rate_sum = 0.0;
    double max_conflict_casualty_rate = 0.0;
    double language_change_sum = 0.0;
    double phonological_complexity_sum = 0.0;
    double sound_shift_sum = 0.0;
    double inherited_phonology_sum = 0.0;
    double estimated_world_population = 0.0;
    double population_pressure_sum = 0.0;
    double conflict_intensity_sum = 0.0;
    double snapshot_fragmentation_sum = 0.0;
    double snapshot_polygon_area_error_sum = 0.0;
    double snapshot_compactness_sum = 0.0;
    double snapshot_geometry_quality_sum = 0.0;
    double snapshot_boundary_perimeter_sum = 0.0;
    double calibration_score_sum = 0.0;
    double border_length = 0.0;
    double trade_volume = 0.0;
    double trade_friction = 0.0;
    int natural_border_segments = 0;
    int interregional_trade_flows = 0;
    int coastal_bar_features = 0;
    int prograding_coastal_features = 0;
    int eroding_coastal_features = 0;
    int active_sedimentary_basins = 0;
    std::vector<double> land_elev;
    std::set<int> basin_ids, endorheic_basin_ids;
    std::map<std::string, int> boundary_counts, crust_counts, biome_counts, resource_counts;
    std::map<std::string, int> water_body_counts, atmospheric_cell_counts, landform_counts;
    for (const Cell& cell : cells) {
        const double area_km2 = std::max(0.0, cell.area_km2);
        ocean += cell.is_water ? 1.0 : 0.0;
        surface_area_km2 += area_km2;
        ocean_area_km2 += cell.is_water ? area_km2 : 0.0;
        ocean_volume_km3 += cell.is_water ?
            std::max(0.0, cell.water_depth_m) * area_km2 / 1000.0 : 0.0;
        cell_area_squared_sum += area_km2 * area_km2;
        min_cell_area_km2 = std::min(min_cell_area_km2, area_km2);
        max_cell_area_km2 = std::max(max_cell_area_km2, area_km2);
        min_elev = std::min(min_elev, cell.elevation_m);
        max_elev = std::max(max_elev, cell.elevation_m);
        cumulative_numeric_depression_fill_sum_m +=
            cell.cumulative_numeric_depression_fill_m;
        max_cumulative_numeric_depression_fill_m = std::max(
            max_cumulative_numeric_depression_fill_m,
            cell.cumulative_numeric_depression_fill_m
        );
        numeric_depression_fill_cell_event_count +=
            cell.numeric_depression_fill_event_count;
        if (cell.numeric_depression_fill_event_count > 0) {
            numeric_depression_filled_unique_cell_count++;
        }
        cumulative_numeric_depression_breach_excavation_sum_m +=
            cell.cumulative_numeric_depression_breach_excavation_m;
        cumulative_numeric_depression_breach_deposition_sum_m +=
            cell.cumulative_numeric_depression_breach_deposition_m;
        numeric_depression_breach_cell_event_count +=
            cell.numeric_depression_breach_event_count;
        numeric_depression_temporary_lake_cell_event_count +=
            cell.numeric_depression_temporary_lake_event_count;
        if (cell.numeric_depression_temporary_lake_event_count > 0) {
            numeric_depression_temporary_lake_unique_cell_count++;
        }
        if (cell.fluvial_sediment_routing_event_count > 0) {
            fluvial_sediment_routed_cell_count++;
        }
        if (cell.fluvial_sediment_terminal_capture_volume_km3 > 0.0) {
            fluvial_sediment_terminal_capture_cell_count++;
        }
        if (cell.hillslope_sediment_outgoing_edge_count > 0) {
            hillslope_sediment_unique_source_cell_count++;
        }
        if (cell.hillslope_sediment_incoming_edge_count > 0) {
            hillslope_sediment_unique_target_cell_count++;
        }
        max_hydrologic_surface_adjustment_m = std::max(
            max_hydrologic_surface_adjustment_m,
            cell.hydrologic_surface_elevation_m - cell.filled_elevation_m
        );
        if (cell.hydrologic_surface_conditioned) {
            hydrologic_surface_conditioned_cell_count++;
        }
        if (cell.flow_to >= 0) {
            const Cell& receiver = cells[static_cast<std::size_t>(cell.flow_to)];
            if (std::abs(cell.filled_elevation_m - receiver.filled_elevation_m) <= 1.0e-9) {
                equal_filled_flow_edge_count++;
            }
            if (cell.elevation_m + 1.0e-9 < receiver.elevation_m) {
                raw_uphill_flow_edge_count++;
                max_raw_uphill_flow_step_m = std::max(
                    max_raw_uphill_flow_step_m,
                    receiver.elevation_m - cell.elevation_m
                );
            }
            if (cell.hydrologic_surface_elevation_m <=
                receiver.hydrologic_surface_elevation_m) {
                non_downhill_hydrologic_flow_edge_count++;
            }
        }
        sediment_sum += cell.sediment_thickness_m;
        sediment_production_sum += cell.sediment_production_m;
        sediment_deposition_sum += cell.sediment_deposition_m;
        sediment_export_sum += cell.sediment_export_m;
        sediment_production_volume_km3 +=
            cell.sediment_production_m * area_km2 / 1000.0;
        sediment_deposition_volume_km3 +=
            cell.sediment_deposition_m * area_km2 / 1000.0;
        sediment_export_volume_km3 +=
            cell.sediment_export_m * area_km2 / 1000.0;
        sediment_inventory_volume_km3 +=
            cell.sediment_thickness_m * area_km2 / 1000.0;
        sediment_alluvium_entrainment_volume_km3 +=
            cell.sediment_alluvium_entrainment_m * area_km2 / 1000.0;
        sediment_bedrock_erosion_volume_km3 +=
            cell.sediment_bedrock_erosion_m * area_km2 / 1000.0;
        initial_isostatic_sum += cell.initial_isostatic_elevation_m;
        initial_thermal_sum += cell.initial_thermal_subsidence_m;
        initial_ridge_sum += cell.initial_ridge_uplift_m;
        initial_orogenic_sum += cell.initial_orogenic_uplift_m;
        initial_volcanic_sum += cell.initial_volcanic_uplift_m;
        initial_trench_sum += cell.initial_trench_subsidence_m;
        initial_rift_sum += cell.initial_rift_subsidence_m;
        initial_transform_sum += cell.initial_transform_fault_relief_m;
        initial_roughness_sum += cell.initial_secondary_roughness_m;
        initial_elevation_sum += cell.initial_elevation_m;
        volcanic_potential_sum += cell.volcanic_potential_index;
        uplift_rate_sum += cell.uplift_rate;
        if (cell.volcanic_potential_index >= 0.65) {
            high_volcanic_potential_cells++;
        }
        orographic_sum += cell.orographic_factor;
        rain_shadow_sum += cell.rain_shadow_factor;
        humidity_transport_sum += cell.humidity_transport_index;
        upwind_fetch_sum += cell.upwind_ocean_fetch_km;
        advected_moisture_sum += cell.advected_moisture_factor;
        surface_pressure_anomaly_sum += cell.surface_pressure_anomaly_hpa;
        vertical_velocity_sum += cell.vertical_velocity_index;
        wind_divergence_sum += cell.wind_divergence_index;
        seasonal_wind_speed_sum += cell.mean_seasonal_wind_speed;
        seasonal_wind_reversal_sum += cell.seasonal_wind_reversal_index;
        vapor_evaporation_sum += cell.vapor_evaporation_mm_y;
        moisture_convergence_sum += cell.moisture_convergence_mm_y;
        orographic_rainout_sum += cell.orographic_rainout_mm_y;
        precipitation_recycling_sum += cell.precipitation_recycling_fraction;
        vapor_deficit_sum += cell.vapor_deficit_mm_y;
        vapor_budget_residual_abs_sum += std::abs(cell.vapor_budget_residual_mm_y);
        ocean_current_strength_sum += std::sqrt(
            cell.ocean_current_east * cell.ocean_current_east +
            cell.ocean_current_north * cell.ocean_current_north
        );
        ocean_current_temp_sum += cell.ocean_current_temperature_c;
        ocean_current_moisture_sum += cell.ocean_current_moisture_factor;
        ice_sum += cell.ice_thickness_m;
        glacial_erosion_sum += cell.glacial_erosion_m;
        moraine_deposition_sum += cell.moraine_deposition_m;
        if (cell.moraine_deposition_m > 0.0) {
            moraine_deposition_cells++;
        }
        if (cell.deglaciation_age_ka > 0.0) {
            deglaciation_age_sum += cell.deglaciation_age_ka;
            deglaciated_cells++;
        }
        if (!cell.is_water && cell.ice_thickness_m > 25.0) {
            glacier_cells++;
            ice_surface_mass_balance_sum += cell.ice_surface_mass_balance_m_y;
            basal_sliding_sum += cell.basal_sliding_index;
            ice_velocity_sum += cell.ice_velocity_m_y;
        }
        if (!cell.is_water) {
            if (cell.political_region_id >= 0) {
                politically_assigned_land_cells++;
            }
            if (cell.culture_region_id >= 0) {
                culturally_assigned_land_cells++;
            }
            if (cell.language_region_id >= 0) {
                linguistically_assigned_land_cells++;
            }
            max_depression_depth = std::max(max_depression_depth, cell.depression_depth_m);
            if (cell.depression_component_id >= 0) {
                depression_component_cell_count++;
            }
            if (cell.depression_depth_m > 0.5 && cell.flow_to == cell.spill_to && !cell.is_lake) {
                spill_corrected_cells++;
            }
            if (cell.is_closed_basin) {
                closed_basin_cells++;
            }
            if (cell.equal_filled_raw_downhill_rerouted) {
                equal_filled_raw_downhill_reroute_count++;
            }
            if (cell.flow_to < 0) {
                terminal_land_sink_count++;
            }
        }
        if (!cell.is_water && cell.rain_shadow_factor < 0.86) {
            rain_shadowed_cells++;
        }
        if (cell.vertical_velocity_index > 0.12) {
            ascending_air_cells++;
        }
        boundary_counts[BOUNDARY_NAMES[cell.boundary_type]]++;
        crust_counts[CRUST_NAMES[cell.crust_type]]++;
        biome_counts[BIOME_NAMES[cell.biome]]++;
        resource_counts[RESOURCE_NAMES[cell.resource]]++;
        water_body_counts[WATER_BODY_NAMES[cell.water_body]]++;
        atmospheric_cell_counts[ATMOSPHERIC_CELL_NAMES[cell.atmospheric_cell]]++;
        landform_counts[LANDFORM_NAMES[cell.landform]]++;
        if (!cell.is_water) {
            land_sum += cell.elevation_m;
            land_count += 1.0;
            land_elev.push_back(cell.elevation_m);
            if (cell.basin_id >= 0 && cell.basin_id < static_cast<int>(cells.size())) {
                basin_ids.insert(cell.basin_id);
                if (!cells[cell.basin_id].is_water) {
                    endorheic_basin_ids.insert(cell.basin_id);
                }
            }
        }
        if (cell.is_river) {
            river_count++;
            if (cell.flow_to >= 0) {
                river_edges++;
                if (cell.hydrologic_surface_elevation_m >
                    cells[cell.flow_to].hydrologic_surface_elevation_m) {
                    downhill_edges++;
                }
            }
        }
        if (cell.is_lake) {
            lake_count++;
        }
    }
    const auto final_flow_path_reaches = [&](int start, int target) {
        int current = start;
        for (int step = 0; step <= static_cast<int>(cells.size()); ++step) {
            if (current == target) {
                return true;
            }
            if (current < 0 || current >= static_cast<int>(cells.size())) {
                return false;
            }
            current = cells[static_cast<std::size_t>(current)].flow_to;
        }
        return true;
    };
    for (const Cell& cell : cells) {
        if (cell.is_water || cell.flow_to >= 0) {
            continue;
        }
        for (int neighbor : cell.neighbors) {
            const Cell& neighbor_cell = cells[static_cast<std::size_t>(neighbor)];
            if (
                std::abs(cell.filled_elevation_m - neighbor_cell.filled_elevation_m) <= 1.0e-9 &&
                cell.elevation_m - neighbor_cell.elevation_m > 1.0e-9 &&
                !final_flow_path_reaches(neighbor, cell.id)
            ) {
                avoidable_equal_filled_raw_downhill_sink_count++;
                break;
            }
        }
    }
    std::vector<int> summary_upstream_count(cells.size(), 0);
    for (const Cell& cell : cells) {
        if (cell.flow_to >= 0 && cell.flow_to < static_cast<int>(cells.size())) {
            summary_upstream_count[static_cast<std::size_t>(cell.flow_to)]++;
        }
    }
    std::queue<int> summary_flow_queue;
    for (int i = 0; i < static_cast<int>(cells.size()); ++i) {
        if (summary_upstream_count[static_cast<std::size_t>(i)] == 0) {
            summary_flow_queue.push(i);
        }
    }
    int summary_processed_flow_cells = 0;
    while (!summary_flow_queue.empty()) {
        const int current = summary_flow_queue.front();
        summary_flow_queue.pop();
        summary_processed_flow_cells++;
        const int to = cells[static_cast<std::size_t>(current)].flow_to;
        if (to < 0 || to >= static_cast<int>(cells.size())) {
            continue;
        }
        int& remaining = summary_upstream_count[static_cast<std::size_t>(to)];
        remaining--;
        if (remaining == 0) {
            summary_flow_queue.push(to);
        }
    }
    flow_cycle_cell_count = static_cast<int>(cells.size()) - summary_processed_flow_cells;
    for (const Watershed& watershed : watersheds) {
        largest_watershed_area = std::max(largest_watershed_area, watershed.area_km2);
        if (!watershed.boundary_ring.empty()) {
            watershed_geometry_count++;
        }
        if (watershed.dissolved_polygon_area_km2 > 0.0) {
            watershed_polygon_count++;
            largest_watershed_polygon_area = std::max(largest_watershed_polygon_area, watershed.dissolved_polygon_area_km2);
            watershed_polygon_area_error_sum += watershed.polygon_area_error_fraction;
            watershed_compactness_sum += watershed.compactness_index;
            watershed_geometry_quality_sum += watershed.geometry_quality;
            watershed_boundary_perimeter_sum += watershed.boundary_perimeter_km;
        }
        largest_watershed_boundary_cell_count = std::max(
            largest_watershed_boundary_cell_count,
            static_cast<int>(watershed.boundary_cell_ids.size())
        );
        if (watershed.is_endorheic) {
            endorheic_watersheds++;
        }
    }
    for (const LakeBasin& basin : lake_basins) {
        if (basin.overflows) {
            overflowing_lake_basins++;
        }
        if (basin.overflow_stage_count > 0) {
            staged_overflow_lake_basins++;
        }
        if (basin.avulsion_risk >= 0.65) {
            high_avulsion_risk_lake_basins++;
        }
        if (basin.is_geologic && basin.depression_policy != 1 &&
            basin.depression_policy != 5) {
            preserved_geologic_depressions++;
        }
        if (basin.depression_policy == 1) {
            corrected_numeric_depressions++;
        }
        if (basin.depression_policy == 5) {
            temporary_numeric_lake_depressions++;
        }
        if (basin.depression_policy == 2 || basin.depression_policy == 4 ||
            (basin.depression_policy == 5 && !basin.overflows)) {
            closed_depressions++;
        }
        lake_fill_fraction_sum += basin.fill_fraction;
        lake_storage_capacity_sum += basin.storage_capacity_km3;
        lake_annual_runoff_sum += basin.annual_runoff_km3;
        lake_overflow_path_length_sum += basin.overflow_path_length_km;
        lake_avulsion_risk_sum += basin.avulsion_risk;
    }
    for (const CoastalFeature& feature : coastal_features) {
        if (feature.type == 1 || feature.type == 2) {
            coastal_bar_features++;
        }
        if (feature.shoreline_trend == 1 || feature.shoreline_trend == 4) {
            prograding_coastal_features++;
        }
        if (feature.shoreline_trend == 2 || feature.shoreline_trend == 3) {
            eroding_coastal_features++;
        }
        coastal_migration_sum += feature.migration_rate_m_y;
    }
    for (const SedimentaryBasin& basin : sedimentary_basins) {
        largest_sedimentary_basin_area = std::max(largest_sedimentary_basin_area, basin.area_km2);
        sedimentary_basin_thickness_sum += basin.mean_sediment_thickness_m;
        if (basin.is_active) {
            active_sedimentary_basins++;
        }
    }
    for (const StratigraphicColumn& column : stratigraphic_columns) {
        stratigraphic_thickness_sum += column.total_thickness_m;
        stratigraphic_layer_count += static_cast<int>(column.layers.size());
        max_stratigraphic_layer_count = std::max(max_stratigraphic_layer_count, static_cast<int>(column.layers.size()));
        if (column.is_active) {
            active_stratigraphic_columns++;
        }
    }
    for (const IceSheet& sheet : ice_sheets) {
        ice_sheet_retreat_rate_sum += sheet.retreat_rate_m_y;
    }
    for (const PoliticalRegion& region : political_regions) {
        largest_region_area = std::max(largest_region_area, region.area_km2);
    }
    for (const CultureRegion& culture : cultural_layers.cultures) {
        largest_culture_area = std::max(largest_culture_area, culture.area_km2);
        cultural_continuity_sum += culture.continuity_index;
    }
    for (const LanguageRegion& language : cultural_layers.language_regions) {
        if (language.parent_language_region_id >= 0) {
            language_lineages++;
        }
        language_change_sum += language.change_rate;
        phonological_complexity_sum += language.phonological_complexity;
        sound_shift_sum += language.sound_shift_index;
        inherited_phonology_sum += language.inherited_phonology_fraction;
    }
    for (const HistoricalEvent& event : historical_layers.events) {
        historical_instability_sum += event.pressure_index;
        if (event.type == 1) {
            dynastic_change_events++;
        } else if (event.type == 2) {
            migration_events++;
        }
    }
    for (const PopulationRegion& population : population_regions) {
        estimated_world_population += population.estimated_population;
        population_pressure_sum += population.population_pressure;
    }
    const double conflict_intensity_scale = std::pow(10.0, static_cast<double>(clamp(params.float_precision, 0, 8)));
    for (const ConflictRecord& conflict : conflicts) {
        conflict_intensity_sum += conflict.intensity;
        conflict_duration_sum += conflict.war_duration_years;
        conflict_mobilized_sum += conflict.mobilized_population;
        conflict_logistics_strain_sum += conflict.logistics_strain_index;
        conflict_economic_disruption_sum += conflict.economic_disruption_index;
        conflict_casualty_rate_sum += conflict.casualty_rate;
        max_conflict_casualty_rate = std::max(max_conflict_casualty_rate, conflict.casualty_rate);
        const double emitted_intensity = std::round(conflict.intensity * conflict_intensity_scale) / conflict_intensity_scale;
        if (emitted_intensity >= 0.65) {
            high_intensity_conflicts++;
        }
        if (conflict.economic_disruption_index >= 0.65) {
            high_economic_disruption_conflicts++;
        }
    }
    for (const DynastyRecord& dynasty : dynasties) {
        if (dynasty.parent_dynasty_id >= 0) {
            dynastic_lineages++;
        } else {
            dynasty_roots++;
        }
        if (dynasty.successor_dynasty_id >= 0) {
            dynasty_successor_links++;
        }
        max_dynasty_lineage_depth = std::max(max_dynasty_lineage_depth, dynasty.lineage_depth);
        dynastic_continuity_sum += dynasty.dynastic_continuity_index;
    }
    for (const TerritorialSnapshot& snapshot : territorial_snapshots) {
        snapshot_region_records += static_cast<int>(snapshot.regions.size());
        snapshot_fragmentation_sum += snapshot.fragmentation_index;
        for (const SnapshotRegion& region : snapshot.regions) {
            if (region.dissolved_polygon_area_km2 > 0.0) {
                snapshot_polygon_region_count++;
                snapshot_polygon_area_error_sum += region.polygon_area_error_fraction;
                snapshot_compactness_sum += region.compactness_index;
                snapshot_geometry_quality_sum += region.geometry_quality;
                snapshot_boundary_perimeter_sum += region.boundary_perimeter_km;
            }
        }
    }
    for (const CalibrationCheck& check : calibration_checks) {
        if (check.passed) {
            calibration_pass_count++;
        }
        calibration_score_sum += check.score;
    }
    for (const BorderSegment& border : borders) {
        border_length += border.length_km;
        if (border.type != 0) {
            natural_border_segments++;
        }
    }
    for (const TradeFlow& flow : trade_flows) {
        trade_volume += flow.volume_index;
        trade_friction += flow.friction;
        if (flow.interregional) {
            interregional_trade_flows++;
        }
    }
    double mountain_threshold = 2000.0;
    if (!land_elev.empty()) {
        std::sort(land_elev.begin(), land_elev.end());
        mountain_threshold = std::max(1600.0, land_elev[static_cast<std::size_t>(0.88 * (land_elev.size() - 1))]);
    }
    int high_mountains = 0, high_mountains_near_conv = 0;
    for (const Cell& cell : cells) {
        if (!cell.is_water && cell.elevation_m >= mountain_threshold) {
            high_mountains++;
            if (cell.boundary_convergent > 0.20 || cell.crust_type == 5) {
                high_mountains_near_conv++;
            }
        }
    }
    std::set<std::pair<int, int>> numeric_depression_fill_stage_passes;
    std::set<int> numeric_depression_fill_unique_cell_ids;
    int numeric_depression_fill_cell_application_count = 0;
    int numeric_depression_fill_geologic_source_event_count = 0;
    double numeric_depression_fill_area_km2 = 0.0;
    double numeric_depression_fill_volume_km3 = 0.0;
    double numeric_depression_fill_depth_sum_m = 0.0;
    double max_numeric_depression_fill_depth_m = 0.0;
    double numeric_depression_fill_candidate_area_km2 = 0.0;
    double numeric_depression_fill_candidate_volume_km3 = 0.0;
    int numeric_depression_fill_candidate_cell_application_count = 0;
    int numeric_depression_breach_feasible_event_count = 0;
    int numeric_depression_breach_lower_volume_event_count = 0;
    int numeric_depression_breach_depth_bound_pass_event_count = 0;
    int numeric_depression_breach_capacity_pass_event_count = 0;
    int numeric_depression_breach_selected_event_count = 0;
    int numeric_depression_breach_excavation_cell_application_count = 0;
    int numeric_depression_breach_deposition_cell_application_count = 0;
    int numeric_depression_temporary_lake_event_count = 0;
    int numeric_depression_temporary_lake_cell_application_count = 0;
    std::set<int> numeric_depression_temporary_lake_unique_cell_ids;
    double numeric_depression_temporary_lake_candidate_area_km2 = 0.0;
    double numeric_depression_temporary_lake_candidate_volume_km3 = 0.0;
    double max_numeric_depression_temporary_lake_depth_m = 0.0;
    double numeric_depression_feasible_breach_excavation_volume_km3 = 0.0;
    double numeric_depression_lower_volume_hybrid_adjustment_volume_km3 = 0.0;
    double numeric_depression_selected_breach_excavation_volume_km3 = 0.0;
    double numeric_depression_selected_breach_deposition_volume_km3 = 0.0;
    double numeric_depression_alluvium_entrainment_volume_km3 = 0.0;
    double numeric_depression_bedrock_erosion_volume_km3 = 0.0;
    double numeric_depression_correction_mass_balance_residual_km3 = 0.0;
    double numeric_depression_breach_excavation_depth_sum_m = 0.0;
    double numeric_depression_breach_deposition_depth_sum_m = 0.0;
    double numeric_depression_breach_path_length_sum_km = 0.0;
    double max_numeric_depression_breach_path_length_km = 0.0;
    double max_numeric_depression_breach_excavation_depth_m = 0.0;
    double max_lower_volume_breach_excavation_depth_m = 0.0;
    for (const NumericDepressionFillEvent& event : numeric_depression_fill_history) {
        if (event.cell_ids.size() !=
                event.sediment_thickness_before_correction_m_by_cell.size() ||
            event.breach_path_cell_ids.size() !=
                event.breach_elevation_before_m_by_cell.size() ||
            event.breach_path_cell_ids.size() !=
                event.breach_target_elevation_m_by_cell.size() ||
            event.breach_path_cell_ids.size() !=
                event.breach_excavation_depth_m_by_cell.size() ||
            event.breach_path_cell_ids.size() !=
                event.breach_sediment_thickness_before_excavation_m_by_cell.size() ||
            event.breach_path_cell_ids.size() !=
                event.breach_alluvium_entrainment_depth_m_by_cell.size() ||
            event.breach_path_cell_ids.size() !=
                event.breach_bedrock_erosion_depth_m_by_cell.size()) {
            throw std::runtime_error("numeric depression breach provenance is inconsistent");
        }
        numeric_depression_fill_stage_passes.insert(
            {event.feedback_stage_id, event.stabilization_pass}
        );
        numeric_depression_fill_candidate_area_km2 += event.area_km2;
        numeric_depression_fill_candidate_volume_km3 += event.fill_volume_km3;
        numeric_depression_fill_candidate_cell_application_count +=
            static_cast<int>(event.cell_ids.size());
        numeric_depression_breach_feasible_event_count +=
            event.breach_feasible ? 1 : 0;
        numeric_depression_breach_lower_volume_event_count +=
            event.breach_has_lower_adjustment_volume ? 1 : 0;
        numeric_depression_breach_depth_bound_pass_event_count +=
            event.breach_depth_bound_passed ? 1 : 0;
        numeric_depression_breach_capacity_pass_event_count +=
            event.breach_deposition_capacity_sufficient ? 1 : 0;
        if (event.breach_feasible) {
            numeric_depression_feasible_breach_excavation_volume_km3 +=
                event.breach_excavation_volume_km3;
            numeric_depression_breach_path_length_sum_km +=
                event.breach_path_length_km;
        }
        numeric_depression_lower_volume_hybrid_adjustment_volume_km3 +=
            event.breach_has_lower_adjustment_volume ?
                event.breach_excavation_volume_km3 : event.fill_volume_km3;
        max_numeric_depression_breach_path_length_km = std::max(
            max_numeric_depression_breach_path_length_km,
            event.breach_path_length_km
        );
        max_numeric_depression_breach_excavation_depth_m = std::max(
            max_numeric_depression_breach_excavation_depth_m,
            event.max_breach_excavation_depth_m
        );
        if (event.breach_has_lower_adjustment_volume) {
            max_lower_volume_breach_excavation_depth_m = std::max(
                max_lower_volume_breach_excavation_depth_m,
                event.max_breach_excavation_depth_m
            );
        }
        numeric_depression_correction_mass_balance_residual_km3 +=
            event.correction_mass_balance_residual_km3;
        if (event.breach_selected) {
            numeric_depression_breach_selected_event_count++;
            numeric_depression_selected_breach_excavation_volume_km3 +=
                event.applied_breach_excavation_volume_km3;
            numeric_depression_selected_breach_deposition_volume_km3 +=
                event.applied_breach_deposition_volume_km3;
            numeric_depression_alluvium_entrainment_volume_km3 +=
                event.applied_alluvium_entrainment_volume_km3;
            numeric_depression_bedrock_erosion_volume_km3 +=
                event.applied_bedrock_erosion_volume_km3;
            for (double depth_m : event.breach_excavation_depth_m_by_cell) {
                if (depth_m > NUMERIC_DEPRESSION_FILL_DEPTH_TOLERANCE_M) {
                    numeric_depression_breach_excavation_cell_application_count++;
                    numeric_depression_breach_excavation_depth_sum_m += depth_m;
                }
            }
            numeric_depression_breach_deposition_cell_application_count +=
                static_cast<int>(event.breach_deposition_cell_ids.size());
            numeric_depression_breach_deposition_depth_sum_m += std::accumulate(
                event.breach_deposition_depth_m_by_cell.begin(),
                event.breach_deposition_depth_m_by_cell.end(),
                0.0
            );
        } else if (event.temporary_numeric_lake_selected) {
            numeric_depression_temporary_lake_event_count++;
            numeric_depression_temporary_lake_cell_application_count +=
                static_cast<int>(event.cell_ids.size());
            numeric_depression_temporary_lake_candidate_area_km2 += event.area_km2;
            numeric_depression_temporary_lake_candidate_volume_km3 +=
                event.fill_volume_km3;
            max_numeric_depression_temporary_lake_depth_m = std::max(
                max_numeric_depression_temporary_lake_depth_m,
                event.max_fill_depth_m
            );
            for (int cell_id : event.cell_ids) {
                numeric_depression_temporary_lake_unique_cell_ids.insert(cell_id);
            }
        } else {
            throw std::runtime_error("numeric depression correction method is invalid");
        }
    }
    if (numeric_depression_fill_cell_application_count !=
            numeric_depression_fill_cell_event_count ||
        numeric_depression_fill_unique_cell_ids.size() !=
            static_cast<std::size_t>(numeric_depression_filled_unique_cell_count) ||
        std::abs(numeric_depression_fill_depth_sum_m -
            cumulative_numeric_depression_fill_sum_m) > 1.0e-6) {
        throw std::runtime_error("numeric depression fill provenance is inconsistent");
    }
    if (numeric_depression_breach_excavation_cell_application_count +
            numeric_depression_breach_deposition_cell_application_count !=
            numeric_depression_breach_cell_event_count ||
        std::abs(numeric_depression_breach_excavation_depth_sum_m -
            cumulative_numeric_depression_breach_excavation_sum_m) > 1.0e-6 ||
        std::abs(numeric_depression_breach_deposition_depth_sum_m -
            cumulative_numeric_depression_breach_deposition_sum_m) > 1.0e-6 ||
        std::abs(numeric_depression_selected_breach_excavation_volume_km3 -
            numeric_depression_selected_breach_deposition_volume_km3) > 1.0e-6) {
        throw std::runtime_error("numeric depression breach provenance is inconsistent");
    }
    if (numeric_depression_temporary_lake_cell_application_count !=
            numeric_depression_temporary_lake_cell_event_count ||
        numeric_depression_temporary_lake_unique_cell_ids.size() !=
            static_cast<std::size_t>(numeric_depression_temporary_lake_unique_cell_count)) {
        throw std::runtime_error(
            "numeric depression temporary lake provenance is inconsistent"
        );
    }
    int erosion_feedback_step_count = 0;
    int cryosphere_feedback_step_count = 0;
    int sea_level_recompute_count = 0;
    int climate_recompute_count = 0;
    int hydrologic_water_budget_recompute_count = 0;
    int hydrology_recompute_count = 0;
    double erosion_elevation_change_sum = 0.0;
    double total_feedback_elevation_change_sum = 0.0;
    int fluvial_sediment_active_cell_step_count = 0;
    int fluvial_sediment_routed_edge_count = 0;
    int fluvial_sediment_land_terminal_count = 0;
    int fluvial_sediment_marine_terminal_count = 0;
    int fluvial_sediment_terminal_allocation_count = 0;
    double fluvial_sediment_local_source_volume_km3 = 0.0;
    double fluvial_sediment_routed_throughput_volume_km3 = 0.0;
    double fluvial_sediment_capacity_deposition_volume_km3 = 0.0;
    double fluvial_sediment_depression_fill_deposition_volume_km3 = 0.0;
    double fluvial_sediment_lake_trap_deposition_volume_km3 = 0.0;
    double fluvial_sediment_terminal_land_deposition_volume_km3 = 0.0;
    double fluvial_sediment_marine_deposition_volume_km3 = 0.0;
    double fluvial_sediment_terminal_export_volume_km3 = 0.0;
    double fluvial_sediment_mass_balance_residual_km3 = 0.0;
    int hillslope_sediment_transport_edge_count = 0;
    int hillslope_sediment_source_cell_stage_count = 0;
    int hillslope_sediment_target_cell_stage_count = 0;
    int hillslope_sediment_land_to_land_edge_count = 0;
    int hillslope_sediment_land_to_marine_edge_count = 0;
    double hillslope_sediment_production_volume_km3 = 0.0;
    double hillslope_sediment_deposition_volume_km3 = 0.0;
    double hillslope_sediment_mass_balance_residual_km3 = 0.0;
    double hillslope_sediment_alluvium_entrainment_volume_km3 = 0.0;
    double hillslope_sediment_bedrock_erosion_volume_km3 = 0.0;
    double max_hillslope_sediment_source_production_depth_m = 0.0;
    double max_hillslope_sediment_target_deposition_depth_m = 0.0;
    double hillslope_sediment_effective_diffusivity_sum = 0.0;
    for (const EarthSystemFeedbackStep& step : feedback_history) {
        sea_level_recompute_count += step.sea_level_recompute_count;
        climate_recompute_count += step.climate_recompute_count;
        hydrologic_water_budget_recompute_count +=
            step.hydrologic_water_budget_recompute_count;
        hydrology_recompute_count += step.hydrology_recompute_count;
        total_feedback_elevation_change_sum += step.mean_abs_elevation_change_m_from_previous_stage;
        fluvial_sediment_active_cell_step_count +=
            step.fluvial_sediment_active_cell_step_count;
        fluvial_sediment_routed_edge_count +=
            step.fluvial_sediment_routed_edge_count;
        fluvial_sediment_land_terminal_count +=
            step.fluvial_sediment_land_terminal_count;
        fluvial_sediment_marine_terminal_count +=
            step.fluvial_sediment_marine_terminal_count;
        fluvial_sediment_terminal_allocation_count +=
            step.fluvial_sediment_terminal_allocation_count;
        fluvial_sediment_local_source_volume_km3 +=
            step.fluvial_sediment_local_source_volume_km3;
        fluvial_sediment_routed_throughput_volume_km3 +=
            step.fluvial_sediment_routed_throughput_volume_km3;
        fluvial_sediment_capacity_deposition_volume_km3 +=
            step.fluvial_sediment_capacity_deposition_volume_km3;
        fluvial_sediment_depression_fill_deposition_volume_km3 +=
            step.fluvial_sediment_depression_fill_deposition_volume_km3;
        fluvial_sediment_lake_trap_deposition_volume_km3 +=
            step.fluvial_sediment_lake_trap_deposition_volume_km3;
        fluvial_sediment_terminal_land_deposition_volume_km3 +=
            step.fluvial_sediment_terminal_land_deposition_volume_km3;
        fluvial_sediment_marine_deposition_volume_km3 +=
            step.fluvial_sediment_marine_deposition_volume_km3;
        fluvial_sediment_terminal_export_volume_km3 +=
            step.fluvial_sediment_terminal_export_volume_km3;
        fluvial_sediment_mass_balance_residual_km3 +=
            step.fluvial_sediment_mass_balance_residual_km3;
        if (step.erosion_applied) {
            erosion_feedback_step_count++;
            erosion_elevation_change_sum += step.mean_abs_elevation_change_m_from_previous_stage;
        }
        if (step.cryosphere_applied) {
            cryosphere_feedback_step_count++;
        }
    }
    for (const HillslopeSedimentTransportStage& stage :
            hillslope_transport_history) {
        hillslope_sediment_transport_edge_count += stage.transport_edge_count;
        hillslope_sediment_source_cell_stage_count += stage.source_cell_count;
        hillslope_sediment_target_cell_stage_count += stage.target_cell_count;
        hillslope_sediment_land_to_land_edge_count +=
            stage.land_to_land_edge_count;
        hillslope_sediment_land_to_marine_edge_count +=
            stage.land_to_marine_edge_count;
        hillslope_sediment_production_volume_km3 +=
            stage.production_volume_km3;
        hillslope_sediment_deposition_volume_km3 +=
            stage.deposition_volume_km3;
        hillslope_sediment_mass_balance_residual_km3 +=
            stage.mass_balance_residual_km3;
        hillslope_sediment_alluvium_entrainment_volume_km3 +=
            stage.alluvium_entrainment_volume_km3;
        hillslope_sediment_bedrock_erosion_volume_km3 +=
            stage.bedrock_erosion_volume_km3;
        max_hillslope_sediment_source_production_depth_m = std::max(
            max_hillslope_sediment_source_production_depth_m,
            stage.max_source_production_depth_m
        );
        max_hillslope_sediment_target_deposition_depth_m = std::max(
            max_hillslope_sediment_target_deposition_depth_m,
            stage.max_target_deposition_depth_m
        );
        hillslope_sediment_effective_diffusivity_sum +=
            stage.mean_effective_diffusivity *
            static_cast<double>(stage.transport_edge_count);
    }
    int glacial_sediment_transfer_count = 0;
    int glacial_sediment_source_cell_count = 0;
    int glacial_sediment_target_cell_count = 0;
    int glacial_sediment_land_target_transfer_count = 0;
    int glacial_sediment_marine_target_transfer_count = 0;
    double glacial_sediment_production_volume_km3 = 0.0;
    double glacial_sediment_deposition_volume_km3 = 0.0;
    double glacial_sediment_mass_balance_residual_km3 = 0.0;
    double glacial_sediment_terrain_volume_change_residual_km3 = 0.0;
    double glacial_sediment_alluvium_entrainment_volume_km3 = 0.0;
    double glacial_sediment_bedrock_erosion_volume_km3 = 0.0;
    double max_glacial_sediment_source_production_depth_m = 0.0;
    double max_glacial_sediment_target_deposition_depth_m = 0.0;
    for (const GlacialSedimentTransportStage& stage :
            glacial_transport_history) {
        glacial_sediment_transfer_count += stage.transfer_count;
        glacial_sediment_source_cell_count += stage.source_cell_count;
        glacial_sediment_target_cell_count += stage.target_cell_count;
        glacial_sediment_land_target_transfer_count +=
            stage.land_target_transfer_count;
        glacial_sediment_marine_target_transfer_count +=
            stage.marine_target_transfer_count;
        glacial_sediment_production_volume_km3 +=
            stage.production_volume_km3;
        glacial_sediment_deposition_volume_km3 +=
            stage.deposition_volume_km3;
        glacial_sediment_mass_balance_residual_km3 +=
            stage.mass_balance_residual_km3;
        glacial_sediment_terrain_volume_change_residual_km3 +=
            stage.terrain_volume_change_residual_km3;
        glacial_sediment_alluvium_entrainment_volume_km3 +=
            stage.alluvium_entrainment_volume_km3;
        glacial_sediment_bedrock_erosion_volume_km3 +=
            stage.bedrock_erosion_volume_km3;
        max_glacial_sediment_source_production_depth_m = std::max(
            max_glacial_sediment_source_production_depth_m,
            stage.max_source_production_depth_m
        );
        max_glacial_sediment_target_deposition_depth_m = std::max(
            max_glacial_sediment_target_deposition_depth_m,
            stage.max_target_deposition_depth_m
        );
    }
    const EarthSystemFeedbackStep* final_feedback_step = feedback_history.empty() ? nullptr : &feedback_history.back();
    int plate_motion_transition_count = 0;
    int total_plate_reassignment_events = 0;
    int plate_reassigned_cell_count = 0;
    int max_plate_assignment_change_count = 0;
    int total_crust_source_remap_events = 0;
    int total_crust_source_reuse = 0;
    int total_aged_oceanic_events = 0;
    int total_rejuvenated_oceanic_events = 0;
    int total_subducted_oceanic_events = 0;
    int final_accreted_terrane_cell_count = 0;
    double plate_motion_abs_age_change_sum = 0.0;
    double plate_motion_abs_thickness_change_sum = 0.0;
    double plate_motion_abs_density_change_sum = 0.0;
    double crust_transport_distance_sum = 0.0;
    double max_crust_transport_distance_km = 0.0;
    double crust_transport_abs_age_change_sum = 0.0;
    double crust_transport_abs_thickness_change_sum = 0.0;
    double crust_transport_abs_density_change_sum = 0.0;
    double crust_process_abs_age_change_sum = 0.0;
    double crust_process_abs_thickness_change_sum = 0.0;
    double crust_process_abs_density_change_sum = 0.0;
    double plate_motion_mean_abs_elevation_change_sum = 0.0;
    double mean_plate_cumulative_rotation_deg = 0.0;
    double max_plate_cumulative_rotation_deg = 0.0;
    for (const PlateMotionStep& step : plate_motion_history) {
        if (step.erosion_iteration < 0) {
            continue;
        }
        plate_motion_transition_count++;
        total_plate_reassignment_events += step.reassigned_cell_count;
        total_crust_source_remap_events += step.crust_source_remap_cell_count;
        total_crust_source_reuse += step.crust_source_reuse_count;
        total_aged_oceanic_events += step.aged_oceanic_cell_count;
        total_rejuvenated_oceanic_events += step.rejuvenated_oceanic_cell_count;
        total_subducted_oceanic_events += step.subducted_oceanic_cell_count;
        plate_motion_abs_age_change_sum += step.mean_abs_crust_age_change_ma;
        plate_motion_abs_thickness_change_sum += step.mean_abs_crust_thickness_change_km;
        plate_motion_abs_density_change_sum += step.mean_abs_crust_density_change;
        crust_transport_distance_sum += step.mean_crust_transport_distance_km;
        max_crust_transport_distance_km = std::max(
            max_crust_transport_distance_km, step.max_crust_transport_distance_km
        );
        crust_transport_abs_age_change_sum += step.mean_abs_crust_age_transport_change_ma;
        crust_transport_abs_thickness_change_sum += step.mean_abs_crust_thickness_transport_change_km;
        crust_transport_abs_density_change_sum += step.mean_abs_crust_density_transport_change;
        crust_process_abs_age_change_sum += step.mean_abs_crust_age_process_change_ma;
        crust_process_abs_thickness_change_sum += step.mean_abs_crust_thickness_process_change_km;
        crust_process_abs_density_change_sum += step.mean_abs_crust_density_process_change;
        plate_motion_mean_abs_elevation_change_sum += step.mean_abs_tectonic_elevation_change_m;
    }
    for (const Cell& cell : cells) {
        if (cell.plate_assignment_change_count > 0) {
            plate_reassigned_cell_count++;
        }
        max_plate_assignment_change_count = std::max(max_plate_assignment_change_count, cell.plate_assignment_change_count);
        final_accreted_terrane_cell_count += cell.crust_type == 8 ? 1 : 0;
    }
    if (!plate_motion_history.empty() && !plate_motion_history.back().plates.empty()) {
        for (const PlateKinematicSnapshot& plate : plate_motion_history.back().plates) {
            mean_plate_cumulative_rotation_deg += std::abs(plate.cumulative_rotation_deg);
            max_plate_cumulative_rotation_deg = std::max(
                max_plate_cumulative_rotation_deg,
                std::abs(plate.cumulative_rotation_deg)
            );
        }
        mean_plate_cumulative_rotation_deg /= static_cast<double>(plate_motion_history.back().plates.size());
    }
    std::vector<double> final_flow_accumulation;
    for (const Cell& cell : cells) {
        if (!cell.is_water && cell.flow_accumulation > 0.0) {
            final_flow_accumulation.push_back(cell.flow_accumulation);
        }
    }
    std::sort(final_flow_accumulation.begin(), final_flow_accumulation.end());
    const double river_flow_accumulation_threshold = final_flow_accumulation.empty() ? 0.0 :
        std::max(
            1.0,
            final_flow_accumulation[static_cast<std::size_t>(
                clamp(params.river_percentile, 0.5, 0.999) *
                static_cast<double>(final_flow_accumulation.size() - 1)
            )]
        );
    std::string out = "{";
    bool first = true;
    const double mean_cell_area_km2 = cells.empty() ? 0.0 :
        surface_area_km2 / static_cast<double>(cells.size());
    const double cell_area_variance = cells.empty() ? 0.0 : std::max(
        0.0,
        cell_area_squared_sum / static_cast<double>(cells.size()) -
            mean_cell_area_km2 * mean_cell_area_km2
    );
    const double cell_area_coefficient_of_variation = mean_cell_area_km2 > 0.0 ?
        std::sqrt(cell_area_variance) / mean_cell_area_km2 : 0.0;
    add_u64(out, first, "seed", params.seed);
    add_str(out, first, "mesh_backend", mesh_backend_name(params.mesh_backend));
    add_str(out, first, "cell_area_model", cell_area_model_name(params.mesh_backend));
    add_int(out, first, "cell_count", static_cast<int>(cells.size()));
    add_int(out, first, "output_float_precision", params.float_precision);
    add_str(out, first, "depression_routing_model",
        "raw_downhill_sink_units_with_priority_flood_spill_corridors_v1");
    add_str(out, first, "depression_geology_model",
        "raw_sink_cell_crust_or_active_boundary_v1");
    add_str(out, first, "numeric_depression_correction_model",
        "bounded_mass_conserving_breach_or_zero_material_temporary_lake_with_coupled_recomputation_v3");
    add_str(out, first, "numeric_depression_correction_selection_model",
        "lower_volume_full_cell_breach_with_50m_depth_bound_else_temporary_lake_v3");
    add_str(out, first, "numeric_depression_breach_diagnostic_model",
        "weighted_graph_excavation_proxy_monotone_lower_outlet_v1");
    add_double(out, first, "numeric_depression_breach_gradient_step_m",
        NUMERIC_DEPRESSION_BREACH_GRADIENT_STEP_M, 6);
    add_double(out, first, "numeric_depression_selected_breach_max_depth_m",
        NUMERIC_DEPRESSION_SELECTED_BREACH_MAX_DEPTH_M, 6);
    add_str(out, first, "numeric_depression_breach_mass_transfer_model",
        "local_excavation_to_nonchannel_depression_deposition_volume_closure_v1");
    add_str(out, first, "numeric_depression_correction_selection_reason",
        "apply_only_lower_volume_depth_bounded_capacity_sufficient_conflict_free_breaches_else_defer_without_material");
    add_int(out, first, "numeric_depression_fill_max_pass_count",
        NUMERIC_DEPRESSION_FILL_MAX_PASSES);
    add_double(out, first, "numeric_depression_fill_depth_tolerance_m",
        NUMERIC_DEPRESSION_FILL_DEPTH_TOLERANCE_M, 12);
    add_str(out, first, "hydrologic_surface_model",
        "priority_flood_fill_with_deterministic_flat_gradient_v1");
    add_str(out, first, "hydrologic_water_budget_model",
        "causal_land_climate_loss_partition_v1");
    add_str(out, first, "hydrologic_water_budget_execution_order",
        "climate_then_pet_then_loss_partition_then_runoff_then_flow_routing");
    add_double(out, first, "hydrologic_flat_gradient_step_m",
        HYDROLOGIC_FLAT_GRADIENT_STEP_M, 6);
    add_str(out, first, "river_extraction_model",
        "flow_accumulation_percentile_on_conditioned_hydrologic_surface_v1");
    add_double(out, first, "river_extraction_percentile",
        params.river_percentile, std::max(6, params.float_precision));
    add_double(out, first, "river_flow_accumulation_threshold",
        river_flow_accumulation_threshold, std::max(6, params.float_precision));
    add_double(out, first, "surface_area_km2", surface_area_km2, std::max(6, params.float_precision));
    add_double(out, first, "mean_cell_area_km2", mean_cell_area_km2, std::max(6, params.float_precision));
    add_double(out, first, "min_cell_area_km2",
        cells.empty() ? 0.0 : min_cell_area_km2, std::max(6, params.float_precision));
    add_double(out, first, "max_cell_area_km2", max_cell_area_km2, std::max(6, params.float_precision));
    add_double(out, first, "cell_area_coefficient_of_variation",
        cell_area_coefficient_of_variation, std::max(6, params.float_precision));
    add_int(out, first, "plate_count", params.plate_count);
    add_int(out, first, "simulation_clock_stage_count", static_cast<int>(feedback_history.size()));
    add_int(out, first, "simulation_clock_erosion_iteration_count", erosion_feedback_step_count);
    add_int(out, first, "simulation_clock_cryosphere_coupling_stage_count",
        cryosphere_feedback_step_count);
    add_int(out, first, "simulation_clock_sea_level_recompute_count", sea_level_recompute_count);
    add_int(out, first, "simulation_clock_climate_recompute_count", climate_recompute_count);
    add_int(out, first,
        "simulation_clock_hydrologic_water_budget_recompute_count",
        hydrologic_water_budget_recompute_count);
    add_int(out, first, "simulation_clock_hydrology_recompute_count", hydrology_recompute_count);
    add_int(out, first, "fluvial_sediment_routing_stage_count",
        erosion_feedback_step_count);
    add_int(out, first, "fluvial_sediment_active_cell_step_count",
        fluvial_sediment_active_cell_step_count);
    add_int(out, first, "fluvial_sediment_routed_edge_count",
        fluvial_sediment_routed_edge_count);
    add_int(out, first, "fluvial_sediment_routed_cell_count",
        fluvial_sediment_routed_cell_count);
    add_int(out, first, "fluvial_sediment_land_terminal_count",
        fluvial_sediment_land_terminal_count);
    add_int(out, first, "fluvial_sediment_marine_terminal_count",
        fluvial_sediment_marine_terminal_count);
    add_int(out, first, "fluvial_sediment_terminal_capture_cell_count",
        fluvial_sediment_terminal_capture_cell_count);
    add_int(out, first, "fluvial_sediment_terminal_allocation_count",
        fluvial_sediment_terminal_allocation_count);
    const int sediment_volume_precision = std::max(10, params.float_precision);
    add_double(out, first, "fluvial_sediment_local_source_volume_km3",
        fluvial_sediment_local_source_volume_km3,
        sediment_volume_precision);
    add_double(out, first, "fluvial_sediment_routed_throughput_volume_km3",
        fluvial_sediment_routed_throughput_volume_km3,
        sediment_volume_precision);
    add_double(out, first, "fluvial_sediment_capacity_deposition_volume_km3",
        fluvial_sediment_capacity_deposition_volume_km3,
        sediment_volume_precision);
    add_double(out, first,
        "fluvial_sediment_depression_fill_deposition_volume_km3",
        fluvial_sediment_depression_fill_deposition_volume_km3,
        sediment_volume_precision);
    add_double(out, first, "fluvial_sediment_lake_trap_deposition_volume_km3",
        fluvial_sediment_lake_trap_deposition_volume_km3,
        sediment_volume_precision);
    add_double(out, first,
        "fluvial_sediment_terminal_land_deposition_volume_km3",
        fluvial_sediment_terminal_land_deposition_volume_km3,
        sediment_volume_precision);
    add_double(out, first, "fluvial_sediment_marine_deposition_volume_km3",
        fluvial_sediment_marine_deposition_volume_km3,
        sediment_volume_precision);
    add_double(out, first, "fluvial_sediment_terminal_export_volume_km3",
        fluvial_sediment_terminal_export_volume_km3,
        sediment_volume_precision);
    add_double(out, first, "fluvial_sediment_total_deposition_volume_km3",
        fluvial_sediment_local_source_volume_km3 -
            fluvial_sediment_terminal_export_volume_km3,
        sediment_volume_precision);
    add_double(out, first, "fluvial_sediment_mass_balance_residual_km3",
        fluvial_sediment_mass_balance_residual_km3,
        sediment_volume_precision);
    add_int(out, first, "hillslope_sediment_transport_stage_count",
        static_cast<int>(hillslope_transport_history.size()));
    add_int(out, first, "hillslope_sediment_transport_edge_count",
        hillslope_sediment_transport_edge_count);
    add_int(out, first, "hillslope_sediment_source_cell_stage_count",
        hillslope_sediment_source_cell_stage_count);
    add_int(out, first, "hillslope_sediment_target_cell_stage_count",
        hillslope_sediment_target_cell_stage_count);
    add_int(out, first, "hillslope_sediment_land_to_land_edge_count",
        hillslope_sediment_land_to_land_edge_count);
    add_int(out, first, "hillslope_sediment_land_to_marine_edge_count",
        hillslope_sediment_land_to_marine_edge_count);
    add_int(out, first, "hillslope_sediment_unique_source_cell_count",
        hillslope_sediment_unique_source_cell_count);
    add_int(out, first, "hillslope_sediment_unique_target_cell_count",
        hillslope_sediment_unique_target_cell_count);
    add_double(out, first, "hillslope_sediment_production_volume_km3",
        hillslope_sediment_production_volume_km3,
        sediment_volume_precision);
    add_double(out, first, "hillslope_sediment_deposition_volume_km3",
        hillslope_sediment_deposition_volume_km3,
        sediment_volume_precision);
    add_double(out, first, "hillslope_sediment_mass_balance_residual_km3",
        hillslope_sediment_mass_balance_residual_km3,
        sediment_volume_precision);
    add_double(out, first,
        "max_hillslope_sediment_source_production_depth_m",
        max_hillslope_sediment_source_production_depth_m,
        std::max(8, params.float_precision));
    add_double(out, first,
        "max_hillslope_sediment_target_deposition_depth_m",
        max_hillslope_sediment_target_deposition_depth_m,
        std::max(8, params.float_precision));
    add_double(out, first, "mean_hillslope_sediment_effective_diffusivity",
        hillslope_sediment_transport_edge_count > 0 ?
            hillslope_sediment_effective_diffusivity_sum /
                static_cast<double>(hillslope_sediment_transport_edge_count) :
            0.0,
        sediment_volume_precision);
    add_int(out, first, "glacial_sediment_transport_stage_count",
        static_cast<int>(glacial_transport_history.size()));
    add_int(out, first, "glacial_sediment_transfer_count",
        glacial_sediment_transfer_count);
    add_int(out, first, "glacial_sediment_source_cell_count",
        glacial_sediment_source_cell_count);
    add_int(out, first, "glacial_sediment_target_cell_count",
        glacial_sediment_target_cell_count);
    add_int(out, first, "glacial_sediment_land_target_transfer_count",
        glacial_sediment_land_target_transfer_count);
    add_int(out, first, "glacial_sediment_marine_target_transfer_count",
        glacial_sediment_marine_target_transfer_count);
    add_double(out, first, "glacial_sediment_production_volume_km3",
        glacial_sediment_production_volume_km3,
        sediment_volume_precision);
    add_double(out, first, "glacial_sediment_deposition_volume_km3",
        glacial_sediment_deposition_volume_km3,
        sediment_volume_precision);
    add_double(out, first, "glacial_sediment_mass_balance_residual_km3",
        glacial_sediment_mass_balance_residual_km3,
        sediment_volume_precision);
    add_double(out, first,
        "glacial_sediment_terrain_volume_change_residual_km3",
        glacial_sediment_terrain_volume_change_residual_km3,
        sediment_volume_precision);
    add_double(out, first,
        "max_glacial_sediment_source_production_depth_m",
        max_glacial_sediment_source_production_depth_m,
        std::max(8, params.float_precision));
    add_double(out, first,
        "max_glacial_sediment_target_deposition_depth_m",
        max_glacial_sediment_target_deposition_depth_m,
        std::max(8, params.float_precision));
    add_double(out, first, "mean_erosion_iteration_elevation_change_m",
        erosion_feedback_step_count > 0 ? erosion_elevation_change_sum / static_cast<double>(erosion_feedback_step_count) : 0.0,
        params.float_precision);
    add_double(out, first, "total_feedback_mean_abs_elevation_change_m",
        total_feedback_elevation_change_sum, params.float_precision);
    add_double(out, first, "final_feedback_mean_abs_temperature_change_c",
        final_feedback_step != nullptr ? final_feedback_step->mean_abs_temperature_change_c_from_previous_stage : 0.0,
        params.float_precision);
    add_double(out, first, "final_feedback_mean_abs_precipitation_change_mm_y",
        final_feedback_step != nullptr ? final_feedback_step->mean_abs_precipitation_change_mm_y_from_previous_stage : 0.0,
        params.float_precision);
    add_double(out, first, "final_feedback_mean_abs_runoff_change_mm_y",
        final_feedback_step != nullptr ? final_feedback_step->mean_abs_runoff_change_mm_y_from_previous_stage : 0.0,
        params.float_precision);
    add_int(out, first, "plate_motion_history_step_count", static_cast<int>(plate_motion_history.size()));
    add_int(out, first, "plate_motion_transition_count", plate_motion_transition_count);
    add_int(out, first, "total_plate_reassignment_event_count", total_plate_reassignment_events);
    add_int(out, first, "plate_reassigned_cell_count", plate_reassigned_cell_count);
    add_int(out, first, "max_plate_assignment_change_count", max_plate_assignment_change_count);
    add_int(out, first, "total_crust_source_remap_event_count", total_crust_source_remap_events);
    add_int(out, first, "total_crust_source_reuse_count", total_crust_source_reuse);
    add_int(out, first, "total_aged_oceanic_event_count", total_aged_oceanic_events);
    add_int(out, first, "total_rejuvenated_oceanic_event_count", total_rejuvenated_oceanic_events);
    add_int(out, first, "total_subducted_oceanic_event_count", total_subducted_oceanic_events);
    add_int(out, first, "accreted_terrane_cell_count", final_accreted_terrane_cell_count);
    add_double(out, first, "mean_plate_cumulative_rotation_deg", mean_plate_cumulative_rotation_deg, params.float_precision);
    add_double(out, first, "max_plate_cumulative_rotation_deg", max_plate_cumulative_rotation_deg, params.float_precision);
    add_double(out, first, "mean_crust_transport_distance_km_per_motion_step",
        plate_motion_transition_count > 0 ? crust_transport_distance_sum / static_cast<double>(plate_motion_transition_count) : 0.0,
        params.float_precision);
    add_double(out, first, "max_crust_transport_distance_km", max_crust_transport_distance_km, params.float_precision);
    add_double(out, first, "mean_abs_crust_age_change_ma_per_motion_step",
        plate_motion_transition_count > 0 ? plate_motion_abs_age_change_sum / static_cast<double>(plate_motion_transition_count) : 0.0,
        params.float_precision);
    add_double(out, first, "mean_abs_crust_thickness_change_km_per_motion_step",
        plate_motion_transition_count > 0 ? plate_motion_abs_thickness_change_sum / static_cast<double>(plate_motion_transition_count) : 0.0,
        params.float_precision);
    add_double(out, first, "mean_abs_crust_density_change_per_motion_step",
        plate_motion_transition_count > 0 ? plate_motion_abs_density_change_sum / static_cast<double>(plate_motion_transition_count) : 0.0,
        params.float_precision);
    add_double(out, first, "mean_abs_crust_age_transport_change_ma_per_motion_step",
        plate_motion_transition_count > 0 ? crust_transport_abs_age_change_sum / static_cast<double>(plate_motion_transition_count) : 0.0,
        params.float_precision);
    add_double(out, first, "mean_abs_crust_thickness_transport_change_km_per_motion_step",
        plate_motion_transition_count > 0 ? crust_transport_abs_thickness_change_sum / static_cast<double>(plate_motion_transition_count) : 0.0,
        params.float_precision);
    add_double(out, first, "mean_abs_crust_density_transport_change_per_motion_step",
        plate_motion_transition_count > 0 ? crust_transport_abs_density_change_sum / static_cast<double>(plate_motion_transition_count) : 0.0,
        params.float_precision);
    add_double(out, first, "mean_abs_crust_age_process_change_ma_per_motion_step",
        plate_motion_transition_count > 0 ? crust_process_abs_age_change_sum / static_cast<double>(plate_motion_transition_count) : 0.0,
        params.float_precision);
    add_double(out, first, "mean_abs_crust_thickness_process_change_km_per_motion_step",
        plate_motion_transition_count > 0 ? crust_process_abs_thickness_change_sum / static_cast<double>(plate_motion_transition_count) : 0.0,
        params.float_precision);
    add_double(out, first, "mean_abs_crust_density_process_change_per_motion_step",
        plate_motion_transition_count > 0 ? crust_process_abs_density_change_sum / static_cast<double>(plate_motion_transition_count) : 0.0,
        params.float_precision);
    add_double(out, first, "mean_abs_tectonic_elevation_change_m_per_motion_step",
        plate_motion_transition_count > 0 ? plate_motion_mean_abs_elevation_change_sum / static_cast<double>(plate_motion_transition_count) : 0.0,
        params.float_precision);
    add_double(out, first, "target_ocean_fraction", params.ocean_fraction_target, params.float_precision);
    add_double(out, first, "target_ocean_water_inventory_km3",
        params.ocean_water_inventory_km3, std::max(6, params.float_precision));
    add_double(out, first, "ocean_area_km2", ocean_area_km2, std::max(6, params.float_precision));
    add_double(out, first, "ocean_volume_km3", ocean_volume_km3, std::max(6, params.float_precision));
    add_double(out, first, "ocean_water_inventory_error_km3",
        std::abs(ocean_volume_km3 - params.ocean_water_inventory_km3),
        std::max(6, params.float_precision));
    add_double(out, first, "ocean_fraction",
        surface_area_km2 > 0.0 ? ocean_area_km2 / surface_area_km2 : 0.0,
        params.float_precision);
    add_double(out, first, "ocean_cell_fraction",
        cells.empty() ? 0.0 : ocean / static_cast<double>(cells.size()),
        params.float_precision);
    add_double(out, first, "min_elevation_m", min_elev, params.float_precision);
    add_double(out, first, "max_elevation_m", max_elev, params.float_precision);
    add_double(out, first, "mean_land_elevation_m", land_count > 0.0 ? land_sum / land_count : 0.0, params.float_precision);
    add_int(out, first, "river_count", river_count);
    add_int(out, first, "equal_filled_raw_downhill_reroute_count", equal_filled_raw_downhill_reroute_count);
    add_int(out, first, "hydrologic_surface_conditioned_cell_count",
        hydrologic_surface_conditioned_cell_count);
    add_int(out, first, "equal_filled_flow_edge_count", equal_filled_flow_edge_count);
    add_int(out, first, "raw_uphill_flow_edge_count", raw_uphill_flow_edge_count);
    add_int(out, first, "non_downhill_hydrologic_flow_edge_count",
        non_downhill_hydrologic_flow_edge_count);
    add_double(out, first, "max_hydrologic_surface_adjustment_m",
        max_hydrologic_surface_adjustment_m, 6);
    add_double(out, first, "max_raw_uphill_flow_step_m",
        max_raw_uphill_flow_step_m, std::max(6, params.float_precision));
    add_int(out, first, "terminal_land_sink_count", terminal_land_sink_count);
    add_int(out, first, "avoidable_equal_filled_raw_downhill_sink_count",
        avoidable_equal_filled_raw_downhill_sink_count);
    add_int(out, first, "flow_cycle_cell_count", flow_cycle_cell_count);
    add_int(out, first, "lake_count", lake_count);
    add_int(out, first, "depression_component_count", static_cast<int>(lake_basins.size()));
    add_int(out, first, "depression_component_cell_count", depression_component_cell_count);
    add_int(out, first, "lake_basin_count", static_cast<int>(lake_basins.size()));
    add_int(out, first, "overflowing_lake_basin_count", overflowing_lake_basins);
    add_int(out, first, "staged_overflow_lake_basin_count", staged_overflow_lake_basins);
    add_int(out, first, "high_avulsion_risk_lake_basin_count", high_avulsion_risk_lake_basins);
    add_int(out, first, "preserved_geologic_depression_count", preserved_geologic_depressions);
    add_int(out, first, "corrected_numeric_depression_count", corrected_numeric_depressions);
    add_int(out, first, "temporary_numeric_lake_depression_count",
        temporary_numeric_lake_depressions);
    add_int(out, first, "numeric_depression_fill_pass_count",
        static_cast<int>(numeric_depression_fill_stage_passes.size()));
    add_int(out, first, "numeric_depression_correction_pass_count",
        static_cast<int>(numeric_depression_fill_stage_passes.size()));
    add_int(out, first, "numeric_depression_correction_event_count",
        static_cast<int>(numeric_depression_fill_history.size()));
    add_int(out, first, "numeric_depression_fill_event_count",
        0);
    add_int(out, first, "numeric_depression_fill_cell_application_count",
        numeric_depression_fill_cell_application_count);
    add_int(out, first, "numeric_depression_filled_unique_cell_count",
        numeric_depression_filled_unique_cell_count);
    add_int(out, first, "numeric_depression_fill_geologic_source_event_count",
        numeric_depression_fill_geologic_source_event_count);
    add_double(out, first, "numeric_depression_fill_area_km2",
        numeric_depression_fill_area_km2, std::max(10, params.float_precision));
    add_double(out, first, "numeric_depression_fill_volume_km3",
        numeric_depression_fill_volume_km3, std::max(10, params.float_precision));
    add_int(out, first, "numeric_depression_fill_candidate_event_count",
        static_cast<int>(numeric_depression_fill_history.size()));
    add_int(out, first, "numeric_depression_fill_candidate_cell_application_count",
        numeric_depression_fill_candidate_cell_application_count);
    add_double(out, first, "numeric_depression_fill_candidate_area_km2",
        numeric_depression_fill_candidate_area_km2,
        std::max(10, params.float_precision));
    add_double(out, first, "numeric_depression_fill_candidate_volume_km3",
        numeric_depression_fill_candidate_volume_km3,
        std::max(10, params.float_precision));
    add_double(out, first, "mean_numeric_depression_fill_depth_m",
        numeric_depression_fill_cell_application_count > 0 ?
            numeric_depression_fill_depth_sum_m /
                static_cast<double>(numeric_depression_fill_cell_application_count) :
            0.0,
        std::max(10, params.float_precision));
    add_double(out, first, "max_numeric_depression_fill_depth_m",
        max_numeric_depression_fill_depth_m, std::max(10, params.float_precision));
    add_double(out, first, "cumulative_numeric_depression_fill_sum_m",
        cumulative_numeric_depression_fill_sum_m, std::max(10, params.float_precision));
    add_double(out, first, "max_cumulative_numeric_depression_fill_m",
        max_cumulative_numeric_depression_fill_m, std::max(10, params.float_precision));
    add_int(out, first, "numeric_depression_temporary_lake_event_count",
        numeric_depression_temporary_lake_event_count);
    add_int(out, first,
        "numeric_depression_temporary_lake_cell_application_count",
        numeric_depression_temporary_lake_cell_application_count);
    add_int(out, first, "numeric_depression_temporary_lake_unique_cell_count",
        numeric_depression_temporary_lake_unique_cell_count);
    add_double(out, first, "numeric_depression_temporary_lake_candidate_area_km2",
        numeric_depression_temporary_lake_candidate_area_km2,
        std::max(10, params.float_precision));
    add_double(out, first, "numeric_depression_temporary_lake_candidate_volume_km3",
        numeric_depression_temporary_lake_candidate_volume_km3,
        std::max(10, params.float_precision));
    add_double(out, first, "max_numeric_depression_temporary_lake_depth_m",
        max_numeric_depression_temporary_lake_depth_m,
        std::max(10, params.float_precision));
    add_int(out, first, "numeric_depression_breach_feasible_event_count",
        numeric_depression_breach_feasible_event_count);
    add_int(out, first, "numeric_depression_breach_lower_volume_event_count",
        numeric_depression_breach_lower_volume_event_count);
    add_int(out, first, "numeric_depression_breach_depth_bound_pass_event_count",
        numeric_depression_breach_depth_bound_pass_event_count);
    add_int(out, first, "numeric_depression_breach_capacity_pass_event_count",
        numeric_depression_breach_capacity_pass_event_count);
    add_int(out, first, "numeric_depression_breach_selected_event_count",
        numeric_depression_breach_selected_event_count);
    add_int(out, first,
        "numeric_depression_breach_excavation_cell_application_count",
        numeric_depression_breach_excavation_cell_application_count);
    add_int(out, first,
        "numeric_depression_breach_deposition_cell_application_count",
        numeric_depression_breach_deposition_cell_application_count);
    add_double(out, first,
        "numeric_depression_selected_breach_excavation_volume_km3",
        numeric_depression_selected_breach_excavation_volume_km3,
        std::max(10, params.float_precision));
    add_double(out, first,
        "numeric_depression_selected_breach_deposition_volume_km3",
        numeric_depression_selected_breach_deposition_volume_km3,
        std::max(10, params.float_precision));
    add_double(out, first,
        "numeric_depression_correction_mass_balance_residual_km3",
        numeric_depression_correction_mass_balance_residual_km3,
        std::max(10, params.float_precision));
    add_int(out, first, "numeric_depression_mass_conserving_event_count",
        static_cast<int>(numeric_depression_fill_history.size()));
    add_int(out, first, "numeric_depression_zero_material_deferral_event_count",
        numeric_depression_temporary_lake_event_count);
    add_int(out, first, "numeric_depression_unbalanced_fill_event_count",
        0);
    add_double(out, first, "numeric_depression_avoided_unsourced_fill_volume_km3",
        numeric_depression_fill_candidate_volume_km3,
        std::max(10, params.float_precision));
    add_double(out, first,
        "numeric_depression_feasible_breach_excavation_volume_km3",
        numeric_depression_feasible_breach_excavation_volume_km3,
        std::max(10, params.float_precision));
    add_double(out, first,
        "numeric_depression_lower_volume_hybrid_adjustment_volume_km3",
        numeric_depression_lower_volume_hybrid_adjustment_volume_km3,
        std::max(10, params.float_precision));
    const double numeric_depression_lower_volume_hybrid_saved_volume_km3 =
        std::max(
            0.0,
            numeric_depression_fill_candidate_volume_km3 -
                numeric_depression_lower_volume_hybrid_adjustment_volume_km3
        );
    add_double(out, first,
        "numeric_depression_lower_volume_hybrid_saved_volume_km3",
        numeric_depression_lower_volume_hybrid_saved_volume_km3,
        std::max(10, params.float_precision));
    add_double(out, first,
        "numeric_depression_lower_volume_hybrid_saved_fraction",
        numeric_depression_fill_candidate_volume_km3 > 0.0 ?
            numeric_depression_lower_volume_hybrid_saved_volume_km3 /
                numeric_depression_fill_candidate_volume_km3 :
            0.0,
        std::max(10, params.float_precision));
    add_double(out, first, "mean_numeric_depression_breach_path_length_km",
        numeric_depression_breach_feasible_event_count > 0 ?
            numeric_depression_breach_path_length_sum_km /
                static_cast<double>(numeric_depression_breach_feasible_event_count) :
            0.0,
        std::max(10, params.float_precision));
    add_double(out, first, "max_numeric_depression_breach_path_length_km",
        max_numeric_depression_breach_path_length_km,
        std::max(10, params.float_precision));
    add_double(out, first, "max_numeric_depression_breach_excavation_depth_m",
        max_numeric_depression_breach_excavation_depth_m,
        std::max(10, params.float_precision));
    add_double(out, first, "max_lower_volume_breach_excavation_depth_m",
        max_lower_volume_breach_excavation_depth_m,
        std::max(10, params.float_precision));
    add_int(out, first, "closed_depression_count", closed_depressions);
    add_double(out, first, "mean_lake_fill_fraction",
        lake_basins.empty() ? 0.0 : lake_fill_fraction_sum / static_cast<double>(lake_basins.size()), params.float_precision);
    add_double(out, first, "lake_storage_capacity_km3", lake_storage_capacity_sum, params.float_precision);
    add_double(out, first, "lake_annual_runoff_km3", lake_annual_runoff_sum, params.float_precision);
    add_double(out, first, "mean_lake_overflow_path_length_km",
        lake_basins.empty() ? 0.0 : lake_overflow_path_length_sum / static_cast<double>(lake_basins.size()), params.float_precision);
    add_double(out, first, "mean_lake_avulsion_risk",
        lake_basins.empty() ? 0.0 : lake_avulsion_risk_sum / static_cast<double>(lake_basins.size()), params.float_precision);
    add_int(out, first, "basin_count", static_cast<int>(basin_ids.size()));
    add_int(out, first, "endorheic_basin_count", endorheic_watersheds);
    add_int(out, first, "watershed_count", static_cast<int>(watersheds.size()));
    add_int(out, first, "endorheic_watershed_count", endorheic_watersheds);
    add_double(out, first, "largest_watershed_area_km2", largest_watershed_area, params.float_precision);
    add_int(out, first, "watershed_geometry_count", watershed_geometry_count);
    add_int(out, first, "largest_watershed_boundary_cell_count", largest_watershed_boundary_cell_count);
    add_int(out, first, "watershed_polygon_count", watershed_polygon_count);
    add_double(out, first, "largest_watershed_polygon_area_km2", largest_watershed_polygon_area, params.float_precision);
    add_double(out, first, "mean_watershed_polygon_area_error_fraction",
        watershed_polygon_count > 0 ? watershed_polygon_area_error_sum / static_cast<double>(watershed_polygon_count) : 0.0,
        params.float_precision);
    add_double(out, first, "mean_watershed_compactness_index",
        watershed_polygon_count > 0 ? watershed_compactness_sum / static_cast<double>(watershed_polygon_count) : 0.0,
        params.float_precision);
    add_double(out, first, "mean_watershed_geometry_quality",
        watershed_polygon_count > 0 ? watershed_geometry_quality_sum / static_cast<double>(watershed_polygon_count) : 0.0,
        params.float_precision);
    add_double(out, first, "mean_watershed_boundary_perimeter_km",
        watershed_polygon_count > 0 ? watershed_boundary_perimeter_sum / static_cast<double>(watershed_polygon_count) : 0.0,
        params.float_precision);
    add_int(out, first, "coastal_feature_count", static_cast<int>(coastal_features.size()));
    add_int(out, first, "coastal_bar_feature_count", coastal_bar_features);
    add_int(out, first, "prograding_coastal_feature_count", prograding_coastal_features);
    add_int(out, first, "eroding_coastal_feature_count", eroding_coastal_features);
    add_double(out, first, "mean_coastal_migration_rate_m_y",
        coastal_features.empty() ? 0.0 : coastal_migration_sum / static_cast<double>(coastal_features.size()), params.float_precision);
    add_int(out, first, "sedimentary_basin_count", static_cast<int>(sedimentary_basins.size()));
    add_int(out, first, "active_sedimentary_basin_count", active_sedimentary_basins);
    add_double(out, first, "largest_sedimentary_basin_area_km2", largest_sedimentary_basin_area, params.float_precision);
    add_double(out, first, "mean_sedimentary_basin_thickness_m",
        sedimentary_basins.empty() ? 0.0 : sedimentary_basin_thickness_sum / static_cast<double>(sedimentary_basins.size()), params.float_precision);
    add_int(out, first, "stratigraphic_column_count", static_cast<int>(stratigraphic_columns.size()));
    add_int(out, first, "stratigraphic_layer_count", stratigraphic_layer_count);
    add_int(out, first, "active_stratigraphic_column_count", active_stratigraphic_columns);
    add_int(out, first, "max_stratigraphic_layer_count", max_stratigraphic_layer_count);
    add_double(out, first, "mean_stratigraphic_thickness_m",
        stratigraphic_columns.empty() ? 0.0 : stratigraphic_thickness_sum / static_cast<double>(stratigraphic_columns.size()), params.float_precision);
    add_int(out, first, "spill_corrected_cell_count", spill_corrected_cells);
    add_int(out, first, "closed_basin_cell_count", closed_basin_cells);
    add_double(out, first, "max_depression_depth_m", max_depression_depth, params.float_precision);
    add_int(out, first, "settlement_count", static_cast<int>(settlements.size()));
    add_int(out, first, "route_count", static_cast<int>(routes.size()));
    add_int(out, first, "trade_flow_count", static_cast<int>(trade_flows.size()));
    add_double(out, first, "trade_total_volume_index", trade_volume, params.float_precision);
    add_double(out, first, "interregional_trade_fraction",
        trade_flows.empty() ? 0.0 : static_cast<double>(interregional_trade_flows) / static_cast<double>(trade_flows.size()), params.float_precision);
    add_double(out, first, "mean_trade_friction",
        trade_flows.empty() ? 0.0 : trade_friction / static_cast<double>(trade_flows.size()), params.float_precision);
    add_int(out, first, "political_region_count", static_cast<int>(political_regions.size()));
    add_int(out, first, "culture_region_count", static_cast<int>(cultural_layers.cultures.size()));
    add_int(out, first, "language_region_count", static_cast<int>(cultural_layers.language_regions.size()));
    add_int(out, first, "historical_era_count", static_cast<int>(historical_layers.eras.size()));
    add_int(out, first, "historical_event_count", static_cast<int>(historical_layers.events.size()));
    add_int(out, first, "migration_event_count", migration_events);
    add_int(out, first, "dynastic_change_count", dynastic_change_events);
    add_int(out, first, "language_lineage_count", language_lineages);
    add_int(out, first, "population_region_count", static_cast<int>(population_regions.size()));
    add_double(out, first, "estimated_world_population", estimated_world_population, params.float_precision);
    add_double(out, first, "mean_population_pressure",
        population_regions.empty() ? 0.0 : population_pressure_sum / static_cast<double>(population_regions.size()), params.float_precision);
    add_int(out, first, "conflict_count", static_cast<int>(conflicts.size()));
    add_int(out, first, "high_intensity_conflict_count", high_intensity_conflicts);
    add_double(out, first, "mean_conflict_intensity",
        conflicts.empty() ? 0.0 : conflict_intensity_sum / static_cast<double>(conflicts.size()), params.float_precision);
    add_double(out, first, "mean_war_duration_years",
        conflicts.empty() ? 0.0 : conflict_duration_sum / static_cast<double>(conflicts.size()), params.float_precision);
    add_double(out, first, "total_mobilized_population", conflict_mobilized_sum, params.float_precision);
    add_double(out, first, "mean_conflict_logistics_strain_index",
        conflicts.empty() ? 0.0 : conflict_logistics_strain_sum / static_cast<double>(conflicts.size()), params.float_precision);
    add_double(out, first, "mean_conflict_economic_disruption_index",
        conflicts.empty() ? 0.0 : conflict_economic_disruption_sum / static_cast<double>(conflicts.size()), params.float_precision);
    add_int(out, first, "high_economic_disruption_conflict_count", high_economic_disruption_conflicts);
    add_double(out, first, "mean_conflict_casualty_rate",
        conflicts.empty() ? 0.0 : conflict_casualty_rate_sum / static_cast<double>(conflicts.size()), params.float_precision);
    add_double(out, first, "max_conflict_casualty_rate", max_conflict_casualty_rate, params.float_precision);
    add_int(out, first, "dynasty_count", static_cast<int>(dynasties.size()));
    add_int(out, first, "dynastic_lineage_count", dynastic_lineages);
    add_int(out, first, "dynasty_root_count", dynasty_roots);
    add_int(out, first, "dynasty_successor_link_count", dynasty_successor_links);
    add_int(out, first, "max_dynasty_lineage_depth", max_dynasty_lineage_depth);
    add_double(out, first, "mean_dynastic_continuity_index",
        dynasties.empty() ? 0.0 : dynastic_continuity_sum / static_cast<double>(dynasties.size()), params.float_precision);
    add_int(out, first, "territorial_snapshot_count", static_cast<int>(territorial_snapshots.size()));
    add_int(out, first, "snapshot_region_record_count", snapshot_region_records);
    add_int(out, first, "snapshot_polygon_region_count", snapshot_polygon_region_count);
    add_double(out, first, "mean_snapshot_fragmentation_index",
        territorial_snapshots.empty() ? 0.0 : snapshot_fragmentation_sum / static_cast<double>(territorial_snapshots.size()), params.float_precision);
    add_double(out, first, "mean_snapshot_polygon_area_error_fraction",
        snapshot_polygon_region_count > 0 ? snapshot_polygon_area_error_sum / static_cast<double>(snapshot_polygon_region_count) : 0.0,
        params.float_precision);
    add_double(out, first, "mean_snapshot_compactness_index",
        snapshot_polygon_region_count > 0 ? snapshot_compactness_sum / static_cast<double>(snapshot_polygon_region_count) : 0.0,
        params.float_precision);
    add_double(out, first, "mean_snapshot_geometry_quality",
        snapshot_polygon_region_count > 0 ? snapshot_geometry_quality_sum / static_cast<double>(snapshot_polygon_region_count) : 0.0,
        params.float_precision);
    add_double(out, first, "mean_snapshot_boundary_perimeter_km",
        snapshot_polygon_region_count > 0 ? snapshot_boundary_perimeter_sum / static_cast<double>(snapshot_polygon_region_count) : 0.0,
        params.float_precision);
    add_double(out, first, "mean_historical_instability",
        historical_layers.events.empty() ? 0.0 : historical_instability_sum / static_cast<double>(historical_layers.events.size()), params.float_precision);
    add_double(out, first, "mean_cultural_continuity",
        cultural_layers.cultures.empty() ? 0.0 : cultural_continuity_sum / static_cast<double>(cultural_layers.cultures.size()), params.float_precision);
    add_double(out, first, "mean_language_change_rate",
        cultural_layers.language_regions.empty() ? 0.0 : language_change_sum / static_cast<double>(cultural_layers.language_regions.size()), params.float_precision);
    add_double(out, first, "mean_phonological_complexity",
        cultural_layers.language_regions.empty() ? 0.0 : phonological_complexity_sum / static_cast<double>(cultural_layers.language_regions.size()), params.float_precision);
    add_double(out, first, "mean_sound_shift_index",
        cultural_layers.language_regions.empty() ? 0.0 : sound_shift_sum / static_cast<double>(cultural_layers.language_regions.size()), params.float_precision);
    add_double(out, first, "mean_inherited_phonology_fraction",
        cultural_layers.language_regions.empty() ? 0.0 : inherited_phonology_sum / static_cast<double>(cultural_layers.language_regions.size()), params.float_precision);
    add_int(out, first, "sacred_area_count", static_cast<int>(cultural_layers.sacred_areas.size()));
    add_int(out, first, "ruin_count", static_cast<int>(cultural_layers.ruins.size()));
    add_int(out, first, "border_segment_count", static_cast<int>(borders.size()));
    add_double(out, first, "border_total_length_km", border_length, params.float_precision);
    add_double(out, first, "natural_border_fraction",
        borders.empty() ? 0.0 : static_cast<double>(natural_border_segments) / static_cast<double>(borders.size()), params.float_precision);
    add_double(out, first, "largest_region_area_km2", largest_region_area, params.float_precision);
    add_double(out, first, "largest_culture_area_km2", largest_culture_area, params.float_precision);
    add_double(out, first, "politically_assigned_land_fraction",
        land_count > 0.0 ? static_cast<double>(politically_assigned_land_cells) / land_count : 0.0, params.float_precision);
    add_double(out, first, "culturally_assigned_land_fraction",
        land_count > 0.0 ? static_cast<double>(culturally_assigned_land_cells) / land_count : 0.0, params.float_precision);
    add_double(out, first, "linguistically_assigned_land_fraction",
        land_count > 0.0 ? static_cast<double>(linguistically_assigned_land_cells) / land_count : 0.0, params.float_precision);
    add_double(
        out,
        first,
        "top_settlement_score",
        settlements.empty() ? 0.0 : settlements.front().score,
        std::max(8, params.float_precision)
    );
    add_double(out, first, "mean_sediment_thickness_m", sediment_sum / static_cast<double>(cells.size()), params.float_precision);
    add_double(out, first, "sediment_budget_production_m", sediment_production_sum, params.float_precision);
    add_double(out, first, "sediment_budget_deposition_m", sediment_deposition_sum, params.float_precision);
    add_double(out, first, "sediment_budget_export_m", sediment_export_sum, params.float_precision);
    add_double(out, first, "sediment_budget_residual_m",
        std::abs(sediment_production_sum - sediment_deposition_sum - sediment_export_sum), params.float_precision);
    add_str(out, first, "sediment_budget_closure_model",
        "cell_area_weighted_hillslope_glacial_and_routed_deposition_terminal_export_volume_v4");
    add_double(out, first, "sediment_budget_production_km3",
        sediment_production_volume_km3, std::max(10, params.float_precision));
    add_double(out, first, "sediment_budget_deposition_km3",
        sediment_deposition_volume_km3, std::max(10, params.float_precision));
    add_double(out, first, "sediment_budget_export_km3",
        sediment_export_volume_km3, std::max(10, params.float_precision));
    add_double(out, first, "sediment_budget_residual_km3",
        std::abs(
            sediment_production_volume_km3 -
                sediment_deposition_volume_km3 - sediment_export_volume_km3
        ),
        std::max(10, params.float_precision));
    add_double(out, first, "sediment_delivery_ratio",
        sediment_production_volume_km3 > 0.0 ?
            sediment_deposition_volume_km3 / sediment_production_volume_km3 :
            0.0,
        params.float_precision);
    const double fluvial_sediment_alluvium_entrainment_volume_km3 =
        std::max(
            0.0,
            sediment_alluvium_entrainment_volume_km3 -
                hillslope_sediment_alluvium_entrainment_volume_km3 -
                glacial_sediment_alluvium_entrainment_volume_km3 -
                numeric_depression_alluvium_entrainment_volume_km3
        );
    const double fluvial_sediment_bedrock_erosion_volume_km3 = std::max(
        0.0,
        sediment_bedrock_erosion_volume_km3 -
            hillslope_sediment_bedrock_erosion_volume_km3 -
            glacial_sediment_bedrock_erosion_volume_km3 -
            numeric_depression_bedrock_erosion_volume_km3
    );
    add_str(out, first, "sediment_inventory_model",
        "finite_alluvium_bedrock_sediment_inventory_v1");
    add_str(out, first, "sediment_initial_mobile_inventory_model",
        "zero_depth_all_cells_v1");
    add_str(out, first, "sediment_source_partition_model",
        "available_alluvium_first_then_bedrock_erosion_v1");
    add_str(out, first, "sediment_erosion_stage_source_partition_order",
        "hillslope_then_fluvial");
    add_double(out, first, "sediment_gross_mobilization_volume_km3",
        sediment_production_volume_km3, sediment_volume_precision);
    add_double(out, first, "sediment_alluvium_entrainment_volume_km3",
        sediment_alluvium_entrainment_volume_km3,
        sediment_volume_precision);
    add_double(out, first, "sediment_bedrock_erosion_volume_km3",
        sediment_bedrock_erosion_volume_km3, sediment_volume_precision);
    add_double(out, first, "sediment_final_inventory_volume_km3",
        sediment_inventory_volume_km3, sediment_volume_precision);
    add_double(out, first, "sediment_source_partition_residual_km3",
        std::abs(
            sediment_production_volume_km3 -
                sediment_alluvium_entrainment_volume_km3 -
                sediment_bedrock_erosion_volume_km3
        ),
        sediment_volume_precision);
    add_double(out, first, "sediment_inventory_mass_balance_residual_km3",
        std::abs(
            sediment_bedrock_erosion_volume_km3 -
                sediment_inventory_volume_km3 - sediment_export_volume_km3
        ),
        sediment_volume_precision);
    add_double(out, first,
        "hillslope_sediment_alluvium_entrainment_volume_km3",
        hillslope_sediment_alluvium_entrainment_volume_km3,
        sediment_volume_precision);
    add_double(out, first, "hillslope_sediment_bedrock_erosion_volume_km3",
        hillslope_sediment_bedrock_erosion_volume_km3,
        sediment_volume_precision);
    add_double(out, first,
        "fluvial_sediment_alluvium_entrainment_volume_km3",
        fluvial_sediment_alluvium_entrainment_volume_km3,
        sediment_volume_precision);
    add_double(out, first, "fluvial_sediment_bedrock_erosion_volume_km3",
        fluvial_sediment_bedrock_erosion_volume_km3,
        sediment_volume_precision);
    add_double(out, first,
        "glacial_sediment_alluvium_entrainment_volume_km3",
        glacial_sediment_alluvium_entrainment_volume_km3,
        sediment_volume_precision);
    add_double(out, first, "glacial_sediment_bedrock_erosion_volume_km3",
        glacial_sediment_bedrock_erosion_volume_km3,
        sediment_volume_precision);
    add_double(out, first,
        "numeric_depression_alluvium_entrainment_volume_km3",
        numeric_depression_alluvium_entrainment_volume_km3,
        sediment_volume_precision);
    add_double(out, first,
        "numeric_depression_bedrock_erosion_volume_km3",
        numeric_depression_bedrock_erosion_volume_km3,
        sediment_volume_precision);
    const double cell_divisor = static_cast<double>(cells.size());
    add_double(out, first, "mean_initial_isostatic_elevation_m", initial_isostatic_sum / cell_divisor, params.float_precision);
    add_double(out, first, "mean_initial_thermal_subsidence_m", initial_thermal_sum / cell_divisor, params.float_precision);
    add_double(out, first, "mean_initial_ridge_uplift_m", initial_ridge_sum / cell_divisor, params.float_precision);
    add_double(out, first, "mean_initial_orogenic_uplift_m", initial_orogenic_sum / cell_divisor, params.float_precision);
    add_double(out, first, "mean_initial_volcanic_uplift_m", initial_volcanic_sum / cell_divisor, params.float_precision);
    add_double(out, first, "mean_initial_trench_subsidence_m", initial_trench_sum / cell_divisor, params.float_precision);
    add_double(out, first, "mean_initial_rift_subsidence_m", initial_rift_sum / cell_divisor, params.float_precision);
    add_double(out, first, "mean_initial_transform_fault_relief_m", initial_transform_sum / cell_divisor, params.float_precision);
    add_double(out, first, "mean_initial_secondary_roughness_m", initial_roughness_sum / cell_divisor, params.float_precision);
    add_double(out, first, "mean_initial_elevation_m", initial_elevation_sum / cell_divisor, params.float_precision);
    add_double(out, first, "mean_tectonic_uplift_rate_m_per_step", uplift_rate_sum / cell_divisor, params.float_precision);
    add_double(out, first, "mean_volcanic_potential_index", volcanic_potential_sum / cell_divisor, params.float_precision);
    add_int(out, first, "high_volcanic_potential_cell_count", high_volcanic_potential_cells);
    add_double(out, first, "mean_orographic_factor", orographic_sum / static_cast<double>(cells.size()), params.float_precision);
    add_double(out, first, "mean_rain_shadow_factor", rain_shadow_sum / static_cast<double>(cells.size()), params.float_precision);
    add_double(out, first, "rain_shadowed_land_fraction",
        land_count > 0.0 ? static_cast<double>(rain_shadowed_cells) / land_count : 0.0, params.float_precision);
    add_double(out, first, "mean_humidity_transport_index",
        humidity_transport_sum / static_cast<double>(cells.size()), params.float_precision);
    add_double(out, first, "mean_upwind_ocean_fetch_km",
        upwind_fetch_sum / static_cast<double>(cells.size()), params.float_precision);
    add_double(out, first, "mean_advected_moisture_factor",
        advected_moisture_sum / static_cast<double>(cells.size()), params.float_precision);
    add_raw(out, first, "atmospheric_cell_counts", counts_json<4>(atmospheric_cell_counts));
    add_double(out, first, "mean_surface_pressure_anomaly_hpa",
        surface_pressure_anomaly_sum / static_cast<double>(cells.size()), params.float_precision);
    add_double(out, first, "mean_vertical_velocity_index",
        vertical_velocity_sum / static_cast<double>(cells.size()), params.float_precision);
    add_double(out, first, "mean_wind_divergence_index",
        wind_divergence_sum / static_cast<double>(cells.size()), params.float_precision);
    add_double(out, first, "mean_seasonal_wind_speed",
        seasonal_wind_speed_sum / static_cast<double>(cells.size()), params.float_precision);
    add_double(out, first, "mean_seasonal_wind_reversal_index",
        seasonal_wind_reversal_sum / static_cast<double>(cells.size()), params.float_precision);
    add_double(out, first, "ascending_air_fraction",
        static_cast<double>(ascending_air_cells) / static_cast<double>(cells.size()), params.float_precision);
    add_double(out, first, "mean_vapor_evaporation_mm_y",
        vapor_evaporation_sum / static_cast<double>(cells.size()), params.float_precision);
    add_double(out, first, "mean_moisture_convergence_mm_y",
        moisture_convergence_sum / static_cast<double>(cells.size()), params.float_precision);
    add_double(out, first, "mean_orographic_rainout_mm_y",
        orographic_rainout_sum / static_cast<double>(cells.size()), params.float_precision);
    add_double(out, first, "mean_precipitation_recycling_fraction",
        precipitation_recycling_sum / static_cast<double>(cells.size()), params.float_precision);
    add_double(out, first, "mean_vapor_deficit_mm_y",
        vapor_deficit_sum / static_cast<double>(cells.size()), params.float_precision);
    add_double(out, first, "mean_abs_vapor_budget_residual_mm_y",
        vapor_budget_residual_abs_sum / static_cast<double>(cells.size()), params.float_precision);
    add_double(out, first, "mean_ocean_current_strength",
        ocean_current_strength_sum / static_cast<double>(cells.size()), params.float_precision);
    add_double(out, first, "mean_ocean_current_temperature_c",
        ocean_current_temp_sum / static_cast<double>(cells.size()), params.float_precision);
    add_double(out, first, "mean_ocean_current_moisture_factor",
        ocean_current_moisture_sum / static_cast<double>(cells.size()), params.float_precision);
    add_double(out, first, "mean_ice_thickness_m", ice_sum / static_cast<double>(cells.size()), params.float_precision);
    add_double(out, first, "mean_glacial_erosion_m", glacial_erosion_sum / static_cast<double>(cells.size()), params.float_precision);
    add_double(out, first, "mean_ice_surface_mass_balance_m_y",
        glacier_cells > 0 ? ice_surface_mass_balance_sum / static_cast<double>(glacier_cells) : 0.0, params.float_precision);
    add_double(out, first, "mean_basal_sliding_index",
        glacier_cells > 0 ? basal_sliding_sum / static_cast<double>(glacier_cells) : 0.0, params.float_precision);
    add_double(out, first, "mean_ice_velocity_m_y",
        glacier_cells > 0 ? ice_velocity_sum / static_cast<double>(glacier_cells) : 0.0, params.float_precision);
    add_double(out, first, "glaciated_land_fraction",
        land_count > 0.0 ? static_cast<double>(glacier_cells) / land_count : 0.0, params.float_precision);
    add_int(out, first, "ice_sheet_count", static_cast<int>(ice_sheets.size()));
    add_double(out, first, "mean_ice_sheet_retreat_rate_m_y",
        ice_sheets.empty() ? 0.0 : ice_sheet_retreat_rate_sum / static_cast<double>(ice_sheets.size()), params.float_precision);
    add_int(out, first, "moraine_deposition_cell_count", moraine_deposition_cells);
    add_double(out, first, "mean_moraine_deposition_m",
        cells.empty() ? 0.0 : moraine_deposition_sum / static_cast<double>(cells.size()), params.float_precision);
    add_double(out, first, "mean_deglaciation_age_ka",
        deglaciated_cells > 0 ? deglaciation_age_sum / static_cast<double>(deglaciated_cells) : 0.0, params.float_precision);
    add_double(out, first, "river_downhill_fraction", river_edges > 0 ? static_cast<double>(downhill_edges) / river_edges : 1.0, params.float_precision);
    add_double(out, first, "mountain_convergent_alignment",
        high_mountains > 0 ? static_cast<double>(high_mountains_near_conv) / high_mountains : 1.0, params.float_precision);
    add_int(out, first, "calibration_check_count", static_cast<int>(calibration_checks.size()));
    add_int(out, first, "calibration_pass_count", calibration_pass_count);
    add_double(out, first, "calibration_pass_fraction",
        calibration_checks.empty() ? 0.0 : static_cast<double>(calibration_pass_count) / static_cast<double>(calibration_checks.size()),
        params.float_precision);
    add_double(out, first, "mean_calibration_score",
        calibration_checks.empty() ? 0.0 : calibration_score_sum / static_cast<double>(calibration_checks.size()),
        params.float_precision);
    add_raw(out, first, "boundary_counts", counts_json<5>(boundary_counts));
    add_raw(out, first, "crust_counts", counts_json<9>(crust_counts));
    add_raw(out, first, "biome_counts", counts_json<16>(biome_counts));
    add_raw(out, first, "resource_counts", counts_json<9>(resource_counts));
    add_raw(out, first, "water_body_counts", counts_json<6>(water_body_counts));
    add_raw(out, first, "landform_counts", counts_json<20>(landform_counts));
    out += "}";
    return out;
}

std::string plates_json(const std::vector<Plate>& plates, int precision) {
    std::string out = "[";
    bool first_plate = true;
    for (const Plate& plate : plates) {
        comma(out, first_plate);
        out += "{";
        bool first = true;
        add_int(out, first, "id", plate.id);
        add_str(out, first, "kind", plate.kind == 0 ? "oceanic" : (plate.kind == 1 ? "continental" : "mixed"));
        add_raw(out, first, "axis", "[" + num(plate.axis.x, precision) + "," + num(plate.axis.y, precision) + "," + num(plate.axis.z, precision) + "]");
        add_raw(out, first, "initial_center", "[" + num(plate.initial_center.x, precision) + "," + num(plate.initial_center.y, precision) + "," + num(plate.initial_center.z, precision) + "]");
        add_raw(out, first, "center", "[" + num(plate.center.x, precision) + "," + num(plate.center.y, precision) + "," + num(plate.center.z, precision) + "]");
        add_double(out, first, "angular_speed", plate.angular_speed, precision);
        add_double(out, first, "cumulative_rotation_deg", plate.cumulative_rotation_deg, precision);
        add_double(out, first, "crust_density", plate.crust_density, precision);
        add_double(out, first, "crust_thickness_km", plate.crust_thickness_km, precision);
        add_int(out, first, "cell_count", plate.cell_count);
        add_double(out, first, "area_km2", plate.area_km2, precision);
        add_double(out, first, "mean_crust_age_ma", plate.mean_crust_age_ma, precision);
        add_double(out, first, "mean_crust_density", plate.mean_crust_density, precision);
        add_double(out, first, "mean_crust_thickness_km", plate.mean_crust_thickness_km, precision);
        add_str(out, first, "dominant_crust_type", CRUST_NAMES[plate.dominant_crust_type]);
        add_str(out, first, "dominant_lithology", LITHOLOGY_NAMES[plate.dominant_lithology]);
        add_double(out, first, "mean_boundary_activity", plate.mean_boundary_activity, precision);
        add_double(out, first, "mean_heat_flow_mw_m2", plate.mean_heat_flow_mw_m2, precision);
        add_str(out, first, "thermal_state",
            plate.mean_heat_flow_mw_m2 >= 95.0 ? "hot_active" : (plate.mean_heat_flow_mw_m2 >= 65.0 ? "warm_active" : "cool_stable"));
        out += "}";
    }
    out += "]";
    return out;
}

std::string int_array_json(const std::vector<int>& values) {
    std::string out = "[";
    for (std::size_t i = 0; i < values.size(); ++i) {
        if (i > 0) {
            out += ",";
        }
        out += std::to_string(values[i]);
    }
    out += "]";
    return out;
}

std::string double_array_json(const std::vector<double>& values, int precision) {
    std::string out = "[";
    for (std::size_t i = 0; i < values.size(); ++i) {
        if (i > 0) {
            out += ",";
        }
        out += num(values[i], precision);
    }
    out += "]";
    return out;
}

std::string vec3_json(Vec3 value, int precision) {
    std::string out = "[";
    out += num(value.x, precision);
    out += ",";
    out += num(value.y, precision);
    out += ",";
    out += num(value.z, precision);
    out += "]";
    return out;
}

std::string latlon_ring_json(const std::vector<LatLon>& ring, int precision) {
    std::string out = "[";
    for (std::size_t i = 0; i < ring.size(); ++i) {
        if (i > 0) {
            out += ",";
        }
        out += "[";
        out += num(ring[i].lat_deg, precision);
        out += ",";
        out += num(ring[i].lon_deg, precision);
        out += "]";
    }
    out += "]";
    return out;
}

std::string cells_json(const std::vector<Cell>& cells, int precision) {
    std::string out = "[";
    bool first_cell = true;
    const int geometry_precision = std::max(12, precision);
    const int surface_precision = std::max(10, precision);
    for (const Cell& cell : cells) {
        comma(out, first_cell);
        out += "{";
        bool first = true;
        add_int(out, first, "id", cell.id);
        add_raw(out, first, "position_3d", vec3_json(cell.p, geometry_precision));
        add_raw(out, first, "normal_3d", vec3_json(cell.p, geometry_precision));
        add_double(out, first, "lat_deg", cell.lat * DEG, geometry_precision);
        add_double(out, first, "lon_deg", cell.lon * DEG, geometry_precision);
        add_double(out, first, "area_km2", cell.area_km2, geometry_precision);
        add_raw(out, first, "neighbors", int_array_json(cell.neighbors));
        add_int(out, first, "political_region_id", cell.political_region_id);
        add_int(out, first, "culture_region_id", cell.culture_region_id);
        add_int(out, first, "language_region_id", cell.language_region_id);
        add_int(out, first, "plate_id", cell.plate_id);
        add_int(out, first, "initial_plate_id", cell.initial_plate_id);
        add_int(out, first, "plate_assignment_change_count", cell.plate_assignment_change_count);
        add_int(out, first, "last_plate_assignment_change_iteration", cell.last_plate_assignment_change_iteration);
        add_int(out, first, "last_crust_source_cell_id", cell.last_crust_source_cell_id);
        add_int(out, first, "crust_source_remap_event_count", cell.crust_source_remap_event_count);
        add_int(out, first, "oceanic_crust_aging_event_count", cell.oceanic_crust_aging_event_count);
        add_int(out, first, "oceanic_crust_rejuvenation_event_count", cell.oceanic_crust_rejuvenation_event_count);
        add_int(out, first, "oceanic_crust_subduction_event_count", cell.oceanic_crust_subduction_event_count);
        add_double(out, first, "cumulative_crust_transport_distance_km",
            cell.cumulative_crust_transport_distance_km, precision);
        add_str(out, first, "crust_type", CRUST_NAMES[cell.crust_type]);
        add_str(out, first, "lithology", LITHOLOGY_NAMES[cell.lithology]);
        add_str(out, first, "boundary_type", BOUNDARY_NAMES[cell.boundary_type]);
        add_double(out, first, "boundary_convergent", cell.boundary_convergent, precision);
        add_double(out, first, "boundary_divergent", cell.boundary_divergent, precision);
        add_double(out, first, "boundary_transform", cell.boundary_transform, precision);
        add_double(out, first, "crust_age_ma", cell.crust_age_ma, precision);
        add_double(out, first, "crust_thickness_km", cell.crust_thickness_km, precision);
        add_double(out, first, "crust_density", cell.crust_density, precision);
        add_double(out, first, "initial_crust_age_ma", cell.initial_crust_age_ma, precision);
        add_double(out, first, "initial_crust_thickness_km", cell.initial_crust_thickness_km, precision);
        add_double(out, first, "initial_crust_density", cell.initial_crust_density, precision);
        add_double(out, first, "cumulative_tectonic_elevation_change_m", cell.cumulative_tectonic_elevation_change_m, precision);
        add_double(out, first, "initial_isostatic_elevation_m", cell.initial_isostatic_elevation_m, precision);
        add_double(out, first, "initial_thermal_subsidence_m", cell.initial_thermal_subsidence_m, precision);
        add_double(out, first, "initial_ridge_uplift_m", cell.initial_ridge_uplift_m, precision);
        add_double(out, first, "initial_orogenic_uplift_m", cell.initial_orogenic_uplift_m, precision);
        add_double(out, first, "initial_volcanic_uplift_m", cell.initial_volcanic_uplift_m, precision);
        add_double(out, first, "initial_trench_subsidence_m", cell.initial_trench_subsidence_m, precision);
        add_double(out, first, "initial_rift_subsidence_m", cell.initial_rift_subsidence_m, precision);
        add_double(out, first, "initial_transform_fault_relief_m", cell.initial_transform_fault_relief_m, precision);
        add_double(out, first, "initial_secondary_roughness_m", cell.initial_secondary_roughness_m, precision);
        add_double(out, first, "initial_elevation_m", cell.initial_elevation_m, precision);
        add_double(out, first, "tectonic_uplift_rate_m_per_step", cell.uplift_rate, precision);
        add_double(out, first, "volcanic_potential_index", cell.volcanic_potential_index, precision);
        add_double(out, first, "elevation_m", cell.elevation_m, surface_precision);
        add_double(out, first, "water_depth_m", cell.water_depth_m, surface_precision);
        add_bool(out, first, "is_water", cell.is_water);
        add_str(out, first, "water_body_type", WATER_BODY_NAMES[cell.water_body]);
        add_double(out, first, "temperature_c", cell.temperature_c, precision);
        add_raw(out, first, "temperature_monthly_c", double_array_json(cell.temperature_monthly_c, precision));
        add_double(out, first, "precipitation_mm_y", cell.precipitation_mm_y, precision);
        add_raw(out, first, "precipitation_monthly_mm", double_array_json(cell.precipitation_monthly_mm, precision));
        add_double(out, first, "wind_east", cell.wind_east, precision);
        add_double(out, first, "wind_north", cell.wind_north, precision);
        add_raw(out, first, "wind_monthly_east", double_array_json(cell.wind_monthly_east, precision));
        add_raw(out, first, "wind_monthly_north", double_array_json(cell.wind_monthly_north, precision));
        add_double(out, first, "mean_seasonal_wind_speed", cell.mean_seasonal_wind_speed, precision);
        add_double(out, first, "seasonal_wind_reversal_index", cell.seasonal_wind_reversal_index, precision);
        add_str(out, first, "atmospheric_cell", ATMOSPHERIC_CELL_NAMES[cell.atmospheric_cell]);
        add_double(out, first, "surface_pressure_anomaly_hpa", cell.surface_pressure_anomaly_hpa, precision);
        add_double(out, first, "vertical_velocity_index", cell.vertical_velocity_index, precision);
        add_double(out, first, "wind_divergence_index", cell.wind_divergence_index, precision);
        add_double(out, first, "ocean_current_east", cell.ocean_current_east, precision);
        add_double(out, first, "ocean_current_north", cell.ocean_current_north, precision);
        add_double(out, first, "ocean_current_temperature_c", cell.ocean_current_temperature_c, precision);
        add_double(out, first, "ocean_current_moisture_factor", cell.ocean_current_moisture_factor, precision);
        add_double(out, first, "humidity_transport_index", cell.humidity_transport_index, precision);
        add_double(out, first, "upwind_ocean_fetch_km", cell.upwind_ocean_fetch_km, precision);
        add_double(out, first, "advected_moisture_factor", cell.advected_moisture_factor, precision);
        add_double(out, first, "orographic_factor", cell.orographic_factor, precision);
        add_double(out, first, "rain_shadow_factor", cell.rain_shadow_factor, precision);
        add_double(out, first, "vapor_evaporation_mm_y", cell.vapor_evaporation_mm_y, precision);
        add_double(out, first, "moisture_convergence_mm_y", cell.moisture_convergence_mm_y, precision);
        add_double(out, first, "orographic_rainout_mm_y", cell.orographic_rainout_mm_y, precision);
        add_double(out, first, "precipitation_recycling_fraction", cell.precipitation_recycling_fraction, precision);
        add_double(out, first, "vapor_deficit_mm_y", cell.vapor_deficit_mm_y, precision);
        add_double(out, first, "vapor_budget_residual_mm_y", cell.vapor_budget_residual_mm_y, precision);
        add_double(out, first, "hydrologic_potential_evapotranspiration_mm_y",
            cell.hydrologic_potential_evapotranspiration_mm_y, precision);
        add_double(out, first, "actual_evapotranspiration_mm_y",
            cell.actual_evapotranspiration_mm_y, precision);
        add_double(out, first, "infiltration_capacity_index",
            cell.infiltration_capacity_index, precision);
        add_double(out, first, "infiltration_mm_y",
            cell.infiltration_mm_y, precision);
        add_double(out, first, "hydrologic_water_balance_mm_y",
            cell.hydrologic_water_balance_mm_y, precision);
        add_double(out, first, "water_budget_runoff_mm_y",
            cell.water_budget_runoff_mm_y, precision);
        add_double(out, first, "runoff_budget_residual_mm_y",
            cell.runoff_budget_residual_mm_y, surface_precision);
        add_double(out, first, "runoff_budget_consistency_index",
            cell.runoff_budget_consistency_index, precision);
        add_double(out, first, "hydrologic_deficit_mm_y",
            cell.hydrologic_deficit_mm_y, precision);
        add_double(out, first, "runoff_generation_fraction",
            cell.runoff_generation_fraction, precision);
        add_double(out, first, "runoff_mm_y", cell.runoff_mm_y, precision);
        add_int(out, first, "flow_to", cell.flow_to);
        add_bool(out, first, "equal_filled_raw_downhill_rerouted", cell.equal_filled_raw_downhill_rerouted);
        add_int(out, first, "spill_to", cell.spill_to);
        add_int(out, first, "depression_component_id", cell.depression_component_id);
        add_int(out, first, "depression_sink_cell_id", cell.depression_sink_cell_id);
        add_int(out, first, "lake_basin_id", cell.lake_basin_id);
        add_str(out, first, "depression_policy", DEPRESSION_POLICY_NAMES[cell.depression_policy]);
        add_double(out, first, "flow_accumulation", cell.flow_accumulation, precision);
        add_double(out, first, "filled_elevation_m", cell.filled_elevation_m, precision);
        add_double(out, first, "hydrologic_surface_elevation_m",
            cell.hydrologic_surface_elevation_m, surface_precision);
        add_double(out, first, "hydrologic_flow_drop_m",
            cell.hydrologic_flow_drop_m, surface_precision);
        add_double(out, first, "hydrologic_flow_slope",
            cell.hydrologic_flow_slope, std::max(12, surface_precision));
        add_bool(out, first, "hydrologic_surface_conditioned",
            cell.hydrologic_surface_conditioned);
        add_double(out, first, "depression_depth_m", cell.depression_depth_m, precision);
        add_double(out, first, "spill_elevation_m", cell.spill_elevation_m, precision);
        add_double(out, first, "lake_fill_fraction", cell.lake_fill_fraction, precision);
        add_int(out, first, "basin_id", cell.basin_id);
        add_bool(out, first, "is_river", cell.is_river);
        add_bool(out, first, "is_lake", cell.is_lake);
        add_bool(out, first, "is_closed_basin", cell.is_closed_basin);
        add_bool(out, first, "lake_overflows", cell.lake_overflows);
        add_double(out, first, "cumulative_numeric_depression_fill_m",
            cell.cumulative_numeric_depression_fill_m, surface_precision);
        add_int(out, first, "numeric_depression_fill_event_count",
            cell.numeric_depression_fill_event_count);
        add_double(out, first,
            "cumulative_numeric_depression_breach_excavation_m",
            cell.cumulative_numeric_depression_breach_excavation_m,
            surface_precision);
        add_double(out, first,
            "cumulative_numeric_depression_breach_deposition_m",
            cell.cumulative_numeric_depression_breach_deposition_m,
            surface_precision);
        add_int(out, first, "numeric_depression_breach_event_count",
            cell.numeric_depression_breach_event_count);
        add_int(out, first, "numeric_depression_temporary_lake_event_count",
            cell.numeric_depression_temporary_lake_event_count);
        add_double(out, first, "erosion_rate", cell.erosion_rate, precision);
        add_double(out, first, "sediment_thickness_m", cell.sediment_thickness_m, precision);
        add_double(out, first, "sediment_production_m", cell.sediment_production_m, precision);
        add_double(out, first, "sediment_deposition_m", cell.sediment_deposition_m, precision);
        add_double(out, first, "sediment_export_m", cell.sediment_export_m, precision);
        add_double(out, first, "sediment_net_budget_m", cell.sediment_net_budget_m, precision);
        add_double(out, first, "sediment_alluvium_entrainment_m",
            cell.sediment_alluvium_entrainment_m, surface_precision);
        add_double(out, first, "sediment_bedrock_erosion_m",
            cell.sediment_bedrock_erosion_m, surface_precision);
        add_double(out, first, "hillslope_sediment_production_m",
            cell.hillslope_sediment_production_m, surface_precision);
        add_double(out, first, "hillslope_sediment_deposition_m",
            cell.hillslope_sediment_deposition_m, surface_precision);
        add_double(out, first, "hillslope_sediment_net_m",
            cell.hillslope_sediment_net_m, surface_precision);
        add_int(out, first, "hillslope_sediment_outgoing_edge_count",
            cell.hillslope_sediment_outgoing_edge_count);
        add_int(out, first, "hillslope_sediment_incoming_edge_count",
            cell.hillslope_sediment_incoming_edge_count);
        add_double(out, first, "fluvial_sediment_local_source_m",
            cell.fluvial_sediment_local_source_m, surface_precision);
        add_double(out, first, "fluvial_sediment_routed_incoming_m",
            cell.fluvial_sediment_routed_incoming_m, surface_precision);
        add_double(out, first, "fluvial_sediment_routed_outgoing_m",
            cell.fluvial_sediment_routed_outgoing_m, surface_precision);
        add_double(out, first, "fluvial_sediment_local_deposition_m",
            cell.fluvial_sediment_local_deposition_m, surface_precision);
        add_double(out, first, "fluvial_sediment_terminal_land_deposition_m",
            cell.fluvial_sediment_terminal_land_deposition_m,
            surface_precision);
        add_double(out, first, "fluvial_sediment_marine_deposition_m",
            cell.fluvial_sediment_marine_deposition_m, surface_precision);
        add_double(out, first, "fluvial_sediment_depression_fill_m",
            cell.fluvial_sediment_depression_fill_m, surface_precision);
        add_double(out, first, "fluvial_sediment_terminal_export_m",
            cell.fluvial_sediment_terminal_export_m, surface_precision);
        add_double(out, first,
            "fluvial_sediment_terminal_capture_volume_km3",
            cell.fluvial_sediment_terminal_capture_volume_km3,
            std::max(10, precision));
        add_int(out, first, "fluvial_sediment_routing_event_count",
            cell.fluvial_sediment_routing_event_count);
        add_double(out, first, "ice_thickness_m", cell.ice_thickness_m, precision);
        add_int(out, first, "ice_sheet_id", cell.ice_sheet_id);
        add_int(out, first, "glacier_flow_to", cell.glacier_flow_to);
        add_double(out, first, "ice_surface_mass_balance_m_y", cell.ice_surface_mass_balance_m_y, precision);
        add_double(out, first, "basal_sliding_index", cell.basal_sliding_index, precision);
        add_double(out, first, "ice_velocity_m_y", cell.ice_velocity_m_y, precision);
        add_double(out, first, "glacial_erosion_m", cell.glacial_erosion_m, precision);
        add_double(out, first, "glacial_sediment_production_m",
            cell.glacial_sediment_production_m, surface_precision);
        add_double(out, first, "glacial_sediment_deposition_m",
            cell.glacial_sediment_deposition_m, surface_precision);
        add_double(out, first, "glacial_sediment_net_m",
            cell.glacial_sediment_net_m, surface_precision);
        add_int(out, first, "glacial_sediment_outgoing_transfer_count",
            cell.glacial_sediment_outgoing_transfer_count);
        add_int(out, first, "glacial_sediment_incoming_transfer_count",
            cell.glacial_sediment_incoming_transfer_count);
        add_double(out, first, "moraine_deposition_m", cell.moraine_deposition_m, precision);
        add_double(out, first, "deglaciation_age_ka", cell.deglaciation_age_ka, precision);
        add_str(out, first, "landform", LANDFORM_NAMES[cell.landform]);
        add_str(out, first, "soil_type", SOIL_NAMES[cell.soil_type]);
        add_double(out, first, "soil_depth_m", cell.soil_depth_m, precision);
        add_double(out, first, "fertility", cell.fertility, std::max(8, precision));
        add_str(out, first, "biome", BIOME_NAMES[cell.biome]);
        add_str(out, first, "resource", RESOURCE_NAMES[cell.resource]);
        add_double(
            out,
            first,
            "settlement_score",
            cell.settlement_score,
            std::max(8, precision)
        );
        out += "}";
    }
    out += "]";
    return out;
}

std::string settlements_json(const std::vector<Cell>& cells, const std::vector<Settlement>& settlements, int precision) {
    std::string out = "[";
    bool first_settlement = true;
    for (const Settlement& settlement : settlements) {
        const Cell& cell = cells[settlement.cell_id];
        comma(out, first_settlement);
        out += "{";
        bool first = true;
        add_int(out, first, "id", settlement.id);
        add_int(out, first, "cell_id", settlement.cell_id);
        add_int(out, first, "region_id", settlement.region_id);
        add_int(out, first, "culture_region_id", settlement.culture_region_id);
        add_int(out, first, "language_region_id", settlement.language_region_id);
        add_str(out, first, "type", SETTLEMENT_TYPE_NAMES[settlement.type]);
        add_double(out, first, "score", settlement.score, std::max(8, precision));
        add_double(out, first, "lat_deg", cell.lat * DEG, precision);
        add_double(out, first, "lon_deg", cell.lon * DEG, precision);
        add_str(out, first, "biome", BIOME_NAMES[cell.biome]);
        add_str(out, first, "resource", RESOURCE_NAMES[cell.resource]);
        add_str(out, first, "water_body_type", WATER_BODY_NAMES[cell.water_body]);
        add_double(out, first, "fertility", cell.fertility, std::max(8, precision));
        add_bool(out, first, "is_river", cell.is_river);
        out += "}";
    }
    out += "]";
    return out;
}

std::string routes_json(const std::vector<Route>& routes, int precision) {
    std::string out = "[";
    bool first_route = true;
    for (const Route& route : routes) {
        comma(out, first_route);
        out += "{";
        bool first = true;
        add_int(out, first, "id", route.id);
        add_int(out, first, "from", route.from);
        add_int(out, first, "to", route.to);
        add_str(out, first, "type", ROUTE_TYPE_NAMES[route.type]);
        add_double(out, first, "distance_km", route.distance_km, precision);
        add_double(out, first, "cost", route.cost, precision);
        out += "}";
    }
    out += "]";
    return out;
}

std::string trade_flows_json(const std::vector<TradeFlow>& flows, int precision) {
    std::string out = "[";
    bool first_flow = true;
    for (const TradeFlow& flow : flows) {
        comma(out, first_flow);
        out += "{";
        bool first = true;
        add_int(out, first, "id", flow.id);
        add_int(out, first, "route_id", flow.route_id);
        add_int(out, first, "from", flow.from);
        add_int(out, first, "to", flow.to);
        add_int(out, first, "region_from", flow.region_from);
        add_int(out, first, "region_to", flow.region_to);
        add_str(out, first, "primary_good", RESOURCE_NAMES[flow.primary_good]);
        add_bool(out, first, "interregional", flow.interregional);
        add_double(out, first, "distance_km", flow.distance_km, precision);
        add_double(out, first, "friction", flow.friction, precision);
        add_double(out, first, "volume_index", flow.volume_index, precision);
        out += "}";
    }
    out += "]";
    return out;
}

std::string watersheds_json(const std::vector<Watershed>& watersheds, int precision) {
    std::string out = "[";
    bool first_watershed = true;
    for (const Watershed& watershed : watersheds) {
        comma(out, first_watershed);
        out += "{";
        bool first = true;
        add_int(out, first, "id", watershed.id);
        add_int(out, first, "basin_id", watershed.basin_id);
        add_int(out, first, "outlet_cell_id", watershed.outlet_cell_id);
        add_str(out, first, "outlet_type", WATERSHED_OUTLET_NAMES[watershed.outlet_type]);
        add_bool(out, first, "is_endorheic", watershed.is_endorheic);
        add_int(out, first, "cell_count", watershed.cell_count);
        add_int(out, first, "river_cell_count", watershed.river_cell_count);
        add_double(out, first, "area_km2", watershed.area_km2, precision);
        add_double(out, first, "mean_runoff_mm_y", watershed.mean_runoff_mm_y, precision);
        add_double(out, first, "mean_elevation_m", watershed.mean_elevation_m, precision);
        add_double(out, first, "max_flow_accumulation", watershed.max_flow_accumulation, precision);
        add_double(out, first, "centroid_lat_deg", watershed.centroid_lat_deg, precision);
        add_double(out, first, "centroid_lon_deg", watershed.centroid_lon_deg, precision);
        add_double(out, first, "min_lat_deg", watershed.min_lat_deg, precision);
        add_double(out, first, "max_lat_deg", watershed.max_lat_deg, precision);
        add_double(out, first, "min_lon_deg", watershed.min_lon_deg, precision);
        add_double(out, first, "max_lon_deg", watershed.max_lon_deg, precision);
        add_double(out, first, "lon_span_deg", watershed.lon_span_deg, precision);
        add_bool(out, first, "crosses_antimeridian", watershed.crosses_antimeridian);
        add_double(out, first, "boundary_perimeter_km", watershed.boundary_perimeter_km, precision);
        add_double(out, first, "dissolved_polygon_area_km2", watershed.dissolved_polygon_area_km2, precision);
        add_double(out, first, "polygon_area_error_fraction", watershed.polygon_area_error_fraction, precision);
        add_double(out, first, "compactness_index", watershed.compactness_index, precision);
        add_double(out, first, "geometry_quality", watershed.geometry_quality, precision);
        add_raw(out, first, "boundary_cell_ids", int_array_json(watershed.boundary_cell_ids));
        add_raw(out, first, "boundary_ring", latlon_ring_json(watershed.boundary_ring, precision));
        out += "}";
    }
    out += "]";
    return out;
}

std::string lake_basins_json(const std::vector<LakeBasin>& basins, int precision) {
    std::string out = "[";
    bool first_basin = true;
    for (const LakeBasin& basin : basins) {
        comma(out, first_basin);
        out += "{";
        bool first = true;
        add_int(out, first, "id", basin.id);
        add_int(out, first, "depression_component_id", basin.depression_component_id);
        add_int(out, first, "outlet_cell_id", basin.outlet_cell_id);
        add_int(out, first, "spill_to_cell_id", basin.spill_to_cell_id);
        add_str(out, first, "depression_policy", DEPRESSION_POLICY_NAMES[basin.depression_policy]);
        add_str(out, first, "water_body_type", WATER_BODY_NAMES[basin.water_body]);
        add_bool(out, first, "is_geologic", basin.is_geologic);
        add_bool(out, first, "overflows", basin.overflows);
        add_int(out, first, "depression_cell_count", basin.depression_cell_count);
        add_int(out, first, "cell_count", basin.cell_count);
        add_int(out, first, "lake_cell_count", basin.lake_cell_count);
        add_double(out, first, "depression_area_km2", basin.depression_area_km2, precision);
        add_double(out, first, "geologic_area_fraction", basin.geologic_area_fraction, precision);
        add_double(out, first, "area_km2", basin.area_km2, precision);
        add_double(out, first, "lake_area_km2", basin.lake_area_km2, precision);
        add_double(out, first, "mean_runoff_mm_y", basin.mean_runoff_mm_y, precision);
        add_double(out, first, "outlet_elevation_m", basin.outlet_elevation_m, precision);
        add_double(out, first, "spill_elevation_m", basin.spill_elevation_m, precision);
        add_double(out, first, "max_depression_depth_m", basin.max_depression_depth_m, precision);
        add_double(out, first, "mean_water_depth_m", basin.mean_water_depth_m, precision);
        add_double(out, first, "fill_fraction", basin.fill_fraction, precision);
        add_double(out, first, "storage_capacity_km3", basin.storage_capacity_km3, precision);
        add_double(out, first, "annual_runoff_km3", basin.annual_runoff_km3, precision);
        add_double(out, first, "overflow_index", basin.overflow_index, precision);
        add_int(out, first, "overflow_stage_count", basin.overflow_stage_count);
        add_double(out, first, "overflow_path_length_km", basin.overflow_path_length_km, precision);
        add_double(out, first, "avulsion_risk", basin.avulsion_risk, precision);
        add_raw(out, first, "overflow_path_cell_ids", int_array_json(basin.overflow_path_cell_ids));
        out += "}";
    }
    out += "]";
    return out;
}

std::string coastal_features_json(const std::vector<CoastalFeature>& features, int precision) {
    std::string out = "[";
    bool first_feature = true;
    for (const CoastalFeature& feature : features) {
        comma(out, first_feature);
        out += "{";
        bool first = true;
        add_int(out, first, "id", feature.id);
        add_int(out, first, "cell_id", feature.cell_id);
        add_str(out, first, "type", COASTAL_FEATURE_TYPE_NAMES[feature.type]);
        add_str(out, first, "shoreline_trend", SHORELINE_TREND_NAMES[feature.shoreline_trend]);
        add_double(out, first, "lat_deg", feature.lat_deg, precision);
        add_double(out, first, "lon_deg", feature.lon_deg, precision);
        add_double(out, first, "length_km", feature.length_km, precision);
        add_double(out, first, "sediment_supply_index", feature.sediment_supply_index, precision);
        add_double(out, first, "wave_energy_index", feature.wave_energy_index, precision);
        add_double(out, first, "progradation_index", feature.progradation_index, precision);
        add_double(out, first, "migration_rate_m_y", feature.migration_rate_m_y, precision);
        add_double(out, first, "longshore_transport_index", feature.longshore_transport_index, precision);
        out += "}";
    }
    out += "]";
    return out;
}

std::string sedimentary_basins_json(const std::vector<SedimentaryBasin>& basins, int precision) {
    std::string out = "[";
    bool first_basin = true;
    for (const SedimentaryBasin& basin : basins) {
        comma(out, first_basin);
        out += "{";
        bool first = true;
        add_int(out, first, "id", basin.id);
        add_int(out, first, "basin_id", basin.basin_id);
        add_str(out, first, "type", SEDIMENTARY_BASIN_TYPE_NAMES[basin.type]);
        add_str(out, first, "dominant_resource", RESOURCE_NAMES[basin.dominant_resource]);
        add_int(out, first, "cell_count", basin.cell_count);
        add_bool(out, first, "is_active", basin.is_active);
        add_double(out, first, "area_km2", basin.area_km2, precision);
        add_double(out, first, "mean_sediment_thickness_m", basin.mean_sediment_thickness_m, precision);
        add_double(out, first, "max_sediment_thickness_m", basin.max_sediment_thickness_m, precision);
        add_double(out, first, "mean_subsidence_index", basin.mean_subsidence_index, precision);
        add_double(out, first, "depositional_age_ma", basin.depositional_age_ma, precision);
        out += "}";
    }
    out += "]";
    return out;
}

std::string stratigraphic_columns_json(const std::vector<StratigraphicColumn>& columns, int precision) {
    std::string out = "[";
    bool first_column = true;
    for (const StratigraphicColumn& column : columns) {
        comma(out, first_column);
        out += "{";
        bool first = true;
        add_int(out, first, "id", column.id);
        add_int(out, first, "basin_id", column.basin_id);
        add_int(out, first, "representative_cell_id", column.representative_cell_id);
        add_str(out, first, "dominant_facies", STRATIGRAPHIC_FACIES_NAMES[column.dominant_facies]);
        add_str(out, first, "sequence_phase", SEQUENCE_PHASE_NAMES[column.sequence_phase]);
        add_bool(out, first, "is_active", column.is_active);
        add_int(out, first, "layer_count", static_cast<int>(column.layers.size()));
        add_double(out, first, "total_thickness_m", column.total_thickness_m, precision);
        add_double(out, first, "depositional_span_ma", column.depositional_span_ma, precision);
        add_double(out, first, "mean_subsidence_index", column.mean_subsidence_index, precision);
        add_double(out, first, "sediment_flux_index", column.sediment_flux_index, precision);
        add_double(out, first, "preservation_potential", column.preservation_potential, precision);
        std::string layers = "[";
        bool first_layer = true;
        for (const StratigraphicLayer& layer : column.layers) {
            comma(layers, first_layer);
            layers += "{";
            bool first_layer_field = true;
            add_int(layers, first_layer_field, "index", layer.index);
            add_str(layers, first_layer_field, "facies", STRATIGRAPHIC_FACIES_NAMES[layer.facies]);
            add_double(layers, first_layer_field, "thickness_m", layer.thickness_m, precision);
            add_double(layers, first_layer_field, "age_top_ma", layer.age_top_ma, precision);
            add_double(layers, first_layer_field, "age_base_ma", layer.age_base_ma, precision);
            add_double(layers, first_layer_field, "grain_size_index", layer.grain_size_index, precision);
            add_double(layers, first_layer_field, "organic_potential", layer.organic_potential, precision);
            add_double(layers, first_layer_field, "reservoir_quality", layer.reservoir_quality, precision);
            add_double(layers, first_layer_field, "seal_quality", layer.seal_quality, precision);
            layers += "}";
        }
        layers += "]";
        add_raw(out, first, "layers", layers);
        out += "}";
    }
    out += "]";
    return out;
}

std::string ice_sheets_json(const std::vector<IceSheet>& sheets, int precision) {
    std::string out = "[";
    bool first_sheet = true;
    for (const IceSheet& sheet : sheets) {
        comma(out, first_sheet);
        out += "{";
        bool first = true;
        add_int(out, first, "id", sheet.id);
        add_str(out, first, "retreat_stage", ICE_RETREAT_STAGE_NAMES[sheet.retreat_stage]);
        add_int(out, first, "cell_count", sheet.cell_count);
        add_int(out, first, "moraine_cell_count", sheet.moraine_cell_count);
        add_double(out, first, "area_km2", sheet.area_km2, precision);
        add_double(out, first, "mean_ice_thickness_m", sheet.mean_ice_thickness_m, precision);
        add_double(out, first, "max_ice_thickness_m", sheet.max_ice_thickness_m, precision);
        add_double(out, first, "mean_glacial_erosion_m", sheet.mean_glacial_erosion_m, precision);
        add_double(out, first, "mean_surface_mass_balance_m_y", sheet.mean_surface_mass_balance_m_y, precision);
        add_double(out, first, "mean_basal_sliding_index", sheet.mean_basal_sliding_index, precision);
        add_double(out, first, "mean_ice_velocity_m_y", sheet.mean_ice_velocity_m_y, precision);
        add_double(out, first, "accumulation_area_fraction", sheet.accumulation_area_fraction, precision);
        add_double(out, first, "equilibrium_line_altitude_m", sheet.equilibrium_line_altitude_m, precision);
        add_double(out, first, "retreat_rate_m_y", sheet.retreat_rate_m_y, precision);
        add_double(out, first, "mean_deglaciation_age_ka", sheet.mean_deglaciation_age_ka, precision);
        add_double(out, first, "mean_moraine_deposition_m", sheet.mean_moraine_deposition_m, precision);
        out += "}";
    }
    out += "]";
    return out;
}

std::string political_regions_json(const std::vector<PoliticalRegion>& regions, int precision) {
    std::string out = "[";
    bool first_region = true;
    for (const PoliticalRegion& region : regions) {
        comma(out, first_region);
        out += "{";
        bool first = true;
        add_int(out, first, "id", region.id);
        add_int(out, first, "capital_settlement_id", region.capital_settlement_id);
        add_str(out, first, "type", POLITICAL_REGION_TYPE_NAMES[region.type]);
        add_str(out, first, "dominant_biome", BIOME_NAMES[region.dominant_biome]);
        add_str(out, first, "dominant_resource", RESOURCE_NAMES[region.dominant_resource]);
        add_int(out, first, "settlement_count", region.settlement_count);
        add_int(out, first, "route_count", region.route_count);
        add_raw(out, first, "settlement_ids", int_array_json(region.settlement_ids));
        add_double(out, first, "area_km2", region.area_km2, precision);
        add_double(out, first, "mean_settlement_score", region.mean_settlement_score, precision);
        add_double(out, first, "mean_elevation_m", region.mean_elevation_m, precision);
        add_double(out, first, "barrier_pressure", region.barrier_pressure, precision);
        out += "}";
    }
    out += "]";
    return out;
}

std::string cultures_json(const std::vector<CultureRegion>& cultures, int precision) {
    std::string out = "[";
    bool first_culture = true;
    for (const CultureRegion& culture : cultures) {
        comma(out, first_culture);
        out += "{";
        bool first = true;
        add_int(out, first, "id", culture.id);
        add_int(out, first, "language_region_id", culture.language_region_id);
        add_int(out, first, "homeland_region_id", culture.homeland_region_id);
        add_str(out, first, "type", CULTURE_TYPE_NAMES[culture.type]);
        add_str(out, first, "dominant_biome", BIOME_NAMES[culture.dominant_biome]);
        add_str(out, first, "dominant_resource", RESOURCE_NAMES[culture.dominant_resource]);
        add_int(out, first, "settlement_count", culture.settlement_count);
        add_int(out, first, "sacred_area_count", culture.sacred_area_count);
        add_int(out, first, "ruin_count", culture.ruin_count);
        add_raw(out, first, "settlement_ids", int_array_json(culture.settlement_ids));
        add_double(out, first, "area_km2", culture.area_km2, precision);
        add_double(out, first, "agricultural_area_km2", culture.agricultural_area_km2, precision);
        add_double(out, first, "mining_area_km2", culture.mining_area_km2, precision);
        add_double(out, first, "mean_fertility", culture.mean_fertility, precision);
        add_double(out, first, "mean_elevation_m", culture.mean_elevation_m, precision);
        add_double(out, first, "barrier_isolation", culture.barrier_isolation, precision);
        add_double(out, first, "trade_contact_index", culture.trade_contact_index, precision);
        add_double(out, first, "migration_pressure", culture.migration_pressure, precision);
        add_double(out, first, "continuity_index", culture.continuity_index, precision);
        add_double(out, first, "estimated_age_years", culture.estimated_age_years, precision);
        out += "}";
    }
    out += "]";
    return out;
}

std::string language_regions_json(const std::vector<LanguageRegion>& languages, int precision) {
    std::string out = "[";
    bool first_language = true;
    for (const LanguageRegion& language : languages) {
        comma(out, first_language);
        out += "{";
        bool first = true;
        add_int(out, first, "id", language.id);
        add_int(out, first, "parent_language_region_id", language.parent_language_region_id);
        add_str(out, first, "family", LANGUAGE_FAMILY_NAMES[language.family]);
        add_int(out, first, "lineage_depth", language.lineage_depth);
        add_int(out, first, "culture_count", language.culture_count);
        add_int(out, first, "settlement_count", language.settlement_count);
        add_raw(out, first, "culture_ids", int_array_json(language.culture_ids));
        add_double(out, first, "area_km2", language.area_km2, precision);
        add_double(out, first, "barrier_isolation", language.barrier_isolation, precision);
        add_double(out, first, "trade_contact_index", language.trade_contact_index, precision);
        add_double(out, first, "divergence_age_years", language.divergence_age_years, precision);
        add_double(out, first, "change_rate", language.change_rate, precision);
        add_int(out, first, "phoneme_inventory_size", language.phoneme_inventory_size);
        add_double(out, first, "phonological_complexity", language.phonological_complexity, precision);
        add_double(out, first, "sound_shift_index", language.sound_shift_index, precision);
        add_double(out, first, "inherited_phonology_fraction", language.inherited_phonology_fraction, precision);
        out += "}";
    }
    out += "]";
    return out;
}

std::string sacred_areas_json(const std::vector<SacredArea>& sacred_areas, int precision) {
    std::string out = "[";
    bool first_site = true;
    for (const SacredArea& site : sacred_areas) {
        comma(out, first_site);
        out += "{";
        bool first = true;
        add_int(out, first, "id", site.id);
        add_int(out, first, "cell_id", site.cell_id);
        add_int(out, first, "culture_region_id", site.culture_region_id);
        add_int(out, first, "language_region_id", site.language_region_id);
        add_str(out, first, "type", SACRED_AREA_TYPE_NAMES[site.type]);
        add_double(out, first, "significance", site.significance, precision);
        add_double(out, first, "lat_deg", site.lat_deg, precision);
        add_double(out, first, "lon_deg", site.lon_deg, precision);
        out += "}";
    }
    out += "]";
    return out;
}

std::string ruins_json(const std::vector<Ruin>& ruins, int precision) {
    std::string out = "[";
    bool first_ruin = true;
    for (const Ruin& ruin : ruins) {
        comma(out, first_ruin);
        out += "{";
        bool first = true;
        add_int(out, first, "id", ruin.id);
        add_int(out, first, "cell_id", ruin.cell_id);
        add_int(out, first, "culture_region_id", ruin.culture_region_id);
        add_int(out, first, "language_region_id", ruin.language_region_id);
        add_str(out, first, "type", RUIN_TYPE_NAMES[ruin.type]);
        add_str(out, first, "abandonment_reason", ABANDONMENT_REASON_NAMES[ruin.abandonment_reason]);
        add_double(out, first, "significance", ruin.significance, precision);
        add_double(out, first, "preservation_score", ruin.preservation_score, precision);
        add_double(out, first, "lat_deg", ruin.lat_deg, precision);
        add_double(out, first, "lon_deg", ruin.lon_deg, precision);
        out += "}";
    }
    out += "]";
    return out;
}

std::string historical_eras_json(const std::vector<HistoricalEra>& eras, int precision) {
    std::string out = "[";
    bool first_era = true;
    for (const HistoricalEra& era : eras) {
        comma(out, first_era);
        out += "{";
        bool first = true;
        add_int(out, first, "id", era.id);
        add_str(out, first, "dominant_process", HISTORICAL_PROCESS_NAMES[era.dominant_process]);
        add_int(out, first, "event_count", era.event_count);
        add_int(out, first, "state_event_count", era.state_event_count);
        add_int(out, first, "migration_event_count", era.migration_event_count);
        add_int(out, first, "language_event_count", era.language_event_count);
        add_double(out, first, "start_year_bp", era.start_year_bp, precision);
        add_double(out, first, "end_year_bp", era.end_year_bp, precision);
        add_double(out, first, "mean_instability", era.mean_instability, precision);
        add_double(out, first, "mean_connectivity", era.mean_connectivity, precision);
        out += "}";
    }
    out += "]";
    return out;
}

std::string historical_events_json(const std::vector<HistoricalEvent>& events, int precision) {
    std::string out = "[";
    bool first_event = true;
    for (const HistoricalEvent& event : events) {
        comma(out, first_event);
        out += "{";
        bool first = true;
        add_int(out, first, "id", event.id);
        add_int(out, first, "era_id", event.era_id);
        add_str(out, first, "type", HISTORY_EVENT_TYPE_NAMES[event.type]);
        add_int(out, first, "region_id", event.region_id);
        add_int(out, first, "related_region_id", event.related_region_id);
        add_int(out, first, "culture_region_id", event.culture_region_id);
        add_int(out, first, "related_culture_region_id", event.related_culture_region_id);
        add_int(out, first, "language_region_id", event.language_region_id);
        add_int(out, first, "related_language_region_id", event.related_language_region_id);
        add_int(out, first, "cell_id", event.cell_id);
        add_double(out, first, "year_bp", event.year_bp, precision);
        add_double(out, first, "pressure_index", event.pressure_index, precision);
        add_double(out, first, "continuity_index", event.continuity_index, precision);
        out += "}";
    }
    out += "]";
    return out;
}

std::string population_regions_json(const std::vector<PopulationRegion>& populations, int precision) {
    std::string out = "[";
    bool first_population = true;
    for (const PopulationRegion& population : populations) {
        comma(out, first_population);
        out += "{";
        bool first = true;
        add_int(out, first, "id", population.id);
        add_int(out, first, "region_id", population.region_id);
        add_int(out, first, "culture_region_id", population.culture_region_id);
        add_int(out, first, "language_region_id", population.language_region_id);
        add_int(out, first, "settlement_count", population.settlement_count);
        add_double(out, first, "carrying_capacity", population.carrying_capacity, precision);
        add_double(out, first, "estimated_population", population.estimated_population, precision);
        add_double(out, first, "agricultural_capacity_index", population.agricultural_capacity_index, precision);
        add_double(out, first, "water_security_index", population.water_security_index, precision);
        add_double(out, first, "urbanization_fraction", population.urbanization_fraction, precision);
        add_double(out, first, "growth_rate_per_year", population.growth_rate_per_year, precision);
        add_double(out, first, "population_pressure", population.population_pressure, precision);
        add_double(out, first, "migration_balance", population.migration_balance, precision);
        add_double(out, first, "hazard_mortality_index", population.hazard_mortality_index, precision);
        out += "}";
    }
    out += "]";
    return out;
}

std::string conflicts_json(const std::vector<ConflictRecord>& conflicts, int precision) {
    std::string out = "[";
    bool first_conflict = true;
    for (const ConflictRecord& conflict : conflicts) {
        comma(out, first_conflict);
        out += "{";
        bool first = true;
        add_int(out, first, "id", conflict.id);
        add_int(out, first, "era_id", conflict.era_id);
        add_int(out, first, "region_a", conflict.region_a);
        add_int(out, first, "region_b", conflict.region_b);
        add_int(out, first, "culture_a", conflict.culture_a);
        add_int(out, first, "culture_b", conflict.culture_b);
        add_str(out, first, "cause", CONFLICT_CAUSE_NAMES[conflict.cause]);
        add_str(out, first, "outcome", CONFLICT_OUTCOME_NAMES[conflict.outcome]);
        add_int(out, first, "contested_cell_id", conflict.contested_cell_id);
        add_double(out, first, "start_year_bp", conflict.start_year_bp, precision);
        add_double(out, first, "end_year_bp", conflict.end_year_bp, precision);
        add_double(out, first, "war_duration_years", conflict.war_duration_years, precision);
        add_double(out, first, "intensity", conflict.intensity, precision);
        add_double(out, first, "resource_pressure", conflict.resource_pressure, precision);
        add_double(out, first, "water_stress", conflict.water_stress, precision);
        add_double(out, first, "trade_chokepoint_index", conflict.trade_chokepoint_index, precision);
        add_double(out, first, "region_a_force_estimate", conflict.region_a_force_estimate, precision);
        add_double(out, first, "region_b_force_estimate", conflict.region_b_force_estimate, precision);
        add_double(out, first, "mobilized_population", conflict.mobilized_population, precision);
        add_double(out, first, "casualty_rate", conflict.casualty_rate, precision);
        add_double(out, first, "logistics_strain_index", conflict.logistics_strain_index, precision);
        add_double(out, first, "economic_disruption_index", conflict.economic_disruption_index, precision);
        add_double(out, first, "estimated_casualties", conflict.estimated_casualties, precision);
        out += "}";
    }
    out += "]";
    return out;
}

std::string dynasties_json(const std::vector<DynastyRecord>& dynasties, int precision) {
    std::string out = "[";
    bool first_dynasty = true;
    for (const DynastyRecord& dynasty : dynasties) {
        comma(out, first_dynasty);
        out += "{";
        bool first = true;
        add_int(out, first, "id", dynasty.id);
        add_int(out, first, "region_id", dynasty.region_id);
        add_int(out, first, "culture_region_id", dynasty.culture_region_id);
        add_int(out, first, "language_region_id", dynasty.language_region_id);
        add_int(out, first, "parent_dynasty_id", dynasty.parent_dynasty_id);
        add_int(out, first, "founder_dynasty_id", dynasty.founder_dynasty_id);
        add_int(out, first, "successor_dynasty_id", dynasty.successor_dynasty_id);
        add_int(out, first, "founding_event_id", dynasty.founding_event_id);
        add_str(out, first, "collapse_reason", DYNASTY_COLLAPSE_REASON_NAMES[dynasty.collapse_reason]);
        add_int(out, first, "lineage_depth", dynasty.lineage_depth);
        add_int(out, first, "child_dynasty_count", dynasty.child_dynasty_count);
        add_raw(out, first, "child_dynasty_ids", int_array_json(dynasty.child_dynasty_ids));
        add_double(out, first, "start_year_bp", dynasty.start_year_bp, precision);
        add_double(out, first, "end_year_bp", dynasty.end_year_bp, precision);
        add_double(out, first, "duration_years", dynasty.duration_years, precision);
        add_double(out, first, "legitimacy_index", dynasty.legitimacy_index, precision);
        add_double(out, first, "succession_pressure", dynasty.succession_pressure, precision);
        add_double(out, first, "dynastic_continuity_index", dynasty.dynastic_continuity_index, precision);
        out += "}";
    }
    out += "]";
    return out;
}

std::string snapshot_regions_json(const std::vector<SnapshotRegion>& regions, int precision) {
    std::string out = "[";
    bool first_region = true;
    for (const SnapshotRegion& region : regions) {
        comma(out, first_region);
        out += "{";
        bool first = true;
        add_int(out, first, "region_id", region.region_id);
        add_int(out, first, "capital_settlement_id", region.capital_settlement_id);
        add_int(out, first, "culture_region_id", region.culture_region_id);
        add_int(out, first, "language_region_id", region.language_region_id);
        add_int(out, first, "cell_count", region.cell_count);
        add_bool(out, first, "crosses_antimeridian", region.crosses_antimeridian);
        add_raw(out, first, "boundary_cell_ids", int_array_json(region.boundary_cell_ids));
        add_raw(out, first, "boundary_ring", latlon_ring_json(region.boundary_ring, precision));
        add_double(out, first, "area_km2", region.area_km2, precision);
        add_double(out, first, "boundary_perimeter_km", region.boundary_perimeter_km, precision);
        add_double(out, first, "dissolved_polygon_area_km2", region.dissolved_polygon_area_km2, precision);
        add_double(out, first, "polygon_area_error_fraction", region.polygon_area_error_fraction, precision);
        add_double(out, first, "compactness_index", region.compactness_index, precision);
        add_double(out, first, "geometry_quality", region.geometry_quality, precision);
        add_double(out, first, "estimated_population", region.estimated_population, precision);
        add_double(out, first, "stability_index", region.stability_index, precision);
        add_double(out, first, "centroid_lat_deg", region.centroid_lat_deg, precision);
        add_double(out, first, "centroid_lon_deg", region.centroid_lon_deg, precision);
        out += "}";
    }
    out += "]";
    return out;
}

std::string territorial_snapshots_json(const std::vector<TerritorialSnapshot>& snapshots, int precision) {
    std::string out = "[";
    bool first_snapshot = true;
    for (const TerritorialSnapshot& snapshot : snapshots) {
        comma(out, first_snapshot);
        out += "{";
        bool first = true;
        add_int(out, first, "id", snapshot.id);
        add_int(out, first, "era_id", snapshot.era_id);
        add_str(out, first, "dominant_process", HISTORICAL_PROCESS_NAMES[snapshot.dominant_process]);
        add_int(out, first, "region_count", snapshot.region_count);
        add_int(out, first, "largest_region_id", snapshot.largest_region_id);
        add_raw(out, first, "regions", snapshot_regions_json(snapshot.regions, precision));
        add_double(out, first, "year_bp", snapshot.year_bp, precision);
        add_double(out, first, "assigned_land_fraction", snapshot.assigned_land_fraction, precision);
        add_double(out, first, "estimated_population", snapshot.estimated_population, precision);
        add_double(out, first, "largest_region_area_km2", snapshot.largest_region_area_km2, precision);
        add_double(out, first, "fragmentation_index", snapshot.fragmentation_index, precision);
        out += "}";
    }
    out += "]";
    return out;
}

std::string climate_model_json(const Params& params) {
    const int precision = std::max(6, params.float_precision);
    const double latitude_temperature_area_mean_offset_c =
        CLIMATE_LATITUDE_TEMPERATURE_GRADIENT_C /
        (CLIMATE_LATITUDE_TEMPERATURE_EXPONENT + 1.0);
    std::string out = "{";
    bool first = true;
    add_str(out, first, "model_type", "equilibrium_latitude_circulation_climate_v3");
    add_str(out, first, "temperature_model", "area_mean_normalized_latitude_centered_local_adjustments_v3");
    add_str(out, first, "precipitation_model", "circulation_orography_wind_transport_subtropical_drying_v1");
    add_str(out, first, "base_temperature_interpretation", "post_centered_local_adjustment_global_area_mean_c");
    add_double(out, first, "base_temperature_c", params.base_temperature_c, precision);
    add_double(out, first, "latitude_temperature_gradient_c",
        CLIMATE_LATITUDE_TEMPERATURE_GRADIENT_C, precision);
    add_double(out, first, "latitude_temperature_exponent",
        CLIMATE_LATITUDE_TEMPERATURE_EXPONENT, precision);
    add_double(out, first, "latitude_temperature_area_mean_offset_c",
        latitude_temperature_area_mean_offset_c, precision);
    add_double(out, first, "lapse_rate_c_per_km", params.lapse_rate_c_per_km, precision);
    add_double(out, first, "marine_annual_temperature_offset_c",
        CLIMATE_MARINE_ANNUAL_TEMPERATURE_OFFSET_C, precision);
    add_double(out, first, "precipitation_scale", params.precipitation_scale, precision);
    add_double(out, first, "subtropical_drying_strength",
        params.subtropical_drying_strength, precision);
    add_double(out, first, "subtropical_drying_min_factor",
        CLIMATE_SUBTROPICAL_DRYING_MIN_FACTOR, precision);
    add_double(out, first, "seasonal_monsoon_precipitation_strength",
        CLIMATE_SEASONAL_MONSOON_PRECIPITATION_STRENGTH, precision);
    add_double(out, first, "seasonal_monsoon_precipitation_min_factor",
        CLIMATE_SEASONAL_MONSOON_PRECIPITATION_MIN_FACTOR, precision);
    add_double(out, first, "seasonal_monsoon_precipitation_max_factor",
        CLIMATE_SEASONAL_MONSOON_PRECIPITATION_MAX_FACTOR, precision);
    add_int(out, first, "configured_month_count", params.months);
    add_bool(out, first, "latitude_temperature_area_normalized", true);
    add_bool(out, first, "local_temperature_adjustments_area_centered", true);
    add_str(out, first, "local_temperature_centering_scope",
        "elevation_lapse_ocean_current");
    add_bool(out, first, "mass_conserving_atmosphere", false);
    add_bool(out, first, "transient_climate_resolved", false);
    add_str(out, first, "model_limitation",
        "equilibrium_diagnostic_climate_without_mass_conserving_three_dimensional_atmosphere");
    out += "}";
    return out;
}

std::string hydrologic_water_budget_model_json(
    const std::vector<HydrologicWaterBudgetStage>& history,
    int precision
) {
    const int model_precision = std::max(10, precision);
    const HydrologicWaterBudgetStage* final_stage =
        history.empty() ? nullptr : &history.back();
    std::string permeability_json = "{";
    bool first_permeability = true;
    for (std::size_t index = 0; index < LITHOLOGY_NAMES.size(); ++index) {
        add_double(
            permeability_json,
            first_permeability,
            LITHOLOGY_NAMES[index],
            hydrologic_lithology_permeability(static_cast<int>(index)),
            model_precision
        );
    }
    permeability_json += "}";

    std::string out = "{";
    bool first = true;
    add_str(out, first, "model_type",
        "causal_land_climate_loss_partition_v1");
    add_str(out, first, "domain", "non_marine_cells");
    add_str(out, first, "execution_order",
        "climate_then_pet_then_loss_partition_then_runoff_then_flow_routing");
    add_str(out, first, "potential_evapotranspiration_model",
        "max_zero_temperature_plus_offset_times_scale_v1");
    add_double(out, first, "pet_temperature_offset_c",
        HYDROLOGIC_PET_TEMPERATURE_OFFSET_C, model_precision);
    add_double(out, first, "pet_scale_mm_y_per_c",
        HYDROLOGIC_PET_SCALE_MM_Y_PER_C, model_precision);
    add_str(out, first, "climate_loss_model",
        "min_precipitation_climate_loss_fraction_times_pet_v1");
    add_double(out, first, "climate_loss_fraction",
        HYDROLOGIC_CLIMATE_LOSS_FRACTION, model_precision);
    add_str(out, first, "infiltration_capacity_model",
        "lithology_sediment_low_relief_frozen_capacity_v1");
    add_raw(out, first, "lithology_permeability", permeability_json);
    add_double(out, first, "minimum_infiltration_capacity_index",
        HYDROLOGIC_MIN_INFILTRATION_CAPACITY, model_precision);
    add_double(out, first, "maximum_infiltration_capacity_index",
        HYDROLOGIC_MAX_INFILTRATION_CAPACITY, model_precision);
    add_str(out, first, "infiltration_share_model",
        "base_share_plus_capacity_share_times_capacity_index_v1");
    add_double(out, first, "infiltration_base_share",
        HYDROLOGIC_INFILTRATION_BASE_SHARE, model_precision);
    add_double(out, first, "infiltration_capacity_share",
        HYDROLOGIC_INFILTRATION_CAPACITY_SHARE, model_precision);
    add_str(out, first, "actual_evapotranspiration_model",
        "climate_loss_minus_infiltration_v1");
    add_str(out, first, "water_balance_equation",
        "precipitation_minus_actual_evapotranspiration_minus_infiltration");
    add_str(out, first, "runoff_equation",
        "max_zero_water_balance");
    add_str(out, first, "marine_cell_treatment",
        "excluded_from_land_budget_with_zero_partition_terms");
    add_bool(out, first, "runoff_computed_before_flow_routing", true);
    add_bool(out, first, "cell_mass_balance_closed", true);
    add_bool(out, first, "physical_time_resolved", false);
    add_str(out, first, "model_limitation",
        "empirical_annual_loss_partition_without_transient_soil_moisture_groundwater_return_flow_or_calibrated_time");
    add_int(out, first, "history_stage_count",
        static_cast<int>(history.size()));
    add_int(out, first, "final_history_stage_id",
        final_stage == nullptr ? -1 : final_stage->id);
    add_int(out, first, "final_land_cell_count",
        final_stage == nullptr ? 0 : final_stage->land_cell_count);
    add_int(out, first, "final_marine_cell_count",
        final_stage == nullptr ? 0 : final_stage->marine_cell_count);
    add_double(out, first, "final_land_precipitation_volume_km3_y",
        final_stage == nullptr ? 0.0 :
            final_stage->land_precipitation_volume_km3_y,
        model_precision);
    add_double(out, first,
        "final_actual_evapotranspiration_volume_km3_y",
        final_stage == nullptr ? 0.0 :
            final_stage->actual_evapotranspiration_volume_km3_y,
        model_precision);
    add_double(out, first, "final_infiltration_volume_km3_y",
        final_stage == nullptr ? 0.0 :
            final_stage->infiltration_volume_km3_y,
        model_precision);
    add_double(out, first, "final_runoff_volume_km3_y",
        final_stage == nullptr ? 0.0 : final_stage->runoff_volume_km3_y,
        model_precision);
    add_double(out, first, "final_mass_balance_residual_km3_y",
        final_stage == nullptr ? 0.0 :
            final_stage->mass_balance_residual_km3_y,
        model_precision);
    add_double(out, first, "final_max_abs_cell_residual_mm_y",
        final_stage == nullptr ? 0.0 :
            final_stage->max_abs_cell_residual_mm_y,
        model_precision);
    out += "}";
    return out;
}

std::string hydrologic_water_budget_history_json(
    const std::vector<HydrologicWaterBudgetStage>& history,
    int precision
) {
    const int value_precision = std::max(10, precision);
    const int volume_precision = std::max(12, precision);
    std::string out = "[";
    bool first_stage = true;
    for (const HydrologicWaterBudgetStage& stage : history) {
        comma(out, first_stage);
        out += "{";
        bool first = true;
        add_int(out, first, "id", stage.id);
        add_int(out, first, "feedback_stage_id", stage.feedback_stage_id);
        add_str(out, first, "stage", stage.stage);
        add_int(out, first, "erosion_iteration", stage.erosion_iteration);
        add_int(out, first, "stabilization_recomputation_index",
            stage.stabilization_recomputation_index);
        add_int(out, first, "cell_count", stage.cell_count);
        add_int(out, first, "land_cell_count", stage.land_cell_count);
        add_int(out, first, "marine_cell_count", stage.marine_cell_count);
        add_double(out, first, "land_precipitation_volume_km3_y",
            stage.land_precipitation_volume_km3_y, volume_precision);
        add_double(out, first,
            "actual_evapotranspiration_volume_km3_y",
            stage.actual_evapotranspiration_volume_km3_y,
            volume_precision);
        add_double(out, first, "infiltration_volume_km3_y",
            stage.infiltration_volume_km3_y, volume_precision);
        add_double(out, first, "runoff_volume_km3_y",
            stage.runoff_volume_km3_y, volume_precision);
        add_double(out, first, "mass_balance_residual_km3_y",
            stage.mass_balance_residual_km3_y, volume_precision);
        add_double(out, first, "max_abs_cell_residual_mm_y",
            stage.max_abs_cell_residual_mm_y, value_precision);
        add_raw(out, first, "cell_ids", int_array_json(stage.cell_ids));
        add_raw(out, first, "is_marine_by_cell",
            int_array_json(stage.is_marine_by_cell));
        add_raw(out, first, "lithology_by_cell",
            int_array_json(stage.lithology_by_cell));
        add_raw(out, first, "cell_area_km2_by_cell",
            double_array_json(stage.cell_area_km2_by_cell, value_precision));
        add_raw(out, first, "elevation_m_by_cell",
            double_array_json(stage.elevation_m_by_cell, value_precision));
        add_raw(out, first, "temperature_c_by_cell",
            double_array_json(stage.temperature_c_by_cell, value_precision));
        add_raw(out, first, "precipitation_mm_y_by_cell",
            double_array_json(stage.precipitation_mm_y_by_cell,
                value_precision));
        add_raw(out, first, "local_relief_m_by_cell",
            double_array_json(stage.local_relief_m_by_cell,
                value_precision));
        add_raw(out, first, "sediment_thickness_m_by_cell",
            double_array_json(stage.sediment_thickness_m_by_cell,
                value_precision));
        add_raw(out, first, "ice_thickness_m_by_cell",
            double_array_json(stage.ice_thickness_m_by_cell,
                value_precision));
        add_raw(out, first,
            "potential_evapotranspiration_mm_y_by_cell",
            double_array_json(
                stage.potential_evapotranspiration_mm_y_by_cell,
                value_precision));
        add_raw(out, first, "infiltration_capacity_index_by_cell",
            double_array_json(stage.infiltration_capacity_index_by_cell,
                value_precision));
        add_raw(out, first,
            "actual_evapotranspiration_mm_y_by_cell",
            double_array_json(
                stage.actual_evapotranspiration_mm_y_by_cell,
                value_precision));
        add_raw(out, first, "infiltration_mm_y_by_cell",
            double_array_json(stage.infiltration_mm_y_by_cell,
                value_precision));
        add_raw(out, first, "water_balance_mm_y_by_cell",
            double_array_json(stage.water_balance_mm_y_by_cell,
                value_precision));
        add_raw(out, first, "runoff_mm_y_by_cell",
            double_array_json(stage.runoff_mm_y_by_cell,
                value_precision));
        add_raw(out, first, "residual_mm_y_by_cell",
            double_array_json(stage.residual_mm_y_by_cell,
                value_precision));
        out += "}";
    }
    out += "]";
    return out;
}

std::string numeric_depression_fill_history_json(
    const std::vector<NumericDepressionFillEvent>& history,
    int precision
) {
    const int surface_precision = std::max(12, precision);
    std::string out = "[";
    bool first_event = true;
    for (const NumericDepressionFillEvent& event : history) {
        comma(out, first_event);
        out += "{";
        bool first = true;
        add_int(out, first, "id", event.id);
        add_int(out, first, "feedback_stage_id", event.feedback_stage_id);
        add_str(out, first, "stage", event.stage);
        add_int(out, first, "erosion_iteration", event.erosion_iteration);
        add_int(out, first, "stabilization_pass", event.stabilization_pass);
        add_str(out, first, "correction_method",
            event.breach_selected ?
                "bounded_mass_conserving_breach_with_local_deposition_v1" :
                "zero_material_temporary_numeric_lake_deferral_v1");
        add_str(out, first, "fill_candidate_model",
            "priority_flood_full_depression_fill_candidate_v1");
        add_str(out, first, "source_depression_policy", "corrected_numeric");
        add_int(out, first, "source_depression_component_id",
            event.source_depression_component_id);
        add_int(out, first, "sink_cell_id", event.sink_cell_id);
        add_str(out, first, "sink_crust_type", CRUST_NAMES[event.sink_crust_type]);
        add_bool(out, first, "sink_is_geologic", event.sink_is_geologic);
        add_double(out, first, "sink_boundary_divergent",
            event.sink_boundary_divergent, precision);
        add_double(out, first, "sink_boundary_convergent",
            event.sink_boundary_convergent, precision);
        add_int(out, first, "cell_count", static_cast<int>(event.cell_ids.size()));
        add_raw(out, first, "cell_ids", int_array_json(event.cell_ids));
        add_raw(out, first, "elevation_before_fill_m_by_cell",
            double_array_json(event.elevation_before_fill_m_by_cell, surface_precision));
        add_raw(out, first, "sediment_thickness_before_correction_m_by_cell",
            double_array_json(
                event.sediment_thickness_before_correction_m_by_cell,
                surface_precision
            ));
        add_raw(out, first, "fill_depth_m_by_cell",
            double_array_json(event.fill_depth_m_by_cell, surface_precision));
        add_raw(out, first, "elevation_after_fill_m_by_cell",
            double_array_json(event.elevation_after_fill_m_by_cell, surface_precision));
        add_double(out, first, "area_km2", event.area_km2, surface_precision);
        add_double(out, first, "fill_volume_km3", event.fill_volume_km3, surface_precision);
        add_double(out, first, "max_fill_depth_m", event.max_fill_depth_m, surface_precision);
        add_bool(out, first, "fill_candidate_applied", false);
        add_bool(out, first, "temporary_numeric_lake_selected",
            event.temporary_numeric_lake_selected);
        add_str(out, first, "breach_diagnostic_model",
            "weighted_graph_excavation_proxy_monotone_lower_outlet_v1");
        add_double(out, first, "breach_gradient_step_m",
            NUMERIC_DEPRESSION_BREACH_GRADIENT_STEP_M, surface_precision);
        add_bool(out, first, "breach_feasible", event.breach_feasible);
        add_int(out, first, "breach_outlet_cell_id", event.breach_outlet_cell_id);
        add_raw(out, first, "breach_path_cell_ids",
            int_array_json(event.breach_path_cell_ids));
        add_raw(out, first, "breach_elevation_before_m_by_cell",
            double_array_json(
                event.breach_elevation_before_m_by_cell,
                surface_precision
            ));
        add_raw(out, first, "breach_target_elevation_m_by_cell",
            double_array_json(event.breach_target_elevation_m_by_cell, surface_precision));
        add_raw(out, first, "breach_excavation_depth_m_by_cell",
            double_array_json(
                event.breach_excavation_depth_m_by_cell,
                surface_precision
            ));
        add_raw(out, first,
            "breach_sediment_thickness_before_excavation_m_by_cell",
            double_array_json(
                event.breach_sediment_thickness_before_excavation_m_by_cell,
                surface_precision
            ));
        add_raw(out, first,
            "breach_alluvium_entrainment_depth_m_by_cell",
            double_array_json(
                event.breach_alluvium_entrainment_depth_m_by_cell,
                surface_precision
            ));
        add_raw(out, first, "breach_bedrock_erosion_depth_m_by_cell",
            double_array_json(
                event.breach_bedrock_erosion_depth_m_by_cell,
                surface_precision
            ));
        add_double(out, first, "breach_path_length_km",
            event.breach_path_length_km, surface_precision);
        add_double(out, first, "breach_excavation_area_km2",
            event.breach_excavation_area_km2, surface_precision);
        add_double(out, first, "breach_excavation_volume_km3",
            event.breach_excavation_volume_km3, surface_precision);
        add_double(out, first, "max_breach_excavation_depth_m",
            event.max_breach_excavation_depth_m, surface_precision);
        add_double(out, first, "breach_to_fill_volume_ratio",
            event.breach_to_fill_volume_ratio, surface_precision);
        add_bool(out, first, "breach_has_lower_adjustment_volume",
            event.breach_has_lower_adjustment_volume);
        add_bool(out, first, "breach_depth_bound_passed",
            event.breach_depth_bound_passed);
        add_bool(out, first, "breach_deposition_capacity_sufficient",
            event.breach_deposition_capacity_sufficient);
        add_bool(out, first, "breach_same_pass_conflict_free",
            event.breach_same_pass_conflict_free);
        add_double(out, first, "breach_deposition_capacity_km3",
            event.breach_deposition_capacity_km3, surface_precision);
        add_int(out, first, "breach_deposition_cell_count",
            static_cast<int>(event.breach_deposition_cell_ids.size()));
        add_raw(out, first, "breach_deposition_cell_ids",
            int_array_json(event.breach_deposition_cell_ids));
        add_raw(out, first, "breach_deposition_depth_m_by_cell",
            double_array_json(
                event.breach_deposition_depth_m_by_cell,
                surface_precision
            ));
        add_double(out, first, "applied_fill_volume_km3",
            event.applied_fill_volume_km3, surface_precision);
        add_double(out, first, "applied_breach_excavation_volume_km3",
            event.applied_breach_excavation_volume_km3, surface_precision);
        add_double(out, first, "applied_breach_deposition_volume_km3",
            event.applied_breach_deposition_volume_km3, surface_precision);
        add_double(out, first, "applied_alluvium_entrainment_volume_km3",
            event.applied_alluvium_entrainment_volume_km3,
            surface_precision);
        add_double(out, first, "applied_bedrock_erosion_volume_km3",
            event.applied_bedrock_erosion_volume_km3, surface_precision);
        add_double(out, first, "correction_mass_balance_residual_km3",
            event.correction_mass_balance_residual_km3, surface_precision);
        add_str(out, first, "lower_adjustment_volume_method",
            event.breach_has_lower_adjustment_volume ? "breach" : "fill");
        add_str(out, first, "selected_correction_method",
            event.breach_selected ?
                "mass_conserving_breach" : "temporary_numeric_lake");
        out += "}";
    }
    out += "]";
    return out;
}

std::string glacial_sediment_transport_model_json(
    const std::vector<GlacialSedimentTransportStage>& history,
    int precision
) {
    int total_transfer_count = 0;
    int total_source_cell_count = 0;
    int total_target_cell_count = 0;
    int total_land_target_transfer_count = 0;
    int total_marine_target_transfer_count = 0;
    double total_production_volume_km3 = 0.0;
    double total_deposition_volume_km3 = 0.0;
    double total_alluvium_entrainment_volume_km3 = 0.0;
    double total_bedrock_erosion_volume_km3 = 0.0;
    double total_mass_balance_residual_km3 = 0.0;
    double total_terrain_volume_change_residual_km3 = 0.0;
    double max_source_production_depth_m = 0.0;
    double max_target_deposition_depth_m = 0.0;
    for (const GlacialSedimentTransportStage& stage : history) {
        total_transfer_count += stage.transfer_count;
        total_source_cell_count += stage.source_cell_count;
        total_target_cell_count += stage.target_cell_count;
        total_land_target_transfer_count +=
            stage.land_target_transfer_count;
        total_marine_target_transfer_count +=
            stage.marine_target_transfer_count;
        total_production_volume_km3 += stage.production_volume_km3;
        total_deposition_volume_km3 += stage.deposition_volume_km3;
        total_alluvium_entrainment_volume_km3 +=
            stage.alluvium_entrainment_volume_km3;
        total_bedrock_erosion_volume_km3 +=
            stage.bedrock_erosion_volume_km3;
        total_mass_balance_residual_km3 +=
            stage.mass_balance_residual_km3;
        total_terrain_volume_change_residual_km3 +=
            stage.terrain_volume_change_residual_km3;
        max_source_production_depth_m = std::max(
            max_source_production_depth_m,
            stage.max_source_production_depth_m
        );
        max_target_deposition_depth_m = std::max(
            max_target_deposition_depth_m,
            stage.max_target_deposition_depth_m
        );
    }
    const int volume_precision = std::max(10, precision);
    const int surface_precision = std::max(8, precision);
    std::string out = "{";
    bool first = true;
    add_str(out, first, "model_type",
        "downhill_area_conserving_glacial_sediment_transport_v2");
    add_str(out, first, "routing_graph",
        "single_steepest_downhill_mesh_neighbor_v1");
    add_str(out, first, "source_state",
        "post_erosion_pre_cryosphere_feedback_cell_state_v1");
    add_str(out, first, "erosion_potential_model",
        "ice_thickness_times_local_slope_proxy_bounded_85m_v1");
    add_double(out, first, "mobile_sediment_fraction",
        GLACIAL_SEDIMENT_MOBILE_FRACTION, surface_precision);
    add_str(out, first, "source_depth_model",
        "glacial_erosion_potential_times_mobile_sediment_fraction");
    add_str(out, first, "source_material_partition_model",
        "available_alluvium_first_then_bedrock_erosion_v1");
    add_str(out, first, "stage_input_snapshot",
        "complete_cell_cryosphere_terrain_and_sediment_inventory_before_transport_v2");
    add_str(out, first, "volume_transfer_model",
        "source_depth_times_source_area_equals_target_depth_times_target_area");
    add_bool(out, first, "mass_conserving", true);
    add_bool(out, first, "finite_sediment_inventory_resolved", true);
    add_bool(out, first, "terrain_elevation_coupled", true);
    add_bool(out, first, "earth_system_recomputed_after_transport", true);
    add_bool(out, first, "physical_time_resolved", false);
    add_bool(out, first, "multi_step_ice_dynamics_resolved", false);
    add_str(out, first, "model_limitation",
        "single_post_erosion_bulk_transfer_without_calibrated_time_multistep_ice_dynamics_or_grain_classes");
    add_int(out, first, "stage_count", static_cast<int>(history.size()));
    add_int(out, first, "total_transfer_count", total_transfer_count);
    add_int(out, first, "total_source_cell_count", total_source_cell_count);
    add_int(out, first, "total_target_cell_count", total_target_cell_count);
    add_int(out, first, "total_land_target_transfer_count",
        total_land_target_transfer_count);
    add_int(out, first, "total_marine_target_transfer_count",
        total_marine_target_transfer_count);
    add_double(out, first, "total_production_volume_km3",
        total_production_volume_km3, volume_precision);
    add_double(out, first, "total_deposition_volume_km3",
        total_deposition_volume_km3, volume_precision);
    add_double(out, first, "total_alluvium_entrainment_volume_km3",
        total_alluvium_entrainment_volume_km3, volume_precision);
    add_double(out, first, "total_bedrock_erosion_volume_km3",
        total_bedrock_erosion_volume_km3, volume_precision);
    add_double(out, first, "total_mass_balance_residual_km3",
        total_mass_balance_residual_km3, volume_precision);
    add_double(out, first, "total_terrain_volume_change_residual_km3",
        total_terrain_volume_change_residual_km3, volume_precision);
    add_double(out, first, "max_source_production_depth_m",
        max_source_production_depth_m, surface_precision);
    add_double(out, first, "max_target_deposition_depth_m",
        max_target_deposition_depth_m, surface_precision);
    out += "}";
    return out;
}

std::string glacial_sediment_transport_history_json(
    const std::vector<GlacialSedimentTransportStage>& history,
    int precision
) {
    const int volume_precision = std::max(10, precision);
    const int surface_precision = std::max(8, precision);
    std::string out = "[";
    bool first_stage = true;
    for (const GlacialSedimentTransportStage& stage : history) {
        comma(out, first_stage);
        out += "{";
        bool first = true;
        add_int(out, first, "id", stage.id);
        add_int(out, first, "feedback_stage_id", stage.feedback_stage_id);
        add_int(out, first, "transfer_count", stage.transfer_count);
        add_int(out, first, "source_cell_count", stage.source_cell_count);
        add_int(out, first, "target_cell_count", stage.target_cell_count);
        add_int(out, first, "land_target_transfer_count",
            stage.land_target_transfer_count);
        add_int(out, first, "marine_target_transfer_count",
            stage.marine_target_transfer_count);
        add_double(out, first, "production_volume_km3",
            stage.production_volume_km3, volume_precision);
        add_double(out, first, "deposition_volume_km3",
            stage.deposition_volume_km3, volume_precision);
        add_double(out, first, "alluvium_entrainment_volume_km3",
            stage.alluvium_entrainment_volume_km3, volume_precision);
        add_double(out, first, "bedrock_erosion_volume_km3",
            stage.bedrock_erosion_volume_km3, volume_precision);
        add_double(out, first, "mass_balance_residual_km3",
            stage.mass_balance_residual_km3, volume_precision);
        add_double(out, first, "terrain_volume_change_residual_km3",
            stage.terrain_volume_change_residual_km3, volume_precision);
        add_double(out, first, "max_source_production_depth_m",
            stage.max_source_production_depth_m, surface_precision);
        add_double(out, first, "max_target_deposition_depth_m",
            stage.max_target_deposition_depth_m, surface_precision);
        add_int(out, first, "input_cell_count",
            static_cast<int>(stage.input_cells.size()));

        std::string input_cells_json = "[";
        bool first_input_cell = true;
        for (const GlacialSedimentTransportInputCell& input_cell :
                stage.input_cells) {
            comma(input_cells_json, first_input_cell);
            input_cells_json += "{";
            bool first_field = true;
            add_int(input_cells_json, first_field, "cell_id",
                input_cell.cell_id);
            add_int(input_cells_json, first_field, "glacier_flow_to_cell_id",
                input_cell.glacier_flow_to_cell_id);
            add_bool(input_cells_json, first_field, "is_water",
                input_cell.is_water);
            add_double(input_cells_json, first_field, "elevation_m",
                input_cell.elevation_m, surface_precision);
            add_double(input_cells_json, first_field, "ice_thickness_m",
                input_cell.ice_thickness_m, surface_precision);
            add_double(input_cells_json, first_field, "glacial_erosion_m",
                input_cell.glacial_erosion_m, surface_precision);
            add_double(input_cells_json, first_field, "sediment_thickness_m",
                input_cell.sediment_thickness_m, surface_precision);
            input_cells_json += "}";
        }
        input_cells_json += "]";
        add_raw(out, first, "input_cells", input_cells_json);

        std::string transfers_json = "[";
        bool first_transfer = true;
        for (const GlacialSedimentTransfer& transfer : stage.transfers) {
            comma(transfers_json, first_transfer);
            transfers_json += "{";
            bool first_field = true;
            add_int(transfers_json, first_field, "id", transfer.id);
            add_int(transfers_json, first_field, "source_cell_id",
                transfer.source_cell_id);
            add_int(transfers_json, first_field, "target_cell_id",
                transfer.target_cell_id);
            add_bool(transfers_json, first_field, "target_is_water",
                transfer.target_is_water);
            add_double(transfers_json, first_field, "source_area_km2",
                transfer.source_area_km2, volume_precision);
            add_double(transfers_json, first_field, "target_area_km2",
                transfer.target_area_km2, volume_precision);
            add_double(transfers_json, first_field, "source_elevation_m",
                transfer.source_elevation_m, surface_precision);
            add_double(transfers_json, first_field, "target_elevation_m",
                transfer.target_elevation_m, surface_precision);
            add_double(transfers_json, first_field, "elevation_drop_m",
                transfer.elevation_drop_m, surface_precision);
            add_double(transfers_json, first_field, "source_ice_thickness_m",
                transfer.source_ice_thickness_m, surface_precision);
            add_double(transfers_json, first_field, "source_glacial_erosion_m",
                transfer.source_glacial_erosion_m, surface_precision);
            add_double(transfers_json, first_field, "source_production_depth_m",
                transfer.source_production_depth_m, surface_precision);
            add_double(transfers_json, first_field, "target_deposition_depth_m",
                transfer.target_deposition_depth_m, surface_precision);
            add_double(transfers_json, first_field, "transfer_volume_km3",
                transfer.transfer_volume_km3, volume_precision);
            add_double(transfers_json, first_field, "mass_balance_residual_km3",
                transfer.mass_balance_residual_km3, volume_precision);
            transfers_json += "}";
        }
        transfers_json += "]";
        add_raw(out, first, "transfers", transfers_json);
        add_raw(out, first, "post_transport_elevation_m_by_cell",
            double_array_json(
                stage.post_transport_elevation_m_by_cell,
                surface_precision
            ));
        out += "}";
    }
    out += "]";
    return out;
}

std::string hillslope_sediment_transport_model_json(
    const Params& params,
    const std::vector<HillslopeSedimentTransportStage>& history
) {
    int total_transport_edge_count = 0;
    int total_source_cell_stage_count = 0;
    int total_target_cell_stage_count = 0;
    int total_land_to_land_edge_count = 0;
    int total_land_to_marine_edge_count = 0;
    double total_production_volume_km3 = 0.0;
    double total_deposition_volume_km3 = 0.0;
    double total_alluvium_entrainment_volume_km3 = 0.0;
    double total_bedrock_erosion_volume_km3 = 0.0;
    double total_mass_balance_residual_km3 = 0.0;
    double max_source_production_depth_m = 0.0;
    double max_target_deposition_depth_m = 0.0;
    double effective_diffusivity_sum = 0.0;
    for (const HillslopeSedimentTransportStage& stage : history) {
        total_transport_edge_count += stage.transport_edge_count;
        total_source_cell_stage_count += stage.source_cell_count;
        total_target_cell_stage_count += stage.target_cell_count;
        total_land_to_land_edge_count += stage.land_to_land_edge_count;
        total_land_to_marine_edge_count += stage.land_to_marine_edge_count;
        total_production_volume_km3 += stage.production_volume_km3;
        total_deposition_volume_km3 += stage.deposition_volume_km3;
        total_alluvium_entrainment_volume_km3 +=
            stage.alluvium_entrainment_volume_km3;
        total_bedrock_erosion_volume_km3 +=
            stage.bedrock_erosion_volume_km3;
        total_mass_balance_residual_km3 += stage.mass_balance_residual_km3;
        max_source_production_depth_m = std::max(
            max_source_production_depth_m,
            stage.max_source_production_depth_m
        );
        max_target_deposition_depth_m = std::max(
            max_target_deposition_depth_m,
            stage.max_target_deposition_depth_m
        );
        effective_diffusivity_sum +=
            stage.mean_effective_diffusivity *
            static_cast<double>(stage.transport_edge_count);
    }
    std::string resistance_json = "{";
    bool first_resistance = true;
    for (std::size_t index = 0; index < LITHOLOGY_NAMES.size(); ++index) {
        add_double(
            resistance_json,
            first_resistance,
            LITHOLOGY_NAMES[index],
            lithology_resistance(static_cast<int>(index)),
            std::max(8, params.float_precision)
        );
    }
    resistance_json += "}";

    std::string out = "{";
    bool first = true;
    add_str(out, first, "model_type",
        "pairwise_lithology_dependent_volume_conserving_hillslope_transport_v2");
    add_str(out, first, "transport_graph",
        "one_directed_transfer_per_eligible_undirected_mesh_edge_v1");
    add_str(out, first, "source_selection",
        "higher_non_marine_cell_to_lower_adjacent_cell");
    add_str(out, first, "effective_diffusivity_model",
        "min_stability_cap_configured_diffusivity_divided_by_source_lithology_resistance");
    add_str(out, first, "source_depth_model",
        "effective_diffusivity_times_elevation_drop_divided_by_source_neighbor_count");
    add_str(out, first, "volume_transfer_model",
        "source_depth_times_source_area_equals_target_depth_times_target_area");
    add_str(out, first, "source_material_partition_model",
        "available_alluvium_first_then_bedrock_erosion_v1");
    add_str(out, first, "erosion_stage_source_partition_order",
        "hillslope_before_fluvial");
    add_double(out, first, "configured_hillslope_diffusivity",
        params.hillslope_diffusion, std::max(8, params.float_precision));
    add_double(out, first, "maximum_effective_diffusivity",
        HILLSLOPE_MAX_EFFECTIVE_DIFFUSIVITY,
        std::max(8, params.float_precision));
    add_raw(out, first, "source_lithology_resistance",
        resistance_json);
    add_bool(out, first, "mass_conserving", true);
    add_bool(out, first, "physical_time_resolved", false);
    add_bool(out, first, "shared_boundary_geometry_resolved", false);
    add_bool(out, first, "regolith_depth_resolved", true);
    add_str(out, first, "model_limitation",
        "procedural_bulk_transport_without_calibrated_time_shared_boundary_flux_or_grain_classes");
    add_str(out, first, "stage_input_snapshot",
        "complete_cell_elevation_water_lake_lithology_and_sediment_inventory_state_before_transport_v2");
    add_int(out, first, "stage_count", static_cast<int>(history.size()));
    add_int(out, first, "total_transport_edge_count",
        total_transport_edge_count);
    add_int(out, first, "total_source_cell_stage_count",
        total_source_cell_stage_count);
    add_int(out, first, "total_target_cell_stage_count",
        total_target_cell_stage_count);
    add_int(out, first, "total_land_to_land_edge_count",
        total_land_to_land_edge_count);
    add_int(out, first, "total_land_to_marine_edge_count",
        total_land_to_marine_edge_count);
    const int volume_precision = std::max(10, params.float_precision);
    add_double(out, first, "total_production_volume_km3",
        total_production_volume_km3, volume_precision);
    add_double(out, first, "total_deposition_volume_km3",
        total_deposition_volume_km3, volume_precision);
    add_double(out, first, "total_alluvium_entrainment_volume_km3",
        total_alluvium_entrainment_volume_km3, volume_precision);
    add_double(out, first, "total_bedrock_erosion_volume_km3",
        total_bedrock_erosion_volume_km3, volume_precision);
    add_double(out, first, "total_mass_balance_residual_km3",
        total_mass_balance_residual_km3, volume_precision);
    add_double(out, first, "max_source_production_depth_m",
        max_source_production_depth_m, std::max(8, params.float_precision));
    add_double(out, first, "max_target_deposition_depth_m",
        max_target_deposition_depth_m, std::max(8, params.float_precision));
    add_double(out, first, "mean_effective_diffusivity",
        total_transport_edge_count > 0 ?
            effective_diffusivity_sum /
                static_cast<double>(total_transport_edge_count) : 0.0,
        std::max(10, params.float_precision));
    out += "}";
    return out;
}

std::string hillslope_sediment_transport_history_json(
    const std::vector<HillslopeSedimentTransportStage>& history,
    int precision
) {
    const int volume_precision = std::max(10, precision);
    const int surface_precision = std::max(8, precision);
    std::string out = "[";
    bool first_stage = true;
    for (const HillslopeSedimentTransportStage& stage : history) {
        comma(out, first_stage);
        out += "{";
        bool first = true;
        add_int(out, first, "id", stage.id);
        add_int(out, first, "feedback_stage_id", stage.feedback_stage_id);
        add_int(out, first, "erosion_iteration", stage.erosion_iteration);
        add_int(out, first, "transport_edge_count",
            stage.transport_edge_count);
        add_int(out, first, "source_cell_count", stage.source_cell_count);
        add_int(out, first, "target_cell_count", stage.target_cell_count);
        add_int(out, first, "land_to_land_edge_count",
            stage.land_to_land_edge_count);
        add_int(out, first, "land_to_marine_edge_count",
            stage.land_to_marine_edge_count);
        add_double(out, first, "production_volume_km3",
            stage.production_volume_km3, volume_precision);
        add_double(out, first, "deposition_volume_km3",
            stage.deposition_volume_km3, volume_precision);
        add_double(out, first, "alluvium_entrainment_volume_km3",
            stage.alluvium_entrainment_volume_km3, volume_precision);
        add_double(out, first, "bedrock_erosion_volume_km3",
            stage.bedrock_erosion_volume_km3, volume_precision);
        add_double(out, first, "mass_balance_residual_km3",
            stage.mass_balance_residual_km3, volume_precision);
        add_double(out, first, "max_source_production_depth_m",
            stage.max_source_production_depth_m, surface_precision);
        add_double(out, first, "max_target_deposition_depth_m",
            stage.max_target_deposition_depth_m, surface_precision);
        add_double(out, first, "mean_effective_diffusivity",
            stage.mean_effective_diffusivity, volume_precision);

        add_int(out, first, "input_cell_count",
            static_cast<int>(stage.input_cells.size()));
        std::string input_cells_json = "[";
        bool first_input_cell = true;
        for (const HillslopeSedimentTransportInputCell& input_cell :
                stage.input_cells) {
            comma(input_cells_json, first_input_cell);
            input_cells_json += "{";
            bool first_field = true;
            add_int(input_cells_json, first_field, "cell_id",
                input_cell.cell_id);
            add_str(input_cells_json, first_field, "lithology",
                LITHOLOGY_NAMES[input_cell.lithology]);
            add_bool(input_cells_json, first_field, "is_water",
                input_cell.is_water);
            add_bool(input_cells_json, first_field, "is_lake",
                input_cell.is_lake);
            add_double(input_cells_json, first_field, "elevation_m",
                input_cell.elevation_m, surface_precision);
            add_double(input_cells_json, first_field, "sediment_thickness_m",
                input_cell.sediment_thickness_m, surface_precision);
            input_cells_json += "}";
        }
        input_cells_json += "]";
        add_raw(out, first, "input_cells", input_cells_json);

        std::string edges_json = "[";
        bool first_edge = true;
        for (const HillslopeSedimentTransportEdge& edge : stage.edges) {
            comma(edges_json, first_edge);
            edges_json += "{";
            bool first_field = true;
            add_int(edges_json, first_field, "id", edge.id);
            add_int(edges_json, first_field, "mesh_edge_cell_a_id",
                edge.mesh_edge_cell_a_id);
            add_int(edges_json, first_field, "mesh_edge_cell_b_id",
                edge.mesh_edge_cell_b_id);
            add_int(edges_json, first_field, "source_cell_id",
                edge.source_cell_id);
            add_int(edges_json, first_field, "target_cell_id",
                edge.target_cell_id);
            add_str(edges_json, first_field, "source_lithology",
                LITHOLOGY_NAMES[edge.source_lithology]);
            add_int(edges_json, first_field, "source_neighbor_count",
                edge.source_neighbor_count);
            add_bool(edges_json, first_field, "source_is_water", false);
            add_bool(edges_json, first_field, "target_is_water",
                edge.target_is_water);
            add_bool(edges_json, first_field, "target_is_lake",
                edge.target_is_lake);
            add_double(edges_json, first_field, "source_area_km2",
                edge.source_area_km2, volume_precision);
            add_double(edges_json, first_field, "target_area_km2",
                edge.target_area_km2, volume_precision);
            add_double(edges_json, first_field, "source_elevation_m",
                edge.source_elevation_m, surface_precision);
            add_double(edges_json, first_field, "target_elevation_m",
                edge.target_elevation_m, surface_precision);
            add_double(edges_json, first_field, "elevation_drop_m",
                edge.elevation_drop_m, surface_precision);
            add_double(edges_json, first_field,
                "source_lithology_resistance",
                edge.source_lithology_resistance, surface_precision);
            add_double(edges_json, first_field, "effective_diffusivity",
                edge.effective_diffusivity, volume_precision);
            add_double(edges_json, first_field, "source_production_depth_m",
                edge.source_production_depth_m, surface_precision);
            add_double(edges_json, first_field, "target_deposition_depth_m",
                edge.target_deposition_depth_m, surface_precision);
            add_double(edges_json, first_field, "transfer_volume_km3",
                edge.transfer_volume_km3, volume_precision);
            add_double(edges_json, first_field, "mass_balance_residual_km3",
                edge.mass_balance_residual_km3, volume_precision);
            edges_json += "}";
        }
        edges_json += "]";
        add_raw(out, first, "edges", edges_json);
        out += "}";
    }
    out += "]";
    return out;
}

std::string fluvial_sediment_routing_model_json(
    const std::vector<FluvialSedimentRoutingStage>& history,
    int precision
) {
    double total_source_volume_km3 = 0.0;
    double total_throughput_volume_km3 = 0.0;
    double total_capacity_deposition_volume_km3 = 0.0;
    double total_depression_fill_deposition_volume_km3 = 0.0;
    double total_lake_trap_deposition_volume_km3 = 0.0;
    double total_terminal_land_deposition_volume_km3 = 0.0;
    double total_marine_deposition_volume_km3 = 0.0;
    double total_terminal_export_volume_km3 = 0.0;
    double total_mass_balance_residual_km3 = 0.0;
    double total_alluvium_entrainment_volume_km3 = 0.0;
    double total_bedrock_erosion_volume_km3 = 0.0;
    int total_active_cell_step_count = 0;
    int total_routed_edge_count = 0;
    int total_terminal_allocation_count = 0;
    for (const FluvialSedimentRoutingStage& stage : history) {
        total_source_volume_km3 += stage.local_source_volume_km3;
        total_throughput_volume_km3 += stage.routed_throughput_volume_km3;
        total_capacity_deposition_volume_km3 +=
            stage.capacity_deposition_volume_km3;
        total_depression_fill_deposition_volume_km3 +=
            stage.depression_fill_deposition_volume_km3;
        total_lake_trap_deposition_volume_km3 +=
            stage.lake_trap_deposition_volume_km3;
        total_terminal_land_deposition_volume_km3 +=
            stage.terminal_land_deposition_volume_km3;
        total_marine_deposition_volume_km3 +=
            stage.marine_deposition_volume_km3;
        total_terminal_export_volume_km3 +=
            stage.terminal_export_volume_km3;
        total_mass_balance_residual_km3 += stage.mass_balance_residual_km3;
        total_alluvium_entrainment_volume_km3 +=
            stage.alluvium_entrainment_volume_km3;
        total_bedrock_erosion_volume_km3 +=
            stage.bedrock_erosion_volume_km3;
        total_active_cell_step_count += stage.active_cell_step_count;
        total_routed_edge_count += stage.routed_edge_count;
        total_terminal_allocation_count += stage.terminal_allocation_count;
    }
    std::string out = "{";
    bool first = true;
    add_str(out, first, "model_type",
        "topological_capacity_limited_fluvial_sediment_routing_v1");
    add_str(out, first, "material_unit", "km3");
    add_str(out, first, "routing_graph",
        "erosion_stage_acyclic_hydrologic_flow_to_v1");
    add_str(out, first, "transport_capacity_model",
        "bounded_dimensionless_flow_slope_runoff_river_capacity_fraction_v1");
    add_str(out, first, "depression_deposition_model",
        "explicit_spill_elevation_accommodation_then_capacity_and_lake_trap_v1");
    add_str(out, first, "land_terminal_model",
        "depression_footprint_proportional_accommodation_then_area_weighted_aggradation_v1");
    add_str(out, first, "marine_terminal_model",
        "water_body_class_deposition_then_unresolved_deep_marine_export_v1");
    add_str(out, first, "cell_depth_conversion",
        "volume_km3_times_1000_divided_by_cell_area_km2");
    add_str(out, first, "source_material_partition_model",
        "available_alluvium_after_hillslope_then_bedrock_erosion_v1");
    add_bool(out, first, "source_material_partition_is_coupled_external_state",
        true);
    add_bool(out, first, "mass_conserving", true);
    add_bool(out, first, "depression_fill_deposition_is_cross_cut", true);
    add_bool(out, first, "grain_size_resolved", false);
    add_bool(out, first, "physical_time_resolved", false);
    add_bool(out, first, "subcell_channel_geometry_resolved", false);
    add_str(out, first, "model_limitation",
        "dimensionless_capacity_proxy_without_grain_size_calibrated_time_or_subcell_channels");
    add_double(out, first, "minimum_transport_capacity_fraction",
        FLUVIAL_SEDIMENT_MIN_TRANSPORT_CAPACITY_FRACTION, precision);
    add_double(out, first, "maximum_transport_capacity_fraction",
        FLUVIAL_SEDIMENT_MAX_TRANSPORT_CAPACITY_FRACTION, precision);
    add_double(out, first, "overflowing_lake_trap_fraction",
        FLUVIAL_SEDIMENT_LAKE_TRAP_FRACTION, precision);
    add_double(out, first, "closed_lake_trap_fraction",
        FLUVIAL_SEDIMENT_CLOSED_LAKE_TRAP_FRACTION, precision);
    add_double(out, first, "open_ocean_deposition_fraction",
        FLUVIAL_SEDIMENT_OPEN_OCEAN_DEPOSITION_FRACTION, precision);
    add_double(out, first, "continental_shelf_deposition_fraction",
        FLUVIAL_SEDIMENT_SHELF_DEPOSITION_FRACTION, precision);
    add_double(out, first, "inland_sea_deposition_fraction",
        FLUVIAL_SEDIMENT_INLAND_SEA_DEPOSITION_FRACTION, precision);
    add_int(out, first, "stage_count", static_cast<int>(history.size()));
    add_int(out, first, "total_active_cell_step_count",
        total_active_cell_step_count);
    add_int(out, first, "total_routed_edge_count", total_routed_edge_count);
    add_int(out, first, "total_terminal_allocation_count",
        total_terminal_allocation_count);
    const int volume_precision = std::max(10, precision);
    add_double(out, first, "total_local_source_volume_km3",
        total_source_volume_km3, volume_precision);
    add_double(out, first, "total_routed_throughput_volume_km3",
        total_throughput_volume_km3, volume_precision);
    add_double(out, first, "total_capacity_deposition_volume_km3",
        total_capacity_deposition_volume_km3, volume_precision);
    add_double(out, first, "total_depression_fill_deposition_volume_km3",
        total_depression_fill_deposition_volume_km3, volume_precision);
    add_double(out, first, "total_lake_trap_deposition_volume_km3",
        total_lake_trap_deposition_volume_km3, volume_precision);
    add_double(out, first, "total_terminal_land_deposition_volume_km3",
        total_terminal_land_deposition_volume_km3, volume_precision);
    add_double(out, first, "total_marine_deposition_volume_km3",
        total_marine_deposition_volume_km3, volume_precision);
    add_double(out, first, "total_terminal_export_volume_km3",
        total_terminal_export_volume_km3, volume_precision);
    add_double(out, first, "total_alluvium_entrainment_volume_km3",
        total_alluvium_entrainment_volume_km3, volume_precision);
    add_double(out, first, "total_bedrock_erosion_volume_km3",
        total_bedrock_erosion_volume_km3, volume_precision);
    add_double(out, first, "total_deposition_volume_km3",
        total_source_volume_km3 - total_terminal_export_volume_km3,
        volume_precision);
    add_double(out, first, "total_mass_balance_residual_km3",
        total_mass_balance_residual_km3, volume_precision);
    out += "}";
    return out;
}

std::string fluvial_sediment_routing_history_json(
    const std::vector<FluvialSedimentRoutingStage>& history,
    int precision
) {
    const int volume_precision = std::max(10, precision);
    const int surface_precision = std::max(8, precision);
    std::string out = "[";
    bool first_stage = true;
    for (const FluvialSedimentRoutingStage& stage : history) {
        comma(out, first_stage);
        out += "{";
        bool first = true;
        add_int(out, first, "id", stage.id);
        add_int(out, first, "feedback_stage_id", stage.feedback_stage_id);
        add_int(out, first, "erosion_iteration", stage.erosion_iteration);
        add_int(out, first, "active_cell_step_count",
            stage.active_cell_step_count);
        add_int(out, first, "routed_edge_count", stage.routed_edge_count);
        add_int(out, first, "land_terminal_count", stage.land_terminal_count);
        add_int(out, first, "marine_terminal_count", stage.marine_terminal_count);
        add_int(out, first, "terminal_allocation_count",
            stage.terminal_allocation_count);
        add_double(out, first, "accumulation_scale",
            stage.accumulation_scale, surface_precision);
        add_double(out, first, "local_source_volume_km3",
            stage.local_source_volume_km3, volume_precision);
        add_double(out, first, "routed_throughput_volume_km3",
            stage.routed_throughput_volume_km3, volume_precision);
        add_double(out, first, "capacity_deposition_volume_km3",
            stage.capacity_deposition_volume_km3, volume_precision);
        add_double(out, first, "depression_fill_deposition_volume_km3",
            stage.depression_fill_deposition_volume_km3, volume_precision);
        add_double(out, first, "lake_trap_deposition_volume_km3",
            stage.lake_trap_deposition_volume_km3, volume_precision);
        add_double(out, first, "terminal_land_deposition_volume_km3",
            stage.terminal_land_deposition_volume_km3, volume_precision);
        add_double(out, first, "marine_deposition_volume_km3",
            stage.marine_deposition_volume_km3, volume_precision);
        add_double(out, first, "terminal_export_volume_km3",
            stage.terminal_export_volume_km3, volume_precision);
        add_double(out, first, "alluvium_entrainment_volume_km3",
            stage.alluvium_entrainment_volume_km3, volume_precision);
        add_double(out, first, "bedrock_erosion_volume_km3",
            stage.bedrock_erosion_volume_km3, volume_precision);
        add_double(out, first, "total_deposition_volume_km3",
            stage.local_source_volume_km3 - stage.terminal_export_volume_km3,
            volume_precision);
        add_double(out, first, "mass_balance_residual_km3",
            stage.mass_balance_residual_km3, volume_precision);

        std::string steps_json = "[";
        bool first_step = true;
        for (const FluvialSedimentRoutingCellStep& step : stage.cell_steps) {
            comma(steps_json, first_step);
            steps_json += "{";
            bool first_field = true;
            add_int(steps_json, first_field, "cell_id", step.cell_id);
            add_int(steps_json, first_field, "flow_to_cell_id",
                step.flow_to_cell_id);
            add_int(steps_json, first_field, "depression_component_id",
                step.depression_component_id);
            add_int(steps_json, first_field, "depression_sink_cell_id",
                step.depression_sink_cell_id);
            add_str(steps_json, first_field, "water_body_type",
                WATER_BODY_NAMES[step.water_body]);
            add_bool(steps_json, first_field, "is_water", step.is_water);
            add_bool(steps_json, first_field, "is_river", step.is_river);
            add_bool(steps_json, first_field, "is_lake", step.is_lake);
            add_bool(steps_json, first_field, "lake_overflows",
                step.lake_overflows);
            add_bool(steps_json, first_field, "is_land_terminal",
                step.is_land_terminal);
            add_bool(steps_json, first_field, "is_marine_terminal",
                step.is_marine_terminal);
            add_double(steps_json, first_field, "cell_area_km2",
                step.cell_area_km2, volume_precision);
            add_double(steps_json, first_field, "flow_accumulation",
                step.flow_accumulation, surface_precision);
            add_double(steps_json, first_field, "runoff_mm_y",
                step.runoff_mm_y, surface_precision);
            add_double(steps_json, first_field, "hydrologic_flow_slope",
                step.hydrologic_flow_slope, 12);
            add_double(steps_json, first_field, "routing_base_elevation_m",
                step.routing_base_elevation_m, surface_precision);
            add_double(steps_json, first_field, "spill_elevation_m",
                step.spill_elevation_m, surface_precision);
            add_double(steps_json, first_field, "local_source_volume_km3",
                step.local_source_volume_km3, volume_precision);
            add_double(steps_json, first_field, "incoming_volume_km3",
                step.incoming_volume_km3, volume_precision);
            add_double(steps_json, first_field, "available_volume_km3",
                step.available_volume_km3, volume_precision);
            add_double(steps_json, first_field, "transport_capacity_fraction",
                step.transport_capacity_fraction, surface_precision);
            add_double(steps_json, first_field,
                "depression_accommodation_volume_km3",
                step.depression_accommodation_volume_km3, volume_precision);
            add_double(steps_json, first_field,
                "capacity_deposition_volume_km3",
                step.capacity_deposition_volume_km3, volume_precision);
            add_double(steps_json, first_field,
                "depression_fill_deposition_volume_km3",
                step.depression_fill_deposition_volume_km3,
                volume_precision);
            add_double(steps_json, first_field,
                "lake_trap_deposition_volume_km3",
                step.lake_trap_deposition_volume_km3, volume_precision);
            add_double(steps_json, first_field, "marine_deposition_volume_km3",
                step.marine_deposition_volume_km3, volume_precision);
            add_double(steps_json, first_field, "routed_outgoing_volume_km3",
                step.routed_outgoing_volume_km3, volume_precision);
            add_double(steps_json, first_field,
                "terminal_land_storage_volume_km3",
                step.terminal_land_storage_volume_km3, volume_precision);
            add_double(steps_json, first_field, "terminal_export_volume_km3",
                step.terminal_export_volume_km3, volume_precision);
            add_double(steps_json, first_field, "local_mass_balance_residual_km3",
                step.local_mass_balance_residual_km3, volume_precision);
            steps_json += "}";
        }
        steps_json += "]";
        add_raw(out, first, "cell_steps", steps_json);

        std::string allocations_json = "[";
        bool first_allocation = true;
        for (
            const FluvialSedimentTerminalAllocation& allocation :
                stage.terminal_allocations
        ) {
            comma(allocations_json, first_allocation);
            allocations_json += "{";
            bool first_field = true;
            add_int(allocations_json, first_field, "sink_cell_id",
                allocation.sink_cell_id);
            add_int(allocations_json, first_field, "target_cell_id",
                allocation.target_cell_id);
            add_int(allocations_json, first_field, "depression_component_id",
                allocation.depression_component_id);
            add_double(allocations_json, first_field, "target_area_km2",
                allocation.target_area_km2, volume_precision);
            add_double(allocations_json, first_field,
                "routing_base_elevation_m",
                allocation.routing_base_elevation_m, surface_precision);
            add_double(allocations_json, first_field, "spill_elevation_m",
                allocation.spill_elevation_m, surface_precision);
            add_double(allocations_json, first_field,
                "prior_local_deposition_volume_km3",
                allocation.prior_local_deposition_volume_km3,
                volume_precision);
            add_double(allocations_json, first_field,
                "accommodation_before_allocation_km3",
                allocation.accommodation_before_allocation_km3,
                volume_precision);
            add_double(allocations_json, first_field,
                "accommodation_deposition_volume_km3",
                allocation.accommodation_deposition_volume_km3,
                volume_precision);
            add_double(allocations_json, first_field,
                "excess_aggradation_volume_km3",
                allocation.excess_aggradation_volume_km3,
                volume_precision);
            add_double(allocations_json, first_field,
                "total_deposition_volume_km3",
                allocation.total_deposition_volume_km3,
                volume_precision);
            allocations_json += "}";
        }
        allocations_json += "]";
        add_raw(out, first, "terminal_allocations", allocations_json);
        out += "}";
    }
    out += "]";
    return out;
}

std::string sediment_inventory_model_json(
    const std::vector<Cell>& cells,
    const std::vector<EarthSystemFeedbackStep>& feedback_history,
    const std::vector<NumericDepressionFillEvent>& numeric_history,
    const std::vector<HillslopeSedimentTransportStage>& hillslope_history,
    const std::vector<FluvialSedimentRoutingStage>& fluvial_history,
    const std::vector<GlacialSedimentTransportStage>& glacial_history,
    int precision
) {
    double hillslope_gross_volume_km3 = 0.0;
    double hillslope_deposition_volume_km3 = 0.0;
    double hillslope_alluvium_volume_km3 = 0.0;
    double hillslope_bedrock_volume_km3 = 0.0;
    for (const HillslopeSedimentTransportStage& stage : hillslope_history) {
        hillslope_gross_volume_km3 += stage.production_volume_km3;
        hillslope_deposition_volume_km3 += stage.deposition_volume_km3;
        hillslope_alluvium_volume_km3 +=
            stage.alluvium_entrainment_volume_km3;
        hillslope_bedrock_volume_km3 += stage.bedrock_erosion_volume_km3;
    }

    double fluvial_gross_volume_km3 = 0.0;
    double fluvial_deposition_volume_km3 = 0.0;
    double fluvial_export_volume_km3 = 0.0;
    double fluvial_alluvium_volume_km3 = 0.0;
    double fluvial_bedrock_volume_km3 = 0.0;
    for (const FluvialSedimentRoutingStage& stage : fluvial_history) {
        fluvial_gross_volume_km3 += stage.local_source_volume_km3;
        fluvial_deposition_volume_km3 +=
            stage.local_source_volume_km3 -
            stage.terminal_export_volume_km3;
        fluvial_export_volume_km3 += stage.terminal_export_volume_km3;
        fluvial_alluvium_volume_km3 +=
            stage.alluvium_entrainment_volume_km3;
        fluvial_bedrock_volume_km3 += stage.bedrock_erosion_volume_km3;
    }

    double glacial_gross_volume_km3 = 0.0;
    double glacial_deposition_volume_km3 = 0.0;
    double glacial_alluvium_volume_km3 = 0.0;
    double glacial_bedrock_volume_km3 = 0.0;
    for (const GlacialSedimentTransportStage& stage : glacial_history) {
        glacial_gross_volume_km3 += stage.production_volume_km3;
        glacial_deposition_volume_km3 += stage.deposition_volume_km3;
        glacial_alluvium_volume_km3 +=
            stage.alluvium_entrainment_volume_km3;
        glacial_bedrock_volume_km3 += stage.bedrock_erosion_volume_km3;
    }

    double numeric_gross_volume_km3 = 0.0;
    double numeric_deposition_volume_km3 = 0.0;
    double numeric_alluvium_volume_km3 = 0.0;
    double numeric_bedrock_volume_km3 = 0.0;
    for (const NumericDepressionFillEvent& event : numeric_history) {
        numeric_gross_volume_km3 +=
            event.applied_breach_excavation_volume_km3;
        numeric_deposition_volume_km3 +=
            event.applied_breach_deposition_volume_km3;
        numeric_alluvium_volume_km3 +=
            event.applied_alluvium_entrainment_volume_km3;
        numeric_bedrock_volume_km3 +=
            event.applied_bedrock_erosion_volume_km3;
    }

    double final_inventory_volume_km3 = 0.0;
    double cell_alluvium_volume_km3 = 0.0;
    double cell_bedrock_volume_km3 = 0.0;
    for (const Cell& cell : cells) {
        const double area_km2 = std::max(0.0, cell.area_km2);
        final_inventory_volume_km3 +=
            cell.sediment_thickness_m * area_km2 / 1000.0;
        cell_alluvium_volume_km3 +=
            cell.sediment_alluvium_entrainment_m * area_km2 / 1000.0;
        cell_bedrock_volume_km3 +=
            cell.sediment_bedrock_erosion_m * area_km2 / 1000.0;
    }

    const double gross_volume_km3 =
        hillslope_gross_volume_km3 + fluvial_gross_volume_km3 +
        glacial_gross_volume_km3 + numeric_gross_volume_km3;
    const double deposition_volume_km3 =
        hillslope_deposition_volume_km3 + fluvial_deposition_volume_km3 +
        glacial_deposition_volume_km3 + numeric_deposition_volume_km3;
    const double alluvium_volume_km3 =
        hillslope_alluvium_volume_km3 + fluvial_alluvium_volume_km3 +
        glacial_alluvium_volume_km3 + numeric_alluvium_volume_km3;
    const double bedrock_volume_km3 =
        hillslope_bedrock_volume_km3 + fluvial_bedrock_volume_km3 +
        glacial_bedrock_volume_km3 + numeric_bedrock_volume_km3;
    const int volume_precision = std::max(10, precision);

    std::string out = "{";
    bool first = true;
    add_str(out, first, "model_type",
        "finite_alluvium_bedrock_sediment_inventory_v1");
    add_str(out, first, "initial_mobile_sediment_inventory",
        "zero_depth_all_cells_v1");
    add_str(out, first, "source_partition_model",
        "available_alluvium_first_then_bedrock_erosion_v1");
    add_str(out, first, "erosion_stage_source_partition_order",
        "hillslope_then_fluvial");
    add_bool(out, first, "same_stage_deposition_available_for_entrainment",
        false);
    add_bool(out, first, "mass_conserving", true);
    add_bool(out, first, "physical_time_resolved", false);
    add_str(out, first, "model_limitation",
        "bulk_inventory_without_grain_classes_calibrated_time_shared_boundary_flux_or_subcell_channels");
    add_int(out, first, "stage_count", static_cast<int>(feedback_history.size()));
    add_double(out, first, "gross_mobilization_volume_km3",
        gross_volume_km3, volume_precision);
    add_double(out, first, "deposition_volume_km3",
        deposition_volume_km3, volume_precision);
    add_double(out, first, "terminal_export_volume_km3",
        fluvial_export_volume_km3, volume_precision);
    add_double(out, first, "alluvium_entrainment_volume_km3",
        alluvium_volume_km3, volume_precision);
    add_double(out, first, "bedrock_erosion_volume_km3",
        bedrock_volume_km3, volume_precision);
    add_double(out, first, "final_mobile_sediment_inventory_volume_km3",
        final_inventory_volume_km3, volume_precision);
    add_double(out, first, "gross_throughput_mass_balance_residual_km3",
        std::abs(gross_volume_km3 - deposition_volume_km3 -
            fluvial_export_volume_km3), volume_precision);
    add_double(out, first, "source_partition_residual_km3",
        std::abs(gross_volume_km3 - alluvium_volume_km3 -
            bedrock_volume_km3), volume_precision);
    add_double(out, first, "inventory_mass_balance_residual_km3",
        std::abs(bedrock_volume_km3 - final_inventory_volume_km3 -
            fluvial_export_volume_km3), volume_precision);
    add_double(out, first, "cell_alluvium_entrainment_volume_km3",
        cell_alluvium_volume_km3, volume_precision);
    add_double(out, first, "cell_bedrock_erosion_volume_km3",
        cell_bedrock_volume_km3, volume_precision);
    add_double(out, first, "cell_source_partition_residual_km3",
        std::abs(gross_volume_km3 - cell_alluvium_volume_km3 -
            cell_bedrock_volume_km3), volume_precision);

    std::string process_json = "{";
    bool first_process = true;
    const auto add_process = [&](
        const char* name,
        double gross,
        double alluvium,
        double bedrock
    ) {
        std::string process = "{";
        bool first_field = true;
        add_double(process, first_field, "gross_mobilization_volume_km3",
            gross, volume_precision);
        add_double(process, first_field, "alluvium_entrainment_volume_km3",
            alluvium, volume_precision);
        add_double(process, first_field, "bedrock_erosion_volume_km3",
            bedrock, volume_precision);
        add_double(process, first_field, "source_partition_residual_km3",
            std::abs(gross - alluvium - bedrock), volume_precision);
        process += "}";
        add_raw(process_json, first_process, name, process);
    };
    add_process("hillslope", hillslope_gross_volume_km3,
        hillslope_alluvium_volume_km3, hillslope_bedrock_volume_km3);
    add_process("fluvial", fluvial_gross_volume_km3,
        fluvial_alluvium_volume_km3, fluvial_bedrock_volume_km3);
    add_process("glacial", glacial_gross_volume_km3,
        glacial_alluvium_volume_km3, glacial_bedrock_volume_km3);
    add_process("numeric_breach", numeric_gross_volume_km3,
        numeric_alluvium_volume_km3, numeric_bedrock_volume_km3);
    process_json += "}";
    add_raw(out, first, "process_source_partition", process_json);
    out += "}";
    return out;
}

std::string simulation_clock_json(
    const Params& params,
    const std::vector<EarthSystemFeedbackStep>& feedback_history
) {
    int feedback_recompute_count = 0;
    int cryosphere_coupling_stage_count = 0;
    int hydrologic_water_budget_recompute_count = 0;
    for (const EarthSystemFeedbackStep& step : feedback_history) {
        feedback_recompute_count +=
            (step.erosion_applied || step.cryosphere_applied) &&
            step.sea_level_recomputed && step.climate_recomputed &&
            step.hydrologic_water_budget_recomputed &&
            step.hydrology_recomputed ? 1 : 0;
        cryosphere_coupling_stage_count += step.cryosphere_applied ? 1 : 0;
        hydrologic_water_budget_recompute_count +=
            step.hydrologic_water_budget_recompute_count;
    }
    std::string out = "{";
    bool first = true;
    add_str(out, first, "clock_type", "coupled_geodynamic_stage_clock_v11");
    add_str(out, first, "time_unit", "model_step");
    add_bool(out, first, "physical_time_resolved", false);
    add_str(out, first, "clock_limitation", "ordered_process_stages_without_calibrated_physical_duration");
    add_str(out, first, "iteration_process_order",
        "{plate_motion->crust_transport->crust_evolution->tectonic_stream_erosion->hillslope_sediment_transport->fluvial_sediment_routing->finite_alluvium_bedrock_inventory_update->(sea_level->climate->causal_water_budget->hydrology->numeric_depression_correction)*until_stable}*configured_erosion_iterations->cryosphere_state->glacial_sediment_transport->finite_alluvium_bedrock_inventory_update->(sea_level->climate->causal_water_budget->hydrology->numeric_depression_correction)*until_stable");
    add_double(out, first, "geological_age_ga", params.geological_age_ga, params.float_precision);
    add_int(out, first, "configured_erosion_iteration_count", params.erosion_iterations);
    add_int(out, first, "configured_cryosphere_coupling_stage_count", 1);
    add_int(out, first, "cryosphere_coupling_stage_count",
        cryosphere_coupling_stage_count);
    add_int(out, first, "feedback_recompute_count", feedback_recompute_count);
    add_int(out, first, "hydrologic_water_budget_recompute_count",
        hydrologic_water_budget_recompute_count);
    add_int(out, first, "stage_count", static_cast<int>(feedback_history.size()));
    add_int(out, first, "initial_stage_id", feedback_history.empty() ? -1 : feedback_history.front().id);
    add_int(out, first, "current_stage_id", feedback_history.empty() ? -1 : feedback_history.back().id);
    add_int(out, first, "final_stage_id", feedback_history.empty() ? -1 : feedback_history.back().id);
    add_int(out, first, "final_cryosphere_stage_id",
        cryosphere_coupling_stage_count == 1 && !feedback_history.empty() ?
            feedback_history.back().id : -1);
    out += "}";
    return out;
}

std::string earth_system_feedback_history_json(
    const std::vector<EarthSystemFeedbackStep>& feedback_history,
    int precision
) {
    std::string out = "[";
    bool first_step = true;
    for (const EarthSystemFeedbackStep& step : feedback_history) {
        comma(out, first_step);
        out += "{";
        bool first = true;
        add_int(out, first, "id", step.id);
        add_str(out, first, "stage", step.stage);
        add_int(out, first, "erosion_iteration", step.erosion_iteration);
        add_bool(out, first, "sea_level_recomputed", step.sea_level_recomputed);
        add_bool(out, first, "climate_recomputed", step.climate_recomputed);
        add_bool(out, first, "hydrologic_water_budget_recomputed",
            step.hydrologic_water_budget_recomputed);
        add_bool(out, first, "hydrology_recomputed", step.hydrology_recomputed);
        add_bool(out, first, "erosion_applied", step.erosion_applied);
        add_bool(out, first, "cryosphere_applied", step.cryosphere_applied);
        add_bool(out, first, "plate_motion_applied", step.plate_motion_applied);
        add_bool(out, first, "crust_transport_applied", step.crust_transport_applied);
        add_bool(out, first, "crust_evolution_applied", step.crust_evolution_applied);
        add_int(out, first, "sea_level_recompute_count", step.sea_level_recompute_count);
        add_int(out, first, "climate_recompute_count", step.climate_recompute_count);
        add_int(out, first, "hydrologic_water_budget_recompute_count",
            step.hydrologic_water_budget_recompute_count);
        add_int(out, first, "hydrology_recompute_count", step.hydrology_recompute_count);
        add_int(out, first, "numeric_depression_fill_pass_count",
            step.numeric_depression_fill_pass_count);
        add_int(out, first, "numeric_depression_fill_event_count",
            step.numeric_depression_fill_event_count);
        add_int(out, first, "numeric_depression_fill_cell_application_count",
            step.numeric_depression_fill_cell_application_count);
        add_int(out, first, "numeric_depression_filled_unique_cell_count",
            step.numeric_depression_filled_unique_cell_count);
        add_int(out, first, "numeric_depression_correction_event_count",
            step.numeric_depression_correction_event_count);
        add_int(out, first, "numeric_depression_breach_selected_event_count",
            step.numeric_depression_breach_selected_event_count);
        add_int(out, first,
            "numeric_depression_breach_excavation_cell_application_count",
            step.numeric_depression_breach_excavation_cell_application_count);
        add_int(out, first,
            "numeric_depression_breach_deposition_cell_application_count",
            step.numeric_depression_breach_deposition_cell_application_count);
        add_int(out, first, "numeric_depression_temporary_lake_event_count",
            step.numeric_depression_temporary_lake_event_count);
        add_int(out, first,
            "numeric_depression_temporary_lake_cell_application_count",
            step.numeric_depression_temporary_lake_cell_application_count);
        add_int(out, first,
            "numeric_depression_temporary_lake_unique_cell_count",
            step.numeric_depression_temporary_lake_unique_cell_count);
        add_int(out, first, "fluvial_sediment_active_cell_step_count",
            step.fluvial_sediment_active_cell_step_count);
        add_int(out, first, "fluvial_sediment_routed_edge_count",
            step.fluvial_sediment_routed_edge_count);
        add_int(out, first, "fluvial_sediment_land_terminal_count",
            step.fluvial_sediment_land_terminal_count);
        add_int(out, first, "fluvial_sediment_marine_terminal_count",
            step.fluvial_sediment_marine_terminal_count);
        add_int(out, first, "fluvial_sediment_terminal_allocation_count",
            step.fluvial_sediment_terminal_allocation_count);
        add_int(out, first, "hillslope_sediment_transport_edge_count",
            step.hillslope_sediment_transport_edge_count);
        add_int(out, first, "hillslope_sediment_source_cell_count",
            step.hillslope_sediment_source_cell_count);
        add_int(out, first, "hillslope_sediment_target_cell_count",
            step.hillslope_sediment_target_cell_count);
        add_int(out, first, "hillslope_sediment_land_to_land_edge_count",
            step.hillslope_sediment_land_to_land_edge_count);
        add_int(out, first, "hillslope_sediment_land_to_marine_edge_count",
            step.hillslope_sediment_land_to_marine_edge_count);
        add_int(out, first, "glacial_sediment_transfer_count",
            step.glacial_sediment_transfer_count);
        add_int(out, first, "glacial_sediment_source_cell_count",
            step.glacial_sediment_source_cell_count);
        add_int(out, first, "glacial_sediment_target_cell_count",
            step.glacial_sediment_target_cell_count);
        add_int(out, first, "glacial_sediment_land_target_transfer_count",
            step.glacial_sediment_land_target_transfer_count);
        add_int(out, first, "glacial_sediment_marine_target_transfer_count",
            step.glacial_sediment_marine_target_transfer_count);
        add_int(out, first, "plate_motion_history_id", step.plate_motion_history_id);
        add_int(out, first, "cell_count", step.cell_count);
        add_int(out, first, "land_cell_count", step.land_cell_count);
        add_int(out, first, "water_cell_count", step.water_cell_count);
        add_int(out, first, "river_cell_count", step.river_cell_count);
        add_double(out, first, "sea_level_adjustment_m", step.sea_level_adjustment_m, precision);
        add_double(out, first, "numeric_depression_fill_area_km2",
            step.numeric_depression_fill_area_km2, precision);
        add_double(out, first, "numeric_depression_fill_volume_km3",
            step.numeric_depression_fill_volume_km3, precision);
        add_double(out, first, "max_numeric_depression_fill_depth_m",
            step.max_numeric_depression_fill_depth_m, precision);
        add_double(out, first,
            "numeric_depression_breach_excavation_volume_km3",
            step.numeric_depression_breach_excavation_volume_km3, precision);
        add_double(out, first,
            "numeric_depression_breach_deposition_volume_km3",
            step.numeric_depression_breach_deposition_volume_km3, precision);
        add_double(out, first,
            "numeric_depression_correction_mass_balance_residual_km3",
            step.numeric_depression_correction_mass_balance_residual_km3,
            precision);
        add_double(out, first,
            "numeric_depression_temporary_lake_candidate_area_km2",
            step.numeric_depression_temporary_lake_candidate_area_km2,
            precision);
        add_double(out, first,
            "numeric_depression_temporary_lake_candidate_volume_km3",
            step.numeric_depression_temporary_lake_candidate_volume_km3,
            precision);
        add_double(out, first, "max_numeric_depression_temporary_lake_depth_m",
            step.max_numeric_depression_temporary_lake_depth_m, precision);
        add_double(out, first, "fluvial_sediment_local_source_volume_km3",
            step.fluvial_sediment_local_source_volume_km3,
            std::max(10, precision));
        add_double(out, first, "fluvial_sediment_routed_throughput_volume_km3",
            step.fluvial_sediment_routed_throughput_volume_km3,
            std::max(10, precision));
        add_double(out, first, "fluvial_sediment_capacity_deposition_volume_km3",
            step.fluvial_sediment_capacity_deposition_volume_km3,
            std::max(10, precision));
        add_double(out, first,
            "fluvial_sediment_depression_fill_deposition_volume_km3",
            step.fluvial_sediment_depression_fill_deposition_volume_km3,
            std::max(10, precision));
        add_double(out, first, "fluvial_sediment_lake_trap_deposition_volume_km3",
            step.fluvial_sediment_lake_trap_deposition_volume_km3,
            std::max(10, precision));
        add_double(out, first,
            "fluvial_sediment_terminal_land_deposition_volume_km3",
            step.fluvial_sediment_terminal_land_deposition_volume_km3,
            std::max(10, precision));
        add_double(out, first, "fluvial_sediment_marine_deposition_volume_km3",
            step.fluvial_sediment_marine_deposition_volume_km3,
            std::max(10, precision));
        add_double(out, first, "fluvial_sediment_terminal_export_volume_km3",
            step.fluvial_sediment_terminal_export_volume_km3,
            std::max(10, precision));
        add_double(out, first, "fluvial_sediment_mass_balance_residual_km3",
            step.fluvial_sediment_mass_balance_residual_km3,
            std::max(10, precision));
        add_double(out, first, "hillslope_sediment_production_volume_km3",
            step.hillslope_sediment_production_volume_km3,
            std::max(10, precision));
        add_double(out, first, "hillslope_sediment_deposition_volume_km3",
            step.hillslope_sediment_deposition_volume_km3,
            std::max(10, precision));
        add_double(out, first, "hillslope_sediment_mass_balance_residual_km3",
            step.hillslope_sediment_mass_balance_residual_km3,
            std::max(10, precision));
        add_double(out, first,
            "max_hillslope_sediment_source_production_depth_m",
            step.max_hillslope_sediment_source_production_depth_m,
            std::max(8, precision));
        add_double(out, first,
            "max_hillslope_sediment_target_deposition_depth_m",
            step.max_hillslope_sediment_target_deposition_depth_m,
            std::max(8, precision));
        add_double(out, first, "mean_hillslope_effective_diffusivity",
            step.mean_hillslope_effective_diffusivity,
            std::max(8, precision));
        add_double(out, first, "glacial_sediment_production_volume_km3",
            step.glacial_sediment_production_volume_km3,
            std::max(10, precision));
        add_double(out, first, "glacial_sediment_deposition_volume_km3",
            step.glacial_sediment_deposition_volume_km3,
            std::max(10, precision));
        add_double(out, first, "glacial_sediment_mass_balance_residual_km3",
            step.glacial_sediment_mass_balance_residual_km3,
            std::max(10, precision));
        add_double(out, first,
            "glacial_sediment_terrain_volume_change_residual_km3",
            step.glacial_sediment_terrain_volume_change_residual_km3,
            std::max(10, precision));
        add_double(out, first,
            "max_glacial_sediment_source_production_depth_m",
            step.max_glacial_sediment_source_production_depth_m,
            std::max(8, precision));
        add_double(out, first,
            "max_glacial_sediment_target_deposition_depth_m",
            step.max_glacial_sediment_target_deposition_depth_m,
            std::max(8, precision));
        add_double(out, first,
            "sediment_alluvium_entrainment_volume_km3",
            step.sediment_alluvium_entrainment_volume_km3,
            std::max(10, precision));
        add_double(out, first, "sediment_bedrock_erosion_volume_km3",
            step.sediment_bedrock_erosion_volume_km3,
            std::max(10, precision));
        add_double(out, first, "sediment_inventory_volume_km3",
            step.sediment_inventory_volume_km3,
            std::max(10, precision));
        add_double(out, first, "sediment_source_partition_residual_km3",
            step.sediment_source_partition_residual_km3,
            std::max(10, precision));
        add_double(out, first,
            "sediment_inventory_mass_balance_residual_km3",
            step.sediment_inventory_mass_balance_residual_km3,
            std::max(10, precision));
        add_double(out, first, "surface_area_km2", step.surface_area_km2, precision);
        add_double(out, first, "ocean_area_km2", step.ocean_area_km2, precision);
        add_double(out, first, "ocean_volume_km3", step.ocean_volume_km3, precision);
        add_double(out, first, "ocean_fraction", step.ocean_fraction, precision);
        add_double(out, first, "mean_elevation_m", step.mean_elevation_m, precision);
        add_double(out, first, "mean_land_elevation_m", step.mean_land_elevation_m, precision);
        add_double(out, first, "min_elevation_m", step.min_elevation_m, precision);
        add_double(out, first, "max_elevation_m", step.max_elevation_m, precision);
        add_double(out, first, "mean_temperature_c", step.mean_temperature_c, precision);
        add_double(out, first, "mean_precipitation_mm_y", step.mean_precipitation_mm_y, precision);
        add_double(out, first, "mean_runoff_mm_y", step.mean_runoff_mm_y, precision);
        add_double(out, first,
            "hydrologic_land_precipitation_volume_km3_y",
            step.hydrologic_land_precipitation_volume_km3_y,
            std::max(10, precision));
        add_double(out, first,
            "hydrologic_actual_evapotranspiration_volume_km3_y",
            step.hydrologic_actual_evapotranspiration_volume_km3_y,
            std::max(10, precision));
        add_double(out, first, "hydrologic_infiltration_volume_km3_y",
            step.hydrologic_infiltration_volume_km3_y,
            std::max(10, precision));
        add_double(out, first, "hydrologic_runoff_volume_km3_y",
            step.hydrologic_runoff_volume_km3_y,
            std::max(10, precision));
        add_double(out, first,
            "hydrologic_water_budget_residual_km3_y",
            step.hydrologic_water_budget_residual_km3_y,
            std::max(12, precision));
        add_double(out, first,
            "max_abs_hydrologic_water_budget_cell_residual_mm_y",
            step.max_abs_hydrologic_water_budget_cell_residual_mm_y,
            std::max(12, precision));
        add_double(out, first, "mean_erosion_rate_m_per_step", step.mean_erosion_rate_m_per_step, precision);
        add_double(out, first, "mean_sediment_thickness_m", step.mean_sediment_thickness_m, precision);
        add_double(out, first, "mean_cumulative_sediment_production_m",
            step.mean_cumulative_sediment_production_m, precision);
        add_double(out, first, "mean_cumulative_sediment_deposition_m",
            step.mean_cumulative_sediment_deposition_m, precision);
        add_double(out, first, "mean_cumulative_sediment_export_m",
            step.mean_cumulative_sediment_export_m, precision);
        add_double(out, first, "cumulative_sediment_production_volume_km3",
            step.cumulative_sediment_production_volume_km3, precision);
        add_double(out, first, "cumulative_sediment_deposition_volume_km3",
            step.cumulative_sediment_deposition_volume_km3, precision);
        add_double(out, first, "cumulative_sediment_export_volume_km3",
            step.cumulative_sediment_export_volume_km3, precision);
        add_double(out, first, "mean_abs_elevation_change_m_from_previous_stage",
            step.mean_abs_elevation_change_m_from_previous_stage, precision);
        add_double(out, first, "mean_abs_temperature_change_c_from_previous_stage",
            step.mean_abs_temperature_change_c_from_previous_stage, precision);
        add_double(out, first, "mean_abs_precipitation_change_mm_y_from_previous_stage",
            step.mean_abs_precipitation_change_mm_y_from_previous_stage, precision);
        add_double(out, first, "mean_abs_runoff_change_mm_y_from_previous_stage",
            step.mean_abs_runoff_change_mm_y_from_previous_stage, precision);
        out += "}";
    }
    out += "]";
    return out;
}

std::string plate_kinematic_model_json(
    const Params& params,
    const std::vector<PlateMotionStep>& history,
    const std::vector<Cell>& cells
) {
    int initial_continental_crust_cell_count = 0;
    int initial_crust_cell_count = 0;
    int initial_continental_crust_component_count = 0;
    int initial_continental_crust_largest_component_cell_count = 0;
    int initial_continental_crust_boundary_edge_count = 0;
    std::vector<int> initial_continental_mask;
    if (!history.empty()) {
        initial_crust_cell_count = static_cast<int>(history.front().crust_type_by_cell.size());
        initial_continental_mask.assign(history.front().crust_type_by_cell.size(), 0);
        for (int crust_type : history.front().crust_type_by_cell) {
            if (crust_type == 1 || crust_type == 4 || crust_type == 5 ||
                crust_type == 6 || crust_type == 7) {
                initial_continental_crust_cell_count++;
            }
        }
        for (std::size_t index = 0; index < history.front().crust_type_by_cell.size(); ++index) {
            const int crust_type = history.front().crust_type_by_cell[index];
            initial_continental_mask[index] =
                crust_type == 1 || crust_type == 4 || crust_type == 5 ||
                crust_type == 6 || crust_type == 7;
        }
    }
    if (initial_continental_mask.size() == cells.size()) {
        std::vector<int> visited(cells.size(), 0);
        for (std::size_t index = 0; index < cells.size(); ++index) {
            if (initial_continental_mask[index] == 0 || visited[index] != 0) {
                continue;
            }
            int component_size = 0;
            std::queue<int> pending;
            pending.push(static_cast<int>(index));
            visited[index] = 1;
            while (!pending.empty()) {
                const int cell_id = pending.front();
                pending.pop();
                component_size++;
                for (int neighbor_id : cells[static_cast<std::size_t>(cell_id)].neighbors) {
                    if (initial_continental_mask[static_cast<std::size_t>(neighbor_id)] != 0 &&
                        visited[static_cast<std::size_t>(neighbor_id)] == 0) {
                        visited[static_cast<std::size_t>(neighbor_id)] = 1;
                        pending.push(neighbor_id);
                    }
                }
            }
            initial_continental_crust_component_count++;
            initial_continental_crust_largest_component_cell_count = std::max(
                initial_continental_crust_largest_component_cell_count,
                component_size
            );
        }
        for (std::size_t index = 0; index < cells.size(); ++index) {
            for (int neighbor_id : cells[index].neighbors) {
                if (static_cast<int>(index) < neighbor_id &&
                    initial_continental_mask[index] !=
                        initial_continental_mask[static_cast<std::size_t>(neighbor_id)]) {
                    initial_continental_crust_boundary_edge_count++;
                }
            }
        }
    }
    const double initial_continental_crust_fraction = initial_crust_cell_count > 0
        ? static_cast<double>(initial_continental_crust_cell_count) /
            static_cast<double>(initial_crust_cell_count)
        : 0.0;
    std::string out = "{";
    bool first = true;
    add_str(out, first, "model_type", "rotating_voronoi_plate_domains_v1");
    add_str(out, first, "time_unit", "model_step");
    add_bool(out, first, "physical_time_resolved", false);
    add_double(out, first, "motion_scale_deg_per_step", params.plate_motion_scale_deg_per_step, std::max(6, params.float_precision));
    add_double(out, first, "effective_oceanic_crust_aging_ma_per_step",
        params.oceanic_crust_aging_ma_per_step, std::max(6, params.float_precision));
    add_int(out, first, "configured_motion_step_count", params.erosion_iterations);
    add_int(out, first, "history_step_count", static_cast<int>(history.size()));
    add_str(out, first, "domain_assignment", "nearest_rotated_plate_center_on_fixed_spherical_mesh");
    add_str(out, first, "initial_crust_partition_model",
        "ranked_graph_coherent_plate_biased_continental_mask_v2");
    add_double(out, first, "continental_crust_fraction_target",
        params.continental_crust_fraction_target, std::max(6, params.float_precision));
    add_int(out, first, "initial_continental_crust_cell_count",
        initial_continental_crust_cell_count);
    add_double(out, first, "initial_continental_crust_fraction",
        initial_continental_crust_fraction, std::max(6, params.float_precision));
    add_int(out, first, "initial_continental_crust_component_count",
        initial_continental_crust_component_count);
    add_int(out, first, "initial_continental_crust_largest_component_cell_count",
        initial_continental_crust_largest_component_cell_count);
    add_int(out, first, "initial_continental_crust_boundary_edge_count",
        initial_continental_crust_boundary_edge_count);
    add_int(out, first, "initial_crust_coherence_smoothing_steps",
        INITIAL_CRUST_COHERENCE_SMOOTHING_STEPS);
    add_double(out, first, "initial_crust_coherence_self_weight",
        INITIAL_CRUST_COHERENCE_SELF_WEIGHT, std::max(6, params.float_precision));
    add_str(out, first, "transitional_crust_margin_model", "one_hop_graph_margin_v1");
    add_str(out, first, "secondary_relief_noise_model", "independently_graph_smoothed_signed_noise_v2");
    add_int(out, first, "secondary_relief_smoothing_steps", SECONDARY_RELIEF_SMOOTHING_STEPS);
    add_double(out, first, "secondary_relief_self_weight",
        SECONDARY_RELIEF_SELF_WEIGHT, std::max(6, params.float_precision));
    add_str(out, first, "initial_relief_model", "causal_isostasy_quadratic_convergence_relief_v2");
    add_double(out, first, "continental_isostatic_freeboard_m",
        CONTINENTAL_ISOSTATIC_FREEBOARD_M, std::max(6, params.float_precision));
    add_double(out, first, "convergence_relief_exponent", 2.0, std::max(6, params.float_precision));
    add_double(out, first, "continental_orogen_uplift_scale_m",
        CONTINENTAL_OROGEN_UPLIFT_SCALE_M, std::max(6, params.float_precision));
    add_double(out, first, "oceanic_trench_subsidence_scale_m",
        OCEANIC_TRENCH_SUBSIDENCE_SCALE_M, std::max(6, params.float_precision));
    add_double(out, first, "volcanic_arc_trench_subsidence_scale_m",
        VOLCANIC_ARC_TRENCH_SUBSIDENCE_SCALE_M, std::max(6, params.float_precision));
    add_double(out, first, "volcanic_arc_uplift_scale_m",
        VOLCANIC_ARC_UPLIFT_SCALE_M, std::max(6, params.float_precision));
    add_bool(out, first, "sea_level_inventory_separate_from_crust_partition", true);
    add_str(out, first, "crust_memory_model", "plate_attached_semi_lagrangian_backtrace_v0");
    add_str(out, first, "crust_transport_model", "inverse_rotation_nearest_previous_plate_cell_v0");
    add_bool(out, first, "crust_advection_resolved", true);
    add_bool(out, first, "mass_conserving_crust_transport", false);
    add_str(out, first, "crust_transport_limitation", "nearest_source_remap_can_reuse_or_omit_source_cells_at_moving_boundaries");
    add_str(out, first, "model_limitation", "kinematic_domains_with_nonconservative_semi_lagrangian_crust_transport_and_uncalibrated_duration");
    out += "}";
    return out;
}

std::string sea_level_model_json(
    const Params& params,
    const std::vector<Cell>& cells
) {
    const int cell_count = static_cast<int>(cells.size());
    const int target_ocean_cell_count = static_cast<int>(std::llround(
        clamp(params.ocean_fraction_target, 0.0, 0.98) * static_cast<double>(cell_count)
    ));
    int ocean_cell_count = 0;
    double surface_area_km2 = 0.0;
    double ocean_area_km2 = 0.0;
    double ocean_volume_km3 = 0.0;
    int below_sea_level_land_cell_count = 0;
    double below_sea_level_land_area_km2 = 0.0;
    for (const Cell& cell : cells) {
        const double area_km2 = std::max(0.0, cell.area_km2);
        surface_area_km2 += area_km2;
        ocean_cell_count += cell.is_water ? 1 : 0;
        ocean_area_km2 += cell.is_water ? area_km2 : 0.0;
        ocean_volume_km3 += cell.is_water ?
            std::max(0.0, cell.water_depth_m) * area_km2 / 1000.0 : 0.0;
        if (!cell.is_water && cell.elevation_m < 0.0) {
            below_sea_level_land_cell_count++;
            below_sea_level_land_area_km2 += area_km2;
        }
    }
    const double target_ocean_area_km2 =
        clamp(params.ocean_fraction_target, 0.0, 0.98) * surface_area_km2;

    int connected_ocean_component_count = 0;
    std::vector<bool> visited(cells.size(), false);
    for (int i = 0; i < cell_count; ++i) {
        if (!cells[i].is_water || visited[static_cast<std::size_t>(i)]) {
            continue;
        }
        connected_ocean_component_count++;
        std::queue<int> queue;
        queue.push(i);
        visited[static_cast<std::size_t>(i)] = true;
        while (!queue.empty()) {
            const int current = queue.front();
            queue.pop();
            for (int neighbor_id : cells[current].neighbors) {
                if (
                    neighbor_id >= 0 && neighbor_id < cell_count &&
                    cells[neighbor_id].is_water &&
                    !visited[static_cast<std::size_t>(neighbor_id)]
                ) {
                    visited[static_cast<std::size_t>(neighbor_id)] = true;
                    queue.push(neighbor_id);
                }
            }
        }
    }

    std::string out = "{";
    bool first = true;
    add_str(out, first, "model_type", "volume_constrained_connectivity_ocean_flood_v3");
    add_str(out, first, "selection_rule",
        "solve_largest_connected_ocean_cell_column_volume_across_elevation_intervals");
    add_str(out, first, "area_basis", "native_cell_area_km2");
    add_str(out, first, "volume_basis", "sum_native_cell_area_times_water_depth");
    add_double(
        out,
        first,
        "ocean_fraction_target",
        params.ocean_fraction_target,
        std::numeric_limits<double>::max_digits10
    );
    add_double(out, first, "surface_area_km2", surface_area_km2,
        std::numeric_limits<double>::max_digits10);
    add_double(out, first, "target_ocean_area_km2", target_ocean_area_km2,
        std::numeric_limits<double>::max_digits10);
    add_double(out, first, "selected_ocean_area_km2", ocean_area_km2,
        std::numeric_limits<double>::max_digits10);
    add_double(out, first, "ocean_water_inventory_km3", params.ocean_water_inventory_km3,
        std::numeric_limits<double>::max_digits10);
    add_double(out, first, "selected_ocean_volume_km3", ocean_volume_km3,
        std::numeric_limits<double>::max_digits10);
    add_double(out, first, "ocean_water_inventory_error_km3",
        std::abs(ocean_volume_km3 - params.ocean_water_inventory_km3),
        std::numeric_limits<double>::max_digits10);
    add_double(out, first, "ocean_water_inventory_error_fraction",
        params.ocean_water_inventory_km3 > 0.0 ?
            std::abs(ocean_volume_km3 - params.ocean_water_inventory_km3) /
                params.ocean_water_inventory_km3 :
            (ocean_volume_km3 > 0.0 ? 1.0 : 0.0),
        std::numeric_limits<double>::max_digits10);
    add_int(out, first, "target_ocean_cell_count", target_ocean_cell_count);
    add_int(out, first, "selected_ocean_cell_count", ocean_cell_count);
    add_double(out, first, "selected_ocean_fraction",
        surface_area_km2 > 0.0 ? ocean_area_km2 / surface_area_km2 : 0.0,
        std::numeric_limits<double>::max_digits10);
    add_double(out, first, "selected_ocean_cell_fraction",
        cell_count > 0 ? static_cast<double>(ocean_cell_count) / static_cast<double>(cell_count) : 0.0,
        std::numeric_limits<double>::max_digits10);
    add_int(out, first, "ocean_area_target_error_cell_count", std::abs(ocean_cell_count - target_ocean_cell_count));
    add_double(out, first, "ocean_area_target_error_fraction",
        surface_area_km2 > 0.0 ? std::abs(ocean_area_km2 - target_ocean_area_km2) / surface_area_km2 : 0.0,
        std::numeric_limits<double>::max_digits10);
    add_double(out, first, "ocean_area_target_error_km2",
        std::abs(ocean_area_km2 - target_ocean_area_km2),
        std::numeric_limits<double>::max_digits10);
    add_double(out, first, "ocean_area_target_error_cell_fraction",
        cell_count > 0 ? std::abs(ocean_cell_count - target_ocean_cell_count) / static_cast<double>(cell_count) : 0.0,
        std::numeric_limits<double>::max_digits10);
    add_int(out, first, "connected_ocean_component_count", connected_ocean_component_count);
    add_int(out, first, "below_sea_level_land_cell_count", below_sea_level_land_cell_count);
    add_double(out, first, "below_sea_level_land_area_km2",
        below_sea_level_land_area_km2, params.float_precision);
    add_bool(out, first, "ocean_connectivity_enforced", true);
    add_bool(out, first, "disconnected_below_sea_level_cells_remain_land", true);
    add_bool(out, first, "sea_level_recomputed_each_erosion_stage", true);
    add_str(out, first, "model_limitation",
        "cell_column_volume_without_subcell_bathymetry_straits_or_exact_coast_polygons");
    out += "}";
    return out;
}

std::string plate_motion_history_json(
    const std::vector<PlateMotionStep>& history,
    int precision
) {
    const int history_precision = std::max(6, precision);
    std::string out = "[";
    bool first_step = true;
    for (const PlateMotionStep& step : history) {
        comma(out, first_step);
        out += "{";
        bool first = true;
        add_int(out, first, "id", step.id);
        add_str(out, first, "stage", step.stage);
        add_int(out, first, "erosion_iteration", step.erosion_iteration);
        add_int(out, first, "cell_count", step.cell_count);
        add_int(out, first, "plate_count", step.plate_count);
        add_int(out, first, "reassigned_cell_count", step.reassigned_cell_count);
        add_double(out, first, "reassigned_cell_fraction", step.reassigned_cell_fraction, history_precision);
        add_int(out, first, "plate_boundary_cell_count", step.plate_boundary_cell_count);
        add_int(out, first, "plate_boundary_edge_count", step.plate_boundary_edge_count);
        add_int(out, first, "accreted_terrane_cell_count", step.accreted_terrane_cell_count);
        add_int(out, first, "crust_source_remap_cell_count", step.crust_source_remap_cell_count);
        add_int(out, first, "unique_crust_source_cell_count", step.unique_crust_source_cell_count);
        add_int(out, first, "crust_source_reuse_count", step.crust_source_reuse_count);
        add_int(out, first, "aged_oceanic_cell_count", step.aged_oceanic_cell_count);
        add_int(out, first, "rejuvenated_oceanic_cell_count", step.rejuvenated_oceanic_cell_count);
        add_int(out, first, "subducted_oceanic_cell_count", step.subducted_oceanic_cell_count);
        add_double(out, first, "mean_plate_rotation_deg", step.mean_plate_rotation_deg, history_precision);
        add_double(out, first, "max_plate_rotation_deg", step.max_plate_rotation_deg, history_precision);
        add_double(out, first, "mean_crust_transport_distance_km", step.mean_crust_transport_distance_km, history_precision);
        add_double(out, first, "max_crust_transport_distance_km", step.max_crust_transport_distance_km, history_precision);
        add_double(out, first, "mean_abs_crust_age_change_ma", step.mean_abs_crust_age_change_ma, history_precision);
        add_double(out, first, "mean_abs_crust_thickness_change_km", step.mean_abs_crust_thickness_change_km, history_precision);
        add_double(out, first, "mean_abs_crust_density_change", step.mean_abs_crust_density_change, history_precision);
        add_double(out, first, "mean_abs_crust_age_transport_change_ma", step.mean_abs_crust_age_transport_change_ma, history_precision);
        add_double(out, first, "mean_abs_crust_thickness_transport_change_km", step.mean_abs_crust_thickness_transport_change_km, history_precision);
        add_double(out, first, "mean_abs_crust_density_transport_change", step.mean_abs_crust_density_transport_change, history_precision);
        add_double(out, first, "mean_abs_crust_age_process_change_ma", step.mean_abs_crust_age_process_change_ma, history_precision);
        add_double(out, first, "mean_abs_crust_thickness_process_change_km", step.mean_abs_crust_thickness_process_change_km, history_precision);
        add_double(out, first, "mean_abs_crust_density_process_change", step.mean_abs_crust_density_process_change, history_precision);
        add_double(out, first, "mean_tectonic_elevation_change_m", step.mean_tectonic_elevation_change_m, history_precision);
        add_double(out, first, "mean_abs_tectonic_elevation_change_m", step.mean_abs_tectonic_elevation_change_m, history_precision);
        add_double(out, first, "max_abs_tectonic_elevation_change_m", step.max_abs_tectonic_elevation_change_m, history_precision);
        add_raw(out, first, "cell_plate_ids", int_array_json(step.cell_plate_ids));
        add_raw(out, first, "crust_source_cell_ids", int_array_json(step.crust_source_cell_ids));
        add_raw(out, first, "crust_type_by_cell", int_array_json(step.crust_type_by_cell));
        add_raw(out, first, "lithology_by_cell", int_array_json(step.lithology_by_cell));
        add_raw(out, first, "crust_transport_distance_km_by_cell",
            double_array_json(step.crust_transport_distance_km_by_cell, history_precision));
        add_raw(out, first, "crust_age_change_ma_by_cell", double_array_json(step.crust_age_change_ma_by_cell, history_precision));
        add_raw(out, first, "crust_thickness_change_km_by_cell", double_array_json(step.crust_thickness_change_km_by_cell, history_precision));
        add_raw(out, first, "crust_density_change_by_cell", double_array_json(step.crust_density_change_by_cell, history_precision));
        add_raw(out, first, "crust_age_transport_change_ma_by_cell",
            double_array_json(step.crust_age_transport_change_ma_by_cell, history_precision));
        add_raw(out, first, "crust_thickness_transport_change_km_by_cell",
            double_array_json(step.crust_thickness_transport_change_km_by_cell, history_precision));
        add_raw(out, first, "crust_density_transport_change_by_cell",
            double_array_json(step.crust_density_transport_change_by_cell, history_precision));
        add_raw(out, first, "crust_age_process_change_ma_by_cell",
            double_array_json(step.crust_age_process_change_ma_by_cell, history_precision));
        add_raw(out, first, "crust_thickness_process_change_km_by_cell",
            double_array_json(step.crust_thickness_process_change_km_by_cell, history_precision));
        add_raw(out, first, "crust_density_process_change_by_cell",
            double_array_json(step.crust_density_process_change_by_cell, history_precision));
        add_raw(out, first, "tectonic_elevation_change_m_by_cell", double_array_json(step.tectonic_elevation_change_m_by_cell, history_precision));
        add_raw(out, first, "aged_oceanic_cell_ids", int_array_json(step.aged_oceanic_cell_ids));
        add_raw(out, first, "rejuvenated_oceanic_cell_ids", int_array_json(step.rejuvenated_oceanic_cell_ids));
        add_raw(out, first, "subducted_oceanic_cell_ids", int_array_json(step.subducted_oceanic_cell_ids));
        std::string plate_snapshots = "[";
        bool first_plate = true;
        for (const PlateKinematicSnapshot& plate : step.plates) {
            comma(plate_snapshots, first_plate);
            plate_snapshots += "{";
            bool first_snapshot_field = true;
            add_int(plate_snapshots, first_snapshot_field, "plate_id", plate.plate_id);
            add_raw(plate_snapshots, first_snapshot_field, "center", vec3_json(plate.center, history_precision));
            add_double(plate_snapshots, first_snapshot_field, "step_rotation_deg", plate.step_rotation_deg, history_precision);
            add_double(plate_snapshots, first_snapshot_field, "cumulative_rotation_deg", plate.cumulative_rotation_deg, history_precision);
            add_int(plate_snapshots, first_snapshot_field, "cell_count", plate.cell_count);
            add_double(plate_snapshots, first_snapshot_field, "area_km2", plate.area_km2, history_precision);
            plate_snapshots += "}";
        }
        plate_snapshots += "]";
        add_raw(out, first, "plates", plate_snapshots);
        out += "}";
    }
    out += "]";
    return out;
}

std::string calibration_checks_json(const std::vector<CalibrationCheck>& checks, int precision) {
    std::string out = "[";
    bool first_check = true;
    for (const CalibrationCheck& check : checks) {
        comma(out, first_check);
        out += "{";
        bool first = true;
        add_int(out, first, "id", check.id);
        add_str(out, first, "dataset", CALIBRATION_DATASET_NAMES[check.dataset]);
        add_str(out, first, "layer", CALIBRATION_LAYER_NAMES[check.layer]);
        add_str(out, first, "metric", CALIBRATION_METRIC_NAMES[check.metric]);
        add_bool(out, first, "passed", check.passed);
        add_double(out, first, "value", check.value, precision);
        add_double(out, first, "target_min", check.target_min, precision);
        add_double(out, first, "target_max", check.target_max, precision);
        add_double(out, first, "score", check.score, precision);
        out += "}";
    }
    out += "]";
    return out;
}

std::string borders_json(const std::vector<BorderSegment>& borders, int precision) {
    std::string out = "[";
    bool first_border = true;
    for (const BorderSegment& border : borders) {
        comma(out, first_border);
        out += "{";
        bool first = true;
        add_int(out, first, "id", border.id);
        add_int(out, first, "region_a", border.region_a);
        add_int(out, first, "region_b", border.region_b);
        add_int(out, first, "cell_a", border.cell_a);
        add_int(out, first, "cell_b", border.cell_b);
        add_str(out, first, "type", BORDER_TYPE_NAMES[border.type]);
        add_double(out, first, "length_km", border.length_km, precision);
        add_double(out, first, "barrier_score", border.barrier_score, precision);
        out += "}";
    }
    out += "]";
    return out;
}

}  // namespace

std::string generate_world_json(const Params& params) {
    validate_params(params);
    configure_threads(params);
    std::vector<Cell> cells = build_mesh(params);
    if (params.plate_count >= static_cast<int>(cells.size())) {
        throw std::runtime_error("plate_count must be smaller than generated mesh cell count");
    }
    std::vector<Plate> plates = generate_plates(params);
    const std::vector<int> seeds = choose_plate_seeds(params, static_cast<int>(cells.size()));
    std::vector<Vec3> plate_centers;
    plate_centers.reserve(plates.size());
    for (std::size_t index = 0; index < plates.size(); ++index) {
        const Vec3 center = cells[static_cast<std::size_t>(seeds[index])].p;
        plates[index].initial_center = center;
        plates[index].center = center;
        plate_centers.push_back(center);
    }
    assign_plates(plate_centers, cells);
    classify_boundaries(params, plates, cells);
    derive_crust_and_topography(params, plates, cells);
    std::vector<PlateMotionStep> plate_motion_history;
    plate_motion_history.push_back(summarize_plate_motion_step(
        cells,
        plates,
        0,
        -1,
        "initial_plate_domains",
        {},
        std::vector<double>(plates.size(), 0.0),
        CrustMotionDiagnostics{},
        std::vector<double>(cells.size(), 0.0),
        std::vector<double>(cells.size(), 0.0),
        std::vector<double>(cells.size(), 0.0),
        std::vector<double>(cells.size(), 0.0)
    ));
    std::vector<NumericDepressionFillEvent> numeric_depression_fill_history;
    std::vector<HydrologicWaterBudgetStage> hydrologic_water_budget_history;
    const HydrologyStabilizationResult initial_stabilization =
        stabilize_numeric_depressions(
            params,
            cells,
            0,
            "initial_climate_hydrology",
            -1,
            numeric_depression_fill_history,
            hydrologic_water_budget_history
        );
    std::vector<EarthSystemFeedbackStep> feedback_history;
    std::vector<FluvialSedimentRoutingStage> sediment_routing_history;
    std::vector<HillslopeSedimentTransportStage> hillslope_transport_history;
    std::vector<GlacialSedimentTransportStage> glacial_transport_history;
    feedback_history.push_back(summarize_feedback_step(
        cells,
        0,
        "initial_climate_hydrology",
        -1,
        initial_stabilization,
        nullptr,
        nullptr,
        nullptr,
        false,
        false,
        false,
        false,
        false,
        0,
        nullptr
    ));
    erode(
        params,
        plates,
        cells,
        feedback_history,
        plate_motion_history,
        numeric_depression_fill_history,
        hydrologic_water_budget_history,
        sediment_routing_history,
        hillslope_transport_history
    );
    const FeedbackReference pre_cryosphere_reference =
        capture_feedback_reference(cells);
    derive_cryosphere_state(params, cells);
    glacial_transport_history.push_back(transport_glacial_sediment(
        0,
        static_cast<int>(feedback_history.size()),
        cells
    ));
    const HydrologyStabilizationResult cryosphere_stabilization =
        stabilize_numeric_depressions(
            params,
            cells,
            static_cast<int>(feedback_history.size()),
            "cryosphere_coupling",
            -1,
            numeric_depression_fill_history,
            hydrologic_water_budget_history
        );
    derive_cryosphere_state(params, cells);
    feedback_history.push_back(summarize_feedback_step(
        cells,
        static_cast<int>(feedback_history.size()),
        "cryosphere_coupling",
        -1,
        cryosphere_stabilization,
        nullptr,
        nullptr,
        &glacial_transport_history.back(),
        false,
        true,
        false,
        false,
        false,
        plate_motion_history.back().id,
        &pre_cryosphere_reference
    ));
    summarize_plates(params, cells, plates);
    derive_soils_biomes_resources(params, cells);
    derive_landforms(cells);
    const std::vector<IceSheet> ice_sheets = generate_ice_sheets(cells);
    const std::vector<LakeBasin> lake_basins = generate_lake_basins(params, cells);
    const std::vector<Watershed> watersheds = generate_watersheds(params, cells);
    const std::vector<CoastalFeature> coastal_features = generate_coastal_features(params, cells);
    const std::vector<SedimentaryBasin> sedimentary_basins = generate_sedimentary_basins(cells);
    const std::vector<StratigraphicColumn> stratigraphic_columns = generate_stratigraphic_columns(cells, sedimentary_basins);
    std::vector<Settlement> settlements = generate_settlements(params, cells);
    const std::vector<Route> routes = generate_routes(params, cells, settlements);
    const std::vector<PoliticalRegion> political_regions = generate_political_regions(params, cells, settlements, routes);
    const std::vector<BorderSegment> borders = generate_border_segments(params, cells);
    const std::vector<TradeFlow> trade_flows = generate_trade_flows(cells, settlements, routes);
    const CulturalLayers cultural_layers = generate_cultural_layers(params, cells, settlements, political_regions, borders, trade_flows);
    const HistoricalLayers historical_layers = generate_historical_layers(
        cells, settlements, political_regions, borders, trade_flows, cultural_layers
    );
    const std::vector<PopulationRegion> population_regions = generate_population_regions(cells, political_regions, cultural_layers);
    const std::vector<ConflictRecord> conflicts = generate_conflicts(
        cells, political_regions, borders, trade_flows, cultural_layers, population_regions
    );
    const std::vector<DynastyRecord> dynasties = generate_dynasties(
        political_regions, cultural_layers, historical_layers, population_regions, conflicts
    );
    const std::vector<TerritorialSnapshot> territorial_snapshots = generate_territorial_snapshots(
        params, cells, political_regions, settlements, cultural_layers, historical_layers, population_regions, conflicts
    );
    const std::vector<CalibrationCheck> calibration_checks = generate_calibration_checks(cells, watersheds);

    std::string out = "{";
    bool first = true;
    add_int(out, first, "schema_version", 1);
    add_str(out, first, "name", params.name);
    add_str(out, first, "mesh_backend", mesh_backend_name(params.mesh_backend));
    add_str(out, first, "cell_area_model", cell_area_model_name(params.mesh_backend));
    add_raw(out, first, "summary", summary_json(
        params, cells, watersheds, lake_basins, coastal_features, sedimentary_basins, stratigraphic_columns, ice_sheets,
        political_regions, borders, trade_flows, cultural_layers, historical_layers, population_regions, conflicts, dynasties,
        territorial_snapshots, calibration_checks, settlements, routes, feedback_history, plate_motion_history,
        numeric_depression_fill_history, hillslope_transport_history,
        glacial_transport_history
    ));
    add_raw(out, first, "backend", backend_info_json());
    add_raw(out, first, "climate_model", climate_model_json(params));
    add_raw(out, first, "hydrologic_water_budget_model",
        hydrologic_water_budget_model_json(
            hydrologic_water_budget_history,
            params.float_precision
        ));
    add_raw(out, first, "hydrologic_water_budget_history",
        hydrologic_water_budget_history_json(
            hydrologic_water_budget_history,
            params.float_precision
        ));
    add_raw(out, first, "simulation_clock", simulation_clock_json(params, feedback_history));
    add_raw(out, first, "earth_system_feedback_history",
        earth_system_feedback_history_json(feedback_history, params.float_precision));
    add_raw(out, first, "sediment_inventory_model",
        sediment_inventory_model_json(
            cells,
            feedback_history,
            numeric_depression_fill_history,
            hillslope_transport_history,
            sediment_routing_history,
            glacial_transport_history,
            params.float_precision
        ));
    add_raw(out, first, "numeric_depression_fill_history",
        numeric_depression_fill_history_json(
            numeric_depression_fill_history,
            params.float_precision
        ));
    add_raw(out, first, "hillslope_sediment_transport_model",
        hillslope_sediment_transport_model_json(
            params,
            hillslope_transport_history
        ));
    add_raw(out, first, "hillslope_sediment_transport_history",
        hillslope_sediment_transport_history_json(
            hillslope_transport_history,
            params.float_precision
        ));
    add_raw(out, first, "glacial_sediment_transport_model",
        glacial_sediment_transport_model_json(
            glacial_transport_history,
            params.float_precision
        ));
    add_raw(out, first, "glacial_sediment_transport_history",
        glacial_sediment_transport_history_json(
            glacial_transport_history,
            params.float_precision
        ));
    add_raw(out, first, "fluvial_sediment_routing_model",
        fluvial_sediment_routing_model_json(
            sediment_routing_history,
            params.float_precision
        ));
    add_raw(out, first, "fluvial_sediment_routing_history",
        fluvial_sediment_routing_history_json(
            sediment_routing_history,
            params.float_precision
        ));
    add_raw(out, first, "plate_kinematic_model", plate_kinematic_model_json(params, plate_motion_history, cells));
    add_raw(out, first, "sea_level_model", sea_level_model_json(params, cells));
    add_raw(out, first, "plate_motion_history",
        plate_motion_history_json(plate_motion_history, params.float_precision));
    add_raw(out, first, "plates", plates_json(plates, params.float_precision));
    add_raw(out, first, "watersheds", watersheds_json(watersheds, params.float_precision));
    add_raw(out, first, "lake_basins", lake_basins_json(lake_basins, params.float_precision));
    add_raw(out, first, "coastal_features", coastal_features_json(coastal_features, params.float_precision));
    add_raw(out, first, "sedimentary_basins", sedimentary_basins_json(sedimentary_basins, params.float_precision));
    add_raw(out, first, "stratigraphic_columns", stratigraphic_columns_json(stratigraphic_columns, params.float_precision));
    add_raw(out, first, "ice_sheets", ice_sheets_json(ice_sheets, params.float_precision));
    add_raw(out, first, "political_regions", political_regions_json(political_regions, params.float_precision));
    add_raw(out, first, "cultures", cultures_json(cultural_layers.cultures, params.float_precision));
    add_raw(out, first, "language_regions", language_regions_json(cultural_layers.language_regions, params.float_precision));
    add_raw(out, first, "historical_eras", historical_eras_json(historical_layers.eras, params.float_precision));
    add_raw(out, first, "historical_events", historical_events_json(historical_layers.events, params.float_precision));
    add_raw(out, first, "population_regions", population_regions_json(population_regions, params.float_precision));
    add_raw(out, first, "conflicts", conflicts_json(conflicts, params.float_precision));
    add_raw(out, first, "dynasties", dynasties_json(dynasties, params.float_precision));
    add_raw(out, first, "territorial_snapshots", territorial_snapshots_json(territorial_snapshots, params.float_precision));
    add_raw(out, first, "calibration_checks", calibration_checks_json(calibration_checks, params.float_precision));
    add_raw(out, first, "sacred_areas", sacred_areas_json(cultural_layers.sacred_areas, params.float_precision));
    add_raw(out, first, "ruins", ruins_json(cultural_layers.ruins, params.float_precision));
    add_raw(out, first, "borders", borders_json(borders, params.float_precision));
    add_raw(out, first, "settlements", settlements_json(cells, settlements, params.float_precision));
    add_raw(out, first, "routes", routes_json(routes, params.float_precision));
    add_raw(out, first, "trade_flows", trade_flows_json(trade_flows, params.float_precision));
    add_raw(out, first, "cells", params.include_cells ? cells_json(cells, params.float_precision) : "[]");
    out += "}";
    return out;
}

}  // namespace magic_geo
