#include "engine/seasonal_climate.hpp"
#include "engine/internal.hpp"

#include <algorithm>
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>

namespace {

using namespace magic_geo::detail;

void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

template <typename Callable>
void rejects(Callable&& callable, const char* message) {
    bool rejected = false;
    try { callable(); } catch (const std::exception&) { rejected = true; }
    require(rejected, message);
}

std::vector<Cell> mesh(int backend) {
    magic_geo::Params params;
    params.mesh_backend = backend;
    params.cell_count = 12;
    params.radius_km = 6371.0;
    return build_mesh(params);
}

void verify_monthly_replay(const PrescribedSeasonalClimate& climate) {
    const auto& year = climate.solution.year;
    const auto& columns = climate.physical_columns.columns;
    const auto& edges = climate.transport_edges;
    const double sigma = 5.670374419e-8;
    for (const auto& month : year.months) {
        std::vector<long double> transported_w(columns.size(), 0.0L);
        for (const auto& edge : edges) {
            const long double watts = static_cast<long double>(edge.conductance_w_k) *
                (static_cast<long double>(month.mean_temperature_k[edge.second_cell]) -
                    month.mean_temperature_k[edge.first_cell]);
            transported_w[edge.first_cell] += watts;
            transported_w[edge.second_cell] -= watts;
        }
        long double global_transport = 0.0L;
        for (std::size_t i = 0; i < columns.size(); ++i) {
            const double outgoing = columns[i].longwave_emissivity * sigma * month.mean_fourth_power_temperature_k4[i];
            const double storage = columns[i].heat_capacity_j_m2_k *
                (month.final_temperature_k[i] - month.initial_temperature_k[i]) / month.duration_seconds;
            const double transport = static_cast<double>(transported_w[i] / columns[i].area_m2);
            require(std::abs(outgoing - month.emitted_longwave_w_m2[i]) < 2.0e-9,
                "monthly fourth moment does not reconstruct outgoing radiation");
            require(std::abs(storage - month.heat_storage_tendency_w_m2[i]) < 2.0e-9,
                "monthly boundaries do not reconstruct storage");
            require(std::abs(transport - month.horizontal_heat_convergence_w_m2[i]) < 2.0e-9,
                "monthly mean temperatures do not reconstruct pair heat exchange");
            const double residual = storage - (month.absorbed_shortwave_w_m2[i] - outgoing + transport);
            require(std::abs(residual - month.balance_residual_w_m2[i]) < 5.0e-9,
                "monthly retained budget does not match its independent replay");
            global_transport += columns[i].area_m2 * static_cast<long double>(month.horizontal_heat_convergence_w_m2[i]);
        }
        require(std::abs(global_transport / climate.physical_columns.total_area_m2) < 1.0e-10,
            "monthly horizontal heat transfer fails global cancellation");
    }

    // Reconstruct the accepted source from retained shared nodes only. This
    // does not call SolarOrbitForcing or retain its dense source matrix.
    std::vector<SurfaceEnergyForcingInterval> replay_forcing;
    for (const auto& node : climate.forcing_intervals) {
        SurfaceEnergyForcingInterval interval;
        interval.month_index = static_cast<int>(node.month_index);
        interval.duration_seconds = climate.options.year_duration_seconds * node.duration_fraction_of_year;
        for (double latitude : climate.latitudes_rad) {
            interval.absorbed_shortwave_w_m2.push_back((1.0 - climate.options.top_of_atmosphere_albedo) *
                daily_mean_solar_insolation_w_m2(latitude, node.declination_rad,
                    1361.0 * climate.options.stellar_luminosity * node.inverse_square_distance_factor));
        }
        replay_forcing.push_back(std::move(interval));
    }
    const SurfaceEnergySystem system(columns, edges);
    const auto replay = solve_periodic_surface_energy_balance(system, replay_forcing,
        year.initial_temperature_k, climate.solution.accepted_periodic_options);
    for (std::size_t month = 0; month < 12; ++month) {
        require(replay.months[month].mean_temperature_k == year.months[month].mean_temperature_k,
            "retained phase/partition/source does not replay the accepted monthly temperatures exactly");
        if (replay.months[month].balance_residual_w_m2 != year.months[month].balance_residual_w_m2) {
            std::cerr << "replay mismatch backend " << climate.mesh_backend << " month " << month
                << " phase equal " << (replay.initial_temperature_k == year.initial_temperature_k)
                << " source equal " << (replay.months[month].absorbed_shortwave_w_m2 == year.months[month].absorbed_shortwave_w_m2)
                << " final equal " << (replay.months[month].final_temperature_k == year.months[month].final_temperature_k)
                << '\n';
            throw std::runtime_error("retained source does not replay the accepted monthly ledger exactly");
        }
    }
}

void airless_analytic_limit_on_both_meshes() {
    for (int backend : {0, 1}) {
        auto cells = mesh(backend);
        PrescribedSeasonalClimateOptions options;
        options.atmosphere.mean_surface_pressure_pa = 0.0;
        options.axial_tilt_deg = 0.0;
        options.orbital_eccentricity = 0.0;
        const auto climate = solve_prescribed_seasonal_climate(backend, cells, options);
        require(climate.transport_edges.empty(), "airless world has atmospheric heat transfer");
        require(climate.solution.monthly_refinement_confirmations == 2, "monthly accuracy checks were skipped");
        for (std::size_t i = 0; i < cells.size(); ++i) {
            const double absorbed = 0.7 * 1361.0 * std::cos(cells[i].lat) / PI;
            const double expected = std::sqrt(std::sqrt(absorbed / 5.670374419e-8));
            for (const auto& month : climate.solution.year.months) {
                require(std::abs(month.mean_temperature_k[i] - expected) < 2.0e-7,
                    "airless circular zero-tilt climate disagrees with analytic gray equilibrium");
            }
        }
        verify_monthly_replay(climate);
    }
}

void actual_terrain_inputs_and_changed_geography() {
    auto cells = mesh(0);
    for (auto& cell : cells) {
        if (cell.p.x > 0.0) {
            cell.is_water = true;
            cell.water_body = 1;
            cell.elevation_m = -(8.0 + 800.0 * (1.0 + cell.p.y));
            cell.water_depth_m = -cell.elevation_m;
        } else cell.elevation_m = 1500.0 + 1000.0 * cell.p.z;
        cell.temperature_c = -123.0;
        cell.temperature_monthly_c.fill(-123.0);
        cell.biome = 99; // Later diagnostics cannot influence prescribed inputs.
    }
    const auto climate = solve_prescribed_seasonal_climate(0, cells);
    require(!climate.transport_edges.empty(), "atmospheric columns were not connected");
    require(std::abs(climate.physical_columns.mean_surface_pressure_residual_pa) < 1.0e-8,
        "terrain pressure normalization changes atmospheric mass");
    require(climate.atmospheric_scale_height_to_radius > 0.0 &&
        climate.maximum_interface_elevation_to_radius > 0.0, "applicability diagnostics are missing");
    for (std::size_t i = 0; i < cells.size(); ++i) {
        require(cells[i].temperature_c == -123.0 && cells[i].temperature_monthly_c[0] == -123.0,
            "composition mutated downstream cell fields");
        require(climate.surfaces[i].interface_elevation_m == (cells[i].is_water ? 0.0 : cells[i].elevation_m),
            "surface interface snapshot used a marine seabed height");
    }
    verify_monthly_replay(climate);

    // A changed shallow sea needs new storage even with unchanged atmospheric
    // interface. The prior phase is only a starting iterate for this new map.
    const auto first_marine = std::find_if(cells.begin(), cells.end(), [](const auto& cell) { return cell.is_water; });
    require(first_marine != cells.end(), "test has no marine cell");
    const auto marine_id = static_cast<std::size_t>(first_marine->id);
    first_marine->elevation_m = -2.0;
    first_marine->water_depth_m = 2.0;
    const auto updated = solve_prescribed_seasonal_climate(0, cells, {}, climate.solution.year.initial_temperature_k);
    require(updated.surfaces[marine_id].surface_heat_capacity_j_m2_k == 2.0 * 4.1813e6,
        "changed shallow-water storage was not rebuilt");
    require(updated.physical_columns.surface_pressure_pa == climate.physical_columns.surface_pressure_pa,
        "marine seabed depth changed atmospheric pressure");
    require(updated.solution.monthly_refinement_confirmations == 2, "warm phase skipped new climate verification");
    verify_monthly_replay(updated);
}

void explicit_boundaries_and_work_limits() {
    const auto cells = mesh(0);
    PrescribedSeasonalClimateOptions options;
    options.radius_m *= 2.0;
    rejects([&] { solve_prescribed_seasonal_climate(0, cells, options); }, "wrong physical radius was accepted");
    options = {};
    options.top_of_atmosphere_albedo = 1.01;
    rejects([&] { solve_prescribed_seasonal_climate(0, cells, options); }, "invalid albedo was accepted");
    options = {};
    options.maximum_stored_forcing_values = 0;
    rejects([&] { solve_prescribed_seasonal_climate(0, cells, options); }, "dense forcing budget was ignored");
    options = {};
    options.integration.maximum_accepted_steps_per_year = 2;
    rejects([&] { solve_prescribed_seasonal_climate(0, cells, options); }, "forcing preflight step budget was ignored");
    options = {};
    options.stellar_luminosity = std::numeric_limits<double>::denorm_min();
    options.top_of_atmosphere_albedo = std::nextafter(1.0, 0.0);
    rejects([&] { solve_prescribed_seasonal_climate(0, cells, options); }, "positive absorption underflow became exact darkness");
    auto malformed = cells;
    malformed[0].lat += 0.1;
    rejects([&] { solve_prescribed_seasonal_climate(0, malformed); }, "inconsistent source latitude was accepted");
    malformed = cells;
    malformed[0].is_lake = true;
    rejects([&] { solve_prescribed_seasonal_climate(0, malformed); }, "stale lake state was accepted");
    rejects([&] { solve_prescribed_seasonal_climate(0, cells, {}, {288.0}); }, "wrong initial phase shape was accepted");
    std::vector<double> invalid(cells.size(), -1.0);
    rejects([&] { solve_prescribed_seasonal_climate(0, cells, {}, invalid); }, "negative phase guess was accepted");
    options = {};
    options.top_of_atmosphere_albedo = 1.0;
    const auto reflected = solve_prescribed_seasonal_climate(0, cells, options, std::vector<double>(cells.size(), 300.0));
    for (double temperature : reflected.solution.year.initial_temperature_k) {
        require(temperature == 0.0, "perfect reflection retained an arbitrary warm periodic root");
    }
}

}  // namespace

int main() {
    try {
        airless_analytic_limit_on_both_meshes();
        actual_terrain_inputs_and_changed_geography();
        explicit_boundaries_and_work_limits();
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
    return 0;
}
