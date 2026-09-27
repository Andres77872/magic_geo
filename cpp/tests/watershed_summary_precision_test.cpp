#include "internal.hpp"
#include <iostream>

using namespace magic_geo;
using namespace magic_geo::detail;

namespace {
double field(const std::string& json, const std::string& key) {
    const std::string marker = "\"" + key + "\":";
    const auto position = json.find(marker);
    if (position == std::string::npos) throw std::runtime_error("missing field: " + key);
    return std::stod(json.substr(position + marker.size()));
}

void check(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

void verify(int precision, const std::vector<double>& areas) {
    Params params;
    params.float_precision = precision;
    Cell cell;
    cell.id = 0;
    cell.area_km2 = 1.0;
    cell.p = {1.0, 0.0, 0.0};
    std::vector<Watershed> watersheds;
    std::vector<const Watershed*> visible;
    for (double area : areas) {
        Watershed watershed;
        watershed.id = static_cast<int>(watersheds.size());
        watershed.dissolved_polygon_area_km2 = area;
        watershed.polygon_area_error_fraction = (watershed.id + 1) * 0.1;
        watershed.compactness_index = (watershed.id + 1) * 0.05;
        watershed.geometry_quality = (watershed.id + 1) * 0.08;
        watershed.boundary_perimeter_km = (watershed.id + 1) * 20.0;
        watersheds.push_back(watershed);
    }
    std::cout << "{\"precision\":" << precision << ",\"raw_areas_km2\":"
              << roundtrip_double_array_json(areas) << ",\"published_areas_km2\":[";
    bool first = true;
    for (const Watershed& watershed : watersheds) {
        // Read the actual entity serializer, independently of the summary's
        // membership predicate and any proposed decimal rounding approximation.
        const double published = field(watersheds_json({watershed}, precision), "dissolved_polygon_area_km2");
        if (!first) std::cout << ',';
        first = false;
        std::cout << roundtrip_num(published);
        if (published > 0.0) visible.push_back(&watershed);
    }
    const auto summary = summary_json(params, {cell}, watersheds,
        {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {});
    std::cout << "],\"published_positive_count\":" << visible.size()
              << ",\"summary_count\":" << field(summary, "watershed_polygon_count") << "}" << std::endl;
    check(field(summary, "watershed_polygon_count") == static_cast<double>(visible.size()),
          "watershed count differs from published positive areas at precision " + std::to_string(precision));
    for (const auto& [key, member] : std::vector<std::pair<const char*, double Watershed::*>>{
        {"mean_watershed_polygon_area_error_fraction", &Watershed::polygon_area_error_fraction},
        {"mean_watershed_compactness_index", &Watershed::compactness_index},
        {"mean_watershed_geometry_quality", &Watershed::geometry_quality},
        {"mean_watershed_boundary_perimeter_km", &Watershed::boundary_perimeter_km}}) {
        double total = 0.0;
        for (const Watershed* watershed : visible) total += watershed->*member;
        const double mean = visible.empty() ? 0.0 : total / static_cast<double>(visible.size());
        check(field(summary, key) == std::stod(num(mean, precision)),
              std::string(key) + " includes a polygon whose published area is zero");
    }
}
}

int main() {
    try {
        for (int precision = 0; precision <= 8; ++precision) {
            const double unit = std::pow(10.0, -precision);
            const double half = unit * 0.5;
            verify(precision, {0.0, unit * 0.25});
            verify(precision, {0.0, unit * 0.25, std::nextafter(half, 0.0), half,
                               std::nextafter(half, 1.0), unit, 4.25});
        }
        verify(4, {1e-10, 10.0});
    } catch (const std::exception& error) {
        std::cerr << error.what() << std::endl;
        return 1;
    }
}
