// Standalone research adapter benchmark; never mutates production generation.
// Build (C++20, e.g. g++ -O2 -ffp-contract=off -Icpp/include -Icpp/src):
// this file + engine/{seasonal_climate,physical_columns,climate_transport,mesh,
// core,solar_insolation,seasonal_energy_balance,time_integrated_energy,
// periodic_energy_balance,adaptive_energy_balance}.cpp.
// The CSV can be extracted with Python csv.writer from an existing world's
// cells: [id,*position_3d,area_km2,elevation_m,int(is_water),int(is_lake)].
// Write the exact header documented by --help. Retain the world/config beside
// the CSV under an ignored runs/research directory to preserve provenance.

#include "engine/climate_transport.hpp"
#include "engine/internal.hpp"
#include "engine/seasonal_climate.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <queue>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
using namespace magic_geo::detail;
using Clock = std::chrono::steady_clock;
constexpr double sigma = 5.670374419e-8;
constexpr const char* csv_header = "id,x,y,z,area_km2,elevation_m,is_water,is_lake";
constexpr const char* help = R"HELP(Prescribed climate benchmark on genuine exported terrain.

Required: --surface-csv PATH
CSV header: id,x,y,z,area_km2,elevation_m,is_water,is_lake
Rows must be canonical numeric cell records; flags must be 0 or 1. Mesh positions
and areas are rebuilt from the declared settings and checked against every row.

  --inland-water-as-land       Explicitly permit final lakes as prescribed land.
  --backend fibonacci|geodesic Mesh backend (default fibonacci).
  --seed N                    Original mesh seed (default 424242).
  --neighbors N               Original neighbor count (default 7).
  --radius-km R               Original planet radius (default 6371).
  --pressure-bar P            Mean surface pressure (default 1).
  --gravity-g G               Gravity relative to 9.80665 m/s2 (default 1).
  --tau T                     Reference infrared optical depth (default 1).
  --greenhouse-factor G       Opacity multiplier (default 1).
  --profile-temperature-k T   Fixed hydrostatic profile temperature (288.15).
  --tilt-deg T                Obliquity (default 23.5).
  --eccentricity E            Orbital eccentricity (default .016).
  --luminosity L              Incident stellar factor (default 1).
  --forcing-refinement N      Astronomical integration level (default 0).
  --changed-depth-m D         Perturbed coastal water depth (default 10).
  --help                     Print this help.

Runs three separately verified adaptive TR-BDF2 periodic solves: initial local
radiative-equilibrium guess, unchanged warm repeat, and warm restart after a
coastal depth change. A second, deep marine bed is adjusted to preserve the
actual area-weighted water volume; its >=50m thermal slab remains unchanged.
The marine mask stays fixed. No lake/ice/cloud feedback or production climate
is generated. Albedo=.3, marine maximum slab=50m, dry slab=4e6 J/m2/K,
atmospheric diffusivity=2.2e6 m2/s, year=365.2422 days. Default adaptive local
tolerance 1e-4 K and monthly .01 K/.05 W/m2 gates with two confirmations apply.
Those gates assess thermal timesteps, not independent astronomical refinement.
Prints one compact JSON object per completed solve. Exit 0 success, 1 solve/input
failure, 2 invalid CLI. Generated CSV/world/JSONL outputs belong under runs/.
)HELP";

double number(const std::string& value) {
    std::size_t used = 0;
    const double result = std::stod(value, &used);
    if (used != value.size() || !std::isfinite(result)) throw std::invalid_argument("expected finite number");
    return result;
}

std::uint64_t integer(const std::string& value) {
    if (value.empty() || value.front() == '-') throw std::invalid_argument("expected nonnegative integer");
    std::size_t used = 0;
    const auto result = std::stoull(value, &used);
    if (used != value.size()) throw std::invalid_argument("expected integer");
    return result;
}

std::string quoted(const std::string& value) {
    std::string result = "\"";
    for (unsigned char c : value) {
        if (c == '"' || c == '\\') { result += '\\'; result += static_cast<char>(c); }
        else if (c == '\n') result += "\\n";
        else if (c == '\r') result += "\\r";
        else if (c == '\t') result += "\\t";
        else if (c < 32) throw std::runtime_error("unprintable JSON string");
        else result += static_cast<char>(c);
    }
    return result + '"';
}

struct SurfaceRow { int id; Vec3 p; double area_km2, elevation_m; bool marine, lake; };

std::vector<SurfaceRow> read_csv(const std::string& path) {
    std::ifstream file(path);
    std::string line;
    if (!std::getline(file, line)) throw std::runtime_error("cannot read surface CSV");
    if (!line.empty() && line.back() == '\r') line.pop_back();
    if (line != csv_header) throw std::runtime_error("unexpected surface CSV header");
    std::vector<SurfaceRow> rows;
    while (std::getline(file, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.empty()) throw std::runtime_error("empty surface CSV row");
        std::vector<double> fields;
        std::istringstream row(line);
        std::string field;
        while (std::getline(row, field, ',')) fields.push_back(number(field));
        if (fields.size() != 8 || line.back() == ',' || fields[0] != static_cast<double>(rows.size()) ||
            (fields[6] != 0 && fields[6] != 1) || (fields[7] != 0 && fields[7] != 1)) {
            throw std::runtime_error("malformed/noncanonical surface CSV row");
        }
        if (rows.size() >= static_cast<std::size_t>(std::numeric_limits<int>::max())) {
            throw std::runtime_error("surface CSV cell count exceeds index range");
        }
        rows.push_back({static_cast<int>(rows.size()), {fields[1],fields[2],fields[3]},
                       fields[4],fields[5],fields[6] == 1,fields[7] == 1});
    }
    if (rows.size() < 12) throw std::runtime_error("surface CSV requires at least 12 cells");
    return rows;
}

void label_marine(std::vector<Cell>& cells) {
    // Match the native label_marine_water_bodies connectivity/count convention.
    std::vector<int> component(cells.size(), -1), sizes;
    for (std::size_t i = 0; i < cells.size(); ++i) {
        if (!cells[i].is_water || component[i] >= 0) continue;
        const int id = static_cast<int>(sizes.size());
        int size = 0;
        std::queue<int> pending;
        pending.push(static_cast<int>(i)); component[i] = id;
        while (!pending.empty()) {
            const int cell = pending.front(); pending.pop(); ++size;
            for (int neighbor : cells[static_cast<std::size_t>(cell)].neighbors) {
                if (cells[static_cast<std::size_t>(neighbor)].is_water && component[static_cast<std::size_t>(neighbor)] < 0) {
                    component[static_cast<std::size_t>(neighbor)] = id; pending.push(neighbor);
                }
            }
        }
        sizes.push_back(size);
    }
    const int largest = sizes.empty() ? -1 : static_cast<int>(std::max_element(sizes.begin(), sizes.end()) - sizes.begin());
    for (std::size_t i = 0; i < cells.size(); ++i) {
        cells[i].water_body = !cells[i].is_water ? 0 : component[i] == largest
            ? (cells[i].water_depth_m < 220.0 ? 2 : 1) : 3;
    }
}

long double water_volume_km3(const std::vector<Cell>& cells) {
    long double result = 0;
    for (const auto& cell : cells) if (cell.is_water) result += static_cast<long double>(cell.area_km2) * cell.water_depth_m / 1000;
    return result;
}

double maximum_month_difference(const PrescribedSeasonalClimate& first, const PrescribedSeasonalClimate& second) {
    double maximum = 0;
    for (std::size_t m=0;m<12;++m) for (std::size_t i=0;i<first.surfaces.size();++i) {
        maximum = std::max(maximum, std::abs(first.solution.year.months[m].mean_temperature_k[i] -
                                            second.solution.year.months[m].mean_temperature_k[i]));
    }
    return maximum;
}

void report(const std::string& run, const std::string& csv, const PrescribedSeasonalClimate& state,
            double seconds, const std::vector<Cell>& cells, std::uint64_t seed, int neighbor_count,
            int original_lakes, double lake_area, int coastal, int compensation, double original_depth,
            long double initial_volume, const PrescribedSeasonalClimate* comparison) {
    const auto& columns = state.physical_columns;
    const auto& adaptive = state.solution;
    const auto& year = adaptive.year;
    long double mean_temperature=0, absorbed=0, emitted=0, storage=0, transport=0, residual=0;
    double replay_radiation=0,replay_storage=0,replay_transport=0,replay_residual=0,monthly_transport=0;
    double minimum_temperature=std::numeric_limits<double>::infinity(),maximum_temperature=0;
    double pressure_min=std::numeric_limits<double>::infinity(),pressure_max=0;
    long double marine_area=0;
    for (std::size_t i=0;i<cells.size();++i) {
        pressure_min=std::min(pressure_min,columns.surface_pressure_pa[i]);
        pressure_max=std::max(pressure_max,columns.surface_pressure_pa[i]);
        if (cells[i].is_water) marine_area+=columns.columns[i].area_m2;
    }
    for (const auto& month : year.months) {
        std::vector<long double> watts(cells.size(),0);
        for (const auto& edge : state.transport_edges) {
            const auto i=static_cast<std::size_t>(edge.first_cell),j=static_cast<std::size_t>(edge.second_cell);
            const long double exchange=static_cast<long double>(edge.conductance_w_k)*
                (static_cast<long double>(month.mean_temperature_k[j])-month.mean_temperature_k[i]);
            watts[i]+=exchange; watts[j]-=exchange;
        }
        long double month_watts=0;
        for (std::size_t i=0;i<cells.size();++i) {
            const long double area=columns.columns[i].area_m2;
            const long double weight=area*month.duration_seconds/year.duration_seconds;
            mean_temperature+=weight*month.mean_temperature_k[i];
            absorbed+=weight*month.absorbed_shortwave_w_m2[i];
            emitted+=weight*month.emitted_longwave_w_m2[i];
            storage+=weight*month.heat_storage_tendency_w_m2[i];
            transport+=weight*month.horizontal_heat_convergence_w_m2[i];
            residual+=weight*month.balance_residual_w_m2[i];
            month_watts+=area*month.horizontal_heat_convergence_w_m2[i];
            minimum_temperature=std::min(minimum_temperature,month.mean_temperature_k[i]);
            maximum_temperature=std::max(maximum_temperature,month.mean_temperature_k[i]);
            const long double replay_olr=static_cast<long double>(columns.columns[i].longwave_emissivity)*sigma*
                month.mean_fourth_power_temperature_k4[i];
            const long double replay_store=static_cast<long double>(columns.columns[i].heat_capacity_j_m2_k)*
                (static_cast<long double>(month.final_temperature_k[i])-month.initial_temperature_k[i])/month.duration_seconds;
            const long double replay_heat=watts[i]/area;
            replay_radiation=std::max(replay_radiation,static_cast<double>(std::abs(replay_olr-month.emitted_longwave_w_m2[i])));
            replay_storage=std::max(replay_storage,static_cast<double>(std::abs(replay_store-month.heat_storage_tendency_w_m2[i])));
            replay_transport=std::max(replay_transport,static_cast<double>(std::abs(replay_heat-month.horizontal_heat_convergence_w_m2[i])));
            replay_residual=std::max(replay_residual,static_cast<double>(std::abs(
                replay_store-month.absorbed_shortwave_w_m2[i]+replay_olr-replay_heat-month.balance_residual_w_m2[i])));
        }
        monthly_transport=std::max(monthly_transport,static_cast<double>(std::abs(month_watts/columns.total_area_m2)));
    }
    std::cout<<std::setprecision(16)<<"{\"run\":"<<quoted(run)<<",\"surface_csv\":"<<quoted(csv)
      <<",\"model\":\"prescribed_hydrostatic_gray_marine_land_columns_v1\",\"status\":\"converged\""
      <<",\"cells\":"<<cells.size()<<",\"seed\":"<<seed<<",\"neighbor_count\":"<<neighbor_count
      <<",\"mesh_backend\":"<<state.mesh_backend<<",\"mesh_geometry\":\"rebuilt_and_checked_against_exported_positions_and_areas\""
      <<",\"original_lakes_treated_as_prescribed_land\":"<<original_lakes<<",\"original_lake_area_km2\":"<<lake_area
      <<",\"seconds\":"<<seconds<<",\"radius_m\":"<<state.options.radius_m
      <<",\"pressure_mean_pa\":"<<state.options.atmosphere.mean_surface_pressure_pa
      <<",\"gravity_m_s2\":"<<state.options.atmosphere.gravity_m_s2
      <<",\"profile_temperature_k\":"<<state.options.atmosphere.profile_temperature_k
      <<",\"reference_infrared_optical_depth\":"<<state.options.atmosphere.reference_infrared_optical_depth
      <<",\"greenhouse_factor\":"<<state.options.atmosphere.greenhouse_factor
      <<",\"toa_albedo\":"<<state.options.top_of_atmosphere_albedo
      <<",\"atmospheric_diffusivity_m2_s\":"<<state.options.atmosphere.atmospheric_diffusivity_m2_s
      <<",\"tilt_deg\":"<<state.options.axial_tilt_deg<<",\"eccentricity\":"<<state.options.orbital_eccentricity
      <<",\"luminosity\":"<<state.options.stellar_luminosity<<",\"year_seconds\":"<<state.options.year_duration_seconds
      <<",\"forcing_refinement_level\":"<<state.options.forcing_refinement_level<<",\"forcing_intervals\":"<<state.forcing_intervals.size()
      <<",\"pressure_min_pa\":"<<pressure_min<<",\"pressure_max_pa\":"<<pressure_max
      <<",\"mean_pressure_residual_pa\":"<<columns.mean_surface_pressure_residual_pa
      <<",\"atmospheric_mass_kg\":"<<columns.total_atmospheric_mass_kg<<",\"atmospheric_mass_residual_kg\":"<<columns.atmospheric_mass_residual_kg
      <<",\"marine_area_fraction\":"<<static_cast<double>(marine_area/columns.total_area_m2)
      <<",\"marine_water_volume_km3\":"<<static_cast<double>(water_volume_km3(cells))
      <<",\"water_volume_change_km3\":"<<static_cast<double>(water_volume_km3(cells)-initial_volume)
      <<",\"coastal_cell_id\":"<<coastal<<",\"compensating_deep_cell_id\":"<<compensation
      <<",\"original_coastal_depth_m\":"<<original_depth<<",\"current_coastal_depth_m\":"<<cells[static_cast<std::size_t>(coastal)].water_depth_m
      <<",\"coastal_surface_heat_capacity_j_m2_k\":"<<state.surfaces[static_cast<std::size_t>(coastal)].surface_heat_capacity_j_m2_k
      <<",\"compensating_deep_depth_m\":"<<cells[static_cast<std::size_t>(compensation)].water_depth_m
      <<",\"compensating_surface_heat_capacity_j_m2_k\":"<<state.surfaces[static_cast<std::size_t>(compensation)].surface_heat_capacity_j_m2_k
      <<",\"maximum_phase_difference_k\":"<<year.maximum_phase_difference_k
      <<",\"maximum_annual_net_heating_w_m2\":"<<year.maximum_annual_net_heating_w_m2
      <<",\"mean_temperature_c\":"<<static_cast<double>(mean_temperature/columns.total_area_m2)-273.15
      <<",\"minimum_monthly_temperature_c\":"<<minimum_temperature-273.15<<",\"maximum_monthly_temperature_c\":"<<maximum_temperature-273.15
      <<",\"global_absorbed_w_m2\":"<<static_cast<double>(absorbed/columns.total_area_m2)
      <<",\"global_emitted_w_m2\":"<<static_cast<double>(emitted/columns.total_area_m2)
      <<",\"global_asr_minus_olr_w_m2\":"<<static_cast<double>((absorbed-emitted)/columns.total_area_m2)
      <<",\"global_storage_w_m2\":"<<static_cast<double>(storage/columns.total_area_m2)
      <<",\"global_transport_w_m2\":"<<static_cast<double>(transport/columns.total_area_m2)
      <<",\"global_balance_residual_w_m2\":"<<static_cast<double>(residual/columns.total_area_m2)
      <<",\"maximum_month_global_transport_w_m2\":"<<monthly_transport
      <<",\"replay_max_olr_difference_w_m2\":"<<replay_radiation<<",\"replay_max_storage_difference_w_m2\":"<<replay_storage
      <<",\"replay_max_transport_difference_w_m2\":"<<replay_transport<<",\"replay_max_residual_difference_w_m2\":"<<replay_residual
      <<",\"accepted_steps_per_year\":"<<year.integration_step_count<<",\"total_step_attempts\":"<<adaptive.total_step_attempts
      <<",\"total_periodic_year_evaluations\":"<<adaptive.total_periodic_year_evaluations
      <<",\"maximum_local_error_ratio\":"<<adaptive.maximum_local_error_ratio<<",\"maximum_numerical_error_ratio\":"<<adaptive.maximum_numerical_error_ratio
      <<",\"monthly_temperature_gate_k\":"<<state.options.integration.monthly_temperature_tolerance_k
      <<",\"monthly_flux_gate_w_m2\":"<<state.options.integration.monthly_flux_tolerance_w_m2
      <<",\"monthly_refinement_confirmations\":"<<adaptive.monthly_refinement_confirmations
      <<",\"maximum_monthly_temperature_change_k\":"<<adaptive.maximum_monthly_temperature_change_k
      <<",\"maximum_monthly_flux_change_w_m2\":"<<adaptive.maximum_monthly_flux_change_w_m2
      <<",\"atmospheric_scale_height_to_radius\":"<<state.atmospheric_scale_height_to_radius
      <<",\"maximum_interface_elevation_to_radius\":"<<state.maximum_interface_elevation_to_radius;
    if (comparison) {
        double pressure_difference=0;
        int changed_capacity_count=0;
        for (std::size_t i=0;i<cells.size();++i) {
            pressure_difference=std::max(pressure_difference,std::abs(columns.surface_pressure_pa[i]-comparison->physical_columns.surface_pressure_pa[i]));
            if (columns.columns[i].heat_capacity_j_m2_k!=comparison->physical_columns.columns[i].heat_capacity_j_m2_k) ++changed_capacity_count;
        }
        std::cout<<",\"maximum_monthly_temperature_difference_from_initial_k\":"<<maximum_month_difference(state,*comparison)
                 <<",\"maximum_pressure_difference_from_initial_pa\":"<<pressure_difference
                 <<",\"changed_column_heat_capacity_count\":"<<changed_capacity_count;
    }
    std::cout<<"}\n"<<std::flush;
}
}  // namespace

int main(int argc,char** argv) {
    magic_geo::Params mesh;
    PrescribedSeasonalClimateOptions options;
    std::string path;
    bool inland_as_land=false;
    double changed_depth=10.0;
    try {
        for (int i=1;i<argc;++i) {
            const std::string arg=argv[i];
            if (arg=="--help") { std::cout<<help; return 0; }
            if (arg=="--inland-water-as-land") { inland_as_land=true; continue; }
            if (++i==argc) throw std::invalid_argument("missing value for "+arg);
            const std::string value=argv[i];
            if (arg=="--surface-csv") path=value;
            else if (arg=="--backend") {
                if (value=="fibonacci") mesh.mesh_backend=MESH_BACKEND_FIBONACCI;
                else if (value=="geodesic") mesh.mesh_backend=MESH_BACKEND_GEODESIC_ICOSAHEDRON;
                else throw std::invalid_argument("unknown backend");
            } else if (arg=="--seed") mesh.seed=integer(value);
            else if (arg=="--neighbors") {
                const auto n=integer(value);
                if (n<3 || n>64) throw std::invalid_argument("neighbors must be 3..64");
                mesh.neighbor_count=static_cast<int>(n);
            } else if (arg=="--radius-km") options.radius_m=number(value)*1000;
            else if (arg=="--pressure-bar") options.atmosphere.mean_surface_pressure_pa=number(value)*100000;
            else if (arg=="--gravity-g") options.atmosphere.gravity_m_s2=number(value)*CLIMATE_REFERENCE_GRAVITY_M_S2;
            else if (arg=="--tau") options.atmosphere.reference_infrared_optical_depth=number(value);
            else if (arg=="--greenhouse-factor") options.atmosphere.greenhouse_factor=number(value);
            else if (arg=="--profile-temperature-k") options.atmosphere.profile_temperature_k=number(value);
            else if (arg=="--tilt-deg") options.axial_tilt_deg=number(value);
            else if (arg=="--eccentricity") options.orbital_eccentricity=number(value);
            else if (arg=="--luminosity") options.stellar_luminosity=number(value);
            else if (arg=="--forcing-refinement") {
                const auto n=integer(value);
                if (n>10) throw std::invalid_argument("forcing refinement must be 0..10");
                options.forcing_refinement_level=static_cast<int>(n);
            } else if (arg=="--changed-depth-m") changed_depth=number(value);
            else throw std::invalid_argument("unknown option "+arg);
        }
        if (path.empty()) throw std::invalid_argument("--surface-csv is required");
        if (!(changed_depth>0 && changed_depth<50)) throw std::invalid_argument("changed depth must be positive and below 50 m");
        if (!(options.radius_m>0) || !std::isfinite(options.radius_m)) throw std::invalid_argument("radius must be positive and finite");
    } catch (const std::exception& e) { std::cerr<<e.what()<<'\n'; return 2; }
    try {
        const auto rows=read_csv(path);
        mesh.cell_count=static_cast<int>(rows.size()); mesh.radius_km=options.radius_m/1000;
        auto cells=build_mesh(mesh);
        if (cells.size()!=rows.size()) throw std::runtime_error("rebuilt mesh cell count differs from CSV");
        int lake_count=0;
        long double lake_area=0;
        for (std::size_t i=0;i<cells.size();++i) {
            const auto& row=rows[i]; auto& cell=cells[i];
            if (!(row.area_km2>0) || std::hypot(cell.p.x-row.p.x,cell.p.y-row.p.y,cell.p.z-row.p.z)>1e-12 ||
                std::abs(cell.area_km2-row.area_km2)>1e-12*cell.area_km2) {
                throw std::runtime_error("exported positions/areas do not match rebuilt mesh");
            }
            if (row.lake) { ++lake_count; lake_area+=row.area_km2; }
            if (row.lake && row.marine) throw std::runtime_error("CSV cell is both marine and inland lake");
            if (row.lake && !inland_as_land) throw std::runtime_error("lake rows require explicit --inland-water-as-land");
            cell.elevation_m=row.elevation_m; cell.is_water=row.marine;
            cell.water_depth_m=row.marine ? -row.elevation_m : 0;
            cell.is_lake=false;  // Explicit prescribed continental-surface experiment.
        }
        label_marine(cells);
        int coastal=-1,compensation=-1;
        for (const auto& cell:cells) {
            if (!cell.is_water) continue;
            const bool touches_land=std::any_of(cell.control_volume_edge_neighbor_ids.begin(),cell.control_volume_edge_neighbor_ids.end(),
                [&](int id){return !cells[static_cast<std::size_t>(id)].is_water;});
            if (touches_land && (coastal<0 || cell.water_depth_m<cells[static_cast<std::size_t>(coastal)].water_depth_m)) coastal=cell.id;
        }
        for (const auto& cell:cells) if (cell.is_water && cell.id!=coastal && cell.water_depth_m>50 &&
            (compensation<0 || cell.water_depth_m>cells[static_cast<std::size_t>(compensation)].water_depth_m)) compensation=cell.id;
        if (coastal<0 || compensation<0) throw std::runtime_error("terrain lacks distinct coastal and deep marine witnesses");
        const double old_depth=cells[static_cast<std::size_t>(coastal)].water_depth_m;
        if (old_depth==changed_depth) throw std::runtime_error("requested coastal depth is unchanged");
        const long double volume=water_volume_km3(cells);
        auto stamp=Clock::now();
        const auto initial=solve_prescribed_seasonal_climate(mesh.mesh_backend,cells,options);
        report("initial",path,initial,std::chrono::duration<double>(Clock::now()-stamp).count(),cells,mesh.seed,mesh.neighbor_count,
               lake_count,static_cast<double>(lake_area),coastal,compensation,old_depth,volume,nullptr);
        stamp=Clock::now();
        const auto warm=solve_prescribed_seasonal_climate(mesh.mesh_backend,cells,options,initial.solution.year.initial_temperature_k);
        report("unchanged_warm",path,warm,std::chrono::duration<double>(Clock::now()-stamp).count(),cells,mesh.seed,mesh.neighbor_count,
               lake_count,static_cast<double>(lake_area),coastal,compensation,old_depth,volume,&initial);
        auto& coast=cells[static_cast<std::size_t>(coastal)]; auto& deep=cells[static_cast<std::size_t>(compensation)];
        const long double displaced=static_cast<long double>(coast.area_km2)*(old_depth-changed_depth);
        const double new_deep=static_cast<double>(static_cast<long double>(deep.water_depth_m)+displaced/deep.area_km2);
        if (!std::isfinite(new_deep) || !(new_deep>50)) throw std::runtime_error("volume-compensating cell would leave deep-slab regime");
        coast.water_depth_m=changed_depth; coast.elevation_m=-changed_depth;
        deep.water_depth_m=new_deep; deep.elevation_m=-new_deep;
        label_marine(cells);
        stamp=Clock::now();
        const auto changed=solve_prescribed_seasonal_climate(mesh.mesh_backend,cells,options,initial.solution.year.initial_temperature_k);
        report("changed_depth_warm",path,changed,std::chrono::duration<double>(Clock::now()-stamp).count(),cells,mesh.seed,mesh.neighbor_count,
               lake_count,static_cast<double>(lake_area),coastal,compensation,old_depth,volume,&initial);
    } catch (const std::exception& e) {
        std::cout<<"{\"status\":\"failed\",\"error\":"<<quoted(e.what())<<"}\n"; return 1;
    }
}
