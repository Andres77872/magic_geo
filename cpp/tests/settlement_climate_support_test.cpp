#include "internal.hpp"
#include "settlement_climate_support.hpp"

#include <fstream>
#include <iostream>
#include <tuple>

using namespace magic_geo;
using namespace magic_geo::detail;

void check(bool ok, const char* message) {
    if (!ok) throw std::runtime_error(message);
}

std::vector<Cell> example(double temperature) {
    std::vector<Cell> cells(3);
    for (int i = 0; i < 3; ++i) {
        Cell& c = cells[i];
        c.id = i; c.p = {std::cos(i * 2.0), std::sin(i * 2.0), 0};
        c.lon = i * 2.0; c.area_km2 = 100; c.elevation_m = 80;
        c.temperature_c = temperature; c.precipitation_mm_y = 1600;
        c.temperature_monthly_c.fill(temperature);
        c.precipitation_monthly_mm.fill(1600.0 / 12);
        c.runoff_mm_y = 800; c.is_river = true; c.sediment_thickness_m = 1.0;
        c.lithology = 5; c.crust_type = 1; c.water_body = 0;
    }
    // Hot/temperate alluvial delta immediately next to marine water.
    cells[0].neighbors = {1}; cells[0].flow_to = 1;
    cells[1].neighbors = {0}; cells[1].is_water = true; cells[1].is_river = false;
    cells[1].water_body = 2; cells[1].elevation_m = -80; cells[1].water_depth_m = 80;
    return cells;
}

auto material(const Cell& c) {
    return std::tuple(c.fertility, c.soil_depth_m, c.soil_type, c.biome, c.landform,
        c.resource, c.elevation_m, c.sediment_thickness_m, c.temperature_c,
        c.temperature_monthly_c, c.precipitation_mm_y, c.precipitation_monthly_mm);
}

std::string world(Params params, std::vector<Cell> cells) {
    const auto settlements = [&] { return generate_settlements(params, cells); }();
    auto mutable_settlements = settlements;
    auto routes = generate_routes(params, cells, mutable_settlements);
    auto regions = generate_political_regions(params, cells, mutable_settlements, routes);
    return "{\"cells\":" + cells_json(cells, params.float_precision, params.temperature_model) +
        ",\"settlements\":" + settlements_json(cells, mutable_settlements, params.float_precision) +
        ",\"routes\":" + routes_json(routes, params.float_precision) +
        ",\"political_regions\":" + political_regions_json(regions, params.float_precision) +
        ",\"planet_parameters\":{\"radius_km\":" + roundtrip_num(params.radius_km) + "}" +
        ",\"summary\":{\"output_float_precision\":" + std::to_string(params.float_precision) +
        ",\"cell_count\":" + std::to_string(cells.size()) +
        ",\"settlement_count\":" + std::to_string(settlements.size()) +
        ",\"route_count\":" + std::to_string(routes.size()) +
        ",\"political_region_count\":" + std::to_string(regions.size()) +
        ",\"top_settlement_score\":" + num(settlements.empty() ? 0.0 : settlements.front().score, std::max(8, params.float_precision)) + "}}";
}

std::vector<Cell> prepare(const Params& params, double temperature) {
    auto cells = example(temperature);
    derive_soils_biomes_resources(params, cells);
    derive_landforms(cells);
    return cells;
}

void units(const char* output) {
    const double infinity = std::numeric_limits<double>::infinity();
    for (double t : {-infinity, -1000.0, -14.0, 48.0, 1000.0, infinity,
        std::numeric_limits<double>::quiet_NaN()}) {
        check(!settlement_annual_climate_supported(t), "unsupported endpoint/nonfinite accepted");
    }
    for (double t : {std::nextafter(-14.0, infinity), 17.0, std::nextafter(48.0, -infinity)}) {
        check(settlement_annual_climate_supported(t), "strictly interior source rejected");
    }
    Params seasonal, legacy;
    legacy.temperature_model = ClimateTemperatureModel::legacy_empirical;
    seasonal.float_precision = legacy.float_precision = 8;
    auto hot = prepare(seasonal, 85.0);
    check(hot[0].landform == 12 && hot[0].settlement_score >= 0.48, "missing favorable hot delta witness");
    const auto before = hot;
    finalize_settlement_climate_applicability(seasonal, hot);
    for (int i = 0; i < 3; ++i) {
        check(material(hot[i]) == material(before[i]), "applicability changed material/climate descriptors");
        check(!hot[i].settlement_climate_supported && hot[i].settlement_score == 0, "landform bonus bypassed support");
    }
    check(generate_settlements(seasonal, hot).empty(), "unsupported settlement was generated");
    const auto finalized = hot;
    finalize_settlement_climate_applicability(seasonal, hot);
    check(cells_json(hot, 8, seasonal.temperature_model) == cells_json(finalized, 8, seasonal.temperature_model), "finalizer not idempotent");

    auto old = before;
    const auto old_json = cells_json(old, 8);
    const auto old_selected = generate_settlements(legacy, old);
    finalize_settlement_climate_applicability(legacy, old);
    check(cells_json(old, 8) == old_json && !old_selected.empty(), "legacy path changed");
    check(old_json.find("settlement_climate_") == std::string::npos, "legacy serialized new field");

    for (double t : {std::nextafter(-14.0, infinity), 0.0, 17.0, 38.0, std::nextafter(48.0, -infinity)}) {
        auto cells = prepare(seasonal, t);
        const auto prior = cells;
        finalize_settlement_climate_applicability(seasonal, cells);
        for (int i = 0; i < 3; ++i) {
            check(cells[i].settlement_climate_supported, "supported water/land flag false");
            check(cells[i].settlement_score == prior[i].settlement_score && material(cells[i]) == material(prior[i]), "supported score parity changed");
        }
    }

    auto contaminated = example(17.0);
    contaminated[0].neighbors = {1}; contaminated[0].settlement_score = 0.6;
    contaminated[1].is_water = false; contaminated[1].temperature_c = 85; contaminated[1].settlement_score = 1;
    contaminated[2].settlement_score = 0;
    const auto current = generate_settlements(seasonal, contaminated);
    check(current.size() == 1 && current[0].cell_id == 0, "unsupported neighbor suppressed supported candidate");
    const auto previous = generate_settlements(legacy, contaminated);
    check(previous.size() == 1 && previous[0].cell_id == 1, "legacy local maximum changed");
    contaminated[0].is_lake = true;
    check(generate_settlements(seasonal, contaminated).empty(), "standing lake became eligible");
    contaminated[0].is_lake = false; contaminated[0].water_body = 5;
    check(generate_settlements(seasonal, contaminated).size() == 1, "dry saline basin mistaken for standing lake");

    auto missing = prepare(seasonal, 17);
    bool rejected = false;
    try { cells_json(missing, 4, seasonal.temperature_model); }
    catch (const std::runtime_error&) { rejected = true; }
    check(rejected, "unfinalized seasonal serialization did not fail closed");

    if (output) {
        auto supported = prepare(seasonal, 17); finalize_settlement_climate_applicability(seasonal, supported);
        auto inside = prepare(seasonal, std::nextafter(48.0, -infinity)); finalize_settlement_climate_applicability(seasonal, inside);
        auto endpoint = prepare(seasonal, 48); finalize_settlement_climate_applicability(seasonal, endpoint);
        std::ofstream stream(output);
        stream << "{\"supported\":" << world(seasonal, supported) << ",\"hot\":" << world(seasonal, hot)
            << ",\"inside\":" << world(seasonal, inside) << ",\"endpoint\":" << world(seasonal, endpoint)
            << ",\"legacy\":" << world(legacy, old) << "}";
        check(bool(stream), "cannot write native unit artifacts");
    }
    std::cout << "native settlement applicability units passed\n";
}

void archive(const char* input, const char* output) {
    std::ifstream stream(input);
    std::size_t n; double radius;
    stream >> n >> radius;
    check(n > 0 && n <= 4096, "invalid archived cell count");
    std::vector<Cell> cells(n);
    for (Cell& c : cells) {
        stream >> c.id >> c.p.x >> c.p.y >> c.p.z >> c.lat >> c.lon >> c.area_km2
            >> c.elevation_m >> c.temperature_c >> c.precipitation_mm_y >> c.runoff_mm_y
            >> c.ice_thickness_m >> c.sediment_thickness_m >> c.glacial_erosion_m
            >> c.boundary_convergent >> c.boundary_divergent >> c.boundary_transform
            >> c.crust_type >> c.lithology >> c.crust_age_ma >> c.water_body
            >> c.is_water >> c.is_lake >> c.is_river >> c.is_closed_basin >> c.flow_to >> c.water_depth_m;
        for (double& t : c.temperature_monthly_c) stream >> t;
        for (double& p : c.precipitation_monthly_mm) stream >> p;
        // Reproduce the native annual-temperature accumulation from retained
        // binary64 month moments/durations, never from rounded display input.
        double year; stream >> year; long double integral = 0;
        for (int m = 0; m < 12; ++m) { double dt, tk; stream >> dt >> tk; integral += static_cast<long double>(dt) * tk; }
        c.temperature_c = static_cast<double>(integral / year - 273.15L);
        std::size_t count; stream >> count; c.neighbors.resize(count);
        for (int& id : c.neighbors) stream >> id;
        check(bool(stream), "truncated archived row");
    }
    Params params; params.radius_km = radius; params.float_precision = 8;
    derive_soils_biomes_resources(params, cells); derive_landforms(cells);
    auto legacy = params; legacy.temperature_model = ClimateTemperatureModel::legacy_empirical;
    const auto baseline = world(legacy, cells);
    const auto physical = cells;
    finalize_settlement_climate_applicability(params, cells);
    for (std::size_t i = 0; i < n; ++i) check(material(cells[i]) == material(physical[i]), "archive material changed");
    std::ofstream out(output);
    out << "{\"old_selection_on_same_seasonal_inputs\":" << baseline << ",\"seasonal_supported_selection\":" << world(params, cells) << "}";
    check(bool(out), "cannot write archive replay");
    std::cout << "archived " << n << " cells replayed without climate integration\n";
}

int main(int argc, char** argv) {
    try {
        if (argc == 3) archive(argv[1], argv[2]);
        else if (argc <= 2) units(argc == 2 ? argv[1] : nullptr);
        else throw std::runtime_error("usage: test [unit-artifact.json] | test archive-input.txt archive-output.json");
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
