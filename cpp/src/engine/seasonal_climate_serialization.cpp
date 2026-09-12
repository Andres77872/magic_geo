#include "seasonal_climate_serialization.hpp"

#include "internal.hpp"
#include "seasonal_climate_cache.hpp"

#include <stdexcept>
#include <utility>

namespace magic_geo::detail {
namespace {

// Keep budget witnesses separate from the ordinary display-precision helpers.
struct Object {
    std::string text = "{";
    bool first = true;
    void raw(const char* key, const std::string& value) { add_raw(text, first, key, value); }
    void number(const char* key, double value) { raw(key, roundtrip_num(value)); }
    void count(const char* key, std::uint64_t value) { raw(key, std::to_string(value)); }
    void integer(const char* key, int value) { add_int(text, first, key, value); }
    void flag(const char* key, bool value) { add_bool(text, first, key, value); }
    void string(const char* key, const std::string& value) { add_str(text, first, key, value); }
    std::string finish() { return std::move(text) + "}"; }
};

const char* method_name(SurfaceEnergyTimeMethod method) {
    switch (method) {
    case SurfaceEnergyTimeMethod::backward_euler: return "backward_euler";
    case SurfaceEnergyTimeMethod::tr_bdf2: return "tr_bdf2";
    }
    throw std::runtime_error("cannot serialize unknown seasonal time method");
}

std::string periodic_options_json(const PeriodicSurfaceEnergyOptions& options) {
    Object out;
    out.string("time_method", method_name(options.time_method));
    out.number("phase_tolerance_k", options.phase_tolerance_k);
    out.number("annual_flux_tolerance_w_m2", options.annual_flux_tolerance_w_m2);
    out.number("relative_tolerance", options.relative_tolerance);
    out.integer("maximum_periodic_iterations", options.maximum_periodic_iterations);
    out.integer("maximum_backtracks", options.maximum_backtracks);
    out.count("maximum_integration_steps", options.maximum_integration_steps);
    Object step;
    step.number("absolute_tolerance_w_m2", options.step.absolute_tolerance_w_m2);
    step.number("relative_tolerance", options.step.relative_tolerance);
    step.integer("maximum_newton_iterations", options.step.maximum_newton_iterations);
    step.integer("maximum_linear_iterations", options.step.maximum_linear_iterations);
    // duration_seconds is assigned from each physical child, not a fixed
    // global step. The accepted partition is published on the source nodes.
    step.string("duration_policy", "parent_duration_divided_by_thermal_subdivisions");
    out.raw("step", step.finish());
    std::string subdivisions = "[";
    for (std::size_t i = 0; i < options.thermal_subdivisions.size(); ++i) {
        if (i) subdivisions += ',';
        subdivisions += std::to_string(options.thermal_subdivisions[i]);
    }
    out.raw("thermal_subdivisions", subdivisions + ']');
    return out.finish();
}

std::string requested_accuracy_json(const AdaptivePeriodicSurfaceEnergyOptions& options) {
    Object out;
    out.raw("periodic", periodic_options_json(options.periodic));
    out.number("local_absolute_tolerance_k", options.local_absolute_tolerance_k);
    out.number("local_relative_tolerance", options.local_relative_tolerance);
    out.number("maximum_numerical_error_fraction", options.maximum_numerical_error_fraction);
    out.number("monthly_temperature_tolerance_k", options.monthly_temperature_tolerance_k);
    out.number("monthly_flux_tolerance_w_m2", options.monthly_flux_tolerance_w_m2);
    out.number("monthly_relative_tolerance", options.monthly_relative_tolerance);
    out.integer("required_monthly_refinement_confirmations", options.required_monthly_refinement_confirmations);
    out.count("maximum_accepted_steps_per_year", options.maximum_accepted_steps_per_year);
    out.count("maximum_total_step_attempts", options.maximum_total_step_attempts);
    out.integer("maximum_partition_refinements", options.maximum_partition_refinements);
    out.integer("maximum_solver_tightenings", options.maximum_solver_tightenings);
    return out.finish();
}

std::string model_json(const PrescribedSeasonalClimateCache& cache, const PrescribedSeasonalClimate& state) {
    const auto& options = state.options;
    const auto& atmosphere = options.atmosphere;
    const auto& physical = state.physical_columns;
    const auto& solution = state.solution;
    const auto& year = solution.year;
    Object out;
    out.string("model", "native_prescribed_seasonal_energy_v1");
    out.integer("budget_schema_version", 1);
    out.string("ownership", "native_temperature_producer");
    out.string("equation", "C_dT_dt_equals_absorbed_shortwave_minus_effective_longwave_plus_horizontal_heat_convergence");
    out.string("residual_sign", "storage_minus_absorbed_shortwave_plus_longwave_minus_horizontal_convergence");
    out.string("coefficient_model", "prescribed_hydrostatic_gray_marine_land_columns_v1");
    out.string("coefficient_source", "fresh_marine_and_exposed_land_before_flow_lake_and_cryosphere_diagnostics");
    out.flag("native_temperature_forcing_coupled", true);
    out.flag("surface_energy_budget_resolved", true);
    out.flag("coupled_atmosphere_ocean_energy_resolved", false);
    out.flag("lake_ice_cloud_biome_feedback_resolved", false);
    out.flag("terrain_iterations_are_elapsed_climate_years", false);
    out.string("temperature_interpretation", "prescribed_surface_column_temperature_used_as_near_surface_climate_proxy");
    out.string("precision", "roundtrip_binary64_independent_of_output_float_precision");
    out.string("monthly_error_interpretation", "observed_reconverged_refinement_change_not_absolute_error_certificate");
    out.flag("astronomical_refinement_independently_verified_for_this_world", false);
    out.string("time_method", method_name(solution.accepted_periodic_options.time_method));
    out.number("tr_bdf2_gamma", 2.0 - std::sqrt(2.0));
    out.string("accepted_step_quadrature", solution.accepted_periodic_options.time_method == SurfaceEnergyTimeMethod::tr_bdf2
        ? "start_stage_endpoint_weights_1_over_2sqrt2_1_over_2sqrt2_1_minus_1_over_sqrt2"
        : "accepted_endpoint");
    out.string("calendar", "twelve_equal_elapsed_time_months_periapsis_at_month_zero_center");
    out.number("year_duration_seconds", year.duration_seconds);
    out.number("requested_year_duration_seconds", options.year_duration_seconds);
    std::vector<double> durations;
    for (const auto& month : year.months) durations.push_back(month.duration_seconds);
    out.raw("monthly_duration_seconds", roundtrip_double_array_json(durations));
    out.string("solar_quadrature", "kepler_true_anomaly_midpoints_time_and_angle_bounded_v2");
    out.number("solar_constant_w_m2", SolarOrbitForcing::solar_constant_w_m2);
    out.number("solar_longitude_at_periapsis_deg", SolarOrbitForcing::solar_longitude_at_periapsis_deg);
    out.integer("forcing_refinement_level", options.forcing_refinement_level);
    out.number("maximum_true_anomaly_step_rad", std::ldexp(SolarOrbitForcing::maximum_true_anomaly_step_rad, -options.forcing_refinement_level));
    out.number("maximum_interval_fraction_of_year", std::ldexp(SolarOrbitForcing::maximum_interval_fraction_of_year, -options.forcing_refinement_level));
    out.count("maximum_stored_forcing_values", options.maximum_stored_forcing_values);
    out.number("radius_m", options.radius_m);
    out.integer("mesh_backend", state.mesh_backend);
    out.number("axial_tilt_deg", options.axial_tilt_deg);
    out.number("orbital_eccentricity", options.orbital_eccentricity);
    out.number("stellar_luminosity", options.stellar_luminosity);
    out.number("top_of_atmosphere_albedo", options.top_of_atmosphere_albedo);
    out.number("marine_mixed_layer_depth_m", options.marine_mixed_layer_depth_m);
    out.number("stefan_boltzmann_w_m2_k4", 5.670374419e-8);
    out.number("mean_surface_pressure_pa", atmosphere.mean_surface_pressure_pa);
    out.number("gravity_m_s2", atmosphere.gravity_m_s2);
    out.number("hydrostatic_profile_temperature_k", atmosphere.profile_temperature_k);
    out.number("reference_infrared_optical_depth", atmosphere.reference_infrared_optical_depth);
    out.number("greenhouse_factor", atmosphere.greenhouse_factor);
    out.number("atmospheric_diffusivity_m2_s", atmosphere.atmospheric_diffusivity_m2_s);
    out.number("dry_air_gas_constant_j_kg_k", CLIMATE_DRY_AIR_GAS_CONSTANT_J_KG_K);
    out.number("dry_air_heat_capacity_j_kg_k", CLIMATE_DRY_AIR_HEAT_CAPACITY_J_KG_K);
    out.number("reference_pressure_pa", CLIMATE_REFERENCE_PRESSURE_PA);
    out.number("reference_gravity_m_s2", CLIMATE_REFERENCE_GRAVITY_M_S2);
    out.number("land_surface_heat_capacity_j_m2_k", CLIMATE_LAND_SLAB_HEAT_CAPACITY_J_M2_K);
    out.number("water_volumetric_heat_capacity_j_m3_k", CLIMATE_WATER_VOLUMETRIC_HEAT_CAPACITY_J_M3_K);
    out.string("pressure_formula", "area_mean_normalized_p_mean_exp_minus_interface_elevation_over_scale_height");
    out.string("opacity_formula", "tau_ref_times_greenhouse_times_pressure_over_reference_times_reference_gravity_over_gravity");
    out.string("longwave_formula", "sigma_times_temperature_fourth_moment_divided_by_one_plus_three_tau_over_four");
    out.string("transport_model", state.mesh_backend == 0 ? "symmetric_voronoi_harmonic_interface_conductivity" : "symmetric_cotangent_triangle_mean_conductivity");
    out.number("total_area_m2", physical.total_area_m2);
    out.number("atmospheric_scale_height_m", physical.atmospheric_scale_height_m);
    out.number("area_weighted_mean_surface_pressure_pa", physical.area_weighted_mean_surface_pressure_pa);
    out.number("mean_surface_pressure_residual_pa", physical.mean_surface_pressure_residual_pa);
    out.number("total_atmospheric_mass_kg", physical.total_atmospheric_mass_kg);
    out.number("atmospheric_mass_residual_kg", physical.atmospheric_mass_residual_kg);
    out.number("atmospheric_scale_height_to_radius", state.atmospheric_scale_height_to_radius);
    out.number("maximum_interface_elevation_to_radius", state.maximum_interface_elevation_to_radius);
    out.raw("requested_accuracy", requested_accuracy_json(options.integration));
    out.raw("accepted_periodic_options", periodic_options_json(solution.accepted_periodic_options));
    Object achieved;
    achieved.number("maximum_phase_difference_k", year.maximum_phase_difference_k);
    achieved.number("maximum_annual_net_heating_w_m2", year.maximum_annual_net_heating_w_m2);
    achieved.number("global_annual_net_heating_w", year.global_annual_net_heating_w);
    achieved.number("maximum_step_balance_residual_w_m2", year.maximum_step_balance_residual_w_m2);
    achieved.number("maximum_local_error_ratio", solution.maximum_local_error_ratio);
    achieved.number("maximum_numerical_error_ratio", solution.maximum_numerical_error_ratio);
    achieved.number("maximum_endpoint_numerical_uncertainty_k", solution.maximum_endpoint_numerical_uncertainty_k);
    achieved.number("maximum_monthly_temperature_change_k", solution.maximum_monthly_temperature_change_k);
    achieved.number("maximum_monthly_flux_change_w_m2", solution.maximum_monthly_flux_change_w_m2);
    achieved.integer("monthly_refinement_confirmations", solution.monthly_refinement_confirmations);
    achieved.integer("partition_refinements", solution.partition_refinements);
    achieved.integer("solver_tightenings", solution.solver_tightenings);
    achieved.integer("final_periodic_iterations", year.periodic_iterations);
    achieved.integer("final_partition_year_evaluations", year.year_evaluations);
    achieved.count("accepted_steps_per_year", year.integration_step_count);
    achieved.count("final_partition_total_steps", year.total_integration_steps);
    achieved.count("accepted_year_newton_iterations", year.year_newton_iterations);
    achieved.count("accepted_year_linear_iterations", year.year_linear_iterations);
    achieved.count("estimator_trials", solution.estimator_trials);
    achieved.count("failed_estimator_trials", solution.failed_estimator_trials);
    achieved.count("total_periodic_year_evaluations", solution.total_periodic_year_evaluations);
    achieved.count("total_step_attempts", solution.total_step_attempts);
    achieved.count("completed_physical_solves", cache.completed_solve_count());
    achieved.flag("last_physical_solve_warm_started", cache.last_solve_was_warm_started());
    out.raw("achieved", achieved.finish());
    return out.finish();
}

std::string forcing_json(const PrescribedSeasonalClimate& state) {
    if (state.forcing_intervals.size() != state.solution.thermal_subdivisions.size()) {
        throw std::runtime_error("seasonal forcing and accepted partition do not match");
    }
    std::string out = "[";
    for (std::size_t i = 0; i < state.forcing_intervals.size(); ++i) {
        const auto& interval = state.forcing_intervals[i];
        Object node;
        node.count("id", i);
        node.count("month_index", interval.month_index);
        node.number("duration_fraction_of_year", interval.duration_fraction_of_year);
        node.number("duration_seconds", interval.duration_fraction_of_year * state.options.year_duration_seconds);
        node.number("declination_rad", interval.declination_rad);
        node.number("inverse_square_distance_factor", interval.inverse_square_distance_factor);
        node.count("thermal_subdivisions", state.solution.thermal_subdivisions[i]);
        if (i) out += ',';
        out += node.finish();
    }
    return out + ']';
}

std::string edges_json(const PrescribedSeasonalClimate& state) {
    std::string out = "[";
    for (std::size_t i = 0; i < state.transport_edges.size(); ++i) {
        const auto& edge = state.transport_edges[i];
        Object item;
        item.integer("first_cell_id", edge.first_cell);
        item.integer("second_cell_id", edge.second_cell);
        item.number("conductance_w_k", edge.conductance_w_k);
        if (i) out += ',';
        out += item.finish();
    }
    return out + ']';
}

std::string records_json(const PrescribedSeasonalClimate& state) {
    const auto& physical = state.physical_columns;
    const auto& year = state.solution.year;
    std::string out = "[";
    for (std::size_t i = 0; i < physical.columns.size(); ++i) {
        const auto& column = physical.columns[i];
        Object record;
        record.count("cell_id", i);
        record.number("latitude_rad", state.latitudes_rad.at(i));
        record.flag("prescribed_marine_surface", state.marine_surface.at(i));
        record.number("prescribed_water_depth_m", state.water_depth_m.at(i));
        record.number("interface_elevation_m", state.surfaces.at(i).interface_elevation_m);
        record.number("area_m2", column.area_m2);
        record.number("heat_capacity_j_m2_k", column.heat_capacity_j_m2_k);
        record.number("surface_heat_capacity_j_m2_k", state.surfaces.at(i).surface_heat_capacity_j_m2_k);
        record.number("atmospheric_heat_capacity_j_m2_k", physical.atmospheric_heat_capacity_j_m2_k.at(i));
        record.number("surface_pressure_pa", physical.surface_pressure_pa.at(i));
        record.number("infrared_optical_depth", physical.infrared_optical_depth.at(i));
        record.number("horizontal_conductivity_w_k", physical.horizontal_conductivity_w_k.at(i));
        record.number("effective_longwave_emissivity", column.longwave_emissivity);
        record.number("top_of_atmosphere_albedo", state.options.top_of_atmosphere_albedo);
        std::vector<double> boundaries{year.initial_temperature_k.at(i)};
        for (const auto& month : year.months) {
            if (month.initial_temperature_k.at(i) != boundaries.back()) {
                throw std::runtime_error("seasonal monthly temperature boundaries are not contiguous");
            }
            boundaries.push_back(month.final_temperature_k.at(i));
        }
        if (boundaries.back() != year.final_temperature_k.at(i)) {
            throw std::runtime_error("seasonal annual boundary does not match final month");
        }
        record.raw("monthly_boundary_temperature_k", roundtrip_double_array_json(boundaries));
        const auto monthly = [&](const char* name, const std::vector<double> SurfaceEnergyMonth::* member) {
            std::vector<double> values;
            for (const auto& month : year.months) values.push_back((month.*member).at(i));
            record.raw(name, roundtrip_double_array_json(values));
        };
        monthly("monthly_mean_temperature_k", &SurfaceEnergyMonth::mean_temperature_k);
        monthly("monthly_mean_fourth_power_temperature_k4", &SurfaceEnergyMonth::mean_fourth_power_temperature_k4);
        monthly("monthly_absorbed_shortwave_w_m2", &SurfaceEnergyMonth::absorbed_shortwave_w_m2);
        monthly("monthly_emitted_longwave_w_m2", &SurfaceEnergyMonth::emitted_longwave_w_m2);
        monthly("monthly_horizontal_heat_convergence_w_m2", &SurfaceEnergyMonth::horizontal_heat_convergence_w_m2);
        monthly("monthly_heat_storage_tendency_w_m2", &SurfaceEnergyMonth::heat_storage_tendency_w_m2);
        monthly("monthly_balance_residual_w_m2", &SurfaceEnergyMonth::balance_residual_w_m2);
        monthly("monthly_balance_tolerance_w_m2", &SurfaceEnergyMonth::balance_tolerance_w_m2);
        record.number("annual_net_heating_w_m2", year.annual_net_heating_w_m2.at(i));
        record.number("annual_flux_tolerance_w_m2", year.annual_flux_tolerance_w_m2.at(i));
        if (i) out += ',';
        out += record.finish();
    }
    return out + ']';
}

}  // namespace

SerializedSeasonalEnergy serialize_prescribed_seasonal_energy(const PrescribedSeasonalClimateCache& cache) {
    const auto* state = cache.last_result();
    if (!state || state->physical_columns.columns.empty()) {
        throw std::runtime_error("native seasonal climate serialization requires a retained verified cycle");
    }
    return {model_json(cache, *state), forcing_json(*state), edges_json(*state), records_json(*state)};
}

}  // namespace magic_geo::detail
