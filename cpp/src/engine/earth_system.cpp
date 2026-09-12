#include "internal.hpp"

namespace magic_geo::detail {

FeedbackReference capture_feedback_reference(const std::vector<Cell>& cells) {
    FeedbackReference reference;
    reference.elevation_m.reserve(cells.size());
    reference.temperature_c.reserve(cells.size());
    reference.precipitation_mm_y.reserve(cells.size());
    reference.runoff_mm_y.reserve(cells.size());
    for (const Cell& cell : cells) {
        reference.elevation_m.push_back(cell.elevation_m);
        reference.temperature_c.push_back(cell.temperature_c);
        reference.precipitation_mm_y.push_back(cell.precipitation_mm_y);
        reference.runoff_mm_y.push_back(cell.runoff_mm_y);
    }
    return reference;
}

EarthSystemFeedbackStep summarize_feedback_step(
    const std::vector<Cell>& cells,
    int id,
    const std::string& stage,
    int erosion_iteration,
    const HydrologyStabilizationResult& stabilization,
    const FluvialSedimentRoutingStage* sediment_routing,
    const HillslopeSedimentTransportStage* hillslope_transport,
    const GlacialSedimentTransportStage* glacial_transport,
    bool erosion_applied,
    bool cryosphere_applied,
    bool plate_motion_applied,
    bool crust_transport_applied,
    bool crust_evolution_applied,
    int plate_motion_history_id,
    const FeedbackReference* previous
) {
    EarthSystemFeedbackStep step;
    step.id = id;
    step.stage = stage;
    step.erosion_iteration = erosion_iteration;
    step.sea_level_recomputed = stabilization.sea_level_recompute_count > 0;
    step.climate_recomputed = stabilization.climate_recompute_count > 0;
    step.hydrologic_water_budget_recomputed =
        stabilization.hydrologic_water_budget_recompute_count > 0;
    step.hydrology_recomputed = stabilization.hydrology_recompute_count > 0;
    step.erosion_applied = erosion_applied;
    step.cryosphere_applied = cryosphere_applied;
    step.plate_motion_applied = plate_motion_applied;
    step.crust_transport_applied = crust_transport_applied;
    step.crust_evolution_applied = crust_evolution_applied;
    step.sea_level_recompute_count = stabilization.sea_level_recompute_count;
    step.climate_recompute_count = stabilization.climate_recompute_count;
    step.hydrologic_water_budget_recompute_count =
        stabilization.hydrologic_water_budget_recompute_count;
    step.hydrology_recompute_count = stabilization.hydrology_recompute_count;
    step.numeric_depression_correction_pass_count =
        stabilization.numeric_depression_correction_pass_count;
    step.numeric_depression_correction_event_count =
        stabilization.numeric_depression_correction_event_count;
    step.numeric_depression_breach_selected_event_count =
        stabilization.numeric_depression_breach_selected_event_count;
    step.numeric_depression_breach_excavation_cell_application_count =
        stabilization.numeric_depression_breach_excavation_cell_application_count;
    step.numeric_depression_breach_deposition_cell_application_count =
        stabilization.numeric_depression_breach_deposition_cell_application_count;
    step.numeric_depression_temporary_lake_event_count =
        stabilization.numeric_depression_temporary_lake_event_count;
    step.numeric_depression_temporary_lake_cell_application_count =
        stabilization.numeric_depression_temporary_lake_cell_application_count;
    step.numeric_depression_temporary_lake_unique_cell_count =
        stabilization.numeric_depression_temporary_lake_unique_cell_count;
    step.plate_motion_history_id = plate_motion_history_id;
    step.sea_level_adjustment_m = stabilization.sea_level_adjustment_m;
    step.numeric_depression_breach_excavation_volume_km3 =
        stabilization.numeric_depression_breach_excavation_volume_km3;
    step.numeric_depression_breach_deposition_volume_km3 =
        stabilization.numeric_depression_breach_deposition_volume_km3;
    step.numeric_depression_correction_mass_balance_residual_km3 =
        stabilization.numeric_depression_correction_mass_balance_residual_km3;
    step.numeric_depression_temporary_lake_candidate_area_km2 =
        stabilization.numeric_depression_temporary_lake_candidate_area_km2;
    step.numeric_depression_temporary_lake_candidate_volume_km3 =
        stabilization.numeric_depression_temporary_lake_candidate_volume_km3;
    step.max_numeric_depression_temporary_lake_depth_m =
        stabilization.max_numeric_depression_temporary_lake_depth_m;
    step.sediment_alluvium_entrainment_volume_km3 =
        stabilization.numeric_depression_alluvium_entrainment_volume_km3;
    step.sediment_bedrock_erosion_volume_km3 =
        stabilization.numeric_depression_bedrock_erosion_volume_km3;
    if (sediment_routing != nullptr) {
        step.fluvial_sediment_active_cell_step_count =
            sediment_routing->active_cell_step_count;
        step.fluvial_sediment_routed_edge_count =
            sediment_routing->routed_edge_count;
        step.fluvial_sediment_land_terminal_count =
            sediment_routing->land_terminal_count;
        step.fluvial_sediment_marine_terminal_count =
            sediment_routing->marine_terminal_count;
        step.fluvial_sediment_terminal_allocation_count =
            sediment_routing->terminal_allocation_count;
        step.fluvial_sediment_local_source_volume_km3 =
            sediment_routing->local_source_volume_km3;
        step.fluvial_sediment_routed_throughput_volume_km3 =
            sediment_routing->routed_throughput_volume_km3;
        step.fluvial_sediment_capacity_deposition_volume_km3 =
            sediment_routing->capacity_deposition_volume_km3;
        step.fluvial_sediment_depression_fill_deposition_volume_km3 =
            sediment_routing->depression_fill_deposition_volume_km3;
        step.fluvial_sediment_lake_trap_deposition_volume_km3 =
            sediment_routing->lake_trap_deposition_volume_km3;
        step.fluvial_sediment_terminal_land_deposition_volume_km3 =
            sediment_routing->terminal_land_deposition_volume_km3;
        step.fluvial_sediment_marine_deposition_volume_km3 =
            sediment_routing->marine_deposition_volume_km3;
        step.fluvial_sediment_terminal_export_volume_km3 =
            sediment_routing->terminal_export_volume_km3;
        step.fluvial_sediment_mass_balance_residual_km3 =
            sediment_routing->mass_balance_residual_km3;
        step.sediment_alluvium_entrainment_volume_km3 +=
            sediment_routing->alluvium_entrainment_volume_km3;
        step.sediment_bedrock_erosion_volume_km3 +=
            sediment_routing->bedrock_erosion_volume_km3;
    }
    if (hillslope_transport != nullptr) {
        step.hillslope_sediment_transport_edge_count =
            hillslope_transport->transport_edge_count;
        step.hillslope_sediment_source_cell_count =
            hillslope_transport->source_cell_count;
        step.hillslope_sediment_target_cell_count =
            hillslope_transport->target_cell_count;
        step.hillslope_sediment_land_to_land_edge_count =
            hillslope_transport->land_to_land_edge_count;
        step.hillslope_sediment_land_to_marine_edge_count =
            hillslope_transport->land_to_marine_edge_count;
        step.hillslope_sediment_production_volume_km3 =
            hillslope_transport->production_volume_km3;
        step.hillslope_sediment_deposition_volume_km3 =
            hillslope_transport->deposition_volume_km3;
        step.hillslope_sediment_mass_balance_residual_km3 =
            hillslope_transport->mass_balance_residual_km3;
        step.max_hillslope_sediment_source_production_depth_m =
            hillslope_transport->max_source_production_depth_m;
        step.max_hillslope_sediment_target_deposition_depth_m =
            hillslope_transport->max_target_deposition_depth_m;
        step.mean_hillslope_effective_diffusivity =
            hillslope_transport->mean_effective_diffusivity;
        step.sediment_alluvium_entrainment_volume_km3 +=
            hillslope_transport->alluvium_entrainment_volume_km3;
        step.sediment_bedrock_erosion_volume_km3 +=
            hillslope_transport->bedrock_erosion_volume_km3;
    }
    if (glacial_transport != nullptr) {
        step.glacial_sediment_transfer_count =
            glacial_transport->transfer_count;
        step.glacial_sediment_source_cell_count =
            glacial_transport->source_cell_count;
        step.glacial_sediment_target_cell_count =
            glacial_transport->target_cell_count;
        step.glacial_sediment_land_target_transfer_count =
            glacial_transport->land_target_transfer_count;
        step.glacial_sediment_marine_target_transfer_count =
            glacial_transport->marine_target_transfer_count;
        step.glacial_sediment_production_volume_km3 =
            glacial_transport->production_volume_km3;
        step.glacial_sediment_deposition_volume_km3 =
            glacial_transport->deposition_volume_km3;
        step.glacial_sediment_mass_balance_residual_km3 =
            glacial_transport->mass_balance_residual_km3;
        step.glacial_sediment_terrain_volume_change_residual_km3 =
            glacial_transport->terrain_volume_change_residual_km3;
        step.max_glacial_sediment_source_production_depth_m =
            glacial_transport->max_source_production_depth_m;
        step.max_glacial_sediment_target_deposition_depth_m =
            glacial_transport->max_target_deposition_depth_m;
        step.sediment_alluvium_entrainment_volume_km3 +=
            glacial_transport->alluvium_entrainment_volume_km3;
        step.sediment_bedrock_erosion_volume_km3 +=
            glacial_transport->bedrock_erosion_volume_km3;
    }
    step.cell_count = static_cast<int>(cells.size());
    if (cells.empty()) {
        return step;
    }

    step.min_elevation_m = std::numeric_limits<double>::infinity();
    step.max_elevation_m = -std::numeric_limits<double>::infinity();
    double land_elevation_sum = 0.0;
    double cumulative_alluvium_entrainment_volume_km3 = 0.0;
    double cumulative_bedrock_erosion_volume_km3 = 0.0;
    double cumulative_process_source_witness_volume_km3 = 0.0;
    for (std::size_t index = 0; index < cells.size(); ++index) {
        const Cell& cell = cells[index];
        const double area_km2 = std::max(0.0, cell.area_km2);
        step.water_cell_count += cell.is_water ? 1 : 0;
        step.land_cell_count += cell.is_water ? 0 : 1;
        step.river_cell_count += cell.is_river ? 1 : 0;
        step.surface_area_km2 += area_km2;
        step.ocean_area_km2 += cell.is_water ? area_km2 : 0.0;
        step.ocean_volume_km3 += cell.is_water ?
            std::max(0.0, -cell.elevation_m) * area_km2 / 1000.0 : 0.0;
        step.mean_elevation_m += cell.elevation_m;
        step.min_elevation_m = std::min(step.min_elevation_m, cell.elevation_m);
        step.max_elevation_m = std::max(step.max_elevation_m, cell.elevation_m);
        step.mean_temperature_c += cell.temperature_c;
        step.mean_precipitation_mm_y += cell.precipitation_mm_y;
        step.mean_runoff_mm_y += cell.runoff_mm_y;
        step.mean_stream_power_response_m_per_reference_step +=
            cell.erosion_rate;
        step.mean_sediment_thickness_m += cell.sediment_thickness_m;
        const double gross_mobilization_m =
            sediment_gross_mobilization_m(cell);
        step.mean_cumulative_sediment_production_m += gross_mobilization_m;
        step.mean_cumulative_sediment_deposition_m += cell.sediment_deposition_m;
        step.mean_cumulative_sediment_export_m += cell.sediment_export_m;
        step.cumulative_sediment_production_volume_km3 +=
            gross_mobilization_m * area_km2 / 1000.0;
        step.cumulative_sediment_deposition_volume_km3 +=
            cell.sediment_deposition_m * area_km2 / 1000.0;
        step.cumulative_sediment_export_volume_km3 +=
            cell.sediment_export_m * area_km2 / 1000.0;
        step.sediment_inventory_volume_km3 +=
            cell.sediment_thickness_m * area_km2 / 1000.0;
        cumulative_alluvium_entrainment_volume_km3 +=
            cell.sediment_alluvium_entrainment_m * area_km2 / 1000.0;
        cumulative_bedrock_erosion_volume_km3 +=
            cell.sediment_bedrock_erosion_m * area_km2 / 1000.0;
        cumulative_process_source_witness_volume_km3 +=
            sediment_process_source_witness_m(cell) * area_km2 / 1000.0;
        if (!cell.is_water) {
            land_elevation_sum += cell.elevation_m;
            step.hydrologic_land_precipitation_volume_km3_y +=
                cell.precipitation_mm_y * area_km2 * 1.0e-6;
            step.hydrologic_actual_evapotranspiration_volume_km3_y +=
                cell.actual_evapotranspiration_mm_y * area_km2 * 1.0e-6;
            step.hydrologic_infiltration_volume_km3_y +=
                cell.infiltration_mm_y * area_km2 * 1.0e-6;
            step.hydrologic_runoff_volume_km3_y +=
                cell.runoff_mm_y * area_km2 * 1.0e-6;
            step.hydrologic_water_budget_residual_km3_y +=
                cell.runoff_budget_residual_mm_y * area_km2 * 1.0e-6;
            step.max_abs_hydrologic_water_budget_cell_residual_mm_y =
                std::max(
                    step.max_abs_hydrologic_water_budget_cell_residual_mm_y,
                    std::abs(cell.runoff_budget_residual_mm_y)
                );
        }
        if (previous != nullptr && previous->elevation_m.size() == cells.size()) {
            step.mean_abs_elevation_change_m_from_previous_stage +=
                std::abs(cell.elevation_m - previous->elevation_m[index]);
            step.mean_abs_temperature_change_c_from_previous_stage +=
                std::abs(cell.temperature_c - previous->temperature_c[index]);
            step.mean_abs_precipitation_change_mm_y_from_previous_stage +=
                std::abs(cell.precipitation_mm_y - previous->precipitation_mm_y[index]);
            step.mean_abs_runoff_change_mm_y_from_previous_stage +=
                std::abs(cell.runoff_mm_y - previous->runoff_mm_y[index]);
        }
    }

    const double divisor = static_cast<double>(cells.size());
    step.ocean_fraction = step.surface_area_km2 > 0.0 ?
        step.ocean_area_km2 / step.surface_area_km2 : 0.0;
    step.mean_elevation_m /= divisor;
    step.mean_land_elevation_m = step.land_cell_count > 0 ? land_elevation_sum / static_cast<double>(step.land_cell_count) : 0.0;
    step.mean_temperature_c /= divisor;
    step.mean_precipitation_mm_y /= divisor;
    step.mean_runoff_mm_y /= divisor;
    step.mean_stream_power_response_m_per_reference_step /= divisor;
    step.mean_sediment_thickness_m /= divisor;
    step.mean_cumulative_sediment_production_m /= divisor;
    step.mean_cumulative_sediment_deposition_m /= divisor;
    step.mean_cumulative_sediment_export_m /= divisor;
    step.sediment_source_partition_residual_km3 = std::abs(
        cumulative_process_source_witness_volume_km3 -
        cumulative_alluvium_entrainment_volume_km3 -
        cumulative_bedrock_erosion_volume_km3
    );
    step.sediment_inventory_mass_balance_residual_km3 = std::abs(
        cumulative_bedrock_erosion_volume_km3 -
        step.sediment_inventory_volume_km3 -
        step.cumulative_sediment_export_volume_km3
    );
    step.mean_abs_elevation_change_m_from_previous_stage /= divisor;
    step.mean_abs_temperature_change_c_from_previous_stage /= divisor;
    step.mean_abs_precipitation_change_mm_y_from_previous_stage /= divisor;
    step.mean_abs_runoff_change_mm_y_from_previous_stage /= divisor;
    return step;
}

HillslopeSedimentTransportStage transport_hillslope_sediment(
    const Params& params,
    int id,
    int feedback_stage_id,
    int erosion_iteration,
    std::vector<Cell>& cells,
    std::vector<double>& production_depth_m,
    std::vector<double>& deposition_depth_m
) {
    const int n = static_cast<int>(cells.size());
    HillslopeSedimentTransportStage stage;
    stage.id = id;
    stage.feedback_stage_id = feedback_stage_id;
    stage.erosion_iteration = erosion_iteration;
    stage.cell_count = n;
    production_depth_m.assign(static_cast<std::size_t>(n), 0.0);
    deposition_depth_m.assign(static_cast<std::size_t>(n), 0.0);
    stage.alluvium_entrainment_depth_m_by_cell.assign(
        static_cast<std::size_t>(n), 0.0
    );
    stage.bedrock_erosion_depth_m_by_cell.assign(
        static_cast<std::size_t>(n), 0.0
    );
    stage.input_cells.reserve(static_cast<std::size_t>(n));
    for (int cell_id = 0; cell_id < n; ++cell_id) {
        const Cell& cell = cells[static_cast<std::size_t>(cell_id)];
        HillslopeSedimentTransportInputCell input_cell;
        input_cell.cell_id = cell_id;
        input_cell.lithology = cell.lithology;
        input_cell.is_water = cell.is_water;
        input_cell.is_lake = cell.is_lake;
        input_cell.elevation_m = cell.elevation_m;
        input_cell.sediment_thickness_m = cell.sediment_thickness_m;
        stage.input_cells.push_back(input_cell);
    }
    std::set<int> source_cell_ids;
    std::set<int> target_cell_ids;
    double effective_diffusivity_sum = 0.0;

    for (int cell_a_id = 0; cell_a_id < n; ++cell_a_id) {
        const Cell& cell_a = cells[static_cast<std::size_t>(cell_a_id)];
        if (cell_a.area_km2 <= 0.0 || cell_a.neighbors.empty()) {
            throw std::runtime_error("hillslope sediment source geometry is invalid");
        }
        for (int cell_b_id : cell_a.neighbors) {
            if (cell_b_id <= cell_a_id) {
                continue;
            }
            if (cell_b_id < 0 || cell_b_id >= n) {
                throw std::runtime_error("hillslope sediment neighbor is invalid");
            }
            const Cell& cell_b = cells[static_cast<std::size_t>(cell_b_id)];
            if (cell_b.area_km2 <= 0.0 || cell_b.neighbors.empty()) {
                throw std::runtime_error("hillslope sediment target geometry is invalid");
            }
            int source_cell_id = cell_a_id;
            int target_cell_id = cell_b_id;
            if (cell_b.elevation_m > cell_a.elevation_m) {
                source_cell_id = cell_b_id;
                target_cell_id = cell_a_id;
            }
            Cell& source = cells[static_cast<std::size_t>(source_cell_id)];
            Cell& target = cells[static_cast<std::size_t>(target_cell_id)];
            const double elevation_drop_m =
                source.elevation_m - target.elevation_m;
            if (source.is_water || elevation_drop_m <= 1.0e-12) {
                continue;
            }
            const double resistance = lithology_resistance(source.lithology);
            const double effective_diffusivity = std::min(
                HILLSLOPE_MAX_EFFECTIVE_DIFFUSIVITY,
                std::max(0.0, params.hillslope_diffusion) *
                    maturation_timestep_scale(params) /
                    std::max(1.0e-12, resistance)
            );
            if (effective_diffusivity <= 0.0) {
                continue;
            }
            const int source_neighbor_count =
                static_cast<int>(source.neighbors.size());
            const double source_depth_m =
                effective_diffusivity * elevation_drop_m /
                static_cast<double>(source_neighbor_count);
            const double transfer_volume_km3 =
                source_depth_m * source.area_km2 / 1000.0;
            const double target_depth_m =
                transfer_volume_km3 * 1000.0 / target.area_km2;
            const double deposited_volume_km3 =
                target_depth_m * target.area_km2 / 1000.0;

            production_depth_m[static_cast<std::size_t>(source_cell_id)] +=
                source_depth_m;
            deposition_depth_m[static_cast<std::size_t>(target_cell_id)] +=
                target_depth_m;
            source.hillslope_sediment_production_m += source_depth_m;
            source.hillslope_sediment_outgoing_edge_count++;
            target.hillslope_sediment_deposition_m += target_depth_m;
            target.hillslope_sediment_incoming_edge_count++;
            source_cell_ids.insert(source_cell_id);
            target_cell_ids.insert(target_cell_id);

            HillslopeSedimentTransportEdge edge;
            edge.id = static_cast<int>(stage.edges.size());
            edge.mesh_edge_cell_a_id = cell_a_id;
            edge.mesh_edge_cell_b_id = cell_b_id;
            edge.source_cell_id = source_cell_id;
            edge.target_cell_id = target_cell_id;
            edge.source_lithology = source.lithology;
            edge.source_neighbor_count = source_neighbor_count;
            edge.target_is_water = target.is_water;
            edge.target_is_lake = target.is_lake;
            edge.source_area_km2 = source.area_km2;
            edge.target_area_km2 = target.area_km2;
            edge.source_elevation_m = source.elevation_m;
            edge.target_elevation_m = target.elevation_m;
            edge.elevation_drop_m = elevation_drop_m;
            edge.source_lithology_resistance = resistance;
            edge.effective_diffusivity = effective_diffusivity;
            edge.source_production_depth_m = source_depth_m;
            edge.target_deposition_depth_m = target_depth_m;
            edge.transfer_volume_km3 = transfer_volume_km3;
            edge.mass_balance_residual_km3 = std::abs(
                transfer_volume_km3 - deposited_volume_km3
            );
            stage.edges.push_back(edge);
            stage.production_volume_km3 += transfer_volume_km3;
            stage.deposition_volume_km3 += deposited_volume_km3;
            stage.land_to_marine_edge_count += target.is_water ? 1 : 0;
            stage.land_to_land_edge_count += target.is_water ? 0 : 1;
            effective_diffusivity_sum += effective_diffusivity;
        }
    }

    for (int cell_id = 0; cell_id < n; ++cell_id) {
        Cell& cell = cells[static_cast<std::size_t>(cell_id)];
        cell.hillslope_sediment_net_m =
            cell.hillslope_sediment_deposition_m -
            cell.hillslope_sediment_production_m;
        stage.max_source_production_depth_m = std::max(
            stage.max_source_production_depth_m,
            production_depth_m[static_cast<std::size_t>(cell_id)]
        );
        stage.max_target_deposition_depth_m = std::max(
            stage.max_target_deposition_depth_m,
            deposition_depth_m[static_cast<std::size_t>(cell_id)]
        );
    }
    stage.transport_edge_count = static_cast<int>(stage.edges.size());
    stage.source_cell_count = static_cast<int>(source_cell_ids.size());
    stage.target_cell_count = static_cast<int>(target_cell_ids.size());
    stage.mean_effective_diffusivity = stage.edges.empty() ? 0.0 :
        effective_diffusivity_sum / static_cast<double>(stage.edges.size());
    stage.mass_balance_residual_km3 = std::abs(
        stage.production_volume_km3 - stage.deposition_volume_km3
    );
    stage.source_production_depth_m_by_cell = production_depth_m;
    return stage;
}

FluvialSedimentRoutingStage route_fluvial_sediment(
    const std::vector<double>& routing_base_elevation_m,
    const std::vector<double>& local_source_depth_m,
    double accumulation_scale,
    int id,
    int feedback_stage_id,
    int erosion_iteration,
    std::vector<Cell>& cells,
    std::vector<double>& deposition_depth_m,
    std::vector<double>& terminal_export_depth_m
) {
    const int n = static_cast<int>(cells.size());
    if (
        routing_base_elevation_m.size() != cells.size() ||
        local_source_depth_m.size() != cells.size()
    ) {
        throw std::runtime_error("fluvial sediment routing input size mismatch");
    }

    FluvialSedimentRoutingStage stage;
    stage.id = id;
    stage.feedback_stage_id = feedback_stage_id;
    stage.erosion_iteration = erosion_iteration;
    stage.cell_count = n;
    stage.accumulation_scale = std::max(1.0, accumulation_scale);
    stage.source_production_depth_m_by_cell = local_source_depth_m;
    deposition_depth_m.assign(static_cast<std::size_t>(n), 0.0);
    terminal_export_depth_m.assign(static_cast<std::size_t>(n), 0.0);
    stage.alluvium_entrainment_depth_m_by_cell.assign(
        static_cast<std::size_t>(n), 0.0
    );
    stage.bedrock_erosion_depth_m_by_cell.assign(
        static_cast<std::size_t>(n), 0.0
    );
    stage.input_cells.reserve(static_cast<std::size_t>(n));

    std::vector<int> upstream_count(static_cast<std::size_t>(n), 0);
    for (int i = 0; i < n; ++i) {
        const Cell& cell = cells[static_cast<std::size_t>(i)];
        if (cell.area_km2 <= 0.0) {
            throw std::runtime_error("fluvial sediment routing cell area is invalid");
        }
        if (cell.flow_to >= 0) {
            if (cell.flow_to >= n || cell.flow_to == i) {
                throw std::runtime_error("fluvial sediment routing receiver is invalid");
            }
            upstream_count[static_cast<std::size_t>(cell.flow_to)]++;
        }
        FluvialSedimentRoutingInputCell input_cell;
        input_cell.cell_id = i;
        input_cell.flow_to_cell_id = cell.flow_to;
        input_cell.depression_component_id = cell.depression_component_id;
        input_cell.depression_sink_cell_id = cell.depression_sink_cell_id;
        input_cell.water_body = cell.water_body;
        input_cell.is_water = cell.is_water;
        input_cell.is_river = cell.is_river;
        input_cell.is_lake = cell.is_lake;
        input_cell.lake_overflows = cell.lake_overflows;
        input_cell.cell_area_km2 = cell.area_km2;
        input_cell.flow_accumulation = cell.flow_accumulation;
        input_cell.runoff_mm_y = cell.runoff_mm_y;
        input_cell.hydrologic_flow_slope = cell.hydrologic_flow_slope;
        input_cell.routing_base_elevation_m =
            routing_base_elevation_m[static_cast<std::size_t>(i)];
        input_cell.spill_elevation_m = cell.spill_elevation_m;
        stage.input_cells.push_back(input_cell);
    }
    std::priority_queue<int, std::vector<int>, std::greater<int>> ready;
    for (int i = 0; i < n; ++i) {
        if (upstream_count[static_cast<std::size_t>(i)] == 0) {
            ready.push(i);
        }
    }
    std::vector<int> flow_order;
    flow_order.reserve(static_cast<std::size_t>(n));
    while (!ready.empty()) {
        const int current = ready.top();
        ready.pop();
        flow_order.push_back(current);
        const int receiver = cells[static_cast<std::size_t>(current)].flow_to;
        if (receiver < 0) {
            continue;
        }
        int& remaining = upstream_count[static_cast<std::size_t>(receiver)];
        remaining--;
        if (remaining == 0) {
            ready.push(receiver);
        }
    }
    if (flow_order.size() != cells.size()) {
        throw std::runtime_error("fluvial sediment routing graph contains a cycle");
    }

    std::vector<double> source_volume_km3(static_cast<std::size_t>(n), 0.0);
    std::vector<double> incoming_volume_km3(static_cast<std::size_t>(n), 0.0);
    std::vector<double> capacity_deposition_volume_km3(static_cast<std::size_t>(n), 0.0);
    std::vector<double> depression_fill_volume_km3(static_cast<std::size_t>(n), 0.0);
    std::vector<double> lake_trap_volume_km3(static_cast<std::size_t>(n), 0.0);
    std::vector<double> marine_deposition_volume_km3(static_cast<std::size_t>(n), 0.0);
    std::vector<double> routed_outgoing_volume_km3(static_cast<std::size_t>(n), 0.0);
    std::vector<double> terminal_land_deposition_volume_km3(static_cast<std::size_t>(n), 0.0);
    std::vector<double> terminal_accommodation_deposition_volume_km3(
        static_cast<std::size_t>(n), 0.0
    );
    std::vector<double> terminal_export_volume_km3(static_cast<std::size_t>(n), 0.0);
    std::vector<double> terminal_load_by_sink_km3(static_cast<std::size_t>(n), 0.0);
    constexpr double volume_epsilon_km3 = 1.0e-15;

    for (int i = 0; i < n; ++i) {
        source_volume_km3[static_cast<std::size_t>(i)] =
            std::max(0.0, local_source_depth_m[static_cast<std::size_t>(i)]) *
            cells[static_cast<std::size_t>(i)].area_km2 / 1000.0;
        stage.local_source_volume_km3 += source_volume_km3[static_cast<std::size_t>(i)];
    }

    for (int cell_id : flow_order) {
        const Cell& cell = cells[static_cast<std::size_t>(cell_id)];
        const double local_source = source_volume_km3[static_cast<std::size_t>(cell_id)];
        const double incoming = incoming_volume_km3[static_cast<std::size_t>(cell_id)];
        const double available = local_source + incoming;
        if (available <= volume_epsilon_km3) {
            continue;
        }

        FluvialSedimentRoutingCellStep step;
        step.cell_id = cell_id;
        step.flow_to_cell_id = cell.flow_to;
        step.depression_component_id = cell.depression_component_id;
        step.depression_sink_cell_id = cell.depression_sink_cell_id;
        step.water_body = cell.water_body;
        step.is_water = cell.is_water;
        step.is_river = cell.is_river;
        step.is_lake = cell.is_lake;
        step.lake_overflows = cell.lake_overflows;
        step.is_land_terminal = !cell.is_water && cell.flow_to < 0;
        step.is_marine_terminal = cell.is_water && cell.flow_to < 0;
        step.cell_area_km2 = cell.area_km2;
        step.flow_accumulation = cell.flow_accumulation;
        step.runoff_mm_y = cell.runoff_mm_y;
        step.hydrologic_flow_slope = cell.hydrologic_flow_slope;
        step.routing_base_elevation_m = routing_base_elevation_m[static_cast<std::size_t>(cell_id)];
        step.spill_elevation_m = cell.spill_elevation_m;
        step.local_source_volume_km3 = local_source;
        step.incoming_volume_km3 = incoming;
        step.available_volume_km3 = available;

        if (step.is_marine_terminal) {
            double deposition_fraction = FLUVIAL_SEDIMENT_OPEN_OCEAN_DEPOSITION_FRACTION;
            if (cell.water_body == 2) {
                deposition_fraction = FLUVIAL_SEDIMENT_SHELF_DEPOSITION_FRACTION;
            } else if (cell.water_body == 3) {
                deposition_fraction = FLUVIAL_SEDIMENT_INLAND_SEA_DEPOSITION_FRACTION;
            }
            step.marine_deposition_volume_km3 = available * deposition_fraction;
            step.terminal_export_volume_km3 =
                available - step.marine_deposition_volume_km3;
            marine_deposition_volume_km3[static_cast<std::size_t>(cell_id)] =
                step.marine_deposition_volume_km3;
            terminal_export_volume_km3[static_cast<std::size_t>(cell_id)] =
                step.terminal_export_volume_km3;
            stage.marine_terminal_count++;
            stage.marine_deposition_volume_km3 +=
                step.marine_deposition_volume_km3;
            stage.terminal_export_volume_km3 +=
                step.terminal_export_volume_km3;
        } else if (step.is_land_terminal) {
            step.terminal_land_storage_volume_km3 = available;
            terminal_load_by_sink_km3[static_cast<std::size_t>(cell_id)] = available;
            stage.land_terminal_count++;
        } else {
            const double flow_index = clamp(
                std::sqrt(
                    std::max(0.0, cell.flow_accumulation) /
                    std::max(1.0, accumulation_scale)
                ),
                0.0,
                1.0
            );
            const double slope_index = clamp(
                std::max(0.0, cell.hydrologic_flow_slope) * 1200.0,
                0.0,
                1.0
            );
            const double runoff_index = clamp(
                std::max(0.0, cell.runoff_mm_y) / 2000.0,
                0.0,
                1.0
            );
            step.transport_capacity_fraction = clamp(
                FLUVIAL_SEDIMENT_MIN_TRANSPORT_CAPACITY_FRACTION +
                    0.045 * flow_index +
                    0.025 * slope_index +
                    0.015 * runoff_index +
                    (cell.is_river ? 0.015 : 0.0),
                FLUVIAL_SEDIMENT_MIN_TRANSPORT_CAPACITY_FRACTION,
                FLUVIAL_SEDIMENT_MAX_TRANSPORT_CAPACITY_FRACTION
            );
            const double raw_capacity_deposition =
                available * (1.0 - step.transport_capacity_fraction);
            double remaining = available;
            if (cell.depression_component_id >= 0) {
                step.depression_accommodation_volume_km3 =
                    std::max(
                        0.0,
                        cell.spill_elevation_m - step.routing_base_elevation_m
                    ) * cell.area_km2 / 1000.0;
                step.depression_fill_deposition_volume_km3 = std::min(
                    remaining,
                    step.depression_accommodation_volume_km3
                );
                remaining -= step.depression_fill_deposition_volume_km3;
            }
            step.capacity_deposition_volume_km3 = std::min(
                remaining,
                raw_capacity_deposition
            );
            remaining -= step.capacity_deposition_volume_km3;
            if (cell.is_lake) {
                const double lake_trap_fraction = cell.lake_overflows ?
                    FLUVIAL_SEDIMENT_LAKE_TRAP_FRACTION :
                    FLUVIAL_SEDIMENT_CLOSED_LAKE_TRAP_FRACTION;
                const double existing_deposition =
                    step.depression_fill_deposition_volume_km3 +
                    step.capacity_deposition_volume_km3;
                step.lake_trap_deposition_volume_km3 = std::min(
                    remaining,
                    std::max(0.0, available * lake_trap_fraction - existing_deposition)
                );
                remaining -= step.lake_trap_deposition_volume_km3;
            }
            step.routed_outgoing_volume_km3 = std::max(0.0, remaining);
            capacity_deposition_volume_km3[static_cast<std::size_t>(cell_id)] =
                step.capacity_deposition_volume_km3;
            depression_fill_volume_km3[static_cast<std::size_t>(cell_id)] =
                step.depression_fill_deposition_volume_km3;
            lake_trap_volume_km3[static_cast<std::size_t>(cell_id)] =
                step.lake_trap_deposition_volume_km3;
            routed_outgoing_volume_km3[static_cast<std::size_t>(cell_id)] =
                step.routed_outgoing_volume_km3;
            incoming_volume_km3[static_cast<std::size_t>(cell.flow_to)] +=
                step.routed_outgoing_volume_km3;
            stage.routed_throughput_volume_km3 +=
                step.routed_outgoing_volume_km3;
            stage.capacity_deposition_volume_km3 +=
                step.capacity_deposition_volume_km3;
            stage.depression_fill_deposition_volume_km3 +=
                step.depression_fill_deposition_volume_km3;
            stage.lake_trap_deposition_volume_km3 +=
                step.lake_trap_deposition_volume_km3;
            if (step.routed_outgoing_volume_km3 > volume_epsilon_km3) {
                stage.routed_edge_count++;
            }
        }
        step.local_mass_balance_residual_km3 =
            step.available_volume_km3 -
            step.capacity_deposition_volume_km3 -
            step.depression_fill_deposition_volume_km3 -
            step.lake_trap_deposition_volume_km3 -
            step.marine_deposition_volume_km3 -
            step.routed_outgoing_volume_km3 -
            step.terminal_land_storage_volume_km3 -
            step.terminal_export_volume_km3;
        stage.cell_steps.push_back(step);
    }

    std::vector<std::vector<int>> terminal_targets_by_sink(
        static_cast<std::size_t>(n)
    );
    for (int cell_id = 0; cell_id < n; ++cell_id) {
        const Cell& cell = cells[static_cast<std::size_t>(cell_id)];
        if (
            !cell.is_water &&
            cell.depression_component_id >= 0 &&
            cell.depression_sink_cell_id >= 0 &&
            cell.depression_sink_cell_id < n
        ) {
            terminal_targets_by_sink[
                static_cast<std::size_t>(cell.depression_sink_cell_id)
            ].push_back(cell_id);
        }
    }
    for (int sink_id = 0; sink_id < n; ++sink_id) {
        const double terminal_load = terminal_load_by_sink_km3[static_cast<std::size_t>(sink_id)];
        if (terminal_load <= volume_epsilon_km3) {
            continue;
        }
        std::vector<int> targets = terminal_targets_by_sink[
            static_cast<std::size_t>(sink_id)
        ];
        if (targets.empty()) {
            targets.push_back(sink_id);
        }

        std::vector<double> accommodation_by_target_km3;
        accommodation_by_target_km3.reserve(targets.size());
        double total_accommodation_km3 = 0.0;
        double total_target_area_km2 = 0.0;
        for (int target_id : targets) {
            const Cell& target = cells[static_cast<std::size_t>(target_id)];
            const double prior_local_deposition_volume_km3 =
                capacity_deposition_volume_km3[static_cast<std::size_t>(target_id)] +
                depression_fill_volume_km3[static_cast<std::size_t>(target_id)] +
                lake_trap_volume_km3[static_cast<std::size_t>(target_id)];
            const double prior_local_deposition_depth_m =
                prior_local_deposition_volume_km3 * 1000.0 / target.area_km2;
            const double accommodation_km3 = target.depression_component_id >= 0 ?
                std::max(
                    0.0,
                    target.spill_elevation_m -
                        routing_base_elevation_m[static_cast<std::size_t>(target_id)] -
                        prior_local_deposition_depth_m
                ) * target.area_km2 / 1000.0 : 0.0;
            accommodation_by_target_km3.push_back(accommodation_km3);
            total_accommodation_km3 += accommodation_km3;
            total_target_area_km2 += target.area_km2;
            FluvialSedimentTerminalAllocation allocation;
            allocation.sink_cell_id = sink_id;
            allocation.target_cell_id = target_id;
            allocation.depression_component_id = target.depression_component_id;
            allocation.target_area_km2 = target.area_km2;
            allocation.routing_base_elevation_m =
                routing_base_elevation_m[static_cast<std::size_t>(target_id)];
            allocation.spill_elevation_m = target.spill_elevation_m;
            allocation.prior_local_deposition_volume_km3 =
                prior_local_deposition_volume_km3;
            allocation.accommodation_before_allocation_km3 = accommodation_km3;
            stage.terminal_allocations.push_back(allocation);
        }

        const std::size_t allocation_start =
            stage.terminal_allocations.size() - targets.size();
        double remaining_accommodation_deposition = std::min(
            terminal_load,
            total_accommodation_km3
        );
        int last_accommodation_target = -1;
        for (std::size_t index = 0; index < targets.size(); ++index) {
            if (accommodation_by_target_km3[index] > volume_epsilon_km3) {
                last_accommodation_target = static_cast<int>(index);
            }
        }
        for (std::size_t index = 0; index < targets.size(); ++index) {
            double allocation_volume = 0.0;
            if (
                remaining_accommodation_deposition > 0.0 &&
                total_accommodation_km3 > 0.0 &&
                accommodation_by_target_km3[index] > 0.0
            ) {
                allocation_volume = static_cast<int>(index) == last_accommodation_target ?
                    remaining_accommodation_deposition :
                    std::min(
                        remaining_accommodation_deposition,
                        std::min(terminal_load, total_accommodation_km3) *
                            accommodation_by_target_km3[index] /
                            total_accommodation_km3
                    );
            }
            remaining_accommodation_deposition -= allocation_volume;
            FluvialSedimentTerminalAllocation& allocation =
                stage.terminal_allocations[allocation_start + index];
            allocation.accommodation_deposition_volume_km3 = allocation_volume;
            allocation.total_deposition_volume_km3 += allocation_volume;
            terminal_land_deposition_volume_km3[static_cast<std::size_t>(targets[index])] +=
                allocation_volume;
            terminal_accommodation_deposition_volume_km3[
                static_cast<std::size_t>(targets[index])
            ] += allocation_volume;
            depression_fill_volume_km3[static_cast<std::size_t>(targets[index])] +=
                allocation_volume;
            stage.depression_fill_deposition_volume_km3 += allocation_volume;
        }

        const double accommodation_deposition = std::min(
            terminal_load,
            total_accommodation_km3
        );
        double remaining_excess = terminal_load - accommodation_deposition;
        const double initial_excess = remaining_excess;
        for (std::size_t index = 0; index < targets.size(); ++index) {
            const Cell& target = cells[static_cast<std::size_t>(targets[index])];
            const double allocation_volume = index + 1 == targets.size() ?
                remaining_excess :
                std::min(
                    remaining_excess,
                    initial_excess * target.area_km2 /
                        std::max(volume_epsilon_km3, total_target_area_km2)
                );
            remaining_excess -= allocation_volume;
            FluvialSedimentTerminalAllocation& allocation =
                stage.terminal_allocations[allocation_start + index];
            allocation.excess_aggradation_volume_km3 = allocation_volume;
            allocation.total_deposition_volume_km3 += allocation_volume;
            terminal_land_deposition_volume_km3[static_cast<std::size_t>(targets[index])] +=
                allocation_volume;
        }
        cells[static_cast<std::size_t>(sink_id)]
            .fluvial_sediment_terminal_capture_volume_km3 += terminal_load;
        stage.terminal_land_deposition_volume_km3 += terminal_load;
    }

    stage.terminal_allocation_count = static_cast<int>(std::count_if(
        stage.terminal_allocations.begin(),
        stage.terminal_allocations.end(),
        [volume_epsilon_km3](const FluvialSedimentTerminalAllocation& allocation) {
            return allocation.total_deposition_volume_km3 > volume_epsilon_km3;
        }
    ));
    stage.active_cell_step_count = static_cast<int>(stage.cell_steps.size());

    double total_deposition_volume_km3 = 0.0;
    for (int i = 0; i < n; ++i) {
        Cell& cell = cells[static_cast<std::size_t>(i)];
        const double area_km2 = cell.area_km2;
        const double land_local_deposition_volume_km3 =
            capacity_deposition_volume_km3[static_cast<std::size_t>(i)] +
            depression_fill_volume_km3[static_cast<std::size_t>(i)] +
            lake_trap_volume_km3[static_cast<std::size_t>(i)] -
            terminal_accommodation_deposition_volume_km3[
                static_cast<std::size_t>(i)
            ];
        const double total_cell_deposition_volume_km3 =
            land_local_deposition_volume_km3 +
            terminal_land_deposition_volume_km3[static_cast<std::size_t>(i)] +
            marine_deposition_volume_km3[static_cast<std::size_t>(i)];
        deposition_depth_m[static_cast<std::size_t>(i)] =
            total_cell_deposition_volume_km3 * 1000.0 / area_km2;
        terminal_export_depth_m[static_cast<std::size_t>(i)] =
            terminal_export_volume_km3[static_cast<std::size_t>(i)] * 1000.0 /
            area_km2;
        cell.fluvial_sediment_local_source_m +=
            source_volume_km3[static_cast<std::size_t>(i)] * 1000.0 / area_km2;
        cell.fluvial_sediment_routed_incoming_m +=
            incoming_volume_km3[static_cast<std::size_t>(i)] * 1000.0 / area_km2;
        cell.fluvial_sediment_routed_outgoing_m +=
            routed_outgoing_volume_km3[static_cast<std::size_t>(i)] * 1000.0 /
            area_km2;
        cell.fluvial_sediment_local_deposition_m +=
            land_local_deposition_volume_km3 * 1000.0 / area_km2;
        cell.fluvial_sediment_terminal_land_deposition_m +=
            terminal_land_deposition_volume_km3[static_cast<std::size_t>(i)] *
            1000.0 / area_km2;
        cell.fluvial_sediment_marine_deposition_m +=
            marine_deposition_volume_km3[static_cast<std::size_t>(i)] * 1000.0 /
            area_km2;
        cell.fluvial_sediment_depression_fill_m +=
            depression_fill_volume_km3[static_cast<std::size_t>(i)] * 1000.0 /
            area_km2;
        cell.fluvial_sediment_terminal_export_m +=
            terminal_export_depth_m[static_cast<std::size_t>(i)];
        if (
            source_volume_km3[static_cast<std::size_t>(i)] > volume_epsilon_km3 ||
            incoming_volume_km3[static_cast<std::size_t>(i)] > volume_epsilon_km3 ||
            terminal_land_deposition_volume_km3[static_cast<std::size_t>(i)] > volume_epsilon_km3
        ) {
            cell.fluvial_sediment_routing_event_count++;
        }
        total_deposition_volume_km3 += total_cell_deposition_volume_km3;
    }
    stage.mass_balance_residual_km3 = std::abs(
        stage.local_source_volume_km3 -
        total_deposition_volume_km3 -
        stage.terminal_export_volume_km3
    );
    return stage;
}

void erode(
    const Params& params,
    std::vector<Plate>& plates,
    std::vector<Cell>& cells,
    std::vector<EarthSystemFeedbackStep>& feedback_history,
    std::vector<PlateMotionStep>& plate_motion_history,
    CrustMaterialShadowState& crust_material_shadow,
    CrustDryRockAccountingState& crust_dry_rock_accounting,
    std::vector<NumericDepressionCorrectionEvent>& numeric_depression_correction_history,
    std::vector<HydrologicWaterBudgetStage>& hydrologic_water_budget_history,
    std::vector<FluvialSedimentRoutingStage>& sediment_routing_history,
    std::vector<HillslopeSedimentTransportStage>& hillslope_transport_history,
    PrescribedSeasonalClimateCache* climate_cache
) {
    const int n = static_cast<int>(cells.size());
    for (int iter = 0; iter < params.erosion_iterations; ++iter) {
        const FeedbackReference previous = capture_feedback_reference(cells);
        const std::vector<double> tectonic_elevation_change = advance_plate_motion_and_crust(
            params,
            iter + 1,
            plates,
            cells,
            plate_motion_history,
            crust_material_shadow,
            crust_dry_rock_accounting
        );
        std::vector<double> accum;
        for (const Cell& cell : cells) {
            if (!cell.is_water && cell.flow_accumulation > 0.0) {
                accum.push_back(cell.flow_accumulation);
            }
        }
        std::sort(accum.begin(), accum.end());
        const double acc_scale = accum.empty() ? 1.0 : std::max(1.0, accum[static_cast<std::size_t>(0.95 * (accum.size() - 1))]);
        std::vector<double> hillslope_production_depth_m;
        std::vector<double> hillslope_deposition_depth_m;
        HillslopeSedimentTransportStage hillslope_transport =
            transport_hillslope_sediment(
                params,
                static_cast<int>(hillslope_transport_history.size()),
                static_cast<int>(feedback_history.size()),
                iter + 1,
                cells,
                hillslope_production_depth_m,
                hillslope_deposition_depth_m
            );
        std::vector<double> next(n);
        std::vector<double> sediment_source(n, 0.0);
        if (std::any_of(cells.begin(), cells.end(), [](const Cell& cell) {
                return cell.area_km2 <= 0.0;
            })) {
            throw std::runtime_error("sediment transfer cell area is invalid");
        }
#pragma omp parallel for schedule(static)
        for (int i = 0; i < n; ++i) {
            Cell& cell = cells[i];
            next[i] =
                cell.elevation_m +
                tectonic_elevation_change[static_cast<std::size_t>(i)] -
                hillslope_production_depth_m[static_cast<std::size_t>(i)] +
                hillslope_deposition_depth_m[static_cast<std::size_t>(i)];
            if (cell.is_water) {
                cell.erosion_rate = 0.0;
                continue;
            }
            double slope = 0.0;
            if (cell.flow_to >= 0) {
                slope = std::max(0.0, cell.hydrologic_flow_slope);
            }
            const double acc_norm = clamp(cell.flow_accumulation / acc_scale, 0.0, 3.0);
            const double erodability = 1.0 / lithology_resistance(cell.lithology);
            const double stream = params.stream_power_coefficient * erodability *
                std::pow(acc_norm, params.drainage_exponent) * std::pow(std::max(0.0, slope * 900.0), params.slope_exponent);
            const double erosion_depth_m =
                stream * maturation_timestep_scale(params);
            // Preserve the exported erosion-rate signal as the 5 Ma reference
            // response used by downstream diagnostics. Only the applied
            // incision/source depth is integrated over the configured nominal
            // transition. Otherwise merely refining dt changes soils,
            // ecosystems, land use, and resource diagnostics by construction.
            cell.erosion_rate = stream;
            sediment_source[static_cast<std::size_t>(i)] = erosion_depth_m;
            next[i] -= erosion_depth_m;
        }
        std::vector<double> sediment_delta;
        std::vector<double> sediment_export;
        FluvialSedimentRoutingStage sediment_routing = route_fluvial_sediment(
            next,
            sediment_source,
            acc_scale,
            static_cast<int>(sediment_routing_history.size()),
            static_cast<int>(feedback_history.size()),
            iter + 1,
            cells,
            sediment_delta,
            sediment_export
        );
        for (int i = 0; i < n; ++i) {
            const double hillslope_source_depth_m =
                hillslope_production_depth_m[static_cast<std::size_t>(i)];
            const double fluvial_source_depth_m =
                sediment_source[static_cast<std::size_t>(i)];
            double available_alluvium_depth_m =
                cells[i].sediment_thickness_m;
            const double hillslope_alluvium_entrainment_depth_m = std::min(
                available_alluvium_depth_m,
                hillslope_source_depth_m
            );
            available_alluvium_depth_m -=
                hillslope_alluvium_entrainment_depth_m;
            const double fluvial_alluvium_entrainment_depth_m = std::min(
                available_alluvium_depth_m,
                fluvial_source_depth_m
            );
            const double hillslope_bedrock_erosion_depth_m = std::max(
                0.0,
                hillslope_source_depth_m -
                    hillslope_alluvium_entrainment_depth_m
            );
            const double fluvial_bedrock_erosion_depth_m = std::max(
                0.0,
                fluvial_source_depth_m -
                    fluvial_alluvium_entrainment_depth_m
            );
            const double area_km2 = cells[i].area_km2;
            hillslope_transport.alluvium_entrainment_volume_km3 +=
                hillslope_alluvium_entrainment_depth_m * area_km2 / 1000.0;
            hillslope_transport.bedrock_erosion_volume_km3 +=
                hillslope_bedrock_erosion_depth_m * area_km2 / 1000.0;
            hillslope_transport.alluvium_entrainment_depth_m_by_cell[
                static_cast<std::size_t>(i)
            ] = hillslope_alluvium_entrainment_depth_m;
            hillslope_transport.bedrock_erosion_depth_m_by_cell[
                static_cast<std::size_t>(i)
            ] = hillslope_bedrock_erosion_depth_m;
            sediment_routing.alluvium_entrainment_volume_km3 +=
                fluvial_alluvium_entrainment_depth_m * area_km2 / 1000.0;
            sediment_routing.bedrock_erosion_volume_km3 +=
                fluvial_bedrock_erosion_depth_m * area_km2 / 1000.0;
            sediment_routing.alluvium_entrainment_depth_m_by_cell[
                static_cast<std::size_t>(i)
            ] = fluvial_alluvium_entrainment_depth_m;
            sediment_routing.bedrock_erosion_depth_m_by_cell[
                static_cast<std::size_t>(i)
            ] = fluvial_bedrock_erosion_depth_m;
            cells[i].sediment_alluvium_entrainment_m +=
                hillslope_alluvium_entrainment_depth_m +
                fluvial_alluvium_entrainment_depth_m;
            cells[i].sediment_bedrock_erosion_m +=
                hillslope_bedrock_erosion_depth_m +
                fluvial_bedrock_erosion_depth_m;
            cells[i].sediment_deposition_m +=
                sediment_delta[static_cast<std::size_t>(i)] +
                hillslope_deposition_depth_m[static_cast<std::size_t>(i)];
            cells[i].sediment_export_m += sediment_export[static_cast<std::size_t>(i)];
            const double compatibility_surface_elevation_m =
                next[i] + sediment_delta[static_cast<std::size_t>(i)];
            apply_sediment_interface_material_change(
                cells[i],
                tectonic_elevation_change[static_cast<std::size_t>(i)],
                hillslope_bedrock_erosion_depth_m +
                    fluvial_bedrock_erosion_depth_m,
                hillslope_alluvium_entrainment_depth_m +
                    fluvial_alluvium_entrainment_depth_m,
                sediment_delta[static_cast<std::size_t>(i)] +
                    hillslope_deposition_depth_m[static_cast<std::size_t>(i)],
                "hillslope/fluvial sediment interface"
            );
            if (
                std::abs(
                    cells[i].elevation_m -
                    compatibility_surface_elevation_m
                ) > std::max(
                    1.0e-9,
                    std::abs(compatibility_surface_elevation_m) * 1.0e-12
                )
            ) {
                throw std::runtime_error(
                    "hillslope/fluvial sediment-interface update changed the compatibility surface"
                );
            }
            cells[i].sediment_net_budget_m =
                cells[i].sediment_deposition_m -
                sediment_gross_mobilization_m(cells[i]);
        }
        maximum_sediment_interface_closure_residual_m(
            cells,
            "post hillslope/fluvial transport"
        );
        validate_sediment_source_partition(
            cells,
            hillslope_transport.source_production_depth_m_by_cell,
            hillslope_transport.alluvium_entrainment_depth_m_by_cell,
            hillslope_transport.bedrock_erosion_depth_m_by_cell,
            hillslope_transport.alluvium_entrainment_volume_km3,
            hillslope_transport.bedrock_erosion_volume_km3,
            "hillslope"
        );
        validate_sediment_source_partition(
            cells,
            sediment_routing.source_production_depth_m_by_cell,
            sediment_routing.alluvium_entrainment_depth_m_by_cell,
            sediment_routing.bedrock_erosion_depth_m_by_cell,
            sediment_routing.alluvium_entrainment_volume_km3,
            sediment_routing.bedrock_erosion_volume_km3,
            "fluvial"
        );
        sediment_routing_history.push_back(std::move(sediment_routing));
        hillslope_transport_history.push_back(std::move(hillslope_transport));
        const HydrologyStabilizationResult stabilization = stabilize_numeric_depressions(
            params,
            cells,
            static_cast<int>(feedback_history.size()),
            "erosion_iteration",
            iter + 1,
            numeric_depression_correction_history,
            hydrologic_water_budget_history,
            climate_cache
        );
        feedback_history.push_back(summarize_feedback_step(
            cells,
            static_cast<int>(feedback_history.size()),
            "erosion_iteration",
            iter + 1,
            stabilization,
            &sediment_routing_history.back(),
            &hillslope_transport_history.back(),
            nullptr,
            true,
            false,
            true,
            true,
            true,
            plate_motion_history.back().id,
            &previous
        ));
    }
}

}  // namespace magic_geo::detail
