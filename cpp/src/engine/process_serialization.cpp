#include "internal.hpp"

namespace magic_geo::detail {

namespace {

constexpr const char* NOMINAL_TIME_MODEL =
    "configured_maturation_timestep_nominal_elapsed_time_v1";
constexpr const char* NOMINAL_TIME_BASIS =
    "configured_maturation_timestep_ma_per_erosion_transition_v1";
constexpr const char* NOMINAL_TIME_SOURCE_PARAMETER =
    "erosion.maturation_timestep_ma";

struct NominalTimeInterval {
    double start_ma = 0.0;
    double end_ma = 0.0;
};

std::string crust_extensive_delta_json(
    double crust_volume_km3,
    double density_weighted_crust_volume,
    double crust_age_volume_moment_km3_ma,
    int precision
) {
    std::string out = "{";
    bool first = true;
    add_double(out, first, "crust_volume_km3", crust_volume_km3, precision);
    add_double(
        out,
        first,
        "density_weighted_crust_volume",
        density_weighted_crust_volume,
        precision
    );
    add_double(
        out,
        first,
        "crust_age_volume_moment_km3_ma",
        crust_age_volume_moment_km3_ma,
        precision
    );
    out += "}";
    return out;
}

double nominal_elapsed_time_ma(const Params& params, int transition_count) {
    if (transition_count < 0 || transition_count > params.erosion_iterations) {
        throw std::runtime_error(
            "nominal maturation transition count is outside the configured clock"
        );
    }
    return params.maturation_timestep_ma *
        static_cast<double>(transition_count);
}

NominalTimeInterval nominal_erosion_interval(
    const Params& params,
    int erosion_iteration
) {
    if (erosion_iteration <= 0 || erosion_iteration > params.erosion_iterations) {
        throw std::runtime_error(
            "erosion history record cannot be placed on the nominal maturation clock"
        );
    }
    return {
        nominal_elapsed_time_ma(params, erosion_iteration - 1),
        nominal_elapsed_time_ma(params, erosion_iteration),
    };
}

double nominal_feedback_stage_time_ma(
    const Params& params,
    int feedback_stage_id
) {
    if (feedback_stage_id < 0 ||
        feedback_stage_id > params.erosion_iterations + 1) {
        throw std::runtime_error(
            "feedback-linked history record is outside the nominal maturation clock"
        );
    }
    return nominal_elapsed_time_ma(
        params,
        std::min(feedback_stage_id, params.erosion_iterations)
    );
}

NominalTimeInterval nominal_feedback_interval(
    const Params& params,
    const EarthSystemFeedbackStep& step
) {
    if (step.id == 0 && step.stage == "initial_climate_hydrology") {
        return {};
    }
    if (step.stage == "erosion_iteration") {
        if (step.id != step.erosion_iteration) {
            throw std::runtime_error(
                "erosion feedback stage cannot be placed on the nominal maturation clock"
            );
        }
        return nominal_erosion_interval(params, step.erosion_iteration);
    }
    if (
        step.id == params.erosion_iterations + 1 &&
        step.stage == "cryosphere_coupling"
    ) {
        const double elapsed_ma = nominal_elapsed_time_ma(
            params,
            params.erosion_iterations
        );
        return {elapsed_ma, elapsed_ma};
    }
    throw std::runtime_error(
        "earth-system feedback stage cannot be placed on the nominal maturation clock"
    );
}

NominalTimeInterval nominal_plate_interval(
    const Params& params,
    const PlateMotionStep& step
) {
    if (step.id == 0 && step.stage == "initial_plate_domains") {
        return {};
    }
    if (
        step.stage == "plate_motion_iteration" &&
        step.id == step.erosion_iteration
    ) {
        return nominal_erosion_interval(params, step.erosion_iteration);
    }
    throw std::runtime_error(
        "plate-motion history stage cannot be placed on the nominal maturation clock"
    );
}

void add_nominal_time_fields(
    std::string& out,
    bool& first,
    const NominalTimeInterval& interval,
    const char* role
) {
    constexpr int precision = std::numeric_limits<double>::max_digits10;
    const double duration_ma = interval.end_ma - interval.start_ma;
    add_str(out, first, "nominal_time_model", NOMINAL_TIME_MODEL);
    add_str(out, first, "nominal_time_unit", "Ma");
    add_str(out, first, "nominal_time_basis", NOMINAL_TIME_BASIS);
    add_str(out, first, "nominal_time_source_parameter",
        NOMINAL_TIME_SOURCE_PARAMETER);
    add_str(out, first, "nominal_time_role", role);
    add_double(out, first, "nominal_interval_start_ma",
        interval.start_ma, precision);
    add_double(out, first, "nominal_interval_end_ma",
        interval.end_ma, precision);
    add_double(out, first, "nominal_interval_duration_ma",
        duration_ma, precision);
    add_double(out, first, "nominal_elapsed_time_ma",
        interval.end_ma, precision);
    add_bool(out, first, "advances_nominal_time", duration_ma > 0.0);
    add_bool(out, first, "nominal_time_calibrated", false);
    add_bool(out, first, "physical_time_resolved", false);
}

}  // namespace

std::string crust_material_shadow_model_json() {
    std::string out = "{";
    bool first = true;
    add_str(out, first, "model_type",
        "persistent_sparse_surface_crust_mass_shadow_v1");
    add_str(out, first, "mode", "shadow");
    add_str(out, first, "mass_unit", "kg");
    add_str(out, first, "dry_rock_mass_definition",
        "cell_area_km2_times_crust_thickness_km_times_crust_density_g_cm3_times_1e12");
    std::string origin_kind_order = "[";
    for (std::size_t index = 0; index < CRUST_NAMES.size(); ++index) {
        if (index > 0) {
            origin_kind_order += ",";
        }
        origin_kind_order += '"';
        origin_kind_order += CRUST_NAMES[index];
        origin_kind_order += '"';
    }
    origin_kind_order += ",\"unresolved_rule_source\"]";
    add_raw(out, first, "origin_kind_order", origin_kind_order);
    add_raw(out, first, "packet_key_fields",
        "[\"origin_kind_id\",\"origin_plate_id\",\"origin_reason_id\"]");
    add_str(out, first, "transport_advection_model",
        "source_normalized_overlap_with_final_edge_remainder_v1");
    add_str(out, first, "transport_normalization_scope",
        "per_source_sum_of_raw_overlap_areas");
    add_str(out, first, "transport_remainder_rule",
        "final_destination_edge_receives_source_mass_roundoff_remainder");
    add_str(out, first, "packet_coalescing_model",
        "sorted_equal_key_sum_v1");
    add_str(out, first, "packet_sort_order",
        "origin_kind_id_then_origin_plate_id_then_origin_reason_id");
    add_str(out, first, "ordered_rule_adjustment_model",
        "ordered_positive_unresolved_source_proportional_negative_sink_v1");
    add_str(out, first, "positive_adjustment_origin_kind",
        "unresolved_rule_source");
    add_str(out, first, "negative_adjustment_allocation",
        "proportional_across_transported_packets_with_remainder_to_largest_packet_lowest_key_tie_break");
    add_str(out, first, "raw_transport_scalar_reference",
        "raw_overlap_density_weighted_crust_volume_times_1e12");
    add_str(out, first, "shadow_minus_raw_transport_residual_semantics",
        "source_normalized_shadow_mass_minus_raw_overlap_scalar_mass_is_a_numerical_geometry_closure_diagnostic_not_a_physical_source_or_sink");
    add_bool(out, first, "authoritative_for_cell_state", false);
    add_bool(out, first, "physical_source_sink_resolved", false);
    add_bool(out, first, "material_provenance_resolved", false);
    add_bool(out, first, "solid_volume_resolved", false);
    add_bool(out, first, "phase_resolved", false);
    add_bool(out, first, "mass_weighted_age_resolved", false);
    add_bool(out, first, "upper_mantle_exchange_reservoir_resolved", false);
    add_bool(out, first, "subducted_slab_reservoir_resolved", false);
    add_bool(out, first,
        "global_crust_cycle_mass_conservation_resolved", false);
    add_bool(out, first, "transport_provenance_shadow_resolved", true);
    add_bool(out, first, "ordered_rule_mass_adjustments_exposed", true);
    out += "}";
    return out;
}

namespace {

std::string crust_material_shadow_packet_table_json(
    const CrustMaterialShadowPacketTable& table
) {
    constexpr int mass_precision =
        std::numeric_limits<double>::max_digits10;
    std::string out = "{";
    bool first = true;
    add_raw(out, first, "cell_offsets", int_array_json(table.cell_offsets));
    add_raw(out, first, "origin_kind_ids",
        int_array_json(table.origin_kind_ids));
    add_raw(out, first, "origin_plate_ids",
        int_array_json(table.origin_plate_ids));
    add_raw(out, first, "origin_reason_ids",
        int_array_json(table.origin_reason_ids));
    add_raw(out, first, "dry_rock_mass_kg",
        double_array_json(table.dry_rock_mass_kg, mass_precision));
    out += "}";
    return out;
}

std::string crust_material_shadow_adjustment_table_json(
    const CrustMaterialShadowAdjustmentTable& table
) {
    constexpr int mass_precision =
        std::numeric_limits<double>::max_digits10;
    std::string out = "{";
    bool first = true;
    add_raw(out, first, "cell_offsets", int_array_json(table.cell_offsets));
    add_raw(out, first, "origin_kind_ids",
        int_array_json(table.origin_kind_ids));
    add_raw(out, first, "origin_plate_ids",
        int_array_json(table.origin_plate_ids));
    add_raw(out, first, "origin_reason_ids",
        int_array_json(table.origin_reason_ids));
    add_raw(out, first, "process_reason_ids",
        int_array_json(table.process_reason_ids));
    add_raw(out, first, "dry_rock_mass_kg",
        double_array_json(table.dry_rock_mass_kg, mass_precision));
    out += "}";
    return out;
}

}  // namespace

std::string crust_material_shadow_history_json(
    const std::vector<CrustMaterialShadowStep>& history
) {
    constexpr int mass_precision =
        std::numeric_limits<double>::max_digits10;
    std::string out = "[";
    bool first_step = true;
    for (const CrustMaterialShadowStep& step : history) {
        comma(out, first_step);
        out += "{";
        bool first = true;
        add_int(out, first, "id", step.id);
        add_int(out, first, "plate_motion_history_id",
            step.plate_motion_history_id);
        add_str(out, first, "stage", step.stage);
        add_int(out, first, "erosion_iteration", step.erosion_iteration);
        add_int(out, first, "cell_count", step.cell_count);
        add_raw(out, first, "opening_packets",
            crust_material_shadow_packet_table_json(step.opening_packets));
        add_raw(out, first, "transported_packets",
            crust_material_shadow_packet_table_json(step.transported_packets));
        add_raw(out, first, "unresolved_source_adjustments",
            crust_material_shadow_adjustment_table_json(
                step.unresolved_source_adjustments
            ));
        add_raw(out, first, "unresolved_sink_adjustments",
            crust_material_shadow_adjustment_table_json(
                step.unresolved_sink_adjustments
            ));
        add_raw(out, first, "closing_packets",
            crust_material_shadow_packet_table_json(step.closing_packets));
        add_double(out, first, "global_opening_mass_kg",
            step.opening_surface_mass_kg, mass_precision);
        add_double(out, first, "global_transported_mass_kg",
            step.transported_surface_mass_kg, mass_precision);
        add_double(out, first, "global_unresolved_source_mass_kg",
            step.unresolved_source_mass_kg, mass_precision);
        add_double(out, first, "global_unresolved_sink_mass_kg",
            step.unresolved_sink_mass_kg, mass_precision);
        add_double(out, first, "global_closing_mass_kg",
            step.closing_surface_mass_kg, mass_precision);
        add_double(out, first, "raw_transported_scalar_mass_kg",
            step.raw_transported_density_weighted_mass_kg, mass_precision);
        add_double(out, first, "shadow_minus_raw_transport_residual_kg",
            step.shadow_minus_raw_transport_mass_kg, mass_precision);
        add_double(out, first, "source_to_transport_residual_kg",
            step.source_to_transport_residual_kg, mass_precision);
        add_double(out, first, "closing_scalar_mass_kg",
            step.closing_scalar_mass_kg, mass_precision);
        add_double(out, first, "closing_scalar_mass_residual_kg",
            step.post_scalar_mirror_residual_kg, mass_precision);
        add_double(out, first,
            "maximum_absolute_cell_closing_scalar_mass_residual_kg",
            step.max_abs_post_scalar_mirror_cell_residual_kg,
            mass_precision);
        add_double(out, first,
            "ordered_adjustment_reconciliation_residual_kg",
            step.ordered_adjustment_reconciliation_residual_kg,
            mass_precision);
        add_int(out, first, "opening_packet_count",
            step.opening_packet_count);
        add_int(out, first, "transported_packet_count",
            step.transported_packet_count);
        add_int(out, first, "unresolved_source_adjustment_count",
            step.unresolved_source_adjustment_count);
        add_int(out, first, "unresolved_sink_adjustment_count",
            step.unresolved_sink_adjustment_count);
        add_int(out, first, "closing_packet_count",
            step.closing_packet_count);
        std::string reason_adjustments = "[";
        for (int reason_index = 0;
             reason_index < CRUST_PROCESS_REASON_COUNT;
             ++reason_index) {
            if (reason_index > 0) {
                reason_adjustments += ",";
            }
            reason_adjustments += "{";
            bool first_reason = true;
            add_int(reason_adjustments, first_reason, "process_reason_id",
                reason_index);
            add_str(reason_adjustments, first_reason, "process_reason",
                CRUST_PROCESS_REASON_NAMES[reason_index]);
            add_double(reason_adjustments, first_reason, "source_mass_kg",
                step.unresolved_source_mass_kg_by_reason[
                    static_cast<std::size_t>(reason_index)
                ], mass_precision);
            add_double(reason_adjustments, first_reason, "sink_mass_kg",
                step.unresolved_sink_mass_kg_by_reason[
                    static_cast<std::size_t>(reason_index)
                ], mass_precision);
            reason_adjustments += "}";
        }
        reason_adjustments += "]";
        add_raw(out, first, "ordered_reason_adjustments",
            reason_adjustments);
        out += "}";
    }
    out += "]";
    return out;
}

std::string climate_model_json(const Params& params) {
    if (params.temperature_model != ClimateTemperatureModel::legacy_empirical) {
        throw std::runtime_error("legacy climate metadata requires legacy_empirical temperatures");
    }
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
    add_str(out, first, "model_type", "equilibrium_latitude_circulation_climate_v5");
    add_str(out, first, "temperature_model", "area_mean_normalized_latitude_centered_local_adjustments_v3");
    add_str(out, first, "precipitation_model",
        "bounded_thermal_moisture_circulation_orography_wind_transport_v3");
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
    add_str(out, first, "negative_precipitation_behavior",
        "clamped_to_zero_before_thermal_moisture_multiplier");
    add_str(out, first, "zero_precipitation_scale_behavior",
        "exact_zero_monthly_and_annual_precipitation");
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
    const Params& params,
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
        const double stage_time_ma = nominal_feedback_stage_time_ma(
            params,
            stage.feedback_stage_id
        );
        add_nominal_time_fields(
            out,
            first,
            {stage_time_ma, stage_time_ma},
            "stage_end_stabilization_recomputation_snapshot"
        );
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

std::string numeric_depression_correction_history_json(
    const Params& params,
    const std::vector<NumericDepressionCorrectionEvent>& history,
    int precision
) {
    const int surface_precision = std::max(12, precision);
    std::string out = "[";
    bool first_event = true;
    for (const NumericDepressionCorrectionEvent& event : history) {
        comma(out, first_event);
        out += "{";
        bool first = true;
        add_int(out, first, "id", event.id);
        add_int(out, first, "feedback_stage_id", event.feedback_stage_id);
        add_str(out, first, "stage", event.stage);
        add_int(out, first, "erosion_iteration", event.erosion_iteration);
        add_int(out, first, "stabilization_pass", event.stabilization_pass);
        const double event_time_ma = nominal_feedback_stage_time_ma(
            params,
            event.feedback_stage_id
        );
        add_nominal_time_fields(
            out,
            first,
            {event_time_ma, event_time_ma},
            "stage_end_stabilization_event"
        );
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

std::string grounded_ice_model_json() {
    std::string out = "{";
    bool first = true;
    add_str(out, first, "model_type",
        "exposed_land_annual_grounded_ice_diagnostic_v1");
    add_str(out, first, "surface_domain",
        "nonmarine_nonlake_cells_v1");
    add_str(out, first, "thickness_model",
        "annual_cold_moisture_latitude_elevation_proxy_v1");
    add_str(out, first, "surface_mass_balance_model",
        "annual_precipitation_temperature_proxy_v1");
    add_str(out, first, "dynamics_model",
        "local_downhill_velocity_erosion_proxy_v1");
    add_str(out, first, "active_membership_model",
        "eligible_cells_with_thickness_strictly_above_25m_v1");
    add_str(out, first, "association_model",
        "active_ice_or_one_edge_adjacent_glacial_terrain_v1");
    add_str(out, first, "water_context_policy",
        "lake_glacial_lake_or_marine_fjord_only");
    add_bool(out, first, "lake_ice_resolved", false);
    add_bool(out, first, "sea_ice_resolved", false);
    add_bool(out, first, "physical_time_resolved", false);
    add_bool(out, first, "water_mass_budget_resolved", false);
    add_bool(out, first, "energy_budget_resolved", false);
    add_str(out, first, "model_limitation",
        "static_grounded_ice_diagnostic_without_seasonal_phase_change_perennial_mass_evolution_or_observed_glacier_calibration");
    add_str(out, first, "active_thickness_field",
        "grounded_ice_diagnostic_thickness_m");
    add_str(out, first, "active_thickness_precision",
        "roundtrip_binary64_decimal_v1");
    return out + "}";
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
        "downhill_area_conserving_glacial_sediment_transport_v3");
    add_str(out, first, "routing_graph",
        "single_steepest_downhill_mesh_neighbor_v1");
    add_str(out, first, "source_state",
        "post_erosion_pre_cryosphere_feedback_cell_state_v1");
    add_str(out, first, "source_grounded_ice_model",
        "exposed_land_annual_grounded_ice_diagnostic_v1");
    add_str(out, first, "erosion_potential_model",
        "ice_thickness_times_local_slope_proxy_bounded_85m_v1");
    add_double(out, first, "mobile_sediment_fraction",
        GLACIAL_SEDIMENT_MOBILE_FRACTION, surface_precision);
    add_str(out, first, "source_depth_model",
        "glacial_erosion_potential_times_mobile_sediment_fraction");
    add_str(out, first, "source_material_partition_model",
        "available_alluvium_first_then_bedrock_erosion_v1");
    add_bool(out, first, "per_cell_source_partition_audit_present", true);
    add_str(out, first, "source_partition_audit_depth_unit", "m");
    add_str(out, first, "source_partition_audit_array_index", "cell_id");
    add_str(out, first, "source_partition_audit_demand_field",
        "source_production_depth_m_by_cell");
    add_bool(out, first, "source_partition_audit_is_mass_claim", false);
    add_bool(out, first, "source_partition_audit_is_provenance_claim", false);
    add_str(out, first, "stage_input_snapshot",
        "complete_cell_cryosphere_terrain_and_sediment_inventory_before_transport_v3");
    add_str(out, first, "volume_transfer_model",
        "source_depth_times_source_area_equals_target_depth_times_target_area");
    add_bool(out, first, "mass_conserving", true);
    add_str(out, first, "mass_conserving_semantics",
        "bulk_reference_volume_only_not_dry_rock_mass");
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
    const Params& params,
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
        if (stage.feedback_stage_id != params.erosion_iterations + 1) {
            throw std::runtime_error(
                "glacial sediment history is not linked to the final cryosphere stage"
            );
        }
        if (
            stage.id != static_cast<int>(&stage - history.data()) ||
            stage.cell_count <= 0 ||
            stage.input_cells.size() !=
                static_cast<std::size_t>(stage.cell_count) ||
            stage.source_production_depth_m_by_cell.size() !=
                static_cast<std::size_t>(stage.cell_count) ||
            stage.alluvium_entrainment_depth_m_by_cell.size() !=
                static_cast<std::size_t>(stage.cell_count) ||
            stage.bedrock_erosion_depth_m_by_cell.size() !=
                static_cast<std::size_t>(stage.cell_count)
        ) {
            throw std::runtime_error(
                "glacial sediment source-partition linkage is malformed"
            );
        }
        for (int cell_id = 0; cell_id < stage.cell_count; ++cell_id) {
            if (
                stage.input_cells[static_cast<std::size_t>(cell_id)].cell_id !=
                cell_id
            ) {
                throw std::runtime_error(
                    "glacial sediment input cells are not cell-id indexed"
                );
            }
        }
        const double stage_time_ma = nominal_feedback_stage_time_ma(
            params,
            stage.feedback_stage_id
        );
        add_nominal_time_fields(
            out,
            first,
            {stage_time_ma, stage_time_ma},
            "final_cryosphere_coupling_bulk_transport"
        );
        add_int(out, first, "transfer_count", stage.transfer_count);
        add_int(out, first, "cell_count", stage.cell_count);
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
        add_raw(out, first, "source_production_depth_m_by_cell",
            double_array_json(
                stage.source_production_depth_m_by_cell,
                std::numeric_limits<double>::max_digits10
            ));
        add_raw(out, first, "alluvium_entrainment_depth_m_by_cell",
            double_array_json(
                stage.alluvium_entrainment_depth_m_by_cell,
                std::numeric_limits<double>::max_digits10
            ));
        add_raw(out, first, "bedrock_erosion_depth_m_by_cell",
            double_array_json(
                stage.bedrock_erosion_depth_m_by_cell,
                std::numeric_limits<double>::max_digits10
            ));
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
            add_bool(input_cells_json, first_field, "is_lake",
                input_cell.is_lake);
            add_double(input_cells_json, first_field, "elevation_m",
                input_cell.elevation_m, surface_precision);
            add_double(input_cells_json, first_field, "ice_thickness_m",
                input_cell.ice_thickness_m, surface_precision);
            add_double(input_cells_json, first_field, "glacial_erosion_m",
                input_cell.glacial_erosion_m, surface_precision);
            add_double(input_cells_json, first_field, "sediment_thickness_m",
                input_cell.sediment_thickness_m,
                std::numeric_limits<double>::max_digits10);
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
                transfer.source_production_depth_m,
                std::numeric_limits<double>::max_digits10);
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
        "min_stability_cap_configured_reference_diffusivity_times_maturation_timestep_scale_divided_by_source_lithology_resistance");
    add_str(out, first, "source_depth_model",
        "effective_diffusivity_times_elevation_drop_divided_by_source_neighbor_count");
    add_str(out, first, "volume_transfer_model",
        "source_depth_times_source_area_equals_target_depth_times_target_area");
    add_str(out, first, "source_material_partition_model",
        "available_alluvium_first_then_bedrock_erosion_v1");
    add_str(out, first, "erosion_stage_source_partition_order",
        "hillslope_before_fluvial");
    add_bool(out, first, "per_cell_source_partition_audit_present", true);
    add_str(out, first, "source_partition_audit_depth_unit", "m");
    add_str(out, first, "source_partition_audit_array_index", "cell_id");
    add_str(out, first, "source_partition_audit_demand_field",
        "source_production_depth_m_by_cell");
    add_bool(out, first, "source_partition_audit_is_mass_claim", false);
    add_bool(out, first, "source_partition_audit_is_provenance_claim", false);
    add_double(out, first, "configured_hillslope_diffusivity",
        params.hillslope_diffusion, std::max(8, params.float_precision));
    add_double(out, first, "reference_timestep_ma",
        MATURATION_REFERENCE_TIMESTEP_MA,
        std::numeric_limits<double>::max_digits10);
    add_double(out, first, "nominal_timestep_ma",
        params.maturation_timestep_ma,
        std::numeric_limits<double>::max_digits10);
    add_double(out, first, "maturation_timestep_scale",
        maturation_timestep_scale(params),
        std::numeric_limits<double>::max_digits10);
    add_bool(out, first, "reference_step_response_timestep_scaled", true);
    add_bool(out, first, "time_step_convergence_demonstrated", false);
    add_double(out, first, "maximum_effective_diffusivity",
        HILLSLOPE_MAX_EFFECTIVE_DIFFUSIVITY,
        std::max(8, params.float_precision));
    add_raw(out, first, "source_lithology_resistance",
        resistance_json);
    add_bool(out, first, "mass_conserving", true);
    add_str(out, first, "mass_conserving_semantics",
        "bulk_reference_volume_only_not_dry_rock_mass");
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
    const Params& params,
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
        if (
            stage.id != static_cast<int>(&stage - history.data()) ||
            stage.feedback_stage_id != stage.erosion_iteration ||
            stage.erosion_iteration != stage.id + 1 ||
            stage.cell_count <= 0 ||
            stage.input_cells.size() !=
                static_cast<std::size_t>(stage.cell_count) ||
            stage.source_production_depth_m_by_cell.size() !=
                static_cast<std::size_t>(stage.cell_count) ||
            stage.alluvium_entrainment_depth_m_by_cell.size() !=
                static_cast<std::size_t>(stage.cell_count) ||
            stage.bedrock_erosion_depth_m_by_cell.size() !=
                static_cast<std::size_t>(stage.cell_count)
        ) {
            throw std::runtime_error(
                "hillslope sediment source-partition linkage is malformed"
            );
        }
        for (int cell_id = 0; cell_id < stage.cell_count; ++cell_id) {
            if (
                stage.input_cells[static_cast<std::size_t>(cell_id)].cell_id !=
                cell_id
            ) {
                throw std::runtime_error(
                    "hillslope sediment input cells are not cell-id indexed"
                );
            }
        }
        add_nominal_time_fields(
            out,
            first,
            nominal_erosion_interval(params, stage.erosion_iteration),
            "erosion_interval_bulk_hillslope_transport"
        );
        add_int(out, first, "transport_edge_count",
            stage.transport_edge_count);
        add_int(out, first, "cell_count", stage.cell_count);
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
        add_raw(out, first, "source_production_depth_m_by_cell",
            double_array_json(
                stage.source_production_depth_m_by_cell,
                std::numeric_limits<double>::max_digits10
            ));
        add_raw(out, first, "alluvium_entrainment_depth_m_by_cell",
            double_array_json(
                stage.alluvium_entrainment_depth_m_by_cell,
                std::numeric_limits<double>::max_digits10
            ));
        add_raw(out, first, "bedrock_erosion_depth_m_by_cell",
            double_array_json(
                stage.bedrock_erosion_depth_m_by_cell,
                std::numeric_limits<double>::max_digits10
            ));
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
                input_cell.sediment_thickness_m,
                std::numeric_limits<double>::max_digits10);
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
                edge.source_production_depth_m,
                std::numeric_limits<double>::max_digits10);
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
    add_str(out, first, "stage_input_snapshot",
        "complete_cell_hydrology_topology_environment_and_provisional_surface_v1");
    add_bool(out, first, "stage_input_snapshot_cell_id_indexed", true);
    add_bool(out, first, "stage_input_snapshot_used_for_replay", true);
    add_bool(out, first, "source_material_partition_is_coupled_external_state",
        true);
    add_bool(out, first, "per_cell_source_partition_audit_present", true);
    add_str(out, first, "source_partition_audit_depth_unit", "m");
    add_str(out, first, "source_partition_audit_array_index", "cell_id");
    add_str(out, first, "source_partition_audit_demand_field",
        "source_production_depth_m_by_cell");
    add_bool(out, first, "source_partition_audit_is_mass_claim", false);
    add_bool(out, first, "source_partition_audit_is_provenance_claim", false);
    add_bool(out, first, "local_source_is_timestep_scaled_upstream", true);
    add_bool(out, first, "routing_partition_fractions_timestep_invariant", true);
    add_bool(out, first, "time_step_convergence_demonstrated", false);
    add_bool(out, first, "mass_conserving", true);
    add_str(out, first, "mass_conserving_semantics",
        "bulk_reference_volume_only_not_dry_rock_mass");
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
    const Params& params,
    const std::vector<FluvialSedimentRoutingStage>& history,
    int precision
) {
    // These history values are replay operands, not presentation-only
    // diagnostics.  Preserve a round-trip representation so downstream
    // validators can independently recompute routing branches and terminal
    // allocations without accepting a scale-relative tolerance large enough
    // to conceal a material-volume mutation.
    const int evidence_precision = std::max(
        std::numeric_limits<double>::max_digits10,
        precision
    );
    const int volume_precision = evidence_precision;
    const int surface_precision = evidence_precision;
    std::string out = "[";
    bool first_stage = true;
    for (const FluvialSedimentRoutingStage& stage : history) {
        comma(out, first_stage);
        out += "{";
        bool first = true;
        add_int(out, first, "id", stage.id);
        add_int(out, first, "feedback_stage_id", stage.feedback_stage_id);
        add_int(out, first, "erosion_iteration", stage.erosion_iteration);
        if (
            stage.id != static_cast<int>(&stage - history.data()) ||
            stage.feedback_stage_id != stage.erosion_iteration ||
            stage.erosion_iteration != stage.id + 1 ||
            stage.cell_count <= 0 ||
            stage.input_cells.size() !=
                static_cast<std::size_t>(stage.cell_count) ||
            stage.source_production_depth_m_by_cell.size() !=
                static_cast<std::size_t>(stage.cell_count) ||
            stage.alluvium_entrainment_depth_m_by_cell.size() !=
                static_cast<std::size_t>(stage.cell_count) ||
            stage.bedrock_erosion_depth_m_by_cell.size() !=
                static_cast<std::size_t>(stage.cell_count)
        ) {
            throw std::runtime_error(
                "fluvial sediment source-partition linkage is malformed"
            );
        }
        for (int cell_id = 0; cell_id < stage.cell_count; ++cell_id) {
            if (
                stage.input_cells[static_cast<std::size_t>(cell_id)].cell_id !=
                cell_id
            ) {
                throw std::runtime_error(
                    "fluvial routing input cells are not cell-id indexed"
                );
            }
        }
        add_nominal_time_fields(
            out,
            first,
            nominal_erosion_interval(params, stage.erosion_iteration),
            "erosion_interval_bulk_fluvial_routing"
        );
        add_int(out, first, "active_cell_step_count",
            stage.active_cell_step_count);
        add_int(out, first, "cell_count", stage.cell_count);
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
        add_raw(out, first, "source_production_depth_m_by_cell",
            double_array_json(
                stage.source_production_depth_m_by_cell,
                std::numeric_limits<double>::max_digits10
            ));
        add_raw(out, first, "alluvium_entrainment_depth_m_by_cell",
            double_array_json(
                stage.alluvium_entrainment_depth_m_by_cell,
                std::numeric_limits<double>::max_digits10
            ));
        add_raw(out, first, "bedrock_erosion_depth_m_by_cell",
            double_array_json(
                stage.bedrock_erosion_depth_m_by_cell,
                std::numeric_limits<double>::max_digits10
            ));
        add_double(out, first, "total_deposition_volume_km3",
            stage.local_source_volume_km3 - stage.terminal_export_volume_km3,
            volume_precision);
        add_double(out, first, "mass_balance_residual_km3",
            stage.mass_balance_residual_km3, volume_precision);

        add_int(out, first, "input_cell_count",
            static_cast<int>(stage.input_cells.size()));
        std::string input_cells_json = "[";
        bool first_input_cell = true;
        for (const FluvialSedimentRoutingInputCell& input_cell :
                stage.input_cells) {
            comma(input_cells_json, first_input_cell);
            input_cells_json += "{";
            bool first_field = true;
            add_int(input_cells_json, first_field, "cell_id",
                input_cell.cell_id);
            add_int(input_cells_json, first_field, "flow_to_cell_id",
                input_cell.flow_to_cell_id);
            add_int(input_cells_json, first_field, "depression_component_id",
                input_cell.depression_component_id);
            add_int(input_cells_json, first_field, "depression_sink_cell_id",
                input_cell.depression_sink_cell_id);
            add_str(input_cells_json, first_field, "water_body_type",
                WATER_BODY_NAMES[input_cell.water_body]);
            add_bool(input_cells_json, first_field, "is_water",
                input_cell.is_water);
            add_bool(input_cells_json, first_field, "is_river",
                input_cell.is_river);
            add_bool(input_cells_json, first_field, "is_lake",
                input_cell.is_lake);
            add_bool(input_cells_json, first_field, "lake_overflows",
                input_cell.lake_overflows);
            add_double(input_cells_json, first_field, "cell_area_km2",
                input_cell.cell_area_km2, evidence_precision);
            add_double(input_cells_json, first_field, "flow_accumulation",
                input_cell.flow_accumulation, evidence_precision);
            add_double(input_cells_json, first_field, "runoff_mm_y",
                input_cell.runoff_mm_y, evidence_precision);
            add_double(input_cells_json, first_field,
                "hydrologic_flow_slope",
                input_cell.hydrologic_flow_slope, evidence_precision);
            add_double(input_cells_json, first_field,
                "routing_base_elevation_m",
                input_cell.routing_base_elevation_m, evidence_precision);
            add_double(input_cells_json, first_field, "spill_elevation_m",
                input_cell.spill_elevation_m, evidence_precision);
            input_cells_json += "}";
        }
        input_cells_json += "]";
        add_raw(out, first, "input_cells", input_cells_json);

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
                step.hydrologic_flow_slope, surface_precision);
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

std::string sediment_interface_model_json(
    const std::vector<Cell>& cells,
    int precision
) {
    const double maximum_final_closure_residual_m =
        maximum_sediment_interface_closure_residual_m(
            cells,
            "sediment-interface serialization"
        );
    const int surface_precision = std::max(10, precision);
    std::string out = "{";
    bool first = true;
    add_str(out, first, "model_type",
        "explicit_bedrock_surface_mobile_sediment_interface_v1");
    add_str(out, first, "elevation_unit", "m");
    add_raw(out, first, "canonical_state_fields",
        "[\"bedrock_surface_elevation_m\",\"sediment_thickness_m\"]");
    add_str(out, first, "derived_surface_field", "elevation_m");
    add_str(out, first, "bedrock_surface_semantics",
        "top_of_nonmobile_bedrock_below_mobile_sediment_not_moho_or_stratigraphic_basement");
    add_str(out, first, "interface_equation",
        "elevation_m=bedrock_surface_elevation_m+sediment_thickness_m");
    add_str(out, first, "initialization_equation",
        "bedrock_surface_elevation_m=elevation_m-sediment_thickness_m");
    add_str(out, first, "material_update_equation",
        "bedrock_surface_elevation_m'=bedrock_surface_elevation_m+vertical_displacement_m-bedrock_erosion_depth_m;sediment_thickness_m'=sediment_thickness_m-alluvium_entrainment_depth_m+deposition_depth_m;elevation_m'=bedrock_surface_elevation_m'+sediment_thickness_m'");
    add_str(out, first, "sea_level_datum_update",
        "bedrock_surface_elevation_m'=bedrock_surface_elevation_m-sea_level_adjustment_m;sediment_thickness_m'=sediment_thickness_m");
    add_str(out, first, "replay_tolerance_model",
        "decimal_quantization_forward_error_by_serialized_operand_precision_v1");
    add_int(out, first, "canonical_state_serialization_decimal_places", 10);
    add_int(out, first,
        "minimum_replay_operand_serialization_decimal_places", 8);
    add_bool(out, first, "authoritative_interface_geometry", true);
    add_bool(out, first, "bedrock_surface_elevation_is_canonical", true);
    add_bool(out, first, "mobile_sediment_thickness_is_canonical", true);
    add_bool(out, first, "surface_elevation_is_derived", true);
    add_bool(out, first, "dry_rock_mass_resolved", false);
    add_bool(out, first, "sediment_density_resolved", false);
    add_bool(out, first, "porosity_resolved", false);
    add_bool(out, first, "compaction_resolved", false);
    add_bool(out, first, "grain_provenance_resolved", false);
    add_bool(out, first, "chemical_weathering_resolved", false);
    add_int(out, first, "cell_count", static_cast<int>(cells.size()));
    add_double(out, first, "maximum_final_closure_residual_m",
        maximum_final_closure_residual_m, surface_precision);
    add_bool(out, first, "final_interface_closure_validated", true);
    out += "}";
    return out;
}

std::string sediment_inventory_model_json(
    const std::vector<Cell>& cells,
    const std::vector<EarthSystemFeedbackStep>& feedback_history,
    const std::vector<NumericDepressionCorrectionEvent>& numeric_history,
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
    for (const NumericDepressionCorrectionEvent& event : numeric_history) {
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
    add_bool(out, first, "erosion_source_depths_timestep_scaled_upstream", true);
    add_bool(out, first, "time_step_convergence_demonstrated", false);
    add_bool(out, first, "mass_conserving", true);
    add_str(out, first, "mass_conserving_semantics",
        "bulk_reference_volume_only_not_dry_rock_mass");
    add_bool(out, first, "dry_rock_mass_resolved", false);
    add_bool(out, first, "sediment_density_resolved", false);
    add_bool(out, first, "porosity_resolved", false);
    add_bool(out, first, "compaction_resolved", false);
    add_bool(out, first, "grain_provenance_resolved", false);
    add_bool(out, first, "chemical_weathering_resolved", false);
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
    const double nominal_timestep_ma = params.maturation_timestep_ma;
    const double nominal_elapsed_ma = nominal_elapsed_time_ma(
        params,
        params.erosion_iterations
    );
    const int time_precision = std::numeric_limits<double>::max_digits10;
    std::string out = "{";
    bool first = true;
    add_str(out, first, "clock_type", "coupled_geodynamic_stage_clock_v12");
    add_str(out, first, "time_unit", "model_step");
    add_bool(out, first, "physical_time_resolved", false);
    add_bool(out, first, "nominal_time_calibrated", false);
    add_bool(out, first, "absolute_geological_age_resolved", false);
    add_bool(out, first, "process_rate_calibration_resolved", false);
    add_bool(out, first, "time_step_convergence_demonstrated", false);
    add_str(out, first, "clock_limitation",
        "nominal_geological_intervals_without_calibrated_physical_time_or_timestep_convergence");
    add_str(out, first, "nominal_time_model", NOMINAL_TIME_MODEL);
    add_str(out, first, "nominal_time_unit", "Ma");
    add_str(out, first, "nominal_time_basis", NOMINAL_TIME_BASIS);
    add_str(out, first, "nominal_time_source_parameter",
        NOMINAL_TIME_SOURCE_PARAMETER);
    add_str(out, first, "nominal_time_direction",
        "forward_from_initial_generated_state");
    add_str(out, first, "cell_erosion_rate_semantics",
        "stream_power_response_per_reference_step_not_applied_transition_depth");
    add_str(out, first, "stream_incision_update",
        "cell_erosion_rate_times_maturation_timestep_scale");
    add_str(out, first, "erosion_transition_coupling_semantics",
        "hillslope_and_stream_use_prior_stabilized_surface_and_hydrology_with_updated_crust_state;tectonic_hillslope_stream_tendencies_are_combined_before_terrain_commit;fluvial_routing_uses_prior_flow_graph_and_provisional_terrain_accommodation");
    add_double(out, first, "nominal_timestep_ma",
        nominal_timestep_ma, time_precision);
    add_double(out, first, "reference_timestep_ma",
        MATURATION_REFERENCE_TIMESTEP_MA, time_precision);
    add_double(out, first, "maturation_timestep_scale",
        maturation_timestep_scale(params), time_precision);
    add_int(out, first, "nominal_timed_transition_count",
        params.erosion_iterations);
    add_double(out, first, "initial_nominal_elapsed_time_ma",
        0.0, time_precision);
    add_double(out, first, "current_nominal_elapsed_time_ma",
        nominal_elapsed_ma, time_precision);
    add_double(out, first, "final_nominal_elapsed_time_ma",
        nominal_elapsed_ma, time_precision);
    add_bool(out, first, "cryosphere_advances_nominal_time", false);
    add_str(out, first, "iteration_process_order",
        "{plate_motion->crust_transport->crust_evolution->precommit_tendency_evaluation[tectonic_elevation+hillslope_sediment+stream_power_incision;prior_stabilized_surface_hydrology]->provisional_terrain_composition->fluvial_sediment_routing[prior_flow_graph+provisional_accommodation]->finite_alluvium_bedrock_inventory_and_terrain_commit->(sea_level->climate->causal_water_budget->hydrology->numeric_depression_correction)*until_stable}*configured_erosion_iterations->cryosphere_state->glacial_sediment_transport->finite_alluvium_bedrock_inventory_and_terrain_commit->(sea_level->climate->causal_water_budget->hydrology->numeric_depression_correction)*until_stable->cryosphere_state_recompute");
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
    const Params& params,
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
        const NominalTimeInterval nominal_interval =
            nominal_feedback_interval(params, step);
        const char* nominal_role = step.stage == "initial_climate_hydrology"
            ? "initial_state_snapshot"
            : (
                step.stage == "erosion_iteration"
                    ? "erosion_transition"
                    : "final_cryosphere_coupling_snapshot"
            );
        add_nominal_time_fields(
            out,
            first,
            nominal_interval,
            nominal_role
        );
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
        add_int(out, first, "numeric_depression_correction_pass_count",
            step.numeric_depression_correction_pass_count);
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
        add_double(out, first, "sea_level_adjustment_m",
            step.sea_level_adjustment_m, std::max(10, precision));
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
        add_double(out, first,
            "mean_stream_power_response_m_per_reference_step",
            step.mean_stream_power_response_m_per_reference_step, precision);
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

std::string initial_oceanic_crust_age_model_json(
    const InitialOceanicCrustAgeDiagnostics& diagnostics
) {
    std::string out = "{";
    bool first = true;
    add_str(out, first, "model_type",
        "multi_source_nominal_ridge_graph_travel_time_v1");
    add_str(out, first, "authority_scope",
        "deterministic_procedural_initial_oceanic_like_age_field_only");
    add_str(out, first, "authoritative_ledger_location",
        "initial_oceanic_crust_age_ledger");
    add_str(out, first, "authoritative_age_field_location",
        "initial_oceanic_crust_age_ledger.age_ma_by_cell");
    add_str(out, first, "initial_state_checkpoint_location",
        "plate_motion_history[0].crust_overlap_ledger.remapped_crust_age_ma_by_cell_where_status_id_is_not_zero");
    add_str(out, first, "initial_state_checkpoint_scope",
        "history_identity_overlap_oceanic_like_ledger_cells_only");
    add_str(out, first, "cell_geometry_source",
        "cells[].position_3d_area_km2_and_neighbors");
    add_str(out, first, "boundary_source",
        "plate_motion_history[0].boundary_segments");
    add_str(out, first, "provisional_crust_state_source",
        "initial_identity_overlap_categories_thickness_density_with_age_zero");
    add_raw(out, first, "provisional_age_for_oceanic_predicate_ma",
        roundtrip_num(0.0));
    add_str(out, first, "oceanic_like_predicate",
        "crust_type_0_or_crust_type_2_with_lithology_0_or_crust_type_3_with_age_le_320_ma_thickness_le_18_km_density_ge_2_84_g_cm3");
    add_str(out, first, "eligible_ridge_segment_rule",
        "direct_divergent_segment_with_both_provisional_opening_sides_oceanic_like_positive_finite_nominal_opening_rate_and_positive_finite_length");
    add_str(out, first, "nonpositive_nominal_opening_rate_policy",
        "zero_rate_segment_excluded_negative_rate_invalid_and_components_without_a_positive_rate_seed_receive_the_model_age_ceiling");
    add_str(out, first, "ridge_seed_rule",
        "sorted_unique_left_and_right_cell_ids_of_eligible_ridge_segments");
    add_str(out, first, "representative_full_spreading_rate_formula",
        "sum(segment_signed_opening_rate_km_per_ma_times_segment_length_km)_divided_by_sum(segment_length_km)");
    add_str(out, first, "representative_rate_accumulation_order",
        "plate_motion_history_zero_boundary_segments_serialized_order");
    add_raw(out, first, "representative_half_spreading_rate_factor",
        roundtrip_num(0.5));
    add_str(out, first, "graph_edge_angle_formula",
        "atan2(norm(cross(source_position_3d,target_position_3d)),clamp(dot(source_position_3d,target_position_3d),-1,1))");
    add_str(out, first, "graph_edge_distance_formula",
        "radius_km_times_graph_edge_angle_rad");
    add_str(out, first, "graph_edge_age_increment_formula",
        "graph_edge_distance_km_divided_by_representative_half_spreading_rate_km_per_ma");
    add_str(out, first, "shortest_path_model",
        "multi_source_dijkstra_over_oceanic_like_cell_neighbor_graph");
    add_str(out, first, "queue_order",
        "ascending_accumulated_age_ma_then_ascending_cell_id");
    add_str(out, first, "neighbor_order",
        "cells[].neighbors_serialized_order");
    add_str(out, first, "equal_path_tie_rule",
        "strictly_lower_age_updates_only_first_discovered_equal_age_path_retained");
    add_str(out, first, "non_oceanic_like_age_rule", "exact_zero_ma");
    add_str(out, first, "reachable_oceanic_like_age_rule",
        "clamp(shortest_path_graph_age_ma,zero,maximum_model_age_ma)");
    add_str(out, first, "unreachable_oceanic_like_age_rule",
        "maximum_model_age_ma_with_unresolved_no_active_ridge_path_status");
    add_raw(out, first, "configured_maximum_model_age_ma",
        roundtrip_num(INITIAL_OCEANIC_CRUST_MAX_AGE_MA));
    add_str(out, first, "effective_maximum_age_formula",
        "min(configured_maximum_model_age_ma,1000_times_geological_age_ga)");
    add_str(out, first, "age_unit", "Ma");
    add_str(out, first, "distance_unit", "km");
    add_str(out, first, "spreading_rate_unit", "km_per_ma");
    add_str(out, first, "cell_area_unit", "km2");
    add_raw(out, first, "status_id_order",
        "[\"not_oceanic_like\",\"ridge_seed\",\"ridge_reachable\",\"ridge_reachable_ceiling_clamped\",\"unresolved_no_active_ridge_path_ceiling\"]");
    add_str(out, first, "unclamped_graph_age_unavailable_sentinel",
        "negative_one_for_non_oceanic_like_or_unreachable_cells");
    add_str(out, first, "array_index", "canonical_cell_id");
    add_str(out, first, "array_serialization_model",
        "decimal_max_digits10_binary64_round_trip");
    add_str(out, first, "cdf_threshold_location",
        "initial_oceanic_crust_age_ledger.cdf_thresholds_ma");
    add_str(out, first, "cdf_threshold_selection",
        "fixed_20_ma_increments_from_20_through_200_for_external_validation_output_not_generation_input");
    add_str(out, first, "cdf_value_location",
        "initial_oceanic_crust_age_ledger.area_weighted_cdf_le_threshold");
    add_str(out, first, "cdf_formula",
        "sum(cells_area_km2_where_oceanic_like_and_age_ma_le_threshold)_divided_by_total_oceanic_like_area_km2");
    add_str(out, first, "cdf_threshold_comparison", "inclusive_less_than_or_equal");
    add_bool(out, first, "procedural_authority", true);
    add_bool(out, first, "path_decision_witness_exposed", true);
    add_bool(out, first,
        "independent_replay_inputs_unconditionally_exposed", false);
    add_bool(out, first, "independent_replay_requires_cells_output", true);
    add_bool(out, first, "physical_seafloor_creation_resolved", false);
    add_bool(out, first, "spreading_rate_calibrated", false);
    add_bool(out, first, "local_spreading_rates_resolved", false);
    add_bool(out, first, "ridge_flowlines_resolved", false);
    add_bool(out, first, "subduction_sink_history_resolved", false);
    add_bool(out, first, "convergence_history_resolved", false);
    add_bool(out, first, "seton_2020_age_grid_used_as_generation_input", false);
    add_str(out, first, "model_limitation",
        "procedural_graph_distance_age_initialization_using_one_global_nominal_half_spreading_rate_without_physical_plate_reconstruction_flowlines_or_crust_creation_and_destruction_history");
    add_raw(out, first, "effective_maximum_age_ma",
        roundtrip_num(diagnostics.maximum_age_ma));
    out += "}";
    return out;
}

std::string initial_oceanic_crust_age_ledger_json(
    const InitialOceanicCrustAgeDiagnostics& diagnostics
) {
    if (
        diagnostics.cell_count < 0 ||
        diagnostics.age_ma_by_cell.size() !=
            static_cast<std::size_t>(diagnostics.cell_count) ||
        diagnostics.unclamped_graph_age_ma_by_cell.size() !=
            diagnostics.age_ma_by_cell.size() ||
        diagnostics.status_id_by_cell.size() !=
            diagnostics.age_ma_by_cell.size() ||
        diagnostics.predecessor_cell_id_by_cell.size() !=
            diagnostics.age_ma_by_cell.size() ||
        diagnostics.origin_ridge_seed_cell_id_by_cell.size() !=
            diagnostics.age_ma_by_cell.size() ||
        diagnostics.cdf_thresholds_ma.size() !=
            diagnostics.area_weighted_cdf_le_threshold.size() ||
        diagnostics.oceanic_like_cell_count < 0 ||
        diagnostics.non_oceanic_like_cell_count < 0 ||
        diagnostics.oceanic_like_cell_count +
            diagnostics.non_oceanic_like_cell_count !=
                diagnostics.cell_count ||
        diagnostics.reachable_oceanic_like_cell_count < 0 ||
        diagnostics.unreachable_oceanic_like_cell_count < 0 ||
        diagnostics.reachable_oceanic_like_cell_count +
            diagnostics.unreachable_oceanic_like_cell_count !=
                diagnostics.oceanic_like_cell_count
    ) {
        throw std::runtime_error(
            "initial oceanic crust age ledger is internally inconsistent"
        );
    }
    std::string out = "{";
    bool first = true;
    add_int(out, first, "source_plate_motion_history_id", 0);
    add_int(out, first, "cell_count", diagnostics.cell_count);
    add_int(out, first, "oceanic_like_cell_count",
        diagnostics.oceanic_like_cell_count);
    add_int(out, first, "non_oceanic_like_cell_count",
        diagnostics.non_oceanic_like_cell_count);
    add_int(out, first, "eligible_ridge_segment_count",
        static_cast<int>(diagnostics.eligible_ridge_segment_ids.size()));
    add_int(out, first, "ridge_seed_cell_count",
        static_cast<int>(diagnostics.ridge_seed_cell_ids.size()));
    add_int(out, first, "reachable_oceanic_like_cell_count",
        diagnostics.reachable_oceanic_like_cell_count);
    add_int(out, first, "unreachable_oceanic_like_cell_count",
        diagnostics.unreachable_oceanic_like_cell_count);
    add_int(out, first, "reachable_ceiling_clamped_cell_count",
        diagnostics.reachable_ceiling_clamped_cell_count);
    add_int(out, first, "ceiling_assigned_cell_count",
        diagnostics.unreachable_oceanic_like_cell_count +
            diagnostics.reachable_ceiling_clamped_cell_count);
    add_raw(out, first, "eligible_ridge_total_length_km",
        roundtrip_num(diagnostics.eligible_ridge_total_length_km));
    add_raw(out, first, "opening_rate_length_sum_km2_per_ma",
        roundtrip_num(diagnostics.opening_rate_length_sum_km2_per_ma));
    add_raw(out, first, "representative_full_spreading_rate_km_per_ma",
        roundtrip_num(
            diagnostics.representative_full_spreading_rate_km_per_ma
        ));
    add_raw(out, first, "representative_half_spreading_rate_km_per_ma",
        roundtrip_num(
            diagnostics.representative_half_spreading_rate_km_per_ma
        ));
    add_raw(out, first, "maximum_age_ma",
        roundtrip_num(diagnostics.maximum_age_ma));
    add_raw(out, first, "oceanic_like_area_km2",
        roundtrip_num(diagnostics.oceanic_like_area_km2));
    add_raw(out, first, "area_weighted_mean_age_ma",
        roundtrip_num(diagnostics.area_weighted_mean_age_ma));
    add_raw(out, first, "minimum_oceanic_like_age_ma",
        roundtrip_num(diagnostics.minimum_oceanic_like_age_ma));
    add_raw(out, first, "maximum_oceanic_like_age_ma",
        roundtrip_num(diagnostics.maximum_oceanic_like_age_ma));
    add_raw(out, first, "eligible_ridge_segment_ids",
        int_array_json(diagnostics.eligible_ridge_segment_ids));
    add_raw(out, first, "ridge_seed_cell_ids",
        int_array_json(diagnostics.ridge_seed_cell_ids));
    add_raw(out, first, "age_ma_by_cell",
        roundtrip_double_array_json(diagnostics.age_ma_by_cell));
    add_raw(out, first, "unclamped_graph_age_ma_by_cell",
        roundtrip_double_array_json(
            diagnostics.unclamped_graph_age_ma_by_cell
        ));
    add_raw(out, first, "status_id_by_cell",
        int_array_json(diagnostics.status_id_by_cell));
    add_raw(out, first, "predecessor_cell_id_by_cell",
        int_array_json(diagnostics.predecessor_cell_id_by_cell));
    add_raw(out, first, "origin_ridge_seed_cell_id_by_cell",
        int_array_json(diagnostics.origin_ridge_seed_cell_id_by_cell));
    add_raw(out, first, "cdf_thresholds_ma",
        roundtrip_double_array_json(diagnostics.cdf_thresholds_ma));
    add_raw(out, first, "area_weighted_cdf_le_threshold",
        roundtrip_double_array_json(
            diagnostics.area_weighted_cdf_le_threshold
        ));
    out += "}";
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
    add_str(out, first, "model_type", "rotating_voronoi_plate_domains_v3");
    add_str(out, first, "time_unit", "model_step");
    add_bool(out, first, "physical_time_resolved", false);
    add_bool(out, first, "nominal_time_calibrated", false);
    add_bool(out, first, "process_rate_calibration_resolved", false);
    add_bool(out, first, "time_step_convergence_demonstrated", false);
    add_str(out, first, "nominal_time_model", NOMINAL_TIME_MODEL);
    add_str(out, first, "nominal_time_unit", "Ma");
    add_str(out, first, "nominal_time_basis", NOMINAL_TIME_BASIS);
    add_str(out, first, "nominal_time_source_parameter",
        NOMINAL_TIME_SOURCE_PARAMETER);
    const int time_precision = std::numeric_limits<double>::max_digits10;
    const double timestep_scale = maturation_timestep_scale(params);
    add_double(out, first, "nominal_timestep_ma",
        params.maturation_timestep_ma, time_precision);
    add_double(out, first, "reference_timestep_ma",
        MATURATION_REFERENCE_TIMESTEP_MA, time_precision);
    add_double(out, first, "maturation_timestep_scale",
        timestep_scale, time_precision);
    add_str(out, first, "timestep_scaling_model",
        "reference_normalized_partial_process_scaling_v1");
    add_double(out, first, "motion_scale_deg_per_step",
        params.plate_motion_scale_deg_per_step * timestep_scale,
        time_precision);
    add_double(out, first, "reference_motion_scale_deg_per_reference_step",
        params.plate_motion_scale_deg_per_step, time_precision);
    add_double(out, first, "effective_motion_scale_deg_per_step",
        params.plate_motion_scale_deg_per_step * timestep_scale,
        time_precision);
    add_double(out, first,
        "reference_oceanic_crust_aging_ma_per_reference_step",
        params.oceanic_crust_aging_ma_per_step, time_precision);
    add_double(out, first, "effective_oceanic_crust_aging_ma_per_step",
        params.oceanic_crust_aging_ma_per_step * timestep_scale,
        time_precision);
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
    add_double(out, first, "oceanic_ridge_reference_depth_m",
        OCEANIC_RIDGE_REFERENCE_DEPTH_M, time_precision);
    add_double(out, first, "continental_reference_crust_thickness_km",
        CONTINENTAL_REFERENCE_CRUST_THICKNESS_KM, time_precision);
    add_double(out, first, "continental_crust_thickness_freeboard_m_per_km",
        CONTINENTAL_CRUST_THICKNESS_FREEBOARD_M_PER_KM, time_precision);
    add_double(out, first, "continental_reference_crust_density_g_cm3",
        CONTINENTAL_REFERENCE_CRUST_DENSITY_G_CM3, time_precision);
    add_double(out, first, "continental_crust_density_freeboard_m_per_g_cm3",
        CONTINENTAL_CRUST_DENSITY_FREEBOARD_M_PER_G_CM3, time_precision);
    add_str(out, first, "isostatic_equilibrium_formula",
        "oceanic_like?-2500:500+12*(crust_thickness_km-30)-1800*(crust_density_g_cm3-2.72)");
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
    add_str(out, first, "crust_memory_model",
        "plate_attached_conservative_extensive_mixture_v1");
    add_str(out, first, "crust_transport_model",
        "forward_spherical_control_volume_overlap_v1");
    add_str(out, first, "crust_transport_ledger_format",
        "destination_csr_spherical_forward_overlap_v1");
    add_str(out, first, "crust_transport_positive_area_serialization_model",
        "general_format_max_digits10_binary64_round_trip_v1");
    add_str(out, first, "crust_transport_coverage_model",
        "destination_local_gnomonic_line_arrangement_multiplicity_v1");
    add_str(out, first, "crust_transport_coverage_histogram_model",
        "global_area_by_integer_source_multiplicity_v1");
    add_str(out, first, "crust_transport_coverage_membership_area_class_model",
        "coalesced_destination_source_membership_area_classes_v1");
    add_str(out, first,
        "crust_transport_coverage_membership_area_class_ledger_format",
        "destination_membership_area_class_csr_with_class_contributor_csr_v1");
    add_str(out, first, "crust_transport_coverage_membership_area_class_order",
        "destination_id_then_multiplicity_then_source_cell_ids");
    add_str(out, first,
        "crust_transport_coverage_membership_area_class_coalescing_key",
        "sorted_contributing_source_cell_ids");
    add_str(out, first,
        "crust_transport_coverage_membership_area_class_representative_model",
        "largest_atomic_arrangement_piece_unprojected_vertex_mean_lowest_xyz_tie_v1");
    add_str(out, first,
        "crust_transport_coverage_membership_area_class_source_plate_id_semantics",
        "source_cell_plate_id_at_transport_source_snapshot");
    add_str(out, first,
        "crust_transport_coverage_membership_area_class_edge_area_reconstruction_tolerance_basis",
        "max_1e-7_km2_or_destination_control_volume_area_km2_times_5e-10");
    add_bool(out, first,
        "crust_transport_coverage_membership_area_class_source_membership_resolved",
        true);
    add_bool(out, first,
        "crust_transport_coverage_membership_area_class_connected_fragment_topology_resolved",
        false);
    add_bool(out, first,
        "crust_transport_coverage_membership_area_class_physical_fate_resolved",
        false);
    add_bool(out, first,
        "crust_transport_coverage_membership_area_class_slab_selection_resolved",
        false);
    add_bool(out, first,
        "crust_transport_coverage_membership_area_class_local_kinematics_resolved",
        false);
    add_str(out, first, "crust_categorical_remap_model",
        "joint_crust_type_lithology_dominant_incoming_volume_v1");
    add_str(out, first, "crust_categorical_remap_tie_break",
        "lowest_crust_type_then_lowest_lithology");
    add_str(out, first, "oceanic_state_classification_model",
        "crust_type_with_transitional_lithology_provenance_and_arc_numeric_guard_v2");
    add_str(out, first, "transitional_oceanic_provenance_rule",
        "crust_type_2_is_oceanic_iff_lithology_0_basalt");
    add_str(out, first, "volcanic_arc_oceanic_state_rule",
        "crust_type_3_is_oceanic_iff_age_le_320_ma_thickness_le_18_km_density_ge_2_84");
    add_int(out, first, "crust_transport_coverage_arrangement_fragment_limit",
        16384);
    add_str(out, first, "crust_transport_execution_backend", "cpu");
    add_str(out, first, "canonical_crust_mixture_provenance_location",
        "plate_motion_history[].crust_overlap_ledger");
    add_str(out, first, "crust_density_unit", "g_cm3");
    add_str(out, first, "density_weighted_crust_volume_unit",
        "g_cm3_km3");
    add_double(out, first,
        "density_weighted_crust_volume_to_mass_kg_factor",
        1.0e12, std::numeric_limits<double>::max_digits10);
    add_bool(out, first, "crust_advection_resolved", true);
    add_bool(out, first, "crust_volume_conserving_transport", true);
    add_bool(out, first, "density_weighted_volume_conserving_transport", true);
    add_bool(out, first, "crust_age_volume_moment_conserving_transport", true);
    add_bool(out, first, "mass_conserving_crust_transport", true);
    add_str(out, first, "mass_conservation_scope",
        "transport_only_before_rule_based_tectonic_processes");
    add_bool(out, first, "destination_overlap_areas_normalized", false);
    add_bool(out, first, "tectonic_process_inventory_changes_separately_ledgered", true);
    add_str(out, first, "tectonic_process_inventory_ledger_granularity",
        "transported_post_and_rule_reason_positive_negative_per_step_v2");
    add_bool(out, first,
        "tectonic_process_reason_resolved_inventory_ledgered", true);
    add_str(out, first, "tectonic_process_inventory_ledger_scope",
        "transported_pre_process_to_post_process_with_sequential_rule_attribution");
    add_str(out, first, "tectonic_process_inventory_attribution_format",
        "sequential_rule_extensive_state_delta_v1");
    add_str(out, first, "tectonic_process_rule_model",
        "ordered_thresholded_crust_state_transition_v2");
    std::string process_reason_order = "[";
    for (int reason_index = 0;
         reason_index < CRUST_PROCESS_REASON_COUNT;
         ++reason_index) {
        if (reason_index > 0) {
            process_reason_order += ",";
        }
        process_reason_order += '"';
        process_reason_order += CRUST_PROCESS_REASON_NAMES[reason_index];
        process_reason_order += '"';
    }
    process_reason_order += "]";
    add_raw(out, first, "tectonic_process_inventory_reason_order",
        process_reason_order);
    add_raw(out, first, "tectonic_process_boundary_input_locations",
        "[\"plate_motion_history[].boundary_convergent_by_cell\","
        "\"plate_motion_history[].boundary_divergent_by_cell\","
        "\"plate_motion_history[].boundary_transform_by_cell\"]");
    add_double(out, first, "tectonic_process_internal_heat_input",
        params.internal_heat, time_precision);
    add_double(out, first, "tectonic_process_geological_age_ga_input",
        params.geological_age_ga, time_precision);
    add_str(out, first, "tectonic_activity_formula",
        "clamp(internal_heat*sqrt(4.5/max(0.05,geological_age_ga)),0.25,2.25)");
    add_double(out, first, "tectonic_activity_index",
        clamp(
            params.internal_heat *
                std::sqrt(4.5 / std::max(0.05, params.geological_age_ga)),
            0.25,
            2.25
        ),
        time_precision);
    add_str(out, first, "tectonic_equilibrium_adjustment_model",
        "quasi_static_full_local_target_difference_plus_bounded_dynamic_relief_v1");
    add_str(out, first, "equilibrium_timescale_separation_basis",
        "nominal_5_ma_reference_step_is_more_than_three_orders_of_magnitude_longer_than_3_to_4_ka_degree_2_to_20_viscoelastic_relaxation_estimates");
    add_str(out, first, "isostatic_relaxation_source_doi",
        "10.1111/j.1365-246X.1971.tb01823.x");
    add_double(out, first, "isostatic_relaxation_reference_min_years",
        3000.0, time_precision);
    add_double(out, first, "isostatic_relaxation_reference_max_years",
        4000.0, time_precision);
    add_double(out, first, "isostatic_target_difference_gain",
        TECTONIC_ISOSTATIC_TARGET_DIFFERENCE_GAIN, time_precision);
    add_double(out, first, "thermal_target_difference_gain",
        OCEANIC_AGE_DEPTH_TARGET_DIFFERENCE_GAIN, time_precision);
    add_bool(out, first, "equilibrium_target_difference_clamped", false);
    add_bool(out, first, "equilibrium_operator_physical_time_calibrated", false);
    add_bool(out, first,
        "combined_tectonic_equilibrium_and_dynamic_clamp_present", false);
    add_str(out, first, "dynamic_relief_change_formula",
        "tectonic_uplift_scale*tectonic_activity*(1.5*divergence+8.5*convergence+2.5_if_volcanic_arc)*maturation_timestep_scale*0.42+80*(convergence-previous_convergence)+55*(divergence-previous_divergence)-30*(transform-previous_transform)");
    add_double(out, first, "tectonic_uplift_scale_input",
        params.tectonic_uplift_scale, time_precision);
    add_double(out, first, "tectonic_uplift_rate_response_fraction",
        TECTONIC_UPLIFT_RATE_RESPONSE_FRACTION, time_precision);
    add_double(out, first, "dynamic_relief_minimum_change_m",
        TECTONIC_DYNAMIC_RELIEF_MINIMUM_CHANGE_M, time_precision);
    add_double(out, first, "dynamic_relief_maximum_change_m",
        TECTONIC_DYNAMIC_RELIEF_MAXIMUM_CHANGE_M, time_precision);
    add_str(out, first, "bounded_dynamic_relief_formula",
        "clamp(unbounded_dynamic_relief_change_m,-180,220)");
    add_str(out, first, "tectonic_elevation_change_formula",
        "isostatic_equilibrium_change_m+thermal_equilibrium_change_m+bounded_dynamic_relief_change_m");
    add_str(out, first, "tectonic_equilibrium_history_location",
        "plate_motion_history[]");
    add_bool(out, first, "tectonic_equilibrium_application_replayable", true);
    add_bool(out, first,
        "tectonic_process_rule_state_source_sink_accounting_resolved", true);
    add_bool(out, first,
        "tectonic_process_source_sink_attribution_resolved", false);
    add_str(out, first, "tectonic_process_source_sink_attribution_semantics",
        "componentwise_positive_negative_ordered_rule_state_delta_not_physical_material_flux");
    add_bool(out, first, "tectonic_process_material_provenance_resolved", false);
    add_bool(out, first, "tectonic_process_attribution_order_dependent", true);
    add_str(out, first, "tectonic_process_changed_cell_count_semantics",
        "numeric_age_thickness_density_change_only_excludes_categorical_transitions");
    add_str(out, first, "oceanic_convergence_subduction_proxy_semantics",
        "rule_adds_thickness_and_reduces_age_not_a_crust_removal_flux");
    add_str(out, first, "plate_crossing_accretion_proxy_semantics",
        "extra_continental_convergence_thickening_not_external_reservoir_provenance");
    add_str(out, first, "crust_transport_limitation",
        "first_order_overlap_is_diffusive_and_boundary_creation_subduction_remain_rule_based_process_inventory_changes");
    add_str(out, first, "model_limitation",
        "kinematic_domains_with_conservative_first_order_crust_transport_rule_based_boundary_processes_partial_reference_timestep_scaling_and_uncalibrated_physical_time");
    out += "}";
    return out;
}

std::string plate_boundary_segment_model_json(
    const Params& params,
    const std::vector<PlateMotionStep>& history
) {
    constexpr int precision = std::numeric_limits<double>::max_digits10;
    const double nominal_velocity_scale_km_per_ma =
        params.radius_km * params.plate_motion_scale_deg_per_step *
        (PI / 180.0) / MATURATION_REFERENCE_TIMESTEP_MA;
    std::int64_t total_boundary_segment_count = 0;
    int maximum_boundary_segment_count = 0;
    int reciprocal_mesh_segment_count = 0;
    for (const PlateMotionStep& step : history) {
        total_boundary_segment_count += step.boundary_segment_count;
        maximum_boundary_segment_count = std::max(
            maximum_boundary_segment_count,
            step.boundary_segment_count
        );
        if (reciprocal_mesh_segment_count == 0) {
            reciprocal_mesh_segment_count =
                step.reciprocal_mesh_segment_count;
        } else if (
            step.reciprocal_mesh_segment_count !=
                reciprocal_mesh_segment_count
        ) {
            throw std::runtime_error(
                "plate-boundary reciprocal mesh segment count changed"
            );
        }
    }
    std::string out = "{";
    bool first = true;
    add_str(out, first, "model_type",
        "exact_directed_reciprocal_control_volume_boundary_segments_v2");
    add_str(out, first, "ledger_location",
        "plate_motion_history[].boundary_segments");
    add_str(out, first, "record_layout", "flat_record_array_v2");
    add_str(out, first, "canonical_side_rule",
        "lower_cell_id_is_left_side");
    add_str(out, first, "canonical_direction_rule",
        "left_cell_counter_clockwise_control_volume_edge_start_to_end");
    add_str(out, first, "record_order",
        "left_cell_id_then_left_edge_index_filtered_to_cross_plate_segments");
    add_str(out, first, "segment_selection",
        "one_record_per_cross_plate_reciprocal_control_volume_segment");
    add_str(out, first, "mesh_segment_id_semantics",
        "stable_index_over_all_reciprocal_mesh_segments_in_left_cell_id_then_left_edge_index_order");
    add_str(out, first, "segment_id_semantics",
        "zero_based_contiguous_index_within_each_steps_cross_plate_ledger");
    add_str(out, first, "geometry_source",
        "canonical_spherical_control_volume_vertices_and_reciprocal_edge_neighbor_ids");
    add_str(out, first, "segment_curve", "shorter_great_circle_arc");
    add_str(out, first, "position_unit", "unit_sphere_cartesian");
    add_str(out, first, "angular_length_unit", "rad");
    add_str(out, first, "length_unit", "km");
    add_str(out, first, "velocity_unit", "km_per_Ma_nominal");
    add_str(out, first, "intrinsic_kinematic_index_unit",
        "unit_sphere_tangent_velocity_per_intrinsic_angular_speed_unit");
    add_str(out, first, "opening_crust_age_unit", "Ma");
    add_str(out, first, "opening_crust_thickness_unit", "km");
    add_str(out, first, "opening_crust_density_unit", "g_cm3");
    add_double(out, first, "reciprocal_endpoint_match_tolerance_chord",
        1.0e-10, precision);
    add_int(out, first, "maximum_control_volume_segments_per_cell", 64);
    add_int(out, first,
        "maximum_reciprocal_mesh_segment_count_multiplier", 8);
    add_str(out, first, "reciprocal_mesh_segment_count_cap_formula",
        "reciprocal_mesh_segment_count_le_8_times_cell_count");
    add_str(out, first, "operational_cap_semantics",
        "nonphysical_fail_closed_resource_and_malformed_geometry_guards");
    add_double(out, first, "euler_axis_unit_tolerance", 1.0e-12,
        precision);
    add_double(out, first, "unit_sphere_vector_norm_tolerance", 3.0e-12,
        precision);
    add_double(out, first, "radius_km", params.radius_km, precision);
    add_double(out, first, "reference_motion_scale_deg_per_reference_step",
        params.plate_motion_scale_deg_per_step, precision);
    add_double(out, first, "reference_timestep_ma",
        MATURATION_REFERENCE_TIMESTEP_MA, precision);
    add_double(out, first, "nominal_velocity_scale_km_per_ma",
        nominal_velocity_scale_km_per_ma, precision);
    add_str(out, first, "nominal_velocity_scale_formula",
        "radius_km*reference_motion_scale_deg_per_reference_step*(pi/180)/reference_timestep_ma");
    add_str(out, first, "intrinsic_euler_velocity_formula",
        "cross(rotation_axis*intrinsic_angular_speed,segment_midpoint_unit)");
    add_str(out, first, "intrinsic_angular_speed_snapshot_semantics",
        "constant_per_plate_across_all_history_steps_including_initial_snapshot");
    add_str(out, first, "intrinsic_angular_speed_top_level_cross_check",
        "plate_motion_history[].plates[].intrinsic_angular_speed_equals_plates[].angular_speed_by_plate_id");
    add_str(out, first, "rotation_axis_snapshot_semantics",
        "constant_per_plate_across_all_history_steps_including_initial_snapshot");
    add_str(out, first, "rotation_axis_top_level_cross_check",
        "plate_motion_history[].plates[].rotation_axis_equals_plates[].axis_by_plate_id");
    add_str(out, first, "initial_snapshot_step_rotation_semantics",
        "zero_state_snapshot_rotation_with_nonzero_intrinsic_angular_speed_allowed");
    add_str(out, first, "noninitial_step_rotation_formula",
        "intrinsic_angular_speed*reference_motion_scale_deg_per_reference_step*maturation_timestep_scale");
    add_int(out, first,
        "intrinsic_angular_speed_serialized_significant_digits", precision);
    add_int(out, first, "rotation_axis_serialized_significant_digits",
        precision);
    add_str(out, first, "assignment_center_snapshot_semantics",
        "authoritative_root_operand_for_same_step_cell_plate_ids");
    add_int(out, first, "assignment_center_serialized_significant_digits",
        precision);
    add_str(out, first, "cell_plate_assignment_formula",
        "argmax_dot_cell_position_3d_and_same_step_plate_snapshot_center");
    add_str(out, first, "cell_plate_assignment_tie_break",
        "plate_id_ascending_with_strict_greater_than_update_exact_tie_keeps_lowest_plate_id");
    add_str(out, first, "cell_plate_ids_semantics",
        "derived_from_cell_position_3d_and_same_step_authoritative_plate_snapshot_centers");
    add_str(out, first, "boundary_segment_plate_id_semantics",
        "derived_from_same_step_cell_plate_ids_at_left_and_right_cell_ids");
    add_str(out, first, "initial_center_top_level_cross_check",
        "plate_motion_history_step_0_plate_center_equals_plates_initial_center_by_plate_id");
    add_str(out, first, "center_transition_formula",
        "normalize_rodrigues_rotate_previous_center_about_rotation_axis_by_step_rotation_deg_times_pi_over_180");
    add_str(out, first, "final_center_top_level_cross_check",
        "last_plate_motion_history_plate_center_equals_plates_center_by_plate_id");
    add_int(out, first,
        "top_level_plate_center_serialized_significant_digits", precision);
    add_str(out, first, "nominal_euler_velocity_formula",
        "intrinsic_euler_velocity*nominal_velocity_scale_km_per_ma");
    add_str(out, first, "relative_velocity_formula",
        "right_euler_velocity-left_euler_velocity");
    add_str(out, first, "signed_opening_rate_formula",
        "dot(relative_velocity_km_per_ma,left_to_right_normal_unit)");
    add_str(out, first, "signed_convergence_rate_formula",
        "-signed_opening_rate_km_per_ma");
    add_str(out, first, "signed_slip_rate_formula",
        "dot(relative_velocity_km_per_ma,tangent_unit)");
    add_str(out, first, "signed_opening_index_formula",
        "dot(right_intrinsic_euler_velocity-left_intrinsic_euler_velocity,left_to_right_normal_unit)");
    add_str(out, first, "signed_convergence_index_formula",
        "-signed_opening_index");
    add_str(out, first, "signed_slip_index_formula",
        "dot(right_intrinsic_euler_velocity-left_intrinsic_euler_velocity,tangent_unit)");
    add_str(out, first, "direct_convergent_strength_formula",
        "clamp(signed_convergence_index*1.25,0,1)");
    add_str(out, first, "direct_divergent_strength_formula",
        "clamp(signed_opening_index*1.25,0,1)");
    add_str(out, first, "direct_transform_strength_formula",
        "clamp((abs(signed_slip_index)-abs(signed_opening_index)*0.35)*1.05,0,1)");
    add_double(out, first, "direct_boundary_class_inactive_threshold",
        0.08, precision);
    add_str(out, first, "direct_boundary_class_rule",
        "inactive_if_max_strength_lt_0.08_else_max_strength");
    add_str(out, first, "direct_boundary_class_tie_break",
        "convergent_then_divergent_then_transform");
    add_str(out, first, "polarity_convergence_applicability_rule",
        "direct_convergent_strength_ge_0_08_independent_of_winning_boundary_class");
    add_str(out, first, "opening_crust_state_source",
        "same_step_crust_overlap_ledger_remapped_pre_process_state");
    add_str(out, first, "opening_crust_state_availability_rule",
        "unavailable_iff_age_ma_and_thickness_km_are_both_zero_density_always_positive_available_states_require_positive_thickness");
    add_str(out, first, "unavailable_opening_crust_sentinel_semantics",
        "retained_categorical_and_density_values_are_fixed_shape_unavailable_state_sentinels_not_material_state");
    add_str(out, first, "opening_oceanic_like_predicate",
        "crust_type_0_or_crust_type_2_with_lithology_0_or_crust_type_3_with_age_le_320_ma_thickness_le_18_km_density_ge_2_84_g_cm3");
    add_str(out, first, "opening_oceanic_like_evaluation_scope",
        "available_opening_crust_states_only_unavailable_states_are_false");
    add_raw(out, first, "polarity_candidate_status_order",
        "[\"no_active_convergence\",\"unresolved_missing_opening_crust_state\",\"left_oceanic_only\",\"right_oceanic_only\",\"ambiguous_both_oceanic\",\"unresolved_no_oceanic_side\"]");
    add_str(out, first, "candidate_subducting_side_mapping",
        "left_oceanic_only_to_left_right_oceanic_only_to_right_all_other_statuses_to_none");
    add_str(out, first, "candidate_overriding_side_mapping",
        "left_oceanic_only_to_right_right_oceanic_only_to_left_all_other_statuses_to_none");
    add_str(out, first, "candidate_side_semantics",
        "oceanic_side_heuristic_is_subducting_candidate_and_opposite_side_is_overriding_candidate_not_physical_polarity");
    add_str(out, first, "physical_polarity_status_rule",
        "active_convergence_unknown_unresolved_else_not_applicable_no_active_convergence");
    add_str(out, first, "physical_polarity_source_rule",
        "none_until_supplied_constraint_or_physical_solver_is_implemented");
    add_str(out, first, "gpgim_supplied_polarity_convention",
        "align_supplied_feature_direction_to_canonical_segment_then_left_or_right_names_overriding_side_and_opposite_names_subducting_side");
    add_int(out, first, "history_step_count", static_cast<int>(history.size()));
    add_raw(out, first, "total_boundary_segment_count",
        std::to_string(total_boundary_segment_count));
    add_int(out, first, "maximum_boundary_segment_count",
        maximum_boundary_segment_count);
    add_int(out, first, "reciprocal_mesh_segment_count",
        reciprocal_mesh_segment_count);
    add_int(out, first, "serialized_float_decimal_significant_digits",
        precision);
    add_bool(out, first, "authoritative_for_segment_geometry", true);
    add_bool(out, first, "authoritative_for_direct_unsmoothed_kinematics", true);
    add_bool(out, first, "reciprocal_segment_identity_resolved", true);
    add_bool(out, first, "opening_remapped_crust_state_recorded", true);
    add_bool(out, first, "smoothed_cell_boundary_forcing_active", true);
    add_bool(out, first,
        "boundary_segments_drive_smoothed_cell_boundary_forcing", false);
    add_bool(out, first, "nominal_time_calibrated", false);
    add_bool(out, first, "physical_time_resolved", false);
    add_bool(out, first, "physical_plate_velocity_calibrated", false);
    add_bool(out, first, "physical_polarity_unknown_state_explicit", true);
    add_bool(out, first, "polarity_candidate_is_physical_decision", false);
    add_bool(out, first, "physical_subduction_polarity_resolved", false);
    add_bool(out, first, "physical_slab_geometry_resolved", false);
    add_bool(out, first, "slab_selection_resolved", false);
    add_bool(out, first, "slab_transfer_resolved", false);
    add_bool(out, first, "physical_material_fate_resolved", false);
    add_bool(out, first, "boundary_segments_drive_slab_transfers", false);
    add_str(out, first, "model_limitation",
        "kinematic_candidate_evidence_only_without_physical_polarity_slab_geometry_material_fate_or_feedback_into_smoothed_cell_boundary_forcing");
    out += "}";
    return out;
}

std::string crust_overlap_candidate_fate_model_json() {
    std::string out = "{";
    bool first = true;
    add_str(out, first, "model_type",
        "sparse_membership_class_to_uniform_boundary_plate_pair_candidate_v1");
    add_str(out, first, "ledger_location",
        "plate_motion_history[].crust_overlap_candidate_fate_ledger");
    add_str(out, first, "membership_source_location",
        "plate_motion_history[].crust_overlap_ledger.coverage_membership_area_class_ledger");
    add_str(out, first, "boundary_evidence_location",
        "plate_motion_history[].boundary_segments");
    add_str(out, first, "source_plate_id_semantics",
        "coverage_membership_area_class_ledger.source_plate_ids_at_transport_source_snapshot");
    add_str(out, first, "boundary_plate_id_semantics",
        "boundary_segments.left_plate_id_and_right_plate_id_at_boundary_assignment_snapshot");
    add_str(out, first, "assignment_step_linkage",
        "step_0_source_0_boundary_0_else_source_step_id_minus_1_boundary_step_id");
    add_str(out, first, "persistent_pair_id_formula",
        "256*plate_low_id+plate_high_id");
    add_str(out, first, "pair_id_semantics",
        "persistent_unordered_plate_pair_id_not_boundary_pair_evidence_array_index");
    add_int(out, first, "maximum_plate_count", 256);
    add_str(out, first, "pair_grouping",
        "all_same_step_boundary_segments_grouped_by_sorted_unordered_plate_id_pair");
    add_str(out, first, "pair_record_order",
        "plate_low_id_then_plate_high_id_with_segment_ids_ascending");
    add_str(out, first, "class_record_selection",
        "one_record_per_membership_area_class_with_multiplicity_at_least_2");
    add_str(out, first, "class_record_order",
        "membership_area_class_id_ascending");
    add_str(out, first, "class_candidate_preference",
        "uniform_resolved_physical_polarity_else_uniform_oceanic_side_heuristic_only_when_all_physical_polarities_unknown");
    add_str(out, first, "overlap_excess_area_formula",
        "(multiplicity-1)*coverage_membership_area_class_ledger.area_km2");
    add_str(out, first, "area_unit", "km2");
    add_str(out, first, "candidate_area_serialization_model",
        "general_format_max_digits10_binary64_round_trip_v1");
    add_str(out, first, "root_overlap_excess_serialization_model",
        "general_format_max_digits10_binary64_round_trip_v1_for_per_cell_and_global_operands");
    add_str(out, first, "candidate_partition_residual_formula",
        "accounted_overlap_excess_area_km2-crust_overlap_ledger.global_overlap_excess_area_km2");
    add_str(out, first, "candidate_partition_residual_acceptance",
        "accumulated_validated_absolute_destination_binary64_fragment_to_class_discrepancy_plus_portable_binary64_gamma_upper_envelope_with_exact_binary64_global_row_replay");
    add_str(out, first, "destination_row_discrepancy_acceptance",
        "binary64_gamma_bound_using_arrangement_fragment_count_class_count_and_nonnegative_excess_operand_sum");
    add_str(out, first, "candidate_partition_tolerance_model",
        "validated_binary64_fragment_to_class_rows_plus_portable_binary64_gamma_upper_envelope_v1");
    add_str(out, first, "final_long_double_operation_bound",
        "portable_binary64_gamma_upper_envelope_for_native_long_double_accumulation_with_explicit_operation_count_and_operand_sum");
    add_str(out, first, "physical_resolved_tuple_contract",
        "resolved_with_supplied_constraint_or_physical_solver_opposite_left_right_roles_and_confidence_in_open_zero_closed_one");
    add_str(out, first, "heuristic_tuple_contract",
        "left_oceanic_only_or_right_oceanic_only_with_matching_opposite_candidate_roles");
    add_str(out, first, "pair_endpoint_incidence_semantics",
        "destination_cell_id_is_an_endpoint_of_at_least_one_segment_in_the_pair_not_a_local_atom_or_fragment_to_segment_link");
    add_str(out, first, "representative_usage",
        "membership_area_class_representatives_are_never_used_for_pair_assignment_or_incidence");
    add_str(out, first, "candidate_contributor_id_semantics",
        "global_index_into_coverage_membership_area_class_ledger_contributor_csr_arrays");
    add_str(out, first, "candidate_area_semantics",
        "diagnostic_partition_of_overlap_excess_not_allocated_material_fate_or_transfer");
    add_str(out, first, "physical_pair_evidence_provenance_limitation",
        "pair_evidence_is_not_standalone_per_segment_physical_polarity_source_and_confidence_are_not_propagated_and_candidate_cannot_promote_or_replace_upstream_evidence");
    add_int(out, first, "maximum_boundary_segment_count_multiplier", 8);
    add_int(out, first, "maximum_membership_area_classes_per_cell", 16384);
    add_int(out, first,
        "maximum_coverage_arrangement_fragments_per_cell", 16384);
    add_str(out, first, "operational_cap_semantics",
        "fail_closed_nonphysical_resource_and_integer_conversion_guards");
    add_raw(out, first, "physical_consensus_status_order",
        "[\"not_all_segments_have_active_convergence\",\"all_active_all_physical_polarities_unknown\",\"all_active_mixed_resolved_and_unknown\",\"all_active_resolved_polarities_conflict\",\"all_active_resolved_polarity_uniform\"]");
    add_raw(out, first, "heuristic_consensus_status_order",
        "[\"not_all_segments_have_active_convergence\",\"all_active_one_or_more_unique_oceanic_candidates_unavailable\",\"all_active_unique_oceanic_candidates_conflict\",\"all_active_unique_oceanic_candidate_uniform\"]");
    add_raw(out, first, "assignment_status_order",
        "[\"unknown_nonbinary_membership\",\"unknown_non_distinct_source_plate_pair\",\"unknown_no_same_step_boundary_pair\",\"unknown_no_same_step_endpoint_incidence\",\"unknown_no_uniform_pair_polarity_evidence\",\"uniform_oceanic_side_heuristic_candidate\",\"uniform_resolved_physical_polarity_backed_candidate\"]");
    add_bool(out, first, "deterministic_crosswalk_authoritative", true);
    add_str(out, first, "deterministic_crosswalk_authority_scope",
        "serialized_pair_consensus_and_membership_class_diagnostic_mapping_only");
    add_bool(out, first, "candidate_allocation_authoritative", false);
    add_bool(out, first, "pair_wide_consensus_only", true);
    add_bool(out, first, "destination_endpoint_incidence_resolved", true);
    add_bool(out, first,
        "pair_evidence_standalone_physical_provenance_complete", false);
    add_bool(out, first,
        "upstream_segment_physical_source_and_confidence_required_for_interpretation",
        true);
    add_bool(out, first, "physical_polarity_authoritative", false);
    add_bool(out, first, "physical_polarity_resolved", false);
    add_bool(out, first, "physical_material_fate_authoritative", false);
    add_bool(out, first, "physical_material_fate_resolved", false);
    add_bool(out, first, "slab_selection_authoritative", false);
    add_bool(out, first, "slab_selection_resolved", false);
    add_bool(out, first, "slab_transfer_authoritative", false);
    add_bool(out, first, "slab_transfer_resolved", false);
    add_bool(out, first, "state_mutation_performed", false);
    add_bool(out, first, "crust_material_shadow_mutation_performed", false);
    add_bool(out, first, "crust_reservoir_mutation_performed", false);
    add_bool(out, first, "swept_area_calculated", false);
    add_bool(out, first, "local_segment_link_resolved", false);
    add_bool(out, first, "connected_atom_topology_resolved", false);
    add_bool(out, first, "local_fragment_topology_resolved", false);
    add_str(out, first, "model_limitation",
        "diagnostic_candidate_crosswalk_only_without_connected_fragment_localization_physical_fate_slab_geometry_swept_area_or_state_transfer");
    out += "}";
    return out;
}

std::string oceanic_age_depth_model_json() {
    std::string out = "{";
    bool first = true;
    add_str(out, first, "model",
        "continuity_adjusted_parsons_sclater_relative_basement_subsidence_v1");
    add_str(out, first, "authority_scope",
        "relative_oceanic_thermal_subsidence_target_curve_only");
    add_str(out, first, "source_doi", "10.1029/JB082i005p00803");
    add_str(out, first, "source_relation_scope",
        "parsons_sclater_1977_supplies_young_350_sqrt_t_relation_and_old_3200_exp_minus_t_over_62_8_shape");
    add_str(out, first, "continuity_adjustment",
        "implementation_switches_at_70_ma_and_adds_an_offset_to_the_old_branch_for_c0_value_continuity_not_c1_slope_continuity");
    add_str(out, first, "age_input_unit", "Ma");
    add_str(out, first, "thermal_subsidence_output_unit", "m");
    add_raw(out, first, "young_age_cutoff_ma",
        roundtrip_num(OCEANIC_AGE_DEPTH_YOUNG_CUTOFF_MA));
    add_raw(out, first, "young_age_coefficient_m_per_sqrt_ma",
        roundtrip_num(
            OCEANIC_AGE_DEPTH_YOUNG_COEFFICIENT_M_PER_SQRT_MA
        ));
    add_raw(out, first, "old_age_exponential_scale_m",
        roundtrip_num(OCEANIC_AGE_DEPTH_OLD_EXPONENTIAL_SCALE_M));
    add_raw(out, first, "old_age_efolding_time_ma",
        roundtrip_num(OCEANIC_AGE_DEPTH_OLD_EFOLDING_TIME_MA));
    add_str(out, first, "young_relative_subsidence_formula",
        "S_m=350*sqrt(t_ma)_for_0_le_t_ma_le_70");
    add_str(out, first, "old_relative_subsidence_formula",
        "S_m=350*sqrt(70)+3200*(exp(-70/62.8)-exp(-t_ma/62.8))_for_t_ma_gt_70");
    add_str(out, first, "thermal_subsidence_sign_formula",
        "thermal_subsidence_target_m=-S_m_for_oceanic_like_else_0");
    add_str(out, first, "oceanic_like_predicate",
        "crust_type_0_or_crust_type_2_with_lithology_0_or_crust_type_3_with_age_le_320_ma_thickness_le_18_km_density_ge_2_84_g_cm3");
    add_str(out, first, "history_location", "plate_motion_history[]");
    add_str(out, first, "final_cell_field",
        "cells[].thermal_subsidence_target_m");
    add_str(out, first, "authoritative_formula_root",
        "plate_motion_history_crust_overlap_remapped_numeric_state_plus_same_step_process_deltas_and_step_categorical_state");
    add_str(out, first, "final_cell_crust_numeric_root_semantics",
        "binary64_round_trip_aliases_cross_checked_against_authoritative_history_roots");
    add_str(out, first, "previous_local_state_semantics",
        "same_cell_id_equilibrium_target_immediately_before_same_step_overlap_transport_and_ordered_crust_process_rules");
    add_str(out, first, "post_process_local_state_semantics",
        "same_cell_id_equilibrium_target_after_same_step_overlap_transport_ordered_crust_process_rules_and_state_bounds");
    add_str(out, first, "initial_step_checkpoint_semantics",
        "previous_local_target_equals_post_process_initial_target_and_thermal_equilibrium_change_is_zero");
    add_raw(out, first, "thermal_target_difference_gain",
        roundtrip_num(
            OCEANIC_AGE_DEPTH_TARGET_DIFFERENCE_GAIN
        ));
    add_str(out, first, "thermal_equilibrium_change_formula",
        "1.0*(post_process_local_thermal_subsidence_target_m-previous_local_thermal_subsidence_target_m)");
    add_str(out, first, "thermal_equilibrium_change_application",
        "full_target_difference_is_applied_outside_the_bounded_dynamic_relief_clamp_with_zero_unapplied_equilibrium_residual");
    add_bool(out, first,
        "thermal_equilibrium_change_application_replayed", true);
    add_str(out, first, "array_serialization_model",
        "general_format_max_digits10_binary64_round_trip_v1");
    add_str(out, first, "array_cardinality",
        "each_thermal_target_or_equilibrium_change_array_length_equals_plate_motion_step_cell_count");
    add_bool(out, first, "finite_nonnegative_age_required", true);
    add_bool(out, first, "continuity_at_transition_resolved", true);
    add_bool(out, first, "derivative_continuity_at_transition_resolved", false);
    add_bool(out, first,
        "authoritative_for_relative_thermal_subsidence_target_curve", true);
    add_bool(out, first,
        "authoritative_for_realized_thermal_relief_component", false);
    add_bool(out, first, "realized_thermal_relief_state_tracked", false);
    add_bool(out, first, "thermal_relaxation_timescale_calibrated", false);
    add_bool(out, first,
        "unapplied_thermal_tendency_residual_carried_forward", false);
    add_bool(out, first,
        "unapplied_thermal_equilibrium_residual_zero_by_construction", true);
    add_bool(out, first,
        "thermal_contribution_outside_bounded_dynamic_relief_clamp_resolved",
        true);
    add_bool(out, first,
        "thermal_contribution_to_tectonic_elevation_change_replayed", true);
    add_bool(out, first, "absolute_basement_depth_calibrated", false);
    add_bool(out, first, "physical_crust_creation_age_provenance", false);
    add_bool(out, first, "ridge_age_distance_consistency", false);
    add_bool(out, first, "thermal_structure_represented", false);
    add_bool(out, first, "heat_flow_represented", false);
    add_bool(out, first, "dynamic_topography_represented", false);
    add_bool(out, first, "flexure_represented", false);
    add_bool(out, first, "physical_dynamics_represented", false);
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
    const Params& params,
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
        add_nominal_time_fields(
            out,
            first,
            nominal_plate_interval(params, step),
            step.stage == "initial_plate_domains"
                ? "initial_plate_state_snapshot"
                : "plate_motion_transition"
        );
        add_int(out, first, "cell_count", step.cell_count);
        add_int(out, first, "plate_count", step.plate_count);
        add_int(out, first, "reassigned_cell_count", step.reassigned_cell_count);
        add_double(out, first, "reassigned_cell_fraction", step.reassigned_cell_fraction, history_precision);
        add_int(out, first, "plate_boundary_cell_count", step.plate_boundary_cell_count);
        add_int(out, first, "plate_boundary_edge_count", step.plate_boundary_edge_count);
        add_int(out, first, "reciprocal_mesh_segment_count",
            step.reciprocal_mesh_segment_count);
        add_int(out, first, "boundary_segment_count",
            step.boundary_segment_count);
        add_int(out, first, "control_volume_boundary_incident_cell_count",
            step.control_volume_boundary_incident_cell_count);
        add_int(out, first, "accreted_terrane_cell_count", step.accreted_terrane_cell_count);
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
        add_double(out, first, "mean_tectonic_elevation_change_m",
            step.mean_tectonic_elevation_change_m,
            std::numeric_limits<double>::max_digits10);
        add_double(out, first, "mean_abs_tectonic_elevation_change_m",
            step.mean_abs_tectonic_elevation_change_m,
            std::numeric_limits<double>::max_digits10);
        add_double(out, first, "max_abs_tectonic_elevation_change_m",
            step.max_abs_tectonic_elevation_change_m,
            std::numeric_limits<double>::max_digits10);
        add_raw(out, first, "cell_plate_ids", int_array_json(step.cell_plate_ids));
        const CrustTransportPlan& transport = step.transport_plan;
        const int transport_precision = std::numeric_limits<double>::max_digits10;
        std::string overlap_ledger = "{";
        bool first_overlap_field = true;
        add_str(overlap_ledger, first_overlap_field, "format",
            "destination_csr_spherical_forward_overlap_v1");
        add_str(overlap_ledger, first_overlap_field, "coverage_model",
            "destination_local_gnomonic_line_arrangement_multiplicity_v1");
        add_str(overlap_ledger, first_overlap_field, "crust_volume_unit", "km3");
        add_str(overlap_ledger, first_overlap_field, "crust_density_unit", "g_cm3");
        add_str(overlap_ledger, first_overlap_field,
            "density_weighted_crust_volume_unit", "g_cm3_km3");
        add_double(overlap_ledger, first_overlap_field,
            "density_weighted_crust_volume_to_mass_kg_factor",
            1.0e12, transport_precision);
        add_str(overlap_ledger, first_overlap_field,
            "crust_age_volume_moment_unit", "km3_ma");
        add_str(overlap_ledger, first_overlap_field,
            "transport_conservation_scope", "source_to_transported_pre_process");
        add_str(overlap_ledger, first_overlap_field,
            "post_process_inventory_semantics",
            "state_snapshot_not_transport_conservation_target");
        add_raw(overlap_ledger, first_overlap_field, "destination_offsets",
            int_array_json(transport.destination_offsets));
        add_raw(overlap_ledger, first_overlap_field, "source_cell_ids",
            int_array_json(transport.source_cell_ids));
        // Exact intersections can retain strictly positive slivers far below
        // 1e-17 km2.  Fixed fractional formatting would serialize those as
        // zero and violate the positive-area ledger contract, so area columns
        // use significant-digit binary64 round-trip formatting.
        add_raw(overlap_ledger, first_overlap_field, "overlap_area_km2",
            roundtrip_double_array_json(transport.overlap_area_km2));
        add_raw(overlap_ledger, first_overlap_field,
            "remap_residual_distance_km",
            double_array_json(
                transport.remap_residual_distance_km, transport_precision
            ));
        add_raw(overlap_ledger, first_overlap_field,
            "source_kinematic_distance_km",
            double_array_json(
                transport.source_kinematic_distance_km, transport_precision
            ));
        add_raw(overlap_ledger, first_overlap_field,
            "dominant_source_cell_ids",
            int_array_json(transport.dominant_source_cell_ids));
        add_raw(overlap_ledger, first_overlap_field,
            "contributor_count_by_cell",
            int_array_json(transport.contributor_count_by_cell));
        add_raw(overlap_ledger, first_overlap_field,
            "dominant_source_volume_fraction_by_cell",
            double_array_json(
                transport.dominant_source_volume_fraction_by_cell,
                transport_precision
            ));
        add_raw(overlap_ledger, first_overlap_field,
            "coverage_area_sum_km2_by_cell",
            double_array_json(
                transport.coverage_area_sum_km2_by_cell, transport_precision
            ));
        add_raw(overlap_ledger, first_overlap_field,
            "covered_union_area_km2_by_cell",
            double_array_json(
                transport.covered_union_area_km2_by_cell, transport_precision
            ));
        add_raw(overlap_ledger, first_overlap_field,
            "uncovered_gap_area_km2_by_cell",
            roundtrip_double_array_json(
                transport.uncovered_gap_area_km2_by_cell
            ));
        add_raw(overlap_ledger, first_overlap_field,
            "overlap_excess_area_km2_by_cell",
            roundtrip_double_array_json(
                transport.overlap_excess_area_km2_by_cell
            ));
        add_raw(overlap_ledger, first_overlap_field,
            "maximum_coverage_multiplicity_by_cell",
            int_array_json(transport.maximum_coverage_multiplicity_by_cell));
        add_raw(overlap_ledger, first_overlap_field,
            "coverage_arrangement_line_count_by_cell",
            int_array_json(transport.coverage_arrangement_line_count_by_cell));
        add_raw(overlap_ledger, first_overlap_field,
            "coverage_arrangement_fragment_count_by_cell",
            int_array_json(
                transport.coverage_arrangement_fragment_count_by_cell
            ));
        const std::int64_t total_arrangement_line_count = std::accumulate(
            transport.coverage_arrangement_line_count_by_cell.begin(),
            transport.coverage_arrangement_line_count_by_cell.end(),
            std::int64_t{0}
        );
        const std::int64_t total_arrangement_fragment_count = std::accumulate(
            transport.coverage_arrangement_fragment_count_by_cell.begin(),
            transport.coverage_arrangement_fragment_count_by_cell.end(),
            std::int64_t{0}
        );
        add_raw(overlap_ledger, first_overlap_field,
            "total_coverage_arrangement_line_count",
            std::to_string(total_arrangement_line_count));
        add_raw(overlap_ledger, first_overlap_field,
            "total_coverage_arrangement_fragment_count",
            std::to_string(total_arrangement_fragment_count));
        add_raw(overlap_ledger, first_overlap_field,
            "coverage_membership_area_class_count_by_cell",
            int_array_json(
                transport.coverage_membership_area_class_count_by_cell
            ));
        const std::int64_t total_membership_area_class_count = std::accumulate(
            transport.coverage_membership_area_class_count_by_cell.begin(),
            transport.coverage_membership_area_class_count_by_cell.end(),
            std::int64_t{0}
        );
        add_raw(overlap_ledger, first_overlap_field,
            "total_coverage_membership_area_class_count",
            std::to_string(total_membership_area_class_count));
        add_int(overlap_ledger, first_overlap_field,
            "maximum_coverage_membership_area_class_count",
            transport.maximum_coverage_membership_area_class_count);
        std::string class_ledger = "{";
        bool first_class_field = true;
        add_str(class_ledger, first_class_field, "format",
            "destination_membership_area_class_csr_with_class_contributor_csr_v1");
        add_str(class_ledger, first_class_field, "model",
            "coalesced_destination_source_membership_area_classes_v1");
        add_str(class_ledger, first_class_field, "class_order",
            "destination_id_then_multiplicity_then_source_cell_ids");
        add_str(class_ledger, first_class_field, "coalescing_key",
            "sorted_contributing_source_cell_ids");
        add_str(class_ledger, first_class_field, "representative_model",
            "largest_atomic_arrangement_piece_unprojected_vertex_mean_lowest_xyz_tie_v1");
        add_str(class_ledger, first_class_field,
            "representative_available_semantics",
            "one_for_every_v1_membership_area_class_zero_reserved_for_future_unavailable_representatives");
        add_str(class_ledger, first_class_field,
            "source_plate_id_semantics",
            "source_cell_plate_id_at_transport_source_snapshot");
        add_str(class_ledger, first_class_field,
            "edge_area_reconstruction_tolerance_basis",
            "max_1e-7_km2_or_destination_control_volume_area_km2_times_5e-10");
        add_str(class_ledger, first_class_field,
            "raw_arrangement_fragment_count_location",
            "sibling_coverage_arrangement_fragment_count_by_cell");
        add_str(class_ledger, first_class_field, "area_unit", "km2");
        add_raw(class_ledger, first_class_field, "destination_offsets",
            int_array_json(
                transport.coverage_membership_area_class_destination_offsets
            ));
        add_raw(class_ledger, first_class_field, "area_km2",
            roundtrip_double_array_json(
                transport.coverage_membership_area_class_area_km2
            ));
        add_raw(class_ledger, first_class_field, "multiplicity",
            int_array_json(
                transport.coverage_membership_area_class_multiplicity
            ));
        add_raw(class_ledger, first_class_field,
            "representative_unit_x",
            double_array_json(
                transport.coverage_membership_area_class_representative_unit_x,
                transport_precision
            ));
        add_raw(class_ledger, first_class_field,
            "representative_unit_y",
            double_array_json(
                transport.coverage_membership_area_class_representative_unit_y,
                transport_precision
            ));
        add_raw(class_ledger, first_class_field,
            "representative_unit_z",
            double_array_json(
                transport.coverage_membership_area_class_representative_unit_z,
                transport_precision
            ));
        add_raw(class_ledger, first_class_field,
            "representative_available",
            int_array_json(
                transport.coverage_membership_area_class_representative_available
            ));
        add_raw(class_ledger, first_class_field, "contributor_offsets",
            int_array_json(
                transport.coverage_membership_area_class_contributor_offsets
            ));
        add_raw(class_ledger, first_class_field, "source_cell_ids",
            int_array_json(
                transport.coverage_membership_area_class_source_cell_ids
            ));
        add_raw(class_ledger, first_class_field, "source_plate_ids",
            int_array_json(
                transport.coverage_membership_area_class_source_plate_ids
            ));
        add_bool(class_ledger, first_class_field,
            "source_membership_resolved", true);
        add_bool(class_ledger, first_class_field,
            "connected_fragment_topology_resolved", false);
        add_bool(class_ledger, first_class_field,
            "physical_fate_resolved", false);
        add_bool(class_ledger, first_class_field,
            "slab_selection_resolved", false);
        add_bool(class_ledger, first_class_field,
            "local_kinematics_resolved", false);
        class_ledger += "}";
        add_raw(overlap_ledger, first_overlap_field,
            "coverage_membership_area_class_ledger", class_ledger);
        add_raw(overlap_ledger, first_overlap_field,
            "global_coverage_area_km2_by_multiplicity",
            double_array_json(
                transport.global_coverage_area_km2_by_multiplicity,
                transport_precision
            ));
        add_raw(overlap_ledger, first_overlap_field,
            "remapped_crust_type_by_cell",
            int_array_json(transport.remapped_crust_type_by_cell));
        add_raw(overlap_ledger, first_overlap_field,
            "remapped_lithology_by_cell",
            int_array_json(transport.remapped_lithology_by_cell));
        add_raw(overlap_ledger, first_overlap_field,
            "remapped_crust_age_ma_by_cell",
            roundtrip_double_array_json(
                transport.remapped_crust_age_ma_by_cell
            ));
        add_raw(overlap_ledger, first_overlap_field,
            "remapped_crust_thickness_km_by_cell",
            roundtrip_double_array_json(
                transport.remapped_crust_thickness_km_by_cell
            ));
        add_raw(overlap_ledger, first_overlap_field,
            "remapped_crust_density_by_cell",
            roundtrip_double_array_json(
                transport.remapped_crust_density_by_cell
            ));
        add_double(overlap_ledger, first_overlap_field,
            "maximum_source_area_closure_error_km2",
            transport.maximum_source_area_closure_error_km2,
            transport_precision);
        add_double(overlap_ledger, first_overlap_field,
            "maximum_source_area_relative_closure_error",
            transport.maximum_source_area_relative_closure_error,
            transport_precision);
        add_double(overlap_ledger, first_overlap_field,
            "maximum_destination_partition_closure_error_km2",
            transport.maximum_destination_partition_closure_error_km2,
            transport_precision);
        add_int(overlap_ledger, first_overlap_field,
            "maximum_coverage_arrangement_line_count",
            transport.maximum_coverage_arrangement_line_count);
        add_int(overlap_ledger, first_overlap_field,
            "maximum_coverage_arrangement_fragment_count",
            transport.maximum_coverage_arrangement_fragment_count);
        add_raw(overlap_ledger, first_overlap_field,
            "global_uncovered_gap_area_km2",
            roundtrip_num(transport.global_uncovered_gap_area_km2));
        add_raw(overlap_ledger, first_overlap_field,
            "global_overlap_excess_area_km2",
            roundtrip_num(transport.global_overlap_excess_area_km2));
        add_raw(overlap_ledger, first_overlap_field,
            "global_gap_overlap_balance_residual_km2",
            roundtrip_num(
                transport.global_overlap_excess_area_km2 -
                    transport.global_uncovered_gap_area_km2
            ));
        std::string source_inventory = "{";
        bool first_source_inventory = true;
        add_double(source_inventory, first_source_inventory,
            "crust_volume_km3", transport.initial_crust_volume_km3,
            transport_precision);
        add_double(source_inventory, first_source_inventory,
            "density_weighted_crust_volume",
            transport.initial_density_weighted_crust_volume,
            transport_precision);
        add_double(source_inventory, first_source_inventory,
            "crust_age_volume_moment_km3_ma",
            transport.initial_crust_age_volume_moment,
            transport_precision);
        source_inventory += "}";
        add_raw(overlap_ledger, first_overlap_field, "source_inventory",
            source_inventory);
        std::string transported_inventory = "{";
        bool first_transported_inventory = true;
        add_double(transported_inventory, first_transported_inventory,
            "crust_volume_km3", transport.transported_crust_volume_km3,
            transport_precision);
        add_double(transported_inventory, first_transported_inventory,
            "density_weighted_crust_volume",
            transport.transported_density_weighted_crust_volume,
            transport_precision);
        add_double(transported_inventory, first_transported_inventory,
            "crust_age_volume_moment_km3_ma",
            transport.transported_crust_age_volume_moment,
            transport_precision);
        transported_inventory += "}";
        add_raw(overlap_ledger, first_overlap_field, "transported_inventory",
            transported_inventory);
        std::string post_process_inventory = "{";
        bool first_post_process_inventory = true;
        add_double(post_process_inventory, first_post_process_inventory,
            "crust_volume_km3", step.post_process_crust_volume_km3,
            transport_precision);
        add_double(post_process_inventory, first_post_process_inventory,
            "density_weighted_crust_volume",
            step.post_process_density_weighted_crust_volume,
            transport_precision);
        add_double(post_process_inventory, first_post_process_inventory,
            "crust_age_volume_moment_km3_ma",
            step.post_process_crust_age_volume_moment,
            transport_precision);
        post_process_inventory += "}";
        add_raw(overlap_ledger, first_overlap_field, "post_process_inventory",
            post_process_inventory);
        std::string process_inventory_delta = "{";
        bool first_process_inventory_delta = true;
        add_double(process_inventory_delta, first_process_inventory_delta,
            "crust_volume_km3",
            step.post_process_crust_volume_km3 -
                transport.transported_crust_volume_km3,
            transport_precision);
        add_double(process_inventory_delta, first_process_inventory_delta,
            "density_weighted_crust_volume",
            step.post_process_density_weighted_crust_volume -
                transport.transported_density_weighted_crust_volume,
            transport_precision);
        add_double(process_inventory_delta, first_process_inventory_delta,
            "crust_age_volume_moment_km3_ma",
            step.post_process_crust_age_volume_moment -
                transport.transported_crust_age_volume_moment,
            transport_precision);
        process_inventory_delta += "}";
        add_raw(overlap_ledger, first_overlap_field, "process_inventory_delta",
            process_inventory_delta);
        const double process_volume_delta =
            step.post_process_crust_volume_km3 -
                transport.transported_crust_volume_km3;
        const double process_density_volume_delta =
            step.post_process_density_weighted_crust_volume -
                transport.transported_density_weighted_crust_volume;
        const double process_age_moment_delta =
            step.post_process_crust_age_volume_moment -
                transport.transported_crust_age_volume_moment;
        double attributed_volume_delta = 0.0;
        double attributed_density_volume_delta = 0.0;
        double attributed_age_moment_delta = 0.0;
        std::string reason_records = "[";
        for (int reason_index = 0;
             reason_index < CRUST_PROCESS_REASON_COUNT;
             ++reason_index) {
            if (reason_index > 0) {
                reason_records += ",";
            }
            const CrustProcessInventoryDelta& reason =
                step.process_inventory_delta_by_reason[
                    static_cast<std::size_t>(reason_index)
                ];
            attributed_volume_delta += reason.crust_volume_km3;
            attributed_density_volume_delta +=
                reason.density_weighted_crust_volume;
            attributed_age_moment_delta +=
                reason.crust_age_volume_moment_km3_ma;
            reason_records += "{";
            bool first_reason_field = true;
            add_str(
                reason_records,
                first_reason_field,
                "reason",
                CRUST_PROCESS_REASON_NAMES[reason_index]
            );
            add_int(
                reason_records,
                first_reason_field,
                "triggered_cell_count",
                reason.triggered_cell_count
            );
            add_int(
                reason_records,
                first_reason_field,
                "extensive_state_changed_cell_count",
                reason.changed_cell_count
            );
            add_raw(
                reason_records,
                first_reason_field,
                "positive_delta",
                crust_extensive_delta_json(
                    reason.positive_crust_volume_km3,
                    reason.positive_density_weighted_crust_volume,
                    reason.positive_crust_age_volume_moment_km3_ma,
                    transport_precision
                )
            );
            add_raw(
                reason_records,
                first_reason_field,
                "negative_delta_magnitude",
                crust_extensive_delta_json(
                    reason.negative_crust_volume_magnitude_km3,
                    reason.negative_density_weighted_crust_volume_magnitude,
                    reason.negative_crust_age_volume_moment_magnitude_km3_ma,
                    transport_precision
                )
            );
            add_raw(
                reason_records,
                first_reason_field,
                "net_delta",
                crust_extensive_delta_json(
                    reason.crust_volume_km3,
                    reason.density_weighted_crust_volume,
                    reason.crust_age_volume_moment_km3_ma,
                    transport_precision
                )
            );
            reason_records += "}";
        }
        reason_records += "]";
        const double residual_volume_delta =
            process_volume_delta - attributed_volume_delta;
        const double residual_density_volume_delta =
            process_density_volume_delta - attributed_density_volume_delta;
        const double residual_age_moment_delta =
            process_age_moment_delta - attributed_age_moment_delta;
        std::string process_attribution = "{";
        bool first_attribution_field = true;
        add_str(
            process_attribution,
            first_attribution_field,
            "format",
            "sequential_rule_extensive_state_delta_v1"
        );
        add_str(
            process_attribution,
            first_attribution_field,
            "semantics",
            "ordered_rule_state_moment_changes_not_physical_material_provenance"
        );
        add_bool(
            process_attribution,
            first_attribution_field,
            "order_dependent",
            true
        );
        add_raw(
            process_attribution,
            first_attribution_field,
            "reasons",
            reason_records
        );
        add_raw(
            process_attribution,
            first_attribution_field,
            "attributed_inventory_delta",
            crust_extensive_delta_json(
                attributed_volume_delta,
                attributed_density_volume_delta,
                attributed_age_moment_delta,
                transport_precision
            )
        );
        add_raw(
            process_attribution,
            first_attribution_field,
            "numerical_closure_residual",
            crust_extensive_delta_json(
                residual_volume_delta,
                residual_density_volume_delta,
                residual_age_moment_delta,
                transport_precision
            )
        );
        add_raw(
            process_attribution,
            first_attribution_field,
            "reconciled_inventory_delta",
            crust_extensive_delta_json(
                attributed_volume_delta + residual_volume_delta,
                attributed_density_volume_delta + residual_density_volume_delta,
                attributed_age_moment_delta + residual_age_moment_delta,
                transport_precision
            )
        );
        process_attribution += "}";
        add_raw(
            overlap_ledger,
            first_overlap_field,
            "process_inventory_attribution",
            process_attribution
        );
        overlap_ledger += "}";
        add_raw(out, first, "crust_overlap_ledger", overlap_ledger);

        const CrustOverlapCandidateFateLedger& candidate_fate =
            step.crust_overlap_candidate_fate_ledger;
        std::string candidate_fate_ledger = "{";
        bool first_candidate_fate_field = true;
        add_str(candidate_fate_ledger, first_candidate_fate_field, "format",
            "sparse_membership_class_to_uniform_boundary_plate_pair_candidate_v1");
        add_int(candidate_fate_ledger, first_candidate_fate_field,
            "source_plate_assignment_step_id",
            candidate_fate.source_plate_assignment_step_id);
        add_int(candidate_fate_ledger, first_candidate_fate_field,
            "boundary_plate_assignment_step_id",
            candidate_fate.boundary_plate_assignment_step_id);

        std::string pair_evidence = "[";
        bool first_pair_evidence = true;
        for (const CrustOverlapBoundaryPairEvidence& pair :
             candidate_fate.boundary_pair_evidence) {
            comma(pair_evidence, first_pair_evidence);
            pair_evidence += "{";
            bool first_pair_field = true;
            add_int(pair_evidence, first_pair_field, "pair_id", pair.pair_id);
            add_int(pair_evidence, first_pair_field, "plate_low_id",
                pair.plate_low_id);
            add_int(pair_evidence, first_pair_field, "plate_high_id",
                pair.plate_high_id);
            add_raw(pair_evidence, first_pair_field, "segment_ids",
                int_array_json(pair.segment_ids));
            add_str(pair_evidence, first_pair_field,
                "physical_consensus_status", pair.physical_consensus_status);
            add_int(pair_evidence, first_pair_field,
                "physical_subducting_plate_id",
                pair.physical_subducting_plate_id);
            add_int(pair_evidence, first_pair_field,
                "physical_overriding_plate_id",
                pair.physical_overriding_plate_id);
            add_str(pair_evidence, first_pair_field,
                "heuristic_consensus_status", pair.heuristic_consensus_status);
            add_int(pair_evidence, first_pair_field,
                "heuristic_subducting_plate_id",
                pair.heuristic_subducting_plate_id);
            add_int(pair_evidence, first_pair_field,
                "heuristic_overriding_plate_id",
                pair.heuristic_overriding_plate_id);
            pair_evidence += "}";
        }
        pair_evidence += "]";
        add_raw(candidate_fate_ledger, first_candidate_fate_field,
            "boundary_pair_evidence", pair_evidence);

        std::string class_candidates = "[";
        bool first_class_candidate = true;
        for (const CrustOverlapClassCandidate& candidate :
             candidate_fate.overlap_class_candidates) {
            comma(class_candidates, first_class_candidate);
            class_candidates += "{";
            bool first_candidate_field = true;
            add_int(class_candidates, first_candidate_field,
                "membership_area_class_id",
                candidate.membership_area_class_id);
            add_int(class_candidates, first_candidate_field,
                "destination_cell_id", candidate.destination_cell_id);
            add_int(class_candidates, first_candidate_field, "multiplicity",
                candidate.multiplicity);
            add_int(class_candidates, first_candidate_field,
                "boundary_pair_evidence_id",
                candidate.boundary_pair_evidence_id);
            add_str(class_candidates, first_candidate_field,
                "assignment_status", candidate.assignment_status);
            add_int(class_candidates, first_candidate_field,
                "candidate_subducting_contributor_id",
                candidate.candidate_subducting_contributor_id);
            add_int(class_candidates, first_candidate_field,
                "candidate_overriding_contributor_id",
                candidate.candidate_overriding_contributor_id);
            class_candidates += "}";
        }
        class_candidates += "]";
        add_raw(candidate_fate_ledger, first_candidate_fate_field,
            "overlap_class_candidates", class_candidates);
        add_raw(candidate_fate_ledger, first_candidate_fate_field,
            "physical_polarity_backed_candidate_excess_area_km2",
            roundtrip_num(
                candidate_fate.physical_polarity_backed_candidate_excess_area_km2
            ));
        add_raw(candidate_fate_ledger, first_candidate_fate_field,
            "oceanic_heuristic_candidate_excess_area_km2",
            roundtrip_num(
                candidate_fate.oceanic_heuristic_candidate_excess_area_km2
            ));
        add_raw(candidate_fate_ledger, first_candidate_fate_field,
            "unresolved_candidate_excess_area_km2",
            roundtrip_num(candidate_fate.unresolved_candidate_excess_area_km2));
        add_raw(candidate_fate_ledger, first_candidate_fate_field,
            "accounted_overlap_excess_area_km2",
            roundtrip_num(candidate_fate.accounted_overlap_excess_area_km2));
        add_raw(candidate_fate_ledger, first_candidate_fate_field,
            "candidate_partition_residual_km2",
            roundtrip_num(candidate_fate.candidate_partition_residual_km2));
        candidate_fate_ledger += "}";
        add_raw(out, first, "crust_overlap_candidate_fate_ledger",
            candidate_fate_ledger);

        std::string boundary_segments = "[";
        bool first_boundary_segment = true;
        for (const PlateBoundarySegment& segment : step.boundary_segments) {
            comma(boundary_segments, first_boundary_segment);
            boundary_segments += "{";
            bool first_segment_field = true;
            const auto add_segment_double = [&](const char* key, double value) {
                add_raw(
                    boundary_segments,
                    first_segment_field,
                    key,
                    roundtrip_num(value)
                );
            };
            add_int(boundary_segments, first_segment_field, "segment_id",
                segment.segment_id);
            add_int(boundary_segments, first_segment_field,
                "mesh_segment_id", segment.mesh_segment_id);
            add_int(boundary_segments, first_segment_field, "left_cell_id",
                segment.left_cell_id);
            add_int(boundary_segments, first_segment_field, "right_cell_id",
                segment.right_cell_id);
            add_int(boundary_segments, first_segment_field,
                "left_edge_index", segment.left_edge_index);
            add_int(boundary_segments, first_segment_field,
                "right_edge_index", segment.right_edge_index);
            add_int(boundary_segments, first_segment_field, "left_plate_id",
                segment.left_plate_id);
            add_int(boundary_segments, first_segment_field, "right_plate_id",
                segment.right_plate_id);
            add_segment_double("start_unit_x", segment.start_unit.x);
            add_segment_double("start_unit_y", segment.start_unit.y);
            add_segment_double("start_unit_z", segment.start_unit.z);
            add_segment_double("midpoint_unit_x", segment.midpoint_unit.x);
            add_segment_double("midpoint_unit_y", segment.midpoint_unit.y);
            add_segment_double("midpoint_unit_z", segment.midpoint_unit.z);
            add_segment_double("end_unit_x", segment.end_unit.x);
            add_segment_double("end_unit_y", segment.end_unit.y);
            add_segment_double("end_unit_z", segment.end_unit.z);
            add_segment_double("tangent_unit_x", segment.tangent_unit.x);
            add_segment_double("tangent_unit_y", segment.tangent_unit.y);
            add_segment_double("tangent_unit_z", segment.tangent_unit.z);
            add_segment_double(
                "left_to_right_normal_unit_x",
                segment.left_to_right_normal_unit.x
            );
            add_segment_double(
                "left_to_right_normal_unit_y",
                segment.left_to_right_normal_unit.y
            );
            add_segment_double(
                "left_to_right_normal_unit_z",
                segment.left_to_right_normal_unit.z
            );
            add_segment_double("angular_length_rad", segment.angular_length_rad);
            add_segment_double("length_km", segment.length_km);
            add_segment_double(
                "left_euler_velocity_x_km_per_ma",
                segment.left_euler_velocity_km_per_ma.x
            );
            add_segment_double(
                "left_euler_velocity_y_km_per_ma",
                segment.left_euler_velocity_km_per_ma.y
            );
            add_segment_double(
                "left_euler_velocity_z_km_per_ma",
                segment.left_euler_velocity_km_per_ma.z
            );
            add_segment_double(
                "right_euler_velocity_x_km_per_ma",
                segment.right_euler_velocity_km_per_ma.x
            );
            add_segment_double(
                "right_euler_velocity_y_km_per_ma",
                segment.right_euler_velocity_km_per_ma.y
            );
            add_segment_double(
                "right_euler_velocity_z_km_per_ma",
                segment.right_euler_velocity_km_per_ma.z
            );
            add_segment_double(
                "relative_velocity_x_km_per_ma",
                segment.relative_velocity_km_per_ma.x
            );
            add_segment_double(
                "relative_velocity_y_km_per_ma",
                segment.relative_velocity_km_per_ma.y
            );
            add_segment_double(
                "relative_velocity_z_km_per_ma",
                segment.relative_velocity_km_per_ma.z
            );
            add_segment_double(
                "signed_opening_rate_km_per_ma",
                segment.signed_opening_rate_km_per_ma
            );
            add_segment_double(
                "signed_convergence_rate_km_per_ma",
                segment.signed_convergence_rate_km_per_ma
            );
            add_segment_double(
                "signed_slip_rate_km_per_ma",
                segment.signed_slip_rate_km_per_ma
            );
            add_segment_double(
                "signed_opening_index",
                segment.signed_opening_index
            );
            add_segment_double(
                "signed_convergence_index",
                segment.signed_convergence_index
            );
            add_segment_double("signed_slip_index", segment.signed_slip_index);
            add_segment_double(
                "direct_convergent_strength",
                segment.direct_convergent_strength
            );
            add_segment_double(
                "direct_divergent_strength",
                segment.direct_divergent_strength
            );
            add_segment_double(
                "direct_transform_strength",
                segment.direct_transform_strength
            );
            add_str(boundary_segments, first_segment_field,
                "direct_boundary_class", segment.direct_boundary_class);
            add_bool(boundary_segments, first_segment_field,
                "convergence_active", segment.convergence_active);
            add_int(boundary_segments, first_segment_field,
                "left_opening_crust_type",
                segment.left_opening_crust_type);
            add_int(boundary_segments, first_segment_field,
                "left_opening_lithology", segment.left_opening_lithology);
            add_segment_double(
                "left_opening_crust_age_ma",
                segment.left_opening_crust_age_ma
            );
            add_segment_double(
                "left_opening_crust_thickness_km",
                segment.left_opening_crust_thickness_km
            );
            add_segment_double(
                "left_opening_crust_density_g_cm3",
                segment.left_opening_crust_density_g_cm3
            );
            add_bool(boundary_segments, first_segment_field,
                "left_opening_crust_state_available",
                segment.left_opening_crust_state_available);
            add_bool(boundary_segments, first_segment_field,
                "left_opening_oceanic_like",
                segment.left_opening_oceanic_like);
            add_int(boundary_segments, first_segment_field,
                "right_opening_crust_type",
                segment.right_opening_crust_type);
            add_int(boundary_segments, first_segment_field,
                "right_opening_lithology", segment.right_opening_lithology);
            add_segment_double(
                "right_opening_crust_age_ma",
                segment.right_opening_crust_age_ma
            );
            add_segment_double(
                "right_opening_crust_thickness_km",
                segment.right_opening_crust_thickness_km
            );
            add_segment_double(
                "right_opening_crust_density_g_cm3",
                segment.right_opening_crust_density_g_cm3
            );
            add_bool(boundary_segments, first_segment_field,
                "right_opening_crust_state_available",
                segment.right_opening_crust_state_available);
            add_bool(boundary_segments, first_segment_field,
                "right_opening_oceanic_like",
                segment.right_opening_oceanic_like);
            add_str(boundary_segments, first_segment_field,
                "polarity_candidate_status",
                segment.polarity_candidate_status);
            add_str(boundary_segments, first_segment_field,
                "candidate_subducting_side",
                segment.candidate_subducting_side);
            add_str(boundary_segments, first_segment_field,
                "candidate_overriding_side",
                segment.candidate_overriding_side);
            add_str(boundary_segments, first_segment_field,
                "physical_polarity_status",
                segment.physical_polarity_status);
            add_str(boundary_segments, first_segment_field,
                "physical_polarity_source",
                segment.physical_polarity_source);
            add_str(boundary_segments, first_segment_field,
                "physical_subducting_side",
                segment.physical_subducting_side);
            add_str(boundary_segments, first_segment_field,
                "physical_overriding_side",
                segment.physical_overriding_side);
            add_segment_double(
                "physical_polarity_confidence",
                segment.physical_polarity_confidence
            );
            boundary_segments += "}";
        }
        boundary_segments += "]";
        add_raw(out, first, "boundary_segments", boundary_segments);
        add_raw(out, first, "crust_type_by_cell", int_array_json(step.crust_type_by_cell));
        add_raw(out, first, "lithology_by_cell", int_array_json(step.lithology_by_cell));
        add_raw(out, first, "boundary_convergent_by_cell",
            roundtrip_double_array_json(step.boundary_convergent_by_cell));
        add_raw(out, first, "boundary_divergent_by_cell",
            roundtrip_double_array_json(step.boundary_divergent_by_cell));
        add_raw(out, first, "boundary_transform_by_cell",
            roundtrip_double_array_json(step.boundary_transform_by_cell));
        add_raw(out, first, "crust_transport_distance_km_by_cell",
            roundtrip_double_array_json(step.crust_transport_distance_km_by_cell));
        add_raw(out, first, "crust_age_change_ma_by_cell",
            roundtrip_double_array_json(step.crust_age_change_ma_by_cell));
        add_raw(out, first, "crust_thickness_change_km_by_cell",
            roundtrip_double_array_json(step.crust_thickness_change_km_by_cell));
        add_raw(out, first, "crust_density_change_by_cell",
            roundtrip_double_array_json(step.crust_density_change_by_cell));
        add_raw(out, first, "crust_age_transport_change_ma_by_cell",
            roundtrip_double_array_json(step.crust_age_transport_change_ma_by_cell));
        add_raw(out, first, "crust_thickness_transport_change_km_by_cell",
            roundtrip_double_array_json(step.crust_thickness_transport_change_km_by_cell));
        add_raw(out, first, "crust_density_transport_change_by_cell",
            roundtrip_double_array_json(step.crust_density_transport_change_by_cell));
        add_raw(out, first, "crust_age_process_change_ma_by_cell",
            roundtrip_double_array_json(step.crust_age_process_change_ma_by_cell));
        add_raw(out, first, "crust_thickness_process_change_km_by_cell",
            roundtrip_double_array_json(step.crust_thickness_process_change_km_by_cell));
        add_raw(out, first, "crust_density_process_change_by_cell",
            roundtrip_double_array_json(step.crust_density_process_change_by_cell));
        add_raw(out, first, "tectonic_elevation_change_m_by_cell",
            roundtrip_double_array_json(
                step.tectonic_elevation_change_m_by_cell
            ));
        add_raw(out, first, "previous_local_isostatic_equilibrium_m",
            roundtrip_double_array_json(
                step.previous_local_isostatic_equilibrium_m
            ));
        add_raw(out, first, "post_process_local_isostatic_equilibrium_m",
            roundtrip_double_array_json(
                step.post_process_local_isostatic_equilibrium_m
            ));
        add_raw(out, first, "isostatic_equilibrium_change_m",
            roundtrip_double_array_json(
                step.isostatic_equilibrium_change_m
            ));
        add_raw(out, first, "previous_local_thermal_subsidence_target_m",
            roundtrip_double_array_json(
                step.previous_local_thermal_subsidence_target_m
            ));
        add_raw(out, first, "post_process_local_thermal_subsidence_target_m",
            roundtrip_double_array_json(
                step.post_process_local_thermal_subsidence_target_m
            ));
        add_raw(out, first, "thermal_equilibrium_change_m",
            roundtrip_double_array_json(
                step.thermal_equilibrium_change_m
            ));
        add_raw(out, first, "unbounded_dynamic_relief_change_m",
            roundtrip_double_array_json(
                step.unbounded_dynamic_relief_change_m
            ));
        add_raw(out, first, "bounded_dynamic_relief_change_m",
            roundtrip_double_array_json(
                step.bounded_dynamic_relief_change_m
            ));
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
            add_raw(plate_snapshots, first_snapshot_field, "center",
                vec3_json(plate.center, transport_precision));
            add_raw(plate_snapshots, first_snapshot_field, "rotation_axis",
                vec3_json(plate.rotation_axis, transport_precision));
            add_double(plate_snapshots, first_snapshot_field,
                "intrinsic_angular_speed", plate.intrinsic_angular_speed,
                transport_precision);
            add_double(plate_snapshots, first_snapshot_field, "step_rotation_deg",
                plate.step_rotation_deg, transport_precision);
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
