#include "internal.hpp"

namespace magic_geo::detail {

double apply_sea_level(const Params& params, std::vector<Cell>& cells) {
    const int n = static_cast<int>(cells.size());
    if (n == 0) {
        return 0.0;
    }

    std::vector<int> order(static_cast<std::size_t>(n));
    std::iota(order.begin(), order.end(), 0);
    std::sort(order.begin(), order.end(), [&](int a, int b) {
        if (cells[a].elevation_m == cells[b].elevation_m) {
            return a < b;
        }
        return cells[a].elevation_m < cells[b].elevation_m;
    });

    const double total_area_km2 = std::accumulate(
        cells.begin(),
        cells.end(),
        0.0,
        [](double total, const Cell& cell) { return total + std::max(0.0, cell.area_km2); }
    );
    if (total_area_km2 <= 0.0) {
        throw std::runtime_error("sea-level selection requires positive cell areas");
    }
    const double target_volume_km3 = params.ocean_water_inventory_km3;
    if (target_volume_km3 <= 0.0) {
        const double sea_level = std::nextafter(
            cells[order.front()].elevation_m,
            -std::numeric_limits<double>::infinity()
        );
        for (Cell& cell : cells) {
            shift_sediment_interface_datum(
                cell,
                -sea_level,
                "zero-ocean sea-level datum"
            );
            cell.is_water = false;
            cell.water_depth_m = 0.0;
            cell.water_body = 0;
            cell.is_lake = false;
        }
        return sea_level;
    }

    std::vector<int> parent(static_cast<std::size_t>(n));
    std::vector<int> component_size(static_cast<std::size_t>(n), 1);
    std::vector<double> component_area_km2(static_cast<std::size_t>(n), 0.0);
    std::vector<double> component_elevation_area_m_km2(static_cast<std::size_t>(n), 0.0);
    std::vector<int> component_min_id(static_cast<std::size_t>(n), 0);
    std::vector<bool> active(static_cast<std::size_t>(n), false);
    std::iota(parent.begin(), parent.end(), 0);
    for (int i = 0; i < n; ++i) {
        component_area_km2[static_cast<std::size_t>(i)] = std::max(0.0, cells[i].area_km2);
        component_elevation_area_m_km2[static_cast<std::size_t>(i)] =
            component_area_km2[static_cast<std::size_t>(i)] * cells[i].elevation_m;
        component_min_id[static_cast<std::size_t>(i)] = i;
    }
    const auto find_root = [&](int start) {
        int root = start;
        while (parent[root] != root) {
            root = parent[root];
        }
        int current = start;
        while (parent[current] != current) {
            const int next = parent[current];
            parent[current] = root;
            current = next;
        }
        return root;
    };
    const auto merge = [&](int a, int b) {
        int root_a = find_root(a);
        int root_b = find_root(b);
        if (root_a == root_b) {
            return root_a;
        }
        if (component_size[root_a] < component_size[root_b] ||
            (component_size[root_a] == component_size[root_b] && root_b < root_a)) {
            std::swap(root_a, root_b);
        }
        parent[root_b] = root_a;
        component_size[root_a] += component_size[root_b];
        component_area_km2[root_a] += component_area_km2[root_b];
        component_elevation_area_m_km2[root_a] += component_elevation_area_m_km2[root_b];
        component_min_id[root_a] = std::min(component_min_id[root_a], component_min_id[root_b]);
        return root_a;
    };

    double best_error_km3 = std::numeric_limits<double>::infinity();
    double best_connected_area_km2 = 0.0;
    double best_flood_elevation = cells[order.front()].elevation_m;
    double best_sea_level = std::nextafter(
        best_flood_elevation,
        std::numeric_limits<double>::infinity()
    );
    int largest_component_root = -1;
    bool exact_solution_found = false;
    const auto consider_candidate = [&](double sea_level, int component_root, double flood_elevation) {
        if (!std::isfinite(sea_level) || component_root < 0) {
            return;
        }
        component_root = find_root(component_root);
        const double area_km2 = component_area_km2[component_root];
        if (area_km2 <= 0.0) {
            return;
        }
        const double volume_km3 = std::max(
            0.0,
            (area_km2 * sea_level - component_elevation_area_m_km2[component_root]) / 1000.0
        );
        const double error_km3 = std::abs(volume_km3 - target_volume_km3);
        if (
            error_km3 < best_error_km3 ||
            (error_km3 == best_error_km3 && sea_level < best_sea_level)
        ) {
            best_error_km3 = error_km3;
            best_connected_area_km2 = area_km2;
            best_flood_elevation = flood_elevation;
            best_sea_level = sea_level;
        }
    };
    std::size_t position = 0;
    while (position < order.size()) {
        const double elevation = cells[order[position]].elevation_m;
        std::size_t end = position;
        while (end < order.size() && cells[order[end]].elevation_m == elevation) {
            active[static_cast<std::size_t>(order[end])] = true;
            ++end;
        }
        for (std::size_t index = position; index < end; ++index) {
            const int cell_id = order[index];
            for (int neighbor_id : cells[cell_id].neighbors) {
                if (neighbor_id >= 0 && neighbor_id < n && active[static_cast<std::size_t>(neighbor_id)]) {
                    merge(cell_id, neighbor_id);
                }
            }
        }
        if (largest_component_root >= 0) {
            largest_component_root = find_root(largest_component_root);
        }
        for (std::size_t index = position; index < end; ++index) {
            const int root = find_root(order[index]);
            if (
                largest_component_root < 0 ||
                component_area_km2[root] > component_area_km2[largest_component_root] ||
                (component_area_km2[root] == component_area_km2[largest_component_root] &&
                    component_min_id[root] < component_min_id[largest_component_root])
            ) {
                largest_component_root = root;
            }
        }
        largest_component_root = find_root(largest_component_root);
        const double component_area = component_area_km2[largest_component_root];
        const double component_elevation_area =
            component_elevation_area_m_km2[largest_component_root];
        const double solved_sea_level =
            (target_volume_km3 * 1000.0 + component_elevation_area) / component_area;
        const double next_elevation = end < order.size()
            ? cells[order[end]].elevation_m
            : std::numeric_limits<double>::infinity();
        const double interval_lower = std::nextafter(
            elevation,
            std::numeric_limits<double>::infinity()
        );
        consider_candidate(interval_lower, largest_component_root, elevation);
        if (solved_sea_level >= interval_lower && solved_sea_level < next_elevation) {
            consider_candidate(solved_sea_level, largest_component_root, elevation);
            exact_solution_found = true;
        } else if (std::isfinite(next_elevation)) {
            const double interval_upper = std::nextafter(next_elevation, elevation);
            if (interval_upper >= interval_lower) {
                consider_candidate(interval_upper, largest_component_root, elevation);
            }
        } else if (solved_sea_level >= interval_lower) {
            consider_candidate(solved_sea_level, largest_component_root, elevation);
            exact_solution_found = true;
        }
        position = end;
        if (exact_solution_found) {
            break;
        }
    }

    std::vector<bool> below_level(static_cast<std::size_t>(n), false);
    for (int i = 0; i < n; ++i) {
        below_level[static_cast<std::size_t>(i)] = cells[i].elevation_m <= best_flood_elevation;
    }
    std::vector<bool> visited(static_cast<std::size_t>(n), false);
    std::vector<int> ocean_component;
    double ocean_component_area_km2 = 0.0;
    int ocean_component_min_id = std::numeric_limits<int>::max();
    for (int start_id : order) {
        if (!below_level[static_cast<std::size_t>(start_id)] || visited[static_cast<std::size_t>(start_id)]) {
            continue;
        }
        std::vector<int> component;
        double component_area = 0.0;
        int component_min_id = start_id;
        std::queue<int> queue;
        queue.push(start_id);
        visited[static_cast<std::size_t>(start_id)] = true;
        while (!queue.empty()) {
            const int current = queue.front();
            queue.pop();
            component.push_back(current);
            component_area += std::max(0.0, cells[current].area_km2);
            component_min_id = std::min(component_min_id, current);
            for (int neighbor_id : cells[current].neighbors) {
                if (
                    neighbor_id >= 0 && neighbor_id < n &&
                    below_level[static_cast<std::size_t>(neighbor_id)] &&
                    !visited[static_cast<std::size_t>(neighbor_id)]
                ) {
                    visited[static_cast<std::size_t>(neighbor_id)] = true;
                    queue.push(neighbor_id);
                }
            }
        }
        if (
            component_area > ocean_component_area_km2 ||
            (component_area == ocean_component_area_km2 && component_min_id < ocean_component_min_id)
        ) {
            ocean_component = std::move(component);
            ocean_component_area_km2 = component_area;
            ocean_component_min_id = component_min_id;
        }
    }
    if (
        std::abs(ocean_component_area_km2 - best_connected_area_km2) >
        std::max(1.0e-6, best_connected_area_km2 * 1.0e-12)
    ) {
        throw std::runtime_error("connectivity-constrained sea-level reconstruction mismatch");
    }

    const double sea_level = best_sea_level;
    std::vector<bool> is_ocean(static_cast<std::size_t>(n), false);
    for (int cell_id : ocean_component) {
        is_ocean[static_cast<std::size_t>(cell_id)] = true;
    }
    for (int i = 0; i < n; ++i) {
        shift_sediment_interface_datum(
            cells[i],
            -sea_level,
            "sea-level datum"
        );
        cells[i].is_water = is_ocean[static_cast<std::size_t>(i)];
        if (cells[i].is_water && !(cells[i].elevation_m < 0.0)) {
            // The flood interval selects cells strictly below best_sea_level,
            // but independently rounded bedrock and mobile-sediment operands
            // can cancel back to signed zero when the datum is composed. Move
            // only the bedrock operand to the immediately lower representable
            // value so the canonical interface preserves the discrete wet
            // decision without a finite empirical depth adjustment.
            cells[i].bedrock_surface_elevation_m = std::nextafter(
                -cells[i].sediment_thickness_m,
                -std::numeric_limits<double>::infinity()
            );
            cells[i].elevation_m =
                cells[i].bedrock_surface_elevation_m +
                cells[i].sediment_thickness_m;
            validate_sediment_interface(
                cells[i],
                "sea-level selected-ocean strict-depth tie"
            );
        }
        cells[i].water_depth_m = cells[i].is_water ? -cells[i].elevation_m : 0.0;
        cells[i].water_body = cells[i].is_water ? 1 : 0;
        cells[i].is_lake = false;
    }
    return sea_level;
}

void label_marine_water_bodies(std::vector<Cell>& cells) {
    const int n = static_cast<int>(cells.size());
    std::vector<int> component(n, -1);
    std::vector<int> sizes;
    int component_id = 0;
    for (int i = 0; i < n; ++i) {
        if (!cells[i].is_water || component[i] >= 0) {
            continue;
        }
        int size = 0;
        std::queue<int> queue;
        queue.push(i);
        component[i] = component_id;
        while (!queue.empty()) {
            const int current = queue.front();
            queue.pop();
            ++size;
            for (int neighbor : cells[current].neighbors) {
                if (cells[neighbor].is_water && component[neighbor] < 0) {
                    component[neighbor] = component_id;
                    queue.push(neighbor);
                }
            }
        }
        sizes.push_back(size);
        ++component_id;
    }
    int largest_component = -1;
    int largest_size = -1;
    for (int id = 0; id < static_cast<int>(sizes.size()); ++id) {
        if (sizes[id] > largest_size) {
            largest_size = sizes[id];
            largest_component = id;
        }
    }
    for (int i = 0; i < n; ++i) {
        if (!cells[i].is_water) {
            cells[i].water_body = 0;
        } else if (component[i] == largest_component) {
            cells[i].water_body = cells[i].water_depth_m < 220.0 ? 2 : 1;
        } else {
            cells[i].water_body = 3;
        }
    }
}

std::vector<int> ocean_distance(const std::vector<Cell>& cells) {
    const int n = static_cast<int>(cells.size());
    std::vector<int> distance(n, std::numeric_limits<int>::max());
    std::queue<int> queue;
    for (int i = 0; i < n; ++i) {
        if (cells[i].is_water) {
            distance[i] = 0;
            queue.push(i);
        }
    }
    while (!queue.empty()) {
        const int i = queue.front();
        queue.pop();
        for (int j : cells[i].neighbors) {
            if (distance[j] == std::numeric_limits<int>::max()) {
                distance[j] = distance[i] + 1;
                queue.push(j);
            }
        }
    }
    for (int& d : distance) {
        if (d == std::numeric_limits<int>::max()) {
            d = n;
        }
    }
    return distance;
}

}  // namespace magic_geo::detail
