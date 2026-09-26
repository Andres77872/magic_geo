#include "internal.hpp"
#include "generation_progress.hpp"
#include "seasonal_climate_serialization.hpp"
#include "world.hpp"

namespace magic_geo::detail {

namespace {

const PrescribedSeasonalClimate& require_retained_climate(
    const Params& params,
    const EarthSystemState& earth
) {
    const auto* state = earth.climate_cache.last_result();
    if (!state || state->mesh_backend != params.mesh_backend ||
        state->options != make_prescribed_seasonal_climate_options(params) ||
        state->physical_columns.columns.size() != earth.cells.size()) {
        throw std::runtime_error("seasonal climate output requires the matching retained producer state");
    }
    // Lakes and later ice labels intentionally differ from the pre-flow
    // prescribed thermal surface. Verify the retained temperature interface,
    // not a newly manufactured solve from these downstream classifications.
    for (std::size_t i = 0; i < earth.cells.size(); ++i) {
        const auto& cell = earth.cells[i];
        if (cell.id != static_cast<int>(i) || cell.lat != state->latitudes_rad.at(i) ||
            cell.temperature_c != prescribed_climate_annual_temperature_c(*state, i)) {
            throw std::runtime_error("seasonal annual temperature changed after the retained solve");
        }
        for (std::size_t month = 0; month < 12; ++month) {
            if (cell.temperature_monthly_c[month] != state->solution.year.months[month].mean_temperature_k.at(i) - 273.15) {
                throw std::runtime_error("seasonal monthly temperature changed after the retained solve");
            }
        }
    }
    return *state;
}

std::string prescribed_climate_model_json(const Params& params, const PrescribedSeasonalClimate& state) {
    std::string out = "{";
    bool first = true;
    const auto number = [&](const char* key, double value) { add_raw(out, first, key, roundtrip_num(value)); };
    add_str(out, first, "model_type", "prescribed_seasonal_surface_energy_v1");
    add_str(out, first, "temperature_model", "periodic_graybody_storage_conservative_transport_v1");
    add_str(out, first, "temperature_interpretation", "prescribed_surface_column_temperature_used_as_near_surface_climate_proxy");
    add_str(out, first, "temperature_source", "climate_energy_balance_records_monthly_mean_temperature_k");
    add_str(out, first, "temperature_annual_mean", "accepted_month_duration_weighted_mean_kelvin_minus_273_15");
    add_int(out, first, "display_temperature_decimal_places", params.float_precision);
    add_int(out, first, "configured_month_count", params.months);
    add_bool(out, first, "native_temperature_forcing_coupled", true);
    add_bool(out, first, "imposed_mean_temperature", false);
    add_bool(out, first, "post_solve_temperature_adjustments", false);
    add_bool(out, first, "transient_climate_resolved", false);
    add_bool(out, first, "periodic_seasonal_cycle_resolved", true);
    add_bool(out, first, "prescribed_atmospheric_mass_conserved", true);
    add_bool(out, first, "mass_conserving_atmospheric_circulation", false);
    add_bool(out, first, "lake_ice_cloud_biome_feedback_resolved", false);
    add_str(out, first, "prescribed_surface_scope", "fresh_marine_and_exposed_land_before_flow_lake_and_cryosphere_diagnostics");
    number("reference_infrared_optical_depth", state.options.atmosphere.reference_infrared_optical_depth);
    add_str(out, first, "greenhouse_factor_interpretation", "reference_infrared_optical_depth_multiplier");
    number("solved_area_time_mean_temperature_c", prescribed_climate_global_mean_temperature_c(state));
    add_str(out, first, "precipitation_model", "solved_temperature_scaled_empirical_circulation_orography_wind_transport_v1");
    number("precipitation_scale", params.precipitation_scale);
    number("subtropical_drying_strength", params.subtropical_drying_strength);
    number("subtropical_drying_min_factor", CLIMATE_SUBTROPICAL_DRYING_MIN_FACTOR);
    number("seasonal_monsoon_precipitation_strength", CLIMATE_SEASONAL_MONSOON_PRECIPITATION_STRENGTH);
    number("seasonal_monsoon_precipitation_min_factor", CLIMATE_SEASONAL_MONSOON_PRECIPITATION_MIN_FACTOR);
    number("seasonal_monsoon_precipitation_max_factor", CLIMATE_SEASONAL_MONSOON_PRECIPITATION_MAX_FACTOR);
    add_str(out, first, "thermal_moisture_capacity_model", "bounded_exponential_solved_area_time_mean_temperature_v1");
    add_str(out, first, "thermal_moisture_capacity_scope", "empirical_global_monthly_precipitation_multiplier");
    number("thermal_moisture_capacity_reference_temperature_c", CLIMATE_THERMAL_MOISTURE_REFERENCE_BASE_TEMPERATURE_C);
    number("thermal_moisture_capacity_temperature_response_per_c", CLIMATE_THERMAL_MOISTURE_RESPONSE_PER_C);
    number("thermal_moisture_capacity_min_factor", CLIMATE_THERMAL_MOISTURE_MIN_FACTOR);
    number("thermal_moisture_capacity_max_factor", CLIMATE_THERMAL_MOISTURE_MAX_FACTOR);
    number("thermal_moisture_capacity_factor", prescribed_climate_thermal_moisture_factor(state));
    add_str(out, first, "negative_precipitation_behavior", "clamped_to_zero_before_thermal_moisture_multiplier");
    add_str(out, first, "zero_precipitation_scale_behavior", "exact_zero_monthly_and_annual_precipitation");
    add_str(out, first, "airless_precipitation_behavior", "exact_zero_monthly_and_annual_precipitation");
    add_str(out, first, "circulation_scope", "empirical_wind_current_and_moisture_descriptors_distinct_from_conservative_heat_transport");
    add_str(out, first, "model_limitation", "prescribed_thermal_columns_with_empirical_rainfall_no_solved_latent_heat_cloud_ice_lake_or_three_dimensional_circulation_feedback");
    return out + "}";
}

}  // namespace

std::string crust_material_shadow_model_json();
std::string crust_material_shadow_history_json(
    const std::vector<CrustMaterialShadowStep>& history
);
std::string summary_with_crust_material_shadow_json(
    std::string summary,
    const std::vector<CrustMaterialShadowStep>& history
);
std::string crust_dry_rock_accounting_model_json();
std::string crust_dry_rock_accounting_history_json(
    const std::vector<CrustDryRockAccountingStep>& history
);
std::string summary_with_crust_dry_rock_accounting_json(
    std::string summary,
    const std::vector<CrustDryRockAccountingStep>& history
);

std::string planet_parameters_json(const Params& params) {
    std::string out = "{";
    bool first = true;
    add_raw(out, first, "radius_km", roundtrip_num(params.radius_km));
    add_raw(out, first, "gravity_g", roundtrip_num(params.gravity_g));
    add_raw(out, first, "day_length_hours", roundtrip_num(params.day_length_hours));
    add_raw(out, first, "axial_tilt_deg", roundtrip_num(params.axial_tilt_deg));
    add_raw(out, first, "orbital_eccentricity", roundtrip_num(params.orbital_eccentricity));
    add_raw(out, first, "stellar_luminosity", roundtrip_num(params.stellar_luminosity));
    add_raw(out, first, "atmosphere_pressure_bar", roundtrip_num(params.atmosphere_pressure_bar));
    add_raw(out, first, "greenhouse_factor", roundtrip_num(params.greenhouse_factor));
    add_raw(out, first, "ocean_fraction_target", roundtrip_num(params.ocean_fraction_target));
    add_raw(out, first, "ocean_water_inventory_km3", roundtrip_num(params.ocean_water_inventory_km3));
    add_raw(out, first, "internal_heat", roundtrip_num(params.internal_heat));
    add_raw(out, first, "geological_age_ga", roundtrip_num(params.geological_age_ga));
    out += "}";
    return out;
}

std::string serialize_world(const Params& params, const GeneratedWorld& world) {
    emit_generation_progress("native_output", "Assembling the simulated world", "Serializing terrain, climate, water and linked records for geographic enrichment.");
    const EarthSystemState& earth = world.earth;
    const NaturalArtifacts& natural = world.natural;
    const SocietyArtifacts& society = world.society;

    std::string out = "{";
    bool first = true;
    add_int(out, first, "schema_version", 2);
    add_str(out, first, "name", params.name);
    add_raw(out, first, "planet_parameters", planet_parameters_json(params));
    add_str(out, first, "mesh_backend", mesh_backend_name(params.mesh_backend));
    add_str(out, first, "cell_area_model", cell_area_model_name(params.mesh_backend));
    add_raw(out, first, "summary",
        summary_with_crust_dry_rock_accounting_json(
            summary_with_crust_material_shadow_json(summary_json(
            params,
            earth.cells,
            natural.watersheds,
            natural.lake_basins,
            natural.coastal_features,
            natural.sedimentary_basins,
            natural.stratigraphic_columns,
            natural.ice_sheets,
            society.political_regions,
            society.borders,
            society.trade_flows,
            society.cultural_layers,
            society.historical_layers,
            society.population_regions,
            society.conflicts,
            society.dynasties,
            society.territorial_snapshots,
            world.calibration_checks,
            society.settlements,
            society.routes,
            earth.feedback_history,
            earth.plate_motion_history,
            earth.numeric_depression_correction_history,
            earth.hillslope_transport_history,
            earth.glacial_transport_history,
            &society.availability
            ), earth.crust_material_shadow.history),
            earth.crust_dry_rock_accounting.history
        ));
    add_raw(out, first, "backend", backend_info_json());
    if (params.temperature_model == ClimateTemperatureModel::prescribed_seasonal) {
        const auto& state = require_retained_climate(params, earth);
        const auto energy = serialize_prescribed_seasonal_energy(earth.climate_cache);
        add_raw(out, first, "climate_model", prescribed_climate_model_json(params, state));
        add_raw(out, first, "climate_energy_model", energy.model);
        add_raw(out, first, "climate_energy_forcing_intervals", energy.forcing_intervals);
        add_raw(out, first, "climate_energy_transport_edges", energy.transport_edges);
        add_raw(out, first, "climate_energy_balance_records", energy.balance_records);
    } else if (params.temperature_model == ClimateTemperatureModel::legacy_empirical) {
        if (earth.climate_cache.last_result()) {
            throw std::runtime_error("legacy climate output cannot discard a retained seasonal solve");
        }
        add_raw(out, first, "climate_model", climate_model_json(params));
    } else {
        throw std::runtime_error("cannot serialize an unknown climate temperature model");
    }
    add_raw(out, first, "hydrologic_water_budget_model",
        hydrologic_water_budget_model_json(
            earth.hydrologic_water_budget_history,
            params.float_precision
        ));
    add_raw(out, first, "hydrologic_water_budget_history",
        hydrologic_water_budget_history_json(
            params,
            earth.hydrologic_water_budget_history,
            params.float_precision
        ));
    add_raw(out, first, "simulation_clock",
        simulation_clock_json(params, earth.feedback_history));
    add_raw(out, first, "earth_system_feedback_history",
        earth_system_feedback_history_json(
            params,
            earth.feedback_history,
            params.float_precision
        ));
    add_raw(out, first, "sediment_interface_model",
        sediment_interface_model_json(
            earth.cells,
            params.float_precision
        ));
    add_raw(out, first, "sediment_inventory_model",
        sediment_inventory_model_json(
            earth.cells,
            earth.feedback_history,
            earth.numeric_depression_correction_history,
            earth.hillslope_transport_history,
            earth.sediment_routing_history,
            earth.glacial_transport_history,
            params.float_precision
        ));
    add_raw(out, first, "numeric_depression_correction_history",
        numeric_depression_correction_history_json(
            params,
            earth.numeric_depression_correction_history,
            params.float_precision
        ));
    add_raw(out, first, "hillslope_sediment_transport_model",
        hillslope_sediment_transport_model_json(
            params,
            earth.hillslope_transport_history
        ));
    add_raw(out, first, "hillslope_sediment_transport_history",
        hillslope_sediment_transport_history_json(
            params,
            earth.hillslope_transport_history,
            params.float_precision
        ));
    add_raw(out, first, "grounded_ice_model", grounded_ice_model_json());
    add_raw(out, first, "glacial_sediment_transport_model",
        glacial_sediment_transport_model_json(
            earth.glacial_transport_history,
            params.float_precision
        ));
    add_raw(out, first, "glacial_sediment_transport_history",
        glacial_sediment_transport_history_json(
            params,
            earth.glacial_transport_history,
            params.float_precision
        ));
    add_raw(out, first, "fluvial_sediment_routing_model",
        fluvial_sediment_routing_model_json(
            earth.sediment_routing_history,
            params.float_precision
        ));
    add_raw(out, first, "fluvial_sediment_routing_history",
        fluvial_sediment_routing_history_json(
            params,
            earth.sediment_routing_history,
            params.float_precision
        ));
    add_raw(out, first, "plate_kinematic_model",
        plate_kinematic_model_json(
            params,
            earth.plate_motion_history,
            earth.cells
        ));
    add_raw(out, first, "plate_boundary_segment_model",
        plate_boundary_segment_model_json(
            params,
            earth.plate_motion_history
        ));
    add_raw(out, first, "initial_oceanic_crust_age_model",
        initial_oceanic_crust_age_model_json(
            earth.initial_oceanic_crust_age
        ));
    add_raw(out, first, "initial_oceanic_crust_age_ledger",
        initial_oceanic_crust_age_ledger_json(
            earth.initial_oceanic_crust_age
        ));
    add_raw(out, first, "crust_overlap_candidate_fate_model",
        crust_overlap_candidate_fate_model_json());
    add_raw(out, first, "oceanic_age_depth_model",
        oceanic_age_depth_model_json());
    add_raw(out, first, "crust_material_shadow_model",
        crust_material_shadow_model_json());
    add_raw(out, first, "crust_dry_rock_accounting_model",
        crust_dry_rock_accounting_model_json());
    add_raw(out, first, "sea_level_model",
        sea_level_model_json(params, earth.cells));
    add_raw(out, first, "plate_motion_history",
        plate_motion_history_json(
            params,
            earth.plate_motion_history,
            params.float_precision
        ));
    add_raw(out, first, "crust_material_shadow_history",
        crust_material_shadow_history_json(
            earth.crust_material_shadow.history
        ));
    add_raw(out, first, "crust_dry_rock_accounting_history",
        crust_dry_rock_accounting_history_json(
            earth.crust_dry_rock_accounting.history
        ));
    add_raw(out, first, "plates",
        plates_json(earth.plates, params.float_precision));
    add_raw(out, first, "watersheds",
        watersheds_json(natural.watersheds, params.float_precision));
    add_raw(out, first, "lake_basins",
        lake_basins_json(natural.lake_basins, params.float_precision));
    add_raw(out, first, "coastal_features",
        coastal_features_json(natural.coastal_features, params.float_precision));
    add_raw(out, first, "sedimentary_basins",
        sedimentary_basins_json(
            natural.sedimentary_basins,
            params.float_precision
        ));
    add_raw(out, first, "stratigraphic_columns",
        stratigraphic_columns_json(
            natural.stratigraphic_columns,
            params.float_precision
        ));
    add_raw(out, first, "ice_sheets",
        ice_sheets_json(natural.ice_sheets, params.float_precision));
    add_raw(out, first, "political_regions",
        political_regions_json(
            society.political_regions,
            params.float_precision
        ));
    if (society.availability.enabled) {
        add_raw(out, first, "native_social_availability_model", native_social_model_json());
        add_raw(out, first, "native_social_availability", native_social_data_json(society.availability));
    }
    add_raw(out, first, "cultures",
        cultures_json(
            society.cultural_layers.cultures,
            params.float_precision, society.availability.enabled
        ));
    add_raw(out, first, "language_regions",
        language_regions_json(
            society.cultural_layers.language_regions,
            params.float_precision
        ));
    add_raw(out, first, "historical_eras",
        historical_eras_json(
            society.historical_layers.eras,
            params.float_precision, society.availability.enabled
        ));
    add_raw(out, first, "historical_events",
        historical_events_json(
            society.historical_layers.events,
            params.float_precision, society.availability.enabled
        ));
    add_raw(out, first, "population_regions",
        population_regions_json(
            society.population_regions,
            params.float_precision, society.availability.enabled
        ));
    add_raw(out, first, "conflicts",
        conflicts_json(society.conflicts, params.float_precision));
    add_raw(out, first, "dynasties",
        dynasties_json(society.dynasties, params.float_precision));
    add_raw(out, first, "territorial_snapshots",
        territorial_snapshots_json(
            society.territorial_snapshots,
            params.float_precision, society.availability.enabled
        ));
    add_raw(out, first, "calibration_checks",
        calibration_checks_json(
            world.calibration_checks,
            params.float_precision
        ));
    add_raw(out, first, "sacred_areas",
        sacred_areas_json(
            society.cultural_layers.sacred_areas,
            params.float_precision
        ));
    add_raw(out, first, "ruins",
        ruins_json(
            society.cultural_layers.ruins,
            params.float_precision
        ));
    add_raw(out, first, "borders",
        borders_json(society.borders, params.float_precision));
    add_raw(out, first, "settlements",
        settlements_json(
            earth.cells,
            society.settlements,
            params.float_precision
        ));
    add_raw(out, first, "routes",
        routes_json(society.routes, params.float_precision));
    add_raw(out, first, "trade_flows",
        trade_flows_json(society.trade_flows, params.float_precision));
    add_raw(out, first, "cells",
        params.include_cells ?
            cells_json(earth.cells, params.float_precision, params.temperature_model) : "[]");
    out += "}";
    return out;
}

}  // namespace magic_geo::detail
