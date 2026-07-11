#include "internal.hpp"

namespace magic_geo::detail {

int historical_era_for_year_bp(double year_bp) {
    if (year_bp > 2400.0) {
        return 0;
    }
    if (year_bp > 1300.0) {
        return 1;
    }
    if (year_bp > 450.0) {
        return 2;
    }
    return 3;
}

std::vector<HistoricalEra> default_historical_eras() {
    std::vector<HistoricalEra> eras(4);
    eras[0].id = 0;
    eras[0].dominant_process = 0;
    eras[0].start_year_bp = 4200.0;
    eras[0].end_year_bp = 2400.0;
    eras[1].id = 1;
    eras[1].dominant_process = 1;
    eras[1].start_year_bp = 2400.0;
    eras[1].end_year_bp = 1300.0;
    eras[2].id = 2;
    eras[2].dominant_process = 2;
    eras[2].start_year_bp = 1300.0;
    eras[2].end_year_bp = 450.0;
    eras[3].id = 3;
    eras[3].dominant_process = 3;
    eras[3].start_year_bp = 450.0;
    eras[3].end_year_bp = 0.0;
    return eras;
}

void add_historical_event(
    std::vector<HistoricalEvent>& events,
    int type,
    double year_bp,
    int region_id,
    int related_region_id,
    int culture_region_id,
    int related_culture_region_id,
    int language_region_id,
    int related_language_region_id,
    int cell_id,
    double pressure_index,
    double continuity_index
) {
    HistoricalEvent event;
    event.id = static_cast<int>(events.size());
    event.type = type;
    event.era_id = historical_era_for_year_bp(year_bp);
    event.year_bp = year_bp;
    event.region_id = region_id;
    event.related_region_id = related_region_id;
    event.culture_region_id = culture_region_id;
    event.related_culture_region_id = related_culture_region_id;
    event.language_region_id = language_region_id;
    event.related_language_region_id = related_language_region_id;
    event.cell_id = cell_id;
    event.pressure_index = clamp(pressure_index, 0.0, 1.0);
    event.continuity_index = clamp(continuity_index, 0.0, 1.0);
    events.push_back(event);
}

HistoricalLayers generate_historical_layers(
    const std::vector<Cell>& cells,
    const std::vector<Settlement>& settlements,
    const std::vector<PoliticalRegion>& political_regions,
    const std::vector<BorderSegment>& borders,
    const std::vector<TradeFlow>& trade_flows,
    const CulturalLayers& cultural_layers
) {
    (void)cells;
    HistoricalLayers history;
    history.eras = default_historical_eras();
    if (political_regions.empty() || cultural_layers.cultures.empty()) {
        return history;
    }

    std::map<int, int> region_to_culture;
    for (const CultureRegion& culture : cultural_layers.cultures) {
        region_to_culture[culture.homeland_region_id] = culture.id;
    }
    std::map<int, double> region_border_pressure;
    std::map<int, double> region_border_length;
    for (const BorderSegment& border : borders) {
        region_border_pressure[border.region_a] += border.barrier_score * border.length_km;
        region_border_pressure[border.region_b] += border.barrier_score * border.length_km;
        region_border_length[border.region_a] += border.length_km;
        region_border_length[border.region_b] += border.length_km;
    }
    std::map<int, double> region_trade_volume;
    for (const TradeFlow& flow : trade_flows) {
        if (flow.region_from >= 0) {
            region_trade_volume[flow.region_from] += flow.volume_index;
        }
        if (flow.region_to >= 0) {
            region_trade_volume[flow.region_to] += flow.volume_index;
        }
    }

    for (const PoliticalRegion& region : political_regions) {
        const int culture_id = region_to_culture.count(region.id) > 0 ? region_to_culture[region.id] : -1;
        const CultureRegion* culture = culture_id >= 0 ? &cultural_layers.cultures[static_cast<std::size_t>(culture_id)] : nullptr;
        const int language_id = culture != nullptr ? culture->language_region_id : -1;
        const int cell_id = region.capital_settlement_id >= 0 &&
                region.capital_settlement_id < static_cast<int>(settlements.size()) ?
            settlements[static_cast<std::size_t>(region.capital_settlement_id)].cell_id :
            -1;
        const double continuity = culture != nullptr ? culture->continuity_index : 0.5;
        const double pressure = clamp(
            0.18 + region.barrier_pressure * 0.32 +
                (region_border_length[region.id] > 0.0 ? region_border_pressure[region.id] / region_border_length[region.id] : 0.0) * 0.28 +
                (region.settlement_count <= 2 ? 0.18 : 0.0),
            0.0,
            1.0
        );
        const double foundation_year = clamp(380.0 + 0.72 * (culture != nullptr ? culture->estimated_age_years : 1800.0), 260.0, 3800.0);
        add_historical_event(
            history.events,
            0,
            foundation_year,
            region.id,
            -1,
            culture_id,
            -1,
            language_id,
            -1,
            cell_id,
            pressure,
            continuity
        );
        const double trade_contact = region_trade_volume[region.id] / (100.0 * std::max(1, region.settlement_count));
        if (pressure > 0.34 || trade_contact > 0.55 || region.route_count == 0) {
            add_historical_event(
                history.events,
                1,
                clamp(foundation_year * 0.48 + 180.0 * (region.id + 1), 180.0, 2100.0),
                region.id,
                -1,
                culture_id,
                -1,
                language_id,
                -1,
                cell_id,
                clamp(pressure + 0.18 * trade_contact, 0.0, 1.0),
                continuity
            );
        }
    }

    for (const CultureRegion& culture : cultural_layers.cultures) {
        if (culture.migration_pressure < 0.42 && culture.trade_contact_index < 0.28) {
            continue;
        }
        int cell_id = -1;
        if (!culture.settlement_ids.empty()) {
            const int settlement_id = culture.settlement_ids.front();
            if (settlement_id >= 0 && settlement_id < static_cast<int>(settlements.size())) {
                cell_id = settlements[static_cast<std::size_t>(settlement_id)].cell_id;
            }
        }
        int related_culture = -1;
        double best_contact = -1.0;
        for (const CultureRegion& other : cultural_layers.cultures) {
            if (other.id == culture.id || other.language_region_id != culture.language_region_id) {
                continue;
            }
            const double contact = 1.0 - std::abs(other.trade_contact_index - culture.trade_contact_index);
            if (contact > best_contact) {
                best_contact = contact;
                related_culture = other.id;
            }
        }
        add_historical_event(
            history.events,
            2,
            clamp(260.0 + 2100.0 * culture.migration_pressure + 220.0 * culture.id, 120.0, 2600.0),
            culture.homeland_region_id,
            -1,
            culture.id,
            related_culture,
            culture.language_region_id,
            -1,
            cell_id,
            culture.migration_pressure,
            culture.continuity_index
        );
    }

    for (const LanguageRegion& language : cultural_layers.language_regions) {
        if (language.parent_language_region_id < 0) {
            continue;
        }
        const int culture_id = language.culture_ids.empty() ? -1 : language.culture_ids.front();
        int cell_id = -1;
        int region_id = -1;
        if (culture_id >= 0) {
            const CultureRegion& culture = cultural_layers.cultures[static_cast<std::size_t>(culture_id)];
            region_id = culture.homeland_region_id;
            if (!culture.settlement_ids.empty()) {
                const int settlement_id = culture.settlement_ids.front();
                if (settlement_id >= 0 && settlement_id < static_cast<int>(settlements.size())) {
                    cell_id = settlements[static_cast<std::size_t>(settlement_id)].cell_id;
                }
            }
        }
        add_historical_event(
            history.events,
            3,
            clamp(language.divergence_age_years, 80.0, 3400.0),
            region_id,
            -1,
            culture_id,
            -1,
            language.id,
            language.parent_language_region_id,
            cell_id,
            language.change_rate,
            clamp(1.0 - language.change_rate, 0.0, 1.0)
        );
    }

    std::vector<TradeFlow> ranked_flows = trade_flows;
    std::sort(ranked_flows.begin(), ranked_flows.end(), [](const TradeFlow& a, const TradeFlow& b) {
        if (a.volume_index == b.volume_index) {
            return a.id < b.id;
        }
        return a.volume_index > b.volume_index;
    });
    const int trade_event_target = std::min(12, static_cast<int>(ranked_flows.size()));
    for (int i = 0; i < trade_event_target; ++i) {
        const TradeFlow& flow = ranked_flows[static_cast<std::size_t>(i)];
        int culture_id = region_to_culture.count(flow.region_from) > 0 ? region_to_culture[flow.region_from] : -1;
        int related_culture = region_to_culture.count(flow.region_to) > 0 ? region_to_culture[flow.region_to] : -1;
        int language_id = culture_id >= 0 ? cultural_layers.cultures[static_cast<std::size_t>(culture_id)].language_region_id : -1;
        int cell_id = flow.from >= 0 && flow.from < static_cast<int>(settlements.size()) ?
            settlements[static_cast<std::size_t>(flow.from)].cell_id :
            -1;
        add_historical_event(
            history.events,
            4,
            clamp(140.0 + 820.0 * (1.0 - clamp(flow.friction / 2.0, 0.0, 1.0)) + 42.0 * i, 70.0, 1300.0),
            flow.region_from,
            flow.region_to,
            culture_id,
            related_culture,
            language_id,
            -1,
            cell_id,
            clamp(flow.volume_index / 100.0, 0.0, 1.0),
            clamp(1.0 - flow.friction / 2.0, 0.0, 1.0)
        );
    }

    const int sacred_event_target = std::min(12, static_cast<int>(cultural_layers.sacred_areas.size()));
    for (int i = 0; i < sacred_event_target; ++i) {
        const SacredArea& site = cultural_layers.sacred_areas[static_cast<std::size_t>(i)];
        const CultureRegion* culture = site.culture_region_id >= 0 ?
            &cultural_layers.cultures[static_cast<std::size_t>(site.culture_region_id)] :
            nullptr;
        add_historical_event(
            history.events,
            5,
            clamp(220.0 + 1800.0 * site.significance + 35.0 * i, 120.0, 2400.0),
            culture != nullptr ? culture->homeland_region_id : -1,
            -1,
            site.culture_region_id,
            -1,
            site.language_region_id,
            -1,
            site.cell_id,
            site.significance,
            culture != nullptr ? culture->continuity_index : 0.5
        );
    }

    const int ruin_event_target = std::min(16, static_cast<int>(cultural_layers.ruins.size()));
    for (int i = 0; i < ruin_event_target; ++i) {
        const Ruin& ruin = cultural_layers.ruins[static_cast<std::size_t>(i)];
        const CultureRegion* culture = ruin.culture_region_id >= 0 ?
            &cultural_layers.cultures[static_cast<std::size_t>(ruin.culture_region_id)] :
            nullptr;
        add_historical_event(
            history.events,
            6,
            clamp(90.0 + 1500.0 * ruin.significance + 28.0 * i, 80.0, 1900.0),
            culture != nullptr ? culture->homeland_region_id : -1,
            -1,
            ruin.culture_region_id,
            -1,
            ruin.language_region_id,
            -1,
            ruin.cell_id,
            ruin.significance,
            ruin.preservation_score
        );
    }

    std::sort(history.events.begin(), history.events.end(), [](const HistoricalEvent& a, const HistoricalEvent& b) {
        if (a.year_bp == b.year_bp) {
            return a.type < b.type;
        }
        return a.year_bp > b.year_bp;
    });
    for (int i = 0; i < static_cast<int>(history.events.size()); ++i) {
        history.events[static_cast<std::size_t>(i)].id = i;
        history.events[static_cast<std::size_t>(i)].era_id = historical_era_for_year_bp(history.events[static_cast<std::size_t>(i)].year_bp);
    }
    for (const HistoricalEvent& event : history.events) {
        if (event.era_id < 0 || event.era_id >= static_cast<int>(history.eras.size())) {
            continue;
        }
        HistoricalEra& era = history.eras[static_cast<std::size_t>(event.era_id)];
        era.event_count += 1;
        era.mean_instability += event.pressure_index;
        era.mean_connectivity += event.continuity_index;
        if (event.type == 0 || event.type == 1) {
            era.state_event_count += 1;
        } else if (event.type == 2) {
            era.migration_event_count += 1;
        } else if (event.type == 3) {
            era.language_event_count += 1;
        }
    }
    for (HistoricalEra& era : history.eras) {
        if (era.event_count > 0) {
            era.mean_instability /= static_cast<double>(era.event_count);
            era.mean_connectivity /= static_cast<double>(era.event_count);
        }
    }
    return history;
}

std::map<int, int> region_to_culture_map(const CulturalLayers& cultural_layers) {
    std::map<int, int> region_to_culture;
    for (const CultureRegion& culture : cultural_layers.cultures) {
        if (culture.homeland_region_id >= 0) {
            region_to_culture[culture.homeland_region_id] = culture.id;
        }
    }
    return region_to_culture;
}

double population_water_security(const std::vector<Cell>& cells, const Cell& cell) {
    double water = clamp(cell.runoff_mm_y / 1300.0, 0.0, 0.70);
    if (cell.is_river) {
        water += 0.24;
    }
    if (cell.is_lake || cell.water_body == 4) {
        water += 0.18;
    }
    if (has_ocean_neighbor(cells, cell.id)) {
        water += 0.08;
    }
    if (cell.water_body == 5 || cell.soil_type == 10) {
        water -= 0.18;
    }
    return clamp(water, 0.0, 1.0);
}

std::vector<PopulationRegion> generate_population_regions(
    const std::vector<Cell>& cells,
    const std::vector<PoliticalRegion>& political_regions,
    const CulturalLayers& cultural_layers
) {
    const std::map<int, int> region_to_culture = region_to_culture_map(cultural_layers);
    std::vector<PopulationRegion> populations;
    populations.reserve(political_regions.size());
    for (const PoliticalRegion& region : political_regions) {
        PopulationRegion pop;
        pop.id = static_cast<int>(populations.size());
        pop.region_id = region.id;
        pop.settlement_count = region.settlement_count;
        if (region_to_culture.count(region.id) > 0) {
            pop.culture_region_id = region_to_culture.at(region.id);
            const CultureRegion& culture = cultural_layers.cultures[static_cast<std::size_t>(pop.culture_region_id)];
            pop.language_region_id = culture.language_region_id;
            pop.migration_balance = clamp(0.5 - culture.migration_pressure, -1.0, 1.0);
        }

        double area = 0.0;
        double fertility_sum = 0.0;
        double water_sum = 0.0;
        double climate_sum = 0.0;
        double hazard_sum = 0.0;
        double urban_site_sum = 0.0;
        int cell_count = 0;
        for (const Cell& cell : cells) {
            if (cell.is_water || cell.political_region_id != region.id) {
                continue;
            }
            const double water = population_water_security(cells, cell);
            const double climate = clamp(
                1.0 - std::abs(cell.temperature_c - 17.0) / 42.0 -
                    std::max(0.0, 360.0 - cell.precipitation_mm_y) / 1400.0 -
                    cell.ice_thickness_m / 2800.0,
                0.0,
                1.0
            );
            const double hazard = clamp(
                0.35 * cell.boundary_convergent + 0.25 * cell.boundary_transform +
                    local_relief(cells, cell.id) / 4200.0 + cell.ice_thickness_m / 3200.0,
                0.0,
                1.0
            );
            area += cell.area_km2;
            fertility_sum += cell.fertility * cell.area_km2;
            water_sum += water * cell.area_km2;
            climate_sum += climate * cell.area_km2;
            hazard_sum += hazard * cell.area_km2;
            urban_site_sum += cell.settlement_score * cell.area_km2;
            cell_count++;
        }
        if (area <= 0.0 || cell_count == 0) {
            populations.push_back(pop);
            continue;
        }
        const double fertility = fertility_sum / area;
        const double water = water_sum / area;
        const double climate = climate_sum / area;
        const double hazard = hazard_sum / area;
        const double site_strength = urban_site_sum / area;
        const double route_factor = clamp(static_cast<double>(region.route_count) / std::max(1.0, static_cast<double>(region.settlement_count)), 0.0, 1.0);
        const double density_capacity = clamp(1.5 + 64.0 * fertility * water * climate + 12.0 * site_strength, 0.2, 90.0);
        pop.agricultural_capacity_index = clamp(fertility * climate * (0.55 + 0.45 * water), 0.0, 1.0);
        pop.water_security_index = water;
        pop.hazard_mortality_index = hazard;
        pop.urbanization_fraction = clamp(0.04 + 0.025 * region.settlement_count + 0.16 * route_factor + 0.12 * site_strength, 0.02, 0.62);
        pop.carrying_capacity = area * density_capacity;
        const double continuity = pop.culture_region_id >= 0 ?
            cultural_layers.cultures[static_cast<std::size_t>(pop.culture_region_id)].continuity_index :
            0.5;
        const double occupancy = clamp(0.22 + 0.30 * continuity + 0.26 * pop.urbanization_fraction + 0.18 * route_factor - 0.18 * hazard, 0.05, 0.93);
        pop.estimated_population = pop.carrying_capacity * occupancy;
        pop.population_pressure = pop.carrying_capacity > 0.0 ? clamp(pop.estimated_population / pop.carrying_capacity, 0.0, 1.4) : 0.0;
        pop.growth_rate_per_year = clamp(
            0.0015 + 0.0065 * pop.agricultural_capacity_index + 0.0025 * pop.water_security_index -
                0.0030 * pop.population_pressure - 0.0045 * hazard,
            -0.012,
            0.018
        );
        populations.push_back(pop);
    }
    return populations;
}

std::vector<ConflictRecord> generate_conflicts(
    const std::vector<Cell>& cells,
    const std::vector<PoliticalRegion>& political_regions,
    const std::vector<BorderSegment>& borders,
    const std::vector<TradeFlow>& trade_flows,
    const CulturalLayers& cultural_layers,
    const std::vector<PopulationRegion>& population_regions
) {
    const std::map<int, int> region_to_culture = region_to_culture_map(cultural_layers);
    std::map<int, const PopulationRegion*> population_by_region;
    for (const PopulationRegion& population : population_regions) {
        population_by_region[population.region_id] = &population;
    }
    std::map<int, const PoliticalRegion*> region_by_id;
    for (const PoliticalRegion& region : political_regions) {
        region_by_id[region.id] = &region;
    }
    std::map<std::pair<int, int>, double> trade_chokepoint_by_pair;
    for (const TradeFlow& flow : trade_flows) {
        if (!flow.interregional || flow.region_from < 0 || flow.region_to < 0) {
            continue;
        }
        const std::pair<int, int> key = std::minmax(flow.region_from, flow.region_to);
        trade_chokepoint_by_pair[key] += flow.volume_index * flow.friction / 100.0;
    }

    struct Candidate {
        ConflictRecord record;
        double score = 0.0;
    };
    std::map<std::pair<int, int>, Candidate> best_by_pair;
    for (const BorderSegment& border : borders) {
        if (border.region_a < 0 || border.region_b < 0 || border.cell_a < 0 || border.cell_b < 0) {
            continue;
        }
        const Cell& a = cells[static_cast<std::size_t>(border.cell_a)];
        const Cell& b = cells[static_cast<std::size_t>(border.cell_b)];
        const std::pair<int, int> pair = std::minmax(border.region_a, border.region_b);
        const PopulationRegion* pop_a = population_by_region.count(pair.first) > 0 ? population_by_region[pair.first] : nullptr;
        const PopulationRegion* pop_b = population_by_region.count(pair.second) > 0 ? population_by_region[pair.second] : nullptr;
        const PoliticalRegion* region_a = region_by_id.count(pair.first) > 0 ? region_by_id[pair.first] : nullptr;
        const PoliticalRegion* region_b = region_by_id.count(pair.second) > 0 ? region_by_id[pair.second] : nullptr;
        const double pressure = 0.5 * (
            (pop_a != nullptr ? pop_a->population_pressure : 0.35) +
            (pop_b != nullptr ? pop_b->population_pressure : 0.35)
        );
        const double resource_pressure = (a.resource != 0 || b.resource != 0) ? 0.72 : 0.0;
        const double water_a = population_water_security(cells, a);
        const double water_b = population_water_security(cells, b);
        const double water_stress = clamp(1.0 - 0.5 * (water_a + water_b), 0.0, 1.0);
        const double fertility_pressure = clamp(0.5 * (a.fertility + b.fertility), 0.0, 1.0);
        const double trade_chokepoint = clamp(
            trade_chokepoint_by_pair[pair] * 0.24 +
                (border.type == 1 || border.type == 2 || border.type == 5 ? 0.34 : 0.0),
            0.0,
            1.0
        );
        double cause_score = water_stress;
        int cause = 0;
        if (fertility_pressure > cause_score) {
            cause_score = fertility_pressure;
            cause = 1;
        }
        if (resource_pressure > cause_score) {
            cause_score = resource_pressure;
            cause = 2;
        }
        if (trade_chokepoint > cause_score) {
            cause_score = trade_chokepoint;
            cause = 3;
        }
        if (border.barrier_score > cause_score && border.type != 0) {
            cause = 4;
        }
        const double intensity = clamp(
            0.12 + 0.28 * pressure + 0.22 * border.barrier_score +
                0.18 * resource_pressure + 0.16 * water_stress + 0.18 * trade_chokepoint,
            0.0,
            1.0
        );
        const double score = intensity + 0.08 * fertility_pressure;
        if (score < 0.24) {
            continue;
        }
        Candidate candidate;
        candidate.score = score;
        candidate.record.region_a = pair.first;
        candidate.record.region_b = pair.second;
        candidate.record.culture_a = region_to_culture.count(pair.first) > 0 ? region_to_culture.at(pair.first) : -1;
        candidate.record.culture_b = region_to_culture.count(pair.second) > 0 ? region_to_culture.at(pair.second) : -1;
        candidate.record.cause = cause;
        candidate.record.contested_cell_id = intensity >= 0.5 ? border.cell_a : border.cell_b;
        candidate.record.intensity = intensity;
        candidate.record.resource_pressure = resource_pressure;
        candidate.record.water_stress = water_stress;
        candidate.record.trade_chokepoint_index = trade_chokepoint;
        const double start_year = clamp(160.0 + 1850.0 * intensity + 17.0 * static_cast<double>(best_by_pair.size() + 1), 90.0, 2600.0);
        const double duration = clamp(12.0 + 90.0 * intensity + 18.0 * trade_chokepoint, 8.0, 160.0);
        candidate.record.start_year_bp = start_year;
        candidate.record.end_year_bp = std::max(0.0, start_year - duration);
        candidate.record.war_duration_years = candidate.record.start_year_bp - candidate.record.end_year_bp;
        candidate.record.era_id = historical_era_for_year_bp(start_year);
        const double population_a = pop_a != nullptr ? pop_a->estimated_population : 0.0;
        const double population_b = pop_b != nullptr ? pop_b->estimated_population : 0.0;
        const double average_population = 0.5 * (
            population_a +
            population_b
        );
        const double total_population = population_a + population_b;
        const double route_factor_a = region_a != nullptr ?
            clamp(static_cast<double>(region_a->route_count) / std::max(1.0, static_cast<double>(region_a->settlement_count)), 0.0, 1.0) :
            0.0;
        const double route_factor_b = region_b != nullptr ?
            clamp(static_cast<double>(region_b->route_count) / std::max(1.0, static_cast<double>(region_b->settlement_count)), 0.0, 1.0) :
            0.0;
        const double urban_a = pop_a != nullptr ? pop_a->urbanization_fraction : 0.05;
        const double urban_b = pop_b != nullptr ? pop_b->urbanization_fraction : 0.05;
        candidate.record.logistics_strain_index = clamp(
            0.24 * border.barrier_score + 0.22 * water_stress + 0.20 * trade_chokepoint +
                0.18 * intensity + (border.type == 1 || border.type == 2 ? 0.10 : 0.0),
            0.0,
            1.0
        );
        const double mobilization_rate = clamp(
            0.012 + 0.070 * intensity + 0.022 * trade_chokepoint + 0.015 * pressure -
                0.018 * candidate.record.logistics_strain_index,
            0.004,
            0.16
        );
        candidate.record.region_a_force_estimate = std::max(0.0, population_a * mobilization_rate *
            (0.72 + 0.28 * urban_a + 0.14 * route_factor_a - 0.22 * candidate.record.logistics_strain_index));
        candidate.record.region_b_force_estimate = std::max(0.0, population_b * mobilization_rate *
            (0.72 + 0.28 * urban_b + 0.14 * route_factor_b - 0.22 * candidate.record.logistics_strain_index));
        candidate.record.mobilized_population =
            candidate.record.region_a_force_estimate + candidate.record.region_b_force_estimate;
        candidate.record.estimated_casualties = average_population * intensity * (0.006 + 0.025 * intensity);
        candidate.record.casualty_rate = total_population > 0.0 ?
            clamp(candidate.record.estimated_casualties / total_population, 0.0, 1.0) :
            0.0;
        candidate.record.economic_disruption_index = clamp(
            0.18 * intensity + 0.18 * candidate.record.logistics_strain_index +
                0.18 * trade_chokepoint + 0.16 * resource_pressure +
                0.14 * water_stress + 0.16 * (candidate.record.war_duration_years / 160.0),
            0.0,
            1.0
        );
        const double effectiveness_a = candidate.record.region_a_force_estimate *
            (1.0 + 0.26 * route_factor_a + 0.18 * urban_a - 0.38 * candidate.record.logistics_strain_index);
        const double effectiveness_b = candidate.record.region_b_force_estimate *
            (1.0 + 0.26 * route_factor_b + 0.18 * urban_b - 0.38 * candidate.record.logistics_strain_index);
        const double force_scale = std::max(1.0, candidate.record.mobilized_population);
        const double advantage = (effectiveness_a - effectiveness_b) / force_scale;
        if (candidate.record.logistics_strain_index > 0.72 && intensity > 0.58) {
            candidate.record.outcome = 4;
        } else if (std::abs(advantage) < 0.08) {
            candidate.record.outcome = 0;
        } else if (std::abs(advantage) < 0.20 && trade_chokepoint > 0.38) {
            candidate.record.outcome = 3;
        } else {
            candidate.record.outcome = advantage > 0.0 ? 1 : 2;
        }
        if (best_by_pair.count(pair) == 0 || score > best_by_pair[pair].score) {
            best_by_pair[pair] = candidate;
        }
    }

    std::vector<Candidate> candidates;
    candidates.reserve(best_by_pair.size());
    for (const auto& [_, candidate] : best_by_pair) {
        candidates.push_back(candidate);
    }
    std::sort(candidates.begin(), candidates.end(), [](const Candidate& a, const Candidate& b) {
        if (a.score == b.score) {
            return std::make_pair(a.record.region_a, a.record.region_b) < std::make_pair(b.record.region_a, b.record.region_b);
        }
        return a.score > b.score;
    });
    const int target = std::min(static_cast<int>(candidates.size()), std::max(0, static_cast<int>(political_regions.size()) * 2));
    std::vector<ConflictRecord> conflicts;
    conflicts.reserve(target);
    for (int i = 0; i < target; ++i) {
        ConflictRecord conflict = candidates[static_cast<std::size_t>(i)].record;
        conflict.id = static_cast<int>(conflicts.size());
        conflicts.push_back(conflict);
    }
    return conflicts;
}

std::vector<DynastyRecord> generate_dynasties(
    const std::vector<PoliticalRegion>& political_regions,
    const CulturalLayers& cultural_layers,
    const HistoricalLayers& historical_layers,
    const std::vector<PopulationRegion>& population_regions,
    const std::vector<ConflictRecord>& conflicts
) {
    const std::map<int, int> region_to_culture = region_to_culture_map(cultural_layers);
    std::map<int, const PopulationRegion*> population_by_region;
    for (const PopulationRegion& population : population_regions) {
        population_by_region[population.region_id] = &population;
    }
    std::map<int, double> conflict_pressure_by_region;
    for (const ConflictRecord& conflict : conflicts) {
        conflict_pressure_by_region[conflict.region_a] += conflict.intensity;
        conflict_pressure_by_region[conflict.region_b] += conflict.intensity;
    }
    std::map<int, int> founding_event_by_region;
    std::map<int, double> founding_year_by_region;
    for (const HistoricalEvent& event : historical_layers.events) {
        if (event.type != 0 || event.region_id < 0) {
            continue;
        }
        if (founding_event_by_region.count(event.region_id) == 0 || event.year_bp > founding_year_by_region[event.region_id]) {
            founding_event_by_region[event.region_id] = event.id;
            founding_year_by_region[event.region_id] = event.year_bp;
        }
    }

    std::vector<DynastyRecord> dynasties;
    for (const PoliticalRegion& region : political_regions) {
        const int culture_id = region_to_culture.count(region.id) > 0 ? region_to_culture.at(region.id) : -1;
        const int language_id = culture_id >= 0 ?
            cultural_layers.cultures[static_cast<std::size_t>(culture_id)].language_region_id :
            -1;
        const double continuity = culture_id >= 0 ?
            cultural_layers.cultures[static_cast<std::size_t>(culture_id)].continuity_index :
            0.5;
        const PopulationRegion* population = population_by_region.count(region.id) > 0 ? population_by_region[region.id] : nullptr;
        const double population_pressure = population != nullptr ? population->population_pressure : 0.4;
        const double conflict_pressure = clamp(conflict_pressure_by_region[region.id] / 3.0, 0.0, 1.0);
        const double base_succession_pressure = clamp(
            0.18 + 0.34 * population_pressure + 0.36 * conflict_pressure +
                (region.route_count == 0 ? 0.10 : 0.0) - 0.24 * continuity,
            0.0,
            1.0
        );
        const int dynasty_count = 1 + (base_succession_pressure > 0.36 ? 1 : 0) + (base_succession_pressure > 0.66 ? 1 : 0);
        const double founding_year = founding_year_by_region.count(region.id) > 0 ?
            founding_year_by_region[region.id] :
            clamp(620.0 + 240.0 * static_cast<double>(region.id + 1), 260.0, 3200.0);
        const int founding_event_id = founding_event_by_region.count(region.id) > 0 ? founding_event_by_region[region.id] : -1;
        int parent_id = -1;
        int founder_id = -1;
        for (int i = 0; i < dynasty_count; ++i) {
            DynastyRecord dynasty;
            dynasty.id = static_cast<int>(dynasties.size());
            if (i == 0) {
                founder_id = dynasty.id;
            }
            dynasty.region_id = region.id;
            dynasty.culture_region_id = culture_id;
            dynasty.language_region_id = language_id;
            dynasty.parent_dynasty_id = parent_id;
            dynasty.founder_dynasty_id = founder_id;
            dynasty.founding_event_id = i == 0 ? founding_event_id : -1;
            dynasty.lineage_depth = i;
            dynasty.start_year_bp = founding_year * (1.0 - static_cast<double>(i) / static_cast<double>(dynasty_count));
            dynasty.end_year_bp = i == dynasty_count - 1 ?
                0.0 :
                founding_year * (1.0 - static_cast<double>(i + 1) / static_cast<double>(dynasty_count));
            dynasty.duration_years = std::max(0.0, dynasty.start_year_bp - dynasty.end_year_bp);
            dynasty.succession_pressure = clamp(base_succession_pressure + 0.10 * static_cast<double>(i), 0.0, 1.0);
            dynasty.legitimacy_index = clamp(
                0.34 + 0.42 * continuity + 0.18 * region.mean_settlement_score -
                    0.22 * dynasty.succession_pressure - 0.10 * conflict_pressure,
                0.0,
                1.0
            );
            dynasty.dynastic_continuity_index = clamp(
                0.26 + 0.34 * dynasty.legitimacy_index +
                    0.22 * (dynasty.duration_years / std::max(1.0, founding_year)) +
                    0.18 * (1.0 - dynasty.succession_pressure),
                0.0,
                1.0
            );
            if (i == dynasty_count - 1) {
                dynasty.collapse_reason = 0;
            } else if (conflict_pressure > 0.45) {
                dynasty.collapse_reason = 5;
            } else if (population_pressure > 0.68) {
                dynasty.collapse_reason = 4;
            } else if (region.dominant_resource != 0 && region.type == 3) {
                dynasty.collapse_reason = 2;
            } else if (region.route_count == 0) {
                dynasty.collapse_reason = 3;
            } else {
                dynasty.collapse_reason = 1;
            }
            dynasties.push_back(dynasty);
            parent_id = dynasty.id;
        }
    }
    for (DynastyRecord& dynasty : dynasties) {
        if (dynasty.parent_dynasty_id < 0 ||
            dynasty.parent_dynasty_id >= static_cast<int>(dynasties.size())) {
            continue;
        }
        DynastyRecord& parent = dynasties[static_cast<std::size_t>(dynasty.parent_dynasty_id)];
        parent.child_dynasty_ids.push_back(dynasty.id);
        parent.child_dynasty_count = static_cast<int>(parent.child_dynasty_ids.size());
        if (parent.successor_dynasty_id < 0 ||
            dynasty.start_year_bp > dynasties[static_cast<std::size_t>(parent.successor_dynasty_id)].start_year_bp) {
            parent.successor_dynasty_id = dynasty.id;
        }
    }
    return dynasties;
}

std::vector<int> sampled_ids(const std::vector<int>& values, int limit) {
    if (static_cast<int>(values.size()) <= limit) {
        return values;
    }
    std::vector<int> sampled;
    sampled.reserve(static_cast<std::size_t>(limit));
    const double stride = static_cast<double>(values.size()) / static_cast<double>(limit);
    for (int i = 0; i < limit; ++i) {
        sampled.push_back(values[static_cast<std::size_t>(std::floor(stride * static_cast<double>(i)))]);
    }
    return sampled;
}

std::vector<TerritorialSnapshot> generate_territorial_snapshots(
    const Params& params,
    const std::vector<Cell>& cells,
    const std::vector<PoliticalRegion>& political_regions,
    const std::vector<Settlement>& settlements,
    const CulturalLayers& cultural_layers,
    const HistoricalLayers& historical_layers,
    const std::vector<PopulationRegion>& population_regions,
    const std::vector<ConflictRecord>& conflicts
) {
    const std::map<int, int> region_to_culture = region_to_culture_map(cultural_layers);
    std::map<int, const PopulationRegion*> population_by_region;
    for (const PopulationRegion& population : population_regions) {
        population_by_region[population.region_id] = &population;
    }
    std::map<std::pair<int, int>, double> conflict_by_region_era;
    for (const ConflictRecord& conflict : conflicts) {
        conflict_by_region_era[{conflict.region_a, conflict.era_id}] += conflict.intensity;
        conflict_by_region_era[{conflict.region_b, conflict.era_id}] += conflict.intensity;
    }

    std::vector<SnapshotRegion> base_regions(political_regions.size());
    std::vector<Vec3> center_weight(political_regions.size(), Vec3{0.0, 0.0, 0.0});
    std::vector<double> lat_weight(political_regions.size(), 0.0);
    std::vector<double> lon_weight(political_regions.size(), 0.0);
    std::vector<double> area_weight(political_regions.size(), 0.0);
    double land_area = 0.0;
    for (const PoliticalRegion& region : political_regions) {
        SnapshotRegion& snapshot_region = base_regions[static_cast<std::size_t>(region.id)];
        snapshot_region.region_id = region.id;
        snapshot_region.capital_settlement_id = region.capital_settlement_id;
        if (region_to_culture.count(region.id) > 0) {
            snapshot_region.culture_region_id = region_to_culture.at(region.id);
            const CultureRegion& culture = cultural_layers.cultures[static_cast<std::size_t>(snapshot_region.culture_region_id)];
            snapshot_region.language_region_id = culture.language_region_id;
        }
    }
    for (const Cell& cell : cells) {
        if (cell.is_water) {
            continue;
        }
        land_area += cell.area_km2;
        const int region_id = cell.political_region_id;
        if (region_id < 0 || region_id >= static_cast<int>(base_regions.size())) {
            continue;
        }
        SnapshotRegion& snapshot_region = base_regions[static_cast<std::size_t>(region_id)];
        snapshot_region.cell_count += 1;
        snapshot_region.area_km2 += cell.area_km2;
        center_weight[static_cast<std::size_t>(region_id)] = add(
            center_weight[static_cast<std::size_t>(region_id)],
            mul(cell.p, cell.area_km2)
        );
        lat_weight[static_cast<std::size_t>(region_id)] += cell.lat * DEG * cell.area_km2;
        lon_weight[static_cast<std::size_t>(region_id)] += cell.lon * DEG * cell.area_km2;
        area_weight[static_cast<std::size_t>(region_id)] += cell.area_km2;
        bool boundary = false;
        for (int neighbor_id : cell.neighbors) {
            const Cell& neighbor = cells[static_cast<std::size_t>(neighbor_id)];
            if (neighbor.is_water || neighbor.political_region_id != region_id) {
                boundary = true;
                break;
            }
        }
        if (boundary) {
            snapshot_region.boundary_cell_ids.push_back(cell.id);
        }
    }
    for (SnapshotRegion& snapshot_region : base_regions) {
        const int region_id = snapshot_region.region_id;
        if (region_id >= 0 && region_id < static_cast<int>(area_weight.size()) && area_weight[static_cast<std::size_t>(region_id)] > 0.0) {
            snapshot_region.centroid_lat_deg = lat_weight[static_cast<std::size_t>(region_id)] / area_weight[static_cast<std::size_t>(region_id)];
            snapshot_region.centroid_lon_deg = lon_weight[static_cast<std::size_t>(region_id)] / area_weight[static_cast<std::size_t>(region_id)];
        } else if (region_id >= 0 && region_id < static_cast<int>(political_regions.size())) {
            const PoliticalRegion& region = political_regions[static_cast<std::size_t>(region_id)];
            if (region.capital_settlement_id >= 0 && region.capital_settlement_id < static_cast<int>(settlements.size())) {
                const Cell& capital_cell = cells[static_cast<std::size_t>(settlements[static_cast<std::size_t>(region.capital_settlement_id)].cell_id)];
                snapshot_region.centroid_lat_deg = capital_cell.lat * DEG;
                snapshot_region.centroid_lon_deg = capital_cell.lon * DEG;
            }
        }
        if (region_id >= 0 && region_id < static_cast<int>(center_weight.size())) {
            const Vec3 weighted_center = center_weight[static_cast<std::size_t>(region_id)];
            snapshot_region.boundary_ring = watershed_boundary_ring(cells, snapshot_region.boundary_cell_ids, weighted_center, 64);
            snapshot_region.boundary_perimeter_km = ring_perimeter_km(params, snapshot_region.boundary_ring);
            snapshot_region.dissolved_polygon_area_km2 = ring_projected_area_km2(params, snapshot_region.boundary_ring, weighted_center);
            if (snapshot_region.area_km2 > 0.0 && snapshot_region.dissolved_polygon_area_km2 > 0.0) {
                snapshot_region.polygon_area_error_fraction = std::abs(snapshot_region.dissolved_polygon_area_km2 - snapshot_region.area_km2) /
                    snapshot_region.area_km2;
            }
            if (snapshot_region.boundary_perimeter_km > 0.0 && snapshot_region.dissolved_polygon_area_km2 > 0.0) {
                snapshot_region.compactness_index = clamp(
                    4.0 * PI * snapshot_region.dissolved_polygon_area_km2 /
                        std::max(1.0, snapshot_region.boundary_perimeter_km * snapshot_region.boundary_perimeter_km),
                    0.0,
                    1.0
                );
            }
            if (!snapshot_region.boundary_ring.empty()) {
                double min_lon = std::numeric_limits<double>::infinity();
                double max_lon = -std::numeric_limits<double>::infinity();
                for (const LatLon& point : snapshot_region.boundary_ring) {
                    min_lon = std::min(min_lon, point.lon_deg);
                    max_lon = std::max(max_lon, point.lon_deg);
                }
                snapshot_region.crosses_antimeridian = max_lon - min_lon > 180.0;
            }
            const double ring_quality = clamp(static_cast<double>(snapshot_region.boundary_ring.size()) / 24.0, 0.0, 1.0);
            const double area_quality = clamp(1.0 - snapshot_region.polygon_area_error_fraction, 0.0, 1.0);
            snapshot_region.geometry_quality = clamp(0.62 * area_quality + 0.38 * ring_quality, 0.0, 1.0);
        }
        snapshot_region.boundary_cell_ids = sampled_ids(snapshot_region.boundary_cell_ids, 64);
    }

    const std::array<double, 4> area_factors = {0.48, 0.78, 0.64, 1.0};
    const std::array<double, 4> population_factors = {0.34, 0.58, 0.74, 1.0};
    std::vector<TerritorialSnapshot> snapshots;
    snapshots.reserve(historical_layers.eras.size());
    for (const HistoricalEra& era : historical_layers.eras) {
        TerritorialSnapshot snapshot;
        snapshot.id = static_cast<int>(snapshots.size());
        snapshot.era_id = era.id;
        snapshot.dominant_process = era.dominant_process;
        snapshot.year_bp = 0.5 * (era.start_year_bp + era.end_year_bp);
        const double era_area_factor = area_factors[static_cast<std::size_t>(clamp(era.id, 0, 3))];
        const double era_population_factor = population_factors[static_cast<std::size_t>(clamp(era.id, 0, 3))];
        double conflict_sum = 0.0;
        for (SnapshotRegion base_region : base_regions) {
            if (base_region.region_id < 0 || base_region.cell_count == 0) {
                continue;
            }
            const PopulationRegion* population = population_by_region.count(base_region.region_id) > 0 ?
                population_by_region[base_region.region_id] :
                nullptr;
            const double region_conflict = clamp(conflict_by_region_era[{base_region.region_id, era.id}] / 2.0, 0.0, 1.0);
            const double continuity = base_region.culture_region_id >= 0 ?
                cultural_layers.cultures[static_cast<std::size_t>(base_region.culture_region_id)].continuity_index :
                0.5;
            const double stability = clamp(0.42 + 0.42 * continuity - 0.30 * region_conflict + 0.10 * era.mean_connectivity, 0.0, 1.0);
            const double region_area_factor = era_area_factor * (0.82 + 0.18 * stability);
            base_region.area_km2 *= region_area_factor;
            base_region.dissolved_polygon_area_km2 *= region_area_factor;
            base_region.boundary_perimeter_km *= std::sqrt(region_area_factor);
            if (base_region.area_km2 > 0.0 && base_region.dissolved_polygon_area_km2 > 0.0) {
                base_region.polygon_area_error_fraction = std::abs(base_region.dissolved_polygon_area_km2 - base_region.area_km2) /
                    base_region.area_km2;
            }
            if (base_region.boundary_perimeter_km > 0.0 && base_region.dissolved_polygon_area_km2 > 0.0) {
                base_region.compactness_index = clamp(
                    4.0 * PI * base_region.dissolved_polygon_area_km2 /
                        std::max(1.0, base_region.boundary_perimeter_km * base_region.boundary_perimeter_km),
                    0.0,
                    1.0
                );
            }
            const double ring_quality = clamp(static_cast<double>(base_region.boundary_ring.size()) / 24.0, 0.0, 1.0);
            const double area_quality = clamp(1.0 - base_region.polygon_area_error_fraction, 0.0, 1.0);
            base_region.geometry_quality = clamp(0.62 * area_quality + 0.38 * ring_quality, 0.0, 1.0);
            base_region.estimated_population = (population != nullptr ? population->estimated_population : 0.0) *
                era_population_factor * (0.82 + 0.22 * stability);
            base_region.stability_index = stability;
            snapshot.estimated_population += base_region.estimated_population;
            snapshot.assigned_land_fraction += base_region.area_km2;
            if (base_region.area_km2 > snapshot.largest_region_area_km2) {
                snapshot.largest_region_area_km2 = base_region.area_km2;
                snapshot.largest_region_id = base_region.region_id;
            }
            conflict_sum += region_conflict;
            snapshot.regions.push_back(base_region);
        }
        snapshot.region_count = static_cast<int>(snapshot.regions.size());
        snapshot.assigned_land_fraction = land_area > 0.0 ? clamp(snapshot.assigned_land_fraction / land_area, 0.0, 1.0) : 0.0;
        const double largest_share = snapshot.assigned_land_fraction > 0.0 && land_area > 0.0 ?
            snapshot.largest_region_area_km2 / (snapshot.assigned_land_fraction * land_area) :
            0.0;
        snapshot.fragmentation_index = clamp(
            (snapshot.region_count > 1 ? 1.0 - largest_share : 0.0) * 0.72 +
                (snapshot.region_count > 0 ? conflict_sum / static_cast<double>(snapshot.region_count) : 0.0) * 0.28,
            0.0,
            1.0
        );
        snapshots.push_back(snapshot);
    }
    return snapshots;
}

double calibration_score_for_range(double value, double target_min, double target_max) {
    if (value >= target_min && value <= target_max) {
        return 1.0;
    }
    const double width = std::max(1.0e-9, target_max - target_min);
    const double distance = value < target_min ? target_min - value : value - target_max;
    return clamp(1.0 - distance / width, 0.0, 1.0);
}

void add_calibration_check(
    std::vector<CalibrationCheck>& checks,
    int dataset,
    int layer,
    int metric,
    double value,
    double target_min,
    double target_max
) {
    CalibrationCheck check;
    check.id = static_cast<int>(checks.size());
    check.dataset = dataset;
    check.layer = layer;
    check.metric = metric;
    check.value = value;
    check.target_min = target_min;
    check.target_max = target_max;
    check.score = calibration_score_for_range(value, target_min, target_max);
    check.passed = value >= target_min && value <= target_max;
    checks.push_back(check);
}

std::vector<CalibrationCheck> generate_calibration_checks(
    const std::vector<Cell>& cells,
    const std::vector<Watershed>& watersheds
) {
    std::vector<CalibrationCheck> checks;
    if (cells.empty()) {
        return checks;
    }

    double water_count = 0.0;
    double water_area_km2 = 0.0;
    double total_area_km2 = 0.0;
    double land_count = 0.0;
    double land_elev_sum = 0.0;
    double min_elevation = std::numeric_limits<double>::infinity();
    double max_elevation = -std::numeric_limits<double>::infinity();
    double temp_sum = 0.0;
    double land_precip_sum = 0.0;
    double monthly_range_sum = 0.0;
    double river_land_count = 0.0;
    double desert_land_count = 0.0;
    double ice_land_count = 0.0;
    double forest_land_count = 0.0;
    double coastal_land_count = 0.0;

    for (const Cell& cell : cells) {
        const double area_km2 = std::max(0.0, cell.area_km2);
        water_count += cell.is_water ? 1.0 : 0.0;
        water_area_km2 += cell.is_water ? area_km2 : 0.0;
        total_area_km2 += area_km2;
        min_elevation = std::min(min_elevation, cell.elevation_m);
        max_elevation = std::max(max_elevation, cell.elevation_m);
        temp_sum += cell.temperature_c;
        if (!cell.temperature_monthly_c.empty()) {
            const auto [min_temp, max_temp] = std::minmax_element(cell.temperature_monthly_c.begin(), cell.temperature_monthly_c.end());
            monthly_range_sum += *max_temp - *min_temp;
        }
        if (cell.is_water) {
            continue;
        }
        land_count += 1.0;
        land_elev_sum += cell.elevation_m;
        land_precip_sum += cell.precipitation_mm_y;
        if (cell.is_river) {
            river_land_count += 1.0;
        }
        if (cell.biome == 9 || cell.biome == 10) {
            desert_land_count += 1.0;
        }
        if (cell.biome == 3 || cell.ice_thickness_m > 25.0) {
            ice_land_count += 1.0;
        }
        if (cell.biome == 5 || cell.biome == 6 || cell.biome == 12 || cell.biome == 13) {
            forest_land_count += 1.0;
        }
        for (int neighbor_id : cell.neighbors) {
            if (neighbor_id >= 0 && neighbor_id < static_cast<int>(cells.size()) && cells[static_cast<std::size_t>(neighbor_id)].is_water) {
                coastal_land_count += 1.0;
                break;
            }
        }
    }

    double endorheic_watersheds = 0.0;
    for (const Watershed& watershed : watersheds) {
        endorheic_watersheds += watershed.is_endorheic ? 1.0 : 0.0;
    }

    const double cell_count = static_cast<double>(cells.size());
    add_calibration_check(
        checks,
        0,
        0,
        0,
        total_area_km2 > 0.0 ? water_area_km2 / total_area_km2 : water_count / cell_count,
        0.55,
        0.78
    );
    add_calibration_check(checks, 0, 0, 1, land_count > 0.0 ? land_elev_sum / land_count : 0.0, 120.0, 1800.0);
    add_calibration_check(checks, 0, 0, 2, max_elevation - min_elevation, 3500.0, 17000.0);
    add_calibration_check(checks, 1, 1, 3, temp_sum / cell_count, -5.0, 28.0);
    add_calibration_check(checks, 1, 1, 4, land_count > 0.0 ? land_precip_sum / land_count : 0.0, 250.0, 2300.0);
    add_calibration_check(checks, 1, 1, 5, monthly_range_sum / cell_count, 2.0, 38.0);
    add_calibration_check(checks, 2, 2, 6, land_count > 0.0 ? river_land_count / land_count : 0.0, 0.005, 0.14);
    add_calibration_check(
        checks,
        2,
        2,
        7,
        watersheds.empty() ? 0.0 : endorheic_watersheds / static_cast<double>(watersheds.size()),
        0.0,
        0.55
    );
    add_calibration_check(checks, 1, 3, 8, land_count > 0.0 ? desert_land_count / land_count : 0.0, 0.04, 0.48);
    add_calibration_check(checks, 1, 3, 9, land_count > 0.0 ? ice_land_count / land_count : 0.0, 0.0, 0.38);
    add_calibration_check(checks, 1, 3, 10, land_count > 0.0 ? forest_land_count / land_count : 0.0, 0.08, 0.58);
    add_calibration_check(checks, 3, 4, 11, land_count > 0.0 ? coastal_land_count / land_count : 0.0, 0.03, 0.48);
    return checks;
}

}  // namespace magic_geo::detail
