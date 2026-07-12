#include "internal.hpp"

namespace magic_geo::detail {

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

std::string summary_with_crust_material_shadow_json(
    std::string summary,
    const std::vector<CrustMaterialShadowStep>& history
) {
    if (summary.size() < 2 || summary.front() != '{' || summary.back() != '}') {
        throw std::runtime_error(
            "crust material shadow summary extension requires a JSON object"
        );
    }
    summary.pop_back();
    bool first = summary.size() == 1;

    std::uint64_t total_opening_packet_count = 0;
    std::uint64_t total_transported_packet_count = 0;
    std::uint64_t total_closing_packet_count = 0;
    std::uint64_t total_source_adjustment_count = 0;
    std::uint64_t total_sink_adjustment_count = 0;
    std::uint64_t maximum_opening_packet_count_per_step = 0;
    std::uint64_t maximum_transported_packet_count_per_step = 0;
    std::uint64_t maximum_closing_packet_count_per_step = 0;
    std::uint64_t maximum_source_adjustment_count_per_step = 0;
    std::uint64_t maximum_sink_adjustment_count_per_step = 0;
    double cumulative_unresolved_source_mass_kg = 0.0;
    double cumulative_unresolved_sink_mass_kg = 0.0;
    double maximum_absolute_transport_raw_residual_kg = 0.0;
    double maximum_closing_scalar_relative_residual = 0.0;
    double maximum_absolute_adjustment_reconciliation_residual_kg = 0.0;

    for (const CrustMaterialShadowStep& step : history) {
        const std::uint64_t opening_packet_count =
            static_cast<std::uint64_t>(step.opening_packet_count);
        const std::uint64_t transported_packet_count =
            static_cast<std::uint64_t>(step.transported_packet_count);
        const std::uint64_t closing_packet_count =
            static_cast<std::uint64_t>(step.closing_packet_count);
        const std::uint64_t source_adjustment_count =
            static_cast<std::uint64_t>(
                step.unresolved_source_adjustment_count
            );
        const std::uint64_t sink_adjustment_count =
            static_cast<std::uint64_t>(
                step.unresolved_sink_adjustment_count
            );
        total_opening_packet_count += opening_packet_count;
        total_transported_packet_count += transported_packet_count;
        total_closing_packet_count += closing_packet_count;
        total_source_adjustment_count += source_adjustment_count;
        total_sink_adjustment_count += sink_adjustment_count;
        maximum_opening_packet_count_per_step = std::max(
            maximum_opening_packet_count_per_step,
            opening_packet_count
        );
        maximum_transported_packet_count_per_step = std::max(
            maximum_transported_packet_count_per_step,
            transported_packet_count
        );
        maximum_closing_packet_count_per_step = std::max(
            maximum_closing_packet_count_per_step,
            closing_packet_count
        );
        maximum_source_adjustment_count_per_step = std::max(
            maximum_source_adjustment_count_per_step,
            source_adjustment_count
        );
        maximum_sink_adjustment_count_per_step = std::max(
            maximum_sink_adjustment_count_per_step,
            sink_adjustment_count
        );
        cumulative_unresolved_source_mass_kg +=
            step.unresolved_source_mass_kg;
        cumulative_unresolved_sink_mass_kg +=
            step.unresolved_sink_mass_kg;
        maximum_absolute_transport_raw_residual_kg = std::max(
            maximum_absolute_transport_raw_residual_kg,
            std::abs(step.shadow_minus_raw_transport_mass_kg)
        );
        maximum_closing_scalar_relative_residual = std::max(
            maximum_closing_scalar_relative_residual,
            std::abs(step.post_scalar_mirror_residual_kg) /
                std::max(1.0, std::abs(step.closing_scalar_mass_kg))
        );
        maximum_absolute_adjustment_reconciliation_residual_kg = std::max(
            maximum_absolute_adjustment_reconciliation_residual_kg,
            std::abs(step.ordered_adjustment_reconciliation_residual_kg)
        );
    }

    const std::uint64_t total_packet_count =
        total_opening_packet_count +
        total_transported_packet_count +
        total_closing_packet_count;
    const std::uint64_t maximum_packet_count_per_table = std::max({
        maximum_opening_packet_count_per_step,
        maximum_transported_packet_count_per_step,
        maximum_closing_packet_count_per_step,
    });
    const std::uint64_t total_adjustment_count =
        total_source_adjustment_count + total_sink_adjustment_count;
    const std::uint64_t maximum_adjustment_count_per_table = std::max(
        maximum_source_adjustment_count_per_step,
        maximum_sink_adjustment_count_per_step
    );
    constexpr int mass_precision =
        std::numeric_limits<double>::max_digits10;
    add_u64(summary, first, "crust_material_shadow_history_step_count",
        static_cast<std::uint64_t>(history.size()));
    add_u64(summary, first, "total_crust_material_shadow_packet_count",
        total_packet_count);
    add_u64(summary, first,
        "maximum_crust_material_shadow_packet_count_per_table",
        maximum_packet_count_per_table);
    add_u64(summary, first,
        "total_crust_material_shadow_opening_packet_count",
        total_opening_packet_count);
    add_u64(summary, first,
        "total_crust_material_shadow_transported_packet_count",
        total_transported_packet_count);
    add_u64(summary, first,
        "total_crust_material_shadow_closing_packet_count",
        total_closing_packet_count);
    add_u64(summary, first,
        "maximum_crust_material_shadow_opening_packet_count_per_step",
        maximum_opening_packet_count_per_step);
    add_u64(summary, first,
        "maximum_crust_material_shadow_transported_packet_count_per_step",
        maximum_transported_packet_count_per_step);
    add_u64(summary, first,
        "maximum_crust_material_shadow_closing_packet_count_per_step",
        maximum_closing_packet_count_per_step);
    add_u64(summary, first, "total_crust_material_shadow_adjustment_count",
        total_adjustment_count);
    add_u64(summary, first,
        "maximum_crust_material_shadow_adjustment_count_per_table",
        maximum_adjustment_count_per_table);
    add_u64(summary, first,
        "total_crust_material_shadow_unresolved_source_adjustment_count",
        total_source_adjustment_count);
    add_u64(summary, first,
        "total_crust_material_shadow_unresolved_sink_adjustment_count",
        total_sink_adjustment_count);
    add_double(summary, first,
        "cumulative_crust_material_shadow_unresolved_source_mass_kg",
        cumulative_unresolved_source_mass_kg, mass_precision);
    add_double(summary, first,
        "cumulative_crust_material_shadow_unresolved_sink_mass_kg",
        cumulative_unresolved_sink_mass_kg, mass_precision);
    add_double(summary, first,
        "maximum_absolute_crust_material_shadow_transport_raw_residual_kg",
        maximum_absolute_transport_raw_residual_kg, mass_precision);
    add_double(summary, first,
        "maximum_crust_material_shadow_closing_scalar_relative_residual",
        maximum_closing_scalar_relative_residual, mass_precision);
    add_double(summary, first,
        "maximum_absolute_crust_material_shadow_adjustment_reconciliation_residual_kg",
        maximum_absolute_adjustment_reconciliation_residual_kg,
        mass_precision);
    summary += "}";
    return summary;
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
    std::uint64_t total_crust_overlap_sparse_edge_count = 0;
    std::uint64_t total_crust_mixed_destination_count = 0;
    int maximum_crust_coverage_multiplicity = 0;
    int maximum_crust_coverage_arrangement_line_count = 0;
    int maximum_crust_coverage_arrangement_fragment_count = 0;
    double maximum_crust_source_area_closure_error_km2 = 0.0;
    double maximum_crust_source_area_relative_closure_error = 0.0;
    double maximum_crust_destination_partition_closure_error_km2 = 0.0;
    double total_crust_uncovered_gap_area_km2 = 0.0;
    double total_crust_overlap_excess_area_km2 = 0.0;
    double maximum_crust_transport_inventory_relative_closure_error = 0.0;
    double cumulative_absolute_tectonic_process_crust_volume_change_km3 = 0.0;
    double net_tectonic_process_crust_volume_change_km3 = 0.0;
    double cumulative_absolute_tectonic_process_density_weighted_crust_volume_change_g_cm3_km3 = 0.0;
    double net_tectonic_process_density_weighted_crust_volume_change_g_cm3_km3 = 0.0;
    double cumulative_absolute_tectonic_process_crust_age_volume_moment_change_km3_ma = 0.0;
    double net_tectonic_process_crust_age_volume_moment_change_km3_ma = 0.0;
    int total_tectonic_process_reason_record_count = 0;
    int active_tectonic_process_reason_record_count = 0;
    double maximum_tectonic_process_attribution_relative_closure_residual = 0.0;
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
        const CrustTransportPlan& transport = step.transport_plan;
        total_crust_overlap_sparse_edge_count += transport.source_cell_ids.size();
        total_crust_mixed_destination_count += static_cast<std::uint64_t>(
            std::count_if(
                transport.contributor_count_by_cell.begin(),
                transport.contributor_count_by_cell.end(),
                [](int contributor_count) { return contributor_count > 1; }
            )
        );
        if (!transport.maximum_coverage_multiplicity_by_cell.empty()) {
            maximum_crust_coverage_multiplicity = std::max(
                maximum_crust_coverage_multiplicity,
                *std::max_element(
                    transport.maximum_coverage_multiplicity_by_cell.begin(),
                    transport.maximum_coverage_multiplicity_by_cell.end()
                )
            );
        }
        maximum_crust_coverage_arrangement_line_count = std::max(
            maximum_crust_coverage_arrangement_line_count,
            transport.maximum_coverage_arrangement_line_count
        );
        maximum_crust_coverage_arrangement_fragment_count = std::max(
            maximum_crust_coverage_arrangement_fragment_count,
            transport.maximum_coverage_arrangement_fragment_count
        );
        maximum_crust_source_area_closure_error_km2 = std::max(
            maximum_crust_source_area_closure_error_km2,
            transport.maximum_source_area_closure_error_km2
        );
        maximum_crust_source_area_relative_closure_error = std::max(
            maximum_crust_source_area_relative_closure_error,
            transport.maximum_source_area_relative_closure_error
        );
        maximum_crust_destination_partition_closure_error_km2 = std::max(
            maximum_crust_destination_partition_closure_error_km2,
            transport.maximum_destination_partition_closure_error_km2
        );
        total_crust_uncovered_gap_area_km2 +=
            transport.global_uncovered_gap_area_km2;
        total_crust_overlap_excess_area_km2 +=
            transport.global_overlap_excess_area_km2;
        maximum_crust_transport_inventory_relative_closure_error = std::max({
            maximum_crust_transport_inventory_relative_closure_error,
            std::abs(
                transport.transported_crust_volume_km3 -
                transport.initial_crust_volume_km3
            ) / std::max(1.0, std::abs(transport.initial_crust_volume_km3)),
            std::abs(
                transport.transported_density_weighted_crust_volume -
                transport.initial_density_weighted_crust_volume
            ) / std::max(
                1.0,
                std::abs(transport.initial_density_weighted_crust_volume)
            ),
            std::abs(
                transport.transported_crust_age_volume_moment -
                transport.initial_crust_age_volume_moment
            ) / std::max(
                1.0,
                std::abs(transport.initial_crust_age_volume_moment)
            ),
        });
        const double process_crust_volume_change_km3 =
            step.post_process_crust_volume_km3 -
            transport.transported_crust_volume_km3;
        const double process_density_weighted_crust_volume_change_g_cm3_km3 =
            step.post_process_density_weighted_crust_volume -
            transport.transported_density_weighted_crust_volume;
        const double process_crust_age_volume_moment_change_km3_ma =
            step.post_process_crust_age_volume_moment -
            transport.transported_crust_age_volume_moment;
        double attributed_process_crust_volume_change_km3 = 0.0;
        double attributed_process_density_weighted_crust_volume_change = 0.0;
        double attributed_process_crust_age_volume_moment_change = 0.0;
        for (const CrustProcessInventoryDelta& reason :
             step.process_inventory_delta_by_reason) {
            total_tectonic_process_reason_record_count++;
            active_tectonic_process_reason_record_count +=
                reason.triggered_cell_count > 0 ? 1 : 0;
            attributed_process_crust_volume_change_km3 +=
                reason.crust_volume_km3;
            attributed_process_density_weighted_crust_volume_change +=
                reason.density_weighted_crust_volume;
            attributed_process_crust_age_volume_moment_change +=
                reason.crust_age_volume_moment_km3_ma;
        }
        maximum_tectonic_process_attribution_relative_closure_residual =
            std::max({
                maximum_tectonic_process_attribution_relative_closure_residual,
                std::abs(
                    process_crust_volume_change_km3 -
                    attributed_process_crust_volume_change_km3
                ) / std::max(1.0, std::abs(process_crust_volume_change_km3)),
                std::abs(
                    process_density_weighted_crust_volume_change_g_cm3_km3 -
                    attributed_process_density_weighted_crust_volume_change
                ) / std::max(
                    1.0,
                    std::abs(
                        process_density_weighted_crust_volume_change_g_cm3_km3
                    )
                ),
                std::abs(
                    process_crust_age_volume_moment_change_km3_ma -
                    attributed_process_crust_age_volume_moment_change
                ) / std::max(
                    1.0,
                    std::abs(process_crust_age_volume_moment_change_km3_ma)
                ),
            });
        cumulative_absolute_tectonic_process_crust_volume_change_km3 +=
            std::abs(process_crust_volume_change_km3);
        net_tectonic_process_crust_volume_change_km3 +=
            process_crust_volume_change_km3;
        cumulative_absolute_tectonic_process_density_weighted_crust_volume_change_g_cm3_km3 +=
            std::abs(process_density_weighted_crust_volume_change_g_cm3_km3);
        net_tectonic_process_density_weighted_crust_volume_change_g_cm3_km3 +=
            process_density_weighted_crust_volume_change_g_cm3_km3;
        cumulative_absolute_tectonic_process_crust_age_volume_moment_change_km3_ma +=
            std::abs(process_crust_age_volume_moment_change_km3_ma);
        net_tectonic_process_crust_age_volume_moment_change_km3_ma +=
            process_crust_age_volume_moment_change_km3_ma;
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
    add_u64(out, first, "total_crust_overlap_sparse_edge_count",
        total_crust_overlap_sparse_edge_count);
    add_u64(out, first, "total_crust_mixed_destination_count",
        total_crust_mixed_destination_count);
    add_int(out, first, "maximum_crust_coverage_multiplicity",
        maximum_crust_coverage_multiplicity);
    add_int(out, first, "maximum_crust_coverage_arrangement_line_count",
        maximum_crust_coverage_arrangement_line_count);
    add_int(out, first, "maximum_crust_coverage_arrangement_fragment_count",
        maximum_crust_coverage_arrangement_fragment_count);
    const int crust_transport_diagnostic_precision =
        std::numeric_limits<double>::max_digits10;
    add_double(out, first, "maximum_crust_source_area_closure_error_km2",
        maximum_crust_source_area_closure_error_km2,
        crust_transport_diagnostic_precision);
    add_double(out, first,
        "maximum_crust_source_area_relative_closure_error",
        maximum_crust_source_area_relative_closure_error,
        crust_transport_diagnostic_precision);
    add_double(out, first,
        "maximum_crust_destination_partition_closure_error_km2",
        maximum_crust_destination_partition_closure_error_km2,
        crust_transport_diagnostic_precision);
    add_double(out, first, "total_crust_uncovered_gap_area_km2",
        total_crust_uncovered_gap_area_km2,
        crust_transport_diagnostic_precision);
    add_double(out, first, "total_crust_overlap_excess_area_km2",
        total_crust_overlap_excess_area_km2,
        crust_transport_diagnostic_precision);
    add_double(out, first,
        "maximum_crust_transport_inventory_relative_closure_error",
        maximum_crust_transport_inventory_relative_closure_error,
        crust_transport_diagnostic_precision);
    add_double(out, first,
        "cumulative_absolute_tectonic_process_crust_volume_change_km3",
        cumulative_absolute_tectonic_process_crust_volume_change_km3,
        crust_transport_diagnostic_precision);
    add_double(out, first,
        "net_tectonic_process_crust_volume_change_km3",
        net_tectonic_process_crust_volume_change_km3,
        crust_transport_diagnostic_precision);
    add_double(out, first,
        "cumulative_absolute_tectonic_process_density_weighted_crust_volume_change_g_cm3_km3",
        cumulative_absolute_tectonic_process_density_weighted_crust_volume_change_g_cm3_km3,
        crust_transport_diagnostic_precision);
    add_double(out, first,
        "net_tectonic_process_density_weighted_crust_volume_change_g_cm3_km3",
        net_tectonic_process_density_weighted_crust_volume_change_g_cm3_km3,
        crust_transport_diagnostic_precision);
    add_double(out, first,
        "cumulative_absolute_tectonic_process_crust_age_volume_moment_change_km3_ma",
        cumulative_absolute_tectonic_process_crust_age_volume_moment_change_km3_ma,
        crust_transport_diagnostic_precision);
    add_double(out, first,
        "net_tectonic_process_crust_age_volume_moment_change_km3_ma",
        net_tectonic_process_crust_age_volume_moment_change_km3_ma,
        crust_transport_diagnostic_precision);
    add_int(out, first, "total_tectonic_process_reason_record_count",
        total_tectonic_process_reason_record_count);
    add_int(out, first, "active_tectonic_process_reason_record_count",
        active_tectonic_process_reason_record_count);
    add_double(out, first,
        "maximum_tectonic_process_attribution_relative_closure_residual",
        maximum_tectonic_process_attribution_relative_closure_residual,
        crust_transport_diagnostic_precision);
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

}  // namespace magic_geo::detail
