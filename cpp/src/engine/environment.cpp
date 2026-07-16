#include "internal.hpp"

namespace magic_geo::detail {

bool has_ocean_neighbor(const std::vector<Cell>& cells, int i) {
    for (int j : cells[i].neighbors) {
        if (cells[j].is_water) {
            return true;
        }
    }
    return false;
}

bool has_glacier_neighbor(const std::vector<Cell>& cells, int i, double threshold_m) {
    for (int j : cells[i].neighbors) {
        if (cells[j].ice_thickness_m >= threshold_m) {
            return true;
        }
    }
    return false;
}

void derive_cryosphere_state(const Params& params, std::vector<Cell>& cells) {
    const int n = static_cast<int>(cells.size());
    for (int i = 0; i < n; ++i) {
        Cell& cell = cells[i];
        cell.ice_thickness_m = 0.0;
        cell.glacier_flow_to = -1;
        cell.ice_surface_mass_balance_m_y = 0.0;
        cell.basal_sliding_index = 0.0;
        cell.ice_velocity_m_y = 0.0;
        cell.glacial_erosion_m = 0.0;
        if (cell.is_water) {
            continue;
        }

        const double lat_factor = clamp((std::abs(cell.lat) * DEG - 50.0) / 32.0, 0.0, 1.25);
        const double elevation_factor = clamp((cell.elevation_m - 1250.0) / 2500.0, 0.0, 1.25);
        const double cold_index = clamp((-cell.temperature_c - 3.0) / 22.0, 0.0, 1.25);
        const double moisture = clamp((cell.precipitation_mm_y - 140.0) / 1500.0, 0.05, 1.15);
        const double persistence = cold_index * moisture * (0.42 + std::max(lat_factor, elevation_factor));
        if (persistence > 0.16) {
            cell.ice_thickness_m = clamp((persistence - 0.16) * 1350.0, 0.0, 3200.0);
            if (cell.temperature_c > -2.0 && cell.elevation_m < 1900.0) {
                cell.ice_thickness_m *= 0.35;
            }
            if (cell.ice_thickness_m < 25.0) {
                cell.ice_thickness_m = 0.0;
            }
        }

        if (cell.ice_thickness_m <= 0.0) {
            continue;
        }
        const double accumulation_m_y = clamp(
            (cell.precipitation_mm_y / 1000.0) * clamp((-cell.temperature_c + 1.0) / 18.0, 0.0, 1.4),
            0.0,
            3.2
        );
        const double ablation_m_y = clamp(std::max(0.0, cell.temperature_c + 1.5) * 0.075, 0.0, 4.0);
        cell.ice_surface_mass_balance_m_y = clamp(accumulation_m_y - ablation_m_y, -4.0, 3.2);
        double best_drop = 0.0;
        int best = -1;
        for (int j : cell.neighbors) {
            const double drop = cell.elevation_m - cells[j].elevation_m;
            if (drop > best_drop) {
                best_drop = drop;
                best = j;
            }
        }
        cell.glacier_flow_to = best;
        if (best >= 0) {
            const double distance = neighbor_distance_m(params, cell, cells[best]);
            const double slope = best_drop / distance;
            cell.basal_sliding_index = clamp(
                0.18 + 0.32 * clamp(cell.ice_thickness_m / 1800.0, 0.0, 1.0) +
                    0.22 * clamp((cell.temperature_c + 8.0) / 10.0, 0.0, 1.0) +
                    0.14 * clamp(cell.precipitation_mm_y / 1600.0, 0.0, 1.0) +
                    0.24 * clamp(slope * 900.0, 0.0, 1.0),
                0.0,
                1.0
            );
            cell.ice_velocity_m_y = clamp(
                4.0 + 110.0 * cell.basal_sliding_index +
                    85.0 * clamp(cell.ice_thickness_m / 2200.0, 0.0, 1.0) * clamp(slope * 1200.0, 0.0, 1.4),
                0.0,
                420.0
            );
            cell.glacial_erosion_m = clamp((cell.ice_thickness_m / 1000.0) * std::max(0.0, slope * 900.0) * 12.0, 0.0, 85.0);
        } else {
            cell.basal_sliding_index = clamp(
                0.12 + 0.30 * clamp(cell.ice_thickness_m / 1800.0, 0.0, 1.0) +
                    0.18 * clamp((cell.temperature_c + 8.0) / 10.0, 0.0, 1.0),
                0.0,
                1.0
            );
            cell.ice_velocity_m_y = clamp(2.0 + 52.0 * cell.basal_sliding_index, 0.0, 120.0);
        }
    }
}

GlacialSedimentTransportStage transport_glacial_sediment(
    int id,
    int feedback_stage_id,
    std::vector<Cell>& cells
) {
    const int n = static_cast<int>(cells.size());
    GlacialSedimentTransportStage stage;
    stage.id = id;
    stage.feedback_stage_id = feedback_stage_id;
    stage.cell_count = n;
    stage.input_cells.reserve(static_cast<std::size_t>(n));
    std::vector<double> production_depth_m(static_cast<std::size_t>(n), 0.0);
    std::vector<double> deposition_depth_m(static_cast<std::size_t>(n), 0.0);
    stage.alluvium_entrainment_depth_m_by_cell.assign(
        static_cast<std::size_t>(n), 0.0
    );
    stage.bedrock_erosion_depth_m_by_cell.assign(
        static_cast<std::size_t>(n), 0.0
    );
    std::set<int> target_cell_ids;

    for (int cell_id = 0; cell_id < n; ++cell_id) {
        const Cell& cell = cells[static_cast<std::size_t>(cell_id)];
        GlacialSedimentTransportInputCell input;
        input.cell_id = cell_id;
        input.glacier_flow_to_cell_id = cell.glacier_flow_to;
        input.is_water = cell.is_water;
        input.elevation_m = cell.elevation_m;
        input.ice_thickness_m = cell.ice_thickness_m;
        input.glacial_erosion_m = cell.glacial_erosion_m;
        input.sediment_thickness_m = cell.sediment_thickness_m;
        stage.input_cells.push_back(input);
    }

    for (int source_cell_id = 0; source_cell_id < n; ++source_cell_id) {
        Cell& source = cells[static_cast<std::size_t>(source_cell_id)];
        const int target_cell_id = source.glacier_flow_to;
        if (target_cell_id < 0 || source.glacial_erosion_m <= 0.0) {
            continue;
        }
        if (
            target_cell_id >= n ||
            std::find(
                source.neighbors.begin(),
                source.neighbors.end(),
                target_cell_id
            ) == source.neighbors.end()
        ) {
            throw std::runtime_error(
                "glacial sediment transfer target is invalid"
            );
        }
        Cell& target = cells[static_cast<std::size_t>(target_cell_id)];
        const double elevation_drop_m =
            source.elevation_m - target.elevation_m;
        if (
            source.is_water || source.ice_thickness_m <= 0.0 ||
            elevation_drop_m <= 0.0 || source.area_km2 <= 0.0 ||
            target.area_km2 <= 0.0
        ) {
            throw std::runtime_error(
                "glacial sediment transfer source state is invalid"
            );
        }
        const double source_depth_m =
            source.glacial_erosion_m * GLACIAL_SEDIMENT_MOBILE_FRACTION;
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
        source.glacial_sediment_production_m += source_depth_m;
        source.glacial_sediment_outgoing_transfer_count++;
        target.glacial_sediment_deposition_m += target_depth_m;
        target.glacial_sediment_incoming_transfer_count++;
        target_cell_ids.insert(target_cell_id);

        GlacialSedimentTransfer transfer;
        transfer.id = static_cast<int>(stage.transfers.size());
        transfer.source_cell_id = source_cell_id;
        transfer.target_cell_id = target_cell_id;
        transfer.target_is_water = target.is_water;
        transfer.source_area_km2 = source.area_km2;
        transfer.target_area_km2 = target.area_km2;
        transfer.source_elevation_m = source.elevation_m;
        transfer.target_elevation_m = target.elevation_m;
        transfer.elevation_drop_m = elevation_drop_m;
        transfer.source_ice_thickness_m = source.ice_thickness_m;
        transfer.source_glacial_erosion_m = source.glacial_erosion_m;
        transfer.source_production_depth_m = source_depth_m;
        transfer.target_deposition_depth_m = target_depth_m;
        transfer.transfer_volume_km3 = transfer_volume_km3;
        transfer.mass_balance_residual_km3 = std::abs(
            transfer_volume_km3 - deposited_volume_km3
        );
        stage.transfers.push_back(transfer);
        stage.production_volume_km3 += transfer_volume_km3;
        stage.deposition_volume_km3 += deposited_volume_km3;
        stage.land_target_transfer_count += target.is_water ? 0 : 1;
        stage.marine_target_transfer_count += target.is_water ? 1 : 0;
        stage.max_source_production_depth_m = std::max(
            stage.max_source_production_depth_m,
            source_depth_m
        );
    }

    for (int i = 0; i < n; ++i) {
        Cell& cell = cells[static_cast<std::size_t>(i)];
        const double source_depth_m =
            production_depth_m[static_cast<std::size_t>(i)];
        const double alluvium_entrainment_depth_m = std::min(
            cell.sediment_thickness_m,
            source_depth_m
        );
        const double bedrock_erosion_depth_m = std::max(
            0.0,
            source_depth_m - alluvium_entrainment_depth_m
        );
        stage.alluvium_entrainment_volume_km3 +=
            alluvium_entrainment_depth_m * cell.area_km2 / 1000.0;
        stage.bedrock_erosion_volume_km3 +=
            bedrock_erosion_depth_m * cell.area_km2 / 1000.0;
        stage.alluvium_entrainment_depth_m_by_cell[
            static_cast<std::size_t>(i)
        ] = alluvium_entrainment_depth_m;
        stage.bedrock_erosion_depth_m_by_cell[
            static_cast<std::size_t>(i)
        ] = bedrock_erosion_depth_m;
        cell.sediment_alluvium_entrainment_m +=
            alluvium_entrainment_depth_m;
        cell.sediment_bedrock_erosion_m += bedrock_erosion_depth_m;
        const double compatibility_surface_elevation_m =
            cell.elevation_m +
            deposition_depth_m[static_cast<std::size_t>(i)] -
            source_depth_m;
        cell.sediment_deposition_m +=
            deposition_depth_m[static_cast<std::size_t>(i)];
        apply_sediment_interface_material_change(
            cell,
            0.0,
            bedrock_erosion_depth_m,
            alluvium_entrainment_depth_m,
            deposition_depth_m[static_cast<std::size_t>(i)],
            "glacial sediment interface"
        );
        if (
            std::abs(cell.elevation_m - compatibility_surface_elevation_m) >
            std::max(
                1.0e-9,
                std::abs(compatibility_surface_elevation_m) * 1.0e-12
            )
        ) {
            throw std::runtime_error(
                "glacial sediment-interface update changed the compatibility surface"
            );
        }
        cell.glacial_sediment_net_m =
            cell.glacial_sediment_deposition_m -
            cell.glacial_sediment_production_m;
        cell.sediment_net_budget_m =
            cell.sediment_deposition_m -
            sediment_gross_mobilization_m(cell);
        stage.max_target_deposition_depth_m = std::max(
            stage.max_target_deposition_depth_m,
            deposition_depth_m[static_cast<std::size_t>(i)]
        );
        stage.post_transport_elevation_m_by_cell.push_back(cell.elevation_m);
    }
    maximum_sediment_interface_closure_residual_m(
        cells,
        "post glacial transport"
    );
    stage.transfer_count = static_cast<int>(stage.transfers.size());
    stage.source_cell_count = stage.transfer_count;
    stage.target_cell_count = static_cast<int>(target_cell_ids.size());
    stage.mass_balance_residual_km3 = std::abs(
        stage.production_volume_km3 - stage.deposition_volume_km3
    );
    stage.terrain_volume_change_residual_km3 =
        stage.mass_balance_residual_km3;
    stage.source_production_depth_m_by_cell = production_depth_m;
    validate_sediment_source_partition(
        cells,
        stage.source_production_depth_m_by_cell,
        stage.alluvium_entrainment_depth_m_by_cell,
        stage.bedrock_erosion_depth_m_by_cell,
        stage.alluvium_entrainment_volume_km3,
        stage.bedrock_erosion_volume_km3,
        "glacial"
    );
    return stage;
}

void derive_soils_biomes_resources(const Params& params, std::vector<Cell>& cells) {
    (void)params;
    const int n = static_cast<int>(cells.size());
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        Cell& cell = cells[i];
        const double relief = local_relief(cells, i);
        const double slope_penalty = clamp(relief / 1800.0, 0.0, 1.0);
        const double pet = std::max(1.0, (cell.temperature_c + 8.0) * 31.0);
        const double aridity = cell.precipitation_mm_y / pet;
        const double latitude_pet_factor = 0.66 + 0.34 *
            (1.0 - std::min(1.0, std::abs(cell.lat) * DEG / 90.0));
        int dry_season_months = 0;
        int wet_season_months = 0;
        const std::size_t climate_month_count = std::min(
            cell.temperature_monthly_c.size(), cell.precipitation_monthly_mm.size()
        );
        for (std::size_t month = 0; month < climate_month_count; ++month) {
            const double monthly_pet = std::max(0.0, cell.temperature_monthly_c[month] + 5.0) *
                3.1 * latitude_pet_factor;
            dry_season_months += cell.precipitation_monthly_mm[month] < monthly_pet * 0.35 ? 1 : 0;
            wet_season_months += cell.precipitation_monthly_mm[month] >= monthly_pet * 0.75 ? 1 : 0;
        }
        const bool warm_seasonal_climate =
            dry_season_months >= 2 && wet_season_months >= 3;
        const bool coast = has_ocean_neighbor(cells, i);
        if (cell.is_water) {
            cell.soil_type = 0;
            cell.soil_depth_m = 0.0;
            cell.fertility = 0.0;
            cell.biome = cell.water_body == 2 ? 1 : (cell.water_body == 3 ? 2 : 0);
            cell.resource = (coast || cell.water_body == 2) ? 8 : 0;
            cell.settlement_score = 0.0;
            continue;
        }
        const double litho_base = cell.lithology == 5 ? 0.78 : (cell.lithology == 1 ? 0.50 : (cell.lithology == 4 ? 0.44 : 0.58));
        const double climate_soil = clamp(cell.precipitation_mm_y / 1300.0, 0.0, 1.2) * clamp((cell.temperature_c + 8.0) / 30.0, 0.0, 1.1);
        cell.soil_depth_m = clamp(0.12 + 1.8 * climate_soil + (cell.is_river ? 0.85 : 0.0) - 1.5 * slope_penalty, 0.02, 5.0);
        cell.fertility = clamp(litho_base + 0.20 * climate_soil + (cell.is_river ? 0.24 : 0.0) -
            0.35 * slope_penalty - (aridity < 0.45 ? 0.28 : 0.0), 0.0, 1.0);
        if (cell.is_lake) {
            cell.water_body = aridity < 0.5 ? 5 : 4;
            cell.soil_type = aridity < 0.5 ? 10 : 9;
            cell.biome = aridity < 0.5 ? 10 : 2;
        } else if (cell.ice_thickness_m > 180.0 ||
            (cell.temperature_c < -8.0 && (std::abs(cell.lat) * DEG > 55.0 || cell.elevation_m > 1600.0))) {
            cell.soil_type = 8;
            cell.biome = 3;
        } else if (cell.elevation_m > 2800.0 && cell.temperature_c < 6.0) {
            cell.soil_type = 1;
            cell.biome = 14;
        } else if (cell.temperature_c < -2.0) {
            cell.soil_type = 8;
            cell.biome = 4;
        } else if (aridity < 0.32) {
            cell.soil_type = 4;
            cell.biome = cell.temperature_c < 11.0 ? 9 : 10;
        } else if (cell.temperature_c > 23.0 && cell.precipitation_mm_y > 2100.0) {
            cell.soil_type = 5;
            cell.biome = 13;
        } else if (cell.temperature_c > 21.0 && cell.precipitation_mm_y > 950.0) {
            cell.soil_type = 5;
            cell.biome = 12;
        } else if (cell.temperature_c > 18.0 && aridity < 0.82 && warm_seasonal_climate) {
            cell.soil_type = 4;
            cell.biome = 11;
        } else if (cell.temperature_c > 8.0 && cell.precipitation_mm_y > 760.0) {
            cell.soil_type = 6;
            cell.biome = 6;
        } else if (cell.temperature_c > 5.0 && aridity > 0.45) {
            cell.soil_type = 6;
            cell.biome = aridity > 1.1 ? 6 : 7;
        } else if (cell.temperature_c > -1.0 && cell.precipitation_mm_y > 420.0) {
            cell.soil_type = 7;
            cell.biome = 5;
        } else {
            cell.soil_type = 4;
            cell.biome = (cell.temperature_c < 2.0 && cell.precipitation_mm_y > 320.0 && aridity > 0.55) ?
                4 :
                (cell.temperature_c < 8.0 ? 9 : 10);
        }
        if (cell.is_river && relief < 450.0 && cell.precipitation_mm_y > 500.0) {
            cell.soil_type = 3;
            if (cell.biome != 13 && cell.biome != 3) {
                cell.biome = 15;
            }
        } else if (cell.lithology == 5 && cell.soil_type != 8) {
            cell.soil_type = 2;
        }
        if (cell.boundary_convergent > 0.38 && (cell.crust_type == 3 || cell.lithology == 5)) {
            cell.resource = 1;
        } else if (cell.crust_type == 4 && cell.crust_age_ma > 1800.0) {
            cell.resource = 2;
        } else if (cell.crust_type == 7 || cell.lithology == 4 || cell.lithology == 2 || cell.sediment_thickness_m > 1.4) {
            cell.resource = aridity < 0.45 ? 4 : 3;
        } else if (cell.is_river && cell.boundary_convergent > 0.16) {
            cell.resource = 5;
        } else if (cell.boundary_divergent > 0.42 || (cell.lithology == 5 && cell.temperature_c > 0.0)) {
            cell.resource = 6;
        } else if (cell.soil_type == 3 && cell.fertility > 0.62) {
            cell.resource = 7;
        } else {
            cell.resource = 0;
        }
        const double water_access = cell.is_river ? 1.0 : (cell.is_lake ? 0.85 : (coast ? 0.78 : clamp(cell.runoff_mm_y / 550.0, 0.0, 0.55)));
        const double climate_score = clamp(1.0 - std::abs(cell.temperature_c - 17.0) / 31.0, 0.0, 1.0);
        const double resource_score = cell.resource == 0 ? 0.0 : 0.18;
        const double hazard = clamp(cell.boundary_convergent * 0.28 + cell.boundary_transform * 0.18 +
            slope_penalty * 0.24 + clamp(cell.ice_thickness_m / 2200.0, 0.0, 1.0) * 0.22, 0.0, 0.65);
        cell.settlement_score = clamp(0.38 * water_access + 0.30 * cell.fertility + 0.18 * climate_score + resource_score - hazard, 0.0, 1.0);
        if (cell.biome == 3 || cell.biome == 4 || cell.biome == 14 || cell.biome == 0) {
            cell.settlement_score *= 0.18;
        }
    }
}

void derive_landforms(std::vector<Cell>& cells) {
    const int n = static_cast<int>(cells.size());
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        Cell& cell = cells[i];
        const double relief = local_relief(cells, i);
        const double pet = std::max(1.0, (cell.temperature_c + 8.0) * 31.0);
        const double aridity = cell.precipitation_mm_y / pet;
        const bool coast = has_ocean_neighbor(cells, i);
        const bool flows_to_water = cell.flow_to >= 0 && cells[cell.flow_to].is_water;
        const bool flows_to_lake = cell.flow_to >= 0 && cells[cell.flow_to].is_lake;
        const bool glacier_neighbor = has_glacier_neighbor(cells, i);

        if (cell.is_water) {
            if (glacier_neighbor && cell.water_depth_m < 1200.0 && (cell.water_body == 2 || cell.water_body == 3)) {
                cell.landform = 16;
            } else if (cell.boundary_convergent > 0.38 && cell.water_depth_m > 700.0) {
                cell.landform = 9;
            } else if (cell.water_body == 2) {
                cell.landform = 1;
            } else if (cell.water_body == 3) {
                cell.landform = 2;
            } else {
                cell.landform = 0;
            }
            continue;
        }

        if (cell.is_lake) {
            cell.landform = glacier_neighbor ? 19 : (cell.water_body == 5 ? 4 : 3);
        } else if (cell.is_closed_basin || cell.water_body == 5) {
            cell.landform = cell.water_body == 5 ? 4 : 3;
        } else if (cell.ice_thickness_m > 180.0 || cell.biome == 3) {
            cell.landform = 5;
        } else if (cell.glacial_erosion_m > 8.0 && relief > 320.0) {
            cell.landform = 17;
        } else if (glacier_neighbor && cell.sediment_thickness_m > 0.35 && cell.elevation_m > 120.0) {
            cell.landform = 18;
        } else if (cell.is_river && cell.elevation_m < 180.0 && (coast || flows_to_water || flows_to_lake) &&
            cell.sediment_thickness_m > 0.6) {
            cell.landform = 12;
        } else if (cell.is_river && aridity < 0.78 && relief > 420.0 && cell.sediment_thickness_m > 0.35) {
            cell.landform = 13;
        } else if (cell.is_river && relief < 360.0 && cell.sediment_thickness_m > 0.45) {
            cell.landform = 11;
        } else if (cell.is_river) {
            cell.landform = 10;
        } else if (cell.crust_type == 5 || (cell.elevation_m > 1600.0 && relief > 430.0)) {
            cell.landform = 6;
        } else if (cell.crust_type == 3 || (cell.lithology == 5 && cell.boundary_convergent > 0.22)) {
            cell.landform = 7;
        } else if (cell.crust_type == 6 || (cell.boundary_divergent > 0.36 && cell.elevation_m < 900.0)) {
            cell.landform = 8;
        } else if (coast && cell.elevation_m < 240.0 && relief < 300.0) {
            cell.landform = 14;
        } else {
            cell.landform = 15;
        }

        if (cell.landform == 12 || cell.landform == 11) {
            cell.soil_type = 3;
            cell.fertility = clamp(cell.fertility + (cell.landform == 12 ? 0.16 : 0.10), 0.0, 1.0);
            if (cell.precipitation_mm_y > 500.0 && cell.biome != 3) {
                cell.biome = 15;
            }
            if (cell.fertility > 0.64) {
                cell.resource = 7;
            }
            cell.settlement_score = clamp(cell.settlement_score + 0.08, 0.0, 1.0);
        } else if (cell.landform == 13) {
            cell.soil_type = cell.soil_type == 8 ? cell.soil_type : 4;
            if (cell.resource == 0 && cell.boundary_convergent > 0.10) {
                cell.resource = 5;
            }
            cell.settlement_score = clamp(cell.settlement_score + 0.03, 0.0, 1.0);
        } else if (cell.landform == 4) {
            cell.soil_type = 10;
            cell.resource = 4;
            cell.settlement_score *= 0.55;
        } else if (cell.landform == 17 || cell.landform == 18 || cell.landform == 19) {
            if (cell.landform != 19) {
                cell.soil_type = 8;
            }
            cell.settlement_score *= cell.landform == 19 ? 0.72 : 0.42;
        } else if (cell.landform == 14 && cell.settlement_score > 0.0) {
            cell.settlement_score = clamp(cell.settlement_score + 0.04, 0.0, 1.0);
        }
    }
}

double coastal_edge_length_km(const Params& params, const std::vector<Cell>& cells, int i) {
    double length_km = 0.0;
    for (int neighbor_id : cells[i].neighbors) {
        if (cells[neighbor_id].is_water) {
            length_km += neighbor_distance_m(params, cells[i], cells[neighbor_id]) / 1000.0;
        }
    }
    return length_km;
}

double coastal_sediment_supply(const std::vector<Cell>& cells, int i) {
    const Cell& cell = cells[i];
    double supply = 0.20 * clamp(cell.sediment_thickness_m / 3.0, 0.0, 1.0);
    if (cell.is_river) {
        supply += 0.34;
    }
    if (cell.landform == 12 || cell.landform == 11 || cell.landform == 14) {
        supply += 0.20;
    }
    for (int neighbor_id : cell.neighbors) {
        const Cell& neighbor = cells[neighbor_id];
        if (neighbor.is_river) {
            supply += 0.08;
        }
        if (neighbor.landform == 12 || neighbor.landform == 11) {
            supply += 0.07;
        }
        supply += 0.03 * clamp(neighbor.sediment_thickness_m / 3.0, 0.0, 1.0);
    }
    return clamp(supply, 0.0, 1.0);
}

double coastal_wave_energy(const std::vector<Cell>& cells, int i) {
    const Cell& cell = cells[i];
    const double current_strength = std::sqrt(
        cell.ocean_current_east * cell.ocean_current_east +
        cell.ocean_current_north * cell.ocean_current_north
    );
    double exposure = 0.0;
    for (int neighbor_id : cell.neighbors) {
        if (cells[neighbor_id].is_water) {
            exposure += 1.0;
        }
    }
    exposure /= std::max(1.0, static_cast<double>(cell.neighbors.size()));
    const double tectonic = clamp(cell.boundary_convergent + 0.5 * cell.boundary_transform, 0.0, 1.0);
    return clamp(0.22 + 0.40 * exposure + 0.24 * current_strength + 0.14 * tectonic, 0.0, 1.0);
}

int coastal_feature_type_for_cell(const std::vector<Cell>& cells, int i, double sediment_supply, double wave_energy) {
    const Cell& cell = cells[i];
    const double relief = local_relief(cells, i);
    if (cell.landform == 12 || (cell.is_river && sediment_supply > 0.58 && cell.elevation_m < 120.0)) {
        return 3;
    }
    if ((cell.landform == 11 || cell.biome == 15) && sediment_supply > 0.42 && wave_energy < 0.55) {
        return 4;
    }
    if (sediment_supply > 0.56 && wave_energy > 0.48 && cell.elevation_m < 90.0) {
        return 2;
    }
    if (sediment_supply > 0.30 && wave_energy > 0.34 && cell.elevation_m < 260.0) {
        return 1;
    }
    if (relief > 650.0 || (cell.elevation_m > 180.0 && wave_energy > 0.62 && sediment_supply < 0.45)) {
        return 5;
    }
    return 0;
}

double coastal_longshore_transport_index(const Cell& cell, double sediment_supply, double wave_energy) {
    const double current_strength = std::sqrt(
        cell.ocean_current_east * cell.ocean_current_east +
        cell.ocean_current_north * cell.ocean_current_north
    );
    return clamp(0.18 + 0.46 * wave_energy + 0.24 * current_strength + 0.12 * sediment_supply, 0.0, 1.0);
}

double coastal_migration_rate_m_y(int feature_type, double sediment_supply, double wave_energy, double longshore_transport) {
    double rate = 1.55 * sediment_supply - 1.05 * wave_energy + 0.28 * longshore_transport;
    if (feature_type == 3) {
        rate += 0.62;
    } else if (feature_type == 1 || feature_type == 2) {
        rate += 0.18 * sediment_supply - 0.24 * wave_energy;
    } else if (feature_type == 5) {
        rate -= 0.55;
    }
    return clamp(rate, -2.5, 4.0);
}

int shoreline_trend_for_feature(int feature_type, double sediment_supply, double wave_energy, double migration_rate) {
    if (feature_type == 3 && sediment_supply > 0.55 && migration_rate > 0.45) {
        return 4;
    }
    if ((feature_type == 1 || feature_type == 2) && wave_energy > 0.56 && migration_rate < 0.25) {
        return 3;
    }
    if (migration_rate > 0.34) {
        return 1;
    }
    if (migration_rate < -0.28 || (feature_type == 5 && wave_energy > 0.58)) {
        return 2;
    }
    return 0;
}

std::vector<CoastalFeature> generate_coastal_features(const Params& params, const std::vector<Cell>& cells) {
    std::vector<CoastalFeature> features;
    for (const Cell& cell : cells) {
        if (cell.is_water || !has_ocean_neighbor(cells, cell.id)) {
            continue;
        }
        const double length_km = coastal_edge_length_km(params, cells, cell.id);
        if (length_km <= 0.0) {
            continue;
        }
        const double sediment_supply = coastal_sediment_supply(cells, cell.id);
        const double wave_energy = coastal_wave_energy(cells, cell.id);
        CoastalFeature feature;
        feature.id = static_cast<int>(features.size());
        feature.cell_id = cell.id;
        feature.type = coastal_feature_type_for_cell(cells, cell.id, sediment_supply, wave_energy);
        feature.lat_deg = cell.lat * DEG;
        feature.lon_deg = cell.lon * DEG;
        feature.length_km = length_km;
        feature.sediment_supply_index = sediment_supply;
        feature.wave_energy_index = wave_energy;
        feature.progradation_index = clamp((sediment_supply + (feature.type == 3 ? 0.22 : 0.0)) / (0.55 + wave_energy), 0.0, 1.0);
        feature.longshore_transport_index = coastal_longshore_transport_index(cell, sediment_supply, wave_energy);
        feature.migration_rate_m_y = coastal_migration_rate_m_y(
            feature.type,
            sediment_supply,
            wave_energy,
            feature.longshore_transport_index
        );
        feature.shoreline_trend = shoreline_trend_for_feature(
            feature.type,
            sediment_supply,
            wave_energy,
            feature.migration_rate_m_y
        );
        features.push_back(feature);
    }
    return features;
}

int sedimentary_basin_type_for_cell(const std::vector<Cell>& cells, const Cell& cell) {
    if (cell.landform == 4 || cell.water_body == 5 || cell.resource == 4) {
        return 4;
    }
    if (cell.landform == 3 || cell.is_lake || cell.is_closed_basin) {
        return 3;
    }
    if (cell.landform == 12 || (cell.is_river && has_ocean_neighbor(cells, cell.id))) {
        return 5;
    }
    if (cell.crust_type == 6 || cell.boundary_divergent > 0.32) {
        return 0;
    }
    if (cell.boundary_convergent > 0.24 && cell.sediment_thickness_m > 0.30) {
        return 1;
    }
    return 2;
}

bool is_sedimentary_basin_cell(const std::vector<Cell>& cells, const Cell& cell) {
    if (cell.is_water || cell.basin_id < 0 || cell.basin_id >= static_cast<int>(cells.size())) {
        return false;
    }
    return cell.crust_type == 7 || cell.crust_type == 6 || cell.sediment_thickness_m > 0.55 ||
        cell.landform == 3 || cell.landform == 4 || cell.landform == 8 ||
        cell.landform == 11 || cell.landform == 12 || cell.landform == 14;
}

std::vector<SedimentaryBasin> generate_sedimentary_basins(const std::vector<Cell>& cells) {
    std::map<int, SedimentaryBasin> by_basin;
    std::map<int, std::map<int, int>> type_counts;
    std::map<int, std::map<int, int>> resource_counts;
    std::map<int, double> weighted_crust_age;
    std::map<int, int> active_cells;
    for (const Cell& cell : cells) {
        if (!is_sedimentary_basin_cell(cells, cell)) {
            continue;
        }
        SedimentaryBasin& basin = by_basin[cell.basin_id];
        basin.basin_id = cell.basin_id;
        basin.cell_count += 1;
        basin.area_km2 += cell.area_km2;
        basin.mean_sediment_thickness_m += cell.sediment_thickness_m * cell.area_km2;
        basin.max_sediment_thickness_m = std::max(basin.max_sediment_thickness_m, cell.sediment_thickness_m);
        const double subsidence = clamp(
            0.20 + 0.42 * cell.boundary_divergent + 0.22 * (cell.crust_type == 7 ? 1.0 : 0.0) +
                0.16 * clamp(cell.sediment_thickness_m / 3.5, 0.0, 1.0),
            0.0,
            1.0
        );
        basin.mean_subsidence_index += subsidence * cell.area_km2;
        weighted_crust_age[cell.basin_id] += cell.crust_age_ma * cell.area_km2;
        type_counts[cell.basin_id][sedimentary_basin_type_for_cell(cells, cell)]++;
        if (cell.resource != 0) {
            resource_counts[cell.basin_id][cell.resource]++;
        }
        if (cell.is_river || cell.is_lake || has_ocean_neighbor(cells, cell.id) || cell.sediment_thickness_m > 0.9) {
            active_cells[cell.basin_id] += 1;
        }
    }

    std::vector<SedimentaryBasin> basins;
    basins.reserve(by_basin.size());
    for (auto& [basin_id, basin] : by_basin) {
        if (basin.cell_count <= 0 || basin.area_km2 <= 0.0) {
            continue;
        }
        basin.mean_sediment_thickness_m /= basin.area_km2;
        basin.mean_subsidence_index /= basin.area_km2;
        const double mean_crust_age = weighted_crust_age[basin_id] / basin.area_km2;
        basin.depositional_age_ma = clamp(
            1.5 + 0.045 * mean_crust_age + 10.0 / (1.0 + basin.mean_sediment_thickness_m),
            0.1,
            320.0
        );
        basin.is_active = active_cells[basin_id] > 0;

        int best_type = 2;
        int best_type_count = -1;
        for (const auto& [type, count] : type_counts[basin_id]) {
            if (count > best_type_count) {
                best_type = type;
                best_type_count = count;
            }
        }
        basin.type = best_type;

        int best_resource = 0;
        int best_resource_count = -1;
        for (const auto& [resource, count] : resource_counts[basin_id]) {
            if (count > best_resource_count) {
                best_resource = resource;
                best_resource_count = count;
            }
        }
        basin.dominant_resource = best_resource_count < 0 ? 0 : best_resource;
        basins.push_back(basin);
    }
    std::sort(basins.begin(), basins.end(), [](const SedimentaryBasin& a, const SedimentaryBasin& b) {
        if (a.area_km2 == b.area_km2) {
            return a.basin_id < b.basin_id;
        }
        return a.area_km2 > b.area_km2;
    });
    for (int i = 0; i < static_cast<int>(basins.size()); ++i) {
        basins[static_cast<std::size_t>(i)].id = i;
    }
    return basins;
}

int sequence_phase_for_basin(const SedimentaryBasin& basin) {
    if (!basin.is_active && basin.mean_sediment_thickness_m < 0.35) {
        return 4;
    }
    if (basin.type == 4) {
        return 3;
    }
    if (basin.type == 5) {
        return 1;
    }
    if (basin.type == 2 && basin.is_active) {
        return 2;
    }
    return 0;
}

int stratigraphic_facies_for_layer(
    const SedimentaryBasin& basin,
    const Cell& representative,
    int layer_index,
    int layer_count
) {
    const double position = layer_count <= 1 ? 1.0 : static_cast<double>(layer_index) / static_cast<double>(layer_count - 1);
    if (representative.ice_thickness_m > 25.0 || representative.landform == 18 || representative.landform == 19) {
        return layer_index == layer_count - 1 ? 8 : 4;
    }
    if (basin.type == 0) {
        return position < 0.34 ? 0 : (position < 0.70 ? 4 : 1);
    }
    if (basin.type == 1) {
        return position < 0.42 ? 0 : (position < 0.76 ? 2 : 1);
    }
    if (basin.type == 2) {
        return position < 0.34 ? 7 : (position < 0.72 ? 6 : 3);
    }
    if (basin.type == 3) {
        return position < 0.72 ? 4 : 2;
    }
    if (basin.type == 4) {
        return position < 0.45 ? 4 : 5;
    }
    if (basin.type == 5) {
        return position < 0.35 ? 1 : (position < 0.76 ? 3 : 6);
    }
    return 2;
}

double facies_grain_size(int facies) {
    switch (facies) {
        case 0: return 0.78;
        case 1: return 0.58;
        case 2: return 0.22;
        case 3: return 0.48;
        case 4: return 0.18;
        case 5: return 0.06;
        case 6: return 0.34;
        case 7: return 0.16;
        case 8: return 0.66;
        default: return 0.35;
    }
}

double facies_organic_potential(int facies) {
    switch (facies) {
        case 3: return 0.58;
        case 4: return 0.64;
        case 7: return 0.50;
        case 2: return 0.32;
        case 6: return 0.24;
        default: return 0.12;
    }
}

double facies_seal_quality(int facies) {
    switch (facies) {
        case 5: return 0.92;
        case 4: return 0.76;
        case 7: return 0.70;
        case 2: return 0.64;
        case 6: return 0.42;
        default: return 0.22;
    }
}

std::vector<StratigraphicColumn> generate_stratigraphic_columns(
    const std::vector<Cell>& cells,
    const std::vector<SedimentaryBasin>& basins
) {
    std::map<int, int> representative_cell;
    std::map<int, double> representative_sediment;
    std::map<int, double> runoff_sum;
    std::map<int, double> area_sum;
    std::map<int, int> river_cell_count;
    for (const Cell& cell : cells) {
        if (cell.basin_id < 0) {
            continue;
        }
        const double previous = representative_sediment.count(cell.basin_id) > 0 ?
            representative_sediment[cell.basin_id] :
            -1.0;
        if (cell.sediment_thickness_m > previous) {
            representative_sediment[cell.basin_id] = cell.sediment_thickness_m;
            representative_cell[cell.basin_id] = cell.id;
        }
        runoff_sum[cell.basin_id] += cell.runoff_mm_y * cell.area_km2;
        area_sum[cell.basin_id] += cell.area_km2;
        if (cell.is_river) {
            river_cell_count[cell.basin_id] += 1;
        }
    }

    std::vector<StratigraphicColumn> columns;
    for (const SedimentaryBasin& basin : basins) {
        if (basin.cell_count <= 0) {
            continue;
        }
        StratigraphicColumn column;
        column.id = static_cast<int>(columns.size());
        column.basin_id = basin.basin_id;
        column.representative_cell_id = representative_cell.count(basin.basin_id) > 0 ?
            representative_cell[basin.basin_id] :
            basin.basin_id;
        if (column.representative_cell_id < 0 || column.representative_cell_id >= static_cast<int>(cells.size())) {
            column.representative_cell_id = basin.basin_id >= 0 && basin.basin_id < static_cast<int>(cells.size()) ?
                basin.basin_id :
                0;
        }
        const Cell& representative = cells[column.representative_cell_id];
        const double area = std::max(1.0, area_sum[basin.basin_id]);
        const double mean_runoff = runoff_sum[basin.basin_id] / area;
        const double river_fraction = static_cast<double>(river_cell_count[basin.basin_id]) /
            std::max(1.0, static_cast<double>(basin.cell_count));
        column.is_active = basin.is_active;
        column.sequence_phase = sequence_phase_for_basin(basin);
        column.total_thickness_m = std::max(
            0.05,
            0.55 * basin.max_sediment_thickness_m + 0.45 * basin.mean_sediment_thickness_m
        );
        column.depositional_span_ma = clamp(
            basin.depositional_age_ma * (0.45 + 0.45 * basin.mean_subsidence_index),
            0.05,
            std::max(0.05, basin.depositional_age_ma)
        );
        column.mean_subsidence_index = basin.mean_subsidence_index;
        column.sediment_flux_index = clamp(
            0.20 + 0.24 * clamp(mean_runoff / 1200.0, 0.0, 1.4) +
                0.28 * clamp(basin.mean_sediment_thickness_m / 4.0, 0.0, 1.3) +
                0.22 * river_fraction + 0.16 * basin.mean_subsidence_index,
            0.0,
            1.0
        );
        column.preservation_potential = clamp(
            0.22 + 0.44 * basin.mean_subsidence_index +
                0.20 * clamp(column.total_thickness_m / 4.0, 0.0, 1.0) +
                (basin.is_active ? 0.08 : -0.04) -
                0.10 * clamp(local_relief(cells, representative.id) / 900.0, 0.0, 1.0),
            0.0,
            1.0
        );

        const int layer_count = clamp(
            2 + static_cast<int>(column.total_thickness_m / 1.15) + (basin.is_active ? 1 : 0),
            2,
            5
        );
        const double top_age = basin.is_active ? 0.0 : clamp(basin.depositional_age_ma - column.depositional_span_ma, 0.0, basin.depositional_age_ma);
        double weight_sum = 0.0;
        std::vector<double> weights(static_cast<std::size_t>(layer_count), 1.0);
        for (int i = 0; i < layer_count; ++i) {
            const double upward = static_cast<double>(i + 1) / static_cast<double>(layer_count);
            weights[static_cast<std::size_t>(i)] = 0.70 + upward * (column.sequence_phase == 1 ? 0.70 : 0.30);
            if (column.sequence_phase == 2) {
                weights[static_cast<std::size_t>(i)] = 1.35 - 0.45 * upward;
            } else if (column.sequence_phase == 3) {
                weights[static_cast<std::size_t>(i)] = 0.95 - 0.18 * upward;
            }
            weight_sum += weights[static_cast<std::size_t>(i)];
        }

        std::map<int, double> facies_thickness;
        for (int i = 0; i < layer_count; ++i) {
            StratigraphicLayer layer;
            layer.index = i;
            layer.facies = stratigraphic_facies_for_layer(basin, representative, i, layer_count);
            layer.thickness_m = column.total_thickness_m * weights[static_cast<std::size_t>(i)] / std::max(0.001, weight_sum);
            const double base_fraction = static_cast<double>(i) / static_cast<double>(layer_count);
            const double top_fraction = static_cast<double>(i + 1) / static_cast<double>(layer_count);
            layer.age_base_ma = basin.depositional_age_ma - column.depositional_span_ma * base_fraction;
            layer.age_top_ma = basin.depositional_age_ma - column.depositional_span_ma * top_fraction;
            if (i == layer_count - 1) {
                layer.age_top_ma = top_age;
            }
            layer.grain_size_index = facies_grain_size(layer.facies);
            layer.organic_potential = clamp(
                facies_organic_potential(layer.facies) +
                    (basin.dominant_resource == 3 ? 0.20 : 0.0) +
                    0.10 * column.preservation_potential,
                0.0,
                1.0
            );
            layer.seal_quality = clamp(
                facies_seal_quality(layer.facies) +
                    (basin.dominant_resource == 4 ? 0.18 : 0.0),
                0.0,
                1.0
            );
            layer.reservoir_quality = clamp(
                0.18 + 0.68 * layer.grain_size_index + 0.14 * column.sediment_flux_index - 0.34 * layer.seal_quality,
                0.0,
                1.0
            );
            facies_thickness[layer.facies] += layer.thickness_m;
            column.layers.push_back(layer);
        }

        int dominant_facies = column.layers.empty() ? 2 : column.layers.front().facies;
        double dominant_thickness = -1.0;
        for (const auto& [facies, thickness] : facies_thickness) {
            if (thickness > dominant_thickness) {
                dominant_facies = facies;
                dominant_thickness = thickness;
            }
        }
        column.dominant_facies = dominant_facies;
        columns.push_back(column);
    }
    return columns;
}

int nearest_neighbor_ice_sheet(const std::vector<Cell>& cells, const Cell& cell) {
    int best_sheet = -1;
    double best_score = -1.0;
    for (int neighbor_id : cell.neighbors) {
        const Cell& neighbor = cells[neighbor_id];
        if (neighbor.ice_sheet_id >= 0) {
            const double score = neighbor.ice_thickness_m + 0.8 * neighbor.glacial_erosion_m;
            if (score > best_score) {
                best_score = score;
                best_sheet = neighbor.ice_sheet_id;
            }
        }
    }
    return best_sheet;
}

int retreat_stage_for_ice_sheet(const IceSheet& sheet) {
    if (sheet.cell_count <= 0) {
        return 4;
    }
    if (sheet.max_ice_thickness_m < 80.0) {
        return 4;
    }
    if (sheet.accumulation_area_fraction < 0.28) {
        return 2;
    }
    if (sheet.moraine_cell_count > sheet.cell_count / 4 && sheet.accumulation_area_fraction < 0.52) {
        return 3;
    }
    if (sheet.accumulation_area_fraction > 0.66 && sheet.mean_ice_thickness_m > 420.0) {
        return 0;
    }
    return 1;
}

std::vector<IceSheet> generate_ice_sheets(std::vector<Cell>& cells) {
    for (Cell& cell : cells) {
        cell.ice_sheet_id = -1;
        cell.moraine_deposition_m = 0.0;
        cell.deglaciation_age_ka = 0.0;
    }

    std::vector<IceSheet> sheets;
    const int n = static_cast<int>(cells.size());
    std::vector<char> visited(static_cast<std::size_t>(n), 0);
    for (int i = 0; i < n; ++i) {
        if (visited[static_cast<std::size_t>(i)] || cells[i].ice_thickness_m <= 25.0 || cells[i].is_water) {
            continue;
        }
        IceSheet sheet;
        sheet.id = static_cast<int>(sheets.size());
        std::queue<int> queue;
        queue.push(i);
        visited[static_cast<std::size_t>(i)] = 1;
        std::vector<double> elevations;
        while (!queue.empty()) {
            const int current = queue.front();
            queue.pop();
            Cell& cell = cells[current];
            cell.ice_sheet_id = sheet.id;
            sheet.cell_count += 1;
            sheet.area_km2 += cell.area_km2;
            sheet.mean_ice_thickness_m += cell.ice_thickness_m * cell.area_km2;
            sheet.max_ice_thickness_m = std::max(sheet.max_ice_thickness_m, cell.ice_thickness_m);
            sheet.mean_glacial_erosion_m += cell.glacial_erosion_m * cell.area_km2;
            sheet.mean_surface_mass_balance_m_y += cell.ice_surface_mass_balance_m_y * cell.area_km2;
            sheet.mean_basal_sliding_index += cell.basal_sliding_index * cell.area_km2;
            sheet.mean_ice_velocity_m_y += cell.ice_velocity_m_y * cell.area_km2;
            if (cell.precipitation_mm_y > 260.0 && cell.temperature_c < -1.0) {
                sheet.accumulation_area_fraction += cell.area_km2;
            }
            elevations.push_back(cell.elevation_m);
            for (int neighbor_id : cell.neighbors) {
                if (!visited[static_cast<std::size_t>(neighbor_id)] &&
                    !cells[neighbor_id].is_water &&
                    cells[neighbor_id].ice_thickness_m > 25.0) {
                    visited[static_cast<std::size_t>(neighbor_id)] = 1;
                    queue.push(neighbor_id);
                }
            }
        }
        if (sheet.area_km2 > 0.0) {
            sheet.mean_ice_thickness_m /= sheet.area_km2;
            sheet.mean_glacial_erosion_m /= sheet.area_km2;
            sheet.mean_surface_mass_balance_m_y /= sheet.area_km2;
            sheet.mean_basal_sliding_index /= sheet.area_km2;
            sheet.mean_ice_velocity_m_y /= sheet.area_km2;
            sheet.accumulation_area_fraction /= sheet.area_km2;
        }
        if (!elevations.empty()) {
            std::sort(elevations.begin(), elevations.end());
            sheet.equilibrium_line_altitude_m = elevations[static_cast<std::size_t>(0.42 * (elevations.size() - 1))];
        }
        sheets.push_back(sheet);
    }

    for (Cell& cell : cells) {
        if (cell.ice_sheet_id < 0 && (cell.landform == 18 || cell.landform == 17 || cell.landform == 19 ||
            (cell.ice_thickness_m <= 25.0 && has_glacier_neighbor(cells, cell.id, 25.0)))) {
            cell.ice_sheet_id = nearest_neighbor_ice_sheet(cells, cell);
        }
        if (cell.ice_sheet_id >= 0 && cell.ice_thickness_m <= 25.0) {
            const double cold_memory = clamp((-cell.temperature_c + 4.0) / 18.0, 0.0, 1.0);
            const double erosion_memory = clamp(cell.glacial_erosion_m / 18.0, 0.0, 1.0);
            const double sediment_memory = clamp(cell.sediment_thickness_m / 2.5, 0.0, 1.0);
            cell.deglaciation_age_ka = clamp(2.0 + 80.0 * cold_memory + 22.0 * erosion_memory, 0.0, 120.0);
            if (cell.landform == 18 || has_glacier_neighbor(cells, cell.id, 25.0)) {
                cell.moraine_deposition_m = clamp(0.18 + 1.4 * sediment_memory + 0.18 * local_relief(cells, cell.id) / 700.0, 0.0, 4.0);
            }
        }
    }

    std::vector<double> sheet_deglaciation_sum(sheets.size(), 0.0);
    std::vector<double> sheet_moraine_sum(sheets.size(), 0.0);
    std::vector<int> sheet_deglaciation_count(sheets.size(), 0);
    for (const Cell& cell : cells) {
        if (cell.ice_sheet_id < 0 || cell.ice_sheet_id >= static_cast<int>(sheets.size())) {
            continue;
        }
        IceSheet& sheet = sheets[static_cast<std::size_t>(cell.ice_sheet_id)];
        if (cell.moraine_deposition_m > 0.0 || cell.landform == 18) {
            sheet.moraine_cell_count += 1;
            sheet_moraine_sum[static_cast<std::size_t>(cell.ice_sheet_id)] += cell.moraine_deposition_m;
        }
        if (cell.deglaciation_age_ka > 0.0) {
            sheet_deglaciation_sum[static_cast<std::size_t>(cell.ice_sheet_id)] += cell.deglaciation_age_ka;
            sheet_deglaciation_count[static_cast<std::size_t>(cell.ice_sheet_id)] += 1;
        }
    }
    for (IceSheet& sheet : sheets) {
        if (sheet.moraine_cell_count > 0) {
            sheet.mean_moraine_deposition_m = sheet_moraine_sum[static_cast<std::size_t>(sheet.id)] /
                static_cast<double>(sheet.moraine_cell_count);
        }
        if (sheet_deglaciation_count[static_cast<std::size_t>(sheet.id)] > 0) {
            sheet.mean_deglaciation_age_ka = sheet_deglaciation_sum[static_cast<std::size_t>(sheet.id)] /
                static_cast<double>(sheet_deglaciation_count[static_cast<std::size_t>(sheet.id)]);
        }
        sheet.retreat_rate_m_y = clamp(
            4.0 + 42.0 * std::max(0.0, 0.45 - sheet.accumulation_area_fraction) +
                16.0 * sheet.mean_basal_sliding_index -
                22.0 * sheet.mean_surface_mass_balance_m_y,
            0.0,
            120.0
        );
        sheet.retreat_stage = retreat_stage_for_ice_sheet(sheet);
    }
    std::sort(sheets.begin(), sheets.end(), [](const IceSheet& a, const IceSheet& b) {
        if (a.area_km2 == b.area_km2) {
            return a.id < b.id;
        }
        return a.area_km2 > b.area_km2;
    });
    std::vector<int> remap(sheets.size(), -1);
    for (int new_id = 0; new_id < static_cast<int>(sheets.size()); ++new_id) {
        remap[static_cast<std::size_t>(sheets[static_cast<std::size_t>(new_id)].id)] = new_id;
        sheets[static_cast<std::size_t>(new_id)].id = new_id;
    }
    for (Cell& cell : cells) {
        if (cell.ice_sheet_id >= 0 && cell.ice_sheet_id < static_cast<int>(remap.size())) {
            cell.ice_sheet_id = remap[static_cast<std::size_t>(cell.ice_sheet_id)];
        }
    }
    return sheets;
}

}  // namespace magic_geo::detail
