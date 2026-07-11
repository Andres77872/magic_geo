#include "internal.hpp"

namespace magic_geo::detail {

std::string climate_model_json(const Params& params) {
    const int precision = std::max(6, params.float_precision);
    const double latitude_temperature_area_mean_offset_c =
        CLIMATE_LATITUDE_TEMPERATURE_GRADIENT_C /
        (CLIMATE_LATITUDE_TEMPERATURE_EXPONENT + 1.0);
    const double thermal_moisture_temperature_anomaly_c =
        climate_thermal_moisture_temperature_anomaly_c(params);
    const double thermal_moisture_capacity_factor =
        climate_thermal_moisture_capacity_factor(params);
    std::string out = "{";
    bool first = true;
    add_str(out, first, "model_type", "equilibrium_latitude_circulation_climate_v4");
    add_str(out, first, "temperature_model", "area_mean_normalized_latitude_centered_local_adjustments_v3");
    add_str(out, first, "precipitation_model",
        "bounded_thermal_moisture_circulation_orography_wind_transport_v2");
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
    add_str(out, first, "thermal_moisture_capacity_model",
        "bounded_exponential_global_temperature_anomaly_v1");
    add_str(out, first, "thermal_moisture_capacity_scope",
        "global_monthly_precipitation_multiplier");
    add_str(out, first, "thermal_moisture_capacity_temperature_anomaly_basis",
        "base_temperature_plus_stellar_and_greenhouse_forcing_relative_to_earth_reference");
    add_double(out, first, "thermal_moisture_capacity_reference_base_temperature_c",
        CLIMATE_THERMAL_MOISTURE_REFERENCE_BASE_TEMPERATURE_C, precision);
    add_double(out, first, "thermal_moisture_capacity_reference_stellar_luminosity",
        1.0, precision);
    add_double(out, first, "thermal_moisture_capacity_reference_greenhouse_factor",
        1.0, precision);
    add_double(out, first, "thermal_moisture_capacity_stellar_temperature_response_c",
        CLIMATE_STELLAR_TEMPERATURE_RESPONSE_C, precision);
    add_double(out, first, "thermal_moisture_capacity_greenhouse_temperature_response_c",
        CLIMATE_GREENHOUSE_TEMPERATURE_RESPONSE_C, precision);
    add_double(out, first, "thermal_moisture_capacity_temperature_response_per_c",
        CLIMATE_THERMAL_MOISTURE_RESPONSE_PER_C, precision);
    add_double(out, first, "thermal_moisture_capacity_min_factor",
        CLIMATE_THERMAL_MOISTURE_MIN_FACTOR, precision);
    add_double(out, first, "thermal_moisture_capacity_max_factor",
        CLIMATE_THERMAL_MOISTURE_MAX_FACTOR, precision);
    add_double(out, first, "thermal_moisture_capacity_temperature_anomaly_c",
        thermal_moisture_temperature_anomaly_c, precision);
    add_double(out, first, "thermal_moisture_capacity_factor",
        thermal_moisture_capacity_factor, precision);
    add_str(out, first, "thermal_moisture_capacity_limitation",
        "diagnostic_global_scaling_without_explicit_atmospheric_water_mass_or_energy_balance");
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

}  // namespace magic_geo::detail
