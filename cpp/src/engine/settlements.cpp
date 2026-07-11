#include "internal.hpp"

namespace magic_geo::detail {

int settlement_type_for_cell(const std::vector<Cell>& cells, const Cell& cell) {
    const bool coast = has_ocean_neighbor(cells, cell.id);
    if (coast) {
        return 1;
    }
    if (cell.is_river) {
        return 0;
    }
    if (cell.resource == 1 || cell.resource == 2 || cell.resource == 5 || cell.resource == 6) {
        return 2;
    }
    if (cell.fertility > 0.66 || cell.resource == 7) {
        return 3;
    }
    if ((cell.biome == 9 || cell.biome == 10) && (cell.runoff_mm_y > 120.0 || cell.is_lake)) {
        return 4;
    }
    return 5;
}

std::vector<Settlement> generate_settlements(const Params& params, const std::vector<Cell>& cells) {
    (void)params;
    std::vector<int> candidates;
    candidates.reserve(cells.size() / 8);
    for (const Cell& cell : cells) {
        if (cell.is_water || cell.settlement_score < 0.48) {
            continue;
        }
        bool local_max = true;
        for (int neighbor : cell.neighbors) {
            if (!cells[neighbor].is_water && cells[neighbor].settlement_score > cell.settlement_score) {
                local_max = false;
                break;
            }
        }
        if (local_max) {
            candidates.push_back(cell.id);
        }
    }
    std::sort(candidates.begin(), candidates.end(), [&](int a, int b) {
        if (cells[a].settlement_score == cells[b].settlement_score) {
            return a < b;
        }
        return cells[a].settlement_score > cells[b].settlement_score;
    });

    const int target = clamp(static_cast<int>(cells.size()) / 180, 8, 64);
    const double min_sep = 2.4 * std::sqrt(
        4.0 * PI / static_cast<double>(std::max<std::size_t>(1, cells.size()))
    );
    std::vector<Settlement> settlements;
    for (int cell_id : candidates) {
        bool too_close = false;
        for (const Settlement& settlement : settlements) {
            if (angular_distance(cells[cell_id].p, cells[settlement.cell_id].p) < min_sep) {
                too_close = true;
                break;
            }
        }
        if (too_close) {
            continue;
        }
        Settlement settlement;
        settlement.id = static_cast<int>(settlements.size());
        settlement.cell_id = cell_id;
        settlement.type = settlement_type_for_cell(cells, cells[cell_id]);
        settlement.score = cells[cell_id].settlement_score;
        settlements.push_back(settlement);
        if (static_cast<int>(settlements.size()) >= target) {
            break;
        }
    }
    return settlements;
}

double route_barrier_cost(const Cell& a, const Cell& b) {
    const double mountain = clamp((std::max(a.elevation_m, b.elevation_m) - 1200.0) / 2600.0, 0.0, 1.0);
    const double tectonic_hazard = 0.5 * (a.boundary_convergent + b.boundary_convergent) +
        0.25 * (a.boundary_transform + b.boundary_transform);
    const double arid = (a.biome == 9 || a.biome == 10 || b.biome == 9 || b.biome == 10) ? 0.18 : 0.0;
    return 1.0 + 0.95 * mountain + 0.45 * clamp(tectonic_hazard, 0.0, 1.0) + arid;
}

int route_type_for_pair(const std::vector<Cell>& cells, const Settlement& a, const Settlement& b) {
    const Cell& ca = cells[a.cell_id];
    const Cell& cb = cells[b.cell_id];
    if (a.type == 1 && b.type == 1) {
        return 2;
    }
    if (ca.is_river && cb.is_river && ca.basin_id == cb.basin_id) {
        return 1;
    }
    if (ca.elevation_m > 1300.0 || cb.elevation_m > 1300.0 || ca.boundary_convergent > 0.24 || cb.boundary_convergent > 0.24) {
        return 3;
    }
    return 0;
}

std::vector<Route> generate_routes(const Params& params, const std::vector<Cell>& cells, const std::vector<Settlement>& settlements) {
    std::vector<Route> routes;
    std::set<std::pair<int, int>> used;
    for (const Settlement& settlement : settlements) {
        std::vector<std::pair<double, int>> ranked;
        for (const Settlement& other : settlements) {
            if (settlement.id == other.id) {
                continue;
            }
            const Cell& a = cells[settlement.cell_id];
            const Cell& b = cells[other.cell_id];
            const double distance_km = angular_distance(a.p, b.p) * params.radius_km;
            double cost = distance_km * route_barrier_cost(a, b);
            if (settlement.type == 1 && other.type == 1) {
                cost *= 0.68;
            } else if (a.basin_id == b.basin_id && (a.is_river || b.is_river)) {
                cost *= 0.78;
            }
            ranked.emplace_back(cost, other.id);
        }
        std::sort(ranked.begin(), ranked.end());
        const int links = std::min(2, static_cast<int>(ranked.size()));
        for (int i = 0; i < links; ++i) {
            const int a_id = std::min(settlement.id, ranked[i].second);
            const int b_id = std::max(settlement.id, ranked[i].second);
            if (!used.insert({a_id, b_id}).second) {
                continue;
            }
            const Settlement& from = settlements[static_cast<std::size_t>(a_id)];
            const Settlement& to = settlements[static_cast<std::size_t>(b_id)];
            const double distance_km = angular_distance(cells[from.cell_id].p, cells[to.cell_id].p) * params.radius_km;
            Route route;
            route.id = static_cast<int>(routes.size());
            route.from = a_id;
            route.to = b_id;
            route.type = route_type_for_pair(cells, from, to);
            route.distance_km = distance_km;
            route.cost = distance_km * route_barrier_cost(cells[from.cell_id], cells[to.cell_id]);
            if (route.type == 2) {
                route.cost *= 0.68;
            } else if (route.type == 1) {
                route.cost *= 0.78;
            }
            routes.push_back(route);
        }
    }
    return routes;
}

}  // namespace magic_geo::detail
