#pragma once

#include "../constants.hpp"
#include "core.hpp"

#include <string>
#include <vector>

namespace magic_geo::detail {

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

struct FluvialSedimentRoutingInputCell {
    int cell_id = -1;
    int flow_to_cell_id = -1;
    int depression_component_id = -1;
    int depression_sink_cell_id = -1;
    int water_body = 0;
    bool is_water = false;
    bool is_river = false;
    bool is_lake = false;
    bool lake_overflows = false;
    double cell_area_km2 = 0.0;
    double flow_accumulation = 0.0;
    double runoff_mm_y = 0.0;
    double hydrologic_flow_slope = 0.0;
    double routing_base_elevation_m = 0.0;
    double spill_elevation_m = 0.0;
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
    int cell_count = 0;
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
    // Cell-id-indexed audit evidence for the alluvium-first source
    // partition. These are geometric depths in metres, not mass or
    // provenance claims.
    std::vector<double> source_production_depth_m_by_cell;
    std::vector<double> alluvium_entrainment_depth_m_by_cell;
    std::vector<double> bedrock_erosion_depth_m_by_cell;
    std::vector<FluvialSedimentRoutingInputCell> input_cells;
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
    int cell_count = 0;
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
    // Cell-id-indexed audit evidence for the alluvium-first source
    // partition. These are geometric depths in metres, not mass or
    // provenance claims.
    std::vector<double> source_production_depth_m_by_cell;
    std::vector<double> alluvium_entrainment_depth_m_by_cell;
    std::vector<double> bedrock_erosion_depth_m_by_cell;
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
    int cell_count = 0;
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
    // Cell-id-indexed audit evidence for the alluvium-first source
    // partition. These are geometric depths in metres, not mass or
    // provenance claims.
    std::vector<double> source_production_depth_m_by_cell;
    std::vector<double> alluvium_entrainment_depth_m_by_cell;
    std::vector<double> bedrock_erosion_depth_m_by_cell;
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
    double mean_stream_power_response_m_per_reference_step = 0.0;
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
    Vec3 rotation_axis;
    double intrinsic_angular_speed = 0.0;
    double step_rotation_deg = 0.0;
    double cumulative_rotation_deg = 0.0;
    int cell_count = 0;
    double area_km2 = 0.0;
};

// One directed, reciprocal control-volume boundary segment.  The lower cell
// id is always the left side and its counter-clockwise control-volume edge
// supplies start -> end, so the tangent and normal signs are canonical.
struct PlateBoundarySegment {
    int segment_id = 0;
    int mesh_segment_id = 0;
    int left_cell_id = 0;
    int right_cell_id = 0;
    int left_edge_index = 0;
    int right_edge_index = 0;
    int left_plate_id = 0;
    int right_plate_id = 0;
    Vec3 start_unit;
    Vec3 midpoint_unit;
    Vec3 end_unit;
    Vec3 tangent_unit;
    Vec3 left_to_right_normal_unit;
    double angular_length_rad = 0.0;
    double length_km = 0.0;
    Vec3 left_euler_velocity_km_per_ma;
    Vec3 right_euler_velocity_km_per_ma;
    Vec3 relative_velocity_km_per_ma;
    double signed_opening_rate_km_per_ma = 0.0;
    double signed_convergence_rate_km_per_ma = 0.0;
    double signed_slip_rate_km_per_ma = 0.0;
    double signed_opening_index = 0.0;
    double signed_convergence_index = 0.0;
    double signed_slip_index = 0.0;
    double direct_convergent_strength = 0.0;
    double direct_divergent_strength = 0.0;
    double direct_transform_strength = 0.0;
    std::string direct_boundary_class;
    bool convergence_active = false;
    int left_opening_crust_type = 0;
    int left_opening_lithology = 0;
    double left_opening_crust_age_ma = 0.0;
    double left_opening_crust_thickness_km = 0.0;
    double left_opening_crust_density_g_cm3 = 0.0;
    bool left_opening_crust_state_available = false;
    bool left_opening_oceanic_like = false;
    int right_opening_crust_type = 0;
    int right_opening_lithology = 0;
    double right_opening_crust_age_ma = 0.0;
    double right_opening_crust_thickness_km = 0.0;
    double right_opening_crust_density_g_cm3 = 0.0;
    bool right_opening_crust_state_available = false;
    bool right_opening_oceanic_like = false;
    std::string polarity_candidate_status;
    std::string candidate_subducting_side;
    std::string candidate_overriding_side;
    // Candidate sides are deliberately separate from the physical decision.
    // Until a supplied constraint or a physical solver exists, convergent
    // segments stay explicitly unknown and cannot select a slab.
    std::string physical_polarity_status;
    std::string physical_polarity_source;
    std::string physical_subducting_side;
    std::string physical_overriding_side;
    double physical_polarity_confidence = 0.0;
};

enum InitialOceanicCrustAgeStatus : int {
    INITIAL_OCEANIC_AGE_NOT_OCEANIC_LIKE = 0,
    INITIAL_OCEANIC_AGE_RIDGE_SEED = 1,
    INITIAL_OCEANIC_AGE_RIDGE_REACHABLE = 2,
    INITIAL_OCEANIC_AGE_RIDGE_REACHABLE_CEILING_CLAMPED = 3,
    INITIAL_OCEANIC_AGE_UNRESOLVED_NO_ACTIVE_RIDGE_PATH_CEILING = 4,
};

// Complete authoritative witness for the procedural initial oceanic-crust age
// field. Per-cell scalar state is retained as a compatibility alias.
struct InitialOceanicCrustAgeDiagnostics {
    std::vector<double> age_ma_by_cell;
    std::vector<double> unclamped_graph_age_ma_by_cell;
    std::vector<int> status_id_by_cell;
    std::vector<int> predecessor_cell_id_by_cell;
    std::vector<int> origin_ridge_seed_cell_id_by_cell;
    std::vector<int> eligible_ridge_segment_ids;
    std::vector<int> ridge_seed_cell_ids;
    std::vector<double> cdf_thresholds_ma;
    std::vector<double> area_weighted_cdf_le_threshold;
    int cell_count = 0;
    int oceanic_like_cell_count = 0;
    int non_oceanic_like_cell_count = 0;
    int reachable_oceanic_like_cell_count = 0;
    int unreachable_oceanic_like_cell_count = 0;
    int reachable_ceiling_clamped_cell_count = 0;
    double eligible_ridge_total_length_km = 0.0;
    double opening_rate_length_sum_km2_per_ma = 0.0;
    double representative_full_spreading_rate_km_per_ma = 0.0;
    double representative_half_spreading_rate_km_per_ma = 0.0;
    double maximum_age_ma = 0.0;
    double oceanic_like_area_km2 = 0.0;
    double area_weighted_mean_age_ma = 0.0;
    double minimum_oceanic_like_age_ma = 0.0;
    double maximum_oceanic_like_age_ma = 0.0;
};

struct CrustTransportPlan {
    // Destination-major CSR. Edge values are raw spherical overlap areas;
    // destination columns are intentionally not normalized because gaps and
    // multiple coverage represent kinematic extension and compression.
    std::vector<int> destination_offsets;
    std::vector<int> source_cell_ids;
    std::vector<double> overlap_area_km2;
    std::vector<double> remap_residual_distance_km;
    std::vector<double> source_kinematic_distance_km;
    std::vector<int> dominant_source_cell_ids;
    std::vector<int> contributor_count_by_cell;
    std::vector<double> dominant_source_volume_fraction_by_cell;
    std::vector<double> coverage_area_sum_km2_by_cell;
    std::vector<double> covered_union_area_km2_by_cell;
    std::vector<double> uncovered_gap_area_km2_by_cell;
    std::vector<double> overlap_excess_area_km2_by_cell;
    std::vector<int> maximum_coverage_multiplicity_by_cell;
    std::vector<int> coverage_arrangement_line_count_by_cell;
    std::vector<int> coverage_arrangement_fragment_count_by_cell;
    // Destination-major membership-area classes with a second CSR for each
    // class's canonically sorted contributing source cells. Disconnected
    // arrangement atoms with the same source membership are intentionally
    // coalesced; no connected topology or physical fate is implied.
    std::vector<int> coverage_membership_area_class_count_by_cell;
    std::vector<int> coverage_membership_area_class_destination_offsets;
    std::vector<double> coverage_membership_area_class_area_km2;
    std::vector<int> coverage_membership_area_class_multiplicity;
    std::vector<double> coverage_membership_area_class_representative_unit_x;
    std::vector<double> coverage_membership_area_class_representative_unit_y;
    std::vector<double> coverage_membership_area_class_representative_unit_z;
    std::vector<int> coverage_membership_area_class_representative_available;
    std::vector<int> coverage_membership_area_class_contributor_offsets;
    std::vector<int> coverage_membership_area_class_source_cell_ids;
    std::vector<int> coverage_membership_area_class_source_plate_ids;
    std::vector<double> global_coverage_area_km2_by_multiplicity;
    std::vector<int> remapped_crust_type_by_cell;
    std::vector<int> remapped_lithology_by_cell;
    std::vector<double> remapped_crust_age_ma_by_cell;
    std::vector<double> remapped_crust_thickness_km_by_cell;
    std::vector<double> remapped_crust_density_by_cell;
    double maximum_source_area_closure_error_km2 = 0.0;
    double maximum_source_area_relative_closure_error = 0.0;
    double maximum_destination_partition_closure_error_km2 = 0.0;
    int maximum_coverage_arrangement_line_count = 0;
    int maximum_coverage_arrangement_fragment_count = 0;
    int maximum_coverage_membership_area_class_count = 0;
    double global_uncovered_gap_area_km2 = 0.0;
    double global_overlap_excess_area_km2 = 0.0;
    double initial_crust_volume_km3 = 0.0;
    double transported_crust_volume_km3 = 0.0;
    double initial_density_weighted_crust_volume = 0.0;
    double transported_density_weighted_crust_volume = 0.0;
    double initial_crust_age_volume_moment = 0.0;
    double transported_crust_age_volume_moment = 0.0;
};

// Diagnostic-only crosswalk between transport overlap membership classes and
// same-step boundary evidence.  Pair ids are stable for the supported
// canonical plate-id range: 256 * plate_low_id + plate_high_id.
struct CrustOverlapBoundaryPairEvidence {
    int pair_id = -1;
    int plate_low_id = -1;
    int plate_high_id = -1;
    std::vector<int> segment_ids;
    std::string physical_consensus_status;
    int physical_subducting_plate_id = -1;
    int physical_overriding_plate_id = -1;
    std::string heuristic_consensus_status;
    int heuristic_subducting_plate_id = -1;
    int heuristic_overriding_plate_id = -1;
};

struct CrustOverlapClassCandidate {
    int membership_area_class_id = -1;
    int destination_cell_id = -1;
    int multiplicity = 0;
    int boundary_pair_evidence_id = -1;
    std::string assignment_status;
    int candidate_subducting_contributor_id = -1;
    int candidate_overriding_contributor_id = -1;
};

struct CrustOverlapCandidateFateLedger {
    int source_plate_assignment_step_id = 0;
    int boundary_plate_assignment_step_id = 0;
    std::vector<CrustOverlapBoundaryPairEvidence> boundary_pair_evidence;
    std::vector<CrustOverlapClassCandidate> overlap_class_candidates;
    double physical_polarity_backed_candidate_excess_area_km2 = 0.0;
    double oceanic_heuristic_candidate_excess_area_km2 = 0.0;
    double unresolved_candidate_excess_area_km2 = 0.0;
    double accounted_overlap_excess_area_km2 = 0.0;
    double candidate_partition_residual_km2 = 0.0;
};

struct CrustProcessInventoryDelta {
    int triggered_cell_count = 0;
    int changed_cell_count = 0;
    double positive_crust_volume_km3 = 0.0;
    double negative_crust_volume_magnitude_km3 = 0.0;
    double positive_density_weighted_crust_volume = 0.0;
    double negative_density_weighted_crust_volume_magnitude = 0.0;
    double positive_crust_age_volume_moment_km3_ma = 0.0;
    double negative_crust_age_volume_moment_magnitude_km3_ma = 0.0;
    double crust_volume_km3 = 0.0;
    double density_weighted_crust_volume = 0.0;
    double crust_age_volume_moment_km3_ma = 0.0;
};

// Private engine-side shadow accounting for persistent surface-crust material.
// The scalar crust fields remain authoritative.  These tables deliberately
// retain unresolved rule additions/removals rather than pretending that the
// present rule system resolves mantle or slab reservoirs.
struct CrustMaterialShadowPacket {
    int origin_kind_id = 0;
    int origin_plate_id = 0;
    int origin_reason_id = -1;
    double dry_rock_mass_kg = 0.0;
};

struct CrustMaterialShadowAdjustment {
    int process_reason_id = 0;
    int origin_kind_id = 0;
    int origin_plate_id = 0;
    int origin_reason_id = -1;
    double dry_rock_mass_kg = 0.0;
};

struct CrustMaterialShadowPacketTable {
    std::vector<int> cell_offsets;
    std::vector<int> origin_kind_ids;
    std::vector<int> origin_plate_ids;
    std::vector<int> origin_reason_ids;
    std::vector<double> dry_rock_mass_kg;
};

struct CrustMaterialShadowAdjustmentTable {
    std::vector<int> cell_offsets;
    std::vector<int> process_reason_ids;
    std::vector<int> origin_kind_ids;
    std::vector<int> origin_plate_ids;
    std::vector<int> origin_reason_ids;
    std::vector<double> dry_rock_mass_kg;
};

struct CrustMaterialShadowStep {
    int id = 0;
    int plate_motion_history_id = 0;
    int erosion_iteration = -1;
    std::string stage;
    int cell_count = 0;
    CrustMaterialShadowPacketTable opening_packets;
    CrustMaterialShadowPacketTable transported_packets;
    CrustMaterialShadowAdjustmentTable unresolved_source_adjustments;
    CrustMaterialShadowAdjustmentTable unresolved_sink_adjustments;
    CrustMaterialShadowPacketTable closing_packets;
    double opening_surface_mass_kg = 0.0;
    double transported_surface_mass_kg = 0.0;
    double unresolved_source_mass_kg = 0.0;
    double unresolved_sink_mass_kg = 0.0;
    double closing_surface_mass_kg = 0.0;
    double closing_scalar_mass_kg = 0.0;
    double raw_transported_density_weighted_mass_kg = 0.0;
    double source_to_transport_residual_kg = 0.0;
    double shadow_minus_raw_transport_mass_kg = 0.0;
    double post_scalar_mirror_residual_kg = 0.0;
    double max_abs_post_scalar_mirror_cell_residual_kg = 0.0;
    double ordered_adjustment_reconciliation_residual_kg = 0.0;
    std::array<double, CRUST_PROCESS_REASON_COUNT>
        unresolved_source_mass_kg_by_reason{};
    std::array<double, CRUST_PROCESS_REASON_COUNT>
        unresolved_sink_mass_kg_by_reason{};
    int opening_packet_count = 0;
    int transported_packet_count = 0;
    int closing_packet_count = 0;
    int unresolved_source_adjustment_count = 0;
    int unresolved_sink_adjustment_count = 0;
};

struct CrustMaterialShadowState {
    std::vector<std::vector<CrustMaterialShadowPacket>>
        surface_packets_by_cell;
    std::vector<std::vector<CrustMaterialShadowAdjustment>>
        unresolved_source_adjustments_by_cell;
    std::vector<std::vector<CrustMaterialShadowAdjustment>>
        unresolved_sink_adjustments_by_cell;
    CrustMaterialShadowStep pending_step;
    bool step_open = false;
    std::vector<CrustMaterialShadowStep> history;
};

struct CrustMotionDiagnostics {
    CrustTransportPlan transport_plan;
    std::vector<int> source_cell_ids;
    std::vector<double> transport_distance_km_by_cell;
    std::vector<double> age_transport_change_ma_by_cell;
    std::vector<double> thickness_transport_change_km_by_cell;
    std::vector<double> density_transport_change_by_cell;
    std::vector<double> age_process_change_ma_by_cell;
    std::vector<double> thickness_process_change_km_by_cell;
    std::vector<double> density_process_change_by_cell;
    std::array<CrustProcessInventoryDelta, CRUST_PROCESS_REASON_COUNT>
        process_inventory_delta_by_reason{};
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
    int reciprocal_mesh_segment_count = 0;
    int boundary_segment_count = 0;
    int control_volume_boundary_incident_cell_count = 0;
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
    CrustTransportPlan transport_plan;
    double post_process_crust_volume_km3 = 0.0;
    double post_process_density_weighted_crust_volume = 0.0;
    double post_process_crust_age_volume_moment = 0.0;
    std::array<CrustProcessInventoryDelta, CRUST_PROCESS_REASON_COUNT>
        process_inventory_delta_by_reason{};
    std::vector<int> cell_plate_ids;
    std::vector<double> boundary_convergent_by_cell;
    std::vector<double> boundary_divergent_by_cell;
    std::vector<double> boundary_transform_by_cell;
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
    std::vector<double> previous_local_isostatic_equilibrium_m;
    std::vector<double> post_process_local_isostatic_equilibrium_m;
    std::vector<double> isostatic_equilibrium_change_m;
    std::vector<double> previous_local_thermal_subsidence_target_m;
    std::vector<double> post_process_local_thermal_subsidence_target_m;
    std::vector<double> thermal_equilibrium_change_m;
    // Deprecated compatibility alias for thermal_equilibrium_change_m.
    std::vector<double> thermal_target_difference_tendency_m;
    std::vector<double> unbounded_dynamic_relief_change_m;
    std::vector<double> bounded_dynamic_relief_change_m;
    std::vector<int> aged_oceanic_cell_ids;
    std::vector<int> rejuvenated_oceanic_cell_ids;
    std::vector<int> subducted_oceanic_cell_ids;
    std::vector<PlateBoundarySegment> boundary_segments;
    CrustOverlapCandidateFateLedger crust_overlap_candidate_fate_ledger;
    std::vector<PlateKinematicSnapshot> plates;
};

}  // namespace magic_geo::detail
