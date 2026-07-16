#pragma once

#include <array>
#include <vector>

namespace magic_geo::detail {

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
    // Authoritative finite-volume geometry. Vertices are ordered
    // counter-clockwise as seen from outside the sphere. Entry i in
    // control_volume_edge_neighbor_ids identifies the cell across the
    // great-circle edge from vertex i to vertex (i + 1) % vertex_count.
    // A geodesic barycentric dual can have two consecutive edge segments
    // with the same neighboring cell because the shared dual boundary bends
    // at the primal-edge midpoint.
    std::vector<Vec3> control_volume_vertices;
    std::vector<int> control_volume_edge_neighbor_ids;
    std::vector<int> neighbors;
    int plate_id = 0;
    int initial_plate_id = 0;
    int plate_assignment_change_count = 0;
    int last_plate_assignment_change_iteration = -1;
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
    double cumulative_tectonic_elevation_change_m = 0.0;
    double boundary_convergent = 0.0;
    double boundary_divergent = 0.0;
    double boundary_transform = 0.0;
    double initial_isostatic_elevation_m = 0.0;
    // Instantaneous relative oceanic-basement equilibrium target from the
    // age-depth curve, not a realized terrain-component state. This is zero
    // for states that do not satisfy the oceanic-like predicate.
    double thermal_subsidence_target_m = 0.0;
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
    // Canonical top of non-mobile bedrock beneath the bulk mobile-sediment
    // layer.  elevation_m is the compatibility surface derived from this
    // interface plus sediment_thickness_m.
    double bedrock_surface_elevation_m = 0.0;
    double elevation_m = 0.0;
    double water_depth_m = 0.0;
    bool is_water = false;
    bool is_river = false;
    bool is_lake = false;
    double temperature_c = 0.0;
    double precipitation_mm_y = 0.0;
    std::array<double, 12> temperature_monthly_c{};
    std::array<double, 12> precipitation_monthly_mm{};
    double wind_east = 0.0;
    double wind_north = 0.0;
    std::array<double, 12> wind_monthly_east{};
    std::array<double, 12> wind_monthly_north{};
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
    double cumulative_numeric_depression_breach_excavation_m = 0.0;
    double cumulative_numeric_depression_breach_deposition_m = 0.0;
    int numeric_depression_breach_event_count = 0;
    bool numeric_depression_temporary_lake_deferred = false;
    int numeric_depression_temporary_lake_event_count = 0;
    double erosion_rate = 0.0;
    double sediment_thickness_m = 0.0;
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

// Canonical cumulative gross mobilization is the material partition sum.
inline double sediment_gross_mobilization_m(const Cell& cell) noexcept {
    return cell.sediment_alluvium_entrainment_m +
        cell.sediment_bedrock_erosion_m;
}

// Independent process-side witness for partition closure. Keep this derived
// from process provenance rather than from the material partitions above.
inline double sediment_process_source_witness_m(const Cell& cell) noexcept {
    return cell.hillslope_sediment_production_m +
        cell.fluvial_sediment_local_source_m +
        cell.glacial_sediment_production_m +
        cell.cumulative_numeric_depression_breach_excavation_m;
}

}  // namespace magic_geo::detail
