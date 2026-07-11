#pragma once

#include "core.hpp"

#include <vector>

namespace magic_geo::detail {

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

}  // namespace magic_geo::detail
