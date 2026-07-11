#include "internal.hpp"

namespace magic_geo::detail {

void derive_lake_overflow_stages(const Params& params, const std::vector<Cell>& cells, LakeBasin& basin) {
    basin.overflow_path_cell_ids.clear();
    basin.overflow_stage_count = 0;
    basin.overflow_path_length_km = 0.0;
    basin.avulsion_risk = 0.0;
    if (!basin.overflows || basin.spill_to_cell_id < 0 ||
        basin.spill_to_cell_id >= static_cast<int>(cells.size())) {
        return;
    }

    std::set<int> seen;
    int current = basin.outlet_cell_id;
    int next = basin.spill_to_cell_id;
    basin.overflow_path_cell_ids.push_back(current);
    for (int step = 0; step < 16; ++step) {
        if (current < 0 || current >= static_cast<int>(cells.size()) ||
            next < 0 || next >= static_cast<int>(cells.size())) {
            break;
        }
        if (!seen.insert(current).second) {
            break;
        }
        basin.overflow_path_length_km += neighbor_distance_m(params, cells[static_cast<std::size_t>(current)],
            cells[static_cast<std::size_t>(next)]) / 1000.0;
        if (basin.overflow_path_cell_ids.empty() || basin.overflow_path_cell_ids.back() != next) {
            basin.overflow_path_cell_ids.push_back(next);
        }
        const Cell& next_cell = cells[static_cast<std::size_t>(next)];
        const bool enters_other_depression = next_cell.depression_component_id >= 0 &&
            next_cell.depression_component_id != basin.depression_component_id;
        if (next_cell.is_water || enters_other_depression ||
            (next_cell.is_lake && next_cell.depression_component_id != basin.depression_component_id)) {
            break;
        }
        current = next;
        next = cells[static_cast<std::size_t>(current)].flow_to;
    }

    basin.overflow_stage_count = std::max(0, static_cast<int>(basin.overflow_path_cell_ids.size()) - 1);
    const double relief = basin.outlet_cell_id >= 0 && basin.outlet_cell_id < static_cast<int>(cells.size()) ?
        local_relief(cells, basin.outlet_cell_id) : 0.0;
    const double pressure = clamp(basin.overflow_index / 4.0, 0.0, 1.0);
    const double short_path = 1.0 / (1.0 + basin.overflow_path_length_km / 180.0);
    const double incision = clamp(basin.max_depression_depth_m / 180.0, 0.0, 1.0);
    const double relief_factor = clamp(relief / 1400.0, 0.0, 1.0);
    basin.avulsion_risk = clamp(0.42 * pressure + 0.24 * short_path + 0.20 * incision + 0.14 * relief_factor, 0.0, 1.0);
}

std::vector<LakeBasin> generate_lake_basins(const Params& params, std::vector<Cell>& cells) {
    for (Cell& cell : cells) {
        cell.lake_basin_id = -1;
    }

    std::map<int, std::vector<int>> depression_cells_by_component;
    for (const Cell& cell : cells) {
        if (!cell.is_water && cell.depression_component_id >= 0) {
            depression_cells_by_component[cell.depression_component_id].push_back(cell.id);
        }
    }

    std::vector<LakeBasin> basins;
    std::map<int, int> basin_by_component;
    for (const auto& [component_id, depression_cell_ids] : depression_cells_by_component) {
        if (depression_cell_ids.empty()) {
            throw std::runtime_error("empty depression component");
        }
        const int sink_id = cells[static_cast<std::size_t>(depression_cell_ids.front())].depression_sink_cell_id;
        if (sink_id < 0 || sink_id >= static_cast<int>(cells.size())) {
            throw std::runtime_error("depression component sink is invalid");
        }
        const Cell& sink = cells[static_cast<std::size_t>(sink_id)];
        LakeBasin basin;
        basin.id = static_cast<int>(basins.size());
        basin.depression_component_id = component_id;
        basin.outlet_cell_id = sink_id;
        basin.spill_to_cell_id = sink.spill_to;
        basin.depression_policy = sink.depression_policy;
        basin.water_body = sink.water_body;
        basin.is_geologic = is_geologic_depression(sink);
        basin.overflows = sink.lake_overflows;
        basin.outlet_elevation_m = sink.elevation_m;
        basin.spill_elevation_m = sink.spill_elevation_m;
        basin.fill_fraction = sink.lake_fill_fraction;
        double geologic_area_km2 = 0.0;
        for (int cell_id : depression_cell_ids) {
            const Cell& cell = cells[static_cast<std::size_t>(cell_id)];
            if (cell.depression_component_id != component_id ||
                cell.depression_sink_cell_id != sink_id ||
                cell.depression_policy != basin.depression_policy) {
                throw std::runtime_error("depression component metadata is inconsistent");
            }
            basin.depression_cell_count++;
            basin.depression_area_km2 += cell.area_km2;
            basin.max_depression_depth_m = std::max(basin.max_depression_depth_m, cell.depression_depth_m);
            basin.storage_capacity_km3 += cell.depression_depth_m * cell.area_km2 / 1000.0;
            if (is_geologic_depression(cell)) {
                geologic_area_km2 += cell.area_km2;
            }
            if (basin.water_body == 0 && cell.water_body != 0) {
                basin.water_body = cell.water_body;
            }
        }
        if (basin.depression_area_km2 > 0.0) {
            basin.geologic_area_fraction = geologic_area_km2 / basin.depression_area_km2;
        }
        basin_by_component[component_id] = basin.id;
        basins.push_back(basin);
    }

    std::vector<double> water_depth_sum(basins.size(), 0.0);
    for (Cell& cell : cells) {
        if (cell.is_water) {
            continue;
        }
        int current = cell.id;
        std::set<int> seen;
        while (current >= 0 && current < static_cast<int>(cells.size())) {
            const int component_id = cells[static_cast<std::size_t>(current)].depression_component_id;
            const auto found = basin_by_component.find(component_id);
            if (found != basin_by_component.end()) {
                LakeBasin& basin = basins[static_cast<std::size_t>(found->second)];
                cell.lake_basin_id = basin.id;
                basin.cell_count += 1;
                basin.area_km2 += cell.area_km2;
                basin.mean_runoff_mm_y += cell.runoff_mm_y * cell.area_km2;
                basin.annual_runoff_km3 += cell.runoff_mm_y * cell.area_km2 * 1.0e-6;
                if (cell.is_lake) {
                    basin.lake_cell_count += 1;
                    basin.lake_area_km2 += cell.area_km2;
                    water_depth_sum[static_cast<std::size_t>(basin.id)] += cell.water_depth_m * cell.area_km2;
                }
                break;
            }
            if (!seen.insert(current).second) {
                break;
            }
            const int next = cells[static_cast<std::size_t>(current)].flow_to;
            if (next < 0 || next >= static_cast<int>(cells.size()) || cells[static_cast<std::size_t>(next)].is_water) {
                break;
            }
            current = next;
        }
    }

    for (LakeBasin& basin : basins) {
        if (basin.area_km2 > 0.0) {
            basin.mean_runoff_mm_y /= basin.area_km2;
        }
        if (basin.lake_area_km2 > 0.0) {
            basin.mean_water_depth_m = water_depth_sum[static_cast<std::size_t>(basin.id)] / basin.lake_area_km2;
        }
        if (basin.overflows) {
            basin.overflow_index = clamp(basin.annual_runoff_km3 / std::max(0.001, basin.storage_capacity_km3), 0.0, 50.0);
        }
        derive_lake_overflow_stages(params, cells, basin);
    }
    return basins;
}

int watershed_outlet_type(const std::vector<Cell>& cells, int basin_id) {
    if (basin_id < 0 || basin_id >= static_cast<int>(cells.size())) {
        return 4;
    }
    const Cell& outlet = cells[basin_id];
    if (outlet.is_lake) {
        return outlet.water_body == 5 ? 2 : 1;
    }
    if (outlet.is_water) {
        if (outlet.water_body == 3) {
            return 3;
        }
        return 0;
    }
    if (outlet.water_body == 5) {
        return 2;
    }
    if (outlet.water_body == 4) {
        return 1;
    }
    return 4;
}

std::vector<LatLon> watershed_boundary_ring(
    const std::vector<Cell>& cells,
    const std::vector<int>& boundary_cell_ids,
    Vec3 weighted_center,
    int max_points
) {
    if (boundary_cell_ids.empty()) {
        return {};
    }
    const Vec3 center = normalize(weighted_center);
    const Vec3 ref = std::abs(center.z) < 0.92 ? Vec3{0.0, 0.0, 1.0} : Vec3{0.0, 1.0, 0.0};
    const Vec3 axis_x = normalize(cross(ref, center));
    const Vec3 axis_y = normalize(cross(center, axis_x));
    std::vector<std::pair<double, int>> ordered;
    ordered.reserve(boundary_cell_ids.size());
    for (int cell_id : boundary_cell_ids) {
        const Cell& cell = cells[cell_id];
        const double angle = std::atan2(dot(cell.p, axis_y), dot(cell.p, axis_x));
        ordered.emplace_back(angle, cell_id);
    }
    std::sort(ordered.begin(), ordered.end());

    const int target = std::min(max_points, static_cast<int>(ordered.size()));
    std::vector<LatLon> ring;
    ring.reserve(static_cast<std::size_t>(target + 1));
    if (target <= 0) {
        return ring;
    }
    for (int k = 0; k < target; ++k) {
        const int index = static_cast<int>(
            std::floor(static_cast<double>(k) * static_cast<double>(ordered.size()) / static_cast<double>(target))
        );
        const Cell& cell = cells[ordered[static_cast<std::size_t>(index)].second];
        ring.push_back({cell.lat * DEG, cell.lon * DEG});
    }
    if (ring.size() > 2) {
        ring.push_back(ring.front());
    }
    return ring;
}

Vec3 latlon_to_vec(const LatLon& point) {
    const double lat = point.lat_deg / DEG;
    const double lon = point.lon_deg / DEG;
    const double c = std::cos(lat);
    return {c * std::cos(lon), c * std::sin(lon), std::sin(lat)};
}

double ring_perimeter_km(const Params& params, const std::vector<LatLon>& ring) {
    if (ring.size() < 2) {
        return 0.0;
    }
    double perimeter = 0.0;
    for (std::size_t i = 1; i < ring.size(); ++i) {
        perimeter += angular_distance(latlon_to_vec(ring[i - 1]), latlon_to_vec(ring[i])) * params.radius_km;
    }
    return perimeter;
}

double ring_projected_area_km2(const Params& params, const std::vector<LatLon>& ring, Vec3 weighted_center) {
    if (ring.size() < 4) {
        return 0.0;
    }
    const Vec3 center = normalize(weighted_center);
    const Vec3 ref = std::abs(center.z) < 0.92 ? Vec3{0.0, 0.0, 1.0} : Vec3{0.0, 1.0, 0.0};
    const Vec3 axis_x = normalize(cross(ref, center));
    const Vec3 axis_y = normalize(cross(center, axis_x));
    std::vector<std::pair<double, double>> points;
    points.reserve(ring.size());
    for (const LatLon& point : ring) {
        const Vec3 p = latlon_to_vec(point);
        const double x = params.radius_km * dot(p, axis_x);
        const double y = params.radius_km * dot(p, axis_y);
        points.push_back({x, y});
    }
    double area = 0.0;
    for (std::size_t i = 1; i < points.size(); ++i) {
        area += points[i - 1].first * points[i].second - points[i].first * points[i - 1].second;
    }
    return std::abs(0.5 * area);
}

std::vector<Watershed> generate_watersheds(const Params& params, const std::vector<Cell>& cells) {
    std::map<int, Watershed> by_basin;
    std::map<int, Vec3> centroid_sum;
    std::map<int, std::vector<int>> watershed_cells;
    std::map<int, std::vector<int>> boundary_cells;
    for (const Cell& cell : cells) {
        if (cell.is_water || cell.basin_id < 0 || cell.basin_id >= static_cast<int>(cells.size())) {
            continue;
        }
        Watershed& watershed = by_basin[cell.basin_id];
        watershed.basin_id = cell.basin_id;
        watershed.outlet_cell_id = cell.basin_id;
        watershed.cell_count += 1;
        watershed.area_km2 += cell.area_km2;
        watershed.mean_runoff_mm_y += cell.runoff_mm_y;
        watershed.mean_elevation_m += cell.elevation_m;
        watershed.max_flow_accumulation = std::max(watershed.max_flow_accumulation, cell.flow_accumulation);
        centroid_sum[cell.basin_id] = add(centroid_sum[cell.basin_id], mul(cell.p, cell.area_km2));
        watershed_cells[cell.basin_id].push_back(cell.id);
        const double lat_deg = cell.lat * DEG;
        if (watershed.cell_count == 1) {
            watershed.min_lat_deg = lat_deg;
            watershed.max_lat_deg = lat_deg;
        } else {
            watershed.min_lat_deg = std::min(watershed.min_lat_deg, lat_deg);
            watershed.max_lat_deg = std::max(watershed.max_lat_deg, lat_deg);
        }
        bool boundary = false;
        for (int neighbor_id : cell.neighbors) {
            const Cell& neighbor = cells[neighbor_id];
            if (neighbor.is_water || neighbor.basin_id != cell.basin_id) {
                boundary = true;
                break;
            }
        }
        if (boundary) {
            boundary_cells[cell.basin_id].push_back(cell.id);
        }
        if (cell.is_river) {
            watershed.river_cell_count += 1;
        }
    }

    std::vector<Watershed> watersheds;
    watersheds.reserve(by_basin.size());
    for (auto& [basin_id, watershed] : by_basin) {
        if (watershed.cell_count <= 0) {
            continue;
        }
        watershed.mean_runoff_mm_y /= static_cast<double>(watershed.cell_count);
        watershed.mean_elevation_m /= static_cast<double>(watershed.cell_count);
        watershed.outlet_type = watershed_outlet_type(cells, basin_id);
        watershed.is_endorheic = watershed.outlet_type != 0;
        const Vec3 center = normalize(centroid_sum[basin_id]);
        watershed.centroid_lat_deg = std::asin(clamp(center.z, -1.0, 1.0)) * DEG;
        watershed.centroid_lon_deg = std::atan2(center.y, center.x) * DEG;
        double min_unwrapped_lon = std::numeric_limits<double>::infinity();
        double max_unwrapped_lon = -std::numeric_limits<double>::infinity();
        const double centroid_lon_rad = watershed.centroid_lon_deg / DEG;
        for (int cell_id : watershed_cells[basin_id]) {
            const double unwrapped = watershed.centroid_lon_deg + wrap_angle(cells[cell_id].lon - centroid_lon_rad) * DEG;
            min_unwrapped_lon = std::min(min_unwrapped_lon, unwrapped);
            max_unwrapped_lon = std::max(max_unwrapped_lon, unwrapped);
        }
        watershed.lon_span_deg = std::max(0.0, max_unwrapped_lon - min_unwrapped_lon);
        watershed.crosses_antimeridian = min_unwrapped_lon < -180.0 || max_unwrapped_lon > 180.0;
        watershed.min_lon_deg = wrap_angle(min_unwrapped_lon / DEG) * DEG;
        watershed.max_lon_deg = wrap_angle(max_unwrapped_lon / DEG) * DEG;
        std::vector<int>& boundary = boundary_cells[basin_id];
        std::sort(boundary.begin(), boundary.end());
        boundary.erase(std::unique(boundary.begin(), boundary.end()), boundary.end());
        watershed.boundary_cell_ids = boundary;
        watershed.boundary_ring = watershed_boundary_ring(cells, watershed.boundary_cell_ids, centroid_sum[basin_id], 64);
        watershed.boundary_perimeter_km = ring_perimeter_km(params, watershed.boundary_ring);
        watershed.dissolved_polygon_area_km2 = ring_projected_area_km2(params, watershed.boundary_ring, centroid_sum[basin_id]);
        if (watershed.area_km2 > 0.0 && watershed.dissolved_polygon_area_km2 > 0.0) {
            watershed.polygon_area_error_fraction = std::abs(watershed.dissolved_polygon_area_km2 - watershed.area_km2) /
                std::max(1.0, watershed.area_km2);
        }
        if (watershed.boundary_perimeter_km > 0.0 && watershed.dissolved_polygon_area_km2 > 0.0) {
            watershed.compactness_index = clamp(
                4.0 * PI * watershed.dissolved_polygon_area_km2 /
                    std::max(1.0, watershed.boundary_perimeter_km * watershed.boundary_perimeter_km),
                0.0,
                1.0
            );
        }
        const double ring_quality = clamp(static_cast<double>(watershed.boundary_ring.size()) / 24.0, 0.0, 1.0);
        const double area_quality = clamp(1.0 - watershed.polygon_area_error_fraction, 0.0, 1.0);
        watershed.geometry_quality = clamp(0.62 * area_quality + 0.38 * ring_quality, 0.0, 1.0);
        watersheds.push_back(watershed);
    }
    std::sort(watersheds.begin(), watersheds.end(), [](const Watershed& a, const Watershed& b) {
        if (a.area_km2 == b.area_km2) {
            return a.basin_id < b.basin_id;
        }
        return a.area_km2 > b.area_km2;
    });
    for (int i = 0; i < static_cast<int>(watersheds.size()); ++i) {
        watersheds[static_cast<std::size_t>(i)].id = i;
    }
    return watersheds;
}

}  // namespace magic_geo::detail
