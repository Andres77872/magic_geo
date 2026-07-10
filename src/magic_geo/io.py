from __future__ import annotations

import csv
import html
import json
import math
from pathlib import Path
from typing import Any


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_cells_csv(path: Path, world: dict[str, Any]) -> None:
    cells = world.get("cells", [])
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "id",
        "lat_deg",
        "lon_deg",
        "mesh_lod_face",
        "mesh_lod_finest_tile_id",
        "boundary_vertex_count",
        "cell_boundary_perimeter_km",
        "cell_polygon_area_km2",
        "cell_polygon_area_error_fraction",
        "cell_geometry_quality",
        "cell_edge_count",
        "mean_neighbor_edge_length_km",
        "max_neighbor_edge_length_km",
        "mean_neighbor_boundary_segment_length_km",
        "max_neighbor_boundary_segment_length_km",
        "mean_neighbor_boundary_segment_mismatch_km",
        "mean_neighbor_boundary_segment_quality",
        "tectonic_neighbor_edge_count",
        "land_water_neighbor_edge_count",
        "biome_transition_neighbor_edge_count",
        "political_region_id",
        "culture_region_id",
        "language_region_id",
        "plate_id",
        "crust_type",
        "boundary_type",
        "collision_zone_id",
        "subduction_zone_id",
        "rift_zone_id",
        "dominant_tectonic_zone_type",
        "tectonic_zone_strength",
        "lithology",
        "crust_age_ma",
        "crust_thickness_km",
        "crust_density",
        "initial_isostatic_elevation_m",
        "initial_thermal_subsidence_m",
        "initial_ridge_uplift_m",
        "initial_orogenic_uplift_m",
        "initial_volcanic_uplift_m",
        "initial_trench_subsidence_m",
        "initial_rift_subsidence_m",
        "initial_transform_fault_relief_m",
        "initial_secondary_roughness_m",
        "initial_elevation_m",
        "tectonic_uplift_rate_m_per_step",
        "volcanic_potential_index",
        "elevation_m",
        "water_depth_m",
        "water_body_type",
        "landmass_id",
        "island_class",
        "marine_region_id",
        "marine_chokepoint_id",
        "river_navigability_index",
        "coastal_navigability_index",
        "harbor_suitability_index",
        "transport_chokepoint_index",
        "navigability_index",
        "navigability_class",
        "navigable_waterway_id",
        "protected_bay_index",
        "river_mouth_port_index",
        "strait_access_index",
        "port_suitability_index",
        "port_site_type",
        "port_site_id",
        "mountain_pass_route_index",
        "river_valley_route_index",
        "coastal_route_index",
        "oasis_route_index",
        "route_corridor_index",
        "route_corridor_type",
        "route_corridor_id",
        "reef_growth_index",
        "reef_sediment_stress_index",
        "reef_wave_exposure_index",
        "reef_island_support_index",
        "reef_bleaching_risk_index",
        "reef_type",
        "reef_system_id",
        "temperature_c",
        "precipitation_mm_y",
        "wind_east",
        "wind_north",
        "mean_seasonal_wind_speed",
        "seasonal_wind_reversal_index",
        "atmospheric_cell",
        "surface_pressure_anomaly_hpa",
        "vertical_velocity_index",
        "wind_divergence_index",
        "ocean_current_east",
        "ocean_current_north",
        "ocean_current_temperature_c",
        "ocean_current_moisture_factor",
        "humidity_transport_index",
        "upwind_ocean_fetch_km",
        "advected_moisture_factor",
        "orographic_factor",
        "rain_shadow_factor",
        "vapor_evaporation_mm_y",
        "moisture_convergence_mm_y",
        "orographic_rainout_mm_y",
        "precipitation_recycling_fraction",
        "vapor_deficit_mm_y",
        "vapor_budget_residual_mm_y",
        "seasonal_precipitation_range_mm",
        "seasonal_aridity_index",
        "cell_monsoon_index",
        "seasonal_humidity_regime",
        "climate_class",
        "top_of_atmosphere_insolation_w_m2",
        "surface_albedo_index",
        "surface_albedo_regime",
        "absorbed_shortwave_w_m2",
        "outgoing_longwave_w_m2",
        "greenhouse_trapping_w_m2",
        "net_radiative_balance_w_m2",
        "no_greenhouse_equilibrium_temperature_c",
        "radiative_equilibrium_temperature_c",
        "energy_balance_residual_c",
        "climate_energy_stress_index",
        "runoff_mm_y",
        "flow_to",
        "equal_filled_raw_downhill_rerouted",
        "spill_to",
        "depression_component_id",
        "depression_sink_cell_id",
        "lake_basin_id",
        "depression_policy",
        "flow_accumulation",
        "filled_elevation_m",
        "depression_depth_m",
        "spill_elevation_m",
        "lake_fill_fraction",
        "basin_id",
        "is_river",
        "is_lake",
        "is_closed_basin",
        "lake_overflows",
        "overflow_channel_active",
        "overflow_channel_incision_m",
        "overflow_channel_sediment_evacuated_km3",
        "overflow_channel_avulsion_risk",
        "river_capture_risk",
        "river_capture_target_cell_id",
        "river_capture_target_basin_id",
        "river_capture_divide_relief_m",
        "river_capture_target_distance_km",
        "river_avulsion_risk",
        "river_network_instability_index",
        "erosion_rate",
        "sediment_thickness_m",
        "sediment_production_m",
        "sediment_deposition_m",
        "sediment_export_m",
        "sediment_net_budget_m",
        "sediment_routing_load_m",
        "sediment_routing_deposition_m",
        "sediment_routing_export_m",
        "sediment_routing_path_count",
        "ice_thickness_m",
        "ice_sheet_id",
        "glacier_flow_to",
        "ice_surface_mass_balance_m_y",
        "basal_sliding_index",
        "ice_velocity_m_y",
        "glacial_erosion_m",
        "moraine_deposition_m",
        "deglaciation_age_ka",
        "ice_flowline_flux_km3_y",
        "ice_flowline_driving_stress_kpa",
        "ice_flowline_strain_heating_index",
        "ice_flowline_path_count",
        "permafrost_extent_index",
        "active_layer_depth_m",
        "ground_ice_content_index",
        "permafrost_class",
        "permafrost_region_id",
        "landform",
        "soil_type",
        "soil_texture_class",
        "soil_drainage_index",
        "soil_moisture_index",
        "soil_ph",
        "soil_organic_matter_fraction",
        "soil_salinity_index",
        "soil_erodibility_index",
        "soil_profile_development_index",
        "soil_profile_id",
        "soil_horizon_count",
        "biome",
        "potential_evapotranspiration_mm_y",
        "climatic_water_deficit_mm_y",
        "climatic_water_surplus_mm_y",
        "growing_season_months",
        "frost_months",
        "dry_season_months",
        "wet_season_months",
        "fire_frequency_index",
        "biome_confidence_index",
        "ecotone_index",
        "biome_transition_zone",
        "biome_ecotone_type",
        "biome_ecotone_confidence",
        "biome_ecotone_region_id",
        "groundwater_recharge_mm_y",
        "groundwater_recharge_km3_y",
        "aquifer_storage_index",
        "aquifer_quality_index",
        "aquifer_productivity_index",
        "aquifer_extraction_risk_index",
        "aquifer_class",
        "aquifer_system_id",
        "karst_potential_index",
        "cave_development_index",
        "subterranean_drainage_fraction",
        "karst_system_id",
        "primary_productivity_index",
        "vegetation_biomass_index",
        "species_richness_index",
        "wildfire_spread_risk_index",
        "ecosystem_disturbance_pressure_index",
        "vegetation_succession_stage",
        "vegetation_recovery_years",
        "forest_growth_index",
        "fishery_productivity_index",
        "resource",
        "agricultural_potential_index",
        "mining_potential_index",
        "agricultural_zone_id",
        "mining_zone_id",
        "natural_frontier_index",
        "natural_frontier_type",
        "natural_frontier_id",
        "settlement_score",
        "continental_shelf_id",
        "distance_to_marine_water_km",
        "continentality_index",
        "oceanic_humidity_availability_index",
        "marine_influence_class",
        "climate_continentality_region_id",
        "actual_evapotranspiration_mm_y",
        "infiltration_capacity_index",
        "infiltration_mm_y",
        "hydrologic_water_balance_mm_y",
        "water_budget_runoff_mm_y",
        "runoff_budget_residual_mm_y",
        "runoff_budget_consistency_index",
        "hydrologic_deficit_mm_y",
        "runoff_generation_fraction",
        "hydrologic_budget_class",
        "hydrologic_budget_region_id",
        "wetland_extent_index",
        "wetland_hydrology_index",
        "wetland_soil_saturation_index",
        "wetland_ecotone_index",
        "wetland_connectivity_index",
        "wetland_coastal_flag",
        "wetland_system_type",
        "wetland_system_id",
        "glacial_landform_index",
        "glacial_erosion_intensity_index",
        "glacial_deposition_index",
        "glacial_meltwater_index",
        "glacial_landform_type",
        "glacial_landform_system_id",
        "seasonal_insolation_range_w_m2",
        "orbital_insolation_variability_index",
        "peak_seasonal_insolation_w_m2",
        "low_seasonal_insolation_w_m2",
        "fault_slip_rate_index",
        "seismic_hazard_index",
        "earthquake_recurrence_interval_y",
        "fault_system_id",
        "groundwater_hydraulic_head_m",
        "groundwater_gradient_index",
        "groundwater_lateral_flow_km3_y",
        "groundwater_discharge_mm_y",
        "groundwater_discharge_km3_y",
        "groundwater_flow_to_cell_id",
        "spring_discharge_index",
        "baseflow_support_index",
        "groundwater_flow_regime",
        "groundwater_flow_system_id",
        "river_channel_width_m",
        "river_channel_depth_m",
        "bankfull_discharge_m3_s",
        "channel_slope_index",
        "stream_power_index",
        "floodplain_connectivity_index",
        "channel_morphology_class",
        "river_channel_system_id",
        "hydraulic_radius_m",
        "flow_velocity_m_s",
        "froude_number",
        "bed_shear_stress_pa",
        "manning_roughness_n",
        "channel_capacity_index",
        "hydraulic_navigability_index",
        "hydraulic_flow_regime",
        "river_hydraulic_reach_id",
        "dominant_species_guild",
        "species_habitat_suitability_index",
        "species_endemism_index",
        "species_range_fragmentation_index",
        "species_composition_confidence_index",
        "species_guild_richness_count",
        "species_range_record_ids",
        "wildfire_ignition_potential_index",
        "wildfire_fuel_continuity_index",
        "wildfire_wind_alignment_index",
        "wildfire_firebreak_index",
        "wildfire_disturbance_regime",
        "wildfire_spread_history_ids",
        "petroleum_source_rock_index",
        "petroleum_maturation_index",
        "petroleum_migration_path_index",
        "petroleum_trap_integrity_index",
        "petroleum_accumulation_index",
        "petroleum_system_id",
        "ore_genesis_potential_index",
        "hydrothermal_alteration_index",
        "metallogenic_fertility_index",
        "ore_structural_control_index",
        "placer_concentration_index",
        "ore_genesis_system_id",
        "healpix_like_nside",
        "healpix_like_ring",
        "healpix_like_lon_bin",
        "healpix_like_pixel_id",
        "healpix_like_pixel_code",
        "s2_like_face",
        "s2_like_face_id",
        "s2_like_cell_level",
        "s2_like_x",
        "s2_like_y",
        "s2_like_cell_id",
        "s2_like_token",
        "ocean_current_speed_index",
        "ocean_current_poleward_index",
        "ocean_heat_transport_index",
        "ocean_current_transport_alignment",
        "ocean_current_transport_target_cell_id",
        "ocean_current_transport_distance_km",
        "ocean_current_convergence_index",
        "ocean_upwelling_index",
        "ocean_current_regime",
        "ocean_current_system_id",
        "initial_plate_id",
        "plate_assignment_change_count",
        "last_plate_assignment_change_iteration",
        "initial_crust_age_ma",
        "initial_crust_thickness_km",
        "initial_crust_density",
        "cumulative_tectonic_elevation_change_m",
        "last_crust_source_cell_id",
        "crust_source_remap_event_count",
        "oceanic_crust_aging_event_count",
        "oceanic_crust_rejuvenation_event_count",
        "oceanic_crust_subduction_event_count",
        "cumulative_crust_transport_distance_km",
        "hydrologic_surface_elevation_m",
        "hydrologic_flow_drop_m",
        "hydrologic_flow_slope",
        "hydrologic_surface_conditioned",
        "cumulative_numeric_depression_fill_m",
        "numeric_depression_fill_event_count",
        "cumulative_numeric_depression_breach_excavation_m",
        "cumulative_numeric_depression_breach_deposition_m",
        "numeric_depression_breach_event_count",
        "glacial_sediment_deposition_m",
        "numeric_depression_temporary_lake_event_count",
        "fluvial_sediment_local_source_m",
        "fluvial_sediment_routed_incoming_m",
        "fluvial_sediment_routed_outgoing_m",
        "fluvial_sediment_local_deposition_m",
        "fluvial_sediment_terminal_land_deposition_m",
        "fluvial_sediment_marine_deposition_m",
        "fluvial_sediment_depression_fill_m",
        "fluvial_sediment_terminal_export_m",
        "fluvial_sediment_terminal_capture_volume_km3",
        "fluvial_sediment_routing_event_count",
        "hillslope_sediment_production_m",
        "hillslope_sediment_deposition_m",
        "hillslope_sediment_net_m",
        "hillslope_sediment_outgoing_edge_count",
        "hillslope_sediment_incoming_edge_count",
        "glacial_sediment_production_m",
        "glacial_sediment_net_m",
        "glacial_sediment_outgoing_transfer_count",
        "glacial_sediment_incoming_transfer_count",
        "sediment_alluvium_entrainment_m",
        "sediment_bedrock_erosion_m",
        "hydrologic_potential_evapotranspiration_mm_y",
        "groundwater_recharge_source_infiltration_mm_y",
        "groundwater_recharge_fraction",
        "vadose_zone_retention_mm_y",
        "vadose_zone_retention_km3_y",
        "groundwater_recharge_mass_balance_residual_mm_y",
        "groundwater_lateral_inflow_km3_y",
        "groundwater_available_volume_km3_y",
        "groundwater_internal_lateral_outflow_km3_y",
        "groundwater_retained_storage_km3_y",
        "groundwater_flow_mass_balance_residual_km3_y",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(cells)


def write_summary_markdown(path: Path, world: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = world.get("summary", {})
    backend = world.get("backend", {})

    lines = [
        f"# {world.get('name', 'magic-geo world')}",
        "",
        "## Summary",
        "",
    ]
    for key in [
        "seed",
        "mesh_backend",
        "cell_area_model",
        "cell_count",
        "output_float_precision",
        "depression_routing_model",
        "depression_geology_model",
        "numeric_depression_correction_model",
        "numeric_depression_correction_selection_model",
        "numeric_depression_breach_diagnostic_model",
        "numeric_depression_breach_gradient_step_m",
        "numeric_depression_selected_breach_max_depth_m",
        "numeric_depression_breach_mass_transfer_model",
        "numeric_depression_correction_selection_reason",
        "numeric_depression_fill_max_pass_count",
        "numeric_depression_fill_depth_tolerance_m",
        "hydrologic_surface_model",
        "hydrologic_water_budget_model",
        "hydrologic_water_budget_execution_order",
        "hydrologic_flat_gradient_step_m",
        "river_extraction_model",
        "river_extraction_percentile",
        "river_flow_accumulation_threshold",
        "surface_area_km2",
        "mean_cell_area_km2",
        "min_cell_area_km2",
        "max_cell_area_km2",
        "cell_area_coefficient_of_variation",
        "mesh_lod_index",
        "mesh_lod_max_level",
        "mesh_lod_level_count",
        "mesh_lod_tile_count",
        "mesh_lod_finest_tile_count",
        "mesh_lod_mean_finest_tile_cell_count",
        "spherical_spatial_index",
        "healpix_like_nside",
        "healpix_like_pixel_count",
        "healpix_like_occupied_pixel_count",
        "healpix_like_mean_cells_per_occupied_pixel",
        "s2_like_cell_level",
        "s2_like_cell_count",
        "s2_like_occupied_cell_count",
        "s2_like_mean_cells_per_occupied_cell",
        "cell_geometry_index",
        "cell_geometry_ring_count",
        "cell_geometry_total_area_km2",
        "cell_geometry_reference_area_km2",
        "cell_geometry_mean_vertex_count",
        "cell_geometry_mean_perimeter_km",
        "cell_geometry_mean_area_error_fraction",
        "cell_geometry_max_area_error_fraction",
        "cell_geometry_mean_quality",
        "cell_adjacency_edge_count",
        "mean_cell_adjacency_edge_length_km",
        "max_cell_adjacency_edge_length_km",
        "cell_boundary_segment_geometry",
        "cell_boundary_segment_count",
        "mean_cell_boundary_segment_length_km",
        "max_cell_boundary_segment_length_km",
        "mean_cell_boundary_segment_mismatch_km",
        "mean_cell_boundary_segment_quality",
        "tectonic_adjacency_edge_count",
        "land_water_adjacency_edge_count",
        "biome_transition_adjacency_edge_count",
        "tectonic_zone_count",
        "collision_zone_count",
        "subduction_zone_count",
        "rift_zone_count",
        "collision_zone_cell_count",
        "subduction_zone_cell_count",
        "rift_zone_cell_count",
        "tectonic_zone_total_area_km2",
        "tectonic_zone_boundary_length_km",
        "mean_tectonic_zone_strength",
        "fault_system_count",
        "fault_system_cell_count",
        "fault_system_total_area_km2",
        "fault_system_boundary_length_km",
        "mean_fault_slip_rate_index",
        "mean_seismic_hazard_index",
        "high_seismic_hazard_cell_count",
        "mean_earthquake_recurrence_interval_y",
        "plate_count",
        "plate_motion_history_step_count",
        "plate_motion_transition_count",
        "total_plate_reassignment_event_count",
        "plate_reassigned_cell_count",
        "max_plate_assignment_change_count",
        "total_crust_source_remap_event_count",
        "total_crust_source_reuse_count",
        "total_aged_oceanic_event_count",
        "total_rejuvenated_oceanic_event_count",
        "total_subducted_oceanic_event_count",
        "accreted_terrane_cell_count",
        "mean_plate_cumulative_rotation_deg",
        "max_plate_cumulative_rotation_deg",
        "mean_crust_transport_distance_km_per_motion_step",
        "max_crust_transport_distance_km",
        "mean_abs_crust_age_change_ma_per_motion_step",
        "mean_abs_crust_thickness_change_km_per_motion_step",
        "mean_abs_crust_density_change_per_motion_step",
        "mean_abs_crust_age_transport_change_ma_per_motion_step",
        "mean_abs_crust_thickness_transport_change_km_per_motion_step",
        "mean_abs_crust_density_transport_change_per_motion_step",
        "mean_abs_crust_age_process_change_ma_per_motion_step",
        "mean_abs_crust_thickness_process_change_km_per_motion_step",
        "mean_abs_crust_density_process_change_per_motion_step",
        "mean_abs_tectonic_elevation_change_m_per_motion_step",
        "target_ocean_water_inventory_km3",
        "ocean_area_km2",
        "ocean_volume_km3",
        "ocean_water_inventory_error_km3",
        "ocean_fraction",
        "ocean_cell_fraction",
        "target_ocean_fraction",
        "simulation_clock_stage_count",
        "simulation_clock_erosion_iteration_count",
        "simulation_clock_cryosphere_coupling_stage_count",
        "simulation_clock_sea_level_recompute_count",
        "simulation_clock_climate_recompute_count",
        "simulation_clock_hydrologic_water_budget_recompute_count",
        "simulation_clock_hydrology_recompute_count",
        "mean_erosion_iteration_elevation_change_m",
        "total_feedback_mean_abs_elevation_change_m",
        "final_feedback_mean_abs_temperature_change_c",
        "final_feedback_mean_abs_precipitation_change_mm_y",
        "final_feedback_mean_abs_runoff_change_mm_y",
        "landmass_count",
        "continent_landmass_count",
        "island_landmass_count",
        "largest_landmass_area_km2",
        "mean_landmass_area_km2",
        "marine_region_count",
        "open_ocean_marine_region_count",
        "inland_sea_marine_region_count",
        "continental_shelf_marine_region_count",
        "largest_marine_region_area_km2",
        "continental_shelf_count",
        "continental_shelf_cell_count",
        "continental_shelf_total_area_km2",
        "largest_continental_shelf_area_km2",
        "mean_continental_shelf_depth_m",
        "continental_shelf_shoreline_edge_count",
        "continental_shelf_break_edge_count",
        "marine_chokepoint_count",
        "strait_chokepoint_count",
        "mean_marine_chokepoint_constriction_index",
        "settlement_selection_model",
        "route_network_model",
        "political_region_model",
        "political_border_model",
        "trade_flow_model",
        "navigability_model",
        "navigable_cell_count",
        "navigable_waterway_count",
        "navigable_waterway_total_area_km2",
        "mean_navigability_index",
        "mean_river_navigability_index",
        "mean_coastal_navigability_index",
        "mean_harbor_suitability_index",
        "mean_transport_chokepoint_index",
        "high_harbor_suitability_cell_count",
        "transport_chokepoint_cell_count",
        "port_site_model",
        "port_site_count",
        "port_candidate_cell_count",
        "port_site_total_area_km2",
        "mean_port_suitability_index",
        "mean_protected_bay_index",
        "mean_river_mouth_port_index",
        "mean_strait_access_index",
        "port_settlement_count",
        "port_settlement_with_site_count",
        "protected_bay_port_site_count",
        "river_mouth_port_site_count",
        "strait_port_site_count",
        "route_corridor_model",
        "route_corridor_count",
        "route_corridor_cell_count",
        "route_corridor_total_path_length_km",
        "mean_route_corridor_index",
        "mean_mountain_pass_route_index",
        "mean_river_valley_route_index",
        "mean_coastal_route_index",
        "mean_oasis_route_index",
        "route_feature_coverage_index",
        "mountain_pass_route_corridor_count",
        "river_valley_route_corridor_count",
        "coastal_route_corridor_count",
        "oasis_route_corridor_count",
        "reef_system_count",
        "reef_cell_count",
        "reef_total_area_km2",
        "mean_reef_growth_index",
        "mean_reef_sediment_stress_index",
        "mean_reef_wave_exposure_index",
        "mean_reef_island_support_index",
        "mean_reef_bleaching_risk_index",
        "fringing_reef_system_count",
        "barrier_reef_system_count",
        "atoll_reef_system_count",
        "patch_reef_system_count",
        "cold_water_reef_system_count",
        "global_liquid_water_temperature_index",
        "atmosphere_gravity_stability_index",
        "rotation_circulation_plausibility_index",
        "surface_water_inventory_index",
        "planet_realism_check_count",
        "planet_realism_pass_count",
        "planet_realism_pass_fraction",
        "mean_planet_realism_score",
        "min_elevation_m",
        "max_elevation_m",
        "mean_land_elevation_m",
        "river_count",
        "hydrologic_surface_conditioned_cell_count",
        "equal_filled_flow_edge_count",
        "raw_uphill_flow_edge_count",
        "non_downhill_hydrologic_flow_edge_count",
        "max_hydrologic_surface_adjustment_m",
        "max_raw_uphill_flow_step_m",
        "equal_filled_raw_downhill_reroute_count",
        "terminal_land_sink_count",
        "avoidable_equal_filled_raw_downhill_sink_count",
        "flow_cycle_cell_count",
        "lake_count",
        "depression_component_count",
        "depression_component_cell_count",
        "lake_basin_count",
        "overflowing_lake_basin_count",
        "staged_overflow_lake_basin_count",
        "high_avulsion_risk_lake_basin_count",
        "preserved_geologic_depression_count",
        "corrected_numeric_depression_count",
        "temporary_numeric_lake_depression_count",
        "numeric_depression_fill_pass_count",
        "numeric_depression_correction_pass_count",
        "numeric_depression_correction_event_count",
        "numeric_depression_fill_event_count",
        "numeric_depression_fill_cell_application_count",
        "numeric_depression_filled_unique_cell_count",
        "numeric_depression_fill_geologic_source_event_count",
        "numeric_depression_fill_area_km2",
        "numeric_depression_fill_volume_km3",
        "numeric_depression_fill_candidate_event_count",
        "numeric_depression_fill_candidate_cell_application_count",
        "numeric_depression_fill_candidate_area_km2",
        "numeric_depression_fill_candidate_volume_km3",
        "mean_numeric_depression_fill_depth_m",
        "max_numeric_depression_fill_depth_m",
        "cumulative_numeric_depression_fill_sum_m",
        "max_cumulative_numeric_depression_fill_m",
        "numeric_depression_temporary_lake_event_count",
        "numeric_depression_temporary_lake_cell_application_count",
        "numeric_depression_temporary_lake_unique_cell_count",
        "numeric_depression_temporary_lake_candidate_area_km2",
        "numeric_depression_temporary_lake_candidate_volume_km3",
        "max_numeric_depression_temporary_lake_depth_m",
        "numeric_depression_breach_feasible_event_count",
        "numeric_depression_breach_lower_volume_event_count",
        "numeric_depression_breach_depth_bound_pass_event_count",
        "numeric_depression_breach_capacity_pass_event_count",
        "numeric_depression_breach_selected_event_count",
        "numeric_depression_breach_excavation_cell_application_count",
        "numeric_depression_breach_deposition_cell_application_count",
        "numeric_depression_selected_breach_excavation_volume_km3",
        "numeric_depression_selected_breach_deposition_volume_km3",
        "numeric_depression_correction_mass_balance_residual_km3",
        "numeric_depression_mass_conserving_event_count",
        "numeric_depression_zero_material_deferral_event_count",
        "numeric_depression_unbalanced_fill_event_count",
        "numeric_depression_avoided_unsourced_fill_volume_km3",
        "sediment_budget_closure_model",
        "sediment_budget_production_km3",
        "sediment_budget_deposition_km3",
        "sediment_budget_export_km3",
        "sediment_budget_residual_km3",
        "sediment_inventory_model",
        "sediment_initial_mobile_inventory_model",
        "sediment_source_partition_model",
        "sediment_erosion_stage_source_partition_order",
        "sediment_gross_mobilization_volume_km3",
        "sediment_alluvium_entrainment_volume_km3",
        "sediment_bedrock_erosion_volume_km3",
        "sediment_final_inventory_volume_km3",
        "sediment_source_partition_residual_km3",
        "sediment_inventory_mass_balance_residual_km3",
        "fluvial_sediment_routing_stage_count",
        "fluvial_sediment_active_cell_step_count",
        "fluvial_sediment_routed_edge_count",
        "fluvial_sediment_routed_cell_count",
        "fluvial_sediment_land_terminal_count",
        "fluvial_sediment_marine_terminal_count",
        "fluvial_sediment_terminal_capture_cell_count",
        "fluvial_sediment_terminal_allocation_count",
        "fluvial_sediment_local_source_volume_km3",
        "fluvial_sediment_routed_throughput_volume_km3",
        "fluvial_sediment_capacity_deposition_volume_km3",
        "fluvial_sediment_depression_fill_deposition_volume_km3",
        "fluvial_sediment_lake_trap_deposition_volume_km3",
        "fluvial_sediment_terminal_land_deposition_volume_km3",
        "fluvial_sediment_marine_deposition_volume_km3",
        "fluvial_sediment_terminal_export_volume_km3",
        "fluvial_sediment_total_deposition_volume_km3",
        "fluvial_sediment_mass_balance_residual_km3",
        "fluvial_sediment_alluvium_entrainment_volume_km3",
        "fluvial_sediment_bedrock_erosion_volume_km3",
        "hillslope_sediment_transport_stage_count",
        "hillslope_sediment_transport_edge_count",
        "hillslope_sediment_source_cell_stage_count",
        "hillslope_sediment_target_cell_stage_count",
        "hillslope_sediment_land_to_land_edge_count",
        "hillslope_sediment_land_to_marine_edge_count",
        "hillslope_sediment_unique_source_cell_count",
        "hillslope_sediment_unique_target_cell_count",
        "hillslope_sediment_production_volume_km3",
        "hillslope_sediment_deposition_volume_km3",
        "hillslope_sediment_mass_balance_residual_km3",
        "hillslope_sediment_alluvium_entrainment_volume_km3",
        "hillslope_sediment_bedrock_erosion_volume_km3",
        "max_hillslope_sediment_source_production_depth_m",
        "max_hillslope_sediment_target_deposition_depth_m",
        "mean_hillslope_sediment_effective_diffusivity",
        "glacial_sediment_transport_stage_count",
        "glacial_sediment_transfer_count",
        "glacial_sediment_source_cell_count",
        "glacial_sediment_target_cell_count",
        "glacial_sediment_land_target_transfer_count",
        "glacial_sediment_marine_target_transfer_count",
        "glacial_sediment_production_volume_km3",
        "glacial_sediment_deposition_volume_km3",
        "glacial_sediment_mass_balance_residual_km3",
        "glacial_sediment_terrain_volume_change_residual_km3",
        "glacial_sediment_alluvium_entrainment_volume_km3",
        "glacial_sediment_bedrock_erosion_volume_km3",
        "max_glacial_sediment_source_production_depth_m",
        "max_glacial_sediment_target_deposition_depth_m",
        "numeric_depression_alluvium_entrainment_volume_km3",
        "numeric_depression_bedrock_erosion_volume_km3",
        "numeric_depression_feasible_breach_excavation_volume_km3",
        "numeric_depression_lower_volume_hybrid_adjustment_volume_km3",
        "numeric_depression_lower_volume_hybrid_saved_volume_km3",
        "numeric_depression_lower_volume_hybrid_saved_fraction",
        "mean_numeric_depression_breach_path_length_km",
        "max_numeric_depression_breach_path_length_km",
        "max_numeric_depression_breach_excavation_depth_m",
        "max_lower_volume_breach_excavation_depth_m",
        "closed_depression_count",
        "mean_lake_fill_fraction",
        "lake_storage_capacity_km3",
        "lake_annual_runoff_km3",
        "mean_lake_overflow_path_length_km",
        "mean_lake_avulsion_risk",
        "simulated_lake_basin_count",
        "lake_overflow_history_count",
        "lake_overflow_history_step_count",
        "lake_overflow_simulation_years",
        "lake_overflow_active_history_count",
        "lake_overflow_avulsion_trigger_count",
        "lake_overflow_total_spill_km3",
        "lake_overflow_total_sink_loss_km3",
        "max_lake_overflow_fill_fraction",
        "lake_overflow_channel_history_count",
        "lake_overflow_channel_step_count",
        "active_lake_overflow_channel_count",
        "lake_overflow_channel_cell_count",
        "lake_overflow_channel_avulsion_count",
        "lake_overflow_total_channel_incision_m",
        "max_lake_overflow_channel_incision_m",
        "lake_overflow_total_channel_sediment_evacuated_km3",
        "mean_lake_overflow_channel_stream_power_index",
        "basin_count",
        "endorheic_basin_count",
        "watershed_count",
        "endorheic_watershed_count",
        "largest_watershed_area_km2",
        "watershed_main_channel_count",
        "watershed_total_river_length_km",
        "watershed_mean_main_channel_length_km",
        "watershed_max_main_channel_length_km",
        "watershed_mean_drainage_density_km_per_1000_km2",
        "watershed_hack_exponent",
        "watershed_hack_fit_coefficient",
        "watershed_mean_hack_coefficient",
        "watershed_mean_abs_hack_residual_fraction",
        "watershed_hack_fitted_observation_count",
        "watershed_hack_fitted_minimum_basin_area_km2",
        "watershed_hack_fitted_exponent",
        "watershed_hack_fitted_coefficient",
        "watershed_hack_fitted_log_rmse",
        "river_channel_morphology_model",
        "river_channel_cell_count",
        "river_channel_system_count",
        "navigable_channel_depth_cell_count",
        "floodplain_connected_channel_cell_count",
        "high_stream_power_channel_cell_count",
        "total_river_channel_length_km",
        "mean_river_channel_width_m",
        "mean_river_channel_depth_m",
        "mean_bankfull_discharge_m3_s",
        "mean_stream_power_index",
        "mean_channel_slope_index",
        "river_hydraulics_model",
        "river_hydraulic_cell_count",
        "river_hydraulic_reach_count",
        "mean_hydraulic_radius_m",
        "mean_flow_velocity_m_s",
        "mean_froude_number",
        "mean_bed_shear_stress_pa",
        "mean_manning_roughness_n",
        "mean_channel_capacity_index",
        "mean_hydraulic_navigability_index",
        "hydraulically_navigable_cell_count",
        "supercritical_flow_cell_count",
        "high_shear_stress_cell_count",
        "hydraulic_flow_regime_counts",
        "valid_river_sink_fraction",
        "river_downhill_realism_index",
        "tributary_merge_coherence_index",
        "delta_lowland_sediment_coast_index",
        "watershed_divide_alignment_index",
        "hydrology_realism_check_count",
        "hydrology_realism_pass_count",
        "hydrology_realism_pass_fraction",
        "mean_hydrology_realism_score",
        "mean_actual_evapotranspiration_mm_y",
        "mean_hydrologic_potential_evapotranspiration_mm_y",
        "mean_infiltration_mm_y",
        "mean_infiltration_capacity_index",
        "mean_hydrologic_water_balance_mm_y",
        "mean_water_budget_runoff_mm_y",
        "mean_hydrologic_deficit_mm_y",
        "mean_runoff_budget_residual_mm_y",
        "mean_abs_runoff_budget_residual_mm_y",
        "mean_runoff_budget_consistency_index",
        "mean_runoff_generation_fraction",
        "total_infiltration_km3_y",
        "total_actual_evapotranspiration_km3_y",
        "total_water_budget_runoff_km3_y",
        "total_land_precipitation_km3_y",
        "total_hydrologic_water_budget_residual_km3_y",
        "high_runoff_generation_cell_count",
        "water_budget_deficit_cell_count",
        "low_runoff_budget_consistency_cell_count",
        "hydrologic_budget_class_counts",
        "hydrologic_budget_region_count",
        "runoff_surplus_region_count",
        "water_deficit_region_count",
        "wetland_cell_count",
        "wetland_system_count",
        "wetland_area_km2",
        "wetland_area_fraction",
        "mean_wetland_extent_index",
        "mean_wetland_hydrology_index",
        "mean_wetland_soil_saturation_index",
        "mean_wetland_ecotone_index",
        "mean_wetland_connectivity_index",
        "mean_wetland_extent_index_over_wetlands",
        "wetland_type_counts",
        "mangrove_wetland_cell_count",
        "tidal_marsh_wetland_cell_count",
        "delta_wetland_cell_count",
        "floodplain_wetland_cell_count",
        "freshwater_swamp_cell_count",
        "river_capture_candidate_count",
        "high_river_capture_risk_cell_count",
        "mean_river_capture_risk",
        "max_river_capture_risk",
        "river_avulsion_candidate_count",
        "high_river_avulsion_risk_cell_count",
        "mean_river_avulsion_risk",
        "max_river_avulsion_risk",
        "river_network_instability_cell_count",
        "high_river_network_instability_cell_count",
        "mean_river_network_instability_index",
        "max_river_network_instability_index",
        "river_network_evolution_event_count",
        "river_reorganization_history_count",
        "river_reorganization_step_count",
        "mean_river_reorganization_risk_index",
        "mean_river_diversion_probability_index",
        "mean_river_reorganization_confidence_index",
        "total_river_divide_lowering_m",
        "total_river_sediment_reworked_m",
        "high_river_reorganization_pressure_count",
        "watershed_geometry_count",
        "largest_watershed_boundary_cell_count",
        "watershed_polygon_count",
        "largest_watershed_polygon_area_km2",
        "mean_watershed_polygon_area_error_fraction",
        "mean_watershed_compactness_index",
        "mean_watershed_geometry_quality",
        "mean_watershed_boundary_perimeter_km",
        "watershed_cell_edge_boundary_segment_count",
        "watershed_cell_edge_boundary_directed_segment_count",
        "watershed_with_cell_edge_boundary_count",
        "watershed_cell_edge_boundary_length_km",
        "mean_watershed_cell_edge_boundary_length_km",
        "mean_watershed_cell_edge_boundary_segment_quality",
        "coastal_feature_count",
        "coastal_bar_feature_count",
        "prograding_coastal_feature_count",
        "eroding_coastal_feature_count",
        "mean_coastal_migration_rate_m_y",
        "sedimentary_basin_count",
        "active_sedimentary_basin_count",
        "largest_sedimentary_basin_area_km2",
        "mean_sedimentary_basin_thickness_m",
        "sediment_transport_history_count",
        "sediment_transport_history_step_count",
        "active_sediment_transport_history_count",
        "sediment_transport_total_input_m",
        "sediment_transport_total_deposition_m",
        "sediment_transport_total_export_m",
        "sediment_transport_total_compaction_m",
        "sediment_transport_mean_final_fill_fraction",
        "sediment_transport_max_progradation_distance_km",
        "sediment_routing_history_count",
        "sediment_routing_step_count",
        "sediment_routing_cell_count",
        "sediment_routing_total_local_supply_m",
        "sediment_routing_total_deposition_m",
        "sediment_routing_total_export_m",
        "sediment_routing_total_sink_loss_m",
        "sediment_routing_total_path_length_km",
        "sediment_routing_mean_path_length_km",
        "sediment_routing_max_final_load_m",
        "sediment_routing_max_delivery_ratio",
        "stratigraphic_column_count",
        "stratigraphic_layer_count",
        "active_stratigraphic_column_count",
        "max_stratigraphic_layer_count",
        "mean_stratigraphic_thickness_m",
        "sequence_stratigraphy_history_count",
        "sequence_stratigraphy_step_count",
        "sequence_stratigraphy_event_count",
        "sequence_boundary_count",
        "transgressive_surface_count",
        "maximum_flooding_surface_count",
        "regressive_surface_count",
        "mean_sequence_accommodation_to_deposition_ratio",
        "mean_sequence_flooding_index",
        "spill_corrected_cell_count",
        "closed_basin_cell_count",
        "max_depression_depth_m",
        "settlement_count",
        "route_count",
        "trade_flow_count",
        "trade_total_volume_index",
        "interregional_trade_fraction",
        "mean_trade_friction",
        "political_region_count",
        "culture_region_model",
        "culture_region_count",
        "language_region_model",
        "language_region_count",
        "phonology_history_model",
        "cultural_site_model",
        "historical_event_model",
        "historical_era_count",
        "historical_event_count",
        "migration_event_count",
        "dynastic_change_count",
        "language_lineage_count",
        "population_region_model",
        "population_region_count",
        "estimated_world_population",
        "mean_population_pressure",
        "conflict_model",
        "population_history_model",
        "population_history_count",
        "population_history_step_count",
        "historical_final_population",
        "historical_peak_population_pressure",
        "max_population_decline_fraction",
        "economy_history_model",
        "economy_history_count",
        "economy_history_step_count",
        "historical_final_gross_output_index",
        "historical_final_treasury_index",
        "historical_total_tax_revenue_index",
        "historical_total_trade_revenue_index",
        "historical_total_war_cost_index",
        "historical_peak_army_capacity_population",
        "mean_historical_prosperity_index",
        "mean_historical_trade_dependency_index",
        "mean_historical_military_burden_index",
        "high_military_burden_economy_step_count",
        "demographic_agent_model",
        "individual_life_event_model",
        "plate_graph_node_count",
        "plate_graph_edge_count",
        "plate_graph_component_count",
        "plate_graph_boundary_cell_edge_count",
        "river_graph_node_count",
        "river_graph_edge_count",
        "river_graph_sink_count",
        "river_graph_component_count",
        "river_graph_total_channel_length_km",
        "watershed_graph_node_count",
        "watershed_graph_edge_count",
        "watershed_graph_component_count",
        "watershed_graph_boundary_edge_count",
        "watershed_graph_total_boundary_length_km",
        "trade_route_graph_node_count",
        "trade_route_graph_edge_count",
        "trade_route_graph_component_count",
        "interregional_trade_route_graph_edge_count",
        "trade_route_graph_total_volume_index",
        "political_region_graph_node_count",
        "political_region_graph_edge_count",
        "political_region_graph_component_count",
        "political_region_graph_border_segment_count",
        "political_region_graph_trade_edge_count",
        "political_region_graph_total_border_length_km",
        "conflict_count",
        "high_intensity_conflict_count",
        "mean_conflict_intensity",
        "mean_war_duration_years",
        "total_mobilized_population",
        "mean_conflict_logistics_strain_index",
        "mean_conflict_economic_disruption_index",
        "high_economic_disruption_conflict_count",
        "mean_conflict_casualty_rate",
        "max_conflict_casualty_rate",
        "dynasty_model",
        "logistics_exchange_model",
        "campaign_operations_model",
        "logistics_network_count",
        "logistics_route_link_count",
        "market_exchange_count",
        "interregional_market_exchange_count",
        "market_clearing_model",
        "route_capacity_constraint_count",
        "market_clearing_record_count",
        "market_agent_order_count",
        "market_price_iteration_count",
        "market_inventory_history_count",
        "market_inventory_step_count",
        "producer_market_order_count",
        "consumer_market_order_count",
        "constrained_market_exchange_count",
        "campaign_movement_count",
        "campaign_path_segment_count",
        "campaign_front_history_count",
        "tactical_engagement_count",
        "strategic_campaign_plan_count",
        "campaign_front_step_count",
        "tactical_engagement_step_count",
        "strategic_decision_point_count",
        "total_market_exchange_volume_index",
        "total_market_requested_volume_index",
        "total_market_cleared_volume_index",
        "total_market_unmet_demand_index",
        "total_endogenous_market_supply_index",
        "total_endogenous_market_demand_index",
        "total_campaign_mobilized_population",
        "total_campaign_path_length_km",
        "mean_logistics_transport_efficiency_index",
        "mean_logistics_resilience_index",
        "mean_market_access_index",
        "mean_market_disruption_risk_index",
        "mean_market_clearance_fraction",
        "mean_route_capacity_utilization_index",
        "mean_market_price_adjustment_index",
        "mean_market_rationing_index",
        "mean_market_equilibrium_residual_index",
        "mean_market_inventory_gap_index",
        "mean_market_learning_rate_index",
        "mean_market_inventory_pressure_index",
        "high_inventory_stress_market_count",
        "mean_campaign_travel_time_days",
        "mean_campaign_attrition_risk_index",
        "mean_campaign_operational_reach_index",
        "mean_campaign_path_length_km",
        "mean_campaign_path_terrain_cost_index",
        "mean_campaign_path_supply_loss_index",
        "mean_campaign_path_attrition_index",
        "mean_campaign_front_supply_integrity_index",
        "mean_campaign_front_control_index",
        "total_campaign_front_attrition_loss_population",
        "tactical_total_attrition_loss_population",
        "mean_tactical_counter_maneuver_index",
        "mean_tactical_front_pressure_index",
        "mean_tactical_supply_contest_index",
        "independent_counter_campaign_plan_count",
        "mean_counter_campaign_viability_index",
        "mean_strategic_plan_confidence_index",
        "mean_strategic_force_reserve_fraction",
        "high_attrition_campaign_count",
        "high_attrition_campaign_path_segment_count",
        "high_pressure_tactical_step_count",
        "high_escalation_strategic_plan_count",
        "household_cohort_count",
        "firm_agent_count",
        "demographic_agent_history_count",
        "demographic_agent_step_count",
        "individual_agent_count",
        "individual_life_event_count",
        "individual_birth_event_count",
        "individual_death_event_count",
        "individual_marriage_event_count",
        "property_transfer_event_count",
        "total_household_cohort_population",
        "total_firm_employment_capacity",
        "total_property_transfer_value_index",
        "mean_household_resilience_index",
        "mean_household_migration_propensity_index",
        "mean_household_consumption_pressure_index",
        "mean_firm_productivity_index",
        "mean_firm_market_dependency_index",
        "mean_firm_supply_chain_risk_index",
        "mean_demographic_vulnerability_index",
        "mean_individual_lifespan_years",
        "high_vulnerability_household_count",
        "ruler_genealogy_model",
        "dynasty_count",
        "dynastic_lineage_count",
        "dynasty_root_count",
        "dynasty_successor_link_count",
        "max_dynasty_lineage_depth",
        "mean_dynastic_continuity_index",
        "ruler_count",
        "named_ruler_dynasty_count",
        "ruler_marriage_alliance_count",
        "cadet_branch_count",
        "married_ruler_count",
        "max_ruler_lineage_depth",
        "mean_ruler_legitimacy_index",
        "mean_succession_crisis_risk",
        "mean_marriage_alliance_strength",
        "mean_cadet_branch_claim_strength",
        "territorial_snapshot_model",
        "territorial_snapshot_count",
        "snapshot_region_record_count",
        "snapshot_polygon_region_count",
        "mean_snapshot_fragmentation_index",
        "mean_snapshot_polygon_area_error_fraction",
        "mean_snapshot_compactness_index",
        "mean_snapshot_geometry_quality",
        "mean_snapshot_boundary_perimeter_km",
        "territorial_cell_edge_boundary_segment_count",
        "territorial_cell_edge_boundary_length_km",
        "snapshot_region_with_cell_edge_boundary_count",
        "mean_snapshot_cell_edge_boundary_segment_count",
        "mean_snapshot_cell_edge_boundary_length_km",
        "mean_snapshot_cell_edge_boundary_quality",
        "mean_historical_instability",
        "mean_cultural_continuity",
        "mean_language_change_rate",
        "mean_phonological_complexity",
        "mean_sound_shift_index",
        "mean_inherited_phonology_fraction",
        "phonological_history_count",
        "phonological_history_step_count",
        "phonological_rule_count",
        "phonological_rule_language_count",
        "max_phonological_shift_stage",
        "mean_phonological_rule_probability_index",
        "mean_phonological_rule_regularity_index",
        "mean_lexical_replacement_index",
        "mean_phonological_contact_influence_index",
        "mean_phonological_drift_index",
        "mean_language_prosodic_complexity_index",
        "mean_phonotactic_complexity_index",
        "lexical_correspondence_count",
        "lexical_correspondence_language_count",
        "lexical_diffusion_history_count",
        "lexical_diffusion_step_count",
        "lexical_diffusion_language_count",
        "mean_regular_correspondence_fraction",
        "mean_lexical_correspondence_replacement_index",
        "mean_lexical_prosodic_weight_index",
        "mean_lexical_diffusion_adoption_index",
        "mean_lexical_innovation_index",
        "mean_semantic_shift_index",
        "speaker_population_history_count",
        "speaker_population_step_count",
        "total_estimated_speaker_population",
        "mean_speaker_allophonic_variation_index",
        "mean_speaker_syllable_pressure_index",
        "mean_speaker_contact_index",
        "mean_speaker_population_adoption_index",
        "mean_speaker_phonetic_reduction_index",
        "mean_speaker_lexical_diffusion_pressure_index",
        "high_contact_speaker_history_count",
        "sacred_area_count",
        "ruin_count",
        "border_segment_count",
        "border_total_length_km",
        "natural_border_fraction",
        "largest_region_area_km2",
        "largest_culture_area_km2",
        "politically_assigned_land_fraction",
        "culturally_assigned_land_fraction",
        "linguistically_assigned_land_fraction",
        "top_settlement_score",
        "soil_diagnostic_cell_count",
        "soil_profile_count",
        "soil_horizon_count",
        "soil_profile_history_count",
        "soil_pedogenesis_step_count",
        "mean_soil_drainage_index",
        "mean_soil_moisture_index",
        "mean_soil_ph",
        "mean_soil_organic_matter_fraction",
        "mean_soil_salinity_index",
        "mean_soil_erodibility_index",
        "mean_soil_profile_development_index",
        "saline_soil_cell_fraction",
        "high_erodibility_soil_fraction",
        "waterlogged_soil_cell_fraction",
        "mean_soil_profile_depth_m",
        "mean_soil_horizon_count",
        "mean_topsoil_organic_matter_fraction",
        "mean_soil_weathering_index",
        "mean_soil_leaching_index",
        "mean_soil_bioturbation_index",
        "mature_soil_profile_fraction",
        "shallow_soil_profile_fraction",
        "total_soil_production_m",
        "total_soil_erosion_loss_m",
        "mean_pedogenic_weathering_index",
        "mean_pedogenic_leaching_index",
        "mean_pedogenic_bioturbation_index",
        "mean_horizon_differentiation_index",
        "mean_pedogenic_flux_index",
        "high_erosion_pedogenesis_count",
        "mean_sediment_thickness_m",
        "sediment_budget_production_m",
        "sediment_budget_deposition_m",
        "sediment_budget_export_m",
        "sediment_budget_residual_m",
        "sediment_delivery_ratio",
        "mean_orographic_factor",
        "mean_rain_shadow_factor",
        "rain_shadowed_land_fraction",
        "mean_humidity_transport_index",
        "mean_upwind_ocean_fetch_km",
        "mean_advected_moisture_factor",
        "atmospheric_cell_counts",
        "mean_surface_pressure_anomaly_hpa",
        "mean_vertical_velocity_index",
        "mean_wind_divergence_index",
        "mean_seasonal_wind_speed",
        "mean_seasonal_wind_reversal_index",
        "ascending_air_fraction",
        "mean_vapor_evaporation_mm_y",
        "mean_moisture_convergence_mm_y",
        "mean_orographic_rainout_mm_y",
        "mean_precipitation_recycling_fraction",
        "mean_vapor_deficit_mm_y",
        "mean_abs_vapor_budget_residual_mm_y",
        "mean_ocean_current_strength",
        "mean_ocean_current_temperature_c",
        "mean_ocean_current_moisture_factor",
        "ocean_current_cell_count",
        "ocean_current_system_count",
        "ocean_current_transport_edge_count",
        "ocean_current_transport_coverage_fraction",
        "ocean_current_total_transport_length_km",
        "ocean_current_total_area_km2",
        "mean_ocean_circulation_speed_index",
        "mean_ocean_current_transport_alignment",
        "mean_ocean_current_poleward_index",
        "mean_ocean_heat_transport_index",
        "mean_ocean_current_convergence_index",
        "mean_ocean_upwelling_index",
        "warm_ocean_current_cell_count",
        "cold_ocean_current_cell_count",
        "poleward_ocean_current_cell_count",
        "equatorward_ocean_current_cell_count",
        "high_ocean_upwelling_cell_count",
        "ocean_current_regime_counts",
        "ocean_current_system_class_counts",
        "mean_distance_to_marine_water_km",
        "mean_continentality_index",
        "max_continentality_index",
        "high_continentality_cell_count",
        "mean_oceanic_humidity_availability_index",
        "low_oceanic_humidity_availability_cell_count",
        "climate_continentality_region_count",
        "continental_core_region_count",
        "maritime_influence_region_count",
        "marine_influence_class_counts",
        "climate_seasonal_history_count",
        "climate_seasonal_step_count",
        "seasonal_humidity_regime_counts",
        "climate_class_count",
        "climate_class_counts",
        "climate_main_class_counts",
        "seasonal_aridity_cell_fraction",
        "mean_cell_monsoon_index",
        "mean_cell_seasonal_aridity_index",
        "climate_seasonal_total_precipitation_mm",
        "climate_seasonal_total_evaporation_mm",
        "climate_seasonal_total_moisture_convergence_mm",
        "climate_seasonal_total_humidity_export_mm",
        "climate_seasonal_total_vapor_deficit_mm",
        "climate_seasonal_mean_abs_residual_mm",
        "max_climate_humidity_storage_mm",
        "max_climate_monsoon_index",
        "climate_energy_balance_record_count",
        "mean_top_of_atmosphere_insolation_w_m2",
        "mean_seasonal_insolation_range_w_m2",
        "mean_orbital_insolation_variability_index",
        "mean_peak_seasonal_insolation_w_m2",
        "mean_low_seasonal_insolation_w_m2",
        "mean_orbital_distance_factor",
        "orbital_eccentricity",
        "mean_surface_albedo_index",
        "mean_absorbed_shortwave_w_m2",
        "mean_outgoing_longwave_w_m2",
        "mean_greenhouse_trapping_w_m2",
        "mean_net_radiative_balance_w_m2",
        "mean_abs_energy_balance_residual_c",
        "mean_climate_energy_stress_index",
        "high_climate_energy_stress_cell_count",
        "subtropical_dry_belt_index",
        "equatorial_ocean_humidity_index",
        "orographic_rain_shadow_index",
        "continentality_temperature_range_index",
        "cold_current_coastal_drying_index",
        "warm_current_moderation_index",
        "climate_realism_check_count",
        "climate_realism_pass_count",
        "climate_realism_pass_fraction",
        "mean_climate_realism_score",
        "mean_ice_thickness_m",
        "mean_glacial_erosion_m",
        "mean_ice_surface_mass_balance_m_y",
        "mean_basal_sliding_index",
        "mean_ice_velocity_m_y",
        "glaciated_land_fraction",
        "ice_sheet_count",
        "mean_ice_sheet_retreat_rate_m_y",
        "permafrost_cell_count",
        "permafrost_region_count",
        "mean_permafrost_extent_index",
        "mean_active_layer_depth_m",
        "mean_ground_ice_content_index",
        "continuous_permafrost_cell_count",
        "ice_cemented_permafrost_cell_count",
        "permafrost_class_counts",
        "ice_sheet_history_count",
        "ice_sheet_history_step_count",
        "ice_sheet_history_total_surface_balance_km3",
        "ice_sheet_history_total_dynamic_loss_km3",
        "ice_sheet_history_total_retreat_loss_km3",
        "ice_sheet_history_total_retreat_distance_km",
        "ice_sheet_history_peak_volume_km3",
        "ice_sheet_history_final_volume_km3",
        "ice_sheet_stability_history_count",
        "ice_sheet_stability_step_count",
        "ice_sheet_retreat_threshold_event_count",
        "high_ice_sheet_instability_count",
        "mean_ice_sheet_stability_index",
        "max_ice_sheet_stability_index",
        "mean_calving_susceptibility_index",
        "mean_grounding_line_instability_index",
        "ice_sheet_total_projected_calving_loss_km3",
        "ice_sheet_total_projected_grounding_line_retreat_km",
        "ice_flowline_history_count",
        "ice_flowline_step_count",
        "ice_flowline_cell_count",
        "ice_flowline_total_dynamic_flux_km3_y",
        "ice_flowline_total_dynamic_loss_km3_y",
        "ice_flowline_total_melt_loss_km3_y",
        "ice_flowline_total_glacial_erosion_m",
        "ice_flowline_total_path_length_km",
        "ice_flowline_mean_path_length_km",
        "ice_flowline_max_driving_stress_kpa",
        "ice_flowline_max_final_flux_km3_y",
        "ice_flowline_max_strain_heating_index",
        "moraine_deposition_cell_count",
        "mean_moraine_deposition_m",
        "mean_deglaciation_age_ka",
        "glacial_landform_cell_count",
        "glacial_landform_system_count",
        "glacial_landform_area_km2",
        "mean_glacial_landform_index",
        "mean_glacial_erosion_intensity_index",
        "mean_glacial_deposition_index",
        "mean_glacial_meltwater_index",
        "glacial_landform_type_counts",
        "ice_cap_landform_cell_count",
        "mountain_glacier_landform_cell_count",
        "fjord_landform_cell_count",
        "glacial_valley_landform_cell_count",
        "glacial_lake_landform_cell_count",
        "moraine_landform_cell_count",
        "biome_diagnostic_count",
        "biome_transition_zone_count",
        "high_fire_frequency_biome_count",
        "water_stressed_biome_cell_fraction",
        "biome_expected_match_fraction",
        "mean_potential_evapotranspiration_mm_y",
        "mean_climatic_water_deficit_mm_y",
        "mean_growing_season_months",
        "mean_fire_frequency_index",
        "mean_biome_confidence_index",
        "mean_ecotone_index",
        "biome_ecotone_cell_count",
        "biome_ecotone_region_count",
        "mean_biome_ecotone_confidence",
        "biome_ecotone_type_counts",
        "mangrove_ecotone_cell_count",
        "cloud_forest_ecotone_cell_count",
        "alpine_paramo_ecotone_cell_count",
        "desert_water_deficit_alignment_index",
        "forest_water_availability_index",
        "tundra_cold_altitude_index",
        "savanna_seasonality_index",
        "mangrove_warm_wet_coast_index",
        "biome_realism_check_count",
        "biome_realism_pass_count",
        "biome_realism_pass_fraction",
        "mean_biome_realism_score",
        "aquifer_resource_model",
        "aquifer_cell_count",
        "aquifer_system_count",
        "groundwater_recharge_cell_count",
        "groundwater_recharge_model",
        "high_productivity_aquifer_cell_count",
        "groundwater_stressed_cell_count",
        "total_groundwater_recharge_km3_y",
        "total_groundwater_recharge_source_infiltration_km3_y",
        "total_vadose_zone_retention_km3_y",
        "groundwater_recharge_mass_balance_residual_km3_y",
        "mean_groundwater_recharge_mm_y",
        "mean_aquifer_storage_index",
        "mean_aquifer_quality_index",
        "mean_aquifer_productivity_index",
        "mean_aquifer_extraction_risk_index",
        "groundwater_flow_model",
        "groundwater_flow_cell_count",
        "groundwater_flow_system_count",
        "groundwater_discharge_cell_count",
        "spring_candidate_cell_count",
        "baseflow_supported_river_cell_count",
        "total_groundwater_discharge_km3_y",
        "total_groundwater_lateral_flow_km3_y",
        "total_groundwater_internal_lateral_flow_km3_y",
        "total_groundwater_retained_storage_km3_y",
        "groundwater_flow_mass_balance_residual_km3_y",
        "total_groundwater_flow_balance_residual_km3_y",
        "mean_groundwater_gradient_index",
        "mean_groundwater_discharge_mm_y",
        "mean_spring_discharge_index",
        "mean_baseflow_support_index",
        "karst_cell_count",
        "karst_system_count",
        "mean_karst_potential_index",
        "mean_cave_development_index",
        "mean_subterranean_drainage_fraction",
        "limestone_karst_cell_fraction",
        "vegetation_succession_history_count",
        "vegetation_succession_step_count",
        "mean_primary_productivity_index",
        "mean_vegetation_biomass_index",
        "mean_species_richness_index",
        "mean_wildfire_spread_risk_index",
        "mean_ecosystem_disturbance_pressure_index",
        "high_wildfire_spread_risk_cell_count",
        "mature_vegetation_cell_fraction",
        "mean_forest_growth_index",
        "mean_fishery_productivity_index",
        "renewable_resource_record_count",
        "forest_growth_resource_count",
        "fishery_productivity_resource_count",
        "species_range_record_count",
        "species_range_cell_count",
        "terrestrial_species_range_count",
        "aquatic_species_range_count",
        "wetland_species_range_count",
        "high_endemism_species_range_count",
        "high_conservation_stress_species_range_count",
        "species_range_total_area_km2",
        "mean_species_habitat_suitability_index",
        "mean_species_endemism_index",
        "mean_species_composition_confidence_index",
        "wildfire_spread_history_count",
        "wildfire_disturbance_cell_count",
        "wildfire_spread_step_count",
        "high_wildfire_ignition_potential_cell_count",
        "high_wildfire_fuel_continuity_cell_count",
        "high_wildfire_firebreak_cell_count",
        "wildfire_total_burned_area_km2",
        "mean_wildfire_ignition_potential_index",
        "mean_wildfire_fuel_continuity_index",
        "mean_wildfire_wind_alignment_index",
        "mean_wildfire_firebreak_index",
        "resource_deposit_count",
        "metal_resource_deposit_count",
        "energy_resource_deposit_count",
        "agricultural_resource_deposit_count",
        "high_viability_resource_deposit_count",
        "resource_deposit_total_area_km2",
        "mean_resource_reserve_potential_index",
        "mean_resource_economic_viability_index",
        "mean_resource_geologic_confidence_index",
        "ore_genesis_system_count",
        "ore_genesis_cell_count",
        "ore_resource_deposit_count",
        "high_ore_genesis_potential_cell_count",
        "high_hydrothermal_alteration_cell_count",
        "high_metallogenic_fertility_cell_count",
        "high_placer_concentration_cell_count",
        "ore_genesis_total_area_km2",
        "mean_ore_genesis_potential_index",
        "mean_hydrothermal_alteration_index",
        "mean_metallogenic_fertility_index",
        "mean_ore_structural_control_index",
        "mean_placer_concentration_index",
        "sedimentary_resource_system_count",
        "petroleum_system_count",
        "coal_system_count",
        "gas_system_count",
        "evaporite_salt_system_count",
        "sedimentary_resource_system_cell_count",
        "sedimentary_resource_system_total_area_km2",
        "mean_petroleum_potential_index",
        "mean_gas_potential_index",
        "mean_coal_potential_index",
        "mean_evaporite_salt_potential_index",
        "mean_sedimentary_resource_confidence_index",
        "petroleum_migration_system_count",
        "petroleum_migration_cell_count",
        "petroleum_source_rock_cell_count",
        "petroleum_mature_source_cell_count",
        "petroleum_trap_cell_count",
        "high_petroleum_accumulation_cell_count",
        "petroleum_migration_total_area_km2",
        "mean_petroleum_source_rock_index",
        "mean_petroleum_maturation_index",
        "mean_petroleum_migration_path_index",
        "mean_petroleum_trap_integrity_index",
        "mean_petroleum_accumulation_index",
        "commodity_occurrence_count",
        "metallic_commodity_occurrence_count",
        "fuel_commodity_occurrence_count",
        "industrial_mineral_commodity_occurrence_count",
        "gemstone_commodity_occurrence_count",
        "geothermal_commodity_occurrence_count",
        "bioproductive_commodity_occurrence_count",
        "high_potential_commodity_occurrence_count",
        "commodity_occurrence_total_area_km2",
        "mean_commodity_occurrence_potential_index",
        "mean_commodity_occurrence_confidence_index",
        "land_use_zone_model",
        "agricultural_zone_count",
        "agricultural_zone_cell_count",
        "agricultural_zone_total_area_km2",
        "mean_agricultural_potential_index",
        "mining_zone_count",
        "mining_zone_cell_count",
        "mining_zone_total_area_km2",
        "mean_mining_potential_index",
        "natural_frontier_model",
        "natural_frontier_count",
        "natural_frontier_cell_count",
        "natural_frontier_border_segment_count",
        "natural_frontier_total_area_km2",
        "natural_frontier_total_length_km",
        "mean_natural_frontier_index",
        "mean_natural_frontier_barrier_score",
        "mountain_frontier_count",
        "river_frontier_count",
        "desert_frontier_count",
        "coastal_frontier_count",
        "ice_frontier_count",
        "dense_forest_frontier_count",
        "wetland_frontier_count",
        "large_settlement_water_access_index",
        "route_barrier_avoidance_index",
        "political_region_connectivity_index",
        "natural_border_alignment_index",
        "resource_geology_dependency_index",
        "worldbuilding_realism_model",
        "worldbuilding_realism_check_count",
        "worldbuilding_realism_pass_count",
        "worldbuilding_realism_pass_fraction",
        "mean_worldbuilding_realism_score",
        "river_downhill_fraction",
        "mountain_convergent_alignment",
        "trench_convergent_alignment",
        "oceanic_ridge_divergent_alignment",
        "volcanic_arc_trench_pairing",
        "transform_fault_linearity",
        "hypsometry_bimodality_index",
        "geology_realism_check_count",
        "geology_realism_pass_count",
        "geology_realism_pass_fraction",
        "mean_geology_realism_score",
        "calibration_check_count",
        "calibration_pass_count",
        "calibration_pass_fraction",
        "mean_calibration_score",
    ]:
        if key in summary:
            lines.append(f"- `{key}`: {summary[key]}")

    for section in [
        "boundary_counts",
        "crust_counts",
        "water_body_counts",
        "landform_counts",
        "soil_texture_counts",
        "soil_profile_class_counts",
        "cell_adjacency_edge_class_counts",
        "watershed_outlet_type_counts",
        "channel_morphology_class_counts",
        "navigability_class_counts",
        "port_site_type_counts",
        "route_corridor_type_counts",
        "reef_type_counts",
        "systems_tract_counts",
        "shoreline_trajectory_counts",
        "ice_sheet_stability_class_counts",
        "surface_albedo_regime_counts",
        "biome_counts",
        "biome_limiting_factor_counts",
        "aquifer_class_counts",
        "groundwater_flow_regime_counts",
        "vegetation_succession_stage_counts",
        "renewable_resource_type_counts",
        "species_guild_type_counts",
        "species_habitat_class_counts",
        "dominant_species_guild_counts",
        "wildfire_disturbance_regime_counts",
        "resource_counts",
        "resource_deposit_class_counts",
        "ore_genesis_system_type_counts",
        "sedimentary_resource_system_type_counts",
        "petroleum_migration_system_type_counts",
        "commodity_occurrence_type_counts",
        "commodity_occurrence_group_counts",
        "natural_frontier_type_counts",
    ]:
        counts = summary.get(section, {})
        if counts:
            lines.extend(["", f"## {section}", ""])
            for key, value in sorted(counts.items()):
                lines.append(f"- `{key}`: {value}")

    lines.extend(["", "## Backend", ""])
    for key, value in sorted(backend.items()):
        lines.append(f"- `{key}`: {value}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_svg_map(
    path: Path,
    world: dict[str, Any],
    *,
    width: int = 1600,
    height: int = 800,
    projection: str = "equirectangular",
    labels: bool = False,
    max_cells: int | None = None,
    contours: bool = True,
    contour_interval_m: float = 500.0,
) -> None:
    cells = world.get("cells", [])
    settlements = world.get("settlements", [])
    routes = world.get("routes", [])
    sacred_areas = world.get("sacred_areas", [])
    ruins = world.get("ruins", [])
    path.parent.mkdir(parents=True, exist_ok=True)
    projection = projection.lower().replace("_", "-")
    if projection not in {"equirectangular", "mollweide", "orthographic"}:
        raise ValueError(f"unknown projection: {projection}")

    palette = {
        "ocean": "#1f5f8b",
        "continental_shelf": "#2e8bb3",
        "lake": "#3c9fc2",
        "ice_cap": "#f1f7f5",
        "tundra": "#b9c6b0",
        "boreal_forest": "#466d55",
        "temperate_forest": "#2f7d4f",
        "temperate_grassland": "#9caf62",
        "mediterranean_scrub": "#b7a565",
        "cold_desert": "#c7b98e",
        "hot_desert": "#d8bb72",
        "savanna": "#c0a44e",
        "tropical_seasonal_forest": "#27824c",
        "tropical_rainforest": "#176b3b",
        "alpine": "#9c9f97",
        "wetland": "#527f73",
    }
    settlement_colors = {
        "river_city": "#f4f1d0",
        "port": "#f6c65b",
        "mining_town": "#d98559",
        "agricultural_town": "#d9e27d",
        "oasis": "#7ed6c4",
        "frontier_town": "#e8dfbd",
    }
    cell_by_id = {int(cell["id"]): cell for cell in cells if "id" in cell}

    def hex_to_rgb(value: str) -> tuple[int, int, int]:
        value = value.lstrip("#")
        return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))

    def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
        return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, channel)) for channel in rgb))

    def blend(color_a: str, color_b: str, amount: float) -> str:
        amount = max(0.0, min(1.0, amount))
        a = hex_to_rgb(color_a)
        b = hex_to_rgb(color_b)
        return rgb_to_hex(tuple(round(a[i] * (1.0 - amount) + b[i] * amount) for i in range(3)))

    def shade(color: str, factor: float) -> str:
        factor = max(0.0, min(2.0, factor))
        rgb = hex_to_rgb(color)
        if factor >= 1.0:
            return rgb_to_hex(tuple(round(channel + (255 - channel) * (factor - 1.0)) for channel in rgb))
        return rgb_to_hex(tuple(round(channel * factor) for channel in rgb))

    def elevation_color(elevation_m: float) -> str:
        if elevation_m < 120.0:
            return blend("#8ba66a", "#d2c080", max(0.0, elevation_m) / 120.0)
        if elevation_m < 900.0:
            return blend("#d2c080", "#9a875c", (elevation_m - 120.0) / 780.0)
        if elevation_m < 1900.0:
            return blend("#9a875c", "#80756a", (elevation_m - 900.0) / 1000.0)
        return blend("#80756a", "#eee8d0", min(1.0, (elevation_m - 1900.0) / 1800.0))

    relief_by_id: dict[int, float] = {}
    for cell in cells:
        try:
            cell_id = int(cell["id"])
        except (KeyError, TypeError, ValueError):
            continue
        neighbors = [cell_by_id.get(int(neighbor)) for neighbor in cell.get("neighbors", [])]
        elevations = [float(neighbor.get("elevation_m", 0.0)) for neighbor in neighbors if neighbor]
        if elevations:
            relief_by_id[cell_id] = max(0.0, float(cell.get("elevation_m", 0.0)) - sum(elevations) / len(elevations))
        else:
            relief_by_id[cell_id] = 0.0

    def terrain_style(cell: dict[str, Any]) -> tuple[str, str, str, float]:
        biome = str(cell.get("biome", "ocean"))
        landform = str(cell.get("landform", ""))
        elevation_m = float(cell.get("elevation_m", 0.0))
        water_depth_m = float(cell.get("water_depth_m", 0.0))
        relief = relief_by_id.get(int(cell.get("id", -1)), 0.0)
        if cell.get("is_water"):
            depth = max(0.0, water_depth_m)
            fill = blend("#71b9c9", "#153f67", min(1.0, depth / 4200.0))
            if str(cell.get("water_body_type", "")) == "continental_shelf":
                fill = blend(fill, "#74c5c7", 0.42)
            elif str(cell.get("water_body_type", "")) == "inland_sea":
                fill = blend(fill, "#4fa5bb", 0.30)
            reef_growth = float(cell.get("reef_growth_index", 0.0))
            if int(cell.get("reef_system_id", -1)) >= 0 or reef_growth >= 0.46:
                fill = blend(fill, "#8df0d2", 0.34 + 0.34 * min(1.0, reef_growth))
            stroke = "#82d0d2" if landform == "fjord" else fill
            return fill, stroke, "0.18", 0.94

        fill = blend(palette.get(biome, "#777777"), elevation_color(elevation_m), 0.46)
        aridity = float(cell.get("precipitation_mm_y", 0.0)) / max(1.0, (float(cell.get("temperature_c", 0.0)) + 8.0) * 31.0)
        if aridity < 0.45:
            fill = blend(fill, "#d8bf7a", 0.40)
        elif aridity > 1.15 and float(cell.get("temperature_c", 0.0)) > 12.0:
            fill = blend(fill, "#2f7651", 0.24)
        if float(cell.get("ice_thickness_m", 0.0)) > 80.0 or biome == "ice_cap":
            fill = blend(fill, "#f4f6ed", 0.78)
        if landform in {"mountain_belt", "volcanic_arc", "glacial_valley"}:
            fill = shade(fill, 0.84)
        elif landform in {"delta", "floodplain", "wetland"}:
            fill = blend(fill, "#6fa78f", 0.44)
        elif landform == "salt_flat":
            fill = blend(fill, "#ece6cf", 0.62)
        elif landform == "moraine":
            fill = blend(fill, "#8f9185", 0.50)

        relief_shade = 0.86 + 0.22 * min(1.0, relief / 1800.0)
        fill = shade(fill, relief_shade)
        contour = elevation_m > 950.0 and abs(elevation_m % 500.0) < 55.0
        if cell.get("is_river"):
            return fill, "#9bd3df", "0.42", 0.98
        if contour:
            return fill, "#f0e0ad", "0.36", 0.97
        if landform in {"delta", "alluvial_fan", "floodplain", "moraine", "glacial_valley"}:
            return fill, "#ead58c", "0.30", 0.97
        return fill, shade(fill, 0.72), "0.08", 0.96

    def project(lat: float, lon: float) -> tuple[float, float] | None:
        if projection == "equirectangular":
            return ((lon + 180.0) / 360.0 * width, (90.0 - lat) / 180.0 * height)
        lat_rad = math.radians(lat)
        lon_rad = math.radians(lon)
        if projection == "orthographic":
            cos_c = math.cos(lat_rad) * math.cos(lon_rad)
            if cos_c < 0.0:
                return None
            radius_px = min(width, height) * 0.47
            return (
                width * 0.5 + radius_px * math.cos(lat_rad) * math.sin(lon_rad),
                height * 0.5 - radius_px * math.sin(lat_rad),
            )
        theta = lat_rad
        for _ in range(8):
            denom = 2.0 + 2.0 * math.cos(2.0 * theta)
            if abs(denom) < 1.0e-9:
                break
            theta -= (2.0 * theta + math.sin(2.0 * theta) - math.pi * math.sin(lat_rad)) / denom
        x_norm = (2.0 * math.sqrt(2.0) / math.pi) * lon_rad * math.cos(theta)
        y_norm = math.sqrt(2.0) * math.sin(theta)
        return (
            width * (0.5 + x_norm / (4.0 * math.sqrt(2.0))),
            height * (0.5 - y_norm / (2.0 * math.sqrt(2.0))),
        )

    def projected_cell(cell: dict[str, Any]) -> tuple[float, float] | None:
        return project(float(cell.get("lat_deg", 0.0)), float(cell.get("lon_deg", 0.0)))

    render_cells = cells
    if max_cells is not None and max_cells > 0 and len(cells) > max_cells:
        stride = max(1, math.ceil(len(cells) / max_cells))
        render_cells = cells[::stride]
    render_cell_ids = {int(cell.get("id", -1)) for cell in render_cells}

    radius = max(0.7, min(3.2, (width * height / max(1, len(render_cells))) ** 0.5 * 0.23))
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" data-projection="{projection}" data-renderer="terrain-v1" data-contours="{str(contours).lower()}">',
        f"<title>{html.escape(str(world.get('name', 'magic-geo world')))} {projection} causal terrain map</title>",
        "<defs>",
        '<filter id="terrain-soften" x="-10%" y="-10%" width="120%" height="120%"><feGaussianBlur stdDeviation="0.08"/></filter>',
        "</defs>",
        '<rect width="100%" height="100%" fill="#173b56"/>',
    ]
    if projection == "orthographic":
        r = min(width, height) * 0.47
        lines.append(
            f'<circle cx="{width * 0.5:.2f}" cy="{height * 0.5:.2f}" r="{r:.2f}" '
            'fill="#173b56" stroke="#8fb6c6" stroke-width="1.2"/>'
        )

    for cell in render_cells:
        point = projected_cell(cell)
        if point is None:
            continue
        x, y = point
        fill, stroke, stroke_width, opacity = terrain_style(cell)
        lines.append(
            f'<circle class="terrain-cell" cx="{x:.2f}" cy="{y:.2f}" r="{radius:.2f}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{stroke_width}" opacity="{opacity:.2f}" filter="url(#terrain-soften)"/>'
        )

    if contours:
        contour_interval = max(50.0, float(contour_interval_m))
        land_elevations = [
            float(cell.get("elevation_m", 0.0))
            for cell in render_cells
            if not cell.get("is_water") and float(cell.get("elevation_m", 0.0)) > contour_interval
        ]
        if land_elevations:
            first_level = math.ceil(min(land_elevations) / contour_interval) * contour_interval
            last_level = math.floor(max(land_elevations) / contour_interval) * contour_interval
            contour_levels = [
                first_level + contour_interval * index
                for index in range(int(max(0.0, (last_level - first_level) / contour_interval)) + 1)
            ]
            lines.append(f'<g class="terrain-contours" data-contour-interval-m="{contour_interval:.0f}">')
            for cell in render_cells:
                try:
                    cell_id = int(cell["id"])
                except (KeyError, TypeError, ValueError):
                    continue
                if cell.get("is_water"):
                    continue
                elevation = float(cell.get("elevation_m", 0.0))
                point_a = projected_cell(cell)
                if point_a is None:
                    continue
                x1, y1 = point_a
                for neighbor_id_raw in cell.get("neighbors", []):
                    try:
                        neighbor_id = int(neighbor_id_raw)
                    except (TypeError, ValueError):
                        continue
                    if neighbor_id <= cell_id or neighbor_id not in render_cell_ids:
                        continue
                    neighbor = cell_by_id.get(neighbor_id)
                    if not neighbor or neighbor.get("is_water"):
                        continue
                    neighbor_elevation = float(neighbor.get("elevation_m", 0.0))
                    low = min(elevation, neighbor_elevation)
                    high = max(elevation, neighbor_elevation)
                    if high < contour_interval or high == low:
                        continue
                    crossed_levels = [level for level in contour_levels if low <= level <= high]
                    if not crossed_levels:
                        continue
                    point_b = projected_cell(neighbor)
                    if point_b is None:
                        continue
                    x2, y2 = point_b
                    if projection == "equirectangular" and abs(x1 - x2) > width * 0.55:
                        continue
                    for level in crossed_levels:
                        major = int(round(level / contour_interval)) % 2 == 0
                        stroke = "#f4e7b8" if major else "#c9b77e"
                        stroke_width = 0.62 if major else 0.38
                        opacity = 0.54 if major else 0.34
                        lines.append(
                            f'<line class="terrain-contour {"terrain-contour-major" if major else "terrain-contour-minor"}" '
                            f'data-elevation-m="{level:.0f}" x1="{x1:.2f}" y1="{y1:.2f}" '
                            f'x2="{x2:.2f}" y2="{y2:.2f}" stroke="{stroke}" '
                            f'stroke-width="{stroke_width:.2f}" stroke-opacity="{opacity:.2f}" '
                            'stroke-linecap="round"/>'
                        )
            lines.append("</g>")

    for route in routes:
        from_index = int(route.get("from", -1))
        to_index = int(route.get("to", -1))
        from_settlement = settlements[from_index] if 0 <= from_index < len(settlements) else None
        to_settlement = settlements[to_index] if 0 <= to_index < len(settlements) else None
        if not from_settlement or not to_settlement:
            continue
        a = cell_by_id.get(int(from_settlement["cell_id"]))
        b = cell_by_id.get(int(to_settlement["cell_id"]))
        if not a or not b:
            continue
        point_a = projected_cell(a)
        point_b = projected_cell(b)
        if point_a is None or point_b is None:
            continue
        x1, y1 = point_a
        x2, y2 = point_b
        if projection == "equirectangular" and abs(x1 - x2) > width * 0.55:
            continue
        color = "#f0d38a" if route.get("type") != "coastal_sea" else "#9bd3df"
        lines.append(
            f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
            f'stroke="{color}" stroke-width="1.15" stroke-opacity="0.78"/>'
        )

    for site in sacred_areas:
        cell = cell_by_id.get(int(site.get("cell_id", -1)))
        if not cell:
            continue
        point = projected_cell(cell)
        if point is None:
            continue
        x, y = point
        size = 4.0 + 3.0 * float(site.get("significance", 0.0))
        points = f"{x:.2f},{y - size:.2f} {x - size:.2f},{y + size:.2f} {x + size:.2f},{y + size:.2f}"
        lines.append(
            f'<polygon points="{points}" fill="#fff0a6" stroke="#6f4c1e" stroke-width="0.95" '
            f'stroke-opacity="0.9"><title>{html.escape(str(site.get("type", "sacred area")))}</title></polygon>'
        )

    for ruin in ruins:
        cell = cell_by_id.get(int(ruin.get("cell_id", -1)))
        if not cell:
            continue
        point = projected_cell(cell)
        if point is None:
            continue
        x, y = point
        size = 3.6 + 2.8 * float(ruin.get("significance", 0.0))
        lines.append(
            f'<rect x="{x - size / 2.0:.2f}" y="{y - size / 2.0:.2f}" width="{size:.2f}" height="{size:.2f}" '
            f'fill="#8b6d5c" stroke="#2b1f17" stroke-width="0.9" transform="rotate(45 {x:.2f} {y:.2f})">'
            f'<title>{html.escape(str(ruin.get("type", "ruin")))}</title></rect>'
        )

    for settlement in settlements:
        cell = cell_by_id.get(int(settlement.get("cell_id", -1)))
        if not cell:
            continue
        point = projected_cell(cell)
        if point is None:
            continue
        x, y = point
        color = settlement_colors.get(str(settlement.get("type", "frontier_town")), "#f0e6bd")
        size = 2.7 + 4.2 * float(settlement.get("score", 0.0))
        lines.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{size:.2f}" fill="{color}" '
            f'stroke="#2b1f17" stroke-width="1.15"/>'
        )

    if labels:
        labeled = sorted(settlements, key=lambda item: float(item.get("score", 0.0)), reverse=True)[:24]
        for settlement in labeled:
            cell = cell_by_id.get(int(settlement.get("cell_id", -1)))
            if not cell:
                continue
            point = projected_cell(cell)
            if point is None:
                continue
            x, y = point
            kind = str(settlement.get("type", "settlement")).replace("_", " ").title()
            text = html.escape(f"{kind} {settlement.get('id', '')}".strip())
            lines.append(
                f'<text x="{x + 7.0:.2f}" y="{y - 7.0:.2f}" font-family="serif" font-size="10" '
                f'fill="#f7f0cf" stroke="#1b2430" stroke-width="2.4" paint-order="stroke">{text}</text>'
            )

    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_raster_map(
    path: Path,
    world: dict[str, Any],
    *,
    width: int = 1600,
    height: int = 800,
    projection: str = "equirectangular",
    max_cells: int | None = None,
    texture: bool = True,
) -> None:
    """Write a dependency-free PPM raster map from generated causal fields."""
    cells = world.get("cells", [])
    settlements = world.get("settlements", [])
    routes = world.get("routes", [])
    path.parent.mkdir(parents=True, exist_ok=True)
    projection = projection.lower().replace("_", "-")
    if projection not in {"equirectangular", "mollweide", "orthographic"}:
        raise ValueError(f"unknown projection: {projection}")

    palette: dict[str, tuple[int, int, int]] = {
        "ocean": (31, 95, 139),
        "continental_shelf": (55, 145, 178),
        "lake": (64, 160, 194),
        "ice_cap": (242, 247, 245),
        "tundra": (185, 198, 176),
        "boreal_forest": (70, 109, 85),
        "temperate_forest": (47, 125, 79),
        "temperate_grassland": (156, 175, 98),
        "mediterranean_scrub": (183, 165, 101),
        "cold_desert": (199, 185, 142),
        "hot_desert": (216, 187, 114),
        "savanna": (192, 164, 78),
        "tropical_seasonal_forest": (39, 130, 76),
        "tropical_rainforest": (23, 107, 59),
        "alpine": (156, 159, 151),
        "wetland": (82, 127, 115),
    }
    cell_by_id = {int(cell["id"]): cell for cell in cells if "id" in cell}

    def clamp_channel(value: float) -> int:
        return max(0, min(255, int(round(value))))

    def blend_rgb(a: tuple[int, int, int], b: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
        amount = max(0.0, min(1.0, amount))
        return tuple(clamp_channel(a[i] * (1.0 - amount) + b[i] * amount) for i in range(3))

    def shade_rgb(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
        factor = max(0.0, min(2.0, factor))
        if factor >= 1.0:
            return tuple(clamp_channel(channel + (255 - channel) * (factor - 1.0)) for channel in color)
        return tuple(clamp_channel(channel * factor) for channel in color)

    def elevation_rgb(elevation_m: float) -> tuple[int, int, int]:
        if elevation_m < 120.0:
            return blend_rgb((139, 166, 106), (210, 192, 128), max(0.0, elevation_m) / 120.0)
        if elevation_m < 900.0:
            return blend_rgb((210, 192, 128), (154, 135, 92), (elevation_m - 120.0) / 780.0)
        if elevation_m < 1900.0:
            return blend_rgb((154, 135, 92), (128, 117, 106), (elevation_m - 900.0) / 1000.0)
        return blend_rgb((128, 117, 106), (238, 232, 208), min(1.0, (elevation_m - 1900.0) / 1800.0))

    def cell_noise(cell_id: int) -> float:
        value = (cell_id * 1103515245 + 12345) & 0x7FFFFFFF
        value ^= (value >> 11)
        return (value & 0xFFFF) / 65535.0

    relief_by_id: dict[int, float] = {}
    for cell in cells:
        try:
            cell_id = int(cell["id"])
        except (KeyError, TypeError, ValueError):
            continue
        neighbors = [cell_by_id.get(int(neighbor)) for neighbor in cell.get("neighbors", [])]
        elevations = [float(neighbor.get("elevation_m", 0.0)) for neighbor in neighbors if neighbor]
        if elevations:
            relief_by_id[cell_id] = max(0.0, float(cell.get("elevation_m", 0.0)) - sum(elevations) / len(elevations))
        else:
            relief_by_id[cell_id] = 0.0

    def terrain_rgb(cell: dict[str, Any]) -> tuple[int, int, int]:
        cell_id = int(cell.get("id", -1))
        biome = str(cell.get("biome", "ocean"))
        landform = str(cell.get("landform", ""))
        elevation_m = float(cell.get("elevation_m", 0.0))
        relief = relief_by_id.get(cell_id, 0.0)
        if cell.get("is_water"):
            depth = max(0.0, float(cell.get("water_depth_m", 0.0)))
            color = blend_rgb((113, 185, 201), (21, 63, 103), min(1.0, depth / 4200.0))
            water_body = str(cell.get("water_body_type", ""))
            if water_body == "continental_shelf":
                color = blend_rgb(color, (116, 197, 199), 0.45)
            elif water_body == "inland_sea":
                color = blend_rgb(color, (79, 165, 187), 0.32)
            elif water_body in {"fresh_lake", "saline_basin"}:
                color = blend_rgb(color, (94, 184, 205), 0.25)
            reef_growth = float(cell.get("reef_growth_index", 0.0))
            if int(cell.get("reef_system_id", -1)) >= 0 or reef_growth >= 0.46:
                color = blend_rgb(color, (141, 240, 210), 0.34 + 0.34 * min(1.0, reef_growth))
            current = float(cell.get("ocean_current_moisture_factor", 1.0))
            color = shade_rgb(color, 0.92 + 0.10 * max(0.0, min(1.0, current - 0.6)))
            return color

        color = blend_rgb(palette.get(biome, (119, 119, 119)), elevation_rgb(elevation_m), 0.48)
        pet = max(1.0, (float(cell.get("temperature_c", 0.0)) + 8.0) * 31.0)
        aridity = float(cell.get("precipitation_mm_y", 0.0)) / pet
        sediment = min(1.0, float(cell.get("sediment_thickness_m", 0.0)) / 8.0)
        if aridity < 0.45:
            color = blend_rgb(color, (216, 191, 122), 0.40)
        elif aridity > 1.15 and float(cell.get("temperature_c", 0.0)) > 12.0:
            color = blend_rgb(color, (47, 118, 81), 0.24)
        if sediment > 0.10 and landform in {"delta", "floodplain", "alluvial_fan", "coastal_plain"}:
            color = blend_rgb(color, (117, 157, 104), 0.18 + 0.22 * sediment)
        if float(cell.get("ice_thickness_m", 0.0)) > 80.0 or biome == "ice_cap":
            color = blend_rgb(color, (244, 246, 237), 0.78)
        if landform in {"mountain_belt", "volcanic_arc", "glacial_valley"}:
            color = shade_rgb(color, 0.82)
        elif landform in {"delta", "floodplain", "wetland"}:
            color = blend_rgb(color, (111, 167, 143), 0.42)
        elif landform == "salt_flat":
            color = blend_rgb(color, (236, 230, 207), 0.62)
        elif landform == "moraine":
            color = blend_rgb(color, (143, 145, 133), 0.50)

        if texture:
            noise = cell_noise(cell_id)
            relief_factor = min(1.0, relief / 1800.0)
            erosion_factor = min(1.0, float(cell.get("erosion_rate", 0.0)) / 18.0)
            color = shade_rgb(color, 0.88 + 0.20 * relief_factor + 0.08 * erosion_factor + 0.10 * (noise - 0.5))
        return color

    def project(lat: float, lon: float) -> tuple[float, float] | None:
        if projection == "equirectangular":
            return ((lon + 180.0) / 360.0 * width, (90.0 - lat) / 180.0 * height)
        lat_rad = math.radians(lat)
        lon_rad = math.radians(lon)
        if projection == "orthographic":
            cos_c = math.cos(lat_rad) * math.cos(lon_rad)
            if cos_c < 0.0:
                return None
            radius_px = min(width, height) * 0.47
            return (
                width * 0.5 + radius_px * math.cos(lat_rad) * math.sin(lon_rad),
                height * 0.5 - radius_px * math.sin(lat_rad),
            )
        theta = lat_rad
        for _ in range(8):
            denom = 2.0 + 2.0 * math.cos(2.0 * theta)
            if abs(denom) < 1.0e-9:
                break
            theta -= (2.0 * theta + math.sin(2.0 * theta) - math.pi * math.sin(lat_rad)) / denom
        x_norm = (2.0 * math.sqrt(2.0) / math.pi) * lon_rad * math.cos(theta)
        y_norm = math.sqrt(2.0) * math.sin(theta)
        return (
            width * (0.5 + x_norm / (4.0 * math.sqrt(2.0))),
            height * (0.5 - y_norm / (2.0 * math.sqrt(2.0))),
        )

    def projected_cell(cell: dict[str, Any]) -> tuple[float, float] | None:
        return project(float(cell.get("lat_deg", 0.0)), float(cell.get("lon_deg", 0.0)))

    def put_pixel(pixels: bytearray, x: int, y: int, color: tuple[int, int, int], alpha: float = 1.0) -> None:
        if x < 0 or x >= width or y < 0 or y >= height:
            return
        index = (y * width + x) * 3
        if alpha >= 1.0:
            pixels[index:index + 3] = bytes(color)
            return
        alpha = max(0.0, min(1.0, alpha))
        for offset, channel in enumerate(color):
            pixels[index + offset] = clamp_channel(pixels[index + offset] * (1.0 - alpha) + channel * alpha)

    def draw_disc(
        pixels: bytearray,
        cx: float,
        cy: float,
        radius: float,
        color: tuple[int, int, int],
        alpha: float = 1.0,
    ) -> None:
        radius = max(0.5, radius)
        min_x = max(0, int(math.floor(cx - radius)))
        max_x = min(width - 1, int(math.ceil(cx + radius)))
        min_y = max(0, int(math.floor(cy - radius)))
        max_y = min(height - 1, int(math.ceil(cy + radius)))
        radius_sq = radius * radius
        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                dx = x + 0.5 - cx
                dy = y + 0.5 - cy
                distance_sq = dx * dx + dy * dy
                if distance_sq <= radius_sq:
                    edge = max(0.0, min(1.0, 1.0 - (distance_sq / radius_sq)))
                    put_pixel(pixels, x, y, color, alpha * (0.70 + 0.30 * edge))

    def draw_line(
        pixels: bytearray,
        a: tuple[float, float],
        b: tuple[float, float],
        color: tuple[int, int, int],
        radius: float,
        alpha: float,
    ) -> None:
        x1, y1 = a
        x2, y2 = b
        if projection == "equirectangular" and abs(x1 - x2) > width * 0.55:
            return
        steps = max(1, int(max(abs(x2 - x1), abs(y2 - y1))))
        for step in range(steps + 1):
            t = step / steps
            draw_disc(pixels, x1 * (1.0 - t) + x2 * t, y1 * (1.0 - t) + y2 * t, radius, color, alpha)

    render_cells = cells
    if max_cells is not None and max_cells > 0 and len(cells) > max_cells:
        stride = max(1, math.ceil(len(cells) / max_cells))
        render_cells = cells[::stride]

    pixels = bytearray((23, 59, 86) * (width * height))
    if projection == "orthographic":
        center_x = width * 0.5
        center_y = height * 0.5
        radius_px = min(width, height) * 0.47
        for y in range(height):
            for x in range(width):
                dx = x + 0.5 - center_x
                dy = y + 0.5 - center_y
                if dx * dx + dy * dy > radius_px * radius_px:
                    put_pixel(pixels, x, y, (12, 25, 37))

    radius = max(1.0, min(18.0, (width * height / max(1, len(render_cells))) ** 0.5 * 0.48))
    for cell in render_cells:
        point = projected_cell(cell)
        if point is None:
            continue
        x, y = point
        draw_disc(pixels, x, y, radius, terrain_rgb(cell), 0.96)

    for route in routes:
        from_index = int(route.get("from", -1))
        to_index = int(route.get("to", -1))
        from_settlement = settlements[from_index] if 0 <= from_index < len(settlements) else None
        to_settlement = settlements[to_index] if 0 <= to_index < len(settlements) else None
        if not from_settlement or not to_settlement:
            continue
        a = cell_by_id.get(int(from_settlement["cell_id"]))
        b = cell_by_id.get(int(to_settlement["cell_id"]))
        if not a or not b:
            continue
        point_a = projected_cell(a)
        point_b = projected_cell(b)
        if point_a is None or point_b is None:
            continue
        color = (240, 211, 138) if route.get("type") != "coastal_sea" else (155, 211, 223)
        draw_line(pixels, point_a, point_b, color, max(0.8, radius * 0.17), 0.70)

    for settlement in settlements:
        cell = cell_by_id.get(int(settlement.get("cell_id", -1)))
        if not cell:
            continue
        point = projected_cell(cell)
        if point is None:
            continue
        size = max(1.5, min(8.0, radius * (0.28 + 0.50 * float(settlement.get("score", 0.0)))))
        draw_disc(pixels, point[0], point[1], size + 1.0, (35, 31, 23), 0.92)
        draw_disc(pixels, point[0], point[1], size, (242, 221, 159), 0.95)

    header = (
        f"P6\n# magic-geo raster-terrain-v1 projection={projection} texture={str(texture).lower()}\n"
        f"{width} {height}\n255\n"
    ).encode("ascii")
    path.write_bytes(header + bytes(pixels))
