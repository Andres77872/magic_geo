#include "engine/internal.hpp"
#include "engine/messagepack.hpp"
#include "engine/seasonal_climate_cache.hpp"
#include "engine/seasonal_climate_serialization.hpp"

#include <bit>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <stdexcept>

namespace {
using namespace magic_geo::detail;

void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

// Independent text-to-binary64 round trip, including every array element.
void check_numbers(const std::string& object, const char* key, const std::vector<double>& values, bool array = true) {
    const std::string prefix = std::string("\"") + key + "\":" + (array ? "[" : "");
    const auto start = object.find(prefix);
    require(start != std::string::npos, "missing serialized energy field");
    const char* cursor = object.c_str() + start + prefix.size();
    for (std::size_t i = 0; i < values.size(); ++i) {
        char* end = nullptr;
        const double parsed = std::strtod(cursor, &end);
        require(end != cursor, "energy field is not numeric");
        require(std::bit_cast<std::uint64_t>(parsed) == std::bit_cast<std::uint64_t>(values[i]),
                "energy serialization loses binary64 precision");
        cursor = end;
        if (i + 1 < values.size()) require(*cursor++ == ',', "missing energy array separator");
    }
    require(array ? *cursor == ']' : (*cursor == ',' || *cursor == '}'), "energy field has unexpected elements");
}

void check_record(const std::string& object, const PrescribedSeasonalClimate& state, std::size_t i) {
    const auto& column = state.physical_columns.columns[i];
    check_numbers(object, "area_m2", {column.area_m2}, false);
    check_numbers(object, "latitude_rad", {state.latitudes_rad[i]}, false);
    check_numbers(object, "heat_capacity_j_m2_k", {column.heat_capacity_j_m2_k}, false);
    check_numbers(object, "effective_longwave_emissivity", {column.longwave_emissivity}, false);
    std::vector<double> boundaries{state.solution.year.initial_temperature_k[i]};
    for (const auto& month : state.solution.year.months) boundaries.push_back(month.final_temperature_k[i]);
    check_numbers(object, "monthly_boundary_temperature_k", boundaries);
    const auto monthly = [&](const char* key, const std::vector<double> SurfaceEnergyMonth::* member) {
        std::vector<double> values;
        for (const auto& month : state.solution.year.months) values.push_back((month.*member)[i]);
        check_numbers(object, key, values);
    };
    monthly("monthly_mean_temperature_k", &SurfaceEnergyMonth::mean_temperature_k);
    monthly("monthly_mean_fourth_power_temperature_k4", &SurfaceEnergyMonth::mean_fourth_power_temperature_k4);
    monthly("monthly_absorbed_shortwave_w_m2", &SurfaceEnergyMonth::absorbed_shortwave_w_m2);
    monthly("monthly_emitted_longwave_w_m2", &SurfaceEnergyMonth::emitted_longwave_w_m2);
    monthly("monthly_horizontal_heat_convergence_w_m2", &SurfaceEnergyMonth::horizontal_heat_convergence_w_m2);
    monthly("monthly_heat_storage_tendency_w_m2", &SurfaceEnergyMonth::heat_storage_tendency_w_m2);
    monthly("monthly_balance_residual_w_m2", &SurfaceEnergyMonth::balance_residual_w_m2);
    monthly("monthly_balance_tolerance_w_m2", &SurfaceEnergyMonth::balance_tolerance_w_m2);
}

}  // namespace

int main(int argc, char** argv) {
    try {
        require(argc <= 2, "usage: seasonal_climate_serialization_test [witness.json]");
        PrescribedSeasonalClimateCache empty_cache;
        bool empty_rejected = false;
        try { (void)serialize_prescribed_seasonal_energy(empty_cache); }
        catch (const std::runtime_error&) { empty_rejected = true; }
        require(empty_rejected, "empty climate cache serialized a fabricated budget");

        for (const auto method : {SurfaceEnergyTimeMethod::tr_bdf2, SurfaceEnergyTimeMethod::backward_euler}) {
            PrescribedSeasonalClimateCache cache;
            magic_geo::Params params;
            params.cell_count = 12;
            auto cells = build_mesh(params);
            for (auto& cell : cells) cell.elevation_m = 1300.0 + 200.0 * cell.p.z;
            cells[0].is_water = true;
            cells[0].water_body = 2;
            cells[0].elevation_m = -7.123456789012345;
            cells[0].water_depth_m = -cells[0].elevation_m;
            PrescribedSeasonalClimateOptions options;
            options.integration.periodic.time_method = method;
            const auto& state = cache.solve(0, cells, options);
            const auto serialized = serialize_prescribed_seasonal_energy(cache);
            const auto witness = std::string("{\"climate_energy_model\":") + serialized.model +
                ",\"climate_energy_forcing_intervals\":" + serialized.forcing_intervals +
                ",\"climate_energy_transport_edges\":" + serialized.transport_edges +
                ",\"climate_energy_balance_records\":" + serialized.balance_records + '}';
            require(!json_to_messagepack(witness).empty(), "energy witness is not valid JSON/MessagePack input");
            std::size_t start = 1;
            for (std::size_t i = 0; i < cells.size(); ++i) {
                require(serialized.balance_records[start] == '{', "missing canonical energy record");
                const auto end = serialized.balance_records.find('}', start);
                require(end != std::string::npos, "unterminated energy record");
                const auto record = serialized.balance_records.substr(start, end - start + 1);
                check_numbers(record, "cell_id", {static_cast<double>(i)}, false);
                check_record(record, state, i);
                start = end + 2;
            }
            require(start == serialized.balance_records.size(), "incorrect energy cell coverage");
            check_numbers(serialized.model, "year_duration_seconds", {state.solution.year.duration_seconds}, false);
            check_numbers(serialized.model, "mean_surface_pressure_pa", {state.options.atmosphere.mean_surface_pressure_pa}, false);

            // Later lake/ecology source mutations cannot rewrite the retained
            // physical snapshot or its numerical evidence during serialization.
            cells[0].water_depth_m = 1000;
            cells[1].is_lake = true;
            cells[1].temperature_c = -999;
            const auto after = serialize_prescribed_seasonal_energy(cache);
            require(after.model == serialized.model && after.forcing_intervals == serialized.forcing_intervals &&
                    after.transport_edges == serialized.transport_edges && after.balance_records == serialized.balance_records,
                    "serialization reread mutable downstream surface state");
            if (argc == 2) {
                // The optional TR witness also has a separately solved BE sibling.
                const std::string suffix = method == SurfaceEnergyTimeMethod::backward_euler ? ".be.json" : "";
                std::ofstream file(std::string(argv[1]) + suffix);
                file << witness << '\n';
                require(static_cast<bool>(file), "could not write requested serialization witness");
            }
        }
        std::cout << "seasonal energy serialization round-trip checks passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
