#include "internal.hpp"

namespace magic_geo::detail {

double hydrologic_lithology_permeability(int lithology) {
    switch (lithology) {
        case 0: return 0.46;
        case 1: return 0.31;
        case 2: return 0.82;
        case 3: return 0.76;
        case 4: return 0.18;
        case 5: return 0.48;
        case 6: return 0.30;
        default: return 0.34;
    }
}

HydrologicWaterBudgetStage compute_hydrologic_water_budget(
    std::vector<Cell>& cells,
    int id,
    int feedback_stage_id,
    const std::string& stage_name,
    int erosion_iteration,
    int stabilization_recomputation_index
) {
    HydrologicWaterBudgetStage stage;
    stage.id = id;
    stage.feedback_stage_id = feedback_stage_id;
    stage.stage = stage_name;
    stage.erosion_iteration = erosion_iteration;
    stage.stabilization_recomputation_index =
        stabilization_recomputation_index;
    stage.cell_count = static_cast<int>(cells.size());

    const std::size_t cell_count = cells.size();
    stage.cell_ids.reserve(cell_count);
    stage.is_marine_by_cell.reserve(cell_count);
    stage.lithology_by_cell.reserve(cell_count);
    stage.cell_area_km2_by_cell.reserve(cell_count);
    stage.elevation_m_by_cell.reserve(cell_count);
    stage.temperature_c_by_cell.reserve(cell_count);
    stage.precipitation_mm_y_by_cell.reserve(cell_count);
    stage.local_relief_m_by_cell.reserve(cell_count);
    stage.sediment_thickness_m_by_cell.reserve(cell_count);
    stage.ice_thickness_m_by_cell.reserve(cell_count);
    stage.potential_evapotranspiration_mm_y_by_cell.reserve(cell_count);
    stage.infiltration_capacity_index_by_cell.reserve(cell_count);
    stage.actual_evapotranspiration_mm_y_by_cell.reserve(cell_count);
    stage.infiltration_mm_y_by_cell.reserve(cell_count);
    stage.water_balance_mm_y_by_cell.reserve(cell_count);
    stage.runoff_mm_y_by_cell.reserve(cell_count);
    stage.residual_mm_y_by_cell.reserve(cell_count);

    for (std::size_t index = 0; index < cell_count; ++index) {
        Cell& cell = cells[index];
        const bool is_marine = cell.is_water;
        const double area_km2 = std::max(0.0, cell.area_km2);
        const double precipitation_mm_y = std::max(
            0.0,
            cell.precipitation_mm_y
        );
        const double relief_m = local_relief(cells, static_cast<int>(index));

        double potential_evapotranspiration_mm_y = 0.0;
        double infiltration_capacity_index = 0.0;
        double actual_evapotranspiration_mm_y = 0.0;
        double infiltration_mm_y = 0.0;
        double water_balance_mm_y = 0.0;
        double runoff_mm_y = 0.0;
        double residual_mm_y = 0.0;

        if (!is_marine) {
            potential_evapotranspiration_mm_y = std::max(
                0.0,
                cell.temperature_c +
                    HYDROLOGIC_PET_TEMPERATURE_OFFSET_C
            ) * HYDROLOGIC_PET_SCALE_MM_Y_PER_C;
            const double permeability =
                hydrologic_lithology_permeability(cell.lithology);
            const double terrain_retention = 1.0 - clamp(
                relief_m / 2500.0,
                0.0,
                1.0
            );
            const double sediment_index = clamp(
                cell.sediment_thickness_m / 3.0,
                0.0,
                1.0
            );
            const double frozen_index = clamp(
                (-cell.temperature_c - 2.0) / 18.0,
                0.0,
                1.0
            );
            infiltration_capacity_index = clamp(
                0.62 * permeability +
                    0.16 * sediment_index +
                    0.12 * terrain_retention -
                    0.10 * frozen_index,
                HYDROLOGIC_MIN_INFILTRATION_CAPACITY,
                HYDROLOGIC_MAX_INFILTRATION_CAPACITY
            );
            const double climate_loss_mm_y = std::min(
                precipitation_mm_y,
                HYDROLOGIC_CLIMATE_LOSS_FRACTION *
                    potential_evapotranspiration_mm_y
            );
            const double infiltration_share = clamp(
                HYDROLOGIC_INFILTRATION_BASE_SHARE +
                    HYDROLOGIC_INFILTRATION_CAPACITY_SHARE *
                        infiltration_capacity_index,
                HYDROLOGIC_INFILTRATION_BASE_SHARE,
                HYDROLOGIC_INFILTRATION_BASE_SHARE +
                    HYDROLOGIC_INFILTRATION_CAPACITY_SHARE *
                        HYDROLOGIC_MAX_INFILTRATION_CAPACITY
            );
            infiltration_mm_y = climate_loss_mm_y * infiltration_share;
            actual_evapotranspiration_mm_y =
                climate_loss_mm_y - infiltration_mm_y;

            // Keep the calibrated loss envelope grouped so routing receives
            // the same residual while the causal source partition is explicit.
            water_balance_mm_y =
                precipitation_mm_y - climate_loss_mm_y;
            runoff_mm_y = std::max(0.0, water_balance_mm_y);
            residual_mm_y =
                precipitation_mm_y -
                actual_evapotranspiration_mm_y -
                infiltration_mm_y -
                runoff_mm_y;
        }

        cell.hydrologic_potential_evapotranspiration_mm_y =
            potential_evapotranspiration_mm_y;
        cell.actual_evapotranspiration_mm_y =
            actual_evapotranspiration_mm_y;
        cell.infiltration_capacity_index = infiltration_capacity_index;
        cell.infiltration_mm_y = infiltration_mm_y;
        cell.hydrologic_water_balance_mm_y = water_balance_mm_y;
        cell.water_budget_runoff_mm_y = runoff_mm_y;
        cell.runoff_mm_y = runoff_mm_y;
        cell.runoff_budget_residual_mm_y = residual_mm_y;
        cell.runoff_budget_consistency_index = clamp(
            1.0 - std::abs(residual_mm_y) /
                std::max(1.0, precipitation_mm_y),
            0.0,
            1.0
        );
        cell.hydrologic_deficit_mm_y = std::max(
            0.0,
            potential_evapotranspiration_mm_y -
                actual_evapotranspiration_mm_y
        );
        cell.runoff_generation_fraction = clamp(
            runoff_mm_y / std::max(1.0, precipitation_mm_y),
            0.0,
            1.0
        );

        stage.cell_ids.push_back(cell.id);
        stage.is_marine_by_cell.push_back(is_marine ? 1 : 0);
        stage.lithology_by_cell.push_back(cell.lithology);
        stage.cell_area_km2_by_cell.push_back(area_km2);
        stage.elevation_m_by_cell.push_back(cell.elevation_m);
        stage.temperature_c_by_cell.push_back(cell.temperature_c);
        stage.precipitation_mm_y_by_cell.push_back(precipitation_mm_y);
        stage.local_relief_m_by_cell.push_back(relief_m);
        stage.sediment_thickness_m_by_cell.push_back(
            cell.sediment_thickness_m
        );
        stage.ice_thickness_m_by_cell.push_back(cell.ice_thickness_m);
        stage.potential_evapotranspiration_mm_y_by_cell.push_back(
            potential_evapotranspiration_mm_y
        );
        stage.infiltration_capacity_index_by_cell.push_back(
            infiltration_capacity_index
        );
        stage.actual_evapotranspiration_mm_y_by_cell.push_back(
            actual_evapotranspiration_mm_y
        );
        stage.infiltration_mm_y_by_cell.push_back(infiltration_mm_y);
        stage.water_balance_mm_y_by_cell.push_back(water_balance_mm_y);
        stage.runoff_mm_y_by_cell.push_back(runoff_mm_y);
        stage.residual_mm_y_by_cell.push_back(residual_mm_y);

        if (is_marine) {
            stage.marine_cell_count++;
        } else {
            stage.land_cell_count++;
            stage.land_precipitation_volume_km3_y +=
                precipitation_mm_y * area_km2 * 1.0e-6;
            stage.actual_evapotranspiration_volume_km3_y +=
                actual_evapotranspiration_mm_y * area_km2 * 1.0e-6;
            stage.infiltration_volume_km3_y +=
                infiltration_mm_y * area_km2 * 1.0e-6;
            stage.runoff_volume_km3_y +=
                runoff_mm_y * area_km2 * 1.0e-6;
            stage.mass_balance_residual_km3_y +=
                residual_mm_y * area_km2 * 1.0e-6;
            stage.max_abs_cell_residual_mm_y = std::max(
                stage.max_abs_cell_residual_mm_y,
                std::abs(residual_mm_y)
            );
        }
    }
    return stage;
}

double neighbor_distance_m(const Params& params, const Cell& a, const Cell& b) {
    return std::max(1.0, angular_distance(a.p, b.p) * params.radius_km * 1000.0);
}

bool is_geologic_depression(const Cell& cell) {
    return cell.crust_type == 6 || cell.crust_type == 7 || cell.boundary_divergent > 0.28 || cell.boundary_convergent > 0.42;
}

struct FloodItem {
    double elevation = 0.0;
    int cell = -1;
};

struct FloodItemGreater {
    bool operator()(const FloodItem& a, const FloodItem& b) const {
        if (a.elevation == b.elevation) {
            return a.cell > b.cell;
        }
        return a.elevation > b.elevation;
    }
};

void compute_priority_flood_spill(std::vector<Cell>& cells) {
    const int n = static_cast<int>(cells.size());
    std::priority_queue<FloodItem, std::vector<FloodItem>, FloodItemGreater> queue;
    for (int i = 0; i < n; ++i) {
        cells[i].filled_elevation_m = std::numeric_limits<double>::infinity();
        cells[i].depression_depth_m = 0.0;
        cells[i].spill_to = -1;
        cells[i].is_closed_basin = false;
        if (cells[i].is_water) {
            cells[i].filled_elevation_m = 0.0;
            queue.push({0.0, i});
        }
    }

    if (queue.empty() && !cells.empty()) {
        int lowest = 0;
        for (int i = 1; i < n; ++i) {
            if (cells[i].elevation_m < cells[lowest].elevation_m) {
                lowest = i;
            }
        }
        cells[lowest].filled_elevation_m = cells[lowest].elevation_m;
        queue.push({cells[lowest].filled_elevation_m, lowest});
    }

    while (!queue.empty()) {
        const FloodItem item = queue.top();
        queue.pop();
        if (item.elevation > cells[item.cell].filled_elevation_m + 1.0e-9) {
            continue;
        }
        for (int neighbor : cells[item.cell].neighbors) {
            if (cells[neighbor].filled_elevation_m != std::numeric_limits<double>::infinity()) {
                continue;
            }
            const double filled = std::max(cells[neighbor].elevation_m, item.elevation);
            cells[neighbor].filled_elevation_m = filled;
            cells[neighbor].depression_depth_m = std::max(0.0, filled - cells[neighbor].elevation_m);
            cells[neighbor].spill_to = item.cell;
            queue.push({filled, neighbor});
        }
    }

    for (Cell& cell : cells) {
        if (!std::isfinite(cell.filled_elevation_m)) {
            cell.filled_elevation_m = cell.elevation_m;
            cell.depression_depth_m = 0.0;
            cell.spill_to = -1;
        }
    }
}

void assign_basin_ids(std::vector<Cell>& cells) {
    const int n = static_cast<int>(cells.size());
    for (Cell& cell : cells) {
        cell.basin_id = -1;
    }
    for (int i = 0; i < n; ++i) {
        if (cells[i].is_water) {
            cells[i].basin_id = i;
        }
    }
    for (int i = 0; i < n; ++i) {
        if (cells[i].basin_id >= 0) {
            continue;
        }
        std::vector<int> path;
        std::set<int> seen;
        int current = i;
        int basin = i;
        while (current >= 0 && current < n) {
            if (cells[current].basin_id >= 0) {
                basin = cells[current].basin_id;
                break;
            }
            if (!seen.insert(current).second) {
                basin = current;
                break;
            }
            path.push_back(current);
            if (cells[current].is_water ||
                (cells[current].is_lake && (cells[current].is_closed_basin || cells[current].flow_to < 0)) ||
                cells[current].flow_to < 0) {
                basin = current;
                break;
            }
            current = cells[current].flow_to;
        }
        for (int cell_id : path) {
            cells[cell_id].basin_id = basin;
        }
    }
}

void condition_hydrologic_surface(
    const Params& params,
    std::vector<Cell>& cells,
    const std::vector<int>& flow_order
) {
    for (Cell& cell : cells) {
        cell.hydrologic_surface_elevation_m = cell.filled_elevation_m;
        cell.hydrologic_flow_drop_m = 0.0;
        cell.hydrologic_flow_slope = 0.0;
        cell.hydrologic_surface_conditioned = false;
    }

    for (auto it = flow_order.rbegin(); it != flow_order.rend(); ++it) {
        Cell& cell = cells[static_cast<std::size_t>(*it)];
        if (cell.flow_to < 0) {
            continue;
        }
        Cell& receiver = cells[static_cast<std::size_t>(cell.flow_to)];
        if (cell.filled_elevation_m + 1.0e-9 < receiver.filled_elevation_m) {
            throw std::runtime_error("Priority-Flood routing surface rises downstream");
        }
        cell.hydrologic_surface_elevation_m = std::max(
            cell.filled_elevation_m,
            receiver.hydrologic_surface_elevation_m + HYDROLOGIC_FLAT_GRADIENT_STEP_M
        );
    }

    for (Cell& cell : cells) {
        cell.hydrologic_surface_conditioned =
            cell.hydrologic_surface_elevation_m > cell.filled_elevation_m + 1.0e-12;
        if (cell.flow_to < 0) {
            continue;
        }
        const Cell& receiver = cells[static_cast<std::size_t>(cell.flow_to)];
        cell.hydrologic_flow_drop_m =
            cell.hydrologic_surface_elevation_m - receiver.hydrologic_surface_elevation_m;
        if (cell.hydrologic_flow_drop_m <= 0.0) {
            throw std::runtime_error("conditioned hydrologic surface is not downhill");
        }
        cell.hydrologic_flow_slope = cell.hydrologic_flow_drop_m /
            neighbor_distance_m(params, cell, receiver);
    }
}

void compute_flow_and_rivers(const Params& params, std::vector<Cell>& cells) {
    const int n = static_cast<int>(cells.size());
    compute_priority_flood_spill(cells);
    std::vector<int> raw_flow_to(static_cast<std::size_t>(n), -1);
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        Cell& cell = cells[i];
        cell.is_river = false;
        cell.is_lake = false;
        cell.flow_to = -1;
        cell.equal_filled_raw_downhill_rerouted = false;
        cell.flow_accumulation = 0.0;
        cell.basin_id = -1;
        cell.depression_component_id = -1;
        cell.depression_sink_cell_id = -1;
        cell.lake_basin_id = -1;
        cell.depression_policy = 0;
        cell.spill_elevation_m = std::isfinite(cell.filled_elevation_m) ? cell.filled_elevation_m : cell.elevation_m;
        cell.lake_fill_fraction = 0.0;
        cell.is_closed_basin = false;
        cell.lake_overflows = false;
        if (cell.is_water) {
            continue;
        }
        cell.water_body = 0;
        cell.flow_accumulation = cell.runoff_mm_y * cell.area_km2;
        double best_raw_drop = 0.0;
        int raw_best = -1;
        for (int j : cell.neighbors) {
            const double raw_drop = cell.elevation_m - cells[j].elevation_m;
            if (
                raw_drop > 1.0e-9 &&
                (raw_drop > best_raw_drop + 1.0e-9 ||
                    (std::abs(raw_drop - best_raw_drop) <= 1.0e-9 && (raw_best < 0 || j < raw_best)))
            ) {
                best_raw_drop = raw_drop;
                raw_best = j;
            }
        }
        raw_flow_to[static_cast<std::size_t>(i)] = raw_best;

        const double current_surface = std::isfinite(cell.filled_elevation_m) ?
            cell.filled_elevation_m : cell.elevation_m;
        double best_drop = 0.0;
        best_raw_drop = -std::numeric_limits<double>::infinity();
        int best = -1;
        for (int j : cell.neighbors) {
            const double neighbor_surface = std::isfinite(cells[j].filled_elevation_m) ?
                cells[j].filled_elevation_m : cells[j].elevation_m;
            const double drop = current_surface - neighbor_surface;
            const double raw_drop = cell.elevation_m - cells[j].elevation_m;
            if (
                drop > 1.0e-9 &&
                (drop > best_drop + 1.0e-9 ||
                    (std::abs(drop - best_drop) <= 1.0e-9 &&
                        (raw_drop > best_raw_drop + 1.0e-9 ||
                            (std::abs(raw_drop - best_raw_drop) <= 1.0e-9 && (best < 0 || j < best)))))
            ) {
                best_drop = drop;
                best_raw_drop = raw_drop;
                best = j;
            }
        }
        if (best < 0 && cell.spill_to >= 0 && cell.spill_to != i) {
            best = cell.spill_to;
            const Cell& receiver = cells[static_cast<std::size_t>(best)];
            cell.equal_filled_raw_downhill_rerouted =
                std::abs(cell.filled_elevation_m - receiver.filled_elevation_m) <= 1.0e-9 &&
                cell.elevation_m - receiver.elevation_m > 1.0e-9;
        }
        cell.flow_to = best;
        cell.water_depth_m = 0.0;
    }

    // Label each raw-downhill drainage tree by its terminal cell. A terminal
    // with Priority-Flood depth is one model depression unit, even when it
    // shares a final fill elevation with neighboring sinks.
    std::vector<int> raw_sink_by_cell(static_cast<std::size_t>(n), -2);
    for (int i = 0; i < n; ++i) {
        if (cells[static_cast<std::size_t>(i)].is_water) {
            raw_sink_by_cell[static_cast<std::size_t>(i)] = -1;
        }
    }
    for (int i = 0; i < n; ++i) {
        if (raw_sink_by_cell[static_cast<std::size_t>(i)] != -2) {
            continue;
        }
        std::vector<int> path;
        int current = i;
        int sink = -3;
        for (int step = 0; step <= n; ++step) {
            if (current < 0) {
                sink = path.empty() ? i : path.back();
                break;
            }
            if (current >= n) {
                throw std::runtime_error("raw hydrology receiver is invalid");
            }
            const int known_sink = raw_sink_by_cell[static_cast<std::size_t>(current)];
            if (known_sink != -2) {
                sink = known_sink;
                break;
            }
            path.push_back(current);
            const int next = raw_flow_to[static_cast<std::size_t>(current)];
            if (next < 0) {
                sink = current;
                break;
            }
            current = next;
        }
        if (sink == -3) {
            throw std::runtime_error("raw hydrology drainage labeling did not terminate");
        }
        for (int cell_id : path) {
            raw_sink_by_cell[static_cast<std::size_t>(cell_id)] = sink;
        }
    }

    std::map<int, std::vector<int>> depression_cells_by_sink;
    for (int i = 0; i < n; ++i) {
        const Cell& cell = cells[static_cast<std::size_t>(i)];
        const int sink = raw_sink_by_cell[static_cast<std::size_t>(i)];
        if (!cell.is_water && cell.depression_depth_m > 1.0e-9 && sink >= 0) {
            depression_cells_by_sink[sink].push_back(i);
        }
    }

    int depression_component_id = 0;
    for (const auto& [sink_id, depression_cell_ids] : depression_cells_by_sink) {
        if (sink_id < 0 || sink_id >= n || depression_cell_ids.empty()) {
            throw std::runtime_error("hydrology depression unit is invalid");
        }
        Cell& sink_cell = cells[static_cast<std::size_t>(sink_id)];
        double area_km2 = 0.0;
        double runoff_area_sum = 0.0;
        double precipitation_area_sum = 0.0;
        double pet_area_sum = 0.0;
        double max_depression_depth_m = 0.0;
        for (int cell_id : depression_cell_ids) {
            Cell& cell = cells[static_cast<std::size_t>(cell_id)];
            cell.depression_component_id = depression_component_id;
            cell.depression_sink_cell_id = sink_id;
            area_km2 += cell.area_km2;
            runoff_area_sum += cell.runoff_mm_y * cell.area_km2;
            precipitation_area_sum += cell.precipitation_mm_y * cell.area_km2;
            pet_area_sum +=
                cell.hydrologic_potential_evapotranspiration_mm_y *
                cell.area_km2;
            max_depression_depth_m = std::max(max_depression_depth_m, cell.depression_depth_m);
        }
        if (area_km2 <= 0.0) {
            throw std::runtime_error("hydrology depression unit has no area");
        }
        const double mean_runoff_mm_y = runoff_area_sum / area_km2;
        const double mean_precipitation_mm_y = precipitation_area_sum / area_km2;
        const double mean_pet_mm_y = pet_area_sum / area_km2;
        const double aridity = mean_precipitation_mm_y / std::max(1.0, mean_pet_mm_y);
        const double fill_fraction = clamp(
            (mean_runoff_mm_y / 220.0) * clamp(aridity, 0.08, 2.5) /
                (1.0 + max_depression_depth_m / 120.0),
            0.0,
            1.5
        );

        std::vector<int> spill_path;
        int spill_destination = -1;
        int current = sink_id;
        for (int step = 0; step <= n; ++step) {
            if (current < 0 || current >= n ||
                raw_sink_by_cell[static_cast<std::size_t>(current)] != sink_id) {
                break;
            }
            spill_path.push_back(current);
            const int next = cells[static_cast<std::size_t>(current)].spill_to;
            if (next < 0 || next >= n) {
                break;
            }
            if (cells[static_cast<std::size_t>(next)].is_water ||
                raw_sink_by_cell[static_cast<std::size_t>(next)] != sink_id) {
                spill_destination = next;
                break;
            }
            current = next;
        }

        const bool geologic_depression =
            params.preserve_geologic_depressions && is_geologic_depression(sink_cell);
        const bool wet_geologic_depression = geologic_depression && mean_runoff_mm_y > 25.0;
        const bool temporary_numeric_depression =
            !geologic_depression &&
            std::any_of(
                depression_cell_ids.begin(),
                depression_cell_ids.end(),
                [&cells](int cell_id) {
                    return cells[static_cast<std::size_t>(cell_id)]
                        .numeric_depression_temporary_lake_deferred;
                }
            );
        const bool wet_temporary_numeric_depression =
            temporary_numeric_depression && mean_runoff_mm_y > 25.0;
        const bool geologic_overflows =
            wet_geologic_depression && spill_destination >= 0 && fill_fraction >= 1.0;
        const bool temporary_numeric_lake_overflows =
            wet_temporary_numeric_depression &&
            spill_destination >= 0 && fill_fraction >= 1.0;
        const bool overflows =
            geologic_overflows || temporary_numeric_lake_overflows;
        int policy = 0;
        if (geologic_overflows) {
            policy = 3;
        } else if (wet_geologic_depression) {
            policy = 2;
        } else if (geologic_depression) {
            policy = 4;
        } else if (temporary_numeric_depression) {
            policy = 5;
        } else if (spill_destination >= 0) {
            policy = 1;
        } else {
            policy = 4;
        }

        for (int cell_id : depression_cell_ids) {
            Cell& cell = cells[static_cast<std::size_t>(cell_id)];
            cell.depression_policy = policy;
            cell.lake_fill_fraction = fill_fraction;
            cell.is_closed_basin = false;
            cell.lake_overflows = false;
            cell.is_lake = false;
            cell.water_body = 0;
            cell.water_depth_m = 0.0;
        }

        if (policy == 1 || policy == 3 ||
            (policy == 5 && temporary_numeric_lake_overflows)) {
            if (spill_destination < 0 || spill_path.empty()) {
                throw std::runtime_error("open depression unit has no spill corridor");
            }
            for (int path_cell_id : spill_path) {
                Cell& path_cell = cells[static_cast<std::size_t>(path_cell_id)];
                if (path_cell.spill_to < 0 || path_cell.spill_to >= n) {
                    throw std::runtime_error("depression spill corridor is invalid");
                }
                path_cell.flow_to = path_cell.spill_to;
            }
        } else {
            for (int cell_id : depression_cell_ids) {
                Cell& cell = cells[static_cast<std::size_t>(cell_id)];
                const int raw_receiver = raw_flow_to[static_cast<std::size_t>(cell_id)];
                if (cell_id != sink_id &&
                    (raw_receiver < 0 || raw_receiver >= n ||
                        raw_sink_by_cell[static_cast<std::size_t>(raw_receiver)] != sink_id ||
                        cells[static_cast<std::size_t>(raw_receiver)].depression_depth_m <= 1.0e-9)) {
                    throw std::runtime_error("closed depression raw routing leaves its footprint");
                }
                cell.flow_to = raw_receiver;
                cell.equal_filled_raw_downhill_rerouted = false;
            }
            sink_cell.flow_to = -1;
            sink_cell.is_closed_basin = true;
        }

        if (wet_geologic_depression || wet_temporary_numeric_depression) {
            const int water_body = aridity < 0.5 ? 5 : 4;
            const double water_surface_m = sink_cell.elevation_m +
                std::min(1.0, fill_fraction) *
                    std::max(0.0, sink_cell.spill_elevation_m - sink_cell.elevation_m);
            for (int cell_id : depression_cell_ids) {
                Cell& cell = cells[static_cast<std::size_t>(cell_id)];
                const double depth_m = std::max(0.0, water_surface_m - cell.elevation_m);
                if (depth_m > 1.0e-9) {
                    cell.is_lake = true;
                    cell.water_body = overflows ? 4 : water_body;
                    cell.water_depth_m = clamp(depth_m, 0.2, 240.0);
                }
            }
            sink_cell.is_lake = true;
            sink_cell.water_body = overflows ? 4 : water_body;
            sink_cell.water_depth_m = clamp(
                std::max(0.2, water_surface_m - sink_cell.elevation_m),
                0.2,
                240.0
            );
            sink_cell.lake_overflows = overflows;
        } else if (geologic_depression && aridity < 0.55) {
            sink_cell.water_body = 5;
        }
        depression_component_id++;
    }

    std::vector<int> upstream_count(static_cast<std::size_t>(n), 0);
    for (int i = 0; i < n; ++i) {
        const int to = cells[static_cast<std::size_t>(i)].flow_to;
        if (to >= 0) {
            if (to >= n || to == i) {
                throw std::runtime_error("hydrology flow receiver is invalid");
            }
            upstream_count[static_cast<std::size_t>(to)]++;
        }
    }
    std::priority_queue<int, std::vector<int>, std::greater<int>> ready;
    for (int i = 0; i < n; ++i) {
        if (upstream_count[static_cast<std::size_t>(i)] == 0) {
            ready.push(i);
        }
    }
    int processed_flow_cells = 0;
    std::vector<int> flow_order;
    flow_order.reserve(static_cast<std::size_t>(n));
    while (!ready.empty()) {
        const int current = ready.top();
        ready.pop();
        processed_flow_cells++;
        flow_order.push_back(current);
        const int to = cells[static_cast<std::size_t>(current)].flow_to;
        if (to < 0) {
            continue;
        }
        if (!cells[static_cast<std::size_t>(current)].is_water) {
            cells[static_cast<std::size_t>(to)].flow_accumulation +=
                cells[static_cast<std::size_t>(current)].flow_accumulation;
        }
        int& remaining = upstream_count[static_cast<std::size_t>(to)];
        remaining--;
        if (remaining == 0) {
            ready.push(to);
        }
    }
    if (processed_flow_cells != n) {
        throw std::runtime_error("hydrology flow graph contains a cycle");
    }
    condition_hydrologic_surface(params, cells, flow_order);
    std::vector<double> accum;
    for (const Cell& cell : cells) {
        if (!cell.is_water && cell.flow_accumulation > 0.0) {
            accum.push_back(cell.flow_accumulation);
        }
    }
    if (accum.empty()) {
        return;
    }
    std::sort(accum.begin(), accum.end());
    const auto idx = static_cast<std::size_t>(clamp(params.river_percentile, 0.5, 0.999) * static_cast<double>(accum.size() - 1));
    const double threshold = std::max(1.0, accum[idx]);
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        if (cells[i].is_water || cells[i].flow_to < 0) {
            continue;
        }
        cells[i].is_river = cells[i].flow_accumulation >= threshold &&
            cells[i].hydrologic_flow_slope > 0.0 && cells[i].runoff_mm_y > 10.0;
    }
    assign_basin_ids(cells);
}

void derive_numeric_depression_breach_alternative(
    const Params& params,
    const std::vector<Cell>& cells,
    const std::vector<double>& elevation_before_correction_m,
    const std::vector<int>& source_component_cell_ids,
    NumericDepressionCorrectionEvent& event
) {
    if (event.sink_cell_id < 0 ||
        event.sink_cell_id >= static_cast<int>(cells.size()) ||
        elevation_before_correction_m.size() != cells.size()) {
        throw std::runtime_error("numeric depression breach diagnostic input is invalid");
    }

    const int n = static_cast<int>(cells.size());
    const std::set<int> source_cells(
        source_component_cell_ids.begin(),
        source_component_cell_ids.end()
    );
    const double sink_elevation_m = elevation_before_correction_m[
        static_cast<std::size_t>(event.sink_cell_id)
    ];
    std::vector<double> best_cost_km3(
        static_cast<std::size_t>(n),
        std::numeric_limits<double>::infinity()
    );
    std::vector<int> parent(static_cast<std::size_t>(n), -1);
    std::vector<int> hop_count(static_cast<std::size_t>(n), 0);
    std::priority_queue<
        std::pair<double, int>,
        std::vector<std::pair<double, int>>,
        std::greater<std::pair<double, int>>
    > queue;
    best_cost_km3[static_cast<std::size_t>(event.sink_cell_id)] = 0.0;
    queue.push({0.0, event.sink_cell_id});

    int outlet_cell_id = -1;
    while (!queue.empty()) {
        const auto [cost_km3, current] = queue.top();
        queue.pop();
        if (cost_km3 > best_cost_km3[static_cast<std::size_t>(current)] + 1.0e-12) {
            continue;
        }
        const int current_hops = hop_count[static_cast<std::size_t>(current)];
        const double current_elevation_m =
            elevation_before_correction_m[static_cast<std::size_t>(current)];
        if (current != event.sink_cell_id &&
            source_cells.count(current) == 0 &&
            current_elevation_m <= sink_elevation_m -
                NUMERIC_DEPRESSION_BREACH_GRADIENT_STEP_M * current_hops) {
            outlet_cell_id = current;
            break;
        }

        for (int next : cells[static_cast<std::size_t>(current)].neighbors) {
            if (next < 0 || next >= n || next == current) {
                throw std::runtime_error("numeric depression breach graph is invalid");
            }
            const int next_hops = current_hops + 1;
            const double required_upper_m = sink_elevation_m -
                NUMERIC_DEPRESSION_BREACH_GRADIENT_STEP_M * next_hops;
            const double next_elevation_m =
                elevation_before_correction_m[static_cast<std::size_t>(next)];
            const bool outside_source = source_cells.count(next) == 0;
            const bool naturally_lower_outlet =
                outside_source && next_elevation_m <= required_upper_m;
            const bool enters_other_depression =
                outside_source &&
                cells[static_cast<std::size_t>(next)].depression_component_id >= 0 &&
                cells[static_cast<std::size_t>(next)].depression_component_id !=
                    event.source_depression_component_id;
            if (!naturally_lower_outlet &&
                (cells[static_cast<std::size_t>(next)].is_water ||
                    enters_other_depression)) {
                continue;
            }

            const double excavation_depth_m = naturally_lower_outlet ?
                0.0 : std::max(0.0, next_elevation_m - required_upper_m);
            const double candidate_cost_km3 = cost_km3 +
                excavation_depth_m *
                    cells[static_cast<std::size_t>(next)].area_km2 / 1000.0;
            double& best_next_cost_km3 =
                best_cost_km3[static_cast<std::size_t>(next)];
            const int previous_parent = parent[static_cast<std::size_t>(next)];
            if (candidate_cost_km3 < best_next_cost_km3 - 1.0e-9 ||
                (std::abs(candidate_cost_km3 - best_next_cost_km3) <= 1.0e-9 &&
                    (previous_parent < 0 || current < previous_parent))) {
                best_next_cost_km3 = candidate_cost_km3;
                parent[static_cast<std::size_t>(next)] = current;
                hop_count[static_cast<std::size_t>(next)] = next_hops;
                queue.push({candidate_cost_km3, next});
            }
        }
    }

    if (outlet_cell_id >= 0) {
        std::vector<int> reverse_path;
        int current = outlet_cell_id;
        for (int step = 0; step <= n; ++step) {
            reverse_path.push_back(current);
            if (current == event.sink_cell_id) {
                break;
            }
            current = parent[static_cast<std::size_t>(current)];
            if (current < 0 || current >= n) {
                reverse_path.clear();
                break;
            }
        }
        if (!reverse_path.empty() &&
            reverse_path.back() == event.sink_cell_id) {
            event.breach_path_cell_ids.assign(
                reverse_path.rbegin(),
                reverse_path.rend()
            );
            event.breach_feasible = true;
            event.breach_outlet_cell_id = outlet_cell_id;
        }
    }

    double current_target_m = sink_elevation_m;
    for (std::size_t index = 0; index < event.breach_path_cell_ids.size(); ++index) {
        const int cell_id = event.breach_path_cell_ids[index];
        const double before_m =
            elevation_before_correction_m[static_cast<std::size_t>(cell_id)];
        double target_m = before_m;
        if (index == 0) {
            target_m = sink_elevation_m;
        } else if (cell_id != outlet_cell_id) {
            target_m = std::min(
                before_m,
                current_target_m - NUMERIC_DEPRESSION_BREACH_GRADIENT_STEP_M
            );
        }
        const double excavation_depth_m = std::max(0.0, before_m - target_m);
        event.breach_elevation_before_m_by_cell.push_back(before_m);
        event.breach_target_elevation_m_by_cell.push_back(target_m);
        event.breach_excavation_depth_m_by_cell.push_back(excavation_depth_m);
        event.breach_sediment_thickness_before_excavation_m_by_cell.push_back(
            cells[static_cast<std::size_t>(cell_id)].sediment_thickness_m
        );
        event.breach_alluvium_entrainment_depth_m_by_cell.push_back(0.0);
        event.breach_bedrock_erosion_depth_m_by_cell.push_back(0.0);
        if (index > 0) {
            event.breach_path_length_km += neighbor_distance_m(
                params,
                cells[static_cast<std::size_t>(event.breach_path_cell_ids[index - 1])],
                cells[static_cast<std::size_t>(cell_id)]
            ) / 1000.0;
        }
        if (excavation_depth_m > NUMERIC_DEPRESSION_FILL_DEPTH_TOLERANCE_M) {
            const Cell& path_cell = cells[static_cast<std::size_t>(cell_id)];
            event.breach_excavation_area_km2 += path_cell.area_km2;
            event.breach_excavation_volume_km3 +=
                excavation_depth_m * path_cell.area_km2 / 1000.0;
            event.max_breach_excavation_depth_m = std::max(
                event.max_breach_excavation_depth_m,
                excavation_depth_m
            );
        }
        current_target_m = target_m;
    }

    event.breach_to_fill_volume_ratio = event.fill_volume_km3 > 0.0 ?
        event.breach_excavation_volume_km3 / event.fill_volume_km3 :
        std::numeric_limits<double>::infinity();
    event.breach_has_lower_adjustment_volume =
        event.breach_feasible &&
        event.breach_excavation_volume_km3 + 1.0e-9 < event.fill_volume_km3;
}

void apply_numeric_depression_correction(
    std::vector<Cell>& cells,
    NumericDepressionCorrectionEvent& event,
    std::set<int>& mutated_cell_ids_this_pass
) {
    std::set<int> excavated_path_cell_ids;
    for (std::size_t index = 0;
         index < event.breach_path_cell_ids.size();
         ++index) {
        if (event.breach_excavation_depth_m_by_cell[index] >
            NUMERIC_DEPRESSION_FILL_DEPTH_TOLERANCE_M) {
            excavated_path_cell_ids.insert(event.breach_path_cell_ids[index]);
        }
    }

    std::vector<std::size_t> deposition_candidate_indices;
    for (std::size_t index = 0; index < event.cell_ids.size(); ++index) {
        const int cell_id = event.cell_ids[index];
        if (excavated_path_cell_ids.count(cell_id) != 0) {
            continue;
        }
        const double capacity_depth_m = event.fill_depth_m_by_cell[index];
        const Cell& cell = cells[static_cast<std::size_t>(cell_id)];
        const double sediment_capacity_depth_m = std::max(
            0.0,
            5000.0 -
                event.sediment_thickness_before_correction_m_by_cell[index]
        );
        const double usable_depth_m = std::min(
            capacity_depth_m,
            sediment_capacity_depth_m
        );
        if (usable_depth_m <= NUMERIC_DEPRESSION_FILL_DEPTH_TOLERANCE_M) {
            continue;
        }
        deposition_candidate_indices.push_back(index);
        event.breach_deposition_capacity_km3 +=
            usable_depth_m * cell.area_km2 / 1000.0;
    }

    event.breach_depth_bound_passed =
        event.breach_feasible &&
        event.max_breach_excavation_depth_m <=
            NUMERIC_DEPRESSION_SELECTED_BREACH_MAX_DEPTH_M +
                NUMERIC_DEPRESSION_FILL_DEPTH_TOLERANCE_M;
    event.breach_deposition_capacity_sufficient =
        event.breach_feasible &&
        event.breach_deposition_capacity_km3 + 1.0e-9 >=
            event.breach_excavation_volume_km3;
    event.breach_same_pass_conflict_free = event.breach_feasible;
    for (int cell_id : excavated_path_cell_ids) {
        if (mutated_cell_ids_this_pass.count(cell_id) != 0) {
            event.breach_same_pass_conflict_free = false;
            break;
        }
    }
    if (event.breach_same_pass_conflict_free) {
        for (std::size_t index : deposition_candidate_indices) {
            if (mutated_cell_ids_this_pass.count(event.cell_ids[index]) != 0) {
                event.breach_same_pass_conflict_free = false;
                break;
            }
        }
    }

    event.breach_selected =
        event.breach_has_lower_adjustment_volume &&
        event.breach_depth_bound_passed &&
        event.breach_deposition_capacity_sufficient &&
        event.breach_same_pass_conflict_free;
    event.temporary_numeric_lake_selected = !event.breach_selected;

    if (!event.breach_selected) {
        for (std::size_t index = 0; index < event.cell_ids.size(); ++index) {
            const int cell_id = event.cell_ids[index];
            Cell& cell = cells[static_cast<std::size_t>(cell_id)];
            const double before_fill_m = event.elevation_before_fill_m_by_cell[index];
            if (std::abs(cell.elevation_m - before_fill_m) > 1.0e-7) {
                throw std::runtime_error(
                    "numeric depression deferral conflicts with an earlier correction"
                );
            }
            cell.numeric_depression_temporary_lake_deferred = true;
            cell.numeric_depression_temporary_lake_event_count++;
        }
        event.correction_mass_balance_residual_km3 = 0.0;
        return;
    }

    for (std::size_t index = 0;
         index < event.breach_path_cell_ids.size();
         ++index) {
        const double excavation_depth_m =
            event.breach_excavation_depth_m_by_cell[index];
        if (excavation_depth_m <= NUMERIC_DEPRESSION_FILL_DEPTH_TOLERANCE_M) {
            continue;
        }
        const int cell_id = event.breach_path_cell_ids[index];
        Cell& cell = cells[static_cast<std::size_t>(cell_id)];
        const double before_m = event.breach_elevation_before_m_by_cell[index];
        if (std::abs(cell.elevation_m - before_m) > 1.0e-7) {
            throw std::runtime_error(
                "numeric depression breach conflicts with an earlier correction"
            );
        }
        const double sediment_thickness_before_m = cell.sediment_thickness_m;
        const double alluvium_entrainment_depth_m = std::min(
            sediment_thickness_before_m,
            excavation_depth_m
        );
        const double bedrock_erosion_depth_m = std::max(
            0.0,
            excavation_depth_m - alluvium_entrainment_depth_m
        );
        event.breach_alluvium_entrainment_depth_m_by_cell[index] =
            alluvium_entrainment_depth_m;
        event.breach_bedrock_erosion_depth_m_by_cell[index] =
            bedrock_erosion_depth_m;
        apply_sediment_interface_material_change(
            cell,
            0.0,
            bedrock_erosion_depth_m,
            alluvium_entrainment_depth_m,
            0.0,
            "numeric depression breach excavation"
        );
        if (
            std::abs(
                cell.elevation_m -
                event.breach_target_elevation_m_by_cell[index]
            ) > 1.0e-7
        ) {
            throw std::runtime_error(
                "numeric depression breach sediment-interface target mismatch"
            );
        }
        cell.sediment_alluvium_entrainment_m +=
            alluvium_entrainment_depth_m;
        cell.sediment_bedrock_erosion_m += bedrock_erosion_depth_m;
        cell.sediment_net_budget_m =
            cell.sediment_deposition_m -
            sediment_gross_mobilization_m(cell);
        cell.cumulative_numeric_depression_breach_excavation_m +=
            excavation_depth_m;
        cell.numeric_depression_breach_event_count++;
        event.applied_breach_excavation_volume_km3 +=
            excavation_depth_m * cell.area_km2 / 1000.0;
        event.applied_alluvium_entrainment_volume_km3 +=
            alluvium_entrainment_depth_m * cell.area_km2 / 1000.0;
        event.applied_bedrock_erosion_volume_km3 +=
            bedrock_erosion_depth_m * cell.area_km2 / 1000.0;
        mutated_cell_ids_this_pass.insert(cell_id);
    }

    double remaining_deposition_volume_km3 =
        event.applied_breach_excavation_volume_km3;
    for (std::size_t candidate_position = 0;
         candidate_position < deposition_candidate_indices.size();
         ++candidate_position) {
        const std::size_t event_index =
            deposition_candidate_indices[candidate_position];
        const int cell_id = event.cell_ids[event_index];
        Cell& cell = cells[static_cast<std::size_t>(cell_id)];
        const double capacity_depth_m = std::min(
            event.fill_depth_m_by_cell[event_index],
            std::max(0.0, 5000.0 - cell.sediment_thickness_m)
        );
        const double capacity_volume_km3 =
            capacity_depth_m * cell.area_km2 / 1000.0;
        const double proportional_volume_km3 =
            event.breach_deposition_capacity_km3 > 0.0 ?
                event.applied_breach_excavation_volume_km3 *
                    capacity_volume_km3 /
                    event.breach_deposition_capacity_km3 :
                0.0;
        const bool last_candidate =
            candidate_position + 1 == deposition_candidate_indices.size();
        const double deposition_volume_km3 = std::min(
            capacity_volume_km3,
            last_candidate ? remaining_deposition_volume_km3 :
                std::min(remaining_deposition_volume_km3, proportional_volume_km3)
        );
        if (deposition_volume_km3 <= 1.0e-12) {
            continue;
        }
        const double deposition_depth_m =
            deposition_volume_km3 * 1000.0 / cell.area_km2;
        apply_sediment_interface_material_change(
            cell,
            0.0,
            0.0,
            0.0,
            deposition_depth_m,
            "numeric depression breach deposition"
        );
        cell.sediment_deposition_m += deposition_depth_m;
        cell.sediment_net_budget_m =
            cell.sediment_deposition_m -
            sediment_gross_mobilization_m(cell);
        cell.cumulative_numeric_depression_breach_deposition_m +=
            deposition_depth_m;
        cell.numeric_depression_breach_event_count++;
        event.breach_deposition_cell_ids.push_back(cell_id);
        event.breach_deposition_depth_m_by_cell.push_back(deposition_depth_m);
        event.applied_breach_deposition_volume_km3 += deposition_volume_km3;
        remaining_deposition_volume_km3 = std::max(
            0.0,
            remaining_deposition_volume_km3 - deposition_volume_km3
        );
        mutated_cell_ids_this_pass.insert(cell_id);
    }
    maximum_sediment_interface_closure_residual_m(
        cells,
        "post numeric depression breach correction"
    );
    if (remaining_deposition_volume_km3 > 1.0e-7) {
        throw std::runtime_error(
            "numeric depression breach deposition capacity was not realized"
        );
    }
    event.correction_mass_balance_residual_km3 = std::abs(
        event.applied_breach_excavation_volume_km3 -
            event.applied_breach_deposition_volume_km3
    );
}

HydrologyStabilizationResult stabilize_numeric_depressions(
    const Params& params,
    std::vector<Cell>& cells,
    int feedback_stage_id,
    const std::string& stage,
    int erosion_iteration,
    std::vector<NumericDepressionCorrectionEvent>& correction_history,
    std::vector<HydrologicWaterBudgetStage>& water_budget_history
) {
    HydrologyStabilizationResult result;
    std::set<int> temporary_lake_unique_cell_ids;
    for (Cell& cell : cells) {
        cell.numeric_depression_temporary_lake_deferred = false;
    }

    for (int recomputation_index = 0;
         recomputation_index <= NUMERIC_DEPRESSION_CORRECTION_MAX_PASSES;
         ++recomputation_index) {
        result.sea_level_adjustment_m += apply_sea_level(params, cells);
        result.sea_level_recompute_count++;
        label_marine_water_bodies(cells);
        compute_climate(params, cells);
        result.climate_recompute_count++;
        water_budget_history.push_back(compute_hydrologic_water_budget(
            cells,
            static_cast<int>(water_budget_history.size()),
            feedback_stage_id,
            stage,
            erosion_iteration,
            recomputation_index
        ));
        result.hydrologic_water_budget_recompute_count++;
        compute_flow_and_rivers(params, cells);
        result.hydrology_recompute_count++;

        std::map<int, std::vector<int>> cells_by_component;
        for (const Cell& cell : cells) {
            if (!cell.is_water && cell.depression_policy == 1) {
                if (cell.depression_component_id < 0 ||
                    cell.depression_sink_cell_id < 0 ||
                    cell.depression_depth_m <= NUMERIC_DEPRESSION_FILL_DEPTH_TOLERANCE_M) {
                    throw std::runtime_error("numeric depression correction candidate is invalid");
                }
                cells_by_component[cell.depression_component_id].push_back(cell.id);
            }
        }
        if (cells_by_component.empty()) {
            result.numeric_depression_temporary_lake_unique_cell_count =
                static_cast<int>(temporary_lake_unique_cell_ids.size());
            maximum_sediment_interface_closure_residual_m(
                cells,
                "post hydrology stabilization"
            );
            return result;
        }
        if (recomputation_index == NUMERIC_DEPRESSION_CORRECTION_MAX_PASSES) {
            throw std::runtime_error("numeric depression correction did not converge within the bounded pass count");
        }

        result.numeric_depression_correction_pass_count++;
        const int stabilization_pass = result.numeric_depression_correction_pass_count;
        std::vector<double> elevation_before_correction_m;
        elevation_before_correction_m.reserve(cells.size());
        for (const Cell& cell : cells) {
            elevation_before_correction_m.push_back(cell.elevation_m);
        }
        std::set<int> mutated_cell_ids_this_pass;
        for (const auto& [component_id, cell_ids] : cells_by_component) {
            if (cell_ids.empty()) {
                throw std::runtime_error("numeric depression correction component is empty");
            }
            const Cell& first_cell = cells[static_cast<std::size_t>(cell_ids.front())];
            const int sink_cell_id = first_cell.depression_sink_cell_id;
            if (sink_cell_id < 0 || sink_cell_id >= static_cast<int>(cells.size())) {
                throw std::runtime_error("numeric depression correction sink is invalid");
            }
            const Cell& sink = cells[static_cast<std::size_t>(sink_cell_id)];

            NumericDepressionCorrectionEvent event;
            event.id = static_cast<int>(correction_history.size());
            event.feedback_stage_id = feedback_stage_id;
            event.stage = stage;
            event.erosion_iteration = erosion_iteration;
            event.stabilization_pass = stabilization_pass;
            event.source_depression_component_id = component_id;
            event.sink_cell_id = sink_cell_id;
            event.sink_crust_type = sink.crust_type;
            event.sink_is_geologic = is_geologic_depression(sink);
            event.sink_boundary_divergent = sink.boundary_divergent;
            event.sink_boundary_convergent = sink.boundary_convergent;
            event.cell_ids.reserve(cell_ids.size());
            event.elevation_before_fill_m_by_cell.reserve(cell_ids.size());
            event.sediment_thickness_before_correction_m_by_cell.reserve(
                cell_ids.size()
            );
            event.fill_depth_m_by_cell.reserve(cell_ids.size());
            event.elevation_after_fill_m_by_cell.reserve(cell_ids.size());

            for (int cell_id : cell_ids) {
                const Cell& cell = cells[static_cast<std::size_t>(cell_id)];
                if (cell.depression_component_id != component_id ||
                    cell.depression_sink_cell_id != sink_cell_id ||
                    cell.depression_policy != 1 ||
                    !std::isfinite(cell.elevation_m) ||
                    !std::isfinite(cell.filled_elevation_m)) {
                    throw std::runtime_error("numeric depression correction metadata is inconsistent");
                }
                const double before_fill_m = cell.elevation_m;
                const double fill_depth_m = cell.filled_elevation_m - before_fill_m;
                if (fill_depth_m <= NUMERIC_DEPRESSION_FILL_DEPTH_TOLERANCE_M ||
                    std::abs(fill_depth_m - cell.depression_depth_m) > 1.0e-7) {
                    throw std::runtime_error("numeric depression correction depth is invalid");
                }
                const double after_fill_m = before_fill_m + fill_depth_m;
                event.cell_ids.push_back(cell_id);
                event.elevation_before_fill_m_by_cell.push_back(before_fill_m);
                event.sediment_thickness_before_correction_m_by_cell.push_back(
                    cell.sediment_thickness_m
                );
                event.fill_depth_m_by_cell.push_back(fill_depth_m);
                event.elevation_after_fill_m_by_cell.push_back(after_fill_m);
                event.area_km2 += cell.area_km2;
                event.fill_volume_km3 += fill_depth_m * cell.area_km2 / 1000.0;
                event.max_fill_depth_m = std::max(event.max_fill_depth_m, fill_depth_m);
            }

            derive_numeric_depression_breach_alternative(
                params,
                cells,
                elevation_before_correction_m,
                cell_ids,
                event
            );
            apply_numeric_depression_correction(
                cells,
                event,
                mutated_cell_ids_this_pass
            );

            result.numeric_depression_correction_event_count++;
            result.numeric_depression_correction_mass_balance_residual_km3 +=
                event.correction_mass_balance_residual_km3;
            if (event.breach_selected) {
                result.numeric_depression_breach_selected_event_count++;
                result.numeric_depression_breach_excavation_cell_application_count +=
                    static_cast<int>(std::count_if(
                        event.breach_excavation_depth_m_by_cell.begin(),
                        event.breach_excavation_depth_m_by_cell.end(),
                        [](double depth_m) {
                            return depth_m >
                                NUMERIC_DEPRESSION_FILL_DEPTH_TOLERANCE_M;
                        }
                    ));
                result.numeric_depression_breach_deposition_cell_application_count +=
                    static_cast<int>(event.breach_deposition_cell_ids.size());
                result.numeric_depression_breach_excavation_volume_km3 +=
                    event.applied_breach_excavation_volume_km3;
                result.numeric_depression_breach_deposition_volume_km3 +=
                    event.applied_breach_deposition_volume_km3;
                result.numeric_depression_alluvium_entrainment_volume_km3 +=
                    event.applied_alluvium_entrainment_volume_km3;
                result.numeric_depression_bedrock_erosion_volume_km3 +=
                    event.applied_bedrock_erosion_volume_km3;
            } else {
                result.numeric_depression_temporary_lake_event_count++;
                result.numeric_depression_temporary_lake_cell_application_count +=
                    static_cast<int>(event.cell_ids.size());
                result.numeric_depression_temporary_lake_candidate_area_km2 +=
                    event.area_km2;
                result.numeric_depression_temporary_lake_candidate_volume_km3 +=
                    event.fill_volume_km3;
                result.max_numeric_depression_temporary_lake_depth_m = std::max(
                    result.max_numeric_depression_temporary_lake_depth_m,
                    event.max_fill_depth_m
                );
                for (int cell_id : event.cell_ids) {
                    temporary_lake_unique_cell_ids.insert(cell_id);
                }
            }
            correction_history.push_back(std::move(event));
        }
    }

    throw std::runtime_error("numeric depression fill stabilization terminated unexpectedly");
}

}  // namespace magic_geo::detail
