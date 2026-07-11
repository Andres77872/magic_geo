#include "internal.hpp"

namespace magic_geo::detail {

int political_region_type_for_capital(const std::vector<Cell>& cells, const Settlement& capital) {
    const Cell& cell = cells[capital.cell_id];
    if (capital.type == 1) {
        return 1;
    }
    if (capital.type == 0 || cell.is_river) {
        return 0;
    }
    if (capital.type == 2 || cell.resource == 1 || cell.resource == 2 || cell.resource == 5 || cell.resource == 6) {
        return 3;
    }
    if (cell.elevation_m > 1200.0 || cell.landform == 6 || cell.landform == 17) {
        return 2;
    }
    if (capital.type == 3 || cell.fertility > 0.68 || cell.resource == 7) {
        return 4;
    }
    return 5;
}

double settlement_region_cost(
    const Params& params,
    const std::vector<Cell>& cells,
    const Settlement& settlement,
    const Settlement& capital,
    const std::vector<Route>& routes
) {
    const Cell& a = cells[settlement.cell_id];
    const Cell& b = cells[capital.cell_id];
    double cost = angular_distance(a.p, b.p) * params.radius_km * route_barrier_cost(a, b);
    if (a.basin_id == b.basin_id && (a.is_river || b.is_river)) {
        cost *= 0.76;
    }
    if (has_ocean_neighbor(cells, a.id) && has_ocean_neighbor(cells, b.id)) {
        cost *= 0.72;
    }
    for (const Route& route : routes) {
        const bool linked = (route.from == settlement.id && route.to == capital.id) ||
            (route.to == settlement.id && route.from == capital.id);
        if (linked) {
            cost *= route.type == 2 ? 0.45 : 0.58;
            break;
        }
    }
    return cost;
}

void assign_cell_regions(const Params& params, std::vector<Cell>& cells, const std::vector<Settlement>& capitals) {
    if (capitals.empty()) {
        for (Cell& cell : cells) {
            cell.political_region_id = -1;
        }
        return;
    }
#pragma omp parallel for schedule(static)
    for (int i = 0; i < static_cast<int>(cells.size()); ++i) {
        if (cells[i].is_water) {
            cells[i].political_region_id = -1;
            continue;
        }
        double best_cost = std::numeric_limits<double>::infinity();
        int best_region = -1;
        for (const Settlement& capital : capitals) {
            const Cell& capital_cell = cells[capital.cell_id];
            double cost = angular_distance(cells[i].p, capital_cell.p) * params.radius_km * route_barrier_cost(cells[i], capital_cell);
            if (cells[i].basin_id == capital_cell.basin_id && (cells[i].is_river || capital_cell.is_river)) {
                cost *= 0.80;
            }
            if (has_ocean_neighbor(cells, i) && has_ocean_neighbor(cells, capital.cell_id)) {
                cost *= 0.76;
            }
            if (cost < best_cost) {
                best_cost = cost;
                best_region = capital.region_id;
            }
        }
        cells[i].political_region_id = best_region;
    }
}

std::vector<PoliticalRegion> generate_political_regions(
    const Params& params,
    std::vector<Cell>& cells,
    std::vector<Settlement>& settlements,
    const std::vector<Route>& routes
) {
    for (Settlement& settlement : settlements) {
        settlement.region_id = -1;
    }
    for (Cell& cell : cells) {
        cell.political_region_id = -1;
    }
    if (settlements.empty()) {
        return {};
    }

    const int target_regions = clamp(static_cast<int>(settlements.size()) / 5 + 1, 1, std::min(10, static_cast<int>(settlements.size())));
    std::vector<int> capital_indices;
    for (const Settlement& settlement : settlements) {
        bool too_close = false;
        for (int capital_index : capital_indices) {
            const double distance = angular_distance(cells[settlement.cell_id].p, cells[settlements[capital_index].cell_id].p);
            if (distance < 0.18) {
                too_close = true;
                break;
            }
        }
        if (!too_close) {
            capital_indices.push_back(settlement.id);
        }
        if (static_cast<int>(capital_indices.size()) >= target_regions) {
            break;
        }
    }
    if (capital_indices.empty()) {
        capital_indices.push_back(settlements.front().id);
    }

    std::vector<PoliticalRegion> regions;
    regions.reserve(capital_indices.size());
    for (int i = 0; i < static_cast<int>(capital_indices.size()); ++i) {
        Settlement& capital = settlements[capital_indices[static_cast<std::size_t>(i)]];
        capital.region_id = i;
        PoliticalRegion region;
        region.id = i;
        region.capital_settlement_id = capital.id;
        region.type = political_region_type_for_capital(cells, capital);
        regions.push_back(region);
    }

    for (Settlement& settlement : settlements) {
        if (settlement.region_id >= 0) {
            continue;
        }
        double best_cost = std::numeric_limits<double>::infinity();
        int best_region = 0;
        for (const PoliticalRegion& region : regions) {
            const Settlement& capital = settlements[region.capital_settlement_id];
            const double cost = settlement_region_cost(params, cells, settlement, capital, routes);
            if (cost < best_cost) {
                best_cost = cost;
                best_region = region.id;
            }
        }
        settlement.region_id = best_region;
    }

    std::vector<Settlement> capitals;
    for (const PoliticalRegion& region : regions) {
        capitals.push_back(settlements[region.capital_settlement_id]);
    }
    assign_cell_regions(params, cells, capitals);

    std::vector<std::map<int, int>> biome_counts(regions.size());
    std::vector<std::map<int, int>> resource_counts(regions.size());
    for (const Settlement& settlement : settlements) {
        if (settlement.region_id < 0 || settlement.region_id >= static_cast<int>(regions.size())) {
            continue;
        }
        PoliticalRegion& region = regions[settlement.region_id];
        region.settlement_ids.push_back(settlement.id);
        region.settlement_count += 1;
        region.mean_settlement_score += settlement.score;
    }
    for (const Route& route : routes) {
        if (route.from < 0 || route.from >= static_cast<int>(settlements.size()) ||
            route.to < 0 || route.to >= static_cast<int>(settlements.size())) {
            continue;
        }
        const int a = settlements[route.from].region_id;
        const int b = settlements[route.to].region_id;
        if (a >= 0 && a == b && a < static_cast<int>(regions.size())) {
            regions[a].route_count += 1;
        }
    }
    for (const Cell& cell : cells) {
        const int region_id = cell.political_region_id;
        if (region_id < 0 || region_id >= static_cast<int>(regions.size())) {
            continue;
        }
        PoliticalRegion& region = regions[region_id];
        region.area_km2 += cell.area_km2;
        region.mean_elevation_m += cell.elevation_m * cell.area_km2;
        region.barrier_pressure += clamp(local_relief(cells, cell.id) / 1800.0, 0.0, 1.0) * cell.area_km2;
        biome_counts[region_id][cell.biome]++;
        resource_counts[region_id][cell.resource]++;
    }
    for (PoliticalRegion& region : regions) {
        if (region.settlement_count > 0) {
            region.mean_settlement_score /= static_cast<double>(region.settlement_count);
        }
        if (region.area_km2 > 0.0) {
            region.mean_elevation_m /= region.area_km2;
            region.barrier_pressure /= region.area_km2;
        }
        int best_biome = 0;
        int best_biome_count = -1;
        for (const auto& [biome, count] : biome_counts[region.id]) {
            if (count > best_biome_count) {
                best_biome = biome;
                best_biome_count = count;
            }
        }
        region.dominant_biome = best_biome;
        int best_resource = 0;
        int best_resource_count = -1;
        for (const auto& [resource, count] : resource_counts[region.id]) {
            if (resource != 0 && count > best_resource_count) {
                best_resource = resource;
                best_resource_count = count;
            }
        }
        region.dominant_resource = best_resource_count < 0 ? 0 : best_resource;
    }
    return regions;
}

int border_type_for_cells(const Cell& a, const Cell& b) {
    if (a.is_river || b.is_river) {
        return 1;
    }
    if (a.landform == 6 || b.landform == 6 || a.landform == 17 || b.landform == 17 ||
        a.elevation_m > 1400.0 || b.elevation_m > 1400.0) {
        return 2;
    }
    if (a.biome == 9 || a.biome == 10 || b.biome == 9 || b.biome == 10) {
        return 3;
    }
    if (a.landform == 5 || b.landform == 5 || a.biome == 3 || b.biome == 3) {
        return 4;
    }
    if (a.landform == 14 || b.landform == 14) {
        return 5;
    }
    return 0;
}

std::vector<BorderSegment> generate_border_segments(const Params& params, const std::vector<Cell>& cells) {
    std::vector<BorderSegment> borders;
    for (const Cell& cell : cells) {
        if (cell.is_water || cell.political_region_id < 0) {
            continue;
        }
        for (int neighbor_id : cell.neighbors) {
            if (neighbor_id <= cell.id) {
                continue;
            }
            const Cell& neighbor = cells[neighbor_id];
            if (neighbor.is_water || neighbor.political_region_id < 0 || neighbor.political_region_id == cell.political_region_id) {
                continue;
            }
            BorderSegment border;
            border.id = static_cast<int>(borders.size());
            border.region_a = std::min(cell.political_region_id, neighbor.political_region_id);
            border.region_b = std::max(cell.political_region_id, neighbor.political_region_id);
            border.cell_a = cell.id;
            border.cell_b = neighbor.id;
            border.length_km = neighbor_distance_m(params, cell, neighbor) / 1000.0;
            border.type = border_type_for_cells(cell, neighbor);
            const double relief = std::abs(cell.elevation_m - neighbor.elevation_m);
            const double hazard = 0.5 * (cell.boundary_convergent + neighbor.boundary_convergent) +
                0.25 * (cell.boundary_transform + neighbor.boundary_transform);
            border.barrier_score = clamp(
                0.18 + relief / 2500.0 + hazard * 0.45 +
                    ((border.type == 2 || border.type == 3 || border.type == 4) ? 0.34 : 0.0),
                0.0,
                1.0
            );
            borders.push_back(border);
        }
    }
    return borders;
}

int trade_good_priority(int resource) {
    switch (resource) {
        case 1:
        case 2:
        case 5:
            return 6;
        case 3:
        case 4:
            return 5;
        case 6:
            return 4;
        case 7:
            return 3;
        case 8:
            return 2;
        default:
            return 0;
    }
}

int primary_trade_good(const std::vector<Cell>& cells, const Settlement& a, const Settlement& b) {
    const Cell& ca = cells[a.cell_id];
    const Cell& cb = cells[b.cell_id];
    int good = 0;
    int best_priority = 0;
    for (int resource : {ca.resource, cb.resource}) {
        const int priority = trade_good_priority(resource);
        if (resource != 0 && priority > best_priority) {
            good = resource;
            best_priority = priority;
        }
    }
    if (good != 0) {
        return good;
    }
    if (a.type == 1 || b.type == 1 || has_ocean_neighbor(cells, ca.id) || has_ocean_neighbor(cells, cb.id)) {
        return 8;
    }
    if (ca.fertility > 0.62 || cb.fertility > 0.62) {
        return 7;
    }
    return 0;
}

std::vector<TradeFlow> generate_trade_flows(
    const std::vector<Cell>& cells,
    const std::vector<Settlement>& settlements,
    const std::vector<Route>& routes
) {
    std::vector<TradeFlow> flows;
    flows.reserve(routes.size());
    for (const Route& route : routes) {
        if (route.from < 0 || route.to < 0 ||
            route.from >= static_cast<int>(settlements.size()) ||
            route.to >= static_cast<int>(settlements.size())) {
            continue;
        }
        const Settlement& from = settlements[route.from];
        const Settlement& to = settlements[route.to];
        const Cell& a = cells[from.cell_id];
        const Cell& b = cells[to.cell_id];
        const double friction = route.cost / std::max(1.0, route.distance_km);
        const int primary_good = primary_trade_good(cells, from, to);
        const double resource_bonus = primary_good == 0 ? 0.0 :
            (primary_good == 7 || primary_good == 8 ? 0.16 : 0.30);
        const double fertility_complement = std::abs(a.fertility - b.fertility);
        const double climate_complement = clamp(std::abs(a.temperature_c - b.temperature_c) / 45.0, 0.0, 0.55);
        const bool interregional = from.region_id >= 0 && to.region_id >= 0 && from.region_id != to.region_id;
        const double region_bonus = interregional ? 0.22 : 0.0;
        const double route_bonus = route.type == 2 ? 0.25 : (route.type == 1 ? 0.18 : (route.type == 3 ? -0.10 : 0.0));
        const double endpoint_strength = 0.5 * (from.score + to.score);
        const double volume = 80.0 * endpoint_strength *
            (1.0 + resource_bonus + 0.35 * fertility_complement + 0.25 * climate_complement + region_bonus + route_bonus) /
            (0.55 + friction);

        TradeFlow flow;
        flow.id = static_cast<int>(flows.size());
        flow.route_id = route.id;
        flow.from = route.from;
        flow.to = route.to;
        flow.region_from = from.region_id;
        flow.region_to = to.region_id;
        flow.primary_good = primary_good;
        flow.interregional = interregional;
        flow.distance_km = route.distance_km;
        flow.friction = friction;
        flow.volume_index = clamp(volume, 0.0, 100.0);
        flows.push_back(flow);
    }
    return flows;
}

int culture_type_for_region(const PoliticalRegion& region) {
    if (region.type == 1) {
        return 1;
    }
    if (region.type == 0) {
        return 0;
    }
    if (region.type == 2 || region.mean_elevation_m > 1100.0) {
        return 2;
    }
    if (region.dominant_biome == 9 || region.dominant_biome == 10) {
        return 3;
    }
    if (region.type == 3 || region.dominant_resource == 1 || region.dominant_resource == 2 ||
        region.dominant_resource == 5 || region.dominant_resource == 6) {
        return 5;
    }
    if (region.dominant_biome == 4 || region.dominant_biome == 5) {
        return 6;
    }
    if (region.dominant_biome == 11 || region.dominant_biome == 12 || region.dominant_biome == 13) {
        return 7;
    }
    return 4;
}

int language_family_for_culture(const CultureRegion& culture) {
    switch (culture.type) {
        case 0:
            return 0;
        case 1:
            return 1;
        case 2:
            return 2;
        case 3:
            return 3;
        case 4:
            return 4;
        default:
            return 5;
    }
}

int base_phoneme_inventory_for_family(int family) {
    switch (family) {
        case 0:
            return 27;
        case 1:
            return 31;
        case 2:
            return 34;
        case 3:
            return 24;
        case 4:
            return 29;
        default:
            return 30;
    }
}

void derive_language_phonology(std::vector<LanguageRegion>& languages) {
    for (LanguageRegion& language : languages) {
        const int base_inventory = base_phoneme_inventory_for_family(language.family);
        language.sound_shift_index = language.parent_language_region_id < 0 ?
            clamp(0.04 + 0.16 * language.change_rate, 0.0, 0.28) :
            clamp(
                0.10 + 0.42 * language.change_rate +
                    0.28 * clamp(language.divergence_age_years / 3200.0, 0.0, 1.0) +
                    0.18 * language.barrier_isolation -
                    0.14 * language.trade_contact_index,
                0.0,
                1.0
            );
        language.inherited_phonology_fraction = language.parent_language_region_id < 0 ?
            1.0 :
            clamp(1.0 - 0.78 * language.sound_shift_index, 0.0, 1.0);
        const int parent_inventory =
            language.parent_language_region_id >= 0 &&
                language.parent_language_region_id < static_cast<int>(languages.size()) &&
                languages[static_cast<std::size_t>(language.parent_language_region_id)].phoneme_inventory_size > 0 ?
            languages[static_cast<std::size_t>(language.parent_language_region_id)].phoneme_inventory_size :
            base_inventory;
        const double innovation = 8.0 * language.sound_shift_index +
            4.0 * language.barrier_isolation -
            3.0 * language.trade_contact_index +
            1.6 * static_cast<double>(language.lineage_depth);
        language.phoneme_inventory_size = clamp(
            static_cast<int>(std::lround(parent_inventory * (0.72 + 0.28 * language.inherited_phonology_fraction) + innovation)),
            16,
            58
        );
        language.phonological_complexity = clamp(
            0.20 +
                0.44 * (static_cast<double>(language.phoneme_inventory_size) / 58.0) +
                0.20 * language.barrier_isolation +
                0.10 * language.sound_shift_index -
                0.10 * language.trade_contact_index +
                0.04 * static_cast<double>(language.lineage_depth),
            0.0,
            1.0
        );
    }
}

int find_root(std::vector<int>& parent, int value) {
    int root = value;
    while (parent[root] != root) {
        root = parent[root];
    }
    while (parent[value] != value) {
        const int next = parent[value];
        parent[value] = root;
        value = next;
    }
    return root;
}

void union_roots(std::vector<int>& parent, int a, int b) {
    const int root_a = find_root(parent, a);
    const int root_b = find_root(parent, b);
    if (root_a != root_b) {
        parent[std::max(root_a, root_b)] = std::min(root_a, root_b);
    }
}

double sacred_significance_for_cell(const std::vector<Cell>& cells, const Cell& cell) {
    double score = 0.0;
    if (cell.elevation_m > 1700.0 || cell.landform == 6 || cell.landform == 17) {
        score += 0.34;
    }
    if (cell.is_river || cell.is_lake || cell.water_body == 4 || cell.water_body == 5) {
        score += 0.18;
    }
    if (cell.resource == 6 || cell.landform == 7) {
        score += 0.26;
    }
    if (cell.landform == 4 || cell.is_closed_basin) {
        score += 0.22;
    }
    if (cell.fertility > 0.74 && cell.precipitation_mm_y > 650.0) {
        score += 0.16;
    }
    if (has_ocean_neighbor(cells, cell.id)) {
        score += 0.12;
    }
    score += 0.12 * clamp(local_relief(cells, cell.id) / 1700.0, 0.0, 1.0);
    return clamp(score, 0.0, 1.0);
}

int sacred_area_type_for_cell(const std::vector<Cell>& cells, const Cell& cell) {
    if (cell.resource == 6 || cell.landform == 7) {
        return 3;
    }
    if (cell.elevation_m > 1700.0 || cell.landform == 6 || cell.landform == 17) {
        return 0;
    }
    if (cell.is_river || cell.is_lake || cell.water_body == 4 || cell.water_body == 5) {
        return 1;
    }
    if (cell.biome == 5 || cell.biome == 6 || cell.biome == 13 || cell.biome == 15) {
        return 2;
    }
    if (cell.biome == 9 || cell.biome == 10 || cell.landform == 4) {
        return 5;
    }
    if (has_ocean_neighbor(cells, cell.id)) {
        return 4;
    }
    return 2;
}

double ruin_significance_for_cell(const std::vector<Cell>& cells, const Cell& cell) {
    const bool coast = has_ocean_neighbor(cells, cell.id);
    double historical_potential = 0.18 + 0.38 * cell.settlement_score + 0.24 * cell.fertility;
    if (cell.is_river || cell.is_lake || coast) {
        historical_potential += 0.14;
    }
    if (cell.resource == 1 || cell.resource == 2 || cell.resource == 3 ||
        cell.resource == 4 || cell.resource == 5 || cell.resource == 6 || cell.resource == 7) {
        historical_potential += 0.16;
    }
    double abandonment_pressure = 0.0;
    if (cell.biome == 9 || cell.biome == 10 || cell.precipitation_mm_y < 220.0) {
        abandonment_pressure += 0.24;
    }
    if (cell.ice_thickness_m > 20.0 || cell.biome == 3) {
        abandonment_pressure += 0.22;
    }
    if (cell.water_body == 5 || cell.landform == 4 || cell.is_closed_basin) {
        abandonment_pressure += 0.18;
    }
    abandonment_pressure += 0.18 * clamp(cell.boundary_convergent + cell.boundary_transform, 0.0, 1.0);
    abandonment_pressure += 0.12 * clamp(local_relief(cells, cell.id) / 1800.0, 0.0, 1.0);
    if (cell.settlement_score < 0.52) {
        abandonment_pressure += 0.10;
    }
    return clamp(historical_potential * (0.55 + abandonment_pressure), 0.0, 1.0);
}

int ruin_type_for_cell(const std::vector<Cell>& cells, const Cell& cell) {
    if (cell.resource == 1 || cell.resource == 2 || cell.resource == 5 || cell.resource == 6) {
        return 1;
    }
    if (cell.biome == 9 || cell.biome == 10 || cell.landform == 4) {
        return 2;
    }
    if (cell.elevation_m > 1300.0 || cell.landform == 6 || cell.landform == 17) {
        return 3;
    }
    if (has_ocean_neighbor(cells, cell.id)) {
        return 4;
    }
    if (cell.ice_thickness_m > 20.0 || cell.biome == 3) {
        return 5;
    }
    return 0;
}

int abandonment_reason_for_cell(const Cell& cell) {
    if (cell.biome == 9 || cell.biome == 10 || cell.precipitation_mm_y < 220.0) {
        return 0;
    }
    if (cell.boundary_convergent + cell.boundary_transform > 0.45) {
        return 1;
    }
    if (cell.ice_thickness_m > 20.0 || cell.biome == 3) {
        return 2;
    }
    if (cell.water_body == 5 || cell.landform == 4 || cell.is_closed_basin) {
        return 3;
    }
    if (cell.settlement_score < 0.48) {
        return 4;
    }
    return 5;
}

CulturalLayers generate_cultural_layers(
    const Params& params,
    std::vector<Cell>& cells,
    std::vector<Settlement>& settlements,
    const std::vector<PoliticalRegion>& political_regions,
    const std::vector<BorderSegment>& borders,
    const std::vector<TradeFlow>& trade_flows
) {
    (void)params;
    for (Cell& cell : cells) {
        cell.culture_region_id = -1;
        cell.language_region_id = -1;
    }
    for (Settlement& settlement : settlements) {
        settlement.culture_region_id = -1;
        settlement.language_region_id = -1;
    }
    CulturalLayers layers;
    if (political_regions.empty()) {
        return layers;
    }

    int max_region_id = -1;
    for (const PoliticalRegion& region : political_regions) {
        max_region_id = std::max(max_region_id, region.id);
    }
    std::vector<int> region_to_culture(static_cast<std::size_t>(max_region_id + 1), -1);
    layers.cultures.reserve(political_regions.size());
    for (const PoliticalRegion& region : political_regions) {
        CultureRegion culture;
        culture.id = static_cast<int>(layers.cultures.size());
        culture.homeland_region_id = region.id;
        culture.type = culture_type_for_region(region);
        culture.dominant_biome = region.dominant_biome;
        culture.dominant_resource = region.dominant_resource;
        culture.settlement_count = region.settlement_count;
        culture.settlement_ids = region.settlement_ids;
        if (region.id >= 0 && region.id < static_cast<int>(region_to_culture.size())) {
            region_to_culture[region.id] = culture.id;
        }
        layers.cultures.push_back(culture);
    }

    for (Cell& cell : cells) {
        if (cell.is_water || cell.political_region_id < 0 ||
            cell.political_region_id >= static_cast<int>(region_to_culture.size())) {
            continue;
        }
        cell.culture_region_id = region_to_culture[cell.political_region_id];
    }

    std::vector<double> barrier_sum(layers.cultures.size(), 0.0);
    std::vector<double> border_length(layers.cultures.size(), 0.0);
    std::vector<double> trade_volume(layers.cultures.size(), 0.0);
    std::vector<std::map<int, int>> biome_counts(layers.cultures.size());
    std::vector<std::map<int, int>> resource_counts(layers.cultures.size());

    for (const Cell& cell : cells) {
        if (cell.culture_region_id < 0) {
            continue;
        }
        CultureRegion& culture = layers.cultures[cell.culture_region_id];
        culture.area_km2 += cell.area_km2;
        culture.mean_fertility += cell.fertility * cell.area_km2;
        culture.mean_elevation_m += cell.elevation_m * cell.area_km2;
        if (cell.fertility > 0.62 || cell.resource == 7 || cell.landform == 11 || cell.landform == 12) {
            culture.agricultural_area_km2 += cell.area_km2;
        }
        if (cell.resource == 1 || cell.resource == 2 || cell.resource == 5 || cell.resource == 6) {
            culture.mining_area_km2 += cell.area_km2;
        }
        biome_counts[cell.culture_region_id][cell.biome]++;
        resource_counts[cell.culture_region_id][cell.resource]++;
    }

    for (const BorderSegment& border : borders) {
        if (border.region_a < 0 || border.region_b < 0 ||
            border.region_a >= static_cast<int>(region_to_culture.size()) ||
            border.region_b >= static_cast<int>(region_to_culture.size())) {
            continue;
        }
        const int a = region_to_culture[border.region_a];
        const int b = region_to_culture[border.region_b];
        if (a < 0 || b < 0 || a == b) {
            continue;
        }
        barrier_sum[a] += border.barrier_score * border.length_km;
        barrier_sum[b] += border.barrier_score * border.length_km;
        border_length[a] += border.length_km;
        border_length[b] += border.length_km;
    }

    std::vector<int> parent(layers.cultures.size());
    std::iota(parent.begin(), parent.end(), 0);
    for (const TradeFlow& flow : trade_flows) {
        if (flow.region_from < 0 || flow.region_to < 0 ||
            flow.region_from >= static_cast<int>(region_to_culture.size()) ||
            flow.region_to >= static_cast<int>(region_to_culture.size())) {
            continue;
        }
        const int a = region_to_culture[flow.region_from];
        const int b = region_to_culture[flow.region_to];
        if (a < 0 || b < 0) {
            continue;
        }
        trade_volume[a] += flow.volume_index;
        trade_volume[b] += flow.volume_index;
        if (a != b && flow.volume_index >= 70.0 && flow.friction <= 0.92) {
            union_roots(parent, a, b);
        }
    }

    std::map<int, int> root_to_language;
    for (CultureRegion& culture : layers.cultures) {
        const int root = find_root(parent, culture.id);
        auto [it, inserted] = root_to_language.emplace(root, static_cast<int>(root_to_language.size()));
        (void)inserted;
        culture.language_region_id = it->second;
    }

    layers.language_regions.resize(root_to_language.size());
    std::vector<std::map<int, double>> language_family_area(layers.language_regions.size());
    for (int i = 0; i < static_cast<int>(layers.language_regions.size()); ++i) {
        layers.language_regions[i].id = i;
    }

    for (CultureRegion& culture : layers.cultures) {
        if (culture.area_km2 > 0.0) {
            culture.mean_fertility /= culture.area_km2;
            culture.mean_elevation_m /= culture.area_km2;
        }
        culture.barrier_isolation = border_length[culture.id] > 0.0 ? barrier_sum[culture.id] / border_length[culture.id] : 0.0;
        culture.trade_contact_index = clamp(trade_volume[culture.id] / (100.0 * std::max(1, culture.settlement_count)), 0.0, 1.0);
        int best_biome = culture.dominant_biome;
        int best_biome_count = -1;
        for (const auto& [biome, count] : biome_counts[culture.id]) {
            if (count > best_biome_count) {
                best_biome = biome;
                best_biome_count = count;
            }
        }
        culture.dominant_biome = best_biome;
        int best_resource = 0;
        int best_resource_count = -1;
        for (const auto& [resource, count] : resource_counts[culture.id]) {
            if (resource != 0 && count > best_resource_count) {
                best_resource = resource;
                best_resource_count = count;
            }
        }
        culture.dominant_resource = best_resource_count < 0 ? 0 : best_resource;
        culture.migration_pressure = clamp(
            0.18 + 0.28 * (1.0 - culture.barrier_isolation) +
                0.22 * culture.trade_contact_index +
                0.16 * (1.0 - culture.mean_fertility) +
                0.12 * clamp(culture.mean_elevation_m / 1800.0, 0.0, 1.0),
            0.0,
            1.0
        );
        culture.continuity_index = clamp(
            0.30 + 0.22 * culture.barrier_isolation +
                0.18 * culture.mean_fertility +
                0.10 * std::min(1.0, static_cast<double>(culture.settlement_count) / 6.0) +
                0.10 * std::min(1.0, static_cast<double>(culture.sacred_area_count) / 3.0) -
                0.16 * std::min(1.0, static_cast<double>(culture.ruin_count) / 4.0),
            0.0,
            1.0
        );
        culture.estimated_age_years = clamp(
            420.0 + 1900.0 * culture.continuity_index +
                520.0 * culture.barrier_isolation +
                260.0 * std::min(1.0, static_cast<double>(culture.settlement_count) / 8.0),
            120.0,
            4200.0
        );

        LanguageRegion& language = layers.language_regions[culture.language_region_id];
        language.culture_count += 1;
        language.settlement_count += culture.settlement_count;
        language.area_km2 += culture.area_km2;
        language.barrier_isolation += culture.barrier_isolation * culture.area_km2;
        language.trade_contact_index += culture.trade_contact_index * culture.area_km2;
        language.culture_ids.push_back(culture.id);
        language_family_area[culture.language_region_id][language_family_for_culture(culture)] += culture.area_km2;
    }

    for (LanguageRegion& language : layers.language_regions) {
        if (language.area_km2 > 0.0) {
            language.barrier_isolation /= language.area_km2;
            language.trade_contact_index /= language.area_km2;
        }
        int best_family = 0;
        double best_area = -1.0;
        for (const auto& [family, area] : language_family_area[language.id]) {
            if (area > best_area) {
                best_family = family;
                best_area = area;
            }
        }
        language.family = best_family;
    }
    std::map<int, std::vector<std::pair<double, int>>> languages_by_family;
    for (const LanguageRegion& language : layers.language_regions) {
        languages_by_family[language.family].push_back({language.area_km2, language.id});
    }
    for (auto& [family, members] : languages_by_family) {
        (void)family;
        std::sort(members.begin(), members.end(), [](const auto& a, const auto& b) {
            if (a.first == b.first) {
                return a.second < b.second;
            }
            return a.first > b.first;
        });
        const int parent_language = members.empty() ? -1 : members.front().second;
        for (std::size_t i = 0; i < members.size(); ++i) {
            LanguageRegion& language = layers.language_regions[static_cast<std::size_t>(members[i].second)];
            language.parent_language_region_id = i == 0 ? -1 : parent_language;
            language.lineage_depth = i == 0 ? 0 : 1;
            language.change_rate = clamp(
                0.16 + 0.48 * language.barrier_isolation -
                    0.26 * language.trade_contact_index +
                    0.08 * std::min(1.0, static_cast<double>(language.culture_count) / 4.0),
                0.0,
                1.0
            );
            language.divergence_age_years = language.parent_language_region_id < 0 ?
                clamp(900.0 + 2100.0 * (1.0 - language.change_rate) + 380.0 * language.barrier_isolation, 250.0, 4200.0) :
                clamp(220.0 + 1700.0 * language.barrier_isolation + 820.0 * (1.0 - language.trade_contact_index), 120.0, 3200.0);
        }
    }
    bool has_lineage = false;
    for (const LanguageRegion& language : layers.language_regions) {
        if (language.parent_language_region_id >= 0) {
            has_lineage = true;
            break;
        }
    }
    if (!has_lineage && layers.language_regions.size() > 1) {
        int parent_language = 0;
        for (int i = 1; i < static_cast<int>(layers.language_regions.size()); ++i) {
            if (layers.language_regions[static_cast<std::size_t>(i)].area_km2 >
                layers.language_regions[static_cast<std::size_t>(parent_language)].area_km2) {
                parent_language = i;
            }
        }
        for (LanguageRegion& language : layers.language_regions) {
            if (language.id == parent_language) {
                continue;
            }
            language.parent_language_region_id = parent_language;
            language.lineage_depth = 1;
            language.divergence_age_years = clamp(
                280.0 + 1500.0 * language.barrier_isolation + 680.0 * (1.0 - language.trade_contact_index),
                120.0,
                3000.0
            );
            language.change_rate = clamp(language.change_rate + 0.08, 0.0, 1.0);
        }
    }

    derive_language_phonology(layers.language_regions);

    for (Cell& cell : cells) {
        if (cell.culture_region_id >= 0) {
            cell.language_region_id = layers.cultures[cell.culture_region_id].language_region_id;
        }
    }
    for (Settlement& settlement : settlements) {
        const Cell& cell = cells[settlement.cell_id];
        settlement.culture_region_id = cell.culture_region_id;
        settlement.language_region_id = cell.language_region_id;
    }

    std::vector<std::pair<double, int>> sacred_candidates;
    for (const Cell& cell : cells) {
        if (cell.is_water || cell.culture_region_id < 0) {
            continue;
        }
        const double significance = sacred_significance_for_cell(cells, cell);
        if (significance >= 0.30) {
            sacred_candidates.emplace_back(significance, cell.id);
        }
    }
    std::sort(sacred_candidates.begin(), sacred_candidates.end(), [](const auto& a, const auto& b) {
        if (a.first == b.first) {
            return a.second < b.second;
        }
        return a.first > b.first;
    });
    const int sacred_target = clamp(static_cast<int>(layers.cultures.size()) * 2, 2, 24);
    const double site_min_sep = 1.4 * std::sqrt(
        4.0 * PI / static_cast<double>(std::max<std::size_t>(1, cells.size()))
    );
    for (const auto& [significance, cell_id] : sacred_candidates) {
        bool too_close = false;
        for (const SacredArea& site : layers.sacred_areas) {
            if (angular_distance(cells[cell_id].p, cells[site.cell_id].p) < site_min_sep) {
                too_close = true;
                break;
            }
        }
        if (too_close) {
            continue;
        }
        const Cell& cell = cells[cell_id];
        SacredArea site;
        site.id = static_cast<int>(layers.sacred_areas.size());
        site.cell_id = cell_id;
        site.culture_region_id = cell.culture_region_id;
        site.language_region_id = cell.language_region_id;
        site.type = sacred_area_type_for_cell(cells, cell);
        site.significance = significance;
        site.lat_deg = cell.lat * DEG;
        site.lon_deg = cell.lon * DEG;
        layers.sacred_areas.push_back(site);
        layers.cultures[site.culture_region_id].sacred_area_count += 1;
        if (static_cast<int>(layers.sacred_areas.size()) >= sacred_target) {
            break;
        }
    }

    std::vector<char> active_settlement_cell(cells.size(), 0);
    for (const Settlement& settlement : settlements) {
        if (settlement.cell_id >= 0 && settlement.cell_id < static_cast<int>(active_settlement_cell.size())) {
            active_settlement_cell[settlement.cell_id] = 1;
        }
    }
    std::vector<std::pair<double, int>> ruin_candidates;
    for (const Cell& cell : cells) {
        if (cell.is_water || cell.culture_region_id < 0 || active_settlement_cell[cell.id]) {
            continue;
        }
        const double significance = ruin_significance_for_cell(cells, cell);
        if (significance >= 0.32) {
            ruin_candidates.emplace_back(significance, cell.id);
        }
    }
    std::sort(ruin_candidates.begin(), ruin_candidates.end(), [](const auto& a, const auto& b) {
        if (a.first == b.first) {
            return a.second < b.second;
        }
        return a.first > b.first;
    });
    const int ruin_target = clamp(static_cast<int>(layers.cultures.size()) + static_cast<int>(settlements.size()) / 4, 2, 32);
    for (const auto& [significance, cell_id] : ruin_candidates) {
        bool too_close = false;
        for (const Ruin& ruin : layers.ruins) {
            if (angular_distance(cells[cell_id].p, cells[ruin.cell_id].p) < site_min_sep) {
                too_close = true;
                break;
            }
        }
        if (too_close) {
            continue;
        }
        const Cell& cell = cells[cell_id];
        Ruin ruin;
        ruin.id = static_cast<int>(layers.ruins.size());
        ruin.cell_id = cell_id;
        ruin.culture_region_id = cell.culture_region_id;
        ruin.language_region_id = cell.language_region_id;
        ruin.type = ruin_type_for_cell(cells, cell);
        ruin.abandonment_reason = abandonment_reason_for_cell(cell);
        ruin.significance = significance;
        ruin.preservation_score = clamp(
            0.35 + 0.20 * ((cell.biome == 9 || cell.biome == 10) ? 1.0 : 0.0) +
                0.20 * (cell.ice_thickness_m > 20.0 ? 1.0 : 0.0) -
                0.18 * (cell.precipitation_mm_y > 1200.0 ? 1.0 : 0.0),
            0.0,
            1.0
        );
        ruin.lat_deg = cell.lat * DEG;
        ruin.lon_deg = cell.lon * DEG;
        layers.ruins.push_back(ruin);
        layers.cultures[ruin.culture_region_id].ruin_count += 1;
        if (static_cast<int>(layers.ruins.size()) >= ruin_target) {
            break;
        }
    }

    for (CultureRegion& culture : layers.cultures) {
        culture.continuity_index = clamp(
            0.30 + 0.22 * culture.barrier_isolation +
                0.18 * culture.mean_fertility +
                0.10 * std::min(1.0, static_cast<double>(culture.settlement_count) / 6.0) +
                0.10 * std::min(1.0, static_cast<double>(culture.sacred_area_count) / 3.0) -
                0.16 * std::min(1.0, static_cast<double>(culture.ruin_count) / 4.0),
            0.0,
            1.0
        );
        culture.estimated_age_years = clamp(
            420.0 + 1900.0 * culture.continuity_index +
                520.0 * culture.barrier_isolation +
                260.0 * std::min(1.0, static_cast<double>(culture.settlement_count) / 8.0),
            120.0,
            4200.0
        );
    }

    return layers;
}

}  // namespace magic_geo::detail
