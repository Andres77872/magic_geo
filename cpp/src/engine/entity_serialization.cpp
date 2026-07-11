#include "internal.hpp"

namespace magic_geo::detail {

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

}  // namespace magic_geo::detail
